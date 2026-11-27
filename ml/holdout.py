"""A predeclared historical test period with spatial blocks unseen in model fitting."""

import hashlib
import math
from datetime import date

from ml.pireps import sector


def spatial_block(lat: float, lon: float) -> str:
    return f"{math.floor(lat / 5)}:{math.floor(lon / 5)}"


def withheld(block: str) -> bool:
    # Reserve one in five 5-degree blocks using a fixed, label-independent assignment.
    return (
        int.from_bytes(hashlib.sha256(("skycalm-7a:" + block).encode()).digest()[:4], "big") % 5
        == 0
    )


def partition(row: dict, validation_start: date, test_start: date) -> str | None:
    if validation_start >= test_start:
        raise ValueError("Validation must precede testing")
    day = date.fromisoformat(row["observed"][:10])
    block = spatial_block(row["lat"], row["lon"])
    if day >= test_start:
        return "test" if withheld(block) else None
    if withheld(block):
        return None
    return "validation" if day >= validation_start else "train"


def independent(partitions: dict[str, list[dict]], manifest: dict) -> bool:
    if manifest.get("holdoutProtocol") != "native-time-and-region-v2":
        return False
    try:
        validation = date.fromisoformat(manifest["validationStart"])
        test = date.fromisoformat(manifest["testStart"])
        previous_ids: set[str] = set()
        previous_runs: set[str] = set()
        cohorts: set[str] = set()
        for side in ("train", "validation", "test"):
            rows = partitions[side]
            ids = {r["id"] for r in rows}
            runs = {r["run"] for r in rows}
            if not rows or len(ids) != len(rows) or ids & previous_ids or runs & previous_runs:
                return False
            for r in rows:
                if (
                    r["gridStep"] != 0.25
                    or not (math.isfinite(r["lat"]) and math.isfinite(r["lon"]))
                    or not (-90 <= r["lat"] <= 90 and -180 <= r["lon"] <= 180)
                    or r["sector"] != sector(r["lat"], r["lon"])
                    or partition(r, validation, test) != side
                ):
                    return False
                cohorts.add(r["cohort"])
            previous_ids.update(ids)
            previous_runs.update(runs)
        return cohorts in ({"cruise"}, {"lower"})
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
