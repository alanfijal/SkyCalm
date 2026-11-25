"""Read-only API used by both the local server and API Gateway."""

import json
import math
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from services.forecast.briefing import cache_key, select, variants
from services.forecast.model_tile import decode_predictions, point_prediction
from services.forecast.product import sample, unpack
from services.forecast.route import route_points
from services.forecast.schema import CATEGORIES, inside, issue_time, utc_text


class RequestError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.status = code, status


@lru_cache(maxsize=1)
def airports() -> dict[str, dict]:
    items = json.loads((Path(__file__).parent / "data" / "airports.json").read_bytes())
    return {a["code"]: a for a in items}


def search(query: str) -> list[dict]:
    needle = query.strip().casefold()
    if len(needle) > 64:
        raise RequestError("invalid_query", "Enter an airport name or code.", 400)
    if not needle:
        return [
            airports()[c] for c in ("BCN", "ARN", "AMS", "LHR", "OSL", "CDG") if c in airports()
        ]
    matches = []
    for a in airports().values():
        code = a["code"].casefold()
        city = (a["city"] or "").casefold()
        name = a["name"].casefold()
        covered = inside(a["lat"], a["lon"])
        if needle == code or (
            covered and (code.startswith(needle) or needle in city or needle in name)
        ):
            matches.append(
                (
                    code != needle,
                    not city.startswith(needle),
                    not code.startswith(needle),
                    name,
                    code,
                    a,
                )
            )
    return [m[-1] for m in sorted(matches)[:12]]


def descriptor(run: dict) -> dict:
    return {k: run[k] for k in ("runId", "issued", "validUntil", "source", "scorer")}


def respond(path: str, query: dict[str, str], store, now: datetime | None = None) -> dict:
    clock = now or datetime.now(UTC)
    if path == "/api/airports":
        return {"airports": search(query.get("q", ""))}
    if path == "/api/observations":
        from services.observations.awc import instant

        selection = query.get("run", "latest")
        if selection != "latest":
            try:
                issue_time(selection)
            except ValueError as exc:
                raise RequestError("invalid_run", "Choose a valid forecast run.", 400) from exc
        snapshot = store.observation_snapshot(selection)
        if snapshot is None:
            raise RequestError(
                "no_observations", "No weather observations for this source yet.", 404
            )
        stamp = instant(snapshot["asOf"])
        return {
            **snapshot,
            "mode": "live" if selection == "latest" else "replay",
            "stale": selection == "latest"
            and (stamp is None or clock - stamp > timedelta(hours=1)),
        }
    if path == "/api/runs":
        latest = store.latest()
        live = store.manifest(latest) if latest else None
        ids = sorted(set(store.replays()) | ({latest} if latest else set()), reverse=True)
        return {
            "latest": descriptor(live) if live else None,
            "serverTime": utc_text(clock),
            "replays": [descriptor(m) for name in ids if (m := store.manifest(name))],
        }
    if path != "/api/forecast":
        raise RequestError("not_found", "Unknown API route.", 404)
    origin = airports().get(query.get("origin", "").upper())
    dest = airports().get(query.get("destination", "").upper())
    if not origin or not dest:
        raise RequestError(
            "unknown_airport", "Select a scheduled-service airport for both ends of the route."
        )
    if not all(inside(a["lat"], a["lon"]) for a in (origin, dest)):
        raise RequestError(
            "outside_coverage",
            "Outside coverage. Choose two airports within the European forecast area.",
        )
    if origin["code"] == dest["code"]:
        raise RequestError("same_airport", "Choose two different airports.")
    try:
        departure = datetime.fromisoformat(query.get("departure", ""))
        if departure.utcoffset() is None:
            raise ValueError
        departure = departure.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise RequestError("invalid_time", "Enter a valid departure date and time in UTC.") from exc
    selection = query.get("run", "latest")
    run_id = store.latest() if selection == "latest" else selection
    if not run_id:
        raise RequestError(
            "no_live_run", "Live weather is unavailable. Choose an archived run.", 503
        )
    try:
        issued = issue_time(run_id)
    except ValueError as exc:
        raise RequestError("invalid_run", "Choose a valid forecast run.", 400) from exc
    manifest = store.manifest(run_id)
    if not manifest:
        raise RequestError("unknown_run", "This forecast run is unavailable.", 404)
    end = issued + timedelta(hours=36)
    if selection == "latest" and clock > end:
        raise RequestError(
            "stale_run",
            "The latest weather grid has expired. Refresh the grid or choose replay.",
            409,
        )
    if departure < issued:
        raise RequestError(
            "before_run", "This departure is earlier than the selected forecast run."
        )
    if departure > end:
        raise RequestError(
            "too_early",
            "Too early to forecast. Choose a departure within this run’s 36-hour window.",
        )
    if selection == "latest" and departure < clock - timedelta(minutes=5):
        raise RequestError("past_departure", "Choose an upcoming departure or switch to replay.")
    try:
        distance, points = route_points(origin, dest, departure)
    except ValueError as exc:
        raise RequestError("same_airport", str(exc)) from exc
    cubes = {}
    digests = {item["lead"]: item["sha256"] for item in manifest["leads"]}
    predictions = {}
    model_digests = {
        item["lead"]: item["modelSha256"] for item in manifest["leads"] if "modelSha256" in item
    }
    start_hours = (departure - issued).total_seconds() / 3600
    for pt in points:
        hours = start_hours + pt["elapsedMinutes"] / 60
        if 0 <= hours <= 36:
            low = int(hours // 3) * 3
            for lead in (low, min(low + 3, 36)):
                if lead not in cubes:
                    cubes[lead] = unpack(store.tile(run_id, lead, digests[lead]))
        pt.update(sample(cubes, hours, pt))
        if model_digests and pt["method"] == "ti1":
            near = 3 * math.ceil(hours / 3 - 0.5)
            if near not in predictions:
                predictions[near] = decode_predictions(
                    store.model_tile(run_id, near, model_digests[near])
                )
            pt.update(point_prediction(predictions[near], cubes[near], pt))
        pt["elapsedMinutes"] = round(pt["elapsedMinutes"], 2)
        pt["distanceKm"] = round(pt["distanceKm"], 2)
    options = variants(points)
    key = cache_key(run_id, origin["code"], dest["code"], utc_text(departure), options)
    try:
        cached = store.briefing(key) if hasattr(store, "briefing") else None
        briefing = select(options, cached["choices"] if cached else [0, 0])
    except (OSError, KeyError, ValueError, TypeError):
        briefing = select(options, [0, 0])
    classes = [p["category"] for p in points if p["category"] in CATEGORIES]
    return {
        "origin": origin,
        "destination": dest,
        "run": descriptor(manifest),
        "mode": "live" if selection == "latest" else "replay",
        "departure": utc_text(departure),
        "distanceKm": round(distance),
        "durationMinutes": round(distance / 800 * 60),
        "peak": max(classes, key=CATEGORIES.index) if classes else "unavailable",
        "samples": points,
        "briefing": briefing,
        "modelVersion": manifest.get("model", {}).get("version"),
    }
