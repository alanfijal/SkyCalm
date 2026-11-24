"""Run the live baseline scorer on pinned, real GFS feature fields."""

import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from grid.compute import encode_features
from services.forecast.schema import LEADS, SCORER, tile_name
from services.forecast.storage import REPLAY_ROOT, validate_manifest
from services.pipeline.contract import REPLAYS

ROOT = Path(__file__).parent / "replay"


def rebuild(run_id: str, store) -> dict:
    if run_id not in REPLAYS:
        raise ValueError("No pinned input features for this run")
    frozen = ROOT / run_id
    manifest = validate_manifest(
        json.loads((REPLAY_ROOT / run_id / "manifest.json").read_bytes()), run_id
    )
    inputs = json.loads((frozen / "manifest.json").read_bytes())
    if (
        inputs["scorer"] != SCORER
        or inputs["runId"] != run_id
        or [i["lead"] for i in inputs["leads"]] != list(LEADS)
    ):
        raise ValueError("Invalid replay feature manifest")
    with TemporaryDirectory() as work:
        directory = Path(work)
        for spec, lead in zip(inputs["leads"], manifest["leads"], strict=True):
            path = frozen / f"f{lead['lead']:03}.npz"
            if hashlib.sha256(path.read_bytes()).hexdigest() != spec["featuresSha256"]:
                raise ValueError("Replay feature checksum mismatch")
            with np.load(path, allow_pickle=False) as cache:
                tile = encode_features(cache)
            if hashlib.sha256(gzip.decompress(tile)).hexdigest() != spec["gridSha256"]:
                raise ValueError("Recomputed grid differs from the archive")
            (directory / tile_name(lead["lead"])).write_bytes(tile)
            lead["sha256"] = hashlib.sha256(tile).hexdigest()
        (directory / "manifest.json").write_text(json.dumps(manifest) + "\n")
        store.publish(directory, manifest)
    return manifest
