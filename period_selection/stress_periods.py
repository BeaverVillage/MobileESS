"""Exogenous-only, non-overlapping 48-hour stress-period selection."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from period_selection import BURN_IN_STEPS
from period_selection.feature_builder import validate_feature_table


def _z(values: np.ndarray) -> np.ndarray:
    median = np.median(values)
    scale = np.quantile(values, 0.95) - np.quantile(values, 0.05)
    if scale <= 0:
        scale = np.quantile(values, 0.99) - np.quantile(values, 0.01)
    if scale <= 0:
        scale = np.max(values) - np.min(values)
    if scale <= 0:
        scale = 1.0
    return (values - median) / scale


def select_stress_periods(features: pd.DataFrame) -> pd.DataFrame:
    validate_feature_table(features)
    ts = pd.DatetimeIndex(features["timestamp_aest"])
    categories = (
        "maximum_regional_demand_stress",
        "price_or_regional_demand_ramp_stress",
        "traffic_mobility_stress",
        "workload_wan_compound_stress",
    )
    annual_demand = features["regional_total_demand_mw"].to_numpy(dtype=float)
    annual_price = features["vic1_rrp_aud_per_mwh"].to_numpy(dtype=float)
    demand_ramp_scale = max(float(np.quantile(np.abs(np.diff(annual_demand)), 0.95)), 1e-12)
    price_ramp_scale = max(float(np.quantile(np.abs(np.diff(annual_price)), 0.95)), 1e-12)
    workload_global = (
        _z(features["job_arrival_count"].to_numpy(dtype=float))
        + _z(features["arriving_gpu"].to_numpy(dtype=float))
        + _z(features["arriving_wan_nominal_gb"].to_numpy(dtype=float))
    )
    starts = range(0, len(features) - BURN_IN_STEPS + 1, BURN_IN_STEPS)
    scored: dict[str, list[tuple[float, int]]] = {name: [] for name in categories}
    for start in starts:
        stop = start + BURN_IN_STEPS
        block = features.iloc[start:stop]
        demand = block["regional_total_demand_mw"].to_numpy(dtype=float)
        price = block["vic1_rrp_aud_per_mwh"].to_numpy(dtype=float)
        traffic = block["traffic_p95_tti"].to_numpy(dtype=float)
        workload = workload_global[start:stop]
        scored[categories[0]].append((float(np.max(demand)), start))
        ramp = max(
            float(np.max(np.abs(np.diff(demand))) / demand_ramp_scale),
            float(np.max(np.abs(np.diff(price))) / price_ramp_scale),
        )
        scored[categories[1]].append((ramp, start))
        scored[categories[2]].append((float(np.mean(traffic)), start))
        scored[categories[3]].append((float(np.max(workload)), start))
    selected_intervals: list[tuple[int, int]] = []
    rows = []
    for category in categories:
        ranked = sorted(scored[category], key=lambda item: (-item[0], item[1]))
        choice = next(
            (item for item in ranked if all(item[1] + BURN_IN_STEPS <= a or item[1] >= b for a, b in selected_intervals)),
            None,
        )
        if choice is None:
            raise ValueError(f"no non-overlapping 48-hour candidate for {category}")
        score, start = choice
        stop = start + BURN_IN_STEPS
        selected_intervals.append((start, stop))
        rows.append({
            "stress_category": category,
            "start_aest": ts[start].isoformat(),
            "end_exclusive_aest": (ts[stop - 1] + timedelta(minutes=5)).isoformat(),
            "start_index": start,
            "end_index_exclusive": stop,
            "steps": BURN_IN_STEPS,
            "score": score,
            "annual_weight": 0.0,
            "selection_inputs": {
                categories[0]: "regional_total_demand_mw (regional pattern only)",
                categories[1]: "annual-p95-normalized absolute 5-minute regional-demand or RRP ramp",
                categories[2]: "traffic_p95_tti",
                categories[3]: "annual-robust-normalized Job count + arriving GPU + Job-derived nominal WAN GB",
            }[category],
        })
    return pd.DataFrame(rows)
