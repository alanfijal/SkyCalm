from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from services.passengers import admission, api, worker
from services.passengers.store import decode, encode
from tests.test_passengers import NOW, OTHER, OWNER, T, http, save
from tests.test_passengers import store as store


def test_classroom_signup_leaves_verification_to_provider(monkeypatch):
    monkeypatch.setenv("CLASSROOM_EMAIL", "team@example.edu")
    good = {"request": {"userAttributes": {"email": "Team@example.edu"}}, "response": {}}
    assert admission.handler(good, None)["response"] == {}
    with pytest.raises(ValueError):
        admission.handler({"request": {"userAttributes": {"email": "else@example.edu"}}}, None)


@pytest.mark.parametrize(
    ("email", "verified", "permitted"),
    [
        ("Presenter@example.com", "true", True),
        ("presenter@example.com", "false", False),
        ("team@example.edu", "true", False),
        ("other@example.com", "true", False),
    ],
)
def test_invite_maps_only_its_verified_identity_to_the_classroom_mailbox(
    store, monkeypatch, email, verified, permitted
):
    monkeypatch.setenv("CLASSROOM_EMAIL", "presenter@example.com")
    monkeypatch.setenv("SES_RECIPIENT", "team@example.edu")
    cognito = Mock()
    cognito.get_user.return_value = {
        "UserAttributes": [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": verified},
        ]
    }
    req = http(
        "/api/me/preferences",
        "PUT",
        {"channel": "email", "enabled": True, "email": "else@example.net"},
        scope=api.PREF,
    )
    if permitted:
        api.dispatch(req, store, lambda name: cognito, NOW)
        assert store.get(OWNER, "account")["prefs"]["email"] == "team@example.edu"
    else:
        with pytest.raises(api.RequestError, match="invited sign-in"):
            api.dispatch(req, store, lambda name: cognito, NOW)
        assert "prefs" not in store.get(OWNER, "account")


def test_demo_seed_respects_personal_routes_and_replayed_events(store, monkeypatch):
    monkeypatch.setenv("PIPELINE_BUS", "demo")
    req = {"action": "seed", "requestId": str(uuid4())}

    def run():
        return api.dispatch(
            http("/api/admin/actions", "POST", req, scope=api.ADMIN, groups="[admins]"),
            store,
            now=NOW,
        )

    run()
    first = api.view(store, OWNER, T)["flights"]
    run()
    assert len(first) == 3 and first == api.view(store, OWNER, T)["flights"]
    f = first[0]
    data = {"owner": OWNER, "slot": 1, "revision": f["revision"], "requestId": str(uuid4())}
    worker.process(store, worker.CHANGE, data, T, 1)
    worker.process(store, worker.CHANGE, data, T, 2)
    assert [n["kind"] for n in api.view(store, OWNER, T)["inbox"]] == ["test-change"]
    save(store, OTHER)
    with pytest.raises(Exception, match="personal flights"):
        api.dispatch(
            http(
                "/api/admin/actions", "POST", req, owner=OTHER, scope=api.ADMIN, groups="[admins]"
            ),
            store,
            now=NOW,
        )


def test_real_archived_grid_reaches_only_classroom_inboxes(store, tmp_path):
    from services.forecast.storage import REPLAY_ROOT, LocalStore
    from services.pipeline.contract import READY, job_spec

    req = {"action": "seed", "requestId": str(uuid4())}
    api.dispatch(
        http("/api/admin/actions", "POST", req, scope=api.ADMIN, groups="[admins]"), store, now=NOW
    )
    save(store, OTHER)
    job = job_spec("gfs-20261124-12", "replay-" + uuid4().hex, "replay")
    tasks = []
    with patch.object(
        worker, "enqueue", side_effect=lambda kind, detail: tasks.append((kind, detail))
    ):
        worker.process(store, READY, job, T, 1)
    assert len(tasks) == 3 and all(t[1]["owner"] == OWNER for t in tasks)
    with (
        patch.object(worker.runtime, "weather"),
        patch.object(worker, "StagedGrid", return_value=LocalStore(tmp_path, REPLAY_ROOT)),
    ):
        for kind, data in tasks:
            worker.process(store, kind, data, T, 1)
            worker.process(store, kind, data, T, 2)
    alerts = api.view(store, OWNER, T)["inbox"]
    assert any(n["slot"] == 1 and n["kind"] == "test-change" for n in alerts)
    assert not api.view(store, OTHER, T)["inbox"]
    api.dispatch(
        http("/api/admin/actions", "POST", req, scope=api.ADMIN, groups="[admins]"), store, now=NOW
    )
    assert len(api.view(store, OWNER, T)["inbox"]) == len(alerts)
    req["requestId"] = str(uuid4())
    api.dispatch(
        http("/api/admin/actions", "POST", req, scope=api.ADMIN, groups="[admins]"), store, now=NOW
    )
    assert not api.view(store, OWNER, T)["inbox"]


def test_push_falls_back_to_opted_in_email_and_duplicate_is_skipped(store, monkeypatch):
    import io

    monkeypatch.setenv("PUSH_FUNCTION", "push")
    monkeypatch.setenv("SES_FROM", "team@example.edu")
    store.preferences(OWNER, {"device": {"endpoint": "mock"}, "email": "team@example.edu"}, None)
    notice = store.notice({"pk": OWNER, "sk": "account"}, "test-push", "case", T)
    sender = Mock()
    sender.invoke.return_value = {"Payload": io.BytesIO(b'{"result":"gone"}')}
    with patch.object(worker.runtime, "client", return_value=sender):
        worker.deliver(store, OWNER, notice["sk"], T, 1)
        worker.deliver(store, OWNER, notice["sk"], T + 1, 2)
    sender.send_email.assert_called_once()
    msg = sender.send_email.call_args.kwargs
    assert msg["Destination"] == {"ToAddresses": ["team@example.edu"]} and "EDI" not in str(
        msg["Content"]
    )
    assert "device" not in store.get(OWNER, "account")["prefs"]
    assert store.get(OWNER, notice["sk"])["delivery"] == "email"


def test_stream_publishes_after_transaction_and_retries_failed_entry(store, monkeypatch):
    monkeypatch.setenv("PIPELINE_BUS", "demo")
    monkeypatch.setenv("PASSENGERS", store.name)
    raw = encode({"pk": OWNER, "sk": "notice#case"})
    assert decode(raw)["pk"] == OWNER
    event = {"Records": [{"dynamodb": {"Keys": raw, "NewImage": raw, "SequenceNumber": "71"}}]}
    emitter = Mock()
    emitter.put_events.return_value = {
        "FailedEntryCount": 1,
        "Entries": [{"ErrorCode": "InternalFailure"}],
    }
    with patch.object(
        worker.runtime, "client", side_effect=lambda svc: store.db if svc == "dynamodb" else emitter
    ):
        assert worker.stream(event, None) == {"batchItemFailures": [{"itemIdentifier": "71"}]}
        emitter.put_events.return_value = {"FailedEntryCount": 0, "Entries": [{"EventId": "ok"}]}
        assert worker.stream(event, None) == {"batchItemFailures": []}
