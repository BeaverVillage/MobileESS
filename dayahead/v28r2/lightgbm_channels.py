"""Frozen LightGBM quantile fits for P, G, and strict full-node W."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from dayahead.v28r2.source_labels import OptimizerLabels, TRAIN_START


SEED = 20260901
QUANTILES = (0.1, 0.5, 0.9)
COMMON = {
    "n_estimators": 120,
    "learning_rate": 0.035,
    "num_leaves": 7,
    "min_child_samples": 12,
    "max_depth": 3,
    "reg_lambda": 1.0,
    "random_state": SEED,
    "deterministic": True,
    "verbosity": -1,
    "n_jobs": 1,
}
SLOT_FEATURES = (
    "slot", "slot_sin", "slot_cos", "dow_sin", "dow_cos", "weekend",
    "month_sin", "month_cos", "lag_2d", "lag_7d", "same_slot_mean_2_8d",
    "same_slot_std_2_8d",
)
DAILY_FEATURES = (
    "dow_sin", "dow_cos", "weekend", "month_sin", "month_cos",
    "lag_2d", "lag_7d", "mean_2_8d", "std_2_8d",
)


@dataclass(frozen=True)
class FitRecord:
    channel: str
    variant: str
    training_end: str
    training_rows: int
    model_sha256: dict[str, str]
    prediction_min: dict[str, float]
    noncrossing_violations: int
    raw_noncrossing_violations: int
    noncrossing_projection_cells: int


def enforce_quantile_integrity(raw_log_predictions: np.ndarray) -> np.ndarray:
    """Map raw Q10/Q50/Q90 log predictions to the public output contract.

    Sorting is a fixed rearrangement, not a fitted calibration.  ``expm1`` of
    nonnegative training-label quantile trees supplies the physical scale; a
    mathematical zero lower bound protects only floating roundoff.
    """

    raw = np.asarray(raw_log_predictions, dtype=float)
    if raw.shape[0] != 3 or not np.isfinite(raw).all():
        raise ValueError("V28R2_QUANTILE_PREDICTION_SHAPE_OR_FINITE")
    return np.maximum(np.expm1(np.sort(raw, axis=0)), 0.0)


def predict_serialized_quantiles(
    model_dir: Path,
    channel: str,
    variant: str,
    features: pd.DataFrame,
    booster_cache: dict[tuple[str, str], tuple[object, ...]] | None = None,
) -> np.ndarray:
    """Load the three hashed model texts without passing a Unicode path to C."""

    import lightgbm as lgb

    key = (channel, variant)
    boosters = booster_cache.get(key) if booster_cache is not None else None
    if boosters is None:
        loaded = []
        for quantile in QUANTILES:
            label = f"q{int(quantile * 100):02d}"
            path = model_dir / f"{channel}_{variant}_{label}.txt"
            loaded.append(lgb.Booster(model_str=path.read_text(encoding="utf-8")))
        boosters = tuple(loaded)
        if booster_cache is not None:
            booster_cache[key] = boosters
    raw = [np.asarray(booster.predict(features), dtype=float) for booster in boosters]
    return enforce_quantile_integrity(np.stack(raw))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slot_features(values: np.ndarray, timestamps: pd.DatetimeIndex) -> pd.DataFrame:
    series = pd.Series(values, index=timestamps, dtype=float)
    slot = timestamps.hour * 4 + timestamps.minute // 15
    frame = pd.DataFrame(index=timestamps)
    frame["slot"] = slot
    frame["slot_sin"] = np.sin(2 * np.pi * slot / 96)
    frame["slot_cos"] = np.cos(2 * np.pi * slot / 96)
    frame["dow_sin"] = np.sin(2 * np.pi * timestamps.dayofweek / 7)
    frame["dow_cos"] = np.cos(2 * np.pi * timestamps.dayofweek / 7)
    frame["weekend"] = (timestamps.dayofweek >= 5).astype(int)
    frame["month_sin"] = np.sin(2 * np.pi * (timestamps.month - 1) / 12)
    frame["month_cos"] = np.cos(2 * np.pi * (timestamps.month - 1) / 12)
    frame["lag_2d"] = series.shift(192)
    frame["lag_7d"] = series.shift(672)
    past = pd.concat([series.shift(96 * lag) for lag in range(2, 9)], axis=1)
    frame["same_slot_mean_2_8d"] = past.mean(axis=1)
    frame["same_slot_std_2_8d"] = past.std(axis=1, ddof=0)
    return frame.loc[:, SLOT_FEATURES]


def daily_features(values: pd.Series) -> pd.DataFrame:
    index = values.index
    frame = pd.DataFrame(index=index)
    frame["dow_sin"] = np.sin(2 * np.pi * index.dayofweek / 7)
    frame["dow_cos"] = np.cos(2 * np.pi * index.dayofweek / 7)
    frame["weekend"] = (index.dayofweek >= 5).astype(int)
    frame["month_sin"] = np.sin(2 * np.pi * (index.month - 1) / 12)
    frame["month_cos"] = np.cos(2 * np.pi * (index.month - 1) / 12)
    frame["lag_2d"] = values.shift(2)
    frame["lag_7d"] = values.shift(7)
    past = pd.concat([values.shift(lag) for lag in range(2, 9)], axis=1)
    frame["mean_2_8d"] = past.mean(axis=1)
    frame["std_2_8d"] = past.std(axis=1, ddof=0)
    return frame.loc[:, DAILY_FEATURES]


def _variant_for_day(day: pd.Timestamp) -> str:
    return "APRIL_01_CAUSAL_FIT" if day.day == 1 else "GENERAL_THROUGH_MARCH_31_FIT"


def _recursive_slot_predictions(
    values: np.ndarray,
    timestamps: pd.DatetimeIndex,
    target: pd.Timestamp,
    model_dir: Path,
    channel: str,
    booster_cache: dict[tuple[str, str], tuple[object, ...]],
) -> np.ndarray:
    """Roll P/G forward with q50 as causal lag state, never April actuals."""
    future_index = pd.date_range(
        timestamps[-1] + pd.Timedelta(minutes=15),
        target + pd.Timedelta(days=1), freq="15min", inclusive="left",
    )
    extended_index = timestamps.append(future_index)
    extended_values = np.concatenate([values, np.full(len(future_index), np.nan)])
    result: np.ndarray | None = None
    first_day = future_index[0].normalize()
    for forecast_day in pd.date_range(first_day, target.normalize(), freq="D"):
        target_index = pd.date_range(forecast_day, periods=96, freq="15min")
        features = slot_features(extended_values, extended_index).loc[target_index]
        if not np.isfinite(features).all().all():
            raise RuntimeError(f"V28R2_CAUSAL_SLOT_FEATURE_MISSING:{channel}:{forecast_day.date()}")
        result = predict_serialized_quantiles(
            model_dir, channel, _variant_for_day(forecast_day), features, booster_cache,
        )
        positions = extended_index.get_indexer(target_index)
        if np.any(positions < 0):
            raise RuntimeError("V28R2_CAUSAL_SLOT_ROLLOUT_AXIS")
        extended_values[positions] = result[1]
    if result is None:
        raise RuntimeError("V28R2_CAUSAL_SLOT_ROLLOUT_EMPTY")
    return result


def _recursive_daily_predictions(
    values: pd.Series,
    target: pd.Timestamp,
    model_dir: Path,
    booster_cache: dict[tuple[str, str], tuple[object, ...]],
) -> np.ndarray:
    """Roll daily W forward with q50 as causal lag state, never April actuals."""
    future_days = pd.date_range(values.index[-1] + pd.Timedelta(days=1), target, freq="D")
    extended = pd.concat([values, pd.Series(np.nan, index=future_days)])
    result: np.ndarray | None = None
    for forecast_day in future_days:
        features = daily_features(extended).loc[[forecast_day]]
        if not np.isfinite(features).all().all():
            raise RuntimeError(f"V28R2_CAUSAL_W_FEATURE_MISSING:{forecast_day.date()}")
        result = predict_serialized_quantiles(
            model_dir, "W_FULLNODE_DAILY", _variant_for_day(forecast_day),
            features, booster_cache,
        )
        extended.loc[forecast_day] = result[1, 0]
    if result is None:
        raise RuntimeError("V28R2_CAUSAL_W_ROLLOUT_EMPTY")
    return result[:, 0]


def causal_optimizer_predictions(
    labels: OptimizerLabels, target_date: str, model_dir: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Materialize P/G slot quantiles and strict-fullnode daily W quantiles."""

    target = pd.Timestamp(target_date, tz=labels.timestamps.tz)
    if not pd.Timestamp("2025-04-01", tz=labels.timestamps.tz) <= target <= pd.Timestamp("2025-04-30", tz=labels.timestamps.tz):
        raise ValueError("V28R2_OPTIMIZER_MATERIALIZATION_APRIL_ONLY")
    booster_cache: dict[tuple[str, str], tuple[object, ...]] = {}
    p_quantiles = _recursive_slot_predictions(
        labels.p_it_kw, labels.timestamps, target, model_dir, "P_REF", booster_cache,
    )
    g_quantiles = _recursive_slot_predictions(
        labels.g_h100_gpu, labels.timestamps, target, model_dir, "G_REF", booster_cache,
    )

    daily_index = pd.date_range(
        labels.timestamps[0].normalize(), labels.timestamps[-1].normalize(),
        freq="D", tz=labels.timestamps.tz,
    )
    daily_w = pd.Series(
        labels.w_nodeh.reshape(-1, 96, len(labels.cohort_ids)).sum(axis=(1, 2)),
        index=daily_index,
    )
    w_quantiles = _recursive_daily_predictions(daily_w, target, model_dir, booster_cache)
    return p_quantiles, g_quantiles, w_quantiles


def _fit_quantiles(
    channel: str,
    variant: str,
    training_end: str,
    features: pd.DataFrame,
    target: pd.Series,
    model_dir: Path,
) -> FitRecord:
    end_exclusive = pd.Timestamp(training_end, tz=target.index.tz) + pd.Timedelta(days=1)
    start = pd.Timestamp(TRAIN_START, tz=target.index.tz)
    selected = target.index.to_series().ge(start).to_numpy() & target.index.to_series().lt(end_exclusive).to_numpy()
    selected &= np.isfinite(target.to_numpy()) & np.isfinite(features.to_numpy()).all(axis=1)
    x = features.loc[selected]
    y = target.loc[selected]
    if len(y) == 0:
        raise RuntimeError(f"V28R2_EMPTY_TRAINING_TARGET:{channel}:{variant}")
    model_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    predictions: list[np.ndarray] = []
    minima: dict[str, float] = {}
    for quantile in QUANTILES:
        label = f"q{int(quantile * 100):02d}"
        model = LGBMRegressor(objective="quantile", alpha=quantile, **COMMON)
        model.fit(x, np.log1p(y))
        path = model_dir / f"{channel}_{variant}_{label}.txt"
        path.write_text(model.booster_.model_to_string(), encoding="utf-8", newline="\n")
        hashes[label] = sha256(path)
        prediction = np.asarray(model.predict(x), dtype=float)
        predictions.append(prediction)
    raw = np.stack(predictions)
    raw_cross = (raw[1] + 1e-12 < raw[0]) | (raw[2] + 1e-12 < raw[1])
    public = enforce_quantile_integrity(raw)
    for index, quantile in enumerate(QUANTILES):
        minima[f"q{int(quantile * 100):02d}"] = float(public[index].min())
    violations = int(((public[0] < 0) | (public[1] < public[0]) | (public[2] < public[1])).sum())
    return FitRecord(
        channel, variant, training_end, int(len(y)), hashes, minima, violations,
        int(raw_cross.sum()), int(np.count_nonzero(raw != np.sort(raw, axis=0))),
    )


def fit_all(labels: OptimizerLabels, model_dir: Path) -> list[FitRecord]:
    p_features = slot_features(labels.p_it_kw, labels.timestamps)
    g_features = slot_features(labels.g_h100_gpu, labels.timestamps)
    p_target = pd.Series(labels.p_it_kw, index=labels.timestamps)
    g_target = pd.Series(labels.g_h100_gpu, index=labels.timestamps)
    daily_index = pd.date_range(labels.timestamps[0].normalize(), labels.timestamps[-1].normalize(), freq="D", tz=labels.timestamps.tz)
    daily_w = pd.Series(labels.w_nodeh.reshape(-1, 96, len(labels.cohort_ids)).sum(axis=(1, 2)), index=daily_index)
    w_features = daily_features(daily_w)
    records: list[FitRecord] = []
    for variant, end in (("APRIL_01_CAUSAL_FIT", "2025-03-30"), ("GENERAL_THROUGH_MARCH_31_FIT", "2025-03-31")):
        records.append(_fit_quantiles("P_REF", variant, end, p_features, p_target, model_dir))
        records.append(_fit_quantiles("G_REF", variant, end, g_features, g_target, model_dir))
        records.append(_fit_quantiles("W_FULLNODE_DAILY", variant, end, w_features, daily_w, model_dir))
    return records
