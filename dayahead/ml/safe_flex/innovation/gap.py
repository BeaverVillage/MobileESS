"""Small pre-cutoff model for six-hour gap innovation."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd


GAP_FEATURES = ["dow_sin", "dow_cos", "month_sin", "month_cos", "lag1_G", "lag7_G", "lag7_total_mean", "lag28_total_mean"]


def gap_daily_frame(shares: pd.DataFrame) -> pd.DataFrame:
    """Create causal daily gap features; units are GPU-hours."""

    frame = shares[["target_day", "H_G_GPU_h", "H_N_GPU_h", "H_total_GPU_h"]].copy()
    date = pd.to_datetime(frame.target_day)
    frame["dow_sin"] = np.sin(2 * np.pi * date.dt.dayofweek / 7)
    frame["dow_cos"] = np.cos(2 * np.pi * date.dt.dayofweek / 7)
    frame["month_sin"] = np.sin(2 * np.pi * date.dt.month / 12)
    frame["month_cos"] = np.cos(2 * np.pi * date.dt.month / 12)
    frame["lag1_G"] = frame.H_G_GPU_h.shift(1)
    frame["lag7_G"] = frame.H_G_GPU_h.shift(7)
    frame["lag7_total_mean"] = frame.H_total_GPU_h.shift(1).rolling(7, min_periods=1).mean()
    frame["lag28_total_mean"] = frame.H_total_GPU_h.shift(1).rolling(28, min_periods=1).mean()
    return frame.fillna(0.0)


def fit_gap_models(train: pd.DataFrame, seed: int) -> dict[str, lgb.LGBMRegressor]:
    """Fit G1 Tweedie mean and G2 quantiles without deep architecture."""

    common = dict(n_estimators=90, learning_rate=0.04, num_leaves=12, min_child_samples=15, verbosity=-1, random_state=seed, n_jobs=-1)
    models = {"mean": lgb.LGBMRegressor(objective="tweedie", tweedie_variance_power=1.3, **common)}
    for name, alpha in (("Q50", 0.5), ("Q90", 0.9)):
        models[name] = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **common)
    for model in models.values():
        model.fit(train[GAP_FEATURES], train.H_G_GPU_h)
    return models


def predict_gap(models: dict[str, lgb.LGBMRegressor], frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Return nonnegative ordered gap mean/Q50/Q90 GPU-hours."""

    mean = np.maximum(models["mean"].predict(frame[GAP_FEATURES]), 0)
    q50 = np.maximum(models["Q50"].predict(frame[GAP_FEATURES]), 0)
    q90 = np.maximum(models["Q90"].predict(frame[GAP_FEATURES]), q50)
    return {"mean": mean, "Q50": q50, "Q90": q90}

