from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

import pandas as pd

from dayahead.v39c.contracts import (
    ARTIFACT_ROOT,
    CLASSIFICATION,
    EXPECTED_GPU_CAPACITY,
    EXPECTED_NODE_CAPACITY,
    EXPECTED_TOP_SEVEN,
    EXPECTED_WEIGHT_ORDER,
    GPU_PER_NODE,
    GPU_TOTAL,
    NODE_TOTAL,
    START_HEAD,
)
from dayahead.v39c.freeze import construct_capacity, load_facility_prior, sha256_file


REPO = Path(__file__).resolve().parents[2]
ARTIFACT = REPO / ARTIFACT_ROOT


def j(name: str) -> dict:
    return json.loads((ARTIFACT / name).read_text(encoding="utf-8"))


def test_capacity_construction_conserves_156_nodes_and_624_gpus() -> None:
    weights, _ = load_facility_prior(REPO)
    result = construct_capacity(weights)
    assert sum(result["site_nodes"].values()) == NODE_TOTAL == 156
    assert sum(result["site_GPU"].values()) == GPU_TOTAL == 624
    assert GPU_TOTAL == NODE_TOTAL * GPU_PER_NODE


def test_all_sites_have_integer_nodes_and_four_gpu_granularity() -> None:
    weights, _ = load_facility_prior(REPO)
    result = construct_capacity(weights)
    assert all(isinstance(value, int) for value in result["site_nodes"].values())
    assert all(value % 4 == 0 for value in result["site_GPU"].values())
    assert all(value >= 32 for value in result["site_GPU"].values())


def test_facility_prior_ranking_and_top_seven_are_exact() -> None:
    weights, _ = load_facility_prior(REPO)
    result = construct_capacity(weights)
    assert tuple(result["facility_weight_order"]) == EXPECTED_WEIGHT_ORDER
    assert tuple(result["top_full_block_recipients"]) == EXPECTED_TOP_SEVEN


def test_aidc05_receives_the_four_node_sixteen_gpu_residual() -> None:
    weights, _ = load_facility_prior(REPO)
    result = construct_capacity(weights)
    assert result["residual_nodes"] == 4
    assert result["residual_GPU"] == 16
    assert result["residual_recipient"] == "AIDC05"


def test_exact_node_and_gpu_vectors_are_independently_recomputed() -> None:
    weights, _ = load_facility_prior(REPO)
    result = construct_capacity(weights)
    assert result["site_nodes"] == EXPECTED_NODE_CAPACITY
    assert result["site_GPU"] == EXPECTED_GPU_CAPACITY
    assert [result["site_GPU"][site] for site in sorted(result["site_GPU"])] == [
        64, 32, 64, 32, 80, 64, 32, 64, 32, 64, 32, 64,
    ]


def test_32gpu_host_positions_equal_19() -> None:
    weights, _ = load_facility_prior(REPO)
    assert construct_capacity(weights)["host_positions_32GPU"] == 19


def test_capacity_authority_is_posthoc_synthetic_not_measured() -> None:
    authority = j("V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json")
    assert authority["classification"] == CLASSIFICATION
    assert authority["measured_GPU_claim"] is False
    assert authority["capacity_semantics"] == "SYNTHETIC_H100_EQUIVALENT_SITE_COMPUTE_CAPACITY"
    assert authority["source_HEAD"] == START_HEAD


def test_capacity_hash_is_stable_and_was_committed_before_may_evaluation() -> None:
    certificate = j("V39C_CAPACITY_FREEZE_CERTIFICATE.json")
    authority_path = ARTIFACT / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    assert sha256_file(authority_path) == certificate["capacity_authority_file_SHA256"]
    assert certificate["CAPACITY_RULE_FROZEN_BEFORE_V39C_MAY_FEASIBILITY"] == "YES"
    assert certificate["capacity_mutations_after_freeze"] == 0


def test_legacy_capacity_is_not_an_installed_gpu_census() -> None:
    audit = j("V39C_LEGACY_GPU_CAPACITY_PROVENANCE_AUDIT.json")
    assert audit["installed_GPU_measurement_found"] == "NO"
    assert audit["measured_site_GPU_claim_authorized"] == "NO"
    assert "SYNTHETIC" in audit["final_classification"]
    assert audit["preserved_not_overwritten"] is True


def test_premay_audit_uses_no_may_fresh_grid_or_actual_rows() -> None:
    audit = j("V39C_PREMAY_JOB_GANG_SIZE_AUDIT.json")
    assert audit["May_rows"] == audit["May_result_reads"] == 0
    assert audit["Fresh_reads"] == audit["grid_reads"] == audit["Actual_reads"] == 0
    assert audit["32GPU_gang_repeatedly_observed"] is True
    assert audit["60GPU_frequency_classification"] == "NOT_OBSERVED_IN_STRICT_PREMAY_AUTHORITY"


def test_science_firewall_has_no_capacity_or_temporal_mutation() -> None:
    for name in (
        "V39C_SLOT_LOCAL_PACKING_AUDIT.json",
        "V39C_INTERVAL_SPATIAL_FEASIBILITY_AUDIT.json",
        "V39C_FULL_CAUSAL_SPATIAL_FEASIBILITY_AUDIT.json",
    ):
        audit = j(name)
        assert audit["temporal_schedule_mutations"] == 0
        assert audit["RW_schedule_mutations"] == 0
        assert audit["RSP_schedule_mutations"] == 0
    assert j("V39C_CAPACITY_FREEZE_CERTIFICATE.json")["capacity_mutations_after_freeze"] == 0


def test_slot_local_exact_packing_passes_all_5952_slots() -> None:
    audit = j("V39C_SLOT_LOCAL_PACKING_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["models"] == 31 * 2 * 96
    assert audit["feasible_slots"] == 31 * 2 * 96
    assert audit["infeasible_slots"] == 0
    assert audit["gang_splitting"] is False


def test_interval_spatial_models_are_all_optimal() -> None:
    audit = j("V39C_INTERVAL_SPATIAL_FEASIBILITY_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["models_built"] == audit["models_optimal"] == 62
    assert audit["models_infeasible"] == 0
    assert audit["one_AIDC_per_contiguous_interval"] is True


def test_full_causal_chains_use_migration_enabled_c1_not_stay_only_c0() -> None:
    audit = j("V39C_FULL_CAUSAL_SPATIAL_FEASIBILITY_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["causal_31day_chains_feasible"] is True
    assert audit["daily_remap_count"] == 0
    assert audit["gang_split_count"] == 0
    assert audit["fixed_WAN_paths"] == audit["expected_fixed_WAN_paths"] == 132
    assert audit["StageC0_STAY_ONLY_status"] == "FAIL"
    assert audit["StageC1_migration_enabled_status"] == "PASS"
    assert audit["StageC1_feasibility_objective"] == "ZERO"
    assert audit["migration_allowed"] == "YES"
    assert audit["migration_forced"] == "NO"
    assert audit["StageC_feasibility_objective"] == "ZERO"
    assert audit["StageC_feasibility_status"] == "PASS"
    assert audit["witness_materialization_performed"] is True
    assert audit["minimum_migration_witness_performed"] is True
    assert audit["selected_RUNNING_migration_count"] >= 0
    assert audit["migration_count"] == audit["selected_RUNNING_migration_count"]
    assert audit["WAN_transfer_count"] == audit["selected_RUNNING_migration_count"]
    assert audit["checkpoint_transfer_count"] == audit["selected_RUNNING_migration_count"]
    assert audit["restart_count"] == audit["selected_RUNNING_migration_count"]
    assert audit["unnecessary_migration_count"] == 0
    assert audit["capacity_SHA_before"] == audit["capacity_SHA_after"]
    assert audit["temporal_schedule_mutation_count"] == 0
    assert audit["execution_classification"] == (
        "SCIENCE_NEUTRAL_FEASIBILITY_EXECUTION_SIMPLIFICATION"
    )
    assert audit["root_cause_classification"] == "STAY_ONLY_FALSE_NEGATIVE"


def test_stay_only_failure_is_preserved_as_non_authoritative_diagnostic() -> None:
    audit = j("V39C_STAGE_C0_STAY_ONLY_DIAGNOSTIC.json")
    assert audit["status"] == "FAIL"
    assert audit["diagnostic_classification"] == "STAGE_C0_STAY_ONLY_DIAGNOSTIC"
    assert audit["readiness_authority"] is False
    assert audit["migration_allowed"] is False


def test_site_gpu_trajectories_conserve_v37_aggregate() -> None:
    frame = pd.read_parquet(ARTIFACT / "V39C_SITE_GPU_TRAJECTORIES.parquet")
    assert len(frame) == 31 * 2 * 96 * 12
    assert (frame["active_GPU"] >= 0).all()
    assert (frame["active_GPU"] <= frame["AIDC_GPU_capacity"]).all()
    audit = j("V39C_POWER_CONSERVATION_AUDIT.json")
    assert audit["GPU_conservation_exact"] is True
    assert audit["RW_GPU_max_error"] == audit["RSP_GPU_max_error"] == 0


def test_site_power_conserves_center_and_full_active_anchor() -> None:
    audit = j("V39C_POWER_CONSERVATION_AUDIT.json")
    assert audit["status"] == "PASS"
    assert Decimal(audit["RW_site_to_aggregate_power_max_error_kW"]) <= Decimal("2e-12")
    assert Decimal(audit["RSP_site_to_aggregate_power_max_error_kW"]) <= Decimal("2e-12")
    assert abs(
        Decimal(audit["full_active_site_sum_kW"])
        - Decimal("406.775993813819")
    ) <= Decimal("2e-12")
    assert audit["additional_1_30_multiplier_used"] is False


def test_b0_b2_and_b1_b3_aidc_identities_hold() -> None:
    audit = j("V39C_POWER_CONSERVATION_AUDIT.json")
    assert audit["B0_equals_B2"] is True
    assert audit["B1_equals_B3"] is True
    assert audit["B0_AIDC_trajectory_SHA256"] == audit["B2_AIDC_trajectory_SHA256"]
    assert audit["B1_AIDC_trajectory_SHA256"] == audit["B3_AIDC_trajectory_SHA256"]
    assert audit["Fresh_placement_feedback_count"] == 0
    assert audit["MESS_schedule_mutation_count"] == 0


def test_site_pcc_trajectory_uses_existing_mapping_and_c1() -> None:
    frame = pd.read_parquet(ARTIFACT / "V39C_SITE_PCC_POWER_TRAJECTORIES.parquet")
    assert len(frame) == 31 * 2 * 96 * 12
    assert frame["existing_feeder_PCC_node"].nunique() == 12
    assert not frame["additional_1_30_multiplier_used"].any()
    assert not frame["C1_changed"].any()


def test_comparison_records_engineering_selection_not_may_tuning() -> None:
    audit = j("V39C_LEGACY_VS_REFROZEN_CAPACITY_COMPARISON.json")
    assert audit["selection_basis"] == "PREDECLARED_ENGINEERING_CONTRACT_NOT_MAY_RESULT_QUALITY"
    assert audit["May_result_role"] == "POST_FREEZE_EVALUATION_ONLY"
    assert audit["legacy"]["total_GPU"] == audit["V39C"]["total_GPU"] == 624


def test_preflight_is_ready_without_starting_may() -> None:
    audit = j("V39C_MAY_31DAY_INPUT_PREFLIGHT.json")
    assert audit["READY"] == 31
    assert audit["NOT_READY"] == audit["missing"] == 0
    assert audit["true_production_loader_PASS_count"] == 31
    assert audit["MAY_CAMPAIGN_LAUNCH_READY"] == "YES"
    assert audit["MAY_STARTED"] == "NO"


def test_final_gate_and_fingerprint_are_closed_and_stable() -> None:
    fingerprint = j("V39C_IMPLEMENTATION_FINGERPRINT.json")
    assert fingerprint["status"] == "PASS"
    assert len(fingerprint["V39C_IMPLEMENTATION_FINGERPRINT"]) == 64
    review = (ARTIFACT / "V39C_FINAL_REVIEW.md").read_text(encoding="utf-8")
    assert "V39C_READY = YES" in review
    assert "TEMPORAL_RECOURSE_REQUIRED_AFTER_CAPACITY_REFREEZE = NO" in review
    assert review.rstrip().endswith("MAY_STARTED = NO")
