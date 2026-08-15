"""Representativeness metrics for provisional K=4/8/12 selections."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from period_selection.candidate_weeks import southern_season
from period_selection.feature_builder import FEATURE_COLUMNS, validate_feature_table


QUANTILES = (0.05, 0.50, 0.95, 0.99)
RAMP_LAGS = (1, 3, 12)


def _safe_relative(error: float, reference: float) -> float | None:
    return None if abs(reference) < 1e-12 else error / abs(reference)


def _reconstructed_blocks(
    features: pd.DataFrame,
    selection: pd.DataFrame,
    season: str | None = None,
) -> list[tuple[pd.DataFrame, int]]:
    rows = selection if season is None else selection[selection["season"] == season]
    return [
        (
            features.iloc[int(row.start_index): int(row.end_index_exclusive)].copy(),
            int(row.cluster_size_weeks),
        )
        for row in rows.itertuples(index=False)
    ]


def _repeat_blocks(blocks: list[tuple[pd.DataFrame, int]]) -> pd.DataFrame:
    pieces = [[block] * repeats for block, repeats in blocks]
    flattened = [item for group in pieces for item in group]
    if not flattened:
        raise ValueError("no reconstructed blocks")
    return pd.concat(flattened, ignore_index=True)


def _mean_energy_errors(reference: pd.DataFrame, reconstructed: pd.DataFrame) -> dict[str, Any]:
    result = {}
    annual_steps = len(reference)
    for name in FEATURE_COLUMNS:
        ref = float(reference[name].mean())
        est = float(reconstructed[name].mean())
        error = est - ref
        ref_energy = ref * annual_steps * 5.0 / 60.0
        est_energy = est * annual_steps * 5.0 / 60.0
        result[name] = {
            "reference_mean": ref,
            "representative_mean": est,
            "mean_absolute_error": abs(error),
            "mean_relative_error": _safe_relative(error, ref),
            "reference_integrated_5min_value_hours": ref_energy,
            "representative_integrated_5min_value_hours": est_energy,
            "energy_relative_error": _safe_relative(est_energy - ref_energy, ref_energy),
        }
    return result


def _quantile_errors(reference: pd.DataFrame, reconstructed: pd.DataFrame) -> dict[str, Any]:
    result = {}
    for name in FEATURE_COLUMNS:
        ref_values = reference[name].to_numpy(dtype=float)
        est_values = reconstructed[name].to_numpy(dtype=float)
        feature = {}
        for q in QUANTILES:
            ref = float(np.quantile(ref_values, q))
            est = float(np.quantile(est_values, q))
            error = est - ref
            feature[f"p{int(q * 100):02d}"] = {
                "reference": ref,
                "representative": est,
                "absolute_error": abs(error),
                "relative_error": _safe_relative(error, ref),
            }
        result[name] = feature
    return result


def _ramp_errors(
    reference: pd.DataFrame,
    blocks: list[tuple[pd.DataFrame, int]],
) -> dict[str, Any]:
    result = {}
    for name in FEATURE_COLUMNS:
        feature = {}
        ref_values = reference[name].to_numpy(dtype=float)
        for lag in RAMP_LAGS:
            ref_ramp = np.abs(ref_values[lag:] - ref_values[:-lag])
            selected_ramps = []
            for block, repeats in blocks:
                values = block[name].to_numpy(dtype=float)
                ramps = np.abs(values[lag:] - values[:-lag])
                selected_ramps.extend([ramps] * repeats)
            est_ramp = np.concatenate(selected_ramps)
            ref = float(np.quantile(ref_ramp, 0.95))
            est = float(np.quantile(est_ramp, 0.95))
            feature[{1: "5min", 3: "15min", 12: "60min"}[lag]] = {
                "reference_p95": ref,
                "representative_p95": est,
                "absolute_error": abs(est - ref),
                "relative_error": _safe_relative(est - ref, ref),
            }
        result[name] = feature
    return result


def _correlation_error(reference: pd.DataFrame, reconstructed: pd.DataFrame) -> dict[str, Any]:
    ref = reference[FEATURE_COLUMNS].corr().fillna(0.0)
    est = reconstructed[FEATURE_COLUMNS].corr().fillna(0.0)
    delta = np.abs(est.to_numpy() - ref.to_numpy())
    return {
        "feature_order": FEATURE_COLUMNS,
        "reference": ref.to_numpy().tolist(),
        "representative": est.to_numpy().tolist(),
        "absolute_error": delta.tolist(),
        "mean_absolute_error": float(delta.mean()),
        "max_absolute_error": float(delta.max()),
    }


def _daytype_coverage(reference: pd.DataFrame, reconstructed: pd.DataFrame) -> dict[str, float]:
    ref_ts = pd.DatetimeIndex(reference["timestamp_aest"])
    est_ts = pd.DatetimeIndex(reconstructed["timestamp_aest"])
    ref_weekend = float((ref_ts.dayofweek >= 5).mean())
    est_weekend = float((est_ts.dayofweek >= 5).mean())
    return {
        "reference_weekday_fraction": 1.0 - ref_weekend,
        "reference_weekend_fraction": ref_weekend,
        "representative_weekday_fraction": 1.0 - est_weekend,
        "representative_weekend_fraction": est_weekend,
        "weekend_fraction_absolute_error": abs(est_weekend - ref_weekend),
    }


def _peak_time_distribution(reference: pd.DataFrame, reconstructed: pd.DataFrame) -> dict[str, Any]:
    result = {}
    for name in FEATURE_COLUMNS:
        ref_threshold = float(reference[name].quantile(0.95))
        est_threshold = float(reconstructed[name].quantile(0.95))
        ref_hours = pd.DatetimeIndex(reference.loc[reference[name] >= ref_threshold, "timestamp_aest"]).hour
        est_hours = pd.DatetimeIndex(reconstructed.loc[reconstructed[name] >= est_threshold, "timestamp_aest"]).hour
        ref_hist = np.bincount(ref_hours, minlength=24).astype(float)
        est_hist = np.bincount(est_hours, minlength=24).astype(float)
        ref_hist /= max(ref_hist.sum(), 1.0)
        est_hist /= max(est_hist.sum(), 1.0)
        result[name] = {
            "hour_order": list(range(24)),
            "reference_top5pct_hour_distribution": ref_hist.tolist(),
            "representative_top5pct_hour_distribution": est_hist.tolist(),
            "total_variation_distance": float(0.5 * np.abs(ref_hist - est_hist).sum()),
        }
    return result


def _composite_score(audit: dict[str, Any], scales: dict[str, float]) -> float:
    mean_terms = [
        audit["annual_mean_energy_error"][name]["mean_absolute_error"] / scales[name]
        for name in FEATURE_COLUMNS
    ]
    quantile_terms = [
        audit["quantile_error"][name][key]["absolute_error"] / scales[name]
        for name in FEATURE_COLUMNS for key in ("p05", "p50", "p95", "p99")
    ]
    ramp_terms = [
        audit["ramp_p95_error"][name][key]["absolute_error"] / scales[name]
        for name in FEATURE_COLUMNS for key in ("5min", "15min", "60min")
    ]
    peak_terms = [audit["peak_time_distribution"][name]["total_variation_distance"] for name in FEATURE_COLUMNS]
    components = {
        "mean_normalized_mae": float(np.mean(mean_terms)),
        "quantile_normalized_mae": float(np.mean(quantile_terms)),
        "ramp_normalized_mae": float(np.mean(ramp_terms)),
        "correlation_mae": float(audit["correlation_matrix_error"]["mean_absolute_error"]),
        "peak_time_tv_mean": float(np.mean(peak_terms)),
    }
    audit["score_components"] = components
    return float(np.mean(list(components.values())))


def build_representativeness_audit(
    features: pd.DataFrame,
    candidates: pd.DataFrame,
    selection: pd.DataFrame,
    scales: dict[str, float],
) -> dict[str, Any]:
    validate_feature_table(features)
    blocks = _reconstructed_blocks(features, selection)
    reconstructed = _repeat_blocks(blocks)
    seasons = np.array([southern_season(x.month) for x in pd.DatetimeIndex(features["timestamp_aest"])])
    seasonal = {}
    for season in ("summer", "autumn", "winter", "spring"):
        reference = features.loc[seasons == season]
        selected_season = _repeat_blocks(_reconstructed_blocks(features, selection, season))
        seasonal[season] = {
            "reference_steps": len(reference),
            "representative_repeated_steps": len(selected_season),
            "mean_energy_error": _mean_energy_errors(reference, selected_season),
        }
    audit: dict[str, Any] = {
        "schema_version": "representativeness_audit_v1",
        "status": "PROVISIONAL",
        "k": int(selection["k"].iloc[0]),
        "reference_axis_steps": len(features),
        "candidate_week_count": len(candidates),
        "representative_repeated_steps": len(reconstructed),
        "annual_mean_energy_error": _mean_energy_errors(features, reconstructed),
        "seasonal_mean_energy_error": seasonal,
        "quantile_error": _quantile_errors(features, reconstructed),
        "ramp_p95_error": _ramp_errors(features, blocks),
        "weekday_weekend_coverage": _daytype_coverage(features, reconstructed),
        "peak_time_distribution": _peak_time_distribution(features, reconstructed),
        "correlation_matrix_error": _correlation_error(features, reconstructed),
        "clusters": json.loads(selection.to_json(orient="records")),
        "annual_weight_sum": float(selection["cluster_weight"].sum()),
        "boundary_note": f"Full observed Monday weeks with 48-hour burn-in exclude incomplete year-boundary weeks; audit reference remains all {len(features)} steps.",
    }
    audit["composite_score"] = _composite_score(audit, scales)
    return audit
