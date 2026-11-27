"""Durable passenger work. Queue payloads carry lookup keys. Detailed alerts require opt-in."""

import json
import logging
import os
import time
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from botocore.exceptions import ClientError

from services.forecast.api import respond
from services.passengers.comfort import email_body
from services.passengers.domain import snapshot
from services.passengers.preferences import inbox_only
from services.passengers.store import PassengerStore, decode, encode
from services.pipeline import runtime
from services.pipeline.artifacts import StagedGrid
from services.pipeline.contract import READY, demonstration_route, parse_job, send_event

log = logging.getLogger(__name__)
NOTICE = "passenger.notice.ready"
CHANGE = "passenger.change.test"


def enqueue(kind, data):
    runtime.client("sqs").send_message(
        QueueUrl=os.environ["WORK_QUEUE"],
        MessageBody=json.dumps({"detail-type": kind, "detail": data}),
    )


def schedule_name(row, hours):
    name = uuid5(NAMESPACE_URL, f"{row['pk']}/{row['sk']}/{row['revision']}")
    return f"f-{name.hex}-{hours}"


def schedules(old, current, scheduler, now, env):
    if old and current and old["revision"] == current["revision"]:
        return
    for hours in (24, 3):
        if old:
            try:
                scheduler.delete_schedule(
                    GroupName=env["SCHEDULE_GROUP"], Name=schedule_name(old, hours)
                )
            except scheduler.exceptions.ResourceNotFoundException:
                pass
        if not current:
            continue
        target = int(current["departureEpoch"]) - 3600 * hours
        if target <= now:
            continue
        name = schedule_name(current, hours)
        data = {
            "owner": current["pk"],
            "slot": int(current["slot"]),
            "revision": current["revision"],
            "hours": hours,
        }
        try:
            scheduler.create_schedule(
                Name=name,
                GroupName=env["SCHEDULE_GROUP"],
                ClientToken=uuid5(NAMESPACE_URL, name).hex,
                ActionAfterCompletion="DELETE",
                ScheduleExpression="at("
                + datetime.fromtimestamp(target, UTC).strftime("%Y-%m-%dT%H:%M:%S")
                + ")",
                ScheduleExpressionTimezone="UTC",
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={
                    "Arn": env["WORK_ARN"],
                    "RoleArn": env["SCHEDULER_ROLE"],
                    "Input": json.dumps({"detail-type": "reminder", "detail": data}),
                    "RetryPolicy": {"MaximumEventAgeInSeconds": 300, "MaximumRetryAttempts": 2},
                    "DeadLetterConfig": {"Arn": env["DEAD_ARN"]},
                },
            )
        except scheduler.exceptions.ConflictException:
            # Deterministic name contains the revision. Service retries can meet an existing schedule.
            existing = scheduler.get_schedule(GroupName=env["SCHEDULE_GROUP"], Name=name)
            if json.loads(existing["Target"]["Input"])["detail"] != data:
                raise


def stream(event, context):
    store = PassengerStore(runtime.client("dynamodb"), os.environ["PASSENGERS"])
    for record in event["Records"]:
        d = record["dynamodb"]
        try:
            key = decode(d["Keys"])
            if key["sk"].startswith("flight#"):
                old = decode(d["OldImage"]) if d.get("OldImage") else None
                new = decode(d["NewImage"]) if d.get("NewImage") else None
                if (old or {}).get("revision") == (new or {}).get("revision"):
                    continue
                live = store.get(key["pk"], key["sk"])
                if new and (
                    live.get("revision") != new["revision"]
                    or store.get(key["pk"], "account").get("erasing")
                ):
                    new = None
                schedules(old, new, runtime.client("scheduler"), int(time.time()), os.environ)
                if new and new["watch"] == "live":
                    enqueue(
                        "initial-score",
                        {"owner": new["pk"], "slot": int(new["slot"]), "revision": new["revision"]},
                    )
            elif key["sk"].startswith("notice#") and d.get("NewImage") and not d.get("OldImage"):
                send_event(
                    runtime.client("events"),
                    os.environ["PIPELINE_BUS"],
                    NOTICE,
                    {"owner": key["pk"], "sk": key["sk"]},
                )
        except Exception as exc:
            log.warning(
                json.dumps({"event": "passenger.stream.failed", "error": type(exc).__name__})
            )
            return {"batchItemFailures": [{"itemIdentifier": d["SequenceNumber"]}]}
    return {"batchItemFailures": []}


def watch_page(store, job, cursor, now):
    mode = "demo" if job["mode"] == "replay" else "live"
    args = dict(
        TableName=store.name,
        IndexName="departures",
        KeyConditionExpression="watch=:w AND departureEpoch BETWEEN :a AND :b",
        ExpressionAttributeValues=encode({":w": mode, ":a": now, ":b": now + 36 * 3600}),
        Limit=8,
    )
    if cursor:
        args["ExclusiveStartKey"] = cursor
    page = store.db.query(**args)
    for raw in page["Items"]:
        row = decode(raw)
        enqueue(
            "score",
            {"job": job, "owner": row["pk"], "slot": int(row["slot"]), "revision": row["revision"]},
        )
    if page.get("LastEvaluatedKey"):
        enqueue("watch", {"job": job, "cursor": page["LastEvaluatedKey"], "asOf": now})


def score(store, flight, job, now):
    replay = job["mode"] == "replay"
    if (flight["watch"] == "demo") != replay:
        return
    run = job["runId"]
    when = demonstration_route(run)["departure"] if replay else flight["departure"]
    query = {
        "origin": flight["origin"],
        "destination": flight["destination"],
        "departure": when,
        "run": run,
        "altitudes": "1",
    }
    if flight.get("arrivalScheduled") and not replay:
        query["arrival"] = flight["arrival"]
    # A new model run can cover less than 36 hours ahead of wall time.
    from services.forecast.schema import issue_time

    lead = (datetime.fromisoformat(when) - issue_time(run)).total_seconds()
    if not 0 <= lead <= 36 * 3600:
        return
    forecast = respond("/api/forecast", query, StagedGrid(runtime.weather(), job))
    assessment = snapshot(forecast)
    # Chronological live keys reject late runs. Replay jobs can revisit the same archive.
    marker = ("replay:" + job["jobId"]) if replay else run
    if flight.get("lastRun") == marker or (not replay and flight.get("lastRun", "") > marker):
        return
    store.record_forecast(flight, marker, assessment, now, test=replay, forecast=forecast)


def deliver(store, owner, sk, now):
    notice = store.claim_delivery(owner, sk, now)
    if not notice:
        return
    account = store.get(owner, "account")
    if account.get("erasing") or (
        "slot" in notice
        and store.get(owner, f"flight#{notice['slot']}").get("revision")
        != notice.get("flightRevision")
    ):
        store.mark_delivery(owner, sk, "cancelled", now)
        return
    prefs = account.get("prefs", {})
    if not prefs.get("email") or inbox_only(notice, prefs, now):
        store.mark_delivery(owner, sk, "inbox", now)
        return
    body = email_body(notice, prefs, os.environ["INBOX_URL"])
    try:
        runtime.client("sesv2").send_email(
            FromEmailAddress=os.environ["SES_FROM"],
            Destination={"ToAddresses": [prefs["email"]]},
            Content={
                "Simple": {
                    "Subject": {"Data": "SkyCalm flight update", "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                }
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "MessageRejected":
            raise
        store.mark_delivery(owner, sk, "email-rejected", now)
        return
    store.mark_delivery(owner, sk, "email", now, sent_body=body)


def process(store, kind, data, now):
    if kind == READY:
        return watch_page(store, parse_job(data), None, now)
    if kind == "watch":
        return watch_page(store, parse_job(data["job"]), data["cursor"], data["asOf"])
    if kind == NOTICE:
        return deliver(store, data["owner"], data["sk"], now)
    if kind not in ("score", "initial-score", "reminder", CHANGE):
        raise ValueError("Unexpected passenger event")
    owner = data["owner"]
    flight = store.get(owner, "flight#" + str(data["slot"]))
    if (
        flight.get("revision") != data["revision"]
        or flight.get("expiresAt", 0) <= now
        or store.get(owner, "account").get("erasing")
    ):
        return
    if kind == "initial-score":
        if flight.get("lastRun") or flight["departureEpoch"] > now + 36 * 3600:
            return
        from services.forecast.api import RequestError

        query = {k: flight[k] for k in ("origin", "destination", "departure")}
        if flight.get("arrivalScheduled"):
            query["arrival"] = flight["arrival"]
        try:
            forecast = respond(
                "/api/forecast",
                {**query, "altitudes": "1"},
                runtime.weather(),
                datetime.fromtimestamp(now, UTC),
            )
        except RequestError as exc:
            if exc.code in {
                "no_live_run",
                "stale_run",
                "unknown_run",
                "before_run",
                "too_early",
                "past_departure",
            }:
                return
            raise
        return store.record_forecast(
            flight, forecast["run"]["runId"], snapshot(forecast), now, forecast=forecast
        )
    if kind == "score":
        return score(store, flight, parse_job(data["job"]), now)
    if kind == "reminder":
        hours = data["hours"]
        if hours not in (3, 24) or flight["departureEpoch"] <= now:
            return
        return store.notice(
            flight,
            f"reminder-{hours}h",
            str(hours),
            now,
            peak=(flight.get("assessment") or {}).get("peak"),
        )
    if flight["watch"] == "demo" and flight.get("lastRun") != data["requestId"]:
        previous = (flight.get("assessment") or {}).get("peak")
        return store.record_forecast(
            flight,
            data["requestId"],
            {
                "peak": "moderate" if previous != "moderate" else "light",
                "firstRough": 45 if previous != "moderate" else None,
            },
            now,
            test=True,
        )


def worker(event, context):
    from services.forecast.api import RequestError

    store = PassengerStore(runtime.client("dynamodb"), os.environ["PASSENGERS"])
    failures = []
    for r in event["Records"]:
        try:
            packet = json.loads(r["body"])
            for attempt in range(2):
                try:
                    process(
                        store,
                        packet["detail-type"],
                        packet["detail"],
                        int(time.time()),
                    )
                    break
                except RequestError as exc:
                    if exc.code != "conflict" or attempt:
                        raise
        except Exception as exc:
            log.warning(
                json.dumps(
                    {
                        "event": "passenger.work.failed",
                        "error": type(exc).__name__,
                        "messageId": r["messageId"],
                    }
                )
            )
            failures.append({"itemIdentifier": r["messageId"]})
    return {"batchItemFailures": failures}
