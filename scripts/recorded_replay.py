"""Rebuild the AZ1704 passenger replay from its open track and archived weather."""

import argparse
import csv
import gzip
import hashlib
import json
from bisect import bisect_left
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from scripts.route_history import distance_km
from services.forecast.api import airports, descriptor
from services.forecast.briefing import select, variants
from services.forecast.product import sample, unpack
from services.forecast.schema import CATEGORIES, issue_time
from services.forecast.storage import REPLAY_ROOT, LocalStore

DATA = Path(__file__).resolve().parents[1] / "web/public/data/recorded-flight"
TRACK = DATA / "az1704-20261121.csv"
FORECAST = DATA / "az1704-20261121.json"
RELEASE = (
    "https://github.com/adsblol/globe_history_2026/releases/tag/v2026.11.21-planes-readsb-prod-0"
)
MEMBER_SHA256 = "f612a10937d485e0502e5176bb1aede6ed875e9672899da399942d868ce7833f"
RUN = "gfs-20261121-06"
CALLSIGN = "ITY1704"


def extract_track(member: bytes, output: Path) -> None:
    if hashlib.sha256(member).hexdigest() != MEMBER_SHA256:
        raise ValueError("The aircraft-day archive member does not match the pinned checksum.")
    aircraft = json.loads(gzip.decompress(member))
    callsign = ""
    rows = []
    # readsb repeats identity intermittently. Only take observed airborne ADS-B
    # positions with fresh coordinates and a barometric altitude for this leg.
    for point in aircraft["trace"]:
        callsign = (point[8] or {}).get("flight", callsign).strip()
        if (
            callsign != CALLSIGN
            or point[9] != "adsb_icao"
            or point[6] & 9
            or not isinstance(point[3], (int, float))
        ):
            continue
        when = datetime.fromtimestamp(aircraft["timestamp"] + point[0], UTC)
        rows.append((when.isoformat(timespec="milliseconds").replace("+00:00", "Z"), *point[1:4]))
    if len(rows) != 750:
        raise ValueError("Unexpected number of recorded positions for ITY1704.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(("time_utc", "latitude", "longitude", "barometric_altitude_ft"))
        writer.writerows(rows)


def recorded_points(path: Path) -> list[dict]:
    points = []
    km = 0.0
    with path.open(newline="") as file:
        for row in csv.DictReader(file):
            at = datetime.fromisoformat(row["time_utc"])
            lat, lon = float(row["latitude"]), float(row["longitude"])
            if points:
                prev = points[-1]
                if not 0 < (at - prev["time"]).total_seconds() <= 30:
                    raise ValueError("Recorded times are out of order or have a coverage gap.")
                km += distance_km(prev["lat"], prev["lon"], lat, lon)
            points.append(
                dict(
                    time=at,
                    lat=lat,
                    lon=lon,
                    altitudeFt=int(row["barometric_altitude_ft"]),
                    distanceKm=km,
                )
            )
    if len(points) < 2:
        raise ValueError("The replay needs at least two recorded positions.")
    return points


def build_replay(path: Path) -> dict:
    points = recorded_points(path)
    origin, destination = airports()["CTA"], airports()["LIN"]
    for stop, point in ((origin, points[0]), (destination, points[-1])):
        if distance_km(stop["lat"], stop["lon"], point["lat"], point["lon"]) > 5:
            raise ValueError("Recorded endpoint is too far from the named airport.")
    start = points[0]["time"]
    seconds = [(p["time"] - start).total_seconds() for p in points]
    # Show the nearest actual observation to each elapsed minute, plus both ends.
    indices = {0, len(points) - 1}
    for minute in range(60, int(seconds[-1]), 60):
        i = bisect_left(seconds, minute)
        indices.add(min((i - 1, i), key=lambda j: abs(seconds[j] - minute)))
    cruise_floor = max(p["altitudeFt"] for p in points) - 1000
    cruise = [i for i, p in enumerate(points) if p["altitudeFt"] >= cruise_floor]
    store = LocalStore(REPLAY_ROOT, REPLAY_ROOT)
    manifest = store.manifest(RUN)
    issued = issue_time(RUN)
    cubes = {x["lead"]: unpack(store.tile(RUN, x["lead"], x["sha256"])) for x in manifest["leads"]}
    samples = []
    for i in sorted(indices):
        p = points[i]
        hours = (p["time"] - issued).total_seconds() / 3600
        phase = "climb" if i < cruise[0] else "descent" if i > cruise[-1] else "cruise"
        pt = {
            "at": p["time"].isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "lat": p["lat"],
            "lon": p["lon"],
            "altitudeFt": p["altitudeFt"],
            "elapsedMinutes": round(seconds[i] / 60, 4),
            "distanceKm": round(p["distanceKm"], 2),
            "phase": phase,
        }
        samples.append(pt | sample(cubes, hours, pt))
    categories = [p["category"] for p in samples if p["category"] in CATEGORIES]
    return {
        "flightNumber": "AZ1704",
        "callsign": CALLSIGN,
        "sourceUrl": RELEASE,
        "licenseUrl": "https://opendatacommons.org/licenses/odbl/1-0/",
        "positions": len(points),
        "maxGapSeconds": round(max(b - a for a, b in pairwise(seconds)), 2),
        "origin": origin,
        "destination": destination,
        "departure": samples[0]["at"],
        "run": descriptor(manifest),
        "mode": "replay",
        "modelVersion": None,
        "durationMinutes": round(seconds[-1] / 60),
        "distanceKm": round(points[-1]["distanceKm"]),
        "peak": max(categories, key=CATEGORIES.index) if categories else "unavailable",
        "briefing": select(variants(samples), [0, 0]),
        "samples": samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-member", type=Path, help="Extract the pinned gzip archive member")
    parser.add_argument(
        "--check", action="store_true", help="Verify the committed forecast offline"
    )
    args = parser.parse_args()
    if args.import_member:
        if args.check:
            parser.error("Use --import-member and --check in separate runs.")
        extract_track(args.import_member.read_bytes(), TRACK)
    data = json.dumps(build_replay(TRACK), ensure_ascii=False, separators=(",", ":")) + "\n"
    if args.check:
        if data != FORECAST.read_text():
            raise SystemExit("Recorded replay differs from its track and weather archive.")
    else:
        FORECAST.write_text(data)


if __name__ == "__main__":
    main()
