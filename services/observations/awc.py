"""One bounded AWC weather snapshot. Only weather fields reach the public map."""

import hashlib
import json
import math
import random
import time
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.forecast.schema import EAST, NORTH, SOUTH, WEST, inside, utc_text

ORIGIN = "https://aviationweather.gov/api/data/"
RESULT_LIMIT = 400
MAX_BYTES = 4 * 1024 * 1024
INTENSITIES = ("smooth", "light", "moderate", "severe")
CODES = {
    "NEG": "smooth",
    "SMTH": "smooth",
    "SMOOTH": "smooth",
    "TRC": "light",
    "LGT": "light",
    "MOD": "moderate",
    "SEV": "severe",
    "HVY": "severe",
    "EXTM": "severe",
    "EXTRM": "severe",
}


def instant(value) -> datetime | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, UTC)
        when = datetime.fromisoformat(value)
        return when.astimezone(UTC) if when.utcoffset() is not None else None
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def numeric(value, lower, upper):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if math.isfinite(n) and lower <= n <= upper else None


def intensity(*codes) -> str | None:
    known = [
        CODES[t]
        for code in codes
        if isinstance(code, str)
        for t in code.upper().replace("/", "-").split("-")
        if t in CODES
    ]
    return max(known, key=INTENSITIES.index) if known else None


def identity(kind: str, fields: list) -> str:
    packed = json.dumps(fields, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    return kind + "-" + hashlib.sha256(packed.encode()).hexdigest()[:24]


def report(row: dict, as_of: datetime) -> dict | None:
    when = instant(row.get("obsTime"))
    receipt = instant(row.get("receiptTime"))
    lat, lon = numeric(row.get("lat"), -90, 90), numeric(row.get("lon"), -180, 180)
    if (
        not when
        or not as_of - timedelta(hours=8) <= when <= as_of
        or (receipt and receipt > as_of)
        or lat is None
        or lon is None
        or not inside(lat, lon)
    ):
        return None
    codes = [row.get(k) for k in ("tbInt1", "tbInt2") if isinstance(row.get(k), str)]
    level = numeric(row.get("fltLvl"), 0, 650)
    altitude = round(level * 100) if level is not None else None
    observed = utc_text(when)
    category = intensity(*codes)
    return {
        "id": identity(
            "report",
            [
                observed,
                lat,
                lon,
                altitude,
                codes,
                row.get("pirepType"),
                *[row.get(k) for k in ("tbBas1", "tbTop1", "tbBas2", "tbTop2")],
            ],
        ),
        "kind": "report",
        "source": str(row.get("pirepType") or "Aircraft report")[:18],
        "from": observed,
        "to": None,
        "intensity": category or "unreported",
        "codes": codes,
        "baseFt": altitude,
        "topFt": altitude,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def polygon_area(coords) -> list:
    if not isinstance(coords, list) or len(coords) < 3:
        return []
    ring = []
    for point in coords:
        if not isinstance(point, dict):
            return []
        lat, lon = numeric(point.get("lat"), -90, 90), numeric(point.get("lon"), -180, 180)
        if lat is None or lon is None:
            return []
        ring.append([lon, lat])
    if len({tuple(p) for p in ring}) < 3:
        return []
    xs, ys = zip(*ring, strict=True)
    if (
        max(xs) - min(xs) > 180
        or max(xs) < WEST
        or min(xs) > EAST
        or max(ys) < SOUTH
        or min(ys) > NORTH
    ):
        return []
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def advisory(row: dict, as_of: datetime) -> dict | None:
    start, end = instant(row.get("validTimeFrom")), instant(row.get("validTimeTo"))
    issued = instant(row.get("issueTime")) or instant(row.get("creationTime"))
    receipt = instant(row.get("receiptTime"))
    if (
        str(row.get("hazard", "")).upper() not in {"TURB", "TURBULENCE"}
        or row.get("geom") != "AREA"
        or row.get("qualifier") == "CNL"
        or not start
        or not end
        or not start <= as_of < end
        or (issued and issued > as_of)
        or (receipt and receipt > as_of)
    ):
        return None
    coords = row.get("coords")
    parts = (
        coords if isinstance(coords, list) and coords and isinstance(coords[0], list) else [coords]
    )
    rings = [ring for part in parts if (ring := polygon_area(part))]
    if not rings:
        return None
    geometry = (
        {"type": "Polygon", "coordinates": [rings[0]]}
        if len(rings) == 1
        else {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}
    )
    code = row.get("qualifier")
    station, fir, series = [str(row.get(k) or "")[:25] for k in ("icaoId", "firId", "seriesId")]
    return {
        "id": identity(
            "sigmet",
            [station, fir, series, utc_text(issued or start), utc_text(start), utc_text(end)],
        ),
        "kind": "sigmet",
        "source": " ".join(x for x in (fir or station, series) if x) or "SIGMET",
        "from": utc_text(start),
        "to": utc_text(end),
        "intensity": intensity(code) or "unreported",
        "codes": [code] if isinstance(code, str) else [],
        "baseFt": numeric(row.get("base"), 0, 70000),
        "topFt": numeric(row.get("top"), 0, 70000),
        "geometry": geometry,
    }


def normalize(as_of: datetime, sigmets: list, reports: list, supplement: list) -> dict:
    items = {}
    for records, transform in ((sigmets, advisory), (reports, report), (supplement, report)):
        for row in records:
            if isinstance(row, dict) and (item := transform(row, as_of)) is not None:
                items[item["id"]] = item
    return {
        "asOf": utc_text(as_of),
        "source": "NOAA Aviation Weather Center",
        "reportWindowHours": 8,
        "limited": any(len(rows) >= RESULT_LIMIT for rows in (sigmets, reports, supplement)),
        "items": sorted(items.values(), key=lambda x: (x["kind"], x["from"], x["id"])),
    }


def fetch(url: str) -> list:
    # AWC requests at most 100 queries per minute and asks clients to space them.
    time.sleep(0.65)
    req = Request(url, headers={"User-Agent": "SkyCalm-ESADE/1.0", "Accept": "application/json"})
    for attempt in range(2):
        try:
            with urlopen(req, timeout=8) as response:
                if response.status == 204:
                    return []
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("AWC response exceeds the byte limit")
            rows = json.loads(raw)
            if not isinstance(rows, list):
                raise ValueError("AWC returned an unexpected response")
            return rows
        except HTTPError as exc:
            exc.close()
            if exc.code < 500 or attempt:
                raise RuntimeError(f"AWC returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            if attempt:
                raise RuntimeError("AWC is unavailable") from exc
        time.sleep(0.3 + random.uniform(0, 0.2))
    raise RuntimeError("AWC is unavailable")


def collect(as_of: datetime, get=fetch) -> tuple[dict, dict]:
    base = {"format": "json", "date": as_of.strftime("%Y%m%d_%H%M")}
    area = {**base, "bbox": f"{SOUTH},{WEST},{NORTH},{EAST}", "age": 8}
    sigmets = get(ORIGIN + "sigmet?" + urlencode({**base, "hazard": "turb"}))
    reports = get(ORIGIN + "pirep?" + urlencode(area))
    # A busy eight-hour query can fill with automated wind reports. Request the
    # provider's significant-intensity subset as well in that case, then deduplicate.
    supplement = (
        get(ORIGIN + "pirep?" + urlencode({**area, "inten": "lgt"}))
        if len(reports) >= RESULT_LIMIT
        else []
    )
    raw = {"sigmets": sigmets, "reports": reports, "supplement": supplement}
    return normalize(as_of, sigmets, reports, supplement), raw
