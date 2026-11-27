"""Fetch complete UTC calendar months from IEM or audit an existing set of CSV files."""

import argparse
import gzip
import hashlib
import json
import os
import random
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ml.pireps import audit_files, csv_header

IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/gis/pireps.py"
LIMIT = 32 * 1024 * 1024


def months(first: date, count: int) -> list[tuple[date, date]]:
    if first.day != 1 or first < date(2015, 1, 1) or not 1 <= count <= 12:
        raise ValueError("Choose 1–12 full calendar months starting in January 2015 or later")
    result = []
    for _ in range(count):
        end = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        if end > datetime.now(UTC).date():
            raise ValueError("Choose completed UTC months")
        result.append((first, end))
        first = end
    return result


def valid_cached(path: Path) -> bool:
    receipt = path.with_suffix(".sha256")
    return (
        path.is_file()
        and receipt.is_file()
        and path.stat().st_size <= LIMIT
        and receipt.read_text().strip() == hashlib.sha256(path.read_bytes()).hexdigest()
    )


def fetch_month(start: date, end: date, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{start:%Y-%m}.csv"
    if valid_cached(path):
        return path
    params = urlencode({"fmt": "csv", "sts": f"{start}T00:00:00Z", "ets": f"{end}T00:00:00Z"})
    req = Request(
        f"{IEM}?{params}", headers={"User-Agent": "SkyCalm-ESADE/1.0", "Accept-Encoding": "gzip"}
    )
    with tempfile.TemporaryDirectory(dir=directory) as tmp:
        partial = Path(tmp) / "reports.csv"
        for attempt in range(2):
            marker = path.with_suffix(f".attempt-{attempt + 1}")
            try:
                marker.touch(exist_ok=False)
            except FileExistsError:
                continue
            try:
                with urlopen(req, timeout=45) as response, partial.open("wb") as output:
                    deadline = time.monotonic() + 120
                    while chunk := response.read(128 * 1024):
                        if output.tell() + len(chunk) > LIMIT or time.monotonic() > deadline:
                            raise ValueError("Monthly response exceeded the download budget")
                        output.write(chunk)
                    length = response.headers.get("Content-Length")
                    if length and output.tell() != int(length):
                        raise ConnectionError("Incomplete IEM download")
                break
            except (HTTPError, URLError, TimeoutError, ConnectionError) as exc:
                if isinstance(exc, HTTPError):
                    exc.close()
                    if exc.code != 429 and exc.code < 500:
                        raise
                if attempt:
                    raise
                time.sleep(1 + random.uniform(0, 0.4))
        else:
            raise RuntimeError(f"Download allowance exhausted for {start:%Y-%m}")
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            uncompressed = Path(tmp) / "uncompressed.csv"
            with gzip.open(partial, "rb") as src, uncompressed.open("wb") as dst:
                while chunk := src.read(128 * 1024):
                    if dst.tell() + len(chunk) > LIMIT:
                        raise ValueError("Expanded monthly CSV exceeds the byte allowance")
                    dst.write(chunk)
            partial = uncompressed
        with partial.open(encoding="utf-8-sig") as src:
            csv_header(src.readline())
        digest = Path(tmp) / "digest"
        digest.write_text(hashlib.sha256(partial.read_bytes()).hexdigest() + "\n")
        os.replace(partial, path)
        os.replace(digest, path.with_suffix(".sha256"))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_subparsers(dest="mode", required=True)
    audit = mode.add_parser("audit", help="Read existing IEM CSVs with no network calls")
    audit.add_argument("files", type=Path, nargs="+")
    fetch = mode.add_parser("fetch", help="Read each named calendar month once")
    fetch.add_argument("--first", required=True, help="YYYY-MM")
    fetch.add_argument("--months", type=int, required=True)
    fetch.add_argument("--directory", required=True, type=Path)
    for sub in (audit, fetch):
        sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "fetch":
        files = []
        missing = []
        for first, end in months(date.fromisoformat(args.first + "-01"), args.months):
            try:
                files.append(fetch_month(first, end, args.directory))
            except (ValueError, RuntimeError, OSError) as exc:
                missing.append(f"{first:%Y-%m}")
                print(
                    json.dumps(
                        {
                            "event": "pirep.month.unavailable",
                            "month": missing[-1],
                            "reason": str(exc),
                        }
                    ),
                    flush=True,
                )
                continue
            print(json.dumps({"event": "pirep.month.ready", "month": f"{first:%Y-%m}"}), flush=True)
        if missing:
            raise SystemExit("Census incomplete. Missing " + ", ".join(missing))
    else:
        files = args.files
    _, summary = audit_files(files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"event": "pirep.audit.complete", "accepted": summary["accepted"]}))


if __name__ == "__main__":
    main()
