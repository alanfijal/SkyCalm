"""Summarize Phase 7A label availability and count weather reads before ordering compute."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from grid.native import forecast_slot
from ml.holdout import partition
from ml.pireps import Report, audit_files
from services.forecast.schema import CATEGORIES, inside, utc_text


def counts(rows: list[Report]) -> dict:
    result = {
        region: {cohort: dict.fromkeys(CATEGORIES, 0) for cohort in ("cruise", "lower")}
        for region in ("europe", "north_atlantic")
    }
    for row in rows:
        result[row.region][row.cohort][row.label] += 1
    return result


def review(rows: list[Report], validation: date, test: date) -> dict:
    regional = [r for r in rows if r.region != "other"]
    temporal = [r for r in regional if r.time.date() >= test]
    split_rows: dict[str, list[Report]] = defaultdict(list)
    cycles: dict[str, set[str]] = defaultdict(set)
    for r in regional:
        side = partition(
            {"observed": utc_text(r.time), "lat": r.lat, "lon": r.lon}, validation, test
        )
        if side:
            split_rows[side].append(r)
            cycles[side].add(forecast_slot(r.time)[0])
    # A forecast used for training or validation cannot also feature in the independent test.
    held = [
        r
        for r in split_rows["test"]
        if forecast_slot(r.time)[0] not in cycles["train"] | cycles["validation"]
    ]
    slots = {forecast_slot(r.time) for r in regional}
    runs = len({run for run, _ in slots})
    # Estimate a wider research benchmark separately. Its geography is outside the passenger grid.
    box = [r for r in rows if 24 <= r.lat <= 72 and -170 <= r.lon < -60]
    study = regional + box
    assigned = defaultdict(list)
    for r in study:
        key = partition(
            {"observed": utc_text(r.time), "lat": r.lat, "lon": r.lon}, validation, test
        )
        if key:
            assigned[key].append(r)
    fitting_runs = {
        forecast_slot(r.time)[0] for key in ("train", "validation") for r in assigned[key]
    }
    study_test = [r for r in assigned["test"] if forecast_slot(r.time)[0] not in fitting_runs]
    research_slots = {forecast_slot(r.time) for r in study}
    fitting_sample = [
        r
        for side in ("train", "validation")
        for r in assigned[side]
        if r.region != "other"
        or int.from_bytes(
            hashlib.sha256(("skycalm-fit:" + forecast_slot(r.time)[0]).encode()).digest()[:4], "big"
        )
        % 8
        == 0
    ]
    # Preserve every independent test observation. Select fitting cycles without using severity.
    compact_slots = {forecast_slot(r.time) for r in regional + fitting_sample + study_test}

    def support(group):
        return {
            cohort: dict(Counter(r.label for r in group if r.cohort == cohort))
            for cohort in ("cruise", "lower")
        }

    return {
        "validationStart": str(validation),
        "testStart": str(test),
        "regions": counts(regional),
        "temporalTestBeforeSpatialHoldout": counts(temporal),
        "independentTest": counts(held),
        "insidePassengerGrid": counts([r for r in regional if inside(r.lat, r.lon)]),
        "distinctDays": {
            area: len({r.time.date() for r in regional if r.region == area})
            for area in ("europe", "north_atlantic")
        },
        "allRegionalReports": len(regional),
        "independentTestReports": len(held),
        "forecastCycles": runs,
        "forecastLeads": len(slots),
        "research": {
            "northAmericaBox": {"south": 24, "north": 72, "west": -170, "eastExclusive": -60},
            "northAmericaAll": support(box),
            "heldOutNorthAmerica": support([r for r in study_test if r.region == "other"]),
            "heldOutEuropeAndAtlantic": counts([r for r in study_test if r.region != "other"]),
            "allStudyTest": support(study_test),
            "chronologicalNorthAmerica": support([r for r in box if r.time.date() >= test]),
            "forecastCycles": len({run for run, _ in research_slots}),
            "forecastLeads": len(research_slots),
            "sampledStudy": {
                "forecastCycles": len({run for run, _ in compact_slots}),
                "forecastLeads": len(compact_slots),
                "fittingSupport": support(fitting_sample),
                "testSupport": support(study_test),
                "nonRegionalFittingFraction": "1/8 of cycles selected by a fixed SHA-256 rule",
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--validation", type=date.fromisoformat, required=True)
    parser.add_argument("--test", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows, audit = audit_files(args.files)
    data = review(rows, args.validation, args.test)
    args.output.write_text(json.dumps({"audit": audit, "review": data}, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: data[k]
                for k in (
                    "allRegionalReports",
                    "independentTestReports",
                    "forecastCycles",
                    "forecastLeads",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
