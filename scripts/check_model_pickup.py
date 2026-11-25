"""Exercise startup and batch inference with a real candidate and a local registry double."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from grid.model import add_predictions, load_approved
from services.forecast.api import respond
from services.forecast.schema import SCORER
from services.forecast.storage import REPLAY_ROOT, LocalStore
from services.pipeline.contract import demonstration_route

GROUP = "skycalm-turbulence"


class RegistryFixture:
    def __init__(self, version):
        self.version = version

    def list_model_packages(self, **params):
        assert params == {
            "ModelPackageGroupName": GROUP,
            "ModelPackageType": "Versioned",
            "ModelApprovalStatus": "Approved",
            "SortBy": "CreationTime",
            "SortOrder": "Descending",
            "MaxResults": 1,
        }
        return {"ModelPackageSummaryList": [{"ModelPackageArn": "fixture"}] if self.version else []}

    def describe_model_package(self, **params):
        assert params == {"ModelPackageName": "fixture"}
        return {
            "ModelPackageGroupName": GROUP,
            "ModelApprovalStatus": "Approved",
            "ModelPackageVersion": self.version,
            "InferenceSpecification": {
                "Containers": [
                    {"ModelDataUrl": "s3://fixture/ml/runs/local/train/output/model.tar.gz"}
                ]
            },
        }


class Artifact:
    bucket = "fixture"

    def __init__(self, path):
        self.path = path

    def read(self, key, limit):
        assert (
            key == "ml/runs/local/train/output/model.tar.gz" and self.path.stat().st_size <= limit
        )
        return self.path.read_bytes()


def verify(archive, preview_dir=None):
    artifact = Artifact(archive)
    assert load_approved(RegistryFixture(None), artifact, GROUP) is None
    candidate = load_approved(RegistryFixture(1), artifact, GROUP)
    later = load_approved(RegistryFixture(2), artifact, GROUP)
    assert candidate[1]["version"] == 1 and later[1]["version"] == 2
    run = "gfs-20261121-06"
    with TemporaryDirectory() as temp:
        import shutil

        output = Path(temp) / SCORER / run
        shutil.copytree(REPLAY_ROOT / run, output)
        manifest = json.loads((output / "manifest.json").read_bytes())
        add_predictions(output, manifest, candidate)
        (output / "manifest.json").write_text(json.dumps(manifest))
        route = respond("/api/forecast", demonstration_route(run), LocalStore(Path(temp)))
        learned = [p for p in route["samples"] if p["method"] == "lightgbm"]
        assert learned and route["modelVersion"] == 1
        assert all(0 <= p["probability"] <= 1 for p in learned)
        assert any(p.get("driver") for p in learned)
        item = manifest["leads"][0]
        blob = (output / "ml-000.gz").read_bytes()
        assert gzip.decompress(blob) and hashlib.sha256(blob).hexdigest() == item["modelSha256"]
        if preview_dir:
            LocalStore(preview_dir).publish(output, manifest)
        print(
            json.dumps(
                {
                    "fixtureRegistryVersions": [1, 2],
                    "routeSamples": len(route["samples"]),
                    "modelSamples": len(learned),
                    "exampleDriver": next(p["driver"] for p in learned if p.get("driver")),
                    "briefing": route["briefing"],
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--preview-dir", type=Path, help="Save the fixture grid for the local UI")
    args = parser.parse_args()
    verify(args.archive, args.preview_dir)
