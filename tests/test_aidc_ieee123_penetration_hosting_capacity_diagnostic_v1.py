import json
from pathlib import Path

import pytest

from dayahead.run_aidc_ieee123_penetration_hosting_capacity_diagnostic_v1 import (
    BETA_CANDIDATES,
    CHECKPOINT_HEAD,
)


REPO = Path(__file__).resolve().parents[1]
PATH = REPO / "dayahead/artifacts/v16_2/AIDC_IEEE123_PENETRATION_HOSTING_CAPACITY_DIAGNOSTIC_V1.json"


def _report() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_penetration_family_and_april_loader_firewall_are_frozen() -> None:
    report = _report()
    assert BETA_CANDIDATES == (0.25, 0.50, 0.75, 1.00)
    assert report["checkpoint"]["head"] == CHECKPOINT_HEAD
    coverage = report["april_coverage"]
    assert coverage["included_day_count"] == 29
    assert coverage["included_dates"] == [f"2025-04-{day:02d}" for day in range(2, 31)]
    assert [row["operating_day"] for row in coverage["excluded_dates"]] == ["2025-04-01"]
    assert coverage["loader_firewall"]["may_operating_day_row_materialization_count"] == 0
    assert coverage["loader_firewall"]["june_operating_day_row_materialization_count"] == 0


def test_discrete_reference_and_fresh_ac_results_are_complete() -> None:
    report = _report()
    planning = report["discrete_beta_day_planning_results"]
    fresh = report["discrete_beta_day_fresh_ac_results"]
    assert len(planning) == len(fresh) == 29 * 4
    assert all(row["reference_contract"]["service_parity_max_abs_nodeh"] <= 1e-8 for row in planning)
    assert all(row["reference_contract"]["reference_gpu_cap_max_violation"] <= 1e-8 for row in planning)
    assert all(row["convergence_count"] == 96 for row in fresh)
    summary = {row["beta_AIDC"]: row for row in report["discrete_candidate_summary"]}
    assert summary[0.25] == {
        "beta_AIDC": 0.25,
        "planning_all_april_pass": False,
        "fresh_ac_all_april_pass": True,
        "combined_pass": False,
    }
    assert all(not row["combined_pass"] for row in summary.values())


def test_continuous_threshold_proves_material_planning_ac_disagreement() -> None:
    report = _report()
    continuous = report["continuous_hosting_capacity"]
    assert continuous["beta_reference_HC_max"] == pytest.approx(0.01660249609375)
    assert continuous["planning_beta_max"] == pytest.approx(0.01660249609375)
    assert continuous["fresh_ac_beta_max"] == pytest.approx(0.33203125)
    assert continuous["limiting_day"] == "2025-04-17"
    assert continuous["limiting_constraint"]["family"] == "voltage_lower"
    assert continuous["limiting_constraint"]["bus"] == "114"
    assert continuous["limiting_constraint"]["phase"] == "A"
    assert continuous["limiting_constraint"]["time_index"] == 66
    assert report["planning_ac_disagreement"]["material"] is True
    assert report["classification"] == "PEN_CLASS_C_PLANNING_AC_DISAGREEMENT"
    assert report["beta_candidate_recommended"] is None
    assert report["recommendation_activated"] is False
    assert report["post_selection_b3_feasibility_only"]["status"] == "NOT_RUN_NO_RECOMMENDED_DISCRETE_BETA"


def test_physical_scaling_and_authority_change_counters_are_zero() -> None:
    report = _report()
    physical = report["physical_consistency"]
    for key, value in physical.items():
        if key.endswith(("_max_abs_error", "_change_count")):
            assert value == 0
    for key in (
        "scientific_authority_changes", "alpha_grid_changes", "native_feeder_rating_changes",
        "u080_changes", "kappa_changes", "PUE_changes", "PF_changes",
        "may_scientific_loader_access_count", "june_scientific_loader_access_count",
    ):
        assert report[key] == 0
    assert report["downstream_call_counts"] == {"G13": 0, "G14": 0, "C12": 0}
