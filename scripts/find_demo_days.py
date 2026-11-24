"""Rank European demo routes using only weather evidence in the pinned snapshots."""

import argparse
import json
import math
from datetime import timedelta

from services.forecast.api import airports
from services.forecast.route import EARTH_KM, route_points
from services.forecast.schema import issue_time, utc_text
from services.observations.archive import ARCHIVE, replay
from services.observations.awc import INTENSITIES, instant


def inside_ring(x, y, ring):
    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:], strict=False):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def matches(item, point, at):
    start = instant(item["from"])
    if item["kind"] == "report":
        if abs((at - start).total_seconds()) > 45 * 60 or (
            item["baseFt"] is not None and abs(point["altitudeFt"] - item["baseFt"]) > 3000
        ):
            return False
        lon, lat = item["geometry"]["coordinates"]
        radians = math.radians
        a = (
            math.sin(radians(lat - point["lat"]) / 2) ** 2
            + math.cos(radians(lat))
            * math.cos(radians(point["lat"]))
            * math.sin(radians(lon - point["lon"]) / 2) ** 2
        )
        return 2 * EARTH_KM * math.asin(math.sqrt(min(1, a))) <= 75
    if (
        not start <= at < instant(item["to"])
        or item["baseFt"] is not None
        and point["altitudeFt"] < item["baseFt"]
        or item["topFt"] is not None
        and point["altitudeFt"] > item["topFt"]
    ):
        return False
    geom = item["geometry"]
    polygons = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return any(
        inside_ring(point["lon"], point["lat"], p[0])
        and not any(inside_ring(point["lon"], point["lat"], hole) for hole in p[1:])
        for p in polygons
    )


def candidates(run_id, pairs):
    snapshot = replay(run_id)
    ref = instant(snapshot["asOf"])
    # Six hours allows for the native model to publish its complete 36h cycle.
    # The selected classroom dates have separately verified index availability.
    first = max(issue_time(run_id) + timedelta(hours=6), ref.replace(minute=0) - timedelta(hours=6))
    last = ref.replace(minute=0)
    results = []
    for a, b in pairs:
        depart = first
        best = None
        while depart <= last:
            _, route = route_points(airports()[a], airports()[b], depart)
            points = [(p, instant(p["at"])) for p in route]
            seen = [
                item for item in snapshot["items"] if any(matches(item, p, t) for p, t in points)
            ]
            if seen:
                ranking = (
                    len({x["kind"] for x in seen}),
                    max(
                        (
                            INTENSITIES.index(x["intensity"])
                            for x in seen
                            if x["intensity"] in INTENSITIES
                        ),
                        default=-1,
                    ),
                    len(seen),
                )
                if best is None or ranking > best[0]:
                    best = (
                        ranking,
                        {
                            "run": run_id,
                            "route": a + "–" + b,
                            "departure": utc_text(depart),
                            "snapshot": snapshot["asOf"],
                            "matches": [
                                {
                                    "id": x["id"],
                                    "source": x["source"],
                                    "kind": x["kind"],
                                    "intensity": x["intensity"],
                                }
                                for x in seen
                            ],
                        },
                    )
            depart += timedelta(minutes=15)
        if best:
            results.append((best[0], best[1]))
    return [row for _, row in sorted(results, key=lambda pair: pair[0], reverse=True)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", nargs="+", default=["BCN-NCE", "EDI-OPO", "DUB-MAD"])
    args = parser.parse_args()
    pairs = [s.upper().split("-") for s in args.routes]
    if len(pairs) > 12 or any(
        len(p) != 2 or any(c not in airports() for c in p) or p[0] == p[1] for p in pairs
    ):
        parser.error("Choose up to 12 different-airport pairs, such as BCN-NCE.")
    print(
        json.dumps(
            {
                path.stem: candidates(path.stem, pairs)
                for path in sorted(ARCHIVE.glob("gfs-*.json"))
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
