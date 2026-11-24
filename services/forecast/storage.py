"""Read immutable runs and atomically advance the latest complete local run."""

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

from services.forecast.schema import LEADS, SCORER, issue_time, tile_name

REPLAY_ROOT = Path(__file__).parent / "data" / "replay"


def validate_manifest(manifest: dict, run_id: str) -> dict:
    if (
        manifest["runId"] != run_id
        or manifest["scorer"] != SCORER
        or [x["lead"] for x in manifest["leads"]] != list(LEADS)
    ):
        raise ValueError("Weather manifest is incompatible or incomplete")
    return manifest


def checked_tile(data: bytes, digest: str) -> bytes:
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Weather tile checksum mismatch")
    return data


@lru_cache(maxsize=48)
def read_tile(path: Path, digest: str) -> bytes:
    return checked_tile(path.read_bytes(), digest)


class LocalStore:
    def __init__(self, root: Path, replay_root: Path | None = None):
        self.root = root
        self.replay_root = replay_root

    def location(self, run_id: str) -> Path:
        issue_time(run_id)
        local = self.root / SCORER / run_id
        if self.replay_root and not local.is_dir():
            return self.replay_root / run_id
        return local

    def manifest(self, run_id: str) -> dict | None:
        path = self.location(run_id) / "manifest.json"
        try:
            return validate_manifest(json.loads(path.read_bytes()), run_id)
        except FileNotFoundError:
            return None

    def latest(self) -> str | None:
        try:
            return (self.root / SCORER / "latest").read_text().strip()
        except FileNotFoundError:
            return None

    def replays(self) -> list[str]:
        if not self.replay_root:
            return []
        return sorted(
            (m.parent.name for m in self.replay_root.glob("gfs-*/manifest.json")), reverse=True
        )

    def tile(self, run_id: str, lead: int, digest: str) -> bytes:
        return read_tile(self.location(run_id) / tile_name(lead), digest)

    def advance(self, run_id: str) -> None:
        if not self.manifest(run_id):
            raise ValueError("Incomplete weather run")
        parent = self.root / SCORER
        parent.mkdir(parents=True, exist_ok=True)
        with (parent / ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = self.latest()
            if current is None or run_id > current:
                pending = parent / "latest.tmp"
                pending.write_text(run_id)
                os.replace(pending, parent / "latest")

    def publish(self, directory: Path, manifest: dict) -> None:
        run_id = manifest["runId"]
        issue_time(run_id)
        validate_manifest(manifest, run_id)
        parent = self.root / SCORER
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / run_id
        with tempfile.TemporaryDirectory(dir=parent) as temp:
            complete = Path(temp) / "complete"
            shutil.copytree(directory, complete)
            for item in manifest["leads"]:
                checked_tile((complete / tile_name(item["lead"])).read_bytes(), item["sha256"])
            with (parent / ".lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if target.exists():
                    if self.manifest(run_id) != manifest:
                        raise ValueError("This run already has a different manifest")
                else:
                    complete.rename(target)
        self.advance(run_id)
