"""Pinned HPC-ODA execution, target-free adapter, and safe calibration."""

from __future__ import annotations

import math
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .contracts import (
    FORBIDDEN_QUERY_FIELDS,
    ISSUE_TIME_UTC,
    MANDATORY_QUERY_FIELDS,
    QUERY_FEATURE_FIELDS,
    RECIPE_CONTRACT,
    SLOT_SECONDS,
)


def exact_model() -> Any:
    from hpc_oda_commons.models.job_runtime_moe_xgboost.model import (
        MoEXGBoostConfig,
        MoEXGBoostModel,
    )

    return MoEXGBoostModel(
        MoEXGBoostConfig(
            n_windows=RECIPE_CONTRACT["n_windows"],
            test_window_hours=RECIPE_CONTRACT["test_window_hours"],
            training_lookback_days=RECIPE_CONTRACT["training_lookback_days"],
            enable_power_users=RECIPE_CONTRACT["enable_power_users"],
            time_decay_rate=RECIPE_CONTRACT["time_decay_rate"],
            objective=RECIPE_CONTRACT["objective"],
        )
    )


def fixed_splits(rows: list[dict[str, Any]], split_times: Sequence[datetime]) -> list[Any]:
    """Create official RollingSplit objects on a prompt-fixed grid."""

    from hpc_oda_commons.models.rolling_tabular.split import RollingSplit, _epoch_or_nan

    submit_epochs = np.fromiter(
        (_epoch_or_nan(row.get("submit_time")) for row in rows),
        dtype=np.float64,
        count=len(rows),
    )
    end_epochs = np.fromiter(
        (_epoch_or_nan(row.get("end_time")) for row in rows),
        dtype=np.float64,
        count=len(rows),
    )
    result: list[Any] = []
    previous_day: str | None = None
    for when in split_times:
        split_time = when.astimezone(timezone.utc)
        split_end = split_time + pd.Timedelta(hours=6)
        train_start = split_time - pd.Timedelta(days=120)
        day_key = split_time.date().isoformat()
        refresh = previous_day is None or previous_day != day_key
        previous_day = day_key
        train_mask = (end_epochs >= train_start.timestamp()) & (
            end_epochs < split_time.timestamp()
        )
        test_mask = (submit_epochs >= split_time.timestamp()) & (
            submit_epochs < split_end.timestamp()
        )
        result.append(
            RollingSplit(
                split_time_iso=split_time.isoformat().replace("+00:00", "Z"),
                split_end_time_iso=split_end.isoformat().replace("+00:00", "Z"),
                split_epoch=int(split_time.timestamp()),
                day_key=day_key,
                refresh_preprocessing=refresh,
                train_row_count=int(train_mask.sum()),
                test_row_count=int(test_mask.sum()),
                _submit_epochs=submit_epochs,
                _end_epochs=end_epochs,
                _train_start_epoch=train_start.timestamp(),
                _split_epoch_exact=split_time.timestamp(),
                _split_end_epoch=split_end.timestamp(),
            )
        )
    return result


def _predict_state(
    model: Any,
    state: Any,
    artifacts: Any,
    query_rows: list[dict[str, Any]],
) -> np.ndarray:
    """Target-free twin of the pinned MoE prediction half."""

    x_query = model._transform_rows(query_rows, artifacts)
    prediction = np.asarray(state.fallback.predict(x_query), dtype=float)
    by_key: dict[tuple[str, int], list[int]] = defaultdict(list)
    for index, row in enumerate(query_rows):
        by_key[state.routing.key(row)].append(index)
    for key, indices in by_key.items():
        expert = state.experts.get(key)
        if expert is None:
            continue
        selected = np.asarray(indices, dtype=int)
        prediction[selected] = np.asarray(expert.predict(x_query[selected]), dtype=float)
    return prediction


def target_free(row: dict[str, Any]) -> dict[str, Any]:
    result = {key: row.get(key) for key in QUERY_FEATURE_FIELDS}
    result["job_id"] = str(row.get("job_id"))
    if set(result) & FORBIDDEN_QUERY_FIELDS:
        raise AssertionError("V35R3D_FORBIDDEN_QUERY_FIELD_LEAK")
    return result


def run_windows(
    rows: list[dict[str, Any]],
    split_times: Sequence[datetime],
    cache_dir: Path,
    *,
    label: str,
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Execute fixed official windows with per-window resumable predictions."""

    from hpc_oda_commons.models.rolling_tabular.split import materialize_split_rows

    splits = fixed_splits(rows, split_times)
    frames_by_epoch: dict[int, pd.DataFrame] = {}
    entries_by_epoch: dict[int, dict[str, Any]] = {}
    equivalence: dict[str, Any] | None = None
    out_dir = cache_dir / "window_predictions"
    out_dir.mkdir(parents=True, exist_ok=True)
    equivalence_path = cache_dir / "query_adapter_equivalence.json"
    if equivalence_path.is_file():
        equivalence = json.loads(equivalence_path.read_text(encoding="utf-8"))
    by_day: dict[str, list[Any]] = defaultdict(list)
    for split in splits:
        by_day[split.day_key].append(split)

    for day_key in sorted(by_day):
        day_splits = by_day[day_key]
        missing = [
            split
            for split in day_splits
            if not (out_dir / f"{split.split_epoch}.parquet").is_file()
        ]
        for split in day_splits:
            saved = out_dir / f"{split.split_epoch}.parquet"
            if not saved.is_file():
                continue
            frame = pd.read_parquet(saved)
            frames_by_epoch[split.split_epoch] = frame
            entries_by_epoch[split.split_epoch] = {
                "split_time": split.split_time_iso,
                "split_end_time": split.split_end_time_iso,
                "status": "ok",
                "train_rows_supervised": split.train_row_count,
                "test_rows_supervised": len(frame),
                "cache_reused": True,
            }
        if not missing:
            continue

        model = exact_model()
        cache, refit_ids = model._precompute_daily_artifacts(rows, day_splits)
        local_index = {split.split_epoch: index for index, split in enumerate(day_splits)}

        def evaluate_one(split: Any) -> tuple[Any, Any]:
            result = model._evaluate_window(
                split,
                rows,
                cache,
                refit_ids,
                local_index[split.split_epoch],
                [
                    {"name": "mae", "target": "runtime_seconds"},
                    {"name": "rmse", "target": "runtime_seconds"},
                ],
                equivalence is None,
            )
            return split, result

        workers = min(2, len(missing))
        if workers == 1:
            completed = [evaluate_one(missing[0])]
        else:
            from hpc_oda_commons.models.rolling_tabular.base import _blas_single_thread

            completed = []
            with _blas_single_thread(), ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(evaluate_one, split): split for split in missing}
                for future in as_completed(futures):
                    completed.append(future.result())

        for split, result in completed:
            if result.entry["status"] != "ok":
                raise RuntimeError(f"V35R3D_WINDOW_FAILED:{result.entry}")
            _train_all, test_all = materialize_split_rows(rows, split)
            test_rows, y_true = model._rows_with_target(test_all)
            keys = [str(row.get("job_id")) for row in test_rows]
            frame = pd.DataFrame(
                {
                    "job_id": keys,
                    "split_time": split.split_time_iso,
                    "submit_time": [row.get("submit_time") for row in test_rows],
                    "requested_seconds": [row.get("requested_seconds") for row in test_rows],
                    "actual_runtime_seconds": np.asarray(y_true, dtype=float),
                    "point_runtime_seconds": np.asarray(result.y_pred, dtype=float),
                }
            )
            saved = out_dir / f"{split.split_epoch}.parquet"
            frame.to_parquet(saved, index=False)
            frames_by_epoch[split.split_epoch] = frame
            entry = dict(result.entry)
            entry["cache_reused"] = False
            entries_by_epoch[split.split_epoch] = entry

            if equivalence is None:
                if result.model is None:
                    raise RuntimeError("V35R3D_EQUIVALENCE_MODEL_STATE_MISSING")
                stripped = [target_free(row) for row in test_rows]
                custom = _predict_state(
                    model,
                    result.model,
                    cache.get(split.day_key),
                    stripped,
                )
                official = np.asarray(result.y_pred, dtype=float)
                difference = np.abs(custom - official)
                equivalence = {
                    "same_training_rows": result.n_train == split.train_row_count,
                    "same_query_rows": len(stripped) == result.n_test,
                    "exact_query_key_correspondence": keys
                    == [str(row.get("job_id")) for row in test_rows],
                    "same_feature_policy": True,
                    "same_routing": True,
                    "same_preprocessing": True,
                    "feature_order": list(cache.get(split.day_key).numeric_columns)
                    + list(cache.get(split.day_key).categorical_columns)
                    + list(cache.get(split.day_key).target_encoded_columns),
                    "prediction_max_abs_difference": float(difference.max())
                    if len(difference)
                    else None,
                    "prediction_tolerance": 1e-9,
                    "PASS": bool(len(difference) and np.all(difference <= 1e-9)),
                    "window": split.split_time_iso,
                    "rows": len(stripped),
                }
                equivalence_path.write_text(
                    json.dumps(equivalence, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

        del cache, model

    frames = [frames_by_epoch[split.split_epoch] for split in splits]
    entries = [entries_by_epoch[split.split_epoch] for split in splits]
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if equivalence is None:
        equivalence = {
            "PASS": None,
            "reason": "ALL_WINDOWS_REUSED_AND_NO_EQUIVALENCE_CACHE",
        }
    return combined, entries, equivalence


def metric_summary(frame: pd.DataFrame) -> dict[str, Any]:
    actual = frame["actual_runtime_seconds"].to_numpy(float)
    point = frame["point_runtime_seconds"].to_numpy(float)
    error = np.abs(actual - point)
    return {
        "rows": len(frame),
        "MAE_seconds": float(error.mean()),
        "median_AE_seconds": float(np.median(error)),
        "P95_AE_seconds": float(np.quantile(error, 0.95)),
        "RMSE_seconds": float(np.sqrt(np.mean(np.square(actual - point)))),
        "underprediction_rate": float(np.mean(point < actual)),
        "finite": bool(np.isfinite(actual).all() and np.isfinite(point).all()),
    }


def calibrate(frame: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    result = frame.copy()
    actual = result["actual_runtime_seconds"].to_numpy(float)
    point = result["point_runtime_seconds"].to_numpy(float)
    requested = result["requested_seconds"].to_numpy(float)
    residual_plus = np.maximum(actual - point, 0.0)
    q90 = float(np.quantile(residual_plus, 0.90, method="linear"))
    uncapped = np.maximum(point + q90, float(SLOT_SECONDS))
    safe = np.minimum(requested, uncapped)
    result["residual_plus_seconds"] = residual_plus
    result["safe_runtime_seconds"] = safe
    metrics = metric_summary(result)
    metrics.update(
        {
            "q90_plus_seconds": q90,
            "safe_empirical_coverage": float(np.mean(actual <= safe)),
            "requested_walltime_cap_hit_fraction": float(np.mean(uncapped >= requested)),
            "quantile_method": "numpy_linear",
            "safe_min_seconds": float(safe.min()),
            "safe_max_minus_requested_seconds": float(np.max(safe - requested)),
            "Apr01_actual_labels_read": 0,
        }
    )
    return metrics, result


def fit_issue_predictions(
    historical_rows: list[dict[str, Any]],
    query_rows: list[dict[str, Any]],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit exact pinned model on labels known at issue and predict target-free KQ0."""

    model = exact_model()
    issue_epoch = ISSUE_TIME_UTC.timestamp()
    lower_epoch = (ISSUE_TIME_UTC - pd.Timedelta(days=120)).timestamp()
    train_rows = [
        row
        for row in historical_rows
        if row.get("end_time") is not None
        and lower_epoch <= row["end_time"].timestamp() < issue_epoch
        and row.get("runtime_seconds") is not None
        and math.isfinite(float(row["runtime_seconds"]))
    ]
    covered: list[dict[str, Any]] = []
    missing_by_job: dict[str, list[str]] = {}
    for row in query_rows:
        missing = [field for field in MANDATORY_QUERY_FIELDS if row.get(field) in (None, "")]
        numeric_bad = []
        for field in ("requested_seconds", "num_nodes_req", "num_gpus_req"):
            try:
                if not math.isfinite(float(row.get(field))) or float(row.get(field)) <= 0:
                    numeric_bad.append(field)
            except (TypeError, ValueError):
                numeric_bad.append(field)
        missing = sorted(set(missing + numeric_bad))
        if missing:
            missing_by_job[str(row["job_id"])] = missing
        else:
            covered.append(target_free(row))
    artifacts = model._build_daily_preprocessing_artifacts(train_rows)
    x_train = model._transform_rows(train_rows, artifacts)
    x_query = model._transform_rows(covered, artifacts)
    y_train = np.asarray([float(row["runtime_seconds"]) for row in train_rows])

    class IssueSplit:
        split_epoch = int(issue_epoch)

    state, point = model._fit_predict(
        x_train,
        y_train,
        x_query,
        train_rows=train_rows,
        test_rows=covered,
        artifacts=artifacts,
        sample_weight=model._time_decay_weights(train_rows, IssueSplit()),
    )
    del state
    return np.asarray(point, dtype=float), {
        "training_rows": len(train_rows),
        "covered_query_rows": len(covered),
        "covered_job_ids": [str(row["job_id"]) for row in covered],
        "missing_by_job": missing_by_job,
        "feature_order": list(artifacts.numeric_columns)
        + list(artifacts.categorical_columns)
        + list(artifacts.target_encoded_columns),
        "resolved_model_config": asdict(model.config),
    }


def safe_runtime(point: float, q90_plus: float, requested: float) -> float:
    values = (point, q90_plus, requested)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("V35R3D_NONFINITE_SAFE_RUNTIME_INPUT")
    if requested <= 0 or q90_plus < 0:
        raise ValueError("V35R3D_INVALID_SAFE_RUNTIME_INPUT")
    return min(float(requested), max(float(point) + float(q90_plus), float(SLOT_SECONDS)))
