"""Build one complete, versioned run and publish it only after all leads succeed."""

import argparse
import hashlib
import json
import os
import signal
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from grid.compute import cruise_wind, decode, encode
from grid.source import GfsSource, NotReady, SourceError
from services.forecast.schema import LEADS, SCORER, issue_time, tile_name, utc_text
from services.forecast.storage import LocalStore


def build_lead(run_id: str, lead: int, directory: Path) -> dict:
    source = GfsSource()
    try:
        fields = {
            (r.field, r.level): decode(data, r, run_id, lead)
            for r, data in source.fields(run_id, lead)
        }
        tile = encode(fields)
        (directory / tile_name(lead)).write_bytes(tile)
        return {
            "lead": lead,
            "sha256": hashlib.sha256(tile).hexdigest(),
            "wind250": cruise_wind(fields),
            **source.last_source,
        }
    finally:
        source.http.clear()


def build(run_id: str, store, model=None) -> dict:
    issued = issue_time(run_id)
    existing = store.published_manifest(run_id)
    if existing:
        store.advance(run_id)
        return existing
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        with ThreadPoolExecutor(max_workers=3) as pool:
            leads = list(pool.map(lambda h: build_lead(run_id, h, directory), LEADS))
        manifest = {
            "runId": run_id,
            "scorer": SCORER,
            "issued": utc_text(issued),
            "validUntil": utc_text(issued + timedelta(hours=36)),
            "leads": leads,
            "source": "NOAA GFS 0.25°",
            "tileStep": 1,
        }
        if model is not None:
            from grid.model import add_predictions

            add_predictions(directory, manifest, model)
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        store.publish(directory, manifest)
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="latest", help="latest or gfs-YYYYMMDD-HH")
    parser.add_argument("--directory", type=Path, default=Path(".local/weather"))
    parser.add_argument("--aws", action="store_true", help="Publish to configured AWS resources")
    parser.add_argument("--job", help="Validated live or replay execution ID")
    args = parser.parse_args()
    # The essential Fargate container exits at the deadline, including during retries.
    signal.alarm(600)
    store = LocalStore(args.directory)
    model = None
    if args.aws:
        from services.forecast.aws import AwsStore

        store = AwsStore.from_env()
        if group := os.getenv("SKYCALM_MODEL_GROUP"):
            import boto3
            from botocore.config import Config

            from grid.model import load_approved

            client = boto3.client(
                "sagemaker",
                region_name="eu-north-1",
                config=Config(connect_timeout=3, read_timeout=8, retries={"total_max_attempts": 2}),
            )
            model = load_approved(client, store, group)
            print(
                json.dumps(
                    {"event": "grid.model", "version": model[1]["version"] if model else "baseline"}
                )
            )
    source = GfsSource()
    started = time.monotonic()
    try:
        run_id = source.latest() if args.run == "latest" else args.run
        if args.job:
            from grid.replay import rebuild
            from services.pipeline.artifacts import StagedGrid
            from services.pipeline.contract import job_spec

            if not args.aws:
                parser.error("--job requires --aws")
            mode = "replay" if args.job.startswith("replay-") else "live"
            store = StagedGrid(store, job_spec(run_id, args.job, mode))
            result = (
                rebuild(run_id, store, model) if mode == "replay" else build(run_id, store, model)
            )
        else:
            result = build(run_id, store, model)
    except (ValueError, NotReady, SourceError, OSError) as exc:
        parser.exit(1, f"Grid build failed: {exc}\n")
    finally:
        source.http.clear()
    print(
        json.dumps(
            {
                "event": "grid.ready",
                "runId": run_id,
                "leads": len(result["leads"]),
                "seconds": round(time.monotonic() - started, 1),
                "sourceBytes": sum(item["bytes"] for item in result["leads"]),
            }
        )
    )


if __name__ == "__main__":
    main()
