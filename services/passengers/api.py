"""Private HTTP API. API Gateway verifies token signature, issuer, client and scopes."""

import base64
import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from botocore.exceptions import ClientError

from services.forecast.api import RequestError
from services.forecast.schema import SCORER, utc_text
from services.passengers.domain import flight_input, identifier, identity, subscription
from services.passengers.journey import detail, flight_or_missing, reminder
from services.passengers.preferences import DEFAULTS, settings_patch
from services.passengers.sharing import read_link, set_link
from services.passengers.store import PassengerStore
from services.pipeline import runtime
from services.pipeline.contract import AVAILABLE, REPLAYS, job_spec, send_event
from services.pipeline.jobs import phase

log = logging.getLogger(__name__)
READ = "skycalm/flights.read"
WRITE = "skycalm/flights.write"
PREF = "skycalm/notifications.write"
ADMIN = "skycalm/admin"
FLIGHT_FIELDS = (
    "slot",
    "flightNumber",
    "arrivalScheduled",
    "id",
    "revision",
    "origin",
    "destination",
    "departure",
    "arrival",
    "watch",
    "assessment",
    "baseline",
    "forecastAt",
    "ribbon",
    "expiresAt",
)
NOTICE_FIELDS = (
    "noticeId",
    "kind",
    "created",
    "slot",
    "delivery",
    "deliveredAt",
    "peak",
    "flightRevision",
    "flightId",
    "routeLabel",
    "runMarker",
    "isRead",
    "sentBody",
)
SEEDS = (("EDI", "OPO", 12), ("AMS", "LHR", 26), ("BCN", "ARN", 30))


def public_row(row, fields):
    return {k: row[k] for k in fields if k in row}


def public_preferences(prefs: dict) -> dict:
    return {
        **{k: prefs.get(k, v) for k, v in DEFAULTS.items()},
        "push": bool(prefs.get("device")),
        "email": bool(prefs.get("email")),
        "explainAlerts": prefs.get("explainAlerts") is True,
    }


def view(store, owner, now):
    rows = list(store.rows(owner, now))
    prefs = next((x.get("prefs", {}) for x in rows if x["sk"] == "account"), {})
    flights = [x for x in rows if x["sk"].startswith("flight#")]
    revisions = {f["revision"]: f for f in flights}
    for row in rows:
        # Pre-7D notices only have a revision. A reused slot must never link to a new passenger trip.
        previous = revisions.get(row.get("flightRevision"))
        if row["sk"].startswith("notice#") and previous and previous["slot"] == row.get("slot"):
            row.setdefault("flightId", previous["id"])
            row.setdefault("routeLabel", previous["origin"] + " → " + previous["destination"])
    return {
        "flights": [
            {**public_row(x, FLIGHT_FIELDS), "nextReminder": reminder(x["departureEpoch"], now)}
            for x in flights
        ],
        "inbox": sorted(
            (public_row(x, NOTICE_FIELDS) for x in rows if x["sk"].startswith("notice#")),
            key=lambda n: n["created"],
            reverse=True,
        ),
        "preferences": public_preferences(prefs),
    }


def identity_attributes(event, clients):
    bearer = event.get("headers", {}).get("authorization", "").split()
    if len(bearer) != 2 or bearer[0].lower() != "bearer":
        raise RequestError("unauthorized", "Please sign in again.", 401)
    user = clients("cognito-idp").get_user(AccessToken=bearer[1])
    return {a["Name"]: a["Value"] for a in user["UserAttributes"]}


def verified_email(event, clients):
    recipient = os.environ.get("SES_RECIPIENT", "")
    if not recipient:
        raise RequestError("email_unavailable", "Classroom email delivery is not configured.")
    invited = os.environ.get("CLASSROOM_EMAIL", recipient).strip().casefold()
    attrs = identity_attributes(event, clients)
    if (
        not invited
        or attrs.get("email_verified") != "true"
        or attrs.get("email", "").strip().casefold() != invited
    ):
        raise RequestError(
            "email_unavailable",
            "Verify the invited sign-in address to enable classroom email.",
            422,
        )
    return recipient


def admin_action(path, method, body, owner, store, now, clients):
    if path == "/api/admin/health" and method == "GET":
        queue = clients("sqs")
        counts = {}
        for name, url in json.loads(os.environ["HEALTH_QUEUES"]).items():
            attr = queue.get_queue_attributes(
                QueueUrl=url,
                AttributeNames=[
                    "ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible",
                ],
            )["Attributes"]
            counts[name] = sum(int(n) for n in attr.values())
        job = runtime.table().get_item(Key={"pk": "active"}, ConsistentRead=True).get("Item", {})
        weather = runtime.weather()
        last = weather.latest()
        try:
            manifest = weather.published_manifest(last) if last else None
        except ClientError as exc:
            # S3 can return 403 for an expired key when this role cannot list the bucket.
            if exc.response["Error"]["Code"] not in {"403", "AccessDenied"}:
                raise
            log.info(json.dumps({"event": "health.manifest.unavailable", "runId": last}))
            manifest = None
        observation = weather.table.get_item(
            Key={"pk": "observations#awc"}, ConsistentRead=True
        ).get("Item", {})
        notices = view(store, owner, int(now.timestamp()))["inbox"]
        return {
            "queues": counts,
            "active": job.get("jobId"),
            "latestRun": last,
            "model": SCORER,
            "manifestAvailable": manifest is not None,
            "modelVersion": (manifest or {}).get("model", {}).get("version"),
            "observationsAsOf": observation.get("asOfTime"),
            "traffic": "Disabled pending permission",
            "lastPush": max(
                (n.get("deliveredAt", 0) for n in notices if n.get("delivery") == "push"),
                default=None,
            ),
        }
    if path.startswith("/api/admin/jobs/") and method == "GET":
        job_id = path.rsplit("/", 1)[-1]
        if not re.fullmatch(r"replay-[0-9a-f]{32}", job_id):
            raise RequestError("invalid_job", "Invalid replay.", 400)
        item = (
            runtime.table().get_item(Key={"pk": "job#" + job_id}, ConsistentRead=True).get("Item")
        )
        return {"phase": phase(item) if item else "queued", "jobId": job_id}
    if method != "POST" or path != "/api/admin/actions":
        raise RequestError("not_found", "Unknown operator action.", 404)
    action = body.get("action")
    req = identifier(body.get("requestId"))
    actor = hashlib.sha256(owner.encode()).hexdigest()[:16]
    log.info(
        json.dumps(
            {
                "event": "passenger.demo.request",
                "action": action if action in ("publish", "seed", "change", "push") else "unknown",
                "actor": actor,
                "requestId": req,
            }
        )
    )
    epoch = int(now.timestamp())
    if action == "seed":
        already_seeded = True
        for slot in range(1, len(SEEDS) + 1):
            old = store.get(owner, f"flight#{slot}")
            already_seeded = already_seeded and old.get("revision") == str(
                uuid5(UUID(req), str(slot))
            )
            if old.get("watch") != "demo" and old.get("expiresAt", 0) > epoch:
                raise RequestError(
                    "occupied",
                    "Move your personal flights out of slots 1–3 before resetting demo flights.",
                    409,
                )
        if already_seeded:
            return {"seeded": len(SEEDS)}
        for row in store.rows(owner, epoch):
            if row["sk"].startswith("notice#") and row.get("demo"):
                store.db.delete_item(**store.key(owner, row["sk"]))
        for slot, (origin, dest, hours) in enumerate(SEEDS, 1):
            rev = str(uuid5(UUID(req), str(slot)))
            old = store.get(owner, f"flight#{slot}")
            if old.get("revision") == rev:
                continue
            data = flight_input(
                {
                    "origin": origin,
                    "destination": dest,
                    "departure": utc_text(
                        now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=hours)
                    ),
                },
                now,
            )
            # Labelled starting scenario for the classroom replay; personal flights always learn a real baseline.
            data["assessment"] = {"peak": "smooth", "firstRough": None}
            store.save(
                owner,
                slot,
                data,
                rev,
                old.get("revision") if old.get("expiresAt", 0) > epoch else None,
                epoch,
                demo=True,
            )
        return {"seeded": 3}
    if action == "publish":
        if body.get("run") not in REPLAYS:
            raise RequestError("invalid_run", "Choose an archived classroom run.")
        job = job_spec(body["run"], "replay-" + req.replace("-", ""), "replay")
        send_event(clients("events"), os.environ["PIPELINE_BUS"], AVAILABLE, job)
        return job
    if action == "push":
        store.notice({"pk": owner, "sk": "account"}, "test-push", req, epoch)
        return {"accepted": True}
    if action == "change":
        slot = body.get("slot")
        flight = store.get(owner, f"flight#{slot}")
        if flight.get("watch") != "demo" or flight.get("expiresAt", 0) <= epoch:
            raise RequestError("demo_only", "Choose an active seeded demo flight.", 409)
        send_event(
            clients("events"),
            os.environ["PIPELINE_BUS"],
            "passenger.change.test",
            {"owner": owner, "slot": slot, "revision": flight["revision"], "requestId": req},
        )
        return {"accepted": True}
    raise RequestError("invalid_action", "Choose an operator action.", 400)


def parse_body(event):
    raw = event.get("body") or "{}"
    if len(raw) > 12000:
        raise RequestError("too_large", "Request is too large.", 413)
    try:
        body = json.loads(
            base64.b64decode(raw, validate=True) if event.get("isBase64Encoded") else raw
        )
        if not isinstance(body, dict):
            raise ValueError
    except (ValueError, TypeError, UnicodeError) as exc:
        raise RequestError("invalid_body", "Expected a JSON object.", 400) from exc
    return body


def dispatch(event, store, clients=runtime.client, now=None):
    now = now or datetime.now(UTC)
    epoch = int(now.timestamp())
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "")
    admin = path.startswith("/api/admin/")
    scope = (
        ADMIN
        if admin
        else PREF
        if path == "/api/me/preferences"
        else READ
        if method == "GET" or (method == "POST" and path == "/api/me/flight-lookup")
        else WRITE
    )
    if method == "POST" and path == "/api/shared":
        return read_link(store, parse_body(event).get("token"), epoch)
    owner, username = identity(event, scope)
    account = store.get(owner, "account")
    closing_sessions = method == "POST" and path == "/api/me/sign-out"
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    if (
        account.get("signedOutAt")
        and int(claims.get("auth_time", 0)) <= account["signedOutAt"]
        and not closing_sessions
    ):
        raise RequestError("signed_out", "Your session ended. Please sign in again.", 401)
    erasing = method == "DELETE" and path == "/api/me"
    if account.get("erasing") and method == "GET" and path == "/api/me":
        return {
            "closing": True,
            "flights": [],
            "inbox": [],
            "preferences": public_preferences({}),
        }
    if account.get("erasing") and not erasing:
        raise RequestError("closed", "This account is closed.", 410)
    body = parse_body(event)
    if closing_sessions:
        bearer = event.get("headers", {}).get("authorization", "").split()
        if len(bearer) != 2 or bearer[0].lower() != "bearer":
            raise RequestError("unauthorized", "Please sign in again.", 401)
        # Cognito rejects revoked tokens for GetUser. A stale token cannot move the cutoff again.
        cognito = clients("cognito-idp")
        try:
            cognito.get_user(AccessToken=bearer[1])
        except cognito.exceptions.NotAuthorizedException as exc:
            raise RequestError("signed_out", "This session has already ended.", 401) from exc
        store.end_sessions(owner, epoch)
        cognito.global_sign_out(AccessToken=bearer[1])
        return {"signedOut": True}
    flight_action = re.fullmatch(r"/api/me/flights/([1-8])/(detail|share)", path)
    if flight_action:
        flight = flight_or_missing(
            store,
            owner,
            int(flight_action[1]),
            epoch,
            identifier(body.get("revision")) if method in ("POST", "DELETE") else None,
        )
        if method == "GET" and flight_action[2] == "detail":
            return detail(store, flight, epoch, runtime.weather)
        if method in ("POST", "DELETE") and flight_action[2] == "share":
            return set_link(store, flight, epoch, method == "POST")
    notice = re.fullmatch(r"/api/me/notices/([0-9a-f]{32})", path)
    if notice and method == "PUT" and isinstance(body.get("read"), bool):
        store.set_read(owner, notice[1], body["read"], epoch)
        return {"read": body["read"]}
    if method == "POST" and path == "/api/me/flight-lookup":
        from services.flights.aws import aws_lookup

        result = aws_lookup(body, owner)
        log.info(
            json.dumps(
                {
                    "event": "flight.lookup",
                    "requestId": event.get("requestContext", {}).get("requestId"),
                    "cached": result.get("cached"),
                    "matches": len(result.get("flights", [])),
                }
            )
        )
        return result
    if admin:
        return admin_action(path, method, body, owner, store, now, clients)
    if method == "GET" and path in ("/api/me", "/api/me/export"):
        data = view(store, owner, epoch)
        if path.endswith("export"):
            data["forecastHistory"] = {
                row["id"]: row.get("forecastHistory", [])
                for row in store.rows(owner, epoch)
                if row["sk"].startswith("flight#")
            }
            data.update(
                subject=owner,
                identity=identity_attributes(event, clients),
                exportedAt=utc_text(now),
                verifiedEmailForDelivery=account.get("prefs", {}).get("email"),
            )
        return data
    if erasing:
        if body.get("confirm") != "DELETE" or not username:
            raise RequestError("confirm", "Type DELETE to erase your account.", 400)
        store.begin_erasure(owner, epoch)
        store.erase_rows(owner, epoch)
        cognito = clients("cognito-idp")
        try:
            cognito.admin_delete_user(UserPoolId=os.environ["USER_POOL"], Username=username)
        except cognito.exceptions.UserNotFoundException:
            pass
        return {"deleted": True}
    if path == "/api/me/preferences" and method == "PUT":
        prefs = dict(account.get("prefs", {}))
        key = body.get("channel")
        if key == "passenger":
            prefs.update(settings_patch(body.get("settings")))
        elif key == "email" and isinstance(body.get("enabled"), bool):
            if body["enabled"]:
                prefs["email"] = verified_email(event, clients)
            else:
                prefs.pop("email", None)
        elif key == "explainAlerts" and isinstance(body.get("enabled"), bool):
            prefs["explainAlerts"] = body["enabled"]
        elif key == "push" and "subscription" in body:
            if body["subscription"] is None:
                prefs.pop("device", None)
            else:
                prefs["device"] = subscription(body["subscription"])
        else:
            raise RequestError("invalid_preferences", "Choose a delivery channel.")
        store.preferences(owner, prefs, previous=account.get("prefs"))
        return public_preferences(prefs)
    match = re.fullmatch(r"/api/me/flights/([1-8])", path)
    if match:
        slot = int(match[1])
        if method == "PUT":
            previous = identifier(body["previous"]) if body.get("previous") else None
            row = store.save(
                owner,
                slot,
                flight_input(body, now),
                identifier(body.get("revision")),
                previous,
                epoch,
            )
            return public_row(row, FLIGHT_FIELDS)
        if method == "DELETE":
            store.remove(owner, slot, identifier(body.get("revision")))
            return {"removed": True}
    raise RequestError("not_found", "Unknown passenger action.", 404)


def handler(event, context):
    if event == {"task": "expire-flight-cache"}:
        from services.flights.aws import purge_expired

        return purge_expired()
    try:
        store = PassengerStore(runtime.client("dynamodb"), os.environ["PASSENGERS"])
        if event.get("routeKey") == "GET /family/{ticket}":
            from services.passengers.preview import preview_response

            ticket = (event.get("pathParameters") or {}).get("ticket", "")
            return preview_response(
                store,
                ticket.removesuffix(".png"),
                ticket.endswith(".png"),
                int(datetime.now(UTC).timestamp()),
                os.environ["PUBLIC_SITE"],
                os.environ["PUBLIC_API"],
            )
        result = dispatch(event, store)
        status = 200
    except RequestError as exc:
        if event.get("routeKey") == "GET /family/{ticket}" and exc.status == 404:
            return {
                "statusCode": 404,
                "headers": {
                    "content-type": "text/html; charset=utf-8",
                    "cache-control": "no-store",
                    "referrer-policy": "no-referrer",
                    "x-robots-tag": "noindex",
                },
                "body": '<!doctype html><html lang="en"><title>Shared forecast · SkyCalm</title><main><h1>Shared forecast</h1><p>This flight link has expired or was removed.</p></main></html>',
            }
        result, status = {"error": exc.code, "message": str(exc)}, exc.status
    except Exception as exc:
        log.error(
            json.dumps(
                {
                    "event": "passenger.request.failed",
                    "error": type(exc).__name__,
                    "requestId": getattr(context, "aws_request_id", None),
                }
            )
        )
        result, status = (
            {"error": "temporarily_unavailable", "message": "Please try again shortly."},
            503,
        )
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(result, default=lambda v: int(v) if isinstance(v, Decimal) else str(v)),
    }
