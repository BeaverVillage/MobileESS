"""Frozen scope and field contracts for V35R3A.

This module deliberately contains no production imports.  It defines the
Apr-01-only boundary and the conservative public-authority interpretation
used by the prototype.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


SOURCE_BASELINE = "1b6916f2829106db9ad5a3589e0cdfa0508c4d5b"
EXPECTED_BRANCH = "codex/v35r3a-kestrel-scheduler-temporal"
ACTIVE_V35R3_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v33x_fasttrack_grid_deliverable_aidc"
)
AUTHORITY_ROOT = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR_scheduler_authority"
)
KESTREL_ZIP = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip"
)

AEST = timezone(timedelta(hours=10), name="AEST_FIXED")
ISSUE_TIME = datetime(2025, 3, 31, 18, 0, tzinfo=AEST)
TARGET_START = datetime(2025, 4, 1, 0, 0, tzinfo=AEST)
TARGET_END = datetime(2025, 4, 2, 0, 0, tzinfo=AEST)
VALIDATION_START = datetime(2025, 3, 24, 0, 0, tzinfo=AEST)
VALIDATION_END = datetime(2025, 3, 31, 0, 0, tzinfo=AEST)
SLOT_MINUTES = 15
SIMULATION_SLOTS = int((TARGET_END - ISSUE_TIME).total_seconds() // (SLOT_MINUTES * 60))
TARGET_SLOTS = 96

# The saved NLR Kestrel page says 156 GPU nodes and four H100 GPUs per node.
GPU_NODE_CAPACITY = 156
GPUS_PER_NODE = 4
GPU_CAPACITY = GPU_NODE_CAPACITY * GPUS_PER_NODE

W1 = (74,)
W3 = (73, 74, 75)
W5 = (72, 73, 74, 75, 76)
CRITICAL_ASSET = "line.sw2::A"
CRITICAL_SLOT = 74

RUNNING_FIXED = "RUNNING_FIXED"
HIGH_PROTECTED = "HIGH_PROTECTED"
NORMAL_QUEUE_CONTROLLED = "NORMAL_QUEUE_CONTROLLED"
STANDBY_QUEUE_CONTROLLED = "STANDBY_QUEUE_CONTROLLED"
# Aggregate reporting class.  Individual jobs retain their service-tier class.
TEMPORAL_QUEUE_CONTROLLED = "TEMPORAL_QUEUE_CONTROLLED"
TEMPORAL_CONTROLLED_CLASSES = frozenset(
    {NORMAL_QUEUE_CONTROLLED, STANDBY_QUEUE_CONTROLLED}
)
# Submission records that cannot be scheduled safely remain excluded rather
# than being forced into one of the controllable tiers.
FIXED_PROTECTED = "FIXED_PROTECTED"
SPATIO_TEMPORAL_CANDIDATE = "SPATIO_TEMPORAL_CANDIDATE"
PREEMPTIVE = "PREEMPTIVE_NOT_AUTHORIZED"

H100_PARTITION_PREFIX = "gpu-h100"
PROTECTED_QOS = frozenset({"high", "urgent"})
STANDBY_QOS = frozenset({"standby"})

SUBMISSION_FIELDS = (
    "id",
    "job_id",
    "array_range",
    "account_hash",
    "partition",
    "submit_time",
    "nodes_req",
    "processors_req",
    "memory_req",
    "wallclock_req",
    "qos",
    "gpus_requested",
)
STATE_EVENT_FIELDS = ("start_time", "end_time")
FORBIDDEN_POLICY_FIELDS = (
    "future_actual_start_time",
    "future_actual_end_time",
    "realized_runtime",
    "queue_wait",
    "nodelist",
    "gpu_nodes_occupied",
    "shared_job_count",
    "nodes_shared",
    "jobs_shared",
    "future_completion_state",
)


def require_apr01(when: datetime) -> datetime:
    """Reject any target time outside fixed-AEST Apr-01."""

    if when.tzinfo is None:
        raise ValueError("V35R3A_NAIVE_TIME_FORBIDDEN")
    value = when.astimezone(AEST)
    if not TARGET_START <= value < TARGET_END:
        raise PermissionError(f"V35R3A_APR01_ONLY:{value.isoformat()}")
    return value


def is_h100_partition(value: object) -> bool:
    return str(value or "").strip().lower().startswith(H100_PARTITION_PREFIX)


def submission_complete(row: Mapping[str, Any]) -> bool:
    """Return whether the scheduler-visible resource request is usable."""

    try:
        nodes = float(row.get("nodes_req"))
        gpus = float(row.get("gpus_requested"))
        seconds = float(row.get("wallclock_seconds"))
    except (TypeError, ValueError):
        return False
    return nodes > 0 and gpus > 0 and seconds > 0 and gpus <= GPUS_PER_NODE * nodes


def classify_pending(row: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    """Classify a pending row using submission-side information only.

    Standby is established only by the raw QoS field.  A partition name that
    contains ``stdby`` is diagnostic evidence, not QoS authority.  Spatial
    candidacy is not asserted because the trace exposes co-residency only ex
    post and no submission-time exclusivity field exists.
    """

    qos = str(row.get("qos") or "").strip().lower()
    partition = str(row.get("partition") or "").strip().lower()
    if not submission_complete(row):
        return FIXED_PROTECTED, ("INSUFFICIENT_SUBMISSION_RESOURCE_AUTHORITY",)
    if qos in PROTECTED_QOS:
        return HIGH_PROTECTED, ("PROTECTED_HIGH_OR_URGENT_QOS",)
    if qos == "normal":
        reasons = ("PARTITION_NAME_NOT_QOS_AUTHORITY",) if "stdby" in partition else ()
        return NORMAL_QUEUE_CONTROLLED, reasons
    if qos in STANDBY_QOS:
        return STANDBY_QUEUE_CONTROLLED, ("STANDBY_IDLE_CAPACITY_SEMANTICS",)
    return FIXED_PROTECTED, ("UNKNOWN_QOS_SEMANTICS",)


def is_temporal_controlled_class(value: object) -> bool:
    return str(value) in TEMPORAL_CONTROLLED_CLASSES


@dataclass(frozen=True)
class ServiceGate:
    passed: bool
    checks: Mapping[str, bool]
    deltas: Mapping[str, float]
