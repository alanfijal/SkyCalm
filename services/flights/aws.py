"""DynamoDB compare-and-swap budget and short-lived commercial schedule data."""

import os
from datetime import date
from functools import lru_cache
from uuid import uuid4

from services.flights.lookup import lookup
from services.flights.provider import fetch
from services.forecast.api import RequestError
from services.passengers.store import decode, encode
from services.pipeline.runtime import client


class DynamoLedger:
    def __init__(self, db, table: str):
        self.db, self.table = db, table

    def read(self, key: str) -> dict:
        item = self.db.get_item(TableName=self.table, Key=encode({"pk": key}), ConsistentRead=True)
        return decode(item.get("Item", {}))

    def reserve(self, previous: str | None, budget: dict) -> bool:
        args = {"ConditionExpression": "attribute_not_exists(pk)"}
        if previous is not None:
            args = {
                "ConditionExpression": "rev = :old",
                "ExpressionAttributeValues": encode({":old": previous}),
            }
        try:
            self.db.put_item(TableName=self.table, Item=encode({"pk": "budget", **budget}), **args)
        except self.db.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def finish(self, budget: dict, key: str, cached: dict | None) -> None:
        released = {**budget, "pk": "budget", "rev": uuid4().hex, "holdUntil": 0}
        writes = [
            {
                "Put": {
                    "TableName": self.table,
                    "Item": encode(released),
                    "ConditionExpression": "rev = :old",
                    "ExpressionAttributeValues": encode({":old": budget["rev"]}),
                }
            }
        ]
        if cached is not None:
            writes.append({"Put": {"TableName": self.table, "Item": encode({"pk": key, **cached})}})
        try:
            self.db.transact_write_items(TransactItems=writes)
        except self.db.exceptions.TransactionCanceledException as exc:
            if (
                exc.response.get("CancellationReasons", [{}])[0].get("Code")
                != "ConditionalCheckFailed"
            ):
                raise


@lru_cache(maxsize=1)
def provider_key(parameter: str) -> str:
    return client("ssm").get_parameter(Name=parameter, WithDecryption=True)["Parameter"]["Value"]


def aws_lookup(body: dict, owner: str) -> dict:
    table, parameter = os.getenv("FLIGHT_LOOKUP_TABLE"), os.getenv("FLIGHT_LOOKUP_PARAMETER")
    if not table or not parameter:
        raise RequestError(
            "lookup_offline", "Flight-number lookup is unavailable. Search by airports.", 503
        )

    def load(code: str, day: date) -> list[dict]:
        return fetch(code, day, provider_key(parameter))

    return lookup(body, owner, DynamoLedger(client("dynamodb"), table), load)


def purge_expired() -> dict:
    """Daily backup to TTL. Only the dedicated schedule table can be reached."""
    import time

    db, table = client("dynamodb"), os.environ["FLIGHT_LOOKUP_TABLE"]
    now = int(time.time())
    deleted = 0
    for page in db.get_paginator("scan").paginate(
        TableName=table,
        ProjectionExpression="pk, expiresAt",
        FilterExpression="expiresAt <= :now",
        ExpressionAttributeValues=encode({":now": now}),
    ):
        for item in page["Items"]:
            try:
                db.delete_item(
                    TableName=table,
                    Key={"pk": item["pk"]},
                    ConditionExpression="expiresAt <= :now",
                    ExpressionAttributeValues=encode({":now": now}),
                )
                deleted += 1
            except db.exceptions.ConditionalCheckFailedException:
                continue
    return {"expired": deleted}
