"""Targeted fail-closed tests for the V35R3F Dataset 312 authority."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.v35r3f.audit import integrate_series_wh, sha256_file
from dayahead.v35r3f.contracts import (
    ARCHIVE,
    ARCHIVE_SHA256,
    ARTIFACT_DIRNAME,
    BRANCH,
    GPUS_PER_NODE,
    PARENT_HEAD,
    PARTIAL_SHARED_ANSWER,
    POWER_AUTHORITY_LEVEL,
    PRIMARY_BOUNDARY,
    PRIMARY_CLASSIFICATION,
    RESOURCE_STATE_SUPPORT,
)


ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "dayahead" / "artifacts" / ARTIFACT_DIRNAME


def load(name: str) -> dict:
    return json.loads((ART / name).read_text(encoding="utf-8"))


def test_lineage_exact_parent_and_branch() -> None:
    state = load("V35R3F_START_STATE.json")
    assert state["parent_actual_at_worktree_creation"] == PARENT_HEAD
    assert state["branch_actual"] == BRANCH


def test_source_archive_exact_sha_and_no_redownload() -> None:
    source = load("V35R3F_SOURCE_AUTHORITY.json")
    assert source["archive_sha256"] == ARCHIVE_SHA256
    assert source["archive_integrity"] == "PASS"
    assert source["zip_crc_test"] == "PASS"
    assert source["no_redownload"] is True
    assert sha256_file(ARCHIVE) == ARCHIVE_SHA256


def test_isolated_worktree_and_no_external_modification() -> None:
    isolation = load("V35R3F_ISOLATION_AUDIT.json")
    assert isolation["isolated_worktree"] is True
    assert isolation["production_files_changed"] == 0
    assert isolation["vendor_files_changed"] == 0
    assert isolation["MESS_files_changed"] == 0
    assert isolation["push"] is False and isolation["merge"] is False


def test_complete_machine_readable_inventory() -> None:
    payload = load("V35R3F_DATASET312_ARCHIVE_INVENTORY.json")
    csv_frame = pd.read_csv(ART / "V35R3F_DATASET312_ARCHIVE_INVENTORY.csv")
    assert len(payload["files"]) == payload["archive_file_count"] == len(csv_frame)
    required = {
        "relative_path", "file_size_bytes", "extension", "apparent_role", "category",
        "workload_identity", "model_identity", "experiment_identity", "node_count",
        "gpus_per_node", "total_gpu_count", "repetition_index", "sampling_source",
        "timestamp_available",
    }
    assert required <= set(csv_frame.columns)
    assert csv_frame["relative_path"].is_unique


def test_schema_fields_have_unit_or_unknown() -> None:
    census = load("V35R3F_DATASET312_SCHEMA_CENSUS.json")
    assert census["all_fields_have_units_or_UNKNOWN"] is True
    for family in census["families"]:
        for field in family.get("fields", {}).values():
            assert field["unit"]


def test_sensor_boundaries_are_explicit() -> None:
    semantics = load("V35R3F_POWER_SENSOR_SEMANTICS.json")
    assert semantics["whole_facility_directory_semantics"] == "DIPLOEE_SIMULATED_NOT_MEASURED"
    assert "WHOLE_NODE_INPUT_POWER" in semantics["channels_absent"]
    assert all(item["physical_boundary"] for item in semantics["fields"])


def test_rapl_package_and_core_never_promoted_as_disjoint() -> None:
    boundaries = load("V35R3F_MEASUREMENT_BOUNDARY_AUTHORITY.json")
    supplied = next(
        item for item in boundaries["authorities"]
        if item["boundary"] == "DATASET_PROVIDED_GPU_PLUS_RAPL_PACKAGE_PLUS_CORE_SUM"
    )
    assert "NONADDITIVE" in supplied["status"]
    assert set(supplied["uses"].values()) == {"NOT_AUTHORIZED"}


def test_native_timebase_audited_before_alignment() -> None:
    frame = pd.read_csv(ART / "V35R3F_TIMEBASE_AUDIT.csv")
    assert set(frame["measurement_family"]) == {"NVML", "RAPL"}
    assert len(frame) == 604
    assert frame["median_dt_seconds"].between(0.09, 0.21).all()
    assert (frame["duplicate_timestamp_count"] >= 0).all()
    assert (frame["missing_or_gap_count"] >= 0).all()


def test_time_weighted_energy_uses_actual_deltas() -> None:
    index = pd.to_datetime(["2026-01-01 00:00:00", "2026-01-01 00:00:01", "2026-01-01 00:00:03"])
    series = pd.Series([100.0, 100.0, 200.0], index=index)
    expected_wh = (100.0 * 1.0 + (100.0 + 200.0) / 2.0 * 2.0) / 3600.0
    assert np.isclose(integrate_series_wh(series), expected_wh)


def test_experiment_dimensions_do_not_conflate_nodes_and_gpus() -> None:
    experiments = pd.read_parquet(ART / "V35R3F_EXPERIMENT_CENSUS.parquet")
    assert set(experiments["node_count"].astype(int)) == {1, 2, 4, 8, 16}
    assert set(experiments["total_gpu_count"].astype(int)) == {4, 8, 16, 32, 64}
    assert (experiments["total_gpu_count"] == GPUS_PER_NODE * experiments["node_count"]).all()


def test_resource_support_fails_closed() -> None:
    support = load("V35R3F_RESOURCE_STATE_SUPPORT.json")
    assert support["classification"] == RESOURCE_STATE_SUPPORT
    assert support["C_1_2_4_8_16_semantics"] == "NODE_COUNTS"
    assert support["PARTIAL_GPU_NODE_POWER_DIRECTLY_IDENTIFIED"] == "NO"
    assert support["SHARED_NODE_POWER_DIRECTLY_IDENTIFIED"] == "NO"
    assert support["IDLE_POWER_DIRECT_AUTHORITY"] == "NO"


def test_raw_profile_statistics_cover_every_valid_run_and_boundary() -> None:
    stats = pd.read_parquet(ART / "V35R3F_RAW_PROFILE_STATISTICS.parquet")
    experiments = pd.read_parquet(ART / "V35R3F_EXPERIMENT_CENSUS.parquet")
    assert stats["experiment_id"].nunique() == len(experiments)
    assert stats.groupby("experiment_id")["power_boundary"].nunique().eq(5).all()
    assert (stats["energy_integral_Wh"] >= 0).all()
    assert set(stats["unit"]) == {"W"}


def test_full_run_primary_and_no_invented_steady_trim() -> None:
    audit = load("V35R3F_TRANSIENT_STEADY_STATE_AUDIT.json")
    assert audit["new_favorable_trimming_rule_invented"] is False
    assert audit["diagnostic_steady_state_computed"] is False
    assert audit["primary_statistics"] == "FULL_DATASET_DEFINED_RUN_OR_WINDOW"


def test_raw_aggregate_reconciliation_is_independent_and_toleranced() -> None:
    audit = load("V35R3F_RAW_AGGREGATED_RECONCILIATION.json")
    frame = pd.read_csv(ART / "V35R3F_RAW_AGGREGATED_RECONCILIATION.csv")
    assert audit["available_aggregate_runs"] == int(frame["aggregate_available"].sum())
    assert audit["tolerances"]["mean_relative"] > 0
    assert "hard-coded expected aggregate" not in json.dumps(audit).lower()


def test_online_rate_interpolation_not_called_native_measurement() -> None:
    audit = load("V35R3F_RAW_AGGREGATED_RECONCILIATION.json")
    assert "0.001 s interpolation" in audit["online_rate_resampling"]
    semantics = load("V35R3F_POWER_SENSOR_SEMANTICS.json")
    aggregate = next(item for item in semantics["fields"] if item["field"] == "aggregated power[W]")
    assert "0.001 s" in aggregate["sampling_interval"]


def test_data_quality_exclusions_are_science_neutral() -> None:
    manifest = load("V35R3F_EXCLUSION_MANIFEST.json")
    assert manifest["runs_removed_for_being_extreme"] == 0
    assert manifest["dataset_supplied_backward_fill_not_used_as_hidden_authority"] is True
    quality = pd.read_csv(ART / "V35R3F_DATA_QUALITY_AUDIT.csv")
    assert {"STRUCTURAL_INVALID", "SENSOR_INVALID", "VALID_EXTREME", "UNKNOWN"} <= set(manifest["rules"])
    assert (quality["sample_count"] > 0).all()


def test_node_scaling_is_matched_and_weak_scaling_labeled() -> None:
    frame = pd.read_parquet(ART / "V35R3F_NODE_SCALING.parquet")
    assert frame["matched_series"].all()
    assert frame["energy_comparable_across_scales"].eq(False).all()
    assert frame["weak_scaling_note"].eq("GLOBAL_BATCH_OR_WORK_INCREASES_WITH_GPU_COUNT").all()
    assert set(frame["node_count"].astype(int)) == {1, 2, 4, 8, 16}


def test_workload_variability_is_engineering_not_significance() -> None:
    payload = load("V35R3F_WORKLOAD_POWER_VARIABILITY.json")
    assert payload["engineering_uncertainty_only"] is True
    assert payload["statistical_significance_claimed"] is False


def test_envelope_is_empirical_deterministic_and_class_stratified() -> None:
    frame = pd.read_parquet(ART / "V35R3F_CLASS_AGNOSTIC_POWER_ENVELOPE.parquet")
    contract = load("V35R3F_POWER_ENVELOPE_CONTRACT.json")
    assert (frame["P_LOW"] <= frame["P_CENTER"]).all()
    assert (frame["P_CENTER"] <= frame["P_HIGH"]).all()
    assert frame["partial_gpu_supported"].eq(False).all()
    assert frame["shared_node_supported"].eq(False).all()
    assert contract["grid_result_used_for_tuning"] is False
    assert contract["experiment_run_level_quantiles_used"] is True
    assert contract["AIDC_IT_LOAD_AUTHORIZATION"] == "NOT_AUTHORIZED_WITHOUT_MISSING_NODE_INPUT_COMPONENTS"


def test_primary_boundary_is_component_level_only() -> None:
    authority = load("V35R3F_POWER_AUTHORITY_DECISION.json")
    assert authority["power_authority_level"] == POWER_AUTHORITY_LEVEL
    assert authority["whole_node_power_directly_measured"] == "NO"
    assert authority["robust_component_envelope_available"] == "YES"
    assert authority["robust_whole_node_envelope_available"] == "NO"


def test_kestrel_bridge_matrix_is_fail_closed() -> None:
    matrix = load("V35R3F_KESTREL_BRIDGE_ELIGIBILITY_MATRIX.json")
    by_number = {item["target_number"]: item["classification"] for item in matrix["targets"]}
    assert by_number[3] == by_number[4] == by_number[5] == by_number[6] == "UNSUPPORTED"
    assert by_number[8] == "SUPPORTED_WITH_ROBUST_ENVELOPE"
    assert matrix["DATASET312_TO_KESTREL_JOB_DIRECT_JOIN"] == "FORBIDDEN"
    assert matrix["RADDIT_CPU_POWER_USED_FOR_H100_MAGNITUDE"] == "NO"


def test_future_node_accounting_counts_physical_node_once() -> None:
    contract = load("V35R3F_NEXT_NODE_PACKING_CONTRACT.json")
    assert "EACH PHYSICAL NODE COUNTED EXACTLY ONCE" in contract["future_invariant"]
    assert contract["execution_in_this_task"] == "FORBIDDEN_NOT_RUN"
    assert contract["KESTREL_NODE_PACKING_NEXT"] == "DEFER"


def test_scope_firewall_reads_are_zero() -> None:
    isolation = load("V35R3F_ISOLATION_AUDIT.json")
    assert set(isolation["firewall_reads"].values()) == {0}
    assert isolation["node_packing_executed"] is False
    assert isolation["scheduler_power_integration_executed"] is False


def test_no_job_power_or_raddit_transfer() -> None:
    decision = load("V35R3F_POWER_AUTHORITY_DECISION.json")
    assert decision["DATASET312_TO_KESTREL_JOB_DIRECT_JOIN"] == "FORBIDDEN"
    assert decision["RADDIT_CPU_POWER_USED_FOR_H100_MAGNITUDE"] == "NO"
    assert decision["partial_shared_public_data_answer"] == PARTIAL_SHARED_ANSWER


def test_final_authority_and_production_decision() -> None:
    decision = load("V35R3F_POWER_AUTHORITY_DECISION.json")
    assert decision["primary_classification"] == PRIMARY_CLASSIFICATION
    assert decision["PRODUCTION_INTEGRATION_RECOMMENDED"] == "NO"
    assert decision["KESTREL_NODE_PACKING_NEXT"] == "DEFER"


def test_compute_firewall_no_heavy_model_or_solver() -> None:
    compute = load("V35R3F_COMPUTE_ACCOUNTING.json")
    assert compute["process_count"] == 1
    assert compute["GPU_training"] is False
    assert compute["XGBoost"] is False
    assert compute["Gurobi"] is False
    assert compute["full_year_simulation"] is False


def test_repair_log_did_not_change_science() -> None:
    repairs = load("V35R3F_REPAIR_LOG.json")
    assert repairs["science_semantics_changed"] is False
    assert repairs["unique_failure_signatures"] <= 5


def test_every_primary_profile_uses_declared_boundary() -> None:
    stats = pd.read_parquet(ART / "V35R3F_RAW_PROFILE_STATISTICS.parquet")
    primary = stats.loc[stats["power_boundary"].eq(PRIMARY_BOUNDARY)]
    assert len(primary) == stats["experiment_id"].nunique()
    assert primary["authority_status"].eq("AUTHORITATIVE_COMPONENT").all()
