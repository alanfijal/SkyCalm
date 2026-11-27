import csv
import gzip
import json
from datetime import UTC, datetime

import pytest

from ml.pireps import Report
from scripts import export_cruise_labels as labels
from scripts import pilot_weather_sample as sample


def test_export_only_typed_cruise_cohorts_from_identical_census(tmp_path, monkeypatch):
    stamp = datetime(2026, 6, 4, 15, tzinfo=UTC)
    reports = [
        Report(stamp, 53, -20, 35000, "B777", "moderate"),
        Report(stamp, 48, 2, 33000, "A320", "smooth"),
        Report(stamp, 40, -100, 30000, "B737", "light"),
        Report(stamp, 48, 3, 10000, "A320", "light"),
        Report(stamp, -10, 110, 30000, "B737", "light"),
    ]
    sources = [{"file": "month.csv", "sha256": "verified"}]
    monkeypatch.setattr(labels, "audit_files", lambda paths: (reports, {"sources": sources}))
    review = {
        "audit": {"sources": sources},
        "review": {"validationStart": "2026-07-01", "testStart": "2026-08-01"},
    }
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(review))
    result = labels.export(tmp_path, path, tmp_path)
    assert result["labels"] == {
        "north_atlantic": {"moderate": 1},
        "europe": {"smooth": 1},
        "north_america": {"light": 1},
    }
    with gzip.open(tmp_path / "cruise-labels.csv.gz", "rt") as stream:
        rows = list(csv.DictReader(stream))
    assert len({r["reportId"] for r in rows}) == 3
    assert all(
        r["forecastCycle"] == "gfs-20260604-06" and r["forecastLeadHours"] == "9" for r in rows
    )
    review["audit"]["sources"] = []
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="audited census"):
        labels.export(tmp_path, path, tmp_path)


def test_weather_sample_filters_holdout_regions_and_missing_features(tmp_path, monkeypatch):
    base = dict(
        forecastCycle="gfs-20260604-06",
        forecastLeadHours=9,
        split="train",
        region="europe",
        latitude=50,
        longitude=4,
        pressureAltitudeFt=34000,
        reportedTurbulence="smooth",
        observedUtc="2026-06-04T15:00:00Z",
    )
    path = tmp_path / "labels.gz"
    with gzip.open(path, "wt") as stream:
        writer = csv.DictWriter(stream, fieldnames=base)
        writer.writeheader()
        for patch in (
            {},
            {"split": "test"},
            {"split": "excluded"},
            {"region": "north_america"},
            {"latitude": 54},
        ):
            writer.writerow({**base, **patch})
    monkeypatch.setattr(sample.native, "load_fields", lambda run, lead, domain: ({}, {"bytes": 9}))
    monkeypatch.setattr(sample.native, "jet_cores", lambda fields, domain: None)
    monkeypatch.setattr(
        sample.native,
        "vector",
        lambda fields, cores, lat, *args: {
            key: 0.0 if lat == 50 else float("nan") for key in sample.native.FEATURES
        },
    )
    slot = ("gfs-20260604-06", 9)
    result = sample.pair_sample(path, [slot], tmp_path)
    assert result["matched"] == 1 and result["sources"][0]["eligible"] == 2
    assert result["labels"] == {"europe": {"smooth": 1}}
    with (tmp_path / "pilot-weather-sample.csv").open() as stream:
        (row,) = csv.DictReader(stream)
    assert row["region"] == "europe" and row["ti1"] == "0.0"
    with pytest.raises(ValueError, match="distinct"):
        sample.pair_sample(path, [slot, slot], tmp_path)
    with pytest.raises(ValueError, match="eligible"):
        sample.pair_sample(path, [("gfs-20260604-06", 6)], tmp_path)
