"""Targeted scientific regression tests for V35R3I."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dayahead.v35r3i.contracts import (
    APR01_SLOTS,
    ARTIFACT_DIRNAME,
    BRANCH,
    FROZEN_IT_REFERENCE_KW,
    GPU_CAPACITY,
    PARENT_HEAD,
    REQUIRED_ARTIFACTS,
    SCENARIOS,
)
from dayahead.v35r3i.pipeline import ROOT, build


ART = ROOT / "dayahead" / "artifacts" / ARTIFACT_DIRNAME


@pytest.fixture(scope="session", autouse=True)
def artifacts() -> Path:
    return build()


def load(name: str) -> dict:
    return json.loads((ART / name).read_text(encoding="utf-8"))


def test_lineage_and_worktree() -> None:
    start = load("V35R3I_START_STATE.json")
    assert start["exact_parent_HEAD"] == PARENT_HEAD
    assert start["branch"] == BRANCH
    assert start["isolated_worktree"] is True
    assert start["push_performed"] is False and start["merge_performed"] is False


def test_required_artifacts_and_gated_pcc_absence() -> None:
    assert all((ART / name).is_file() for name in REQUIRED_ARTIFACTS)
    assert not (ART / "V35R3I_RW_RSP_AIDC_PCC_CANDIDATE.csv").exists()


@pytest.mark.parametrize("key", [
    "Apr01_realized_runtime_reads", "Apr01_future_end_reads",
    "Apr01_consumed_energy_reads", "future_node_assignment_reads",
    "Planning_reads", "Fresh_reads", "MESS_reads", "May_reads",
])
def test_causal_and_scope_read_firewall(key: str) -> None:
    assert load("V35R3I_ISOLATION_AUDIT.json")[key] == 0


def test_no_forbidden_execution_or_mutation() -> None:
    audit = load("V35R3I_ISOLATION_AUDIT.json")
    assert audit["Gurobi_runs"] == 0
    assert audit["XGBoost_training_runs"] == 0
    assert audit["grid_optimization_runs"] == 0
    assert audit["production_files_changed"] == 0
    assert audit["MESS_files_changed"] == 0
    assert audit["public_source_files_changed"] == 0


def test_scheduler_occupancy_shape_and_bounds() -> None:
    frame = pd.read_csv(ART / "V35R3I_RW_RSP_GPU_OCCUPANCY.csv")
    assert len(frame) == APR01_SLOTS
    for mode in ("RW", "RSP"):
        assert frame[f"N_active_{mode}"].between(0, GPU_CAPACITY).all()
        assert frame[f"N_idle_{mode}"].ge(0).all()
        assert np.allclose(frame[f"N_active_{mode}"] + frame[f"N_idle_{mode}"], GPU_CAPACITY)
        assert np.allclose(frame[f"component_sum_active_GPUs_{mode}"], frame[f"N_active_{mode}"])


def test_scheduler_regression() -> None:
    report = load("V35R3I_TEST_REPORT.json")["RSP_regression_checks"]
    assert all(report.values())
    occ = load("V35R3I_GPU_OCCUPANCY_CONSERVATION.json")
    assert occ["RW_saturated_slots"] == 96
    assert occ["RSP_saturated_slots"] == 59
    assert occ["RW_mean_active_GPUs"] == 624.0
    assert occ["RSP_mean_active_GPUs"] == pytest.approx(583.34375)
    assert occ["maximum_RW_minus_RSP_active_GPU_difference"] == 205.0


def test_expanded_coverage_distinguishes_jobs_and_gpu_hours() -> None:
    coverage = load("V35R3I_EXPANDED_FLEX_POWER_COVERAGE.json")
    assert coverage["temporal_jobs_total"] == 339
    assert coverage["partial_shared_temporal_jobs"] == 336
    assert coverage["jobs_covered_by_GPU_slot_model"] == 339
    assert coverage["temporal_requested_GPU_hours"] == 14832.0
    assert coverage["partial_shared_requested_GPU_hours"] == 14256.0
    assert coverage["GPU_hours_uncovered"] == 0.0
    assert coverage["GPU_hour_coverage_fraction"] == 1.0


def test_active_authority_is_h100_run_level() -> None:
    authority = load("V35R3I_H100_ACTIVE_GPU_POWER_AUTHORITY.json")
    stats = pd.read_parquet(ART / "V35R3I_H100_ACTIVE_GPU_RUN_STATISTICS.parquet")
    assert len(stats) == 2431
    assert stats["gpu_hardware"].eq("NVIDIA_H100_SXM_80GB").all()
    assert stats["statistical_unit"].eq("EXPERIMENT_RUN").all()
    assert stats["power_boundary"].eq("GPU_ONLY_POWER").all()
    assert "NOT_RAW_SAMPLE_WEIGHTED" in authority["statistics_basis"]
    assert authority["job_class_mapping_used"] is False


def test_active_scenario_values() -> None:
    values = load("V35R3I_H100_ACTIVE_GPU_POWER_AUTHORITY.json")["active_power_W_per_GPU"]
    assert values["LOW"] == pytest.approx(469.25416154435004)
    assert values["CENTER"] == pytest.approx(620.2239090195797)
    assert values["HIGH"] == pytest.approx(656.5288975728544)


def test_idle_is_direct_and_not_tuned() -> None:
    idle = load("V35R3I_H100_IDLE_GPU_POWER_AUTHORITY.json")
    assert idle["classification"] == "IDLE_AUTHORITY_DIRECT"
    assert idle["evidence_level"] == "LEVEL_A"
    assert idle["sensor_boundary"] == "NVML PER_GPU COMPONENT"
    assert idle["allocated"] == "NO"
    assert idle["scheduler_benefit_used_for_tuning"] is False
    assert idle["scenario_idle_power_W_per_GPU"] == {"LOW": 72.4, "CENTER": 72.5, "HIGH": 72.6}


def test_exact_three_ordered_nonnegative_scenarios() -> None:
    payload = load("V35R3I_GPU_SLOT_POWER_SCENARIOS.json")
    assert payload["scenario_count"] == 3
    assert set(payload["scenarios"]) == set(SCENARIOS)
    increments = [payload["scenarios"][name]["delta_p_W_per_GPU"] for name in SCENARIOS]
    assert all(value >= 0 for value in increments)
    assert increments == sorted(increments)
    assert payload["parameters_optimized"] is False


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_power_delta_identity_and_equal_occupancy_zero(scenario: str) -> None:
    power = pd.read_csv(ART / "V35R3I_RW_RSP_GPU_COMPONENT_POWER.csv")
    config = load("V35R3I_GPU_SLOT_POWER_SCENARIOS.json")["scenarios"][scenario]
    expected = power["N_active_delta_RSP_minus_RW"] * config["delta_p_W_per_GPU"] / 1000.0
    assert np.allclose(power[f"Delta_P_GPU_{scenario}_kW"], expected)
    equal = power["N_active_delta_RSP_minus_RW"].eq(0)
    assert np.allclose(power.loc[equal, f"Delta_P_GPU_{scenario}_kW"], 0.0)


def test_power_direction_is_robust() -> None:
    direction = load("V35R3I_POWER_DIRECTION_ROBUSTNESS.json")
    assert direction["slots_robustly_lower_under_RSP"] == 37
    assert direction["slots_robustly_equal"] == 59
    assert direction["slots_uncertain"] == 0
    assert direction["slots_higher"] == 0
    assert direction["all_nonzero_differences_sign_robust"] is True


def test_energy_units_and_sign() -> None:
    payload = load("V35R3I_RW_RSP_GPU_COMPONENT_ENERGY.json")
    assert payload["slot_hours"] == 0.25
    assert payload["units"] == {"daily_energy": "kWh", "trajectory": "kW"}
    for scenario in SCENARIOS:
        values = payload["by_scenario"][scenario]
        assert values["daily_energy_delta_RSP_minus_RW_kWh"] < 0
        assert values["maximum_slot_reduction_kW"] > 0
        assert values["W1"]["mean"] < 0
        assert values["W3"]["mean"] < 0
        assert values["W5"]["mean"] < 0


def test_partial_shared_double_count_firewall() -> None:
    shared = load("V35R3I_PARTIAL_SHARED_GPU_CONSERVATION.json")
    assert shared["PARTIAL_SHARED_INCLUDED_IN_POWER_ACCOUNTING"] == "YES"
    assert shared["SHARED_JOB_POWER_ATTRIBUTION_USED"] == "NO"
    assert shared["FULL_NODE_COEFFICIENT_APPLIED_PER_SHARED_JOB"] == "NO"
    assert shared["AGGREGATE_GPU_DELTA_REQUIRES_NODE_PACKING"] == "NO"
    assert shared["double_count_conservation_status"] == "PASS"


def test_workload_classes_not_invented() -> None:
    uncertainty = load("V35R3I_WORKLOAD_CLASS_UNCERTAINTY.json")
    assert uncertainty["actual_Kestrel_job_class_mapping_available"] is False
    assert uncertainty["job_classes_invented"] is False
    assert uncertainty["composition_only_directional_claim_authorized"] is False


def test_frozen_baseline_scale_and_no_beta() -> None:
    scale = load("V35R3I_FROZEN_AIDC_POWER_SCALE_AUDIT.json")
    assert scale["AIDC_DELTA_SCALE_BINDING"] == "PASS"
    assert scale["physical_kW_delta_scale_factor"] == 1.0
    assert scale["arbitrary_beta_AIDC_introduced"] is False
    assert scale["Dataset312_magnitude_fit_to_existing_peak"] is False
    assert scale["ABSOLUTE_WHOLE_NODE_POWER_RECONSTRUCTED"] == "NO"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_it_candidate_is_frozen_baseline_plus_delta(scenario: str) -> None:
    frame = pd.read_csv(ART / "V35R3I_RW_RSP_AIDC_IT_CANDIDATE.csv")
    assert np.allclose(frame["P_IT_RW_FROZEN_kW"], FROZEN_IT_REFERENCE_KW)
    assert np.allclose(
        frame[f"P_IT_RSP_{scenario}_kW"],
        frame["P_IT_RW_FROZEN_kW"] + frame[f"Delta_P_GPU_{scenario}_kW"],
    )


def test_non_gpu_primary_delta_is_zero() -> None:
    payload = load("V35R3I_NON_GPU_DELTA_ASSUMPTION.json")
    assert payload["primary_scheduler_induced_non_GPU_component_delta_kW"] == 0.0
    assert payload["CPU_power_scaled_by_requested_GPU_count"] is False
    assert payload["RAPL_mixed_into_primary_CENTER"] is False


def test_strict_f0_comparison() -> None:
    payload = load("V35R3I_STRICT_F0_VS_EXPANDED_COMPARISON.json")
    assert payload["strict_F0_controllable_jobs"] == 3
    assert payload["strict_F0_controllable_GPU_hours"] == 576.0
    assert payload["expanded_job_count_multiple"] == 113.0
    assert payload["expanded_GPU_hour_multiple"] == 25.75
    assert payload["expanded_partial_shared_GPU_hours"] == 14256.0


def test_site_binding_gates_c1_and_pcc() -> None:
    binding = load("V35R3I_SITE_BINDING_AUDIT.json")
    assert binding["existing_site_rack_PCC_binding_available"] == "NO"
    assert binding["SITE_BINDING_STATUS"] == "MISSING_FOR_GRID_INTEGRATION"
    assert binding["aggregate_IT_characterization_blocked"] is False
    assert binding["C1_conversion_authorized"] is False
    assert binding["PCC_candidate_generated"] is False


def test_authority_and_next_step_decisions() -> None:
    decision = load("V35R3I_SEMI_EMPIRICAL_AUTHORITY_DECISION.json")
    next_step = load("V35R3I_NEXT_STEP_DECISION.json")
    assert decision["semi_empirical_authority"] == "SE3_FROZEN_AIDC_IT_DELTA_CANDIDATE"
    assert decision["primary_classification"] == "V35R3I_EXPANDED_H100_POWER_BRIDGE_PASS"
    assert next_step["EXPANDED_FLEX_POWER_READY"] == "YES"
    assert next_step["AIDC_GRID_INTEGRATION_NEXT"] == "YES_AFTER_SITE_BINDING"
    assert next_step["PRODUCTION_INTEGRATION_RECOMMENDED"] == "NO"


def test_literature_boundaries_are_not_transferred() -> None:
    payload = load("V35R3I_PUBLIC_POWER_LITERATURE_AUTHORITY.json")
    assert len(payload["sources"]) == 4
    assert payload["preprint_called_peer_reviewed_journal"] is False
    assert payload["whole_node_values_transferred_or_divided_into_Kestrel"] is False
    assert all(source["GPU_hardware"].find("H100") >= 0 for source in payload["sources"])


def test_final_review_has_exact_numbered_fields_and_23_answers() -> None:
    review = load("V35R3I_FINAL_REVIEW.json")
    numbered = []
    for section, values in review.items():
        if section not in {"artifact_id", "QUESTIONS"}:
            numbered.extend(int(key.split("_", 1)[0]) for key in values)
    assert sorted(numbered) == list(range(1, 85))
    assert set(review["QUESTIONS"]) == {f"Q{i}" for i in range(1, 24)}
