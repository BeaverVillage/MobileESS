"""Frozen units, schemas, folds, and causal constants for V24M FASER-Flex."""

from __future__ import annotations

from dataclasses import dataclass


POWER_TIERS = ("FULL_1", "FULL_2", "FULL_4", "FULL_8", "FULL_16", "PARTIAL")
LATENCY_CLASSES = ("C1", "C2", "C3", "C4", "C5")
TRAIN_START = "2024-08-19"
TRAIN_END_INCLUSIVE = "2025-03-31"
TRAIN_END_EXCLUSIVE = "2025-04-01"
PRODUCTION_CUTOFF_HOUR_AEST = 18
PATH_LOOKBACK_DAYS = 7
PATH_HOURS = 168
C_MODEL_GPU_EQUIVALENT = 528
SLOT_CAPACITY_GPU_H = 132.0
SEEDS = (20260901, 20260902, 20260903)
PREDICTIVE_SAMPLES = 4096

ALLOWED_FEATURE_FIELDS = (
    "submit_time",
    "inter_arrival_time",
    "gpus_requested",
    "nodes_req",
    "wallclock_req",
    "partition",
    "qos",
    "account_hash",
    "request_full_partial",
    "historical_event_counts",
    "historical_requested_GPU",
    "historical_requested_GPU_h",
    "historical_node_counts",
    "historical_account_diversity",
    "calendar",
    "holiday",
    "causal_rolling_statistics",
)
TARGET_ONLY_FIELDS = (
    "realized_runtime",
    "semantic_flexible_label",
    "historical_queue_wait_derived_label",
    "completion_state_for_target_construction",
)
FORBIDDEN_FEATURE_FIELDS = (
    "D_day_actual_submissions",
    "future_start",
    "future_end",
    "future_queue_wait",
    "future_completion",
    "future_realized_runtime",
    "future_state",
    "future_job_id",
    "retrospective_future_flexible_label",
)


@dataclass(frozen=True)
class Fold:
    """One expanding blocked-CV split with inclusive date endpoints."""

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
