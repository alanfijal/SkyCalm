from datetime import UTC, datetime

import numpy as np
import pytest

from grid import native
from grid.report_shard import plan, process
from ml.pireps import Report


def weather(domain=native.REGIONAL):
    # Zero-copy synthetic planes. Linear eastward wind shear and a fixed lapse rate.
    shape = (len(domain.latitudes), len(domain.longitudes))

    def plane(value):
        return np.broadcast_to(np.asarray(value), shape)

    fields = {
        ("HGT", "surface"): plane(10),
        ("HGT", "tropopause"): plane(11500),
        ("CAPE", "surface"): plane(300),
    }
    for p in native.PRESSURES:
        z = (1000 - p) * 12.0
        for name, value in (
            ("HGT", z),
            ("TMP", 290 - 0.006 * z),
            ("VVEL", 0.2),
            ("UGRD", 15 + 0.002 * z),
            ("VGRD", 0.0),
        ):
            fields[name, f"{p} mb"] = plane(value)
    return fields


def test_native_diagnostic_units_and_missing_outside_support():
    fields = weather()
    cores = native.jet_cores(fields)
    values = native.vector(fields, cores, 51, -1, 34000, 3)
    assert tuple(values) == native.FEATURES
    assert values["shear"] == pytest.approx(2.0)
    assert values["lapse_k_km"] == pytest.approx(6.0)
    assert values["ti1"] == values["ti2"] == values["frontogenesis_k_100km_3h"] == 0
    assert values["omega_pa_s"] == 0.2 and values["jet_core_km_500"] == 500
    assert values["brown_s1"] > 0 and values["gradient_ri"] > 0
    assert values["tropopause_above_m"] == pytest.approx(11500 - values["height"])
    assert native.vector(fields, cores, 0, 0, 34000, 3) is None
    assert native.pressure_at(58000) is None
    phi, lam = np.radians([51]), np.radians([-1])
    assert native.jet_distance(51, -1, (phi, lam)) == 0


def test_as_of_shard_reuses_success_and_never_commits_partial_results(tmp_path):
    report = Report(datetime(2025, 12, 31, 1, 31, tzinfo=UTC), 51, -1, 34000, "A320", "light")
    assert native.forecast_slot(report.time) == ("gfs-20251230-18", 9)
    manifests = tmp_path / "manifest"
    assert plan([report], manifests) == (1, 1)
    (path,) = manifests.glob("*.json")

    def failed(*args):
        raise RuntimeError("source unavailable")

    with pytest.raises(RuntimeError):
        process(path, tmp_path / "output", load=failed)
    assert not list((tmp_path / "output").glob("*.json"))
    result = process(path, tmp_path / "output", load=lambda *args: (weather(), {"bytes": 123}))
    assert len(result["rows"]) == 1 and result["rows"][0]["gridStep"] == 0.25
    assert process(path, tmp_path / "output", load=failed) == result


def test_north_american_weather_keeps_geography_and_feature_units():
    domain = native.NORTH_AMERICA
    fields = weather(domain)
    cores = native.jet_cores(fields, domain)
    for lat, lon in ((24, -170), (40, -105), (72, -60)):
        values = native.vector(fields, cores, lat, lon, 34000, 3, domain)
        assert values["latitude"] == lat
        assert values["shear"] == pytest.approx(2.0)
    assert native.vector(fields, cores, 51, -1, 34000, 3, domain) is None
