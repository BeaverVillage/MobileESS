"""Exhaustively audit whether the frozen seasonal mean threshold is reachable."""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import pandas as pd

from period_selection.candidate_weeks import SEASON_ORDER, southern_season
from period_selection.constrained_kmedoids import DistanceContext
from period_selection.feature_builder import FEATURE_COLUMNS


def build_threshold_feasibility_audit(
    features: pd.DataFrame,
    candidates: pd.DataFrame,
    context: DistanceContext,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Enumerate every season-quota medoid combination for K=4/8/12.

    This is a diagnostic only: it does not change the selector or thresholds.
    Candidate weeks are assigned to their nearest candidate medoid using the
    frozen distance matrix, exactly as in the production selector.
    """
    weekly_means = np.asarray([
        features.iloc[int(row.start_index): int(row.end_index_exclusive)][FEATURE_COLUMNS]
        .mean().to_numpy(dtype=float)
        for row in candidates.itertuples(index=False)
    ])
    feature_seasons = np.asarray([
        southern_season(stamp.month) for stamp in pd.DatetimeIndex(features["timestamp_aest"])
    ])
    threshold = float(config["selection_constraints"]["seasonal_mean_relative_error_max"])
    by_k: dict[str, Any] = {}
    for k in (4, 8, 12):
        season_results: dict[str, Any] = {}
        quota_map = config["seasonal_quotas"][str(k)]
        for season in SEASON_ORDER:
            member_indices = np.flatnonzero(candidates["season"].to_numpy() == season)
            reference = features.loc[feature_seasons == season, FEATURE_COLUMNS].mean().to_numpy(dtype=float)
            best_score = float("inf")
            best: dict[str, Any] | None = None
            for combo in itertools.combinations(member_indices.tolist(), int(quota_map[season])):
                combo_array = np.asarray(combo, dtype=int)
                nearest = combo_array[
                    np.argmin(context.distances[np.ix_(member_indices, combo_array)], axis=1)
                ]
                cluster_sizes = np.asarray([(nearest == medoid).sum() for medoid in combo_array])
                estimate = np.average(weekly_means[combo_array], axis=0, weights=cluster_sizes)
                errors = np.abs(estimate - reference) / np.maximum(np.abs(reference), 1e-12)
                score = float(errors.max())
                if score < best_score - 1e-12:
                    worst = int(np.argmax(errors))
                    best_score = score
                    best = {
                        "best_possible_max_relative_error": score,
                        "worst_feature": FEATURE_COLUMNS[worst],
                        "best_medoid_ids": [str(candidates.iloc[index]["candidate_id"]) for index in combo],
                        "cluster_sizes": cluster_sizes.astype(int).tolist(),
                        "feature_relative_errors": {
                            name: float(errors[index]) for index, name in enumerate(FEATURE_COLUMNS)
                        },
                    }
            assert best is not None
            best["threshold"] = threshold
            best["threshold_reachable"] = best_score <= threshold
            season_results[season] = best
        by_k[str(k)] = {
            "seasons": season_results,
            "all_seasons_threshold_reachable": all(
                item["threshold_reachable"] for item in season_results.values()
            ),
        }
    return {
        "schema_version": "rep_period_threshold_feasibility_v1",
        "scope": "exhaustive seasonal-quota medoid combinations with frozen nearest-medoid assignment",
        "changes_selection_or_thresholds": False,
        "criterion": "seasonal_mean_relative_error_max",
        "threshold": threshold,
        "by_k": by_k,
        "any_candidate_k_reachable": any(
            result["all_seasons_threshold_reachable"] for result in by_k.values()
        ),
        "conclusion": (
            "AT_LEAST_ONE_K_CAN_REACH_THE_FROZEN_SEASONAL_MEAN_CRITERION"
            if any(result["all_seasons_threshold_reachable"] for result in by_k.values())
            else "NO_K_IN_4_8_12_CAN_REACH_THE_FROZEN_SEASONAL_MEAN_CRITERION"
        ),
    }
