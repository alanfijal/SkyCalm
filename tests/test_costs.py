from dataclasses import replace
from pathlib import Path

import pytest

from scripts.estimate_cost import SCENARIOS, cost_table, estimate


def test_public_ip_is_charged_only_when_a_task_runs() -> None:
    label = "Network (IP or endpoints + relay)"
    assert estimate(SCENARIOS["Idle month"])[label] == 0
    assert estimate(SCENARIOS["Demo month"])[label] == pytest.approx(24 * 0.1 * 0.005)


def test_each_private_az_adds_four_endpoint_hour_charges() -> None:
    for scenario in SCENARIOS.values():
        one = sum(estimate(scenario, private_azs=1).values())
        two = sum(estimate(scenario, private_azs=2).values())
        assert two - one == pytest.approx(4 * scenario.days * 24 * 0.0105)


def test_private_staging_and_data_are_charged_when_a_grid_runs() -> None:
    label = "Network (IP or endpoints + relay)"
    w = replace(SCENARIOS["Idle month"], runs=1)
    baseline = estimate(SCENARIOS["Idle month"], private_azs=1)[label]
    delta = estimate(w, private_azs=1)[label] - baseline
    assert delta == pytest.approx(1.05 * 0.01 + 120 * 0.0000133334 + 13 * 0.0000052)


def test_one_training_cycle_includes_both_processing_jobs_and_volume_time() -> None:
    label = "SageMaker jobs, volumes and KMS"
    idle = SCENARIOS["Idle month"]
    delta = estimate(replace(idle, training_cycles=1))[label] - estimate(idle)[label]
    assert delta == pytest.approx(2 * 0.122 + 30 / 720 * (0.10 + 0.146) + 0.006)


def test_invalid_network_option_fails() -> None:
    with pytest.raises(ValueError):
        estimate(SCENARIOS["Demo day"], private_azs=3)


def test_published_cost_table_matches_the_calculation() -> None:
    report = Path(__file__).resolve().parents[1] / "docs" / "costs.md"
    assert cost_table() in report.read_text()
