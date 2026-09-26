"""Frozen lineage, time, source, and recipe contracts for V35R3D."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from dayahead.v35r3c.contracts import (
    AEST,
    HPCODA_HEAD,
    ISSUE_TIME,
    ISSUE_TIME_UTC,
    KESTREL_ARCHIVE,
    KESTREL_ARCHIVE_SHA256,
    TARGET_END,
    TARGET_START,
    W1,
    W3,
    W5,
)


PARENT_HEAD = "11553d456beb5a821408065aeea3bbda107961e9"
EXPECTED_BRANCH = "codex/v35r3d-kestrel-runtime-authority-closure"
PRODUCTION_HEAD = "c1d13a3e9c03c4b02ce87ccc5e69e5c7e0f01fb3"
WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3d_kestrel_runtime_authority_closure"
)
V35R3A_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3a_kestrel_scheduler_temporal"
)
V35R3B_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3b_job_power_runtime_forensic"
)
V35R3C_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3c_raddit_hpcoda_authority_recovery"
)
PRODUCTION_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v33x_fasttrack_grid_deliverable_aidc"
)
AUTHORITY_ROOT = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR_scheduler_authority"
)
HPCODA_ROOT = AUTHORITY_ROOT / "07_hpc-oda-commons"
HPCODA_RECIPE = (
    HPCODA_ROOT
    / "src"
    / "hpc_oda_commons"
    / "recipes"
    / "job-runtime"
    / "kestrel_moe_best_rolling.yml"
)
HPCODA_DESCRIPTOR = (
    HPCODA_ROOT
    / "src"
    / "hpc_oda_commons"
    / "datasets"
    / "descriptors"
    / "job-runtime"
    / "nlr_kestrel.yml"
)
VENV_REQUESTED = Path(
    r"C:\Users\kjw39\AppData\Local\MobileESS\venvs\v35r3d-runtime"
)

ARTIFACT_DIRNAME = "v35r3d_kestrel_runtime_authority_closure"
CACHE_DIRNAME = "v35r3d_kestrel_runtime_authority_closure"
LOG_DIRNAME = "v35r3d_kestrel_runtime_authority_closure"

CALIBRATION_START = TARGET_START - timedelta(days=8)  # 2025-03-24 00:00 fixed AEST
CALIBRATION_END = TARGET_START - timedelta(days=1)  # 2025-03-31 00:00 fixed AEST
B2_START = CALIBRATION_START - timedelta(days=1)
B2_SPLIT_TIMES = tuple(B2_START + timedelta(hours=6 * index) for index in range(4))
CALIBRATION_SPLIT_TIMES = tuple(
    CALIBRATION_START + timedelta(hours=6 * index) for index in range(28)
)
FULL_PREISSUE_SPLIT_TIMES = tuple(
    CALIBRATION_END - timedelta(hours=6 * (120 - index)) for index in range(120)
)
EARLIEST_TRAIN_END = FULL_PREISSUE_SPLIT_TIMES[0] - timedelta(days=120)

RECIPE_CONTRACT = {
    "recipe_id": "recipe.job_runtime.kestrel_moe_best_rolling",
    "model_id": "model.job_runtime_moe_xgboost",
    "model_version": "0.1.0",
    "n_windows": 120,
    "test_window_hours": 6,
    "training_lookback_days": 120,
    "enable_power_users": False,
    "time_decay_rate": 0.05,
    "objective": "reg:absoluteerror",
    "xgboost_version": "3.2.0",
}

SLOT_SECONDS = 900
TARGET_SLOTS = 96
GPU_CAPACITY = 624.0
TARGET_OFFSET_SLOTS = int((TARGET_START - ISSUE_TIME).total_seconds() // SLOT_SECONDS)
TARGET_END_SLOT = int((TARGET_END - ISSUE_TIME).total_seconds() // SLOT_SECONDS)

QUERY_FEATURE_FIELDS = (
    "requested_seconds",
    "num_nodes_req",
    "num_cores_req",
    "num_gpus_req",
    "requested_memory_mib",
    "partition",
    "qos",
    "user",
    "account",
)
MANDATORY_QUERY_FIELDS = (
    "requested_seconds",
    "num_nodes_req",
    "num_gpus_req",
    "partition",
    "qos",
)
FORBIDDEN_QUERY_FIELDS = frozenset(
    {
        "start_time",
        "end_time",
        "runtime_seconds",
        "num_nodes_alloc",
        "num_cores_alloc",
        "job_state",
        "exit_code",
        "nodelist",
        "shared_job_count",
        "nodes_shared",
        "jobs_shared",
        "grid_data",
        "Fresh",
    }
)

PRIMARY_CLASSIFICATIONS = frozenset(
    {
        "V35R3D_RUNTIME_R3Q_CAPACITY_TURNOVER_INCREASED",
        "V35R3D_RUNTIME_R3Q_CAPACITY_TURNOVER_UNCHANGED",
        "V35R3D_RUNTIME_R3_PASS_SAFE_CALIBRATION_FAIL",
        "V35R3D_RUNTIME_PARTIAL_COVERAGE_ONLY",
        "V35R3D_RUNTIME_QUERY_ADAPTER_EQUIVALENCE_FAIL",
        "V35R3D_RUNTIME_ENVIRONMENT_FAIL",
        "V35R3D_RUNTIME_IMPLEMENTATION_FAIL",
    }
)

__all__ = [
    "AEST",
    "ARTIFACT_DIRNAME",
    "B2_SPLIT_TIMES",
    "CACHE_DIRNAME",
    "CALIBRATION_END",
    "CALIBRATION_SPLIT_TIMES",
    "CALIBRATION_START",
    "EARLIEST_TRAIN_END",
    "EXPECTED_BRANCH",
    "FORBIDDEN_QUERY_FIELDS",
    "FULL_PREISSUE_SPLIT_TIMES",
    "GPU_CAPACITY",
    "HPCODA_DESCRIPTOR",
    "HPCODA_HEAD",
    "HPCODA_RECIPE",
    "HPCODA_ROOT",
    "ISSUE_TIME",
    "ISSUE_TIME_UTC",
    "KESTREL_ARCHIVE",
    "KESTREL_ARCHIVE_SHA256",
    "LOG_DIRNAME",
    "MANDATORY_QUERY_FIELDS",
    "PARENT_HEAD",
    "PRODUCTION_HEAD",
    "QUERY_FEATURE_FIELDS",
    "RECIPE_CONTRACT",
    "SLOT_SECONDS",
    "TARGET_END",
    "TARGET_END_SLOT",
    "TARGET_OFFSET_SLOTS",
    "TARGET_SLOTS",
    "TARGET_START",
    "VENV_REQUESTED",
    "W1",
    "W3",
    "W5",
    "WORKTREE",
]
