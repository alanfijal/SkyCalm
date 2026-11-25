"""Owner partitions. Transactions serialize account erasure, flight edits and inbox alerts."""

import hashlib
from uuid import UUID, uuid5

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from services.forecast.api import RequestError
from services.passengers.domain import changed

PACK = TypeSerializer()
UNPACK = TypeDeserializer()
LIMIT = 8


def encode(item):
    return {k: PACK.serialize(v) for k, v in item.items()}


def decode(item):
    return {k: UNPACK.deserialize(v) for k, v in item.items()}


def conflict():
    return RequestError("conflict", "This item changed. Refresh and try again.", 409)


class PassengerStore:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def key(self, owner, sk):
        return {"TableName": self.name, "Key": encode({"pk": owner, "sk": sk})}

    def get(self, owner, sk):
        item = self.db.get_item(**self.key(owner, sk), ConsistentRead=True).get("Item")
        return decode(item) if item else {}

    def rows(self, owner, now, include_expired=False):
        query = dict(
            TableName=self.name,
            KeyConditionExpression="pk = :p",
            ExpressionAttributeValues=encode({":p": owner}),
            ConsistentRead=True,
        )
        while True:
            page = self.db.query(**query)
            for raw in page["Items"]:
                row = decode(raw)
                if include_expired or row.get("expiresAt", now + 1) > now:
                    yield row
            if not page.get("LastEvaluatedKey"):
                break
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def transact(self, owner, writes):
        active = {
            **self.key(owner, "account"),
            "ConditionExpression": "attribute_not_exists(erasing)",
        }
        try:
            self.db.transact_write_items(TransactItems=[{"ConditionCheck": active}, *writes])
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "TransactionCanceledException" and any(
                x.get("Code") in ("ConditionalCheckFailed", "TransactionConflict")
                for x in exc.response.get("CancellationReasons", [])
            ):
                raise conflict() from exc
            raise

    def preferences(self, owner, prefs, previous):
        match = "prefs=:previous" if previous is not None else "attribute_not_exists(prefs)"
        values = {":v": prefs}
        if previous is not None:
            values[":previous"] = previous
        try:
            self.db.update_item(
                **self.key(owner, "account"),
                ConditionExpression="attribute_not_exists(erasing) AND " + match,
                UpdateExpression="SET prefs = :v",
                ExpressionAttributeValues=encode(values),
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise conflict() from exc
            raise

    def save(self, owner, slot, data, revision, expected, now, demo=False):
        key = "flight#" + str(slot)
        old = self.get(owner, key)
        if old.get("revision") == revision:
            if all(old.get(k) == v for k, v in data.items()):
                return old
            raise conflict()
        item = dict(
            pk=owner,
            sk=key,
            slot=slot,
            id=old["id"] if expected and old else str(uuid5(UUID(owner), f"{slot}:{revision}")),
            revision=revision,
            watch="demo" if demo or (expected and old.get("watch") == "demo") else "live",
            **data,
        )
        cond = (
            "revision = :old AND expiresAt > :now"
            if expected
            else "attribute_not_exists(pk) OR expiresAt <= :now"
        )
        args = {":now": now}
        if expected:
            args[":old"] = expected
        self.transact(
            owner,
            [
                {
                    "Put": dict(
                        TableName=self.name,
                        Item=encode(item),
                        ConditionExpression=cond,
                        ExpressionAttributeValues=encode(args),
                    )
                }
            ],
        )
        return item

    def remove(self, owner, slot, revision):
        self.transact(
            owner,
            [
                {
                    "Delete": {
                        **self.key(owner, f"flight#{slot}"),
                        "ConditionExpression": "revision = :r",
                        "ExpressionAttributeValues": encode({":r": revision}),
                    }
                }
            ],
        )

    def begin_erasure(self, owner, now):
        self.db.put_item(
            TableName=self.name,
            Item=encode(dict(pk=owner, sk="account", erasing=True, expiresAt=now + 86400)),
        )

    def erase_rows(self, owner, now):
        for row in self.rows(owner, now, include_expired=True):
            if row["sk"] != "account":
                self.db.delete_item(**self.key(owner, row["sk"]))

    def notice(self, flight, kind, event_id, now, *, updates=None, condition=None, values=None):
        owner, sk = flight["pk"], flight["sk"]
        uid = hashlib.sha256(
            f"{owner}/{sk}/{flight.get('revision', '')}/{kind}/{event_id}".encode()
        ).hexdigest()[:32]
        notice = dict(
            pk=owner,
            sk="notice#" + uid,
            noticeId=uid,
            kind=kind,
            created=now,
            expiresAt=int(flight.get("expiresAt", now + 7 * 86400)),
            delivery="pending",
            demo=flight.get("watch") == "demo" or kind.startswith("test-"),
        )
        writes = []
        if sk.startswith("flight#"):
            notice.update(slot=flight["slot"], flightRevision=flight["revision"])
            guard = {
                **self.key(owner, sk),
                "ConditionExpression": "revision=:r AND expiresAt>:now"
                + (f" AND ({condition})" if condition else ""),
                "ExpressionAttributeValues": encode(
                    {":r": flight["revision"], ":now": now, **(values or {})}
                ),
            }
            if updates:
                writes.append({"Update": {**guard, "UpdateExpression": updates}})
            else:
                writes.append({"ConditionCheck": guard})
        writes.append(
            {
                "Put": dict(
                    TableName=self.name,
                    Item=encode(notice),
                    ConditionExpression="attribute_not_exists(pk)",
                )
            }
        )
        try:
            self.transact(owner, writes)
        except RequestError as exc:
            if exc.code != "conflict" or not self.get(owner, notice["sk"]):
                raise
        return notice

    def record_forecast(self, flight, run, summary, now, test=False):
        if summary is None:
            return
        old = flight.get("assessment")
        fresh = "attribute_not_exists(lastRun) OR lastRun < :run"
        values = {":run": run, ":s": summary}
        if test:
            fresh = "attribute_not_exists(lastRun) OR lastRun <> :run"
        edits = "SET lastRun=:run, assessment=:s"
        condition = "(" + fresh + ")"
        # Compare against precisely the previous assessment used in the decision.
        if flight.get("lastRun"):
            condition += " AND lastRun=:prev"
            values[":prev"] = flight["lastRun"]
        else:
            condition += " AND attribute_not_exists(lastRun)"
        if changed(old, summary) and now - int(flight.get("lastAlert", 0)) >= 10800:
            return self.notice(
                flight,
                "test-change" if test else "forecast-change",
                run,
                now,
                updates=edits + ", lastAlert=:now",
                condition=condition,
                values=values,
            )
        self.transact(
            flight["pk"],
            [
                {
                    "Update": {
                        **self.key(flight["pk"], flight["sk"]),
                        "UpdateExpression": edits,
                        "ConditionExpression": f"revision=:r AND ({condition})",
                        "ExpressionAttributeValues": encode({":r": flight["revision"], **values}),
                    }
                }
            ],
        )

    def mark_delivery(self, owner, sk, result, stamp):
        try:
            self.db.update_item(
                **self.key(owner, sk),
                ConditionExpression="attribute_exists(pk) AND delivery=:p",
                UpdateExpression="SET delivery=:s, deliveredAt=:t",
                ExpressionAttributeValues=encode({":p": "pending", ":s": result, ":t": stamp}),
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
