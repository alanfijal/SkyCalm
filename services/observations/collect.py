"""Capture one eight-hour weather observation window. No recurring local producer."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from services.forecast.schema import issue_time
from services.observations.archive import ARCHIVE, atomic, encoded, public_map, publish_local
from services.observations.awc import collect, instant


def capture_time(value: str | None):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    when = instant(value) if value else now
    if when is None or when > now or when < now - timedelta(days=30):
        raise ValueError("Choose a UTC instant within the past 30 days of AWC coverage.")
    return when.replace(second=0, microsecond=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at", help="UTC timestamp for a retrospective query")
    parser.add_argument("--pin-run", help="Archive the public weather fields for this replay run")
    parser.add_argument("--directory", type=Path, default=Path(".local/weather"))
    args = parser.parse_args()
    try:
        at = capture_time(args.at)
        if args.pin_run and (
            not args.at
            or not issue_time(args.pin_run) <= at <= issue_time(args.pin_run) + timedelta(hours=36)
        ):
            raise ValueError("A pinned snapshot needs an explicit time within the forecast run.")
        snapshot, raw = collect(at)
        version = publish_local(args.directory, snapshot, raw, live=args.at is None)
        if args.pin_run:
            dest = ARCHIVE / (args.pin_run + ".json")
            day = "day=" + snapshot["asOf"][:10]
            history = args.directory / "observations/history" / day / (version + ".json.gz")
            pinned_history = (
                ARCHIVE.parent / "observation-history" / day / (args.pin_run + ".json.gz")
            )
            public = encoded(public_map(snapshot)) + b"\n"
            if dest.exists() and dest.read_bytes() != public:
                raise ValueError("This replay already has a different pinned snapshot.")
            atomic(dest, public)
            atomic(pinned_history, history.read_bytes())
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Weather capture failed: {exc}\n")
    print(
        json.dumps(
            {
                "event": "observations.ready",
                "version": version,
                "weatherRecords": len(snapshot["items"]),
            }
        )
    )


if __name__ == "__main__":
    main()
