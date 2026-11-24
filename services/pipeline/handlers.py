"""Durable workflow and independent SQS consumers for one forecast job."""

import json
import logging
import os

from botocore.exceptions import ClientError

from services.pipeline import runtime
from services.pipeline.artifacts import StagedGrid
from services.pipeline.contract import AVAILABLE, PROBE, READY, SOURCE, parse_job
from services.pipeline.jobs import claim, mark, release, route_summary

log = logging.getLogger(__name__)


def process_batch(event, handle):
    failed = []
    for record in event["Records"]:
        try:
            envelope = json.loads(record["body"])
            if envelope.get("source") != SOURCE:
                raise ValueError("Unexpected event source")
            handle(envelope["detail-type"], envelope["detail"])
        except Exception as exc:
            log.warning(
                json.dumps(
                    {
                        "event": "pipeline.delivery.failed",
                        "messageId": record["messageId"],
                        "error": type(exc).__name__,
                    }
                )
            )
            failed.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failed}


def start(kind, detail):
    if kind != AVAILABLE:
        raise ValueError("Unexpected admission event")
    job = parse_job(detail)
    sfn = runtime.client("stepfunctions")
    machine = os.environ["STATE_MACHINE"]
    content = json.dumps({"job": job}, sort_keys=True, separators=(",", ":"))
    try:
        sfn.start_execution(stateMachineArn=machine, name=job["jobId"], input=content)
    except sfn.exceptions.ExecutionAlreadyExists:
        # A closed execution also rejects a reused name. A different payload is a collision.
        arn = machine.replace(":stateMachine:", ":execution:") + ":" + job["jobId"]
        if sfn.describe_execution(executionArn=arn)["input"] != content:
            raise ValueError("Execution name belongs to another request") from None
    log.info(json.dumps({"event": "pipeline.accepted", **job}))


def admission(event, context):
    return process_batch(event, start)


def workflow(event, context):
    job = parse_job(event["job"])
    action = event["action"]
    db = runtime.table()
    if action == "claim":
        return {
            "acquired": claim(db, job),
            "command": ["--aws", "--run", job["runId"], "--job", job["jobId"]],
        }
    if action == "verify":
        base = runtime.weather()
        manifest = StagedGrid(base, job).published_manifest(job["runId"])
        if not manifest:
            raise ValueError("Worker exited without a complete manifest")
        mark(db, job, "gridReadyAt", leads=len(manifest["leads"]))
    elif action == "sent":
        if job["mode"] == "live":
            runtime.weather().advance(job["runId"])
        mark(db, job, "dispatchedAt")
        release(db, job)
    elif action == "failed":
        mark(db, job, "failedAt", reason=str(event.get("reason", "GridFailed"))[:120])
        release(db, job)
    else:
        raise ValueError("Unexpected workflow action")
    log.info(json.dumps({"event": "pipeline." + action, **job}))
    return {}


def rescore(kind, detail):
    if kind == PROBE:
        raise ValueError("Intentional classroom delivery test")
    if kind != READY:
        raise ValueError("Unexpected forecast event")
    job = parse_job(detail)
    output = route_summary(StagedGrid(runtime.weather(), job), job["runId"])
    mark(runtime.table(), job, "routeAt", route=output)
    log.info(json.dumps({"event": "pipeline.route.ready", **job}))


def receipt(kind, detail):
    if kind != READY:
        raise ValueError("Unexpected audit event")
    job = parse_job(detail)
    body = json.dumps({"type": READY, **job}, sort_keys=True, separators=(",", ":")).encode()
    try:
        runtime.client("s3").put_object(
            Bucket=os.environ["SKYCALM_BUCKET"],
            Key=f"pipeline/receipts/{job['jobId']}.json",
            Body=body,
            ContentType="application/json",
            IfNoneMatch="*",
        )
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
            raise
    mark(runtime.table(), job, "receiptAt")
    log.info(json.dumps({"event": "pipeline.receipt.saved", **job}))


def routes(event, context):
    return process_batch(event, rescore)


def audit(event, context):
    return process_batch(event, receipt)
