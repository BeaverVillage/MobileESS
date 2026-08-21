#!/usr/bin/env python3
"""Build the causal SCATS Q2 overlay required by the January 2025 campaign.

This is a technical input repair. It applies the already frozen 2024 LightGBM
models to causal history and target-calendar features. It never replaces an
existing finite Q2 value and never reads a future observed target.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd


SLOTS15 = 96
Q2_NAME = "q2_global_volume_forecast_offsets1_19.float32.npy"
TOTAL_NAME = "scats_mapped_total_volume_15m.float32.npy"
LAGS = (0, 1, 2, 3, 4, 8, 12, 24, 48, 96, 192, 672)
ROLLING_WINDOWS = (4, 8, 16, 32, 96, 672)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def date_arrays(splits: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dates = pd.to_datetime(splits["date"])
    dow_day = dates.dt.dayofweek.to_numpy(np.int16)
    month_day = dates.dt.month.to_numpy(np.int16)
    dow = np.repeat(dow_day, SLOTS15)
    month = np.repeat(month_day, SLOTS15)
    slot = np.tile(np.arange(SLOTS15, dtype=np.int16), len(splits))
    return dow, month, slot


def rolling_stats(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(y, dtype=np.float64)
    cumulative = np.concatenate([[0.0], np.cumsum(values)])
    cumulative_squared = np.concatenate([[0.0], np.cumsum(values * values)])
    return cumulative, cumulative_squared


def make_scats_features(
    ylog: np.ndarray,
    idx: np.ndarray,
    horizon: int,
    dow: np.ndarray,
    month: np.ndarray,
    slot: np.ndarray,
    cumulative: np.ndarray,
    cumulative_squared: np.ndarray,
) -> np.ndarray:
    idx = np.asarray(idx, dtype=np.int64)
    target = idx + horizon
    features: list[np.ndarray] = []
    for lag in LAGS:
        features.append(ylog[idx - lag])
    for window in ROLLING_WINDOWS:
        start = idx - window + 1
        total = cumulative[idx + 1] - cumulative[start]
        total_squared = cumulative_squared[idx + 1] - cumulative_squared[start]
        mean = total / window
        variance = np.maximum(total_squared / window - mean * mean, 0.0)
        features.append(mean)
        features.append(np.sqrt(variance))
    origin_slot = slot[idx].astype(float)
    target_slot = slot[target].astype(float)
    features += [
        np.sin(2 * np.pi * origin_slot / SLOTS15),
        np.cos(2 * np.pi * origin_slot / SLOTS15),
        np.sin(2 * np.pi * target_slot / SLOTS15),
        np.cos(2 * np.pi * target_slot / SLOTS15),
        np.sin(2 * np.pi * dow[idx] / 7.0),
        np.cos(2 * np.pi * dow[idx] / 7.0),
        np.sin(2 * np.pi * dow[target] / 7.0),
        np.cos(2 * np.pi * dow[target] / 7.0),
        np.sin(2 * np.pi * (month[idx] - 1) / 12.0),
        np.cos(2 * np.pi * (month[idx] - 1) / 12.0),
        ylog[idx] - ylog[idx - 4],
        ylog[idx] - ylog[idx - 96],
    ]
    matrix = np.column_stack(features).astype(np.float32)
    if matrix.shape[1] != 36 or not np.isfinite(matrix).all():
        raise RuntimeError(f"invalid feature matrix: shape={matrix.shape}")
    return matrix


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--technical-amendment", type=Path, required=True)
    parser.add_argument("--date-splits", type=Path, required=True)
    parser.add_argument("--stage2a-root", type=Path, required=True)
    parser.add_argument("--start-issue", type=int, default=0)
    parser.add_argument("--issue-count", type=int, default=9216)
    parser.add_argument("--first-origin5", type=int, default=631296)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--authority-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.start_issue < 0 or args.issue_count <= 0:
        raise ValueError("start issue must be nonnegative and issue count positive")

    amendment = json.loads(args.technical_amendment.read_text(encoding="utf-8"))
    if amendment.get("status") != "APPLIED_BEFORE_FIRST_PREDICTION":
        raise RuntimeError("technical amendment is not pre-prediction authoritative")
    if amendment.get("model_changed") is not False:
        raise RuntimeError("technical amendment did not preserve frozen models")
    if amendment.get("performance_values_seen_before_amendment") is not False:
        raise RuntimeError("technical amendment was performance-informed")

    feature_contract = amendment["feature_contract"]
    feature_source = Path(feature_contract["source_reference"])
    if sha256_file(feature_source) != feature_contract["source_reference_sha256"]:
        raise RuntimeError("feature source SHA-256 mismatch")
    if feature_contract.get("future_observation_used") is not False:
        raise RuntimeError("feature contract permits future observations")

    base_q2 = args.stage2a_root / "scats_forecast" / Q2_NAME
    mapped_total_path = args.stage2a_root / "tensor_store" / TOTAL_NAME
    expected_base_sha = amendment["frozen_q2_sha256"]
    if sha256_file(base_q2) != expected_base_sha:
        raise RuntimeError("base Q2 SHA-256 mismatch")

    model_rows = sorted(amendment["frozen_model_rows"], key=lambda row: row["horizon_offset15"])
    if [row["horizon_offset15"] for row in model_rows] != list(range(1, 20)):
        raise RuntimeError("frozen model horizon axis is not 1..19")
    for row in model_rows:
        model_path = Path(row["path"])
        if sha256_file(model_path) != row["sha256"]:
            raise RuntimeError(f"frozen model SHA-256 mismatch: {model_path}")

    output_root = args.output_root.resolve()
    authority_path = args.authority_output or output_root / "JANUARY_Q2_OVERLAY_AUTHORITY.json"
    output_q2 = output_root / "scats_forecast" / Q2_NAME
    if output_root.exists():
        raise FileExistsError(f"refusing to mutate existing overlay: {output_root}")
    output_q2.parent.mkdir(parents=True)
    shutil.copy2(base_q2, output_q2)
    (output_root / "tensor_store").symlink_to(
        (args.stage2a_root / "tensor_store").resolve(), target_is_directory=True
    )

    base = np.load(base_q2, mmap_mode="r")
    overlay = np.load(output_q2, mmap_mode="r+")
    mapped_total = np.load(mapped_total_path, mmap_mode="r")
    if base.shape != overlay.shape or base.ndim != 2 or base.shape[1] != 19:
        raise RuntimeError(f"unexpected Q2 shape: {base.shape}")
    if mapped_total.ndim != 1 or len(mapped_total) != base.shape[0]:
        raise RuntimeError("mapped-total and Q2 axes differ")
    if not np.isfinite(mapped_total).all() or np.any(mapped_total < 0.0):
        raise RuntimeError("mapped total volume is not finite and nonnegative")

    splits = pd.read_csv(args.date_splits).sort_values("date").reset_index(drop=True)
    if len(splits) * SLOTS15 != len(mapped_total):
        raise RuntimeError("date split and SCATS 15-minute axes differ")
    dow, month, slot = date_arrays(splits)
    ylog = np.log1p(np.asarray(mapped_total, dtype=np.float64))
    cumulative, cumulative_squared = rolling_stats(ylog)

    first_origin5 = args.first_origin5 + args.start_issue
    last_origin5 = first_origin5 + args.issue_count - 1
    first_row = first_origin5 // 3 - 1
    last_row = last_origin5 // 3 - 1
    if first_row < max(LAGS) or last_row + 19 >= len(mapped_total):
        raise RuntimeError("requested repair rows exceed the causal feature axis")

    window = overlay[first_row : last_row + 1]
    missing_before = ~np.isfinite(window)
    repaired_count = 0
    generation_rows: list[dict[str, Any]] = []
    for model_row in model_rows:
        horizon = int(model_row["horizon_offset15"])
        column = horizon - 1
        missing_relative = np.flatnonzero(missing_before[:, column])
        if not len(missing_relative):
            generation_rows.append(
                {"horizon_offset15": horizon, "repaired_values": 0, "model_sha256": model_row["sha256"]}
            )
            continue
        indices = first_row + missing_relative
        features = make_scats_features(
            ylog, indices, horizon, dow, month, slot, cumulative, cumulative_squared
        )
        booster = lgb.Booster(model_file=model_row["path"])
        prediction = np.maximum(
            np.expm1(booster.predict(features, num_iteration=booster.current_iteration())), 0.0
        ).astype(np.float32)
        if not np.isfinite(prediction).all():
            raise RuntimeError(f"nonfinite prediction at horizon {horizon}")
        overlay[indices, column] = prediction
        repaired_count += len(indices)
        generation_rows.append(
            {
                "horizon_offset15": horizon,
                "repaired_values": int(len(indices)),
                "minimum_prediction": float(prediction.min()),
                "maximum_prediction": float(prediction.max()),
                "mean_prediction": float(prediction.mean()),
                "model_sha256": model_row["sha256"],
                "model_iterations": int(booster.current_iteration()),
            }
        )
    overlay.flush()

    if not np.isfinite(overlay[first_row : last_row + 1]).all():
        raise RuntimeError("Q2 repair window remains nonfinite")
    base_finite = np.isfinite(base)
    if not np.array_equal(overlay[base_finite], base[base_finite]):
        raise RuntimeError("an existing finite Q2 value changed")
    observed_repairs = int(np.count_nonzero(~np.isfinite(base) & np.isfinite(overlay)))
    if observed_repairs != repaired_count:
        raise RuntimeError("repair count audit mismatch")

    authority = {
        "status": "PASS",
        "contract": "PFR_JANUARY_2025_CAUSAL_Q2_OVERLAY_V1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "technical_amendment": str(args.technical_amendment.resolve()),
        "technical_amendment_sha256": sha256_file(args.technical_amendment),
        "feature_source": str(feature_source),
        "feature_source_sha256": sha256_file(feature_source),
        "feature_count": 36,
        "future_observation_used": False,
        "performance_informed": False,
        "retuning_performed": False,
        "model_changed": False,
        "start_issue": args.start_issue,
        "last_issue": args.start_issue + args.issue_count - 1,
        "issue_count": args.issue_count,
        "first_origin5": first_origin5,
        "last_origin5": last_origin5,
        "first_latest_complete_15m_row": first_row,
        "last_latest_complete_15m_row": last_row,
        "base_q2": str(base_q2.resolve()),
        "base_q2_sha256": expected_base_sha,
        "overlay_q2": str(output_q2),
        "overlay_q2_sha256": sha256_file(output_q2),
        "existing_finite_values_preserved_exactly": True,
        "repaired_nonfinite_values": repaired_count,
        "requested_window_all_finite": True,
        "tensor_store_target": str((args.stage2a_root / "tensor_store").resolve()),
        "generation_rows": generation_rows,
    }
    write_json_atomic(authority_path, authority)
    print(json.dumps(authority, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
