import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier
from urllib.error import HTTPError

import boto3
import pytest
from moto import mock_aws

from services.flights import provider
from services.flights.aws import DynamoLedger
from services.flights.local import LocalLedger
from services.flights.lookup import lookup
from services.forecast.api import RequestError

DAY = date(2026, 11, 28)
NOW = int(datetime(2026, 11, 26, 12, tzinfo=UTC).timestamp())
BODY = {"number": " ib 3204 ", "date": str(DAY)}


def flight(dep="MAD", arr="LHR", local="2026-11-28 00:30+01:00", utc="2026-11-27 23:30Z"):
    return {
        "number": "IB 3204",
        "airline": {"iata": "IB", "icao": "IBE"},
        "departure": {"airport": {"iata": dep}, "scheduledTime": {"utc": utc, "local": local}},
        "arrival": {
            "airport": {"iata": arr},
            "scheduledTime": {"utc": "2026-11-28 01:40Z", "local": "2026-11-28 01:40+00:00"},
        },
        "aircraft": {"model": "Airbus A320", "reg": "omit"},
        "status": "Expected",
    }


def test_local_departure_date_codeshares_and_multileg():
    late = flight("LHR", "EDI", "2026-11-28 06:00+00:00", "2026-11-28 06:00Z")
    otherday = flight(local="2026-11-27 00:30+01:00", utc="2026-11-26 23:30Z")
    assert provider.number("U2 0021") == "U221"
    assert provider.query(BODY, DAY) == ("IB3204", DAY)
    for code in ("IB3204", "IBE3204"):
        result = provider.select(
            [
                late,
                flight(),
                flight(),
                otherday,
                {**flight(), "isCargo": True},
                {**flight(), "number": "IB444"},
            ],
            code,
            DAY,
        )
        assert [r["departure"]["code"] for r in result] == ["MAD", "LHR"]
        assert result[0]["departure"]["time"]["utc"] == "2026-11-27T23:30:00Z"
        assert result[0]["aircraft"] == "Airbus A320" and "reg" not in json.dumps(result)
        assert result[1]["arrival"]["time"] is None
    missing = flight()
    missing["departure"]["scheduledTime"]["local"] = "2026-11-28 00:30+07:00"
    with pytest.raises(ValueError):
        provider.select([missing], "IB3204", DAY)
    for body in (
        {"number": "IB/321", "date": str(DAY)},
        {**BODY, "date": "20261128"},
        {**BODY, "date": "2029-01-01"},
    ):
        with pytest.raises(RequestError):
            provider.query(body, DAY)


def test_provider_single_call_and_failure_contract():
    calls = []

    class Response(io.BytesIO):
        status = 200

    def send(request, timeout):
        calls.append(request)
        assert request.get_header("X-rapidapi-key") == "key"
        assert (
            timeout == 5
            and "dateLocalRole=Departure" in request.full_url
            and "withFlightPlan=false" in request.full_url
        )
        return Response(json.dumps([flight()]).encode())

    assert len(provider.fetch("IB3204", DAY, "key\n", open_request=send)) == 1
    assert len(calls) == 1 and "key" not in calls[0].full_url

    def none(*args, **kwargs):
        r = Response(b"")
        r.status = 204
        return r

    assert provider.fetch("IB3204", DAY, "key", open_request=none) == []

    def limited(*args, **kwargs):
        raise HTTPError("https://example.invalid", 429, "", {}, None)

    with pytest.raises(RequestError, match="busy") as exc:
        provider.fetch("IB3204", DAY, "key", open_request=limited)
    assert exc.value.status == 429


def test_durable_quota_empty_cache_and_new_month(tmp_path):
    ledger = LocalLedger(tmp_path)
    calls = []

    def loader(n, d):
        calls.append(n)
        return []

    def run(n, owner="A", offset=0):
        return lookup({**BODY, "number": n}, owner, ledger, loader, clock=lambda: NOW + offset)

    assert not run("IB1")["cached"]
    assert run("IB1", "B")["cached"] and calls == ["IB1"]
    with pytest.raises(RequestError, match="moment"):
        run("IB2", "B")
    assert not run("IB1", offset=181)["cached"]
    run("IB2", offset=185)
    with pytest.raises(RequestError, match="allowance"):
        run("IB3", offset=190)
    assert len(LocalLedger(tmp_path).read("budget")["recent"]) == 3
    run("IB4", "B", 192)
    run("IB5", "C", 195)
    with pytest.raises(RequestError, match="allowance"):
        run("IB6", "D", 198)
    assert not run("IB6", "A", 86400)["cached"]
    before = ledger.read("budget")
    full = {**before, "recent": [NOW] * 60, "rev": "full"}
    assert ledger.reserve(before["rev"], full)
    with pytest.raises(RequestError, match="allowance"):
        run("IB7", "E", 86420)
    with pytest.raises(RequestError, match="allowance"):
        run("IB7", "E", 7 * 86400)
    assert not run("IB7", "E", 33 * 86400)["cached"]


def test_one_reservation_survives_races_and_failed_provider_attempts(tmp_path):
    ledger = LocalLedger(tmp_path)
    barrier = Barrier(2)

    def reserve(i):
        barrier.wait()
        return ledger.reserve(None, {"rev": str(i)})

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, (1, 2))) == [False, True]

    def failure(*args):
        raise RequestError("outage", "Unavailable", 503)

    with pytest.raises(RequestError):
        lookup(BODY, "A", ledger, failure, clock=lambda: NOW)
    assert len(ledger.read("budget")["recent"]) == 1 and ledger.read("budget")["holdUntil"] == 0
    assert not ledger.read("schedule#IB3204#2026-11-28")


@mock_aws
def test_dynamo_cache_and_stale_completion():
    db = boto3.client("dynamodb", region_name="eu-north-1")
    db.create_table(
        TableName="schedule",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    ledger = DynamoLedger(db, "schedule")

    def load(n, d):
        return provider.select([flight()], n, d)

    first = lookup(BODY, "A", ledger, load, clock=lambda: NOW)
    again = lookup(
        BODY, "B", ledger, lambda *_: pytest.fail("provider called on cache hit"), clock=lambda: NOW
    )
    assert first["flights"] == again["flights"] and again["cached"]
    budget = ledger.read("budget")
    assert not ledger.reserve("old", {"rev": "new"})
    ledger.finish({**budget, "rev": "stale"}, "wrong", {"flights": [], "expiresAt": NOW + 60})
    assert not ledger.read("wrong")
