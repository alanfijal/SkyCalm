"""Owner partitions. Transactions serialize account erasure, flight edits and inbox alerts."""

import hashlib
from uuid import UUID, uuid5

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from services.forecast.api import RequestError
from services.forecast.schema import CATEGORIES
from services.passengers.domain import changed

PACK = TypeSerializer()
UNPACK = TypeDeserializer()
LIMIT = 8
DELIVERY_LEASE_SECONDS = 90


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

    def rows(self, owner, now, include_expired=False, include_snapshots=False):
        query = dict(
            TableName=self.name,
            KeyConditionExpression="pk = :p",
            ExpressionAttributeValues=encode({":p": owner}),
            ConsistentRead=True,
        )
        if not include_snapshots:
            query["FilterExpression"] = "attribute_not_exists(#payload)"
            query["ExpressionAttributeNames"] = {"#payload": "payload"}
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
        cleanup = self.related_deletes(owner, old)
        self.transact(
            owner,
            [
                *cleanup,
                {
                    "Put": dict(
                        TableName=self.name,
                        Item=encode(item),
                        ConditionExpression=cond,
                        ExpressionAttributeValues=encode(args),
                    )
                },
            ],
        )
        return item

    def related_deletes(self, owner, flight):
        if not flight.get("id"):
            return []
        return [
            {"Delete": self.key(owner, "forecast#" + flight["id"])},
            {"Delete": self.key("link#" + flight["id"].replace("-", ""), "forecast")},
        ]

    def remove(self, owner, slot, revision):
        old = self.get(owner, f"flight#{slot}")
        self.transact(
            owner,
            [
                *self.related_deletes(owner, old),
                {
                    "Delete": {
                        **self.key(owner, f"flight#{slot}"),
                        "ConditionExpression": "revision = :r",
                        "ExpressionAttributeValues": encode({":r": revision}),
                    }
                },
            ],
        )

    def begin_erasure(self, owner, now):
        self.db.put_item(
            TableName=self.name,
            Item=encode(dict(pk=owner, sk="account", erasing=True, expiresAt=now + 86400)),
        )

    def erase_rows(self, owner, now):
        for row in self.rows(owner, now, include_expired=True, include_snapshots=True):
            if row["sk"].startswith("flight#") and row.get("familyGrant"):
                self.db.delete_item(**self.key("link#" + row["id"].replace("-", ""), "forecast"))
            if row["sk"] != "account":
                self.db.delete_item(**self.key(owner, row["sk"]))

    def notice(
        self,
        flight,
        kind,
        event_id,
        now,
        *,
        peak=None,
        updates=None,
        condition=None,
        values=None,
        extra=(),
    ):
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
        if peak in CATEGORIES:
            notice["peak"] = peak
        writes = list(extra)
        if sk.startswith("flight#"):
            notice.update(
                slot=flight["slot"],
                flightRevision=flight["revision"],
                flightId=flight["id"],
                routeLabel=flight["origin"] + " → " + flight["destination"],
            )
            if updates:
                notice["runMarker"] = event_id
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

    def record_forecast(self, flight, run, summary, now, test=False, forecast=None):
        if summary is None:
            return
        old = flight.get("assessment")
        fresh = "attribute_not_exists(lastRun) OR lastRun < :run"
        values = {":run": run, ":s": summary}
        if test:
            fresh = "attribute_not_exists(lastRun) OR lastRun <> :run"
        from services.passengers.journey import compact_forecast, ribbon

        history = list(flight.get("forecastHistory", []))
        point = {"marker": run, "at": now, "peak": summary["peak"]}
        if forecast is not None:
            point.update(run=forecast["run"]["runId"], issued=forecast["run"]["issued"])
        elif test:
            point["simulated"] = True
        history.append(point)
        values.update({":history": history[-32:], ":baseline": old or summary, ":at": now})
        edits = (
            "SET lastRun=:run, assessment=:s, baseline=if_not_exists(baseline,:baseline), "
            "forecastAt=:at, forecastHistory=:history"
        )
        extra = []
        if forecast is not None:
            values[":ribbon"] = ribbon(forecast["samples"])
            edits += ", ribbon=:ribbon"
            extra.append(
                {
                    "Put": {
                        "TableName": self.name,
                        "Item": encode(
                            {
                                "pk": flight["pk"],
                                "sk": "forecast#" + flight["id"],
                                "revision": flight["revision"],
                                "expiresAt": flight["expiresAt"],
                                "payload": compact_forecast(forecast),
                            }
                        ),
                    }
                }
            )
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
                peak=summary["peak"],
                updates=edits + ", lastAlert=:now",
                condition=condition,
                values=values,
                extra=extra,
            )
        self.transact(
            flight["pk"],
            [
                *extra,
                {
                    "Update": {
                        **self.key(flight["pk"], flight["sk"]),
                        "UpdateExpression": edits,
                        "ConditionExpression": f"revision=:r AND ({condition})",
                        "ExpressionAttributeValues": encode({":r": flight["revision"], **values}),
                    }
                },
            ],
        )

    def set_read(self, owner, uid, read, now):
        self.transact(
            owner,
            [
                {
                    "Update": {
                        **self.key(owner, "notice#" + uid),
                        "ConditionExpression": "attribute_exists(pk) AND expiresAt>:now",
                        "UpdateExpression": "SET isRead=:read",
                        "ExpressionAttributeValues": encode({":now": now, ":read": read}),
                    }
                }
            ],
        )

    def end_sessions(self, owner, now):
        try:
            self.db.update_item(
                **self.key(owner, "account"),
                ConditionExpression="attribute_not_exists(erasing) AND (attribute_not_exists(signedOutAt) OR signedOutAt <= :t)",
                UpdateExpression="SET signedOutAt=:t",
                ExpressionAttributeValues=encode({":t": now}),
            )
        except self.db.exceptions.ConditionalCheckFailedException as exc:
            raise conflict() from exc

    def claim_delivery(self, owner, sk, now):
        # Longer than the 55-second worker timeout and shorter than SQS redelivery.
        try:
            row = self.db.update_item(
                **self.key(owner, sk),
                ConditionExpression=(
                    "delivery=:pending AND expiresAt>:now AND "
                    "(attribute_not_exists(leaseUntil) OR leaseUntil<=:now)"
                ),
                UpdateExpression="SET leaseUntil=:until",
                ExpressionAttributeValues=encode(
                    {":pending": "pending", ":now": now, ":until": now + DELIVERY_LEASE_SECONDS}
                ),
                ReturnValues="ALL_NEW",
            )
            return decode(row["Attributes"])
        except self.db.exceptions.ConditionalCheckFailedException:
            current = self.get(owner, sk)
            if current.get("delivery") == "pending" and current.get("expiresAt", 0) > now:
                raise RuntimeError("Notification delivery in progress") from None
            return None

    def mark_delivery(self, owner, sk, result, stamp, *, sent_body=None):
        try:
            self.db.update_item(
                **self.key(owner, sk),
                ConditionExpression="delivery=:p AND leaseUntil=:until",
                UpdateExpression="SET delivery=:s, deliveredAt=:t, sentBody=:body REMOVE leaseUntil",
                ExpressionAttributeValues=encode(
                    {
                        ":p": "pending",
                        ":s": result,
                        ":t": stamp,
                        ":until": stamp + DELIVERY_LEASE_SECONDS,
                        ":body": sent_body,
                    }
                ),
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
