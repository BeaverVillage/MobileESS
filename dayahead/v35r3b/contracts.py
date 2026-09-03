"""Frozen boundaries for the V35R3B Apr-01 local-only forensic.

The package is deliberately separated from production AIDC/MESS science.  It
reads the completed V35R3A evidence and downloaded authority in read-only mode.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


SOURCE_PARENT = "7db7b46a8aa30b9ea763ea1c1a8abd97b5026b31"
EXPECTED_BRANCH = "codex/v35r3b-job-power-runtime-forensic"
ARTIFACT_DIRNAME = "v35r3b_job_power_runtime_forensic"

WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3b_job_power_runtime_forensic"
)
PARENT_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3a_kestrel_scheduler_temporal"
)
ACTIVE_V35R3_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v33x_fasttrack_grid_deliverable_aidc"
)
AUTHORITY_ROOT = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR_scheduler_authority"
)
KESTREL_ARCHIVE = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip"
)

RADDIT_ROOT = AUTHORITY_ROOT / "02_RADDiT"
FASTSIM_ROOT = AUTHORITY_ROOT / "03_FastSim"
NLR_DOCS_ROOT = AUTHORITY_ROOT / "04_NLR_HPC_docs_repo"
EAGLE_ROOT = AUTHORITY_ROOT / "05_Eagle_jobs_reference"

RADDIT_HEAD = "ae1bf132addb41b469f3ef25a7626fe5ab06bc81"
FASTSIM_HEAD = "68c8ba7ede664e7678a84a924eaedaa58503defb"
NLR_DOCS_HEAD = "914f6da551424f6227e9bd65e0745b6686a6cbd8"
EAGLE_HEAD = "ef34f9fa5edabb04b460dcf58929b841555a2e2d"
KESTREL_ARCHIVE_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
KESTREL_DATACARD_SHA256 = "0139b75b80cd3029e0af54e22fc0dbad3080e92a8a7a602f1bd62cd7a36f62e9"

AEST = timezone(timedelta(hours=10), name="AEST_FIXED")
ISSUE_TIME = datetime(2025, 3, 31, 18, 0, tzinfo=AEST)
TARGET_START = datetime(2025, 4, 1, 0, 0, tzinfo=AEST)
TARGET_END = datetime(2025, 4, 2, 0, 0, tzinfo=AEST)
SLOT_MINUTES = 15
TARGET_SLOTS = 96
GPU_CAPACITY = 624.0
W1 = (74,)
W3 = (73, 74, 75)
W5 = (72, 73, 74, 75, 76)

POWER_AUTHORITY_LEVEL = "P1_AGGREGATE_PROXY_ONLY"
RUNTIME_AUTHORITY_LEVEL = "R1_REQUESTED_WALLTIME_ONLY"
PRIMARY_CLASSIFICATION = "V35R3B_LOCAL_AUTHORITY_INSUFFICIENT_MULTIPLE_BLOCKERS"
PRODUCTION_RECOMMENDATION = "NO"
GRID_BINDING_STATUS = "GRID_BINDING_INCOMPLETE"
FRESH_STATUS = "FRESH_NOT_RUN_GRID_BINDING_INCOMPLETE"
SATURATION_CAUSE = "UNRESOLVED_NO_CAUSAL_RUNTIME_AUTHORITY"

FORBIDDEN_CAUSAL_FEATURES = frozenset(
    {
        "future_actual_start",
        "future_actual_start_time",
        "future_actual_end",
        "future_actual_end_time",
        "realized_runtime",
        "wallclock_used",
        "wallclock_used_sec",
        "realized_power",
        "avg_power_per_node",
        "future_nodelist",
        "nodelist",
        "future_sharing_state",
        "completion_status",
        "fresh_output",
        "d_day_grid_measurement",
    }
)

NETWORK_COMMANDS_EXECUTED: tuple[str, ...] = ()
PUSH_PERFORMED = False
MERGE_PERFORMED = False
