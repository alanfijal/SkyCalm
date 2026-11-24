#!/usr/bin/env bash
set -euo pipefail

expected=${TF_VAR_account_id:?Set TF_VAR_account_id to the approved AWS account ID}
if ! [[ "$expected" =~ ^[0-9]{12}$ ]]; then
  echo "Expected a 12-digit AWS account ID." >&2
  exit 2
fi
actual=$(aws sts get-caller-identity --region eu-north-1 --query Account --output text --no-cli-pager)
if [[ "$actual" != "$expected" ]]; then
  echo "AWS identity differs from the approved account. Stopping." >&2
  exit 1
fi
echo "Verified the approved AWS account for eu-north-1."
