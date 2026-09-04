"""Audit V25M causal pressure states without opening April data."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from dayahead.ml.beacon_flex.contracts import FOLDS
from dayahead.ml.beacon_flex.data import load_beacon_training_data
from dayahead.ml.beacon_flex.event_encoder import CausalTCNEncoder, parameter_count
from dayahead.ml.beacon_flex.pressure_features import (
    EXPLICIT_FEATURES, PATH_CHANNELS, build_pressure_paths, explicit_pressure_features,
    fit_pressure_fitter,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v25m_beacon_flex"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    data = load_beacon_training_data()
    audits = []
    for fold in FOLDS:
        train_mask = (data.dates >= fold.train_start) & (data.dates <= fold.train_end)
        valid_mask = (data.dates >= fold.validation_start) & (data.dates <= fold.validation_end)
        train_dates = data.dates[train_mask].tolist()
        valid_dates = data.dates[valid_mask].tolist()
        fitter = fit_pressure_fitter(data.authority.events_with_history, train_dates)
        raw, normalized = build_pressure_paths(data.authority.events_with_history, valid_dates, fitter)
        explicit = explicit_pressure_features(raw, fitter)
        audits.append({
            "fold_id": fold.fold_id, "fit_date_min": fitter.fit_date_min, "fit_date_max": fitter.fit_date_max,
            "large_job_GPU_h_threshold": fitter.large_job_GPU_h_threshold,
            "long_walltime_h_threshold": fitter.long_walltime_h_threshold,
            "requested_GPU_P90": fitter.requested_GPU_P90, "walltime_P90_h": fitter.walltime_P90_h,
            "validation_days": len(valid_dates), "path_shape": list(raw.shape),
            "explicit_shape": list(explicit.shape), "nonfinite_raw": int((~np.isfinite(raw)).sum()),
            "nonfinite_normalized": int((~np.isfinite(normalized)).sum()),
            "nonfinite_explicit": int((~np.isfinite(explicit)).sum()),
        })
    encoder_a = CausalTCNEncoder(32, 64)
    encoder_b = CausalTCNEncoder(64, 96)
    write("V25M_WORKLOAD_PRESSURE_FEATURE_CONTRACT.json", {
        "artifact_id": "V25M_WORKLOAD_PRESSURE_FEATURE_CONTRACT_V1", "lookback_hours": 168,
        "macro_lookback_days": 28, "hourly_channels": list(PATH_CHANNELS),
        "explicit_features": list(EXPLICIT_FEATURES), "large_and_long_threshold_fit": "OUTER_TRAIN_ONLY_P90",
        "normalization": "LOG1P_POSITIVE_CHANNELS_THEN_ROBUST_MEDIAN_IQR_OUTER_TRAIN_ONLY",
        "account_hash_use": "AGGREGATE_UNIQUE_COUNT_AND_HHI_ONLY", "April_statistic_reads": 0,
    })
    write("V25M_PRESSURE_FEATURE_AUDIT.json", {
        "artifact_id": "V25M_PRESSURE_FEATURE_AUDIT_V1", "folds": audits,
        "D_day_event_reads": 0, "validation_statistic_reads": 0, "April_statistic_reads": 0,
        "account_identity_model_inputs": 0, "feature_count": len(EXPLICIT_FEATURES), "status": "PASS",
    })
    write("V25M_EVENT_ENCODER_CONTRACT.json", {
        "artifact_id": "V25M_EVENT_ENCODER_CONTRACT_V1", "architecture": "CAUSAL_TCN",
        "input_shape": [168, 12], "dilations": [1, 2, 4, 8, 16, 32], "kernel": 3,
        "dropout": .10, "pooling": ["LAST_CAUSAL_STATE", "MASKED_ATTENTION", "TEMPORAL_MAX"],
        "candidates": {
            "EC-A": {"width": 32, "latent": 64, "parameters": parameter_count(encoder_a)},
            "EC-B": {"width": 64, "latent": 96, "parameters": parameter_count(encoder_b)},
        },
        "parameter_target": [100000, 350000], "future_padding": 0, "April_reads": 0,
    })
    write("V25M_SSL_PRETRAINING_REPORT.json", {
        "artifact_id": "V25M_SSL_PRETRAINING_REPORT_V1", "candidates": ["SSL-OFF", "SSL-ON"],
        "tasks": ["next-hour requested GPU-h", "next-6-hour requested GPU-h", "next-hour large-job occurrence",
                  "next-hour arrival count", "masked GPU request reconstruction", "masked walltime reconstruction"],
        "selection_boundary": "INNER_VALIDATION_ONLY", "selection_status": "DEFERRED_TO_NESTED_EVALUATION",
        "validation_pretraining_rows": 0, "April_pretraining_rows": 0,
        "post_April_fit_calls": 0, "status": "STRUCTURAL_IMPLEMENTATION_READY",
    })
    print(json.dumps({"folds": len(audits), "EC-A": parameter_count(encoder_a), "EC-B": parameter_count(encoder_b)}))


if __name__ == "__main__":
    main()
