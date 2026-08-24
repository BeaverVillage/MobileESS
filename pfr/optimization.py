"""Continuous Gurobi fast-recourse optimizer for the PFR runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import os
import time
from typing import Mapping, Protocol

from .slow_fast import FastControl, FastLayerLimits, FastLayerState


class FastOptimizationError(RuntimeError):
    pass


def gurobi_thread_limit() -> int:
    """Return the configured per-process Gurobi thread limit."""
    try:
        value = int(os.environ.get("PFR_GUROBI_THREADS", "1"))
    except ValueError as exc:
        raise FastOptimizationError("PFR_GUROBI_THREADS must be an integer") from exc
    if not 1 <= value <= 64:
        raise FastOptimizationError("PFR_GUROBI_THREADS must be in [1, 64]")
    return value


@dataclass(frozen=True)
class FastOptimizationContext:
    issue: int
    current_price_aud_per_mwh: float
    horizon_price_median_aud_per_mwh: float
    job_destination: Mapping[str, str]
    job_deadline_step: Mapping[str, int]
    site_gpu_capacity: Mapping[str, int]
    mess_operational_enabled: bool
    compute_modulation_enabled: bool

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
    raw_maximum_constraint_violation: float | None = None
    post_projection_maximum_constraint_violation: float | None = None
    numerical_recovery_used: bool = False
    numerical_retry_count: int = 0

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
        dt_hours = limits.step_minutes / 60.0
        compute = {
            job_id: min(
                max(
                    float(nominal.job_compute_rate_fraction.get(job_id, 0.0)),
                    0.0,
                ),
                1.0,
                float(state.remaining_work_gpu_hours[job_id])
                / (int(limits.job_gpu_count[job_id]) * dt_hours),
            )
            for job_id in state.remaining_work_gpu_hours
        }
        control = FastControl(
            dict(nominal.mess_charge_kw),
            dict(nominal.mess_discharge_kw),
            dict(nominal.mess_q_kvar),
            compute,
            dict(nominal.site_throughput_fraction),
        )
        return OptimizedFastControl(
            control,
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
        model.Params.Threads = gurobi_thread_limit()
        model.Params.Seed = 0
        model.Params.NumericFocus = 2
        model.Params.FeasibilityTol = 1e-8
        model.Params.OptimalityTol = 1e-8
        dt_hours = limits.step_minutes / 60.0

        compute = {}
        compute_lower = {}
        compute_upper = {}
        objective = gp.QuadExpr()
        for job_id in sorted(state.remaining_work_gpu_hours):
            gpu = int(limits.job_gpu_count[job_id])
            remaining = float(state.remaining_work_gpu_hours[job_id])
            upper = min(1.0, remaining / (gpu * dt_hours))
            target = min(max(float(nominal.job_compute_rate_fraction.get(job_id, 0.0)), 0.0), upper)
            lower = 0.0 if context.compute_modulation_enabled else target
            variable_upper = upper if context.compute_modulation_enabled else target
            variable = model.addVar(
                lb=lower,
                ub=variable_upper,
                name=f"compute[{job_id}]",
            )
            compute[job_id] = variable
            compute_lower[job_id] = lower
            compute_upper[job_id] = variable_upper
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
        mess_bounds = {}
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
            if not context.mess_operational_enabled:
                lower = upper = 0.0
            p_var = model.addVar(lb=lower, ub=upper, name=f"mess_p[{mess_id}]")
            target = (
                float(nominal.mess_discharge_kw.get(mess_id, 0.0))
                - float(nominal.mess_charge_kw.get(mess_id, 0.0))
            )
            scale = max(float(limits.mess_discharge_limit_kw[mess_id]), 1.0)
            objective += ((p_var - target) / scale) * ((p_var - target) / scale)
            mess_p[mess_id] = p_var
            mess_bounds[mess_id] = (lower, upper)

        model.setObjective(objective, GRB.MINIMIZE)
        model.optimize()
        primal_variables = tuple(compute.values()) + tuple(mess_p.values())
        finite_primal = model.SolCount >= 1 and all(math.isfinite(float(variable.X)) for variable in primal_variables)
        feasible_status = model.Status in {GRB.OPTIMAL, GRB.SUBOPTIMAL}
        raw_max_violation = float(model.MaxVio) if model.SolCount >= 1 else None
        numerical_retry_count = 0
        if feasible_status and finite_primal and raw_max_violation is not None and raw_max_violation > 1e-6:
            # The model contains only continuous bound and site-capacity constraints.
            # Retry deterministically with stronger scaling before applying the exact
            # canonical feasibility projection below.  This does not relax a limit.
            numerical_retry_count = 1
            model.Params.NumericFocus = 3
            model.Params.ScaleFlag = 2
            model.Params.BarHomogeneous = 1
            model.reset()
            model.optimize()
            finite_primal = model.SolCount >= 1 and all(
                math.isfinite(float(variable.X)) for variable in primal_variables
            )
            feasible_status = model.Status in {GRB.OPTIMAL, GRB.SUBOPTIMAL}
            raw_max_violation = float(model.MaxVio) if model.SolCount >= 1 else None
        if not feasible_status or not finite_primal:
            status = model.Status
            solutions = model.SolCount
            max_violation = raw_max_violation
            model.dispose()
            raise FastOptimizationError(
                f"Gurobi fast recourse failed closed: status={status}, "
                f"solutions={solutions}, max_violation={max_violation}"
            )

        # Canonicalize the continuous primal to the unchanged hard bounds.  Gurobi's
        # MaxVio can be a few e-6 on this badly scaled QP even when it reports an
        # optimal solution.  Clipping and proportional site projection are exact for
        # this feasible set and are independently checked below.
        compute_value = {
            job_id: min(
                compute_upper[job_id],
                max(compute_lower[job_id], float(variable.X)),
            )
            for job_id, variable in compute.items()
        }
        for site, capacity in context.site_gpu_capacity.items():
            site_jobs = [
                job_id
                for job_id in compute_value
                if context.job_destination[job_id] == site
            ]
            used = sum(limits.job_gpu_count[job_id] * compute_value[job_id] for job_id in site_jobs)
            if used > float(capacity):
                if not context.compute_modulation_enabled:
                    model.dispose()
                    raise FastOptimizationError(
                        "fixed compute schedule exceeds IDC GPU capacity"
                    )
                factor = float(capacity) / used
                for job_id in site_jobs:
                    compute_value[job_id] *= factor
        mess_value = {
            mess_id: min(upper, max(lower, float(mess_p[mess_id].X)))
            for mess_id, (lower, upper) in mess_bounds.items()
        }
        residuals = [
            max(
                0.0,
                compute_lower[job_id] - value,
                value - compute_upper[job_id],
            )
            for job_id, value in compute_value.items()
        ]
        residuals.extend(
            max(
                0.0,
                sum(
                    limits.job_gpu_count[job_id] * compute_value[job_id]
                    for job_id in compute_value
                    if context.job_destination[job_id] == site
                ) - float(capacity),
            )
            for site, capacity in context.site_gpu_capacity.items()
        )
        residuals.extend(
            max(0.0, lower - mess_value[mess_id], mess_value[mess_id] - upper)
            for mess_id, (lower, upper) in mess_bounds.items()
        )
        post_projection_violation = max(residuals, default=0.0)
        if post_projection_violation > 1e-9:
            model.dispose()
            raise FastOptimizationError(
                "canonical fast-recourse feasibility projection failed closed: "
                f"max_violation={post_projection_violation}"
            )
        charge = {mess_id: max(0.0, -value) for mess_id, value in mess_value.items()}
        discharge = {mess_id: max(0.0, value) for mess_id, value in mess_value.items()}
        control = FastControl(
            mess_charge_kw=charge,
            mess_discharge_kw=discharge,
            mess_q_kvar={mess_id: 0.0 for mess_id in mess_p},
            job_compute_rate_fraction=compute_value,
            site_throughput_fraction=dict(nominal.site_throughput_fraction),
        )
        certificate = FastOptimizationCertificate(
            solver=f"GUROBI_{gp.gurobi.version()[0]}.{gp.gurobi.version()[1]}",
            status=(
                "OPTIMAL_NUMERICAL_RECOVERY_PROJECTED"
                if numerical_retry_count or (raw_max_violation or 0.0) > 1e-6
                else ("OPTIMAL" if model.Status == GRB.OPTIMAL else "SUBOPTIMAL_NUMERIC_FEASIBLE")
            ),
            actual_gurobi_used=True,
            solution_count=model.SolCount,
            objective_value=float(model.ObjVal),
            maximum_constraint_violation=post_projection_violation,
            runtime_seconds=time.monotonic() - started,
            raw_maximum_constraint_violation=raw_max_violation,
            post_projection_maximum_constraint_violation=post_projection_violation,
            numerical_recovery_used=bool(
                numerical_retry_count or (raw_max_violation or 0.0) > 1e-6
            ),
            numerical_retry_count=numerical_retry_count,
        )
        model.dispose()
        return OptimizedFastControl(control, certificate)
