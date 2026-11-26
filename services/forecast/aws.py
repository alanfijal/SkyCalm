"""Regional S3 tiles and a monotonic DynamoDB head pointer."""

import json
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from services.forecast.schema import SCORER, issue_time, tile_name
from services.forecast.storage import REPLAY_ROOT, checked_tile, validate_manifest


class AwsStore:
    def __init__(self, s3, bucket: str, table):
        self.s3, self.bucket, self.table = s3, bucket, table

    @classmethod
    def from_env(cls):
        session = boto3.Session(region_name=os.environ.get("AWS_REGION", "eu-north-1"))
        config = Config(
            connect_timeout=3, read_timeout=8, retries={"total_max_attempts": 3, "mode": "standard"}
        )
        table = session.resource("dynamodb", config=config).Table(os.environ["SKYCALM_TABLE"])
        return cls(session.client("s3", config=config), os.environ["SKYCALM_BUCKET"], table)

    @staticmethod
    def prefix(run_id: str) -> str:
        issue_time(run_id)
        return f"runs/{SCORER}/{run_id}/"

    def latest(self) -> str | None:
        return (
            self.table.get_item(Key={"pk": f"latest#{SCORER}"}, ConsistentRead=True)
            .get("Item", {})
            .get("runId")
        )

    def replays(self) -> list[str]:
        return sorted(
            (m.parent.name for m in REPLAY_ROOT.glob("gfs-*/manifest.json")), reverse=True
        )

    def observation_snapshot(self, selection: str) -> dict | None:
        if selection == "latest":
            head = self.table.get_item(Key={"pk": "observations#awc"}, ConsistentRead=True)
            if "Item" not in head:
                return None
            key = "observations/snapshots/" + head["Item"]["version"] + ".json"
        else:
            issue_time(selection)
            key = "archive/observations/" + selection + ".json"
        try:
            return json.loads(self.read(key, 2_000_000))
        except self.s3.exceptions.NoSuchKey:
            return None

    def route_observations(self, departure, arrival):
        from datetime import UTC, datetime, timedelta

        from services.passengers.journey import capture_prefixes

        first = datetime.fromisoformat(departure) - timedelta(minutes=45)
        end = datetime.fromisoformat(arrival) + timedelta(hours=6)
        keys = []
        for day in capture_prefixes(first.isoformat(), arrival):
            # Snapshot keys start with the UTC capture minute; one listing per day.
            page = self.s3.list_objects_v2(
                Bucket=self.bucket, Prefix="observations/snapshots/" + day, MaxKeys=1000
            )
            for item in page.get("Contents", []):
                key = item["Key"]
                try:
                    at = datetime.strptime(key.split("/")[-1][:15], "%Y-%m-%d-%H%M").replace(
                        tzinfo=UTC
                    )
                except ValueError:
                    continue
                if first <= at <= end:
                    keys.append(key)
        # Pick up to six evenly spaced captures including the first and last.
        keys.sort()
        if len(keys) > 6:
            keys = [keys[round(i * (len(keys) - 1) / 5)] for i in range(6)]
        return [json.loads(self.read(key, 2_000_000)) for key in keys]

    def read(self, key: str, limit: int) -> bytes:
        response = self.s3.get_object(Bucket=self.bucket, Key=key)
        with response["Body"] as body:
            raw = body.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Weather asset exceeds the supported size")
        return raw

    def published_manifest(self, run_id: str) -> dict | None:
        try:
            data = self.read(self.prefix(run_id) + "manifest.json", 64_000)
        except self.s3.exceptions.NoSuchKey:
            return None
        return validate_manifest(json.loads(data), run_id)

    def manifest(self, run_id: str) -> dict | None:
        published = self.published_manifest(run_id)
        if published:
            return published
        if run_id not in self.replays():
            return None
        try:
            data = self.read(f"archive/{SCORER}/{run_id}/manifest.json", 64_000)
        except self.s3.exceptions.NoSuchKey:
            return None
        return validate_manifest(json.loads(data), run_id)

    def tile(self, run_id: str, lead: int, digest: str) -> bytes:
        try:
            data = self.read(self.prefix(run_id) + digest + ".bin.gz", 300_000)
        except self.s3.exceptions.NoSuchKey:
            data = self.read(f"archive/{SCORER}/{run_id}/{tile_name(lead)}", 300_000)
        return checked_tile(data, digest)

    def briefing(self, key):
        if os.getenv("SKYCALM_BRIEFINGS") != "enabled":
            return None
        try:
            return json.loads(self.read(f"ml/briefings/{key}.json", 1024))
        except (BotoCoreError, ClientError):
            return None

    def model_tile(self, run_id, lead, digest):
        try:
            data = self.read(self.prefix(run_id) + digest + ".ml.gz", 150_000)
        except self.s3.exceptions.NoSuchKey:
            data = self.read(f"archive/{SCORER}/{run_id}/ml-{lead:03}.gz", 150_000)
        return checked_tile(data, digest)

    def advance(self, run_id: str) -> None:
        issue_time(run_id)
        try:
            self.table.update_item(
                Key={"pk": f"latest#{SCORER}"},
                UpdateExpression="SET runId = :r",
                ConditionExpression="attribute_not_exists(runId) OR runId < :r",
                ExpressionAttributeValues={":r": run_id},
            )
        except self.table.meta.client.exceptions.ConditionalCheckFailedException:
            pass  # The committed head already names this run or a newer one.

    def publish(self, directory: Path, manifest: dict) -> None:
        run = manifest["runId"]
        validate_manifest(manifest, run)
        prefix = self.prefix(run)
        for item in manifest["leads"]:
            raw = checked_tile((directory / tile_name(item["lead"])).read_bytes(), item["sha256"])
            self.s3.put_object(
                Bucket=self.bucket, Key=prefix + item["sha256"] + ".bin.gz", Body=raw
            )
            if "model" in manifest:
                digest = item["modelSha256"]
                ml = checked_tile((directory / f"ml-{item['lead']:03}.gz").read_bytes(), digest)
                self.s3.put_object(Bucket=self.bucket, Key=prefix + digest + ".ml.gz", Body=ml)
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=prefix + "manifest.json",
                Body=json.dumps(manifest).encode(),
                ContentType="application/json",
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if (
                exc.response["ResponseMetadata"]["HTTPStatusCode"] != 412
                or self.manifest(run) != manifest
            ):
                raise
        self.advance(run)
