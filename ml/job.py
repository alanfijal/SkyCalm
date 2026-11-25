"""Container entry points for SageMaker Training and Processing."""

import json
import sys
from pathlib import Path

from ml.artifact import read_artifact


def unpack_model(archive, output):
    output.mkdir(parents=True, exist_ok=True)
    with archive.open("rb") as source:
        text, metadata = read_artifact(source)
    (output / "model.txt").write_bytes(text)
    (output / "model.json").write_bytes(metadata)


def main():
    root = Path("/opt/ml/processing")
    mode = sys.argv[1]
    if mode == "prepare":
        from ml.prepare import prepare

        prepare(root / "observations", root / "grids", root / "dataset")
    elif mode == "train":
        from ml.train import train

        options = Path("/opt/ml/input/config/hyperparameters.json")
        params = json.loads(options.read_bytes()) if options.is_file() else {}
        train(
            Path("/opt/ml/input/data/training"),
            Path("/opt/ml/model"),
            int(params.get("rounds", 40)),
        )
    elif mode == "evaluate":
        from ml.evaluate import evaluate

        model = root / "unpacked"
        unpack_model(root / "model/model.tar.gz", model)
        evaluate(root / "dataset", model, root / "metrics")
    else:
        raise SystemExit("Use prepare, train or evaluate")


if __name__ == "__main__":
    main()
