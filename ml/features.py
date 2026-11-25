"""Features shared by report matching and batch predictions on the published GFS grid."""

import math
from datetime import timedelta

from services.forecast.model_tile import CELLS
from services.forecast.schema import MISSING, SOUTH, WIDTH


def nearest_lead(issued, observed):
    hours = (observed - issued) / timedelta(hours=1)
    if not 0 <= hours <= 36:
        return None
    return 3 * math.ceil(hours / 3 - 0.5)


def vector(cube, cell, level, month):
    k = 2 + level * 3
    cape, terrain, height, ti, shear = [cube[i * CELLS + cell] for i in (0, 1, k, k + 1, k + 2)]
    if MISSING in (cape, terrain, height, ti, shear):
        return None
    ti, shear = ti / 100, shear / 100
    # TI1 = 10^7 * shear(s^-1) * deformation(s^-1). Stored shear is m/s per km.
    deformation = ti / (10_000 * shear) if shear > 0 else 0.0
    return [ti, shear, deformation, cape, terrain, height, SOUTH + cell // WIDTH, month]
