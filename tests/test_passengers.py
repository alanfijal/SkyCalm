import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws

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


def test_forecast_outbox_and_three_hour_limit(store):
    save(store)

    def get():
        return store.get(OWNER, "flight#1")

    base = {"peak": "smooth", "firstRough": None}
    rough = {"peak": "moderate", "firstRough": 20}
    store.record_forecast(get(), "gfs-1", base, T)
    store.record_forecast(get(), "gfs-2", rough, T + 1)
    store.record_forecast(get(), "gfs-3", base, T + 2)
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
    api.dispatch(
        http(
            "/api/me/flights/1", "PUT", {**inputs(), "previous": first["revision"]}, scope=api.WRITE
        ),
        store,
        now=NOW,
    )
    worker.process(store, "reminder", {**msg, "hours": 3}, T, 1)
    assert len(api.view(store, OWNER, T)["inbox"]) == 1


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
        api.dispatch(http("/api/me/export"), store, now=NOW)["verifiedEmailForDelivery"]
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
