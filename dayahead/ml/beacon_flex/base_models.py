"""Frozen LightGBM mean and expanded-quantile base models."""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np

from .contracts import BASE_QUANTILES


@dataclass
class BaseModels:
    """A conditional mean model and nine quantile models in GPU-h."""

    mean_model: lgb.LGBMRegressor
    quantile_models: list[lgb.LGBMRegressor]

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return nonnegative raw conditional mean and quantile grid in GPU-h."""

        mean = np.maximum(0.0, self.mean_model.predict(features))
        quantiles = np.column_stack([np.maximum(0.0, model.predict(features)) for model in self.quantile_models])
        return mean, quantiles


def fit_base_models(features: np.ndarray, target_GPU_h: np.ndarray, seed: int) -> BaseModels:
    """Fit the B2-compatible mean and B3-feature-universe quantile grid."""

    common = dict(
        n_estimators=120, learning_rate=0.035, num_leaves=7, min_child_samples=12,
        max_depth=3, reg_lambda=1.0, random_state=seed, deterministic=True,
        force_col_wise=True, verbosity=-1, n_jobs=1,
    )
    mean_model = lgb.LGBMRegressor(objective="tweedie", tweedie_variance_power=1.5, **common)
    mean_model.fit(features, target_GPU_h)
    quantile_models = []
    for tau in BASE_QUANTILES:
        model = lgb.LGBMRegressor(objective="quantile", alpha=tau, **common)
        model.fit(features, target_GPU_h)
        quantile_models.append(model)
    return BaseModels(mean_model, quantile_models)

