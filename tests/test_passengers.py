import base64
import json
from io import BytesIO
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws
from PIL import Image

from services.forecast.api import RequestError
from services.passengers import api, worker
from services.passengers.domain import changed, flight_input, identity, subscription
from services.passengers.store import PassengerStore

NOW = datetime(2026, 11, 25, 12, tzinfo=UTC)
T = int(NOW.timestamp())
OWNER = str(uuid4())
OTHER = str(uuid4())


@pytest.fixture
def store():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(
            TableName="passengers",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
                {"AttributeName": "watch", "AttributeType": "S"},
                {"AttributeName": "departureEpoch", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "departures",
                    "KeySchema": [
                        {"AttributeName": "watch", "KeyType": "HASH"},
                        {"AttributeName": "departureEpoch", "KeyType": "RANGE"},
                    ],
                    "Projection": {
                        "ProjectionType": "INCLUDE",
                        "NonKeyAttributes": ["slot", "revision"],
                    },
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield PassengerStore(client, "passengers")


def http(
    path="/api/me", method="GET", body=None, owner=OWNER, scope=api.READ, groups="[]", use="access"
):
    return {
        "rawPath": path,
        "body": json.dumps(body or {}),
        "headers": {"authorization": "Bearer demonstration"},
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "token_use": use,
                        "sub": owner,
                        "username": "local-user",
                        "cognito:groups": groups,
                        "scope": scope,
                    }
                }
            },
        },
    }


def inputs():
    return {
        "origin": "edi",
        "destination": "OPO",
        "departure": (NOW + timedelta(hours=30)).isoformat(),
        "revision": str(uuid4()),
    }


def save(store, owner=OWNER):
    body = inputs()
    return api.dispatch(http("/api/me/flights/1", "PUT", body, owner, api.WRITE), store, now=NOW)


def test_private_crud_edit_collision_and_eventual_expiry(store):
    body = inputs()

    def put(b, owner=OWNER):
        return api.dispatch(http("/api/me/flights/1", "PUT", b, owner, api.WRITE), store, now=NOW)

    first = put(body)
    assert put(body) == first
    assert not api.dispatch(http(owner=OTHER), store, now=NOW)["flights"]
    with pytest.raises(RequestError, match="changed"):
        put({**inputs(), "previous": str(uuid4())})
    edited = put({**inputs(), "previous": first["revision"], "origin": "AMS"})
    assert edited["id"] == first["id"]
    with pytest.raises(RequestError):
        api.dispatch(
            http("/api/me/flights/1", "DELETE", {"revision": first["revision"]}, scope=api.WRITE),
            store,
            now=NOW,
        )
    assert not api.dispatch(http(), store, now=NOW + timedelta(days=12))["flights"]
    api.dispatch(
        http("/api/me/flights/1", "DELETE", {"revision": edited["revision"]}, scope=api.WRITE),
        store,
        now=NOW,
    )
    assert not api.dispatch(http(), store, now=NOW)["flights"]


@pytest.mark.parametrize(
    "patch",
    [
        {"origin": "JFK"},
        {"origin": "OPO"},
        {"departure": "2026-11-25T18:00"},
        {"departure": NOW.isoformat()},
        {"departure": "2035-01-01T00:00:00Z"},
    ],
)
def test_route_validation(patch):
    with pytest.raises(RequestError):
        flight_input({**inputs(), **patch}, NOW)


def test_scopes_group_and_token_use():
    for scope, groups, use in [
        (api.READ, "[admins]", "access"),
        (api.ADMIN, "[passengers]", "access"),
        (api.ADMIN, "[admins]", "id"),
    ]:
        with pytest.raises(RequestError):
            identity(http(scope=scope, groups=groups, use=use), api.ADMIN)
    assert identity(http(scope=api.ADMIN, groups="[admins]"), api.ADMIN)[0] == OWNER


@pytest.mark.parametrize(
    ("latest", "manifest", "expected"),
    [(None, None, None), ("run1", {}, None), ("run2", {"model": {"version": 1}}, 1)],
)
def test_health_reads_the_version_from_the_published_grid(
    store, monkeypatch, latest, manifest, expected
):
    weather = Mock()
    weather.latest.return_value = latest
    weather.published_manifest.return_value = manifest
    weather.table.get_item.return_value = {"Item": {"asOfTime": "2026-11-25T06:00:00Z"}}
    jobs = Mock()
    jobs.get_item.return_value = {}
    monkeypatch.setattr(api.runtime, "weather", lambda: weather)
    monkeypatch.setattr(api.runtime, "table", lambda: jobs)
    monkeypatch.setenv("HEALTH_QUEUES", "{}")
    result = api.dispatch(
        http("/api/admin/health", scope=api.ADMIN, groups="[admins]"),
        store,
        now=NOW,
        clients=Mock(),
    )
    assert result["modelVersion"] == expected
    assert result["manifestAvailable"] is (manifest is not None)
    assert result["observationsAsOf"] == "2026-11-25T06:00:00Z"
    if latest:
        weather.published_manifest.assert_called_once_with(latest)
    else:
        weather.published_manifest.assert_not_called()


def test_forecast_outbox_and_three_hour_limit(store):
    save(store)

    def get():
        return store.get(OWNER, "flight#1")

    base = {"peak": "smooth", "firstRough": None}
    rough = {"peak": "moderate", "firstRough": 20}
    store.record_forecast(get(), "gfs-1", base, T)
    store.record_forecast(get(), "gfs-2", rough, T + 1)
    first = api.view(store, OWNER, T + 1)["inbox"][0]
    assert first["peak"] == "moderate"
    store.record_forecast(get(), "gfs-3", base, T + 2)
    assert get()["assessment"]["peak"] == "smooth"
    assert api.view(store, OWNER, T + 2)["inbox"][0] == first
    store.record_forecast(get(), "gfs-4", rough, T + 10802)
    assert len(api.view(store, OWNER, T)["inbox"]) == 2
    with pytest.raises(RequestError):
        store.record_forecast(get(), "gfs-3", base, T + 10803)
    assert not changed(rough, {**rough, "firstRough": 50})
    assert changed(rough, {**rough, "firstRough": 51})


def test_retry_and_old_reminder_after_edit(store):
    first = save(store)
    msg = {"owner": OWNER, "slot": 1, "revision": first["revision"], "hours": 24}
    worker.process(store, "reminder", msg, T, 1)
    worker.process(store, "reminder", msg, T, 2)
    assert len(api.view(store, OWNER, T)["inbox"]) == 1
    assert "peak" not in api.view(store, OWNER, T)["inbox"][0]
    api.dispatch(
        http(
            "/api/me/flights/1", "PUT", {**inputs(), "previous": first["revision"]}, scope=api.WRITE
        ),
        store,
        now=NOW,
    )
    worker.process(store, "reminder", {**msg, "hours": 3}, T, 1)
    assert len(api.view(store, OWNER, T)["inbox"]) == 1


def test_alert_details_require_explicit_preference_and_notification_scope(store):
    def toggle(value, scope=api.PREF):
        request = http(
            "/api/me/preferences",
            "PUT",
            {"channel": "explainAlerts", "enabled": value},
            scope=scope,
        )
        return api.dispatch(request, store, now=NOW)

    assert api.view(store, OWNER, T)["preferences"]["explainAlerts"] is False
    with pytest.raises(RequestError):
        toggle("true")
    with pytest.raises(RequestError):
        toggle(True, api.READ)
    assert toggle(True) == {**api.DEFAULTS, "push": False, "email": False, "explainAlerts": True}
    assert api.view(store, OTHER, T)["preferences"]["explainAlerts"] is False
    assert toggle(False)["explainAlerts"] is False


def test_scheduler_marks_one_time_reminders_and_skips_past(store):
    save(store)
    flight = store.get(OWNER, "flight#1")

    class Scheduler:
        def __init__(self):
            self.created = []
            self.deleted = []

        def create_schedule(self, **kw):
            self.created.append(kw)

        def delete_schedule(self, **kw):
            self.deleted.append(kw)

    s = Scheduler()
    env = dict(SCHEDULE_GROUP="group", SCHEDULER_ROLE="role", WORK_ARN="queue", DEAD_ARN="dead")
    worker.schedules(None, flight, s, T, env)
    assert len(s.created) == 2 and all(x["ActionAfterCompletion"] == "DELETE" for x in s.created)
    worker.schedules(flight, None, s, T, env)
    assert {x["Name"] for x in s.deleted} == {x["Name"] for x in s.created}
    s.created.clear()
    worker.schedules(None, flight, s, T + 12 * 3600, env)
    assert [json.loads(x["Target"]["Input"])["detail"]["hours"] for x in s.created] == [3]


def test_preferences_export_erasure_and_replay_guard(store, monkeypatch):
    monkeypatch.setenv("USER_POOL", "demo")
    monkeypatch.setenv("SES_RECIPIENT", "school@example.edu")

    class Cognito:
        def get_user(self, **kwargs):
            return {
                "UserAttributes": [
                    {"Name": "email", "Value": "school@example.edu"},
                    {"Name": "email_verified", "Value": "true"},
                ]
            }

        def admin_delete_user(self, **kwargs):
            assert kwargs["Username"] == "local-user"

    def clients(name):
        return Cognito()

    save(store)
    save(store, OTHER)
    api.dispatch(
        http(
            "/api/me/preferences",
            "PUT",
            {"channel": "email", "enabled": True, "email": "outsider@example.com"},
            scope=api.PREF,
        ),
        store,
        clients,
        NOW,
    )
    assert (
        api.dispatch(http("/api/me/export"), store, clients, NOW)["verifiedEmailForDelivery"]
        == "school@example.edu"
    )
    api.dispatch(
        http("/api/me", "DELETE", {"confirm": "DELETE"}, scope=api.WRITE), store, clients, NOW
    )
    assert list(store.rows(OWNER, T))[0]["erasing"]
    assert len(list(store.rows(OTHER, T))) == 1
    with pytest.raises(RequestError):
        save(store)
    with pytest.raises(RequestError):
        store.preferences(OWNER, {}, None)


def test_ignores_body_identity_and_blocks_unknown_push_endpoint(store):
    for endpoint in (
        "http://fcm.googleapis.com/test",
        "https://example.org/test",
        "https://fcm.googleapis.com.evil.example/test",
    ):
        with pytest.raises(RequestError):
            subscription({"endpoint": endpoint, "keys": {}})
    api.dispatch(
        http("/api/me/flights/1", "PUT", {**inputs(), "owner": OTHER}, scope=api.WRITE),
        store,
        now=NOW,
    )
    assert len(list(store.rows(OWNER, T))) == 1 and not list(store.rows(OTHER, T))


def test_numbered_itinerary_persists_times_and_lookup_requires_read_scope(store, monkeypatch):
    body = {
        "origin": "AMS",
        "destination": "LHR",
        "flightNumber": "KL 1001",
        "departure": "2026-11-27T07:20:00+01:00",
        "scheduledArrival": "2026-11-27T07:40:00Z",
        "revision": str(uuid4()),
    }
    saved = api.dispatch(http("/api/me/flights/1", "PUT", body, scope=api.WRITE), store, now=NOW)
    assert saved["flightNumber"] == "KL1001" and saved["arrivalScheduled"]
    assert saved["arrival"] == "2026-11-27T07:40:00Z"
    assert api.dispatch(http(), store, now=NOW)["flights"][0]["flightNumber"] == "KL1001"
    monkeypatch.setattr(
        "services.flights.aws.aws_lookup",
        lambda body, owner: {"number": body["number"], "owner": owner},
    )
    lookup = http("/api/me/flight-lookup", "POST", {"number": "KL1001"})
    assert api.dispatch(lookup, store, now=NOW)["owner"] == OWNER
    lookup["requestContext"].pop("authorizer")
    with pytest.raises(RequestError) as exc:
        api.dispatch(lookup, store, now=NOW)
    assert exc.value.status == 401


def test_private_flight_history_alerts_and_isolation(store):
    from services.forecast.api import respond
    from services.forecast.storage import REPLAY_ROOT, LocalStore
    from services.passengers.domain import snapshot
    from services.pipeline.contract import demonstration_route

    flight = save(store)
    other = save(store, OTHER)
    run = "gfs-20261124-12"
    forecast = respond(
        "/api/forecast",
        {**demonstration_route(run), "altitudes": "1"},
        LocalStore(REPLAY_ROOT, REPLAY_ROOT),
    )
    summary = snapshot(forecast)
    row = store.get(OWNER, "flight#1")
    store.record_forecast(row, "run-1", summary, T, forecast=forecast)
    new = {"peak": "severe" if summary["peak"] != "severe" else "light", "firstRough": 2}
    store.record_forecast(store.get(OWNER, "flight#1"), "run-2", new, T + 65, test=True)
    with pytest.raises(RequestError):
        store.record_forecast(row, "run-1", summary, T + 70, forecast=forecast)
    for owner, expected in ((OWNER, flight), (OTHER, other)):
        details = api.dispatch(
            http("/api/me/flights/1/detail", body={"owner": OWNER}, owner=owner), store, now=NOW
        )
        assert details["flight"]["id"] == expected["id"]
        if owner == OTHER:
            assert details["forecast"] is None and details["history"] == []
        else:
            assert details["forecast"]["samples"] == forecast["samples"]
            assert [p["peak"] for p in details["history"]] == [summary["peak"], new["peak"]]
            assert set(details["forecast"]["altitudeBands"]) == {"30000", "34000", "38000", "40000"}
    notice = api.view(store, OWNER, T)["inbox"][0]
    assert notice["flightId"] == flight["id"] and notice["runMarker"] == "run-2"
    url = "/api/me/notices/" + notice["noticeId"]
    with pytest.raises(RequestError):
        api.dispatch(http(url, "PUT", {"read": True}, OTHER, api.WRITE), store, now=NOW)
    for read in (True, False):
        api.dispatch(http(url, "PUT", {"read": read}, scope=api.WRITE), store, now=NOW)
        assert api.view(store, OWNER, T)["inbox"][0]["isRead"] is read
    store.remove(OWNER, 1, flight["revision"])
    replace = save(store)
    assert replace["id"] != notice["flightId"]
    assert not store.get(OWNER, "forecast#" + flight["id"])


def test_family_projection_excludes_private_fields_at_every_level():
    from services.passengers.sharing import family_forecast

    data = {
        "origin": {"code": "EDI", "private": "private"},
        "destination": {"code": "OPO"},
        "run": {"runId": "gfs", "private": "private"},
        "samples": [{"category": "moderate", "private": "private"}],
        "private": "private",
    }
    assert family_forecast(data) == {
        "origin": {"code": "EDI"},
        "destination": {"code": "OPO"},
        "run": {"runId": "gfs"},
        "samples": [{"category": "moderate"}],
    }


def test_anonymous_family_links_expire_rotate_and_revoke(store):
    flight = save(store)
    url = "/api/me/flights/1/share"

    def share(method="POST", owner=OWNER):
        return api.dispatch(
            http(url, method, {"revision": flight["revision"]}, owner, api.WRITE), store, now=NOW
        )

    def visit(token, when=NOW):
        event = http("/api/shared", "POST", {"token": token, "owner": OTHER})
        del event["requestContext"]["authorizer"]
        return api.dispatch(event, store, now=when)

    with pytest.raises(RequestError):
        share(owner=OTHER)
    from services.passengers.preview import preview_response

    def card(ticket, image=False, when=T):
        return preview_response(
            store, ticket, image, when, "https://app.example", "https://api.example"
        )

    grant = share()
    token, preview = grant["token"], grant["preview"]
    html = card(preview)
    assert html["statusCode"] == 200 and "no-store" in html["headers"]["cache-control"]
    assert (
        "og:image" in html["body"] and f"https://api.example/family/{preview}.png" in html["body"]
    )
    assert token not in html["body"] and OWNER not in html["body"] and "watch" not in html["body"]
    png = card(preview, True)
    assert png["isBase64Encoded"] and png["headers"]["content-type"] == "image/png"
    with Image.open(BytesIO(base64.b64decode(png["body"]))) as picture:
        assert picture.format == "PNG" and picture.size == (1200, 630)
    for action in (
        lambda: visit(preview),
        lambda: card(token),
        lambda: card(preview, when=T + 86400),
    ):
        with pytest.raises(RequestError, match="expired"):
            action()
    shared = visit(token)
    assert set(shared) == {"flight", "forecast", "expiresAt"}
    assert set(shared["flight"]) == {"origin", "destination", "departure", "arrival", "watch"}
    assert OWNER not in token and OWNER not in json.dumps(shared, default=str)
    for value in (token[:-4], token[:-1] + ("a" if token[-1] != "a" else "b"), ""):
        with pytest.raises(RequestError, match="expired"):
            visit(value)
    with pytest.raises(RequestError, match="expired"):
        visit(token, NOW + timedelta(days=1))
    rotated = share()
    new = rotated["token"]
    with pytest.raises(RequestError):
        card(preview, True)
    with pytest.raises(RequestError):
        visit(token)
    share("DELETE")
    with pytest.raises(RequestError):
        card(rotated["preview"])
    with pytest.raises(RequestError):
        visit(new)
    new = share()["token"]
    api.dispatch(
        http(
            "/api/me/flights/1",
            "PUT",
            {**inputs(), "previous": flight["revision"]},
            scope=api.WRITE,
        ),
        store,
        now=NOW,
    )
    with pytest.raises(RequestError):
        visit(new)


def test_quiet_hours_sensitivity_and_account_session_cutoff(store):
    from services.passengers.preferences import inbox_only, settings_patch

    hours = {"start": "22:00", "end": "07:00", "zone": "Europe/Madrid"}
    prefs = settings_patch(
        {"quietHours": hours, "sensitivity": "moderate", "homeAirport": "BCN", "altitudeUnit": "m"}
    )
    for stamp in ("2026-10-25T00:30:00Z", "2026-10-25T01:30:00Z"):
        assert inbox_only({"kind": "reminder-3h"}, prefs, datetime.fromisoformat(stamp).timestamp())
    assert not inbox_only({"kind": "reminder-3h"}, prefs, T)
    assert inbox_only({"kind": "forecast-change", "peak": "light"}, prefs, T)
    assert not inbox_only({"kind": "forecast-change", "peak": "moderate"}, prefs, T)
    for patch in (
        {"quietHours": {**hours, "zone": "Invalid/Place"}},
        {"nervousFlyer": 1},
        {"homeAirport": "JFK"},
        {"email": "other"},
        {"quietHours": {**hours, "end": "22:00"}},
    ):
        with pytest.raises(RequestError):
            settings_patch(patch)
    cognito = Mock()
    api.dispatch(http("/api/me/sign-out", "POST", scope=api.WRITE), store, lambda _: cognito, NOW)
    cognito.global_sign_out.assert_called_once_with(AccessToken="demonstration")
    for path in ("/api/me", "/api/me/export", "/api/me/flight-lookup", "/api/admin/health"):
        req = http(
            path,
            "POST" if "lookup" in path else "GET",
            scope=api.ADMIN if "admin" in path else api.READ,
            groups="[admins]",
        )
        req["requestContext"]["authorizer"]["jwt"]["claims"]["auth_time"] = str(T - 1)
        with pytest.raises(RequestError, match="ended"):
            api.dispatch(req, store, now=NOW)
    fresh = http()
    fresh["requestContext"]["authorizer"]["jwt"]["claims"]["auth_time"] = str(T + 1)
    assert api.dispatch(fresh, store, now=NOW)["flights"] == []
    assert api.dispatch(http(owner=OTHER), store, now=NOW)["flights"] == []


def test_postflight_recap_qualifies_observations_and_expires(store):
    from services.forecast.api import respond
    from services.forecast.storage import REPLAY_ROOT, LocalStore
    from services.passengers.domain import snapshot
    from services.passengers.journey import detail
    from services.pipeline.contract import demonstration_route

    run = "gfs-20261124-12"
    forecast = respond(
        "/api/forecast", demonstration_route(run), LocalStore(REPLAY_ROOT, REPLAY_ROOT)
    )
    before = datetime.fromisoformat(forecast["departure"]) - timedelta(hours=3)
    route = flight_input(
        {"origin": "EDI", "destination": "OPO", "departure": forecast["departure"]}, before
    )
    actual = store.save(OWNER, 1, route, str(uuid4()), None, int(before.timestamp()))
    store.record_forecast(
        actual, run, snapshot(forecast), int(before.timestamp()), forecast=forecast
    )
    row = store.get(OWNER, "flight#1")
    weather = Mock()
    sample = forecast["samples"][20]
    report = {
        "kind": "report",
        "geometry": {"type": "Point", "coordinates": [sample["lon"], sample["lat"]]},
        "intensity": "moderate",
        "baseFt": sample["altitudeFt"],
        "id": "r",
        "from": sample["at"],
        "source": "AWC",
    }
    weather.route_observations.return_value = [
        {"items": [report, report, {**report, "id": "missing-altitude", "baseFt": None}]}
    ]
    assert detail(store, row, int(before.timestamp()), lambda: weather)["recap"] is None
    end = datetime.fromisoformat(row["arrival"]) + timedelta(minutes=1)
    result = detail(store, row, int(end.timestamp()), lambda: weather)["recap"]
    assert len(result["reports"]) == 1 and result["reports"][0]["forecast"] == sample["category"]
    weather.route_observations.return_value = []
    assert (
        detail(store, row, int(end.timestamp()), lambda: weather)["recap"]["status"]
        == "no-captures"
    )
    with pytest.raises(RequestError):
        api.dispatch(http("/api/me/flights/1/detail"), store, now=end + timedelta(days=7))


def test_quiet_delivery_stays_inapp_and_keeps_read_flag(store, monkeypatch):
    flight = save(store)
    row = store.get(OWNER, "flight#1")
    notice = store.notice(row, "reminder-3h", flight["revision"], T)
    store.preferences(
        OWNER,
        {
            "quietHours": {"start": "11:00", "end": "15:00", "zone": "Europe/Madrid"},
            "email": "example@example.edu",
        },
        None,
    )
    monkeypatch.setattr(
        worker.runtime, "client", lambda _: pytest.fail("Quiet hours must not contact a provider")
    )
    store.set_read(OWNER, notice["noticeId"], True, T)
    worker.deliver(store, OWNER, notice["sk"], T, 1)
    saved = store.get(OWNER, notice["sk"])
    assert saved["delivery"] == "inbox" and saved["isRead"] is True


def test_overview_filter_uses_only_non_key_attributes(store):
    # The hosted Query API rejects key columns in FilterExpression. Moto accepts them.
    def verify(params, **kwargs):
        expr = params["FilterExpression"]
        assert expr == "attribute_not_exists(#payload)"
        assert params["ExpressionAttributeNames"]["#payload"] == "payload"
        assert params["KeyConditionExpression"] == "pk = :p"

    store.db.meta.events.register("before-parameter-build.dynamodb.Query", verify)
    assert list(store.rows(OWNER, T)) == []
