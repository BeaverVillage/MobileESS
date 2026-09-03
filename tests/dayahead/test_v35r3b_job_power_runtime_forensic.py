from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dayahead.v35r3b.contracts import (
    ACTIVE_V35R3_WORKTREE,
    ARTIFACT_DIRNAME,
    AUTHORITY_ROOT,
    EXPECTED_BRANCH,
    FRESH_STATUS,
    GPU_CAPACITY,
    GRID_BINDING_STATUS,
    PARENT_WORKTREE,
    POWER_AUTHORITY_LEVEL,
    PRIMARY_CLASSIFICATION,
    RUNTIME_AUTHORITY_LEVEL,
    SOURCE_PARENT,
    TARGET_SLOTS,
    WORKTREE,
)
from dayahead.v35r3b.forensic import (
    assert_no_fuzzy_join,
    causal_feature_audit,
    deterministic_rank,
    exact_key_join,
    inventory_authority,
    lfs_pointer_info,
    normalize_job_key,
    power_profile_from_jobs,
    profile_energy_gpu_hours,
    remaining_duration_slots,
    requested_duration_slots,
    target_gpu_profile,
    top_k_escalation,
)


REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
PARENT_ARTIFACTS = REPO / "dayahead" / "artifacts" / "v35r3a_kestrel_scheduler_temporal"


def _json(name: str):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def _git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), *args], text=True, encoding="utf-8", errors="replace"
    ).strip()


def test_exact_parent_branch_and_separate_worktree():
    assert _git(REPO, "branch", "--show-current") == EXPECTED_BRANCH
    assert _git(REPO, "merge-base", "HEAD", SOURCE_PARENT) == SOURCE_PARENT
    assert REPO.resolve() == WORKTREE.resolve()
    assert REPO.resolve() not in {ACTIVE_V35R3_WORKTREE.resolve(), PARENT_WORKTREE.resolve()}


def test_isolation_declares_zero_external_writes_and_network_calls():
    audit = _json("V35R3B_ISOLATION_AUDIT.json")
    assert audit["worktree_separate"]
    assert not audit["paths_shared_with_active_V35R3"]
    assert not audit["paths_shared_with_V35R3A_artifacts"]
    assert audit["active_V35R3_files_changed_by_this_task"] == 0
    assert audit["V35R3A_parent_worktree_files_changed_by_this_task"] == 0
    assert audit["downloaded_authority_files_changed_by_this_task"] == 0
    assert audit["network_calls"] == 0
    assert audit["network_commands_executed"] == []
    assert not audit["push_performed"] and not audit["merge_performed"]


def test_active_parallel_process_is_audited_and_parent_remains_unchanged():
    start = _json("V35R3B_START_STATE.json")
    assert start["active_V35R3_HEAD_at_start"]
    # The explicitly parallel V35R3 process may complete independently. Its
    # current state is finalized separately; V35R3B performed zero writes there.
    assert _git(PARENT_WORKTREE, "status", "--short") == start["V35R3A_parent_status_at_start"] == ""
    assert _git(PARENT_WORKTREE, "rev-parse", "HEAD") == start["V35R3A_parent_HEAD_at_start"] == SOURCE_PARENT


def test_vendor_heads_and_statuses_remain_at_start_state():
    start = _json("V35R3B_START_STATE.json")
    for state in start["vendor_repository_states_at_start"].values():
        path = Path(state["path"])
        assert _git(path, "rev-parse", "HEAD") == state["HEAD"]
        assert _git(path, "status", "--short") == state["status"]


def test_authority_inventory_sha_and_fingerprint_are_reproducible():
    recorded = _json("V35R3B_LOCAL_AUTHORITY_INVENTORY.json")["authority_root"]
    rows, current = inventory_authority(AUTHORITY_ROOT)
    assert len(rows) == recorded["file_count"] == 773
    assert current["content_fingerprint_sha256"] == recorded["content_fingerprint_sha256"]
    assert current["lfs_pointer_count"] == 50
    assert current["lfs_objects_cached_locally"] == 0


def test_lfs_pointer_parser_and_real_parquet_distinction():
    pointer = AUTHORITY_ROOT / "02_RADDiT" / "data" / "baseline_power_results.parquet"
    real = AUTHORITY_ROOT / "02_RADDiT" / "data" / "ground_truth.parquet"
    info = lfs_pointer_info(pointer)
    assert info == {
        "oid_sha256": "5b94583ed2a944b9554ffdd0bdc8ca61cf17d3cd122ded47e3eeb7549145b419",
        "expected_size": 8730834,
        "pointer_size": 132,
    }
    assert lfs_pointer_info(real) is None
    assert pd.read_parquet(real).shape == (161266, 7)


def test_placeholder_and_unreadable_paths_are_explicitly_recorded():
    inventory = pd.read_csv(ARTIFACTS / "V35R3B_FILE_SCHEMA_INVENTORY.csv")
    assert inventory["offline_placeholder"].fillna(False).astype(bool).sum() == 0
    assert inventory["parse_error"].notna().sum() == 22
    assert inventory["zero_byte"].fillna(False).astype(bool).sum() == 26
    assert not inventory.loc[inventory["parse_error"].notna(), "readable"].astype(bool).any()


def test_schema_capture_for_every_real_raddit_parquet():
    inventory = pd.read_csv(ARTIFACTS / "V35R3B_FILE_SCHEMA_INVENTORY.csv")
    real = inventory.loc[inventory["format"].eq("PARQUET")]
    assert len(real) == 6
    ground = real.loc[real["relative_path"].eq("02_RADDiT/data/ground_truth.parquet")].iloc[0]
    assert int(ground["row_count"]) == 161266
    assert "avg_power_per_node" in ground["columns"]


def test_missing_authority_manifest_covers_every_lfs_oid():
    lfs = pd.read_csv(ARTIFACTS / "V35R3B_LFS_PLACEHOLDER_AUDIT.csv")
    missing = _json("V35R3B_MISSING_EXTERNAL_AUTHORITY_REQUEST.json")
    manifest_oids = {row["git_lfs_oid_sha256"] for row in missing["requests"] if row["git_lfs_oid_sha256"]}
    assert len(lfs) == 50
    assert set(lfs["lfs_oid_sha256"]) <= manifest_oids
    assert missing["missing_object_count"] == len(missing["requests"]) == 59
    assert missing["generated_offline"] and not missing["guessed_URLs"]


def test_job_key_normalization_is_exact_not_fuzzy():
    assert normalize_job_key(123) == "123"
    assert normalize_job_key(123.0) == "123"
    assert normalize_job_key(" 00123 ") == "00123"
    with pytest.raises(ValueError, match="NON_INTEGRAL"):
        normalize_job_key(1.5)


def test_exact_join_rejects_duplicate_authority_keys():
    left = pd.DataFrame({"job_id": [1, 2]})
    right = pd.DataFrame({"key": [1, 1], "prediction": [10.0, 11.0]})
    with pytest.raises(ValueError, match="DUPLICATE_AUTHORITY_JOB_KEY"):
        exact_key_join(left, right, left_key="job_id", right_key="key")


def test_fuzzy_production_join_is_forbidden():
    assert_no_fuzzy_join("J1_EXACT_KEY")
    assert_no_fuzzy_join("J2_DOCUMENTED_TRANSFORM")
    assert_no_fuzzy_join("J3_MODEL_INFERENCE")
    with pytest.raises(PermissionError, match="FUZZY"):
        assert_no_fuzzy_join("J4_COMPOSITE_DIAGNOSTIC")


def test_apr01_join_coverage_conservation_and_conflicts():
    audit = pd.read_csv(ARTIFACTS / "V35R3B_JOB_ID_JOIN_AUDIT.csv")
    temporal = audit.loc[audit["population"].eq("temporal_controlled")]
    assert set(temporal["job_count"]) == {339}
    assert temporal["causal_prediction_matched_jobs"].sum() == 0
    assert temporal["unmatched_count"].eq(339).all()
    runtime = _json("V35R3B_RUNTIME_AUTHORITY_DECISION.json")
    assert runtime["diagnostic_source_duplicate_keys"] == 343
    assert runtime["Apr01_queue_one_to_many_conflicts"] == 0


def test_causality_firewall_rejects_realized_and_future_features():
    counters = causal_feature_audit(["nodes_req", "partition", "qos"])
    assert set(counters.values()) == {0}
    for forbidden in ("future_actual_start", "future_actual_end", "wallclock_used_sec", "avg_power_per_node", "fresh_output"):
        with pytest.raises(PermissionError, match="FORBIDDEN"):
            causal_feature_audit([forbidden])


def test_feature_table_records_zero_policy_reads_for_unavailable_models():
    audit = pd.read_csv(ARTIFACTS / "V35R3B_FEATURE_CAUSALITY_AUDIT.csv")
    assert audit["policy_read_count"].sum() == 0
    forbidden = audit.loc[audit["role"].eq("LABEL_OR_FORBIDDEN")]
    assert not forbidden["known_at_submission_or_issue"].astype(bool).any()


def test_power_authority_fails_closed_at_p1():
    decision = _json("V35R3B_POWER_AUTHORITY_DECISION.json")
    coverage = _json("V35R3B_APR01_POWER_COVERAGE.json")
    assert decision["authority_level"] == POWER_AUTHORITY_LEVEL == "P1_AGGREGATE_PROXY_ONLY"
    assert not decision["HP_eligible"] and not decision["P3_P4_claimed"]
    assert coverage["covered_jobs"] == 0
    assert coverage["PARTIAL_shared_jobs"] == 336
    assert coverage["PARTIAL_shared_covered"] == 0
    assert coverage["distribution"]["P50_W"] is None


def test_power_units_are_not_silently_interchanged():
    total = power_profile_from_jobs(
        [{"predicted_power_kw": 2.0, "power_unit_semantics": "TOTAL_JOB_IT_KW", "requested_gpus": 4, "requested_nodes": 1, "start_slot": 0, "end_slot": 2, "partial_or_shared": False}],
        shared_power_incremental_proven=False,
    )
    per_gpu = power_profile_from_jobs(
        [{"predicted_power_kw": 0.5, "power_unit_semantics": "PER_GPU_KW", "requested_gpus": 4, "requested_nodes": 1, "start_slot": 0, "end_slot": 2, "partial_or_shared": False}],
        shared_power_incremental_proven=False,
    )
    per_node = power_profile_from_jobs(
        [{"predicted_power_kw": 2.0, "power_unit_semantics": "PER_NODE_KW", "requested_gpus": 4, "requested_nodes": 1, "start_slot": 0, "end_slot": 2, "partial_or_shared": False}],
        shared_power_incremental_proven=False,
    )
    assert np.array_equal(total, per_gpu)
    assert np.array_equal(total, per_node)
    with pytest.raises(ValueError, match="UNKNOWN_POWER_UNIT"):
        power_profile_from_jobs(
            [{"predicted_power_kw": 1, "power_unit_semantics": "WISHFUL", "requested_gpus": 1, "requested_nodes": 1, "start_slot": 0, "end_slot": 1, "partial_or_shared": False}],
            shared_power_incremental_proven=True,
        )


def test_shared_node_power_cannot_be_double_counted():
    row = {"predicted_power_kw": 1.0, "power_unit_semantics": "PER_NODE_KW", "requested_gpus": 1, "requested_nodes": 1, "start_slot": 0, "end_slot": 1, "partial_or_shared": True}
    with pytest.raises(PermissionError, match="POWER_ATTRIBUTION_AMBIGUOUS"):
        power_profile_from_jobs([row], shared_power_incremental_proven=False)


def test_apr01_job_power_distribution_has_no_invented_predictions():
    distribution = pd.read_csv(ARTIFACTS / "V35R3B_APR01_JOB_POWER_DISTRIBUTION.csv")
    assert len(distribution) == 339
    assert distribution["predicted_power_W"].isna().all()
    assert distribution["predicted_kW_per_GPU"].isna().all()
    assert distribution["H0_proxy_job_kW"].notna().all()
    assert distribution["FULL_PARTIAL_shared"].eq("PARTIAL_SHARED").sum() == 336


def test_runtime_authority_keeps_requested_predicted_and_realized_distinct():
    decision = _json("V35R3B_RUNTIME_AUTHORITY_DECISION.json")
    distribution = pd.read_csv(ARTIFACTS / "V35R3B_APR01_JOB_RUNTIME_DISTRIBUTION.csv")
    assert decision["authority_level"] == RUNTIME_AUTHORITY_LEVEL == "R1_REQUESTED_WALLTIME_ONLY"
    assert not decision["HPR_eligible"] and not decision["R3_R4_claimed"]
    assert len(distribution) == 339
    assert distribution["predicted_runtime_seconds"].isna().all()
    assert np.array_equal(distribution["requested_walltime_slots"], distribution["authorized_duration_slots"])


def test_runtime_slot_calculations_are_conservative_and_separate():
    assert requested_duration_slots(901) == 2
    assert remaining_duration_slots(3600, 1800) == 2
    assert remaining_duration_slots(3600, 4000) == 1
    with pytest.raises(ValueError, match="NEGATIVE"):
        remaining_duration_slots(-1, 0)


def test_h0_profile_is_96_slots_capacity_feasible_and_energy_consistent():
    schedule = pd.read_parquet(PARENT_ARTIFACTS / "V35R3A_BASELINE_SCHEDULE.parquet")
    profile = target_gpu_profile(schedule)
    h0 = _json("V35R3B_MODE_H0_RESULTS.json")
    assert profile.shape == (TARGET_SLOTS,)
    assert np.all(profile <= GPU_CAPACITY)
    assert np.array_equal(profile, np.asarray(h0["occupancy_GPUs_96_slots"]))
    assert profile_energy_gpu_hours(profile) == pytest.approx(h0["occupancy_GPU_hours"])
    assert h0["saturation_slots"] == 96
    assert h0["minimum_free_GPU_capacity"] == 0
    assert h0["first_capacity_release_slot"] is None


def test_capacity_release_rw_has_no_apr01_free_capacity():
    capacity = pd.read_csv(ARTIFACTS / "V35R3B_CAPACITY_RELEASE_RW.csv")
    assert len(capacity) == 96
    assert capacity["occupied_GPUs"].eq(624).all()
    assert capacity["free_GPUs"].eq(0).all()
    assert capacity["saturated_624"].astype(bool).all()


def test_candidate_waterfall_accounts_for_all_temporal_jobs_and_pairs():
    waterfall = pd.read_csv(ARTIFACTS / "V35R3B_CANDIDATE_WATERFALL.csv")
    assert waterfall.loc[waterfall["stage"].eq(1), "count"].item() == 339
    assert waterfall.loc[waterfall["stage"].eq(3), "count"].item() == 202
    assert waterfall.loc[waterfall["stage"].eq(4), "count"].item() == 137
    assert waterfall.loc[waterfall["stage"].eq(5), "count"].item() == 201 * 137
    assert waterfall.loc[waterfall["stage"].eq(6), "count"].item() == 24
    assert waterfall.loc[waterfall["stage"].eq(7), "count"].item() == 0
    assert waterfall.loc[waterfall["stage"].eq(12), "count"].item() == 0


def test_h0_candidate_and_rejection_reason_conservation():
    h0 = _json("V35R3B_MODE_H0_RESULTS.json")
    reasons = pd.read_csv(ARTIFACTS / "V35R3B_CANDIDATE_REJECTION_REASONS.csv")
    h0_reasons = reasons.loc[reasons["counted_in_H0_candidate_conservation"].astype(bool)]
    assert h0_reasons["rejection_count"].sum() == h0["generated_scheduler_candidates"] == 26
    assert h0["generated_exchange_pairs"] == 24
    assert h0["service_safe_exchange_pairs"] == 24
    assert h0["accepted_reprioritizations"] == 0
    assert set(reasons["primary_reason"]) == {"MODEL_AUTHORITY_UNAVAILABLE", "SAME_PREDICTED_POWER", "COMPLETED_WORK_DEGRADATION"}


def test_candidate_tier_compatibility_and_resource_feasibility():
    schedule = pd.read_parquet(PARENT_ARTIFACTS / "V35R3A_BASELINE_SCHEDULE.parquet").set_index("job_id")
    trace = pd.read_csv(PARENT_ARTIFACTS / "V35R3A_SEARCH_TRACE.csv")
    pairs = trace.loc[trace["candidate"].str.startswith("STANDBY_W5_PAIR_SWAP:")]
    for candidate in pairs["candidate"]:
        _, left, right = candidate.split(":")
        assert schedule.loc[left, "qos"] == schedule.loc[right, "qos"] == "standby"
    assert pairs["service_gate_passed"].astype(bool).all()
    assert pairs["critical_slot_GPU"].le(GPU_CAPACITY).all()


def test_deterministic_ranking_and_top_k_escalation_have_no_randomness():
    candidates = [
        {"candidate_id": "b", "predicted_w5_it_reduction_kw": 2, "planning_rho": 1, "critical_exposure": 1, "reprioritized_jobs": 2, "total_sitefactor": 2},
        {"candidate_id": "a", "predicted_w5_it_reduction_kw": 2, "planning_rho": 1, "critical_exposure": 1, "reprioritized_jobs": 2, "total_sitefactor": 2},
        {"candidate_id": "c", "predicted_w5_it_reduction_kw": 1, "planning_rho": 0, "critical_exposure": 0, "reprioritized_jobs": 1, "total_sitefactor": 1},
    ]
    assert [row["candidate_id"] for row in deterministic_rank(candidates)] == ["a", "b", "c"]
    assert top_k_escalation(24) == [24]
    assert top_k_escalation(1001) == [50, 200, 1000, 1001]
    for source in (REPO / "dayahead" / "v35r3b").glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        assert all(not (isinstance(node, ast.Import) and any(alias.name == "random" for alias in node.names)) for node in ast.walk(tree))


def test_strict_service_contract_is_preserved_for_h0():
    service = _json("V35R3B_SERVICE_GATE.json")
    assert service["H0_identity_result"] == "PASS"
    assert service["running_unchanged"]
    assert service["preemption_count"] == 0
    assert service["high_normal_delay_count"] == 0
    assert service["normal_completed_job_delta"] == 0
    assert service["normal_completed_GPU_hour_delta"] == 0
    assert service["normal_terminal_pending_GPU_hour_delta"] == 0
    assert service["standby_completed_job_delta"] == 0
    assert service["standby_completed_GPU_hour_delta"] == 0
    assert service["standby_terminal_pending_GPU_hour_delta"] == 0
    assert not service["standby_displaces_high_normal"]


def test_hp_hpr_controlled_and_fresh_outputs_are_absent_when_unauthorized():
    forbidden = {
        "V35R3B_POWER_MODEL_QUALITY.json",
        "V35R3B_RUNTIME_MODEL_QUALITY.json",
        "V35R3B_CAPACITY_RELEASE_PR.csv",
        "V35R3B_MODE_HP_RESULTS.json",
        "V35R3B_MODE_HPR_RESULTS.json",
        "V35R3B_CONTROLLED_SCHEDULE.parquet",
        "V35R3B_FRESH_REVALIDATION.json",
    }
    assert not (forbidden & {path.name for path in ARTIFACTS.iterdir()})


def test_grid_binding_and_fresh_fail_closed():
    binding = _json("V35R3B_JOB_GRID_BINDING_AUDIT.json")
    grid = _json("V35R3B_GRID_EFFECT.json")
    assert binding["classification"] == GRID_BINDING_STATUS
    assert not binding["acceptable_binding_found"]
    assert binding["MobileESS_independent_runtime_source"]["valid_IT_power_rows"] == 0
    assert binding["MobileESS_independent_runtime_source"]["rack_power_valid_rows"] == 0
    assert binding["Fresh_status"] == FRESH_STATUS
    assert grid["Fresh_status"] == FRESH_STATUS
    assert "NO_GRID_BENEFIT" not in grid["interpretation"] or grid["interpretation"].startswith("No claim")


def test_production_science_and_scope_are_preserved():
    recommendation = _json("V35R3B_PRODUCTION_INTEGRATION_RECOMMENDATION.json")
    assert recommendation["PRODUCTION_INTEGRATION_RECOMMENDED"] == "NO"
    assert recommendation["production_files_modified"] == 0
    assert not recommendation["AIDC_MESS_science_modified"]
    assert not recommendation["Apr02_or_later_run"]
    assert not recommendation["Apr21_read"]
    assert not recommendation["May_opened"]
    assert not recommendation["push"] and not recommendation["merge"]


def test_changes_are_confined_to_v35r3b_namespaces():
    allowed = (
        "dayahead/artifacts/v35r3b_job_power_runtime_forensic/",
        "dayahead/v35r3b/",
        "tools/v35r3b/",
        "tests/dayahead/test_v35r3b_",
        "logs/v35r3b_job_power_runtime_forensic/",
    )
    for line in _git(REPO, "status", "--short").splitlines():
        path = line[3:].replace("\\", "/")
        assert path.startswith(allowed), path


def test_required_artifacts_and_final_report_are_complete():
    required = {
        "V35R3B_START_STATE.json",
        "V35R3B_ISOLATION_AUDIT.json",
        "V35R3B_LOCAL_AUTHORITY_INVENTORY.json",
        "V35R3B_FILE_SCHEMA_INVENTORY.csv",
        "V35R3B_LFS_PLACEHOLDER_AUDIT.csv",
        "V35R3B_POWER_OBJECT_CLASSIFICATION.csv",
        "V35R3B_RUNTIME_OBJECT_CLASSIFICATION.csv",
        "V35R3B_POWER_AUTHORITY_DECISION.json",
        "V35R3B_RUNTIME_AUTHORITY_DECISION.json",
        "V35R3B_JOB_ID_JOIN_AUDIT.csv",
        "V35R3B_APR01_POWER_COVERAGE.json",
        "V35R3B_APR01_RUNTIME_COVERAGE.json",
        "V35R3B_FEATURE_CAUSALITY_AUDIT.csv",
        "V35R3B_APR01_JOB_POWER_DISTRIBUTION.csv",
        "V35R3B_APR01_JOB_RUNTIME_DISTRIBUTION.csv",
        "V35R3B_CAPACITY_RELEASE_RW.csv",
        "V35R3B_JOB_GRID_BINDING_AUDIT.json",
        "V35R3B_CANDIDATE_WATERFALL.csv",
        "V35R3B_CANDIDATE_REJECTION_REASONS.csv",
        "V35R3B_MODE_H0_RESULTS.json",
        "V35R3B_SERVICE_GATE.json",
        "V35R3B_GRID_EFFECT.json",
        "V35R3B_MISSING_EXTERNAL_AUTHORITY_REQUEST.json",
        "V35R3B_PRODUCTION_INTEGRATION_RECOMMENDATION.json",
        "V35R3B_REPAIR_LOG.json",
        "V35R3B_TEST_REPORT.json",
        "V35R3B_FINAL_REVIEW.json",
        "V35R3B_FINAL_REVIEW.md",
    }
    assert required <= {path.name for path in ARTIFACTS.iterdir()}
    review = _json("V35R3B_FINAL_REVIEW.json")
    assert set(review["numbered_report"]) == {str(value) for value in range(1, 70)}
    assert set(review["questions"]) == {f"Q{value}" for value in range(1, 13)}
    assert review["numbered_report"]["68"]["value"] == PRIMARY_CLASSIFICATION
    assert review["questions"]["Q8"].startswith("NO")
    assert review["questions"]["Q9"].startswith("NO")


def test_repair_log_preserves_scientific_rules():
    repair = _json("V35R3B_REPAIR_LOG.json")
    assert repair["unique_failure_signatures"] == 3
    assert not repair["scientific_rules_changed"]
    assert all(not row["scientific_rules_changed"] for row in repair["repairs"])
