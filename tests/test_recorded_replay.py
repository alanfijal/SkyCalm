import csv
import hashlib
import json
from collections import Counter
from itertools import pairwise

import pytest

from scripts.recorded_replay import (
    DATA,
    FLIGHTS,
    FORECAST,
    INDEX,
    TRACK,
    build_replay,
    extract_track,
    index_entry,
    recorded_points,
)


def test_replay_pairs_real_observations_with_the_weather_at_the_time():
    assert hashlib.sha256(TRACK.read_bytes()).hexdigest() == (
        "2cb3f4773f9cb583b2c759cc5cdb20a5ff221944e863015ec125e880751ae5eb"
    )
    forecast = build_replay(TRACK)
    assert forecast == json.loads(FORECAST.read_bytes())
    assert (
        forecast["flightNumber"],
        forecast["origin"]["code"],
        forecast["destination"]["code"],
    ) == (
        "AZ1704",
        "CTA",
        "LIN",
    )
    assert forecast["run"]["issued"] == "2026-11-21T06:00:00Z"
    assert forecast["positions"] == 750 and forecast["maxGapSeconds"] == 20
    with TRACK.open() as source:
        obs = {r["time_utc"]: r for r in csv.DictReader(source)}
    samples = forecast["samples"]
    assert len(samples) == 111
    assert (samples[0]["at"], samples[-1]["at"]) == (next(iter(obs)), next(reversed(obs)))
    for point in samples:
        row = obs[point["at"]]
        assert (point["lat"], point["lon"], point["altitudeFt"]) == (
            float(row["latitude"]),
            float(row["longitude"]),
            int(row["barometric_altitude_ft"]),
        )
    assert all(a["distanceKm"] < b["distanceKm"] for a, b in pairwise(samples))
    assert Counter(p["category"] for p in samples) == {"smooth": 41, "light": 67, "moderate": 3}
    assert forecast["peak"] == "moderate"


@pytest.mark.parametrize("seconds", [0, 31])
def test_replay_rejects_duplicate_times_and_coverage_gaps(tmp_path, seconds):
    path = tmp_path / "track.csv"
    path.write_text(
        "time_utc,latitude,longitude,barometric_altitude_ft\n"
        "2026-11-21T14:00:00Z,37.4,15.1,1175\n"
        f"2026-11-21T14:00:{seconds:02}Z,37.5,15.2,1475\n"
    )
    with pytest.raises(ValueError, match="coverage gap"):
        recorded_points(path)


def test_wrong_source_is_rejected_before_export(tmp_path):
    path = tmp_path / "track.csv"
    with pytest.raises(ValueError, match="checksum"):
        extract_track(b"another aircraft or release", path)
    assert not path.exists()


@pytest.mark.parametrize("leg", FLIGHTS, ids=lambda leg: leg["number"])
def test_search_index_opens_the_exact_dated_recording(leg):
    track = DATA / (leg["id"] + ".csv")
    replay = build_replay(track, leg)
    assert replay == json.loads((DATA / (leg["id"] + ".json")).read_text())
    entry = index_entry(leg, replay)
    assert [r for r in json.loads(INDEX.read_text()) if r["id"] == leg["id"]] == [entry]
    assert (entry["origin"]["code"], entry["destination"]["code"]) == (
        leg["origin"],
        leg["destination"],
    )
    assert entry["localDate"] == "2026-11-21"
    assert 0 < replay["maxGapSeconds"] <= 30
    assert replay["positions"] == len(recorded_points(track)) == leg["positions"]
