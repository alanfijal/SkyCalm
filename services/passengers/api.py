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

from services.forecast.api import RequestError
from services.forecast.schema import SCORER, utc_text
from services.passengers.domain import flight_input, identifier, identity, subscription
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
    "id",
    "revision",
    "origin",
    "destination",
    "departure",
    "arrival",
    "watch",
    "assessment",
)
NOTICE_FIELDS = ("noticeId", "kind", "created", "slot", "delivery", "deliveredAt")
SEEDS = (("EDI", "OPO", 12), ("AMS", "LHR", 26), ("BCN", "ARN", 30))


def public_row(row, fields):
    return {k: row[k] for k in fields if k in row}


def view(store, owner, now):
    rows = list(store.rows(owner, now))
    prefs = next((x.get("prefs", {}) for x in rows if x["sk"] == "account"), {})
    return {
        "flights": [public_row(x, FLIGHT_FIELDS) for x in rows if x["sk"].startswith("flight#")],
        "inbox": sorted(
            (public_row(x, NOTICE_FIELDS) for x in rows if x["sk"].startswith("notice#")),
            key=lambda n: n["created"],
            reverse=True,
        ),
        "preferences": {"push": bool(prefs.get("device")), "email": bool(prefs.get("email"))},
    }


def verified_email(event, clients):
    bearer = event.get("headers", {}).get("authorization", "").split()
    if len(bearer) != 2 or bearer[0].lower() != "bearer":
        raise RequestError("unauthorized", "Please sign in again.", 401)
    user = clients("cognito-idp").get_user(AccessToken=bearer[1])
    attrs = {a["Name"]: a["Value"] for a in user["UserAttributes"]}
    sandbox = os.environ.get("SES_RECIPIENT", "")
    if (
        attrs.get("email_verified") != "true"
        or not attrs.get("email")
        or (sandbox and sandbox.casefold() != attrs["email"].casefold())
    ):
        raise RequestError(
            "email_unavailable", "Email delivery requires a verified classroom mailbox.", 422
        )
    return attrs["email"]


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
        last = runtime.weather().latest()
        notices = view(store, owner, int(now.timestamp()))["inbox"]
        return {
            "queues": counts,
            "active": job.get("jobId"),
            "latestRun": last,
            "model": SCORER,
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
        for slot in range(1, len(SEEDS) + 1):
            old = store.get(owner, f"flight#{slot}")
            if old.get("watch") != "demo" and old.get("expiresAt", 0) > epoch:
                raise RequestError(
                    "occupied",
                    "Move your personal flights out of slots 1–3 before resetting demo flights.",
                    409,
                )
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
        if method == "GET"
        else WRITE
    )
    owner, username = identity(event, scope)
    account = store.get(owner, "account")
    erasing = method == "DELETE" and path == "/api/me"
    if account.get("erasing") and not erasing:
        raise RequestError("closed", "This account is closed.", 410)
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
    if admin:
        return admin_action(path, method, body, owner, store, now, clients)
    if method == "GET" and path in ("/api/me", "/api/me/export"):
        data = view(store, owner, epoch)
        if path.endswith("export"):
            data.update(
                subject=owner,
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
        if key == "email" and isinstance(body.get("enabled"), bool):
            if body["enabled"]:
                prefs["email"] = verified_email(event, clients)
            else:
                prefs.pop("email", None)
        elif key == "push" and "subscription" in body:
            if body["subscription"] is None:
                prefs.pop("device", None)
            else:
                prefs["device"] = subscription(body["subscription"])
        else:
            raise RequestError("invalid_preferences", "Choose a delivery channel.")
        store.preferences(owner, prefs, previous=account.get("prefs"))
        return {"push": bool(prefs.get("device")), "email": bool(prefs.get("email"))}
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
    try:
        result = dispatch(
            event, PassengerStore(runtime.client("dynamodb"), os.environ["PASSENGERS"])
        )
        status = 200
    except RequestError as exc:
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
