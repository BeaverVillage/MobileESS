"""Pre-development non-causal oracle ceiling for committed workload state."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dayahead.ml.safe_flex.capacity_timeline import capacity_for_day


ORACLE_CASES = {
    "O0": "LEGACY_INNOVATION_ONLY",
    "O1": "ORACLE_PRE_CUTOFF_PENDING_SERVICE",
    "O2": "ORACLE_PRE_CUTOFF_ALL_FUTURE_SERVICE",
    "O3": "ORACLE_INNOVATION",
    "O4": "FULL_ORACLE",
}


def aggregate_service_descriptor(
    q50_GPU_h: float,
    q90_GPU_h: float,
    capacity_GPU: int,
    slots: int = 96,
) -> dict[str, object]:
    """Project aggregate daily mass to a frozen cumulative service descriptor.

    Units are GPU-hours. The gate diagnostic uses uniform release over 96
    15-minute slots and an eight-slot deadline shift. This is an engineering
    proxy, not the final class-resolved SAFE service set. Work exceeding the
    daily capacity is explicitly marked rather than clipped.
    """

    time_fraction = np.arange(1, slots + 1, dtype=float) / slots
    upper_q50 = max(float(q50_GPU_h), 0.0) * time_fraction
    upper_q90 = max(float(q90_GPU_h), 0.0) * time_fraction
    lower_q50 = np.concatenate((np.zeros(8), upper_q50[:-8]))
    lower_q90 = np.concatenate((np.zeros(8), upper_q90[:-8]))
    daily_capacity = float(capacity_GPU) * 24.0
    feasible = max(float(q90_GPU_h), 0.0) <= daily_capacity + 1e-9
    return {
        "L_Q50_terminal_GPU_h": float(lower_q50[-1]),
        "U_Q50_terminal_GPU_h": float(upper_q50[-1]),
        "L_Q90_terminal_GPU_h": float(lower_q90[-1]),
        "U_Q90_terminal_GPU_h": float(upper_q90[-1]),
        "safe_envelope_width_GPU_h": float(np.trapz(upper_q90 - lower_q90) / slots),
        "feasible_set_volume_proxy_GPU_h2": float(np.trapz(upper_q90) * max(float(q90_GPU_h), 0.0) / slots),
        "projector_status": "FEASIBLE" if feasible else "CAPACITY_INFEASIBLE",
        "hidden_shedding_GPU_h": 0.0,
        "terminal_backlog_GPU_h": float(max(q90_GPU_h, 0.0) - lower_q90[-1]),
    }


def evaluate_oracle_cases(
    shares: pd.DataFrame,
    canonical_oof: pd.DataFrame,
    capacity_timeline: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate O0--O4 on identical pre-April OOF days.

    B2 mean and raw B3 Q50/Q90 are historical OOF authorities. Oracle values
    are post-hoc labels only and cannot enter any deployable forecast feature.
    """

    b2 = canonical_oof.loc[
        canonical_oof["model"].eq("C-B0_B2_LIGHTGBM_TWEEDIE"),
        ["date", "mean_GPU_h"],
    ]
    b3 = canonical_oof.loc[
        canonical_oof["model"].eq("C-B1_B3_LIGHTGBM_QUANTILE"),
        ["date", "Q50_GPU_h", "Q90_GPU_h"],
    ]
    merged = shares.merge(b2, left_on="target_day", right_on="date", validate="one_to_one")
    merged = merged.merge(b3, on="date", validate="one_to_one")
    rows: list[dict[str, object]] = []
    for record in merged.to_dict(orient="records"):
        y = float(record["H_total_GPU_h"])
        case_values = {
            "O0": (float(record["mean_GPU_h"]), float(record["Q50_GPU_h"]), float(record["Q90_GPU_h"])),
            "O1": tuple(float(value) + float(record["H_K_pending_GPU_h"]) for value in (record["mean_GPU_h"], record["Q50_GPU_h"], record["Q90_GPU_h"])),
            "O2": tuple(float(value) + float(record["H_K_total_GPU_h"]) for value in (record["mean_GPU_h"], record["Q50_GPU_h"], record["Q90_GPU_h"])),
            "O3": (float(record["H_G_GPU_h"] + record["H_N_GPU_h"]),) * 3,
            "O4": (y, y, y),
        }
        capacity = capacity_for_day(capacity_timeline, record["date"])
        for case_id, (mean, q50, q90) in case_values.items():
            descriptor = aggregate_service_descriptor(q50, q90, capacity)
            q50_pinball = 2.0 * max(0.5 * (y - q50), -0.5 * (y - q50))
            q90_pinball = 2.0 * max(0.9 * (y - q90), -0.1 * (y - q90))
            rows.append(
                {
                    "date": record["date"],
                    "case_id": case_id,
                    "case": ORACLE_CASES[case_id],
                    "reference_GPU_h": y,
                    "predicted_mean_GPU_h": mean,
                    "predicted_Q50_GPU_h": q50,
                    "predicted_Q90_GPU_h": q90,
                    "boundary_abs_error_GPU_h": abs(q50 - y),
                    "WIS_CRPS_proxy_GPU_h": 0.5 * (q50_pinball + q90_pinball),
                    "simultaneous_aggregate_coverage": bool(0.0 <= y <= q90),
                    "reserve_shortfall_GPU_h": max(q50 - y, 0.0),
                    "capacity_GPU": capacity,
                    **descriptor,
                }
            )
    return pd.DataFrame(rows)


def summarize_oracle(results: pd.DataFrame) -> list[dict[str, object]]:
    """Summarize case-level oracle metrics and O1 relative improvements."""

    rows = []
    reference_total = float(results.loc[results.case_id.eq("O0"), "reference_GPU_h"].sum())
    for case_id, group in results.groupby("case_id", sort=True):
        rows.append(
            {
                "case_id": case_id,
                "case": str(group["case"].iloc[0]),
                "days": int(len(group)),
                "boundary_MAE_GPU_h": float(group.boundary_abs_error_GPU_h.mean()),
                "primary_normalized_envelope_score": float(group.boundary_abs_error_GPU_h.sum() / reference_total),
                "WIS_CRPS_proxy_GPU_h": float(group.WIS_CRPS_proxy_GPU_h.mean()),
                "simultaneous_aggregate_coverage": float(group.simultaneous_aggregate_coverage.mean()),
                "reserve_shortfall_GPU_h": float(group.reserve_shortfall_GPU_h.sum()),
                "mean_safe_envelope_width_GPU_h": float(group.safe_envelope_width_GPU_h.mean()),
                "mean_feasible_set_volume_proxy_GPU_h2": float(group.feasible_set_volume_proxy_GPU_h2.mean()),
                "projector_feasible_rate": float(group.projector_status.eq("FEASIBLE").mean()),
                "hidden_shedding_GPU_h": float(group.hidden_shedding_GPU_h.sum()),
            }
        )
    return rows

