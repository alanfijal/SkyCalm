"""Write the presentation report from an actual evaluation artifact."""

import argparse
import json
from pathlib import Path

from services.forecast.schema import CATEGORIES


def report(evidence):
    lines = [
        "# Turbulence model evaluation",
        "",
        "The candidate uses class-weighted LightGBM. The benchmark applies the published Ellrod thresholds at the matched pressure level.",
        "",
        "| Split | Reports | First observation (UTC) | Last observation (UTC) |",
        "| --- | ---: | --- | --- |",
    ]
    for name, s in evidence["dataset"]["splits"].items():
        lines.append(f"| {name} | {s['rows']} | {s['first']} | {s['last']} |")
    lines += [
        "",
        f"Forecast-cycle overlap excluded {evidence['dataset']['splitOverlapDropped']} additional reports.",
        "Only point aircraft reports with an explicit intensity and a pressure level within 1 km entered the dataset. Weather advisories were excluded. An unspecified intensity provides no training label. Forecast issue time precedes each report. Historical publication latency is unknown.",
        "",
        "| Held-out sector | Reports | Model macro F1 | Baseline macro F1 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, s in evidence["sectors"].items():
        scores = [
            "—" if s[m]["macroF1"] is None else f"{s[m]['macroF1']:.3f}"
            for m in ("model", "baseline")
        ]
        lines.append(
            f"| {name.replace('_', ' ')} | {s['model']['rows']} | {scores[0]} | {scores[1]} |"
        )
    lines += [
        "",
        "The North Atlantic sector covers the part of the grid west of 12°W. Macro F1 gives all four categories equal weight, including absent classes with zero F1.",
        "",
        "| Test class | Support | Model precision | Model recall | Baseline recall |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    all_scores = evidence["sectors"]["all"]
    for name in CATEGORIES:
        c = all_scores["model"]["classes"][name]
        values = [c["precision"], c["recall"], all_scores["baseline"]["classes"][name]["recall"]]
        lines.append(
            f"| {name} | {c['support']} | "
            + " | ".join("—" if v is None else f"{v:.3f}" for v in values)
            + " |"
        )
    lines += ["", f"**Registry decision from evaluation**  `{evidence['approval']['status']}`.", ""]
    lines += ["- " + reason for reason in evidence["approval"]["reasons"]]
    lines += [
        "",
        "Reports cluster along flown routes and overrepresent bumps. The archive retains Ellrod index, shear, derived deformation, CAPE, terrain and pressure-level heights. Latitude and month complete the eight inputs. The current archive lacks wind speed, lapse rate and Richardson number.",
        "The full evaluation JSON contains the confusion matrices and reliability-bin counts for both methods. The small sample limits any inference about calibration or severe events.",
        "",
        "An independent, geographically broader archive with explicit smooth and severe encounters is needed before promotion. The production grid selects only approved registry versions at task start.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(report(json.loads(args.evidence.read_bytes())))
