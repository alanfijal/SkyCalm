"""Admit only complete public NOAA cycles during a bounded collection window."""

import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from xml.etree import ElementTree

from grid.source import ORIGIN, GfsSource
from services.forecast.schema import LEADS
from services.pipeline import runtime
from services.pipeline.contract import AVAILABLE, job_spec, send_event


def complete_run(source, when: datetime) -> bool:
    prefix = f"gfs.{when:%Y%m%d}/{when:%H}/atmos/gfs.t{when:%H}z.pgrb2.0p25.f"
    query = urlencode({"list-type": "2", "prefix": prefix, "max-keys": 80})
    raw, _ = source.get(ORIGIN + "/?" + query, limit=80_000)
    root = ElementTree.fromstring(raw)
    keys = {
        item.findtext("{*}Key")
        for item in root.findall("{*}Contents")
        if int(item.findtext("{*}Size", "0")) > 0
    }
    return all(prefix + f"{lead:03}" + ext in keys for lead in LEADS for ext in ("", ".idx"))


def candidate(source, current: str | None, now: datetime) -> str | None:
    cycle = now.astimezone(UTC).replace(
        hour=now.astimezone(UTC).hour // 6 * 6, minute=0, second=0, microsecond=0
    )
    for offset in range(3):
        when = cycle - timedelta(hours=6 * offset)
        run = when.strftime("gfs-%Y%m%d-%H")
        if current and run <= current:
            break
        if complete_run(source, when):
            return run
    return None


def handler(event, context):
    source = GfsSource()
    try:
        run = candidate(source, runtime.weather().latest(), datetime.now(UTC))
    finally:
        source.http.clear()
    if not run:
        return {"found": False}
    job = job_spec(run, "live-" + run, "live")
    send_event(runtime.client("events"), os.environ["PIPELINE_BUS"], AVAILABLE, job)
    return {"found": True, **job}
