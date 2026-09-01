"""Frozen V23M schemas, units, and causal constants."""

from __future__ import annotations

from dataclasses import dataclass


POWER_TIERS = ("FULL_1", "FULL_2", "FULL_4", "FULL_8", "FULL_16", "PARTIAL")
LATENCY_CLASSES = ("C1", "C2", "C3", "C4", "C5")
C_MODEL_GPU = 528
SLOT_CAPACITY_GPU_H = 132.0
PRODUCTION_CUTOFF_HOUR_AEST = 18
TRAIN_START = "2024-08-19"
TRAIN_END_INCLUSIVE = "2025-03-31"

ALLOWED_FEATURE_FIELDS = (
    "submit_time",
    "inter_arrival_seconds",
    "gpus_requested",
    "nodes_req",
    "wallclock_req",
    "partition",
    "qos",
    "account_hash",
    "request_full_partial",
    "historical_submission_counts",
    "historical_requested_GPU_sums",
    "historical_requested_walltime_sums",
    "calendar",
    "public_holiday",
    "causal_rolling_statistics",
)
TARGET_ONLY_FIELDS = (
    "start_time",
    "end_time",
    "queue_wait",
    "state_simple",
    "realized_runtime_hours",
    "semantic_flexible_label",
)
FORBIDDEN_FEATURE_FIELDS = (
    "D_day_actual_arrivals",
    "future_start",
    "future_end",
    "future_queue_wait",
    "future_completion",
    "future_state_simple",
    "future_actual_runtime",
    "future_job_id",
)


@dataclass(frozen=True)
class Fold:
    """One expanding blocked-CV split, with inclusive date endpoints."""

    fold_id: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str


FOLDS = (
    Fold(1, TRAIN_START, "2024-10-31", "2024-11-01", "2024-11-30"),
    Fold(2, TRAIN_START, "2024-11-30", "2024-12-01", "2024-12-31"),
    Fold(3, TRAIN_START, "2024-12-31", "2025-01-01", "2025-01-31"),
    Fold(4, TRAIN_START, "2025-01-31", "2025-02-01", "2025-02-28"),
    Fold(5, TRAIN_START, "2025-02-28", "2025-03-01", "2025-03-31"),
)
