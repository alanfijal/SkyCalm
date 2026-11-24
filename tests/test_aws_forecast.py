import json
from copy import deepcopy
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws

from services.forecast import handler
from services.forecast.aws import AwsStore
from services.forecast.storage import REPLAY_ROOT


@mock_aws
def test_cloud_publication_and_http_api_replay(monkeypatch):
    session = boto3.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing", region_name="eu-north-1"
    )
    s3 = session.client("s3")
    bucket = "skycalm-mocked-grid"
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "eu-north-1"})
    table = session.resource("dynamodb").create_table(
        TableName="runs",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    store = AwsStore(s3, bucket, table)
    pin = "gfs-20261124-12"
    manifest = store.manifest(pin)
    assert manifest and store.published_manifest(pin) is None and store.latest() is None
    store.publish(REPLAY_ROOT / pin, manifest)
    store.publish(REPLAY_ROOT / pin, manifest)
    assert store.published_manifest(pin) == manifest and store.latest() == pin
    store.advance("gfs-20261124-06")
    assert store.latest() == pin
    corrupt = deepcopy(manifest)
    corrupt["leads"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        store.publish(REPLAY_ROOT / pin, corrupt)
    monkeypatch.setattr(handler, "store", lambda: store)
    event = {
        "requestContext": {"http": {"method": "GET"}},
        "rawPath": "/api/forecast",
        "rawQueryString": "origin=BCN&destination=ARN&departure=2026-11-24T18%3A00%3A00Z&run="
        + pin,
    }
    result = handler.handler(event, SimpleNamespace(aws_request_id="local-test"))
    assert result["statusCode"] == 200 and json.loads(result["body"])["peak"] == "moderate"
