import hashlib
from datetime import UTC, datetime

import numpy as np
import pytest

from grid.compute import STEP, diagnostics
from grid.source import FIELDS, GfsSource, NotReady, SourceError, select_records
from services.forecast.schema import LEADS, SCORER, tile_name
from services.forecast.storage import LocalStore


def test_index_selects_required_fields_and_uses_file_size_for_last_record() -> None:
    fields = [("RH", "surface"), *sorted(FIELDS)]
    idx = "\n".join(
        f"{i + 1}:{i * 10}:d=2026112412:{f}:{level}:anl:" for i, (f, level) in enumerate(fields)
    )
    selected = select_records(idx, len(fields) * 10 + 7)
    assert len(selected) == 22
    assert selected[0].start == 10
    assert selected[-1].end == len(fields) * 10 + 6
    with pytest.raises(SourceError):
        select_records(idx.rsplit("\n", 1)[0], len(fields) * 10)


def test_ti1_uses_height_and_physical_horizontal_distance() -> None:
    lat = np.array([49.75, 50.0, 50.25])
    dy = 6_371_000 * np.radians(STEP)
    dx = dy * np.cos(np.radians(50))
    z = np.broadcast_to(np.array([7000, 9000, 11000])[:, None, None], (3, 3, 3))
    u = np.broadcast_to(z * 0.004 + np.arange(3)[None, None, :] * dx * 1e-4, (3, 3, 3))
    ti, shear = diagnostics(u, np.zeros_like(u), z, lat)
    assert shear[1, 1, 1] == pytest.approx(4)
    assert ti[1, 1, 1] == pytest.approx(4)
    calm, _ = diagnostics(np.zeros_like(u), np.zeros_like(u), z, lat)
    assert (calm == 0).all()


def test_latest_steps_back_from_incomplete_cycle(monkeypatch) -> None:
    calls = []

    def get(self, url, **kwargs):
        calls.append(url)
        if ".t18z." in url:
            raise NotReady
        return b"", {}

    monkeypatch.setattr(GfsSource, "get", get)
    assert GfsSource().latest(datetime(2026, 11, 24, 19, tzinfo=UTC)) == "gfs-20261124-12"
    assert len(calls) == 2


def test_source_refuses_full_response_to_a_range_before_reading() -> None:
    class FullResponse:
        status = 200

        def read(self, *args, **kwargs):
            pytest.fail("An unrequested full download was attempted")

        def close(self):
            pass

        def release_conn(self):
            pass

    class Pool:
        def request(self, *args, **kwargs):
            return FullResponse()

    source = GfsSource()
    source.http = Pool()
    with pytest.raises(SourceError, match="200"):
        source.get("https://example.invalid", span=(1, 10), size=100, etag="fixture")


def test_incomplete_run_never_replaces_latest_and_old_run_cannot_regress_it(tmp_path) -> None:
    import json

    staging = tmp_path / "staging"
    staging.mkdir()
    store = LocalStore(tmp_path / "published")
    leads = [{"lead": h, "sha256": hashlib.sha256(bytes([h])).hexdigest()} for h in LEADS]

    def manifest(run_id):
        return {"runId": run_id, "scorer": SCORER, "leads": leads}

    def put(run_id):
        doc = manifest(run_id)
        (staging / "manifest.json").write_text(json.dumps(doc))
        store.publish(staging, doc)

    for h in LEADS:
        (staging / tile_name(h)).write_bytes(bytes([h]))
    put("gfs-20261124-12")
    put("gfs-20261124-06")
    assert store.latest() == "gfs-20261124-12"
    (staging / tile_name(9)).write_bytes(b"broken")
    with pytest.raises(ValueError, match="checksum"):
        put("gfs-20261124-18")
    assert store.latest() == "gfs-20261124-12"
    assert store.manifest("gfs-20261124-18") is None
