"""Frozen authority and scope contracts for V35R3C.

The package is deliberately isolated from production AIDC/MESS code.  It may
read the pinned production commit and external authority, but it writes only
inside the V35R3C prototype namespaces.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


SOURCE_PARENT = "27b427827bdf1c397b66391f012be41ef9b2ae87"
PRODUCTION_AUTHORITY = "c1d13a3e9c03c4b02ce87ccc5e69e5c7e0f01fb3"
EXPECTED_BRANCH = "codex/v35r3c-raddit-hpcoda-authority-recovery"
ARTIFACT_DIRNAME = "v35r3c_raddit_hpcoda_authority_recovery"
PRIMARY_CLASSIFICATION = "V35R3C_RECOVERED_AUTHORITY_STILL_INSUFFICIENT"
PRODUCTION_RECOMMENDATION = "NO"

WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3c_raddit_hpcoda_authority_recovery"
)
V35R3B_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3b_job_power_runtime_forensic"
)
V35R3A_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3a_kestrel_scheduler_temporal"
)
PRODUCTION_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v33x_fasttrack_grid_deliverable_aidc"
)
AUTHORITY_ROOT = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR_scheduler_authority"
)
RADDIT_ROOT = AUTHORITY_ROOT / "02_RADDiT"
HPCODA_ROOT = AUTHORITY_ROOT / "07_hpc-oda-commons"
RECOVERY_ROOT = AUTHORITY_ROOT / "99_manifest" / "web_authority_recovery"
KESTREL_ARCHIVE = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip"
)

RADDIT_HEAD = "ae1bf132addb41b469f3ef25a7626fe5ab06bc81"
HPCODA_HEAD = "218d75f56b783ebfd698100f9406cfb46fa04c01"
KESTREL_ARCHIVE_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"

RECOVERED_FILES = {
    "data/baseline_power_results.parquet": (
        8_730_834,
        "5b94583ed2a944b9554ffdd0bdc8ca61cf17d3cd122ded47e3eeb7549145b419",
    ),
    "data/baseline_runtime_results.parquet": (
        2_981_549,
        "b02a175f8ae95605e66355f77ebb65393783671826bff3b3f544d3effc0144ea",
    ),
    "data/historic_job_trace.parquet": (
        91_292_582,
        "b8361fddd68b057604eb1740a94b27c260f135036dc562d3cbce8a8591279c94",
    ),
    "data/semantic_search_power_results.parquet": (
        14_648_367,
        "da300027aa194f27ff12fc1937c896da6cd4e76a2ed4e6e1db98e766730926e6",
    ),
    "data/semantic_search_runtime_results.parquet": (
        8_778_440,
        "68d86c98b7822ba58a0e34f7187f8dbb4f8a884677748911fe5fb149334d4a15",
    ),
}

AEST = timezone(timedelta(hours=10), name="AEST_FIXED")
ISSUE_TIME = datetime(2025, 3, 31, 18, 0, tzinfo=AEST)
ISSUE_TIME_UTC = ISSUE_TIME.astimezone(timezone.utc)
TARGET_START = datetime(2025, 4, 1, 0, 0, tzinfo=AEST)
TARGET_END = datetime(2025, 4, 2, 0, 0, tzinfo=AEST)
SLOT_SECONDS = 900
TARGET_SLOTS = 96
GPU_CAPACITY = 624.0
W1 = (74,)
W3 = (73, 74, 75)
W5 = (72, 73, 74, 75, 76)

RUNTIME_RECIPE = (
    HPCODA_ROOT
    / "src"
    / "hpc_oda_commons"
    / "recipes"
    / "job-runtime"
    / "kestrel_moe_best_rolling.yml"
)
RUNTIME_MODEL_SOURCE = (
    HPCODA_ROOT
    / "src"
    / "hpc_oda_commons"
    / "models"
    / "job_runtime_moe_xgboost"
    / "model.py"
)
RUNTIME_BASE_SOURCE = (
    HPCODA_ROOT
    / "src"
    / "hpc_oda_commons"
    / "models"
    / "rolling_tabular"
    / "base.py"
)
RUNTIME_POLICY_SOURCE = (
    HPCODA_ROOT / "src" / "hpc_oda_commons" / "models" / "feature_policy.py"
)
KESTREL_DESCRIPTOR = (
    HPCODA_ROOT
    / "src"
    / "hpc_oda_commons"
    / "datasets"
    / "descriptors"
    / "job-runtime"
    / "nlr_kestrel.yml"
)

EXPECTED_RECIPE_CONFIG = {
    "n_windows": 120,
    "test_window_hours": 6,
    "training_lookback_days": 120,
    "enable_power_users": False,
    "time_decay_rate": 0.05,
    "objective": "reg:absoluteerror",
}

HPCODA_DATASET_FEATURES = (
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

FORBIDDEN_QUERY_FEATURES = frozenset(
    {
        "start_time",
        "end_time",
        "runtime_seconds",
        "job_state",
        "exit_code",
        "num_nodes_alloc",
        "num_cores_alloc",
        "allocgpus",
        "nodelist",
        "consumed_energy_raw_joules",
        "fresh",
        "grid_result",
    }
)
