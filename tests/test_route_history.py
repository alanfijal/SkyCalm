import json

from scripts.route_history import OUTPUT, ROUTES, archive, match_reports


def test_archive_contains_five_real_runs_for_each_route():
    rows = list(archive())
    assert rows == [json.loads(line) for line in OUTPUT.read_text().splitlines()]
    assert len(rows) == 5 * len(ROUTES)
    assert len({(r["origin"], r["destination"], r["run_id"]) for r in rows}) == len(rows)
    flight = next(r for r in rows if r["origin"] == "EDI" and r["run_id"] == "gfs-20261121-06")
    assert flight["peak"] == "moderate" and flight["report_count"] == 1
    assert flight["reports"][0]["reported"] == "light"


def test_postflight_requires_point_time_height_and_counts_each_report_once():
    sample = {
        "lat": 52,
        "lon": -3,
        "altitudeFt": 35000,
        "at": "2026-11-21T14:00:00Z",
        "elapsedMinutes": 25,
        "category": "moderate",
    }
    report = {
        "kind": "report",
        "geometry": {"type": "Point", "coordinates": [-3, 52]},
        "id": "one",
        "from": sample["at"],
        "baseFt": 35000,
        "source": "AIREP",
        "intensity": "light",
    }
    bad = [
        report | changes
        for changes in (
            {"kind": "sigmet"},
            {"baseFt": None},
            {"baseFt": 24000},
            {"from": "2026-11-21T16:00:00Z"},
            {"geometry": {"type": "Point", "coordinates": [2, 52]}},
        )
    ]
    assert match_reports([sample], bad) == []
    hits = match_reports([sample, sample | {"lat": 52.05}], [report, report])
    assert len(hits) == 1 and hits[0]["forecast"] == "moderate" and hits[0]["reported"] == "light"
