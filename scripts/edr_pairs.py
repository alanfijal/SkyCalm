"""Pair reported aircraft peak EDR with archived SkyCalm weather. Export coarse research cells."""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import median

import numpy as np

from ml.features import nearest_lead, vector
from ml.pireps import JETS
from scripts.madis_coverage import open_hour, screen
from services.forecast.model_tile import NAMES, cell_for
from services.forecast.product import unpack
from services.forecast.schema import LEVELS, issue_time, tile_name
from services.forecast.storage import read_tile, validate_manifest

# ICAO standard pressure altitudes (metres) for the published levels, 400 down to 200 hPa.
# MADIS altitude is pressure altitude, independent of the day's actual geopotential heights.
PRESSURE_HEIGHT = {400: 7185, 350: 8117, 300: 9164, 250: 10363, 200: 11784}
PEAK_CUT = 0.2  # m^(2/3)/s, a research threshold on atmospheric EDR


@lru_cache(maxsize=4)
def cube(path, digest):
    return unpack(read_tile(path, digest))


def pair_hours(paths, grids, output):
    manifests = {}
    for path in grids.glob("gfs-*/manifest.json"):
        run = path.parent.name
        manifest = validate_manifest(json.loads(path.read_bytes()), run)
        manifests[issue_time(run)] = (
            path.parent,
            {x["lead"]: x["sha256"] for x in manifest["leads"]},
        )

    cells, peaks = {}, defaultdict(list)
    files = []
    by_region = defaultdict(Counter)
    seen_hours = set()
    for path in sorted(paths):
        with open_hour(path) as (dataset, hour, source):
            if hour in seen_hours:
                raise ValueError("Each archive hour must be supplied once")
            seen_hours.add(hour)
            fields = dataset.variables
            rows = screen(dataset, hour)
            eligible = rows.located & rows.peak_ok & (fields["altitude"].data >= 6096)
            observed = fields["timeObs"].data
            seen = {}
            duplicates = conflicts = 0
            for i in np.flatnonzero(eligible):
                lat, lon = (float(fields[k].data[i]) for k in ("latitude", "longitude"))
                cell = cell_for(lat, lon)
                if cell is None:
                    continue
                altitude = float(fields["altitude"].data[i])
                stamp = float(observed[i])
                value = float(fields["maxEDR"].data[i])
                # Identical time, position and pressure altitude provide no new independent evidence.
                key = (stamp, lat, lon, altitude)
                if key in seen:
                    duplicates += 1
                    if seen[key] is not None and seen[key][1] != value:
                        conflicts += 1
                        seen[key] = None
                    continue
                seen[key] = (i, value, cell)
            matched = 0
            for (stamp, _, _, altitude), item in seen.items():
                if item is None:
                    continue
                i, value, cell = item
                region = str(rows.sectors[i])
                counts = by_region[region]
                counts["screenedCruiseReports"] += 1
                when = datetime.fromtimestamp(stamp, UTC)
                available = [
                    issued
                    for issued in manifests
                    if timedelta(hours=6) <= when - issued <= timedelta(hours=36)
                ]
                if not available:
                    continue
                issued = max(available)
                directory, digests = manifests[issued]
                lead = nearest_lead(issued, when)
                level = min(LEVELS, key=lambda hpa: abs(PRESSURE_HEIGHT[hpa] - altitude))
                if abs(PRESSURE_HEIGHT[level] - altitude) > 1000:
                    continue
                weather = vector(
                    cube(directory / tile_name(lead), digests[lead]),
                    cell,
                    LEVELS.index(level),
                    (issued + timedelta(hours=lead)).month,
                )
                if weather is None:
                    continue
                key = (region, directory.name, lead, level, cell)
                cells[key] = weather
                peaks[key].append(value)
                matched += 1
                counts.update(
                    {
                        "matchedReports": 1,
                        "reportedZero": int(value == 0),
                        "atOrAbovePointTwo": int(value >= PEAK_CUT),
                        "documentedJet": int(rows.aircraft[i] in JETS),
                        "noProviderPeakQc": int(fields["maxEDRDD"].data[i] == b"Z"),
                    }
                )
            files.append(
                {
                    **source,
                    "file": path.name,
                    "matched": matched,
                    "duplicatePoints": duplicates,
                    "conflictingPointsExcluded": conflicts,
                }
            )
    output.mkdir(parents=True, exist_ok=True)
    with (output / "weather-edr.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "sector",
                "run",
                "leadHours",
                "levelHpa",
                "gridCell",
                *NAMES,
                "reports",
                "zeroPeak",
                "atOrAbovePointTwo",
                "medianReportedPeak",
                "maxReportedPeak",
            ]
        )
        for key, weather in sorted(cells.items()):
            vals = peaks[key]
            writer.writerow(
                [
                    *key,
                    *weather,
                    len(vals),
                    vals.count(0),
                    sum(v >= PEAK_CUT for v in vals),
                    round(median(vals), 5),
                    round(max(vals), 5),
                ]
            )
            by_region[key[0]]["weatherCells"] += 1
            by_region[key[0]]["cellsAtOrAbovePointTwo"] += int(max(vals) >= PEAK_CUT)
    result = {
        "files": files,
        "sectors": dict(by_region),
        "target": "Reported peak EDR in m^(2/3)/s. Zero and missing are distinct.",
        "cohort": "Pressure altitude >= FL200 in the SkyCalm grid. Aircraft type is optional for exploratory physical EDR only.",
        "weather": "Checked archived 1-degree serving tiles, issue 6 to 36 hours before the report. Nominal report UTC used.",
        "grouping": "One row per sector, forecast issue, lead, grid cell and pressure level. Repeated reports may be correlated.",
    }
    (output / "coverage.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hours", nargs="+", type=Path)
    parser.add_argument("--grids", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(pair_hours(args.hours, args.grids, args.output)["sectors"], indent=2))
