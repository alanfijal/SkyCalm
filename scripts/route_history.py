"""Build the fixed passenger-route archive used by the history page and Athena."""

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

from services.forecast.api import respond
from services.forecast.schema import CATEGORIES
from services.forecast.storage import REPLAY_ROOT, LocalStore
from services.observations.archive import replay
from services.pipeline.contract import demonstration_route

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web/public/data/route-history/days.jsonl"
ROUTES = (("EDI", "OPO"), ("AMS", "LHR"), ("BCN", "ARN"))


def distance_km(lat, lon, other_lat, other_lon):
    lat, lon, other_lat, other_lon = map(math.radians, (lat, lon, other_lat, other_lon))
    a = math.sin((other_lat - lat) / 2) ** 2 + (
        math.cos(lat) * math.cos(other_lat) * math.sin((other_lon - lon) / 2) ** 2
    )
    return 12742 * math.asin(min(1, math.sqrt(a)))


def match_reports(samples, items):
    """Use each timed, altitude-qualified point report once, at its nearest eligible sample."""
    matches = {}
    for item in items:
        if (
            item["kind"] != "report"
            or item["geometry"]["type"] != "Point"
            or item["intensity"] not in CATEGORIES
            or item["baseFt"] is None
        ):
            continue
        lon, lat = item["geometry"]["coordinates"]
        observed = datetime.fromisoformat(item["from"])
        eligible = []
        for index, pt in enumerate(samples):
            minutes = abs((datetime.fromisoformat(pt["at"]) - observed).total_seconds()) / 60
            if minutes > 45 or abs(pt["altitudeFt"] - item["baseFt"]) > 3000:
                continue
            km = distance_km(lat, lon, pt["lat"], pt["lon"])
            if km <= 75:
                eligible.append((km, minutes, index))
        if eligible:
            km, _, index = min(eligible)
            pt = samples[index]
            matches[item["id"]] = {
                "source": item["source"],
                "observed": item["from"],
                "altitude_ft": item["baseFt"],
                "distance_km": round(km),
                "elapsed_minutes": round(pt["elapsedMinutes"]),
                "reported": item["intensity"],
                "forecast": pt["category"],
            }
    return sorted(
        matches.values(), key=lambda report: (report["observed"], report["elapsed_minutes"])
    )


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
