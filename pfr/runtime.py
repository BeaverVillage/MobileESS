"""PFR9+ causal B0-B7 runtime with Fresh Exact AC commit authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import csv
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence, Tuple

from .methods import ComparisonMethod, K9H7ResultIdentityV2, MethodConfig
from .optimization import (
    FastControlOptimizer,
    FastOptimizationContext,
    IdentityFastControlOptimizer,
)
from .power import H100UtilizationPowerCurve
from .risk import PlanValidityRiskMonitor, ReplanCost, RiskConstraint, RiskFamily
from .safety import (
    AcSafetyFilter,
    EscalatedCandidate,
    ExactAcResult,
    ProjectionCandidate,
    ProjectionCertificate,
)
from .slow_fast import (
    FastControl,
    FastLayerLimits,
    FastLayerState,
    GridScreenResult,
    SlowDiscretePlan,
    SlowFastArchitecture,
    execute_fast_recourse,
)


IDCS = tuple(f"IDC{i:02d}" for i in range(1, 13))
MESS_IDS = tuple(f"MESS{i:02d}" for i in range(1, 5))
STEP_HOURS = 5.0 / 60.0
MESS_CAPACITY_KWH = 1080.0
MESS_FLOOR_KWH = 440.0
MESS_SAFETY_RESERVE_KWH = 440.0
MESS_CANONICAL_DAILY_PRE_KWH = 760.0
MESS_CHARGE_LIMIT_KW = 550.0
MESS_NOMINAL_DISCHARGE_KW = 20.0
MESS_CHARGE_EFFICIENCY = 0.95
MAXIMUM_REFRESH_STEPS = 6
PRICE_DEADBAND_FRACTION = 0.05
MODELED_GPU_CAPACITY_PER_IDC = 256


class RuntimeContractError(RuntimeError):
    pass


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OperationalTrainingJob:
    job_uid: str
    origin_idc: str
    arrival_step: int
    latest_start_step: int
    deadline_step: int
    requested_gpu: int
    runtime_seconds_source: float
    cpu_request_share_kw: float
    input_bytes: Optional[int]
    source_record_id: str

    def validate(self) -> None:
        if not self.job_uid or self.origin_idc not in IDCS or not self.source_record_id:
            raise RuntimeContractError("operational job identity is invalid")
        if not (0 <= self.arrival_step <= self.latest_start_step < self.deadline_step):
            raise RuntimeContractError("operational job timing is invalid")
        if self.requested_gpu <= 0 or self.runtime_seconds_source <= 0.0:
            raise RuntimeContractError("job GPU gang and runtime must be positive")
        if self.cpu_request_share_kw < 0.0 or not math.isfinite(self.cpu_request_share_kw):
            raise RuntimeContractError("CPU request-share power must be finite and non-negative")
        if self.input_bytes is not None and self.input_bytes < 0:
            raise RuntimeContractError("input bytes cannot be negative")

    @property
    def total_work_gpu_hours(self) -> float:
        self.validate()
        return self.requested_gpu * self.runtime_seconds_source / 3600.0


@dataclass(frozen=True)
class MobilityRouteForecast:
    source_service_id: str
    destination_service_id: str
    od_index: int
    rank: int
    q50_eta_seconds: float
    safe_eta_seconds: float
    q50_energy_kwh: float
    safe_energy_kwh: float
    profile_template_id: int
    profile_horizon_steps: int

    def validate(self) -> None:
        if self.source_service_id == self.destination_service_id:
            raise RuntimeContractError("mobility route must connect distinct services")
        if self.rank not in {1, 2, 3} or self.od_index < 0:
            raise RuntimeContractError("mobility route is outside frozen K=3")
        values = (
            self.q50_eta_seconds,
            self.safe_eta_seconds,
            self.q50_energy_kwh,
            self.safe_energy_kwh,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise RuntimeContractError("mobility forecast must be finite and non-negative")
        if self.profile_template_id < 0 or self.profile_horizon_steps <= 0:
            raise RuntimeContractError("mobility E4 profile authority is invalid")


@dataclass(frozen=True)
class CausalExperimentFrame:
    issue: int
    current_price_aud_per_mwh: float
    horizon_price_median_aud_per_mwh: float
    q50_background_p_kw: float
    q50_background_q_kvar: float
    arrivals: Tuple[OperationalTrainingJob, ...]
    exogenous_sha256: str
    future_actual_used: bool = False
    grid_upper_background_p_kw: float = 0.0
    grid_upper_background_q_kvar: float = 0.0
    robust_background_p_kw: Tuple[Tuple[float, ...], ...] = ()
    robust_background_q_kvar: Tuple[Tuple[float, ...], ...] = ()
    robust_pv_available_kw: Tuple[Tuple[float, ...], ...] = ()
    workload_reserve_gpu: Mapping[str, float] = field(default_factory=dict)
    mobility_routes: Tuple[MobilityRouteForecast, ...] = ()
    mobility_template_bank: Mapping[int, Tuple[float, ...]] = field(default_factory=dict)

    def validate(self) -> None:
        values = (
            self.current_price_aud_per_mwh,
            self.horizon_price_median_aud_per_mwh,
            self.q50_background_p_kw,
            self.q50_background_q_kvar,
        )
        if self.issue < 0 or any(not math.isfinite(value) for value in values):
            raise RuntimeContractError("causal frame contains invalid numeric data")
        if self.future_actual_used:
            raise RuntimeContractError("future actual is prohibited")
        if len(self.exogenous_sha256) != 64:
            raise RuntimeContractError("causal exogenous identity must be SHA-256")
        for job in self.arrivals:
            job.validate()
            if job.arrival_step != self.issue:
                raise RuntimeContractError("arrival is attached to the wrong issue")
        if self.workload_reserve_gpu and set(self.workload_reserve_gpu) != set(IDCS):
            raise RuntimeContractError("workload reserve must cover all 12 IDCs")
        if any(value < 0.0 or not math.isfinite(value) for value in self.workload_reserve_gpu.values()):
            raise RuntimeContractError("workload reserve must be finite and non-negative")
        robust = (
            self.robust_background_p_kw,
            self.robust_background_q_kvar,
            self.robust_pv_available_kw,
        )
        if any(robust) and any(len(array) != 131 or any(len(row) != 3 for row in array) for array in robust):
            raise RuntimeContractError("robust grid arrays must be 131x3")
        for route in self.mobility_routes:
            route.validate()

    def routes_for(self, source: str, destination: str) -> Tuple[MobilityRouteForecast, ...]:
        return tuple(
            route
            for route in self.mobility_routes
            if route.source_service_id == source and route.destination_service_id == destination
        )


@dataclass(frozen=True)
class RuntimeInitialState:
    issue: int
    state_sha256: str
    mess_energy_kwh: Mapping[str, float]
    mess_location: Mapping[str, str]

    def validate(self) -> None:
        if self.issue < 0 or len(self.state_sha256) != 64:
            raise RuntimeContractError("initial state identity is invalid")
        if set(self.mess_energy_kwh) != set(MESS_IDS) or set(self.mess_location) != set(MESS_IDS):
            raise RuntimeContractError("initial MESS state is incomplete")
        if any(not MESS_FLOOR_KWH <= value <= MESS_CAPACITY_KWH for value in self.mess_energy_kwh.values()):
            raise RuntimeContractError("initial MESS energy violates hard bounds")


@dataclass
class RuntimeJobState:
    source: OperationalTrainingJob
    destination_idc: str
    logical_rack_id: str
    gang_membership: Tuple[str, ...]
    remaining_work_gpu_hours: float
    lifecycle: str = "QUEUED"
    compute_rate_fraction: float = 0.0
    start_issue: Optional[int] = None
    completion_issue: Optional[int] = None
    checkpoint_state: str = "UNAVAILABLE_NOT_MEASURED"
    migration_state: str = "BLOCKED_MISSING_PAYLOAD_AUTHORITY"


@dataclass
class MutableMethodState:
    issue: int
    pre_state_sha256: str
    mess_energy_kwh: dict[str, float]
    mess_location: dict[str, str]
    jobs: dict[str, RuntimeJobState] = field(default_factory=dict)
    active_plan: Optional[SlowDiscretePlan] = None
    active_plan_age_steps: int = 10**9
    full_replan_count: int = 0
    communication_bytes: int = 0
    wan_transferred_bytes_cumulative: int = 0
    wan_active_transfers: int = 0
    compute_debt_gpu_hours: float = 0.0
    energy_debt_kwh: float = 0.0
    last_exact: Optional[Mapping[str, Any]] = None
    mess_in_transit: dict[str, bool] = field(
        default_factory=lambda: {mid: False for mid in MESS_IDS}
    )
    mess_route_destination: dict[str, Optional[str]] = field(
        default_factory=lambda: {mid: None for mid in MESS_IDS}
    )
    mess_route_rank: dict[str, int] = field(
        default_factory=lambda: {mid: 1 for mid in MESS_IDS}
    )
    mess_route_energy_profile_kwh: dict[str, Tuple[float, ...]] = field(
        default_factory=lambda: {mid: () for mid in MESS_IDS}
    )
    mess_route_profile_index: dict[str, int] = field(
        default_factory=lambda: {mid: 0 for mid in MESS_IDS}
    )
    last_slow_miqp_certificate: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhysicalCommit:
    exact: ExactAcResult
    raw_metrics: Mapping[str, Any]
    actual_gurobi_used: bool
    actual_fresh_opendss_used: bool


class FreshPhysicalBackend(Protocol):
    def verify_fresh(
        self,
        *,
        issue: int,
        facility_p_kw: Sequence[float],
        facility_q_kvar: Sequence[float],
        mess_location: Sequence[str],
        mess_p_kw: Sequence[float],
        mess_q_kvar: Sequence[float],
        mess_in_transit: Sequence[bool],
        robust_background_p_kw: Sequence[Sequence[float]],
        robust_background_q_kvar: Sequence[Sequence[float]],
        robust_pv_available_kw: Sequence[Sequence[float]],
    ) -> PhysicalCommit:
        ...


class _IdentityProjector:
    def project(self, *, nominal: FastControl, state: FastLayerState, slow_plan: SlowDiscretePlan) -> ProjectionCandidate:
        return ProjectionCandidate(
            control=nominal,
            certificate=ProjectionCertificate(
                "CONVEX_CONTINUOUS_SOCP", True, True, True, True, True, True, True, True
            ),
            slow_plan_fingerprint=slow_plan.fingerprint,
            objective_nominal=0.0,
            objective_projected=0.0,
            runtime_seconds=0.0,
        )


class _PhysicalVerifierAdapter:
    def __init__(
        self,
        backend: FreshPhysicalBackend,
        issue: int,
        jobs: Mapping[str, RuntimeJobState],
        power_curve: H100UtilizationPowerCurve,
        mess_location: Sequence[str],
        mess_in_transit: Sequence[bool],
        robust_background_p_kw: Sequence[Sequence[float]],
        robust_background_q_kvar: Sequence[Sequence[float]],
        robust_pv_available_kw: Sequence[Sequence[float]],
    ) -> None:
        self.backend = backend
        self.issue = issue
        self.jobs = jobs
        self.power_curve = power_curve
        self.mess_location = tuple(mess_location)
        self.mess_in_transit = tuple(bool(value) for value in mess_in_transit)
        self.robust_background_p_kw = tuple(tuple(row) for row in robust_background_p_kw)
        self.robust_background_q_kvar = tuple(tuple(row) for row in robust_background_q_kvar)
        self.robust_pv_available_kw = tuple(tuple(row) for row in robust_pv_available_kw)
        self.last_commit: Optional[PhysicalCommit] = None

    def verify_fresh(self, *, control: FastControl, **_: Any) -> ExactAcResult:
        facility_p = {site: 0.0 for site in IDCS}
        for job_id, fraction in control.job_compute_rate_fraction.items():
            job = self.jobs[job_id]
            if job.lifecycle == "COMPLETED" or fraction <= 0.0:
                continue
            facility_p[job.destination_idc] += (
                self.power_curve.gang_power_kw(job.source.requested_gpu, fraction)
                + job.source.cpu_request_share_kw
            )
        if any(value > 750.0 + 1e-9 for value in facility_p.values()):
            raise RuntimeContractError("projected AI load exceeds unchanged 750-kVA transformer rating")
        mess_p = tuple(
            control.mess_discharge_kw.get(mid, 0.0) - control.mess_charge_kw.get(mid, 0.0)
            for mid in MESS_IDS
        )
        mess_q = tuple(control.mess_q_kvar.get(mid, 0.0) for mid in MESS_IDS)
        self.last_commit = self.backend.verify_fresh(
            issue=self.issue,
            facility_p_kw=tuple(facility_p[site] for site in IDCS),
            facility_q_kvar=(0.0,) * len(IDCS),
            mess_location=self.mess_location,
            mess_p_kw=mess_p,
            mess_q_kvar=mess_q,
            mess_in_transit=self.mess_in_transit,
            robust_background_p_kw=self.robust_background_p_kw,
            robust_background_q_kvar=self.robust_background_q_kvar,
            robust_pv_available_kw=self.robust_pv_available_kw,
        )
        if not self.last_commit.actual_fresh_opendss_used:
            raise RuntimeContractError("physical backend did not execute Fresh OpenDSS")
        return self.last_commit.exact


def _blend_control(left: FastControl, right: FastControl, weight: float) -> FastControl:
    weight = min(max(float(weight), 0.0), 1.0)
    blend = lambda a, b: float(a) + weight * (float(b) - float(a))
    return FastControl(
        mess_charge_kw={key: blend(left.mess_charge_kw[key], right.mess_charge_kw[key]) for key in left.mess_charge_kw},
        mess_discharge_kw={key: blend(left.mess_discharge_kw[key], right.mess_discharge_kw[key]) for key in left.mess_discharge_kw},
        mess_q_kvar={key: blend(left.mess_q_kvar[key], right.mess_q_kvar[key]) for key in left.mess_q_kvar},
        job_compute_rate_fraction={
            key: blend(left.job_compute_rate_fraction[key], right.job_compute_rate_fraction[key])
            for key in left.job_compute_rate_fraction
        },
        site_throughput_fraction=dict(left.site_throughput_fraction),
    )


class _GurobiSensitivityProjector:
    """Minimal continuous projection over a Fresh-AC finite-difference envelope."""

    def __init__(self, verifier: _PhysicalVerifierAdapter, *, allow_mess: bool) -> None:
        self.verifier = verifier
        self.allow_mess = allow_mess
        self.trace: list[Mapping[str, Any]] = []

    @staticmethod
    def _objective_distance(nominal: FastControl, candidate: FastControl) -> float:
        maps = (
            (nominal.mess_charge_kw, candidate.mess_charge_kw),
            (nominal.mess_discharge_kw, candidate.mess_discharge_kw),
            (nominal.mess_q_kvar, candidate.mess_q_kvar),
            (nominal.job_compute_rate_fraction, candidate.job_compute_rate_fraction),
        )
        return sum((float(right[key]) - float(left[key])) ** 2 for left, right in maps for key in left)

    @staticmethod
    def _violation_score(exact: ExactAcResult) -> float:
        violations = (
            max(0.0, 0.95 - exact.minimum_voltage_pu),
            max(0.0, exact.maximum_voltage_pu - 1.05),
            max(0.0, exact.maximum_line_loading_fraction - 1.0),
            max(0.0, exact.maximum_transformer_loading_fraction - 1.0),
        )
        root_sign_penalty = 10.0 if "ROOT_SIGN" in exact.status else 0.0
        return root_sign_penalty + sum(value * value for value in violations)

    def _targets(
        self, control: FastControl, state: FastLayerState, exact: ExactAcResult
    ) -> tuple[FastControl, FastControl]:
        active_compute = {
            key: 0.0 for key in control.job_compute_rate_fraction
        }
        active_charge, active_discharge, active_q = {}, {}, {}
        voltage_charge = dict(control.mess_charge_kw)
        voltage_discharge = dict(control.mess_discharge_kw)
        voltage_q = {}
        for mess_id in control.mess_charge_kw:
            mess_index = MESS_IDS.index(mess_id)
            if self.verifier.mess_in_transit[mess_index]:
                active_charge[mess_id] = 0.0
                active_discharge[mess_id] = 0.0
                active_q[mess_id] = 0.0
                voltage_charge[mess_id] = 0.0
                voltage_discharge[mess_id] = 0.0
                voltage_q[mess_id] = 0.0
                continue
            energy = state.mess_soc[mess_id] * MESS_CAPACITY_KWH
            max_charge = max(0.0, (MESS_CAPACITY_KWH - energy) / (0.95 * STEP_HOURS))
            max_discharge = max(0.0, (energy - MESS_FLOOR_KWH) * 0.95 / STEP_HOURS)
            if self.allow_mess:
                active_charge[mess_id], active_discharge[mess_id] = 0.0, min(550.0, max_discharge)
            else:
                active_charge[mess_id] = control.mess_charge_kw[mess_id]
                active_discharge[mess_id] = control.mess_discharge_kw[mess_id]
            active_q[mess_id] = control.mess_q_kvar[mess_id]
            thermal_relief = (
                exact.maximum_line_loading_fraction > 1.0
                or exact.maximum_transformer_loading_fraction > 1.0
            )
            if self.allow_mess:
                if thermal_relief:
                    voltage_charge[mess_id] = control.mess_charge_kw[mess_id]
                    voltage_discharge[mess_id] = control.mess_discharge_kw[mess_id]
                elif exact.maximum_voltage_pu > 1.05:
                    voltage_charge[mess_id] = control.mess_charge_kw[mess_id]
                    voltage_discharge[mess_id] = control.mess_discharge_kw[mess_id]
                elif exact.minimum_voltage_pu < 0.95:
                    voltage_charge[mess_id] = 0.0
                    voltage_discharge[mess_id] = min(550.0, max_discharge)
            p = float(voltage_discharge[mess_id]) - float(voltage_charge[mess_id])
            q_cap = math.sqrt(max(0.0, 700.0**2 - p**2))
            if self.allow_mess and thermal_relief:
                voltage_q[mess_id] = q_cap
            elif self.allow_mess and exact.maximum_voltage_pu > 1.05:
                voltage_q[mess_id] = -q_cap
            elif self.allow_mess and exact.minimum_voltage_pu < 0.95:
                voltage_q[mess_id] = q_cap
            else:
                voltage_q[mess_id] = control.mess_q_kvar[mess_id]
        active = FastControl(
            active_charge, active_discharge, active_q, active_compute,
            dict(control.site_throughput_fraction),
        )
        voltage = FastControl(
            voltage_charge, voltage_discharge, voltage_q,
            dict(control.job_compute_rate_fraction), dict(control.site_throughput_fraction),
        )
        return active, voltage

    @staticmethod
    def _combine(base: FastControl, active: FastControl, voltage: FastControl, z_active: float, z_voltage: float) -> FastControl:
        combine = lambda value, a, v: float(value) + z_active * (float(a) - float(value)) + z_voltage * (float(v) - float(value))
        raw_charge = {key: combine(base.mess_charge_kw[key], active.mess_charge_kw[key], voltage.mess_charge_kw[key]) for key in base.mess_charge_kw}
        raw_discharge = {key: combine(base.mess_discharge_kw[key], active.mess_discharge_kw[key], voltage.mess_discharge_kw[key]) for key in base.mess_discharge_kw}
        raw_q = {key: combine(base.mess_q_kvar[key], active.mess_q_kvar[key], voltage.mess_q_kvar[key]) for key in base.mess_q_kvar}
        charge, discharge, reactive = {}, {}, {}
        for key in base.mess_charge_kw:
            net_p = min(550.0, max(-550.0, raw_discharge[key] - raw_charge[key]))
            charge[key] = max(0.0, -net_p)
            discharge[key] = max(0.0, net_p)
            q_cap = math.sqrt(max(0.0, 700.0**2 - net_p**2))
            reactive[key] = min(q_cap, max(-q_cap, raw_q[key]))
        return FastControl(
            mess_charge_kw=charge,
            mess_discharge_kw=discharge,
            mess_q_kvar=reactive,
            job_compute_rate_fraction={key: combine(base.job_compute_rate_fraction[key], active.job_compute_rate_fraction[key], voltage.job_compute_rate_fraction[key]) for key in base.job_compute_rate_fraction},
            site_throughput_fraction=dict(base.site_throughput_fraction),
        )

    def _coordinate_q_step(
        self,
        control: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
        exact: ExactAcResult,
    ) -> Optional[tuple[FastControl, ExactAcResult, Mapping[str, Any]]]:
        if not self.allow_mess:
            return None
        base_score = self._violation_score(exact)
        probes = []
        for mess_index, mess_id in enumerate(MESS_IDS):
            if self.verifier.mess_in_transit[mess_index]:
                continue
            p = float(control.mess_discharge_kw[mess_id]) - float(control.mess_charge_kw[mess_id])
            q_cap = math.sqrt(max(0.0, 700.0**2 - p**2))
            for direction in (-1.0, 1.0):
                target = direction * q_cap
                q = dict(control.mess_q_kvar)
                q[mess_id] = float(q[mess_id]) + 0.25 * (target - float(q[mess_id]))
                candidate = FastControl(
                    dict(control.mess_charge_kw),
                    dict(control.mess_discharge_kw),
                    q,
                    dict(control.job_compute_rate_fraction),
                    dict(control.site_throughput_fraction),
                )
                candidate_exact = self.verifier.verify_fresh(
                    control=candidate, state=state, slow_plan=slow_plan
                )
                candidate_exact.validate()
                probes.append((candidate, candidate_exact, mess_id, direction, 0.25))
        passing = [item for item in probes if item[1].passed]
        if passing:
            candidate, candidate_exact, mess_id, direction, fraction = min(
                passing, key=lambda item: self._objective_distance(control, item[0])
            )
            return candidate, candidate_exact, {
                "status": "FRESH_OPENDSS_PASSING_COORDINATE_Q_PROBE",
                "mess_id": mess_id,
                "direction": direction,
                "fraction": fraction,
            }
        improving = [
            item for item in probes
            if self._violation_score(item[1]) < base_score - 1e-12
        ]
        if not improving:
            return None
        seed = min(improving, key=lambda item: self._violation_score(item[1]))
        expanded = []
        _, _, mess_id, direction, _ = seed
        p = float(control.mess_discharge_kw[mess_id]) - float(control.mess_charge_kw[mess_id])
        target = direction * math.sqrt(max(0.0, 700.0**2 - p**2))
        for fraction in tuple(index / 40.0 for index in range(1, 11)) + (0.5, 0.75, 1.0):
            q = dict(control.mess_q_kvar)
            q[mess_id] = float(q[mess_id]) + fraction * (target - float(q[mess_id]))
            candidate = FastControl(
                dict(control.mess_charge_kw),
                dict(control.mess_discharge_kw),
                q,
                dict(control.job_compute_rate_fraction),
                dict(control.site_throughput_fraction),
            )
            candidate_exact = self.verifier.verify_fresh(
                control=candidate, state=state, slow_plan=slow_plan
            )
            candidate_exact.validate()
            expanded.append((candidate, candidate_exact, mess_id, direction, fraction))
        def preserves_satisfied_constraints(candidate_exact: ExactAcResult) -> bool:
            return (
                (exact.minimum_voltage_pu < 0.95 or candidate_exact.minimum_voltage_pu >= 0.95)
                and (exact.maximum_voltage_pu > 1.05 or candidate_exact.maximum_voltage_pu <= 1.05)
                and (exact.maximum_line_loading_fraction > 1.0 or candidate_exact.maximum_line_loading_fraction <= 1.0)
                and (exact.maximum_transformer_loading_fraction > 1.0 or candidate_exact.maximum_transformer_loading_fraction <= 1.0)
                and ("ROOT_SIGN" in exact.status or "ROOT_SIGN" not in candidate_exact.status)
            )
        admissible = [
            item for item in expanded
            if item[1].passed
            or (
                preserves_satisfied_constraints(item[1])
                and self._violation_score(item[1]) < base_score - 1e-12
            )
        ]
        if not admissible:
            return None
        passing = [item for item in admissible if item[1].passed]
        selected = min(
            passing if passing else admissible,
            key=(
                (lambda item: self._objective_distance(control, item[0]))
                if passing
                else (lambda item: self._violation_score(item[1]))
            ),
        )
        if not selected[1].passed and self._violation_score(selected[1]) >= base_score - 1e-12:
            return None
        candidate, candidate_exact, mess_id, direction, fraction = selected
        return candidate, candidate_exact, {
            "status": "FRESH_OPENDSS_COORDINATE_Q_SEARCH",
            "mess_id": mess_id,
            "direction": direction,
            "fraction": fraction,
            "passed": candidate_exact.passed,
        }

    def _sensitivity_qp_step(
        self,
        control: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
        exact: ExactAcResult,
    ) -> Optional[tuple[FastControl, ExactAcResult, Mapping[str, Any]]]:
        if not self.allow_mess:
            return None
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as exc:
            raise RuntimeContractError("gurobipy is required by the AC sensitivity QP") from exc

        metric_names = ("vmin", "vmax", "line", "transformer")
        base_metrics = {
            "vmin": exact.minimum_voltage_pu,
            "vmax": exact.maximum_voltage_pu,
            "line": exact.maximum_line_loading_fraction,
            "transformer": exact.maximum_transformer_loading_fraction,
        }
        q_bounds = {}
        derivatives = {name: {} for name in metric_names}
        for mess_index, mess_id in enumerate(MESS_IDS):
            if self.verifier.mess_in_transit[mess_index]:
                continue
            p = (
                float(control.mess_discharge_kw[mess_id])
                - float(control.mess_charge_kw[mess_id])
            )
            q_cap = math.sqrt(max(0.0, 700.0**2 - p**2))
            current_q = float(control.mess_q_kvar[mess_id])
            lower_delta = -q_cap - current_q
            upper_delta = q_cap - current_q
            q_bounds[mess_id] = (lower_delta, upper_delta, q_cap)
            negative_delta = max(lower_delta, -70.0)
            positive_delta = min(upper_delta, 70.0)
            if positive_delta - negative_delta <= 1e-6:
                continue
            probe_metrics = []
            for delta in (negative_delta, positive_delta):
                q = dict(control.mess_q_kvar)
                q[mess_id] = current_q + delta
                candidate = FastControl(
                    dict(control.mess_charge_kw),
                    dict(control.mess_discharge_kw),
                    q,
                    dict(control.job_compute_rate_fraction),
                    dict(control.site_throughput_fraction),
                )
                candidate_exact = self.verifier.verify_fresh(
                    control=candidate, state=state, slow_plan=slow_plan
                )
                candidate_exact.validate()
                probe_metrics.append(
                    {
                        "vmin": candidate_exact.minimum_voltage_pu,
                        "vmax": candidate_exact.maximum_voltage_pu,
                        "line": candidate_exact.maximum_line_loading_fraction,
                        "transformer": candidate_exact.maximum_transformer_loading_fraction,
                    }
                )
            denominator = positive_delta - negative_delta
            for name in metric_names:
                derivatives[name][mess_id] = (
                    probe_metrics[1][name] - probe_metrics[0][name]
                ) / denominator
        if not q_bounds:
            return None

        model = gp.Model("pfr_exact_ac_q_sensitivity")
        model.Params.OutputFlag = 0
        model.Params.Threads = 1
        model.Params.Seed = 0
        delta_q = {
            mess_id: model.addVar(lb=bounds[0], ub=bounds[1], name=f"delta_q[{mess_id}]")
            for mess_id, bounds in q_bounds.items()
        }
        expressions = {
            name: base_metrics[name]
            + gp.quicksum(
                derivatives[name].get(mess_id, 0.0) * variable
                for mess_id, variable in delta_q.items()
            )
            for name in metric_names
        }
        model.addConstr(expressions["vmin"] >= 0.9505, name="minimum_voltage")
        model.addConstr(expressions["vmax"] <= 1.0495, name="maximum_voltage")
        model.addConstr(expressions["line"] <= 1.0, name="line_loading")
        model.addConstr(expressions["transformer"] <= 1.0, name="transformer_loading")
        model.setObjective(
            gp.quicksum(
                (variable / max(q_bounds[mess_id][2], 1.0))
                * (variable / max(q_bounds[mess_id][2], 1.0))
                for mess_id, variable in delta_q.items()
            ),
            GRB.MINIMIZE,
        )
        model.optimize()
        if model.Status not in {GRB.OPTIMAL, GRB.SUBOPTIMAL} or model.SolCount < 1 or float(model.MaxVio) > 1e-6:
            status = int(model.Status)
            model.dispose()
            return None
        solution = {mess_id: float(variable.X) for mess_id, variable in delta_q.items()}
        model.dispose()

        base_score = self._violation_score(exact)
        candidates = []
        for scale in (0.25, 0.5, 0.75, 1.0, 1.05):
            q = dict(control.mess_q_kvar)
            for mess_id, delta in solution.items():
                lower, upper, _ = q_bounds[mess_id]
                scaled_delta = min(upper, max(lower, scale * delta))
                q[mess_id] = float(q[mess_id]) + scaled_delta
            candidate = FastControl(
                dict(control.mess_charge_kw),
                dict(control.mess_discharge_kw),
                q,
                dict(control.job_compute_rate_fraction),
                dict(control.site_throughput_fraction),
            )
            candidate_exact = self.verifier.verify_fresh(
                control=candidate, state=state, slow_plan=slow_plan
            )
            candidate_exact.validate()
            candidates.append((candidate, candidate_exact, scale))

        def preserves_satisfied_constraints(candidate_exact: ExactAcResult) -> bool:
            return (
                (exact.minimum_voltage_pu < 0.95 or candidate_exact.minimum_voltage_pu >= 0.95)
                and (exact.maximum_voltage_pu > 1.05 or candidate_exact.maximum_voltage_pu <= 1.05)
                and (exact.maximum_line_loading_fraction > 1.0 or candidate_exact.maximum_line_loading_fraction <= 1.0)
                and (exact.maximum_transformer_loading_fraction > 1.0 or candidate_exact.maximum_transformer_loading_fraction <= 1.0)
                and ("ROOT_SIGN" in exact.status or "ROOT_SIGN" not in candidate_exact.status)
            )

        passing = [item for item in candidates if item[1].passed]
        admissible = passing or [
            item
            for item in candidates
            if preserves_satisfied_constraints(item[1])
            and self._violation_score(item[1]) < base_score - 1e-12
        ]
        if not admissible:
            return None
        selected = min(
            admissible,
            key=(
                (lambda item: self._objective_distance(control, item[0]))
                if passing
                else (lambda item: self._violation_score(item[1]))
            ),
        )
        candidate, candidate_exact, scale = selected
        return candidate, candidate_exact, {
            "status": "FRESH_OPENDSS_CONTINUOUS_Q_SENSITIVITY_QP",
            "scale": scale,
            "passed": candidate_exact.passed,
            "continuous_variables": len(solution),
            "integer_variables": 0,
        }

    def _active_sensitivity_qp_step(
        self,
        control: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
        exact: ExactAcResult,
    ) -> Optional[tuple[FastControl, ExactAcResult, Mapping[str, Any]]]:
        if not self.allow_mess:
            return None
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as exc:
            raise RuntimeContractError("gurobipy is required by the AC active-power sensitivity QP") from exc

        metric_names = ("vmin", "vmax", "line", "transformer")
        base_metrics = {
            "vmin": exact.minimum_voltage_pu,
            "vmax": exact.maximum_voltage_pu,
            "line": exact.maximum_line_loading_fraction,
            "transformer": exact.maximum_transformer_loading_fraction,
        }
        p_bounds = {}
        derivatives = {name: {} for name in metric_names}
        for mess_index, mess_id in enumerate(MESS_IDS):
            if self.verifier.mess_in_transit[mess_index]:
                continue
            current_p = (
                float(control.mess_discharge_kw[mess_id])
                - float(control.mess_charge_kw[mess_id])
            )
            current_q = float(control.mess_q_kvar[mess_id])
            energy = float(state.mess_soc[mess_id]) * MESS_CAPACITY_KWH
            max_charge = min(
                550.0,
                max(0.0, (MESS_CAPACITY_KWH - energy) / (MESS_CHARGE_EFFICIENCY * STEP_HOURS)),
            )
            max_discharge = min(
                550.0,
                max(0.0, (energy - MESS_FLOOR_KWH) * MESS_CHARGE_EFFICIENCY / STEP_HOURS),
            )
            apparent_p_cap = math.sqrt(max(0.0, 700.0**2 - current_q**2))
            lower_p = max(-max_charge, -apparent_p_cap)
            upper_p = min(max_discharge, apparent_p_cap)
            lower_delta = lower_p - current_p
            upper_delta = upper_p - current_p
            p_bounds[mess_id] = (lower_delta, upper_delta, current_p)
            negative_delta = max(lower_delta, -50.0)
            positive_delta = min(upper_delta, 50.0)
            if positive_delta - negative_delta <= 1e-6:
                continue
            probe_metrics = []
            for delta in (negative_delta, positive_delta):
                candidate_p = current_p + delta
                candidate = FastControl(
                    {**control.mess_charge_kw, mess_id: max(0.0, -candidate_p)},
                    {**control.mess_discharge_kw, mess_id: max(0.0, candidate_p)},
                    dict(control.mess_q_kvar),
                    dict(control.job_compute_rate_fraction),
                    dict(control.site_throughput_fraction),
                )
                candidate_exact = self.verifier.verify_fresh(
                    control=candidate, state=state, slow_plan=slow_plan
                )
                candidate_exact.validate()
                probe_metrics.append(
                    {
                        "vmin": candidate_exact.minimum_voltage_pu,
                        "vmax": candidate_exact.maximum_voltage_pu,
                        "line": candidate_exact.maximum_line_loading_fraction,
                        "transformer": candidate_exact.maximum_transformer_loading_fraction,
                    }
                )
            denominator = positive_delta - negative_delta
            for name in metric_names:
                derivatives[name][mess_id] = (
                    probe_metrics[1][name] - probe_metrics[0][name]
                ) / denominator
        if not p_bounds:
            return None

        model = gp.Model("pfr_exact_ac_active_sensitivity")
        model.Params.OutputFlag = 0
        model.Params.Threads = 1
        model.Params.Seed = 0
        delta_p = {
            mess_id: model.addVar(lb=bounds[0], ub=bounds[1], name=f"delta_p[{mess_id}]")
            for mess_id, bounds in p_bounds.items()
        }
        expressions = {
            name: base_metrics[name]
            + gp.quicksum(
                derivatives[name].get(mess_id, 0.0) * variable
                for mess_id, variable in delta_p.items()
            )
            for name in metric_names
        }
        model.addConstr(expressions["vmin"] >= 0.9505, name="minimum_voltage")
        model.addConstr(expressions["vmax"] <= 1.0495, name="maximum_voltage")
        model.addConstr(expressions["line"] <= 1.0, name="line_loading")
        model.addConstr(expressions["transformer"] <= 1.0, name="transformer_loading")
        model.setObjective(
            gp.quicksum((variable / 550.0) * (variable / 550.0) for variable in delta_p.values()),
            GRB.MINIMIZE,
        )
        model.optimize()
        if model.Status not in {GRB.OPTIMAL, GRB.SUBOPTIMAL} or model.SolCount < 1 or float(model.MaxVio) > 1e-6:
            model.dispose()
            return None
        solution = {mess_id: float(variable.X) for mess_id, variable in delta_p.items()}
        model.dispose()

        base_score = self._violation_score(exact)
        candidates = []
        for scale in (0.25, 0.5, 0.75, 1.0, 1.05):
            charge = dict(control.mess_charge_kw)
            discharge = dict(control.mess_discharge_kw)
            for mess_id, delta in solution.items():
                lower, upper, current_p = p_bounds[mess_id]
                scaled_delta = min(upper, max(lower, scale * delta))
                candidate_p = current_p + scaled_delta
                charge[mess_id] = max(0.0, -candidate_p)
                discharge[mess_id] = max(0.0, candidate_p)
            candidate = FastControl(
                charge,
                discharge,
                dict(control.mess_q_kvar),
                dict(control.job_compute_rate_fraction),
                dict(control.site_throughput_fraction),
            )
            candidate_exact = self.verifier.verify_fresh(
                control=candidate, state=state, slow_plan=slow_plan
            )
            candidate_exact.validate()
            candidates.append((candidate, candidate_exact, scale))

        def preserves_satisfied_constraints(candidate_exact: ExactAcResult) -> bool:
            return (
                (exact.minimum_voltage_pu < 0.95 or candidate_exact.minimum_voltage_pu >= 0.95)
                and (exact.maximum_voltage_pu > 1.05 or candidate_exact.maximum_voltage_pu <= 1.05)
                and (exact.maximum_line_loading_fraction > 1.0 or candidate_exact.maximum_line_loading_fraction <= 1.0)
                and (exact.maximum_transformer_loading_fraction > 1.0 or candidate_exact.maximum_transformer_loading_fraction <= 1.0)
                and ("ROOT_SIGN" in exact.status or "ROOT_SIGN" not in candidate_exact.status)
            )

        passing = [item for item in candidates if item[1].passed]
        admissible = passing or [
            item
            for item in candidates
            if preserves_satisfied_constraints(item[1])
            and self._violation_score(item[1]) < base_score - 1e-12
        ]
        if not admissible:
            return None
        selected = min(
            admissible,
            key=(
                (lambda item: self._objective_distance(control, item[0]))
                if passing
                else (lambda item: self._violation_score(item[1]))
            ),
        )
        candidate, candidate_exact, scale = selected
        return candidate, candidate_exact, {
            "status": "FRESH_OPENDSS_CONTINUOUS_P_SENSITIVITY_QP",
            "scale": scale,
            "passed": candidate_exact.passed,
            "continuous_variables": len(solution),
            "integer_variables": 0,
        }

    def _pairwise_q_step(
        self,
        control: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
        exact: ExactAcResult,
    ) -> Optional[tuple[FastControl, ExactAcResult, Mapping[str, Any]]]:
        if not self.allow_mess:
            return None
        base_score = self._violation_score(exact)
        connected = [
            mess_id
            for mess_index, mess_id in enumerate(MESS_IDS)
            if not self.verifier.mess_in_transit[mess_index]
        ]
        probes = []
        for left_index, left_id in enumerate(connected):
            for right_id in connected[left_index + 1:]:
                for left_direction in (-1.0, 1.0):
                    for right_direction in (-1.0, 1.0):
                        for fraction in (0.1, 0.25, 0.5, 1.0):
                            q = dict(control.mess_q_kvar)
                            for mess_id, direction in (
                                (left_id, left_direction),
                                (right_id, right_direction),
                            ):
                                p = (
                                    float(control.mess_discharge_kw[mess_id])
                                    - float(control.mess_charge_kw[mess_id])
                                )
                                target = direction * math.sqrt(
                                    max(0.0, 700.0**2 - p**2)
                                )
                                q[mess_id] = float(q[mess_id]) + fraction * (
                                    target - float(q[mess_id])
                                )
                            candidate = FastControl(
                                dict(control.mess_charge_kw),
                                dict(control.mess_discharge_kw),
                                q,
                                dict(control.job_compute_rate_fraction),
                                dict(control.site_throughput_fraction),
                            )
                            candidate_exact = self.verifier.verify_fresh(
                                control=candidate, state=state, slow_plan=slow_plan
                            )
                            candidate_exact.validate()
                            probes.append(
                                (
                                    candidate,
                                    candidate_exact,
                                    left_id,
                                    right_id,
                                    left_direction,
                                    right_direction,
                                    fraction,
                                )
                            )

        def preserves_satisfied_constraints(candidate_exact: ExactAcResult) -> bool:
            return (
                (exact.minimum_voltage_pu < 0.95 or candidate_exact.minimum_voltage_pu >= 0.95)
                and (exact.maximum_voltage_pu > 1.05 or candidate_exact.maximum_voltage_pu <= 1.05)
                and (exact.maximum_line_loading_fraction > 1.0 or candidate_exact.maximum_line_loading_fraction <= 1.0)
                and (exact.maximum_transformer_loading_fraction > 1.0 or candidate_exact.maximum_transformer_loading_fraction <= 1.0)
                and ("ROOT_SIGN" in exact.status or "ROOT_SIGN" not in candidate_exact.status)
            )

        passing = [item for item in probes if item[1].passed]
        admissible = passing or [
            item
            for item in probes
            if preserves_satisfied_constraints(item[1])
            and self._violation_score(item[1]) < base_score - 1e-12
        ]
        if not admissible:
            return None
        selected = min(
            admissible,
            key=(
                (lambda item: self._objective_distance(control, item[0]))
                if passing
                else (lambda item: self._violation_score(item[1]))
            ),
        )
        candidate, candidate_exact, left_id, right_id, left_direction, right_direction, fraction = selected
        return candidate, candidate_exact, {
            "status": "FRESH_OPENDSS_PAIRWISE_Q_SEARCH",
            "mess_ids": [left_id, right_id],
            "directions": [left_direction, right_direction],
            "fraction": fraction,
            "passed": candidate_exact.passed,
        }

    def _fleet_q_step(
        self,
        control: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
        exact: ExactAcResult,
    ) -> Optional[tuple[FastControl, ExactAcResult, Mapping[str, Any]]]:
        if not self.allow_mess:
            return None
        base_score = self._violation_score(exact)
        connected = [
            mess_id
            for mess_index, mess_id in enumerate(MESS_IDS)
            if not self.verifier.mess_in_transit[mess_index]
        ]
        if len(connected) < 3:
            return None
        probes = []
        for direction_mask in range(1 << len(connected)):
            directions = tuple(
                1.0 if direction_mask & (1 << index) else -1.0
                for index in range(len(connected))
            )
            for fraction in (0.1, 0.25, 0.5, 1.0):
                q = dict(control.mess_q_kvar)
                for mess_id, direction in zip(connected, directions):
                    p = (
                        float(control.mess_discharge_kw[mess_id])
                        - float(control.mess_charge_kw[mess_id])
                    )
                    target = direction * math.sqrt(max(0.0, 700.0**2 - p**2))
                    q[mess_id] = float(q[mess_id]) + fraction * (
                        target - float(q[mess_id])
                    )
                candidate = FastControl(
                    dict(control.mess_charge_kw),
                    dict(control.mess_discharge_kw),
                    q,
                    dict(control.job_compute_rate_fraction),
                    dict(control.site_throughput_fraction),
                )
                candidate_exact = self.verifier.verify_fresh(
                    control=candidate, state=state, slow_plan=slow_plan
                )
                candidate_exact.validate()
                probes.append(
                    (candidate, candidate_exact, directions, fraction)
                )

        def preserves_satisfied_constraints(candidate_exact: ExactAcResult) -> bool:
            return (
                (exact.minimum_voltage_pu < 0.95 or candidate_exact.minimum_voltage_pu >= 0.95)
                and (exact.maximum_voltage_pu > 1.05 or candidate_exact.maximum_voltage_pu <= 1.05)
                and (exact.maximum_line_loading_fraction > 1.0 or candidate_exact.maximum_line_loading_fraction <= 1.0)
                and (exact.maximum_transformer_loading_fraction > 1.0 or candidate_exact.maximum_transformer_loading_fraction <= 1.0)
                and ("ROOT_SIGN" in exact.status or "ROOT_SIGN" not in candidate_exact.status)
            )

        passing = [item for item in probes if item[1].passed]
        admissible = passing or [
            item
            for item in probes
            if preserves_satisfied_constraints(item[1])
            and self._violation_score(item[1]) < base_score - 1e-12
        ]
        if not admissible:
            return None
        selected = min(
            admissible,
            key=(
                (lambda item: self._objective_distance(control, item[0]))
                if passing
                else (lambda item: self._violation_score(item[1]))
            ),
        )
        candidate, candidate_exact, directions, fraction = selected
        return candidate, candidate_exact, {
            "status": "FRESH_OPENDSS_FLEET_Q_SEARCH",
            "mess_ids": connected,
            "directions": directions,
            "fraction": fraction,
            "passed": candidate_exact.passed,
        }

    def _active_coordinate_q_step(
        self,
        control: FastControl,
        active_target: FastControl,
        voltage_target: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
    ) -> Optional[tuple[FastControl, ExactAcResult, Mapping[str, Any]]]:
        passing = []
        for active_fraction in (0.25, 0.5, 0.75, 1.0):
            active_candidate = self._combine(
                control, active_target, voltage_target, active_fraction, 0.0
            )
            active_exact = self.verifier.verify_fresh(
                control=active_candidate, state=state, slow_plan=slow_plan
            )
            active_exact.validate()
            if active_exact.passed:
                passing.append((active_candidate, active_exact, active_fraction, None))
                continue
            coordinate = self._coordinate_q_step(
                active_candidate, state, slow_plan, active_exact
            )
            if coordinate is not None and coordinate[1].passed:
                candidate, candidate_exact, coordinate_trace = coordinate
                passing.append(
                    (candidate, candidate_exact, active_fraction, coordinate_trace)
                )
                continue
            sensitivity = self._sensitivity_qp_step(
                active_candidate, state, slow_plan, active_exact
            )
            if sensitivity is not None and sensitivity[1].passed:
                candidate, candidate_exact, sensitivity_trace = sensitivity
                passing.append(
                    (candidate, candidate_exact, active_fraction, sensitivity_trace)
                )
                continue
            active_sensitivity = self._active_sensitivity_qp_step(
                active_candidate, state, slow_plan, active_exact
            )
            if active_sensitivity is not None and active_sensitivity[1].passed:
                candidate, candidate_exact, active_sensitivity_trace = active_sensitivity
                passing.append(
                    (candidate, candidate_exact, active_fraction, active_sensitivity_trace)
                )
                continue
            pairwise = self._pairwise_q_step(
                active_candidate, state, slow_plan, active_exact
            )
            if pairwise is not None and pairwise[1].passed:
                candidate, candidate_exact, pairwise_trace = pairwise
                passing.append(
                    (candidate, candidate_exact, active_fraction, pairwise_trace)
                )
                continue
            fleet = self._fleet_q_step(
                active_candidate, state, slow_plan, active_exact
            )
            if fleet is not None and fleet[1].passed:
                candidate, candidate_exact, fleet_trace = fleet
                passing.append(
                    (candidate, candidate_exact, active_fraction, fleet_trace)
                )
        if not passing:
            return None
        candidate, candidate_exact, active_fraction, coordinate_trace = min(
            passing, key=lambda item: self._objective_distance(control, item[0])
        )
        return candidate, candidate_exact, {
            "status": "FRESH_OPENDSS_PASSING_ACTIVE_COORDINATE_Q_SEARCH",
            "active_fraction": active_fraction,
            "coordinate_q": coordinate_trace,
        }

    def project(
        self, *, nominal: FastControl, state: FastLayerState, slow_plan: SlowDiscretePlan
    ) -> ProjectionCandidate:
        started = time.monotonic()
        current = nominal
        exact = self.verifier.verify_fresh(control=current, state=state, slow_plan=slow_plan)
        exact.validate()
        for _ in range(12):
            if exact.passed:
                break
            trace_row: dict[str, Any] = {
                "base": {
                    "vmin": exact.minimum_voltage_pu,
                    "vmax": exact.maximum_voltage_pu,
                    "line": exact.maximum_line_loading_fraction,
                    "transformer": exact.maximum_transformer_loading_fraction,
                }
            }
            if exact.minimum_voltage_pu < 0.95 or exact.maximum_voltage_pu > 1.05:
                coordinate = self._coordinate_q_step(current, state, slow_plan, exact)
                if coordinate is not None:
                    current, exact, coordinate_trace = coordinate
                    trace_row["coordinate_q"] = coordinate_trace
                    trace_row["candidate"] = {
                        "vmin": exact.minimum_voltage_pu,
                        "vmax": exact.maximum_voltage_pu,
                        "line": exact.maximum_line_loading_fraction,
                        "transformer": exact.maximum_transformer_loading_fraction,
                    }
                    self.trace.append(trace_row)
                    continue
                sensitivity = self._sensitivity_qp_step(
                    current, state, slow_plan, exact
                )
                if sensitivity is not None:
                    current, exact, sensitivity_trace = sensitivity
                    trace_row["sensitivity_qp"] = sensitivity_trace
                    trace_row["candidate"] = {
                        "vmin": exact.minimum_voltage_pu,
                        "vmax": exact.maximum_voltage_pu,
                        "line": exact.maximum_line_loading_fraction,
                        "transformer": exact.maximum_transformer_loading_fraction,
                    }
                    self.trace.append(trace_row)
                    continue
                active_sensitivity = self._active_sensitivity_qp_step(
                    current, state, slow_plan, exact
                )
                if active_sensitivity is not None:
                    current, exact, active_sensitivity_trace = active_sensitivity
                    trace_row["active_sensitivity_qp"] = active_sensitivity_trace
                    trace_row["candidate"] = {
                        "vmin": exact.minimum_voltage_pu,
                        "vmax": exact.maximum_voltage_pu,
                        "line": exact.maximum_line_loading_fraction,
                        "transformer": exact.maximum_transformer_loading_fraction,
                    }
                    self.trace.append(trace_row)
                    continue
                pairwise = self._pairwise_q_step(current, state, slow_plan, exact)
                if pairwise is not None:
                    current, exact, pairwise_trace = pairwise
                    trace_row["pairwise_q"] = pairwise_trace
                    trace_row["candidate"] = {
                        "vmin": exact.minimum_voltage_pu,
                        "vmax": exact.maximum_voltage_pu,
                        "line": exact.maximum_line_loading_fraction,
                        "transformer": exact.maximum_transformer_loading_fraction,
                    }
                    self.trace.append(trace_row)
                    continue
                fleet = self._fleet_q_step(current, state, slow_plan, exact)
                if fleet is not None:
                    current, exact, fleet_trace = fleet
                    trace_row["fleet_q"] = fleet_trace
                    trace_row["candidate"] = {
                        "vmin": exact.minimum_voltage_pu,
                        "vmax": exact.maximum_voltage_pu,
                        "line": exact.maximum_line_loading_fraction,
                        "transformer": exact.maximum_transformer_loading_fraction,
                    }
                    self.trace.append(trace_row)
                    continue
            active_target, voltage_target = self._targets(current, state, exact)
            thermal_or_low_voltage = (
                exact.minimum_voltage_pu < 0.95
                or exact.maximum_line_loading_fraction > 1.0
                or exact.maximum_transformer_loading_fraction > 1.0
            )
            voltage_violation = exact.maximum_voltage_pu > 1.05 or exact.minimum_voltage_pu < 0.95
            active_enabled = thermal_or_low_voltage
            voltage_enabled = voltage_violation
            active_distance = self._objective_distance(current, active_target) if active_enabled else 0.0
            voltage_distance = self._objective_distance(current, voltage_target) if voltage_enabled else 0.0
            if active_distance <= 1e-18 and voltage_distance <= 1e-18:
                break
            active_probe_fraction = 1.0
            voltage_probe_fraction = 0.25
            active_probe_exact = exact
            voltage_probe_exact = exact
            if active_distance > 1e-18:
                active_probe = self._combine(current, active_target, voltage_target, active_probe_fraction, 0.0)
                active_probe_exact = self.verifier.verify_fresh(control=active_probe, state=state, slow_plan=slow_plan)
                active_probe_exact.validate()
            if voltage_distance > 1e-18:
                voltage_probe = self._combine(current, active_target, voltage_target, 0.0, voltage_probe_fraction)
                voltage_probe_exact = self.verifier.verify_fresh(control=voltage_probe, state=state, slow_plan=slow_plan)
                voltage_probe_exact.validate()
            trace_row["active_probe"] = {
                "fraction": active_probe_fraction,
                "vmin": active_probe_exact.minimum_voltage_pu,
                "vmax": active_probe_exact.maximum_voltage_pu,
                "line": active_probe_exact.maximum_line_loading_fraction,
                "transformer": active_probe_exact.maximum_transformer_loading_fraction,
            }
            trace_row["voltage_probe"] = {
                "fraction": voltage_probe_fraction,
                "vmin": voltage_probe_exact.minimum_voltage_pu,
                "vmax": voltage_probe_exact.maximum_voltage_pu,
                "line": voltage_probe_exact.maximum_line_loading_fraction,
                "transformer": voltage_probe_exact.maximum_transformer_loading_fraction,
            }
            passing_probes = []
            if active_distance > 1e-18 and active_probe_exact.passed:
                passing_probes.append((active_probe, active_probe_exact, "active"))
            if voltage_distance > 1e-18 and voltage_probe_exact.passed:
                passing_probes.append((voltage_probe, voltage_probe_exact, "voltage"))
            if passing_probes:
                current, exact, accepted_axis = min(
                    passing_probes,
                    key=lambda item: self._objective_distance(current, item[0]),
                )
                trace_row["solver"] = {
                    "status": f"EXACT_AC_PASSING_{accepted_axis.upper()}_PROBE"
                }
                trace_row["candidate"] = {
                    "vmin": exact.minimum_voltage_pu,
                    "vmax": exact.maximum_voltage_pu,
                    "line": exact.maximum_line_loading_fraction,
                    "transformer": exact.maximum_transformer_loading_fraction,
                }
                self.trace.append(trace_row)
                continue
            if active_distance > 1e-18 and (
                active_probe_exact.minimum_voltage_pu < 0.95
                or active_probe_exact.maximum_voltage_pu > 1.05
            ):
                joint = self._active_coordinate_q_step(
                    current, active_target, voltage_target, state, slow_plan
                )
                if joint is not None:
                    current, exact, joint_trace = joint
                    trace_row["solver"] = joint_trace
                    trace_row["candidate"] = {
                        "vmin": exact.minimum_voltage_pu,
                        "vmax": exact.maximum_voltage_pu,
                        "line": exact.maximum_line_loading_fraction,
                        "transformer": exact.maximum_transformer_loading_fraction,
                    }
                    self.trace.append(trace_row)
                    continue
            try:
                import gurobipy as gp
                from gurobipy import GRB
            except ImportError as exc:
                raise RuntimeContractError("gurobipy is required by the AC safety projector") from exc
            model = gp.Model("pfr_ac_safety_projection")
            model.Params.OutputFlag = 0
            model.Params.Threads = 1
            model.Params.Seed = 0
            z_active = model.addVar(lb=0.0, ub=1.0 if active_distance > 1e-18 else 0.0, name="active_relief_fraction")
            z_voltage = model.addVar(lb=0.0, ub=1.0 if voltage_distance > 1e-18 else 0.0, name="voltage_support_fraction")
            metrics = (
                (exact.minimum_voltage_pu, active_probe_exact.minimum_voltage_pu, voltage_probe_exact.minimum_voltage_pu, GRB.GREATER_EQUAL, 0.9505),
                (exact.maximum_voltage_pu, active_probe_exact.maximum_voltage_pu, voltage_probe_exact.maximum_voltage_pu, GRB.LESS_EQUAL, 1.0495),
                (exact.maximum_line_loading_fraction, active_probe_exact.maximum_line_loading_fraction, voltage_probe_exact.maximum_line_loading_fraction, GRB.LESS_EQUAL, 1.0),
                (exact.maximum_transformer_loading_fraction, active_probe_exact.maximum_transformer_loading_fraction, voltage_probe_exact.maximum_transformer_loading_fraction, GRB.LESS_EQUAL, 1.0),
            )
            for index, (base, sampled_active, sampled_voltage, sense, bound) in enumerate(metrics):
                slope_active = (sampled_active - base) / active_probe_fraction
                slope_voltage = (sampled_voltage - base) / voltage_probe_fraction
                expression = base + slope_active * z_active + slope_voltage * z_voltage
                constraint = expression >= bound if sense == GRB.GREATER_EQUAL else expression <= bound
                model.addConstr(constraint, name=f"ac_envelope[{index}]")
            model.setObjective(
                max(active_distance, 1e-12) * z_active * z_active
                + max(voltage_distance, 1e-12) * z_voltage * z_voltage,
                GRB.MINIMIZE,
            )
            model.addConstr(z_active + z_voltage <= 1.0, name="opposing_active_power_axes")
            model.optimize()
            if model.Status not in {GRB.OPTIMAL, GRB.SUBOPTIMAL} or model.SolCount < 1 or float(model.MaxVio) > 1e-6:
                trace_row["solver"] = {"status": int(model.Status), "solutions": int(model.SolCount)}
                model.dispose()
                exact_line_search = []
                if voltage_distance > 1e-18:
                    for fraction_index in range(1, 10):
                        fraction = fraction_index / 40.0
                        line_candidate = self._combine(
                            current, active_target, voltage_target, 0.0, fraction
                        )
                        line_exact = self.verifier.verify_fresh(
                            control=line_candidate, state=state, slow_plan=slow_plan
                        )
                        line_exact.validate()
                        if line_exact.passed:
                            exact_line_search.append(
                                (line_candidate, line_exact, fraction)
                            )
                if exact_line_search:
                    current, exact, accepted_fraction = min(
                        exact_line_search,
                        key=lambda item: self._objective_distance(current, item[0]),
                    )
                    trace_row["solver"]["fallback"] = "FRESH_OPENDSS_EXACT_VOLTAGE_LINE_SEARCH"
                    trace_row["solver"]["accepted_voltage_fraction"] = accepted_fraction
                    trace_row["candidate"] = {
                        "vmin": exact.minimum_voltage_pu,
                        "vmax": exact.maximum_voltage_pu,
                        "line": exact.maximum_line_loading_fraction,
                        "transformer": exact.maximum_transformer_loading_fraction,
                    }
                    self.trace.append(trace_row)
                    continue
                improving_probes = []
                base_score = self._violation_score(exact)
                if active_distance > 1e-18 and self._violation_score(active_probe_exact) < base_score - 1e-12:
                    improving_probes.append((active_probe, active_probe_exact, "active"))
                if voltage_distance > 1e-18 and self._violation_score(voltage_probe_exact) < base_score - 1e-12:
                    improving_probes.append((voltage_probe, voltage_probe_exact, "voltage"))
                if not improving_probes:
                    self.trace.append(trace_row)
                    break
                current, exact, accepted_axis = min(
                    improving_probes, key=lambda item: self._violation_score(item[1])
                )
                trace_row["solver"]["fallback"] = f"EXACT_AC_IMPROVING_{accepted_axis.upper()}_PROBE"
                trace_row["candidate"] = {
                    "vmin": exact.minimum_voltage_pu,
                    "vmax": exact.maximum_voltage_pu,
                    "line": exact.maximum_line_loading_fraction,
                    "transformer": exact.maximum_transformer_loading_fraction,
                }
                self.trace.append(trace_row)
                continue
            active_fraction = min(1.0, max(0.0, float(z_active.X) * 1.05))
            voltage_fraction = min(1.0, max(0.0, float(z_voltage.X) * 1.05))
            model.dispose()
            base_score = self._violation_score(exact)
            accepted = None
            for backtrack in range(9):
                candidate = self._combine(
                    current,
                    active_target,
                    voltage_target,
                    active_fraction,
                    voltage_fraction,
                )
                candidate_exact = self.verifier.verify_fresh(
                    control=candidate, state=state, slow_plan=slow_plan
                )
                candidate_exact.validate()
                if candidate_exact.passed or self._violation_score(candidate_exact) < base_score - 1e-12:
                    accepted = (candidate, candidate_exact, backtrack)
                    break
                active_fraction *= 0.5
                voltage_fraction *= 0.5
            if accepted is None:
                trace_row["solver"] = {"status": "REJECTED_NONIMPROVING_EXACT_AC"}
                self.trace.append(trace_row)
                break
            current, exact, backtrack = accepted
            trace_row["solver"] = {
                "status": "ACCEPTED_NUMERIC",
                "active_fraction": active_fraction,
                "voltage_fraction": voltage_fraction,
                "exact_ac_backtracks": backtrack,
            }
            trace_row["candidate"] = {
                "vmin": exact.minimum_voltage_pu,
                "vmax": exact.maximum_voltage_pu,
                "line": exact.maximum_line_loading_fraction,
                "transformer": exact.maximum_transformer_loading_fraction,
            }
            self.trace.append(trace_row)
        return ProjectionCandidate(
            control=current,
            certificate=ProjectionCertificate(
                "CONVEX_CONTINUOUS_QP", True, True, True, True, True, True, True, True
            ),
            slow_plan_fingerprint=slow_plan.fingerprint,
            objective_nominal=0.0,
            objective_projected=self._objective_distance(nominal, current),
            runtime_seconds=time.monotonic() - started,
        )


def _method_uses_temporal(config: MethodConfig) -> bool:
    return config.temporal_workload_shift


def _admit_arrivals(state: MutableMethodState, frame: CausalExperimentFrame, config: MethodConfig) -> int:
    spatial_blocked = 0
    site_counts = {site: sum(job.destination_idc == site for job in state.jobs.values()) for site in IDCS}
    for source in frame.arrivals:
        if source.job_uid in state.jobs:
            raise RuntimeContractError("duplicate job arrival")
        destination = source.origin_idc
        migration_state = "NOT_REQUESTED"
        if config.spatial_workload_migration:
            if source.input_bytes is None:
                migration_state = "BLOCKED_MISSING_PAYLOAD_AUTHORITY"
                spatial_blocked += 1
            else:
                destination = min(IDCS, key=lambda site: (site_counts[site], site))
                migration_state = "NEW_JOB_PLACEMENT_PAYLOAD_KNOWN"
        site_counts[destination] += 1
        gang = tuple(f"{destination}:PFR-GPU:{source.job_uid}:{index}" for index in range(source.requested_gpu))
        state.jobs[source.job_uid] = RuntimeJobState(
            source=source,
            destination_idc=destination,
            logical_rack_id=f"{destination}:PFR-H100-LOGICAL-POOL",
            gang_membership=gang,
            remaining_work_gpu_hours=source.total_work_gpu_hours,
            migration_state=migration_state,
        )
    return spatial_blocked


def _compute_fraction(job: RuntimeJobState, frame: CausalExperimentFrame, config: MethodConfig) -> float:
    if job.lifecycle == "COMPLETED":
        return 0.0
    remaining_full_steps = math.ceil(job.remaining_work_gpu_hours / (job.source.requested_gpu * STEP_HOURS))
    steps_to_deadline = job.source.deadline_step - frame.issue
    urgent = frame.issue >= job.source.latest_start_step or remaining_full_steps >= steps_to_deadline
    if not _method_uses_temporal(config) or urgent:
        return 1.0
    return 1.0 if frame.current_price_aud_per_mwh <= frame.horizon_price_median_aud_per_mwh else 0.5


def _pareto_routes(
    routes: Sequence[MobilityRouteForecast], *, safe: bool
) -> Tuple[MobilityRouteForecast, ...]:
    def metrics(route: MobilityRouteForecast) -> Tuple[float, float]:
        return (
            route.safe_eta_seconds if safe else route.q50_eta_seconds,
            route.safe_energy_kwh if safe else route.q50_energy_kwh,
        )

    kept = []
    for candidate in routes:
        candidate_metrics = metrics(candidate)
        dominated = any(
            metrics(other)[0] <= candidate_metrics[0]
            and metrics(other)[1] <= candidate_metrics[1]
            and metrics(other) != candidate_metrics
            for other in routes
        )
        if not dominated:
            kept.append(candidate)
    return tuple(sorted(kept, key=lambda route: route.rank))


def _mobility_energy_profile(
    route: MobilityRouteForecast,
    template_bank: Mapping[int, Tuple[float, ...]],
    *,
    safe: bool,
) -> Tuple[float, ...]:
    route.validate()
    cumulative = template_bank.get(route.profile_template_id)
    if cumulative is None or len(cumulative) != 129:
        raise RuntimeContractError("selected route lacks its frozen E4B profile template")
    if any(not math.isfinite(value) for value in cumulative) or abs(cumulative[0]) > 1e-9 or abs(cumulative[-1] - 1.0) > 1e-6:
        raise RuntimeContractError("E4B cumulative profile is invalid")
    eta = route.safe_eta_seconds if safe else route.q50_eta_seconds
    total = route.safe_energy_kwh if safe else route.q50_energy_kwh
    steps = min(54, max(1, math.ceil(eta / 300.0), route.profile_horizon_steps))

    def interpolate(fraction: float) -> float:
        position = fraction * 128.0
        left = min(127, int(math.floor(position)))
        weight = position - left
        return cumulative[left] + weight * (cumulative[left + 1] - cumulative[left])

    sampled = tuple(interpolate(index / steps) for index in range(steps + 1))
    profile = tuple(max(0.0, sampled[index + 1] - sampled[index]) * total for index in range(steps))
    if abs(sum(profile) - total) > max(1e-8, total * 1e-8):
        raise RuntimeContractError("E4B route profile does not conserve safe mobility energy")
    return profile


def _optimize_mess_routes(
    state: MutableMethodState,
    config: MethodConfig,
    frame: CausalExperimentFrame,
) -> Tuple[dict[str, str], dict[str, int]]:
    destinations = dict(state.mess_location)
    ranks = dict(state.mess_route_rank)
    if config.energy_flexibility != "MESS" or not frame.mobility_routes:
        state.last_slow_miqp_certificate = {
            "status": "NO_MOBILE_ROUTE_OPTIMIZATION_FOR_METHOD",
            "actual_gurobi_used": False,
            "num_integer_variables": 0,
        }
        return destinations, ranks
    demand = {site: 0.0 for site in IDCS}
    for job in state.jobs.values():
        if job.lifecycle != "COMPLETED":
            demand[job.destination_idc] += job.remaining_work_gpu_hours
    candidate_sites = tuple(site for site in IDCS if demand[site] > 0.0)
    if not candidate_sites:
        state.last_slow_miqp_certificate = {
            "status": "NO_ACTIVE_WORKLOAD_DESTINATION",
            "actual_gurobi_used": False,
            "num_integer_variables": 0,
        }
        return destinations, ranks

    candidates: dict[str, list[Tuple[str, int, Optional[MobilityRouteForecast], float]]] = {}
    safe = config.joint_uncertainty
    for mid in MESS_IDS:
        if state.mess_in_transit[mid]:
            target = state.mess_route_destination[mid]
            if target is None:
                raise RuntimeContractError("transit MESS lacks destination")
            candidates[mid] = [(target, state.mess_route_rank[mid], None, 0.0)]
            continue
        current = state.mess_location[mid]
        rows = [(current, 1, None, -demand.get(current, 0.0) / 25.0)]
        for destination in candidate_sites:
            if destination == current:
                continue
            for route in _pareto_routes(frame.routes_for(current, destination), safe=safe):
                eta = route.safe_eta_seconds if safe else route.q50_eta_seconds
                energy = route.safe_energy_kwh if safe else route.q50_energy_kwh
                if math.ceil(eta / 300.0) > 54:
                    continue
                if state.mess_energy_kwh[mid] - energy < MESS_FLOOR_KWH - 1e-9:
                    continue
                score = eta / 1800.0 + energy / 100.0 - demand[destination] / 25.0
                rows.append((destination, route.rank, route, score))
        candidates[mid] = rows

    try:
        import gurobipy as gp
        from gurobipy import GRB
    except Exception as exc:
        raise RuntimeContractError("slow mobility MIQP requires gurobipy") from exc
    model = gp.Model("pfr_slow_mobility_miqp")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 0
    variables = {
        (mid, index): model.addVar(vtype=GRB.BINARY, name=f"z_{mid}_{index}")
        for mid, rows in candidates.items()
        for index in range(len(rows))
    }
    for mid, rows in candidates.items():
        model.addConstr(gp.quicksum(variables[mid, index] for index in range(len(rows))) == 1.0)
    model.addConstr(
        gp.quicksum(
            variables[mid, index]
            for mid, rows in candidates.items()
            for index, row in enumerate(rows)
            if row[2] is not None
        )
        <= 1,
        name="retain_three_parked_mess_for_common_ac_safety",
    )
    objective = gp.quicksum(
        row[3] * variables[mid, index]
        for mid, rows in candidates.items()
        for index, row in enumerate(rows)
    )
    for destination in candidate_sites:
        assigned = gp.quicksum(
            variables[mid, index]
            for mid, rows in candidates.items()
            for index, row in enumerate(rows)
            if row[0] == destination
        )
        objective += 0.02 * assigned * assigned
    model.setObjective(objective, GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL or model.SolCount < 1 or float(model.MaxVio) > 1e-6:
        status = int(model.Status)
        model.dispose()
        raise RuntimeContractError(f"slow mobility MIQP failed status={status}")
    for mid, rows in candidates.items():
        selected = next(index for index in range(len(rows)) if variables[mid, index].X > 0.5)
        destinations[mid], ranks[mid] = rows[selected][0], rows[selected][1]
    state.last_slow_miqp_certificate = {
        "status": "OPTIMAL",
        "actual_gurobi_used": True,
        "num_integer_variables": len(variables),
        "num_quadratic_objective_terms": len(candidate_sites),
        "joint_safe_eta_energy_used": safe,
    }
    model.dispose()
    return destinations, ranks


def _build_slow_plan(
    state: MutableMethodState, config: MethodConfig, frame: CausalExperimentFrame
) -> SlowDiscretePlan:
    jobs = {uid: job for uid, job in state.jobs.items() if job.lifecycle != "COMPLETED"}
    destinations, route_ranks = _optimize_mess_routes(state, config, frame)
    plan = SlowDiscretePlan(
        plan_id=f"{config.comparison_method_id.value}-{frame.issue}-{state.full_replan_count + 1}",
        valid_from_issue=frame.issue,
        mess_destination=destinations,
        mess_native_route_rank=route_ranks,
        job_idc_placement={uid: job.destination_idc for uid, job in jobs.items()},
        checkpoint_migration={uid: None for uid in jobs},
        gpu_gang_allocation={uid: job.gang_membership for uid, job in jobs.items()},
        job_start_issue={uid: max(frame.issue, job.source.arrival_step) for uid, job in jobs.items()},
        coarse_charging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
    )
    plan.validate()
    return plan


def _start_planned_routes(
    state: MutableMethodState, config: MethodConfig, frame: CausalExperimentFrame
) -> None:
    if state.active_plan is None or config.energy_flexibility != "MESS":
        return
    for mid in MESS_IDS:
        if state.mess_in_transit[mid]:
            continue
        source = state.mess_location[mid]
        destination = state.active_plan.mess_destination[mid]
        if source == destination:
            continue
        rank = state.active_plan.mess_native_route_rank[mid]
        routes = [route for route in frame.routes_for(source, destination) if route.rank == rank]
        if len(routes) != 1:
            raise RuntimeContractError("slow plan selected a route outside frozen K=3")
        profile = _mobility_energy_profile(
            routes[0], frame.mobility_template_bank, safe=config.joint_uncertainty
        )
        if state.mess_energy_kwh[mid] - sum(profile) < MESS_FLOOR_KWH - 1e-9:
            raise RuntimeContractError("selected mobility profile violates protected SOC floor")
        state.mess_in_transit[mid] = True
        state.mess_route_destination[mid] = destination
        state.mess_route_rank[mid] = rank
        state.mess_route_energy_profile_kwh[mid] = profile
        state.mess_route_profile_index[mid] = 0


def _risk_decision(state: MutableMethodState, frame: CausalExperimentFrame, config: MethodConfig):
    active_jobs = [job for job in state.jobs.values() if job.lifecycle != "COMPLETED"]
    gpu_by_site = {site: sum(job.source.requested_gpu for job in active_jobs if job.destination_idc == site) for site in IDCS}
    if config.joint_uncertainty:
        gpu_by_site = {
            site: gpu_by_site[site] + frame.workload_reserve_gpu.get(site, 0.0)
            for site in IDCS
        }
    deadline_margin = max(
        (
            job.remaining_work_gpu_hours
            - max(0, job.source.deadline_step - frame.issue) * job.source.requested_gpu * STEP_HOURS
            for job in active_jobs
        ),
        default=-1.0,
    )
    min_energy = min(state.mess_energy_kwh.values())
    if state.last_exact is None:
        voltage_margin, thermal_margin = -0.01, -0.10
    else:
        voltage_margin = max(
            0.95 - float(state.last_exact["voltage_min_pu"]),
            float(state.last_exact["voltage_max_pu"]) - 1.05,
        )
        thermal_margin = max(
            float(state.last_exact["line_max_loading_pu"]) - 1.0,
            float(state.last_exact["transformer_max_current_loading_pu"]) - 1.0,
        )
    calibrated = config.risk_interface == "CALIBRATED"
    constraints = (
        RiskConstraint("soc", RiskFamily.SOC, MESS_FLOOR_KWH - min_energy, 100.0),
        RiskConstraint("deadline", RiskFamily.DEADLINE, deadline_margin, 1.0),
        RiskConstraint("gpu", RiskFamily.GPU, max(gpu_by_site.values(), default=0) - MODELED_GPU_CAPACITY_PER_IDC, 32.0),
        RiskConstraint("wan", RiskFamily.WAN, -1.0, 1.0),
        RiskConstraint("voltage", RiskFamily.VOLTAGE, voltage_margin, 0.01),
        RiskConstraint("thermal", RiskFamily.THERMAL, thermal_margin, 0.10),
    )
    return PlanValidityRiskMonitor(calibrated=calibrated, maximum_refresh_steps=6).evaluate(
        constraints=constraints,
        expected_replan_benefit=0.0,
        replan_cost=ReplanCost(1.0, 0.0, 0.1, 0.01),
        plan_age_steps=state.active_plan_age_steps,
    )


def _should_replan(state: MutableMethodState, config: MethodConfig, risk: Any, issue_offset: int) -> Tuple[bool, Tuple[str, ...]]:
    if state.active_plan is None:
        return True, ("INITIAL_PLAN",)
    if config.control_mode == "PERIODIC_MPC" and state.active_plan_age_steps >= 6:
        return True, ("PERIODIC_30_MINUTE_REFRESH",)
    if config.control_mode == "EVENT_TRIGGERED" and risk.request_full_replan:
        return True, risk.trigger_causes
    return False, ()


def _facility_power(
    jobs: Iterable[RuntimeJobState], curve: H100UtilizationPowerCurve
) -> Tuple[Tuple[float, ...], Tuple[float, ...]]:
    active = [job for job in jobs if job.lifecycle == "RUNNING" and job.compute_rate_fraction > 0.0]
    p = {site: 0.0 for site in IDCS}
    for job in active:
        p[job.destination_idc] += (
            curve.gang_power_kw(job.source.requested_gpu, job.compute_rate_fraction)
            + job.source.cpu_request_share_kw
        )
    if any(value > 750.0 + 1e-9 for value in p.values()):
        raise RuntimeContractError("AI facility load exceeds unchanged 750-kVA transformer rating")
    return tuple(p[site] for site in IDCS), (0.0,) * len(IDCS)


def _nominal_mess_dispatch(
    *,
    energy_kwh: Mapping[str, float],
    in_transit: Mapping[str, bool],
    energy_enabled: bool,
    current_price_aud_per_mwh: float,
    horizon_price_median_aud_per_mwh: float,
) -> Tuple[Mapping[str, float], Mapping[str, float]]:
    charge = {mid: 0.0 for mid in MESS_IDS}
    discharge = {mid: 0.0 for mid in MESS_IDS}
    if not energy_enabled:
        return charge, discharge

    price_margin = PRICE_DEADBAND_FRACTION * max(abs(horizon_price_median_aud_per_mwh), 1.0)
    low_price = current_price_aud_per_mwh < horizon_price_median_aud_per_mwh - price_margin
    high_price = current_price_aud_per_mwh > horizon_price_median_aud_per_mwh + price_margin
    recovery_hours = MAXIMUM_REFRESH_STEPS * STEP_HOURS
    for mid in MESS_IDS:
        if in_transit[mid]:
            continue
        energy = float(energy_kwh[mid])
        if low_price and energy < MESS_CAPACITY_KWH:
            charge[mid] = min(
                MESS_CHARGE_LIMIT_KW,
                (MESS_CAPACITY_KWH - energy) / (MESS_CHARGE_EFFICIENCY * recovery_hours),
            )
        elif not high_price and energy < MESS_CANONICAL_DAILY_PRE_KWH:
            charge[mid] = min(
                MESS_CHARGE_LIMIT_KW,
                (MESS_CANONICAL_DAILY_PRE_KWH - energy) / (MESS_CHARGE_EFFICIENCY * recovery_hours),
            )
        elif high_price and energy > MESS_SAFETY_RESERVE_KWH:
            discharge[mid] = min(
                MESS_NOMINAL_DISCHARGE_KW,
                (energy - MESS_SAFETY_RESERVE_KWH) * MESS_CHARGE_EFFICIENCY / STEP_HOURS,
            )
    return charge, discharge


def _nominal_control(state: MutableMethodState, config: MethodConfig, frame: CausalExperimentFrame) -> FastControl:
    compute = {
        uid: _compute_fraction(job, frame, config)
        for uid, job in state.jobs.items()
        if job.lifecycle != "COMPLETED"
    }
    energy_enabled = config.energy_flexibility in {"MESS", "STATIONARY_BESS"}
    charge, discharge = _nominal_mess_dispatch(
        energy_kwh=state.mess_energy_kwh,
        in_transit=state.mess_in_transit,
        energy_enabled=energy_enabled,
        current_price_aud_per_mwh=frame.current_price_aud_per_mwh,
        horizon_price_median_aud_per_mwh=frame.horizon_price_median_aud_per_mwh,
    )
    return FastControl(
        mess_charge_kw=charge,
        mess_discharge_kw=discharge,
        mess_q_kvar={mid: 0.0 for mid in MESS_IDS},
        job_compute_rate_fraction=compute,
        site_throughput_fraction={site: 1.0 for site in IDCS},
    )


def _post_payload(state: MutableMethodState, method_id: str) -> Mapping[str, Any]:
    return {
        "comparison_method_id": method_id,
        "issue": state.issue,
        "mess_energy_kwh": state.mess_energy_kwh,
        "mess_location": state.mess_location,
        "mess_in_transit": state.mess_in_transit,
        "mess_route_destination": state.mess_route_destination,
        "mess_route_rank": state.mess_route_rank,
        "mess_route_profile_index": state.mess_route_profile_index,
        "wan_transferred_bytes_cumulative": state.wan_transferred_bytes_cumulative,
        "wan_active_transfers": state.wan_active_transfers,
        "jobs": {
            uid: {
                "destination_idc": job.destination_idc,
                "logical_rack_id": job.logical_rack_id,
                "gang_membership": job.gang_membership,
                "remaining_work_gpu_hours": job.remaining_work_gpu_hours,
                "lifecycle": job.lifecycle,
                "start_issue": job.start_issue,
                "completion_issue": job.completion_issue,
                "checkpoint_state": job.checkpoint_state,
                "migration_state": job.migration_state,
            }
            for uid, job in sorted(state.jobs.items())
        },
        "compute_debt_gpu_hours": state.compute_debt_gpu_hours,
        "energy_debt_kwh": state.energy_debt_kwh,
    }


class PfrRuntimeRunner:
    def __init__(
        self,
        *,
        power_curve: H100UtilizationPowerCurve,
        physical_backend: FreshPhysicalBackend,
        fast_optimizer: Optional[FastControlOptimizer] = None,
        controller_id: str = "PFR_V13_SLOW_FAST_AC_SAFE_V1",
    ) -> None:
        power_curve.validate()
        self.power_curve = power_curve
        self.physical_backend = physical_backend
        self.fast_optimizer = fast_optimizer or IdentityFastControlOptimizer()
        self.controller_id = controller_id
        self.architecture = SlowFastArchitecture()

    def run_method(
        self,
        *,
        config: MethodConfig,
        frames: Sequence[CausalExperimentFrame],
        initial: RuntimeInitialState,
        representative_week_id: str,
        output: Path,
    ) -> Mapping[str, Any]:
        if not frames:
            raise RuntimeContractError("runtime needs at least one frame")
        initial.validate()
        if frames[0].issue != initial.issue or [frame.issue for frame in frames] != list(range(initial.issue, initial.issue + len(frames))):
            raise RuntimeContractError("runtime frame axis is not contiguous from canonical PRE")
        identity = K9H7ResultIdentityV2.for_method(
            config, controller_id=self.controller_id, representative_week_id=representative_week_id
        )
        method_root = output / config.comparison_method_id.value
        method_root.mkdir(parents=True, exist_ok=True)
        state = MutableMethodState(
            issue=initial.issue,
            pre_state_sha256=initial.state_sha256,
            mess_energy_kwh=dict(initial.mess_energy_kwh),
            mess_location=dict(initial.mess_location),
        )
        records = []
        failure: Optional[Mapping[str, Any]] = None
        for offset, frame in enumerate(frames):
            started = time.monotonic()
            frame.validate()
            if frame.issue != state.issue:
                raise RuntimeContractError("PRE state issue does not match causal frame")
            blocked_spatial = _admit_arrivals(state, frame, config)
            risk = _risk_decision(state, frame, config)
            replan, replan_causes = _should_replan(state, config, risk, offset)
            if replan:
                state.active_plan = _build_slow_plan(state, config, frame)
                state.active_plan_age_steps = 0
                state.full_replan_count += 1
                state.communication_bytes += len(
                    json.dumps(asdict(state.active_plan), sort_keys=True, separators=(",", ":"))
                )
                _start_planned_routes(state, config, frame)
            if state.active_plan is None:
                raise RuntimeContractError("no active slow plan")
            slow_fingerprint = state.active_plan.fingerprint
            nominal = _nominal_control(state, config, frame)
            fast_state = FastLayerState(
                issue=frame.issue,
                mess_soc={mid: state.mess_energy_kwh[mid] / MESS_CAPACITY_KWH for mid in MESS_IDS},
                remaining_work_gpu_hours={
                    uid: job.remaining_work_gpu_hours
                    for uid, job in state.jobs.items()
                    if job.lifecycle != "COMPLETED" and uid in state.active_plan.job_idc_placement
                },
            )
            limits = FastLayerLimits(
                step_minutes=5,
                mess_energy_capacity_kwh={mid: MESS_CAPACITY_KWH for mid in MESS_IDS},
                mess_charge_limit_kw={mid: 0.0 if state.mess_in_transit[mid] else 550.0 for mid in MESS_IDS},
                mess_discharge_limit_kw={mid: 0.0 if state.mess_in_transit[mid] else 550.0 for mid in MESS_IDS},
                mess_pcs_kva={mid: 700.0 for mid in MESS_IDS},
                mess_soc_min={mid: MESS_FLOOR_KWH / MESS_CAPACITY_KWH for mid in MESS_IDS},
                mess_soc_max={mid: 1.0 for mid in MESS_IDS},
                job_gpu_count={uid: state.jobs[uid].source.requested_gpu for uid in fast_state.remaining_work_gpu_hours},
                site_throughput_limit={site: 1.0 for site in IDCS},
            )
            optimized = self.fast_optimizer.optimize(
                nominal=nominal,
                state=fast_state,
                limits=limits,
                context=FastOptimizationContext(
                    issue=frame.issue,
                    current_price_aud_per_mwh=frame.current_price_aud_per_mwh,
                    horizon_price_median_aud_per_mwh=frame.horizon_price_median_aud_per_mwh,
                    job_destination={uid: state.jobs[uid].destination_idc for uid in fast_state.remaining_work_gpu_hours},
                    job_deadline_step={uid: state.jobs[uid].source.deadline_step for uid in fast_state.remaining_work_gpu_hours},
                    site_gpu_capacity={
                        site: MODELED_GPU_CAPACITY_PER_IDC
                        - (frame.workload_reserve_gpu.get(site, 0.0) if config.joint_uncertainty else 0.0)
                        for site in IDCS
                    },
                    mess_operational_enabled=config.energy_flexibility in {"MESS", "STATIONARY_BESS"},
                ),
            )
            fast = execute_fast_recourse(
                architecture=self.architecture,
                slow_plan=state.active_plan,
                state=fast_state,
                nominal=optimized.control,
                limits=limits,
                grid_screen=lambda control, candidate_state: GridScreenResult(
                    True, "PFR6_CONSERVATIVE_PROJECTION_DOMAIN_SCREEN", 0.95, 1.05, 1.0
                ),
            )
            verifier = _PhysicalVerifierAdapter(
                self.physical_backend,
                frame.issue,
                state.jobs,
                self.power_curve,
                tuple(state.mess_location[mid] for mid in MESS_IDS),
                tuple(state.mess_in_transit[mid] for mid in MESS_IDS),
                frame.robust_background_p_kw,
                frame.robust_background_q_kvar,
                frame.robust_pv_available_kw,
            )
            accepted_fast_state = fast_state
            accepted_limits = limits
            active_optimization = optimized
            safety_replan = False

            def escalate_for_safety() -> EscalatedCandidate:
                nonlocal accepted_fast_state, accepted_limits, active_optimization, fast, safety_replan
                state.active_plan = _build_slow_plan(state, config, frame)
                state.active_plan_age_steps = 0
                state.full_replan_count += 1
                state.communication_bytes += len(
                    json.dumps(asdict(state.active_plan), sort_keys=True, separators=(",", ":"))
                )
                safety_replan = True
                accepted_fast_state = FastLayerState(
                    issue=frame.issue,
                    mess_soc={mid: state.mess_energy_kwh[mid] / MESS_CAPACITY_KWH for mid in MESS_IDS},
                    remaining_work_gpu_hours={
                        uid: job.remaining_work_gpu_hours
                        for uid, job in state.jobs.items()
                        if job.lifecycle != "COMPLETED" and uid in state.active_plan.job_idc_placement
                    },
                )
                accepted_limits = FastLayerLimits(
                    step_minutes=5,
                    mess_energy_capacity_kwh={mid: MESS_CAPACITY_KWH for mid in MESS_IDS},
                    mess_charge_limit_kw={mid: 0.0 if state.mess_in_transit[mid] else 550.0 for mid in MESS_IDS},
                    mess_discharge_limit_kw={mid: 0.0 if state.mess_in_transit[mid] else 550.0 for mid in MESS_IDS},
                    mess_pcs_kva={mid: 700.0 for mid in MESS_IDS},
                    mess_soc_min={mid: MESS_FLOOR_KWH / MESS_CAPACITY_KWH for mid in MESS_IDS},
                    mess_soc_max={mid: 1.0 for mid in MESS_IDS},
                    job_gpu_count={uid: state.jobs[uid].source.requested_gpu for uid in accepted_fast_state.remaining_work_gpu_hours},
                    site_throughput_limit={site: 1.0 for site in IDCS},
                )
                escalated_nominal = _nominal_control(state, config, frame)
                active_optimization = self.fast_optimizer.optimize(
                    nominal=escalated_nominal,
                    state=accepted_fast_state,
                    limits=accepted_limits,
                    context=FastOptimizationContext(
                        issue=frame.issue,
                        current_price_aud_per_mwh=frame.current_price_aud_per_mwh,
                        horizon_price_median_aud_per_mwh=frame.horizon_price_median_aud_per_mwh,
                        job_destination={uid: state.jobs[uid].destination_idc for uid in accepted_fast_state.remaining_work_gpu_hours},
                        job_deadline_step={uid: state.jobs[uid].source.deadline_step for uid in accepted_fast_state.remaining_work_gpu_hours},
                        site_gpu_capacity={
                            site: MODELED_GPU_CAPACITY_PER_IDC
                            - (frame.workload_reserve_gpu.get(site, 0.0) if config.joint_uncertainty else 0.0)
                            for site in IDCS
                        },
                        mess_operational_enabled=config.energy_flexibility in {"MESS", "STATIONARY_BESS"},
                    ),
                )
                fast = execute_fast_recourse(
                    architecture=self.architecture,
                    slow_plan=state.active_plan,
                    state=accepted_fast_state,
                    nominal=active_optimization.control,
                    limits=accepted_limits,
                    grid_screen=lambda control, candidate_state: GridScreenResult(
                        True, "PFR6_CONSERVATIVE_PROJECTION_DOMAIN_SCREEN", 0.95, 1.05, 1.0
                    ),
                )
                return EscalatedCandidate(state.active_plan, accepted_fast_state, fast.control, True, True)

            safety_projector = _GurobiSensitivityProjector(verifier, allow_mess=True)
            safety = AcSafetyFilter(
                projector=safety_projector,
                verifier=verifier,
            ).filter(
                nominal=fast.control,
                state=accepted_fast_state,
                slow_plan=state.active_plan,
                escalate_full_replan=escalate_for_safety,
            )
            if verifier.last_commit is None:
                raise RuntimeContractError("Fresh physical verifier produced no commit evidence")
            if not safety.accepted:
                failure = {
                    "status": "FAIL_CLOSED_EXACT_AC",
                    "issue": frame.issue,
                    "comparison_method_id": config.comparison_method_id.value,
                    "exact_ac": dict(verifier.last_commit.raw_metrics),
                    "safety_projection_trace": safety_projector.trace,
                    "partial_results_preserved": True,
                }
                (method_root / "FAILURE.json").write_text(
                    json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                break
            fast = execute_fast_recourse(
                architecture=self.architecture,
                slow_plan=state.active_plan,
                state=accepted_fast_state,
                nominal=safety.safe_control,
                limits=accepted_limits,
                grid_screen=lambda control, candidate_state: GridScreenResult(
                    True, "PFR6_EXACT_ACCEPTED_CONTROL", 0.95, 1.05, 1.0
                ),
            )
            for uid, fraction in fast.control.job_compute_rate_fraction.items():
                job = state.jobs[uid]
                job.compute_rate_fraction = fraction
                if fraction > 0.0 and job.lifecycle == "QUEUED":
                    job.lifecycle = "RUNNING"
                    job.start_issue = frame.issue
            facility_p, _ = _facility_power(state.jobs.values(), self.power_curve)
            for mid in MESS_IDS:
                state.mess_energy_kwh[mid] = fast.next_state.mess_soc[mid] * MESS_CAPACITY_KWH
            mobility_energy_kwh = 0.0
            for mid in MESS_IDS:
                if not state.mess_in_transit[mid]:
                    continue
                index = state.mess_route_profile_index[mid]
                profile = state.mess_route_energy_profile_kwh[mid]
                if index >= len(profile):
                    raise RuntimeContractError("transit profile index escaped E4B authority")
                movement = profile[index]
                mobility_energy_kwh += movement
                state.mess_energy_kwh[mid] -= movement
                if state.mess_energy_kwh[mid] < MESS_FLOOR_KWH - 1e-9:
                    raise RuntimeContractError("realized mobility profile violated protected SOC floor")
                state.mess_route_profile_index[mid] += 1
                if state.mess_route_profile_index[mid] == len(profile):
                    destination = state.mess_route_destination[mid]
                    if destination is None:
                        raise RuntimeContractError("completed route lacks destination")
                    state.mess_location[mid] = destination
                    state.mess_in_transit[mid] = False
                    state.mess_route_destination[mid] = None
                    state.mess_route_energy_profile_kwh[mid] = ()
                    state.mess_route_profile_index[mid] = 0
            for uid, remaining in fast.next_state.remaining_work_gpu_hours.items():
                job = state.jobs[uid]
                job.remaining_work_gpu_hours = remaining
                if remaining <= 1e-12:
                    job.remaining_work_gpu_hours = 0.0
                    job.lifecycle = "COMPLETED"
                    job.completion_issue = frame.issue + 1
            state.compute_debt_gpu_hours = sum(
                max(0.0, job.remaining_work_gpu_hours - max(0, job.source.deadline_step - frame.issue - 1) * job.source.requested_gpu * STEP_HOURS)
                for job in state.jobs.values() if job.lifecycle != "COMPLETED"
            )
            state.last_exact = dict(verifier.last_commit.raw_metrics)
            pre_hash = state.pre_state_sha256
            state.issue = frame.issue + 1
            post_hash = canonical_hash(_post_payload(state, config.comparison_method_id.value))
            state.pre_state_sha256 = post_hash
            state.active_plan_age_steps += 1
            deadline_misses = sum(
                job.lifecycle != "COMPLETED" and state.issue > job.source.deadline_step
                for job in state.jobs.values()
            )
            record = {
                "schema_version": "K9H7_RESULT_V2.issue_commit.v1",
                "result_uid": identity.result_uid,
                "scientific_framework_id": identity.scientific_framework_id,
                "comparison_method_id": config.comparison_method_id.value,
                "controller_id": identity.controller_id,
                "ablation_id": identity.ablation_id,
                "representative_week_id": representative_week_id,
                "issue": frame.issue,
                "status": "PASS_COMMITTED",
                "commit_marker": True,
                "pre_state_sha256": pre_hash,
                "post_state_sha256": post_hash,
                "causal_exogenous_sha256": frame.exogenous_sha256,
                "future_actual_used": False,
                "h0_only_committed": True,
                "slow_plan_fingerprint": state.active_plan.fingerprint,
                "binary_state_unchanged": fast.binary_state_unchanged,
                "full_replan_executed": replan or safety_replan,
                "replan_causes": replan_causes + (("AC_SAFETY_ESCALATION",) if safety_replan else ()),
                "full_replan_count_cumulative": state.full_replan_count,
                "communication_bytes_cumulative": state.communication_bytes,
                "wan_transferred_bytes_cumulative": state.wan_transferred_bytes_cumulative,
                "wan_active_transfers": state.wan_active_transfers,
                "wan_transfer_authority": "NO_AUTHORIZED_MIGRATIONS_MISSING_PAYLOAD",
                "risk_interface": risk.active_risk_interface,
                "risk": risk.active_risk,
                "risk_components": risk.calibrated_components if config.risk_interface == "CALIBRATED" else risk.raw_components,
                "arrivals": len(frame.arrivals),
                "active_jobs": sum(job.lifecycle == "RUNNING" for job in state.jobs.values()),
                "completed_jobs": sum(job.lifecycle == "COMPLETED" for job in state.jobs.values()),
                "deadline_misses": deadline_misses,
                "remaining_work_gpu_hours": sum(job.remaining_work_gpu_hours for job in state.jobs.values()),
                "spatial_actions_blocked_missing_payload": blocked_spatial,
                "checkpoint_authority": "UNAVAILABLE_NOT_MEASURED",
                "migration_payload_authority": "NULL_INPUT_BYTES_BLOCKS_MIGRATION",
                "facility_p_kw_total": sum(facility_p),
                "mess_p_kw_total": sum(fast.control.mess_discharge_kw.values()) - sum(fast.control.mess_charge_kw.values()),
                "mess_q_kvar_total": sum(fast.control.mess_q_kvar.values()),
                "minimum_mess_energy_kwh": min(state.mess_energy_kwh.values()),
                "mobility_energy_kwh": mobility_energy_kwh,
                "mess_in_transit": dict(state.mess_in_transit),
                "mess_location": dict(state.mess_location),
                "mess_route_rank": dict(state.mess_route_rank),
                "slow_miqp_certificate": dict(state.last_slow_miqp_certificate),
                "joint_uncertainty_decision_use": config.joint_uncertainty,
                "workload_reserve_gpu": dict(frame.workload_reserve_gpu) if config.joint_uncertainty else {},
                "robust_grid_fresh_opendss": bool(
                    verifier.last_commit.raw_metrics.get("robust_grid_fresh_opendss", False)
                ),
                "compute_debt_gpu_hours": state.compute_debt_gpu_hours,
                "energy_debt_kwh": state.energy_debt_kwh,
                "fast_recourse_runtime_seconds": fast.runtime_seconds,
                "safety_filter_runtime_seconds": safety.filter_runtime_seconds,
                "safety_filter_intervention": safety.intervention,
                "safety_filter_delta_p_kw": safety.delta_p_kw,
                "safety_filter_delta_q_kvar": safety.delta_q_kvar,
                "safety_filter_compute_throttling_fraction": safety.compute_throttling_fraction,
                "safety_filter_escalation_count": safety.escalation_count,
                "common_emergency_mess_override": safety.intervention and safety.delta_p_kw > 1e-12,
                "fresh_exact_opendss": True,
                "actual_gurobi_used": active_optimization.certificate.actual_gurobi_used,
                "optimization_certificate": active_optimization.certificate.as_dict(),
                "actual_fresh_opendss_used": verifier.last_commit.actual_fresh_opendss_used,
                "exact_ac": dict(verifier.last_commit.raw_metrics),
                "price_aud_per_mwh": frame.current_price_aud_per_mwh,
                "realized_grid_cost_aud": (
                    float(verifier.last_commit.raw_metrics["root_import_p_kw"])
                    * frame.current_price_aud_per_mwh * STEP_HOURS / 1000.0
                ),
                "runtime_seconds": time.monotonic() - started,
            }
            issue_root = method_root / f"issue_{frame.issue:06d}"
            issue_root.mkdir(parents=True, exist_ok=True)
            (issue_root / "COMMIT_MARKER.json").write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            records.append(record)
        summary = {
            "schema_version": "K9H7_RESULT_V2.method_run.v1",
            "status": "PASS" if failure is None and len(records) == len(frames) else "FAIL_CLOSED",
            "comparison_method_id": config.comparison_method_id.value,
            "representative_week_id": representative_week_id,
            "requested_issues": len(frames),
            "committed_issues": len(records),
            "commit_marker_count": len(records),
            "fresh_exact_opendss_count": sum(row["actual_fresh_opendss_used"] for row in records),
            "actual_gurobi_count": sum(row["actual_gurobi_used"] for row in records),
            "state_chain_complete": all(
                records[index]["post_state_sha256"] == records[index + 1]["pre_state_sha256"]
                for index in range(max(0, len(records) - 1))
            ),
            "binary_state_unchanged": all(row["binary_state_unchanged"] for row in records),
            "future_actual_used": False,
            "full_replan_count": state.full_replan_count,
            "communication_bytes": state.communication_bytes,
            "deadline_misses": sum(row["deadline_misses"] for row in records[-1:]),
            "final_compute_debt_gpu_hours": state.compute_debt_gpu_hours,
            "final_energy_debt_kwh": state.energy_debt_kwh,
            "final_minimum_mess_energy_kwh": min(state.mess_energy_kwh.values()),
            "failure": failure,
        }
        (method_root / "METHOD_SUMMARY.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if records:
            fields = tuple(records[0])
            with (method_root / "MATERIALIZED_COMMIT_ROWS.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for row in records:
                    writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list, tuple)) else value for key, value in row.items()})
        return summary

    def run_matrix(
        self,
        *,
        configs: Sequence[MethodConfig],
        frames: Sequence[CausalExperimentFrame],
        initial: RuntimeInitialState,
        representative_week_id: str,
        output: Path,
    ) -> Mapping[str, Any]:
        if tuple(config.comparison_method_id for config in configs) != tuple(ComparisonMethod):
            raise RuntimeContractError("runtime matrix must execute B0-B7 in order")
        summaries = [
            self.run_method(
                config=config,
                frames=frames,
                initial=initial,
                representative_week_id=representative_week_id,
                output=output,
            )
            for config in configs
        ]
        expected = len(frames) * 8
        committed = sum(item["committed_issues"] for item in summaries)
        matrix = {
            "schema_version": "K9H7_RESULT_V2.matrix_run.v1",
            "status": "PASS" if committed == expected and all(item["status"] == "PASS" for item in summaries) else "FAIL_CLOSED",
            "representative_week_id": representative_week_id,
            "method_count": 8,
            "issues_per_method": len(frames),
            "expected_commit_markers": expected,
            "valid_commit_markers": committed,
            "all_fresh_exact_opendss": all(item["fresh_exact_opendss_count"] == len(frames) for item in summaries),
            "all_actual_gurobi": all(item["actual_gurobi_count"] == len(frames) for item in summaries),
            "all_state_chains_complete": all(item["state_chain_complete"] for item in summaries),
            "all_binary_states_unchanged_in_fast_layer": all(item["binary_state_unchanged"] for item in summaries),
            "future_actual_used": False,
            "method_summaries": summaries,
        }
        output.mkdir(parents=True, exist_ok=True)
        (output / "MATRIX_SUMMARY.json").write_text(
            json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return matrix
