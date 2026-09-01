"""Pure contracts for the prospective V16.3 correction study.

The module contains no optimizer or OpenDSS call.  The tolerances below are
declared before the corrected current sensitivities are generated or read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from .v16_3_nonzero_validity import RHO_GRID


CURRENT_LIMIT_PU = 1.0
CURRENT_CLASS_TOLERANCE_PU = 1e-9
CURRENT_ERROR_TOLERANCE = {
    "max_abs_normalized_current_error_pu": 0.030,
    "mean_abs_normalized_current_error_pu": 0.010,
    "p95_abs_normalized_current_error_pu": 0.020,
}
FALSE_INFEASIBLE_SEVERE_RATE = 1e-3


def current_comparison(
    predicted: Sequence[float],
    actual: Sequence[float],
    identities: Sequence[str],
) -> dict[str, object]:
    """Compare matched phase-current loadings without clipping."""

    pred = np.asarray(predicted, dtype=float)
    ac = np.asarray(actual, dtype=float)
    if pred.ndim != 1 or pred.shape != ac.shape or len(identities) != pred.size:
        raise ValueError("V163_CORR_CURRENT_AXIS_MISMATCH")
    if pred.size == 0 or not np.isfinite(pred).all() or not np.isfinite(ac).all():
        raise ValueError("V163_CORR_CURRENT_NONFINITE_OR_EMPTY")
    error = np.abs(pred - ac)
    pred_feasible = pred <= CURRENT_LIMIT_PU + CURRENT_CLASS_TOLERANCE_PU
    ac_feasible = ac <= CURRENT_LIMIT_PU + CURRENT_CLASS_TOLERANCE_PU
    worst = int(np.argmax(error))
    return {
        "sample_count": int(pred.size),
        "max_abs_normalized_current_error_pu": float(error.max()),
        "mean_abs_normalized_current_error_pu": float(error.mean()),
        "p95_abs_normalized_current_error_pu": float(np.quantile(error, 0.95)),
        "false_current_feasible_count": int(np.sum(pred_feasible & ~ac_feasible)),
        "false_current_infeasible_count": int(np.sum(~pred_feasible & ac_feasible)),
        "worst_element_phase": str(identities[worst]),
        "worst_predicted_loading_pu": float(pred[worst]),
        "worst_actual_loading_pu": float(ac[worst]),
    }


def current_metrics_pass(metrics: Mapping[str, float | int]) -> bool:
    return (
        int(metrics["false_current_feasible_count"]) == 0
        and float(metrics["max_abs_normalized_current_error_pu"])
        <= CURRENT_ERROR_TOLERANCE["max_abs_normalized_current_error_pu"] + 1e-12
        and float(metrics["mean_abs_normalized_current_error_pu"])
        <= CURRENT_ERROR_TOLERANCE["mean_abs_normalized_current_error_pu"] + 1e-12
        and float(metrics["p95_abs_normalized_current_error_pu"])
        <= CURRENT_ERROR_TOLERANCE["p95_abs_normalized_current_error_pu"] + 1e-12
    )


def cumulative_valid_radius(rows: Sequence[Mapping[str, object]]) -> float | None:
    """Largest predeclared rho whose inner primary rows all pass."""

    accepted: float | None = None
    for rho in RHO_GRID:
        inner = [row for row in rows if float(row["rho"]) <= rho + 1e-12]
        if not inner or not all(bool(row["primary_pass"]) for row in inner):
            break
        accepted = float(rho)
    return accepted

