import gzip
import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from services.forecast.api import RequestError, respond
from services.forecast.storage import LocalStore
from services.observations.archive import ARCHIVE, local_latest, objects, public_map, publish_local
from services.observations.awc import collect, instant, normalize, report
from services.observations.handler import publish

CLOCK = instant("2026-11-24T18:05:00Z")
PIN = "gfs-20261124-12"
ROW = {
    "obsTime": int(CLOCK.timestamp()) - 120,
    "lat": 50,
    "lon": 8,
    "fltLvl": "230",
    "tbInt1": "MOD",
    "tbInt2": "NEG",
    "pirepType": "AIREP",
    "rawOb": "excluded",
    "icaoId": "excluded",
}
ADVISORY = {
    "icaoId": "TEST",
    "firId": "FIR",
    "seriesId": "2",
    "hazard": "TURB",
    "qualifier": "SEV",
    "geom": "AREA",
    "base": 12000,
    "top": 37000,
    "validTimeFrom": int(CLOCK.timestamp()) - 3600,
    "validTimeTo": int(CLOCK.timestamp()) + 3600,
    "coords": [{"lon": 0, "lat": 48}, {"lon": 2, "lat": 48}, {"lon": 1, "lat": 50}],
}


def test_normalize_and_deidentify_observations():
    result = normalize(CLOCK, [ADVISORY], [ROW, {**ROW, "tbInt1": None, "tbInt2": None}], [ROW])
    assert len(result["items"]) == 3
    public = public_map(result)
    assert len(public["items"]) == 2 and "excluded" not in json.dumps(public)
    obs = next(i for i in public["items"] if i["kind"] == "report")
    assert (obs["intensity"], obs["codes"], obs["baseFt"]) == ("moderate", ["MOD", "NEG"], 23000)
    assert report({**ROW, "tbInt1": "NEG"}, CLOCK)["intensity"] == "smooth"
    area = next(i for i in public["items"] if i["kind"] == "sigmet")["geometry"]["coordinates"][0]
    assert area[0] == area[-1]


def test_exclude_outside_expired_and_future_data():
    past = int(CLOCK.timestamp()) - 1
    reports = [
        {**ROW, "lat": 10},
        {**ROW, "receiptTime": "2026-11-25T00:00:00Z"},
        {**ROW, "obsTime": past - 8 * 3600},
    ]
    warnings = [
        {**ADVISORY, "validTimeTo": past},
        {**ADVISORY, "geom": "LINE"},
        {**ADVISORY, "coords": [{"lon": j, "lat": -50} for j in range(3)]},
    ]
    assert normalize(CLOCK, warnings, reports, [])["items"] == []


def test_cap_supplement_and_empty_feed():
    calls = []

    def get(url):
        calls.append(url)
        if "sigmet?" in url:
            return []
        return [ROW] if "inten=lgt" in url else [ROW] * 400

    snap, raw = collect(CLOCK, get)
    assert (
        len(calls) == 3
        and snap["limited"]
        and len(snap["items"]) == 1
        and len(raw["reports"]) == 400
    )
    assert collect(CLOCK, lambda _: [])[0]["items"] == []


def test_older_snapshots_replay_and_absent_live(tmp_path):
    snapshot = normalize(CLOCK, [], [ROW], [])
    v = publish_local(tmp_path, snapshot, {})
    publish_local(tmp_path, {**snapshot, "asOf": "2026-11-23T18:05:00Z"}, {})
    assert local_latest(tmp_path)["asOf"] == snapshot["asOf"]
    assert publish_local(tmp_path, snapshot, {}) == v
    store = LocalStore(tmp_path)
    assert respond("/api/observations", {}, store, CLOCK + timedelta(hours=2))["stale"]
    assert respond("/api/observations", {"run": PIN}, store, CLOCK)["mode"] == "replay"
    with pytest.raises(RequestError, match="No weather observations"):
        respond("/api/observations", {}, LocalStore(tmp_path / "missing"), CLOCK)
    with pytest.raises(RequestError, match="valid forecast run"):
        respond("/api/observations", {"run": "../bad"}, store, CLOCK)


@mock_aws
def test_cloud_reads_only_complete_snapshot(tmp_path):
    from services.forecast.aws import AwsStore

    sess = boto3.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing", region_name="eu-north-1"
    )
    s3 = sess.client("s3")
    bucket = "fixture-skycalm-observations"
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "eu-north-1"})
    table = sess.resource("dynamodb").create_table(
        TableName="runs",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    store = AwsStore(s3, bucket, table)
    snap = normalize(CLOCK, [], [ROW], [])
    assert store.observation_snapshot("latest") is None

    class Broken:
        def put_object(self, **kwargs):
            raise OSError("write interrupted")

    with pytest.raises(OSError):
        publish(snap, {}, Broken(), bucket, table)
    assert store.observation_snapshot("latest") is None
    publish(snap, {}, s3, bucket, table)
    publish({**snap, "asOf": "2026-11-23T18:05:00Z"}, {}, s3, bucket, table)
    assert store.observation_snapshot("latest") == public_map(snap)
    assert store.observation_snapshot(PIN) is None
    version, files = objects(snap, {})
    key = next(k for k in files if "/history/" in k)
    assert json.loads(gzip.decompress(files[key]))["intensity"] == "moderate"
    assert len(version) > 10


def test_history_query_deduplicates_and_counts_unreported():
    db = sqlite3.connect(":memory:")
    db.execute("ATTACH DATABASE ':memory:' AS skycalm_dev_weather")
    db.execute(
        "CREATE TABLE skycalm_dev_weather.observations (day, id, kind, observed, intensity, source, expires, base_ft, top_ft)"
    )
    paths = sorted((ARCHIVE.parent / "observation-history").glob("day=*/*.json.gz"))
    assert len(paths) == 5
    known = {}
    for path in paths:
        for line in gzip.decompress(path.read_bytes()).splitlines():
            row = json.loads(line)
            record = [
                path.parent.name[4:],
                *[
                    row[k]
                    for k in (
                        "id",
                        "kind",
                        "observed",
                        "intensity",
                        "source",
                        "expires",
                        "base_ft",
                        "top_ft",
                    )
                ],
            ]
            db.executemany(
                "INSERT INTO skycalm_dev_weather.observations VALUES (?,?,?,?,?,?,?,?,?)",
                [record, record],
            )
            if row["kind"] == "report":
                known.setdefault(row["intensity"], set()).add(row["id"])
    root = Path(__file__).resolve().parents[1]
    result = list(db.execute((root / "analytics/monthly_reports.sql").read_text()))
    assert {r[1]: r[2] for r in result} == {k: len(v) for k, v in known.items()}
    assert {"moderate", "unreported"} <= known.keys()
    assert list(db.execute((root / "analytics/advisories.sql").read_text()))
