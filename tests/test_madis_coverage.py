import csv
import gzip
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from scipy.io import netcdf_file

from scripts import madis_coverage as madis
from scripts.edr_pairs import pair_hours

HOUR = datetime(2026, 8, 15, 12, tzinfo=UTC)


def archive(tmp_path, rows, *, include_type=True, altitude_units=None):
    path = tmp_path / "sample.nc"
    with netcdf_file(path, "w") as ds:
        ds.createDimension("record", len(rows))
        ds.createDimension("width", 8)
        defaults = {
            "latitude": 51,
            "longitude": -1,
            "altitude": 6096,
            "timeObs": HOUR.timestamp(),
            "maxEDR": 0.0,
        }
        for name, default in defaults.items():
            field = ds.createVariable(name, "d", ("record",))
            field.units = (
                altitude_units if name == "altitude" and altitude_units else madis.UNITS[name]
            )
            field._FillValue = 99999.0
            field[:] = [r.get(name, default) for r in rows]
            qc = ds.createVariable(name + "DD", "c", ("record",))
            qc[:] = [r.get(name + "DD", b"Z") for r in rows]
            word = ds.createVariable(name + "QCR", "i", ("record",))
            word[:] = [r.get(name + "QCR", 0) for r in rows]
        for name, default in (
            ("interpolatedLL", "r"),
            ("interpolatedTime", "r"),
            ("turbulenceError", "-"),
        ):
            field = ds.createVariable(name, "b", ("record",))
            field[:] = [ord(r.get(name, default)) for r in rows]
        # The raw field can contain a NOAA error code even when the clean field is missing.
        ds.createVariable("maxTurbulence", "d", ("record",))[:] = 2.54
        if include_type:
            field = ds.createVariable("tamdarAcType", "c", ("record", "width"))
            field[:] = [np.frombuffer(r.get("type", b"").ljust(8), dtype="S1") for r in rows]
    compressed = tmp_path / "20260815_1200.gz"
    compressed.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
    return compressed


def test_count_measured_zero_missing_peak_and_explicit_jet_separately(tmp_path):
    path = archive(
        tmp_path,
        [
            {"longitude": -12},
            {"type": b"A320", "maxEDR": 0.28, "maxEDRDD": b"S"},
            {"type": b"AT76", "altitude": 6095},
            {"maxEDR": 99999},
            {"maxEDR": np.nan},
            {"maxEDRDD": b"Q"},
            {"maxEDRQCR": 1},
            {"turbulenceError": "f"},
            {"longitude": -12.1, "type": b"AT76"},
            {"longitude": -90},
            {"altitude": 99999},
            {"latitudeQCR": 1},
            {"interpolatedLL": "i"},
            {"interpolatedTime": "i"},
            {"timeObs": HOUR.timestamp() + 3600},
        ],
    )
    result = madis.audit(path)
    assert result["archiveRows"] == 15
    assert result["hourUtc"] == "2026-08-15T12:00:00Z"
    assert result["regions"]["europe"] == {
        "locatedRows": 8,
        "missingPeak": 2,
        "rejectedPeakQc": 3,
        "reportedPeak": 3,
        "reportedZeroPeak": 2,
        "peakWithoutQc": 2,
        "belowFL200": 1,
        "atOrAboveFL200": 2,
        "nonblankAircraftField": 2,
        "knownJetAtOrAboveFL200": 1,
    }
    atlantic = result["regions"]["north_atlantic"]
    assert atlantic["reportedPeak"] == 1
    assert atlantic["knownJetAtOrAboveFL200"] == 0


def test_absent_type_does_not_discard_measurements_or_create_jets(tmp_path):
    result = madis.audit(archive(tmp_path, [{}], include_type=False))
    europe = result["regions"]["europe"]
    assert europe["reportedPeak"] == 1
    assert europe["nonblankAircraftField"] == europe["knownJetAtOrAboveFL200"] == 0


def test_wrong_altitude_units_and_oversize_archives_stop_the_audit(tmp_path, monkeypatch):
    path = archive(tmp_path, [{}], altitude_units=b"feet")
    with pytest.raises(ValueError, match="units for altitude"):
        madis.audit(path)
    monkeypatch.setattr(madis, "MAX_EXPANDED", 20)
    with pytest.raises(ValueError, match="Expanded MADIS hour"):
        madis.audit(path)
    monkeypatch.setattr(madis, "MAX_COMPRESSED", 20)
    with pytest.raises(ValueError, match="Compressed MADIS hour"):
        madis.audit(path)


def test_pair_only_measured_cruise_values_and_group_shared_weather(tmp_path):
    stamp = datetime(2026, 11, 20, 12, tzinfo=UTC).timestamp()
    rows = [
        {"timeObs": stamp + offset, "maxEDR": peak, "type": aircraft, "altitude": 10000}
        for offset, peak, aircraft in (
            (0, 0, b""),
            (0, 0, b""),
            (10, 0.2, b"A320"),
            (11, 99999, b""),
            (12, 0.31, b""),
            (12, 0.1, b""),
        )
    ]
    path = archive(tmp_path, rows).rename(tmp_path / "20261120_1200.gz")
    grids = Path(__file__).resolve().parents[1] / "services/forecast/data/replay"
    result = pair_hours([path], grids, tmp_path)
    counts = result["sectors"]["europe"]
    assert counts["matchedReports"] == 2
    assert counts["reportedZero"] == counts["atOrAbovePointTwo"] == counts["documentedJet"] == 1
    assert counts["weatherCells"] == 1
    assert result["files"][0]["duplicatePoints"] == 2
    assert result["files"][0]["conflictingPointsExcluded"] == 1
    with (tmp_path / "weather-edr.csv").open() as stream:
        (row,) = csv.DictReader(stream)
    assert (row["run"], row["reports"], row["atOrAbovePointTwo"]) == ("gfs-20261120-06", "2", "1")
    assert float(row["medianReportedPeak"]) == pytest.approx(0.1)


def test_future_grids_and_repeated_archives_cannot_supply_matches(tmp_path):
    path = archive(tmp_path, [{"altitude": 10000}], include_type=False)
    grids = Path(__file__).resolve().parents[1] / "services/forecast/data/replay"
    result = pair_hours([path], grids, tmp_path)
    assert result["sectors"]["europe"]["screenedCruiseReports"] == 1
    assert result["files"][0]["matched"] == 0
    with pytest.raises(ValueError, match="supplied once"):
        pair_hours([path, path], grids, tmp_path)
