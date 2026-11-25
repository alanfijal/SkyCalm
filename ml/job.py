"""Container entry points for SageMaker Training and Processing."""

import json
import sys
import tarfile
from pathlib import Path


def unpack_model(archive, output):
    output.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        for name in ("model.txt", "model.json"):
            member = tar.getmember(name)
            if not member.isfile() or not 0 < member.size <= 5_000_000:
                raise ValueError("Invalid model artifact")
            with tar.extractfile(member) as src:
                (output / name).write_bytes(src.read(member.size))


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
