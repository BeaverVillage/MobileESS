"""D-1-only E1 Stage-1 solve with an injected planning voltage ceiling.

This decision module deliberately imports neither Actual replay nor Fresh/OpenDSS.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Mapping

import numpy as np

from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v28r2.schedule_freeze import _schedule
from dayahead.v28r2.solver_payload import payload_from_registry
from dayahead.v28r2.solver_runner import add_grid_rows
from dayahead.v28r2.variable_registry import build_resource_model, value


@dataclass(frozen=True)
class Stage1Result:
    schedule: Mapping[str, object]
    feasible: bool
    objective: float
    planning_vmin_pu: float
    planning_vmax_pu: float
    solver_iterations: int
    runtime_seconds: float
    mess_max_abs_p_difference_kw: float
    mess_max_abs_q_difference_kvar: float


class Stage1Infeasible(RuntimeError):
    def __init__(self, case: str, status: int):
        self.case = case
        self.status = status
        super().__init__(f"V33XR2_STAGE1_INFEASIBLE:{case}:{status}")


def solve_stage1(
    data: object,
    context: object,
    voltage: object,
    current: object,
    case: str,
    frozen_mess_schedule: Mapping[str, object],
    planning_vmax_pu: float,
) -> Stage1Result:
    """Re-solve workload placement while keeping the supplied MESS trajectory fixed."""

    from gurobipy import GRB

    if case not in {"B1", "B3"}:
        raise ValueError("V33XR2_STAGE1_CASE")
    if not math.isclose(float(planning_vmax_pu), 1.0495, rel_tol=0.0, abs_tol=0.0):
        raise ValueError("V33XR2_SINGLE_PREDECLARED_VMAX")
    started = time.perf_counter()
    registry = build_resource_model(data, voltage, case, rho_aidc=1.0, rho_mess=0.10)
    try:
        add_grid_rows(
            registry, context, voltage, current,
            planning_vmax_pu=planning_vmax_pu,
        )
        model = registry.model
        mess_ids = tuple(sorted(data.mess_records))
        frozen_p = np.asarray(frozen_mess_schedule["mess_p_kw"], dtype=float)
        frozen_q = np.asarray(frozen_mess_schedule["mess_q_kvar"], dtype=float)
        for slot in range(96):
            for index, mess in enumerate(mess_ids):
                model.addConstr(
                    registry.mess_p[(mess, slot)] == float(frozen_p[slot, index]),
                    name=f"v33xr2_frozen_mess_p[{mess},{slot}]",
                )
                model.addConstr(
                    registry.mess_q[(mess, slot)] == float(frozen_q[slot, index]),
                    name=f"v33xr2_frozen_mess_q[{mess},{slot}]",
                )
        model.update()
        model.optimize()
        if model.Status != GRB.OPTIMAL:
            raise Stage1Infeasible(case, int(model.Status))
        objective = float(value(registry.eta))
        payload = payload_from_registry(
            registry, solver="MONOLITHIC", status="OPTIMAL", hard_feasible=True,
            objective=objective, lower_bound=objective, upper_bound=objective, gap=0.0,
            iterations=int(model.IterCount), optimality_cuts=0, feasibility_cuts=0,
            termination_reason="V33XR2_GUROBI_OPTIMAL", runtime_seconds=time.perf_counter() - started,
        )
        schedule = _schedule(payload, str(frozen_mess_schedule["reference_schedule_sha256"]))
        schedule["development_planning_vmax_pu"] = float(planning_vmax_pu)
        schedule["fresh_physical_vmax_pu"] = 1.05
        schedule["fresh_inputs"] = 0
        schedule["formulation_fingerprint"] = canonical_sha256({
            "base": schedule["formulation_fingerprint"],
            "experiment": "V33XR2_E1_VMAX10495",
            "planning_vmax_pu": float(planning_vmax_pu),
            "planning_vmin_pu": 0.95,
            "mess_frozen_schedule_sha256": frozen_mess_schedule["schedule_sha256"],
        })
        schedule.pop("schedule_sha256", None)
        schedule["schedule_sha256"] = canonical_sha256(schedule)

        controls = np.asarray(schedule["controls"], dtype=float)
        voltage_rows = []
        for slot in range(96):
            coefficient = slot_coefficients(context, voltage, current, slot)
            voltage_rows.append(
                np.asarray(coefficient.voltage_constant, dtype=float)
                + np.asarray(coefficient.voltage_matrix, dtype=float).T @ controls[slot]
            )
        voltage_pu = np.sqrt(np.maximum(np.asarray(voltage_rows), 0.0))
        result_p = np.asarray(schedule["mess_p_kw"], dtype=float)
        result_q = np.asarray(schedule["mess_q_kvar"], dtype=float)
        return Stage1Result(
            schedule=schedule,
            feasible=True,
            objective=objective,
            planning_vmin_pu=float(voltage_pu.min()),
            planning_vmax_pu=float(voltage_pu.max()),
            solver_iterations=int(model.IterCount),
            runtime_seconds=time.perf_counter() - started,
            mess_max_abs_p_difference_kw=float(np.max(np.abs(result_p - frozen_p))),
            mess_max_abs_q_difference_kvar=float(np.max(np.abs(result_q - frozen_q))),
        )
    finally:
        registry.model.dispose()
