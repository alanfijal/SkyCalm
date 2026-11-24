"""Passenger route approximation along a great circle."""

import math
from datetime import datetime, timedelta

from services.forecast.schema import utc_text

EARTH_KM = 6371.0


def vector(lat: float, lon: float) -> tuple[float, float, float]:
    lat, lon = math.radians(lat), math.radians(lon)
    return math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)


def route_points(origin: dict, destination: dict, departure: datetime) -> tuple[float, list[dict]]:
    a, b = vector(origin["lat"], origin["lon"]), vector(destination["lat"], destination["lon"])
    angle = math.acos(max(-1, min(1, sum(x * y for x, y in zip(a, b, strict=True)))))
    distance = angle * EARTH_KM
    if distance < 0.1:
        raise ValueError("Choose two different airports.")
    steps = max(2, math.ceil(distance / 25))
    points = []
    for i in range(steps + 1):
        t = i / steps
        left = math.sin((1 - t) * angle) / math.sin(angle)
        right = math.sin(t * angle) / math.sin(angle)
        x, y, z = (left * u + right * v for u, v in zip(a, b, strict=True))
        km = distance * t
        from_ground = origin.get("elevationFt") or 0
        to_ground = destination.get("elevationFt") or 0
        climb = from_ground + (35000 - from_ground) * km / 150
        descent = to_ground + (35000 - to_ground) * (distance - km) / 150
        altitude = min(35000, climb, descent)
        minutes = km / 800 * 60
        points.append(
            {
                "lat": round(math.degrees(math.atan2(z, math.hypot(x, y))), 6),
                "lon": round(math.degrees(math.atan2(y, x)), 6),
                "altitudeFt": round(altitude),
                "elapsedMinutes": minutes,
                "distanceKm": km,
                "phase": "climb"
                if climb < min(35000, descent)
                else "descent"
                if descent < 35000
                else "cruise",
                "at": utc_text(departure + timedelta(minutes=minutes)),
            }
        )
    return distance, points
