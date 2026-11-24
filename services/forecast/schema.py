"""Shared weather product coordinates and versioned on-disk format."""

import re
from datetime import UTC, datetime

SOUTH, NORTH, WEST, EAST = 34, 72, -25, 45
# Tiles sample every degree after computing derivatives on the native 0.25° grid.
WIDTH, HEIGHT = EAST - WEST + 1, NORTH - SOUTH + 1
LEVELS = (400, 350, 300, 250, 200)
LEADS = tuple(range(0, 37, 3))
SCORER = "ti1-cape-v1"
MISSING = -32768
# One surface CAPE plane, terrain, then height/TI1/shear at each pressure.
PLANES = 2 + len(LEVELS) * 3
CATEGORIES = ("smooth", "light", "moderate", "severe")


def issue_time(run_id: str) -> datetime:
    if not re.fullmatch(r"gfs-\d{8}-(00|06|12|18)", run_id):
        raise ValueError("Choose a valid GFS run.")
    return datetime.strptime(run_id, "gfs-%Y%m%d-%H").replace(tzinfo=UTC)


def utc_text(when: datetime) -> str:
    return when.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def inside(lat: float, lon: float) -> bool:
    return SOUTH <= lat <= NORTH and WEST <= lon <= EAST


def tile_name(lead: int) -> str:
    if lead not in LEADS:
        raise ValueError("Invalid forecast lead")
    return f"f{lead:03}.bin.gz"
