"""Bounded private forecast snapshots and post-flight comparisons."""

import gzip
import json
from datetime import UTC, datetime, timedelta

from services.forecast.api import RequestError
from services.forecast.schema import CATEGORIES
from services.observations.matching import match_reports


def flight_or_missing(store, owner, slot, now, revision=None):
    flight = store.get(owner, f"flight#{slot}")
    if flight.get("expiresAt", 0) <= now or (revision and flight.get("revision") != revision):
        raise RequestError("flight_missing", "This flight is no longer available.", 404)
    return flight


def compact_forecast(forecast):
    return gzip.compress(
        json.dumps(forecast, separators=(",", ":"), allow_nan=False).encode(), mtime=0
    )


def forecast_for(store, flight):
    record = store.get(flight["pk"], "forecast#" + flight["id"])
    if record.get("revision") != flight["revision"] or not record.get("payload"):
        return None
    return json.loads(gzip.decompress(bytes(record["payload"])))


def ribbon(samples, count=16):
    # For a compact card, take the worst known section in each contiguous bucket.
    count = min(count, len(samples))
    bands = []
    for i in range(count):
        chunk = samples[i * len(samples) // count : (i + 1) * len(samples) // count]
        bands.append(
            max(
                (p["category"] for p in chunk if p["category"] in CATEGORIES),
                key=CATEGORIES.index,
                default="unavailable",
            )
        )
    return bands


def recap(flight, forecast, weather):
    if not forecast:
        return {"status": "no-forecast", "reports": []}
    if flight["watch"] == "demo":
        from services.observations.archive import replay

        snapshot = replay(forecast["run"]["runId"])
        captures = [snapshot] if snapshot else []
    else:
        captures = weather().route_observations(flight["departure"], flight["arrival"])
    by_id = {item["id"]: item for capture in captures for item in capture["items"]}
    return {
        "status": "available" if captures else "no-captures",
        "captures": len(captures),
        "reports": match_reports(forecast["samples"], by_id.values()),
    }


def reminder(departure, now):
    return next((due for h in (24, 3) if (due := departure - h * 3600) > now), None)


def detail(store, flight, now, weather):
    from services.passengers.api import FLIGHT_FIELDS, public_row

    forecast = forecast_for(store, flight)
    past = datetime.fromisoformat(flight["arrival"]) <= datetime.fromtimestamp(now, UTC)
    return {
        "flight": public_row(flight, FLIGHT_FIELDS),
        "forecast": forecast,
        "history": flight.get("forecastHistory", []),
        "shareUntil": (flight.get("familyGrant") or {}).get("until"),
        "recap": recap(flight, forecast, weather) if past else None,
    }


def capture_prefixes(departure, arrival):
    # AWC captures include recent PIREPs. Look from departure to six hours after landing.
    start = datetime.fromisoformat(departure).astimezone(UTC).date()
    end = (datetime.fromisoformat(arrival).astimezone(UTC) + timedelta(hours=6)).date()
    return [(start + timedelta(days=d)).isoformat() for d in range((end - start).days + 1)]
