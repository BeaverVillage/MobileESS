"""Fast artifact-level verification for the V35R3D scientific closure."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dayahead.v35r3d.contracts import (
    ARTIFACT_DIRNAME,
    CALIBRATION_END,
    EXPECTED_BRANCH,
    HPCODA_HEAD,
    KESTREL_ARCHIVE_SHA256,
    PARENT_HEAD,
    RECIPE_CONTRACT,
)


ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "dayahead" / "artifacts" / ARTIFACT_DIRNAME


def load(name: str) -> dict:
    return json.loads((ART / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def environment() -> dict:
    return load("V35R3D_RUNTIME_ENVIRONMENT.json")


@pytest.fixture(scope="module")
def isolation() -> dict:
    return load("V35R3D_ISOLATION_AUDIT.json")


@pytest.fixture(scope="module")
def benchmark() -> dict:
    return load("V35R3D_PUBLIC_BENCHMARK_REPRO.json")


@pytest.fixture(scope="module")
def equivalence() -> dict:
    return load("V35R3D_QUERY_ADAPTER_EQUIVALENCE.json")


@pytest.fixture(scope="module")
def calibration() -> dict:
    return load("V35R3D_RUNTIME_CALIBRATION.json")


def test_environment_outside_repository(environment: dict) -> None:
    assert environment["environment_outside_repository"] is True


def test_base_environment_untouched(environment: dict) -> None:
    assert environment["base_environment_modified"] is False


def test_xgboost_exact(environment: dict) -> None:
    assert environment["packages"]["xgboost"] == "3.2.0"


def test_hpc_oda_is_local_pinned(environment: dict) -> None:
    assert environment["hpc_oda_source_HEAD"] == HPCODA_HEAD
    assert environment["hpc_oda_direct_url"]["url"].startswith("file:")


def test_no_vendor_modification() -> None:
    assert load("V35R3D_HPCODA_SOURCE_AUDIT.json")["vendor_files_modified_by_V35R3D"] == []


def test_parent_exact() -> None:
    assert load("V35R3D_START_STATE.json")["parent_actual"] == PARENT_HEAD


def test_branch_exact() -> None:
    assert load("V35R3D_START_STATE.json")["branch_actual"] == EXPECTED_BRANCH


def test_isolated_worktree(isolation: dict) -> None:
    assert isolation["isolated_worktree"] is True


@pytest.mark.parametrize(
    "field",
    [
        "production_files_changed_by_V35R3D",
        "vendor_files_changed_by_V35R3D",
        "V35R3A_files_changed_by_V35R3D",
        "V35R3B_files_changed_by_V35R3D",
        "V35R3C_files_changed_by_V35R3D",
    ],
)
def test_no_out_of_scope_writes(isolation: dict, field: str) -> None:
    assert isolation[field] == 0


def test_no_push_merge(isolation: dict) -> None:
    assert isolation["push_performed"] is False
    assert isolation["merge_performed"] is False


def test_kestrel_sha_exact() -> None:
    audit = load("V35R3D_KESTREL_SOURCE_AUDIT.json")
    assert audit["actual_SHA256"] == KESTREL_ARCHIVE_SHA256
    assert audit["SHA_PASS"] is True


def test_hpcoda_head_exact() -> None:
    assert load("V35R3D_HPCODA_SOURCE_AUDIT.json")["actual_HEAD"] == HPCODA_HEAD


def test_timestamps_timezone_aware(calibration: dict) -> None:
    assert pd.Timestamp(calibration["interval_start_AEST"]).tz is not None
    assert pd.Timestamp(calibration["interval_end_exclusive_AEST"]).tz is not None


def test_no_apr02_science(isolation: dict) -> None:
    assert isolation["Apr02_plus_science_reads"] == 0


def test_feature_firewall_counters_zero() -> None:
    ledger = pd.read_csv(ART / "V35R3D_RUNTIME_FEATURE_CAUSALITY.csv").set_index("counter")
    for field in (
        "future_actual_start_feature_reads",
        "future_actual_end_feature_reads",
        "realized_runtime_query_feature_reads",
        "future_job_identity_reads_KQ0",
        "grid_feedback_reads",
        "Fresh_reads",
        "pending_actual_start_reads",
        "Apr01_actual_label_reads",
    ):
        assert str(ledger.loc[field, "value"]) in {"0", "0.0"}


def test_job_id_not_ml_feature() -> None:
    contract = load("V35R3D_QUERY_ADAPTER_CONTRACT.json")
    assert "job_id" not in contract["query_allowlist"]
    assert contract["job_id_role"].startswith("row identifier only")


def test_exact_recipe() -> None:
    audit = load("V35R3D_PUBLIC_RECIPE_CONTRACT.json")
    assert audit["exact_recipe_config_PASS"] is True
    assert audit["resolved_contract"] == RECIPE_CONTRACT


@pytest.mark.parametrize("stage", ["B0", "B1", "B2"])
def test_benchmark_stages_pass(benchmark: dict, stage: str) -> None:
    assert benchmark[stage]["status"] == "PASS"


def test_reference_subset_finite(benchmark: dict) -> None:
    metrics = benchmark["B3"]["metrics"]
    assert benchmark["B3"]["windows_executed"] == 32
    assert metrics["finite"] is True
    assert all(np.isfinite(metrics[key]) for key in ("MAE_seconds", "median_AE_seconds", "RMSE_seconds"))
    assert benchmark["B3"]["same_order_of_magnitude"] is True


@pytest.mark.parametrize(
    "field",
    [
        "same_training_rows",
        "same_query_rows",
        "same_feature_policy",
        "same_routing",
        "same_preprocessing",
        "exact_query_key_correspondence",
    ],
)
def test_adapter_equivalence_components(equivalence: dict, field: str) -> None:
    assert equivalence[field] is True


def test_adapter_predictions_match(equivalence: dict) -> None:
    assert equivalence["PASS"] is True
    assert equivalence["prediction_max_abs_difference"] <= equivalence["prediction_tolerance"]


def test_calibration_ends_pre_issue(calibration: dict) -> None:
    assert pd.Timestamp(calibration["interval_end_exclusive_AEST"]) == pd.Timestamp(CALIBRATION_END)
    assert calibration["all_labels_pre_issue"] is True


def test_calibration_q90_preissue(calibration: dict) -> None:
    assert calibration["q90_plus_seconds"] >= 0
    assert calibration["Apr01_actual_labels_read"] == 0


def test_safe_bounds() -> None:
    frame = pd.read_parquet(ART / "V35R3D_APR01_RUNTIME_SAFE.parquet")
    covered = frame.loc[frame["safe_covered"]]
    assert (covered["T_hat_safe_seconds"] >= 900).all()
    assert (covered["T_hat_safe_seconds"] <= covered["requested_walltime_seconds"] + 1e-9).all()


def test_running_elapsed_and_remaining_are_causal() -> None:
    frame = pd.read_parquet(ART / "V35R3D_APR01_RUNTIME_SAFE.parquet")
    running = frame.loc[frame["state_at_issue"].eq("RUNNING") & frame["safe_covered"]]
    assert (running["elapsed_seconds_at_issue"] >= 0).all()
    assert (running["remaining_safe_seconds"] >= 900).all()
    assert (
        running["elapsed_seconds_at_issue"] + running["remaining_safe_seconds"]
        <= running["requested_walltime_seconds"] + 1e-9
    ).all()


@pytest.mark.parametrize("mode", ["RW", "RP", "RS"])
def test_scheduler_capacity_and_accounting(mode: str) -> None:
    frame = pd.read_csv(ART / f"V35R3D_CAPACITY_{mode}.csv")
    assert len(frame) == 96
    assert frame["post_refill_occupied_GPUs"].max() <= 624 + 1e-9
    assert np.allclose(
        frame["pre_refill_continuing_GPUs"] + frame["started_GPUs_at_boundary"],
        frame["post_refill_occupied_GPUs"],
    )


@pytest.mark.parametrize("mode", ["RW", "RP", "RS"])
def test_scheduler_service_invariants(mode: str) -> None:
    service = load("V35R3D_SERVICE_ACCOUNTING.json")["modes"][mode]
    assert service["running_unchanged_at_issue"] is True
    assert service["preemption_count"] == 0
    assert service["negative_execution_intervals"] == 0
    assert service["one_duration_authority_per_job"] is True
    assert service["fallback_jobs_conservative"] is True
    assert service["tier_precedence_preserved"] is True
    assert service["standby_did_not_displace_high_normal"] is True
    assert service["deterministic_replay"] is True


def test_rw_reproduces_parent_scheduler() -> None:
    service = load("V35R3D_SERVICE_ACCOUNTING.json")["modes"]["RW"]
    assert service["parent_RW_schedule_reproduced"] is True


def test_scope_excludes_power_grid_fresh_mess(isolation: dict) -> None:
    for field in ("power_model_runs", "grid_model_runs", "Fresh_runs", "MESS_runs", "May_science_reads"):
        assert isolation[field] == 0


def test_production_recommendation_no() -> None:
    decision = load("V35R3D_RESEARCH_DECISION.json")
    assert decision["PRODUCTION_INTEGRATION_RECOMMENDED"] == "NO"
