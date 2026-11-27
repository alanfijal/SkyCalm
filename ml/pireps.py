"""Quality control for point turbulence reports. Coordinates are WGS84 and heights feet."""

import csv
import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from services.forecast.schema import CATEGORIES, utc_text

# Explicit ICAO jet types and common unambiguous PIREP family codes. Unknown stays unknown.
JETS = frozenset(
    """A20N A21N A19N A220 BCS1 BCS3 A306 A310 A318 A319 A320 A321 A332 A333
    A338 A339 A342 A343 A345 A346 A359 A35K A388 B712 B722 B732 B733 B734 B735 B736
    B737 B738 B739 B37M B38M B39M B3XM B741 B742 B743 B744 B748 B752 B753 B757
    B762 B763 B764 B772 B773 B77L B77W B788 B789 B78X CRJ1 CRJ2 CRJ7 CRJ9 CRJX
    E135 E145 E170 E175 E190 E195 E75L E75S E290 E295 MD11 MD82 MD83 MD88 MD90
    F70 F100 C25A C25B C25C C510 C525 C550 C560 C56X C650 C680 C68A C700 C750
    GLF3 GLF4 GLF5 GLF6 GL5T GLEX GL7T GA5C GA6C GA7C CL30 CL35 CL60 CL64
    FA20 FA50 F900 FA7X FA8X F2TH H25B H25C LJ35 LJ40 LJ45 LJ60 LJ75 PRM1""".split()
)
SEVERITY = {
    word: level
    for level, words in enumerate(
        (
            "NEG NEGATIVE NIL NONE SMTH SMOOTH",
            "LGT LT LIGHT",
            "MOD MODERATE",
            "SEV SEVERE EXT EXTRM EXTM EXTREME",
        )
    )
    for word in words.split()
}
COORDS = re.compile(r"(\d{2}|\d{4})([NS])\s*(\d{2,3}|\d{4,5})([EW])")


class Rejected(ValueError):
    """The report cannot be assigned one location, altitude and observed category."""


@dataclass(frozen=True)
class Report:
    time: datetime
    lat: float
    lon: float
    feet: int
    aircraft: str
    label: str

    @property
    def cohort(self) -> str:
        return "cruise" if self.feet >= 20_000 else "lower"

    @property
    def region(self) -> str:
        return sector(self.lat, self.lon)

    @property
    def key(self) -> str:
        # One encounter can be carried by several bulletins or both feeds.
        parts = f"{utc_text(self.time)}|{self.lat:.2f}|{self.lon:.2f}|{self.feet}|{self.aircraft}"
        return hashlib.sha256(parts.encode()).hexdigest()[:24]


def sector(lat: float, lon: float) -> str:
    if 34 <= lat <= 72 and -12 <= lon <= 45:
        return "europe"
    if 34 <= lat <= 72 and -60 <= lon < -12:
        return "north_atlantic"
    return "other"


def section(raw: str, tag: str) -> str:
    hit = re.search(rf"/{tag}\s*([^/]*)", raw)
    return hit[1].strip() if hit else ""


def coordinate(value: str, axis: str) -> float:
    if len(value) <= (2 if axis in "NS" else 3):
        degrees, minutes = int(value), 0
    else:
        degrees, minutes = int(value[:-2]), int(value[-2:])
    limit = 90 if axis in "NS" else 180
    if minutes >= 60 or degrees + minutes / 60 > limit:
        raise Rejected("position")
    return (degrees + minutes / 60) * (-1 if axis in "SW" else 1)


def checked_position(raw: str, lat: float, lon: float) -> None:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == lon == 0):
        raise Rejected("position")
    point = section(raw, "OV")
    if match := COORDS.fullmatch(point):
        a, b, c, d = match.groups()
        expected = coordinate(a, b), coordinate(c, d)
        # Match provider rounding while rejecting misplaced or truncated coordinates.
        if max(abs(lat - expected[0]), abs(lon - expected[1])) <= 0.05:
            return
    elif re.fullmatch("[A-Z0-9]{3}|K[A-Z0-9]{3}", point):
        from services.forecast.api import airports

        airport = airports().get(point[-3:])
        if airport and (len(point) == 3 or airport["country"] == "US"):
            if max(abs(lat - airport["lat"]), abs(lon - airport["lon"])) <= 0.05:
                return
    raise Rejected("unverified_position")


def intensity(text: str, feet: int) -> str:
    words = re.findall("[A-Z]+|[0-9]+", text.upper())
    classes = {SEVERITY[w] for w in words if w in SEVERITY}
    if not classes:
        raise Rejected("no_turbulence_label")
    # Mixed layers, altitude ranges and negated positive categories are ambiguous.
    if (
        (0 in classes and len(classes) > 1)
        or any(
            w in {"ABV", "ABOVE", "BLO", "BLW", "BELOW", "BTWN", "EXC", "NOT", "NO"} for w in words
        )
        or any(w.isdigit() and (len(w) != 3 or int(w) * 100 != feet) for w in words)
    ):
        raise Rejected("ambiguous_turbulence")
    return CATEGORIES[max(classes)]


def read_iem(row: Mapping[str, str]) -> Report:
    raw = row["REPORT"].upper()
    raw_fl = section(raw, "FL")
    if raw_fl and not re.fullmatch(r"\d{3}", raw_fl):
        raise Rejected("flight_level")
    try:
        feet = int(row["FL"]) if row["FL"] not in ("", "None") else 100 * int(raw_fl)
        when = datetime.strptime(row["VALID"], "%Y%m%d%H%M").replace(tzinfo=UTC)
    except (TypeError, ValueError) as exc:
        raise Rejected("flight_level_or_time") from exc
    if not 0 < feet <= 60_000 or (raw_fl and feet != int(raw_fl) * 100):
        raise Rejected("flight_level")
    aircraft = row["AIRCRAFT"].strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,4}", aircraft) or aircraft in {"NONE", "UNKN", "ZZZZ"}:
        raise Rejected("unknown_aircraft")
    if feet >= 20_000 and aircraft not in JETS:
        raise Rejected("unverified_cruise_jet")
    # The CSV uses the literal string "None" for a missing field, including before extraction.
    tb = row["TURBULENCE"]
    turbulence = intensity(section(raw, "TB") if tb in ("None", "") else tb, feet)
    try:
        lat, lon = float(row["LAT"]), float(row["LON"])
    except (ValueError, TypeError) as exc:
        raise Rejected("position") from exc
    checked_position(raw, lat, lon)
    return Report(when, lat, lon, feet, aircraft, turbulence)


def read_awc(row: dict) -> Report:
    """Use the explicit PIREP fields. Some AIREPs put a callsign in acType."""
    raw = str(row.get("rawOb") or "").upper()
    aircraft = section(raw, "TP") or str(row.get("acType") or "").upper()
    try:
        when = datetime.fromtimestamp(int(row["obsTime"]), UTC)
        fl = int(row["fltLvl"])
    except (KeyError, ValueError, TypeError, OSError, OverflowError) as exc:
        raise Rejected("flight_level_or_time") from exc
    for key in ("tbBas1", "tbTop1", "tbBas2", "tbTop2"):
        if row.get(key) not in (None, "", fl):
            raise Rejected("ambiguous_turbulence")
    words = " ".join(str(row.get(k) or "") for k in ("tbInt1", "tbInt2")).strip()
    if row.get("pirepType") == "AIREP" and "/TP" not in raw:
        # AWC also carries ARP bulletins with the actual ICAO type in a final remark.
        # An airline callsign in acType cannot establish aircraft propulsion.
        parts = re.fullmatch(
            r"ARP\s+\S+\s+(\d{2,4}[NS]\s+\d{2,5}[EW])\s+(\d{4})\s+F(\d{3})\b.*?\bRM\s+([A-Z0-9]{2,4})\s*",
            raw,
        )
        if not parts or parts[4] not in JETS:
            raise Rejected("unverified_aircraft_type")
        if int(parts[3]) != fl or parts[2] != when.strftime("%H%M"):
            raise Rejected("flight_level_or_time")
        aircraft, raw = parts[4], f"/OV {parts[1]}/FL{parts[3]}/TP {parts[4]}"
    elif row.get("pirepType") not in {"PIREP", "UA", "UUA"} and "/TP" not in raw:
        raise Rejected("unverified_aircraft_type")
    return read_iem(
        {
            "REPORT": raw,
            "VALID": when.strftime("%Y%m%d%H%M"),
            "FL": str(fl * 100),
            "AIRCRAFT": aircraft,
            "LAT": str(row.get("lat")),
            "LON": str(row.get("lon")),
            "TURBULENCE": words if not section(raw, "TB") else section(raw, "TB"),
        }
    )


def unique_reports(reports: Iterable[Report], counts: Counter) -> list[Report]:
    kept: dict[str, Report] = {}
    conflicts: set[str] = set()
    for row in reports:
        key = row.key
        if key in conflicts:
            counts["duplicate"] += 1
        elif key not in kept:
            kept[key] = row
        elif row.label != kept[key].label:
            del kept[key]
            conflicts.add(key)
            counts["conflicting_reports"] += 2
        else:
            counts["duplicate"] += 1
    return sorted(kept.values(), key=lambda r: (r.time, r.key))


def csv_header(text: str) -> list[str]:
    header = next(csv.reader([text]))
    if not {"VALID", "AIRCRAFT", "REPORT", "TURBULENCE", "FL", "LAT", "LON"}.issubset(header):
        raise ValueError("Unexpected IEM CSV schema")
    return header


def archive_rows(path: Path, counts: Counter) -> Iterator[dict[str, str]]:
    # Reports in this feed start with a UTC timestamp. Isolate damaged quoted records:
    # an unmatched quote in free text must not consume the following day's valid reports.
    date_prefix = (
        path.stem.replace("-", "") if re.fullmatch(r"\d{4}-\d\d(-\d\d)?", path.stem) else ""
    )
    with path.open(newline="", encoding="utf-8-sig") as stream:
        header = csv_header(stream.readline())
        chunk: list[str] = []
        for line in stream:
            if re.match(r"^\d{12},", line) and chunk:
                yield from parse_record(chunk, header, date_prefix, counts)
                chunk = []
            chunk.append(line)
        if chunk:
            yield from parse_record(chunk, header, date_prefix, counts)


def parse_record(
    lines: list[str], header: list[str], date_prefix: str, counts: Counter
) -> Iterator[dict[str, str]]:
    try:
        rows = list(csv.reader(lines, strict=True))
        if len(rows) != 1 or len(rows[0]) != len(header):
            raise ValueError
        row = dict(zip(header, rows[0], strict=True))
    except (csv.Error, ValueError):
        counts["malformed_csv"] += 1
        return
    if date_prefix and not row["VALID"].startswith(date_prefix):
        counts["outside_requested_period"] += 1
        return
    yield row


def audit_files(paths: Iterable[Path]) -> tuple[list[Report], dict]:
    counts: Counter = Counter()
    upper: Counter = Counter()
    sources = []

    def candidates() -> Iterator[Report]:
        for path in sorted(paths):
            source = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            sources.append(source)
            for row in archive_rows(path, counts):
                counts["input"] += 1
                if row["TURBULENCE"] not in ("", "None") or section(row["REPORT"], "TB"):
                    try:
                        lat, lon = float(row["LAT"]), float(row["LON"])
                        if math.isfinite(lat) and math.isfinite(lon):
                            upper[sector(lat, lon)] += 1
                    except ValueError:
                        pass
                try:
                    yield read_iem(row)
                except Rejected as exc:
                    counts[str(exc)] += 1

    rows = unique_reports(candidates(), counts)
    coverage: dict[str, dict[str, Counter]] = {
        area: {c: Counter({v: 0 for v in CATEGORIES}) for c in ("cruise", "lower")}
        for area in ("europe", "north_atlantic", "other")
    }
    for row in rows:
        coverage[row.region][row.cohort][row.label] += 1
    return rows, {
        "sources": sources,
        "counts": dict(counts),
        "turbulenceBeforeQC": dict(upper),
        "accepted": len(rows),
        "coverage": coverage,
    }
