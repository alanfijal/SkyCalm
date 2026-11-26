"""Altitude-, time- and distance-qualified turbulence reports for a passenger route."""

import math
from datetime import datetime

from services.forecast.schema import CATEGORIES


def distance_km(lat, lon, other_lat, other_lon):
    lat, lon, other_lat, other_lon = map(math.radians, (lat, lon, other_lat, other_lon))
    a = math.sin((other_lat - lat) / 2) ** 2 + (
        math.cos(lat) * math.cos(other_lat) * math.sin((other_lon - lon) / 2) ** 2
    )
    return 12742 * math.asin(min(1, math.sqrt(a)))


def match_reports(samples, items):
    """Use each timed, altitude-qualified point report once, at its nearest eligible sample."""
    matches = {}
    for item in items:
        if (
            item["kind"] != "report"
            or item["geometry"]["type"] != "Point"
            or item["intensity"] not in CATEGORIES
            or item["baseFt"] is None
        ):
            continue
        lon, lat = item["geometry"]["coordinates"]
        observed = datetime.fromisoformat(item["from"])
        eligible = []
        for index, pt in enumerate(samples):
            minutes = abs((datetime.fromisoformat(pt["at"]) - observed).total_seconds()) / 60
            if minutes > 45 or abs(pt["altitudeFt"] - item["baseFt"]) > 3000:
                continue
            km = distance_km(lat, lon, pt["lat"], pt["lon"])
            if km <= 75:
                eligible.append((km, minutes, index))
        if eligible:
            km, _, index = min(eligible)
            pt = samples[index]
            matches[item["id"]] = {
                "source": item["source"],
                "observed": item["from"],
                "altitude_ft": item["baseFt"],
                "distance_km": round(km),
                "elapsed_minutes": round(pt["elapsedMinutes"]),
                "reported": item["intensity"],
                "forecast": pt["category"],
            }
    return sorted(
        matches.values(), key=lambda report: (report["observed"], report["elapsed_minutes"])
    )
