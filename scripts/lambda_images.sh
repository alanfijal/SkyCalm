#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
revision=$(git rev-parse HEAD)
region=eu-north-1
account=028718095604
registry="$account.dkr.ecr.$region.amazonaws.com"
case "${1:-build}" in
  build)
    if [[ -n "$(git status --porcelain)" ]]; then revision="$revision-dirty"; fi
    docker buildx build --platform linux/arm64 --provenance=false --sbom=false \
      --label "org.opencontainers.image.revision=$revision" --load --target python \
      -f services/Dockerfile -t "skycalm-python:local" .
    ;;
  publish)
    [[ -z "$(git status --porcelain)" ]] || { echo "Commit the release before publishing." >&2; exit 1; }
    [[ "$(aws sts get-caller-identity --region "$region" --query Account --output text)" == "$account" ]]
    built=$(docker inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "skycalm-python:local")
    [[ "$built" == "$revision" ]] || { echo "Build and test the current commit first." >&2; exit 1; }
    aws ecr get-login-password --region "$region" | docker login -u AWS --password-stdin "$registry"
    mkdir -p build
    tag="python-$revision"
    ref="$registry/skycalm/functions:$tag"
    docker tag "skycalm-python:local" "$ref"
    docker push "$ref"
    aws ecr describe-images --region "$region" --repository-name skycalm/functions \
      --image-ids "imageTag=$tag" --query 'imageDetails[0]' --output json > "build/python-manifest.json"
    python3 - <<'PY'
import json
from pathlib import Path

image = json.loads(Path("build/python-manifest.json").read_bytes())
if image["imageManifestMediaType"] not in (
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
):
    raise SystemExit("The Python image must use a single-architecture manifest")
settings = {"lambda_image_digests": {"python": image["imageDigest"]}}
Path("build/lambda-images.tfvars.json").write_text(json.dumps(settings) + "\n")
PY
    ;;
  *) echo "Usage: bash scripts/lambda_images.sh [build|publish]" >&2; exit 2 ;;
esac
