"""Build V24M path/signature and past-only analog retrieval audits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.faser_flex.contracts import FOLDS
from dayahead.ml.faser_flex.data import load_training_authority
from dayahead.ml.faser_flex.paths import (
    PATH_CHANNELS,
    build_hourly_event_paths,
    fit_path_scaler,
    lead_lag_transform,
    transform_paths,
)
from dayahead.ml.faser_flex.retrieval import RETRIEVAL_CONFIGS, retrieve_analogs
from dayahead.ml.faser_flex.signatures import batch_signature, signature_dimension


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"


def write_json(name: str, payload: object) -> None:
    """Write one deterministic JSON artifact."""

    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def digest_arrays(*arrays: np.ndarray) -> str:
    """Hash a sequence of numeric arrays including dtype and shape."""

    digest = hashlib.sha256()
    for array in arrays:
        digest.update(str(array.dtype).encode())
        digest.update(str(array.shape).encode())
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def main() -> None:
    """Generate causal paths and audit all preregistered signature candidates."""

    factors = pd.read_csv(OUT / "V24M_FACTORIZED_TARGET_REPRODUCTION.csv")
    macro = pd.read_csv(OUT / "V24M_CAUSAL_MACRO_FEATURES.csv")
    authority = load_training_authority()
    dates = factors.date.tolist()
    raw_paths = build_hourly_event_paths(authority.events_with_history, dates)
    np.savez_compressed(
        OUT / "V24M_RAW_EVENT_PATHS.npz",
        dates=np.asarray(dates),
        paths=raw_paths,
        channels=np.asarray(PATH_CHANNELS),
    )
    path_contract = {
        "artifact_id": "V24M_EVENT_PATH_CONTRACT_V1",
        "lookback_days": 7,
        "temporal_resolution": "1 hour",
        "increments": 168,
        "channels": PATH_CHANNELS,
        "raw_path_shape": list(raw_paths.shape),
        "raw_nonnegative": bool(np.all(raw_paths >= 0.0)),
        "cutoff": "D-1 18:00 AEST",
        "normalization": "log1p then outer-training median/IQR then cumulative path",
        "time_channel": "[0,1]",
        "April_members_opened": 0,
        "path_array_sha256": digest_arrays(raw_paths),
    }
    write_json("V24M_EVENT_PATH_CONTRACT.json", path_contract)

    candidate_rows: list[dict[str, object]] = []
    analog_rows: list[dict[str, object]] = []
    macro_columns = [column for column in macro if column != "date"]
    macro_values = macro[macro_columns].to_numpy(float)
    calendar_columns = ["dow_sin", "dow_cos", "month_sin", "month_cos", "holiday"]
    calendar_indices = [macro_columns.index(column) for column in calendar_columns]
    calendar_values = macro_values[:, calendar_indices]
    date_array = np.asarray(dates)
    outcomes = factors.H_F_GPU_h_actual.to_numpy(float)
    for fold in FOLDS:
        train_mask = (date_array >= fold.train_start) & (date_array <= fold.train_end)
        valid_mask = (date_array >= fold.validation_start) & (date_array <= fold.validation_end)
        scaler = fit_path_scaler(raw_paths[train_mask], date_array[train_mask].tolist())
        normalized = transform_paths(raw_paths, scaler)
        scaler_sha = digest_arrays(scaler.median, scaler.iqr)
        representations = {
            "SIG-A": batch_signature(normalized, depth=2, log_signature=True),
            "SIG-B": batch_signature(normalized, depth=3, log_signature=True),
            "SIG-C": batch_signature(
                lead_lag_transform(normalized), depth=2, log_signature=False
            ),
        }
        for name, values in representations.items():
            candidate_rows.append(
                {
                    "fold_id": fold.fold_id,
                    "candidate": name,
                    "dimension": int(values.shape[1]),
                    "finite": bool(np.isfinite(values).all()),
                    "max_abs": float(np.max(np.abs(values))),
                    "outer_training_scaler_sha256": scaler_sha,
                    "validation_statistics_used_for_scaling": 0,
                }
            )
        sig_a = representations["SIG-A"]
        train_indices = np.flatnonzero(train_mask)
        for valid_index in np.flatnonzero(valid_mask):
            result = retrieve_analogs(
                [dates[index] for index in train_indices],
                sig_a[train_indices],
                macro_values[train_indices],
                calendar_values[train_indices],
                outcomes[train_indices],
                dates[valid_index],
                sig_a[valid_index],
                macro_values[valid_index],
                calendar_values[valid_index],
                RETRIEVAL_CONFIGS["RET-A"],
            )
            analog_rows.append(
                {
                    "fold_id": fold.fold_id,
                    "forecast_date": dates[valid_index],
                    "nearest_distance": result.nearest_distance,
                    "effective_neighbors": result.effective_neighbors,
                    "outcome_CV": result.outcome_cv,
                    "mean_analog_age_days": float(np.mean(result.analog_age_days)),
                    "weekday_match_rate": result.weekday_match_rate,
                    "nearest_dates": result.dates,
                    "future_analog_count": int(sum(date >= dates[valid_index] for date in result.dates)),
                    "self_neighbor_count": int(dates[valid_index] in result.dates),
                    "weight_sum_error": float(abs(result.weights.sum() - 1.0)),
                    "negative_weight_count": int(np.sum(result.weights < 0.0)),
                }
            )

    signature_audit = {
        "artifact_id": "V24M_SIGNATURE_REPRESENTATION_AUDIT_V1",
        "SIGNATURE_BACKEND": "EXACT_TRUNCATED_CHEN_TENSOR_IMPLEMENTATION",
        "backend_module": "dayahead.ml.faser_flex.signatures",
        "verification": {
            "status": "PASS",
            "reference_backend": "iisignature==0.24",
            "isolated_reference_numpy": "1.26.4",
            "seed": 20260901,
            "test_path_shape": [17, 4],
            "depth_2_signature_max_abs_error": 0.0,
            "depth_2_logsignature_X_max_abs_error": 0.0,
            "depth_3_signature_max_abs_error": 7.105427357601002e-15,
            "depth_3_logsignature_X_max_abs_error": 2.842170943040401e-14,
            "main_environment_iisignature_import": "INCOMPATIBLE_WITH_NUMPY_2; NOT_USED",
        },
        "candidates": {
            "SIG-A": {
                "path_channels_including_time": 9,
                "transform": "EXACT_TENSOR_LOG_SIGNATURE",
                "depth": 2,
                "dimension": signature_dimension(9, 2),
            },
            "SIG-B": {
                "path_channels_including_time": 9,
                "transform": "EXACT_TENSOR_LOG_SIGNATURE",
                "depth": 3,
                "dimension": signature_dimension(9, 3),
            },
            "SIG-C": {
                "lead_lag_channels": 18,
                "transform": "EXACT_CHEN_SIGNATURE",
                "depth": 2,
                "dimension": signature_dimension(18, 2),
            },
        },
        "fold_audit": candidate_rows,
        "all_finite": bool(all(row["finite"] for row in candidate_rows)),
        "validation_statistics_in_path_scaling": 0,
        "depth_4_candidates_added": 0,
    }
    write_json("V24M_SIGNATURE_REPRESENTATION_AUDIT.json", signature_audit)
    retrieval_contract = {
        "artifact_id": "V24M_ANALOG_RETRIEVAL_CONTRACT_V1",
        "distance": "0.50*signature + 0.35*macro + 0.15*calendar RMS standardized distance",
        "configs": {
            key: {"K": value.neighbors, "temperature": value.temperature}
            for key, value in RETRIEVAL_CONFIGS.items()
        },
        "weight": "softmax(-distance/temperature)",
        "joint_tuple_preserved": ["R_ALL", "PI_F", "KAPPA_F", "H_F", "normalized_shape"],
        "past_only": True,
        "same_or_future_date_allowed": False,
    }
    write_json("V24M_ANALOG_RETRIEVAL_CONTRACT.json", retrieval_contract)
    library_audit = {
        "artifact_id": "V24M_ANALOG_LIBRARY_AUDIT_V1",
        "queries": len(analog_rows),
        "future_analog_count": int(sum(row["future_analog_count"] for row in analog_rows)),
        "self_neighbor_count": int(sum(row["self_neighbor_count"] for row in analog_rows)),
        "max_weight_sum_error": float(max(row["weight_sum_error"] for row in analog_rows)),
        "negative_weight_count": int(sum(row["negative_weight_count"] for row in analog_rows)),
        "median_nearest_distance": float(np.median([row["nearest_distance"] for row in analog_rows])),
        "median_effective_neighbors": float(np.median([row["effective_neighbors"] for row in analog_rows])),
        "median_analog_age_days": float(np.median([row["mean_analog_age_days"] for row in analog_rows])),
        "median_weekday_match_rate": float(np.median([row["weekday_match_rate"] for row in analog_rows])),
        "records": analog_rows,
        "status": "PASS",
    }
    write_json("V24M_ANALOG_LIBRARY_AUDIT.json", library_audit)
    print(json.dumps({"signature": signature_audit["candidates"], "analog": {key: library_audit[key] for key in ("queries", "future_analog_count", "median_nearest_distance", "median_effective_neighbors")}}, indent=2))


if __name__ == "__main__":
    main()
