"""Loopback adapter. Only quota counters survive a server restart."""

import json
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4

from services.flights.lookup import CACHE_SECONDS, lookup
from services.flights.provider import fetch
from services.forecast.api import RequestError


class LocalLedger:
    def __init__(self, directory: Path):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = directory / "flight-lookup.sqlite"
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY, rev TEXT, value TEXT)"
            )
        self.cache: dict[str, dict] = {}
        self.lock = threading.Lock()

    def read(self, key: str) -> dict:
        if key == "budget":
            with sqlite3.connect(self.path) as db:
                row = db.execute("SELECT value FROM budget WHERE id=1").fetchone()
            return json.loads(row[0]) if row else {}
        with self.lock:
            return self.cache.get(key, {})

    def reserve(self, previous: str | None, budget: dict) -> bool:
        with sqlite3.connect(self.path) as db:
            return (
                db.execute(
                    "INSERT INTO budget VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET rev=excluded.rev,value=excluded.value WHERE budget.rev=?",
                    (budget["rev"], json.dumps(budget), previous),
                ).rowcount
                == 1
            )

    def finish(self, budget: dict, key: str, cached: dict | None) -> None:
        released = {**budget, "rev": uuid4().hex, "holdUntil": 0}
        with self.lock:
            if self.reserve(budget["rev"], released) and cached is not None:
                self.cache[key] = cached

                def forget() -> None:
                    with self.lock:
                        if self.cache.get(key) is cached:
                            self.cache.pop(key)

                timer = threading.Timer(CACHE_SECONDS, forget)
                timer.daemon = True
                timer.start()


def local_lookup(body: dict, directory: Path, ledger: LocalLedger) -> dict:
    api_key = directory / "providers" / "aerodatabox.key"

    def load(code, day):
        try:
            key = api_key.read_text().strip()
        except FileNotFoundError:
            key = ""
        if not key:
            raise RequestError(
                "lookup_offline", "Flight-number lookup is unavailable. Search by airports.", 503
            )
        return fetch(code, day, key)

    if not api_key.is_file():
        raise RequestError(
            "lookup_offline", "Flight-number lookup is unavailable. Search by airports.", 503
        )
    return lookup(body, "local-presenter", ledger, load)
