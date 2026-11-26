"""Measure primary mobile entry points against a locally served production build."""

import argparse
import json
import os
import statistics
import subprocess
from pathlib import Path

PAGES = {
    "welcome": "/",
    "forecast": "/forecast",
    "replay": "/replay",
    "recordings": "/recordings",
    "history": "/history",
    "flights": "/flights",
}
CATEGORIES = ("performance", "accessibility")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:4173")
    parser.add_argument("--output", type=Path, default=Path(".local/mobile-audit"))
    parser.add_argument("--runs", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    binary = os.environ.get("SKYCALM_LIGHTHOUSE_CLI")
    command = ["node", binary] if binary else ["npx", "--yes", "lighthouse@12.8.2"]
    result = {}
    for name, route in PAGES.items():
        scores = {key: [] for key in CATEGORIES}
        for number in range(args.runs):
            path = args.output / f"{name}-{number + 1}.json"
            subprocess.run(
                [
                    *command,
                    args.origin.rstrip("/") + route,
                    "--quiet",
                    "--form-factor=mobile",
                    "--only-categories=performance,accessibility",
                    "--output=json",
                    "--chrome-flags=--headless --no-first-run --disable-dev-shm-usage",
                    "--output-path=" + str(path.resolve()),
                ],
                check=True,
                timeout=150,
            )
            report = json.loads(path.read_bytes())
            if report.get("runtimeError") or report["lighthouseVersion"] != "12.8.2":
                raise RuntimeError(f"Unexpected Lighthouse result: {path}")
            for key in CATEGORIES:
                scores[key].append(round(100 * report["categories"][key]["score"]))
        result[name] = {
            key: {"runs": values, "median": statistics.median(values)}
            for key, values in scores.items()
        }
        print(name, result[name], flush=True)
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return int(any(data["median"] < 90 for page in result.values() for data in page.values()))


if __name__ == "__main__":
    raise SystemExit(main())
