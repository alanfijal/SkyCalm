"""Join a bounded sample of training-set pilot reports to native historical GFS fields."""

import argparse
import csv
import gzip
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

from grid import native


def pair_sample(labels, slots, output, *, north_america=False):
    if not 1 <= len(slots) <= 3 or len(set(slots)) != len(slots):
        raise ValueError("Supply one to three distinct forecast slots")
    domain = native.NORTH_AMERICA if north_america else native.REGIONAL
    regions = {"north_america"} if north_america else {"europe", "north_atlantic"}
    with gzip.open(labels, "rt", newline="") as stream:
        candidates = {slot: [] for slot in slots}
        reader = csv.DictReader(stream)
        label_fields = reader.fieldnames or []
        for row in reader:
            slot = (row["forecastCycle"], int(row["forecastLeadHours"]))
            if slot in candidates and row["split"] == "train" and row["region"] in regions:
                if native.forecast_slot(datetime.fromisoformat(row["observedUtc"])) != slot:
                    raise ValueError("Weather slot differs from the timestamp-derived forecast")
                candidates[slot].append(row)
    if not all(candidates.values()):
        raise ValueError("Each slot needs at least one eligible training report")

    rows, sources = [], []
    labels_by_region = {}
    for (run, lead), reports in candidates.items():
        fields, source = native.load_fields(run, lead, domain)
        cores = native.jet_cores(fields, domain)
        matched = 0
        for row in reports:
            values = native.vector(
                fields,
                cores,
                float(row["latitude"]),
                float(row["longitude"]),
                int(row["pressureAltitudeFt"]),
                datetime.fromisoformat(row["observedUtc"]).month,
                domain,
            )
            if values is None or not all(math.isfinite(v) for v in values.values()):
                continue
            rows.append({**row, **values})
            labels_by_region.setdefault(row["region"], Counter())[row["reportedTurbulence"]] += 1
            matched += 1
        sources.append(
            {
                "run": run,
                "leadHours": lead,
                "eligible": len(reports),
                "matched": matched,
                "source": source,
            }
        )
    output.mkdir(parents=True, exist_ok=True)
    with (output / "pilot-weather-sample.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[*label_fields, *native.FEATURES])
        writer.writeheader()
        writer.writerows(rows)
    result = {
        "use": "Training partition only. Dates chosen for class diversity. Unsuitable for estimating prevalence or accuracy.",
        "labels": labels_by_region,
        "matched": len(rows),
        "sources": sources,
    }
    (output / "pilot-weather-sample.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--north-america", action="store_true", help="Use the North American training domain"
    )
    parser.add_argument("--slot", action="append", nargs=2, metavar=("RUN", "LEAD"), required=True)
    args = parser.parse_args()
    slots = [(run, int(lead)) for run, lead in args.slot]
    print(
        json.dumps(
            pair_sample(args.labels, slots, args.output, north_america=args.north_america)[
                "labels"
            ],
            indent=2,
        )
    )
