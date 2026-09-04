"""Preregistered fixed residual-signal audit models."""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler, StandardScaler

from .residual_dataset import BASE_FEATURES, RUNNING_FEATURES, STATE_FEATURES


@dataclass(frozen=True)
class ModelSpec:
    name: str
    features: list[str]
    kind: str
    shrinkage: float


def audit_specs() -> list[ModelSpec]:
    return [
        ModelSpec("R0_ZERO_CORRECTION", [], "zero", 0.0),
        ModelSpec("R1_ELASTICNET_RESIDUAL", BASE_FEATURES + STATE_FEATURES + RUNNING_FEATURES, "elastic", 0.50),
        ModelSpec("R2_BASE_ONLY_LGBM_RESIDUAL", BASE_FEATURES, "lgbm", 0.50),
        ModelSpec("R3_STATE_LGBM_RESIDUAL", BASE_FEATURES + STATE_FEATURES, "lgbm", 0.50),
        ModelSpec("R4_STATE_RUNNING_LGBM_RESIDUAL", BASE_FEATURES + STATE_FEATURES + RUNNING_FEATURES, "lgbm", 0.50),
        ModelSpec("R5_SMALL_MLP_RESIDUAL", BASE_FEATURES + STATE_FEATURES + RUNNING_FEATURES, "mlp", 0.25),
    ]


def fit_predict(train: pd.DataFrame, valid: pd.DataFrame, spec: ModelSpec, target: str, seed: int) -> np.ndarray:
    if spec.kind == "zero":
        return np.zeros(len(valid), dtype=float)
    x_train = train[spec.features]
    x_valid = valid[spec.features]
    if spec.kind == "elastic":
        model = make_pipeline(RobustScaler(), ElasticNet(alpha=0.01, l1_ratio=0.25, max_iter=5000, random_state=seed))
    elif spec.kind == "lgbm":
        model = lgb.LGBMRegressor(
            objective="regression_l1", n_estimators=160, learning_rate=0.03,
            num_leaves=16, max_depth=5, min_child_samples=96,
            reg_lambda=2.0, reg_alpha=0.1, verbosity=-1,
            deterministic=True, force_col_wise=True, random_state=seed, n_jobs=1,
        )
    elif spec.kind == "mlp":
        model = make_pipeline(
            StandardScaler(),
            MLPRegressor(hidden_layer_sizes=(32,), activation="relu", alpha=0.01,
                         max_iter=200, early_stopping=True, random_state=seed),
        )
    else:
        raise ValueError(spec.kind)
    model.fit(x_train, train[target])
    return spec.shrinkage * model.predict(x_valid)

