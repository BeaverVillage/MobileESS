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
MAX_DYNAMIC_QUEUED_JOB_SLOTS = 1024
MAX_SEPARATION_ROUNDS = 12
SEPARATION_GAP_PARTITIONS = 16
GLOBAL_ASSET_REFINEMENT_DIRECTIONS = 64
# Gurobi certifies the scaled QCP rows, not an absolute kVA residual.  Keep the
# numerical contract dimensionless and reserve a separate physical margin so a
# solution at the numerical boundary is still strictly inside nameplate.
NORM_RELATIVE_TOLERANCE = 1e-6
NORM_ENGINEERING_MARGIN_FRACTION = 1e-5
NORM_SAFE_LIMIT_FACTOR = 1.0 - NORM_ENGINEERING_MARGIN_FRACTION
if NORM_SAFE_LIMIT_FACTOR + NORM_RELATIVE_TOLERANCE >= 1.0:
    raise RuntimeError("norm engineering margin must dominate solver tolerance")
# The causal radial surrogate is an optimization/ranking model, while Fresh
# three-phase OpenDSS is the H0 execution authority.  Its normalized stress
# epigraph must therefore be able to report values above one; clipping it at
# one turned conservative forecast error into a false solver infeasibility.
PLANNING_STRESS_EPIGRAPH_MAX = 10.0
LEX_TOLERANCE = 1e-7
EXCLUSIVITY_TOLERANCE_KW = 1e-4
MAX_EXACT_QCP_FEASIBILITY_RESTORATION_ROUNDS = 4
P_MAX = 550.0
ETA_DISCHARGE = 0.95
# A 3% discrete master gap can hide the entire marginal value of mobility:
# the February counterfactual exposed a 2.97% stress improvement that Gurobi
# was allowed to treat as equivalent to STAY.  Keep the published 3% ceiling
# for the continuous recourse certificate, but solve route/workload binaries
# to a sub-percent gap so an enabled flexibility is actually compared.
SLOW_MASTER_MIP_GAP = 0.001
MOBILITY_ROUTE_CANDIDATE_MIN_K = 16


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
    effective_steps: int
    route_options: tuple[_MobilityTemplate, ...]
    queued_job_ids: tuple[str, ...]
    deferred_queued_job_ids: tuple[str, ...]
    job_options: tuple[tuple[_WorkloadOption, ...], ...]
    running_it_kw: np.ndarray
    running_gpu: np.ndarray
    running_rack_gpu: Mapping[str, np.ndarray]
    running_rack_power_kw: Mapping[str, np.ndarray]
    wan_capacity_gb: np.ndarray
    route_audit: Mapping[str, Any]
    workload_audit: Mapping[str, Any]


def _episode_terminal_debt_rhs(
    effective_steps: int,
    horizon_steps: int = PLANNING_HORIZON_STEPS,
    *,
    additional_zero_boundaries: Sequence[int] = (),
) -> tuple[float, ...]:
    """Return debt bounds at the episode end and fixed recovery deadlines."""

    effective = int(effective_steps)
    horizon = int(horizon_steps)
    if not 1 <= effective <= horizon:
        raise RuntimeContractError("effective episode horizon is invalid")
    zero_boundaries = {effective}
    zero_boundaries.update(
        int(boundary)
        for boundary in additional_zero_boundaries
        if 1 <= int(boundary) <= effective
    )
    return tuple(
        0.0 if boundary in zero_boundaries else MESS_CAPACITY_KWH
        for boundary in range(1, horizon + 1)
    )


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
        self.candidate_limit = int(os.environ.get("PFR_ONLINE_CANDIDATE_K", "4"))
        if self.candidate_limit not in ALLOWED_DEVELOPMENT_K:
            raise RuntimeContractError(
                f"candidate K must lie on {ALLOWED_DEVELOPMENT_K}"
            )
        self.candidate_limit_frozen = (
            os.environ.get("PFR_ONLINE_CANDIDATE_K_FROZEN", "0") == "1"
        )
        self.base_candidate_limit = self.candidate_limit
        self.adaptive_candidate_max = int(
            os.environ.get("PFR_ONLINE_ADAPTIVE_CANDIDATE_MAX_K", "64")
        )
        if (
            self.adaptive_candidate_max not in ALLOWED_DEVELOPMENT_K
            or self.adaptive_candidate_max < self.base_candidate_limit
        ):
            raise RuntimeContractError(
                "adaptive candidate maximum must be an allowed K no smaller "
                "than the base candidate K"
            )
        self.wall_budget_seconds = float(
            os.environ.get("PFR_ONLINE_MILP_WALL_BUDGET_SECONDS", "60.0")
        )
        self.bootstrap_wall_budget_seconds = float(
            os.environ.get("PFR_ONLINE_BOOTSTRAP_WALL_BUDGET_SECONDS", "60.0")
        )
        self.max_persistent_solve_reuses = int(
            os.environ.get("PFR_PERSISTENT_MODEL_MAX_REUSES", "16")
        )
        if not math.isfinite(self.wall_budget_seconds) or self.wall_budget_seconds <= 0:
            raise RuntimeContractError("online MILP wall budget must be positive")
        if (
            not math.isfinite(self.bootstrap_wall_budget_seconds)
            or self.bootstrap_wall_budget_seconds <= 0
        ):
            raise RuntimeContractError("bootstrap wall budget must be positive")
        if self.max_persistent_solve_reuses < 1:
            raise RuntimeContractError("persistent model max reuses must be positive")
        self._kernels: dict[str, _RadialStressKernel] = {}
        self._kernel_issue: dict[str, int] = {}
        self._static_context_by_method: dict[str, Mapping[str, Any]] = {}
        self._master_models: dict[str, _PersistentMilpModel] = {}
        self._recourse_models: dict[str, _PersistentMilpModel] = {}
        self._job_slot_capacity_by_method: dict[str, int] = {}
        self._model_solve_generation_by_method: dict[str, int] = {}
        self._adaptive_domain_cache_by_method: dict[
            str, tuple[int, str, int, int, _PreparedOnlineDomain]
        ] = {}

    def _dispose_method_models(self, method_key: str) -> None:
        for models in (self._master_models, self._recourse_models):
            stale = models.pop(method_key, None)
            if stale is not None:
                stale.model.dispose()

    @staticmethod
    def _shared_watchdog_budgets(
        total_seconds: float,
        *,
        master_elapsed_seconds: float | None = None,
    ) -> float:
        """Allocate one watchdog across the master and exact-recourse stages.

        January R6 and R8 exposed that both the former 55/45 split and a later
        20/10 reserved split could time out the master even when both stages
        could still complete inside the planner-wide watchdog.
        The master therefore sees the one total deadline; exact recourse gets
        precisely the wall time that remains after the master and decision fix.
        """

        total = float(total_seconds)
        if not math.isfinite(total) or total <= 0.0:
            raise RuntimeContractError("shared planner watchdog must be positive")
        if master_elapsed_seconds is None:
            return total
        elapsed = float(master_elapsed_seconds)
        if not math.isfinite(elapsed) or elapsed < 0.0:
            raise RuntimeContractError("master elapsed time must be nonnegative")
        remaining = total - elapsed
        if remaining <= 0.0:
            raise RuntimeContractError(
                "slow master exhausted the shared planner watchdog before exact recourse"
            )
        return remaining

    def materialize_runtime_rack_assignments(
        self, state: MutableMethodState, config: MethodConfig
    ) -> Mapping[str, Any]:
        """Assign ready pooled gangs to the retained physical rack domain.

        Admission can occur between slow replans and therefore cannot depend
        on the bounded queued-job optimization domain.  Use the same retained
        rack capacities and per-job admissible domains here so a work-
        conserving IDC-level admission never becomes an unmodelled rack
        overload at the next replan.
        """

        self._initialize()
        cap = self.scope["cap"].copy()
        rack_rows = {
            str(row.rack_pool_id): row for row in cap.itertuples(index=False)
        }
        occupied_gpu = {rack: 0.0 for rack in rack_rows}
        occupied_power = {rack: 0.0 for rack in rack_rows}
        assigned = 0
        capacity_blocked = 0

        def is_ready(uid: str, job: Any) -> bool:
            if job.lifecycle != "QUEUED":
                return True
            if job.migration_state == "PRESTART_WAN_PENDING":
                return False
            if state.active_plan is None:
                return True
            return state.issue >= int(
                state.active_plan.job_start_issue.get(uid, state.issue)
            )

        ordered = sorted(
            (
                (uid, job)
                for uid, job in state.jobs.items()
                if job.lifecycle != "COMPLETED" and is_ready(uid, job)
            ),
            key=lambda item: (
                item[1].lifecycle == "QUEUED",
                (
                    item[1].lifecycle == "QUEUED"
                    and str(item[1].logical_rack_id) not in rack_rows
                ),
                item[1].source.latest_start_step,
                item[1].source.deadline_step,
                item[1].source.arrival_step,
                item[0],
            ),
        )
        for uid, job in ordered:
            destination = _effective_job_site(job)
            row = self._scope_job(uid, job)
            power_kw = (
                float(row["IT_power_kW"])
                if job.lifecycle in {"RUNNING", "QUEUED"}
                else 0.0
            )
            gpu = int(job.source.requested_gpu)
            admissible_rows = [
                item
                for item in self.scope["domains"][uid]
                if (
                    config.spatial_workload_migration
                    or str(item["destination_IDC_id"]) == destination
                )
            ]
            allowed = sorted(
                {str(item["rack_pool_id"]) for item in admissible_rows}
            )
            current = str(job.logical_rack_id)
            if current in rack_rows:
                if current not in allowed:
                    raise RuntimeContractError(
                        f"job {uid} physical rack is outside its retained domain"
                    )
                selected = current
            else:
                feasible = [
                    rack
                    for rack in allowed
                    if occupied_gpu[rack] + gpu
                    <= float(rack_rows[rack].deliverable_active_gpu_capacity)
                    + 1e-9
                    and occupied_power[rack] + power_kw
                    <= float(rack_rows[rack].rack_power_cap_kw) + 1e-9
                ]
                if not feasible:
                    if job.lifecycle != "QUEUED":
                        raise RuntimeContractError(
                            f"running job {uid} cannot be placed in its physical rack domain"
                        )
                    capacity_blocked += 1
                    continue
                selected = min(
                    feasible,
                    key=lambda rack: (
                        (
                            (occupied_gpu[rack] + gpu)
                            / float(
                                rack_rows[rack].deliverable_active_gpu_capacity
                            )
                        ),
                        (
                            (occupied_power[rack] + power_kw)
                            / float(rack_rows[rack].rack_power_cap_kw)
                        ),
                        rack,
                    ),
                )
                selected_destination = str(
                    rack_rows[selected].idc_id
                )
                if selected_destination != destination:
                    if not config.spatial_workload_migration:
                        raise RuntimeContractError(
                            "non-spatial method selected a remote admission rack"
                        )
                    job.destination_idc = selected_destination
                    job.migration_state = (
                        "PRESTART_PLACED_DATASET_PRESTAGED"
                    )
                job.logical_rack_id = selected
                job.gang_membership = tuple(
                    f"{selected}:PFR-GPU:{uid}:{index}"
                    for index in range(gpu)
                )
                assigned += 1
            occupied_gpu[selected] += gpu
            occupied_power[selected] += power_kw
            if (
                occupied_gpu[selected]
                > float(rack_rows[selected].deliverable_active_gpu_capacity)
                + 1e-9
                or occupied_power[selected]
                > float(rack_rows[selected].rack_power_cap_kw) + 1e-9
            ):
                raise RuntimeContractError(
                    f"physical rack occupancy exceeds retained capacity: {selected}"
                )
        return {
            "assigned_jobs": assigned,
            "capacity_blocked_jobs": capacity_blocked,
            "occupied_gpu_by_rack": occupied_gpu,
            "occupied_power_kw_by_rack": occupied_power,
        }

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
        phase_envelope_evidence: dict[str, Any] = {
            "authority": "BALANCED_REFERENCE_FIRST_ISSUE",
            "causal_lag_steps": None,
        }
        if state.last_exact is not None:
            previous_vmin = float(state.last_exact["voltage_min_pu"])
            previous_vmax = float(state.last_exact["voltage_max_pu"])
            lower_stress = max(0.0, (1.0 - previous_vmin) / 0.05)
            upper_stress = max(0.0, (previous_vmax - 1.0) / 0.05)
            balanced_vpu = np.sqrt(kernel.reference_u / kernel.nominal_u)
            delta_p = np.zeros(len(kernel.nodes), dtype=float)
            delta_q = np.zeros(len(kernel.nodes), dtype=float)
            for mid in MESS_IDS:
                service = state.mess_location[mid]
                bus = kernel.index[kernel.service_bus[service]]
                delta_p[bus] -= float(state.last_committed_mess_p_kw[mid])
                delta_q[bus] -= float(state.last_committed_mess_q_kvar[mid])
            action_du = (
                delta_p @ kernel.voltage_p.T
                + delta_q @ kernel.voltage_q.T
            )
            balanced_action_vpu = np.sqrt(
                np.maximum(kernel.reference_u + action_du, 1e-12)
                / kernel.nominal_u
            )
            if upper_stress >= lower_stress:
                dominant = "UPPER"
                shift = previous_vmax - float(np.max(balanced_action_vpu))
            else:
                dominant = "LOWER"
                shift = previous_vmin - float(np.min(balanced_action_vpu))
            corrected_vpu = balanced_vpu + shift
            if np.any(corrected_vpu <= 0.0):
                raise RuntimeContractError("causal phase-envelope correction is invalid")
            kernel.reference_u = kernel.nominal_u * corrected_vpu**2
            phase_envelope_evidence = {
                "authority": "PREVIOUS_COMMITTED_FRESH_AC_PHASE_ENVELOPE",
                "causal_lag_steps": 1,
                "dominant_boundary": dominant,
                "previous_minimum_voltage_pu": previous_vmin,
                "previous_maximum_voltage_pu": previous_vmax,
                "balanced_vpu_shift": float(shift),
                "future_actual_used": False,
            }
        kernel.phase_envelope_evidence = phase_envelope_evidence
        self._kernels[method_key] = kernel
        self._kernel_issue[method_key] = int(frame.issue)
        self._static_context_by_method[method_key] = static
        return kernel

    def evaluate_h0_surrogate(
        self,
        *,
        method_key: str,
        state: MutableMethodState,
        frame: CausalExperimentFrame,
        facility_it_kw: Sequence[float],
        mess_p_kw: Sequence[float],
        mess_q_kvar: Sequence[float],
        mess_location: Sequence[str],
    ) -> Mapping[str, float | str]:
        """Score one fixed H0 action with the live issue's causal surrogate."""

        if self._kernel_issue.get(method_key) != int(frame.issue):
            audit_root = (
                self.output_root
                / "_H0_FIDELITY"
                / method_key
                / f"issue_{frame.issue:06d}"
            )
            audit_root.mkdir(parents=True, exist_ok=True)
            self._issue_kernel(
                method_key=method_key,
                state=state,
                frame=frame,
                output=audit_root,
            )
        kernel = self._kernels[method_key]
        idc = np.repeat(
            np.asarray(tuple(facility_it_kw), dtype=float)[None, :],
            PLANNING_HORIZON_STEPS,
            axis=0,
        )
        mess_p = np.repeat(
            np.asarray(tuple(mess_p_kw), dtype=float)[None, :],
            PLANNING_HORIZON_STEPS,
            axis=0,
        )
        mess_q = np.repeat(
            np.asarray(tuple(mess_q_kvar), dtype=float)[None, :],
            PLANNING_HORIZON_STEPS,
            axis=0,
        )
        locations = [
            [str(service)] * PLANNING_HORIZON_STEPS
            for service in mess_location
        ]
        result = kernel.evaluate(frame, idc, mess_p, mess_q, locations)
        return {
            "worst": float(result.per_step[0]),
            "voltage": float(result.voltage[0]),
            "line": float(result.line[0]),
            "transformer": float(result.transformer[0]),
            "phase_envelope_authority": str(
                kernel.phase_envelope_evidence["authority"]
            ),
        }

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
        migration_authority: MigrationAuthority,
    ) -> tuple[
        tuple[str, ...],
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
        all_queued: list[tuple[str, Any]] = []
        for uid, job in sorted(state.jobs.items()):
            if job.lifecycle == "COMPLETED":
                continue
            if job.lifecycle == "QUEUED":
                all_queued.append((uid, job))
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
        # The resident MILP owns a bounded causal decision frontier, not the
        # entire visible queue.  Optimize the most urgent jobs and preserve
        # the remaining backlog in runtime state for later rolling horizons.
        # Treating the model slot count as a queue-size limit made legitimate
        # burst arrivals structurally infeasible.
        all_queued.sort(
            key=lambda item: (
                item[1].source.latest_start_step,
                item[1].source.deadline_step,
                item[1].source.arrival_step,
                item[0],
            )
        )
        slot_capacity = self._job_slot_capacity_by_method.get(
            config.comparison_method_id.value,
            MAX_ONLINE_QUEUED_JOBS,
        )
        queued = all_queued[:slot_capacity]
        deferred_queued = all_queued[slot_capacity:]
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
        # Rack identity changes GPU/rack feasibility but not the radial-grid
        # injection produced by an otherwise identical job placement.  The
        # old nested loop recomputed the same H54 electrical score once per
        # admissible rack, which became the dominant runtime for burst queues
        # (issue 2069 evaluated 11,808 choices).  Cache only the electrical
        # score; every rack-specific hard-cap and WAN check still runs.
        electrical_score_cache: dict[
            tuple[str, int, int, float], tuple[float, float]
        ] = {}
        electrical_score_evaluations = 0
        electrical_score_cache_hits = 0
        option_sets: list[tuple[_WorkloadOption, ...]] = []
        no_bounded_option_job_ids: list[str] = []
        candidate_selection_mode = (
            "GLOBAL_ELECTRICAL_SCORE_TOP_K"
            if self.candidate_limit <= 16
            else "DESTINATION_OFFSET_BALANCED_THEN_RACK_ROUND_ROBIN"
        )
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
                offsets = []
            elif config.temporal_workload_shift:
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
                        # The frozen placement authority declares the dataset
                        # pre-staged at all 12 IDCs.  A queued-job placement
                        # therefore transfers zero bytes; the separate 80-GB
                        # checkpoint payload applies only to a running-job
                        # migration.  Charging the historical input-size
                        # sensitivity here made burst placement impossible and
                        # contradicted the declared residency mode.
                        required_gb = 0.0
                        if (
                            destination != job.source.origin_idc
                            and migration_authority.dataset_residency_mode
                            != "PRESTAGED_AT_ALL_12_IDCS"
                        ):
                            raise RuntimeContractError(
                                "remote queued placement lacks dataset residency authority"
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
                        power_kw = float(row["IT_power_kW"])
                        score_key = (destination, offset, end, power_kw)
                        electrical_score = electrical_score_cache.get(score_key)
                        if electrical_score is None:
                            trial = running_it.copy()
                            trial[offset:end, IDCS.index(destination)] += power_kw
                            result = kernel.evaluate(
                                frame, trial, zero_mess, zero_mess, locations
                            )
                            electrical_score = (
                                float(result.objective[0]),
                                float(result.objective[1]),
                            )
                            electrical_score_cache[score_key] = electrical_score
                            electrical_score_evaluations += 1
                        else:
                            electrical_score_cache_hits += 1
                        score = (
                            electrical_score[0],
                            electrical_score[1],
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
                # A capacity burst can legitimately leave an urgent whole gang
                # without a placement in this rolling H54 window.  Keep an
                # empty option set: the resident model's explicit deferral
                # decision preserves the job in the visible runtime queue.
                # Physical capacity and deadlines remain unchanged.
                no_bounded_option_job_ids.append(uid)
            selected = self._select_resilient_workload_options(
                feasible,
                self.candidate_limit,
            )
            candidate_selection_mode = (
                "GLOBAL_ELECTRICAL_SCORE_TOP_K"
                if self.candidate_limit <= 16
                else "GLOBAL_TOP16_THEN_DESTINATION_OFFSET_RACK_DIVERSITY"
            )
            bounded_removed += len(feasible) - len(selected)
            option_sets.append(tuple(selected))
        return (
            tuple(uid for uid, _job in queued),
            tuple(uid for uid, _job in deferred_queued),
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
                "candidate_selection_mode": candidate_selection_mode,
                "electrical_score_evaluations": electrical_score_evaluations,
                "electrical_score_cache_hits": electrical_score_cache_hits,
                "visible_queued_jobs": len(all_queued),
                "optimized_queued_jobs": len(queued),
                "deferred_queued_jobs": len(deferred_queued),
                "no_bounded_option_jobs": len(no_bounded_option_job_ids),
                "no_bounded_option_job_ids": no_bounded_option_job_ids,
                "queued_domain_limit": slot_capacity,
                "queued_dataset_residency_mode": (
                    migration_authority.dataset_residency_mode
                ),
                "queued_remote_placement_transfer_bytes": 0,
            },
        )

    @staticmethod
    def _select_resilient_workload_options(
        feasible: Sequence[_WorkloadOption],
        limit: int,
    ) -> list[_WorkloadOption]:
        """Preserve legacy K<=16 and add diversity only beyond that prefix."""

        ranked = sorted(feasible, key=lambda option: option.generation_score)
        if limit <= 16 or len(ranked) <= 16:
            return ranked[:limit]

        # _prepare_domain builds one maximum-K superset and slices it for every
        # retry.  Its first 16 entries must therefore remain the former global
        # order so K=4/8/16 decisions and state hashes stay unchanged.
        diverse = PersistentBoundedMilpPlanner._select_diverse_workload_options(
            feasible,
            len(feasible),
        )
        selected = ranked[:16]
        selected_set = set(selected)
        selected.extend(option for option in diverse if option not in selected_set)
        return selected[:limit]

    @staticmethod
    def _select_diverse_workload_options(
        feasible: Sequence[_WorkloadOption],
        limit: int,
    ) -> list[_WorkloadOption]:
        """Truncate without destroying aggregate placement feasibility.

        Electrical score ties are common: rack identity does not change the
        radial injection, and a burst can give many jobs the same best IDC and
        start offset.  A plain global top-K consequently filled every bounded
        domain with near-duplicates.  Increasing K then added more racks at
        that same IDC before exposing another IDC/time bin, so a physically
        feasible burst could remain master-infeasible solely because of the
        truncation order.

        Preserve the best electrical ordering *between* choices while first
        covering distinct (destination, start-offset) bins.  Within each bin,
        round-robin racks before taking a second option from a rack.  This
        makes K a latency/quality knob rather than an accidental site-capacity
        restriction.  The exact rack/IDC/GPU/WAN checks above and the master,
        exact QCP recourse, and Fresh OpenDSS gates remain unchanged.
        """

        if limit <= 0 or not feasible:
            return []

        ranked = sorted(feasible, key=lambda option: option.generation_score)

        bin_options: dict[
            tuple[str, int], dict[str, list[_WorkloadOption]]
        ] = {}
        for option in ranked:
            group = bin_options.setdefault(
                (option.destination, option.start_offset),
                {},
            )
            group.setdefault(option.rack, []).append(option)

        # Each bin's sequence covers all admissible racks before repeating a
        # rack.  Keys are ordered by their best original electrical score.
        bin_sequences: dict[tuple[str, int], list[_WorkloadOption]] = {}
        for key, racks in bin_options.items():
            rack_order = sorted(
                racks,
                key=lambda rack: racks[rack][0].generation_score,
            )
            sequence: list[_WorkloadOption] = []
            depth = 0
            while True:
                added = False
                for rack in rack_order:
                    if depth < len(racks[rack]):
                        sequence.append(racks[rack][depth])
                        added = True
                if not added:
                    break
                depth += 1
            bin_sequences[key] = sequence

        destination_bins: dict[str, list[tuple[str, int]]] = {}
        for key in bin_sequences:
            destination_bins.setdefault(key[0], []).append(key)
        for destination, keys in destination_bins.items():
            keys.sort(key=lambda key: bin_sequences[key][0].generation_score)

        destination_order = sorted(
            destination_bins,
            key=lambda destination: min(
                bin_sequences[key][0].generation_score
                for key in destination_bins[destination]
            ),
        )

        # First cover the best time bin at every IDC, then the second-best bin
        # at every IDC, and so on.  Only after all site/time bins are exposed
        # do we consume second-rack/deeper choices from those bins.
        ordered_bins: list[tuple[str, int]] = []
        bin_depth = 0
        while True:
            added = False
            for destination in destination_order:
                keys = destination_bins[destination]
                if bin_depth < len(keys):
                    ordered_bins.append(keys[bin_depth])
                    added = True
            if not added:
                break
            bin_depth += 1

        selected: list[_WorkloadOption] = []
        option_depth = 0
        while len(selected) < limit:
            added = False
            for key in ordered_bins:
                sequence = bin_sequences[key]
                if option_depth < len(sequence):
                    selected.append(sequence[option_depth])
                    added = True
                    if len(selected) == limit:
                        break
            if not added:
                break
            option_depth += 1
        return selected

    def _prepare_domain(
        self,
        *,
        kernel: _RadialStressKernel,
        static: Mapping[str, Any],
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        migration_authority: MigrationAuthority,
        effective_steps: int,
        output: Path,
    ) -> _PreparedOnlineDomain:
        method_key = config.comparison_method_id.value
        target_limit = self.candidate_limit
        superset_limit = (
            self.base_candidate_limit
            if self.candidate_limit_frozen
            else self.adaptive_candidate_max
        )
        cache_key = (
            int(frame.issue),
            str(state.pre_state_sha256),
            int(effective_steps),
            int(superset_limit),
        )
        cached = self._adaptive_domain_cache_by_method.get(method_key)
        cache_reused = cached is not None and cached[:4] == cache_key
        if cache_reused:
            superset = cached[4]
        else:
            # Ranking every exact-hard-feasible choice already dominates the
            # cost; retaining the first 16 instead of the first 4 is nearly
            # free.  Generate one preregistered superset so a K expansion can
            # slice it without repeating thousands of causal grid scores.
            self.candidate_limit = superset_limit
            try:
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
                    deferred_queued,
                    options,
                    running_it,
                    running_gpu,
                    rack_gpu,
                    rack_power,
                    wan_capacity,
                    workload_audit,
                ) = self._workload_domain(
                    kernel=kernel,
                    state=state,
                    config=config,
                    frame=frame,
                    migration_authority=migration_authority,
                )
            finally:
                self.candidate_limit = target_limit
            superset = _PreparedOnlineDomain(
                effective_steps=int(effective_steps),
                route_options=routes,
                queued_job_ids=queued,
                deferred_queued_job_ids=deferred_queued,
                job_options=options,
                running_it_kw=running_it,
                running_gpu=running_gpu,
                running_rack_gpu=rack_gpu,
                running_rack_power_kw=rack_power,
                wan_capacity_gb=wan_capacity,
                route_audit=route_audit,
                workload_audit=workload_audit,
            )
            self._adaptive_domain_cache_by_method[method_key] = (*cache_key, superset)

        route_target_limit = target_limit
        if (
            bool(config.h54_capability_mask["mess_mobility"])
            and not self.candidate_limit_frozen
        ):
            # Route ranking is only a causal screen.  Unlike workload options,
            # retaining K=4 can erase the mobility treatment by admitting
            # several near-duplicate departures but omitting the destination
            # that wins the full H54 recourse.  The persistent model already
            # reserves the adaptive K=64 route axis, so exposing a compact,
            # destination-balanced K=16 route set adds no model-build memory.
            route_target_limit = min(
                superset_limit,
                max(target_limit, MOBILITY_ROUTE_CANDIDATE_MIN_K),
            )
        routes = tuple(superset.route_options[:route_target_limit])
        options = tuple(
            tuple(job_options[:target_limit])
            for job_options in superset.job_options
        )
        route_audit = dict(superset.route_audit)
        route_audit.update(
            {
                "candidate_limit_k": route_target_limit,
                "base_candidate_limit_k": target_limit,
                "mobility_route_candidate_floor_k": (
                    MOBILITY_ROUTE_CANDIDATE_MIN_K
                    if bool(config.h54_capability_mask["mess_mobility"])
                    and not self.candidate_limit_frozen
                    else None
                ),
                "bounded_domain_size": len(routes),
                "bounded_truncation_removed": max(
                    0,
                    int(
                        route_audit.get(
                            "feasibility_preserving_domain_size", len(routes)
                        )
                    )
                    - len(routes),
                ),
                "adaptive_superset_candidate_limit_k": superset_limit,
                "adaptive_superset_reused": cache_reused,
                "bounded_candidates": list(
                    route_audit.get("bounded_candidates", [])[
                        :route_target_limit
                    ]
                ),
                "selected_actionable_candidate_count": sum(
                    row.get("departure_offset") is not None
                    and int(row["departure_offset"])
                    < int(route_audit.get("commitment_window_steps", 1))
                    for row in route_audit.get("bounded_candidates", [])[
                        :route_target_limit
                    ]
                ),
            }
        )
        workload_audit = dict(superset.workload_audit)
        bounded_workload_size = sum(map(len, options))
        workload_audit.update(
            {
                "candidate_limit_k_per_job": target_limit,
                "bounded_domain_size": bounded_workload_size,
                "bounded_feasible_choices_removed": max(
                    0,
                    int(
                        workload_audit.get(
                            "domain_after_exact_safe", bounded_workload_size
                        )
                    )
                    - bounded_workload_size,
                ),
                "adaptive_superset_candidate_limit_k": superset_limit,
                "adaptive_superset_reused": cache_reused,
            }
        )
        return _PreparedOnlineDomain(
            effective_steps=int(effective_steps),
            route_options=routes,
            queued_job_ids=superset.queued_job_ids,
            deferred_queued_job_ids=superset.deferred_queued_job_ids,
            job_options=options,
            running_it_kw=superset.running_it_kw,
            running_gpu=superset.running_gpu,
            running_rack_gpu=superset.running_rack_gpu,
            running_rack_power_kw=superset.running_rack_power_kw,
            wan_capacity_gb=superset.wan_capacity_gb,
            route_audit=route_audit,
            workload_audit=workload_audit,
        )

    @staticmethod
    def _is_candidate_truncation_infeasibility(error: BaseException) -> bool:
        message = str(error)
        return (
            (
                "hierarchical slow_master multiobjective solve failed" in message
                or "hierarchical slow_master admission gate solve failed"
                in message
            )
            and "status=INFEASIBLE" in message
        )

    def _candidate_expansion_grid(self) -> tuple[int, ...]:
        maximum = (
            self.base_candidate_limit
            if self.candidate_limit_frozen
            else self.adaptive_candidate_max
        )
        return tuple(
            candidate
            for candidate in ALLOWED_DEVELOPMENT_K
            if self.base_candidate_limit <= candidate <= maximum
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
        """Solve at the fast base K, expanding only on proven truncation.

        Candidate K is a latency control, not a physical feasibility limit.
        A base-K master can therefore be infeasible solely because the useful
        route or placement was ranked outside the truncated domain.  Preserve
        the common-case K=4 latency, but rebuild at the next preregistered K
        after an actual slow-master INFEASIBLE status.  Every successful
        attempt still passes the same recourse, exact norm audit, and Fresh
        OpenDSS commit authority.
        """

        method_key = config.comparison_method_id.value
        if self.candidate_limit != self.base_candidate_limit:
            self.candidate_limit = self.base_candidate_limit

        attempted: list[int] = []
        infeasible_messages: list[str] = []
        deferred_expansion_attempts = 0
        admission_screen_attempts: list[int] = []
        admission_screen_solve_seconds = 0.0
        admission_screen_total_seconds = 0.0
        admission_screen_model_build_seconds = 0.0
        candidate_attempt_timings: list[Mapping[str, Any]] = []
        candidate_search_started = time.monotonic()
        expansion_grid = self._candidate_expansion_grid()
        visible_queue = any(
            job.lifecycle == "QUEUED" for job in state.jobs.values()
        )
        admission_screen_required = (
            not self.candidate_limit_frozen and visible_queue
        )
        for candidate_limit in expansion_grid:
            if self.candidate_limit != candidate_limit:
                self.candidate_limit = candidate_limit
            # The admission screen exists only to detect candidate-truncated
            # queue deferral before the full lexicographic solve.  With no
            # visible queued jobs the deferred count is identically zero, so
            # solving the master once as a screen and then again for the full
            # plan is pure duplicate work.  Route-domain infeasibility remains
            # protected by the full solve's existing adaptive-K exception path.
            admission_screen_only = admission_screen_required
            attempted.append(candidate_limit)
            try:
                attempt_started = time.monotonic()
                plan, certificate = self._solve_current_candidate_limit(
                    state=state,
                    config=config,
                    frame=frame,
                    migration_authority=migration_authority,
                    evaluation_steps_remaining=evaluation_steps_remaining,
                    admission_screen_only=admission_screen_only,
                )
                candidate_attempt_timings.append(
                    {
                        "candidate_limit_k": candidate_limit,
                        "mode": (
                            "ADMISSION_SCREEN"
                            if admission_screen_only
                            else "FULL_LEXICOGRAPHIC_RECOURSE"
                        ),
                        "wall_seconds": time.monotonic() - attempt_started,
                    }
                )
                if admission_screen_only:
                    admission_screen_attempts.append(candidate_limit)
                    admission_screen_solve_seconds += float(
                        certificate.get("admission_gate_solve_seconds", 0.0)
                    )
                    admission_screen_total_seconds += float(
                        certificate.get("admission_screen_total_seconds", 0.0)
                    )
                    admission_screen_model_build_seconds += float(
                        certificate.get(
                            "admission_screen_model_build_seconds", 0.0
                        )
                    )
                    screen_workload = certificate.get(
                        "workload_domain_reduction", {}
                    )
                    screen_unavoidable = int(
                        screen_workload.get("no_bounded_option_jobs", 0)
                        if isinstance(screen_workload, Mapping)
                        else 0
                    )
                    screen_deferred = int(
                        certificate.get("optimized_deferred_job_count", 0)
                    )
                    if (
                        screen_deferred > screen_unavoidable
                        and candidate_limit != expansion_grid[-1]
                    ):
                        deferred_expansion_attempts += 1
                        continue
                    attempt_started = time.monotonic()
                    plan, certificate = self._solve_current_candidate_limit(
                        state=state,
                        config=config,
                        frame=frame,
                        migration_authority=migration_authority,
                        evaluation_steps_remaining=evaluation_steps_remaining,
                        admission_ceiling_deferred_count=screen_deferred,
                    )
                    candidate_attempt_timings.append(
                        {
                            "candidate_limit_k": candidate_limit,
                            "mode": "FULL_LEXICOGRAPHIC_RECOURSE",
                            "wall_seconds": time.monotonic() - attempt_started,
                        }
                    )
            except RuntimeContractError as error:
                if not self._is_candidate_truncation_infeasibility(error):
                    raise
                infeasible_messages.append(str(error))
                if candidate_limit == expansion_grid[-1]:
                    raise RuntimeContractError(
                        "adaptive candidate expansion exhausted after genuine "
                        "slow-master infeasibility: "
                        f"attempted_k={attempted} final_error={error}"
                    ) from error
                continue
            optimized_deferred = int(
                certificate.get("optimized_deferred_job_count", 0)
            )
            workload_reduction = certificate.get(
                "workload_domain_reduction", {}
            )
            unavoidable_deferred = int(
                workload_reduction.get("no_bounded_option_jobs", 0)
                if isinstance(workload_reduction, Mapping)
                else 0
            )
            if (
                optimized_deferred > unavoidable_deferred
                and not self.candidate_limit_frozen
                and candidate_limit != expansion_grid[-1]
            ):
                # A K-truncated option set can make a job appear deferrable even
                # though a later exact-safe candidate admits it.  Expand before
                # accepting deferral, just as the former infeasibility path did.
                deferred_expansion_attempts += 1
                continue
            evidence = dict(certificate)
            evidence.update(
                {
                    "candidate_limit_base_k": self.base_candidate_limit,
                    "candidate_limit_attempts": list(attempted),
                    "candidate_limit_adaptive_max_k": (
                        self.base_candidate_limit
                        if self.candidate_limit_frozen
                        else self.adaptive_candidate_max
                    ),
                    "candidate_limit_adaptive_expansion_used": (
                        len(attempted) > 1
                    ),
                    "candidate_limit_infeasible_attempt_count": len(
                        infeasible_messages
                    ),
                    "candidate_limit_deferred_attempt_count": (
                        deferred_expansion_attempts
                    ),
                    "candidate_limit_admission_screen_attempts": list(
                        admission_screen_attempts
                    ),
                    "candidate_limit_admission_screen_solve_seconds": (
                        admission_screen_solve_seconds
                    ),
                    "candidate_limit_admission_screen_total_seconds": (
                        admission_screen_total_seconds
                    ),
                    "candidate_limit_admission_screen_model_build_seconds": (
                        admission_screen_model_build_seconds
                    ),
                    "candidate_limit_admission_screen_skipped_reason": (
                        "CANDIDATE_K_FROZEN"
                        if self.candidate_limit_frozen
                        else (
                            "NO_VISIBLE_QUEUED_JOBS"
                            if not visible_queue
                            else None
                        )
                    ),
                    "candidate_limit_attempt_timings": list(
                        candidate_attempt_timings
                    ),
                    "candidate_limit_search_total_seconds": (
                        time.monotonic() - candidate_search_started
                    ),
                    "candidate_limit_unavoidable_deferred_job_count": (
                        unavoidable_deferred
                    ),
                    "candidate_limit_expansion_avoided_reason": (
                        "ONLY_EXACT_INFEASIBLE_WORKLOADS_DEFERRED"
                        if optimized_deferred > 0
                        and optimized_deferred == unavoidable_deferred
                        and len(attempted) == 1
                        else None
                    ),
                    "candidate_limit_expansion_reason": (
                        (
                            "BASE_DOMAIN_CAPACITY_DEFERRAL"
                            if deferred_expansion_attempts
                            else "BASE_DOMAIN_SLOW_MASTER_INFEASIBLE"
                        )
                        if len(attempted) > 1
                        else None
                    ),
                }
            )
            if plan is None:
                raise RuntimeContractError(
                    "candidate admission screen returned without a full plan"
                )
            return plan, evidence
        raise RuntimeContractError("adaptive candidate expansion grid is empty")

    def _solve_current_candidate_limit(
        self,
        *,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        migration_authority: Optional[MigrationAuthority],
        evaluation_steps_remaining: int,
        admission_screen_only: bool = False,
        admission_ceiling_deferred_count: Optional[int] = None,
    ) -> tuple[Optional[SlowDiscretePlan], Mapping[str, Any]]:
        if migration_authority is None:
            raise RuntimeContractError(
                "persistent planner requires migration/dataset residency authority"
            )
        migration_authority.validate()
        total_started = time.monotonic()
        method_key = config.comparison_method_id.value
        visible_queue = sum(
            job.lifecycle == "QUEUED" for job in state.jobs.values()
        )
        current_slots = self._job_slot_capacity_by_method.get(
            method_key, MAX_ONLINE_QUEUED_JOBS
        )
        required_slots = min(
            MAX_DYNAMIC_QUEUED_JOB_SLOTS,
            max(MAX_ONLINE_QUEUED_JOBS, visible_queue),
        )
        grown_slots = min(
            MAX_DYNAMIC_QUEUED_JOB_SLOTS,
            1 << (required_slots - 1).bit_length(),
        )
        model_refresh_reason: str | None = None
        if grown_slots > current_slots:
            self._dispose_method_models(method_key)
            self._model_solve_generation_by_method[method_key] = 0
            model_refresh_reason = "JOB_SLOT_CAPACITY_GROWTH"
            current_slots = grown_slots
        elif (
            self._model_solve_generation_by_method.get(method_key, 0)
            >= self.max_persistent_solve_reuses
        ):
            # Gurobi's retained multiobjective reoptimization state can become
            # substantially slower than a cold model after repeated RHS and
            # coefficient updates.  Bound that numerical state age without
            # changing the mathematical model or any accepted decision.
            self._dispose_method_models(method_key)
            self._model_solve_generation_by_method[method_key] = 0
            model_refresh_reason = "PERIODIC_NUMERICAL_STATE_REFRESH"
        self._job_slot_capacity_by_method[method_key] = current_slots
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
            migration_authority=migration_authority,
            effective_steps=min(
                PLANNING_HORIZON_STEPS, int(evaluation_steps_remaining)
            ),
            output=issue_root,
        )
        domain_seconds = time.monotonic() - domain_started
        # A queued workload is never a mathematically forced domain: even a
        # single placement option can conflict jointly with other gangs or the
        # grid.  The slow master must retain the explicit queue-deferral choice.
        slow_domain_forced = (
            len(domain.route_options) == 1 and not domain.job_options
        )
        build_seconds = 0.0
        needs_master = (
            not slow_domain_forced
            and method_key not in self._master_models
        )
        needs_recourse = (
            not admission_screen_only
            and method_key not in self._recourse_models
        )
        if needs_master or needs_recourse:
            if model_refresh_reason is None:
                model_refresh_reason = "INITIAL_MODEL_BUILD"
            build_started = time.monotonic()
            common_model_kwargs = {
                # Keep one resident superset skeleton and mask options above
                # the active K through bounds in update().  Rebuilding and
                # disposing two large Gurobi models at every 4/8/16/32/64
                # expansion dominated the solve itself.
                "candidate_limit": (
                    self.base_candidate_limit
                    if self.candidate_limit_frozen
                    else self.adaptive_candidate_max
                ),
                "job_slot_capacity": current_slots,
                "static": self._static_context_by_method[method_key],
                "kernel": kernel,
                "rack_rows": {
                    str(row.rack_pool_id): row
                    for row in self.scope["cap"].itertuples(index=False)
                },
            }
            if needs_master:
                self._master_models[method_key] = _PersistentMilpModel(
                    **common_model_kwargs,
                    model_role="slow_master",
                )
            if needs_recourse:
                self._recourse_models[method_key] = _PersistentMilpModel(
                    **common_model_kwargs,
                    model_role="exact_recourse",
                )
            build_seconds = time.monotonic() - build_started
        master = self._master_models.get(method_key)
        recourse = self._recourse_models.get(method_key)
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
            if admission_ceiling_deferred_count is not None:
                master.set_admission_ceiling(
                    admission_ceiling_deferred_count
                )
        if not admission_screen_only:
            if recourse is None:
                raise RuntimeContractError("exact recourse model missing")
            recourse.update(**update_kwargs)
        update_seconds = time.monotonic() - update_started
        master_started = time.monotonic()
        shared_solve_started = master_started
        active_wall_budget = (
            self.bootstrap_wall_budget_seconds
            if build_seconds > 0.0
            else self.wall_budget_seconds
        )
        if admission_screen_only:
            if slow_domain_forced:
                screen_result = {
                    "capacity_admission_gate": 0.0,
                    "optimized_deferred_job_count": 0,
                    "admission_gate_solve_seconds": 0.0,
                }
            else:
                if master is None:
                    raise RuntimeContractError("slow master model missing")
                screen_result = master.solve_admission_gate(
                    wall_budget_seconds=self._shared_watchdog_budgets(
                        active_wall_budget
                    )
                )
            return None, {
                "candidate_limit_k": self.candidate_limit,
                "visible_queued_jobs": visible_queue,
                "mobility_domain_reduction": dict(domain.route_audit),
                "workload_domain_reduction": dict(domain.workload_audit),
                "capacity_admission_gate": screen_result[
                    "capacity_admission_gate"
                ],
                "optimized_deferred_job_count": screen_result[
                    "optimized_deferred_job_count"
                ],
                "admission_gate_solve_seconds": screen_result[
                    "admission_gate_solve_seconds"
                ],
                "admission_screen_model_build_seconds": build_seconds,
                "admission_screen_parameter_update_seconds": update_seconds,
                "admission_screen_total_seconds": time.monotonic()
                - total_started,
            }
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
                wall_budget_seconds=self._shared_watchdog_budgets(
                    active_wall_budget
                )
            )
            route_index, job_option_indices = master.selected_domain_decisions()
        master_seconds = time.monotonic() - master_started
        recourse_started = time.monotonic()
        if recourse is None:
            raise RuntimeContractError("exact recourse model missing")
        recourse.fix_slow_decisions(
            route_index=route_index,
            job_option_indices=job_option_indices,
        )
        recourse_wall_budget = self._shared_watchdog_budgets(
            active_wall_budget,
            master_elapsed_seconds=time.monotonic() - shared_solve_started,
        )
        result = recourse.solve_lexicographic(
            wall_budget_seconds=recourse_wall_budget
        )
        plan = recourse.extract_plan(
            state=state,
            config=config,
            frame=frame,
            domain=domain,
        )
        recourse_seconds = time.monotonic() - recourse_started
        plan.validate()
        selected_route = domain.route_options[route_index]
        model_solve_generation = (
            self._model_solve_generation_by_method.get(method_key, 0) + 1
        )
        self._model_solve_generation_by_method[method_key] = model_solve_generation
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
            "persistent_model_candidate_capacity_k": (
                master.k if master is not None else recourse.k
            ),
            "resident_job_slot_capacity": current_slots,
            "visible_queued_jobs": visible_queue,
            "candidate_limit_frozen": self.candidate_limit_frozen,
            "mobility_domain_reduction": dict(domain.route_audit),
            "workload_domain_reduction": dict(domain.workload_audit),
            "capacity_admission_gate": result["capacity_admission_gate"],
            "capacity_admission_screen_ceiling_count": (
                admission_ceiling_deferred_count
            ),
            "optimized_deferred_job_count": result[
                "optimized_deferred_job_count"
            ],
            "solution_status": result["solution_status"],
            "actual_gurobi_used": True,
            "gurobi_slow_master_numeric_focus": (
                master.numeric_focus if master is not None else None
            ),
            "slow_master_mip_gap_tolerance": (
                master.mip_gap if master is not None else 0.0
            ),
            "gurobi_numeric_focus": recourse.numeric_focus,
            "selected_mobility_candidate": {
                "domain_index": int(route_index),
                "is_stay": bool(selected_route.is_stay),
                "departure_offset": selected_route.departure_offset,
                "destination_service_id": (
                    selected_route.destination_service_id
                ),
                "route_rank": int(selected_route.route_rank),
                "transit_steps": int(selected_route.transit_steps),
                "energy_kwh": float(selected_route.energy_kwh),
            },
            "persistent_model_reused": build_seconds == 0.0,
            "persistent_model_refresh_reason": model_refresh_reason,
            "persistent_model_solve_generation": model_solve_generation,
            "persistent_model_max_reuses": self.max_persistent_solve_reuses,
            "model_build_once_seconds": build_seconds,
            "cold_start_bootstrap_budget_used": build_seconds > 0.0,
            "active_planner_wall_budget_seconds": active_wall_budget,
            "shared_master_wall_budget_seconds": (
                self._shared_watchdog_budgets(active_wall_budget)
            ),
            "shared_recourse_wall_budget_seconds": recourse_wall_budget,
            "shared_watchdog_unused_master_seconds_transferred": max(
                0.0,
                self._shared_watchdog_budgets(active_wall_budget)
                - master_seconds,
            ),
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
            "maximum_exact_norm_relative_residual": result[
                "maximum_exact_norm_relative_residual"
            ],
            "norm_relative_tolerance": result["norm_relative_tolerance"],
            "norm_engineering_margin_fraction": result[
                "norm_engineering_margin_fraction"
            ],
            "norm_constraint_mode": result["norm_constraint_mode"],
            "norm_inner_polygon_sides": result["norm_inner_polygon_sides"],
            "norm_inner_polygon_max_radial_conservatism_fraction": result[
                "norm_inner_polygon_max_radial_conservatism_fraction"
            ],
            "exact_qcp_feasibility_restoration_rounds": result[
                "exact_qcp_feasibility_restoration_rounds"
            ],
            "exact_qcp_implied_tangent_cuts_added": result[
                "exact_qcp_implied_tangent_cuts_added"
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
            "planning_surrogate_grid_is_advisory": True,
            "planning_surrogate_stress_above_one_reportable": True,
            "hard_grid_candidate_pass": False,
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
        job_slot_capacity: int,
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
        self.job_slot_capacity = int(job_slot_capacity)
        if self.job_slot_capacity < MAX_ONLINE_QUEUED_JOBS:
            raise RuntimeContractError("persistent job-slot capacity is invalid")
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
        self.mip_gap = (
            SLOW_MASTER_MIP_GAP if model_role == "slow_master" else 0.03
        )
        self.model.Params.MIPGap = self.mip_gap
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
        self.norm_constraint_mode = os.environ.get(
            "PFR_NORM_CONSTRAINT_MODE", "INNER_POLYGON"
        ).upper()
        if self.norm_constraint_mode not in {"EXACT_QCP", "INNER_POLYGON"}:
            raise RuntimeContractError(
                "PFR_NORM_CONSTRAINT_MODE must be EXACT_QCP or INNER_POLYGON"
            )
        self.norm_inner_polygon_sides = int(
            os.environ.get("PFR_NORM_INNER_POLYGON_SIDES", "16")
        )
        if self.norm_inner_polygon_sides not in {8, 16, 32}:
            raise RuntimeContractError(
                "PFR_NORM_INNER_POLYGON_SIDES must be one of 8, 16, or 32"
            )
        self.exact_qcp_diagnostic = (
            model_role == "exact_recourse"
            and self.norm_constraint_mode == "EXACT_QCP"
        )
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
            for j in range(self.job_slot_capacity)
            for o in range(self.k)
        }
        self.defer_job = {
            j: self.model.addVar(
                lb=0.0,
                ub=1.0,
                vtype=discrete_type,
                name=f"defer_job[{j}]",
            )
            for j in range(self.job_slot_capacity)
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
            step: self.model.addVar(
                lb=0.0, ub=PLANNING_STRESS_EPIGRAPH_MAX, name=f"z[{step}]"
            )
            for step in range(self.h)
        }
        self.zmax = self.model.addVar(
            lb=0.0, ub=PLANNING_STRESS_EPIGRAPH_MAX, name="zmax"
        )
        self._build_constraints(kernel)
        self.model.update()
        self._last_job_mapping: dict[tuple[int, int], Optional[_WorkloadOption]] = {}
        self._last_dispatch_service: dict[tuple[str, int, int], Optional[str]] = {}
        self._last_route_energy: dict[tuple[int, int], float] = {}
        self._last_dep_reserve: dict[tuple[int, int], float] = {}
        self._cut_directions: set[tuple[str, str, int, int, int]] = set()
        self._cut_angles: dict[tuple[str, str, int], list[float]] = {}
        self._globally_refined_assets: set[tuple[str, str]] = set()
        if self.norm_constraint_mode == "INNER_POLYGON":
            self._add_inner_norm_constraints(self.norm_inner_polygon_sides)
        elif self.model_role == "slow_master":
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
                gp.quicksum(self.job[(j, o)] for o in range(self.k))
                + self.defer_job[j]
                == 0.0,
                name=f"job_one[{j}]",
            )
            for j in range(self.job_slot_capacity)
        }
        self.admission_ceiling = self.model.addConstr(
            gp.quicksum(self.defer_job.values())
            <= float(self.job_slot_capacity),
            name="admission_ceiling",
        )
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
        self.episode_terminal_debt = {}
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
            for boundary in range(1, self.h + 1):
                self.episode_terminal_debt[(mid, boundary)] = self.model.addConstr(
                    self.debt[(mid, boundary)] <= MESS_CAPACITY_KWH,
                    name=f"episode_terminal_debt[{mid},{boundary}]",
                )
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
                self.service_p[(service, step)] == 0.0,
                name=f"service_p_def[{service},{step}]",
            )
            for service in self.services
            for step in range(self.h)
        }
        self.service_q_def = {
            (service, step): self.model.addConstr(
                self.service_q[(service, step)] == 0.0,
                name=f"service_q_def[{service},{step}]",
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
                self.flow_p_def[(node, step)] = self.model.addConstr(
                    pexpr == 0.0, name=f"flow_p_def[{node},{step}]"
                )
                self.flow_q_def[(node, step)] = self.model.addConstr(
                    qexpr == 0.0, name=f"flow_q_def[{node},{step}]"
                )
        self.du_def = {}
        self.voltage_low = {}
        self.voltage_high = {}
        self.voltage_below = {}
        self.voltage_above = {}
        for step in range(self.h):
            self.du_def[(self.root, step)] = self.model.addConstr(
                self.du[(self.root, step)] == 0.0,
                name=f"du_def[{self.root},{step}]",
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
                self.du_def[(node, step)] = self.model.addConstr(
                    expr == 0.0, name=f"du_def[{node},{step}]"
                )
            for node in self.nodes:
                i = kernel.index[node]
                low = float(
                    kernel.nominal_u[i]
                    - kernel.reference_u[i]
                    - PLANNING_STRESS_EPIGRAPH_MAX
                    * (kernel.nominal_u[i] - kernel.low_u[i])
                )
                high = float(
                    kernel.nominal_u[i]
                    - kernel.reference_u[i]
                    + PLANNING_STRESS_EPIGRAPH_MAX
                    * (kernel.high_u[i] - kernel.nominal_u[i])
                )
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
                    >= below,
                    name=f"voltage_below[{node},{step}]",
                )
                self.voltage_above[(node, step)] = self.model.addConstr(
                    (kernel.high_u[i] - kernel.nominal_u[i]) * self.z[step]
                    - self.du[(node, step)]
                    >= above,
                    name=f"voltage_above[{node},{step}]",
                )
            self.model.addConstr(
                self.zmax >= self.z[step], name=f"zmax_epigraph[{step}]"
            )
            for site in IDCS:
                self.model.addConstr(
                    PUE * self.it[(site, step)]
                    <= IDC_TRANSFORMER_LIMIT_KW * self.z[step],
                    name=f"idc_transformer_stress[{site},{step}]",
                )
        # These retained rows lock priorities only for the non-native fallback
        # path.  They bound the reporting epigraph, not physical feasibility;
        # Fresh OpenDSS remains the H0 hard commit authority.
        self.primary_lock = self.model.addConstr(
            self.zmax <= PLANNING_STRESS_EPIGRAPH_MAX
        )
        self.secondary_lock = self.model.addConstr(
            STEP_HOURS * gp.quicksum(self.z.values())
            <= PLANNING_STRESS_EPIGRAPH_MAX * self.h * STEP_HOURS
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
            self.model.addConstr(lhs <= NORM_SAFE_LIMIT_FACTOR * PCS_KVA)
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

    def _add_inner_norm_constraints(self, sides: int) -> None:
        """Conservative polyhedral circle model for latency-sensitive runs.

        The intersection of regularly spaced halfspaces with apothem
        ``R*cos(pi/sides)`` is an inscribed polygon.  Every point admitted by
        these linear rows is therefore inside the physical Euclidean circle.
        This trades at most ``1-cos(pi/sides)`` radial capability for removal
        of the online QCP barrier while retaining the independent exact-norm
        audit and downstream Fresh OpenDSS hard gate.
        """

        apothem_factor = math.cos(math.pi / sides)
        directions = tuple(
            (
                math.cos(2.0 * math.pi * index / sides),
                math.sin(2.0 * math.pi * index / sides),
            )
            for index in range(sides)
        )
        for step in range(self.h):
            for node in self.nonroot:
                edge_key = (self.static["parent"][node], node)
                if edge_key not in self.static["lim"]:
                    continue
                limit = float(self.static["lim"][edge_key]) * apothem_factor
                for direction_p, direction_q in directions:
                    self.model.addConstr(
                        direction_p * self.flow_p[(node, step)]
                        + direction_q * self.flow_q[(node, step)]
                        <= limit * self.z[step],
                        name=(
                            f"inner_line_stress[{node},{step},"
                            f"{direction_p:.9f},{direction_q:.9f}]"
                        ),
                    )
            for service in self.services:
                limit = (
                    float(self.static["service_kva"][service])
                    * apothem_factor
                )
                for direction_p, direction_q in directions:
                    self.model.addConstr(
                        direction_p * self.service_p[(service, step)]
                        + direction_q * self.service_q[(service, step)]
                        <= limit * self.z[step],
                        name=(
                            f"inner_service_stress[{service},{step},"
                            f"{direction_p:.9f},{direction_q:.9f}]"
                        ),
                    )
            for mid in MESS_IDS:
                for route_index in self._route_axis(mid):
                    pnet = self._pnet(mid, route_index, step)
                    limit = (
                        NORM_SAFE_LIMIT_FACTOR * PCS_KVA * apothem_factor
                    )
                    for direction_p, direction_q in directions:
                        self.model.addConstr(
                            direction_p * pnet
                            + direction_q * self.q[(mid, route_index, step)]
                            <= limit,
                            name=(
                                f"inner_pcs_limit[{mid},{route_index},{step},"
                                f"{direction_p:.9f},{direction_q:.9f}]"
                            ),
                        )

    def _add_exact_norm_constraints(self) -> None:
        """Dimensionless exact-circle realization of the bounded domain.

        Writing these rows in raw kVA squared makes the solver's feasibility
        test depend on equipment size.  Every axis is therefore divided by an
        physical nameplate.  The nonlinear rows are O(1), and the independent
        acceptance audit uses the same dimensionless scale.  A separate zmax
        hard cap (and direct PCS cap) reserves engineering headroom without
        changing the paper-facing stress objective's physical normalization.
        """

        for step in range(self.h):
            for node in self.nonroot:
                edge_key = (self.static["parent"][node], node)
                if edge_key not in self.static["lim"]:
                    continue
                limit = float(self.static["lim"][edge_key])
                self.model.addQConstr(
                    (self.flow_p[(node, step)] / limit)
                    * (self.flow_p[(node, step)] / limit)
                    + (self.flow_q[(node, step)] / limit)
                    * (self.flow_q[(node, step)] / limit)
                    <= self.z[step] * self.z[step],
                    name=f"exact_line_norm[{node},{step}]",
                )
            for service in self.services:
                limit = float(self.static["service_kva"][service])
                self.model.addQConstr(
                    (self.service_p[(service, step)] / limit)
                    * (self.service_p[(service, step)] / limit)
                    + (self.service_q[(service, step)] / limit)
                    * (self.service_q[(service, step)] / limit)
                    <= self.z[step] * self.z[step],
                    name=f"exact_service_norm[{service},{step}]",
                )
            for mid in MESS_IDS:
                for r in self._route_axis(mid):
                    pnet = self._pnet(mid, r, step)
                    limit = NORM_SAFE_LIMIT_FACTOR * PCS_KVA
                    self.model.addQConstr(
                        (pnet / limit) * (pnet / limit)
                        + (self.q[(mid, r, step)] / limit)
                        * (self.q[(mid, r, step)] / limit)
                        <= 1.0,
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
        self.admission_ceiling.RHS = float(self.job_slot_capacity)
        mobile = MOBILITY_ELIGIBLE_MESS_IDS[0]
        dispatch_enabled = bool(config.h54_capability_mask["mess_dispatch"])
        fleet_recovery_pending = any(
            float(value) > 1e-9
            for value in state.mess_energy_debt_kwh.values()
        )
        effective_steps = int(domain.effective_steps)
        if not 1 <= effective_steps <= self.h:
            raise RuntimeContractError("effective episode horizon is invalid")
        for r in range(self.k):
            active = r < len(domain.route_options)
            self.route[r].LB = 0.0
            self.route[r].UB = 1.0 if active else 0.0
            route = domain.route_options[r] if active else None
            locations = (
                self._locations_for_route(state, route) if route is not None else [None] * self.h
            )
            for step in range(self.h):
                available = (
                    active
                    and step < effective_steps
                    and locations[step] is not None
                    and dispatch_enabled
                )
                key = (mobile, r, step)
                self.pdis[key].UB = (
                    P_MAX
                    if available
                    and not fleet_recovery_pending
                    else 0.0
                )
                self.pchg[key].UB = P_MAX if available else 0.0
                # The retained balanced model reverses the ranking of several
                # phase-specific PCC Q actions.  Until a three-phase reactive
                # sensitivity authority is frozen, Q is removed from the
                # admissible controller domain instead of being optimized on
                # a known-wrong direction.  Active-power flexibility remains.
                self.q[key].LB = 0.0
                self.q[key].UB = 0.0
                self.qabs[key].UB = 0.0
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
            due = state.mess_energy_recovery_due_issue.get(mid)
            recovery_boundary = (
                max(1, min(effective_steps, int(due) - int(frame.issue) + 1))
                if due is not None
                else effective_steps
            )
            terminal_rhs = _episode_terminal_debt_rhs(
                effective_steps,
                self.h,
                additional_zero_boundaries=(recovery_boundary,),
            )
            for boundary in range(1, self.h + 1):
                self.episode_terminal_debt[(mid, boundary)].RHS = (
                    terminal_rhs[boundary - 1]
                )
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
                available = (
                    step < effective_steps
                    and not state.mess_in_transit[mid]
                    and dispatch_enabled
                )
                key = (mid, 0, step)
                self.pdis[key].UB = (
                    P_MAX
                    if available
                    and not fleet_recovery_pending
                    else 0.0
                )
                self.pchg[key].UB = P_MAX if available else 0.0
                self.q[key].LB = 0.0
                self.q[key].UB = 0.0
                self.qabs[key].UB = 0.0
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
                    self.mode[(mid, step)].UB = (
                        1.0 if step < effective_steps else 0.0
                    )

        # Clear and remap bounded workload-option coefficients.
        for key, old in tuple(self._last_job_mapping.items()):
            if old is not None:
                self._clear_job_coefficients(key, old)
        self._last_job_mapping.clear()
        for j in range(self.job_slot_capacity):
            active_job = j < len(domain.queued_job_ids)
            self.job_one[j].RHS = 1.0 if active_job else 0.0
            self.defer_job[j].LB = 0.0
            self.defer_job[j].UB = 1.0 if active_job else 0.0
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
                    kernel.nominal_u[i]
                    - kernel.reference_u[i]
                    - PLANNING_STRESS_EPIGRAPH_MAX
                    * (kernel.nominal_u[i] - kernel.low_u[i])
                )
                self.voltage_high[(node, step)].RHS = float(
                    kernel.nominal_u[i]
                    - kernel.reference_u[i]
                    + PLANNING_STRESS_EPIGRAPH_MAX
                    * (kernel.high_u[i] - kernel.nominal_u[i])
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
        # Reoptimization must preserve the same engineering headroom as model
        # construction.  Resetting this row to 1.0 silently removed the
        # physical safety margin after the first persistent update.
        self.primary_lock.RHS = PLANNING_STRESS_EPIGRAPH_MAX
        self.secondary_lock.RHS = (
            PLANNING_STRESS_EPIGRAPH_MAX * self.h * STEP_HOURS
        )
        self.model.update()

    def set_admission_ceiling(self, deferred_job_count: int) -> None:
        """Keep lower-priority objectives from degrading screened admission."""

        ceiling = int(deferred_job_count)
        if not 0 <= ceiling <= self.job_slot_capacity:
            raise RuntimeContractError("admission ceiling is outside model slots")
        self.admission_ceiling.RHS = float(ceiling)
        self.model.update()

    def selected_domain_decisions(self) -> tuple[int, dict[int, Optional[int]]]:
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
        jobs: dict[int, Optional[int]] = {}
        for j, options in enumerate(self.domain.job_options):
            hits = [
                o for o in range(len(options)) if float(self.job[(j, o)].X) > 0.5
            ]
            deferred = float(self.defer_job[j].X) > 0.5
            if len(hits) + int(deferred) != 1:
                raise RuntimeContractError(
                    "slow master job admission decision is not integral "
                    f"j={j}: options={hits} deferred={deferred}"
                )
            jobs[j] = None if deferred else hits[0]
        return route_hits[0], jobs

    def fix_slow_decisions(
        self,
        *,
        route_index: int,
        job_option_indices: Mapping[int, Optional[int]],
    ) -> None:
        """Fix slow binaries so the second level is an exact continuous QCP."""

        if self.model_role != "exact_recourse" or self.domain is None:
            raise RuntimeContractError("slow decisions can only fix exact recourse")
        for r in range(self.k):
            value = 1.0 if r == int(route_index) else 0.0
            self.route[r].LB = value
            self.route[r].UB = value
        for j in range(self.job_slot_capacity):
            options = self.domain.job_options[j] if j < len(self.domain.job_options) else ()
            chosen = job_option_indices.get(j)
            deferred = j < len(self.domain.job_options) and chosen is None
            self.defer_job[j].LB = 1.0 if deferred else 0.0
            self.defer_job[j].UB = 1.0 if deferred else 0.0
            for o in range(self.k):
                value = 1.0 if chosen is not None and o == int(chosen) else 0.0
                if o >= len(options):
                    value = 0.0
                self.job[(j, o)].LB = value
                self.job[(j, o)].UB = value
        self.model.update()

    def _exact_norm_residuals(
        self,
    ) -> tuple[
        float,
        float,
        list[tuple[str, str, int, float, float]],
    ]:
        violations: list[tuple[str, str, int, float, float]] = []
        maximum_kva = 0.0
        maximum_relative = 0.0
        for step in range(self.h):
            z = float(self.z[step].X)
            for node in self.nonroot:
                edge_key = (self.static["parent"][node], node)
                if edge_key not in self.static["lim"]:
                    continue
                p = float(self.flow_p[(node, step)].X)
                q = float(self.flow_q[(node, step)].X)
                nameplate = float(self.static["lim"][edge_key])
                norm = math.hypot(p, q)
                residual_kva = norm - nameplate * z
                residual_relative = residual_kva / nameplate
                maximum_kva = max(maximum_kva, residual_kva)
                maximum_relative = max(maximum_relative, residual_relative)
                if residual_relative > NORM_RELATIVE_TOLERANCE:
                    violations.append(("LINE", node, step, p / norm, q / norm))
            for service in self.services:
                p = float(self.service_p[(service, step)].X)
                q = float(self.service_q[(service, step)].X)
                nameplate = float(self.static["service_kva"][service])
                norm = math.hypot(p, q)
                residual_kva = norm - nameplate * z
                residual_relative = residual_kva / nameplate
                maximum_kva = max(maximum_kva, residual_kva)
                maximum_relative = max(maximum_relative, residual_relative)
                if residual_relative > NORM_RELATIVE_TOLERANCE:
                    violations.append(
                        ("SERVICE", service, step, p / norm, q / norm)
                    )
            for mid in MESS_IDS:
                for r in self._route_axis(mid):
                    p = float(self._pnet(mid, r, step).getValue())
                    q = float(self.q[(mid, r, step)].X)
                    residual_kva = (
                        math.hypot(p, q)
                        - NORM_SAFE_LIMIT_FACTOR * PCS_KVA
                    )
                    residual_relative = residual_kva / PCS_KVA
                    maximum_kva = max(maximum_kva, residual_kva)
                    maximum_relative = max(maximum_relative, residual_relative)
                    if residual_relative > NORM_RELATIVE_TOLERANCE:
                        norm = math.hypot(p, q)
                        violations.append(
                            (f"PCS:{mid}", str(r), step, p / norm, q / norm)
                        )
        return (
            max(0.0, maximum_kva),
            max(0.0, maximum_relative),
            violations,
        )

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
                        norm
                        >= utilization_floor * NORM_SAFE_LIMIT_FACTOR * PCS_KVA
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
            if (
                not status_ok
                or not math.isfinite(gap)
                or gap > self.mip_gap + 1e-12
            ):
                raise RuntimeContractError(
                    "persistent MILP lacks its configured gap certificate: "
                    f"status={_status_name(self.GRB, self.model.Status)} gap={gap}"
                )
            separation_started = time.monotonic()
            (
                maximum_residual_kva,
                maximum_relative_residual,
                violations,
            ) = self._exact_norm_residuals()
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
                    "maximum_residual": maximum_residual_kva,
                    "maximum_relative_residual": maximum_relative_residual,
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
                    f"max_kva={maximum_residual_kva} "
                    f"max_relative={maximum_relative_residual}"
                )
            self.model.update()
        raise RuntimeContractError(
            "persistent MILP exhausted exact norm-separation rounds: "
            f"rounds={MAX_SEPARATION_ROUNDS} "
            f"max_residual_kva={maximum_residual_kva:.12g} "
            f"max_relative_residual={maximum_relative_residual:.12g} "
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

    def _admission_objective(self) -> Any:
        """Return the frozen whole-gang admission objective."""

        nslots = self.job_slot_capacity
        expression = self.gp.LinExpr()
        for j, variable in self.defer_job.items():
            expression += variable
            expression += (
                float(nslots - j) / float((nslots + 1) ** 2)
            ) * variable
        return expression

    def solve_admission_gate(
        self, *, wall_budget_seconds: float
    ) -> Mapping[str, Any]:
        """Screen an expanded domain without solving discarded priorities."""

        if self.model_role != "slow_master":
            raise RuntimeContractError(
                "admission-only screening is restricted to the slow master"
            )
        admission_expr = self._admission_objective()
        self.model.NumObj = 1
        self.model.setObjective(admission_expr, self.GRB.MINIMIZE)
        self.model.Params.TimeLimit = max(0.001, float(wall_budget_seconds))
        solve_started = time.monotonic()
        self.model.optimize()
        solve_seconds = time.monotonic() - solve_started
        if self.model.SolCount < 1 or self.model.Status != self.GRB.OPTIMAL:
            try:
                gap = float(self.model.MIPGap)
            except Exception:
                gap = math.inf
            raise RuntimeContractError(
                "hierarchical slow_master admission gate solve failed: "
                f"status={_status_name(self.GRB, self.model.Status)} "
                f"final_gap={gap} solve_seconds={solve_seconds:.6f}"
            )
        return {
            "capacity_admission_gate": float(admission_expr.getValue()),
            "optimized_deferred_job_count": sum(
                float(self.defer_job[j].X) > 0.5
                for j in range(len(self.domain.job_options))
            ),
            "admission_gate_solve_seconds": solve_seconds,
        }

    def solve_lexicographic(self, *, wall_budget_seconds: float) -> Mapping[str, Any]:
        deadline = time.monotonic() + float(wall_budget_seconds)
        # This is a feasibility/admission gate, not a replacement research
        # objective.  Minimize deferred gangs before applying the frozen three
        # electrical-stress priorities.  A sub-unit EDF term breaks equal-count
        # ties without ever outweighing one additional admitted job.
        admission_expr = self._admission_objective()
        exposure_expr = STEP_HOURS * self.gp.quicksum(self.z.values())
        tertiary_expr = self._tertiary_objective()
        charge_discharge_mode_projection_used = False
        maximum_simultaneous_before_projection = 0.0
        exact_qcp_feasibility_restoration_rounds = 0
        exact_qcp_implied_tangent_cuts_added = 0
        use_native_multiobjective = True
        if use_native_multiobjective:
            # Match the retained Full-H54 oracle's native Gurobi
            # lexicographic execution instead of rebuilding the branch tree
            # in three independent Python-side solves.
            self.model.NumObj = 4
            self.model.setObjective(self.gp.LinExpr(), self.GRB.MINIMIZE)
            self.model.setObjectiveN(
                admission_expr, 0, priority=4, abstol=1e-8, reltol=0.0,
                name="capacity_admission_gate",
            )
            self.model.setObjectiveN(
                self.zmax, 1, priority=3, abstol=1e-6, reltol=0.0,
                name="worst_electrical_stress",
            )
            self.model.setObjectiveN(
                exposure_expr, 2, priority=2, abstol=1e-6, reltol=0.0,
                name="electrical_stress_exposure",
            )
            self.model.setObjectiveN(
                tertiary_expr, 3, priority=1, abstol=1e-8, reltol=0.0,
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
                iis_sample: list[str] = []
                if self.model.Status in {
                    self.GRB.INFEASIBLE,
                    self.GRB.INF_OR_UNBD,
                }:
                    try:
                        self.model.computeIIS()
                        iis_sample.extend(
                            f"constr:{row.ConstrName}"
                            for row in self.model.getConstrs()
                            if row.IISConstr
                        )
                        iis_sample.extend(
                            f"qconstr:{row.QCName}"
                            for row in self.model.getQConstrs()
                            if row.IISQConstr
                        )
                        iis_sample.extend(
                            f"lb:{row.VarName}"
                            for row in self.model.getVars()
                            if row.IISLB
                        )
                        iis_sample.extend(
                            f"ub:{row.VarName}"
                            for row in self.model.getVars()
                            if row.IISUB
                        )
                    except Exception as iis_error:
                        iis_sample = [f"IIS_UNAVAILABLE:{type(iis_error).__name__}"]
                raise RuntimeContractError(
                    f"hierarchical {self.model_role} multiobjective solve failed "
                    "to complete all priorities: "
                    f"status={_status_name(self.GRB, self.model.Status)} "
                    f"final_gap={gap} solve_seconds={exact_solve_seconds:.6f} "
                    f"iis_sample={iis_sample[:24]}"
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
            if self.exact_qcp_diagnostic:
                # A conic barrier solution can satisfy Gurobi's internal QCP
                # test yet miss the independent scale-aware residual audit.
                # Supporting tangents are already implied by the exact circle,
                # so adding them changes no mathematical feasible point.  They
                # give the optimizer a linear row in the precise violated
                # direction and make the returned solution independently
                # certifiable against the engineering-safe circle.
                for restoration_round in range(
                    1, MAX_EXACT_QCP_FEASIBILITY_RESTORATION_ROUNDS + 1
                ):
                    (
                        residual_kva,
                        relative_residual,
                        violations,
                    ) = self._exact_norm_residuals()
                    if (
                        not violations
                        and relative_residual <= NORM_RELATIVE_TOLERANCE
                    ):
                        break
                    added = 0
                    for kind, element, step, direction_p, direction_q in violations:
                        added += int(
                            self._add_cut(
                                kind=kind,
                                element=element,
                                step=step,
                                direction_p=direction_p,
                                direction_q=direction_q,
                            )
                        )
                    if added == 0:
                        raise RuntimeContractError(
                            "exact QCP feasibility restoration stalled: "
                            f"max_residual_kva={residual_kva:.12g} "
                            f"max_relative_residual={relative_residual:.12g} "
                            f"remaining={violations[:5]}"
                        )
                    exact_qcp_implied_tangent_cuts_added += added
                    exact_qcp_feasibility_restoration_rounds = restoration_round
                    self.model.update()
                    remaining_budget = deadline - time.monotonic()
                    if remaining_budget <= 0.0:
                        raise RuntimeContractError(
                            "exact recourse exhausted its wall budget during "
                            "scale-aware QCP feasibility restoration"
                        )
                    self.model.Params.TimeLimit = max(0.001, remaining_budget)
                    # Re-optimizing a previously crossed-over cone after a
                    # supporting row is added can terminate SUBOPTIMAL from a
                    # degenerate crossover basis.  The rare restoration pass
                    # therefore uses the barrier point directly at maximum
                    # numerical focus, then restores the normal online policy.
                    self.model.Params.NumericFocus = 3
                    self.model.Params.Crossover = 0
                    restoration_started = time.monotonic()
                    self.model.optimize()
                    exact_solve_seconds += (
                        time.monotonic() - restoration_started
                    )
                    self.model.Params.NumericFocus = self.numeric_focus
                    self.model.Params.Crossover = -1
                    if (
                        self.model.SolCount < 1
                        or self.model.Status != self.GRB.OPTIMAL
                    ):
                        raise RuntimeContractError(
                            "exact QCP feasibility-restoration solve failed "
                            "to complete all objective priorities: "
                            f"status={_status_name(self.GRB, self.model.Status)} "
                            f"round={restoration_round} "
                            f"solve_seconds={exact_solve_seconds:.6f}"
                        )
                else:
                    (
                        residual_kva,
                        relative_residual,
                        violations,
                    ) = self._exact_norm_residuals()
                    if (
                        violations
                        or relative_residual > NORM_RELATIVE_TOLERANCE
                    ):
                        raise RuntimeContractError(
                            "exact QCP feasibility restoration exhausted: "
                            f"rounds={MAX_EXACT_QCP_FEASIBILITY_RESTORATION_ROUNDS} "
                            f"max_residual_kva={residual_kva:.12g} "
                            f"max_relative_residual={relative_residual:.12g} "
                            f"remaining={violations[:5]}"
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
        residual_kva, relative_residual, remaining = self._exact_norm_residuals()
        if self.model_role == "exact_recourse":
            if remaining or relative_residual > NORM_RELATIVE_TOLERANCE:
                raise RuntimeContractError(
                    "exact H54 recourse lost Euclidean-norm feasibility: "
                    f"max_residual_kva={residual_kva:.12g} "
                    f"max_relative_residual={relative_residual:.12g} "
                    f"remaining={remaining[:5]}"
                )
        else:
            # The slow MILP is a discrete-decision master. Its polyhedral
            # circle relaxation is never committed; exact H54 recourse below
            # is the physical/objective acceptance authority.
            residual_kva = max(0.0, residual_kva)
            relative_residual = max(0.0, relative_residual)
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
                else (
                    "FIXED_SLOW_DECISIONS_H54_EXACT_QCP_COMPLETE"
                    if self.norm_constraint_mode == "EXACT_QCP"
                    else "FIXED_SLOW_DECISIONS_H54_INNER_POLYGON_COMPLETE"
                )
            ),
            "norm_constraint_mode": self.norm_constraint_mode,
            "norm_inner_polygon_sides": (
                self.norm_inner_polygon_sides
                if self.norm_constraint_mode == "INNER_POLYGON"
                else None
            ),
            "norm_inner_polygon_max_radial_conservatism_fraction": (
                1.0 - math.cos(math.pi / self.norm_inner_polygon_sides)
                if self.norm_constraint_mode == "INNER_POLYGON"
                else 0.0
            ),
            "primary_worst_stress": float(self.zmax.X),
            "secondary_exposure": float(exposure_expr.getValue()),
            "tertiary_actuation": float(tertiary_expr.getValue()),
            "capacity_admission_gate": float(admission_expr.getValue()),
            "optimized_deferred_job_count": sum(
                float(self.defer_job[j].X) > 0.5
                for j in range(len(self.domain.job_options))
            ),
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
            "maximum_exact_norm_residual": residual_kva,
            "maximum_exact_norm_relative_residual": relative_residual,
            "norm_relative_tolerance": NORM_RELATIVE_TOLERANCE,
            "norm_engineering_margin_fraction": (
                NORM_ENGINEERING_MARGIN_FRACTION
            ),
            "exact_qcp_feasibility_restoration_rounds": (
                exact_qcp_feasibility_restoration_rounds
            ),
            "exact_qcp_implied_tangent_cuts_added": (
                exact_qcp_implied_tangent_cuts_added
            ),
            "exact_qcp_restoration_numeric_focus": (
                3 if exact_qcp_feasibility_restoration_rounds else None
            ),
            "exact_qcp_restoration_crossover": (
                0 if exact_qcp_feasibility_restoration_rounds else None
            ),
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
        gangs: dict[str, tuple[str, ...]] = {}
        wan: dict[str, tuple[float, ...]] = {}
        wan_required: dict[str, int] = {}
        queued_index = {uid: index for index, uid in enumerate(domain.queued_job_ids)}
        active_jobs = {
            uid: job for uid, job in state.jobs.items() if job.lifecycle != "COMPLETED"
        }
        for uid, job in sorted(active_jobs.items()):
            if uid not in queued_index:
                destination = _effective_job_site(job)
                if job.lifecycle == "QUEUED":
                    # Jobs outside the bounded causal decision frontier remain
                    # visible and ready under their current admission state.
                    # They are reconsidered by EDF in later rolling horizons.
                    placements[uid] = destination
                    prior_start = (
                        state.active_plan.job_start_issue.get(uid, frame.issue)
                        if state.active_plan is not None
                        else frame.issue
                    )
                    starts[uid] = max(frame.issue, int(prior_start))
                    # This is a preserved queue record, not an optimized rack
                    # decision.  Publish a pooled gang so the runtime rack
                    # authority repacks it around the selected frontier.
                    gangs[uid] = tuple(
                        f"{destination}:PFR-GPU:{uid}:{index}"
                        for index in range(job.source.requested_gpu)
                    )
                    wan[uid] = (0.0,) * self.h
                    wan_required[uid] = 0
                    continue
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
                gangs[uid] = tuple(
                    f"{rack}:PFR-GPU:{uid}:{index}"
                    for index in range(job.source.requested_gpu)
                )
                wan[uid] = (0.0,) * self.h
                wan_required[uid] = 0
                continue
            j = queued_index[uid]
            hits = [
                o
                for o in range(len(domain.job_options[j]))
                if self.job[(j, o)].X > 0.5
            ]
            deferred = float(self.defer_job[j].X) > 0.5
            if len(hits) + int(deferred) != 1:
                raise RuntimeContractError(
                    "persistent MILP job admission is not integral "
                    f"uid={uid} options={hits} deferred={deferred}"
                )
            if deferred:
                destination = _effective_job_site(job)
                placements[uid] = destination
                prior_start = (
                    state.active_plan.job_start_issue.get(uid, frame.issue)
                    if state.active_plan is not None
                    else frame.issue
                )
                starts[uid] = max(frame.issue, int(prior_start))
                gangs[uid] = tuple(
                    f"{destination}:PFR-GPU:{uid}:{index}"
                    for index in range(job.source.requested_gpu)
                )
                wan[uid] = (0.0,) * self.h
                wan_required[uid] = 0
                continue
            option = domain.job_options[j][hits[0]]
            placements[uid] = option.destination
            starts[uid] = frame.issue + option.start_offset
            racks[uid] = option.rack
            gangs[uid] = tuple(
                f"{option.rack}:PFR-GPU:{uid}:{index}"
                for index in range(job.source.requested_gpu)
            )
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
            gpu_gang_allocation=gangs,
            job_start_issue=starts,
            coarse_charging_kw=charge,
            coarse_discharging_kw=discharge,
            coarse_reactive_kvar=reactive,
            mess_departure_issue=departures,
            job_wan_send_gb=wan,
            job_wan_required_bytes=wan_required,
        )
