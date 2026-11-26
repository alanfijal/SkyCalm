"""Passenger display and delivery settings. Quiet hours use the chosen local clock."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.forecast.api import RequestError, airports
from services.forecast.schema import inside

DEFAULTS = {
    "sensitivity": "all",
    "quietHours": None,
    "altitudeUnit": "ft",
    "timeDisplay": "local",
    "nervousFlyer": False,
    "homeAirport": "",
}
OPTIONS = {
    "sensitivity": ("all", "moderate"),
    "altitudeUnit": ("ft", "m"),
    "timeDisplay": ("local", "utc"),
}


def settings_patch(value):
    if not isinstance(value, dict) or not value or value.keys() - DEFAULTS.keys():
        raise RequestError("invalid_preferences", "Choose supported passenger preferences.")
    for key, val in value.items():
        if key in OPTIONS:
            valid = val in OPTIONS[key]
        elif key == "nervousFlyer":
            valid = isinstance(val, bool)
        elif key == "homeAirport":
            airport = airports().get(val) if isinstance(val, str) else None
            valid = val == "" or bool(airport and inside(airport["lat"], airport["lon"]))
        else:
            valid = val is None or valid_hours(val)
        if not valid:
            raise RequestError("invalid_preferences", f"Check the value for {key}.")
    return value


def valid_hours(value):
    if not isinstance(value, dict) or set(value) != {"start", "end", "zone"}:
        return False
    if value["start"] == value["end"] or not all(
        isinstance(value[k], str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value[k])
        for k in ("start", "end")
    ):
        return False
    try:
        ZoneInfo(value["zone"])
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return False
    return True


def inbox_only(notice, prefs, stamp):
    hours = prefs.get("quietHours")
    if hours:
        local = datetime.fromtimestamp(stamp, ZoneInfo(hours["zone"])).strftime("%H:%M")
        start, end = hours["start"], hours["end"]
        quiet = start <= local < end if start < end else local >= start or local < end
        if quiet:
            return True
    return (
        prefs.get("sensitivity") == "moderate"
        and notice["kind"] in ("forecast-change", "test-change")
        and notice.get("peak") not in ("moderate", "severe")
    )
