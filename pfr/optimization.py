"""Continuous Gurobi fast-recourse optimizer for the PFR runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import time
from typing import Mapping, Protocol

from .slow_fast import FastControl, FastLayerLimits, FastLayerState


class FastOptimizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class FastOptimizationContext:
    issue: int
    current_price_aud_per_mwh: float
    horizon_price_median_aud_per_mwh: float
    job_destination: Mapping[str, str]
    job_deadline_step: Mapping[str, int]
    site_gpu_capacity: Mapping[str, int]

    def validate(self, state: FastLayerState, limits: FastLayerLimits) -> None:
        jobs = set(state.remaining_work_gpu_hours)
        if set(self.job_destination) != jobs or set(self.job_deadline_step) != jobs:
            raise FastOptimizationError("optimization context does not cover the active jobs")
        if set(self.site_gpu_capacity) != set(limits.site_throughput_limit):
            raise FastOptimizationError("optimization context does not cover every IDC")
        if any(value <= 0 for value in self.site_gpu_capacity.values()):
            raise FastOptimizationError("IDC GPU capacities must be positive")
        prices = (self.current_price_aud_per_mwh, self.horizon_price_median_aud_per_mwh)
        if any(not math.isfinite(float(value)) for value in prices):
            raise FastOptimizationError("optimization prices must be finite")


@dataclass(frozen=True)
class FastOptimizationCertificate:
    solver: str
    status: str
    actual_gurobi_used: bool
    solution_count: int
    objective_value: float | None
    maximum_constraint_violation: float | None
    runtime_seconds: float
    continuous_only: bool = True

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class OptimizedFastControl:
    control: FastControl
    certificate: FastOptimizationCertificate


class FastControlOptimizer(Protocol):
    def optimize(
        self,
        *,
        nominal: FastControl,
        state: FastLayerState,
        limits: FastLayerLimits,
        context: FastOptimizationContext,
    ) -> OptimizedFastControl:
        ...


class IdentityFastControlOptimizer:
    """Default test path; scientific runs must inject the Gurobi optimizer."""

    def optimize(
        self,
        *,
        nominal: FastControl,
        state: FastLayerState,
        limits: FastLayerLimits,
        context: FastOptimizationContext,
    ) -> OptimizedFastControl:
        context.validate(state, limits)
        return OptimizedFastControl(
            nominal,
            FastOptimizationCertificate(
                solver="NONE",
                status="IDENTITY_NOT_SCIENTIFIC",
                actual_gurobi_used=False,
                solution_count=0,
                objective_value=None,
                maximum_constraint_violation=None,
                runtime_seconds=0.0,
            ),
        )


class GurobiFastControlOptimizer:
    """Solve the h0 continuous recourse problem without introducing binaries."""

    def optimize(
        self,
        *,
        nominal: FastControl,
        state: FastLayerState,
        limits: FastLayerLimits,
        context: FastOptimizationContext,
    ) -> OptimizedFastControl:
        started = time.monotonic()
        state.validate()
        limits.validate()
        context.validate(state, limits)
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as exc:
            raise FastOptimizationError("gurobipy is required for scientific PFR runs") from exc

        model = gp.Model("pfr_fast_recourse_h0")
        model.Params.OutputFlag = 0
        model.Params.Threads = 1
        model.Params.Seed = 0
        model.Params.NumericFocus = 2
        model.Params.FeasibilityTol = 1e-8
        model.Params.OptimalityTol = 1e-8
        dt_hours = limits.step_minutes / 60.0

        compute = {}
        objective = gp.QuadExpr()
        for job_id in sorted(state.remaining_work_gpu_hours):
            gpu = int(limits.job_gpu_count[job_id])
            remaining = float(state.remaining_work_gpu_hours[job_id])
            upper = min(1.0, remaining / (gpu * dt_hours))
            variable = model.addVar(lb=0.0, ub=upper, name=f"compute[{job_id}]")
            compute[job_id] = variable
            target = min(max(float(nominal.job_compute_rate_fraction.get(job_id, 0.0)), 0.0), upper)
            urgency = 1.0 / max(1, int(context.job_deadline_step[job_id]) - context.issue)
            objective += 10.0 * (variable - target) * (variable - target)
            objective += 0.1 * urgency * (1.0 - variable) * (1.0 - variable)

        for site in sorted(context.site_gpu_capacity):
            model.addConstr(
                gp.quicksum(
                    limits.job_gpu_count[job_id] * variable
                    for job_id, variable in compute.items()
                    if context.job_destination[job_id] == site
                ) <= context.site_gpu_capacity[site],
                name=f"gpu_capacity[{site}]",
            )

        mess_p = {}
        mess_q = {}
        median = max(abs(context.horizon_price_median_aud_per_mwh), 1.0)
        price_ratio = context.current_price_aud_per_mwh / median
        for mess_id in sorted(state.mess_soc):
            capacity = float(limits.mess_energy_capacity_kwh[mess_id])
            soc = float(state.mess_soc[mess_id])
            max_charge_soc = max(
                0.0,
                (float(limits.mess_soc_max[mess_id]) - soc)
                * capacity / (limits.charge_efficiency * dt_hours),
            )
            max_discharge_soc = max(
                0.0,
                (soc - float(limits.mess_soc_min[mess_id]))
                * capacity * limits.discharge_efficiency / dt_hours,
            )
            lower = -min(float(limits.mess_charge_limit_kw[mess_id]), max_charge_soc)
            upper = min(float(limits.mess_discharge_limit_kw[mess_id]), max_discharge_soc)
            p_var = model.addVar(lb=lower, ub=upper, name=f"mess_p[{mess_id}]")
            q_limit = float(limits.mess_pcs_kva[mess_id])
            q_var = model.addVar(lb=-q_limit, ub=q_limit, name=f"mess_q[{mess_id}]")
            model.addQConstr(
                p_var * p_var + q_var * q_var <= q_limit * q_limit,
                name=f"pcs_circle[{mess_id}]",
            )
            target = (
                float(nominal.mess_discharge_kw.get(mess_id, 0.0))
                - float(nominal.mess_charge_kw.get(mess_id, 0.0))
            )
            scale = max(float(limits.mess_discharge_limit_kw[mess_id]), 1.0)
            objective += ((p_var - target) / scale) * ((p_var - target) / scale)
            objective += (q_var / q_limit) * (q_var / q_limit)
            objective += -0.002 * price_ratio * p_var / scale
            mess_p[mess_id], mess_q[mess_id] = p_var, q_var

        model.setObjective(objective, GRB.MINIMIZE)
        model.optimize()
        if model.Status != GRB.OPTIMAL or model.SolCount != 1:
            raise FastOptimizationError(
                f"Gurobi fast recourse failed closed: status={model.Status}, solutions={model.SolCount}"
            )
        charge = {mess_id: max(0.0, -variable.X) for mess_id, variable in mess_p.items()}
        discharge = {mess_id: max(0.0, variable.X) for mess_id, variable in mess_p.items()}
        control = FastControl(
            mess_charge_kw=charge,
            mess_discharge_kw=discharge,
            mess_q_kvar={mess_id: variable.X for mess_id, variable in mess_q.items()},
            job_compute_rate_fraction={job_id: variable.X for job_id, variable in compute.items()},
            site_throughput_fraction=dict(nominal.site_throughput_fraction),
        )
        certificate = FastOptimizationCertificate(
            solver=f"GUROBI_{gp.gurobi.version()[0]}.{gp.gurobi.version()[1]}",
            status="OPTIMAL",
            actual_gurobi_used=True,
            solution_count=model.SolCount,
            objective_value=float(model.ObjVal),
            maximum_constraint_violation=float(model.MaxVio),
            runtime_seconds=time.monotonic() - started,
        )
        model.dispose()
        return OptimizedFastControl(control, certificate)
