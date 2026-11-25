"""Read the compact batch predictions alongside a physical weather tile."""

import gzip
import io
import math
from functools import lru_cache

from services.forecast.schema import CATEGORIES, HEIGHT, LEVELS, MISSING, SOUTH, WEST, WIDTH, inside

NAMES = ("ti1", "shear", "deformation", "cape", "terrain", "height", "latitude", "month")
WORDS = (
    "wind shear and deformation",
    "wind changing with height",
    "horizontal wind deformation",
    "convective energy",
    "terrain height",
    "forecast level",
    "latitude",
    "time of year",
)
SCHEMA = "gfs-pressure-v1"
CELLS = HEIGHT * WIDTH
WIDTH_BYTES = 5
NO_FEATURE = 254
NO_DATA = 255


def cell_for(lat, lon):
    if not inside(lat, lon):
        return None
    return math.floor(lat - SOUTH + 0.5) * WIDTH + math.floor(lon - WEST + 0.5)


def level_for(cube, cell, feet):
    heights = [
        (abs(cube[(2 + 3 * k) * CELLS + cell] - feet * 0.3048), k)
        for k in range(len(LEVELS))
        if cube[(2 + 3 * k) * CELLS + cell] != MISSING
    ]
    if not heights:
        return None
    distance, level = min(heights)
    return level if distance <= 1000 else None


@lru_cache(maxsize=16)
def decode_predictions(payload):
    expected = CELLS * len(LEVELS) * WIDTH_BYTES
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
        data = stream.read(expected + 1)
    if len(data) != expected:
        raise ValueError("Invalid prediction grid dimensions")
    return data


def point_prediction(tile, cube, pt):
    cell = cell_for(pt["lat"], pt["lon"])
    level = level_for(cube, cell, pt["altitudeFt"]) if cell is not None else None
    if level is None:
        return {}
    offset = (level * CELLS + cell) * WIDTH_BYTES
    *prob, feature = tile[offset : offset + WIDTH_BYTES]
    if feature == NO_DATA:
        return {}
    win = max(range(4), key=prob.__getitem__)
    return {
        "category": CATEGORIES[win],
        "method": "lightgbm",
        "probability": round(prob[win] / 255, 3),
        "driver": WORDS[feature] if feature < len(WORDS) else None,
    }
