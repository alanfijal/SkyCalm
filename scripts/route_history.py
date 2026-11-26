"""Build the fixed passenger-route archive used by the history page and Athena."""

import argparse
import json
from pathlib import Path

from services.forecast.api import respond
from services.forecast.storage import REPLAY_ROOT, LocalStore
from services.observations.archive import replay
from services.observations.matching import match_reports
from services.pipeline.contract import demonstration_route

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web/public/data/route-history/days.jsonl"
ROUTES = (("EDI", "OPO"), ("AMS", "LHR"), ("BCN", "ARN"))


def archive():
    # Read the original dated forecasts, independent of a present-day model approval.
    store = LocalStore(REPLAY_ROOT, REPLAY_ROOT)
    for run in sorted(store.replays()):
        observations = replay(run)
        if observations is None:
            continue
        for origin, destination in ROUTES:
            query = demonstration_route(run) | {"origin": origin, "destination": destination}
            route = respond("/api/forecast", query, store)
            reports = match_reports(route["samples"], observations["items"])
            yield {
                "origin": origin,
                "destination": destination,
                "run_id": run,
                "departure": route["departure"],
                "peak": route["peak"],
                "snapshot_at": observations["asOf"],
                "report_count": len(reports),
                "reports": reports,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check the committed archive for drift"
    )
    args = parser.parse_args()
    content = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in archive())
    if args.check:
        if OUTPUT.read_text() != content:
            raise SystemExit("Regenerate route history with python -m scripts.route_history")
        return
    OUTPUT.parent.mkdir(exist_ok=True, parents=True)
    OUTPUT.write_text(content)


if __name__ == "__main__":
    main()
