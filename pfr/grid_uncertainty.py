"""Causal grid quantile-envelope authority for PFR3."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class GridUncertaintyError(ValueError):
    pass


@dataclass(frozen=True)
class GridEnvelopeAudit:
    issue_count: int
    horizon_steps: int
    target_count: int
    quantile_crossings: int
    nonfinite_values: int
    maximum_demand_q90_q10_width_mw: float
    maximum_pv_q90_q10_width_mw: float
    maximum_price_q90_q10_width_aud_per_mwh: float


def audit_grid_quantile_envelope(
    issue_step: np.ndarray,
    q10: np.ndarray,
    q50: np.ndarray,
    q90: np.ndarray,
    target_names: tuple[str, ...],
) -> GridEnvelopeAudit:
    expected_targets = ("demand_mw", "rooftop_pv_mw", "rrp_aud_per_mwh")
    if target_names != expected_targets:
        raise GridUncertaintyError("grid forecast target axis changed")
    if q10.shape != q50.shape or q50.shape != q90.shape or q10.ndim != 3:
        raise GridUncertaintyError("grid quantile tensor shapes differ")
    if q10.shape[0] != len(issue_step) or q10.shape[1:] != (54, 3):
        raise GridUncertaintyError("grid issue/horizon/target axis changed")
    if not np.array_equal(issue_step, np.arange(len(issue_step), dtype=issue_step.dtype)):
        raise GridUncertaintyError("grid issue axis is not contiguous from zero")
    nonfinite = int(sum(np.count_nonzero(~np.isfinite(array)) for array in (q10, q50, q90)))
    crossings = int(np.count_nonzero(q10 > q50) + np.count_nonzero(q50 > q90))
    if nonfinite or crossings:
        raise GridUncertaintyError("grid quantile envelope is invalid")
    width = q90 - q10
    return GridEnvelopeAudit(
        issue_count=len(issue_step),
        horizon_steps=54,
        target_count=3,
        quantile_crossings=0,
        nonfinite_values=0,
        maximum_demand_q90_q10_width_mw=float(np.max(width[:, :, 0])),
        maximum_pv_q90_q10_width_mw=float(np.max(width[:, :, 1])),
        maximum_price_q90_q10_width_aud_per_mwh=float(np.max(width[:, :, 2])),
    )
