"""Count observations in one historical NOAA MADIS ACARS hour, without exporting flight IDs."""

import argparse
import gzip
import hashlib
import io
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

from ml.pireps import JETS, sector
from services.forecast.schema import utc_text

MAX_COMPRESSED = 16 * 1024**2
MAX_EXPANDED = 128 * 1024**2
UNITS = {
    "latitude": b"degree_N",
    "longitude": b"degree_E",
    "altitude": b"meter (pressure altitude, msl)",
    "timeObs": b"seconds since 1970-1-1 00:00:00",
    "maxEDR": b"m^(2/3) s^-1",
}


@dataclass
class Screening:
    sectors: np.ndarray
    located: np.ndarray
    peak_present: np.ndarray
    peak_ok: np.ndarray
    aircraft: np.ndarray


def screen(dataset, hour: datetime) -> Screening:
    variables = dataset.variables
    for name, unit in UNITS.items():
        if variables[name].units != unit:
            raise ValueError(f"Unrecognized MADIS units for {name}")
    lat = variables["latitude"].data
    lon = variables["longitude"].data
    altitude = variables["altitude"].data
    observed = variables["timeObs"].data
    peak = variables["maxEDR"].data

    def usable(name: str) -> np.ndarray:
        field = variables[name]
        # Z means the provider supplied no QC. Report that separately from QC failures.
        return (
            np.isfinite(field.data)
            & (field.data != field._FillValue)
            & np.isin(variables[name + "DD"].data, [b"Z", b"C", b"S", b"V", b"G"])
            & (variables[name + "QCR"].data == 0)
        )

    locations = np.array([sector(y, x) for y, x in zip(lat, lon, strict=True)])
    point = (
        usable("latitude")
        & usable("longitude")
        & usable("altitude")
        & usable("timeObs")
        & (altitude > 0)
        & (altitude <= 60_000 * 0.3048)
        & (observed >= hour.timestamp())
        & (observed < hour.timestamp() + 3600)
        & (variables["interpolatedLL"].data == ord("r"))
        & (variables["interpolatedTime"].data == ord("r"))
    )
    # NOAA removes embedded no-data codes in maxEDR. maxTurbulence is the raw encoding.
    peak_present = np.isfinite(peak) & (peak >= 0) & (peak != variables["maxEDR"]._FillValue)
    peak_ok = peak_present & usable("maxEDR") & (variables["turbulenceError"].data != ord("f"))
    aircraft = np.full(len(lat), "", dtype="U8")
    if "tamdarAcType" in variables:
        aircraft = np.array(
            [
                b"".join(row).strip(b" \x00").decode("ascii").upper()
                for row in variables["tamdarAcType"].data
            ],
            dtype="U8",
        )
    return Screening(locations, point, peak_present, peak_ok, aircraft)


def summarize(dataset, hour: datetime) -> dict:
    variables = dataset.variables
    peak = variables["maxEDR"].data
    altitude = variables["altitude"].data
    rows = screen(dataset, hour)
    locations, point = rows.sectors, rows.located
    peak_present, peak_ok, aircraft = rows.peak_present, rows.peak_ok, rows.aircraft
    jet = np.isin(aircraft, sorted(JETS))
    high = altitude >= 6096  # FL200 in pressure metres
    regions = {}
    for name in ("europe", "north_atlantic"):
        located = point & (locations == name)
        measured = located & peak_ok
        regions[name] = {
            "locatedRows": int(located.sum()),
            "missingPeak": int((located & ~peak_present).sum()),
            "rejectedPeakQc": int((located & peak_present & ~peak_ok).sum()),
            "reportedPeak": int(measured.sum()),
            "reportedZeroPeak": int((measured & (peak == 0)).sum()),
            "peakWithoutQc": int((measured & (variables["maxEDRDD"].data == b"Z")).sum()),
            "belowFL200": int((measured & ~high).sum()),
            "atOrAboveFL200": int((measured & high).sum()),
            "nonblankAircraftField": int((measured & (aircraft != "")).sum()),
            "knownJetAtOrAboveFL200": int((measured & high & jet).sum()),
        }
    return {"hourUtc": utc_text(hour), "archiveRows": len(peak), "regions": regions}


@contextmanager
def open_hour(path: Path):
    hour = datetime.strptime(path.name, "%Y%m%d_%H00.gz").replace(tzinfo=UTC)
    with path.open("rb") as stream:
        compressed = stream.read(MAX_COMPRESSED + 1)
    if len(compressed) > MAX_COMPRESSED:
        raise ValueError("Compressed MADIS hour exceeds the sample limit")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        payload = stream.read(MAX_EXPANDED + 1)
    if len(payload) > MAX_EXPANDED:
        raise ValueError("Expanded MADIS hour exceeds the sample limit")
    with netcdf_file(io.BytesIO(payload), mmap=False) as dataset:
        yield (
            dataset,
            hour,
            {
                "compressedBytes": len(compressed),
                "sha256": hashlib.sha256(compressed).hexdigest(),
            },
        )


def audit(path: Path) -> dict:
    with open_hour(path) as (dataset, hour, source):
        return {**summarize(dataset, hour), **source}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hour", type=Path, help="A local YYYYMMDD_HH00.gz ACARS point file")
    print(json.dumps(audit(parser.parse_args().hour), indent=2, allow_nan=False))
