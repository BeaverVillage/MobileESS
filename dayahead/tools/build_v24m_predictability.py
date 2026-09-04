"""Build V24M factor distribution, predictability, and oracle artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logit
from scipy.stats import skew

from dayahead.ml.faser_flex.data import load_training_authority
from dayahead.ml.faser_flex.predictability_audit import (
    blocked_factor_probes,
    build_macro_features,
    point_metrics,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"


def write_json(name: str, payload: object) -> None:
    """Write one deterministic JSON artifact."""

    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def summary(values: np.ndarray) -> dict[str, float]:
    """Summarize a one-dimensional numeric factor."""

    return {
        "zero_rate": float(np.mean(values == 0.0)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "P10": float(np.quantile(values, 0.10)),
        "P50": float(np.quantile(values, 0.50)),
        "P90": float(np.quantile(values, 0.90)),
        "P95": float(np.quantile(values, 0.95)),
        "P99": float(np.quantile(values, 0.99)),
        "skewness": float(skew(values)),
        "CV": float(np.std(values) / max(abs(np.mean(values)), 1e-12)),
        "lag1_autocorrelation": float(pd.Series(values).autocorr(lag=1)),
        "burstiness_P99_over_median": float(
            np.quantile(values, 0.99) / max(np.median(values), 1e-12)
        ),
    }


def main() -> None:
    """Run all factor probes and freeze the information-bottleneck diagnosis."""

    factors = pd.read_csv(OUT / "V24M_FACTORIZED_TARGET_REPRODUCTION.csv")
    factors["KAPPA_DEFINED"] = factors.KAPPA_DEFINED.astype(bool)
    authority = load_training_authority()
    features = build_macro_features(authority.events_with_history, factors.date.tolist())
    features.to_csv(OUT / "V24M_CAUSAL_MACRO_FEATURES.csv", index=False)
    probes = blocked_factor_probes(factors, features).rows
    probes.to_csv(OUT / "V24M_FACTOR_PROBE_OOF.csv", index=False)

    r = factors.R_ALL_GPU_h_requested.to_numpy(float)
    pi = factors.PI_F.to_numpy(float)
    k = factors.loc[factors.KAPPA_DEFINED, "KAPPA_F"].to_numpy(float)
    h = factors.H_F_GPU_h_actual.to_numpy(float)
    valid_joint = factors.KAPPA_DEFINED & factors.PI_F.gt(0.0) & factors.PI_F.lt(1.0)
    joint = factors.loc[valid_joint]
    transformed = np.column_stack(
        [
            np.log1p(joint.R_ALL_GPU_h_requested.to_numpy(float)),
            logit(joint.PI_F.to_numpy(float)),
            logit(joint.KAPPA_F.to_numpy(float)),
        ]
    )
    distribution = {
        "artifact_id": "V24M_FACTOR_DISTRIBUTION_AUDIT_V1",
        "R_ALL": summary(r),
        "PI_F": {
            **summary(pi),
            "one_rate": float(np.mean(pi == 1.0)),
            "weekday_means": factors.assign(dow=pd.to_datetime(factors.date).dt.dayofweek).groupby("dow").PI_F.mean().to_dict(),
            "month_means": factors.assign(month=pd.to_datetime(factors.date).dt.month).groupby("month").PI_F.mean().to_dict(),
        },
        "KAPPA_F_defined": {
            **summary(k),
            "defined_rate": float(factors.KAPPA_DEFINED.mean()),
            "correlation_with_R_F_requested": float(
                factors.loc[factors.KAPPA_DEFINED, ["KAPPA_F", "R_F_GPU_h_requested"]].corr().iloc[0, 1]
            ),
        },
        "H_F": summary(h),
        "transformed_factor_correlation": {
            "columns": ["log1p_R_ALL", "logit_PI_F", "logit_KAPPA_F"],
            "matrix": np.corrcoef(transformed, rowvar=False).tolist(),
            "days": int(len(joint)),
        },
        "target_clipping_calls": 0,
    }
    write_json("V24M_FACTOR_DISTRIBUTION_AUDIT.json", distribution)

    actual = probes.H_F_GPU_h_actual.to_numpy(float)
    burst_thresholds = {}
    burst_mask = np.zeros(len(probes), dtype=bool)
    for fold_id in sorted(probes.fold_id.unique()):
        validation = probes.fold_id.eq(fold_id)
        fold_start = probes.loc[validation, "date"].min()
        training_h = factors.loc[factors.date < fold_start, "H_F_GPU_h_actual"].to_numpy(float)
        threshold = float(np.quantile(training_h, 0.90))
        burst_thresholds[int(fold_id)] = threshold
        burst_mask[validation.to_numpy()] = actual[validation.to_numpy()] >= threshold

    model_columns = {
        "F0_DIRECT_LIGHTGBM_H_F": "F0_DIRECT_LGB",
        "F1_FACTORIZED_LIGHTGBM": "F1_FACTORIZED_LGB",
        "F2_SIMPLE_WEEKDAY_FACTORIZED": "F2_WEEKDAY_FACTORIZED",
        "F3_DIRECT_ORDINARY_RBF_GP": "F3_ORDINARY_GP",
    }
    metrics = {
        name: point_metrics(actual, probes[column].to_numpy(float), burst_mask)
        for name, column in model_columns.items()
    }
    baseline = probes.F1_FACTORIZED_LGB.to_numpy(float)
    pred_r = probes.pred_R_ALL.to_numpy(float)
    pred_pi = probes.pred_PI_F.to_numpy(float)
    pred_k = probes.pred_KAPPA_F.to_numpy(float)
    actual_r = probes.R_ALL_GPU_h_requested.to_numpy(float)
    actual_pi = probes.PI_F.to_numpy(float)
    actual_k = probes.KAPPA_F.fillna(0.0).to_numpy(float)
    oracle_predictions = {
        "ORACLE_R": actual_r * pred_pi * pred_k,
        "ORACLE_PI": pred_r * actual_pi * pred_k,
        "ORACLE_KAPPA": pred_r * pred_pi * actual_k,
        "ORACLE_DAY_REQUEST": actual_r * pred_pi * pred_k,
    }
    oracle_burst = baseline.copy()
    for fold_id in sorted(probes.fold_id.unique()):
        validation = probes.fold_id.eq(fold_id).to_numpy()
        training_h = factors.loc[
            factors.date < probes.loc[validation, "date"].min(), "H_F_GPU_h_actual"
        ].to_numpy(float)
        replacement = float(np.mean(training_h[training_h >= np.quantile(training_h, 0.90)]))
        oracle_burst[validation & burst_mask] = replacement
    oracle_predictions["ORACLE_BURST"] = oracle_burst
    oracle_metrics = {
        name: point_metrics(actual, prediction, burst_mask)
        for name, prediction in oracle_predictions.items()
    }
    direct_wape = metrics["F0_DIRECT_LIGHTGBM_H_F"]["Mean_WAPE"]
    improvements = {
        name: (metrics["F1_FACTORIZED_LIGHTGBM"]["Mean_WAPE"] - value["Mean_WAPE"])
        for name, value in oracle_metrics.items()
    }
    factor_map = {
        "ORACLE_R": "TOTAL_REQUEST_MASS",
        "ORACLE_PI": "FLEXIBLE_SHARE",
        "ORACLE_KAPPA": "RUNTIME_REALIZATION",
        "ORACLE_BURST": "BURST_OCCURRENCE",
        "ORACLE_DAY_REQUEST": "TOTAL_REQUEST_MASS",
    }
    best_oracle = max(improvements, key=improvements.get)
    primary = factor_map[best_oracle]
    if max(improvements.values()) <= 0:
        primary = "TARGET_NOISE_LIMIT"
    elif direct_wape < metrics["F1_FACTORIZED_LIGHTGBM"]["Mean_WAPE"] and max(improvements.values()) < 0.05:
        primary = "MULTI_FACTOR"

    predictability = {
        "artifact_id": "V24M_FACTOR_PREDICTABILITY_AUDIT_V1",
        "folds": 5,
        "same_cutoff": "D-1 18:00 AEST",
        "causal_feature_columns": [column for column in features if column != "date"],
        "model_metrics": metrics,
        "factorized_minus_direct_Mean_WAPE": float(
            metrics["F1_FACTORIZED_LIGHTGBM"]["Mean_WAPE"] - direct_wape
        ),
        "factorized_better_than_direct": bool(
            metrics["F1_FACTORIZED_LIGHTGBM"]["Mean_WAPE"] < direct_wape
        ),
        "burst_threshold_by_fold_GPU_h": burst_thresholds,
        "PRIMARY_BOTTLENECK": primary,
    }
    write_json("V24M_FACTOR_PREDICTABILITY_AUDIT.json", predictability)
    oracle = {
        "artifact_id": "V24M_FACTOR_ORACLE_DIAGNOSTICS_V1",
        "label": "NON_CAUSAL_ORACLE_DIAGNOSTIC_ONLY",
        "production_feature_use": False,
        "oracle_metrics": oracle_metrics,
        "Mean_WAPE_improvement_vs_factorized": improvements,
        "primary_bottleneck": primary,
        "April_reads": 0,
    }
    write_json("V24M_FACTOR_ORACLE_DIAGNOSTICS.json", oracle)
    review = [
        "# V24M factor predictability and oracle ceiling review",
        "",
        f"- Primary bottleneck: `{primary}`",
        f"- Direct LightGBM Mean WAPE: `{direct_wape:.12f}`",
        f"- Factorized LightGBM Mean WAPE: `{metrics['F1_FACTORIZED_LIGHTGBM']['Mean_WAPE']:.12f}`",
        f"- Factorization better than direct: `{str(predictability['factorized_better_than_direct']).lower()}`",
        "",
        "Oracle values are explicitly non-causal diagnostics and are excluded from every production feature and selection path.",
    ]
    (OUT / "V24M_FACTOR_BOTTLENECK_REVIEW.md").write_text(
        "\n".join(review) + "\n", encoding="utf-8"
    )
    print(json.dumps({"metrics": metrics, "oracle": oracle_metrics, "bottleneck": primary}, indent=2))


if __name__ == "__main__":
    main()
