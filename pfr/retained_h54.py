"""Concrete adapter for the retained ``science/main.py::build_full`` asset.

The adapter does not recreate the optimizer.  It binds the live PFR runtime
state and the issue-causal H54 forecasts to the retained joint MIQCP and
translates its full-horizon solution into ``SlowDiscretePlan``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Optional

import numpy as np

try:
    import fcntl
except ImportError:  # pragma: no cover - production campaigns run under WSL/POSIX.
    fcntl = None

from .electrical_stress import OBJECTIVE_AUTHORITY
from .methods import MethodConfig
from .migration import MigrationAuthority
from .power import H100UtilizationPowerCurve
from .runtime import (
    CausalExperimentFrame,
    IDCS,
    MESS_CANONICAL_STAGING,
    MESS_IDS,
    MutableMethodState,
    PLANNING_HORIZON_STEPS,
    RuntimeContractError,
    STEP_HOURS,
    _effective_job_site,
)
from .slow_fast import SlowDiscretePlan


ADAPTER_ID = "RETAINED_SCIENCE_BUILD_FULL_H54_ADAPTER_V1"

_FORMULATION_DEFAULTS = {
    "MOBILEESS_OPT_HORIZON_STEPS": "54",
    "MOBILEESS_R24_PERMANENT_EXACT_REBASE": "1",
    "MOBILEESS_R25A_FORWARD_BACKWARD_PRUNE": "1",
    "MOBILEESS_R25B_ROUTE_DOMINANCE_AUDIT": "1",
    "MOBILEESS_R25D_RADIAL_GRID_PROJECTION": "1",
    "MOBILEESS_R25E_NODE_ARC_EXACT": "1",
    "MOBILEESS_R25G_HYBRID_STAY_BINARY": "1",
    "MOBILEESS_R25H_B1_CERTIFICATE_FOCUS": "1",
    "MOBILEESS_R25I_B2_NUMERICAL_RESCALING": "1",
    "MOBILEESS_R25K_B4_ROOT_BRANCH_STRENGTHENING": "1",
    "MOBILEESS_R25N_B6C5R4_COMPLETE_UNIT_NORMALIZATION": "1",
    "MOBILEESS_EXACT_IMPLIED_BOUNDS": "1",
    # These dense B4 rows are algebraic consequences of the retained SOC/debt
    # recursions.  Omitting them preserves both the integer and continuous
    # feasible sets while avoiding millions of repeated route-arc nonzeros.
    "MOBILEESS_POST15_SKIP_REDUNDANT_DENSE_B4_CUTS": "1",
    # The retained solver already implements a solver-checked, one-step-shifted
    # causal MIP start.  Keep it enabled now that the runtime adapter carries
    # the preceding plan between replans of the same method.
    "MOBILEESS_R25V_CAUSAL_ROLLING_MIPSTART": "1",
    # R26 multiresolution MPC: retain all 54 physical five-minute grid/SOC/
    # workload evaluations, but place far-horizon mobility departures on the
    # predeclared 15-minute stage grid after the first fine 60 minutes.
    "MOBILEESS_R26_MULTIRES_MOBILITY": "1",
    "MOBILEESS_R26_SINGLE_RELOCATION_TRUST_REGION": "1",
    "MOBILEESS_VECTOR_K3_PARETO": "1",
    "MOBILEESS_BULK_MOBILITY_VARS": "1",
    "MOBILEESS_GUROBI_ECON_MIPGAP": "0.03",
    "MOBILEESS_GUROBI_PRIMARY_STRESS_MIPGAP": "0.03",
    "MOBILEESS_GUROBI_EXPOSURE_MIPGAP": "0.03",
    "MOBILEESS_GUROBI_TIMELIMIT": "300",
}


class _RuntimeZeroFixedRackEnvironment:
    """Retain the engine API while removing its pilot-period rack baseline.

    Runtime facility demand is reconstructed from the admitted/running job
    state.  Reading the retained pilot baseline here would both double count
    jobs and fail outside that pilot's timestamp index.
    """

    def __init__(self, retained_environment: Any) -> None:
        self._retained_environment = retained_environment

    def current_fixed(self, _issue: Any, _rack: str) -> tuple[float, float]:
        return 0.0, 0.0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._retained_environment, name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_science_module(repo: Path):
    science = (repo / "science").resolve()
    source = science / "main.py"
    if not source.is_file():
        raise RuntimeContractError(f"retained H54 source is missing: {source}")
    if str(science) not in sys.path:
        sys.path.insert(0, str(science))
    name = "mobileess_retained_h54_science_main"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise RuntimeContractError("cannot load retained H54 science module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RetainedH54JointPlanner:
    """Stateful, static-cache-preserving adapter to the retained joint MIQCP."""

    def __init__(
        self,
        *,
        repo: Path,
        base: Path,
        output_root: Path,
        power_curve: H100UtilizationPowerCurve,
        gurobi_threads: Optional[int] = None,
        legacy_causal_screening: bool = False,
    ) -> None:
        self.repo = repo.resolve()
        self.base = base.resolve()
        self.output_root = output_root.resolve()
        power_curve.validate()
        self.power_curve = power_curve
        self.legacy_causal_screening = bool(legacy_causal_screening)
        if not self.base.is_dir():
            raise RuntimeContractError(
                f"retained H54 base directory is missing: {self.base}"
            )
        for name, value in _FORMULATION_DEFAULTS.items():
            observed = os.environ.get(name)
            if observed is not None and observed != value:
                raise RuntimeContractError(
                    f"retained H54 formulation environment drift {name}: "
                    f"expected={value} observed={observed}"
                )
            os.environ[name] = value
        os.environ["MOBILEESS_R25M_B6_EXACT_DECOMPOSITION"] = "0"
        if gurobi_threads is not None:
            if not 1 <= int(gurobi_threads) <= 16:
                raise RuntimeContractError("retained H54 threads must lie in [1,16]")
            os.environ["MOBILEESS_GUROBI_THREADS"] = str(int(gurobi_threads))
        elif "MOBILEESS_GUROBI_THREADS" not in os.environ:
            os.environ["MOBILEESS_GUROBI_THREADS"] = os.environ.get(
                "PFR_GUROBI_THREADS", "4"
            )
        self.science = _load_science_module(self.repo)
        self._initialized = False
        self._rolling_warmstarts: dict[str, Mapping[str, Any]] = {}

    def _legacy_fixed_location_screen(
        self, state: MutableMethodState, config: MethodConfig
    ) -> tuple[Optional[dict[str, str]], str]:
        """Reuse the old causal no-demand mobility decision as domain screening.

        The historical route optimizer returned STAY without building its small
        MIQP when no active workload destination existed and every MESS was at
        canonical staging.  In that exact state we omit the time-expanded
        mobility network, but retain the complete H54 P/Q, SOC, recovery,
        workload, and electrical-stress MIQCP.
        """

        if not self.legacy_causal_screening:
            return None, "DISABLED"
        if not bool(config.h54_capability_mask.get("mess_mobility", False)):
            return None, "CAPABILITY_OFF_HANDLED_BY_COMMON_FORMULATION"
        if any(bool(state.mess_in_transit[mid]) for mid in MESS_IDS):
            return None, "COMMITTED_TRANSIT_PRESENT"
        active_sites = {
            _effective_job_site(job)
            for job in state.jobs.values()
            if job.lifecycle != "COMPLETED"
        }
        away = {
            mid
            for mid in MESS_IDS
            if state.mess_location[mid] != MESS_CANONICAL_STAGING[mid]
        }
        if active_sites or away:
            return None, "ACTIVE_WORKLOAD_OR_AWAY_MESS_REQUIRES_ROUTE_DOMAIN"
        homes = {mid: str(state.mess_location[mid]) for mid in MESS_IDS}
        if len(set(homes.values())) != len(homes):
            return None, "SHARED_PCC_REQUIRES_COMMON_CONNECTION_MODEL"
        return homes, "LEGACY_CAUSAL_NO_ACTIVE_DESTINATION_ALL_CANONICAL_STAY"

    def _initialize(self) -> None:
        if self._initialized:
            return
        root = self.output_root / "_RETAINED_H54_FOUNDATION"
        root.mkdir(parents=True, exist_ok=True)
        # Six independent day processes are intentionally kept for campaign
        # throughput.  Their retained-foundation construction, however, has a
        # short high-memory extraction/import/static-grid phase.  Serializing
        # only that one-time phase prevents concurrent RSS spikes without
        # reducing steady-state day or solver parallelism.
        lock_path = Path(
            os.environ.get(
                "PFR_FOUNDATION_STARTUP_LOCK",
                str(self.output_root.parent / ".PFR_FOUNDATION_STARTUP.lock"),
            )
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = lock_path.open("a+", encoding="utf-8")
        wait_started = time.monotonic()
        try:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            wait_seconds = time.monotonic() - wait_started
            foundation, _ = self.science._worker_foundation(self.base, root)
            self.foundation = foundation
            self.b4 = foundation["b4"]
            self.ar2 = foundation["ar2"]
            self.b6 = foundation["b6"]
            self.op1 = foundation["op1"]
            self.grid = foundation["grid"]
            self.metrics = foundation["metrics"]
            self.scope = self.b4.prepare_scope(
                self.base, foundation["rack"], self.op1, root
            )
            self.scope["env"] = _RuntimeZeroFixedRackEnvironment(self.scope["env"])
            if foundation.get("gstatic") is None:
                foundation["gstatic"] = self.b4.build_grid_static(
                    foundation["engine"],
                    self.grid,
                    self.metrics,
                    self.scope,
                    foundation["b2"],
                )
            self.gstatic = foundation["gstatic"]
            self._initialized = True
            (root / "FOUNDATION_STARTUP_MEMORY_GATE.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "lock_path": str(lock_path.resolve()),
                        "wait_seconds": wait_seconds,
                        "serialized_scope": "FOUNDATION_ONLY",
                        "steady_state_day_parallelism_reduced": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        finally:
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()

    def _scope_job(self, uid: str, state_job: Any) -> dict[str, Any]:
        if uid not in self.scope["pmap"]:
            source = state_job.source
            duration_steps = max(
                1, int(math.ceil(float(source.runtime_seconds_source) / 300.0))
            )
            row = {
                "job_uid": uid,
                "origin_IDC_id": source.origin_idc,
                "arrival_step": int(source.arrival_step),
                "latest_start_step": int(source.latest_start_step),
                "latest_completion_step_exclusive": int(source.deadline_step),
                "duration_steps": duration_steps,
                "requested_gpu": float(source.requested_gpu),
                "IT_power_kW": float(
                    self.power_curve.gang_power_kw(source.requested_gpu, 1.0)
                    + source.cpu_request_share_kw
                ),
            }
            self.scope["pmap"][uid] = row
            self.scope["domains"][uid] = [
                {
                    "destination_IDC_id": str(capacity.idc_id),
                    "rack_pool_id": str(capacity.rack_pool_id),
                    "is_local": str(capacity.idc_id) == source.origin_idc,
                }
                for capacity in self.scope["cap"].itertuples(index=False)
            ]
            if uid not in self.scope["wan_map"]:
                self.scope["wan_map"][uid] = (
                    float(source.input_bytes) / 1e9
                    if source.input_bytes is not None
                    else 0.0
                )
        row = dict(self.scope["pmap"][uid])
        source = state_job.source
        checks = {
            "arrival_step": source.arrival_step,
            "latest_start_step": source.latest_start_step,
            "latest_completion_step_exclusive": source.deadline_step,
            "requested_gpu": source.requested_gpu,
        }
        for field, expected in checks.items():
            if int(row[field]) != int(expected):
                raise RuntimeContractError(
                    f"retained workload authority drift uid={uid} field={field} "
                    f"retained={row[field]} runtime={expected}"
                )
        return row

    def _rack_for(self, uid: str, destination: str) -> str:
        options = [
            str(row["rack_pool_id"])
            for row in self.scope["domains"][uid]
            if str(row["destination_IDC_id"]) == destination
        ]
        if not options:
            raise RuntimeContractError(
                f"retained rack domain lacks uid={uid} destination={destination}"
            )
        return sorted(options)[0]

    def _workload_state(self, state: MutableMethodState):
        queue: dict[str, dict[str, Any]] = {}
        running: dict[str, dict[str, Any]] = {}
        inventory: dict[str, float] = {}
        destination_commit: dict[str, str] = {}
        debt = {site: 0.0 for site in IDCS}
        for uid, job in sorted(state.jobs.items()):
            if job.lifecycle == "COMPLETED":
                continue
            row = self._scope_job(uid, job)
            debt[job.source.origin_idc] += max(
                0.0,
                job.remaining_work_gpu_hours
                - max(0, job.source.deadline_step - state.issue)
                * job.source.requested_gpu
                * STEP_HOURS,
            )
            if job.lifecycle in {"RUNNING", "MIGRATING", "RESTARTING"}:
                destination = _effective_job_site(job)
                remaining_steps = max(
                    1,
                    int(
                        math.ceil(
                            job.remaining_work_gpu_hours
                            / (job.source.requested_gpu * STEP_HOURS)
                            - 1e-12
                        )
                    ),
                )
                running[uid] = {
                    "job_uid": uid,
                    "state": job.lifecycle,
                    "destination_IDC_id": destination,
                    "rack_pool_id": self._rack_for(uid, destination),
                    "remaining_steps": remaining_steps,
                    "requested_gpu": int(job.source.requested_gpu),
                    "IT_power_kW": (
                        float(row["IT_power_kW"])
                        if job.lifecycle == "RUNNING"
                        else 0.0
                    ),
                }
                continue
            queued = dict(row)
            queued["state"] = "QUEUED"
            queue[uid] = queued
            required_gb = float(self.scope["wan_map"][uid])
            target = job.prestart_wan_target_idc
            if target is not None:
                destination_commit[uid] = target
                inventory[uid] = min(
                    required_gb,
                    job.prestart_wan_transferred_bytes / 1e9,
                )
            elif job.destination_idc != job.source.origin_idc:
                destination_commit[uid] = job.destination_idc
                inventory[uid] = required_gb
            else:
                inventory[uid] = 0.0
        return queue, running, inventory, destination_commit, debt

    @staticmethod
    def _rolling_mess_state(state: MutableMethodState) -> dict[str, dict[str, Any]]:
        result = {}
        for mid in MESS_IDS:
            if not state.mess_in_transit[mid]:
                location = state.mess_location[mid]
                result[mid] = {
                    "phase": "STAY",
                    "service_id": location,
                    "source_service_id": location,
                    "dest_service_id": location,
                    "remaining_total_steps": 0,
                    "remaining_profile_kWh": [],
                }
                continue
            destination = state.mess_route_destination[mid]
            if destination is None:
                raise RuntimeContractError("in-transit MESS lacks destination")
            profile = state.mess_route_energy_profile_kwh[mid]
            index = state.mess_route_profile_index[mid]
            remaining = tuple(float(value) for value in profile[index:])
            if not remaining:
                raise RuntimeContractError("in-transit MESS lacks remaining profile")
            result[mid] = {
                "phase": "MOVE",
                "service_id": state.mess_location[mid],
                "source_service_id": state.mess_location[mid],
                "dest_service_id": destination,
                "remaining_total_steps": len(remaining),
                "remaining_profile_kWh": list(remaining),
            }
        return result

    def solve(
        self,
        *,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        migration_authority: Optional[MigrationAuthority],
        evaluation_steps_remaining: int,
    ) -> tuple[SlowDiscretePlan, Mapping[str, Any]]:
        self._initialize()
        issue_root = (
            self.output_root
            / "_RETAINED_H54"
            / config.comparison_method_id.value
            / f"issue_{frame.issue:06d}"
        )
        issue_root.mkdir(parents=True, exist_ok=True)
        queue, running, inventory, destination_commit, workload_debt = (
            self._workload_state(state)
        )
        reference = self.b4.reference_grid(
            self.scope,
            self.grid,
            self.metrics,
            self.gstatic,
            frame.issue,
            running,
            issue_root,
        )
        reference["store"] = self.gstatic["store"]
        static_context = self.science.prepare_static_context(
            self.ar2, self.b6, reference, self.b4
        )
        mobility_path = Path(frame.planning_mobility_npz_path).resolve()
        if not mobility_path.is_file():
            raise RuntimeContractError(
                f"runtime H54 mobility file is missing: {mobility_path}"
            )
        if _sha256(mobility_path) != frame.planning_mobility_npz_sha256:
            raise RuntimeContractError("runtime H54 mobility SHA-256 drift")
        mobility = self.science._npz_immutable(mobility_path)
        connection_delay = self.science.d2_connection_delay_steps(
            self.scope, issue_root
        )
        moves, _ = self.science.pareto_moves(
            static_context["route_df"], mobility, connection_delay
        )
        moves = {
            key: value
            for key, value in moves.items()
            if int(key[0]) + int(value["D"]) <= evaluation_steps_remaining
        }
        planning_override = {
            "background_p_kw": frame.planning_forecast_background_p_kw,
            "background_q_kvar": frame.planning_forecast_background_q_kvar,
            "pv_available_kw": frame.planning_forecast_pv_available_kw,
        }
        price_override = (
            float(frame.current_price_aud_per_mwh),
        ) + (float(frame.horizon_price_median_aud_per_mwh),) * (
            PLANNING_HORIZON_STEPS - 1
        )
        method_key = config.comparison_method_id.value
        screened_homes, screening_reason = self._legacy_fixed_location_screen(
            state, config
        )
        solution = self.science.build_full(
            self.scope,
            self.b4,
            self.op1,
            frame.issue,
            queue,
            running,
            inventory,
            destination_commit,
            dict(state.mess_energy_kwh),
            reference,
            self.ar2,
            self.b6,
            mobility,
            static_context["route_df"],
            moves,
            connection_delay,
            static_context["price"],
            issue_root,
            static_context,
            rolling_mess_state=self._rolling_mess_state(state),
            mess_DE0=dict(state.mess_energy_debt_kwh),
            workload_debt0=workload_debt,
            capability_mask=dict(config.h54_capability_mask),
            planning_forecast_override=planning_override,
            price_forecast_override=price_override,
            # Runtime facility demand contains admitted/running jobs only.
            # The retained pilot rack baseline is both out-of-period and would
            # double count load, so bind its fixed-rack term to runtime zero.
            fixed_rack_forecast_override=lambda _rack, _step: (0.0, 0.0, 0.0),
            rolling_warmstart=self._rolling_warmstarts.get(method_key),
            fixed_location_projection_override=(
                True if screened_homes is not None else None
            ),
            fixed_location_homes_override=screened_homes,
        )
        # Store only the optimizer's causal plan.  This is solver guidance for
        # the next replan of the same method, never an execution authority and
        # never a source of future realized information.
        self._rolling_warmstarts[method_key] = dict(
            solution["rolling_warmstart_payload"]
        )
        selected_jobs = {
            str(row["job_uid"]): dict(row) for row in solution["plan"]
        }
        active_jobs = {
            uid: job
            for uid, job in state.jobs.items()
            if job.lifecycle != "COMPLETED"
        }
        placements: dict[str, str] = {}
        starts: dict[str, int] = {}
        gangs: dict[str, tuple[str, ...]] = {}
        checkpoints: dict[str, Optional[str]] = {}
        wan_schedules: dict[str, tuple[float, ...]] = {}
        wan_required: dict[str, int] = {}
        for uid, job in sorted(active_jobs.items()):
            selected = selected_jobs.get(uid)
            destination = (
                str(selected["destination_IDC_id"])
                if selected is not None
                else _effective_job_site(job)
            )
            start = (
                int(selected["start_step"])
                if selected is not None
                else (
                    frame.issue
                    if job.lifecycle != "QUEUED"
                    else min(
                        job.source.latest_start_step,
                        frame.issue + PLANNING_HORIZON_STEPS,
                    )
                )
            )
            placements[uid] = destination
            starts[uid] = start
            gangs[uid] = tuple(
                f"{destination}:PFR-GPU:{uid}:{index}"
                for index in range(job.source.requested_gpu)
            )
            checkpoints[uid] = None
            schedule = []
            for horizon in range(PLANNING_HORIZON_STEPS):
                absolute = frame.issue + horizon
                schedule.append(
                    sum(
                        float(value)
                        for (job_uid, target, step), value in solution["wan_all"].items()
                        if str(job_uid) == uid
                        and str(target) == destination
                        and int(step) == absolute
                    )
                )
            wan_schedules[uid] = tuple(schedule)
            wan_required[uid] = (
                int(round(float(self.scope["wan_map"][uid]) * 1e9))
                if destination != job.source.origin_idc
                and job.lifecycle == "QUEUED"
                else 0
            )
        mess_rows = solution["mess_rows"]
        charge = {}
        discharge = {}
        reactive = {}
        destination = {}
        rank = {}
        departure = {}
        for mid in MESS_IDS:
            rows = sorted(
                (row for row in mess_rows if str(row["mess_id"]) == mid),
                key=lambda row: int(row["horizon_step"]),
            )
            if len(rows) != PLANNING_HORIZON_STEPS:
                raise RuntimeContractError(
                    f"retained H54 MESS schedule length drift mid={mid}"
                )
            charge[mid] = tuple(float(row["P_charge_kW"]) for row in rows)
            discharge[mid] = tuple(float(row["P_discharge_kW"]) for row in rows)
            reactive[mid] = tuple(float(row["Q_kvar"]) for row in rows)
            selected_routes = sorted(
                (
                    row
                    for row in solution["route_rows"]
                    if str(row["mess_id"]) == mid
                ),
                key=lambda row: int(row["horizon_step"]),
            )
            if selected_routes:
                first = selected_routes[0]
                destination[mid] = str(first["destination_service_id"])
                rank[mid] = int(first["slot"]) % 3 + 1
                departure[mid] = frame.issue + int(first["horizon_step"])
            elif state.mess_in_transit[mid]:
                destination[mid] = str(state.mess_route_destination[mid])
                rank[mid] = int(state.mess_route_rank[mid])
                departure[mid] = None
            else:
                destination[mid] = state.mess_location[mid]
                rank[mid] = 1
                departure[mid] = None
        plan = SlowDiscretePlan(
            plan_id=(
                f"{config.comparison_method_id.value}-{frame.issue}-"
                f"{state.full_replan_count + 1}"
            ),
            valid_from_issue=frame.issue,
            mess_destination=destination,
            mess_native_route_rank=rank,
            job_idc_placement=placements,
            checkpoint_migration=checkpoints,
            gpu_gang_allocation=gangs,
            job_start_issue=starts,
            coarse_charging_kw=charge,
            coarse_discharging_kw=discharge,
            coarse_reactive_kvar=reactive,
            mess_departure_issue=departure,
            job_wan_send_gb=wan_schedules,
            job_wan_required_bytes=wan_required,
        )
        plan.validate()
        metrics = dict(solution["metrics"])
        certificate = {
            **metrics,
            "adapter_id": ADAPTER_ID,
            "objective_authority": OBJECTIVE_AUTHORITY,
            "capability_mask": dict(config.h54_capability_mask),
            "actual_gurobi_used": True,
            "runtime_state_issue": frame.issue,
            "evaluation_steps_remaining": evaluation_steps_remaining,
            "planning_mobility_npz_sha256": frame.planning_mobility_npz_sha256,
            "future_actual_used": False,
            "price_used_by_optimizer": False,
            "runtime_fixed_rack_baseline_zeroed": True,
            "legacy_causal_mobility_screening": {
                "enabled": self.legacy_causal_screening,
                "applied": screened_homes is not None,
                "reason": screening_reason,
                "restricted_domain": screened_homes is not None,
                "fixed_homes": screened_homes or {},
                "decision_authority": "RESTRICTED_H54_MIQCP",
                "heuristic_role": "DOMAIN_SCREENING_ONLY",
                "mobility_domain_before_candidate_arcs": len(moves),
                "mobility_domain_after_candidate_arcs": int(
                    metrics.get("candidate_move_continuous_arc_count", 0)
                ),
                "heuristic_recommended_routes": [],
                "restricted_miqcp_objective_z": float(
                    metrics["objective_worst_predicted_electrical_stress_pu"]
                ),
            },
            "planned_mobility_routes": [
                {
                    "mess_id": str(row["mess_id"]),
                    "horizon_step": int(row["horizon_step"]),
                    "destination_service_id": str(row["destination_service_id"]),
                    "route_slot": int(row["slot"]),
                }
                for row in solution["route_rows"]
            ],
        }
        return plan, certificate
