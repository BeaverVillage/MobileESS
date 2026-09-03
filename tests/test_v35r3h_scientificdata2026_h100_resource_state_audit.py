"""Targeted contract tests for the V35R3H authority audit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dayahead.v35r3h.audit import (
    filename_dimensions,
    gpu_type_from_path,
    integrate_power_joules,
    table_row_count,
    timebase_summary,
    workload_from_path,
)
from dayahead.v35r3h.contracts import (
    ARCHIVE_MD5,
    ARCHIVE_SHA256,
    BRANCH,
    CODE_HEAD,
    CONDITIONAL_ARTIFACT,
    FIGSHARE_DOI,
    FIGSHARE_VERSION,
    PARENT_HEAD,
    PRIMARY_CLASSIFICATION,
    REQUIRED_ARTIFACTS,
)


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "dayahead" / "artifacts" / "v35r3h_scientificdata2026_h100_resource_state_audit"


def load(name: str) -> dict:
    return json.loads((ART / name).read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-c", "core.longpaths=true", *args], cwd=ROOT, text=True).strip()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("x/Node_Dataset/H100/a.csv", "H100_CONFIRMED"),
        ("x/Node_Dataset/B200/a.csv", "B200_CONFIRMED"),
        ("x/Single_Machine_Dataset/a.csv", "NON_TARGET_RTX3060"),
        ("x/unknown/a.csv", "GPU_TYPE_UNKNOWN"),
    ],
)
def test_gpu_type_rule(path: str, expected: str) -> None:
    assert gpu_type_from_path(path) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("x/Image Generation Diffusion Models/a.csv", "IMAGE_GENERATION_DIFFUSION"),
        ("x/Text Generation LLMs/a.csv", "LLM_TEXT_GENERATION"),
        ("x/Feature Forecasting/a.csv", "FEATURE_FORECASTING"),
    ],
)
def test_workload_rule(path: str, expected: str) -> None:
    assert workload_from_path(path) == expected


def test_filename_dimensions() -> None:
    dims = filename_dimensions("x_ModelSize7B_batchsize8_SeqLength512_Deepspeedds_z3.csv")
    assert dims["batch_size"] == "8"
    assert dims["model_size"] == "7B"
    assert dims["sequence_length"] == "512"
    assert dims["parallelism"] == "DEEPSPEED_ZERO_STAGE_3"


def test_table_row_count() -> None:
    assert table_row_count(b"a,b\n1,2\n3,4\n") == 2


def test_native_timestamp_integration() -> None:
    timestamp = pd.Series(pd.to_datetime(["2026-01-01T00:00:00", "2026-01-01T00:00:01", "2026-01-01T00:00:02"]))
    energy, intervals = integrate_power_joules(timestamp, pd.Series([100.0, 100.0, 100.0]))
    assert energy == pytest.approx(200.0)
    assert intervals == 2


def test_timebase_duplicate_and_gap() -> None:
    timestamp = pd.Series(pd.to_datetime(["2026-01-01T00:00:00.000", "2026-01-01T00:00:00.020", "2026-01-01T00:00:00.020", "2026-01-01T00:00:00.100"]))
    summary = timebase_summary(timestamp, 0.02)
    assert summary["duplicate_timestamps"] == 1
    assert summary["gap_count"] == 1


def test_exact_lineage() -> None:
    assert git("merge-base", "HEAD", PARENT_HEAD) == PARENT_HEAD
    assert git("branch", "--show-current") == BRANCH
    assert load("V35R3H_START_STATE.json")["isolated_worktree"] is True


@pytest.mark.parametrize("field", ["production_files_changed", "MESS_files_changed", "source_files_changed"])
def test_no_forbidden_changes(field: str) -> None:
    assert load("V35R3H_ISOLATION_AUDIT.json")[field] == 0


@pytest.mark.parametrize(
    "field",
    [
        "Kestrel_Apr01_schedule_reads", "RW_schedule_reads", "RSP_schedule_reads",
        "Planning_reads", "Fresh_reads", "MESS_reads", "Apr02_plus_reads", "May_reads",
        "XGBoost_calls", "Gurobi_calls", "power_model_training_runs",
        "Kestrel_node_packing_runs", "RW_RSP_power_replay_runs",
    ],
)
def test_firewall_zero(field: str) -> None:
    assert load("V35R3H_ISOLATION_AUDIT.json")[field] == 0


def test_source_authority() -> None:
    source = load("V35R3H_SOURCE_AUTHORITY.json")
    assert source["Figshare_returned_DOI"] == FIGSHARE_DOI
    assert source["Figshare_version"] == FIGSHARE_VERSION
    assert source["archive"]["actual_MD5"] == ARCHIVE_MD5
    assert source["archive"]["actual_SHA256"] == ARCHIVE_SHA256
    assert source["all_Figshare_downloaded_files_size_hash"] == "PASS"
    assert source["code_repository"]["HEAD"] == CODE_HEAD
    assert source["code_repository"]["clean"] is True
    assert source["redownloads"] == 0


def test_file_inventory_conserved() -> None:
    inventory = pd.read_csv(ART / "V35R3H_FILE_INVENTORY.csv")
    assert len(inventory) == 106
    assert inventory["record_kind"].eq("ARCHIVE_MEMBER").sum() == 105
    assert inventory["file_type"].eq(".csv").sum() == 95
    assert inventory.loc[inventory["record_kind"].eq("ARCHIVE_MEMBER"), "local_SHA256"].notna().all()


def test_session_census() -> None:
    sessions = pd.read_parquet(ART / "V35R3H_SESSION_CENSUS.parquet")
    counts = sessions["GPU_type"].value_counts().to_dict()
    assert len(sessions) == 72
    assert counts == {"NON_TARGET_RTX3060": 40, "B200_CONFIRMED": 16, "H100_CONFIRMED": 16}
    assert sessions["source_content_SHA256"].is_unique


def test_gpu_type_firewall() -> None:
    authority = load("V35R3H_GPU_TYPE_AUTHORITY.json")
    assert authority["cohorts"]["GPU_TYPE_UNKNOWN"]["sessions"] == 0
    assert authority["B200_USED_FOR_H100_MAGNITUDE"] == "NO"
    profiles = pd.read_parquet(ART / "V35R3H_H100_GPU_PROFILE_STATISTICS.parquet")
    assert set(profiles["GPU_type"]) == {"H100_CONFIRMED"}


def test_sensor_boundary() -> None:
    sensors = load("V35R3H_SENSOR_SEMANTICS.json")
    assert sensors["WHOLE_NODE_POWER_DIRECTLY_MEASURED"] == "NO"
    summed = next(row for row in sensors["channels"] if row["field"] == "P_GPU_NODE_SUM")
    assert summed["measurement"] == "DERIVED"
    assert summed["boundary"] == "SUM_OF_8_GPU_COMPONENTS"
    assert "non-GPU" in summed["excludes"]


def test_timebase_native() -> None:
    timebase = pd.read_csv(ART / "V35R3H_TIMEBASE_AUDIT.csv")
    h100 = timebase.loc[timebase["GPU_type"].eq("H100_CONFIRMED")]
    assert len(timebase) == 72
    assert len(h100) == 16
    assert h100["native_or_resampled"].eq("NATIVE_RAW_TIMESTAMP").all()
    assert np.allclose(h100["delta_median_seconds"], 0.02, atol=1e-6)
    assert h100["duplicate_timestamps"].sum() == 0
    assert h100["non_monotonic_rows"].sum() == 0


def test_h100_profiles_and_energy() -> None:
    gpu = pd.read_parquet(ART / "V35R3H_H100_GPU_PROFILE_STATISTICS.parquet")
    node = pd.read_parquet(ART / "V35R3H_H100_NODE_GPU_SUM_STATISTICS.parquet")
    assert len(gpu) == 128
    assert len(node) == 16
    assert gpu.groupby("session_id")["gpu_id"].nunique().eq(8).all()
    assert gpu["energy_integral_joules"].gt(0).all()
    assert node["energy_integral_joules"].gt(0).all()
    assert node["power_boundary"].str.contains("8_SIMULTANEOUS_NVML").all()


def test_conservation() -> None:
    conservation = load("V35R3H_GPU_POWER_CONSERVATION.json")
    assert conservation["status"] == "PASS"
    assert conservation["GPU_IDs"] == list(range(8))
    assert conservation["missing_power_values"] == 0
    assert conservation["missing_values_counted_as_zero"] is False


def test_multigpu_not_partial_or_shared() -> None:
    semantics = load("V35R3H_MULTI_GPU_SEMANTICS.json")
    assert semantics["partial_occupancy_sessions"] == 0
    assert semantics["independent_co_resident_job_sessions"] == 0
    assert semantics["multi_node_sessions"] == 0


def test_direct_state_is_k8_only() -> None:
    active = load("V35R3H_H100_ACTIVE_GPU_STATE_CENSUS.json")
    support = load("V35R3H_H100_RESOURCE_STATE_SUPPORT.json")
    assert [(row["k"], row["sessions"]) for row in active["direct_states"]] == [(8, 16)]
    assert support["direct_k_states"] == [8]
    assert support["curve_directly_identified"] is False


@pytest.mark.parametrize(
    ("filename", "field", "expected"),
    [
        ("V35R3H_PARTIAL_GPU_STATE_AUTHORITY.json", "PARTIAL_GPU_PUBLIC_AUTHORITY", "NO"),
        ("V35R3H_IDLE_STATE_AUTHORITY.json", "IDLE_GPU_PUBLIC_AUTHORITY", "NO"),
        ("V35R3H_IDLE_STATE_AUTHORITY.json", "ALL_GPU_IDLE_STATE", "NO"),
        ("V35R3H_IDLE_STATE_AUTHORITY.json", "WHOLE_NODE_IDLE_BASE_POWER", "NO"),
        ("V35R3H_SHARED_STATE_AUTHORITY.json", "SHARED_MULTI_JOB_PUBLIC_AUTHORITY", "NO"),
    ],
)
def test_absent_state_authority(filename: str, field: str, expected: str) -> None:
    assert load(filename)[field] == expected


def test_component_envelope() -> None:
    envelope = pd.read_parquet(ART / "V35R3H_H100_GPU_STATE_ENVELOPE.parquet")
    row = envelope.iloc[0]
    assert len(envelope) == 1
    assert row["active_GPU_state_k"] == 8
    assert row["P_LOW"] < row["P_CENTER"] < row["P_HIGH"]
    assert row["P_LOW"] / 8 == pytest.approx(row["P_LOW_per_GPU_normalized"])


def test_workload_classes_retained() -> None:
    variability = load("V35R3H_H100_WORKLOAD_VARIABILITY.json")
    assert variability["classification"] == "MATERIAL_WORKLOAD_DEPENDENCE_AT_K8"
    assert len(variability["classes"]) == 2
    assert variability["collapse_before_audit"] is False


def test_valid_extremes_retained() -> None:
    quality = pd.read_csv(ART / "V35R3H_DATA_QUALITY_AUDIT.csv")
    h100 = quality.loc[quality["GPU_type"].eq("H100_CONFIRMED")]
    exclusion = load("V35R3H_EXCLUSION_MANIFEST.json")
    assert h100["negative_power_values"].sum() == 0
    assert h100["missing_power_values"].sum() == 0
    assert exclusion["retained_extremes"] is True
    assert exclusion["excluded_exact_duplicate_CSV_alias_count"] == 23


def test_dataset312_diagnostic_only() -> None:
    cross = load("V35R3H_DATASET312_COMPONENT_CROSSCHECK.json")
    assert cross["boundary_compatibility"] == "COMPATIBLE_NVML_PER_GPU_COMPONENT_POWER"
    assert cross["magnitude_fitting_or_scaling"] is False
    assert cross["Dataset312_authority_changed"] == "NO"


def test_bridge_matrix() -> None:
    rows = load("V35R3H_KESTREL_BRIDGE_ELIGIBILITY_MATRIX.json")["targets"]
    assert len(rows) == 10
    mapping = {row["target"]: row["classification"] for row in rows}
    assert mapping["H100 per-GPU component power"] == "DIRECTLY_SUPPORTED"
    assert mapping["H100 partial-GPU state power"] == "UNSUPPORTED"
    assert mapping["shared multi-job power"] == "UNSUPPORTED"
    assert mapping["whole-node active power"] == "UNSUPPORTED"


def test_authority_decision() -> None:
    decision = load("V35R3H_AUTHORITY_DECISION.json")
    assert decision["highest_H100_authority"] == "S2_H100_MULTI_GPU_NODE_COMPONENT_AUTHORITY"
    assert decision["whole_node_authority"] == "W0_NO_WHOLE_NODE_POWER"
    assert decision["primary_classification"] == PRIMARY_CLASSIFICATION


def test_next_step_deferred() -> None:
    decision = load("V35R3H_NEXT_STEP_DECISION.json")
    assert decision["KESTREL_NODE_PACKING_NEXT"] == "DEFER"
    assert decision["PUBLIC_H100_EXACT_PARTIAL_SHARED_POWER_BLOCKER_REMAINS"] == "YES"
    assert decision["PRODUCTION_INTEGRATION_RECOMMENDED"] == "NO"
    assert not (ART / CONDITIONAL_ARTIFACT).exists()


def test_artifact_contract_complete() -> None:
    assert len(REQUIRED_ARTIFACTS) == 35
    present = {path.name for path in ART.iterdir() if path.is_file()}
    assert set(REQUIRED_ARTIFACTS) <= present


def test_final_review_exact_shape() -> None:
    review = load("V35R3H_FINAL_REVIEW.json")
    assert list(review["numbered_report"]) == [str(index) for index in range(1, 81)]
    assert list(review["questions"]) == [f"Q{index}" for index in range(1, 24)]
    assert review["numbered_report"]["60"] == "NO"
    assert review["numbered_report"]["61"] == "NO"
    assert review["numbered_report"]["71"] == "NO"


def test_reconciliation_discrepancies_explicit() -> None:
    reconciliation = load("V35R3H_PAPER_CODE_DATA_RECONCILIATION.json")
    classifications = [row["classification"] for row in reconciliation["discrepancies"]]
    assert ["PAPER_DATA_MISMATCH", "DATA_CODE_MISMATCH"] in classifications
    assert "UNRESOLVED" in classifications
    assert reconciliation["silent_conflict_resolution"] is False


def test_compute_is_bounded() -> None:
    compute = load("V35R3H_COMPUTE_ACCOUNTING.json")
    assert compute["worker_thread_count"] == 1
    assert compute["heavy_ML_or_optimization"] is False
    assert compute["raw_samples"] == 1_843_334
    assert compute["valid_H100_samples"] == 720_000
    assert compute["valid_B200_samples"] == 720_000
