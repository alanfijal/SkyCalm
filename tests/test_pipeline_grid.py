import gzip
import hashlib
import json

import boto3
import pytest
from moto import mock_aws

from grid.replay import rebuild
from services.forecast.aws import AwsStore
from services.forecast.schema import LEADS, tile_name
from services.forecast.storage import REPLAY_ROOT, LocalStore
from services.pipeline.artifacts import StagedGrid
from services.pipeline.contract import REPLAYS, job_spec


@pytest.mark.parametrize("run", REPLAYS)
def test_rescore_reproduces_each_uncompressed_archived_tile(tmp_path, run):
    target = LocalStore(tmp_path)
    result = rebuild(run, target)
    assert target.published_manifest(run) == result
    for lead in LEADS:
        actual = target.tile(run, lead, result["leads"][LEADS.index(lead)]["sha256"])
        assert gzip.decompress(actual) == gzip.decompress(
            (REPLAY_ROOT / run / tile_name(lead)).read_bytes()
        )


@mock_aws
def test_staged_live_and_replay_never_advance_the_serving_head():
    session = boto3.Session(region_name="eu-north-1")
    s3 = session.client("s3")
    s3.create_bucket(
        Bucket="skycalm-pipeline-test",
        CreateBucketConfiguration={"LocationConstraint": "eu-north-1"},
    )
    table = session.resource("dynamodb").create_table(
        TableName="runs",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    base = AwsStore(s3, "skycalm-pipeline-test", table)
    run = REPLAYS[0]
    old = "gfs-20261124-12"
    base.advance(old)
    for mode, job in [("replay", "replay-" + "1" * 32), ("live", "live-" + run)]:
        target = StagedGrid(base, job_spec(run, job, mode))
        assert target.manifest(run) is None
        manifest = json.loads((REPLAY_ROOT / run / "manifest.json").read_text())
        target.publish(REPLAY_ROOT / run, manifest)
        assert target.manifest(run) == manifest
        assert (
            hashlib.sha256(target.tile(run, 0, manifest["leads"][0]["sha256"])).hexdigest()
            == manifest["leads"][0]["sha256"]
        )
        assert base.latest() == old
        if mode == "replay":
            assert base.published_manifest(run) is None
