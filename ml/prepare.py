"""Join explicit aircraft reports to forecasts available at observation time."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from ml.features import nearest_lead, vector
from services.forecast.model_tile import NAMES, cell_for, level_for
from services.forecast.product import TI1_LIMITS, category, unpack
from services.forecast.schema import CATEGORIES, issue_time, tile_name
from services.forecast.storage import validate_manifest


def match(observations, grids):
    runs = {}
    for path in sorted(grids.glob("gfs-*/manifest.json")):
        run = path.parent.name
        manifest = validate_manifest(json.loads(path.read_bytes()), run)
        runs[issue_time(run)] = (path.parent, {x["lead"]: x["sha256"] for x in manifest["leads"]})
    counts, seen, rows, cache = Counter(), set(), [], {}
    for path in sorted(observations.glob("gfs-*.json")):
        for item in json.loads(path.read_bytes())["items"]:
            if item["kind"] != "report":
                counts["advisories"] += 1
                continue
            if item["id"] in seen:
                counts["duplicate"] += 1
                continue
            seen.add(item["id"])
            if item["intensity"] not in CATEGORIES:
                counts["unreported"] += 1
                continue
            when = datetime.fromisoformat(item["from"])
            possible = [i for i in runs if nearest_lead(i, when) is not None]
            if not possible:
                counts["outside_forecast_time"] += 1
                continue
            issued = max(possible)
            directory, digests = runs[issued]
            lead = nearest_lead(issued, when)
            key = (issued, lead)
            if key not in cache:
                payload = (directory / tile_name(lead)).read_bytes()
                if hashlib.sha256(payload).hexdigest() != digests[lead]:
                    raise ValueError("Weather tile checksum mismatch")
                cache[key] = unpack(payload)
            lon, lat = item["geometry"]["coordinates"]
            cell = cell_for(lat, lon)
            feet = item["baseFt"]
            level = (
                level_for(cache[key], cell, feet) if cell is not None and feet is not None else None
            )
            data = (
                vector(cache[key], cell, level, (issued + timedelta(hours=lead)).month)
                if level is not None
                else None
            )
            if data is None:
                counts["outside_pressure_grid"] += 1
                continue
            rows.append(
                dict(zip(NAMES, data, strict=True))
                | {
                    "id": item["id"],
                    "observed": item["from"],
                    "run": directory.name,
                    "lead": lead,
                    "sector": "north_atlantic" if lon < -12 else "europe",
                    "label": CATEGORIES.index(item["intensity"]),
                    "baseline": CATEGORIES.index(category(data[0], TI1_LIMITS)),
                }
            )
    return sorted(rows, key=lambda r: (r["observed"], r["id"])), dict(counts)


def split(rows):
    days = sorted({r["observed"][:10] for r in rows})
    if len(days) < 3:
        raise ValueError("Three independent observation days are required")
    first = min(max(1, len(days) * 3 // 5), len(days) - 2)
    second = min(max(first + 1, len(days) * 4 // 5), len(days) - 1)
    # Keep one issue cycle on only one side of a split as well as keeping complete observation days.
    partitions = [[], [], []]
    occupied = {}
    removed = 0
    for row in rows:
        i = (
            0
            if row["observed"][:10] < days[first]
            else 1
            if row["observed"][:10] < days[second]
            else 2
        )
        if occupied.setdefault(row["run"], i) != i:
            removed += 1
            continue
        partitions[i].append(row)
    if not all(partitions):
        raise ValueError("A chronological split has no independent forecast cycle")
    return dict(zip(("train", "validation", "test"), partitions, strict=True)), removed


def prepare(observations, grids, output):
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows, counts = match(observations, grids)
    partitions, removed = split(rows)
    output.mkdir(parents=True, exist_ok=True)
    summary = {"excluded": counts, "splitOverlapDropped": removed, "splits": {}}
    for name, items in partitions.items():
        pq.write_table(pa.Table.from_pylist(items), output / f"{name}.parquet")
        summary["splits"][name] = {
            "rows": len(items),
            "first": items[0]["observed"],
            "last": items[-1]["observed"],
            "classes": dict(Counter(CATEGORIES[r["label"]] for r in items)),
        }
    (output / "dataset.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--grids", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.observations, args.grids, args.output)))
