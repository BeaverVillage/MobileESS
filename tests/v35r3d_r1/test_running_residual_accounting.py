"""Targeted verification of V35R3D-R1 without any model refit."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dayahead.v35r3d_r1.contracts import (
    ARTIFACT_DIRNAME,
    BRANCH,
    CALIBRATION_END,
    CALIBRATION_START,
    PARENT_CACHE,
    PARENT_HEAD,
    QUANTILE_LEVEL,
    TARGET_END_SLOT,
)


ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "dayahead" / "artifacts" / ARTIFACT_DIRNAME


def load(name: str) -> dict:
    return json.loads((ART / name).read_text(encoding="utf-8"))


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_exact_parent() -> None:
    start = load("V35R3D_R1_START_STATE.json")
    assert start["parent_actual"] == PARENT_HEAD


def test_exact_branch() -> None:
    assert load("V35R3D_R1_START_STATE.json")["branch_actual"] == BRANCH


def test_isolated_and_no_external_writes() -> None:
    audit = load("V35R3D_R1_ISOLATION_AUDIT.json")
    assert audit["isolated_worktree"] is True
    assert audit["production_files_changed"] == 0
    assert audit["vendor_files_changed"] == 0
    assert audit["parent_files_changed"] == 0
    assert audit["push"] is False and audit["merge"] is False


def test_parent_cache_hashes_unchanged() -> None:
    authority = load("V35R3D_R1_PARENT_RUNTIME_AUTHORITY.json")
    for record in authority["reuse_manifest"]["files"]:
        assert file_sha(Path(record["path"])) == record["sha256"]


def test_no_xgboost_refit_and_32_windows_preserved() -> None:
    reuse = load("V35R3D_R1_PARENT_RUNTIME_AUTHORITY.json")["reuse_manifest"]
    assert reuse["xgboost_fit_calls"] == 0
    assert reuse["window_prediction_files"] == 32


def test_running_survival_partition() -> None:
    frame = pd.read_csv(ART / "V35R3D_R1_RUNNING_SURVIVAL_AUDIT.csv")
    assert len(frame) == 243
    assert frame["survival_category"].value_counts().to_dict() == {
        "A_ELAPSED_LT_POINT": 170,
        "C_ELAPSED_GE_SAFE": 73,
    }


def test_elapsed_uses_known_current_start_only() -> None:
    frame = pd.read_csv(ART / "V35R3D_R1_RUNNING_SURVIVAL_AUDIT.csv")
    assert (frame["elapsed_seconds_at_issue"] >= 0).all()
    assert not any("end_time" in column for column in frame.columns)


def test_rsp_running_uses_requested_remaining() -> None:
    frame = pd.read_parquet(ART / "V35R3D_R1_RSP_DURATION_AUTHORITY.parquet")
    running = frame.loc[frame["state_at_issue"].eq("RUNNING")]
    expected = np.maximum(
        running["requested_walltime_seconds"] - running["elapsed_seconds_at_issue"], 900.0
    )
    assert np.allclose(running["RSP_duration_seconds"], expected)
    assert running["duration_authority"].eq("REQUESTED_REMAINING").all()


def test_expired_safe_does_not_imply_one_slot() -> None:
    survival = pd.read_csv(ART / "V35R3D_R1_RUNNING_SURVIVAL_AUDIT.csv")
    authority = pd.read_parquet(ART / "V35R3D_R1_RSP_DURATION_AUTHORITY.parquet")
    expired = survival.loc[survival["survival_category"].eq("C_ELAPSED_GE_SAFE"), "job_id"].astype(str)
    selected = authority.loc[authority["job_id"].astype(str).isin(expired)]
    assert len(selected) == 73
    assert (selected["RSP_duration_seconds"] > 900).all()


def test_minimum_one_slot_and_exceeds_reported() -> None:
    authority = pd.read_parquet(ART / "V35R3D_R1_RSP_DURATION_AUTHORITY.parquet")
    running = authority.loc[authority["state_at_issue"].eq("RUNNING")]
    assert (running["RSP_duration_seconds"] >= 900).all()
    summary = load("V35R3D_R1_RUNNING_SURVIVAL_SUMMARY.json")
    assert summary["categories"]["D_elapsed_ge_requested"]["jobs"] == int(
        running["RUNNING_ELAPSED_EXCEEDS_REQUESTED_WALLTIME"].sum()
    )


def test_no_residual_model_created() -> None:
    contract = load("V35R3D_R1_SAFE_RUNTIME_CONTRACT.json")
    assert contract["running_residual_model"] == "NOT_CREATED"
    assert contract["memorylessness_assumed"] is False


def test_calibration_interval_and_rows() -> None:
    audit = load("V35R3D_R1_CALIBRATION_QUANTILE_AUDIT.json")
    assert audit["interval_start_AEST"] == CALIBRATION_START
    assert audit["interval_end_exclusive_AEST"] == CALIBRATION_END
    assert audit["rows"] == 87824


def test_empirical_quantile_exact() -> None:
    frame = pd.read_parquet(PARENT_CACHE / "calibration_predictions.parquet")
    residual = np.maximum(frame["actual_runtime_seconds"] - frame["point_runtime_seconds"], 0)
    expected = float(np.quantile(residual, QUANTILE_LEVEL, method="linear"))
    assert load("V35R3D_R1_CALIBRATION_QUANTILE_AUDIT.json")["Q_EMP90"]["q_seconds"] == expected


def test_conformal_quantile_exact() -> None:
    frame = pd.read_parquet(PARENT_CACHE / "calibration_predictions.parquet")
    residual = np.sort(
        np.maximum(frame["actual_runtime_seconds"] - frame["point_runtime_seconds"], 0)
    )
    k = min(len(residual), math.ceil((len(residual) + 1) * QUANTILE_LEVEL))
    audit = load("V35R3D_R1_CALIBRATION_QUANTILE_AUDIT.json")
    assert audit["Q_CONF90"]["rank_k"] == k
    assert audit["Q_CONF90"]["q_seconds"] == float(residual[k - 1])


def test_uncapped_and_capped_coverage_separated() -> None:
    audit = load("V35R3D_R1_CALIBRATION_QUANTILE_AUDIT.json")
    assert audit["Q_CONF90"]["uncapped_coverage"] >= 0.90
    assert audit["Q_CONF90"]["capped_coverage"] < 0.90
    assert audit["SAFE_COVERAGE_LIMITED_BY_REQUESTED_WALLTIME_CAP"] is True
    assert audit["Q_CONF90"]["actual_gt_requested_fraction"] > 0


def test_q_selection_is_scheduler_independent() -> None:
    audit = load("V35R3D_R1_CALIBRATION_QUANTILE_AUDIT.json")
    assert audit["selected_q_method"] == "Q_CONF90_FINITE_SAMPLE_SPLIT_CONFORMAL"
    assert audit["scheduler_result_used_for_q_selection"] is False
    assert audit["Apr01_actual_labels_read"] == 0


def test_coverage_decomposition_dimensions() -> None:
    frame = pd.read_csv(ART / "V35R3D_R1_CALIBRATION_COVERAGE_DECOMPOSITION.csv")
    assert {"ALL", "REQUESTED_WALLTIME_BIN", "QOS", "GPU_REQUEST_COUNT"} <= set(
        frame["group_dimension"]
    )
    assert set(frame["quantile_method"]) == {"Q_EMP90", "Q_CONF90"}


def test_start_interval_partition_is_disjoint() -> None:
    frame = pd.read_parquet(ART / "V35R3D_R1_STANDBY_START_ACCOUNTING.parquet")
    allowed = {"PRE_DAY", "APR01", "NOT_STARTED_BY_T2"}
    for mode in ("RW", "OLD_RS", "RSP"):
        assert set(frame[f"start_interval_{mode}"]) <= allowed
        assert len(frame[f"start_interval_{mode}"]) == frame["job_id"].nunique()


@pytest.mark.parametrize("mode", ["RW", "OLD_RS", "RSP"])
def test_pending_start_conservation(mode: str) -> None:
    summary = load("V35R3D_R1_STANDBY_START_ACCOUNTING_SUMMARY.json")["modes"][mode]
    assert summary["initial_pending_jobs"] == 339
    assert summary["started_by_T2"] + summary["terminal_pending_jobs"] == 339
    assert summary["pending_conservation_PASS"] is True
    assert summary["standby_conservation_PASS"] is True
    assert summary["normal_conservation_PASS"] is True


def test_accounting_label_ambiguity_corrected() -> None:
    summary = load("V35R3D_R1_STANDBY_START_ACCOUNTING_SUMMARY.json")
    assert summary["classification"] == "ACCOUNTING_LABEL_AMBIGUITY_CORRECTED"
    assert summary["modes"]["OLD_RS"]["standby"]["PRE_DAY"] == 338
    assert summary["modes"]["OLD_RS"]["standby"]["APR01"] == 0


@pytest.mark.parametrize("mode", ["RW", "OLD_RS", "RSP"])
def test_capacity_conservation_and_bounds(mode: str) -> None:
    frame = pd.read_csv(ART / f"V35R3D_R1_CAPACITY_{mode}.csv")
    assert len(frame) == TARGET_END_SLOT == 120
    assert np.allclose(frame["conservation_residual_GPUs"], 0)
    assert frame["post_refill_GPU_occupancy"].between(0, 624).all()


def test_deterministic_rw_and_rsp() -> None:
    audit = load("V35R3D_R1_CAPACITY_CONSERVATION.json")["modes"]
    assert audit["RW_parent_equivalent"] is True
    assert audit["RSP_deterministic_replay"] is True
    assert audit["all_conservation_PASS"] is True


def test_rsp_running_authority_conservative() -> None:
    frame = pd.read_parquet(ART / "V35R3D_R1_RSP_DURATION_AUTHORITY.parquet")
    assert frame.loc[frame["state_at_issue"].eq("RUNNING"), "duration_authority"].eq(
        "REQUESTED_REMAINING"
    ).all()


def test_critical_windows_unchanged_and_runtime_only() -> None:
    artifact = load("V35R3D_R1_W1_W3_W5_OPPORTUNITY.json")
    assert artifact["windows_unchanged"] is True
    assert artifact["power_grid_calculation"] is False
    assert set(artifact["modes"]["RSP"]) == {"W1", "W3", "W5"}


def test_pre_w5_metric_runtime_only() -> None:
    artifact = load("V35R3D_R1_PRE_W5_HORIZON_OPPORTUNITY.json")
    assert artifact["runtime_occupancy_only"] is True
    assert artifact["RW_RSP_composition_comparison"]["composition_changed"] is True


def test_causality_and_scope_firewall() -> None:
    isolation = load("V35R3D_R1_ISOLATION_AUDIT.json")
    for field in (
        "Dataset312_reads",
        "H100_power_runs",
        "Planning_runs",
        "Fresh_reads",
        "MESS_runs",
        "Apr02_plus_outcome_reads",
        "May_reads",
    ):
        assert isolation[field] == 0
    final = load("V35R3D_R1_FINAL_REVIEW.json")["numbered_report"]
    assert final["80"] == final["81"] == final["82"] == final["83"] == "0"
    assert final["84"] == "NO"


def test_authority_not_upgraded_and_production_no() -> None:
    authority = load("V35R3D_R1_RUNTIME_AUTHORITY_DECISION.json")
    assert authority["runtime_authority"] == "R2_DIAGNOSTIC_CAUSAL_RUNTIME"
    assert authority["RUNNING_RESIDUAL_AUTHORITY"] == "REQUESTED_WALLTIME_CONSERVATIVE"
    assert load("V35R3D_R1_H100_POWER_RESEARCH_DECISION.json")[
        "PRODUCTION_INTEGRATION_RECOMMENDED"
    ] == "NO"
