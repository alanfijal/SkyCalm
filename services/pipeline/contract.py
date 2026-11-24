"""Validate the event schema shared by producers and consumers."""

import json
import re
from datetime import timedelta

from services.forecast.schema import issue_time, utc_text

REPLAYS = ("gfs-20261121-06", "gfs-20261124-12")
SOURCE = "skycalm.forecast"
AVAILABLE = "forecast.run.available"
READY = "forecast.tiles.ready"
PROBE = "forecast.delivery.test"


def job_spec(run_id: str, job_id: str, mode: str) -> dict[str, str]:
    if not isinstance(run_id, str) or not isinstance(job_id, str):
        raise ValueError("Invalid forecast request")
    issue_time(run_id)
    if mode == "live" and job_id == f"live-{run_id}":
        return {"jobId": job_id, "runId": run_id, "mode": mode}
    if mode == "replay" and run_id in REPLAYS and re.fullmatch(r"replay-[0-9a-f]{32}", job_id):
        return {"jobId": job_id, "runId": run_id, "mode": mode}
    raise ValueError("Choose a supported forecast run")


def parse_job(detail: dict) -> dict[str, str]:
    return job_spec(detail.get("runId"), detail.get("jobId"), detail.get("mode"))


def send_event(client, bus: str, kind: str, detail: dict) -> str:
    result = client.put_events(
        Entries=[
            {
                "Source": SOURCE,
                "EventBusName": bus,
                "DetailType": kind,
                "Detail": json.dumps(detail, separators=(",", ":")),
            }
        ]
    )
    entry = result["Entries"][0]
    if result["FailedEntryCount"] or not entry.get("EventId"):
        raise RuntimeError(f"Event delivery failed: {entry.get('ErrorCode', 'unknown')}")
    return entry["EventId"]


def demonstration_route(run_id: str) -> dict[str, str]:
    departure = issue_time(run_id) + timedelta(hours=8, minutes=15)
    return {"origin": "EDI", "destination": "OPO", "departure": utc_text(departure), "run": run_id}
