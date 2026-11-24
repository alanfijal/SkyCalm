"""Verify the generation and the two offline map assets through their public formats."""

import csv
import io
import json
from pathlib import Path

import pytest

from scripts.prepare_geodata import airports, polygon

ROOT = Path(__file__).resolve().parents[1]


def airport_csv(*rows: dict[str, str]) -> bytes:
    example = {
        "iata_code": "ABC",
        "icao_code": "ABCD",
        "name": "Example airport",
        "municipality": "Example",
        "iso_country": "GB",
        "latitude_deg": "51.0",
        "longitude_deg": "-1",
        "elevation_ft": "",
        "type": "medium_airport",
        "scheduled_service": "yes",
    }
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=example)
    writer.writeheader()
    writer.writerows(example | row for row in rows)
    return stream.getvalue().encode()


def test_code_priority_and_scheduled_service_filter() -> None:
    records = airports(
        airport_csv(
            {"iata_code": "", "icao_code": "EPSA", "elevation_ft": "36"},
            {},
            {"scheduled_service": "no"},
            {"type": "closed"},
            {"iata_code": "", "icao_code": ""},
        )
    )
    assert [record["code"] for record in records] == ["ABC", "EPSA"]
    assert [record["elevationFt"] for record in records] == [None, 36]


def test_code_collisions_fail_instead_of_overwriting_an_airport() -> None:
    with pytest.raises(ValueError, match="Duplicate airport code ABC"):
        airports(airport_csv({}, {"name": "Another airport"}))


def test_country_ring_quantization_preserves_closure_and_removes_collapsed_holes() -> None:
    outer = [[0, 0], [1, 0], [1.00003, 0.00004], [0, 1], [0, 0]]
    hole = [[0.1, 0.1], [0.10001, 0.10001], [0.10002, 0.10002], [0.1, 0.1]]
    assert polygon([outer, hole]) == [[(0, 0), (1, 0), (0, 1), (0, 0)]]
    assert polygon([hole]) == []


def test_bundled_airports_include_europe_and_identifiable_outside_routes() -> None:
    rows = json.loads((ROOT / "services/forecast/data/airports.json").read_bytes())
    airports_by_code = {r["code"]: r for r in rows}
    assert list(airports_by_code) == sorted(airports_by_code)
    assert len(rows) == len(airports_by_code)
    assert airports_by_code["BCN"]["elevationFt"] == 12
    assert airports_by_code["JFK"]["country"] == "US"


def test_bundled_globe_has_a_real_label_point_for_every_unique_country() -> None:
    folder = ROOT / "web/public/maps"
    land = json.loads((folder / "land.geojson").read_bytes())
    labels = json.loads((folder / "labels.json").read_bytes())
    assert land["type"] == labels["type"] == "FeatureCollection"
    codes = [f["properties"]["code"] for f in land["features"]]
    assert len(set(codes)) == len(codes)
    assert set(codes) >= {"ESP", "FRA", "NOR", "GBR"}
    assert codes == [f["properties"]["code"] for f in labels["features"]]
    for feature in labels["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert feature["geometry"]["type"] == "Point" and -180 <= lon <= 180 and -90 <= lat <= 90
        assert feature["properties"]["kind"] == "country"
