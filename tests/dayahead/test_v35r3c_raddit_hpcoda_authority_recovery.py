from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from dayahead.v35r3c.audit import (
    assert_causal_features,
    running_remaining_seconds,
    safe_runtime_seconds,
    sha256_file,
)
from dayahead.v35r3c.contracts import (
    ARTIFACT_DIRNAME,
    EXPECTED_BRANCH,
    EXPECTED_RECIPE_CONFIG,
    FORBIDDEN_QUERY_FEATURES,
    GPU_CAPACITY,
    HPCODA_DATASET_FEATURES,
    HPCODA_HEAD,
    HPCODA_ROOT,
    KESTREL_ARCHIVE,
    KESTREL_ARCHIVE_SHA256,
    PRIMARY_CLASSIFICATION,
    PRODUCTION_AUTHORITY,
    PRODUCTION_RECOMMENDATION,
    PRODUCTION_WORKTREE,
    RADDIT_HEAD,
    RADDIT_ROOT,
    RECOVERED_FILES,
    SOURCE_PARENT,
    V35R3A_WORKTREE,
    V35R3B_WORKTREE,
    WORKTREE,
)


REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
PARENT_B = REPO / "dayahead" / "artifacts" / "v35r3b_job_power_runtime_forensic"


def _json(name: str):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def _git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()


def test_exact_parent_branch_and_separate_worktree():
    assert REPO.resolve() == WORKTREE.resolve()
    assert _git(REPO, "branch", "--show-current") == EXPECTED_BRANCH
    assert _git(REPO, "merge-base", "HEAD", SOURCE_PARENT) == SOURCE_PARENT
    assert REPO.resolve() not in {
        V35R3A_WORKTREE.resolve(),
        V35R3B_WORKTREE.resolve(),
        PRODUCTION_WORKTREE.resolve(),
    }


def test_start_state_and_external_isolation_are_frozen():
    start = _json("V35R3C_START_STATE.json")
    isolation = _json("V35R3C_ISOLATION_AUDIT.json")
    assert start["parent_HEAD"] == SOURCE_PARENT
    assert start["worktree_HEAD_at_creation"] == SOURCE_PARENT
    assert start["worktree_status_at_creation"] == ""
    assert start["production_authority_commit"] == PRODUCTION_AUTHORITY
    assert isolation["worktree_separate"]
    assert isolation["vendor_states_unchanged"]
    assert isolation["external_worktree_states_unchanged"]
    assert isolation["parent_V35R3B_artifacts_unchanged"]
    assert isolation["production_files_changed_by_task"] == 0
    assert isolation["V35R3A_files_changed_by_task"] == 0
    assert isolation["V35R3B_files_changed_by_task"] == 0
    assert isolation["vendor_or_data_files_changed_by_task"] == 0
    assert isolation["network_calls"] == 0
    assert not isolation["push_performed"] and not isolation["merge_performed"]


def test_external_heads_and_preexisting_statuses_are_unchanged():
    start = _json("V35R3C_START_STATE.json")
    expected = {
        "RADDiT": RADDIT_HEAD,
        "hpc-oda-commons": HPCODA_HEAD,
    }
    for name, head in expected.items():
        state = start["vendor_repository_states_at_start"][name]
        path = Path(state["path"])
        assert _git(path, "rev-parse", "HEAD") == head == state["HEAD"]
        assert _git(path, "status", "--short") == state["status"]
    assert _git(PRODUCTION_WORKTREE, "rev-parse", "HEAD") == PRODUCTION_AUTHORITY


def test_all_five_recovered_files_are_exact_real_parquet():
    audit = _json("V35R3C_RECOVERED_LFS_VERIFICATION.json")
    assert audit["RADDIT_CORE_LFS_RECOVERY"] == "PASS"
    assert len(audit["files"]) == 5
    for row in audit["files"]:
        expected_size, expected_sha = RECOVERED_FILES[row["relative_path"]]
        path = Path(row["physical_path"])
        assert row["status"] == "PASS"
        assert row["actual_size"] == expected_size == path.stat().st_size
        assert row["actual_sha256"] == expected_sha == sha256_file(path)
        assert row["parquet_magic_start"] == row["parquet_magic_end"] == "PAR1"
        assert pq.ParquetFile(path).metadata.num_rows == row["row_count"]


def test_old_lfs_blocker_is_superseded_but_scientific_blockers_are_retested():
    audit = _json("V35R3C_RECOVERED_LFS_VERIFICATION.json")
    assert set(audit["superseded_V35R3B_blockers"].values()) == {
        "SUPERSEDED_BY_RECOVERED_EXTERNAL_AUTHORITY"
    }
    assert {
        "POWER_DOMAIN_MISMATCH",
        "POWER_ATTRIBUTION_AMBIGUOUS",
        "IDENTITY_BLOCKED",
        "GRID_BINDING_INCOMPLETE",
    } <= set(audit["not_automatically_superseded"])


def test_payload_schema_and_aggregate_classification_are_exact():
    schema = pd.read_csv(ARTIFACTS / "V35R3C_RADDIT_REAL_PAYLOAD_SCHEMA.csv")
    assert len(schema) == 5
    counts = dict(zip(schema["relative_path"], schema["row_count"], strict=True))
    assert counts == {
        "data/baseline_power_results.parquet": 1035281,
        "data/baseline_runtime_results.parquet": 1035281,
        "data/historic_job_trace.parquet": 2557884,
        "data/semantic_search_power_results.parquet": 1035365,
        "data/semantic_search_runtime_results.parquet": 1035365,
    }
    result_rows = schema.loc[~schema["relative_path"].str.contains("historic_job_trace")]
    assert result_rows["classification"].eq(
        "AGGREGATE_EVALUATION_PAYLOAD_NOT_DIRECT_APR01_JOIN_AUTHORITY"
    ).all()
    assert not result_rows["keyed"].astype(bool).any()
    assert not result_rows["Apr01_direct_join"].astype(bool).any()


def test_raddit_historic_trace_time_range_and_domain_are_recorded():
    coverage = _json("V35R3C_RADDIT_PAYLOAD_TIME_COVERAGE.json")
    historic = coverage["files"]["data/historic_job_trace.parquet"]
    assert historic["row_count"] == 2557884
    assert historic["time_ranges"]["submit_time"]["min"].startswith("2023-11-07")
    assert historic["time_ranges"]["submit_time"]["max"].startswith("2025-03-10")
    assert coverage["direct_Apr01_prediction_rows"] == 0
    domain = _json("V35R3C_RADDIT_POWER_DOMAIN_AUDIT.json")
    assert not domain["GPU_request_field_present"]
    assert not domain["H100_partition_identifiable"]
    assert not domain["shared_job_summation_safe"]


def test_identity_audit_rejects_coincidental_numeric_overlap():
    audit = _json("V35R3C_RADDIT_KESTREL_IDENTITY_AUDIT.json")
    assert audit["method"] == "EXACT_NORMALIZED_FULL_ID_ONLY_NO_FUZZY_MATCH"
    assert audit["RADDiT_total_job_IDs"] == 2557884
    assert audit["Kestrel_preissue_total_rows"] == 6309542
    assert audit["exact_normalized_full_ID_overlap"] == 1172189
    assert audit["date_restricted_overlap"] == 593692
    assert audit["timestamp_consistent_overlap"] == 0
    assert audit["timestamp_and_all_resource_consistent_overlap"] == 0
    assert audit["classification"] == "RADDIT_KESTREL_IDENTITY_DIRECT_JOIN_BLOCKED"


def test_identity_duplicates_and_apr01_populations_conserve():
    audit = _json("V35R3C_RADDIT_KESTREL_IDENTITY_AUDIT.json")
    assert audit["RADDiT_duplicate_extra_rows"] == 0
    assert audit["Kestrel_full_ID_duplicate_extra_rows"] == 0
    assert audit["Kestrel_numeric_raw_duplicate_extra_rows"] == 304311
    assert audit["one_to_many_conflicts_full_ID"] == 0
    assert (audit["Apr01_R_tau_total"], audit["Apr01_R_tau_overlap"]) == (243, 0)
    assert (audit["Apr01_P_tau_total"], audit["Apr01_P_tau_overlap"]) == (421, 0)
    assert (audit["Apr01_temporal_total"], audit["Apr01_temporal_overlap"]) == (339, 0)


def test_hpcoda_exact_head_recipe_and_source_sha_match():
    audit = _json("V35R3C_HPCODA_RUNTIME_SOURCE_AUDIT.json")
    assert audit["repository_HEAD"] == audit["expected_HEAD"] == HPCODA_HEAD
    assert audit["HEAD_match"]
    assert audit["actual_config"] == audit["expected_config"] == EXPECTED_RECIPE_CONFIG
    assert audit["config_semantic_equivalence"] == "PASS"
    assert audit["selected_source_files_modified"] == []
    assert audit["canonical_archive_sha_match"]
    assert audit["canonical_archive_actual_sha256"] == KESTREL_ARCHIVE_SHA256
    assert sha256_file(KESTREL_ARCHIVE) == KESTREL_ARCHIVE_SHA256


def test_runtime_feature_allowlist_is_submission_causal():
    audit = _json("V35R3C_HPCODA_RUNTIME_SOURCE_AUDIT.json")
    assert set(audit["eligible_submission_features"]) == set(HPCODA_DATASET_FEATURES)
    assert set(audit["eligible_submission_features"]).isdisjoint(FORBIDDEN_QUERY_FEATURES)
    assert audit["future_feature_reads"] == 0
    table = pd.read_csv(ARTIFACTS / "V35R3C_RUNTIME_FEATURE_CAUSALITY.csv")
    assert table["query_policy_read_count"].sum() == 0
    forbidden = table.loc[table["role"].eq("LABEL_OR_FORBIDDEN")]
    assert not forbidden["known_at_submission_or_issue"].astype(bool).any()
    assert not forbidden["allowed_by_pinned_policy"].astype(bool).any()
    assert_causal_features(list(HPCODA_DATASET_FEATURES))
    with pytest.raises(PermissionError, match="FORBIDDEN_QUERY_FEATURES"):
        assert_causal_features(["start_time", "runtime_seconds"])


def test_benchmark_and_adapter_fail_closed_without_substitution():
    source = _json("V35R3C_HPCODA_RUNTIME_SOURCE_AUDIT.json")
    benchmark = _json("V35R3C_HPCODA_RUNTIME_BENCHMARK_REPRO.json")
    equivalence = _json("V35R3C_HPCODA_QUERY_ADAPTER_EQUIVALENCE.json")
    assert source["dependency_versions"]["xgboost"] is None
    assert source["execution_status"] == "BLOCKED_MISSING_XGBOOST_DEPENDENCY"
    assert benchmark["status"] == "NOT_REPRODUCED_MISSING_XGBOOST_DEPENDENCY"
    assert not benchmark["attempted_network_or_install"]
    assert benchmark["scored_rows"] == 0
    assert benchmark["published_reference"]["MAE_seconds"] == 11527.4
    assert not equivalence["equivalence_pass"]
    assert equivalence["classification"] == "RUNTIME_QUERY_ADAPTER_EQUIVALENCE_FAIL"
    assert not equivalence["Apr01_adapter_authorized"]


def test_runtime_predictions_are_empty_and_authority_remains_r1():
    point = pd.read_parquet(ARTIFACTS / "V35R3C_APR01_RUNTIME_POINT.parquet")
    safe = pd.read_parquet(ARTIFACTS / "V35R3C_APR01_RUNTIME_SAFE.parquet")
    decision = _json("V35R3C_RUNTIME_AUTHORITY_DECISION.json")
    calibration = _json("V35R3C_RUNTIME_CALIBRATION.json")
    assert list(point.columns) == list(safe.columns)
    assert len(point) == len(safe) == 0
    assert decision["authority_level"] == "R1_REQUESTED_WALLTIME_ONLY"
    assert decision["Apr01_point_coverage_jobs"] == 0
    assert decision["Apr01_safe_coverage_jobs"] == 0
    assert not decision["R3_eligible"] and not decision["R3Q_eligible"]
    assert calibration["coverage_target"] == 0.9
    assert calibration["Apr01_outcomes_read"] == 0
    assert calibration["q90_positive_residual_seconds"] is None


def test_safe_runtime_and_running_remaining_invariants():
    assert safe_runtime_seconds(100.0, 200.0, 1000.0) == 900.0
    assert safe_runtime_seconds(800.0, 500.0, 1000.0) == 1000.0
    assert 900.0 <= safe_runtime_seconds(1000.0, 100.0, 5000.0) <= 5000.0
    assert running_remaining_seconds(1000.0, 1200.0, 2000.0) == 900.0
    assert running_remaining_seconds(4000.0, 1000.0, 3000.0) == 2000.0
    with pytest.raises(ValueError):
        safe_runtime_seconds(-1, 0, 1000)
    with pytest.raises(ValueError):
        running_remaining_seconds(1000, -1, 1000)


def test_raddit_power_replay_does_not_invent_missing_transform():
    replay = _json("V35R3C_RADDIT_POWER_REPLAY_AUDIT.json")
    assert not replay["required_input_present"]
    assert not replay["source_defined_creation_path_found"]
    assert replay["checkpoint_required"] is False
    assert all(value == "NOT_FOUND" or value.startswith("ABSENT") for value in replay["normalization_path"].values())
    assert not replay["P3_eligible"]
    assert replay["aggregate_payload_scientific_use"] == "MODEL_VALIDATION_ONLY_NOT_APR01_JOIN"
    assert replay["aggregate_evaluation_metrics"]["baseline_power_results.parquet"]["rows"] > 1_000_000


def test_h100_energy_and_power_paths_fail_closed():
    energy = _json("V35R3C_H100_ENERGY_FIELD_AUDIT.json")
    cohort = _json("V35R3C_H100_POWER_TRAINING_COHORT.json")
    decision = _json("V35R3C_POWER_AUTHORITY_DECISION.json")
    assert energy["H100_rows"] == 241730
    assert energy["H100_energy_nonnull_rows"] == energy["H100_energy_zero_rows"] == 36116
    assert energy["H100_energy_positive_rows"] == 0
    assert energy["H100_shared_count_zero_rows"] == 0
    assert energy["exclusive_full_positive_energy_training_rows"] == 0
    assert energy["Apr01_full_node_shape_jobs"] == 3
    assert energy["Apr01_partial_shared_shape_jobs"] == 336
    assert cohort["eligible_rows"] == 0 and not cohort["model_trained"]
    assert not cohort["P2_eligible"]
    assert decision["authority_level"] == "RADDIT_POWER_DOMAIN_MISMATCH_FOR_H100"
    assert decision["Apr01_H100_power_coverage_jobs"] == 0
    assert decision["Apr01_partial_shared_covered"] == 0
    assert decision["double_counting_prevented"]


def test_unauthorized_power_and_runtime_mode_artifacts_are_absent():
    absent = {
        "V35R3C_H100_POWER_MODEL_QUALITY.json",
        "V35R3C_APR01_JOB_POWER.parquet",
        "V35R3C_CAPACITY_RP.csv",
        "V35R3C_CAPACITY_RS.csv",
        "V35R3C_MODE_HR.json",
        "V35R3C_MODE_HP.json",
        "V35R3C_MODE_HPR.json",
        "V35R3C_FRESH_REVALIDATION.json",
    }
    assert absent.isdisjoint(path.name for path in ARTIFACTS.iterdir())


def test_rw_capacity_is_exactly_96_slots_and_capacity_feasible():
    capacity = pd.read_csv(ARTIFACTS / "V35R3C_CAPACITY_RW.csv")
    assert len(capacity) == 96
    assert capacity["duration_authority"].eq("RW_REQUESTED_WALLTIME").all()
    assert capacity["occupied_GPUs"].le(GPU_CAPACITY).all()
    assert capacity["occupied_GPUs"].eq(GPU_CAPACITY).all()
    assert capacity["free_GPUs"].eq(0).all()
    assert capacity["saturated_624"].astype(bool).all()


def test_h0_queue_and_service_semantics_are_preserved():
    h0 = _json("V35R3C_MODE_H0.json")
    service = _json("V35R3C_SERVICE_GATE.json")
    assert h0["running_jobs"] == 243
    assert h0["raw_pending_jobs"] == 421
    assert h0["schedulable_pending_jobs"] == 339
    assert h0["saturation_slots"] == 96
    assert h0["accepted_reprioritizations"] == 0
    assert service["H0_identity_result"] == "PASS_REVALIDATED"
    assert service["running_unchanged"]
    assert service["preemption_count"] == 0
    assert service["high_normal_delay_count"] == 0
    assert service["unsupported_deadline"] is False
    assert not service["standby_displaces_high_normal"]


def test_candidate_waterfall_and_primary_reason_conservation():
    waterfall = pd.read_csv(ARTIFACTS / "V35R3C_CANDIDATE_WATERFALL.csv")
    expected = {1: 339, 2: 202, 3: 0, 4: 0, 5: 27537, 6: 24, 7: 24, 8: 0, 9: 0, 10: 0, 11: 0, 12: 0}
    assert dict(zip(waterfall["stage"], waterfall["count"], strict=True)) == expected
    reasons = pd.read_csv(ARTIFACTS / "V35R3C_CANDIDATE_REJECTION_REASONS.csv")
    allowed = {
        "NO_RUNTIME_COVERAGE",
        "NO_POWER_COVERAGE",
        "POWER_DOMAIN_MISMATCH",
        "POWER_ATTRIBUTION_AMBIGUOUS",
        "NO_CAPACITY_RELEASE",
        "SAME_POWER",
        "RESOURCE_MISMATCH",
        "SERVICE_GATE_FAIL",
        "NO_W5_REDUCTION",
        "NO_PLANNING_IMPROVEMENT",
        "REBOUND",
        "GRID_BINDING_INCOMPLETE",
    }
    assert set(reasons["primary_reason"]) <= allowed
    pair_universe = reasons.loc[reasons["scope"].eq("POWER_AWARE_RAW_PAIR_UNIVERSE")]
    assert pair_universe["rejection_count"].sum() == 27537


def test_grid_binding_and_fresh_are_rejected_without_invention():
    binding = _json("V35R3C_GRID_BINDING_AUDIT.json")
    planning = _json("V35R3C_PLANNING_GRID_EFFECT.json")
    assert binding["production_commit"] == PRODUCTION_AUTHORITY
    assert binding["production_accepts_aggregate_AIDC_PCC_array"]
    assert binding["production_service_to_PCC_mapping_present"]
    assert binding["service_mapping_scope"] == "MESS service/station nodes only"
    assert not binding["job_or_resource_pool_to_IDC_mapping_present"]
    assert not binding["job_or_resource_pool_to_rack_mapping_present"]
    assert not binding["job_or_resource_pool_to_PCC_mapping_present"]
    assert not binding["job_or_resource_pool_to_phase_mapping_present"]
    assert binding["classification"] == "GRID_BINDING_INCOMPLETE"
    assert not binding["Fresh_eligibility"]
    assert planning["Fresh_status"] == "FRESH_NOT_RUN_GRID_BINDING_INCOMPLETE"
    assert "NO claim of NO_GRID_BENEFIT" in planning["interpretation"]


def test_strict_scope_production_and_mess_remain_untouched():
    decision = _json("V35R3C_PRODUCTION_INTEGRATION_DECISION.json")
    isolation = _json("V35R3C_ISOLATION_AUDIT.json")
    assert decision["PRODUCTION_INTEGRATION_RECOMMENDED"] == PRODUCTION_RECOMMENDATION == "NO"
    assert decision["production_files_modified"] == 0
    assert not decision["MESS_run"] and not decision["MESS_modified"]
    assert not decision["Apr02_or_later_run"]
    assert not decision["Apr21_or_later_read"]
    assert not decision["May_opened"]
    assert not decision["push"] and not decision["merge"]
    assert not isolation["MESS_run"]


def test_v35r3b_required_evidence_bytes_remain_unchanged():
    start = _json("V35R3C_START_STATE.json")
    for name, digest in start["parent_V35R3B_artifact_hashes"].items():
        assert sha256_file(PARENT_B / name) == digest


def test_changes_are_confined_to_v35r3c_namespaces():
    allowed = (
        "dayahead/artifacts/v35r3c_raddit_hpcoda_authority_recovery/",
        "dayahead/v35r3c/",
        "tools/v35r3c/",
        "tests/dayahead/test_v35r3c_",
    )
    for line in _git(REPO, "status", "--short").splitlines():
        path = line[3:].replace("\\", "/")
        assert path.startswith(allowed), path


def test_v35r3c_source_contains_no_random_or_network_client_imports():
    forbidden_imports = {"random", "requests", "urllib", "httpx", "aiohttp"}
    for source in (REPO / "dayahead" / "v35r3c").glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert imported.isdisjoint(forbidden_imports)


def test_required_artifacts_and_exact_final_report_shape():
    required = {
        "V35R3C_START_STATE.json",
        "V35R3C_ISOLATION_AUDIT.json",
        "V35R3C_RECOVERED_LFS_VERIFICATION.json",
        "V35R3C_RADDIT_REAL_PAYLOAD_SCHEMA.csv",
        "V35R3C_RADDIT_PAYLOAD_TIME_COVERAGE.json",
        "V35R3C_RADDIT_KESTREL_IDENTITY_AUDIT.json",
        "V35R3C_RADDIT_POWER_DOMAIN_AUDIT.json",
        "V35R3C_RADDIT_POWER_REPLAY_AUDIT.json",
        "V35R3C_HPCODA_RUNTIME_SOURCE_AUDIT.json",
        "V35R3C_HPCODA_RUNTIME_BENCHMARK_REPRO.json",
        "V35R3C_HPCODA_QUERY_ADAPTER_EQUIVALENCE.json",
        "V35R3C_RUNTIME_FEATURE_CAUSALITY.csv",
        "V35R3C_APR01_RUNTIME_POINT.parquet",
        "V35R3C_APR01_RUNTIME_SAFE.parquet",
        "V35R3C_RUNTIME_CALIBRATION.json",
        "V35R3C_RUNTIME_AUTHORITY_DECISION.json",
        "V35R3C_H100_ENERGY_FIELD_AUDIT.json",
        "V35R3C_H100_POWER_TRAINING_COHORT.json",
        "V35R3C_POWER_AUTHORITY_DECISION.json",
        "V35R3C_GRID_BINDING_AUDIT.json",
        "V35R3C_CAPACITY_RW.csv",
        "V35R3C_MODE_H0.json",
        "V35R3C_CANDIDATE_WATERFALL.csv",
        "V35R3C_CANDIDATE_REJECTION_REASONS.csv",
        "V35R3C_SERVICE_GATE.json",
        "V35R3C_PLANNING_GRID_EFFECT.json",
        "V35R3C_PRODUCTION_INTEGRATION_DECISION.json",
        "V35R3C_REPAIR_LOG.json",
        "V35R3C_TEST_REPORT.json",
        "V35R3C_FINAL_REVIEW.json",
        "V35R3C_FINAL_REVIEW.md",
    }
    assert required <= {path.name for path in ARTIFACTS.iterdir()}
    review = _json("V35R3C_FINAL_REVIEW.json")
    assert set(review["numbered_report"]) == {str(value) for value in range(1, 78)}
    assert set(review["questions"]) == {f"Q{value}" for value in range(1, 15)}
    assert review["numbered_report"]["73"]["value"] == "NO"
    assert review["numbered_report"]["74"]["value"] == "NO"
    assert review["numbered_report"]["76"]["value"] == PRIMARY_CLASSIFICATION
    assert review["numbered_report"]["77"]["value"].endswith("NO")
    assert _json("V35R3C_TEST_REPORT.json")["status"] in {"NOT_RUN", "PASS"}
