"""AeroDataBox's single-day schedule, projected to passenger-facing fields."""

import json
import logging
import re
from datetime import date, datetime, timedelta
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.forecast.api import RequestError, airports
from services.forecast.schema import inside, utc_text

log = logging.getLogger(__name__)
HOST = "aerodatabox.p.rapidapi.com"
MAX_BYTES = 256 * 1024
FLIGHT = re.compile(r"([A-Z]{3}|[A-Z][A-Z0-9]|[0-9][A-Z])\s*([0-9]{1,4})([A-Z]?)", re.ASCII)


def number(value: object) -> str:
    if not isinstance(value, str) or len(value) > 12:
        raise ValueError
    match = FLIGHT.fullmatch(value.strip().upper())
    if not match or not int(match[2]):
        raise ValueError
    return f"{match[1]}{int(match[2])}{match[3]}"


def query(body: dict, today: date) -> tuple[str, date]:
    try:
        code = number(body.get("number"))
    except ValueError as exc:
        raise RequestError("flight_number", "Enter a flight number such as IB3204.", 400) from exc
    try:
        value = body["date"]
        day = date.fromisoformat(value)
        if value != day.isoformat() or abs((day - today).days) > 365:
            raise ValueError
    except (KeyError, ValueError, TypeError) as exc:
        raise RequestError(
            "flight_date", "Choose a departure date within one year of today.", 400
        ) from exc
    return code, day


def scheduled(movement: dict) -> dict | None:
    times = movement.get("scheduledTime") or {}
    try:
        utc = datetime.fromisoformat(times["utc"])
        if utc.utcoffset() != timedelta(0):
            return None
        zone = movement["airport"].get("timeZone")
        value = times.get("local")
        if value:
            local = datetime.fromisoformat(value)
            if local.utcoffset() is None or local != utc:
                return None
        elif zone:
            local = utc.astimezone(ZoneInfo(zone))
        else:
            return None
        return {"utc": utc_text(utc), "local": local.isoformat(timespec="minutes")}
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError, ZoneInfoNotFoundError):
        return None


def leg(movement: dict) -> dict:
    airport = movement["airport"]
    code = airport.get("iata")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError
    directory = airports().get(code)
    return {
        "code": code,
        "name": str(airport.get("shortName") or airport.get("name") or code)[:96],
        "time": scheduled(movement),
        "covered": bool(directory and inside(directory["lat"], directory["lon"])),
    }


def select(rows: object, code: str, day: date) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError("Invalid schedule response")
    results = {}
    incomplete = False
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError
            if row.get("isCargo"):
                continue
            reported = number(row["number"])
            suffix = FLIGHT.fullmatch(reported)[2] + FLIGHT.fullmatch(reported)[3]
            airline = row.get("airline") or {}
            if code not in {
                reported,
                *(str(airline.get(k, "")) + suffix for k in ("iata", "icao")),
            }:
                continue
            dep, arr = leg(row["departure"]), leg(row["arrival"])
            if not dep["time"]:
                raise ValueError
            if dep["time"]["local"][:10] != day.isoformat():
                continue
            if arr["time"] and arr["time"]["utc"] <= dep["time"]["utc"]:
                arr["time"] = None
            model = (row.get("aircraft") or {}).get("model")
            key = (dep["time"]["utc"], dep["code"], arr["code"])
            results[key] = {
                "number": code,
                "departure": dep,
                "arrival": arr,
                "aircraft": model[:80] if isinstance(model, str) else None,
                "status": str(row.get("status") or "Unknown")[:32],
            }
        except (KeyError, ValueError, TypeError, AttributeError):
            incomplete = True
    if incomplete and not results:
        raise ValueError("Schedule could not be verified")
    return [results[k] for k in sorted(results)]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(code: str, day: date, key: str, *, open_request=None) -> list[dict]:
    url = f"https://{HOST}/flights/number/{code}/{day}?dateLocalRole=Departure&withFlightPlan=false&withLocation=false&withAircraftImage=false"
    request = Request(
        url,
        headers={
            "X-RapidAPI-Key": key.strip(),
            "X-RapidAPI-Host": HOST,
            "Accept": "application/json",
        },
    )
    send = open_request or build_opener(NoRedirect()).open
    try:
        with send(request, timeout=5) as reply:
            if reply.status == 204:
                return []
            data = reply.read(MAX_BYTES + 1)
            if reply.status != 200 or len(data) > MAX_BYTES:
                raise ValueError
            return select(json.loads(data), code, day)
    except HTTPError as exc:
        log.warning(json.dumps({"event": "flight.provider.http", "status": exc.code}))
        if exc.code in (401, 403):
            raise RequestError(
                "provider_access",
                "Schedule access is unavailable. You can still search by airports.",
                503,
            ) from None
        if exc.code == 429:
            raise RequestError(
                "provider_limit",
                "The schedule provider is busy. Try again later or search by airports.",
                429,
            ) from None
    except (URLError, TimeoutError, HTTPException, ValueError, OSError) as exc:
        log.warning(json.dumps({"event": "flight.provider.error", "kind": type(exc).__name__}))
    raise RequestError(
        "provider_unavailable",
        "The schedule provider is unavailable. Try again later or search by airports.",
        503,
    )
