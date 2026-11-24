"""Local rehearsal and temporary-IAM adapters for the private operator panel."""

import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from boto3.dynamodb.types import TypeDeserializer

from services.forecast.schema import SCORER
from services.forecast.storage import LocalStore
from services.pipeline.contract import AVAILABLE, PROBE, SOURCE, job_spec
from services.pipeline.jobs import phase, route_summary, stamp

REGION = "eu-north-1"
PREFIX = "skycalm-dev-pipeline"
QUEUES = (
    "admission",
    "routes",
    "audit",
    "admission-dlq",
    "routes-dlq",
    "audit-dlq",
    "delivery-dlq",
)
ALARMS = tuple(
    PREFIX + "-" + suffix
    for suffix in (
        "admission-dlq",
        "routes-dlq",
        "audit-dlq",
        "delivery-dlq",
        "admission-age",
        "routes-age",
        "ExecutionsFailed",
        "ExecutionsTimedOut",
    )
)


def valid_id(job_id: str) -> bool:
    return bool(
        isinstance(job_id, str)
        and re.fullmatch(r"replay-[0-9a-f]{32}|live-gfs-[0-9]{8}-(00|06|12|18)", job_id)
    )


class LocalOperator:
    mode = "Local rehearsal"
    principal = "local operator"

    def __init__(self):
        self.jobs = {}
        self.active = None
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=1)

    def publish(self, run, request_id):
        job = job_spec(run, "replay-" + request_id, "replay")
        key = job["jobId"]
        with self.lock:
            old = self.jobs.get(key)
            if old:
                if old["runId"] != run:
                    raise ValueError("This request belongs to another run")
                return job
            if self.active:
                raise ValueError("A grid is already running")
            if len(self.jobs) >= 32:
                self.jobs.pop(next(iter(self.jobs)))
            self.active = key
            self.jobs[key] = {**job, "phase": "queued", "acceptedAt": stamp()}
        self.pool.submit(self._build, job)
        return job

    def _build(self, job):
        from grid.replay import rebuild

        key = job["jobId"]

        def update(**data):
            with self.lock:
                self.jobs[key].update(data)

        try:
            update(phase="building", buildingAt=stamp())
            with TemporaryDirectory() as tmp:
                grid = LocalStore(Path(tmp))
                manifest = rebuild(job["runId"], grid)
                update(phase="delivering", gridReadyAt=stamp(), leads=len(manifest["leads"]))
                route = route_summary(grid, job["runId"])
                update(phase="ready", route=route, routeAt=stamp())
        except Exception as exc:
            update(phase="failed", reason=type(exc).__name__)
        finally:
            with self.lock:
                self.active = None

    def status(self, job_id):
        with self.lock:
            return self.jobs.get(job_id, {"phase": "unknown"}).copy()

    def health(self):
        with self.lock:
            return {"mode": self.mode, "active": self.active, "queues": {}, "alarms": {}}

    def close(self):
        self.pool.shutdown()


class AwsError(RuntimeError):
    pass


class CloudOperator:
    mode = "AWS Stockholm"

    def __init__(self, account, profile):
        if not re.fullmatch(r"[0-9]{12}", account or ""):
            raise ValueError("Supply the approved 12-digit account ID")
        self.account = account
        self.profile = profile
        who = self.aws("sts", "get-caller-identity")
        if who["Account"] != account:
            raise ValueError("AWS identity differs from the approved account")
        self.principal = who["Arn"]

    def aws(self, *args, timeout=35):
        command = [
            "aws",
            *args,
            "--profile",
            self.profile,
            "--region",
            REGION,
            "--no-cli-pager",
            "--output",
            "json",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "AWS_MAX_ATTEMPTS": "2", "AWS_RETRY_MODE": "standard"},
        )
        if result.returncode:
            code = re.search(r"\(([A-Za-z0-9.]+)\) when calling", result.stderr)
            raise AwsError(code.group(1) if code else "AWS CLI session or request unavailable")
        return json.loads(result.stdout)

    def event(self, kind, detail):
        entries = [
            {
                "EventBusName": PREFIX,
                "Source": SOURCE,
                "DetailType": kind,
                "Detail": json.dumps(detail),
            }
        ]
        result = self.aws("events", "put-events", "--entries", json.dumps(entries))
        if result["FailedEntryCount"] or not result["Entries"][0].get("EventId"):
            raise AwsError("EventBridge rejected the event")
        return result["Entries"][0]["EventId"]

    def publish(self, run, request_id):
        job = job_spec(run, "replay-" + request_id, "replay")
        self.event(AVAILABLE, job)
        return job

    def probe(self, request_id):
        return {"eventId": self.event(PROBE, {"testId": request_id}), "testId": request_id}

    def discover(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            result = self.aws(
                "lambda",
                "invoke",
                "--function-name",
                PREFIX + "-discover",
                "--cli-binary-format",
                "raw-in-base64-out",
                "--payload",
                "{}",
                "--cli-read-timeout",
                "100",
                str(path),
                timeout=110,
            )
            if result.get("FunctionError"):
                raise AwsError("The weather availability check failed")
            return json.loads(path.read_bytes())

    def item(self, table, key):
        response = self.aws(
            "dynamodb",
            "get-item",
            "--table-name",
            table,
            "--key",
            json.dumps({"pk": {"S": key}}),
            "--consistent-read",
        )
        decoder = TypeDeserializer()
        return {k: decoder.deserialize(v) for k, v in response.get("Item", {}).items()}

    def status(self, job_id):
        item = self.item(PREFIX, "job#" + job_id)
        stage = phase(item)
        execution = f"arn:aws:states:{REGION}:{self.account}:execution:{PREFIX}:{job_id}"
        if stage not in ("ready", "failed"):
            try:
                result = self.aws(
                    "stepfunctions", "describe-execution", "--execution-arn", execution
                )
                if result["status"] in ("FAILED", "ABORTED", "TIMED_OUT"):
                    stage = "failed"
                    item["reason"] = result.get("error", result["status"])
            except AwsError as exc:
                if str(exc) != "ExecutionDoesNotExist":
                    raise
        item.pop("expiresAt", None)
        item.pop("pk", None)
        return {**item, "phase": stage, "executionArn": execution}

    def health(self):
        def depth(name):
            url = f"https://sqs.{REGION}.amazonaws.com/{self.account}/{PREFIX}-{name}"
            response = self.aws(
                "sqs",
                "get-queue-attributes",
                "--queue-url",
                url,
                "--attribute-names",
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
            )
            attrs = response["Attributes"]
            return {
                "visible": int(attrs["ApproximateNumberOfMessages"]),
                "processing": int(attrs["ApproximateNumberOfMessagesNotVisible"]),
            }

        with ThreadPoolExecutor(max_workers=4) as pool:
            queues = dict(zip(QUEUES, pool.map(depth, QUEUES), strict=True))
        alarms = self.aws("cloudwatch", "describe-alarms", "--alarm-names", *ALARMS)["MetricAlarms"]
        active = self.item(PREFIX, "active")
        return {
            "mode": self.mode,
            "active": active.get("jobId") if active.get("expiresAt", 0) > time.time() else None,
            "latestRun": self.item("skycalm-dev-runs", "latest#" + SCORER).get("runId"),
            "observations": self.item("skycalm-dev-runs", "observations#awc").get("asOfTime"),
            "queues": queues,
            "alarms": {a["AlarmName"].removeprefix(PREFIX + "-"): a["StateValue"] for a in alarms},
        }

    def close(self):
        pass
