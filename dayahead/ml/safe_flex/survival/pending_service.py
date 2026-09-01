"""Conditional pending-job service requirement distributions."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from dayahead.ml.safe_flex.survival.pending_realization import PENDING_FEATURES


def fit_service_models(train: pd.DataFrame, seed: int) -> dict[str, lgb.LGBMRegressor]:
    """Fit conditional mean/Q10/Q50/Q90 service models in GPU-hour units."""

    realized = train.loc[train.realized_service.eq(1) & train.service_total_GPU_h.gt(0)]
    common = dict(n_estimators=160, learning_rate=0.035, num_leaves=24, min_child_samples=50, verbosity=-1, random_state=seed, n_jobs=-1)
    models = {"mean": lgb.LGBMRegressor(objective="tweedie", tweedie_variance_power=1.4, **common)}
    for name, alpha in (("Q10", 0.1), ("Q50", 0.5), ("Q90", 0.9)):
        models[name] = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **common)
    for model in models.values():
        model.fit(realized[PENDING_FEATURES], realized.service_total_GPU_h)
    return models


def predict_service(models: dict[str, lgb.LGBMRegressor], frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Predict nonnegative ordered conditional service statistics."""

    raw = {name: np.maximum(model.predict(frame[PENDING_FEATURES]), 0.0) for name, model in models.items()}
    ordered = np.sort(np.column_stack((raw["Q10"], raw["Q50"], raw["Q90"])), axis=1)
    return {"mean": raw["mean"], "Q10": ordered[:, 0], "Q50": ordered[:, 1], "Q90": ordered[:, 2]}


def service_metrics(frame: pd.DataFrame, pred: dict[str, np.ndarray]) -> dict[str, float]:
    """Return conditional service WAPE, pinball, and interval coverage."""

    y = frame.service_total_GPU_h.to_numpy(float)
    pin = lambda q, p: float(np.mean(np.maximum(q * (y - p), (q - 1) * (y - p))))
    return {
        "mean_WAPE": float(np.abs(y - pred["mean"]).sum() / y.sum()),
        "Q50_WAPE": float(np.abs(y - pred["Q50"]).sum() / y.sum()),
        "Q10_pinball": pin(0.1, pred["Q10"]), "Q50_pinball": pin(0.5, pred["Q50"]),
        "Q90_pinball": pin(0.9, pred["Q90"]),
        "Q10_Q90_coverage": float(np.mean((y >= pred["Q10"]) & (y <= pred["Q90"]))),
        "positive_duration_predictions": bool(np.all(pred["mean"] >= 0)),
    }

