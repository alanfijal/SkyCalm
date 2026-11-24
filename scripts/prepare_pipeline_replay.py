"""Freeze the weather features and prove that they reproduce each archived grid."""

import argparse
import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from grid.compute import decode, encode_features, features
from grid.source import GfsSource
from services.forecast.schema import LEADS, issue_time, tile_name
from services.forecast.storage import REPLAY_ROOT, validate_manifest

FEATURES = Path(__file__).resolve().parents[1] / "grid/replay"


def prepare(run: str, output: Path = FEATURES) -> None:
    issue_time(run)
    archived = REPLAY_ROOT / run
    manifest = validate_manifest(json.loads((archived / "manifest.json").read_bytes()), run)
    output.mkdir(parents=True, exist_ok=True)

    def capture(lead, stage):
        source = GfsSource()
        try:
            fields = {
                (r.field, r.level): decode(body, r, run, lead)
                for r, body in source.fields(run, lead)
            }
        finally:
            source.http.clear()
        data = features(fields)
        tile = (archived / tile_name(lead)).read_bytes()
        expected = manifest["leads"][LEADS.index(lead)]
        if hashlib.sha256(tile).hexdigest() != expected["sha256"] or gzip.decompress(
            encode_features(data)
        ) != gzip.decompress(tile):
            raise ValueError(f"Archived weather differs at {run} f{lead:03}")
        path = stage / f"f{lead:03}.npz"
        np.savez_compressed(path, **data)
        return {
            "lead": lead,
            "featuresSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "gridSha256": hashlib.sha256(gzip.decompress(tile)).hexdigest(),
        }

    with TemporaryDirectory(dir=output) as work:
        stage = Path(work) / run
        stage.mkdir()
        with ThreadPoolExecutor(max_workers=3) as pool:
            leads = list(pool.map(lambda lead: capture(lead, stage), LEADS))
        (stage / "manifest.json").write_text(
            json.dumps({"runId": run, "scorer": manifest["scorer"], "leads": leads}, indent=2)
            + "\n"
        )
        dest = output / run
        if dest.exists():
            if (stage / "manifest.json").read_bytes() != (dest / "manifest.json").read_bytes():
                raise ValueError("Existing replay inputs differ")
        else:
            stage.rename(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    args = parser.parse_args()
    prepare(args.run)
