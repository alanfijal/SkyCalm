"""Bounded byte-range reads from the public NOAA GFS bucket."""

import hashlib
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import urllib3

from services.forecast.schema import LEADS, LEVELS, issue_time

ORIGIN = "https://noaa-gfs-bdp-pds.s3.us-east-1.amazonaws.com"
FIELDS = {(name, f"{level} mb") for level in LEVELS for name in ("UGRD", "VGRD", "TMP", "HGT")}
FIELDS |= {("CAPE", "surface"), ("HGT", "surface")}
MAX_LEAD = 24 * 1024 * 1024
MAX_INDEX = 200_000


class NotReady(Exception):
    """NOAA has not published this product yet."""


class SourceError(Exception):
    """Invalid or incomplete source data."""


@dataclass(frozen=True)
class Record:
    field: str
    level: str
    start: int
    end: int


def url_for(run_id: str, lead: int) -> str:
    when = issue_time(run_id)
    if lead not in LEADS:
        raise ValueError("Unsupported forecast hour")
    return f"{ORIGIN}/gfs.{when:%Y%m%d}/{when:%H}/atmos/gfs.t{when:%H}z.pgrb2.0p25.f{lead:03}"


def select_records(index: str, size: int, *, fields=FIELDS, byte_limit=MAX_LEAD) -> list[Record]:
    lines = [line.split(":") for line in index.splitlines() if line.strip()]
    if not lines or any(len(row) < 6 for row in lines):
        raise SourceError("Invalid GRIB index")
    offsets = [int(row[1]) for row in lines] + [size]
    if offsets[0] != 0 or any(a >= b for a, b in zip(offsets, offsets[1:], strict=False)):
        raise SourceError("Invalid GRIB offsets")
    selected = [
        Record(row[3], row[4], offsets[i], offsets[i + 1] - 1)
        for i, row in enumerate(lines)
        if (row[3], row[4]) in fields
    ]
    if len(selected) != len(fields) or {(r.field, r.level) for r in selected} != fields:
        raise SourceError("Required weather fields are missing or duplicated")
    if sum(r.end - r.start + 1 for r in selected) > byte_limit:
        raise SourceError("Selected weather data exceeds the byte budget")
    return selected


class GfsSource:
    def __init__(self) -> None:
        self.http = urllib3.PoolManager(num_pools=1, maxsize=4, block=True)

    def get(
        self,
        url: str,
        *,
        method: str = "GET",
        limit: int = MAX_INDEX,
        span: tuple[int, int] | None = None,
        etag: str = "",
        size: int = 0,
    ) -> tuple[bytes, dict]:
        headers = {"User-Agent": "SkyCalm-university/1.0", "Accept-Encoding": "identity"}
        if span is not None:
            headers.update({"Range": f"bytes={span[0]}-{span[1]}", "If-Match": etag})
        for attempt in range(3):
            try:
                resp = self.http.request(
                    method,
                    url,
                    headers=headers,
                    preload_content=False,
                    timeout=urllib3.Timeout(connect=4, read=12),
                    retries=False,
                    redirect=False,
                )
                try:
                    if resp.status == 404:
                        raise NotReady(url)
                    if resp.status == 429 or resp.status >= 500:
                        raise OSError(f"Source status {resp.status}")
                    if resp.status != (206 if span is not None else 200):
                        raise SourceError(f"Unexpected weather response {resp.status}")
                    if (
                        span is not None
                        and resp.headers.get("Content-Range") != f"bytes {span[0]}-{span[1]}/{size}"
                    ):
                        raise SourceError("Source returned an incorrect byte range")
                    data = b"" if method == "HEAD" else resp.read(limit + 1, decode_content=False)
                    if len(data) > limit or (
                        span is not None and len(data) != span[1] - span[0] + 1
                    ):
                        raise SourceError("Unexpected weather payload size")
                    return data, dict(resp.headers)
                finally:
                    resp.close()
                    resp.release_conn()
            except (urllib3.exceptions.HTTPError, OSError) as exc:
                if attempt == 2:
                    raise SourceError(
                        "Weather source timed out or is temporarily unavailable"
                    ) from exc
                time.sleep(0.25 * 2**attempt + random.uniform(0, 0.15))
        raise AssertionError("unreachable")

    def latest(self, now: datetime | None = None) -> str:
        when = (now or datetime.now(UTC)).astimezone(UTC)
        cycle = when.replace(hour=when.hour // 6 * 6, minute=0, second=0, microsecond=0)
        for offset in range(4):
            run_id = (cycle - timedelta(hours=offset * 6)).strftime("gfs-%Y%m%d-%H")
            try:
                self.get(url_for(run_id, 36) + ".idx", method="HEAD")
                return run_id
            except NotReady:
                continue
        raise SourceError("No ready 36-hour forecast among the four most recent cycles")

    def fields(self, run_id: str, lead: int, *, fields=FIELDS, byte_limit=MAX_LEAD):
        url = url_for(run_id, lead)
        index, _ = self.get(url + ".idx")
        _, head = self.get(url, method="HEAD")
        headers = {k.lower(): v for k, v in head.items()}
        size, etag = int(headers["content-length"]), headers["etag"]
        records = select_records(index.decode("ascii"), size, fields=fields, byte_limit=byte_limit)
        digest = hashlib.sha256()
        total = 0
        for record in records:
            length = record.end - record.start + 1
            data, _ = self.get(
                url, limit=length, span=(record.start, record.end), etag=etag, size=size
            )
            digest.update(data)
            total += length
            yield record, data
        self.last_source = {
            "url": url,
            "etag": etag,
            "bytes": total,
            "messages": len(records),
            "indexSha256": hashlib.sha256(index).hexdigest(),
            "selectedSha256": digest.hexdigest(),
        }
