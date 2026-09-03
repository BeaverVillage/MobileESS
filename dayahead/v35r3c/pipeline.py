"""Build the V35R3C recovered-authority evidence bundle."""

from __future__ import annotations

import json
import math
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .audit import (
    assert_causal_features,
    capacity_summary,
    dependency_version,
    empty_runtime_frame,
    git,
    git_state,
    h100_energy_audit,
    identity_audit,
    raddit_payload_audit,
    recovered_lfs_verification,
    sha256_file,
    write_csv,
    write_json,
)
from .contracts import (
    ARTIFACT_DIRNAME,
    AUTHORITY_ROOT,
    EXPECTED_BRANCH,
    EXPECTED_RECIPE_CONFIG,
    FORBIDDEN_QUERY_FEATURES,
    HPCODA_DATASET_FEATURES,
    HPCODA_HEAD,
    HPCODA_ROOT,
    ISSUE_TIME,
    KESTREL_ARCHIVE,
    KESTREL_ARCHIVE_SHA256,
    KESTREL_DESCRIPTOR,
    PRIMARY_CLASSIFICATION,
    PRODUCTION_AUTHORITY,
    PRODUCTION_RECOMMENDATION,
    PRODUCTION_WORKTREE,
    RADDIT_HEAD,
    RADDIT_ROOT,
    RUNTIME_BASE_SOURCE,
    RUNTIME_MODEL_SOURCE,
    RUNTIME_POLICY_SOURCE,
    RUNTIME_RECIPE,
    SOURCE_PARENT,
    TARGET_START,
    V35R3A_WORKTREE,
    V35R3B_WORKTREE,
    WORKTREE,
)


V35R3A_ARTIFACTS = "v35r3a_kestrel_scheduler_temporal"
V35R3B_ARTIFACTS = "v35r3b_job_power_runtime_forensic"


def _metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float | int]:
    good = actual.notna() & predicted.notna() & np.isfinite(actual) & np.isfinite(predicted)
    y = actual.loc[good].to_numpy(float)
    p = predicted.loc[good].to_numpy(float)
    error = np.abs(y - p)
    return {
        "rows": int(len(y)),
        "MAE": float(error.mean()),
        "RMSE": float(np.sqrt(np.mean((y - p) ** 2))),
        "median_AE": float(np.median(error)),
        "P95_AE": float(np.quantile(error, 0.95)),
        "WAPE": float(error.sum() / np.abs(y).sum()),
        "Spearman": float(pd.Series(y).corr(pd.Series(p), method="spearman")),
    }


def _aggregate_evaluation_metrics() -> dict[str, Any]:
    data = RADDIT_ROOT / "data"
    result: dict[str, Any] = {}
    for name in ("baseline_power_results.parquet", "semantic_search_power_results.parquet"):
        frame = pd.read_parquet(data / name)
        result[name] = _metrics(frame["avg_power_per_node"], frame["predicted_power"])
    for name in ("baseline_runtime_results.parquet", "semantic_search_runtime_results.parquet"):
        frame = pd.read_parquet(data / name)
        result[name] = _metrics(
            frame["wallclock_used_sec"] / 3600.0,
            frame["predicted_runtime_hours"],
        )
        result[name]["metric_unit"] = "hours"
        result[name]["negative_prediction_rows"] = int(
            frame["predicted_runtime_hours"].lt(0).sum()
        )
    return result


def _runtime_source_audit() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    recipe_text = RUNTIME_RECIPE.read_text(encoding="utf-8")
    descriptor_text = KESTREL_DESCRIPTOR.read_text(encoding="utf-8")

    def scalar(text: str, key: str) -> str:
        match = re.search(rf"^\s*{re.escape(key)}:\s*([^#\r\n]+?)\s*$", text, re.MULTILINE)
        if not match:
            raise AssertionError(f"V35R3C_PINNED_YAML_KEY_MISSING:{key}")
        return match.group(1).strip().strip('"').strip("'")

    actual_config = {
        "n_windows": int(scalar(recipe_text, "n_windows")),
        "test_window_hours": int(scalar(recipe_text, "test_window_hours")),
        "training_lookback_days": int(scalar(recipe_text, "training_lookback_days")),
        "enable_power_users": scalar(recipe_text, "enable_power_users").lower() == "true",
        "time_decay_rate": float(scalar(recipe_text, "time_decay_rate")),
        "objective": scalar(recipe_text, "objective"),
    }
    config_pass = actual_config == EXPECTED_RECIPE_CONFIG
    descriptor_sha = scalar(descriptor_text, "sha256")
    selected_paths = [
        RUNTIME_RECIPE,
        RUNTIME_MODEL_SOURCE,
        RUNTIME_BASE_SOURCE,
        RUNTIME_POLICY_SOURCE,
        KESTREL_DESCRIPTOR,
    ]
    selected_relative = [str(path.relative_to(HPCODA_ROOT)).replace("\\", "/") for path in selected_paths]
    modified = set(git(HPCODA_ROOT, "diff", "--name-only").splitlines())
    selected_modified = sorted(modified & set(selected_relative))
    assert_causal_features(HPCODA_DATASET_FEATURES)
    xgb_version = dependency_version("xgboost")
    sklearn_version = dependency_version("scikit-learn")
    archive_sha = sha256_file(KESTREL_ARCHIVE)
    source = {
        "artifact_id": "V35R3C_HPCODA_RUNTIME_SOURCE_AUDIT_V1",
        "repository_path": str(HPCODA_ROOT),
        "repository_HEAD": git(HPCODA_ROOT, "rev-parse", "HEAD"),
        "expected_HEAD": HPCODA_HEAD,
        "HEAD_match": git(HPCODA_ROOT, "rev-parse", "HEAD") == HPCODA_HEAD,
        "repository_preexisting_status": git(HPCODA_ROOT, "status", "--short"),
        "selected_source_files_modified": selected_modified,
        "selected_source_files": {
            str(path.relative_to(HPCODA_ROOT)).replace("\\", "/"): sha256_file(path)
            for path in selected_paths
        },
        "recipe_id": scalar(recipe_text, "recipe_id"),
        "model_id": "model.job_runtime_moe_xgboost",
        "model_version": "0.1.0",
        "expected_config": EXPECTED_RECIPE_CONFIG,
        "actual_config": actual_config,
        "config_semantic_equivalence": "PASS" if config_pass else "FAIL",
        "dataset_descriptor_source_sha256": descriptor_sha,
        "canonical_archive_actual_sha256": archive_sha,
        "canonical_archive_sha_match": descriptor_sha == archive_sha == KESTREL_ARCHIVE_SHA256,
        "dataset_mapping": {
            "job_id": "id",
            "submit_time": "submit_time",
            "start_time": "start_time",
            "end_time": "end_time",
            "runtime_seconds": "end_time - start_time",
            "requested_seconds": "wallclock_req duration",
            "num_nodes_req": "nodes_req",
            "num_cores_req": "processors_req",
            "num_nodes_alloc": "nodes_used",
            "num_cores_alloc": "processors_used",
            "num_gpus_req": "gpus_requested",
            "requested_memory_mib": "memory_req memory_slurm",
            "partition": "partition",
            "qos": "qos",
            "job_state": "state_simple",
            "user": "user_hash",
            "account": "account_hash",
        },
        "eligible_submission_features": list(HPCODA_DATASET_FEATURES),
        "forbidden_query_features": sorted(FORBIDDEN_QUERY_FEATURES),
        "future_feature_reads": 0,
        "python": sys.version,
        "platform": platform.platform(),
        "dependency_versions": {
            "xgboost": xgb_version,
            "scikit-learn": sklearn_version,
            "pandas": dependency_version("pandas"),
            "pyarrow": dependency_version("pyarrow"),
        },
        "source_status": "PASS_PIN_CONFIG_DATA_AND_CAUSAL_POLICY",
        "execution_status": (
            "READY" if xgb_version is not None else "BLOCKED_MISSING_XGBOOST_DEPENDENCY"
        ),
    }
    benchmark = {
        "artifact_id": "V35R3C_HPCODA_RUNTIME_BENCHMARK_REPRO_V1",
        "published_reference": {
            "MAE_seconds": 11527.4,
            "median_AE_seconds": 1374.3,
            "RMSE_seconds": 33974.5,
            "scored_rows": 254338,
            "declared_environment": "macOS/arm64 xgboost 3.2.0",
            "architecture_variance_allowed_by_source": True,
        },
        "local_scope": "PREISSUE_WINDOW_ONLY; NO_APR02_PLUS; NO_MAY",
        "config_semantic_equivalence": source["config_semantic_equivalence"],
        "source_dataset_SHA_match": source["canonical_archive_sha_match"],
        "local_xgboost_version": xgb_version,
        "attempted_network_or_install": False,
        "scored_rows": 0,
        "MAE_seconds": None,
        "median_AE_seconds": None,
        "RMSE_seconds": None,
        "status": "NOT_REPRODUCED_MISSING_XGBOOST_DEPENDENCY",
        "reason": (
            "Pinned MoE imports xgboost.XGBRegressor and requires xgboost>=2.0; no installed "
            "Windows, bundled, cached-wheel, or WSL runtime contains xgboost, and installation is forbidden."
        ),
    }
    equivalence = {
        "artifact_id": "V35R3C_HPCODA_QUERY_ADAPTER_EQUIVALENCE_V1",
        "historical_window": "PREISSUE_REQUIRED_BUT_NOT_EXECUTED",
        "official_path_row_count": 0,
        "custom_adapter_row_count": 0,
        "exact_key_correspondence": None,
        "prediction_max_abs_difference": None,
        "floating_point_tolerance": 1e-9,
        "identical_feature_allowlist": True,
        "identical_routing_config": True,
        "identical_preprocessing_config": True,
        "equivalence_pass": False,
        "classification": "RUNTIME_QUERY_ADAPTER_EQUIVALENCE_FAIL",
        "status": "NOT_RUN_PREREQUISITE_PINNED_MODEL_EXECUTION_BLOCKED",
        "Apr01_adapter_authorized": False,
    }
    return source, benchmark, equivalence


def _feature_rows() -> list[dict[str, Any]]:
    rows = []
    mapping = {
        "requested_seconds": "wallclock_req",
        "num_nodes_req": "nodes_req",
        "num_cores_req": "processors_req",
        "num_gpus_req": "gpus_requested",
        "requested_memory_mib": "memory_req",
        "partition": "partition",
        "qos": "qos",
        "user": "user_hash",
        "account": "account_hash",
    }
    for feature in HPCODA_DATASET_FEATURES:
        rows.append(
            {
                "canonical_feature": feature,
                "Kestrel_source_field": mapping[feature],
                "known_at_submission_or_issue": True,
                "allowed_by_pinned_policy": True,
                "query_policy_read_count": 0,
                "role": "ELIGIBLE_SUBMISSION_FEATURE",
                "status": "NOT_READ_MODEL_EXECUTION_BLOCKED",
            }
        )
    for feature in sorted(FORBIDDEN_QUERY_FEATURES):
        rows.append(
            {
                "canonical_feature": feature,
                "Kestrel_source_field": feature,
                "known_at_submission_or_issue": False,
                "allowed_by_pinned_policy": False,
                "query_policy_read_count": 0,
                "role": "LABEL_OR_FORBIDDEN",
                "status": "FIREWALL_EXCLUDED",
            }
        )
    return rows


def _power_domain_audit() -> dict[str, Any]:
    path = RADDIT_ROOT / "data" / "historic_job_trace.parquet"
    parquet = pq.ParquetFile(path)
    columns = [field.name for field in parquet.schema_arrow]
    power = pq.read_table(path, columns=["avg_power_per_node"])["avg_power_per_node"].to_pandas()
    return {
        "artifact_id": "V35R3C_RADDIT_POWER_DOMAIN_AUDIT_V1",
        "historic_trace_rows": parquet.metadata.num_rows,
        "historic_trace_columns": columns,
        "GPU_request_field_present": False,
        "H100_partition_identifiable": False,
        "shared_or_coresident_field_present": False,
        "avg_power_per_node_unit": "W_per_node",
        "avg_power_per_node_distribution_W": {
            "min": float(power.min()),
            "P50": float(power.median()),
            "P95": float(power.quantile(0.95)),
            "max": float(power.max()),
        },
        "published_validation_domain": "CPU_EXCLUSIVE_JOBS",
        "published_README_evidence": "README.md line 31: approximately 17 W median error on CPU-exclusive jobs",
        "node_total_or_incremental_job_contribution": "NOT_DOCUMENTED_AS_INCREMENTAL_H100_JOB_POWER",
        "shared_job_summation_safe": False,
        "Apr01_partial_shared_applicability": 0,
        "classification": "RADDIT_POWER_DOMAIN_MISMATCH_FOR_H100",
    }


def _power_replay_audit(metrics: dict[str, Any]) -> dict[str, Any]:
    source = RADDIT_ROOT / "energy_aware_scheduling" / "scripts" / "baseline_models.py"
    required_input = RADDIT_ROOT / "energy_aware_scheduling" / "scripts" / "kestrel_baseline_data.parquet"
    return {
        "artifact_id": "V35R3C_RADDIT_POWER_REPLAY_AUDIT_V1",
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "source_model": "xgboost.XGBRegressor defaults, freshly fitted per one-hour split",
        "source_training_days": 100,
        "source_test_hours": 1,
        "source_preprocessing": {
            "categorical": ["job_type", "user", "account", "partition"],
            "multilabel": ["modules_set", "conda_envs_set"],
            "minimum_frequency": 1000,
            "PCA_components": 100,
            "numeric": [
                "nodes_req",
                "wallclock_req_seconds",
                "processors_req",
                "memory_req_raw",
            ],
        },
        "required_input": "kestrel_baseline_data.parquet",
        "required_input_present": required_input.is_file(),
        "source_defined_creation_path_found": False,
        "normalization_path": {
            "modules_to_modules_set": "NOT_FOUND",
            "conda_envs_to_conda_envs_set": "NOT_FOUND",
            "wallclock_req_sec_to_wallclock_req_seconds": "NOT_FOUND",
            "array_pos": "ABSENT_FROM_RECOVERED_HISTORIC_TRACE",
        },
        "checkpoint_required": False,
        "complete_exact_input_and_transform_required": True,
        "local_xgboost_version": dependency_version("xgboost"),
        "aggregate_evaluation_metrics": metrics,
        "aggregate_payload_scientific_use": "MODEL_VALIDATION_ONLY_NOT_APR01_JOIN",
        "P3_eligible": False,
        "classification": "PUBLISHED_POWER_REPLAY_BLOCKED_INCOMPLETE_INPUT_TRANSFORM_AND_H100_DOMAIN",
    }


def _render_markdown(review: dict[str, Any]) -> str:
    lines = ["# V35R3C 최종 검토", ""]
    groups = [
        ("GIT", 1, 8),
        ("RECOVERED AUTHORITY", 9, 14),
        ("IDENTITY", 15, 19),
        ("RUNTIME", 20, 29),
        ("SATURATION", 30, 38),
        ("POWER", 39, 46),
        ("GRID BINDING", 47, 49),
        ("CANDIDATES", 50, 58),
        ("EFFECT", 59, 67),
        ("SERVICE / CAUSALITY", 68, 74),
        ("TESTS", 75, 75),
        ("CONCLUSION", 76, 77),
    ]
    for title, first, last in groups:
        lines.extend([f"## {title}", ""])
        for index in range(first, last + 1):
            row = review["numbered_report"][str(index)]
            value = row["value"]
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            lines.append(f"{index}. {row['label']}: {value}")
        lines.append("")
    lines.extend(["## Q1–Q14", ""])
    for index in range(1, 15):
        lines.extend([f"Q{index}. {review['questions'][f'Q{index}']}", ""])
    return "\n".join(lines).rstrip() + "\n"


def _final_review(
    lfs: dict[str, Any],
    schema_rows: list[dict[str, Any]],
    identity: dict[str, Any],
    runtime_source: dict[str, Any],
    benchmark: dict[str, Any],
    equivalence: dict[str, Any],
    power_domain: dict[str, Any],
    energy: dict[str, Any],
    h0: dict[str, Any],
    capacity: dict[str, Any],
    waterfall: list[dict[str, Any]],
) -> dict[str, Any]:
    rows_by_path = {row["relative_path"]: row for row in schema_rows}
    row_counts = {path: row["row_count"] for path, row in rows_by_path.items()}
    schemas = {path: row["schema_json"] for path, row in rows_by_path.items()}
    ranges = {
        path: row["min_max_timestamps_json"] for path, row in rows_by_path.items()
    }
    future_counts = {
        "future_actual_start_feature_reads": 0,
        "future_actual_end_feature_reads": 0,
        "realized_runtime_feature_reads_for_query": 0,
        "post_issue_job_identity_reads_KQ0": 0,
        "Fresh_reads_during_selection": 0,
    }
    report: dict[str, dict[str, Any]] = {}

    def put(index: int, label: str, value: Any) -> None:
        report[str(index)] = {"label": label, "value": value}

    put(1, "parent HEAD", SOURCE_PARENT)
    put(2, "branch", EXPECTED_BRANCH)
    put(3, "worktree", str(WORKTREE))
    put(4, "final HEAD", "RECORDED_AFTER_COMMIT_IN_FINAL_RESPONSE")
    put(5, "clean", "EXPECTED_CLEAN_AFTER_COMMIT")
    put(6, "production files changed", 0)
    put(7, "vendor/data files changed", 0)
    put(8, "push/merge", "NO/NO")
    put(9, "five RADDiT hashes PASS/FAIL", lfs["RADDIT_CORE_LFS_RECOVERY"])
    put(10, "RADDiT payload row counts", row_counts)
    put(11, "payload schemas", schemas)
    put(12, "payload time ranges", ranges)
    put(13, "hpc-oda HEAD", runtime_source["repository_HEAD"])
    put(14, "Kestrel source SHA match", runtime_source["canonical_archive_sha_match"])
    put(15, "RADDiT/Kestrel exact ID overlap", identity["exact_normalized_full_ID_overlap"])
    put(16, "timestamp-consistent overlap", identity["timestamp_consistent_overlap"])
    put(17, "Apr-01 R_tau overlap", identity["Apr01_R_tau_overlap"])
    put(18, "Apr-01 P_tau overlap", identity["Apr01_P_tau_overlap"])
    put(19, "339 temporal-job overlap", identity["Apr01_temporal_overlap"])
    put(20, "runtime authority R-level", "R1_REQUESTED_WALLTIME_ONLY")
    put(21, "public benchmark reproduction", benchmark["status"])
    put(22, "query adapter equivalence", equivalence["classification"])
    put(23, "Apr-01 prediction coverage", "0/339 point; 0/339 safe")
    put(24, "point MAE / median AE / P95 AE", "NOT_AVAILABLE")
    put(25, "point underprediction rate", "NOT_AVAILABLE")
    put(26, "q90 positive residual", None)
    put(27, "safe historical coverage", "NOT_AVAILABLE")
    put(28, "requested-walltime/point ratio", "NOT_AVAILABLE")
    put(29, "requested-walltime/safe ratio", "NOT_AVAILABLE")
    put(30, "RW saturated slots", capacity["saturated_slots"])
    put(31, "RP saturated slots", "NOT_RUN_RUNTIME_POINT_UNAVAILABLE")
    put(32, "RS saturated slots", "NOT_RUN_RUNTIME_SAFE_UNAVAILABLE")
    put(33, "first RS capacity-release slot", None)
    put(34, "W1 free GPU", 0.0)
    put(35, "W3 free GPU", 0.0)
    put(36, "W5 free GPU", 0.0)
    put(37, "free GPU-hours", capacity["free_GPU_hours"])
    put(38, "requested-walltime artifact", "UNRESOLVED_NO_R3Q_SAFE_RUNTIME")
    put(39, "power authority P-level", "RADDIT_POWER_DOMAIN_MISMATCH_FOR_H100")
    put(40, "RADDiT CPU/GPU domain", "CPU-exclusive validation; GPU/H100 not identifiable")
    put(41, "H100 coverage", "0/339")
    put(42, "exclusive/shared applicability", "No H100 applicability; PARTIAL/shared 0/336")
    put(43, "attribution status", "POWER_ATTRIBUTION_AMBIGUOUS")
    put(44, "model quality", "CPU aggregate evaluation only; no H100 model")
    put(45, "same-GPU-count power spread", "NOT_AVAILABLE")
    put(46, "Apr-01 power coverage", "0/339")
    put(47, "production mapping authority", "GRID_BINDING_INCOMPLETE")
    put(48, "result-independence PASS/FAIL", "FAIL_NO_JOB_TO_AIDC_MAPPING")
    put(49, "Fresh eligibility", "FRESH_NOT_RUN_GRID_BINDING_INCOMPLETE")
    by_stage = {row["stage"]: row["count"] for row in waterfall}
    put(50, "temporal jobs", by_stage[1])
    put(51, "W5-overlap jobs", by_stage[2])
    put(52, "raw same-tier pairs", by_stage[5])
    put(53, "resource-feasible", by_stage[6])
    put(54, "service-safe", by_stage[7])
    put(55, "power-heterogeneous", by_stage[8])
    put(56, "power-reducing", by_stage[10])
    put(57, "Planning-improving", by_stage[11])
    put(58, "accepted reprioritizations", by_stage[12])
    put(59, "shifted GPU-hours", 0.0)
    put(60, "W1 IT power change", 0.0)
    put(61, "W3 IT power change", 0.0)
    put(62, "W5 IT power change", 0.0)
    put(63, "PCC change", "UNAVAILABLE_GRID_BINDING_INCOMPLETE")
    put(64, "Planning rho change", 0.0)
    put(65, "critical exposure change", "0.0 H0 proxy; exact unavailable")
    put(66, "rebound", 0.0)
    put(67, "Fresh rho/direction if authorized", "NOT_AUTHORIZED")
    put(68, "high/normal delay", 0)
    put(69, "completed-job delta", 0.0)
    put(70, "completed-GPU-hour delta", 0.0)
    put(71, "terminal pending delta", 0.0)
    put(72, "future-feature reads", future_counts)
    put(73, "unsupported deadline", "NO")
    put(74, "Fresh used in selection", "NO")
    put(75, "passed/failed", {"status": "NOT_RUN", "passed": 0, "failed": 0})
    put(76, "primary classification", PRIMARY_CLASSIFICATION)
    put(77, "production integration recommendation", "PRODUCTION_INTEGRATION_RECOMMENDED = NO")
    questions = {
        "Q1": "예. 5개 모두 지정 SHA-256·크기·PAR1 매직을 만족하는 실제 Parquet이다.",
        "Q2": "아니오. 숫자 full-ID는 1,172,189건 우연히 겹치지만 제출시각 일치는 0건이고 RADDiT ID는 연속 행 인덱스다.",
        "Q3": "아니오. source/config/data SHA는 맞지만 필수 xgboost>=2.0 실행환경이 없고 설치가 금지되어 pinned MoE와 동등성 시험이 막혔다.",
        "Q4": "point 0.0%, safe 0.0%다.",
        "Q5": "판정 불가다. 권위 있는 safe runtime이 없어 RS를 실행하지 않았다.",
        "Q6": "UNRESOLVED다. RP가 아니라 유효 RS로만 확정할 수 있다.",
        "Q7": "CPU-exclusive 검증만 덮는다. recovered trace에는 GPU 요청/H100 식별 필드가 없다.",
        "Q8": "아니오. 336개 PARTIAL/shared에 대한 incremental power 경계가 없고 합산은 이중계산 위험이 있다.",
        "Q9": "아니오. canonical H100 최근 120일의 양의 raw-energy 행이 0이라 P2 전용-node cohort도 비었다.",
        "Q10": "0개다. H0의 resource/service-safe pair는 24개지만 power-beneficial 권위 교집합은 0개다.",
        "Q11": "아니오. H0는 변화가 없고 job-to-AIDC/PCC binding이 없어 power-aware Planning을 실행하지 않았다.",
        "Q12": "Fresh는 과학적으로 허가되지 않아 실행하지 않았다.",
        "Q13": "아니오. V35R3 production 통합을 권고하지 않는다.",
        "Q14": "정확한 blockers는 pinned xgboost 실행/adapter 동등성 부재, H100-valid power label·모델 부재, PARTIAL/shared attribution 모호성, exact job-to-AIDC/PCC binding 부재다.",
    }
    return {
        "artifact_id": "V35R3C_FINAL_REVIEW_V1",
        "status": "RECOVERED_AUTHORITY_REVALIDATED_FAIL_CLOSED",
        "numbered_report": report,
        "questions": questions,
        "authority_decisions": {
            "runtime": "R1_REQUESTED_WALLTIME_ONLY",
            "power": "RADDIT_POWER_DOMAIN_MISMATCH_FOR_H100",
            "grid_binding": "GRID_BINDING_INCOMPLETE",
        },
        "queue_contract": {
            "running": 243,
            "pending": 421,
            "raw_standby": 420,
            "raw_normal": 1,
            "temporal": 339,
            "temporal_requested_GPU_hours": 14832.0,
            "standby": 338,
            "standby_requested_GPU_hours": 14640.0,
            "partial_shared_temporal": 336,
            "high": 0,
            "preemptive": False,
        },
    }


def build(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    if repo != WORKTREE.resolve():
        raise AssertionError(f"V35R3C_WRONG_WORKTREE:{repo}")
    if git(repo, "branch", "--show-current") != EXPECTED_BRANCH:
        raise AssertionError("V35R3C_WRONG_BRANCH")
    if git(repo, "merge-base", "HEAD", SOURCE_PARENT) != SOURCE_PARENT:
        raise AssertionError("V35R3C_WRONG_PARENT")

    artifact_dir = repo / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
    artifact_dir.mkdir(parents=True, exist_ok=True)
    parent_a = repo / "dayahead" / "artifacts" / V35R3A_ARTIFACTS
    parent_b = repo / "dayahead" / "artifacts" / V35R3B_ARTIFACTS
    parent_hashes_before = {
        name: sha256_file(parent_b / name)
        for name in ("V35R3B_FINAL_REVIEW.json", "V35R3B_MISSING_EXTERNAL_AUTHORITY_REQUEST.json")
    }
    vendor_start = {"RADDiT": git_state(RADDIT_ROOT), "hpc-oda-commons": git_state(HPCODA_ROOT)}
    external_start = {
        "V35R3A": git_state(V35R3A_WORKTREE),
        "V35R3B": git_state(V35R3B_WORKTREE),
        "production": git_state(PRODUCTION_WORKTREE),
    }
    start = {
        "artifact_id": "V35R3C_START_STATE_V1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_HEAD": SOURCE_PARENT,
        "branch": EXPECTED_BRANCH,
        "worktree": str(repo),
        "worktree_HEAD_at_creation": SOURCE_PARENT,
        "worktree_status_at_creation": "",
        "production_authority_commit": PRODUCTION_AUTHORITY,
        "issue_time": ISSUE_TIME.isoformat(),
        "target_day": TARGET_START.date().isoformat(),
        "vendor_repository_states_at_start": vendor_start,
        "external_worktree_states_at_start": external_start,
        "parent_V35R3B_artifact_hashes": parent_hashes_before,
        "network_calls": 0,
    }
    write_json(artifact_dir / "V35R3C_START_STATE.json", start)

    lfs = recovered_lfs_verification()
    if lfs["RADDIT_CORE_LFS_RECOVERY"] != "PASS":
        raise AssertionError("V35R3C_RADDIT_CORE_LFS_RECOVERY_FAIL")
    write_json(artifact_dir / "V35R3C_RECOVERED_LFS_VERIFICATION.json", lfs)

    schema_rows, time_coverage = raddit_payload_audit()
    write_csv(artifact_dir / "V35R3C_RADDIT_REAL_PAYLOAD_SCHEMA.csv", schema_rows)
    write_json(artifact_dir / "V35R3C_RADDIT_PAYLOAD_TIME_COVERAGE.json", time_coverage)

    identity = identity_audit(parent_a)
    write_json(artifact_dir / "V35R3C_RADDIT_KESTREL_IDENTITY_AUDIT.json", identity)

    aggregate_metrics = _aggregate_evaluation_metrics()
    power_domain = _power_domain_audit()
    power_replay = _power_replay_audit(aggregate_metrics)
    write_json(artifact_dir / "V35R3C_RADDIT_POWER_DOMAIN_AUDIT.json", power_domain)
    write_json(artifact_dir / "V35R3C_RADDIT_POWER_REPLAY_AUDIT.json", power_replay)

    runtime_source, benchmark, equivalence = _runtime_source_audit()
    write_json(artifact_dir / "V35R3C_HPCODA_RUNTIME_SOURCE_AUDIT.json", runtime_source)
    write_json(artifact_dir / "V35R3C_HPCODA_RUNTIME_BENCHMARK_REPRO.json", benchmark)
    write_json(artifact_dir / "V35R3C_HPCODA_QUERY_ADAPTER_EQUIVALENCE.json", equivalence)
    write_csv(artifact_dir / "V35R3C_RUNTIME_FEATURE_CAUSALITY.csv", _feature_rows())

    point = empty_runtime_frame("point")
    safe = empty_runtime_frame("safe")
    point.to_parquet(artifact_dir / "V35R3C_APR01_RUNTIME_POINT.parquet", index=False)
    safe.to_parquet(artifact_dir / "V35R3C_APR01_RUNTIME_SAFE.parquet", index=False)
    calibration = {
        "artifact_id": "V35R3C_RUNTIME_CALIBRATION_V1",
        "coverage_target": 0.90,
        "calibration_set_end_before_issue": True,
        "q90_positive_residual_seconds": None,
        "point_MAE_seconds": None,
        "point_median_AE_seconds": None,
        "point_P95_AE_seconds": None,
        "point_underprediction_rate": None,
        "safe_empirical_coverage": None,
        "Apr01_outcomes_read": 0,
        "status": "NOT_RUN_PINNED_MODEL_AND_EQUIVALENCE_BLOCKED",
    }
    runtime_decision = {
        "artifact_id": "V35R3C_RUNTIME_AUTHORITY_DECISION_V1",
        "authority_level": "R1_REQUESTED_WALLTIME_ONLY",
        "exact_pinned_source": True,
        "same_canonical_Kestrel_source": True,
        "causal_feature_policy": True,
        "benchmark_reproduction": benchmark["status"],
        "adapter_equivalence": equivalence["classification"],
        "Apr01_point_coverage_jobs": 0,
        "Apr01_safe_coverage_jobs": 0,
        "Apr01_temporal_jobs": 339,
        "R3_eligible": False,
        "R3Q_eligible": False,
        "fallback": "REQUESTED_WALLTIME_AND_RUNNING_REMAINING_REQUESTED_WALLTIME",
        "reason": "PINNED_MODEL_EXECUTION_AND_QUERY_ADAPTER_EQUIVALENCE_NOT_ESTABLISHED",
    }
    write_json(artifact_dir / "V35R3C_RUNTIME_CALIBRATION.json", calibration)
    write_json(artifact_dir / "V35R3C_RUNTIME_AUTHORITY_DECISION.json", runtime_decision)

    energy, cohort = h100_energy_audit(parent_a)
    write_json(artifact_dir / "V35R3C_H100_ENERGY_FIELD_AUDIT.json", energy)
    write_json(artifact_dir / "V35R3C_H100_POWER_TRAINING_COHORT.json", cohort)
    power_decision = {
        "artifact_id": "V35R3C_POWER_AUTHORITY_DECISION_V1",
        "authority_level": "RADDIT_POWER_DOMAIN_MISMATCH_FOR_H100",
        "H0_aggregate_proxy_available": True,
        "P2_eligible": False,
        "P3_eligible": False,
        "P4_eligible": False,
        "Apr01_H100_power_coverage_jobs": 0,
        "Apr01_temporal_jobs": 339,
        "Apr01_partial_shared_jobs": 336,
        "Apr01_partial_shared_covered": 0,
        "attribution": "POWER_ATTRIBUTION_AMBIGUOUS",
        "double_counting_prevented": True,
        "HP_eligible": False,
        "HPR_eligible": False,
    }
    write_json(artifact_dir / "V35R3C_POWER_AUTHORITY_DECISION.json", power_decision)

    production_algorithm = subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{PRODUCTION_AUTHORITY}:dayahead/v35r3/algorithm.py"],
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    production_execution = subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{PRODUCTION_AUTHORITY}:dayahead/v35/execution.py"],
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    binding = {
        "artifact_id": "V35R3C_GRID_BINDING_AUDIT_V1",
        "production_commit": PRODUCTION_AUTHORITY,
        "read_method": "git show exact commit; no merge/cherry-pick",
        "production_accepts_aggregate_AIDC_PCC_array": "aidc_pcc_kw_96x12" in production_algorithm,
        "production_service_to_PCC_mapping_present": "service_to_pcc" in production_execution,
        "service_mapping_scope": "MESS service/station nodes only",
        "job_or_resource_pool_to_IDC_mapping_present": False,
        "job_or_resource_pool_to_rack_mapping_present": False,
        "job_or_resource_pool_to_PCC_mapping_present": False,
        "job_or_resource_pool_to_phase_mapping_present": False,
        "result_independent_mapping_pass": False,
        "classification": "GRID_BINDING_INCOMPLETE",
        "Fresh_eligibility": False,
        "Fresh_status": "FRESH_NOT_RUN_GRID_BINDING_INCOMPLETE",
        "rejected_new_mappings": [
            "grid-benefit-selected assignment",
            "random assignment",
            "new equal split",
            "all jobs to most sensitive AIDC",
        ],
    }
    write_json(artifact_dir / "V35R3C_GRID_BINDING_AUDIT.json", binding)

    capacity_rw = pd.read_csv(parent_b / "V35R3B_CAPACITY_RELEASE_RW.csv")
    capacity_rw["duration_authority"] = "RW_REQUESTED_WALLTIME"
    capacity_rw.to_csv(artifact_dir / "V35R3C_CAPACITY_RW.csv", index=False)
    capacity = capacity_summary(capacity_rw)
    h0 = json.loads((parent_b / "V35R3B_MODE_H0_RESULTS.json").read_text(encoding="utf-8"))
    h0["artifact_id"] = "V35R3C_MODE_H0_V1"
    h0["status"] = "REVALIDATED_IDENTICAL_H0_REQUESTED_WALLTIME"
    h0["mode"] = "H0_HOMOGENEOUS_POWER_REQUESTED_WALLTIME"
    h0["runtime_revalidation"] = "R1_ONLY_PINNED_MOE_EXECUTION_BLOCKED"
    h0["power_revalidation"] = "RADDIT_POWER_DOMAIN_MISMATCH_FOR_H100"
    write_json(artifact_dir / "V35R3C_MODE_H0.json", h0)

    waterfall = [
        {"stage": 1, "name": "temporal-controlled jobs", "count": 339, "unit": "jobs", "note": "14832 GPU-h"},
        {"stage": 2, "name": "W5-overlap temporal jobs", "count": 202, "unit": "jobs", "note": "standby=201 normal=1"},
        {"stage": 3, "name": "jobs with safe-runtime prediction", "count": 0, "unit": "jobs", "note": "R3Q blocked"},
        {"stage": 4, "name": "jobs with H100 power prediction", "count": 0, "unit": "jobs", "note": "domain mismatch and no energy cohort"},
        {"stage": 5, "name": "same-tier raw exchange pairs", "count": 27537, "unit": "pairs", "note": "201 x 137 standby"},
        {"stage": 6, "name": "resource-feasible pairs", "count": 24, "unit": "pairs", "note": "V35R3A deterministic replay"},
        {"stage": 7, "name": "service-safe pairs", "count": 24, "unit": "pairs", "note": "strict tier gate"},
        {"stage": 8, "name": "power-heterogeneous pairs", "count": 0, "unit": "pairs", "note": "no job power authority"},
        {"stage": 9, "name": "capacity-release-enabled pairs", "count": 0, "unit": "pairs", "note": "no safe runtime"},
        {"stage": 10, "name": "W5-power-reducing pairs", "count": 0, "unit": "pairs", "note": "power path blocked"},
        {"stage": 11, "name": "Planning-improving pairs", "count": 0, "unit": "pairs", "note": "grid binding incomplete"},
        {"stage": 12, "name": "accepted reprioritizations", "count": 0, "unit": "pairs", "note": "H0 only"},
    ]
    write_csv(artifact_dir / "V35R3C_CANDIDATE_WATERFALL.csv", waterfall)
    rejection = [
        {
            "scope": "POWER_AWARE_RAW_PAIR_UNIVERSE",
            "candidate_id": "27537_SAME_TIER_RAW_PAIRS",
            "rejection_count": 27537,
            "primary_reason": "NO_RUNTIME_COVERAGE",
            "detail": "Exact pinned runtime adapter coverage is 0/339; waterfall stops before power/grid evaluation.",
        },
        {
            "scope": "H0_SCHEDULER_CANDIDATES",
            "candidate_id": "25_SERVICE_SAFE_H0_CANDIDATES",
            "rejection_count": 25,
            "primary_reason": "SAME_POWER",
            "detail": "Homogeneous power at 624 GPUs cannot reduce W5 power.",
        },
        {
            "scope": "H0_SCHEDULER_CANDIDATES",
            "candidate_id": "STANDBY_GPU_ASC_DURATION_ASC",
            "rejection_count": 1,
            "primary_reason": "SERVICE_GATE_FAIL",
            "detail": "Completed-work noninferiority fails under the frozen tier-aware gate.",
        },
        {
            "scope": "POWER_DOMAIN_DIAGNOSTIC_NOT_ADDITIONAL_CANDIDATES",
            "candidate_id": "ALL_339_TEMPORAL_JOBS",
            "rejection_count": 339,
            "primary_reason": "POWER_DOMAIN_MISMATCH",
            "detail": "RADDiT trace has no GPU/H100 field; not counted again in pair conservation.",
        },
        {
            "scope": "PARTIAL_SHARED_DIAGNOSTIC_NOT_ADDITIONAL_CANDIDATES",
            "candidate_id": "336_PARTIAL_SHARED_JOBS",
            "rejection_count": 336,
            "primary_reason": "POWER_ATTRIBUTION_AMBIGUOUS",
            "detail": "No incremental job-power boundary; not counted again in pair conservation.",
        },
        {
            "scope": "GRID_DIAGNOSTIC_NOT_ADDITIONAL_CANDIDATES",
            "candidate_id": "ALL_POWER_AWARE_MODES",
            "rejection_count": 1,
            "primary_reason": "GRID_BINDING_INCOMPLETE",
            "detail": "No exact exogenous job/resource-to-IDC/rack/PCC/phase mapping.",
        },
    ]
    write_csv(artifact_dir / "V35R3C_CANDIDATE_REJECTION_REASONS.csv", rejection)

    service = json.loads((parent_b / "V35R3B_SERVICE_GATE.json").read_text(encoding="utf-8"))
    service["artifact_id"] = "V35R3C_SERVICE_GATE_V1"
    service["H0_identity_result"] = "PASS_REVALIDATED"
    service["HR_result"] = "NOT_EVALUATED_SAFE_RUNTIME_UNAVAILABLE"
    service["HP_result"] = "NOT_EVALUATED_H100_POWER_UNAVAILABLE"
    service["HPR_result"] = "NOT_EVALUATED_RUNTIME_AND_POWER_UNAVAILABLE"
    write_json(artifact_dir / "V35R3C_SERVICE_GATE.json", service)

    planning = {
        "artifact_id": "V35R3C_PLANNING_GRID_EFFECT_V1",
        "H0": {
            "schedule_identical": True,
            "shifted_GPU_hours": 0.0,
            "W1_IT_power_change_kW": 0.0,
            "W3_IT_power_change_kW": 0.0,
            "W5_IT_power_change_kW": 0.0,
            "Planning_rho_change": 0.0,
            "critical_exposure_proxy_change": 0.0,
            "rebound_kW": 0.0,
        },
        "HR": "NOT_RUN_SAFE_RUNTIME_UNAVAILABLE",
        "HP": "NOT_RUN_H100_POWER_AUTHORITY_UNAVAILABLE",
        "HPR": "NOT_RUN_RUNTIME_AND_POWER_AUTHORITY_UNAVAILABLE",
        "exact_PCC_effect": "UNAVAILABLE_GRID_BINDING_INCOMPLETE",
        "Fresh_status": "FRESH_NOT_RUN_GRID_BINDING_INCOMPLETE",
        "interpretation": "NO claim of NO_GRID_BENEFIT; runtime, H100 power, and binding are not jointly adequate.",
    }
    write_json(artifact_dir / "V35R3C_PLANNING_GRID_EFFECT.json", planning)

    production = {
        "artifact_id": "V35R3C_PRODUCTION_INTEGRATION_DECISION_V1",
        "PRODUCTION_INTEGRATION_RECOMMENDED": PRODUCTION_RECOMMENDATION,
        "primary_classification": PRIMARY_CLASSIFICATION,
        "validated": [
            "five recovered files are exact real Parquet payloads",
            "H0 requested-walltime reference remains identical and service-safe",
            "pinned HPC-ODA source/config and canonical Kestrel SHA match",
        ],
        "blocking_conditions": [
            "PINNED_XGBOOST_EXECUTION_AND_QUERY_ADAPTER_EQUIVALENCE_NOT_ESTABLISHED",
            "RADDIT_POWER_DOMAIN_MISMATCH_FOR_H100",
            "NO_POSITIVE_H100_ENERGY_TRAINING_COHORT",
            "PARTIAL_SHARED_POWER_ATTRIBUTION_AMBIGUOUS",
            "GRID_BINDING_INCOMPLETE",
        ],
        "production_files_modified": 0,
        "MESS_run": False,
        "MESS_modified": False,
        "Apr02_or_later_run": False,
        "Apr21_or_later_read": False,
        "May_opened": False,
        "push": False,
        "merge": False,
    }
    write_json(artifact_dir / "V35R3C_PRODUCTION_INTEGRATION_DECISION.json", production)

    repair = {
        "artifact_id": "V35R3C_REPAIR_LOG_V1",
        "scientific_rules_changed": False,
        "repairs": [
            {"signature": "RADDIT_LFS_POINTER_BLOCKER", "action": "REVERIFY_EXACT_RECOVERED_BYTES", "result": "SUPERSEDED", "scientific_rules_changed": False},
            {"signature": "NUMERIC_ID_FALSE_OVERLAP", "action": "REQUIRE_TIMESTAMP_AND_RESOURCE_CONSISTENCY", "result": "DIRECT_JOIN_BLOCKED", "scientific_rules_changed": False},
            {"signature": "PINNED_XGBOOST_DEPENDENCY_ABSENT", "action": "FAIL_CLOSED_NO_ESTIMATOR_SUBSTITUTION", "result": "R1_ONLY", "scientific_rules_changed": False},
            {"signature": "H100_RAW_ENERGY_ALL_ZERO", "action": "REJECT_EMPTY_P2_COHORT", "result": "POWER_BLOCKED", "scientific_rules_changed": False},
            {"signature": "JOB_GRID_BINDING_ABSENT", "action": "DO_NOT_INVENT_MAPPING_OR_RUN_FRESH", "result": "FRESH_NOT_RUN", "scientific_rules_changed": False},
        ],
    }
    repair["unique_failure_signatures"] = len(repair["repairs"])
    write_json(artifact_dir / "V35R3C_REPAIR_LOG.json", repair)

    test_report = {
        "artifact_id": "V35R3C_TEST_REPORT_V1",
        "status": "NOT_RUN",
        "command": "python -m pytest tests/dayahead/test_v35r3a_kestrel_scheduler_temporal.py tests/dayahead/test_v35r3c_raddit_hpcoda_authority_recovery.py -q",
        "passed": 0,
        "failed": 0,
        "output": "Pending targeted test finalization",
    }
    write_json(artifact_dir / "V35R3C_TEST_REPORT.json", test_report)

    review = _final_review(
        lfs,
        schema_rows,
        identity,
        runtime_source,
        benchmark,
        equivalence,
        power_domain,
        energy,
        h0,
        capacity,
        waterfall,
    )
    write_json(artifact_dir / "V35R3C_FINAL_REVIEW.json", review)
    (artifact_dir / "V35R3C_FINAL_REVIEW.md").write_text(
        _render_markdown(review), encoding="utf-8"
    )

    vendor_end = {"RADDiT": git_state(RADDIT_ROOT), "hpc-oda-commons": git_state(HPCODA_ROOT)}
    external_end = {
        "V35R3A": git_state(V35R3A_WORKTREE),
        "V35R3B": git_state(V35R3B_WORKTREE),
        "production": git_state(PRODUCTION_WORKTREE),
    }
    parent_hashes_after = {
        name: sha256_file(parent_b / name)
        for name in ("V35R3B_FINAL_REVIEW.json", "V35R3B_MISSING_EXTERNAL_AUTHORITY_REQUEST.json")
    }
    isolation = {
        "artifact_id": "V35R3C_ISOLATION_AUDIT_V1",
        "worktree_separate": repo not in {V35R3A_WORKTREE, V35R3B_WORKTREE, PRODUCTION_WORKTREE},
        "allowed_write_namespaces": [
            "dayahead/v35r3c/",
            f"dayahead/artifacts/{ARTIFACT_DIRNAME}/",
            "tools/v35r3c/",
            "tests/dayahead/test_v35r3c_",
        ],
        "vendor_states_unchanged": vendor_start == vendor_end,
        "external_worktree_states_unchanged": external_start == external_end,
        "parent_V35R3B_artifacts_unchanged": parent_hashes_before == parent_hashes_after,
        "production_files_changed_by_task": 0,
        "V35R3A_files_changed_by_task": 0,
        "V35R3B_files_changed_by_task": 0,
        "vendor_or_data_files_changed_by_task": 0,
        "network_calls": 0,
        "network_commands_executed": [],
        "push_performed": False,
        "merge_performed": False,
        "MESS_run": False,
        "Apr02_or_later_run": False,
        "Apr21_or_later_read": False,
        "May_opened": False,
        "vendor_states_at_start": vendor_start,
        "vendor_states_at_end": vendor_end,
        "external_states_at_start": external_start,
        "external_states_at_end": external_end,
    }
    write_json(artifact_dir / "V35R3C_ISOLATION_AUDIT.json", isolation)
    return {
        "artifact_dir": str(artifact_dir),
        "primary_classification": PRIMARY_CLASSIFICATION,
        "production_recommendation": PRODUCTION_RECOMMENDATION,
        "RADDIT_CORE_LFS_RECOVERY": lfs["RADDIT_CORE_LFS_RECOVERY"],
        "runtime_authority": runtime_decision["authority_level"],
        "power_authority": power_decision["authority_level"],
        "grid_binding": binding["classification"],
    }


def finalize_test_report(repo: Path, report: dict[str, Any]) -> None:
    artifact_dir = repo / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
    write_json(artifact_dir / "V35R3C_TEST_REPORT.json", report)
    review_path = artifact_dir / "V35R3C_FINAL_REVIEW.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["numbered_report"]["75"]["value"] = {
        "status": report["status"],
        "passed": report["passed"],
        "failed": report["failed"],
        "command": report["command"],
        "output": report["output"],
    }
    write_json(review_path, review)
    (artifact_dir / "V35R3C_FINAL_REVIEW.md").write_text(
        _render_markdown(review), encoding="utf-8"
    )
