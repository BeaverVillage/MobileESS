"""Targeted V35R3J scale-closure and freeze tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dayahead.v35r3j.contracts import (
    ARTIFACT_DIRNAME, BRANCH, GPU_CAPACITY, PARENT_HEAD, REQUIRED_ARTIFACTS, SCENARIOS,
)
from dayahead.v35r3j.pipeline import ROOT, build


ART = ROOT / "dayahead" / "artifacts" / ARTIFACT_DIRNAME


@pytest.fixture(scope="session", autouse=True)
def artifacts() -> Path:
    return build()


def load(name: str) -> dict:
    return json.loads((ART / name).read_text(encoding="utf-8"))


def test_exact_lineage() -> None:
    start = load("V35R3J_START_STATE.json")
    assert start["exact_parent_HEAD"] == PARENT_HEAD
    assert start["branch"] == BRANCH
    assert start["isolated_worktree"] is True
    assert start["push_performed"] is False and start["merge_performed"] is False


def test_required_artifacts() -> None:
    assert all((ART / name).is_file() for name in REQUIRED_ARTIFACTS)


def test_v35r3i_inputs_byte_conserved() -> None:
    authority = load("V35R3J_V35R3I_INPUT_AUTHORITY.json")
    assert authority["V35R3I_INPUT_SHA_CONSERVATION"] == "PASS"
    assert len(authority["files"]) == 10
    assert all(item["unchanged_from_parent"] for item in authority["files"])
    assert authority["Dataset312_raw_statistics_recomputed"] is False
    assert authority["temporal_cohort_altered"] is False


@pytest.mark.parametrize("key", [
    "Apr01_realized_runtime_reads", "Apr01_future_end_reads", "Apr01_consumed_energy_reads",
    "Planning_reads", "Fresh_reads", "MESS_reads", "Apr02_plus_outcome_reads", "May_reads",
])
def test_read_firewall(key: str) -> None:
    assert load("V35R3J_ISOLATION_AUDIT.json")[key] == 0


def test_idc_firewall() -> None:
    audit = load("V35R3J_ISOLATION_AUDIT.json")
    assert audit["IDC_location_optimization_runs"] == 0
    assert audit["IDC_LOCATION_CHANGED"] == "NO"
    assert audit["SITE_LOCATION_AUDIT_PERFORMED"] == "NO"
    assert audit["NEW_PCC_MAPPING_CREATED"] == "NO"


def test_scope_firewall() -> None:
    audit = load("V35R3J_ISOLATION_AUDIT.json")
    assert audit["C1_runs"] == 0 and audit["PCC_trajectory_generations"] == 0
    assert audit["Gurobi_runs"] == 0 and audit["XGBoost_runs"] == 0
    assert audit["Grid_objective_used_for_scale_selection"] == "NO"
    assert audit["production_files_changed"] == audit["MESS_files_changed"] == audit["public_source_files_changed"] == 0


def test_reference_lineage_and_semantics() -> None:
    lineage = load("V35R3J_FROZEN_IT_REFERENCE_LINEAGE.json")
    assert lineage["frozen_AIDC_IT_reference_kW"] == pytest.approx(406.77599381381907)
    assert lineage["frozen_GPU_capacity"] == GPU_CAPACITY
    assert lineage["c_ref_W_per_requested_GPU"] == pytest.approx(406.77599381381907 * 1000 / 624)
    assert lineage["reference_semantic_classification"] == "C_TESTBED_EQUIVALENT_IT_ACTIVE_STATE_ANCHOR"
    assert lineage["coefficient_semantic_classification"].startswith("D_HOMOGENEOUS_RESOURCE_POWER_PROXY")
    assert lineage["direct_physical_whole_IT_measurement"] is False


def test_direct_physical_comparison_rejected() -> None:
    boundary = load("V35R3J_PHYSICAL_BOUNDARY_COMPATIBILITY.json")
    assert boundary["direct_comparison_624_times_NVML_active_vs_frozen_reference"] == "NO"
    assert boundary["direct_hardware_containment_required"] is False
    assert boundary["measured_GPU_component_renamed_whole_node_IT"] is False


def test_inconsistency_reproduced() -> None:
    audit = load("V35R3J_V35R3I_SCALE_INCONSISTENCY_AUDIT.json")
    assert audit["by_scenario"]["LOW"]["full_active_measured_GPU_component_kW"] == pytest.approx(292.8145968036744)
    assert audit["by_scenario"]["CENTER"]["full_active_measured_GPU_component_kW"] == pytest.approx(387.01971922821775)
    assert audit["by_scenario"]["HIGH"]["full_active_measured_GPU_component_kW"] == pytest.approx(409.67403208546114)
    assert audit["by_scenario"]["HIGH"]["residual_if_direct_kW"] < 0
    assert audit["HIGH_negative_residual_verified"] is True


def test_only_predeclared_methods() -> None:
    methods = load("V35R3J_SCALE_METHOD_COMPARISON.json")
    assert set(methods["methods"]) == {"M0", "M1", "M2", "M3"}
    assert methods["predeclared_methods_only"] is True
    assert methods["grid_Fresh_MESS_or_location_input_used"] is False
    assert methods["arbitrary_beta_introduced"] is False
    assert all(item["reason"] for item in methods["methods"].values())


def test_method_hierarchy_selects_m2() -> None:
    decision = load("V35R3J_SCALE_METHOD_DECISION.json")
    assert decision["selected_method"] == "M2_CONSERVATIVE_DUAL_ANCHOR_MODULATION"
    assert decision["selection_hierarchy_step"] == 2
    assert decision["grid_result_used"] is False


def test_final_swing_exact_and_ordered() -> None:
    decision = load("V35R3J_SCALE_METHOD_DECISION.json")
    swing = decision["final_swing_W_per_GPU"]
    assert swing["LOW"] == pytest.approx(396.85416154435006)
    assert swing["CENTER"] == pytest.approx(547.7239090195797)
    assert swing["HIGH"] == pytest.approx(579.7981786096108)
    assert 0 <= swing["LOW"] <= swing["CENTER"] <= swing["HIGH"]
    assert decision["original_LOW_CENTER_HIGH_changed"] == "YES_HIGH_ONLY"
    assert decision["measured_active_or_idle_values_modified"] is False


def test_expanded_cohort_preserved() -> None:
    cohort = load("V35R3J_EXPANDED_COHORT_REGRESSION.json")
    assert cohort["status"] == "PASS"
    assert cohort["temporal_jobs"] == 339 and cohort["partial_shared_jobs"] == 336
    assert cohort["temporal_GPU_hours"] == 14832.0
    assert cohort["partial_shared_GPU_hours"] == 14256.0
    assert cohort["job_count_power_coverage"] == cohort["GPU_hour_power_coverage"] == 1.0


def test_partial_shared_conservation() -> None:
    shared = load("V35R3J_PARTIAL_SHARED_CONSERVATION.json")
    assert shared["PARTIAL_SHARED_INCLUDED"] == "YES"
    assert shared["SHARED_JOB_POWER_ATTRIBUTION_USED"] == "NO"
    assert shared["NODE_PACKING_REQUIRED_FOR_AGGREGATE_DELTA"] == "NO"
    assert shared["GPU_SLOT_DOUBLE_COUNT"] == 0 and shared["GPU_CAPACITY_EXCEEDANCE"] == 0


def test_final_trajectory_shape_and_formula() -> None:
    frame = pd.read_csv(ART / "V35R3J_RW_RSP_FINAL_AIDC_IT.csv")
    swing = load("V35R3J_SCALE_METHOD_DECISION.json")["final_swing_W_per_GPU"]
    assert len(frame) == 96
    for scenario in SCENARIOS:
        expected = frame["P_IT_RW_FROZEN_kW"] + frame["N_active_delta_RSP_minus_RW"] * swing[scenario] / 1000
        assert np.allclose(frame[f"P_IT_RSP_{scenario}_kW"], expected)
        assert frame[f"P_IT_RSP_{scenario}_kW"].ge(0).all()
        assert frame[f"Delta_P_IT_{scenario}_kW"].le(1e-12).all()


def test_rw_baseline_exactly_preserved() -> None:
    final = pd.read_csv(ART / "V35R3J_RW_RSP_FINAL_AIDC_IT.csv")
    source = pd.read_csv(ROOT / "dayahead/artifacts/v35r3i_semiempirical_h100_gpu_slot_power_bridge/V35R3I_RW_RSP_AIDC_IT_CANDIDATE.csv")
    assert np.array_equal(final["P_IT_RW_FROZEN_kW"].to_numpy(), source["P_IT_RW_FROZEN_kW"].to_numpy())


def test_full_active_reference_preserved() -> None:
    summary = load("V35R3J_RW_RSP_FINAL_AIDC_IT_SUMMARY.json")
    assert summary["FULL_ACTIVE_REFERENCE_PRESERVED"] == "YES"
    assert summary["RW_baseline_numerically_preserved"] is True
    for scenario in SCENARIOS:
        assert summary["by_trajectory"][scenario]["maximum_kW"] == pytest.approx(summary["by_trajectory"]["RW"]["maximum_kW"])


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_trajectory_direction_counts(scenario: str) -> None:
    result = load("V35R3J_RW_RSP_FINAL_AIDC_IT_SUMMARY.json")["by_trajectory"][scenario]
    assert result["slots_below_RW"] == 37
    assert result["slots_equal_RW"] == 59
    assert result["slots_above_RW"] == 0


def test_windows_reused() -> None:
    windows = load("V35R3J_CRITICAL_WINDOW_POWER.json")
    assert windows["definitions_reused_unchanged"] == {"W1": [74], "W3": [73, 74, 75], "W5": [72, 73, 74, 75, 76]}
    for window in ("W1", "W3", "W5"):
        for scenario in SCENARIOS:
            assert windows["windows"][window][scenario]["mean_delta_kW"] < 0


def test_daily_energy_separates_achieved_and_mass() -> None:
    energy = load("V35R3J_DAILY_IT_ENERGY.json")
    assert energy["achieved_Apr01_reduction_distinct_from_cohort_flexibility_mass"] is True
    for scenario in SCENARIOS:
        assert energy["RSP_minus_RW_daily_energy_delta_kWh"][scenario] < 0


def test_strict_comparison_preserved() -> None:
    compare = load("V35R3J_STRICT_F0_EXPANDED_FINAL_COMPARISON.json")
    assert compare["strict_F0_jobs"] == 3 and compare["strict_F0_GPU_hours"] == 576.0
    assert compare["expanded_jobs"] == 339 and compare["expanded_GPU_hours"] == 14832.0
    assert compare["job_count_multiple"] == 113.0 and compare["GPU_hour_multiple"] == 25.75
    for scenario in SCENARIOS:
        assert compare["scale_consistent_expanded_flexibility_energy_mass_kWh"][scenario] == pytest.approx(
            25.75 * compare["scale_consistent_strict_F0_flexibility_energy_mass_kWh"][scenario]
        )


def test_final_contract_firewalls() -> None:
    contract = load("V35R3J_EXPANDED_AIDC_POWER_CONTRACT.json")
    assert contract["selected_scale_closure_method"] == "M2_CONSERVATIVE_DUAL_ANCHOR_MODULATION"
    assert contract["PRIMARY_NON_GPU_DELTA_KW"] == 0.0
    assert contract["FULL_ACTIVE_REFERENCE_PRESERVED"] == "YES"
    assert contract["ABSOLUTE_WHOLE_NODE_POWER_RECONSTRUCTED"] == "NO"
    assert contract["arbitrary_beta_introduced"] == "NO"
    assert contract["penetration_rescaling_introduced"] == "NO"


def test_authority_and_next_step() -> None:
    authority = load("V35R3J_AUTHORITY_DECISION.json")
    next_step = load("V35R3J_NEXT_STEP_DECISION.json")
    assert authority["authority_level"] == "AF2_EXPANDED_AIDC_IT_CONTRACT_FROZEN"
    assert authority["primary_classification"] == "V35R3J_AIDC_IT_SCALE_PASS_WITH_CONSERVATIVE_NORMALIZATION"
    assert next_step["EXPANDED_AIDC_POWER_CONTRACT_READY"] == "YES"
    assert next_step["AIDC_AGGREGATE_SCIENCE_FREEZE"] == "YES"
    assert next_step["AIDC_NEXT"] == "DOWNSTREAM_GRID_CERTIFICATION_AFTER_MESS_FREEZE"
    assert next_step["PRODUCTION_INTEGRATION_RECOMMENDED"] == "NO"
    assert next_step["another_public_H100_dataset_required"] == "NO"


def test_final_review_exact_fields_and_questions() -> None:
    review = load("V35R3J_FINAL_REVIEW.json")
    numbers = []
    for section, values in review.items():
        if section not in {"artifact_id", "QUESTIONS"}:
            numbers.extend(int(key.split("_", 1)[0]) for key in values)
    assert sorted(numbers) == list(range(1, 87))
    assert set(review["QUESTIONS"]) == {f"Q{n}" for n in range(1, 22)}
