"""Reproduce the two GFS cruise wind overlays from the original archived object revisions."""

import hashlib
import json
from pathlib import Path

from grid.compute import cruise_wind, decode
from grid.source import GfsSource, select_records, url_for
from services.forecast.storage import REPLAY_ROOT

DESTINATION = Path(__file__).resolve().parents[1] / "web/public/data/wind"


def archive(run: str) -> None:
    manifest = json.loads((REPLAY_ROOT / run / "manifest.json").read_bytes())
    source = GfsSource()
    frames = []
    try:
        for entry in manifest["leads"]:
            lead = entry["lead"]
            url = url_for(run, lead)
            index, _ = source.get(url + ".idx")
            _, head = source.get(url, method="HEAD")
            metadata = {k.lower(): v for k, v in head.items()}
            if (
                metadata["etag"] != entry["etag"]
                or hashlib.sha256(index).hexdigest() != entry["indexSha256"]
            ):
                raise ValueError(f"Source revision changed at {run} +{lead}")
            size = int(metadata["content-length"])
            fields = {}
            for record in select_records(index.decode("ascii"), size):
                if record.level == "250 mb" and record.field in {"UGRD", "VGRD"}:
                    length = record.end - record.start + 1
                    if length > 2_000_000:
                        raise ValueError("Wind message exceeds the archive byte allowance")
                    data, _ = source.get(
                        url,
                        limit=length,
                        span=(record.start, record.end),
                        etag=entry["etag"],
                        size=size,
                    )
                    fields[record.field, record.level] = decode(data, record, run, lead)
            frames.append(cruise_wind(fields))
    finally:
        source.http.clear()
    DESTINATION.mkdir(parents=True, exist_ok=True)
    (DESTINATION / (run + ".json")).write_text(json.dumps(frames, separators=(",", ":")) + "\n")
    print(f"{run}: {len(frames)} verified 250 hPa wind grids", flush=True)


if __name__ == "__main__":
    for cycle in ("gfs-20261124-12", "gfs-20261121-06"):
        archive(cycle)
