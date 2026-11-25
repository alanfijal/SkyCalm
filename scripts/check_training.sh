#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
directory=$(mktemp -d "${TMPDIR:-/tmp}/skycalm-training.XXXXXXXX")
mkdir -p "$directory"/{dataset,trained,model,metrics}
runtime=(docker run --rm --platform linux/amd64 --network none --read-only --tmpfs /tmp)
image=${1:-skycalm-training:local}
"${runtime[@]}" -v "$PWD/services/forecast/data/observations:/opt/ml/processing/observations:ro" \
  -v "$PWD/services/forecast/data/replay:/opt/ml/processing/grids:ro" \
  -v "$directory/dataset:/opt/ml/processing/dataset" "$image" prepare
"${runtime[@]}" -v "$directory/dataset:/opt/ml/input/data/training:ro" \
  -v "$directory/trained:/opt/ml/model" "$image" train
tar -czf "$directory/model/model.tar.gz" -C "$directory/trained" model.txt model.json
"${runtime[@]}" --tmpfs /opt/ml/processing/unpacked -v "$directory/dataset:/opt/ml/processing/dataset:ro" \
  -v "$directory/model:/opt/ml/processing/model:ro" -v "$directory/metrics:/opt/ml/processing/metrics" "$image" evaluate
if [[ -n "${CHECK_GRID_IMAGE:-}" ]]; then
  mkdir -p "$directory/preview"
  "${runtime[@]}" -v "$PWD:/work:ro" -w /work -v "$directory/model/model.tar.gz:/model.tar.gz:ro" \
    -v "$directory/preview:/preview" --entrypoint python "$CHECK_GRID_IMAGE" \
    -m scripts.check_model_pickup /model.tar.gz --preview-dir /preview
fi
python3 -m ml.report "$directory/metrics/evaluation.json" "$directory/report.md"
printf 'Evaluation and report saved in %s\n' "$directory"
