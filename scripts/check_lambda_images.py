"""Invoke the deployed runtime targets locally with a read-only image and no network egress."""

import json
import subprocess
import time
from contextlib import contextmanager

INVOKE = "http://127.0.0.1:8080/2015-03-31/functions/function/invocations"
PYTHON_HANDLERS = (
    "services.forecast.handler.handler",
    "services.observations.handler.handler",
    "services.passengers.admission.handler",
    "services.passengers.api.handler",
    "services.passengers.worker.stream",
    "services.passengers.worker.worker",
    "services.pipeline.handlers.admission",
    "services.pipeline.handlers.workflow",
    "services.pipeline.handlers.routes",
    "services.pipeline.handlers.audit",
    "services.pipeline.discovery.handler",
)


def docker(*args, **kwargs):
    return subprocess.run(
        ["docker", *args], text=True, check=True, stdout=subprocess.PIPE, **kwargs
    )


@contextmanager
def runtime(handler):
    cid = docker(
        "run",
        "-d",
        "--network=none",
        "--read-only",
        "--user=10001:10001",
        "--tmpfs",
        "/tmp:rw,mode=1777",
        "-e",
        "AWS_REGION=eu-north-1",
        "-e",
        "AWS_EC2_METADATA_DISABLED=true",
        "-e",
        "SKYCALM_BUCKET=example",
        "-e",
        "SKYCALM_TABLE=example",
        "skycalm-python:local",
        handler,
    ).stdout.strip()
    try:
        yield cid
    except Exception:
        subprocess.run(["docker", "logs", "--tail", "30", cid], check=False)
        raise
    finally:
        docker("rm", "-f", cid)


def invoke(cid, event):
    client = [
        "python",
        "-c",
        "import sys,urllib.request as u; print(u.urlopen(sys.argv[1], "
        "sys.argv[2].encode(), timeout=8).read().decode())",
    ]
    for attempt in range(12):
        try:
            result = docker("exec", cid, *client, INVOKE, json.dumps(event), timeout=15)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError:
            if attempt == 11:
                raise
            time.sleep(0.25)


def main():
    with runtime(PYTHON_HANDLERS[0]) as cid:
        docker(
            "exec",
            cid,
            "python",
            "-c",
            "from services.passengers.preview import card_png; "
            "assert card_png('CTA','LIN','21 Nov 2026','moderate').startswith(bytes.fromhex('89504e470d0a1a0a'))",
        )
        docker(
            "exec",
            cid,
            "python",
            "-c",
            "import importlib,sys\nfor key in sys.argv[1:]:\n"
            " module,name=key.rsplit('.',1)\n assert callable(getattr(importlib.import_module(module),name))",
            *PYTHON_HANDLERS,
        )
        event = {
            "requestContext": {"http": {"method": "GET"}},
            "rawPath": "/api/airports",
            "rawQueryString": "q=EDI",
        }
        response = invoke(cid, event)
        assert (
            response["statusCode"] == 200
            and json.loads(response["body"])["airports"][0]["code"] == "EDI"
        )
    print(f"Loaded {len(PYTHON_HANDLERS)} Python handlers and invoked the ARM64 runtime offline.")


if __name__ == "__main__":
    main()
