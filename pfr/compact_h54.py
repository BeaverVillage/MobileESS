"""Low-latency H54 electrical-stress planner for the closed-loop runtime.

The retained ``science/main.py::build_full`` MIQCP remains the formulation
oracle.  Rebuilding and globally closing that large model at every five-minute
event is not a real-time controller, however.  This module compiles the same
radial LinDistFlow stress endpoints into NumPy arrays once and performs a
deterministic, capability-masked lexicographic search over feasible H54 action
templates.  Fresh three-phase OpenDSS remains the execution/commit authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import time
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .electrical_stress import OBJECTIVE_AUTHORITY
from .methods import MethodConfig
from .migration import MigrationAuthority
from .retained_h54 import RetainedH54JointPlanner
from .runtime import (
    CausalExperimentFrame,
    IDCS,
    IDC_FACILITY_POWER_FACTOR,
    IDC_FACILITY_PUE,
    IDC_FACILITY_TANPHI,
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


COMPACT_ADAPTER_ID = "OFFLINE_ORACLE_VALIDATED_BOUNDED_CANDIDATE_H54_V1"
ONLINE_DOMAIN_AUTHORITY = "BOUNDED_CANDIDATE_ONLINE_DOMAIN_V1"
ALLOWED_DEVELOPMENT_K = (4, 8, 16, 32, 64)
DEFAULT_CANDIDATE_LIMIT = 16
PUE = IDC_FACILITY_PUE
PF = IDC_FACILITY_POWER_FACTOR
TANPHI = IDC_FACILITY_TANPHI
IDC_TRANSFORMER_LIMIT_KW = 750.0 * PF
PCS_KVA = 700.0


@dataclass(frozen=True)
class _MobilityTemplate:
    """One physically admissible single-relocation schedule.

    ``None`` denotes STAY.  Exact-safe screening constructs the physical
    superset first; score-based truncation is performed later and is recorded
    explicitly as an approximation.
    """

    departure_offset: Optional[int]
    destination_service_id: str
    route_rank: int
    route_slot: Optional[int]
    transit_steps: int
    energy_kwh: float
    source: str
    generation_reason: str
    mess_id: Optional[str]

    @property
    def is_stay(self) -> bool:
        return self.departure_offset is None

    @property
    def identity(self) -> tuple[Any, ...]:
        return (
            self.mess_id,
            self.departure_offset,
            self.destination_service_id,
            self.route_rank,
            self.route_slot,
        )


def _ordered_mobility_candidates(
    *,
    mandatory: Sequence[_MobilityTemplate],
    ranked: Sequence[tuple[_MobilityTemplate, float]],
    commitment_window_steps: int,
) -> list[_MobilityTemplate]:
    """Return a stable prefix that exposes executable mobility decisions.

    A global electrical-score ordering can fill a small K domain with routes
    whose departures all lie beyond the next scheduled replan.  Rolling the
    horizon then recreates those future departures indefinitely, so mobility
    is enabled on paper but no route can ever start.  Keep the frozen score
    ordering, while putting an actionable candidate for every eligible MESS
    and destination-diverse candidates at the front of the optional prefix.
    The best unrestricted future-preposition candidate follows them.  STAY
    and a previously retained plan remain mandatory and movement is never
    forced.
    """

    ordered: list[_MobilityTemplate] = []
    seen: set[tuple[Any, ...]] = set()

    def add(candidate: _MobilityTemplate) -> None:
        if candidate.identity not in seen:
            ordered.append(candidate)
            seen.add(candidate.identity)

    for candidate in mandatory:
        add(candidate)

    actionable = [
        candidate
        for candidate, _score in ranked
        if candidate.departure_offset is not None
        and int(candidate.departure_offset) < int(commitment_window_steps)
    ]
    if actionable:
        # Fleet diversity is part of the treatment definition: a bounded
        # prefix must not silently reduce four mobile assets to whichever one
        # happens to win the causal screen tie-break.
        for mid in MOBILITY_ELIGIBLE_MESS_IDS:
            candidate = next(
                (row for row in actionable if row.mess_id == mid),
                None,
            )
            if candidate is not None:
                add(candidate)
        add(actionable[0])
        first_destination = actionable[0].destination_service_id
        second_destination = next(
            (
                candidate
                for candidate in actionable[1:]
                if candidate.destination_service_id != first_destination
            ),
            None,
        )
        if second_destination is not None:
            add(second_destination)

    if ranked:
        add(ranked[0][0])

    # Fill the remaining actionable prefix destination-by-destination.  The
    # single-step screen often gives many departure/rank variants at one PCC
    # identical scores; a flat ordering can consume K before a location whose
    # full H54 recourse is better is ever exposed to the master.
    by_asset_destination: dict[tuple[Optional[str], str], list[_MobilityTemplate]] = {}
    asset_destination_order: list[tuple[Optional[str], str]] = []
    for candidate in actionable:
        key = (candidate.mess_id, candidate.destination_service_id)
        if key not in by_asset_destination:
            by_asset_destination[key] = []
            asset_destination_order.append(key)
        by_asset_destination[key].append(candidate)
    depth = 0
    while True:
        added_at_depth = False
        for key in asset_destination_order:
            candidates = by_asset_destination[key]
            if depth < len(candidates):
                add(candidates[depth])
                added_at_depth = True
        if not added_at_depth:
            break
        depth += 1
    for candidate, _score in ranked:
        add(candidate)
    return ordered


@dataclass(frozen=True)
class _CandidateEvaluation:
    template: _MobilityTemplate
    locations: list[list[Optional[str]]]
    idc_it_kw: np.ndarray
    placements: Mapping[str, str]
    starts: Mapping[str, int]
    racks: Mapping[str, str]
    wan_schedules_gb: Mapping[str, tuple[float, ...]]
    wan_required_bytes: Mapping[str, int]
    mess_p_kw: np.ndarray
    mess_q_kvar: np.ndarray
    stress: _StressResult


class _CandidateInfeasible(RuntimeError):
    """Internal marker used to reject one bounded-domain action template."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class _StressResult:
    per_step: np.ndarray
    voltage: np.ndarray
    line: np.ndarray
    transformer: np.ndarray
    worst_type: str
    worst_element: str

    @property
    def objective(self) -> tuple[float, float]:
        return (float(np.max(self.per_step)), float(np.sum(self.per_step) * STEP_HOURS))


class _RadialStressKernel:
    """Vectorized algebraic evaluator of the retained lossless LinDistFlow model."""

    def __init__(self, static: Mapping[str, Any], reference: Mapping[str, Any]) -> None:
        self.nodes = tuple(str(value).lower() for value in static["nodes"])
        self.index = {node: index for index, node in enumerate(self.nodes)}
        self.root = str(static["root"]).lower()
        self.parent = {str(k).lower(): str(v).lower() for k, v in static["parent"].items()}
        self.children = {
            str(k).lower(): tuple(str(value).lower() for value in values)
            for k, values in static["children"].items()
        }
        self.topological = tuple(str(value).lower() for value in static["nodes_topo"])
        self.reverse = tuple(str(value).lower() for value in static["nodes_reverse"])
        self.edge = {str(k).lower(): value for k, value in static["edge"].items()}
        self.background_buses = tuple(str(value).lower() for value in static["bgbus"])
        self.idc_bus = {str(k): str(v).lower() for k, v in static["idc_bus"].items()}
        self.service_bus = {str(k): str(v).lower() for k, v in static["pcc"].items()}
        self.service_kva = {str(k): float(v) for k, v in static["service_kva"].items()}
        self.line_children = tuple(
            child
            for (parent, child), limit in sorted(static["lim"].items())
            if float(limit) > 0.0 and child in self.index and parent in self.index
        )
        self.line_limits = np.asarray(
            [float(static["lim"][(self.parent[child], child)]) for child in self.line_children],
            dtype=float,
        )
        n = len(self.nodes)
        descendant = np.zeros((n, n), dtype=float)
        for child in self.reverse:
            ci = self.index[child]
            descendant[ci, ci] = 1.0
            for grandchild in self.children.get(child, ()):
                descendant[ci] += descendant[self.index[grandchild]]
        self.descendant = descendant
        # Compile voltage response matrices once.  For a unit nodal P/Q
        # injection, descendant[edge,node] is the corresponding branch-flow
        # response; LinDistFlow voltage is therefore one fixed linear map.
        self.voltage_p = np.zeros((n, n), dtype=float)
        self.voltage_q = np.zeros((n, n), dtype=float)
        for node in self.topological:
            if node == self.root:
                continue
            i = self.index[node]
            pi = self.index[self.parent[node]]
            edge = self.edge[node]
            if str(edge["edge_kind"]) == "LINE":
                self.voltage_p[i] = self.voltage_p[pi] - 0.002 * float(
                    edge["r_total_ohm"]
                ) * descendant[i]
                self.voltage_q[i] = self.voltage_q[pi] - 0.002 * float(
                    edge["x_total_ohm"]
                ) * descendant[i]
            else:
                ratio = float(edge["ratio2_ref"])
                self.voltage_p[i] = ratio * self.voltage_p[pi]
                self.voltage_q[i] = ratio * self.voltage_q[pi]
        self.anchor_p: Optional[np.ndarray] = None
        self.anchor_q: Optional[np.ndarray] = None
        self.reference_p = np.zeros(n, dtype=float)
        self.reference_q = np.zeros(n, dtype=float)
        self.reference_u = np.empty(n, dtype=float)
        self.nominal_u = np.empty(n, dtype=float)
        self.low_u = np.empty(n, dtype=float)
        self.high_u = np.empty(n, dtype=float)
        for node in self.nodes:
            i = self.index[node]
            kv = float(reference["bkv"][node])
            vpu = float(reference["vpu"][node])
            self.reference_u[i] = (math.sqrt(3.0) * kv * vpu) ** 2
            self.nominal_u[i] = (math.sqrt(3.0) * kv) ** 2
            self.low_u[i] = (0.95 * math.sqrt(3.0) * kv) ** 2
            self.high_u[i] = (1.05 * math.sqrt(3.0) * kv) ** 2

    def injections(
        self,
        frame: CausalExperimentFrame,
        idc_it_kw: np.ndarray,
        mess_p_kw: np.ndarray,
        mess_q_kvar: np.ndarray,
        mess_location: Sequence[Sequence[Optional[str]]],
    ) -> tuple[np.ndarray, np.ndarray]:
        h = PLANNING_HORIZON_STEPS
        own_p = np.zeros((h, len(self.nodes)), dtype=float)
        own_q = np.zeros_like(own_p)
        fp = np.asarray(frame.planning_forecast_background_p_kw, dtype=float)
        fq = np.asarray(frame.planning_forecast_background_q_kvar, dtype=float)
        pv = np.asarray(frame.planning_forecast_pv_available_kw, dtype=float)
        net_p = np.sum(fp - pv, axis=2)
        net_q = np.sum(fq, axis=2)
        for column, bus in enumerate(self.background_buses):
            own_p[:, self.index[bus]] += net_p[:, column]
            own_q[:, self.index[bus]] += net_q[:, column]
        for column, site in enumerate(IDCS):
            bus = self.index[self.idc_bus[site]]
            facility = PUE * idc_it_kw[:, column]
            own_p[:, bus] += facility
            own_q[:, bus] += TANPHI * facility
        for column, _mid in enumerate(MESS_IDS):
            for step in range(h):
                service = mess_location[column][step]
                if service is None:
                    continue
                bus = self.index[self.service_bus[str(service)]]
                # Positive schedule means injection/discharge and therefore
                # reduces the feeder's own demand.
                own_p[step, bus] -= float(mess_p_kw[step, column])
                own_q[step, bus] -= float(mess_q_kvar[step, column])
        return own_p, own_q

    def evaluate(
        self,
        frame: CausalExperimentFrame,
        idc_it_kw: np.ndarray,
        mess_p_kw: np.ndarray,
        mess_q_kvar: np.ndarray,
        mess_location: Sequence[Sequence[Optional[str]]],
    ) -> _StressResult:
        own_p, own_q = self.injections(
            frame, idc_it_kw, mess_p_kw, mess_q_kvar, mess_location
        )
        if self.anchor_p is None:
            self.anchor_p = own_p[0].copy()
            self.anchor_q = own_q[0].copy()
        flow_p = own_p @ self.descendant.T
        flow_q = own_q @ self.descendant.T
        du = (
            (own_p - self.anchor_p[None, :]) @ self.voltage_p.T
            + (own_q - self.anchor_q[None, :]) @ self.voltage_q.T
        )
        u = self.reference_u[None, :] + du
        voltage = np.maximum.reduce(
            (
                np.zeros_like(u),
                (self.nominal_u[None, :] - u)
                / (self.nominal_u - self.low_u)[None, :],
                (u - self.nominal_u[None, :])
                / (self.high_u - self.nominal_u)[None, :],
            )
        )
        line_index = np.asarray([self.index[node] for node in self.line_children])
        loading = np.hypot(flow_p[:, line_index], flow_q[:, line_index]) / self.line_limits
        line = np.max(loading, axis=1) if loading.size else np.zeros(PLANNING_HORIZON_STEPS)
        idc_transformer = PUE * idc_it_kw / IDC_TRANSFORMER_LIMIT_KW
        service_transformer = np.zeros_like(mess_p_kw)
        for column, _mid in enumerate(MESS_IDS):
            for step in range(PLANNING_HORIZON_STEPS):
                service = mess_location[column][step]
                if service is not None:
                    service_transformer[step, column] = math.hypot(
                        float(mess_p_kw[step, column]),
                        float(mess_q_kvar[step, column]),
                    ) / self.service_kva[str(service)]
        transformer = np.maximum(
            np.max(idc_transformer, axis=1),
            np.max(service_transformer, axis=1),
        )
        voltage_step = np.max(voltage, axis=1)
        per_step = np.maximum.reduce((voltage_step, line, transformer))
        step = int(np.argmax(per_step))
        component_values = {
            "VOLTAGE": float(voltage_step[step]),
            "LINE": float(line[step]),
            "TRANSFORMER": float(transformer[step]),
        }
        worst_type = max(component_values, key=component_values.get)
        if worst_type == "VOLTAGE":
            worst_element = self.nodes[int(np.argmax(voltage[step]))]
        elif worst_type == "LINE":
            worst_element = self.line_children[int(np.argmax(loading[step]))]
        else:
            idc_col = int(np.argmax(idc_transformer[step]))
            mess_col = int(np.argmax(service_transformer[step]))
            if idc_transformer[step, idc_col] >= service_transformer[step, mess_col]:
                worst_element = IDCS[idc_col]
            else:
                worst_element = str(mess_location[mess_col][step])
        return _StressResult(
            per_step=per_step,
            voltage=voltage_step,
            line=line,
            transformer=transformer,
            worst_type=worst_type,
            worst_element=worst_element,
        )

    def screen_route_support(
        self,
        frame: CausalExperimentFrame,
        idc_it_kw: np.ndarray,
        mess_p_kw: np.ndarray,
        mess_q_kvar: np.ndarray,
        mess_location: Sequence[Sequence[Optional[str]]],
        candidates: Sequence[tuple[int, str]],
        support_kw: float = 100.0,
    ) -> np.ndarray:
        """Batch-score the best active-P direction at each route destination.

        Storage can charge or discharge.  Screening only positive injection
        reverses location rankings during upper-voltage stress and can remove
        the destination that the full H54 recourse would select.  Evaluate the
        same bounded probe in both directions and retain the lower stress.
        """
        if not candidates:
            return np.empty(0, dtype=float)
        own_p, own_q = self.injections(
            frame, idc_it_kw, mess_p_kw, mess_q_kvar, mess_location
        )
        if self.anchor_p is None:
            self.anchor_p = own_p[0].copy()
            self.anchor_q = own_q[0].copy()
        steps_one = np.asarray(
            [int(step) for step, _service in candidates], dtype=int
        )
        steps = np.repeat(steps_one, 2)
        batch_p = own_p[steps].copy()
        batch_q = own_q[steps].copy()
        for candidate_index, (_step, service) in enumerate(candidates):
            bus = self.index[self.service_bus[str(service)]]
            # Even row: discharge/injection.  Odd row: charge/withdrawal.
            batch_p[2 * candidate_index, bus] -= support_kw
            batch_p[2 * candidate_index + 1, bus] += support_kw
        flow_p = batch_p @ self.descendant.T
        flow_q = batch_q @ self.descendant.T
        du = (
            (batch_p - self.anchor_p[None, :]) @ self.voltage_p.T
            + (batch_q - self.anchor_q[None, :]) @ self.voltage_q.T
        )
        u = self.reference_u[None, :] + du
        voltage = np.maximum.reduce(
            (
                np.zeros_like(u),
                (self.nominal_u[None, :] - u)
                / (self.nominal_u - self.low_u)[None, :],
                (u - self.nominal_u[None, :])
                / (self.high_u - self.nominal_u)[None, :],
            )
        )
        line_index = np.asarray([self.index[node] for node in self.line_children])
        line = np.max(
            np.hypot(flow_p[:, line_index], flow_q[:, line_index])
            / self.line_limits,
            axis=1,
        )
        idc = np.max(PUE * idc_it_kw[steps] / IDC_TRANSFORMER_LIMIT_KW, axis=1)
        service = np.repeat(
            np.asarray(
                [
                    support_kw / self.service_kva[str(name)]
                    for _step, name in candidates
                ]
            ),
            2,
        )
        directional = np.maximum.reduce(
            (np.max(voltage, axis=1), line, idc, service)
        )
        return np.min(directional.reshape(len(candidates), 2), axis=1)


class CompactH54JointPlanner(RetainedH54JointPlanner):
    """Existing retained adapter with a low-latency runtime solve path."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._kernel: Optional[_RadialStressKernel] = None
        self._reference: Optional[Mapping[str, Any]] = None
        self._kernel_issue: Optional[int] = None
        candidate_limit = int(
            os.environ.get("PFR_ONLINE_CANDIDATE_K", str(DEFAULT_CANDIDATE_LIMIT))
        )
        if candidate_limit not in ALLOWED_DEVELOPMENT_K:
            raise RuntimeContractError(
                "online candidate K must be one of "
                f"{ALLOWED_DEVELOPMENT_K}; observed={candidate_limit}"
            )
        self.candidate_limit = candidate_limit
        self.candidate_limit_frozen = (
            os.environ.get("PFR_ONLINE_CANDIDATE_K_FROZEN", "0") == "1"
        )

    def _ensure_kernel(
        self, state: MutableMethodState, frame: CausalExperimentFrame, output: Any
    ) -> _RadialStressKernel:
        self._initialize()
        if self._kernel is None or self._kernel_issue != frame.issue:
            running = {
                uid: row for uid, row in self._workload_state(state)[1].items()
            }
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
            # Immutable CSV/NPZ/parquet assets are cached inside the retained
            # loader, but the edge records are rebuilt because transformer tap
            # ratios belong to the current causal OpenDSS anchor.
            static_context = self.science.prepare_static_context(
                self.ar2, self.b6, reference, self.b4
            )
            self._reference = reference
            self._static_context = static_context
            self._kernel = _RadialStressKernel(static_context, reference)
            self._kernel_issue = int(frame.issue)
        return self._kernel

    @staticmethod
    def _lex(result: _StressResult, actuation: float = 0.0) -> tuple[float, float, float]:
        return (*result.objective, float(actuation))

    def _workload_schedule(
        self,
        kernel: _RadialStressKernel,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        mess_location: Sequence[Sequence[Optional[str]]],
    ) -> tuple[
        np.ndarray,
        dict[str, str],
        dict[str, int],
        dict[str, str],
        dict[str, tuple[float, ...]],
        dict[str, int],
        Mapping[str, Any],
    ]:
        h = PLANNING_HORIZON_STEPS
        idc_it = np.zeros((h, len(IDCS)), dtype=float)
        gpu = np.zeros_like(idc_it)
        placements: dict[str, str] = {}
        starts: dict[str, int] = {}
        racks: dict[str, str] = {}
        wan_schedules: dict[str, tuple[float, ...]] = {}
        wan_required: dict[str, int] = {}
        cap = self.scope["cap"].copy()
        rack_rows = {
            str(row.rack_pool_id): row for row in cap.itertuples(index=False)
        }
        rack_gpu = {
            rack: np.zeros(h, dtype=float) for rack in sorted(rack_rows)
        }
        rack_power = {
            rack: np.zeros(h, dtype=float) for rack in sorted(rack_rows)
        }
        wan_index = self.scope["wan_cap"].set_index("oracle_step")
        wan_available = np.asarray(
            [
                float(wan_index.loc[frame.issue + step, "public_path_safe_capacity_GB_per_5min"])
                if frame.issue + step in wan_index.index
                else 0.0
                for step in range(h)
            ],
            dtype=float,
        )
        if np.any(wan_available < -1e-12) or not np.all(np.isfinite(wan_available)):
            raise RuntimeContractError("compact H54 WAN authority contains invalid capacity")
        zero_p = np.zeros((h, len(MESS_IDS)), dtype=float)
        zero_q = np.zeros_like(zero_p)
        queued = []
        for uid, job in sorted(state.jobs.items()):
            if job.lifecycle == "COMPLETED":
                continue
            site = _effective_job_site(job)
            placements[uid] = site
            if job.lifecycle != "QUEUED":
                starts[uid] = frame.issue
                duration = min(
                    h,
                    max(1, int(math.ceil(job.remaining_work_gpu_hours / (job.source.requested_gpu * STEP_HOURS) - 1e-12))),
                )
                column = IDCS.index(site)
                power = self._scope_job(uid, job)["IT_power_kW"]
                rack = str(job.logical_rack_id)
                if rack not in rack_rows:
                    rack = self._rack_for(uid, site)
                idc_it[:duration, column] += float(power)
                gpu[:duration, column] += float(job.source.requested_gpu)
                rack_gpu[rack][:duration] += float(job.source.requested_gpu)
                rack_power[rack][:duration] += float(power)
                racks[uid] = rack
            else:
                queued.append((uid, job))
            wan_schedules[uid] = (0.0,) * h
            wan_required[uid] = 0
        baseline = kernel.evaluate(frame, idc_it, zero_p, zero_q, mess_location)
        site_order = list(IDCS)
        if config.spatial_workload_migration:
            site_scores = []
            for site in IDCS:
                trial = idc_it.copy()
                trial[:, IDCS.index(site)] += 1.0
                score = kernel.evaluate(
                    frame, trial, zero_p, zero_q, mess_location
                ).objective
                site_scores.append((score, site))
            site_order = [site for _score, site in sorted(site_scores)]
        workload_domain_before = 0
        workload_exact_infeasible = 0
        workload_evaluated = 0
        for uid, job in sorted(
            queued,
            key=lambda item: (
                item[1].source.latest_start_step,
                item[1].source.deadline_step,
                item[1].source.arrival_step,
                item[0],
            ),
        ):
            row = self._scope_job(uid, job)
            duration = max(1, int(row["duration_steps"]))
            latest = min(
                int(job.source.latest_start_step),
                int(job.source.deadline_step) - duration,
                frame.issue + h - 1,
            )
            if latest < frame.issue:
                raise RuntimeContractError(f"compact H54 job {uid} has no deadline-feasible start")
            current_site = _effective_job_site(job)
            sites = (
                tuple(dict.fromkeys((current_site, *site_order)))
                if config.spatial_workload_migration
                else (current_site,)
            )
            if config.temporal_workload_shift:
                offsets = {0, latest - frame.issue}
                window = np.convolve(
                    baseline.per_step,
                    np.ones(min(duration, h), dtype=float),
                    mode="valid",
                )
                for index in np.argsort(window)[:4]:
                    if int(index) <= latest - frame.issue:
                        offsets.add(int(index))
            else:
                offsets = {0}
            candidates = []
            for site in sites:
                column = IDCS.index(site)
                destination_racks = sorted(
                    {
                        str(row["rack_pool_id"])
                        for row in self.scope["domains"][uid]
                        if str(row["destination_IDC_id"]) == site
                    }
                )
                for rack in destination_racks:
                    rack_row = rack_rows[rack]
                    for offset in sorted(offsets):
                        workload_domain_before += 1
                        absolute_start = frame.issue + int(offset)
                        if absolute_start + duration > int(job.source.deadline_step):
                            workload_exact_infeasible += 1
                            continue
                        end = min(h, offset + duration)
                        if end <= offset:
                            workload_exact_infeasible += 1
                            continue
                        if np.any(
                            gpu[offset:end, column] + job.source.requested_gpu
                            > MODELED_GPU_CAPACITY_PER_IDC + 1e-9
                        ):
                            workload_exact_infeasible += 1
                            continue
                        if np.any(
                            rack_gpu[rack][offset:end] + job.source.requested_gpu
                            > float(rack_row.deliverable_active_gpu_capacity) + 1e-9
                        ):
                            workload_exact_infeasible += 1
                            continue
                        trial = idc_it.copy()
                        trial[offset:end, column] += float(row["IT_power_kW"])
                        if np.any(
                            PUE * trial[:, column]
                            > IDC_TRANSFORMER_LIMIT_KW + 1e-9
                        ) or np.any(
                            rack_power[rack][offset:end] + float(row["IT_power_kW"])
                            > float(rack_row.rack_power_cap_kw) + 1e-9
                        ):
                            workload_exact_infeasible += 1
                            continue
                        # Queued datasets are frozen as pre-staged at every
                        # IDC.  WAN/checkpoint bytes belong only to migration
                        # of an already-running job.
                        required_gb = 0.0
                        committed_gb = 0.0
                        if job.prestart_wan_transferred_bytes > 0:
                            if job.prestart_wan_target_idc != site:
                                workload_exact_infeasible += 1
                                continue
                            committed_gb = float(job.prestart_wan_transferred_bytes) / 1e9
                        remaining_gb = max(0.0, required_gb - committed_gb)
                        trial_wan = wan_available.copy()
                        schedule = np.zeros(h, dtype=float)
                        for send_step in range(max(0, int(offset))):
                            amount = min(remaining_gb, trial_wan[send_step])
                            schedule[send_step] = amount
                            trial_wan[send_step] -= amount
                            remaining_gb -= amount
                            if remaining_gb <= 1e-12:
                                break
                        if remaining_gb > 1e-9:
                            workload_exact_infeasible += 1
                            continue
                        result = kernel.evaluate(
                            frame, trial, zero_p, zero_q, mess_location
                        )
                        actuation = (
                            float(offset) / h
                            + (1.0 if site != job.source.origin_idc else 0.0)
                            + float(np.sum(schedule)) / max(1.0, required_gb)
                        )
                        workload_evaluated += 1
                        candidates.append(
                            (
                                self._lex(result, actuation),
                                site,
                                rack,
                                offset,
                                end,
                                trial,
                                result,
                                trial_wan,
                                tuple(float(value) for value in schedule),
                                int(round(required_gb * 1e9)),
                            )
                        )
            if not candidates:
                raise RuntimeContractError(f"compact H54 job {uid} has no GPU/transformer-feasible placement")
            (
                _,
                site,
                rack,
                offset,
                end,
                idc_it,
                baseline,
                wan_available,
                selected_wan,
                required_bytes,
            ) = min(
                candidates, key=lambda value: (value[0], value[1], value[2], value[3])
            )
            column = IDCS.index(site)
            gpu[offset:end, column] += float(job.source.requested_gpu)
            rack_gpu[rack][offset:end] += float(job.source.requested_gpu)
            rack_power[rack][offset:end] += float(row["IT_power_kW"])
            placements[uid] = site
            starts[uid] = frame.issue + offset
            racks[uid] = rack
            wan_schedules[uid] = selected_wan
            wan_required[uid] = required_bytes
        return (
            idc_it,
            placements,
            starts,
            racks,
            wan_schedules,
            wan_required,
            {
                "physical_domain_size": workload_domain_before,
                "queued_dataset_residency_mode": "PRESTAGED_AT_ALL_12_IDCS",
                "queued_remote_placement_transfer_bytes": 0,
                "exact_infeasible_removed": workload_exact_infeasible,
                "bounded_candidates_evaluated": workload_evaluated,
                "temporal_offsets_per_job_upper_bound": 6,
                "spatial_destinations_retained": len(IDCS)
                if config.spatial_workload_migration
                else 1,
            },
        )

    @staticmethod
    def _stationary_locations(state: MutableMethodState) -> list[list[Optional[str]]]:
        result: list[list[Optional[str]]] = []
        for mid in MESS_IDS:
            if not state.mess_in_transit[mid]:
                result.append([state.mess_location[mid]] * PLANNING_HORIZON_STEPS)
                continue
            destination = state.mess_route_destination[mid]
            if destination is None:
                raise RuntimeContractError("in-transit MESS lacks a destination")
            remaining = max(
                0,
                len(state.mess_route_energy_profile_kwh[mid])
                - int(state.mess_route_profile_index[mid]),
            )
            result.append(
                [None] * min(remaining, PLANNING_HORIZON_STEPS)
                + [destination] * max(0, PLANNING_HORIZON_STEPS - remaining)
            )
        return result

    def _locations_for_template(
        self,
        state: MutableMethodState,
        template: _MobilityTemplate,
    ) -> list[list[Optional[str]]]:
        locations = self._stationary_locations(state)
        if template.is_stay:
            return locations
        mid = template.mess_id
        if mid not in MOBILITY_ELIGIBLE_MESS_IDS:
            raise _CandidateInfeasible("mobility template lacks an eligible MESS")
        if state.mess_in_transit[mid]:
            raise _CandidateInfeasible("cannot schedule a new route during committed transit")
        departure = int(template.departure_offset)
        arrival = departure + int(template.transit_steps)
        if not 0 <= departure < arrival <= PLANNING_HORIZON_STEPS:
            raise _CandidateInfeasible("mobility template escaped H54")
        column = MESS_IDS.index(mid)
        current = state.mess_location[mid]
        locations[column] = (
            [current] * departure
            + [None] * int(template.transit_steps)
            + [template.destination_service_id]
            * (PLANNING_HORIZON_STEPS - arrival)
        )
        return locations

    def _mobility_templates(
        self,
        *,
        kernel: _RadialStressKernel,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        effective_steps: int,
        output: Path,
    ) -> tuple[list[_MobilityTemplate], Mapping[str, Any]]:
        """Build physical candidates, then apply the explicit bounded approximation."""

        stay = _MobilityTemplate(
            departure_offset=None,
            destination_service_id="FLEET_STAY",
            route_rank=0,
            route_slot=None,
            transit_steps=0,
            energy_kwh=0.0,
            source="FLEET_STATE",
            generation_reason="MANDATORY_STAY_OR_COMMITTED_TRANSIT",
            mess_id=None,
        )
        if not config.h54_capability_mask["mess_mobility"]:
            return [stay], {
                "physical_domain_size": 1,
                "exact_infeasible_removed": 0,
                "exact_k3_dominated_removed": 0,
                "bounded_domain_size": 1,
                "bounded_truncation_removed": 0,
                "candidate_limit_k": self.candidate_limit,
            }

        mobility_path = Path(frame.planning_mobility_npz_path).resolve()
        if not mobility_path.is_file():
            raise RuntimeContractError(f"bounded H54 mobility source is missing: {mobility_path}")
        if _file_sha256(mobility_path) != frame.planning_mobility_npz_sha256:
            raise RuntimeContractError("bounded H54 mobility SHA-256 drift")
        mobility = self.science._npz_immutable(mobility_path)
        route_df = self._static_context["route_df"].sort_values(
            "slot", kind="mergesort"
        )
        slots = route_df["slot"].to_numpy(dtype=np.int64)
        if not np.array_equal(slots, np.arange(len(route_df), dtype=np.int64)):
            raise RuntimeContractError("bounded H54 route slots are not contiguous")
        sources = route_df["source_service_id"].astype(str).to_numpy()
        destinations = route_df["destination_service_id"].astype(str).to_numpy()
        ranks = route_df["rank"].to_numpy(dtype=np.int64)
        profile_steps = np.asarray(
            mobility["profile_safe_horizon_steps"], dtype=np.int64
        )
        safe_energy = np.asarray(mobility["safe_energy_kWh"], dtype=float)
        if profile_steps.shape[:2] != (PLANNING_HORIZON_STEPS, len(route_df)):
            raise RuntimeContractError("bounded H54 mobility profile shape drift")
        connection_delay = int(
            self.science.d2_connection_delay_steps(self.scope, output)
        )
        departure_grid = tuple(range(0, min(12, effective_steps))) + tuple(
            range(12, effective_steps, 3)
        )
        peak_reserve = float(self.science.PEAK_RESERVE)
        physical: list[_MobilityTemplate] = []
        exact_removed = 0
        for mid in MOBILITY_ELIGIBLE_MESS_IDS:
            if state.mess_in_transit[mid]:
                continue
            current = state.mess_location[mid]
            source_slots = np.flatnonzero(sources == current)
            for departure in departure_grid:
                optimistic_energy = min(
                    MESS_CAPACITY_KWH,
                    float(state.mess_energy_kwh[mid])
                    + departure
                    * MESS_CHARGE_EFFICIENCY
                    * STEP_HOURS
                    * MESS_CHARGE_LIMIT_KW,
                )
                for slot in source_slots.tolist():
                    travel = int(profile_steps[departure, slot])
                    transit = travel + connection_delay
                    energy = float(safe_energy[departure, slot])
                    if (
                        transit <= 0
                        # Arrival at the terminal boundary leaves no in-horizon
                        # connected dispatch step.  Such a move consumes energy
                        # but cannot improve any retained H54 stress component and
                        # is exactly dominated by staying at the source.
                        or departure + transit >= effective_steps
                        or not math.isfinite(energy)
                        or energy < 0.0
                        or optimistic_energy
                        < MESS_FLOOR_KWH + max(peak_reserve, energy) - 1e-9
                    ):
                        exact_removed += 1
                        continue
                    physical.append(
                        _MobilityTemplate(
                            departure_offset=int(departure),
                            destination_service_id=str(destinations[slot]),
                            route_rank=int(ranks[slot]),
                            route_slot=int(slot),
                            transit_steps=transit,
                            energy_kwh=energy,
                            source=current,
                            generation_reason="CAUSAL_H54_PREPOSITION_CANDIDATE",
                            mess_id=mid,
                        )
                    )

        # K=3 route dominance is exact within a fixed departure/source/destination:
        # a route with no shorter duration and no lower energy cannot improve any
        # retained hard resource constraint or stress trajectory.
        nondominated: list[_MobilityTemplate] = []
        dominated_removed = 0
        groups: dict[tuple[str, int, str], list[_MobilityTemplate]] = {}
        for candidate in physical:
            groups.setdefault(
                (
                    str(candidate.mess_id),
                    int(candidate.departure_offset),
                    candidate.destination_service_id,
                ),
                [],
            ).append(candidate)
        for group in groups.values():
            for candidate in group:
                dominated = any(
                    other.identity != candidate.identity
                    and other.transit_steps <= candidate.transit_steps
                    and other.energy_kwh <= candidate.energy_kwh + 1e-9
                    and (
                        other.transit_steps < candidate.transit_steps
                        or other.energy_kwh < candidate.energy_kwh - 1e-9
                        or (
                            other.transit_steps == candidate.transit_steps
                            and abs(other.energy_kwh - candidate.energy_kwh) <= 1e-9
                            and other.route_rank < candidate.route_rank
                        )
                    )
                    for other in group
                )
                if dominated:
                    dominated_removed += 1
                else:
                    nondominated.append(candidate)

        zero_it = np.zeros((PLANNING_HORIZON_STEPS, len(IDCS)), dtype=float)
        zero_p = np.zeros((PLANNING_HORIZON_STEPS, len(MESS_IDS)), dtype=float)
        zero_q = np.zeros_like(zero_p)
        stay_locations = self._stationary_locations(state)
        baseline = kernel.evaluate(frame, zero_it, zero_p, zero_q, stay_locations)
        screen_rows: list[tuple[int, str]] = []
        for candidate in nondominated:
            arrival = int(candidate.departure_offset) + candidate.transit_steps
            support_step = min(
                range(arrival, effective_steps),
                key=lambda step: (-baseline.per_step[step], step),
            )
            screen_rows.append((support_step, candidate.destination_service_id))
        screen_scores = kernel.screen_route_support(
            frame,
            zero_it,
            zero_p,
            zero_q,
            stay_locations,
            screen_rows,
        )
        ranked = sorted(
            zip(nondominated, screen_scores.tolist()),
            key=lambda row: (
                float(row[1]),
                float(row[0].energy_kwh),
                int(row[0].transit_steps),
                int(row[0].departure_offset),
                row[0].destination_service_id,
                row[0].route_rank,
            ),
        )

        mandatory: list[_MobilityTemplate] = [stay]
        if state.active_plan is not None:
            for mid in MOBILITY_ELIGIBLE_MESS_IDS:
                planned_departure = state.active_plan.mess_departure_issue.get(mid)
                planned_destination = state.active_plan.mess_destination.get(mid)
                planned_rank = state.active_plan.mess_native_route_rank.get(mid)
                if planned_departure is not None and int(planned_departure) >= frame.issue:
                    offset = int(planned_departure) - frame.issue
                    previous = next(
                        (
                            candidate
                            for candidate in nondominated
                            if candidate.mess_id == mid
                            and candidate.departure_offset == offset
                            and candidate.destination_service_id == planned_destination
                            and candidate.route_rank == int(planned_rank)
                        ),
                        None,
                    )
                    if previous is not None:
                        mandatory.append(
                            _MobilityTemplate(
                                **{
                                    **previous.__dict__,
                                    "generation_reason": "MANDATORY_PREVIOUS_CAUSAL_PLAN",
                                }
                            )
                        )
        screen_score_by_identity = {
            candidate.identity: float(score) for candidate, score in ranked
        }
        commitment_window_steps = int(config.periodic_replan_steps or 6)
        ordered = _ordered_mobility_candidates(
            mandatory=mandatory,
            ranked=ranked,
            commitment_window_steps=commitment_window_steps,
        )
        selected = ordered[: self.candidate_limit]
        return selected, {
            "physical_domain_size": 1 + len(physical),
            "exact_infeasible_removed": exact_removed,
            "exact_k3_dominated_removed": dominated_removed,
            "feasibility_preserving_domain_size": 1 + len(nondominated),
            "bounded_domain_size": len(selected),
            "bounded_truncation_removed": max(
                0, 1 + len(nondominated) - len(selected)
            ),
            "candidate_limit_k": self.candidate_limit,
            "previous_plan_retained": any(
                candidate.generation_reason == "MANDATORY_PREVIOUS_CAUSAL_PLAN"
                for candidate in selected
            ),
            "stay_retained": True,
            "future_preposition_candidates_enabled": True,
            "departure_grid": list(departure_grid),
            "heuristic_role": "BOUNDED_DOMAIN_GENERATION_ONLY",
            "candidate_selection_mode": (
                "COMMITMENT_WINDOW_DESTINATION_ROUND_ROBIN_THEN_GLOBAL_SCORE"
            ),
            "candidate_screen_dispatch_domain": (
                "BIDIRECTIONAL_ACTIVE_P_100KW"
            ),
            "commitment_window_steps": commitment_window_steps,
            "actionable_candidate_count": sum(
                candidate.departure_offset is not None
                and int(candidate.departure_offset) < commitment_window_steps
                for candidate, _score in ranked
            ),
            "selected_actionable_candidate_count": sum(
                candidate.departure_offset is not None
                and int(candidate.departure_offset) < commitment_window_steps
                for candidate in selected
            ),
            "bounded_candidates": [
                {
                    "is_stay": bool(candidate.is_stay),
                    "mess_id": candidate.mess_id,
                    "departure_offset": candidate.departure_offset,
                    "destination_service_id": candidate.destination_service_id,
                    "route_rank": int(candidate.route_rank),
                    "transit_steps": int(candidate.transit_steps),
                    "energy_kwh": float(candidate.energy_kwh),
                    "screen_stress": screen_score_by_identity.get(
                        candidate.identity
                    ),
                    "generation_reason": candidate.generation_reason,
                }
                for candidate in selected
            ],
        }

    def _dispatch(
        self,
        kernel: _RadialStressKernel,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        idc_it: np.ndarray,
        locations: list[list[Optional[str]]],
        effective_steps: int,
        mobility_template: _MobilityTemplate,
    ) -> tuple[np.ndarray, np.ndarray, _StressResult]:
        h = PLANNING_HORIZON_STEPS
        p = np.zeros((h, len(MESS_IDS)), dtype=float)
        q = np.zeros_like(p)
        result = kernel.evaluate(frame, idc_it, p, q, locations)
        if not config.h54_capability_mask["mess_dispatch"]:
            return p, q, result
        # Repay carried support debt first at the least-stressed available steps.
        energy = {mid: float(state.mess_energy_kwh[mid]) for mid in MESS_IDS}
        debt = {mid: float(state.mess_energy_debt_kwh[mid]) for mid in MESS_IDS}
        for column, mid in enumerate(MESS_IDS):
            available = [step for step in range(effective_steps) if locations[column][step] is not None]
            for step in sorted(available, key=lambda value: (result.per_step[value], value)):
                if debt[mid] <= 1e-9:
                    break
                max_charge = min(
                    150.0,
                    MESS_CHARGE_LIMIT_KW,
                    (MESS_CAPACITY_KWH - energy[mid]) / (MESS_CHARGE_EFFICIENCY * STEP_HOURS),
                    debt[mid] / (MESS_CHARGE_EFFICIENCY * STEP_HOURS),
                )
                if max_charge <= 1e-9:
                    continue
                p[step, column] -= max_charge
                energy[mid] += MESS_CHARGE_EFFICIENCY * max_charge * STEP_HOURS
                debt[mid] = max(0.0, debt[mid] - MESS_CHARGE_EFFICIENCY * max_charge * STEP_HOURS)
            if debt[mid] > 1e-6:
                raise _CandidateInfeasible(
                    f"bounded H54 cannot recover carried energy debt for {mid}"
                )
        result = kernel.evaluate(frame, idc_it, p, q, locations)
        # Add paired support/recovery templates only when they improve the
        # frozen lexicographic stress tuple. Pairing makes terminal energy debt
        # exactly zero without a monetary rebound penalty.
        for column, mid in enumerate(MESS_IDS):
            available = [
                step
                for step in range(effective_steps)
                if locations[column][step] is not None
            ]
            if len(available) < 2:
                continue
            discharge_step = min(available, key=lambda s: (-result.per_step[s], s))
            charge_step = min(available, key=lambda s: (result.per_step[s], s))
            if discharge_step == charge_step:
                continue
            discharge = 100.0
            charge = discharge / (MESS_CHARGE_EFFICIENCY**2)
            trial = p.copy()
            trial[discharge_step, column] += discharge
            trial[charge_step, column] -= charge
            level = float(state.mess_energy_kwh[mid])
            feasible = True
            for step in range(effective_steps):
                if state.mess_in_transit[mid]:
                    profile = state.mess_route_energy_profile_kwh[mid]
                    index = int(state.mess_route_profile_index[mid]) + step
                    if index < len(profile):
                        level -= float(profile[index])
                if (
                    mid == mobility_template.mess_id
                    and not mobility_template.is_stay
                    and step == int(mobility_template.departure_offset)
                ):
                    reserve = float(self.science.PEAK_RESERVE)
                    if level < MESS_FLOOR_KWH + max(
                        reserve, mobility_template.energy_kwh
                    ) - 1e-9:
                        feasible = False
                        break
                    level -= mobility_template.energy_kwh
                level += (
                    MESS_CHARGE_EFFICIENCY * max(0.0, -trial[step, column])
                    - max(0.0, trial[step, column]) / MESS_CHARGE_EFFICIENCY
                ) * STEP_HOURS
                if not (MESS_FLOOR_KWH - 1e-9 <= level <= MESS_CAPACITY_KWH + 1e-9):
                    feasible = False
                    break
            if feasible:
                candidate = kernel.evaluate(frame, idc_it, trial, q, locations)
                if self._lex(candidate, float(np.sum(np.abs(trial)))) < self._lex(
                    result, float(np.sum(np.abs(p)))
                ):
                    p, result = trial, candidate
        # Reactive support is debt-free. Coordinate-search the common exact-AC
        # trust-region levels while retaining the PCS circle.
        reactive_steps = sorted(
            range(effective_steps), key=lambda value: (-result.per_step[value], value)
        )[:4]
        for column, _mid in enumerate(MESS_IDS):
            active_steps = [
                step for step in reactive_steps if locations[column][step] is not None
            ]
            if not active_steps:
                continue
            best = (
                self._lex(
                    result,
                    float(np.sum(np.abs(p))) + float(np.sum(np.abs(q))),
                ),
                q,
                result,
            )
            for sign in (-1.0, 1.0):
                trial_q = q.copy()
                for step in active_steps:
                    q_limit = min(
                        210.0,
                        math.sqrt(max(0.0, PCS_KVA**2 - p[step, column] ** 2)),
                    )
                    trial_q[step, column] = sign * q_limit
                candidate = kernel.evaluate(frame, idc_it, p, trial_q, locations)
                key = self._lex(
                    candidate,
                    float(np.sum(np.abs(p))) + float(np.sum(np.abs(trial_q))),
                )
                if key < best[0]:
                    best = (key, trial_q, candidate)
            q, result = best[1], best[2]
        # Final exact resource replay.  Candidate generation may use optimistic
        # SOC only for feasibility-preserving pruning; acceptance uses the
        # selected dispatch, committed profile, route reserve, PCS, and terminal
        # support-debt trajectory without relaxation.
        for column, mid in enumerate(MESS_IDS):
            level = float(state.mess_energy_kwh[mid])
            support_debt = float(state.mess_energy_debt_kwh[mid])
            for step in range(effective_steps):
                if state.mess_in_transit[mid]:
                    profile = state.mess_route_energy_profile_kwh[mid]
                    index = int(state.mess_route_profile_index[mid]) + step
                    if index < len(profile):
                        level -= float(profile[index])
                if (
                    mid == mobility_template.mess_id
                    and not mobility_template.is_stay
                    and step == int(mobility_template.departure_offset)
                ):
                    reserve = float(self.science.PEAK_RESERVE)
                    if level < MESS_FLOOR_KWH + max(
                        reserve, mobility_template.energy_kwh
                    ) - 1e-9:
                        raise _CandidateInfeasible("route departure reserve violated")
                    level -= mobility_template.energy_kwh
                discharge = max(0.0, float(p[step, column]))
                charge = max(0.0, -float(p[step, column]))
                if math.hypot(float(p[step, column]), float(q[step, column])) > PCS_KVA + 1e-7:
                    raise _CandidateInfeasible("PCS P-Q circle violated")
                level += (
                    MESS_CHARGE_EFFICIENCY * charge
                    - discharge / MESS_CHARGE_EFFICIENCY
                ) * STEP_HOURS
                support_debt = max(
                    0.0,
                    support_debt
                    + discharge * STEP_HOURS / MESS_CHARGE_EFFICIENCY
                    - charge * STEP_HOURS * MESS_CHARGE_EFFICIENCY,
                )
                if not MESS_FLOOR_KWH - 1e-7 <= level <= MESS_CAPACITY_KWH + 1e-7:
                    raise _CandidateInfeasible("MESS SOC bound violated")
            if support_debt > 1e-6:
                raise _CandidateInfeasible("terminal support-energy debt is nonzero")
        return p, q, result

    def solve(
        self,
        *,
        state: MutableMethodState,
        config: MethodConfig,
        frame: CausalExperimentFrame,
        migration_authority: Optional[MigrationAuthority],
        evaluation_steps_remaining: int,
    ) -> tuple[SlowDiscretePlan, Mapping[str, Any]]:
        del migration_authority  # Datasets are frozen prestaged; no running migration is invented.
        started = time.monotonic()
        issue_root = self.output_root / "_COMPACT_H54" / config.comparison_method_id.value
        issue_root.mkdir(parents=True, exist_ok=True)
        kernel = self._ensure_kernel(state, frame, issue_root)
        effective_steps = min(PLANNING_HORIZON_STEPS, int(evaluation_steps_remaining))
        if effective_steps <= 0:
            raise RuntimeContractError("compact H54 lacks an evaluation horizon")
        templates, mobility_audit = self._mobility_templates(
            kernel=kernel,
            state=state,
            config=config,
            frame=frame,
            effective_steps=effective_steps,
            output=issue_root,
        )
        evaluations: list[tuple[tuple[float, float, float], _CandidateEvaluation, Mapping[str, Any]]] = []
        rejected: list[Mapping[str, Any]] = []
        for template in templates:
            try:
                candidate_locations = self._locations_for_template(state, template)
                (
                    candidate_it,
                    candidate_placements,
                    candidate_starts,
                    candidate_racks,
                    candidate_wan,
                    candidate_wan_required,
                    workload_audit,
                ) = self._workload_schedule(
                    kernel, state, config, frame, candidate_locations
                )
                candidate_p, candidate_q, candidate_stress = self._dispatch(
                    kernel,
                    state,
                    config,
                    frame,
                    candidate_it,
                    candidate_locations,
                    effective_steps,
                    template,
                )
                worst = float(np.max(candidate_stress.per_step[:effective_steps]))
                if worst > 1.0 + 1e-9:
                    raise _CandidateInfeasible(
                        f"predicted hard-grid stress {worst:.12g} exceeds 1"
                    )
                remote_jobs = sum(
                    int(
                        destination
                        != state.jobs[uid].source.origin_idc
                    )
                    for uid, destination in candidate_placements.items()
                    if uid in state.jobs
                )
                wait_steps = sum(
                    max(0, int(start) - frame.issue)
                    for start in candidate_starts.values()
                )
                actuation = (
                    float(np.sum(np.abs(candidate_p))) / max(1.0, 550.0 * effective_steps)
                    + float(np.sum(np.abs(candidate_q))) / max(1.0, PCS_KVA * effective_steps)
                    + float(template.energy_kwh) / MESS_CAPACITY_KWH
                    + float(remote_jobs)
                    + float(wait_steps) / max(1, effective_steps)
                )
                evaluation = _CandidateEvaluation(
                    template=template,
                    locations=candidate_locations,
                    idc_it_kw=candidate_it,
                    placements=dict(candidate_placements),
                    starts=dict(candidate_starts),
                    racks=dict(candidate_racks),
                    wan_schedules_gb=dict(candidate_wan),
                    wan_required_bytes=dict(candidate_wan_required),
                    mess_p_kw=candidate_p,
                    mess_q_kvar=candidate_q,
                    stress=candidate_stress,
                )
                evaluations.append((self._lex(candidate_stress, actuation), evaluation, workload_audit))
            except _CandidateInfeasible as exc:
                rejected.append(
                    {
                        "identity": list(template.identity),
                        "reason": str(exc),
                    }
                )
        if not evaluations:
            raise RuntimeContractError(
                "bounded H54 has no candidate satisfying unchanged hard constraints; "
                f"rejections={rejected[:5]}"
            )
        _, selected, workload_audit = min(
            evaluations,
            key=lambda row: (
                row[0],
                "" if row[1].template.mess_id is None else row[1].template.mess_id,
                row[1].template.destination_service_id,
                row[1].template.route_rank,
                -1
                if row[1].template.departure_offset is None
                else int(row[1].template.departure_offset),
            ),
        )
        locations = selected.locations
        idc_it = selected.idc_it_kw
        placements = dict(selected.placements)
        starts = dict(selected.starts)
        racks = dict(selected.racks)
        wan_schedule = dict(selected.wan_schedules_gb)
        wan_required = dict(selected.wan_required_bytes)
        p = selected.mess_p_kw
        q = selected.mess_q_kvar
        result = selected.stress
        selected_template = selected.template
        destinations = {mid: state.mess_location[mid] for mid in MESS_IDS}
        ranks = {mid: int(state.mess_route_rank[mid]) for mid in MESS_IDS}
        departures: dict[str, Optional[int]] = {mid: None for mid in MESS_IDS}
        for mid in MOBILITY_ELIGIBLE_MESS_IDS:
            if state.mess_in_transit[mid]:
                destinations[mid] = str(state.mess_route_destination[mid])
                ranks[mid] = int(state.mess_route_rank[mid])
            elif not selected_template.is_stay and selected_template.mess_id == mid:
                destinations[mid] = selected_template.destination_service_id
                ranks[mid] = selected_template.route_rank
                departures[mid] = frame.issue + int(selected_template.departure_offset)
        if float(np.max(result.per_step[:effective_steps])) > 1.0 + 1e-9:
            raise RuntimeContractError(
                "compact H54 has no hard-grid-feasible candidate: "
                f"predicted_worst_stress={float(np.max(result.per_step[:effective_steps])):.12g}"
            )
        active = {
            uid: job for uid, job in state.jobs.items() if job.lifecycle != "COMPLETED"
        }
        plan = SlowDiscretePlan(
            plan_id=f"{config.comparison_method_id.value}-{frame.issue}-{state.full_replan_count + 1}",
            valid_from_issue=frame.issue,
            mess_destination=destinations,
            mess_native_route_rank=ranks,
            job_idc_placement=placements,
            checkpoint_migration={uid: None for uid in active},
            gpu_gang_allocation={
                uid: tuple(
                    f"{racks[uid]}:PFR-GPU:{uid}:{index}"
                    for index in range(job.source.requested_gpu)
                )
                for uid, job in active.items()
            },
            job_start_issue=starts,
            coarse_charging_kw={mid: tuple(float(max(0.0, -p[step, column])) for step in range(PLANNING_HORIZON_STEPS)) for column, mid in enumerate(MESS_IDS)},
            coarse_discharging_kw={mid: tuple(float(max(0.0, p[step, column])) for step in range(PLANNING_HORIZON_STEPS)) for column, mid in enumerate(MESS_IDS)},
            coarse_reactive_kvar={mid: tuple(float(q[step, column]) for step in range(PLANNING_HORIZON_STEPS)) for column, mid in enumerate(MESS_IDS)},
            mess_departure_issue=departures,
            job_wan_send_gb=wan_schedule,
            job_wan_required_bytes=wan_required,
        )
        plan.validate()
        runtime = time.monotonic() - started
        certificate = {
            "adapter_id": COMPACT_ADAPTER_ID,
            "objective_authority": OBJECTIVE_AUTHORITY,
            "online_domain_authority": ONLINE_DOMAIN_AUTHORITY,
            "capability_mask": dict(config.h54_capability_mask),
            "solver": "DETERMINISTIC_VECTORIZED_FINITE_CANDIDATE_LEXICOGRAPHIC_SEARCH",
            "solution_status": "LEXICOGRAPHIC_OPTIMUM_OVER_RECORDED_RESTRICTED_ONLINE_DOMAIN",
            "global_miqcp_optimality_claimed": False,
            "retained_full_miqcp_oracle": "science/main.py::build_full",
            "full_miqcp_executed_in_online_loop": False,
            "same_objective_constraints_physical_semantics": True,
            "restricted_online_decision_domain_acknowledged": True,
            "actual_gurobi_used": False,
            "runtime_state_issue": frame.issue,
            "runtime_seconds": runtime,
            "evaluation_steps_remaining": evaluation_steps_remaining,
            "planning_horizon_steps": PLANNING_HORIZON_STEPS,
            "effective_episode_steps": effective_steps,
            "candidate_limit_k": self.candidate_limit,
            "candidate_limit_frozen": self.candidate_limit_frozen,
            "candidate_limit_development_grid": list(ALLOWED_DEVELOPMENT_K),
            "mobility_domain_reduction": dict(mobility_audit),
            "workload_domain_reduction": dict(workload_audit),
            "bounded_candidates_hard_feasible": len(evaluations),
            "bounded_candidates_hard_rejected": len(rejected),
            "bounded_candidate_rejections": rejected,
            "selected_candidate": {
                "departure_offset": selected_template.departure_offset,
                "destination_service_id": selected_template.destination_service_id,
                "route_rank": selected_template.route_rank,
                "route_slot": selected_template.route_slot,
                "transit_steps": selected_template.transit_steps,
                "safe_energy_kwh": selected_template.energy_kwh,
                "generation_reason": selected_template.generation_reason,
            },
            "objective_worst_predicted_electrical_stress_pu": float(np.max(result.per_step[:effective_steps])),
            "objective_predicted_stress_exposure_pu_hours": float(np.sum(result.per_step[:effective_steps]) * STEP_HOURS),
            "predicted_voltage_stress_max": float(np.max(result.voltage[:effective_steps])),
            "predicted_line_stress_max": float(np.max(result.line[:effective_steps])),
            "predicted_transformer_stress_max": float(np.max(result.transformer[:effective_steps])),
            "predicted_worst_stress_type": result.worst_type,
            "predicted_worst_element_id": result.worst_element,
            "predicted_worst_phase": None,
            "hard_grid_candidate_pass": True,
            "hard_mess_soc_pcs_route_candidate_pass": True,
            "hard_gpu_rack_idc_candidate_pass": True,
            "hard_wan_checkpoint_candidate_pass": True,
            "hard_deadline_candidate_pass": True,
            "terminal_energy_debt_candidate_pass": True,
            "fresh_exact_opendss_commit_required_downstream": True,
            "future_actual_used": False,
            "price_used_by_optimizer": False,
        }
        return plan, certificate
