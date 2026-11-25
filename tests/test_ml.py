from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from ml.evaluate import approval, metrics
from ml.features import nearest_lead
from ml.prepare import split
from services.forecast.schema import CATEGORIES


def test_matching_uses_only_available_forecasts_and_breaks_lead_ties_earlier():
    issue = datetime(2026, 11, 21, 6, tzinfo=UTC)
    assert nearest_lead(issue, issue - timedelta(seconds=1)) is None
    assert nearest_lead(issue, issue + timedelta(minutes=90)) == 0
    assert nearest_lead(issue, issue + timedelta(minutes=91)) == 3
    assert nearest_lead(issue, issue + timedelta(hours=36, seconds=1)) is None


def test_chronological_holdouts_remove_reused_cycles():
    rows = [
        {"id": str(d), "observed": f"2026-11-{20 + d}T12:00:00Z", "run": f"run{d}"}
        for d in range(5)
    ]
    rows.insert(4, {**rows[3], "observed": "2026-11-24T08:00:00Z"})
    parts, removed = split(rows)
    assert removed == 1 and [len(v) for v in parts.values()] == [3, 1, 1]
    assert max(r["observed"] for r in parts["train"]) < parts["validation"][0]["observed"]
    with pytest.raises(ValueError):
        split(rows[:2])


def test_missing_positives_and_empty_sector_block_promotion():
    perfect = metrics([1], [[0, 1, 0, 0]])
    assert perfect["classes"]["light"]["calibration"][-1]["observedRate"] == 1
    assert perfect["classes"]["smooth"]["recall"] is None
    report = {
        "europe": {"model": perfect, "baseline": metrics([1], [[1, 0, 0, 0]])},
        "north_atlantic": {"model": metrics([], []), "baseline": metrics([], [])},
    }
    assert approval(report)["status"] == "PendingManualApproval"


def test_promotion_requires_european_gain_and_no_regional_recall_loss():
    labels = list(range(len(CATEGORIES))) * 5
    good = [[int(c == y) for c in range(4)] for y in labels]
    worse = deepcopy(good)
    worse[1] = worse[0]
    sector = {"model": metrics(labels, good), "baseline": metrics(labels, worse)}
    report = {"europe": sector, "north_atlantic": deepcopy(sector)}
    assert approval(report)["status"] == "Approved"
    report["north_atlantic"]["model"]["classes"]["severe"]["recall"] = 0.8
    assert approval(report)["status"] == "PendingManualApproval"
