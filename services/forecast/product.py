"""Sample the compact grid without a native decoder in the passenger API."""

import gzip
import io
import math
import sys
from array import array
from functools import lru_cache

from services.forecast.schema import (
    CATEGORIES,
    HEIGHT,
    LEVELS,
    MISSING,
    PLANES,
    SOUTH,
    WEST,
    WIDTH,
    inside,
)

TI1_LIMITS = (2.0, 6.0, 12.0)  # index in 10^-7 s^-2
CAPE_LIMITS = (500.0, 1500.0, 2500.0)  # J/kg surface-parcel proxy


def category(value: float, thresholds: tuple) -> str:
    return CATEGORIES[sum(value >= t for t in thresholds)]


@lru_cache(maxsize=36)
def unpack(data: bytes) -> array:
    length = PLANES * HEIGHT * WIDTH * 2
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
        raw = gz.read(length + 1)
    if len(raw) != length:
        raise ValueError("Incomplete weather tile")
    result = array("h")
    result.frombytes(raw)
    if sys.byteorder != "little":
        result.byteswap()
    return result


def bilinear(cube: array, plane: int, lat: float, lon: float) -> float | None:
    y, x = lat - SOUTH, lon - WEST
    r, c = math.floor(y), math.floor(x)
    dy, dx = y - r, x - c
    total = 0.0
    for row, wy in ((r, 1 - dy), (r + 1, dy)):
        for col, wx in ((c, 1 - dx), (c + 1, dx)):
            if not wy * wx:
                continue
            value = cube[(plane * HEIGHT + row) * WIDTH + col]
            if value == MISSING:
                return None
            total += value * wy * wx
    return total


def interpolate(a: float | None, b: float | None, t: float) -> float | None:
    if a is None or b is None:
        return None
    return a + (b - a) * t


def sample(cubes: dict[int, array], hours: float, point: dict) -> dict:
    result = {
        "category": "unavailable",
        "method": "missing",
        "ti1": None,
        "shear": None,
        "cape": None,
    }
    lat, lon = point["lat"], point["lon"]
    if not inside(lat, lon):
        return {**result, "method": "outside"}
    if not 0 <= hours <= 36:
        return {**result, "method": "horizon"}
    low = int(hours // 3) * 3
    fraction = (hours - low) / 3

    def plane(k: int) -> float | None:
        first = bilinear(cubes[low], k, lat, lon)
        if fraction == 0:
            return first
        return interpolate(first, bilinear(cubes[low + 3], k, lat, lon), fraction)

    heights = [plane(2 + i * 3) for i in range(len(LEVELS))]
    altitude = point["altitudeFt"] * 0.3048
    if heights[0] is not None and altitude < heights[0] and point["phase"] != "cruise":
        cape = plane(0)
        if cape is not None and cape >= 0:
            return {
                **result,
                "method": "cape",
                "cape": round(cape),
                "category": category(cape, CAPE_LIMITS),
            }
        return result
    for i, (h0, h1) in enumerate(zip(heights, heights[1:], strict=False)):
        if h0 is None or h1 is None or not h0 <= altitude <= h1 or h1 <= h0:
            continue
        t = (altitude - h0) / (h1 - h0)
        ti1 = interpolate(plane(3 + 3 * i), plane(6 + 3 * i), t)
        shear = interpolate(plane(4 + 3 * i), plane(7 + 3 * i), t)
        if ti1 is not None and shear is not None:
            return {
                **result,
                "method": "ti1",
                "ti1": round(ti1 / 100, 2),
                "shear": round(shear / 100, 2),
                "category": category(ti1 / 100, TI1_LIMITS),
            }
    return result
