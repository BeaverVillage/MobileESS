"""PFR4 slow-discrete / fast-continuous controller contract.

The slow layer owns every binary or categorical choice.  The five-minute
layer may only project continuous set-points while preserving the exact slow
plan fingerprint.  Fresh Exact OpenDSS remains a later mandatory commit gate;
the linear screen here can reject a candidate but can never certify a commit.
New causal workload arrivals are published as immutable admission-only slow-plan
revisions before this fast contract is entered; the fast layer never invents or
hides workload membership.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import time
from typing import Callable, Mapping, Optional, Tuple


class SlowFastContractError(ValueError):
    """Raised when a controller action violates the PFR4 architecture."""


def _canonical_hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite_nonnegative(values: Mapping[str, float], name: str) -> None:
    if any(not math.isfinite(float(value)) or float(value) < 0.0 for value in values.values()):
        raise SlowFastContractError(f"{name} must contain finite non-negative values")


@dataclass(frozen=True)
class SlowFastArchitecture:
    planning_horizon_minutes: int = 270
    replanning_interval_minutes: int = 30
    fast_step_minutes: int = 5
    native_route_count: int = 3
    local_repair_enabled: bool = False

    def validate(self) -> None:
        if self.planning_horizon_minutes != 270:
            raise SlowFastContractError("PFR4 planning horizon must remain H54=270 minutes")
        if self.fast_step_minutes != 5:
            raise SlowFastContractError("fast recourse cadence must be five minutes")
        if not (self.fast_step_minutes < self.replanning_interval_minutes <= self.planning_horizon_minutes):
            raise SlowFastContractError("planning, replanning, and fast cadences are not separated")
        if self.replanning_interval_minutes % self.fast_step_minutes:
            raise SlowFastContractError("replanning interval must align to the fast cadence")
        if self.native_route_count != 3:
            raise SlowFastContractError("only the native K=3 route set is authorized")
        if self.local_repair_enabled:
            raise SlowFastContractError("Local Repair is not authorized in PFR4")


@dataclass(frozen=True)
class SlowDiscretePlan:
    plan_id: str
    valid_from_issue: int
    mess_destination: Mapping[str, str]
    mess_native_route_rank: Mapping[str, int]
    job_idc_placement: Mapping[str, str]
    checkpoint_migration: Mapping[str, Optional[str]]
    gpu_gang_allocation: Mapping[str, Tuple[str, ...]]
    # Earliest start-eligibility issue.  Actual RUNNING admission is performed
    # by the common capacity-feasible whole-gang dispatcher.
    job_start_issue: Mapping[str, int]
    coarse_charging_kw: Mapping[str, Tuple[float, ...]]

    def validate(self) -> None:
        if not self.plan_id or self.valid_from_issue < 0:
            raise SlowFastContractError("slow plan identity is invalid")
        mess_ids = set(self.mess_destination)
        if not mess_ids or set(self.mess_native_route_rank) != mess_ids:
            raise SlowFastContractError("every MESS requires a destination and native route")
        if any(int(rank) not in {1, 2, 3} for rank in self.mess_native_route_rank.values()):
            raise SlowFastContractError("route rank must select one of the native K=3 routes")
        jobs = set(self.job_idc_placement)
        if set(self.checkpoint_migration) != jobs:
            raise SlowFastContractError("every job requires placement and migration decisions")
        if set(self.gpu_gang_allocation) != jobs or set(self.job_start_issue) != jobs:
            raise SlowFastContractError("every job requires gang allocation and start decision")
        if any(not tuple(gang) or len(set(gang)) != len(tuple(gang)) for gang in self.gpu_gang_allocation.values()):
            raise SlowFastContractError("GPU gangs must be non-empty and duplicate-free")
        if any(int(issue) < self.valid_from_issue for issue in self.job_start_issue.values()):
            raise SlowFastContractError("job start precedes plan validity")
        if set(self.coarse_charging_kw) != mess_ids:
            raise SlowFastContractError("every MESS requires a coarse charging schedule")
        for schedule in self.coarse_charging_kw.values():
            if not schedule or any(not math.isfinite(float(value)) for value in schedule):
                raise SlowFastContractError("coarse charging schedule is invalid")

    @property
    def fingerprint(self) -> str:
        self.validate()
        return _canonical_hash(asdict(self))


@dataclass(frozen=True)
class FastLayerState:
    issue: int
    mess_soc: Mapping[str, float]
    remaining_work_gpu_hours: Mapping[str, float]

    def validate(self) -> None:
        if self.issue < 0:
            raise SlowFastContractError("issue must be non-negative")
        if any(not math.isfinite(float(soc)) or not 0.0 <= float(soc) <= 1.0 for soc in self.mess_soc.values()):
            raise SlowFastContractError("SOC must lie in [0,1]")
        _finite_nonnegative(self.remaining_work_gpu_hours, "remaining work")


@dataclass(frozen=True)
class FastControl:
    mess_charge_kw: Mapping[str, float]
    mess_discharge_kw: Mapping[str, float]
    mess_q_kvar: Mapping[str, float]
    job_compute_rate_fraction: Mapping[str, float]
    site_throughput_fraction: Mapping[str, float]


@dataclass(frozen=True)
class FastLayerLimits:
    step_minutes: int
    mess_energy_capacity_kwh: Mapping[str, float]
    mess_charge_limit_kw: Mapping[str, float]
    mess_discharge_limit_kw: Mapping[str, float]
    mess_pcs_kva: Mapping[str, float]
    mess_soc_min: Mapping[str, float]
    mess_soc_max: Mapping[str, float]
    job_gpu_count: Mapping[str, int]
    site_throughput_limit: Mapping[str, float]
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95

    def validate(self) -> None:
        if self.step_minutes != 5:
            raise SlowFastContractError("fast limits must use a five-minute step")
        mess_ids = set(self.mess_energy_capacity_kwh)
        required = (
            self.mess_charge_limit_kw,
            self.mess_discharge_limit_kw,
            self.mess_pcs_kva,
            self.mess_soc_min,
            self.mess_soc_max,
        )
        if not mess_ids or any(set(item) != mess_ids for item in required):
            raise SlowFastContractError("MESS limit maps must share identities")
        _finite_nonnegative(self.mess_energy_capacity_kwh, "energy capacity")
        _finite_nonnegative(self.mess_charge_limit_kw, "charge limits")
        _finite_nonnegative(self.mess_discharge_limit_kw, "discharge limits")
        _finite_nonnegative(self.mess_pcs_kva, "PCS limits")
        if any(float(self.mess_energy_capacity_kwh[key]) <= 0.0 for key in mess_ids):
            raise SlowFastContractError("energy capacity must be positive")
        if any(not 0.0 <= float(self.mess_soc_min[key]) <= float(self.mess_soc_max[key]) <= 1.0 for key in mess_ids):
            raise SlowFastContractError("SOC bounds are invalid")
        if any(int(gpu) <= 0 for gpu in self.job_gpu_count.values()):
            raise SlowFastContractError("job GPU counts must be positive")
        if not 0.0 < self.charge_efficiency <= 1.0 or not 0.0 < self.discharge_efficiency <= 1.0:
            raise SlowFastContractError("efficiencies must lie in (0,1]")


@dataclass(frozen=True)
class GridScreenResult:
    passed: bool
    status: str
    minimum_voltage_pu: float
    maximum_voltage_pu: float
    maximum_thermal_loading_fraction: float


@dataclass(frozen=True)
class FastRecourseResult:
    accepted_by_screen: bool
    status: str
    control: FastControl
    next_state: FastLayerState
    slow_plan_fingerprint_before: str
    slow_plan_fingerprint_after: str
    binary_state_unchanged: bool
    grid_screen: GridScreenResult
    runtime_seconds: float


GridScreen = Callable[[FastControl, FastLayerState], GridScreenResult]


def _clip(value: float, lower: float, upper: float) -> float:
    if not math.isfinite(float(value)):
        raise SlowFastContractError("fast set-points must be finite")
    return min(max(float(value), float(lower)), float(upper))


def execute_fast_recourse(
    *,
    architecture: SlowFastArchitecture,
    slow_plan: SlowDiscretePlan,
    state: FastLayerState,
    nominal: FastControl,
    limits: FastLayerLimits,
    grid_screen: GridScreen,
) -> FastRecourseResult:
    """Project one continuous h0 action without changing any slow decision."""

    started = time.monotonic()
    architecture.validate()
    slow_plan.validate()
    state.validate()
    limits.validate()
    fingerprint = slow_plan.fingerprint
    if state.issue < slow_plan.valid_from_issue:
        raise SlowFastContractError("fast state precedes the active slow plan")
    mess_ids = set(state.mess_soc)
    if mess_ids != set(limits.mess_energy_capacity_kwh):
        raise SlowFastContractError("state and MESS limits have different identities")
    jobs = set(state.remaining_work_gpu_hours)
    if jobs != set(limits.job_gpu_count) or not jobs.issubset(slow_plan.job_idc_placement):
        raise SlowFastContractError("fast jobs do not match the fixed slow placement")

    charge: dict[str, float] = {}
    discharge: dict[str, float] = {}
    reactive: dict[str, float] = {}
    next_soc: dict[str, float] = {}
    dt_hours = limits.step_minutes / 60.0
    for mess_id in sorted(mess_ids):
        ch = _clip(nominal.mess_charge_kw.get(mess_id, 0.0), 0.0, limits.mess_charge_limit_kw[mess_id])
        dis = _clip(nominal.mess_discharge_kw.get(mess_id, 0.0), 0.0, limits.mess_discharge_limit_kw[mess_id])
        net = dis - ch
        ch, dis = (0.0, net) if net >= 0.0 else (-net, 0.0)
        soc = float(state.mess_soc[mess_id])
        capacity = float(limits.mess_energy_capacity_kwh[mess_id])
        max_ch_by_soc = max(0.0, (float(limits.mess_soc_max[mess_id]) - soc) * capacity / (limits.charge_efficiency * dt_hours))
        max_dis_by_soc = max(0.0, (soc - float(limits.mess_soc_min[mess_id])) * capacity * limits.discharge_efficiency / dt_hours)
        ch = min(ch, max_ch_by_soc)
        dis = min(dis, max_dis_by_soc)
        p = dis - ch
        q_limit = math.sqrt(max(0.0, float(limits.mess_pcs_kva[mess_id]) ** 2 - p**2))
        q = _clip(nominal.mess_q_kvar.get(mess_id, 0.0), -q_limit, q_limit)
        charge[mess_id], discharge[mess_id], reactive[mess_id] = ch, dis, q
        next_soc[mess_id] = soc + (limits.charge_efficiency * ch - dis / limits.discharge_efficiency) * dt_hours / capacity

    compute: dict[str, float] = {}
    remaining: dict[str, float] = {}
    for job_id in sorted(jobs):
        fraction = _clip(nominal.job_compute_rate_fraction.get(job_id, 0.0), 0.0, 1.0)
        executed = int(limits.job_gpu_count[job_id]) * fraction * dt_hours
        compute[job_id] = fraction
        remaining[job_id] = max(0.0, float(state.remaining_work_gpu_hours[job_id]) - executed)
    throughput = {
        site: _clip(nominal.site_throughput_fraction.get(site, 0.0), 0.0, limit)
        for site, limit in limits.site_throughput_limit.items()
    }
    projected = FastControl(charge, discharge, reactive, compute, throughput)
    candidate_state = FastLayerState(state.issue + 1, next_soc, remaining)
    screen = grid_screen(projected, candidate_state)
    if screen.passed and not (
        0.95 <= screen.minimum_voltage_pu <= screen.maximum_voltage_pu <= 1.05
        and screen.maximum_thermal_loading_fraction <= 1.0
    ):
        raise SlowFastContractError("grid screen claimed PASS outside hard limits")
    fingerprint_after = slow_plan.fingerprint
    unchanged = fingerprint == fingerprint_after
    if not unchanged:
        raise SlowFastContractError("fast layer mutated a slow binary decision")
    return FastRecourseResult(
        accepted_by_screen=screen.passed,
        status="FAST_RECOURSE_SCREENED" if screen.passed else "FAIL_CLOSED_GRID_SCREEN",
        control=projected,
        next_state=candidate_state,
        slow_plan_fingerprint_before=fingerprint,
        slow_plan_fingerprint_after=fingerprint_after,
        binary_state_unchanged=unchanged,
        grid_screen=screen,
        runtime_seconds=time.monotonic() - started,
    )
