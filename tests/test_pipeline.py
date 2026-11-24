import json
from datetime import UTC, datetime
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws

from services.forecast.aws import AwsStore
from services.forecast.schema import LEADS
from services.forecast.storage import REPLAY_ROOT
from services.pipeline import handlers
from services.pipeline.artifacts import StagedGrid
from services.pipeline.contract import (
    AVAILABLE,
    PROBE,
    READY,
    REPLAYS,
    SOURCE,
    job_spec,
    send_event,
)
from services.pipeline.discovery import candidate, complete_run
from services.pipeline.jobs import claim, phase, release

RUN = REPLAYS[0]
JOB = job_spec(RUN, "replay-" + "a" * 32, "replay")


@pytest.fixture
def stores(monkeypatch):
    with mock_aws():
        session = boto3.Session(region_name="eu-north-1")
        s3 = session.client("s3")
        s3.create_bucket(
            Bucket="class-weather", CreateBucketConfiguration={"LocationConstraint": "eu-north-1"}
        )
        db = session.resource("dynamodb")

        def make(name):
            return db.create_table(
                TableName=name,
                KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )

        jobs = make("jobs")
        weather = AwsStore(s3, "class-weather", make("weather"))
        monkeypatch.setattr(handlers.runtime, "table", lambda: jobs)
        monkeypatch.setattr(handlers.runtime, "weather", lambda: weather)
        monkeypatch.setattr(handlers.runtime, "client", lambda name: s3)
        monkeypatch.setenv("SKYCALM_BUCKET", "class-weather")
        yield jobs, weather


def item(table, job=JOB):
    return table.get_item(Key={"pk": "job#" + job["jobId"]}, ConsistentRead=True).get("Item", {})


def do(action, job=JOB):
    return handlers.workflow({"action": action, "job": job}, None)


def seed(weather, job):
    root = REPLAY_ROOT / job["runId"]
    StagedGrid(weather, job).publish(root, json.loads((root / "manifest.json").read_text()))


def test_lease_is_exclusive_idempotent_and_can_be_recovered(stores):
    jobs, _ = stores
    second = job_spec(REPLAYS[1], "replay-" + "b" * 32, "replay")
    assert claim(jobs, JOB) and claim(jobs, JOB)
    assert not claim(jobs, second)
    assert phase(item(jobs, second)) == "queued"
    release(jobs, second)
    assert not claim(jobs, second)
    jobs.update_item(
        Key={"pk": "active"},
        UpdateExpression="SET expiresAt=:old",
        ExpressionAttributeValues={":old": 0},
    )
    assert claim(jobs, second)
    release(jobs, JOB)
    assert jobs.get_item(Key={"pk": "active"})["Item"]["jobId"] == second["jobId"]


def test_replay_fanout_can_finish_in_any_order_and_repeatedly(stores):
    jobs, weather = stores
    weather.advance(REPLAYS[1])
    assert do("claim")["acquired"]
    with pytest.raises(ValueError, match="complete manifest"):
        do("verify")
    seed(weather, JOB)
    do("verify")
    handlers.receipt(READY, JOB)
    handlers.rescore(READY, JOB)
    assert phase(item(jobs)) == "delivering"
    do("sent")
    before = item(jobs)
    assert phase(before) == "ready" and len(before["route"]["categories"]) == 69
    handlers.rescore(READY, JOB)
    handlers.receipt(READY, JOB)
    do("sent")
    assert item(jobs) == before and weather.latest() == REPLAYS[1]
    files = weather.s3.list_objects_v2(Bucket=weather.bucket, Prefix="pipeline/receipts/")
    assert files["KeyCount"] == 1


def test_live_pointer_advances_only_after_event_acceptance(stores):
    jobs, weather = stores
    live = job_spec(RUN, "live-" + RUN, "live")
    do("claim", live)
    seed(weather, live)
    do("verify", live)
    assert weather.latest() is None
    do("sent", live)
    assert weather.latest() == RUN
    weather.advance(REPLAYS[1])
    do("sent", live)
    assert weather.latest() == REPLAYS[1] and item(jobs, live)["leads"] == 13


def test_batch_failure_isolated_and_event_publication_checked(stores):
    def record(i, kind):
        return {
            "messageId": i,
            "body": json.dumps({"source": SOURCE, "detail-type": kind, "detail": JOB}),
        }

    jobs, weather = stores
    seed(weather, JOB)
    result = handlers.routes({"Records": [record("bad", PROBE), record("ok", READY)]}, None)
    assert result == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    assert "routeAt" in item(jobs)
    events = SimpleNamespace(
        put_events=lambda **kwargs: {
            "FailedEntryCount": 1,
            "Entries": [{"ErrorCode": "InternalFailure"}],
        }
    )
    with pytest.raises(RuntimeError, match="InternalFailure"):
        send_event(events, "class", AVAILABLE, JOB)


def test_sfn_admission_is_named_and_detects_payload_collisions(monkeypatch):
    class Exists(Exception):
        pass

    calls = {}

    def start(**kw):
        if kw["name"] in calls:
            raise Exists
        calls[kw["name"]] = kw["input"]

    client = SimpleNamespace(
        start_execution=start,
        exceptions=SimpleNamespace(ExecutionAlreadyExists=Exists),
        describe_execution=lambda **kw: {"input": calls[JOB["jobId"]]},
    )
    monkeypatch.setattr(handlers.runtime, "client", lambda service: client)
    monkeypatch.setenv(
        "STATE_MACHINE", "arn:aws:states:eu-north-1:123456789012:stateMachine:skycalm"
    )
    handlers.start(AVAILABLE, JOB)
    handlers.start(AVAILABLE, JOB)
    assert list(calls) == [JOB["jobId"]]
    with pytest.raises(ValueError, match="another request"):
        handlers.start(AVAILABLE, {**JOB, "runId": REPLAYS[1]})


def test_noaa_requires_all_26_objects_and_never_moves_backward():
    clock = datetime(2026, 11, 21, 8, tzinfo=UTC)
    prefix = "gfs.20261121/06/atmos/gfs.t06z.pgrb2.0p25.f"
    keys = [prefix + f"{lead:03}" + ext for lead in LEADS for ext in ("", ".idx")]

    def source(names):
        xml = (
            "<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'>"
            + "".join(
                "<Contents><Key>" + key + "</Key><Size>100</Size></Contents>" for key in names
            )
            + "</ListBucketResult>"
        )
        return SimpleNamespace(get=lambda *args, **kwargs: (xml.encode(), {}))

    assert not complete_run(source(keys[:-1]), clock.replace(hour=6))
    assert candidate(source(keys), None, clock) == RUN
    assert candidate(source(keys), RUN, clock) is None
    assert candidate(source(keys), REPLAYS[1], clock) is None
