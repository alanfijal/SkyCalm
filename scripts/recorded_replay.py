"""Rebuild the passenger recordings and their search index from ADS-B and archived weather."""

import argparse
import csv
import gzip
import hashlib
import json
from bisect import bisect_left
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from zoneinfo import ZoneInfo

from services.forecast.api import airports, descriptor
from services.forecast.briefing import select, variants
from services.forecast.product import sample, unpack
from services.forecast.schema import CATEGORIES, issue_time
from services.forecast.storage import REPLAY_ROOT, LocalStore
from services.observations.matching import distance_km

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "web/public/data/recorded-flight"
INDEX = ROOT / "web/src/recordingIndex.json"
SOURCES = json.loads(Path(__file__).with_name("recorded_sources.json").read_text())
FLIGHTS = SOURCES["flights"]
ORIGINAL = next(f for f in FLIGHTS if f["id"] == "az1704-20261121")
TRACK = DATA / "az1704-20261121.csv"
FORECAST = DATA / "az1704-20261121.json"
CITY_LABELS = {"LIN": "Milan Linate", "TRN": "Turin", "MAN": "Manchester"}


def extract_track(member: bytes, output: Path, flight: dict = ORIGINAL) -> None:
    if hashlib.sha256(member).hexdigest() != SOURCES["members"][flight["member"]]["sha256"]:
        raise ValueError("The aircraft-day archive member does not match the pinned checksum.")
    aircraft = json.loads(gzip.decompress(member))
    if aircraft["icao"] != flight["member"]:
        raise ValueError("Unexpected aircraft identity in the archive.")
    callsign = ""
    rows = []
    # readsb repeats identity intermittently. Only take observed airborne ADS-B
    # positions with fresh coordinates and a barometric altitude for this leg.
    for point in aircraft["trace"]:
        callsign = (point[8] or {}).get("flight", callsign).strip()
        if (
            callsign != flight["callsign"]
            or point[9] != "adsb_icao"
            or point[6] & 9
            or not isinstance(point[3], (int, float))
        ):
            continue
        when = datetime.fromtimestamp(aircraft["timestamp"] + point[0], UTC)
        stamp = when.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if flight["first"] <= stamp <= flight["last"]:
            rows.append((stamp, *point[1:4]))
    if len(rows) != flight["positions"] or (rows[0][0], rows[-1][0]) != (
        flight["first"],
        flight["last"],
    ):
        raise ValueError(f"Unexpected observations for {flight['callsign']}.")
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


def build_replay(path: Path, flight: dict = ORIGINAL) -> dict:
    points = recorded_points(path)
    origin, destination = airports()[flight["origin"]], airports()[flight["destination"]]
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
    run = flight["run"]
    manifest = store.manifest(run)
    issued = issue_time(run)
    if start < issued or points[-1]["time"] > datetime.fromisoformat(manifest["validUntil"]):
        raise ValueError("Weather does not cover the recorded flight.")
    cubes = {x["lead"]: unpack(store.tile(run, x["lead"], x["sha256"])) for x in manifest["leads"]}
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
        "flightNumber": flight["number"],
        "callsign": flight["callsign"],
        "sourceUrl": "https://github.com/adsblol/globe_history_2026/releases/tag/"
        + SOURCES["members"][flight["member"]]["tag"],
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


def index_entry(flight: dict, replay: dict) -> dict:
    def airport(stop: dict) -> dict:
        return {
            "code": stop["code"],
            "city": CITY_LABELS.get(stop["code"], stop["city"]),
            "name": stop["name"],
        }

    first, last = replay["samples"][0]["at"], replay["samples"][-1]["at"]
    if (first, last, replay["positions"]) != (flight["first"], flight["last"], flight["positions"]):
        raise ValueError(f"Track does not match the dated leg {flight['id']}.")
    return {
        "id": flight["id"],
        "number": flight["number"],
        "callsign": flight["callsign"],
        "airline": flight["airline"],
        "origin": airport(replay["origin"]),
        "destination": airport(replay["destination"]),
        "localDate": datetime.fromisoformat(first)
        .astimezone(ZoneInfo(flight["timezone"]))
        .date()
        .isoformat(),
        "first": first,
        "last": last,
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
        member = args.import_member.read_bytes()
        digest = hashlib.sha256(member).hexdigest()
        matches = [f for f in FLIGHTS if SOURCES["members"][f["member"]]["sha256"] == digest]
        if not matches:
            parser.error("Unknown archive member checksum.")
        for flight in matches:
            extract_track(member, DATA / (flight["id"] + ".csv"), flight)

    def write(path: Path, body: str) -> None:
        if args.check:
            if body != path.read_text():
                raise SystemExit(f"{path.name} differs from its archived source.")
        else:
            path.write_text(body)

    index = []
    for flight in FLIGHTS:
        replay = build_replay(DATA / (flight["id"] + ".csv"), flight)
        index.append(index_entry(flight, replay))
        write(
            DATA / (flight["id"] + ".json"),
            json.dumps(replay, ensure_ascii=False, separators=(",", ":")) + "\n",
        )
    if len({f["id"] for f in index}) != len(index):
        raise ValueError("Duplicate recording id.")
    write(
        INDEX,
        json.dumps(sorted(index, key=lambda f: f["first"]), ensure_ascii=False, indent=2) + "\n",
    )


if __name__ == "__main__":
    main()
