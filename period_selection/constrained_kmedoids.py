"""Deterministic exact constrained k-medoids over actual observed weeks."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from period_selection.candidate_weeks import SEASON_ORDER, southern_season
from period_selection.feature_builder import FEATURE_COLUMNS, validate_feature_table


@dataclass(frozen=True)
class DistanceContext:
    candidate_ids: tuple[str, ...]
    distances: np.ndarray
    centers: dict[str, float]
    scales: dict[str, float]
    scale_methods: dict[str, str]
    weights: dict[str, float]
    distance_component_weights: dict[str, float]
    weekly_summary_centers: dict[str, float]
    weekly_summary_scales: dict[str, float]


def build_distance_context(
    features: pd.DataFrame,
    candidates: pd.DataFrame,
    config: dict[str, Any],
    locked_2024_context: DistanceContext | None = None,
) -> tuple[pd.DataFrame, DistanceContext]:
    validate_feature_table(features)
    ordered = candidates.sort_values(["week_start_aest", "candidate_id"], kind="stable").reset_index(drop=True)
    feature_weights = (
        dict(locked_2024_context.weights) if locked_2024_context is not None
        else {name: float(config["feature_weights"][name]) for name in FEATURE_COLUMNS}
    )
    minimum = float(config["normalization"]["minimum_scale"])
    centers: dict[str, float] = {}
    scales: dict[str, float] = {}
    scale_methods: dict[str, str] = {}
    annual = features[FEATURE_COLUMNS]
    if locked_2024_context is not None:
        centers = dict(locked_2024_context.centers)
        scales = dict(locked_2024_context.scales)
        scale_methods = {name: "locked_from_2024" for name in FEATURE_COLUMNS}
    else:
        for name in FEATURE_COLUMNS:
            values = annual[name].to_numpy(dtype=float)
            centers[name] = float(np.median(values))
            scale = float(np.quantile(values, 0.75) - np.quantile(values, 0.25))
            method = "iqr_q75_minus_q25"
            if scale <= minimum:
                scale = float(np.quantile(values, 0.95) - np.quantile(values, 0.05))
                method = "sparse_fallback_q95_minus_q05"
            if scale <= minimum:
                scale = float(np.max(values) - np.min(values))
                method = "sparse_fallback_max_minus_min"
            if scale <= minimum:
                scale = 1.0
                method = "constant_feature_unit_scale"
            scales[name] = scale
            scale_methods[name] = method
    vectors = []
    summaries = []
    summary_names = []
    for row in ordered.to_dict("records"):
        block = features.iloc[int(row["start_index"]): int(row["end_index_exclusive"])][FEATURE_COLUMNS]
        normalized = np.empty(block.shape, dtype=np.float64)
        for index, name in enumerate(FEATURE_COLUMNS):
            normalized[:, index] = (
                (block[name].to_numpy(dtype=float) - centers[name]) / scales[name]
                * np.sqrt(feature_weights[name])
            )
        vectors.append(normalized.ravel())
        summary = []
        names = []
        for index, name in enumerate(FEATURE_COLUMNS):
            values = normalized[:, index]
            metrics = {
                "mean": float(np.mean(values)),
                "p95": float(np.quantile(values, 0.95)),
                "p99": float(np.quantile(values, 0.99)),
                "ramp5_p95": float(np.quantile(np.abs(np.diff(values, n=1)), 0.95)),
                "ramp15_p95": float(np.quantile(np.abs(values[3:] - values[:-3]), 0.95)),
                "ramp60_p95": float(np.quantile(np.abs(values[12:] - values[:-12]), 0.95)),
            }
            for metric, value in metrics.items():
                names.append(f"{name}:{metric}")
                summary.append(value)
        summaries.append(summary)
        summary_names = names
    matrix = np.asarray(vectors, dtype=np.float64)
    squared_norm = np.einsum("ij,ij->i", matrix, matrix)
    distance_sq = squared_norm[:, None] + squared_norm[None, :] - 2.0 * matrix.dot(matrix.T)
    np.maximum(distance_sq, 0.0, out=distance_sq)
    profile_distance_sq = distance_sq / matrix.shape[1]
    summary_matrix = np.asarray(summaries, dtype=np.float64)
    summary_centers: dict[str, float] = {}
    summary_scales: dict[str, float] = {}
    for index, name in enumerate(summary_names):
        values = summary_matrix[:, index]
        if locked_2024_context is not None:
            center = float(locked_2024_context.weekly_summary_centers[name])
            scale = float(locked_2024_context.weekly_summary_scales[name])
        else:
            center = float(np.median(values))
            scale = float(np.quantile(values, 0.75) - np.quantile(values, 0.25))
            if scale <= minimum:
                scale = float(np.quantile(values, 0.95) - np.quantile(values, 0.05))
            if scale <= minimum:
                scale = float(np.max(values) - np.min(values))
            if scale <= minimum:
                scale = 1.0
        summary_centers[name] = center
        summary_scales[name] = scale
        summary_matrix[:, index] = (values - center) / scale
    summary_norm = np.einsum("ij,ij->i", summary_matrix, summary_matrix)
    summary_distance_sq = summary_norm[:, None] + summary_norm[None, :] - 2.0 * summary_matrix.dot(summary_matrix.T)
    np.maximum(summary_distance_sq, 0.0, out=summary_distance_sq)
    summary_distance_sq /= summary_matrix.shape[1]
    component_weights = (
        dict(locked_2024_context.distance_component_weights)
        if locked_2024_context is not None
        else {key: float(value) for key, value in config["distance_components"].items()}
    )
    distances = np.sqrt(
        component_weights["time_aligned_profile_rmse"] * profile_distance_sq
        + component_weights["weekly_distribution_summary_rmse"] * summary_distance_sq
    )
    np.fill_diagonal(distances, 0.0)
    context = DistanceContext(
        candidate_ids=tuple(ordered["candidate_id"].astype(str)),
        distances=distances,
        centers=centers,
        scales=scales,
        scale_methods=scale_methods,
        weights=feature_weights,
        distance_component_weights=component_weights,
        weekly_summary_centers=summary_centers,
        weekly_summary_scales=summary_scales,
    )
    return ordered, context


def _best_medoids_for_season(
    indices: tuple[int, ...],
    quota: int,
    distances: np.ndarray,
    weekly_means: np.ndarray | None = None,
    reference_mean: np.ndarray | None = None,
    maximum_relative_error: float | None = None,
) -> tuple[int, ...]:
    if quota <= 0 or quota > len(indices):
        raise ValueError(f"invalid quota {quota} for {len(indices)} candidates")
    best_combo: tuple[int, ...] | None = None
    best_cost = float("inf")
    for combo in itertools.combinations(indices, quota):
        if maximum_relative_error is not None:
            if weekly_means is None or reference_mean is None:
                raise ValueError("mean-preservation constraint requires weekly and reference means")
            combo_array = np.asarray(combo, dtype=int)
            winners = combo_array[
                np.argmin(distances[np.ix_(indices, combo_array)], axis=1)
            ]
            cluster_sizes = np.asarray([(winners == medoid).sum() for medoid in combo_array])
            estimate = np.average(weekly_means[combo_array], axis=0, weights=cluster_sizes)
            relative_errors = np.abs(estimate - reference_mean) / np.maximum(
                np.abs(reference_mean), 1e-12
            )
            if float(relative_errors.max()) > maximum_relative_error + 1e-12:
                continue
        cost = float(np.min(distances[np.ix_(indices, combo)], axis=1).sum())
        if cost < best_cost - 1e-12 or (
            abs(cost - best_cost) <= 1e-12 and (best_combo is None or combo < best_combo)
        ):
            best_cost = cost
            best_combo = combo
    if best_combo is None:
        raise ValueError(
            f"no quota-{quota} medoid combination satisfies seasonal mean relative error "
            f"<= {maximum_relative_error}"
        )
    return best_combo


def select_representative_weeks(
    candidates: pd.DataFrame,
    context: DistanceContext,
    k: int,
    config: dict[str, Any],
    features: pd.DataFrame | None = None,
    enforce_mean_constraint: bool = False,
) -> pd.DataFrame:
    if len(candidates) != len(context.candidate_ids):
        raise ValueError("candidate/context length mismatch")
    if tuple(candidates["candidate_id"].astype(str)) != context.candidate_ids:
        raise ValueError("candidates must use the canonical sorted context order")
    quota_map = {key: int(value) for key, value in config["seasonal_quotas"][str(k)].items()}
    if sum(quota_map.values()) != k:
        raise ValueError(f"seasonal quota sum does not equal K={k}")
    selected: list[int] = []
    assignments: dict[int, list[int]] = {}
    weekly_means: np.ndarray | None = None
    reference_by_season: dict[str, np.ndarray] = {}
    maximum_relative_error: float | None = None
    if enforce_mean_constraint:
        if features is None:
            raise ValueError("features are required for the mean-preserving selector")
        validate_feature_table(features)
        weekly_means = np.asarray([
            features.iloc[int(row.start_index): int(row.end_index_exclusive)][FEATURE_COLUMNS]
            .mean().to_numpy(dtype=float)
            for row in candidates.itertuples(index=False)
        ])
        feature_seasons = np.asarray([
            southern_season(stamp.month)
            for stamp in pd.DatetimeIndex(features["timestamp_aest"])
        ])
        reference_by_season = {
            season: features.loc[feature_seasons == season, FEATURE_COLUMNS].mean().to_numpy(dtype=float)
            for season in SEASON_ORDER
        }
        maximum_relative_error = float(
            config["selection_constraints"]["seasonal_mean_relative_error_max"]
        )
    for season in SEASON_ORDER:
        members = tuple(int(x) for x in candidates.index[candidates["season"] == season])
        medoids = _best_medoids_for_season(
            members,
            quota_map[season],
            context.distances,
            weekly_means,
            reference_by_season.get(season),
            maximum_relative_error,
        )
        selected.extend(medoids)
        for member in members:
            # medoids are time-sorted, so argmin is the stable timestamp tie-breaker.
            winner = medoids[int(np.argmin(context.distances[member, list(medoids)]))]
            assignments.setdefault(winner, []).append(member)
    rows = []
    total = len(candidates)
    for rank, medoid in enumerate(sorted(selected), start=1):
        source = candidates.iloc[medoid].to_dict()
        member_indices = sorted(assignments[medoid])
        member_ids = [str(candidates.iloc[i]["candidate_id"]) for i in member_indices]
        rows.append({
            "k": k,
            "medoid_rank": rank,
            "candidate_id": source["candidate_id"],
            "season": source["season"],
            "week_start_aest": source["week_start_aest"],
            "week_end_exclusive_aest": source["week_end_exclusive_aest"],
            "burn_in_start_aest": source["burn_in_start_aest"],
            "burn_in_end_exclusive_aest": source["burn_in_end_exclusive_aest"],
            "start_index": int(source["start_index"]),
            "end_index_exclusive": int(source["end_index_exclusive"]),
            "burn_in_start_index": int(source["burn_in_start_index"]),
            "cluster_size_weeks": len(member_ids),
            "cluster_weight": len(member_ids) / total,
            "cluster_member_ids_json": json.dumps(member_ids, separators=(",", ":")),
            "cluster_mean_distance": float(np.mean(context.distances[member_indices, medoid])),
            "cluster_max_distance": float(np.max(context.distances[member_indices, medoid])),
        })
    result = pd.DataFrame(rows)
    counts = result.groupby("season").size().to_dict()
    if counts != quota_map:
        raise AssertionError(f"season quota failure: {counts} != {quota_map}")
    if not np.isclose(result["cluster_weight"].sum(), 1.0):
        raise AssertionError("cluster weights do not sum to one")
    return result


def normalization_manifest(context: DistanceContext) -> dict[str, Any]:
    return {
        "method": "2024 annual median center; IQR scale with q95-q05 and range fallback for sparse features",
        "centers": context.centers,
        "scales": context.scales,
        "scale_methods_by_feature": context.scale_methods,
        "weights": context.weights,
        "distance_component_weights": context.distance_component_weights,
        "weekly_summary_centers": context.weekly_summary_centers,
        "weekly_summary_scales": context.weekly_summary_scales,
        "weekly_summary_metrics": ["mean", "p95", "p99", "5/15/60-minute ramp p95"],
        "distance": "weighted combination of time-aligned profile RMSE and weekly distribution-summary RMSE",
        "tie_breaker": "earliest week_start_aest",
        "algorithm": "exact seasonal quota-constrained k-medoids enumeration",
    }
