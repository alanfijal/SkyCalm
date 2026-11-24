"""Rebuild the bundled airport and globe data from checksum-pinned public sources."""

import csv
import hashlib
import io
import json
import os
import random
import re
import time
from itertools import groupby
from pathlib import Path
from tempfile import mkstemp
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".local" / "geodata-source"
MAPS = ROOT / "web" / "public" / "maps"
RAW = "https://raw.githubusercontent.com/"
AIRPORTS_URL = (
    RAW + "davidmegginson/ourairports-data/52f8e87ff0e29bc0f260ac20b261c05ec575a1a8/airports.csv"
)
COUNTRIES_URL = (
    RAW + "nvkelso/natural-earth-vector/ca96624a56bd078437bca8184e78163e5039ad19/"
    "geojson/ne_50m_admin_0_countries.geojson"
)
AIRPORTS_SHA256 = "a903f63c4a5fef41acd82ed0876acce0d1efd470849e1a6a1f79d34948b6123b"
COUNTRIES_SHA256 = "3e458fc036ad0a66411f2c1e6cac49c5d7bfb81cb1123bc513b22511a2b7fdeb"


def save(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = mkstemp(dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as dest:
            dest.write(data)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def source(name: str, url: str, digest: str, limit: int) -> bytes:
    path = CACHE / name
    if path.is_file() and path.stat().st_size <= limit:
        cached = path.read_bytes()
        if hashlib.sha256(cached).hexdigest() == digest:
            return cached

    request = Request(url, headers={"User-Agent": "SkyCalm-geodata/1"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read(limit + 1)
            break
        except OSError as exc:
            if isinstance(exc, HTTPError) and exc.code not in {408, 429, 500, 502, 503, 504}:
                raise
            if attempt == 2:
                raise
            time.sleep(2**attempt + random.uniform(0, 0.25))
    if len(data) > limit or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Unexpected size or SHA-256 for {name}")
    save(path, data)
    return data


def airports(data: bytes) -> list[dict]:
    by_code = {}
    for row in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        if row["scheduled_service"] != "yes" or row["type"] == "closed":
            continue
        if re.fullmatch(r"[A-Z]{3}", row["iata_code"]):
            code = row["iata_code"]
        elif re.fullmatch(r"[A-Z]{4}", row["icao_code"]):
            code = row["icao_code"]
        else:
            continue
        if code in by_code:
            raise ValueError(f"Duplicate airport code {code}")
        lat, lon = float(row["latitude_deg"]), float(row["longitude_deg"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"Invalid airport coordinates for {code}")
        by_code[code] = {
            "code": code,
            "name": row["name"],
            "city": row["municipality"],
            "country": row["iso_country"],
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "elevationFt": int(row["elevation_ft"]) if row["elevation_ft"] else None,
        }
    return [by_code[code] for code in sorted(by_code)]


def polygon(rings: list) -> list:
    """Quantize the generalized boundaries identically on both sides of each border."""
    output = []
    for i, ring in enumerate(rings):
        points = [(round(lon, 3), round(lat, 3)) for lon, lat in ring]
        coords = [point for point, _ in groupby(points)]
        if coords[0] != coords[-1]:
            raise ValueError("Open Natural Earth polygon ring")
        if len(set(coords)) < 3:
            if i == 0:
                return []
            continue
        output.append(coords)
    return output


def map_features(data: bytes) -> tuple[list[dict], list[dict]]:
    land, labels = [], []
    for feature in json.loads(data)["features"]:
        props, geom = feature["properties"], feature["geometry"]
        code = props["ISO_A3"] if props["ISO_A3"] != "-99" else props["ADM0_A3"]
        country = {"name": props["NAME_EN"], "code": code}
        if geom["type"] == "Polygon":
            coords = polygon(geom["coordinates"])
        elif geom["type"] == "MultiPolygon":
            coords = [p for rings in geom["coordinates"] if (p := polygon(rings))]
        else:
            raise ValueError(f"Unexpected Natural Earth geometry {geom['type']}")
        if not coords:
            raise ValueError(f"Empty Natural Earth geometry for {code}")
        land.append(
            {
                "type": "Feature",
                "properties": country,
                "geometry": {"type": geom["type"], "coordinates": coords},
            }
        )
        labels.append(
            {
                "type": "Feature",
                "properties": {**country, "kind": "country", "rank": props["LABELRANK"]},
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(props["LABEL_X"], 3), round(props["LABEL_Y"], 3)],
                },
            }
        )
    return land, labels


def records_json(records: list[dict[str, Any]], *, geojson: bool = False) -> bytes:
    # One record per line gives dataset updates a useful Git diff.
    lines = [
        json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        for row in records
    ]
    array = "[\n" + ",\n".join(lines) + "\n]"
    payload = '{"type":"FeatureCollection","features":' + array + "}" if geojson else array
    return (payload + "\n").encode()


def main() -> None:
    stations = airports(source("airports.csv", AIRPORTS_URL, AIRPORTS_SHA256, 16_000_000))
    land, labels = map_features(
        source("countries.geojson", COUNTRIES_URL, COUNTRIES_SHA256, 4_000_000)
    )
    save(ROOT / "services" / "forecast" / "data" / "airports.json", records_json(stations))
    save(MAPS / "land.geojson", records_json(land, geojson=True))
    save(MAPS / "labels.json", records_json(labels, geojson=True))
    print(f"Prepared {len(stations)} scheduled-service airports and {len(land)} country features.")


if __name__ == "__main__":
    main()
