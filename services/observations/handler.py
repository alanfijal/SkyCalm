"""On-demand weather capture for the Stockholm Lambda."""

import json
import logging
import os
from functools import lru_cache

import boto3
from botocore.config import Config

from services.observations.archive import objects
from services.observations.awc import collect
from services.observations.collect import capture_time

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def clients():
    session = boto3.Session()
    config = Config(
        connect_timeout=3, read_timeout=8, retries={"mode": "standard", "total_max_attempts": 3}
    )
    return (
        session.client("s3", config=config),
        session.resource("dynamodb", config=config).Table(os.environ["SKYCALM_TABLE"]),
    )


def publish(snapshot, raw, s3, bucket, table):
    version, payloads = objects(snapshot, raw)
    for key, body in payloads.items():
        extra = {"ContentEncoding": "gzip"} if key.endswith(".gz") else {}
        if key.startswith("observations/history/"):
            extra["Tagging"] = "Retention=working"
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json", **extra)
    try:
        table.update_item(
            Key={"pk": "observations#awc"},
            UpdateExpression="SET asOfTime = :at, version = :v",
            ConditionExpression="attribute_not_exists(asOfTime) OR asOfTime < :at",
            ExpressionAttributeValues={":at": snapshot["asOf"], ":v": version},
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        pass  # A complete snapshot at this time or a newer one already won.
    return version


def handler(event, context):
    as_of = capture_time(event.get("at"))
    data, raw = collect(as_of)
    s3, table = clients()
    version = publish(data, raw, s3, os.environ["SKYCALM_BUCKET"], table)
    result = {
        "event": "observations.ready",
        "version": version,
        "weatherRecords": len(data["items"]),
        "requestId": context.aws_request_id,
    }
    logger.info(json.dumps(result))
    return result
