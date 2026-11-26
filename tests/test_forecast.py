import json
import math
from array import array
from datetime import UTC, datetime

import pytest

from services.forecast.api import RequestError, airports, respond, search
from services.forecast.http import response
from services.forecast.product import CAPE_LIMITS, TI1_LIMITS, category, interpolate, sample
from services.forecast.route import route_points
from services.forecast.schema import HEIGHT, MISSING, PLANES, WIDTH
from services.forecast.storage import REPLAY_ROOT, LocalStore

PIN = "gfs-20261124-12"
CLOCK = datetime(2026, 11, 24, 16, tzinfo=UTC)


def params(**changes):
    return {
        "origin": "BCN",
        "destination": "ARN",
        "run": PIN,
        "departure": "2026-11-24T18:00:00Z",
        **changes,
    }


def test_great_circle_endpoints_spacing_altitude_and_reverse():
    a, b = airports()["BCN"], airports()["ARN"]
    distance, route = route_points(a, b, CLOCK)
    back, reverse = route_points(b, a, CLOCK)
    assert back == pytest.approx(distance)
    assert 2290 < distance < 2340
    assert len(route) == math.ceil(distance / 25) + 1
    for i, j in ((0, a), (-1, b)):
        assert route[i]["lat"] == pytest.approx(j["lat"], abs=1e-6)
        assert route[i]["altitudeFt"] == j["elevationFt"]
    middle = route[len(route) // 2]
    assert middle["altitudeFt"] == 35000
    assert middle["phase"] == "cruise"
    assert reverse[-1]["lon"] == pytest.approx(route[0]["lon"], abs=1e-6)
    _, short = route_points(airports()["LHR"], airports()["LGW"], CLOCK)
    assert max(p["altitudeFt"] for p in short) < 10000


def test_thresholds_include_boundaries_and_missing_is_distinct():
    assert interpolate(5.0, None, 0) == 5
    assert interpolate(None, 9.0, 1) == 9
    assert interpolate(None, 9.0, 0.5) is None
    assert [category(x, TI1_LIMITS) for x in (0, 2, 6, 12)] == [
        "smooth",
        "light",
        "moderate",
        "severe",
    ]
    assert category(1500, CAPE_LIMITS) == "moderate"
    cube = array("h", [MISSING]) * (WIDTH * HEIGHT * PLANES)
    p = {"lat": 45.25, "lon": 2.5, "altitudeFt": 0, "phase": "climb"}
    assert sample({0: cube}, 0, p)["category"] == "unavailable"
    assert sample({}, 37, p)["method"] == "horizon"


def test_wind_frames_are_optional_and_partial_cycles_stay_unavailable(tmp_path, monkeypatch):
    store = LocalStore(tmp_path, REPLAY_ROOT)
    manifest = store.manifest(PIN)
    frames = json.loads(
        (REPLAY_ROOT.parents[3] / "web/public/data/wind" / (PIN + ".json")).read_text()
    )
    assert len(frames) == len(manifest["leads"]) == 13
    for lead, frame in zip(manifest["leads"], frames, strict=True):
        lead["wind250"] = frame
    monkeypatch.setattr(store, "manifest", lambda _: manifest)
    assert respond("/api/forecast", params(wind="1"), store, CLOCK)["wind250"] == frames
    assert "wind250" not in respond("/api/forecast", params(), store, CLOCK)
    del manifest["leads"][1]["wind250"]
    assert "wind250" not in respond("/api/forecast", params(wind="1"), store, CLOCK)


def test_bilinear_and_temporal_interpolation_use_time_and_position():
    cube = array("h", [0]) * (WIDTH * HEIGHT * PLANES)
    count = WIDTH * HEIGHT
    for i in range(count):
        row, col = divmod(i, WIDTH)
        cube[i] = 100 + 100 * row + 20 * col
        cube[2 * count + i] = 7500
    later = array("h", cube)
    for i in range(count):
        later[i] += 600
    p = {"lat": 34.5, "lon": -24.5, "altitudeFt": 0, "phase": "climb"}
    result = sample({0: cube, 3: later}, 1.5, p)
    assert result["cape"] == 460
    assert sample({36: cube}, 36, {**p, "lat": 72, "lon": 45})["cape"] is not None


def test_real_replay_is_stable_and_windows_and_categories_are_explicit(tmp_path):
    store = LocalStore(tmp_path, REPLAY_ROOT)
    f = respond("/api/forecast", params(), store, CLOCK)
    later = respond("/api/forecast", params(departure="2026-11-24T19:00:00+01:00"), store)
    assert f == later
    assert f["mode"] == "replay" and f["run"]["runId"] == PIN
    assert f["durationMinutes"] == 174 and len(f["samples"]) == 94
    assert {p["method"] for p in f["samples"]} == {"cape", "ti1"}
    assert f["peak"] == "moderate"
    edge = respond("/api/forecast", params(departure="2026-11-25T23:50:00Z"), store, CLOCK)
    assert edge["samples"][0]["category"] != "unavailable"
    assert edge["samples"][-1]["method"] == "horizon"


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"origin": "JFK"}, "outside_coverage"),
        ({"origin": "ZZZZZZ"}, "unknown_airport"),
        ({"destination": "BCN"}, "same_airport"),
        ({"run": "../local"}, "invalid_run"),
        ({"departure": "2026-11-24T18:00"}, "invalid_time"),
        ({"departure": "2026-11-24T11:00:00Z"}, "before_run"),
        ({"departure": "2026-11-26T01:00:00Z"}, "too_early"),
        ({"run": "latest"}, "no_live_run"),
        ({"run": "gfs-20261124-06"}, "unknown_run"),
    ],
)
def test_rejections_have_actionable_error_codes(tmp_path, changes, error):
    with pytest.raises(RequestError) as exc:
        respond("/api/forecast", params(**changes), LocalStore(tmp_path, REPLAY_ROOT), CLOCK)
    assert exc.value.code == error


def test_stale_latest_requires_explicit_replay(tmp_path):
    store = LocalStore(tmp_path, REPLAY_ROOT)
    manifest = store.manifest(PIN)
    store.publish(REPLAY_ROOT / PIN, manifest)
    with pytest.raises(RequestError) as exc:
        respond("/api/forecast", params(run="latest"), store, datetime(2026, 12, 1, tzinfo=UTC))
    assert exc.value.code == "stale_run"
    assert respond("/api/forecast", params(run="latest"), store, CLOCK)["mode"] == "live"


def test_airport_search_and_invalid_http_input(tmp_path):
    assert search("stockholm")[0]["country"] == "SE"
    assert search("JFK")[0]["code"] == "JFK"
    store = LocalStore(tmp_path, REPLAY_ROOT)
    r = response("GET", "/api/airports", "q=BCN&q=JFK", store, "test")
    assert r["statusCode"] == 400 and json.loads(r["body"])["code"] == "invalid_query"
    assert response("POST", "/api/forecast", "", store, "test")["statusCode"] == 405


def test_timetable_duration_reaches_the_scheduled_arrival(tmp_path):
    store = LocalStore(tmp_path, REPLAY_ROOT)
    timed = respond("/api/forecast", params(arrival="2026-11-24T21:55:00+01:00"), store, CLOCK)
    assert timed["durationMinutes"] == 175
    assert timed["samples"][-1]["at"] == "2026-11-24T20:55:00Z"
    for invalid in ("2026-11-24T17:00:00Z", "2026-11-26T00:00:00Z", "2026-11-24T21:00"):
        with pytest.raises(RequestError) as exc:
            respond("/api/forecast", params(arrival=invalid), store, CLOCK)
        assert exc.value.code == "invalid_arrival"
