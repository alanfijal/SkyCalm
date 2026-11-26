"""Shared schedule cache admission for the classroom provider allowance."""

import hashlib
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import uuid4

from services.flights.provider import query
from services.forecast.api import RequestError

USER_DAY, GLOBAL_DAY, MAX_32_DAYS = 3, 5, 60
CACHE_SECONDS, EMPTY_SECONDS = 900, 180


class Ledger(Protocol):
    def read(self, key: str) -> dict: ...
    def reserve(self, previous: str | None, budget: dict) -> bool: ...
    def finish(self, budget: dict, key: str, cached: dict | None) -> None: ...


def lookup(
    body: dict,
    owner: str,
    ledger: Ledger,
    load: Callable[[str, date], list[dict]],
    *,
    clock=time.time,
) -> dict:
    now = int(clock())
    today = datetime.fromtimestamp(now, UTC).date()
    number, day = query(body, today)
    key = f"schedule#{number}#{day}"
    previous = ledger.read("budget")
    cached = ledger.read(key)
    if cached.get("expiresAt", 0) > now:
        return {"flights": cached["flights"], "checkedAt": cached["checkedAt"], "cached": True}
    if max(previous.get("nextAt", 0), previous.get("holdUntil", 0)) > now:
        raise RequestError(
            "lookup_busy", "Another flight lookup just started. Try again in a moment.", 429
        )
    users = dict(previous.get("users", {})) if previous.get("day") == str(today) else {}
    subject = hashlib.sha256(owner.encode()).hexdigest()[:32]
    # A billing cycle can straddle two UTC calendar months. Charge every attempted call.
    # Carry over any counters created by the first local rehearsal.
    recent = previous.get("recent")
    if recent is None:
        recent = [now] * min(int(previous.get("monthly", 0)), MAX_32_DAYS)
    recent = [int(stamp) for stamp in recent if int(stamp) > now - 32 * 86400]
    if (
        users.get(subject, 0) >= USER_DAY
        or sum(users.values()) >= GLOBAL_DAY
        or len(recent) >= MAX_32_DAYS
    ):
        raise RequestError(
            "lookup_quota",
            "The flight lookup allowance has been reached. You can still search by airports.",
            429,
        )
    users[subject] = users.get(subject, 0) + 1
    budget = {
        "rev": uuid4().hex,
        "day": str(today),
        "recent": [*recent, now],
        "users": users,
        "holdUntil": now + 30,
        "nextAt": now + 2,
    }
    if not ledger.reserve(previous.get("rev"), budget):
        raise RequestError(
            "lookup_busy", "Another lookup is in progress. Try again in a moment.", 429
        )
    result = None
    try:
        flights = load(number, day)
        result = {
            "flights": flights,
            "checkedAt": now,
            "expiresAt": now + (CACHE_SECONDS if flights else EMPTY_SECONDS),
        }
    finally:
        # Failed provider calls can still consume units. Release only our own reservation.
        ledger.finish(budget, key, result)
    return {"flights": flights, "checkedAt": now, "cached": False}
