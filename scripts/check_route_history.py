"""Run one bounded Athena check and compare its result with the passenger archive."""

import argparse
import hashlib
import json
import os
import subprocess
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUP = "skycalm-dev-weather"
DATABASE = "skycalm_dev_weather"
LIMIT = 10 * 1024 * 1024


def expected(rows):
    counts = defaultdict(lambda: [0, 0])
    for row in rows:
        key = (row["origin"], row["destination"], row["departure"][:7], row["peak"])
        counts[key][0] += 1
        counts[key][1] += row["report_count"]
    return {key: tuple(value) for key, value in counts.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True, help="Expected 12-digit AWS account")
    parser.add_argument("--profile", default="coldchain-console")
    parser.add_argument("--check-id", required=True, help="Stable rehearsal or release identifier")
    args = parser.parse_args()

    def aws(*command):
        result = subprocess.check_output(
            [
                "aws",
                "--profile",
                args.profile,
                "--region",
                "eu-north-1",
                *command,
                "--output",
                "json",
            ],
            env=os.environ | {"AWS_PAGER": ""},
        )
        return json.loads(result) if result else {}

    if aws("sts", "get-caller-identity")["Account"] != args.account:
        raise SystemExit("AWS account mismatch")
    config = aws("athena", "get-work-group", "--work-group", GROUP)["WorkGroup"]["Configuration"]
    if (
        not config["EnforceWorkGroupConfiguration"]
        or not 0 < config.get("BytesScannedCutoffPerQuery", 0) <= LIMIT
    ):
        raise SystemExit("The query needs an enforced scan limit of at most 10 MiB")
    query = (ROOT / "analytics/route_summary.sql").read_text()
    token = hashlib.sha256((GROUP + query + args.check_id).encode()).hexdigest()
    query_id = aws(
        "athena",
        "start-query-execution",
        "--work-group",
        GROUP,
        "--query-execution-context",
        "Database=" + DATABASE,
        "--query-string",
        query,
        "--client-request-token",
        token,
    )["QueryExecutionId"]
    for _ in range(30):
        run = aws("athena", "get-query-execution", "--query-execution-id", query_id)[
            "QueryExecution"
        ]
        state = run["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in {"FAILED", "CANCELLED"}:
            raise SystemExit(f"{query_id}: {state}. See the execution in Athena.")
        time.sleep(1)
    else:
        aws("athena", "stop-query-execution", "--query-execution-id", query_id)
        raise SystemExit("Query timed out and cancellation was requested")
    records = aws("athena", "get-query-results", "--query-execution-id", query_id)["ResultSet"][
        "Rows"
    ]
    values = ([c["VarCharValue"] for c in row["Data"]] for row in records[1:])
    observed = {
        (a, b, month, peak): (int(days), int(reports))
        for a, b, month, peak, days, reports in values
    }
    path = ROOT / "web/public/data/route-history/days.jsonl"
    baseline = expected(json.loads(line) for line in path.read_text().splitlines())
    if baseline != observed or len(records) != len(baseline) + 1:
        raise SystemExit("Athena differs from the passenger archive")
    print(
        json.dumps(
            {
                "queryId": query_id,
                "scannedBytes": run["Statistics"]["DataScannedInBytes"],
                "departures": sum(n for n, _ in observed.values()),
                "reportMatches": sum(n for _, n in observed.values()),
            }
        )
    )


if __name__ == "__main__":
    main()
