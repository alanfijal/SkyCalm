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
