"""Training-only causal factor probes and non-causal oracle diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from dayahead.ml.c_mass_tpp.data import AEST, VICTORIA_HOLIDAYS

from .contracts import FOLDS


@dataclass(frozen=True)
class ProbePredictions:
    """Daily out-of-fold factor and total forecasts in physical units."""

    rows: pd.DataFrame


def production_cutoff(date: str) -> pd.Timestamp:
    """Return the D-1 18:00 AEST forecast cutoff for a target day."""

    return pd.Timestamp(date, tz=AEST) - pd.Timedelta(hours=6)


def build_macro_features(events: pd.DataFrame, dates: list[str]) -> pd.DataFrame:
    """Build request-side aggregate predictors using only events before each cutoff."""

    rows: list[dict[str, float | str]] = []
    for date in dates:
        cutoff = production_cutoff(date)
        row: dict[str, float | str] = {"date": date}
        for days, suffix in ((1, "1d"), (7, "7d"), (28, "28d")):
            part = events.loc[
                events.submit_AEST.lt(cutoff)
                & events.submit_AEST.ge(cutoff - pd.Timedelta(days=days))
            ]
            requested = part.requested_service_proxy_GPU_h.to_numpy(float)
            row[f"jobs_{suffix}"] = float(len(part))
            row[f"requested_GPU_{suffix}"] = float(part.gpus_requested.sum())
            row[f"requested_GPU_h_{suffix}"] = float(np.sum(requested))
            row[f"requested_nodes_{suffix}"] = float(part.nodes_req.sum())
            row[f"unique_accounts_{suffix}"] = float(part.account_hash.nunique())
            row[f"full_requested_GPU_h_{suffix}"] = float(
                part.loc[part.request_full.eq(1.0), "requested_service_proxy_GPU_h"].sum()
            )
        part28 = events.loc[
            events.submit_AEST.lt(cutoff)
            & events.submit_AEST.ge(cutoff - pd.Timedelta(days=28))
        ]
        account_mass = (
            part28.groupby("account_hash").requested_service_proxy_GPU_h.sum().to_numpy(float)
        )
        if account_mass.sum() > 0:
            probability = account_mass / account_mass.sum()
            row["account_entropy_28d"] = float(
                -np.sum(probability * np.log(np.maximum(probability, 1e-15)))
            )
        else:
            row["account_entropy_28d"] = 0.0
        for suffix in ("7d", "28d"):
            total = float(row[f"requested_GPU_h_{suffix}"])
            row[f"full_share_{suffix}"] = (
                float(row[f"full_requested_GPU_h_{suffix}"]) / total if total > 0 else 0.0
            )
        timestamp = pd.Timestamp(date)
        row.update(
            {
                "dow_sin": float(np.sin(2 * np.pi * timestamp.dayofweek / 7)),
                "dow_cos": float(np.cos(2 * np.pi * timestamp.dayofweek / 7)),
                "month_sin": float(np.sin(2 * np.pi * timestamp.month / 12)),
                "month_cos": float(np.cos(2 * np.pi * timestamp.month / 12)),
                "holiday": float(date in VICTORIA_HOLIDAYS),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _lgb_regressor(objective: str, seed: int) -> lgb.LGBMRegressor:
    """Return the preregistered compact deterministic LightGBM probe."""

    return lgb.LGBMRegressor(
        objective=objective,
        n_estimators=100,
        learning_rate=0.04,
        num_leaves=15,
        min_child_samples=12,
        subsample=1.0,
        colsample_bytree=1.0,
        reg_lambda=1.0,
        random_state=seed,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
    )


def _fit_direct_lgb(
    train_x: pd.DataFrame, train_y: np.ndarray, valid_x: pd.DataFrame, seed: int
) -> np.ndarray:
    """Predict nonnegative daily actual GPU-h with a Tweedie objective."""

    model = _lgb_regressor("tweedie", seed)
    model.set_params(tweedie_variance_power=1.5)
    model.fit(train_x, train_y)
    return np.maximum(0.0, model.predict(valid_x))


def _fit_factorized_lgb(
    train_x: pd.DataFrame,
    train: pd.DataFrame,
    valid_x: pd.DataFrame,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Predict R_ALL, PI_F, and KAPPA_F separately and multiply in physical space."""

    r_model = _lgb_regressor("tweedie", seed)
    r_model.set_params(tweedie_variance_power=1.5)
    r_model.fit(train_x, train.R_ALL_GPU_h_requested.to_numpy(float))
    pred_r = np.maximum(0.0, r_model.predict(valid_x))

    positive = train.PI_F.gt(0.0)
    occurrence = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=80,
        learning_rate=0.04,
        num_leaves=9,
        min_child_samples=12,
        reg_lambda=1.0,
        random_state=seed,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
    )
    occurrence.fit(train_x, positive.astype(int))
    p_positive = occurrence.predict_proba(valid_x)[:, 1]
    positive_pi = train.loc[positive, "PI_F"].to_numpy(float)
    if np.any(positive_pi >= 1.0):
        raise RuntimeError("V24M_PI_ONE_INFLATION_REQUIRES_EXPLICIT_BRANCH")
    pi_model = _lgb_regressor("regression", seed)
    pi_model.fit(train_x.loc[positive], logit(positive_pi))
    pred_pi = p_positive * expit(pi_model.predict(valid_x))

    defined = train.KAPPA_DEFINED.astype(bool)
    kappa_values = train.loc[defined, "KAPPA_F"].to_numpy(float)
    if np.any((kappa_values <= 0.0) | (kappa_values >= 1.0)):
        raise RuntimeError("V24M_KAPPA_LOGIT_SUPPORT_VIOLATION")
    kappa_model = _lgb_regressor("regression", seed)
    kappa_model.fit(train_x.loc[defined], logit(kappa_values))
    pred_kappa = expit(kappa_model.predict(valid_x))
    pred_h = pred_r * pred_pi * pred_kappa
    return pred_r, pred_pi, pred_kappa, pred_h


def _fit_weekday_factorized(train: pd.DataFrame, valid: pd.DataFrame) -> np.ndarray:
    """Return a training-only weekday factor-product baseline in GPU-h."""

    train = train.copy()
    valid = valid.copy()
    train["dow"] = pd.to_datetime(train.date).dt.dayofweek
    valid["dow"] = pd.to_datetime(valid.date).dt.dayofweek
    global_values = {
        "R": float(train.R_ALL_GPU_h_requested.mean()),
        "PI": float(train.PI_F.mean()),
        "K": float(train.loc[train.KAPPA_DEFINED, "KAPPA_F"].mean()),
    }
    grouped = train.groupby("dow").agg(
        R=("R_ALL_GPU_h_requested", "mean"),
        PI=("PI_F", "mean"),
        K=("KAPPA_F", "mean"),
    )
    return np.asarray(
        [
            float(grouped.loc[dow, "R"] if dow in grouped.index else global_values["R"])
            * float(grouped.loc[dow, "PI"] if dow in grouped.index else global_values["PI"])
            * float(grouped.loc[dow, "K"] if dow in grouped.index else global_values["K"])
            for dow in valid.dow
        ]
    )


def _fit_ordinary_gp(
    train_x: pd.DataFrame, train_y: np.ndarray, valid_x: pd.DataFrame, seed: int
) -> np.ndarray:
    """Fit an exact ordinary-feature GP on log1p daily GPU-h."""

    kernel = ConstantKernel(1.0, (1e-2, 1e2)) * Matern(
        length_scale=1.0, nu=1.5
    ) + WhiteKernel(noise_level=0.1, noise_level_bounds=(1e-5, 10.0))
    model = make_pipeline(
        StandardScaler(),
        GaussianProcessRegressor(
            kernel=kernel,
            alpha=1e-6,
            normalize_y=True,
            n_restarts_optimizer=0,
            random_state=seed,
        ),
    )
    model.fit(train_x, np.log1p(train_y))
    return np.maximum(0.0, np.expm1(model.predict(valid_x)))


def blocked_factor_probes(
    factors: pd.DataFrame, features: pd.DataFrame, seed: int = 20260901
) -> ProbePredictions:
    """Run F0--F3 and factor predictions on the frozen expanding folds."""

    data = factors.merge(features, on="date", validate="one_to_one")
    feature_columns = [column for column in features.columns if column != "date"]
    output: list[pd.DataFrame] = []
    for fold in FOLDS:
        train = data.loc[(data.date >= fold.train_start) & (data.date <= fold.train_end)]
        valid = data.loc[
            (data.date >= fold.validation_start) & (data.date <= fold.validation_end)
        ].copy()
        train_x = train[feature_columns]
        valid_x = valid[feature_columns]
        direct = _fit_direct_lgb(
            train_x, train.H_F_GPU_h_actual.to_numpy(float), valid_x, seed
        )
        pred_r, pred_pi, pred_k, factorized = _fit_factorized_lgb(
            train_x, train, valid_x, seed
        )
        weekday = _fit_weekday_factorized(train, valid)
        gp = _fit_ordinary_gp(
            train_x, train.H_F_GPU_h_actual.to_numpy(float), valid_x, seed
        )
        block = valid[
            [
                "date",
                "R_ALL_GPU_h_requested",
                "PI_F",
                "KAPPA_DEFINED",
                "KAPPA_F",
                "H_F_GPU_h_actual",
            ]
        ].copy()
        block["fold_id"] = fold.fold_id
        block["F0_DIRECT_LGB"] = direct
        block["pred_R_ALL"] = pred_r
        block["pred_PI_F"] = pred_pi
        block["pred_KAPPA_F"] = pred_k
        block["F1_FACTORIZED_LGB"] = factorized
        block["F2_WEEKDAY_FACTORIZED"] = weekday
        block["F3_ORDINARY_GP"] = gp
        output.append(block)
    return ProbePredictions(pd.concat(output, ignore_index=True))


def point_metrics(actual: np.ndarray, predicted: np.ndarray, burst: np.ndarray) -> dict[str, float]:
    """Compute daily GPU-h point metrics without target or forecast clipping."""

    error = predicted - actual
    denominator = max(float(np.abs(actual).sum()), 1e-12)
    burst_denominator = max(float(np.abs(actual[burst]).sum()), 1e-12)
    return {
        "Mean_WAPE": float(np.abs(error).sum() / denominator),
        "MAE_GPU_h": float(np.mean(np.abs(error))),
        "aggregate_mass_ratio": float(predicted.sum() / denominator),
        "Burst_WAPE": float(np.abs(error[burst]).sum() / burst_denominator),
    }
