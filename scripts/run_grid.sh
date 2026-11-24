#!/usr/bin/env bash
# Submit one dated weather run through the same admission queue as NOAA discovery.
set -euo pipefail

run=${1:-}
if ! [[ "$run" =~ ^gfs-[0-9]{8}-(00|06|12|18)$ ]]; then
  echo "Usage: bash scripts/run_grid.sh gfs-YYYYMMDD-HH" >&2
  exit 2
fi

root=$(cd "$(dirname "$0")/.." && pwd)
bash "$root/scripts/check_aws.sh"
pipeline=skycalm-dev-pipeline
job_id="live-$run"
entries=$(jq -cn --arg run "$run" --arg job "$job_id" --arg bus "$pipeline" '
  [{EventBusName: $bus, Source: "skycalm.forecast", DetailType: "forecast.run.available",
    Detail: ({mode: "live", runId: $run, jobId: $job} | tojson)}]')
result=$(aws events put-events --entries "$entries" --region eu-north-1 --output json --no-cli-pager)
if ! jq -e '.FailedEntryCount == 0 and (.Entries[0].EventId | type == "string" and length > 0)' <<< "$result" > /dev/null; then
  jq -c '.Entries' <<< "$result" >&2
  exit 1
fi
printf 'arn:aws:states:eu-north-1:%s:execution:%s:%s\n' "$TF_VAR_account_id" "$pipeline" "$job_id"
