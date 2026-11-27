"""Export the audited pilot-report cruise labels with the existing time and geography split."""

import argparse
import csv
import gzip
import io
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from grid.native import forecast_slot
from ml.holdout import partition
from ml.pireps import audit_files
from services.forecast.schema import utc_text


def export(directory, review_path, output):
    review = json.loads(review_path.read_bytes())
    reports, audit = audit_files(directory.glob("*.csv"))
    if audit["sources"] != review["audit"]["sources"]:
        raise ValueError("The source files differ from the audited census")
    validation, test = (
        date.fromisoformat(review["review"][k]) for k in ("validationStart", "testStart")
    )
    assigned = []
    cycles = defaultdict(set)
    for report in reports:
        region = report.region
        if region == "other":
            if not (24 <= report.lat <= 72 and -170 <= report.lon < -60):
                continue
            region = "north_america"
        observed = utc_text(report.time)
        split = partition(
            {"observed": observed, "lat": report.lat, "lon": report.lon}, validation, test
        )
        run, lead = forecast_slot(report.time)
        if split:
            cycles[split].add(run)
        if report.cohort == "cruise":
            assigned.append((report, region, observed, split or "excluded", run, lead))
    output.mkdir(parents=True, exist_ok=True)
    counts, by_split = defaultdict(Counter), defaultdict(Counter)
    with (
        (output / "cruise-labels.csv.gz").open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped,
        io.TextIOWrapper(zipped, newline="") as stream,
    ):
        writer = csv.writer(stream)
        writer.writerow(
            [
                "reportId",
                "observedUtc",
                "latitude",
                "longitude",
                "pressureAltitudeFt",
                "aircraftType",
                "region",
                "reportedTurbulence",
                "split",
                "forecastCycle",
                "forecastLeadHours",
            ]
        )
        for r, region, observed, split, run, lead in assigned:
            if (split == "validation" and run in cycles["train"]) or (
                split == "test" and (run in cycles["train"] or run in cycles["validation"])
            ):
                split = "excluded"
            writer.writerow(
                [
                    r.key,
                    observed,
                    r.lat,
                    r.lon,
                    r.feet,
                    r.aircraft,
                    region,
                    r.label,
                    split,
                    run,
                    lead,
                ]
            )
            counts[region][r.label] += 1
            by_split[region][split] += 1
    result = {
        "labels": dict(counts),
        "split": dict(by_split),
        "sources": audit["sources"],
        "validationStart": validation.isoformat(),
        "testStart": test.isoformat(),
        "note": "Labels only. The forecast cycle and lead are lookup keys for historical weather. Keep excluded rows out of fitting and evaluation.",
    }
    (output / "pilot-census.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.months, args.review, args.output)["labels"], indent=2))
