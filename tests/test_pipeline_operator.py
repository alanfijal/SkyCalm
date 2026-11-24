import http.client
import json
import os
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from services.pipeline.contract import REPLAYS
from services.pipeline.operator import handler_for
from services.pipeline.operator_backend import AwsError, CloudOperator, LocalOperator


@pytest.fixture
def panel(tmp_path):
    app = LocalOperator()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), handler_for(app, "local-secret", tmp_path / "actions.jsonl")
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    try:

        def call(method, path, data=None, **overrides):
            headers = {
                "Host": f"127.0.0.1:{port}",
                "Origin": f"http://127.0.0.1:{port}",
                "X-SkyCalm-Token": "local-secret",
                "Content-Type": "application/json",
                **overrides,
            }
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                conn.request(
                    method, path, body=None if data is None else json.dumps(data), headers=headers
                )
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()

        yield call
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        app.close()


def test_panel_rejects_cross_origin_host_and_missing_token(panel):
    payload = {"run": REPLAYS[0], "requestId": "3" * 32}
    assert panel("GET", "/demo", Host="other.example")[0] == 403
    assert panel("POST", "/api/publish", payload, Origin="https://other.example")[0] == 403
    assert panel("POST", "/api/publish", payload, **{"X-SkyCalm-Token": ""})[0] == 403
    assert panel("GET", "/api/health", **{"X-SkyCalm-Token": ""})[0] == 403
    assert panel("POST", "/api/probe", payload)[0] == 400
    assert panel("POST", "/api/publish", {**payload, "run": "unexpected"})[0] == 400


def test_panel_publishes_real_replay_and_updates_route(panel, tmp_path):
    payload = {"run": REPLAYS[0], "requestId": "1" * 32}
    assert panel("GET", "/demo")[0] == 200
    assert json.loads(panel("GET", "/api/session")[1])["cloud"] is False
    status, body = panel("POST", "/api/publish", payload)
    assert status == 202
    job = json.loads(body)["jobId"]
    assert json.loads(panel("POST", "/api/publish", payload)[1])["jobId"] == job
    for _ in range(100):
        result = json.loads(panel("GET", "/api/jobs/" + job)[1])
        if result["phase"] == "ready":
            break
        time.sleep(0.05)
    assert result["phase"] == "ready"
    assert (
        result["leads"] == 13
        and result["route"]["destination"] == "OPO"
        and len(result["route"]["categories"]) == 69
    )
    assert "local-secret" not in (tmp_path / "actions.jsonl").read_text()
    assert json.loads(panel("GET", "/api/health")[1])["active"] is None


def test_cloud_panel_checks_account_before_any_actions(monkeypatch):
    monkeypatch.setattr(
        CloudOperator, "aws", lambda self, *args: {"Account": "111111111111", "Arn": "test"}
    )
    with pytest.raises(ValueError, match="identity"):
        CloudOperator("222222222222", "demo")


def test_cloud_panel_reads_an_absent_lease_from_the_cli(monkeypatch):
    def run(command, **kwargs):
        output = '{"Account":"111111111111","Arn":"presenter"}' if command[1] == "sts" else ""
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    operator = CloudOperator("111111111111", "demo")
    assert operator.item("skycalm-dev-pipeline", "active") == {}
    with pytest.raises(AwsError, match="unreadable"):
        operator.aws("cloudwatch", "describe-alarms")


@pytest.mark.parametrize("failure_count", [0, 1])
def test_command_line_refresh_uses_pipeline_admission(tmp_path, monkeypatch, failure_count):
    # The executable records the exact API request and returns an EventBridge response.
    fake = tmp_path / "aws"
    fake.write_text(
        "#!/bin/sh\n"
        'if [ "$1 $2" = "sts get-caller-identity" ]; then echo "$TF_VAR_account_id"; exit; fi\n'
        '[ "$1 $2 $3" = "events put-events --entries" ] || exit 9\n'
        'printf "%s" "$4" > "$TEST_ENTRIES"\n'
        'printf "%s" "$TEST_RESULT"\n'
    )
    fake.chmod(0o700)
    entries = tmp_path / "entries.json"
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("TF_VAR_account_id", "111111111111")
    monkeypatch.setenv("TEST_ENTRIES", str(entries))
    entry = {"ErrorCode": "ThrottlingException"} if failure_count else {"EventId": "accepted"}
    monkeypatch.setenv(
        "TEST_RESULT", json.dumps({"FailedEntryCount": failure_count, "Entries": [entry]})
    )
    script = Path(__file__).resolve().parents[1] / "scripts/run_grid.sh"
    result = subprocess.run(["bash", str(script), REPLAYS[0]], capture_output=True, text=True)
    assert result.returncode == failure_count
    [event] = json.loads(entries.read_bytes())
    assert event["EventBusName"] == "skycalm-dev-pipeline"
    assert event["DetailType"] == "forecast.run.available"
    assert json.loads(event["Detail"]) == {
        "mode": "live",
        "runId": REPLAYS[0],
        "jobId": "live-" + REPLAYS[0],
    }
    assert ("arn:aws:states:" in result.stdout) is (failure_count == 0)
