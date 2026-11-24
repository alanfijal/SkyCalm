"""Durable per-run progress and a lease for the one grid worker."""

import time
from datetime import UTC, datetime

from services.forecast.api import respond
from services.forecast.schema import utc_text
from services.pipeline.contract import demonstration_route

WEEK = 7 * 86400
LEASE_SECONDS = 780


def stamp():
    return utc_text(datetime.now(UTC))


def mark(db, job: dict, field: str, **values):
    key = {"pk": "job#" + job["jobId"]}
    data = {
        field: stamp(),
        "runId": job["runId"],
        "mode": job["mode"],
        "expiresAt": int(time.time()) + WEEK,
        **values,
    }
    fields = list(data)
    # Multiple targets may finish in either order. Retries keep the original receipt.
    db.update_item(
        Key=key,
        UpdateExpression="SET "
        + ", ".join(f"#{key}=if_not_exists(#{key},:{key})" for key in fields),
        ExpressionAttributeNames={f"#{key}": key for key in fields},
        ExpressionAttributeValues={f":{key}": value for key, value in data.items()},
        ConditionExpression="attribute_not_exists(#runId) OR #runId=:runId",
    )


def claim(db, job: dict) -> bool:
    mark(db, job, "acceptedAt")
    now = int(time.time())
    try:
        db.update_item(
            Key={"pk": "active"},
            UpdateExpression="SET jobId=:job, expiresAt=:end",
            ConditionExpression="attribute_not_exists(jobId) OR jobId=:job OR expiresAt<=:now",
            ExpressionAttributeValues={
                ":job": job["jobId"],
                ":now": now,
                ":end": now + LEASE_SECONDS,
            },
        )
    except db.meta.client.exceptions.ConditionalCheckFailedException:
        return False
    mark(db, job, "buildingAt")
    return True


def release(db, job: dict):
    try:
        db.delete_item(
            Key={"pk": "active"},
            ConditionExpression="jobId=:job",
            ExpressionAttributeValues={":job": job["jobId"]},
        )
    except db.meta.client.exceptions.ConditionalCheckFailedException:
        pass


def route_summary(store, run: str) -> dict:
    route = respond("/api/forecast", demonstration_route(run), store)
    return {
        "origin": route["origin"]["code"],
        "destination": route["destination"]["code"],
        "departure": route["departure"],
        "durationMinutes": route["durationMinutes"],
        "peak": route["peak"],
        "categories": [p["category"] for p in route["samples"]],
    }


def phase(item: dict) -> str:
    if item.get("failedAt"):
        return "failed"
    if item.get("routeAt") and item.get("receiptAt") and item.get("dispatchedAt"):
        return "ready"
    if item.get("gridReadyAt"):
        return "delivering"
    if item.get("buildingAt"):
        return "building"
    return "queued"
