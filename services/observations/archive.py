"""Store complete snapshots before advancing the latest pointer."""

import fcntl
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path

from services.forecast.schema import issue_time

ARCHIVE = Path(__file__).resolve().parents[1] / "forecast/data/observations"


def public_map(snapshot: dict) -> dict:
    return {
        **snapshot,
        "items": [
            item
            for item in snapshot["items"]
            if item["kind"] == "sigmet" or item["intensity"] != "unreported"
        ],
    }


def encoded(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()


def objects(snapshot: dict, raw: dict) -> tuple[str, dict[str, bytes]]:
    date, time = snapshot["asOf"].split("T")
    stamp = date + "-" + time[:5].replace(":", "")
    body = encoded(snapshot)
    version = stamp + "-" + hashlib.sha256(body).hexdigest()[:12]
    history = b"".join(
        encoded(
            {
                "id": item["id"],
                "kind": item["kind"],
                "source": item["source"],
                "intensity": item["intensity"],
                "observed": item["from"],
                "expires": item["to"],
                "base_ft": item["baseFt"],
                "top_ft": item["topFt"],
            }
        )
        + b"\n"
        for item in snapshot["items"]
    )
    original = encoded(raw)
    batch = hashlib.sha256(original).hexdigest()[:16]
    return version, {
        f"observations/raw/day={date}/{stamp}-{batch}.json.gz": gzip.compress(original, mtime=0),
        f"observations/history/day={date}/{version}.json.gz": gzip.compress(history, mtime=0),
        f"observations/snapshots/{version}.json": encoded(public_map(snapshot)),
    }


def replay(run: str) -> dict | None:
    issue_time(run)
    path = ARCHIVE / (run + ".json")
    return json.loads(path.read_bytes()) if path.is_file() else None


def atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        name = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            name.unlink(missing_ok=True)
            raise
    try:
        os.replace(name, path)
    finally:
        name.unlink(missing_ok=True)


def publish_local(root: Path, snapshot: dict, raw: dict, *, live: bool = True) -> str:
    version, keys = objects(snapshot, raw)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".observations.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for key, body in keys.items():
            atomic(root / key, body)
        head = root / "observations/latest.json"
        if live and (not head.exists() or json.loads(head.read_bytes())["asOf"] < snapshot["asOf"]):
            atomic(head, encoded({"asOf": snapshot["asOf"], "version": version}))
    return version


def local_latest(root: Path) -> dict | None:
    try:
        head = json.loads((root / "observations/latest.json").read_bytes())
        return json.loads(
            (root / "observations/snapshots" / (head["version"] + ".json")).read_bytes()
        )
    except FileNotFoundError:
        return None
