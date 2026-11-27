"""Native point diagnostics shared by a historical weather shard and prospective scoring."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property

import numpy as np

from grid.compute import STEP, decode
from grid.source import GfsSource
from ml.features import nearest_lead
from services.forecast.model_tile import NAMES

PRESSURES = (1000, 950, 900, 850, 700, 600, 500, 400, 350, 300, 250, 200, 150)


@dataclass(frozen=True)
class WeatherDomain:
    south: int
    north: int
    west: int
    east: int

    @cached_property
    def latitudes(self):
        # Keep the original margins for the 500 km jet-distance diagnostic.
        return np.arange(self.south - 6, self.north + 6 + STEP, STEP)

    @cached_property
    def longitudes(self):
        return np.arange(self.west - 18, self.east + 18 + STEP, STEP)


REGIONAL = WeatherDomain(34, 72, -60, 45)
NORTH_AMERICA = WeatherDomain(24, 72, -170, -60)
FIELDS = {(v, f"{p} mb") for p in PRESSURES for v in ("UGRD", "VGRD", "TMP", "VVEL", "HGT")}
FIELDS |= {("HGT", "tropopause"), ("HGT", "surface"), ("CAPE", "surface")}
MAX_BYTES = 64 * 1024 * 1024
FEATURES = (
    *NAMES,
    "wind_ms",
    "jet_core_km_500",
    "gradient_ri",
    "lapse_k_km",
    "tropopause_above_m",
    "omega_pa_s",
    "terrain_lift_700_ms",
    "ti2",
    "brown_s1",
    "frontogenesis_k_100km_3h",
)
EARTH = 6_371_000


def forecast_slot(observed: datetime) -> tuple[str, int]:
    if observed.utcoffset() != timedelta(0):
        raise ValueError("Expected an observation time in UTC")
    # Allow six hours after initialization for model dissemination. Never use an analysis.
    before = observed - timedelta(hours=6)
    cycle = before.replace(hour=before.hour // 6 * 6, minute=0, second=0, microsecond=0)
    return cycle.strftime("gfs-%Y%m%d-%H"), nearest_lead(cycle, observed)


def load_fields(run: str, lead: int, domain=REGIONAL) -> tuple[dict, dict]:
    src = GfsSource()
    rows = np.rint((90 - domain.latitudes) / STEP).astype(int)
    cols = np.rint((domain.longitudes % 360) / STEP).astype(int)
    try:
        fields = {
            (record.field, record.level): decode(
                blob, record, run, lead, rows=rows, cols=cols
            ).astype(np.float32)
            for record, blob in src.fields(run, lead, fields=FIELDS, byte_limit=MAX_BYTES)
        }
        return fields, src.last_source
    finally:
        src.http.clear()


def jet_cores(fields: dict, domain=REGIONAL) -> tuple[np.ndarray, np.ndarray]:
    peak = np.maximum.reduce(
        [np.hypot(fields["UGRD", f"{p} mb"], fields["VGRD", f"{p} mb"]) for p in (300, 250, 200)]
    )
    center = peak[1:-1]
    rows, cols = np.where((center >= 40) & (center > peak[:-2]) & (center >= peak[2:]))
    return np.radians(domain.latitudes[rows + 1]), np.radians(domain.longitudes[cols])


def jet_distance(lat: float, lon: float, cores: tuple[np.ndarray, np.ndarray]) -> float:
    if not len(cores[0]):
        return 500.0
    phi, lam = np.radians((lat, lon))
    h = (
        np.sin((cores[0] - phi) / 2) ** 2
        + np.cos(phi) * np.cos(cores[0]) * np.sin((cores[1] - lam) / 2) ** 2
    )
    return min(500.0, 2 * EARTH / 1000 * math.asin(math.sqrt(float(np.clip(h.min(), 0, 1)))))


def pressure_at(feet: int) -> int | None:
    # Flight levels reference standard pressure altitude. ISA above the 11 km tropopause is isothermal.
    z = feet * 0.3048
    p = (
        1013.25 * (1 - 0.0065 * z / 288.15) ** 5.25588
        if z <= 11000
        else 226.32 * math.exp(-(z - 11000) / 6341.6)
    )
    level = min(PRESSURES, key=lambda x: abs(math.log(x / p)))
    return level if abs(math.log(level / p)) < 0.13 else None


def vector(
    fields: dict,
    cores: tuple[np.ndarray, np.ndarray],
    lat: float,
    lon: float,
    feet: int,
    month: int,
    domain=REGIONAL,
) -> dict[str, float] | None:
    if not (
        domain.south <= lat <= domain.north
        and domain.west <= lon <= domain.east
        and 1 <= month <= 12
    ):
        return None
    pressure = pressure_at(feet)
    if pressure is None:
        return None
    i, j = round((lat - domain.latitudes[0]) / STEP), round((lon - domain.longitudes[0]) / STEP)
    grid_lat, grid_lon = float(domain.latitudes[i]), float(domain.longitudes[j])
    k = PRESSURES.index(pressure)
    above, below = PRESSURES[min(k + 1, len(PRESSURES) - 1)], PRESSURES[max(0, k - 1)]
    dy = EARTH * math.radians(STEP)
    dx = dy * math.cos(math.radians(grid_lat))

    def at(name: str, level: int | str = pressure) -> float:
        field = f"{level} mb" if isinstance(level, int) else level
        return float(fields[name, field][i, j])

    def gradient(name: str, level: str) -> tuple[float, float]:
        a = fields[name, level]
        return float(a[i, j + 1] - a[i, j - 1]) / (2 * dx), float(a[i + 1, j] - a[i - 1, j]) / (
            2 * dy
        )

    height, terrain = at("HGT"), at("HGT", "surface")
    dz = at("HGT", above) - at("HGT", below)
    if height < terrain or not dz > 0:
        return None
    shear = (
        math.hypot(at("UGRD", above) - at("UGRD", below), at("VGRD", above) - at("VGRD", below))
        / dz
    )
    ux, uy = gradient("UGRD", f"{pressure} mb")
    vx, vy = gradient("VGRD", f"{pressure} mb")
    deform = math.hypot(ux - vy, vx + uy)
    theta = (1000 / pressure) ** 0.2854
    tx, ty = (t * theta for t in gradient("TMP", f"{pressure} mb"))
    dt = at("TMP", above) * (1000 / above) ** 0.2854 - at("TMP", below) * (1000 / below) ** 0.2854
    stability = 9.80665 * dt / (at("TMP") * theta * dz)
    # At vanishing shear Ri is undefined. Preserve a missing input rather than assigning zero.
    ri = stability / shear**2 if shear > 1e-8 else math.nan
    txh, tyh = gradient("HGT", "surface")
    grad = math.hypot(tx, ty)
    front = -(ux * tx**2 + (uy + vx) * tx * ty + vy * ty**2) / grad if grad else 0.0
    absolute_vorticity = vx - uy + 2 * 7.292115e-5 * math.sin(math.radians(grid_lat))
    values = (
        1e7 * shear * deform,
        1000 * shear,
        deform,
        at("CAPE", "surface"),
        terrain,
        height,
        grid_lat,
        month,
        math.hypot(at("UGRD"), at("VGRD")),
        jet_distance(grid_lat, grid_lon, cores),
        ri,
        1000 * (at("TMP", below) - at("TMP", above)) / dz,
        at("HGT", "tropopause") - height,
        at("VVEL"),
        at("UGRD", 700) * txh + at("VGRD", 700) * tyh if at("HGT", 700) > terrain else math.nan,
        1e7 * shear * (deform - ux - vy),
        math.sqrt(0.3 * absolute_vorticity**2 + deform**2),
        front * 1.08e9,
    )
    return dict(zip(FEATURES, map(float, values), strict=True))
