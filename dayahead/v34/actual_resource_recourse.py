"""Actual AIDC resource-only spatial recourse.

This decision module intentionally imports no planning-grid, Fresh/OpenDSS,
voltage, current, transformer, or rho authority.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from .contracts import ACTUAL_AIDC_FIREWALL_FIELDS


TOL = 1e-9


@dataclass(frozen=True)
class ResourceRecourseResult:
    executed_nodeh: np.ndarray
    backlog_nodeh: np.ndarray
    recourse_nodeh: float
    solver_calls: int
    read_ledger: tuple[dict[str, int | str], ...]
    firewall: dict[str, int]

    @property
    def executed_total_nodeh(self) -> float:
        return float(self.executed_nodeh.sum())


def _solve_slot(
    authorized: np.ndarray,
    available: np.ndarray,
    capacity: np.ndarray,
    compatibility: np.ndarray,
) -> tuple[np.ndarray, int]:
    cohorts, racks = authorized.shape
    n = cohorts * racks
    bounds = [
        (0.0, None if compatibility[c, r] else 0.0)
        for c in range(cohorts) for r in range(racks)
    ]
    aub, bub = [], []
    for c in range(cohorts):
        row = np.zeros(n); row[c * racks:(c + 1) * racks] = 1.0
        aub.append(row); bub.append(float(min(available[c], authorized[c].sum())))
    for r in range(racks):
        row = np.zeros(n); row[r::racks] = 1.0
        aub.append(row); bub.append(float(capacity[r]))
    primary = linprog(
        -np.ones(n), A_ub=np.asarray(aub), b_ub=np.asarray(bub), bounds=bounds,
        method="highs",
    )
    if not primary.success:
        raise RuntimeError(f"V34_RESOURCE_RECOURSE_PRIMARY:{primary.message}")
    service = float(np.asarray(primary.x).sum())

    # The second objective minimizes deviation from the authorized DA rack
    # placement.  Rewarding overlap is exactly equivalent while service is fixed.
    overlap_capacity = authorized.ravel()
    c = np.where(overlap_capacity > TOL, -1.0, 0.0)
    aeq = np.ones((1, n))
    secondary = linprog(
        c, A_ub=np.asarray(aub), b_ub=np.asarray(bub),
        A_eq=aeq, b_eq=np.asarray([service]), bounds=bounds, method="highs",
    )
    if not secondary.success:
        raise RuntimeError(f"V34_RESOURCE_RECOURSE_SECONDARY:{secondary.message}")
    return np.asarray(secondary.x).reshape(cohorts, racks), 2


def solve_resource_only_recourse(
    da_authorization_nodeh: np.ndarray,
    actual_workload_arrivals_nodeh: np.ndarray,
    actual_rack_capacity_nodeh: np.ndarray,
    compatibility: np.ndarray,
    *,
    initial_backlog_nodeh: np.ndarray | None = None,
) -> ResourceRecourseResult:
    da = np.asarray(da_authorization_nodeh, dtype=float)
    arrivals = np.asarray(actual_workload_arrivals_nodeh, dtype=float)
    capacity = np.asarray(actual_rack_capacity_nodeh, dtype=float)
    compatible = np.asarray(compatibility, dtype=bool)
    if da.ndim != 3:
        raise ValueError("V34_DA_AUTHORIZATION_AXIS")
    cohorts, racks, slots = da.shape
    if slots != 96 or arrivals.shape != (96, cohorts) or capacity.shape != (96, racks):
        raise ValueError("V34_ACTUAL_RESOURCE_AXIS")
    if compatible.shape != (cohorts, racks):
        raise ValueError("V34_COMPATIBILITY_AXIS")
    if np.any(da < 0) or np.any(arrivals < 0) or np.any(capacity < 0):
        raise ValueError("V34_RESOURCE_INPUT_NEGATIVE")
    initial = np.zeros(cohorts) if initial_backlog_nodeh is None else np.asarray(initial_backlog_nodeh, dtype=float)
    if initial.shape != (cohorts,) or np.any(initial < 0):
        raise ValueError("V34_INITIAL_BACKLOG_AXIS_OR_SIGN")

    backlog = np.zeros((97, cohorts), dtype=float); backlog[0] = initial
    executed = np.zeros_like(da)
    reads: list[dict[str, int | str]] = []
    calls = 0
    for slot in range(96):
        # Every read is current-slot AIDC resource state.  No electrical state
        # is accepted by this function's signature.
        for field in ("actual_workload_availability", "actual_rack_capacity", "rack_compatibility", "dayahead_authorization"):
            reads.append({"field": field, "current_slot": slot, "requested_slot": slot})
        backlog[slot + 1] = backlog[slot] + arrivals[slot]
        y, count = _solve_slot(da[:, :, slot], backlog[slot + 1], capacity[slot], compatible)
        calls += count
        executed[:, :, slot] = y
        backlog[slot + 1] -= y.sum(axis=1)
        if np.any(backlog[slot + 1] < -1e-8):
            raise RuntimeError("V34_RESOURCE_RECOURSE_NEGATIVE_BACKLOG")

    source_error = float(initial.sum() + arrivals.sum() - executed.sum() - backlog[-1].sum())
    if abs(source_error) > 1e-8:
        raise RuntimeError("V34_RESOURCE_RECOURSE_MASS_IDENTITY")
    original = np.minimum(executed, da).sum()
    firewall = {field: 0 for field in ACTUAL_AIDC_FIREWALL_FIELDS}
    return ResourceRecourseResult(
        executed, backlog, float(executed.sum() - original), calls, tuple(reads), firewall,
    )
