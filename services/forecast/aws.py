"""Regional S3 tiles and a monotonic DynamoDB head pointer."""

import json
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

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
