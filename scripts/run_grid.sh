#!/usr/bin/env bash
# Run one explicitly dated weather job after the initial deployment is approved.
set -euo pipefail

run=${1:-}
if ! [[ "$run" =~ ^gfs-[0-9]{8}-(00|06|12|18)$ ]]; then
  echo "Usage: bash scripts/run_grid.sh gfs-YYYYMMDD-HH" >&2
  exit 2
fi

root=$(cd "$(dirname "$0")/.." && pwd)
bash "$root/scripts/check_aws.sh"
request=$(terraform -chdir="$root/infra/environments/dev" output -json grid_run_request)
cluster=$(jq -er '.cluster' <<< "$request")
aws_ecs=(aws ecs --region eu-north-1 --no-cli-pager)
active=$("${aws_ecs[@]}" list-tasks --cluster "$cluster" --desired-status RUNNING --query 'length(taskArns)' --output text)
if [[ "$active" != 0 ]]; then
  echo "Another grid task is active. Check it before starting a new run." >&2
  exit 1
fi
request=$(jq -c --arg run "$run" '.overrides = {containerOverrides: [{name:"grid",command:["--aws","--run",$run]}]}' <<< "$request")
result=$("${aws_ecs[@]}" run-task --cli-input-json "$request" --client-token "skycalm-dev-$run")
if ! jq -e '(.failures | length) == 0 and (.tasks | length) == 1' <<< "$result" > /dev/null; then
  jq -c '.failures' <<< "$result" >&2
  exit 1
fi
jq -r '.tasks[0].taskArn' <<< "$result"
