"""Decode native pressure fields and score a European grid with a derivative halo."""

import gzip

import eccodes as ec
import numpy as np

from grid.source import Record, SourceError
from services.forecast.schema import EAST, LEVELS, MISSING, NORTH, SOUTH, WEST, issue_time

STEP = 0.25
LATS = np.arange(SOUTH - STEP, NORTH + 2 * STEP, STEP)
LONS = np.arange(WEST - STEP, EAST + 2 * STEP, STEP)
ROWS = np.rint((90 - LATS) / STEP).astype(int)
COLS = np.rint((LONS % 360) / STEP).astype(int)
FIELD_NUMBERS = {"UGRD": (2, 2), "VGRD": (2, 3), "TMP": (0, 0), "HGT": (3, 5), "CAPE": (7, 6)}


def decode(message: bytes, record: Record, run_id: str, lead: int) -> np.ndarray:
    if (
        message[:4] != b"GRIB"
        or message[-4:] != b"7777"
        or int.from_bytes(message[8:16]) != len(message)
    ):
        raise SourceError("Truncated or unexpected GRIB2 message")
    handle = ec.codes_new_from_message(message)
    when = issue_time(run_id)
    expected = {
        "edition": 2,
        "discipline": 0,
        "gridType": "regular_ll",
        "Ni": 1440,
        "Nj": 721,
        "scanningMode": 0,
        "latitudeOfFirstGridPointInDegrees": 90,
        "longitudeOfFirstGridPointInDegrees": 0,
        "iDirectionIncrementInDegrees": STEP,
        "jDirectionIncrementInDegrees": STEP,
        "parameterCategory": FIELD_NUMBERS[record.field][0],
        "parameterNumber": FIELD_NUMBERS[record.field][1],
        "dataDate": int(when.strftime("%Y%m%d")),
        "dataTime": when.hour * 100,
        "endStep": lead,
        "typeOfLevel": "surface" if record.level == "surface" else "isobaricInhPa",
    }
    if record.level != "surface":
        expected["level"] = int(record.level.split()[0])
    try:
        for key, value in expected.items():
            if ec.codes_get(handle, key) != value:
                raise SourceError(f"Unexpected {key} for {record.field} at {record.level}")
        local = ec.codes_get_values(handle).reshape(721, 1440)[np.ix_(ROWS, COLS)]
        if ec.codes_get(handle, "bitmapPresent"):
            local[local == ec.codes_get(handle, "missingValue")] = np.nan
        return local
    finally:
        ec.codes_release(handle)


def diagnostics(u: np.ndarray, v: np.ndarray, height: np.ndarray, latitudes: np.ndarray):
    # Fields are ordered from south to north and low to high altitude.
    dy = 6_371_000 * np.radians(STEP)
    dx = dy * np.cos(np.radians(latitudes))[None, :, None]
    dudx, dvdx = np.gradient(u, axis=2) / dx, np.gradient(v, axis=2) / dx
    dudy, dvdy = np.gradient(u, axis=1) / dy, np.gradient(v, axis=1) / dy
    dz = np.gradient(height, axis=0)
    dz = np.where(dz > 0, dz, np.nan)
    shear = np.hypot(np.gradient(u, axis=0), np.gradient(v, axis=0)) / dz
    deformation = np.hypot(dudx - dvdy, dvdx + dudy)
    return 1e7 * shear * deformation, 1000 * shear


def encode(fields: dict[tuple[str, str], np.ndarray]) -> bytes:
    def stack(name: str) -> np.ndarray:
        return np.stack([fields[name, f"{p} mb"] for p in LEVELS])

    height = stack("HGT")
    ti1, shear = diagnostics(stack("UGRD"), stack("VGRD"), height, LATS)
    valid = np.isfinite(stack("TMP")) & np.isfinite(height)
    planes = [fields["CAPE", "surface"], fields["HGT", "surface"]]
    for k in range(len(LEVELS)):
        planes.extend(
            [
                height[k],
                np.where(valid[k], ti1[k] * 100, np.nan),
                np.where(valid[k], shear[k] * 100, np.nan),
            ]
        )
    # Remove the halo and sample the scored grid at 1° for serving.
    cube = np.stack(planes)[:, 1:-1:4, 1:-1:4]
    encoded = np.where(np.isfinite(cube), np.clip(np.rint(cube), -32767, 32767), MISSING)
    return gzip.compress(encoded.astype("<i2").tobytes(), compresslevel=6, mtime=0)
