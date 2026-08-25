"""Hierarchical move-blocked H54 optimizer for the online ICPS loop.

The retained Full H54 MIQCP remains an offline reference oracle.  The slow
master selects bounded route/workload decisions with a polyhedral MILP.  Those
decisions are then fixed in a persistent continuous H54 QCP carrying the exact
line, transformer, and PCS circles.  Only the exact recourse can produce a
plan for the downstream Fresh OpenDSS commit gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import time
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .compact_h54 import (
    ALLOWED_DEVELOPMENT_K,
    IDC_TRANSFORMER_LIMIT_KW,
    ONLINE_DOMAIN_AUTHORITY,
    PCS_KVA,
    PF,
    PUE,
    TANPHI,
    _MobilityTemplate,
    _RadialStressKernel,
)
from .electrical_stress import OBJECTIVE_AUTHORITY
from .methods import MethodConfig
from .migration import MigrationAuthority
from .retained_h54 import RetainedH54JointPlanner
from .runtime import (
    CausalExperimentFrame,
    IDCS,
    MESS_CAPACITY_KWH,
    MESS_CHARGE_EFFICIENCY,
    MESS_CHARGE_LIMIT_KW,
    MESS_FLOOR_KWH,
    MESS_IDS,
    MOBILITY_ELIGIBLE_MESS_IDS,
    MODELED_GPU_CAPACITY_PER_IDC,
    MutableMethodState,
    PLANNING_HORIZON_STEPS,
    RuntimeContractError,
    STEP_HOURS,
    _effective_job_site,
)
from .slow_fast import SlowDiscretePlan


ADAPTER_ID = "HIERARCHICAL_MOVE_BLOCKED_MIXED_INTEGER_H54_MPC_V1"
SOLVER_CONTRACT = "HIERARCHICAL_MOVE_BLOCKED_MIXED_INTEGER_MPC_V1"
MAX_ONLINE_QUEUED_JOBS = 16
MAX_SEPARATION_ROUNDS = 12
SEPARATION_GAP_PARTITIONS = 16
GLOBAL_ASSET_REFINEMENT_DIRECTIONS = 64
NORM_TOLERANCE = 1e-7
LEX_TOLERANCE = 1e-7
EXCLUSIVITY_TOLERANCE_KW = 1e-4
P_MAX = 550.0
ETA_DISCHARGE = 0.95


@dataclass(frozen=True)
class _WorkloadOption:
    destination: str
    rack: str
    start_offset: int
    duration_steps: int
    it_power_kw: float
    requested_gpu: int
    wan_schedule_gb: tuple[float, ...]
    wan_required_bytes: int
    remote: bool
    generation_score: tuple[float, float, float, str, str]

    @property
    def active_slice(self) -> range:
        return range(
            self.start_offset,
            min(
                PLANNING_HORIZON_STEPS,
                self.start_offset + self.duration_steps,
            ),
        )


@dataclass(frozen=True)
class _PreparedOnlineDomain:
    route_options: tuple[_MobilityTemplate, ...]
    queued_job_ids: tuple[str, ...]
    job_options: tuple[tuple[_WorkloadOption, ...], ...]
    running_it_kw: np.ndarray
    running_gpu: np.ndarray
    running_rack_gpu: Mapping[str, np.ndarray]
    running_rack_power_kw: Mapping[str, np.ndarray]
    wan_capacity_gb: np.ndarray
    route_audit: Mapping[str, Any]
    workload_audit: Mapping[str, Any]


def _status_name(grb: Any, status: int) -> str:
    names = {
        grb.OPTIMAL: "OPTIMAL",
        grb.TIME_LIMIT: "TIME_LIMIT",
        grb.SUBOPTIMAL: "SUBOPTIMAL",
        grb.INFEASIBLE: "INFEASIBLE",
        grb.INF_OR_UNBD: "INF_OR_UNBD",
        grb.INTERRUPTED: "INTERRUPTED",
    }
    return names.get(int(status), f"STATUS_{status}")


class PersistentBoundedMilpPlanner(RetainedH54JointPlanner):
    """Stateful online MILP adapter with per-method persistent solver models."""

    def __init__(self, **kwargs: Any) -> None:
        # Soft legacy location fixing is never authoritative in this backend.
        kwargs["legacy_causal_screening"] = False
        super().__init__(**kwargs)
        self.candidate_limit = int(os.environ.get("PFR_ONLINE_CANDIDATE_K", "16"))
        if self.candidate_limit not in ALLOWED_DEVELOPMENT_K:
            raise RuntimeContractError(
                f"candidate K must lie on {ALLOWED_DEVELOPMENT_K}"
            )
        self.candidate_limit_frozen = (
            os.environ.get("PFR_ONLINE_CANDIDATE_K_FROZEN", "0") == "1"
        )
        self.wall_budget_seconds = float(
            os.environ.get("PFR_ONLINE_MILP_WALL_BUDGET_SECONDS", "30.0")
        )
        self.bootstrap_wall_budget_seconds = float(
            os.environ.get("PFR_ONLINE_BOOTSTRAP_WALL_BUDGET_SECONDS", "30.0")
        )
        if not math.isfinite(self.wall_budget_seconds) or self.wall_budget_seconds <= 0:
            raise RuntimeContractError("online MILP wall budget must be positive")
        if (
            not math.isfinite(self.bootstrap_wall_budget_seconds)
            or self.bootstrap_wall_budget_seconds <= 0
        ):
            raise RuntimeContractError("bootstrap wall budget must be positive")
        self._kernels: dict[str, _RadialStressKernel] = {}
        self._kernel_issue: dict[str, int] = {}
        self._static_context_by_method: dict[str, Mapping[str, Any]] = {}
        self._master_models: dict[str, _PersistentMilpModel] = {}
        self._recourse_models: dict[str, _PersistentMilpModel] = {}

    def _issue_kernel(
        self,
        *,
        method_key: str,
        state: MutableMethodState,
        frame: CausalExperimentFrame,
        output: Path,
    ) -> _RadialStressKernel:
        self._initialize()
        running = self._workload_state(state)[1]
        reference = self.b4.reference_grid(
            self.scope,
            self.grid,
            self.metrics,
            self.gstatic,
            frame.issue,
            running,
            output,
        )
        reference["store"] = self.gstatic["store"]
        static = self.science.prepare_static_context(
            self.ar2, self.b6, reference, self.b4
        )
        kernel = _RadialStressKernel(static, reference)
        self._kernels[method_key] = kernel
        self._kernel_issue[method_key] = int(frame.issue)
        self._static_context_by_method[method_key] = static
        return kernel

    def _route_domain(
        self,
        *,
        kernel: _RadialStressKernel,
        static: Mapping[str, Any],
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        effective_steps: int,
        output: Path,
    ) -> tuple[tuple[_MobilityTemplate, ...], Mapping[str, Any]]:
        # Reuse the audited causal H54 future-prepositioning generator.  It
        # returns choices, not completed plans; the MILP jointly selects one
        # route with workload placement and continuous dispatch.
        from .compact_h54 import CompactH54JointPlanner

        helper = object.__new__(CompactH54JointPlanner)
        helper.candidate_limit = self.candidate_limit
        helper.science = self.science
        helper.scope = self.scope
        helper._static_context = static
        routes, audit = CompactH54JointPlanner._mobility_templates(
            helper,
            kernel=kernel,
            state=state,
            config=config,
            frame=frame,
            effective_steps=effective_steps,
            output=output,
        )
        return tuple(routes), dict(audit)

    def _workload_domain(
        self,
        *,
        kernel: _RadialStressKernel,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
    ) -> tuple[
        tuple[str, ...],
        tuple[tuple[_WorkloadOption, ...], ...],
        np.ndarray,
        np.ndarray,
        Mapping[str, np.ndarray],
        Mapping[str, np.ndarray],
        np.ndarray,
        Mapping[str, Any],
    ]:
        h = PLANNING_HORIZON_STEPS
        running_it = np.zeros((h, len(IDCS)), dtype=float)
        running_gpu = np.zeros_like(running_it)
        cap = self.scope["cap"].copy()
        rack_rows = {
            str(row.rack_pool_id): row for row in cap.itertuples(index=False)
        }
        rack_gpu = {rack: np.zeros(h) for rack in rack_rows}
        rack_power = {rack: np.zeros(h) for rack in rack_rows}
        queued: list[tuple[str, Any]] = []
        for uid, job in sorted(state.jobs.items()):
            if job.lifecycle == "COMPLETED":
                continue
            if job.lifecycle == "QUEUED":
                queued.append((uid, job))
                continue
            site = _effective_job_site(job)
            rack = str(job.logical_rack_id)
            if rack not in rack_rows:
                rack = self._rack_for(uid, site)
            duration = min(
                h,
                max(
                    1,
                    int(
                        math.ceil(
                            job.remaining_work_gpu_hours
                            / (job.source.requested_gpu * STEP_HOURS)
                            - 1e-12
                        )
                    ),
                ),
            )
            power = float(self._scope_job(uid, job)["IT_power_kW"])
            col = IDCS.index(site)
            running_it[:duration, col] += power
            running_gpu[:duration, col] += job.source.requested_gpu
            rack_gpu[rack][:duration] += job.source.requested_gpu
            rack_power[rack][:duration] += power
        if len(queued) > MAX_ONLINE_QUEUED_JOBS:
            raise RuntimeContractError(
                f"queued-job count {len(queued)} exceeds persistent authority "
                f"{MAX_ONLINE_QUEUED_JOBS}"
            )
        wan_index = self.scope["wan_cap"].set_index("oracle_step")
        wan_capacity = np.asarray(
            [
                float(
                    wan_index.loc[
                        frame.issue + step,
                        "public_path_safe_capacity_GB_per_5min",
                    ]
                )
                if frame.issue + step in wan_index.index
                else 0.0
                for step in range(h)
            ]
        )
        zero_mess = np.zeros((h, len(MESS_IDS)))
        locations = []
        for mid in MESS_IDS:
            locations.append([state.mess_location[mid]] * h)
        baseline = kernel.evaluate(
            frame, running_it, zero_mess, zero_mess, locations
        )
        option_sets: list[tuple[_WorkloadOption, ...]] = []
        before = 0
        exact_removed = 0
        bounded_removed = 0
        for uid, job in queued:
            row = self._scope_job(uid, job)
            duration = max(1, int(row["duration_steps"]))
            latest_offset = min(
                h - 1,
                int(job.source.latest_start_step) - frame.issue,
                int(job.source.deadline_step) - frame.issue - duration,
            )
            if latest_offset < 0:
                raise RuntimeContractError(f"job {uid} cannot meet its deadline")
            if config.temporal_workload_shift:
                offsets = list(range(latest_offset + 1))
            else:
                offsets = [0]
            if config.spatial_workload_migration:
                destinations = list(IDCS)
            else:
                destinations = [_effective_job_site(job)]
            feasible: list[_WorkloadOption] = []
            for destination in destinations:
                destination_racks = sorted(
                    {
                        str(item["rack_pool_id"])
                        for item in self.scope["domains"][uid]
                        if str(item["destination_IDC_id"]) == destination
                    }
                )
                for rack in destination_racks:
                    rack_row = rack_rows[rack]
                    for offset in offsets:
                        before += 1
                        end = min(h, offset + duration)
                        if (
                            frame.issue + offset + duration
                            > job.source.deadline_step
                            or np.any(
                                running_gpu[offset:end, IDCS.index(destination)]
                                + job.source.requested_gpu
                                > MODELED_GPU_CAPACITY_PER_IDC + 1e-9
                            )
                            or np.any(
                                rack_gpu[rack][offset:end]
                                + job.source.requested_gpu
                                > float(rack_row.deliverable_active_gpu_capacity)
                                + 1e-9
                            )
                            or np.any(
                                rack_power[rack][offset:end]
                                + float(row["IT_power_kW"])
                                > float(rack_row.rack_power_cap_kw) + 1e-9
                            )
                        ):
                            exact_removed += 1
                            continue
                        required_gb = (
                            float(self.scope["wan_map"][uid])
                            if destination != job.source.origin_idc
                            else 0.0
                        )
                        committed_gb = 0.0
                        if job.prestart_wan_transferred_bytes:
                            if job.prestart_wan_target_idc != destination:
                                exact_removed += 1
                                continue
                            committed_gb = job.prestart_wan_transferred_bytes / 1e9
                        remaining = max(0.0, required_gb - committed_gb)
                        schedule = np.zeros(h)
                        for send_step in range(offset - 1, -1, -1):
                            amount = min(remaining, wan_capacity[send_step])
                            schedule[send_step] = amount
                            remaining -= amount
                            if remaining <= 1e-12:
                                break
                        if remaining > 1e-9:
                            exact_removed += 1
                            continue
                        trial = running_it.copy()
                        trial[offset:end, IDCS.index(destination)] += float(
                            row["IT_power_kW"]
                        )
                        result = kernel.evaluate(
                            frame, trial, zero_mess, zero_mess, locations
                        )
                        score = (
                            float(result.objective[0]),
                            float(result.objective[1]),
                            float(offset) / h
                            + float(destination != job.source.origin_idc),
                            destination,
                            rack,
                        )
                        feasible.append(
                            _WorkloadOption(
                                destination=destination,
                                rack=rack,
                                start_offset=int(offset),
                                duration_steps=duration,
                                it_power_kw=float(row["IT_power_kW"]),
                                requested_gpu=int(job.source.requested_gpu),
                                wan_schedule_gb=tuple(float(v) for v in schedule),
                                wan_required_bytes=int(round(required_gb * 1e9)),
                                remote=destination != job.source.origin_idc,
                                generation_score=score,
                            )
                        )
            if not feasible:
                raise RuntimeContractError(
                    f"job {uid} has no exact-hard-feasible bounded option"
                )
            feasible.sort(key=lambda option: option.generation_score)
            selected = feasible[: self.candidate_limit]
            bounded_removed += len(feasible) - len(selected)
            option_sets.append(tuple(selected))
        return (
            tuple(uid for uid, _job in queued),
            tuple(option_sets),
            running_it,
            running_gpu,
            rack_gpu,
            rack_power,
            wan_capacity,
            {
                "domain_before_exact_safe": before,
                "exact_infeasible_removed": exact_removed,
                "exact_dominated_removed": 0,
                "domain_after_exact_safe": before - exact_removed,
                "bounded_domain_size": sum(map(len, option_sets)),
                "bounded_feasible_choices_removed": bounded_removed,
                "candidate_limit_k_per_job": self.candidate_limit,
            },
        )

    def _prepare_domain(
        self,
        *,
        kernel: _RadialStressKernel,
        static: Mapping[str, Any],
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        effective_steps: int,
        output: Path,
    ) -> _PreparedOnlineDomain:
        routes, route_audit = self._route_domain(
            kernel=kernel,
            static=static,
            state=state,
            config=config,
            frame=frame,
            effective_steps=effective_steps,
            output=output,
        )
        (
            queued,
            options,
            running_it,
            running_gpu,
            rack_gpu,
            rack_power,
            wan_capacity,
            workload_audit,
        ) = self._workload_domain(
            kernel=kernel, state=state, config=config, frame=frame
        )
        return _PreparedOnlineDomain(
            route_options=routes,
            queued_job_ids=queued,
            job_options=options,
            running_it_kw=running_it,
            running_gpu=running_gpu,
            running_rack_gpu=rack_gpu,
            running_rack_power_kw=rack_power,
            wan_capacity_gb=wan_capacity,
            route_audit=route_audit,
            workload_audit=workload_audit,
        )

    def solve(
        self,
        *,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        migration_authority: Optional[MigrationAuthority],
        evaluation_steps_remaining: int,
    ) -> tuple[SlowDiscretePlan, Mapping[str, Any]]:
        del migration_authority
        total_started = time.monotonic()
        method_key = config.comparison_method_id.value
        issue_root = (
            self.output_root
            / "_PERSISTENT_BOUNDED_MILP"
            / method_key
            / f"issue_{frame.issue:06d}"
        )
        issue_root.mkdir(parents=True, exist_ok=True)
        reference_started = time.monotonic()
        kernel = self._issue_kernel(
            method_key=method_key,
            state=state,
            frame=frame,
            output=issue_root,
        )
        reference_seconds = time.monotonic() - reference_started
        domain_started = time.monotonic()
        domain = self._prepare_domain(
            kernel=kernel,
            static=self._static_context_by_method[method_key],
            state=state,
            config=config,
            frame=frame,
            effective_steps=min(
                PLANNING_HORIZON_STEPS, int(evaluation_steps_remaining)
            ),
            output=issue_root,
        )
        domain_seconds = time.monotonic() - domain_started
        slow_domain_forced = (
            len(domain.route_options) == 1
            and all(len(options) == 1 for options in domain.job_options)
        )
        build_seconds = 0.0
        if (
            method_key not in self._recourse_models
            or (
                not slow_domain_forced
                and method_key not in self._master_models
            )
        ):
            build_started = time.monotonic()
            common_model_kwargs = {
                "candidate_limit": self.candidate_limit,
                "static": self._static_context_by_method[method_key],
                "kernel": kernel,
                "rack_rows": {
                    str(row.rack_pool_id): row
                    for row in self.scope["cap"].itertuples(index=False)
                },
            }
            if (
                not slow_domain_forced
                and method_key not in self._master_models
            ):
                self._master_models[method_key] = _PersistentMilpModel(
                    **common_model_kwargs,
                    model_role="slow_master",
                )
            if method_key not in self._recourse_models:
                self._recourse_models[method_key] = _PersistentMilpModel(
                    **common_model_kwargs,
                    model_role="exact_recourse",
                )
            build_seconds = time.monotonic() - build_started
        master = self._master_models.get(method_key)
        recourse = self._recourse_models[method_key]
        update_started = time.monotonic()
        update_kwargs = {
            "kernel": kernel,
            "state": state,
            "config": config,
            "frame": frame,
            "domain": domain,
            "peak_reserve_kwh": float(self.science.PEAK_RESERVE),
        }
        if not slow_domain_forced:
            if master is None:
                raise RuntimeContractError("slow master model missing")
            master.update(**update_kwargs)
        recourse.update(**update_kwargs)
        update_seconds = time.monotonic() - update_started
        master_started = time.monotonic()
        active_wall_budget = (
            self.bootstrap_wall_budget_seconds
            if build_seconds > 0.0
            else self.wall_budget_seconds
        )
        if slow_domain_forced:
            route_index = 0
            job_option_indices = {
                j: 0 for j in range(len(domain.job_options))
            }
            master_result = {
                "solution_status": "EXACT_FORCED_SLOW_DOMAIN_NO_MILP_REQUIRED",
                "milp_solve_seconds": 0.0,
                "separation_rounds": [0, 0, 0],
                "separation_cuts_added": 0,
            }
        else:
            if master is None:
                raise RuntimeContractError("slow master model missing")
            master_result = master.solve_lexicographic(
                wall_budget_seconds=max(0.05, 0.55 * active_wall_budget)
            )
            route_index, job_option_indices = master.selected_domain_decisions()
        master_seconds = time.monotonic() - master_started
        recourse_started = time.monotonic()
        recourse.fix_slow_decisions(
            route_index=route_index,
            job_option_indices=job_option_indices,
        )
        result = recourse.solve_lexicographic(
            wall_budget_seconds=max(0.05, 0.45 * active_wall_budget)
        )
        plan = recourse.extract_plan(
            state=state,
            config=config,
            frame=frame,
            domain=domain,
        )
        recourse_seconds = time.monotonic() - recourse_started
        plan.validate()
        total_seconds = time.monotonic() - total_started
        certificate = {
            "adapter_id": ADAPTER_ID,
            "solver_contract": SOLVER_CONTRACT,
            "objective_authority": OBJECTIVE_AUTHORITY,
            "online_domain_authority": ONLINE_DOMAIN_AUTHORITY,
            "capability_mask": dict(config.h54_capability_mask),
            "planning_horizon_steps": PLANNING_HORIZON_STEPS,
            "same_objective_constraints_physical_semantics": True,
            "restricted_online_discrete_domain": True,
            "global_full_miqcp_optimality_claimed": False,
            "full_miqcp_executed_in_online_loop": False,
            "offline_reference_oracle": "science/main.py::build_full",
            "candidate_limit_k": self.candidate_limit,
            "candidate_limit_frozen": self.candidate_limit_frozen,
            "mobility_domain_reduction": dict(domain.route_audit),
            "workload_domain_reduction": dict(domain.workload_audit),
            "solution_status": result["solution_status"],
            "actual_gurobi_used": True,
            "gurobi_slow_master_numeric_focus": (
                master.numeric_focus if master is not None else None
            ),
            "gurobi_numeric_focus": recourse.numeric_focus,
            "persistent_model_reused": build_seconds == 0.0,
            "model_build_once_seconds": build_seconds,
            "cold_start_bootstrap_budget_used": build_seconds > 0.0,
            "active_planner_wall_budget_seconds": active_wall_budget,
            "reference_anchor_seconds": reference_seconds,
            "causal_domain_generation_seconds": domain_seconds,
            "parameter_update_seconds": update_seconds,
            "slow_master_milp_seconds": master_seconds,
            "fixed_binary_exact_h54_recourse_seconds": recourse_seconds,
            "milp_solve_seconds": master_result["milp_solve_seconds"],
            "exact_recourse_solve_seconds": result["milp_solve_seconds"],
            "recourse_lexicographic_backend": result["lexicographic_backend"],
            "recourse_priority_solve_seconds": result[
                "priority_solve_seconds"
            ],
            "recourse_priority_timing_basis": result[
                "priority_timing_basis"
            ],
            "norm_separation_seconds": result["norm_separation_seconds"],
            "online_planner_total_seconds": total_seconds - build_seconds,
            "total_with_initial_model_build_seconds": total_seconds,
            "objective_worst_predicted_electrical_stress_pu": result[
                "primary_worst_stress"
            ],
            "objective_predicted_stress_exposure_pu_hours": result[
                "secondary_exposure"
            ],
            "objective_secondary_actuation": result["tertiary_actuation"],
            "predicted_voltage_stress_max": result[
                "predicted_voltage_stress_max"
            ],
            "predicted_line_stress_max": result["predicted_line_stress_max"],
            "predicted_transformer_stress_max": result[
                "predicted_transformer_stress_max"
            ],
            "priority_status": result["priority_status"],
            "priority_mip_gaps": result["priority_mip_gaps"],
            "separation_rounds": master_result["separation_rounds"],
            "separation_cuts_added": master_result["separation_cuts_added"],
            "maximum_exact_norm_residual": result[
                "maximum_exact_norm_residual"
            ],
            "maximum_simultaneous_charge_discharge_kw": result[
                "maximum_simultaneous_charge_discharge_kw"
            ],
            "charge_discharge_exclusivity_pass": result[
                "charge_discharge_exclusivity_pass"
            ],
            "charge_discharge_mode_projection_used": result[
                "charge_discharge_mode_projection_used"
            ],
            "maximum_simultaneous_charge_discharge_kw_before_projection": (
                result[
                    "maximum_simultaneous_charge_discharge_kw_before_projection"
                ]
            ),
            "charge_discharge_exclusivity_tolerance_kw": (
                EXCLUSIVITY_TOLERANCE_KW
            ),
            "charge_discharge_exclusivity_tolerance_pu": (
                EXCLUSIVITY_TOLERANCE_KW / P_MAX
            ),
            "exact_norm_separation_pass": True,
            "hierarchical_move_blocking": True,
            "slow_binary_grid_minutes": 30,
            "slow_binary_stage_count": 9,
            "fast_continuous_grid_minutes": 5,
            "slow_master_status": master_result["solution_status"],
            "slow_master_skipped_exact_forced_domain": slow_domain_forced,
            "hard_grid_candidate_pass": True,
            "hard_mess_soc_pcs_route_candidate_pass": True,
            "hard_gpu_rack_idc_candidate_pass": True,
            "hard_wan_checkpoint_candidate_pass": True,
            "hard_deadline_candidate_pass": True,
            "terminal_energy_debt_candidate_pass": True,
            "fresh_exact_opendss_commit_required_downstream": True,
            "future_actual_used": False,
            "price_used_by_optimizer": False,
            "planning_mobility_npz_sha256": frame.planning_mobility_npz_sha256,
        }
        return plan, certificate


class _PersistentMilpModel:
    """Persistent slow-MILP or fixed-slow-decision exact-QCP skeleton."""

    def __init__(
        self,
        *,
        candidate_limit: int,
        static: Mapping[str, Any],
        kernel: _RadialStressKernel,
        rack_rows: Mapping[str, Any],
        model_role: str,
    ) -> None:
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as exc:
            raise RuntimeContractError(
                "gurobipy is required by the persistent bounded MILP"
            ) from exc
        self.gp = gp
        self.GRB = GRB
        self.k = int(candidate_limit)
        if model_role not in {"slow_master", "exact_recourse"}:
            raise RuntimeContractError(f"unknown hierarchical model role {model_role}")
        self.model_role = model_role
        self.h = PLANNING_HORIZON_STEPS
        self.static = static
        self.nodes = tuple(kernel.nodes)
        self.root = kernel.root
        self.nonroot = tuple(node for node in self.nodes if node != self.root)
        self.services = tuple(sorted(kernel.service_bus))
        self.racks = tuple(sorted(rack_rows))
        self.rack_rows = dict(rack_rows)
        self.idc_by_bus: dict[str, list[str]] = {}
        self.service_by_bus: dict[str, list[str]] = {}
        for site, bus in kernel.idc_bus.items():
            self.idc_by_bus.setdefault(bus, []).append(site)
        for service, bus in kernel.service_bus.items():
            self.service_by_bus.setdefault(bus, []).append(service)
        self.model = gp.Model(f"pfr_hierarchical_h54_{model_role}")
        self.model.Params.OutputFlag = 0
        self.model.Params.Threads = int(os.environ.get("PFR_GUROBI_THREADS", "4"))
        self.model.Params.Seed = 0
        self.model.Params.MIPGap = 0.03
        # NumericFocus 0/1 are prohibited for the exact recourse: clean
        # default reruns exceeded the frozen charge/discharge residual.  The
        # non-committing polyhedral slow master may use 0; its selected slow
        # decisions still pass the separate NumericFocus=2 exact QCP and Fresh
        # OpenDSS authorities before commitment.
        self.numeric_focus = 0 if model_role == "slow_master" else 2
        self.model.Params.NumericFocus = self.numeric_focus
        self.model.Params.FeasibilityTol = 1e-8
        self.model.Params.IntFeasTol = 1e-8
        self.model.Params.OptimalityTol = 1e-8
        self.exact_qcp_diagnostic = model_role == "exact_recourse"
        self.relaxed_dispatch_mode_diagnostic = True
        discrete_type = GRB.BINARY if model_role == "slow_master" else GRB.CONTINUOUS
        self.route = {
            r: self.model.addVar(
                lb=0.0, ub=1.0, vtype=discrete_type, name=f"route[{r}]"
            )
            for r in range(self.k)
        }
        self.job = {
            (j, o): self.model.addVar(
                lb=0.0,
                ub=1.0,
                vtype=discrete_type,
                name=f"job[{j},{o}]",
            )
            for j in range(MAX_ONLINE_QUEUED_JOBS)
            for o in range(self.k)
        }
        self.mode = {
            (mid, step): self.model.addVar(
                lb=0.0,
                ub=1.0,
                vtype=(
                    GRB.CONTINUOUS
                    if self.relaxed_dispatch_mode_diagnostic
                    else GRB.BINARY
                ),
                name=f"mode[{mid},{step}]",
            )
            for mid in MESS_IDS
            for step in range(self.h)
        }
        self.pdis: dict[tuple[str, int, int], Any] = {}
        self.pchg: dict[tuple[str, int, int], Any] = {}
        self.q: dict[tuple[str, int, int], Any] = {}
        self.qabs: dict[tuple[str, int, int], Any] = {}
        mobile = MOBILITY_ELIGIBLE_MESS_IDS[0]
        for mid in MESS_IDS:
            route_axis = range(self.k) if mid == mobile else range(1)
            for r in route_axis:
                for step in range(self.h):
                    key = (mid, r, step)
                    self.pdis[key] = self.model.addVar(
                        lb=0.0, ub=P_MAX, name=f"pdis[{mid},{r},{step}]"
                    )
                    self.pchg[key] = self.model.addVar(
                        lb=0.0, ub=P_MAX, name=f"pchg[{mid},{r},{step}]"
                    )
                    self.q[key] = self.model.addVar(
                        lb=-PCS_KVA, ub=PCS_KVA, name=f"q[{mid},{r},{step}]"
                    )
                    self.qabs[key] = self.model.addVar(
                        lb=0.0, ub=PCS_KVA, name=f"qabs[{mid},{r},{step}]"
                    )
                    self.model.addConstr(self.qabs[key] >= self.q[key])
                    self.model.addConstr(self.qabs[key] >= -self.q[key])
        self.energy = {
            (mid, step): self.model.addVar(
                lb=MESS_FLOOR_KWH,
                ub=MESS_CAPACITY_KWH,
                name=f"energy[{mid},{step}]",
            )
            for mid in MESS_IDS
            for step in range(self.h + 1)
        }
        self.debt = {
            (mid, step): self.model.addVar(
                lb=0.0, ub=MESS_CAPACITY_KWH, name=f"debt[{mid},{step}]"
            )
            for mid in MESS_IDS
            for step in range(self.h + 1)
        }
        self.repay = {
            (mid, step): self.model.addVar(
                lb=0.0,
                ub=MESS_CHARGE_EFFICIENCY * STEP_HOURS * P_MAX,
                name=f"repay[{mid},{step}]",
            )
            for mid in MESS_IDS
            for step in range(self.h)
        }
        self.it = {
            (site, step): self.model.addVar(
                lb=0.0, name=f"it[{site},{step}]"
            )
            for site in IDCS
            for step in range(self.h)
        }
        self.service_p = {
            (service, step): self.model.addVar(
                lb=-4 * P_MAX, ub=4 * P_MAX, name=f"sp[{service},{step}]"
            )
            for service in self.services
            for step in range(self.h)
        }
        self.service_q = {
            (service, step): self.model.addVar(
                lb=-4 * PCS_KVA,
                ub=4 * PCS_KVA,
                name=f"sq[{service},{step}]",
            )
            for service in self.services
            for step in range(self.h)
        }
        self.flow_p = {
            (node, step): self.model.addVar(
                lb=-GRB.INFINITY, name=f"fp[{node},{step}]"
            )
            for node in self.nodes
            for step in range(self.h)
        }
        self.flow_q = {
            (node, step): self.model.addVar(
                lb=-GRB.INFINITY, name=f"fq[{node},{step}]"
            )
            for node in self.nodes
            for step in range(self.h)
        }
        self.du = {
            (node, step): self.model.addVar(
                lb=-GRB.INFINITY, name=f"du[{node},{step}]"
            )
            for node in self.nodes
            for step in range(self.h)
        }
        self.z = {
            step: self.model.addVar(lb=0.0, ub=1.0, name=f"z[{step}]")
            for step in range(self.h)
        }
        self.zmax = self.model.addVar(lb=0.0, ub=1.0, name="zmax")
        self._build_constraints(kernel)
        self.model.update()
        self._last_job_mapping: dict[tuple[int, int], Optional[_WorkloadOption]] = {}
        self._last_dispatch_service: dict[tuple[str, int, int], Optional[str]] = {}
        self._last_route_energy: dict[tuple[int, int], float] = {}
        self._last_dep_reserve: dict[tuple[int, int], float] = {}
        self._cut_directions: set[tuple[str, str, int, int, int]] = set()
        self._cut_angles: dict[tuple[str, str, int], list[float]] = {}
        self._globally_refined_assets: set[tuple[str, str]] = set()
        if self.model_role == "slow_master":
            self._add_initial_norm_cuts()
        else:
            self._add_exact_norm_constraints()
        self.model.update()
        self.domain: Optional[_PreparedOnlineDomain] = None
        self.state: Optional[MutableMethodState] = None
        self.config: Optional[MethodConfig] = None
        self.frame: Optional[CausalExperimentFrame] = None
        self.kernel = kernel

    def _route_axis(self, mid: str) -> range:
        return range(self.k) if mid == MOBILITY_ELIGIBLE_MESS_IDS[0] else range(1)

    def _pnet(self, mid: str, r: int, step: int) -> Any:
        return self.pdis[(mid, r, step)] - self.pchg[(mid, r, step)]

    def _build_constraints(self, kernel: _RadialStressKernel) -> None:
        gp = self.gp
        self.route_one = self.model.addConstr(
            gp.quicksum(self.route.values()) == 1.0, name="route_one"
        )
        self.job_one = {
            j: self.model.addConstr(
                gp.quicksum(self.job[(j, o)] for o in range(self.k)) == 0.0,
                name=f"job_one[{j}]",
            )
            for j in range(MAX_ONLINE_QUEUED_JOBS)
        }
        self.dis_gate = {}
        self.chg_gate = {}
        self.route_dispatch_gate = {}
        mobile = MOBILITY_ELIGIBLE_MESS_IDS[0]
        for mid in MESS_IDS:
            for step in range(self.h):
                pdis = gp.quicksum(
                    self.pdis[(mid, r, step)] for r in self._route_axis(mid)
                )
                pchg = gp.quicksum(
                    self.pchg[(mid, r, step)] for r in self._route_axis(mid)
                )
                self.dis_gate[(mid, step)] = self.model.addConstr(
                    pdis <= P_MAX * self.mode[(mid, step)]
                )
                self.chg_gate[(mid, step)] = self.model.addConstr(
                    pchg <= P_MAX * (1.0 - self.mode[(mid, step)])
                )
            if mid == mobile:
                for r in range(self.k):
                    for step in range(self.h):
                        self.route_dispatch_gate[(r, step)] = self.model.addConstr(
                            self.pdis[(mid, r, step)]
                            + self.pchg[(mid, r, step)]
                            <= P_MAX * self.route[r]
                        )
                        self.model.addConstr(
                            self.q[(mid, r, step)] <= PCS_KVA * self.route[r]
                        )
                        self.model.addConstr(
                            self.q[(mid, r, step)] >= -PCS_KVA * self.route[r]
                        )
        self.energy0 = {}
        self.debt0 = {}
        self.energy_dyn = {}
        self.debt_dyn = {}
        self.dep_reserve = {}
        for mid in MESS_IDS:
            self.energy0[mid] = self.model.addConstr(self.energy[(mid, 0)] == 0.0)
            self.debt0[mid] = self.model.addConstr(self.debt[(mid, 0)] == 0.0)
            for step in range(self.h):
                charge = gp.quicksum(
                    self.pchg[(mid, r, step)] for r in self._route_axis(mid)
                )
                discharge = gp.quicksum(
                    self.pdis[(mid, r, step)] for r in self._route_axis(mid)
                )
                self.energy_dyn[(mid, step)] = self.model.addConstr(
                    self.energy[(mid, step + 1)]
                    - self.energy[(mid, step)]
                    - MESS_CHARGE_EFFICIENCY * STEP_HOURS * charge
                    + STEP_HOURS / ETA_DISCHARGE * discharge
                    == 0.0
                )
                self.model.addConstr(
                    self.repay[(mid, step)]
                    <= MESS_CHARGE_EFFICIENCY * STEP_HOURS * charge
                )
                self.model.addConstr(
                    self.repay[(mid, step)]
                    <= self.debt[(mid, step)]
                    + STEP_HOURS / ETA_DISCHARGE * discharge
                )
                self.debt_dyn[(mid, step)] = self.model.addConstr(
                    self.debt[(mid, step + 1)]
                    - self.debt[(mid, step)]
                    - STEP_HOURS / ETA_DISCHARGE * discharge
                    + self.repay[(mid, step)]
                    == 0.0
                )
            self.model.addConstr(self.debt[(mid, self.h)] == 0.0)
        for r in range(self.k):
            for step in range(self.h):
                self.dep_reserve[(r, step)] = self.model.addConstr(
                    self.energy[(mobile, step)] >= MESS_FLOOR_KWH
                )
        self.it_def = {
            (site, step): self.model.addConstr(
                self.it[(site, step)] == 0.0,
                name=f"it_def[{site},{step}]",
            )
            for site in IDCS
            for step in range(self.h)
        }
        self.site_gpu = {
            (site, step): self.model.addConstr(
                gp.LinExpr() <= MODELED_GPU_CAPACITY_PER_IDC,
                name=f"site_gpu[{site},{step}]",
            )
            for site in IDCS
            for step in range(self.h)
        }
        self.rack_gpu = {
            (rack, step): self.model.addConstr(
                gp.LinExpr()
                <= float(self.rack_rows[rack].deliverable_active_gpu_capacity),
                name=f"rack_gpu[{rack},{step}]",
            )
            for rack in self.racks
            for step in range(self.h)
        }
        self.rack_power = {
            (rack, step): self.model.addConstr(
                gp.LinExpr() <= float(self.rack_rows[rack].rack_power_cap_kw),
                name=f"rack_power[{rack},{step}]",
            )
            for rack in self.racks
            for step in range(self.h)
        }
        self.wan = {
            step: self.model.addConstr(gp.LinExpr() <= 0.0, name=f"wan[{step}]")
            for step in range(self.h)
        }
        self.service_p_def = {
            (service, step): self.model.addConstr(
                self.service_p[(service, step)] == 0.0
            )
            for service in self.services
            for step in range(self.h)
        }
        self.service_q_def = {
            (service, step): self.model.addConstr(
                self.service_q[(service, step)] == 0.0
            )
            for service in self.services
            for step in range(self.h)
        }
        self.flow_p_def = {}
        self.flow_q_def = {}
        for node in self.nodes:
            for step in range(self.h):
                pexpr = self.flow_p[(node, step)] - gp.quicksum(
                    self.flow_p[(child, step)]
                    for child in kernel.children.get(node, ())
                )
                qexpr = self.flow_q[(node, step)] - gp.quicksum(
                    self.flow_q[(child, step)]
                    for child in kernel.children.get(node, ())
                )
                for site in self.idc_by_bus.get(node, ()):
                    pexpr -= PUE * self.it[(site, step)]
                    qexpr -= PUE * TANPHI * self.it[(site, step)]
                for service in self.service_by_bus.get(node, ()):
                    pexpr += self.service_p[(service, step)]
                    qexpr += self.service_q[(service, step)]
                self.flow_p_def[(node, step)] = self.model.addConstr(pexpr == 0.0)
                self.flow_q_def[(node, step)] = self.model.addConstr(qexpr == 0.0)
        self.du_def = {}
        self.voltage_low = {}
        self.voltage_high = {}
        self.voltage_below = {}
        self.voltage_above = {}
        for step in range(self.h):
            self.du_def[(self.root, step)] = self.model.addConstr(
                self.du[(self.root, step)] == 0.0
            )
            for node in self.nonroot:
                parent = kernel.parent[node]
                edge = kernel.edge[node]
                if str(edge["edge_kind"]) == "LINE":
                    expr = (
                        self.du[(node, step)]
                        - self.du[(parent, step)]
                        + 0.002
                        * float(edge["r_total_ohm"])
                        * self.flow_p[(node, step)]
                        + 0.002
                        * float(edge["x_total_ohm"])
                        * self.flow_q[(node, step)]
                    )
                else:
                    expr = self.du[(node, step)] - float(
                        edge["ratio2_ref"]
                    ) * self.du[(parent, step)]
                self.du_def[(node, step)] = self.model.addConstr(expr == 0.0)
            for node in self.nodes:
                i = kernel.index[node]
                low = float(kernel.low_u[i] - kernel.reference_u[i])
                high = float(kernel.high_u[i] - kernel.reference_u[i])
                self.voltage_low[(node, step)] = self.model.addConstr(
                    self.du[(node, step)] >= low
                )
                self.voltage_high[(node, step)] = self.model.addConstr(
                    self.du[(node, step)] <= high
                )
                below = float(kernel.nominal_u[i] - kernel.reference_u[i])
                above = float(kernel.reference_u[i] - kernel.nominal_u[i])
                self.voltage_below[(node, step)] = self.model.addConstr(
                    (kernel.nominal_u[i] - kernel.low_u[i]) * self.z[step]
                    + self.du[(node, step)]
                    >= below
                )
                self.voltage_above[(node, step)] = self.model.addConstr(
                    (kernel.high_u[i] - kernel.nominal_u[i]) * self.z[step]
                    - self.du[(node, step)]
                    >= above
                )
            self.model.addConstr(self.zmax >= self.z[step])
            for site in IDCS:
                self.model.addConstr(
                    PUE * self.it[(site, step)]
                    <= IDC_TRANSFORMER_LIMIT_KW * self.z[step]
                )
        self.primary_lock = self.model.addConstr(self.zmax <= 1.0)
        self.secondary_lock = self.model.addConstr(
            STEP_HOURS * gp.quicksum(self.z.values()) <= self.h * STEP_HOURS
        )

    def _add_cut(
        self,
        *,
        kind: str,
        element: str,
        step: int,
        direction_p: float,
        direction_q: float,
    ) -> bool:
        # Quantization prevents numerically duplicate cuts across reoptimizations.
        qp = int(round(direction_p * 1e9))
        qq = int(round(direction_q * 1e9))
        key = (kind, element, int(step), qp, qq)
        if key in self._cut_directions:
            return False
        self._cut_directions.add(key)
        angle_key = (kind, element, int(step))
        angle = math.atan2(direction_q, direction_p) % (2.0 * math.pi)
        self._cut_angles.setdefault(angle_key, []).append(angle)
        if kind == "LINE":
            limit = float(
                self.static["lim"][(self.static["parent"][element], element)]
            )
            lhs = (
                direction_p * self.flow_p[(element, step)]
                + direction_q * self.flow_q[(element, step)]
            )
            self.model.addConstr(lhs <= limit * self.z[step])
        elif kind == "SERVICE":
            limit = float(self.static["service_kva"][element])
            lhs = (
                direction_p * self.service_p[(element, step)]
                + direction_q * self.service_q[(element, step)]
            )
            self.model.addConstr(lhs <= limit * self.z[step])
        elif kind.startswith("PCS:"):
            mid = kind.split(":", 1)[1]
            r = int(element)
            lhs = (
                direction_p * self._pnet(mid, r, step)
                + direction_q * self.q[(mid, r, step)]
            )
            self.model.addConstr(lhs <= PCS_KVA)
        else:
            raise RuntimeContractError(f"unknown norm-cut kind {kind}")
        return True

    def _refine_violated_angular_gap(
        self,
        *,
        kind: str,
        element: str,
        step: int,
        direction_p: float,
        direction_q: float,
    ) -> int:
        """Partition the active outer-approximation gap around an incumbent.

        Adding only the tangent at the incumbent lets a circular constraint
        rotate to the adjacent face and can require dozens of MILP resolves.
        The cuts below are the same valid Euclidean supporting half-spaces; we
        simply partition the entire angular gap containing the violation.  A
        16-way refinement reduces the worst angular error geometrically while
        preserving the exact circle as the acceptance authority.
        """

        angle_key = (kind, element, int(step))
        angles = sorted(set(self._cut_angles.get(angle_key, ())))
        if len(angles) < 2:
            return int(
                self._add_cut(
                    kind=kind,
                    element=element,
                    step=step,
                    direction_p=direction_p,
                    direction_q=direction_q,
                )
            )
        theta = math.atan2(direction_q, direction_p) % (2.0 * math.pi)
        extended = angles + [angles[0] + 2.0 * math.pi]
        theta_extended = theta
        if theta < angles[0]:
            theta_extended += 2.0 * math.pi
        lower = angles[-1]
        upper = angles[0] + 2.0 * math.pi
        for index in range(len(angles)):
            candidate_lower = extended[index]
            candidate_upper = extended[index + 1]
            if candidate_lower - 1e-14 <= theta_extended <= candidate_upper + 1e-14:
                lower, upper = candidate_lower, candidate_upper
                break
        added = 0
        for partition in range(1, SEPARATION_GAP_PARTITIONS):
            refined = lower + (upper - lower) * (
                partition / SEPARATION_GAP_PARTITIONS
            )
            added += int(
                self._add_cut(
                    kind=kind,
                    element=element,
                    step=step,
                    direction_p=math.cos(refined),
                    direction_q=math.sin(refined),
                )
            )
        added += int(
            self._add_cut(
                kind=kind,
                element=element,
                step=step,
                direction_p=direction_p,
                direction_q=direction_q,
            )
        )
        return added

    def _add_initial_norm_cuts(self) -> None:
        directions = tuple(
            (math.cos(2 * math.pi * index / 8), math.sin(2 * math.pi * index / 8))
            for index in range(8)
        )
        for step in range(self.h):
            for node in self.nonroot:
                if (self.static["parent"][node], node) not in self.static["lim"]:
                    continue
                for dp, dq in directions:
                    self._add_cut(
                        kind="LINE", element=node, step=step,
                        direction_p=dp, direction_q=dq,
                    )
            for service in self.services:
                for dp, dq in directions:
                    self._add_cut(
                        kind="SERVICE", element=service, step=step,
                        direction_p=dp, direction_q=dq,
                    )
            for mid in MESS_IDS:
                for r in self._route_axis(mid):
                    for dp, dq in directions:
                        self._add_cut(
                            kind=f"PCS:{mid}", element=str(r), step=step,
                            direction_p=dp, direction_q=dq,
                        )

    def _add_exact_norm_constraints(self) -> None:
        """Diagnostic exact-circle realization of the same bounded domain."""

        for step in range(self.h):
            for node in self.nonroot:
                edge_key = (self.static["parent"][node], node)
                if edge_key not in self.static["lim"]:
                    continue
                limit = float(self.static["lim"][edge_key])
                self.model.addQConstr(
                    self.flow_p[(node, step)] * self.flow_p[(node, step)]
                    + self.flow_q[(node, step)] * self.flow_q[(node, step)]
                    <= limit * limit * self.z[step] * self.z[step],
                    name=f"exact_line_norm[{node},{step}]",
                )
            for service in self.services:
                limit = float(self.static["service_kva"][service])
                self.model.addQConstr(
                    self.service_p[(service, step)]
                    * self.service_p[(service, step)]
                    + self.service_q[(service, step)]
                    * self.service_q[(service, step)]
                    <= limit * limit * self.z[step] * self.z[step],
                    name=f"exact_service_norm[{service},{step}]",
                )
            for mid in MESS_IDS:
                for r in self._route_axis(mid):
                    pnet = self._pnet(mid, r, step)
                    self.model.addQConstr(
                        pnet * pnet
                        + self.q[(mid, r, step)] * self.q[(mid, r, step)]
                        <= PCS_KVA * PCS_KVA,
                        name=f"exact_pcs_norm[{mid},{r},{step}]",
                    )

    @staticmethod
    def _locations_for_route(
        state: MutableMethodState,
        route: _MobilityTemplate,
    ) -> list[Optional[str]]:
        mid = MOBILITY_ELIGIBLE_MESS_IDS[0]
        if state.mess_in_transit[mid]:
            destination = state.mess_route_destination[mid]
            if destination is None:
                raise RuntimeContractError("committed transit lacks destination")
            remaining = max(
                0,
                len(state.mess_route_energy_profile_kwh[mid])
                - int(state.mess_route_profile_index[mid]),
            )
            return [None] * min(remaining, PLANNING_HORIZON_STEPS) + [
                str(destination)
            ] * max(0, PLANNING_HORIZON_STEPS - remaining)
        current = state.mess_location[mid]
        if route.is_stay:
            return [current] * PLANNING_HORIZON_STEPS
        departure = int(route.departure_offset)
        arrival = departure + int(route.transit_steps)
        return (
            [current] * departure
            + [None] * int(route.transit_steps)
            + [route.destination_service_id]
            * (PLANNING_HORIZON_STEPS - arrival)
        )

    def _clear_job_coefficients(
        self, key: tuple[int, int], option: _WorkloadOption
    ) -> None:
        variable = self.job[key]
        for step in option.active_slice:
            self.model.chgCoeff(
                self.it_def[(option.destination, step)], variable, 0.0
            )
            self.model.chgCoeff(
                self.site_gpu[(option.destination, step)], variable, 0.0
            )
            self.model.chgCoeff(
                self.rack_gpu[(option.rack, step)], variable, 0.0
            )
            self.model.chgCoeff(
                self.rack_power[(option.rack, step)], variable, 0.0
            )
        for step, amount in enumerate(option.wan_schedule_gb):
            if amount:
                self.model.chgCoeff(self.wan[step], variable, 0.0)

    def _set_job_coefficients(
        self, key: tuple[int, int], option: _WorkloadOption
    ) -> None:
        variable = self.job[key]
        for step in option.active_slice:
            self.model.chgCoeff(
                self.it_def[(option.destination, step)],
                variable,
                -option.it_power_kw,
            )
            self.model.chgCoeff(
                self.site_gpu[(option.destination, step)],
                variable,
                option.requested_gpu,
            )
            self.model.chgCoeff(
                self.rack_gpu[(option.rack, step)],
                variable,
                option.requested_gpu,
            )
            self.model.chgCoeff(
                self.rack_power[(option.rack, step)],
                variable,
                option.it_power_kw,
            )
        for step, amount in enumerate(option.wan_schedule_gb):
            if amount:
                self.model.chgCoeff(self.wan[step], variable, amount)

    def _move_dispatch_service(
        self,
        key: tuple[str, int, int],
        service: Optional[str],
    ) -> None:
        old = self._last_dispatch_service.get(key)
        mid, r, step = key
        if old == service:
            return
        if old is not None:
            self.model.chgCoeff(
                self.service_p_def[(old, step)], self.pdis[key], 0.0
            )
            self.model.chgCoeff(
                self.service_p_def[(old, step)], self.pchg[key], 0.0
            )
            self.model.chgCoeff(
                self.service_q_def[(old, step)], self.q[key], 0.0
            )
        if service is not None:
            self.model.chgCoeff(
                self.service_p_def[(service, step)], self.pdis[key], -1.0
            )
            self.model.chgCoeff(
                self.service_p_def[(service, step)], self.pchg[key], 1.0
            )
            self.model.chgCoeff(
                self.service_q_def[(service, step)], self.q[key], -1.0
            )
        self._last_dispatch_service[key] = service

    def update(
        self,
        *,
        kernel: _RadialStressKernel,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        domain: _PreparedOnlineDomain,
        peak_reserve_kwh: float,
    ) -> None:
        if self.model.SolCount:
            for variable in self.model.getVars():
                variable.Start = float(variable.X)
        self.kernel = kernel
        self.domain = domain
        self.state = state
        self.config = config
        self.frame = frame
        mobile = MOBILITY_ELIGIBLE_MESS_IDS[0]
        dispatch_enabled = bool(config.h54_capability_mask["mess_dispatch"])

        for r in range(self.k):
            active = r < len(domain.route_options)
            self.route[r].LB = 0.0
            self.route[r].UB = 1.0 if active else 0.0
            route = domain.route_options[r] if active else None
            locations = (
                self._locations_for_route(state, route) if route is not None else [None] * self.h
            )
            for step in range(self.h):
                available = active and locations[step] is not None and dispatch_enabled
                key = (mobile, r, step)
                self.pdis[key].UB = P_MAX if available else 0.0
                self.pchg[key].UB = P_MAX if available else 0.0
                self.q[key].LB = -PCS_KVA if available else 0.0
                self.q[key].UB = PCS_KVA if available else 0.0
                self.qabs[key].UB = PCS_KVA if available else 0.0
                self._move_dispatch_service(
                    key, str(locations[step]) if available else None
                )
                old_energy = self._last_route_energy.get((r, step), 0.0)
                new_energy = (
                    float(route.energy_kwh)
                    if route is not None
                    and not route.is_stay
                    and int(route.departure_offset) == step
                    else 0.0
                )
                if old_energy != new_energy:
                    self.model.chgCoeff(
                        self.energy_dyn[(mobile, step)], self.route[r], new_energy
                    )
                    self._last_route_energy[(r, step)] = new_energy
                old_reserve = self._last_dep_reserve.get((r, step), 0.0)
                new_reserve = (
                    max(peak_reserve_kwh, float(route.energy_kwh))
                    if route is not None
                    and not route.is_stay
                    and int(route.departure_offset) == step
                    else 0.0
                )
                if old_reserve != new_reserve:
                    self.model.chgCoeff(
                        self.dep_reserve[(r, step)], self.route[r], -new_reserve
                    )
                    self._last_dep_reserve[(r, step)] = new_reserve

        for mid in MESS_IDS:
            self.energy0[mid].RHS = float(state.mess_energy_kwh[mid])
            self.debt0[mid].RHS = float(state.mess_energy_debt_kwh[mid])
            for step in range(self.h):
                committed = 0.0
                if state.mess_in_transit[mid]:
                    index = int(state.mess_route_profile_index[mid]) + step
                    profile = state.mess_route_energy_profile_kwh[mid]
                    if index < len(profile):
                        committed = float(profile[index])
                self.energy_dyn[(mid, step)].RHS = -committed
                if mid == mobile:
                    continue
                available = not state.mess_in_transit[mid] and dispatch_enabled
                key = (mid, 0, step)
                self.pdis[key].UB = P_MAX if available else 0.0
                self.pchg[key].UB = P_MAX if available else 0.0
                self.q[key].LB = -PCS_KVA if available else 0.0
                self.q[key].UB = PCS_KVA if available else 0.0
                self.qabs[key].UB = PCS_KVA if available else 0.0
                self._move_dispatch_service(
                    key, state.mess_location[mid] if available else None
                )
            if not dispatch_enabled:
                for step in range(self.h):
                    self.mode[(mid, step)].LB = 0.0
                    self.mode[(mid, step)].UB = 0.0
            else:
                for step in range(self.h):
                    # A prior exact-recourse solve may have fixed these bounds
                    # while projecting a numerically non-exclusive relaxed
                    # incumbent.  Every new issue starts from the original
                    # continuous recourse domain.
                    self.mode[(mid, step)].LB = 0.0
                    self.mode[(mid, step)].UB = 1.0

        # Clear and remap bounded workload-option coefficients.
        for key, old in tuple(self._last_job_mapping.items()):
            if old is not None:
                self._clear_job_coefficients(key, old)
        self._last_job_mapping.clear()
        for j in range(MAX_ONLINE_QUEUED_JOBS):
            active_job = j < len(domain.queued_job_ids)
            self.job_one[j].RHS = 1.0 if active_job else 0.0
            options = domain.job_options[j] if active_job else ()
            for o in range(self.k):
                key = (j, o)
                active_option = o < len(options)
                self.job[key].LB = 0.0
                self.job[key].UB = 1.0 if active_option else 0.0
                option = options[o] if active_option else None
                self._last_job_mapping[key] = option
                if option is not None:
                    self._set_job_coefficients(key, option)

        for site in IDCS:
            col = IDCS.index(site)
            for step in range(self.h):
                self.it_def[(site, step)].RHS = float(
                    domain.running_it_kw[step, col]
                )
                self.site_gpu[(site, step)].RHS = (
                    MODELED_GPU_CAPACITY_PER_IDC
                    - float(domain.running_gpu[step, col])
                )
        for rack in self.racks:
            for step in range(self.h):
                self.rack_gpu[(rack, step)].RHS = (
                    float(self.rack_rows[rack].deliverable_active_gpu_capacity)
                    - float(domain.running_rack_gpu[rack][step])
                )
                self.rack_power[(rack, step)].RHS = (
                    float(self.rack_rows[rack].rack_power_cap_kw)
                    - float(domain.running_rack_power_kw[rack][step])
                )
        for step in range(self.h):
            self.wan[step].RHS = float(domain.wan_capacity_gb[step])

        # Background nodal demands are RHS updates; all control coefficients
        # remain sparse and resident in the persistent model.
        zero_it = np.zeros((self.h, len(IDCS)))
        zero_mess = np.zeros((self.h, len(MESS_IDS)))
        dummy_locations = [
            [state.mess_location[mid]] * self.h for mid in MESS_IDS
        ]
        background_p, background_q = kernel.injections(
            frame, zero_it, zero_mess, zero_mess, dummy_locations
        )
        anchor_p_own, anchor_q_own = kernel.injections(
            frame,
            domain.running_it_kw,
            zero_mess,
            zero_mess,
            dummy_locations,
        )
        kernel.anchor_p = anchor_p_own[0].copy()
        kernel.anchor_q = anchor_q_own[0].copy()
        anchor_flow_p = kernel.anchor_p @ kernel.descendant.T
        anchor_flow_q = kernel.anchor_q @ kernel.descendant.T
        for node in self.nodes:
            i = kernel.index[node]
            for step in range(self.h):
                self.flow_p_def[(node, step)].RHS = float(background_p[step, i])
                self.flow_q_def[(node, step)].RHS = float(background_q[step, i])
                self.voltage_low[(node, step)].RHS = float(
                    kernel.low_u[i] - kernel.reference_u[i]
                )
                self.voltage_high[(node, step)].RHS = float(
                    kernel.high_u[i] - kernel.reference_u[i]
                )
                self.voltage_below[(node, step)].RHS = float(
                    kernel.nominal_u[i] - kernel.reference_u[i]
                )
                self.voltage_above[(node, step)].RHS = float(
                    kernel.reference_u[i] - kernel.nominal_u[i]
                )
                if node == self.root:
                    continue
                parent = kernel.parent[node]
                edge = kernel.edge[node]
                if str(edge["edge_kind"]) == "LINE":
                    self.model.chgCoeff(
                        self.du_def[(node, step)],
                        self.du[(parent, step)],
                        -1.0,
                    )
                    self.du_def[(node, step)].RHS = float(
                        0.002
                        * (
                            float(edge["r_total_ohm"]) * anchor_flow_p[i]
                            + float(edge["x_total_ohm"]) * anchor_flow_q[i]
                        )
                    )
                else:
                    self.model.chgCoeff(
                        self.du_def[(node, step)],
                        self.du[(parent, step)],
                        -float(edge["ratio2_ref"]),
                    )
                    self.du_def[(node, step)].RHS = 0.0
        self.primary_lock.RHS = 1.0
        self.secondary_lock.RHS = self.h * STEP_HOURS
        self.model.update()

    def selected_domain_decisions(self) -> tuple[int, dict[int, int]]:
        """Extract the slow master's integral route and workload decisions."""

        if self.model_role != "slow_master" or self.model.SolCount < 1:
            raise RuntimeContractError("slow-master decisions requested without a solution")
        if self.domain is None:
            raise RuntimeContractError("slow-master domain is unavailable")
        route_hits = [
            r
            for r in range(len(self.domain.route_options))
            if float(self.route[r].X) > 0.5
        ]
        if len(route_hits) != 1:
            raise RuntimeContractError(
                f"slow master route decision is not integral: {route_hits}"
            )
        jobs: dict[int, int] = {}
        for j, options in enumerate(self.domain.job_options):
            hits = [
                o for o in range(len(options)) if float(self.job[(j, o)].X) > 0.5
            ]
            if len(hits) != 1:
                raise RuntimeContractError(
                    f"slow master job decision is not integral j={j}: {hits}"
                )
            jobs[j] = hits[0]
        return route_hits[0], jobs

    def fix_slow_decisions(
        self,
        *,
        route_index: int,
        job_option_indices: Mapping[int, int],
    ) -> None:
        """Fix slow binaries so the second level is an exact continuous QCP."""

        if self.model_role != "exact_recourse" or self.domain is None:
            raise RuntimeContractError("slow decisions can only fix exact recourse")
        for r in range(self.k):
            value = 1.0 if r == int(route_index) else 0.0
            self.route[r].LB = value
            self.route[r].UB = value
        for j in range(MAX_ONLINE_QUEUED_JOBS):
            options = self.domain.job_options[j] if j < len(self.domain.job_options) else ()
            chosen = job_option_indices.get(j)
            for o in range(self.k):
                value = 1.0 if chosen is not None and o == int(chosen) else 0.0
                if o >= len(options):
                    value = 0.0
                self.job[(j, o)].LB = value
                self.job[(j, o)].UB = value
        self.model.update()

    def _exact_norm_residuals(self) -> tuple[float, list[tuple[str, str, int, float, float]]]:
        violations: list[tuple[str, str, int, float, float]] = []
        maximum = 0.0
        for step in range(self.h):
            z = float(self.z[step].X)
            for node in self.nonroot:
                edge_key = (self.static["parent"][node], node)
                if edge_key not in self.static["lim"]:
                    continue
                p = float(self.flow_p[(node, step)].X)
                q = float(self.flow_q[(node, step)].X)
                limit = float(self.static["lim"][edge_key]) * z
                residual = math.hypot(p, q) - limit
                maximum = max(maximum, residual)
                if residual > NORM_TOLERANCE:
                    norm = math.hypot(p, q)
                    violations.append(("LINE", node, step, p / norm, q / norm))
            for service in self.services:
                p = float(self.service_p[(service, step)].X)
                q = float(self.service_q[(service, step)].X)
                limit = float(self.static["service_kva"][service]) * z
                residual = math.hypot(p, q) - limit
                maximum = max(maximum, residual)
                if residual > NORM_TOLERANCE:
                    norm = math.hypot(p, q)
                    violations.append(
                        ("SERVICE", service, step, p / norm, q / norm)
                    )
            for mid in MESS_IDS:
                for r in self._route_axis(mid):
                    p = float(self._pnet(mid, r, step).getValue())
                    q = float(self.q[(mid, r, step)].X)
                    residual = math.hypot(p, q) - PCS_KVA
                    maximum = max(maximum, residual)
                    if residual > NORM_TOLERANCE:
                        norm = math.hypot(p, q)
                        violations.append(
                            (f"PCS:{mid}", str(r), step, p / norm, q / norm)
                        )
        return max(0.0, maximum), violations

    def _near_active_norm_directions(
        self,
        *,
        seed_violations: Sequence[tuple[str, str, int, float, float]] = (),
        utilization_floor: float = 0.90,
    ) -> list[tuple[str, str, int, float, float]]:
        """Return near-binding circles and every time slice of a violated asset.

        The horizon can otherwise move reactive support from one time slice to
        another after each cut.  Refining all 54 slices of an asset once any of
        its slices violates prevents that temporal whack-a-mole without adding
        a constraint that is not valid for the original Euclidean circle.
        """

        active_assets = {(kind, element) for kind, element, *_ in seed_violations}
        candidates: dict[
            tuple[str, str, int], tuple[str, str, int, float, float]
        ] = {}
        for step in range(self.h):
            z = float(self.z[step].X)
            for node in self.nonroot:
                edge_key = (self.static["parent"][node], node)
                if edge_key not in self.static["lim"]:
                    continue
                p = float(self.flow_p[(node, step)].X)
                q = float(self.flow_q[(node, step)].X)
                norm = math.hypot(p, q)
                limit = float(self.static["lim"][edge_key]) * z
                if norm > 0.0 and (
                    norm >= utilization_floor * limit
                    or ("LINE", node) in active_assets
                ):
                    candidates[("LINE", node, step)] = (
                        "LINE", node, step, p / norm, q / norm
                    )
            for service in self.services:
                p = float(self.service_p[(service, step)].X)
                q = float(self.service_q[(service, step)].X)
                norm = math.hypot(p, q)
                limit = float(self.static["service_kva"][service]) * z
                if norm > 0.0 and (
                    norm >= utilization_floor * limit
                    or ("SERVICE", service) in active_assets
                ):
                    candidates[("SERVICE", service, step)] = (
                        "SERVICE", service, step, p / norm, q / norm
                    )
            for mid in MESS_IDS:
                for r in self._route_axis(mid):
                    p = float(self._pnet(mid, r, step).getValue())
                    q = float(self.q[(mid, r, step)].X)
                    norm = math.hypot(p, q)
                    kind = f"PCS:{mid}"
                    element = str(r)
                    if norm > 0.0 and (
                        norm >= utilization_floor * PCS_KVA
                        or (kind, element) in active_assets
                    ):
                        candidates[(kind, element, step)] = (
                            kind, element, step, p / norm, q / norm
                        )
        return list(candidates.values())

    def _globally_refine_newly_violated_assets(
        self,
        violations: Sequence[tuple[str, str, int, float, float]],
    ) -> int:
        """Install a moderate full-circle grid once per violated asset.

        Reactive support can rotate a bottleneck through several coarse angular
        sectors.  The one-time grid prevents repeated sector hopping; the local
        gap partition and exact residual check still determine acceptance.
        """

        added = 0
        for kind, element in sorted({(row[0], row[1]) for row in violations}):
            asset = (kind, element)
            if asset in self._globally_refined_assets:
                continue
            self._globally_refined_assets.add(asset)
            for step in range(self.h):
                for index in range(GLOBAL_ASSET_REFINEMENT_DIRECTIONS):
                    angle = 2.0 * math.pi * (
                        index / GLOBAL_ASSET_REFINEMENT_DIRECTIONS
                    )
                    added += int(
                        self._add_cut(
                            kind=kind,
                            element=element,
                            step=step,
                            direction_p=math.cos(angle),
                            direction_q=math.sin(angle),
                        )
                    )
        return added

    def _optimize_priority(
        self,
        *,
        objective: Any,
        deadline: float,
    ) -> Mapping[str, Any]:
        self.model.setObjective(objective, self.GRB.MINIMIZE)
        solve_seconds = 0.0
        separation_seconds = 0.0
        cuts_added = 0
        maximum_residual = math.inf
        last_violations: list[tuple[str, str, int, float, float]] = []
        for separation_round in range(1, MAX_SEPARATION_ROUNDS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                raise RuntimeContractError(
                    "persistent MILP exceeded its wall budget before exact separation"
                )
            self.model.Params.TimeLimit = max(0.001, remaining)
            solve_started = time.monotonic()
            self.model.optimize()
            solve_seconds += time.monotonic() - solve_started
            if self.model.SolCount < 1:
                raise RuntimeContractError(
                    "persistent MILP failed closed without an incumbent: "
                    f"status={_status_name(self.GRB, self.model.Status)}"
                )
            status_ok = self.model.Status in {
                self.GRB.OPTIMAL,
                self.GRB.TIME_LIMIT,
                self.GRB.SUBOPTIMAL,
            }
            gap = (
                float(self.model.MIPGap)
                if int(self.model.IsMIP) != 0
                else 0.0
            )
            if not status_ok or not math.isfinite(gap) or gap > 0.03 + 1e-12:
                raise RuntimeContractError(
                    "persistent MILP lacks the frozen 3% certificate: "
                    f"status={_status_name(self.GRB, self.model.Status)} gap={gap}"
                )
            separation_started = time.monotonic()
            maximum_residual, violations = self._exact_norm_residuals()
            last_violations = violations
            separation_seconds += time.monotonic() - separation_started
            if not violations:
                return {
                    "status": _status_name(self.GRB, self.model.Status),
                    "gap": gap,
                    "objective": float(self.model.ObjVal),
                    "rounds": separation_round,
                    "cuts_added": cuts_added,
                    "solve_seconds": solve_seconds,
                    "separation_seconds": separation_seconds,
                    "maximum_residual": maximum_residual,
                }
            # Refine every near-active circle, not only the circles that happen
            # to violate at this incumbent.  Otherwise the MILP successively
            # rotates among coarse faces at different assets/times and exact
            # separation converges far too slowly.
            added_this_round = self._globally_refine_newly_violated_assets(
                violations
            )
            refinement_targets = self._near_active_norm_directions(
                seed_violations=violations
            )
            for kind, element, step, dp, dq in refinement_targets:
                added_this_round += self._refine_violated_angular_gap(
                    kind=kind,
                    element=element,
                    step=step,
                    direction_p=dp,
                    direction_q=dq,
                )
            cuts_added += added_this_round
            if added_this_round == 0:
                raise RuntimeContractError(
                    "exact norm separation stalled with a positive residual: "
                    f"max={maximum_residual}"
                )
            self.model.update()
        raise RuntimeContractError(
            "persistent MILP exhausted exact norm-separation rounds: "
            f"rounds={MAX_SEPARATION_ROUNDS} "
            f"max_residual_kva={maximum_residual:.12g} "
            f"remaining={len(last_violations)} "
            f"sample={last_violations[:5]}"
        )

    def _tertiary_objective(self) -> Any:
        gp = self.gp
        if self.domain is None:
            raise RuntimeContractError("persistent MILP has no updated domain")
        expression = gp.LinExpr()
        for key in self.pdis:
            expression += self.pdis[key] / (P_MAX * self.h * len(MESS_IDS))
            expression += self.pchg[key] / (P_MAX * self.h * len(MESS_IDS))
            expression += self.qabs[key] / (PCS_KVA * self.h * len(MESS_IDS))
        for r, route in enumerate(self.domain.route_options):
            expression += (
                float(route.energy_kwh) / MESS_CAPACITY_KWH
            ) * self.route[r]
        for (j, o), option in self._last_job_mapping.items():
            if option is None:
                continue
            expression += (
                float(option.start_offset) / self.h
                + float(option.remote)
                + sum(option.wan_schedule_gb)
                / max(1.0, option.wan_required_bytes / 1e9)
            ) * self.job[(j, o)]
        return expression

    def _maximum_simultaneous_charge_discharge_kw(self) -> float:
        return max(
            min(float(self.pdis[key].X), float(self.pchg[key].X))
            for key in self.pdis
        )

    def _fix_dispatch_modes_from_incumbent(self) -> None:
        """Project the relaxed incumbent onto physical dispatch directions.

        The exact recourse keeps the charge/discharge mode continuous so its
        network model remains a convex QCP.  A lexicographic actuation cost
        normally makes that relaxation exact, but optimizer tolerances can
        leave a small positive value on both power variables.  Widening the
        acceptance tolerance would merely hide that nonphysical incumbent.
        Instead, choose each direction from the incumbent's net power, fix the
        mode bounds, and solve the complete lexicographic QCP again.
        """

        if self.model_role != "exact_recourse":
            raise RuntimeContractError(
                "dispatch-mode projection is only valid for exact recourse"
            )
        for mid in MESS_IDS:
            for step in range(self.h):
                discharge = sum(
                    float(self.pdis[(mid, r, step)].X)
                    for r in self._route_axis(mid)
                )
                charge = sum(
                    float(self.pchg[(mid, r, step)].X)
                    for r in self._route_axis(mid)
                )
                direction = 1.0 if discharge >= charge else 0.0
                self.mode[(mid, step)].LB = direction
                self.mode[(mid, step)].UB = direction
        self.model.update()

    def solve_lexicographic(self, *, wall_budget_seconds: float) -> Mapping[str, Any]:
        deadline = time.monotonic() + float(wall_budget_seconds)
        exposure_expr = STEP_HOURS * self.gp.quicksum(self.z.values())
        tertiary_expr = self._tertiary_objective()
        charge_discharge_mode_projection_used = False
        maximum_simultaneous_before_projection = 0.0
        use_native_multiobjective = True
        if use_native_multiobjective:
            # Match the retained Full-H54 oracle's native Gurobi
            # lexicographic execution instead of rebuilding the branch tree
            # in three independent Python-side solves.
            self.model.setObjective(self.gp.LinExpr(), self.GRB.MINIMIZE)
            self.model.setObjectiveN(
                self.zmax, 0, priority=3, abstol=1e-6, reltol=0.0,
                name="worst_electrical_stress",
            )
            self.model.setObjectiveN(
                exposure_expr, 1, priority=2, abstol=1e-6, reltol=0.0,
                name="electrical_stress_exposure",
            )
            self.model.setObjectiveN(
                tertiary_expr, 2, priority=1, abstol=1e-8, reltol=0.0,
                name="secondary_actuation",
            )
            self.model.Params.TimeLimit = max(0.001, deadline - time.monotonic())
            solve_started = time.monotonic()
            self.model.optimize()
            exact_solve_seconds = time.monotonic() - solve_started
            if self.model.SolCount < 1 or self.model.Status != self.GRB.OPTIMAL:
                try:
                    gap = float(self.model.MIPGap)
                except Exception:
                    gap = math.inf
                raise RuntimeContractError(
                    f"hierarchical {self.model_role} multiobjective solve failed "
                    "to complete all priorities: "
                    f"status={_status_name(self.GRB, self.model.Status)} "
                    f"final_gap={gap} solve_seconds={exact_solve_seconds:.6f}"
                )
            maximum_simultaneous_before_projection = (
                self._maximum_simultaneous_charge_discharge_kw()
            )
            if (
                self.model_role == "exact_recourse"
                and maximum_simultaneous_before_projection
                > EXCLUSIVITY_TOLERANCE_KW
            ):
                # The relaxed convex-QCP incumbent is not a physical dispatch.
                # Fix its net directions and re-solve every objective priority;
                # do not accept it by relaxing the scientific tolerance.
                self._fix_dispatch_modes_from_incumbent()
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    raise RuntimeContractError(
                        "exact recourse exhausted its wall budget before "
                        "charge/discharge mode projection"
                    )
                self.model.Params.TimeLimit = max(0.001, remaining)
                projection_started = time.monotonic()
                self.model.optimize()
                exact_solve_seconds += time.monotonic() - projection_started
                charge_discharge_mode_projection_used = True
                if self.model.SolCount < 1 or self.model.Status != self.GRB.OPTIMAL:
                    raise RuntimeContractError(
                        "charge/discharge mode-projected exact recourse failed "
                        "to complete all objective priorities: "
                        f"status={_status_name(self.GRB, self.model.Status)} "
                        f"solve_seconds={exact_solve_seconds:.6f}"
                    )
            # Gurobi does not expose a single MIPGap attribute after a native
            # multiobjective solve.  OPTIMAL here means every priority stopped
            # under the model's frozen MIPGap parameter, so record the
            # conservative certified upper bound rather than inventing a
            # per-pass measured value.
            final_gap = float(self.model.Params.MIPGap)
            primary = secondary = tertiary = {
                "status": _status_name(self.GRB, self.model.Status),
                "gap": final_gap,
                "rounds": 1,
                "cuts_added": 0,
                "solve_seconds": exact_solve_seconds / 3.0,
                "separation_seconds": 0.0,
            }
        residual, remaining = self._exact_norm_residuals()
        if self.model_role == "exact_recourse":
            if remaining or residual > NORM_TOLERANCE:
                raise RuntimeContractError(
                    "exact H54 recourse lost Euclidean-norm feasibility: "
                    f"max_residual={residual:.12g} "
                    f"remaining={remaining[:5]}"
                )
        else:
            # The slow MILP is a discrete-decision master. Its polyhedral
            # circle relaxation is never committed; exact H54 recourse below
            # is the physical/objective acceptance authority.
            residual = max(0.0, residual)
        maximum_simultaneous_kw = (
            self._maximum_simultaneous_charge_discharge_kw()
        )
        if (
            self.model_role == "exact_recourse"
            and maximum_simultaneous_kw > EXCLUSIVITY_TOLERANCE_KW
        ):
            raise RuntimeContractError(
                "accepted solution violates charge/discharge exclusivity: "
                f"simultaneous_kw={maximum_simultaneous_kw:.12g}"
            )
        voltage_max = 0.0
        line_max = 0.0
        transformer_max = 0.0
        for step in range(self.h):
            for node in self.nodes:
                i = self.kernel.index[node]
                u = self.kernel.reference_u[i] + float(self.du[(node, step)].X)
                voltage_max = max(
                    voltage_max,
                    max(
                        0.0,
                        (self.kernel.nominal_u[i] - u)
                        / (self.kernel.nominal_u[i] - self.kernel.low_u[i]),
                        (u - self.kernel.nominal_u[i])
                        / (self.kernel.high_u[i] - self.kernel.nominal_u[i]),
                    ),
                )
            for node in self.nonroot:
                edge_key = (self.static["parent"][node], node)
                if edge_key in self.static["lim"]:
                    line_max = max(
                        line_max,
                        math.hypot(
                            float(self.flow_p[(node, step)].X),
                            float(self.flow_q[(node, step)].X),
                        )
                        / float(self.static["lim"][edge_key]),
                    )
            transformer_max = max(
                transformer_max,
                max(
                    PUE * float(self.it[(site, step)].X)
                    / IDC_TRANSFORMER_LIMIT_KW
                    for site in IDCS
                ),
                max(
                    math.hypot(
                        float(self.service_p[(service, step)].X),
                        float(self.service_q[(service, step)].X),
                    )
                    / float(self.static["service_kva"][service])
                    for service in self.services
                ),
            )
        return {
            "solution_status": (
                "HIERARCHICAL_SLOW_MASTER_COMPLETE"
                if self.model_role == "slow_master"
                else "FIXED_SLOW_DECISIONS_H54_EXACT_QCP_COMPLETE"
            ),
            "primary_worst_stress": float(self.zmax.X),
            "secondary_exposure": float(exposure_expr.getValue()),
            "tertiary_actuation": float(tertiary_expr.getValue()),
            "priority_status": [
                primary["status"], secondary["status"], tertiary["status"]
            ],
            "priority_mip_gaps": [
                primary["gap"], secondary["gap"], tertiary["gap"]
            ],
            "priority_solve_seconds": [
                None if use_native_multiobjective else primary["solve_seconds"],
                None if use_native_multiobjective else secondary["solve_seconds"],
                None if use_native_multiobjective else tertiary["solve_seconds"],
            ],
            "priority_timing_basis": (
                "AGGREGATE_ONLY_GUROBI_NATIVE_MULTIOBJECTIVE"
                if use_native_multiobjective
                else "MEASURED_P1_P2_P3_PERSISTENT_REOPTIMIZATION"
            ),
            "lexicographic_backend": (
                "native-multiobjective"
            ),
            "separation_rounds": [
                primary["rounds"], secondary["rounds"], tertiary["rounds"]
            ],
            "separation_cuts_added": sum(
                row["cuts_added"] for row in (primary, secondary, tertiary)
            ),
            "milp_solve_seconds": sum(
                row["solve_seconds"] for row in (primary, secondary, tertiary)
            ),
            "norm_separation_seconds": sum(
                row["separation_seconds"]
                for row in (primary, secondary, tertiary)
            ),
            "maximum_exact_norm_residual": residual,
            "maximum_simultaneous_charge_discharge_kw": (
                maximum_simultaneous_kw
            ),
            "maximum_simultaneous_charge_discharge_kw_before_projection": (
                maximum_simultaneous_before_projection
            ),
            "charge_discharge_mode_projection_used": (
                charge_discharge_mode_projection_used
            ),
            "charge_discharge_exclusivity_pass": True,
            "predicted_voltage_stress_max": voltage_max,
            "predicted_line_stress_max": line_max,
            "predicted_transformer_stress_max": transformer_max,
        }

    def extract_plan(
        self,
        *,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        domain: _PreparedOnlineDomain,
    ) -> SlowDiscretePlan:
        route_hits = [r for r in range(len(domain.route_options)) if self.route[r].X > 0.5]
        if len(route_hits) != 1:
            raise RuntimeContractError("persistent MILP route selection is not integral")
        route = domain.route_options[route_hits[0]]
        mobile = MOBILITY_ELIGIBLE_MESS_IDS[0]
        destinations = {mid: state.mess_location[mid] for mid in MESS_IDS}
        ranks = {mid: int(state.mess_route_rank[mid]) for mid in MESS_IDS}
        departures: dict[str, Optional[int]] = {mid: None for mid in MESS_IDS}
        if state.mess_in_transit[mobile]:
            destinations[mobile] = str(state.mess_route_destination[mobile])
            ranks[mobile] = int(state.mess_route_rank[mobile])
        elif not route.is_stay:
            destinations[mobile] = route.destination_service_id
            ranks[mobile] = route.route_rank
            departures[mobile] = frame.issue + int(route.departure_offset)
        placements: dict[str, str] = {}
        starts: dict[str, int] = {}
        racks: dict[str, str] = {}
        wan: dict[str, tuple[float, ...]] = {}
        wan_required: dict[str, int] = {}
        queued_index = {uid: index for index, uid in enumerate(domain.queued_job_ids)}
        active_jobs = {
            uid: job for uid, job in state.jobs.items() if job.lifecycle != "COMPLETED"
        }
        for uid, job in sorted(active_jobs.items()):
            if uid not in queued_index:
                destination = _effective_job_site(job)
                rack = str(job.logical_rack_id)
                if rack not in self.racks:
                    rack = next(
                        rack_id
                        for rack_id, row in self.rack_rows.items()
                        if str(row.idc_id) == destination
                    )
                placements[uid] = destination
                starts[uid] = frame.issue
                racks[uid] = rack
                wan[uid] = (0.0,) * self.h
                wan_required[uid] = 0
                continue
            j = queued_index[uid]
            hits = [
                o
                for o in range(len(domain.job_options[j]))
                if self.job[(j, o)].X > 0.5
            ]
            if len(hits) != 1:
                raise RuntimeContractError(
                    f"persistent MILP job option is not integral uid={uid}"
                )
            option = domain.job_options[j][hits[0]]
            placements[uid] = option.destination
            starts[uid] = frame.issue + option.start_offset
            racks[uid] = option.rack
            wan[uid] = option.wan_schedule_gb
            wan_required[uid] = option.wan_required_bytes
        charge: dict[str, tuple[float, ...]] = {}
        discharge: dict[str, tuple[float, ...]] = {}
        reactive: dict[str, tuple[float, ...]] = {}
        for mid in MESS_IDS:
            selected_r = route_hits[0] if mid == mobile else 0
            charge[mid] = tuple(
                float(self.pchg[(mid, selected_r, step)].X)
                for step in range(self.h)
            )
            discharge[mid] = tuple(
                float(self.pdis[(mid, selected_r, step)].X)
                for step in range(self.h)
            )
            reactive[mid] = tuple(
                float(self.q[(mid, selected_r, step)].X)
                for step in range(self.h)
            )
        return SlowDiscretePlan(
            plan_id=(
                f"{config.comparison_method_id.value}-{frame.issue}-"
                f"{state.full_replan_count + 1}"
            ),
            valid_from_issue=frame.issue,
            mess_destination=destinations,
            mess_native_route_rank=ranks,
            job_idc_placement=placements,
            checkpoint_migration={uid: None for uid in active_jobs},
            gpu_gang_allocation={
                uid: tuple(
                    f"{racks[uid]}:PFR-GPU:{uid}:{index}"
                    for index in range(job.source.requested_gpu)
                )
                for uid, job in active_jobs.items()
            },
            job_start_issue=starts,
            coarse_charging_kw=charge,
            coarse_discharging_kw=discharge,
            coarse_reactive_kvar=reactive,
            mess_departure_issue=departures,
            job_wan_send_gb=wan,
            job_wan_required_bytes=wan_required,
        )
