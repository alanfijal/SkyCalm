"""Passenger inputs, forecast comparisons and trusted identity boundaries."""

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from services.forecast.api import RequestError, airports
from services.forecast.route import route_points, scheduled_end
from services.forecast.schema import CATEGORIES, inside, utc_text


def identifier(value):
    try:
        parsed = UUID(value)
        if str(parsed) == value:
            return value
    except (ValueError, AttributeError, TypeError):
        pass
    raise RequestError("invalid_id", "Invalid identifier.", 400)


def identity(event, scope):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    if claims.get("token_use") != "access" or not claims.get("sub"):
        raise RequestError("unauthorized", "Please sign in.", 401)
    groups = re.findall(r"[\w-]+", str(claims.get("cognito:groups", "")))
    if scope not in claims.get("scope", "").split() or (
        scope == "skycalm/admin" and "admins" not in groups
    ):
        raise RequestError("forbidden", "This account cannot perform that action.", 403)
    return identifier(claims["sub"]), claims.get("username")


def flight_input(body, now):
    if not isinstance(body, dict):
        raise RequestError("invalid_flight", "Enter a route and departure time.")
    codes = [body.get(k) for k in ("origin", "destination")]
    pair = [airports().get(c.upper()) if isinstance(c, str) else None for c in codes]
    if any(not a or not inside(a["lat"], a["lon"]) for a in pair) or pair[0] == pair[1]:
        raise RequestError(
            "invalid_route", "Choose two different airports within European forecast coverage."
        )
    try:
        departure = datetime.fromisoformat(body.get("departure", ""))
        if departure.tzinfo is None:
            raise ValueError
        departure = departure.astimezone(UTC)
    except (ValueError, TypeError, OverflowError) as exc:
        raise RequestError("invalid_time", "Enter the departure in UTC.") from exc
    if not now < departure <= now + timedelta(days=365):
        raise RequestError("invalid_time", "Choose a departure in the next year.")
    _, points = route_points(*pair, departure)
    arrival = departure + timedelta(minutes=points[-1]["elapsedMinutes"])
    schedule = {}
    if body.get("flightNumber"):
        from services.flights.provider import number

        try:
            schedule["flightNumber"] = number(body["flightNumber"])
            if body.get("scheduledArrival"):
                arrival = scheduled_end(body["scheduledArrival"], departure)
                schedule["arrivalScheduled"] = True
        except (ValueError, TypeError, OverflowError) as exc:
            raise RequestError(
                "invalid_schedule", "Check the flight number and scheduled arrival."
            ) from exc
    return dict(
        **schedule,
        origin=pair[0]["code"],
        destination=pair[1]["code"],
        departure=utc_text(departure),
        departureEpoch=int(departure.timestamp()),
        arrival=utc_text(arrival),
        expiresAt=int((arrival + timedelta(days=7)).timestamp()),
    )


def snapshot(forecast):
    peak = forecast["peak"]
    if peak not in CATEGORIES:
        return None
    rough = next(
        (
            round(p["elapsedMinutes"])
            for p in forecast["samples"]
            if p["category"] in ("moderate", "severe")
        ),
        None,
    )
    return {"peak": peak, "firstRough": rough}


def changed(previous, current):
    if previous is None or current is None:
        return False
    if previous["peak"] != current["peak"]:
        return True
    a, b = previous["firstRough"], current["firstRough"]
    return a is not None and b is not None and abs(a - b) > 30
