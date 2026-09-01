"""V28R2 payload-exposing adapter for the frozen Standard/CL-MC Benders method."""

from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np

from dayahead.v28r2.electrical_subproblem import ExactGridSubproblem, add_cut, slot_coefficients
from dayahead.v28r2.solver_payload import SolverPayload, payload_from_registry
from dayahead.v28r2.variable_registry import build_resource_model


GAMMA_CRIT = 0.98
TOLERANCE = 1e-3


class V28R2GridSubproblem(ExactGridSubproblem):
    def __init__(self, coefficients):
        super().__init__(coefficients)
        self.model.Params.Threads = 4


def solve_benders(
    *, data, context: object, voltage: object, current: object, method: str,
    raw_dir: Path | None = None, max_iterations: int = 200,
    time_limit: float = 1800.0, tolerance: float = TOLERANCE,
) -> SolverPayload:
    from gurobipy import GRB

    if method not in {"STANDARD_BD", "CL_MC_BD"}:
        raise ValueError("V28R2_BENDERS_METHOD")
    started = time.perf_counter()
    registry = build_resource_model(data, voltage, "B3")
    coefficients = [slot_coefficients(context, voltage, current, slot) for slot in range(96)]
    subproblems = [V28R2GridSubproblem(row) for row in coefficients]
    lower, upper = -math.inf, math.inf
    optimality_cuts = feasibility_cuts = cut_index = 0
    iteration_count = 0
    for iteration in range(1, max_iterations + 1):
        elapsed = time.perf_counter() - started
        if elapsed >= time_limit:
            break
        registry.model.Params.TimeLimit = max(1.0, time_limit - elapsed)
        registry.model.optimize()
        if registry.model.Status == GRB.INFEASIBLE:
            raise RuntimeError(f"V28R2_{method}_MASTER_INFEASIBLE")
        if registry.model.Status != GRB.OPTIMAL:
            break
        iteration_count = iteration
        controls = registry.controls()
        lower = max(lower, float(registry.model.ObjBound))
        results = [subproblem.solve(controls[slot], iteration, raw_dir) for slot, subproblem in enumerate(subproblems)]
        feasible = [result for result in results if result.feasible]
        infeasible = [result for result in results if not result.feasible]
        all_feasible = not infeasible
        if all_feasible:
            # The returned primal schedule is the current master incumbent.
            # Use its feasible grid value as UB so objective and full payload
            # can never refer to different iterations.
            upper = max(float(result.objective) for result in feasible)
        selected = list(infeasible)
        if all_feasible:
            if method == "STANDARD_BD":
                selected.append(max(feasible, key=lambda result: (float(result.objective), -result.slot)))
            else:
                threshold = GAMMA_CRIT * max(float(result.critical_loading) for result in feasible)
                selected.extend(
                    result for result in feasible
                    if float(result.critical_loading) >= threshold - 1e-12
                )
        for result in selected:
            cut_index += 1
            kind = add_cut(registry, result, cut_index)
            optimality_cuts += int(kind == "OPTIMALITY")
            feasibility_cuts += int(kind == "FARKAS")
        gap = (
            max(0.0, (upper - lower) / max(abs(upper), 1e-6))
            if math.isfinite(upper) and math.isfinite(lower) else math.inf
        )
        if gap <= tolerance:
            break
    runtime = time.perf_counter() - started
    gap = (
        max(0.0, (upper - lower) / max(abs(upper), 1e-6))
        if math.isfinite(upper) and math.isfinite(lower) else math.inf
    )
    if gap > tolerance or not math.isfinite(upper):
        raise RuntimeError(f"V28R2_{method}_NOT_CERTIFIED:{gap}")
    return payload_from_registry(
        registry, solver=method, status="OPTIMAL_CERTIFIED", hard_feasible=True,
        objective=float(upper), lower_bound=float(lower), upper_bound=float(upper),
        gap=float(gap), iterations=iteration_count, optimality_cuts=optimality_cuts,
        feasibility_cuts=feasibility_cuts, termination_reason="FROZEN_RELATIVE_GAP",
        runtime_seconds=runtime,
    )
