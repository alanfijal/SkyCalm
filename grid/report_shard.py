"""Plan native NOAA matches offline and process exactly one historical forecast cycle."""

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from grid.native import FEATURES, forecast_slot, jet_cores, load_fields, vector
from ml.pireps import Report, audit_files
from services.forecast.schema import issue_time, utc_text

SCHEMA = "gfs-native-report-v2.1"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            json.dump(data, stream, allow_nan=False, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    os.replace(tmp, path)


def plan(rows: list[Report], directory: Path) -> tuple[int, int]:
    jobs: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.region == "other":
            continue
        run, lead = forecast_slot(row.time)
        jobs[run].append(
            {
                "id": row.key,
                "observed": utc_text(row.time),
                "lead": lead,
                "lat": row.lat,
                "lon": row.lon,
                "feet": row.feet,
                "aircraft": row.aircraft,
                "cohort": row.cohort,
                "sector": row.region,
                "label": row.label,
            }
        )
    leads = 0
    for run, encounters in sorted(jobs.items()):
        write_json(
            directory / f"{run}.json", {"schema": SCHEMA, "run": run, "encounters": encounters}
        )
        leads += len({r["lead"] for r in encounters})
    return len(jobs), leads


def process(source: Path, output: Path, *, load=load_fields) -> dict:
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    job = json.loads(payload)
    run = job["run"]
    issued = issue_time(run)
    encounters = job["encounters"]
    if job.get("schema") != SCHEMA or not 1 <= len(encounters) <= 4000:
        raise ValueError("Invalid native point job")
    by_lead: dict[int, list[dict]] = defaultdict(list)
    for row in encounters:
        expected = forecast_slot(datetime.fromisoformat(row["observed"]))
        if expected != (run, row["lead"]) or row["lead"] not in (6, 9, 12):
            raise ValueError("Encounter does not belong to this forecast cycle and lead")
        by_lead[row["lead"]].append(row)
    target = output / f"{run}-{digest}.json"
    if target.exists():
        old = json.loads(target.read_bytes())
        if old.get("schema") != SCHEMA or old.get("inputSha256") != digest or old.get("run") != run:
            raise ValueError("Invalid existing native shard")
        return old
    rows, evidence, rejected = [], [], Counter()
    for lead, reports in sorted(by_lead.items()):
        fields, metadata = load(run, lead)
        cores = jet_cores(fields)
        for report in reports:
            features = vector(
                fields,
                cores,
                report["lat"],
                report["lon"],
                report["feet"],
                (issued + timedelta(hours=lead)).month,
            )
            if features is None:
                rejected["outside_valid_pressure_level"] += 1
                continue
            if not all(math.isfinite(features[name]) for name in FEATURES[:8]):
                rejected["missing_baseline_fields"] += 1
                continue
            rows.append(
                report
                | {
                    "gridStep": 0.25,
                    "run": run,
                    "features": {k: v if math.isfinite(v) else None for k, v in features.items()},
                }
            )
        evidence.append({"lead": lead, **metadata})
    result = {
        "schema": SCHEMA,
        "run": run,
        "inputSha256": digest,
        "sources": evidence,
        "rows": rows,
        "excluded": dict(rejected),
    }
    write_json(target, result)
    return result


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    subs = args.add_subparsers(dest="mode", required=True)
    make = subs.add_parser("plan", help="Create per-cycle manifests without fetching weather")
    make.add_argument("files", nargs="+", type=Path)
    make.add_argument("--output", type=Path, required=True)
    work = subs.add_parser("process", help="Download only the selected leads from one NOAA cycle")
    work.add_argument("--input", required=True, type=Path)
    work.add_argument("--output", type=Path, required=True)
    options = args.parse_args()
    if options.mode == "plan":
        rows, _ = audit_files(options.files)
        runs, leads = plan(rows, options.output)
        print(json.dumps({"event": "native.plan.ready", "runs": runs, "leads": leads}))
    else:
        shard = process(options.input, options.output)
        print(
            json.dumps(
                {
                    "event": "native.shard.ready",
                    "run": shard["run"],
                    "rows": len(shard["rows"]),
                    "inputSha256": shard["inputSha256"],
                }
            )
        )


if __name__ == "__main__":
    main()
