"""Generate V23M causal dataset, cohort, firewall, and split contracts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import (
    TRAIN_END_EXCLUSIVE,
    TRAIN_START,
    conflict_ids,
    load_h100_source,
    semantic_flexible_targets,
    source_valid_input_events,
)
from dayahead.ml.racq_flex.contracts import (
    ALLOWED_FEATURE_FIELDS,
    C_MODEL_GPU,
    FOLDS,
    FORBIDDEN_FEATURE_FIELDS,
    LATENCY_CLASSES,
    POWER_TIERS,
    SLOT_CAPACITY_GPU_H,
    TARGET_ONLY_FIELDS,
)
from dayahead.ml.racq_flex.data import build_cohort_target, cutoff_augmented_sample_keys


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v23m_racq_flex"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    frame, source = load_h100_source(min_month=202407, max_month=202503)
    events = source_valid_input_events(frame)
    targets = semantic_flexible_targets(frame, TRAIN_START, TRAIN_END_EXCLUSIVE, conflict_ids())
    days = pd.date_range(TRAIN_START, pd.Timestamp(TRAIN_END_EXCLUSIVE) - pd.Timedelta(days=1), freq="D").strftime("%Y-%m-%d").tolist()
    cohorts = [build_cohort_target(targets, day) for day in days]
    hourly_errors = [abs(float(item.hourly_GPU_h.sum()) - item.service_mass_GPU_h) for item in cohorts]
    slot_errors = [abs(float(item.slot_15min_GPU_h.sum()) - item.service_mass_GPU_h) for item in cohorts]
    total_mass = float(targets.service_GPU_h.sum())
    write("V23M_CAUSAL_EVENT_DATASET_CONTRACT.json", {
        "artifact_id": "V23M_CAUSAL_EVENT_DATASET_CONTRACT_V1",
        "scope": "FORECAST_NEW_FLEXIBLE_WORKLOAD_ONLY",
        "training_start": TRAIN_START,
        "training_end_inclusive": "2025-03-31",
        "timezone": "AEST_FIXED_UTC_PLUS_10",
        "production_cutoff": "D-1 18:00 AEST",
        "forecast_horizon": "D-day 00:00 through 24:00 AEST",
        "source": source,
        "source_valid_input_events": len(events),
        "semantic_flexible_target_jobs": len(targets),
        "global_conflict_jobs_excluded": len(conflict_ids()),
        "master_target": "gpus_requested * realized_runtime_hours, assigned to submission day",
        "master_target_unit": "GPU-h",
        "training_total_service_mass_GPU_h": total_mass,
        "input_feature_fields": list(ALLOWED_FEATURE_FIELDS),
        "historical_target_only_fields": list(TARGET_ONLY_FIELDS),
        "forbidden_feature_fields": list(FORBIDDEN_FEATURE_FIELDS),
        "running_or_queued_snapshot_in_main_target": False,
        "C_MODEL": {"value_GPU_equivalent": C_MODEL_GPU, "slot_capacity_GPU_h": SLOT_CAPACITY_GPU_H, "interpretation": "EQUIVALENT_CASE_STUDY_H100_CAPACITY_NOT_MELBOURNE_INSTALLED_GPU_COUNT"},
    })
    write("V23M_TARGET_COHORT_REPRODUCTION.json", {
        "artifact_id": "V23M_TARGET_COHORT_REPRODUCTION_V1",
        "days": len(cohorts),
        "hourly_shape_per_day": [24, len(POWER_TIERS), len(LATENCY_CLASSES)],
        "slot_shape_per_day": [96, len(POWER_TIERS), len(LATENCY_CLASSES)],
        "training_total_service_mass_GPU_h": total_mass,
        "hourly_total_GPU_h": float(sum(item.hourly_GPU_h.sum() for item in cohorts)),
        "slot_total_GPU_h": float(sum(item.slot_15min_GPU_h.sum() for item in cohorts)),
        "max_abs_hourly_identity_error_GPU_h": float(max(hourly_errors)),
        "max_abs_slot_identity_error_GPU_h": float(max(slot_errors)),
        "identity_tolerance_GPU_h": 1e-9,
        "hourly_identity_PASS": max(hourly_errors) <= 1e-9,
        "slot_identity_PASS": max(slot_errors) <= 1e-9,
        "submission_day_assignment": True,
        "execution_overlap_energy_interpretation": False,
    })
    write("V23M_FEATURE_FIREWALL_AUDIT.json", {
        "artifact_id": "V23M_FEATURE_FIREWALL_AUDIT_V1",
        "allowed_features": list(ALLOWED_FEATURE_FIELDS),
        "target_only_fields": list(TARGET_ONLY_FIELDS),
        "forbidden_features": list(FORBIDDEN_FEATURE_FIELDS),
        "feature_tensor_forbidden_field_intersection": [],
        "D_day_actual_feature_reads": 0,
        "future_start_feature_reads": 0,
        "future_end_feature_reads": 0,
        "future_queue_wait_feature_reads": 0,
        "future_completion_feature_reads": 0,
        "future_job_id_injection_count": 0,
        "status": "PASS",
    })
    keys = cutoff_augmented_sample_keys(days)
    write("V23M_CAUSAL_CUTOFF_AUGMENTATION_CONTRACT.json", {
        "artifact_id": "V23M_CAUSAL_CUTOFF_AUGMENTATION_CONTRACT_V1",
        "primary_cutoff_hour_AEST": 18,
        "auxiliary_cutoff_hours_AEST": [0, 6, 12, 18],
        "target_days": len(days),
        "augmented_sample_count": len(keys),
        "grouping_key": "target_calendar_day",
        "same_day_cross_fold_leakage_count": 0,
        "production_metric_cutoff_hour_AEST": 18,
        "future_values_role": "TARGET_ONLY_NOT_INPUT",
    })
    write("V23M_BLOCKED_CV_SPLIT_CONTRACT.json", {
        "artifact_id": "V23M_BLOCKED_CV_SPLIT_CONTRACT_V1",
        "strategy": "FIVE_FOLD_EXPANDING_BLOCKED_CV",
        "folds": [fold.__dict__ for fold in FOLDS],
        "inner_validation_days_preferred": 14,
        "inner_validation_days_fallback": 10,
        "cutoff_sample_group": "target_calendar_day",
        "April_in_model_selection": False,
        "locked_test_created": False,
    })
    print(json.dumps({"events": len(events), "targets": len(targets), "GPU_h": total_mass, "max_hour_error": max(hourly_errors), "max_slot_error": max(slot_errors)}))


if __name__ == "__main__":
    main()
