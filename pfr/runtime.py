"""PFR9+ causal B0-B7 runtime with Fresh Exact AC commit authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence, Tuple

from .electrical_stress import (
    OBJECTIVE_AUTHORITY,
    stress_from_extrema,
    trajectory_summary,
)
from .methods import (
    ComparisonMethod,
    ElectricalStressMethod,
    K9H7ResultIdentityV2,
    MAIN_COMPARISON_METHODS,
    MethodConfig,
)
from .migration import MigrationAuthority
from .mobility_execution import MobilityExecutionRealization
from .native_predictive import PREDICTIVE_NATIVE_HORIZON_STEPS
from .optimization import (
    FastControlOptimizer,
    FastOptimizationContext,
    IdentityFastControlOptimizer,
)
from .power import H100UtilizationPowerCurve
from .risk import PlanValidityRiskMonitor, ReplanCost, RiskConstraint, RiskFamily
from .risk_calibration import FrozenRiskCalibration, RISK_FAMILY_SCALES
from .result_storage import materialize_campaign_summary, materialize_method_results
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
MOBILITY_ELIGIBLE_MESS_IDS = ("MESS03",)
MESS_CANONICAL_STAGING = {
    "MESS01": "STA09",
    "MESS02": "IDC12",
    "MESS03": "STA07",
    "MESS04": "STA11",
}
STEP_HOURS = 5.0 / 60.0
MESS_CAPACITY_KWH = 1080.0
MESS_FLOOR_KWH = 440.0
MESS_PHYSICAL_MIN_KWH = 0.0
MESS_SAFETY_RESERVE_KWH = 440.0
MESS_CANONICAL_DAILY_PRE_KWH = 760.0
MESS_CHARGE_LIMIT_KW = 550.0
MESS_NOMINAL_DISCHARGE_KW = 20.0
MESS_CHARGE_EFFICIENCY = 0.95
MAXIMUM_REFRESH_STEPS = 6
MAX_MESS_TRANSIT_STEPS = 54
MAX_MESS_TRANSIT_SECONDS = MAX_MESS_TRANSIT_STEPS * 300
PLANNING_HORIZON_STEPS = 54
MODELED_GPU_CAPACITY_PER_IDC = 256
EXACT_AC_PROJECTION_MARGIN_PU = 2e-5
EXACT_AC_PROJECTION_VOLTAGE_MIN_PU = 0.95 + EXACT_AC_PROJECTION_MARGIN_PU
EXACT_AC_PROJECTION_VOLTAGE_MAX_PU = 1.05 - EXACT_AC_PROJECTION_MARGIN_PU
EXACT_AC_P_TRUST_REGION_KW = 150.0
EXACT_AC_Q_TRUST_REGION_KVAR = 210.0


class RuntimeContractError(RuntimeError):
    pass


def _fast_recourse_soc_min(energy_kwh: float) -> float:
    """Prevent control-induced worsening while preserving realized SOC violations."""
    if not math.isfinite(energy_kwh) or energy_kwh < MESS_PHYSICAL_MIN_KWH - 1e-9:
        raise RuntimeContractError("MESS energy violates physical battery bounds")
    return min(
        MESS_FLOOR_KWH / MESS_CAPACITY_KWH,
        max(MESS_PHYSICAL_MIN_KWH, energy_kwh) / MESS_CAPACITY_KWH,
    )


class MobilityExecutionAuthority(Protocol):
    """Execution environment hidden from the planning optimizer."""

    fingerprint: str

    def realize(
        self, *, issue: int, route: "MobilityRouteForecast"
    ) -> MobilityExecutionRealization:
        ...


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Durably publish JSON so a killed process cannot expose a partial artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def gurobi_thread_limit() -> int:
    try:
        value = int(os.environ.get("PFR_GUROBI_THREADS", "1"))
    except ValueError as exc:
        raise RuntimeContractError("PFR_GUROBI_THREADS must be an integer") from exc
    if not 1 <= value <= 64:
        raise RuntimeContractError("PFR_GUROBI_THREADS must be in [1, 64]")
    return value


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
    migration_payload_bytes: Optional[int] = None
    migration_authority_sha256: Optional[str] = None

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
        if self.migration_payload_bytes is not None and self.migration_payload_bytes <= 0:
            raise RuntimeContractError("authorized migration payload must be positive")
        if self.migration_payload_bytes is None:
            if self.migration_authority_sha256 is not None:
                raise RuntimeContractError("migration fingerprint lacks a payload")
        elif (
            self.migration_authority_sha256 is None
            or len(self.migration_authority_sha256) != 64
        ):
            raise RuntimeContractError("migration payload lacks authority SHA-256")

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
    native_forecast_background_p_kw: Tuple[
        Tuple[Tuple[float, ...], ...], ...
    ] = ()
    native_forecast_background_q_kvar: Tuple[
        Tuple[Tuple[float, ...], ...], ...
    ] = ()
    native_forecast_pv_available_kw: Tuple[
        Tuple[Tuple[float, ...], ...], ...
    ] = ()
    planning_forecast_background_p_kw: Tuple[
        Tuple[Tuple[float, ...], ...], ...
    ] = ()
    planning_forecast_background_q_kvar: Tuple[
        Tuple[Tuple[float, ...], ...], ...
    ] = ()
    planning_forecast_pv_available_kw: Tuple[
        Tuple[Tuple[float, ...], ...], ...
    ] = ()
    workload_reserve_gpu: Mapping[str, float] = field(default_factory=dict)
    mobility_routes: Tuple[MobilityRouteForecast, ...] = ()
    planning_mobility_npz_path: str = ""
    planning_mobility_npz_sha256: str = ""

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
        native_forecasts = (
            self.native_forecast_background_p_kw,
            self.native_forecast_background_q_kvar,
            self.native_forecast_pv_available_kw,
        )
        if any(native_forecasts):
            if not all(native_forecasts):
                raise RuntimeContractError(
                    "predictive native forecast must provide P, Q, and PV"
                )
            if any(
                len(forecast) != PREDICTIVE_NATIVE_HORIZON_STEPS
                or any(
                    len(profile) != 131
                    or any(len(row) != 3 for row in profile)
                    for profile in forecast
                )
                for forecast in native_forecasts
            ):
                raise RuntimeContractError(
                    "predictive native forecast must be 12x131x3"
                )
        planning_forecasts = (
            self.planning_forecast_background_p_kw,
            self.planning_forecast_background_q_kvar,
            self.planning_forecast_pv_available_kw,
        )
        if any(planning_forecasts):
            if not all(planning_forecasts):
                raise RuntimeContractError(
                    "H54 planning forecast must provide P, Q, and PV"
                )
            if any(
                len(forecast) != PLANNING_HORIZON_STEPS
                or any(
                    len(profile) != 131
                    or any(len(row) != 3 for row in profile)
                    for profile in forecast
                )
                for forecast in planning_forecasts
            ):
                raise RuntimeContractError(
                    "H54 planning forecast must be 54x131x3"
                )
        for route in self.mobility_routes:
            route.validate()
        if bool(self.planning_mobility_npz_path) != bool(
            self.planning_mobility_npz_sha256
        ):
            raise RuntimeContractError(
                "H54 mobility source path and SHA-256 must be provided together"
            )
        if self.planning_mobility_npz_sha256 and (
            len(self.planning_mobility_npz_sha256) != 64
            or any(
                char not in "0123456789abcdef"
                for char in self.planning_mobility_npz_sha256
            )
        ):
            raise RuntimeContractError("H54 mobility source identity must be SHA-256")

    def routes_for(self, source: str, destination: str) -> Tuple[MobilityRouteForecast, ...]:
        return tuple(
            route
            for route in self.mobility_routes
            if route.source_service_id == source and route.destination_service_id == destination
        )


class H54JointPlanner(Protocol):
    """Adapter boundary to the retained 54-step joint MIQCP formulation."""

    def solve(
        self,
        *,
        state: "MutableMethodState",
        config: MethodConfig,
        frame: CausalExperimentFrame,
        migration_authority: Optional[MigrationAuthority],
        evaluation_steps_remaining: int,
    ) -> tuple[SlowDiscretePlan, Mapping[str, Any]]:
        ...


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
    migration_state: str = "NOT_EVALUATED_METHOD_CAPABILITY"
    steps_since_checkpoint: int = 0
    migration_source_idc: Optional[str] = None
    migration_destination_idc: Optional[str] = None
    migration_payload_remaining_bytes: int = 0
    restart_remaining_steps: int = 0
    migration_work_gpu_hours_at_start: Optional[float] = None
    migration_start_issue: Optional[int] = None
    migration_predicted_transfer_steps: Optional[int] = None
    migration_predicted_restart_steps: Optional[int] = None
    migration_transfer_complete_issue: Optional[int] = None
    migration_actual_transfer_steps: Optional[int] = None
    queue_wait_steps: int = 0
    prestart_wan_target_idc: Optional[str] = None
    prestart_wan_required_bytes: int = 0
    prestart_wan_transferred_bytes: int = 0


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
    admission_plan_revision_count: int = 0
    admission_communication_bytes: int = 0
    scheduler_started_jobs_cumulative: int = 0
    capacity_queue_wait_job_steps_cumulative: int = 0
    planned_temporal_wait_job_steps_cumulative: int = 0
    wan_transferred_bytes_cumulative: int = 0
    wan_active_transfers: int = 0
    migration_count_cumulative: int = 0
    compute_debt_gpu_hours: float = 0.0
    energy_debt_kwh: float = 0.0
    mess_energy_debt_kwh: dict[str, float] = field(
        default_factory=lambda: {mid: 0.0 for mid in MESS_IDS}
    )
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
    last_spatial_optimizer_certificate: Mapping[str, Any] = field(default_factory=dict)
    native_capacitor_states: dict[str, Tuple[int, ...]] = field(default_factory=dict)
    native_capacitor_dwell_remaining_steps: dict[str, int] = field(
        default_factory=dict
    )
    native_capacitor_switch_count: dict[str, int] = field(default_factory=dict)
    native_regulator_tap_numbers: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class PhysicalCommit:
    exact: ExactAcResult
    raw_metrics: Mapping[str, Any]
    actual_gurobi_used: bool
    actual_fresh_opendss_used: bool


@dataclass(frozen=True)
class NativeGridControlDecision:
    states: Mapping[str, Tuple[int, ...]]
    raw_metrics: Mapping[str, Any]
    fresh_instance: bool
    common_to_all_methods: bool
    regulator_taps: Mapping[str, int] = field(default_factory=dict)
    pv_q_fraction_by_phase: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    def validate(self) -> None:
        if not self.fresh_instance or not self.common_to_all_methods:
            raise RuntimeContractError(
                "native grid-control decision must be Fresh and common to B0-B7"
            )
        if any(
            not name or not values or any(value not in (0, 1) for value in values)
            for name, values in self.states.items()
        ):
            raise RuntimeContractError("native capacitor state decision is invalid")
        if any(
            not name or not -16 <= int(tap) <= 16
            for name, tap in self.regulator_taps.items()
        ):
            raise RuntimeContractError("native regulator tap decision is invalid")
        if (
            len(self.pv_q_fraction_by_phase) != 3
            or any(
                not math.isfinite(float(value)) or abs(float(value)) > 1.0 + 1e-9
                for value in self.pv_q_fraction_by_phase
            )
        ):
            raise RuntimeContractError("common PV inverter Q fraction is invalid")


class FreshPhysicalBackend(Protocol):
    def select_native_control(
        self,
        *,
        issue: int,
        facility_p_kw: Sequence[float],
        facility_q_kvar: Sequence[float],
        mess_location: Sequence[str],
        mess_p_kw: Sequence[float],
        mess_q_kvar: Sequence[float],
        mess_in_transit: Sequence[bool],
        previous_capacitor_states: Mapping[str, Sequence[int]],
        previous_regulator_taps: Mapping[str, int],
        locked_capacitors: Sequence[str],
        native_forecast_background_p_kw: Sequence[
            Sequence[Sequence[float]]
        ] = (),
        native_forecast_background_q_kvar: Sequence[
            Sequence[Sequence[float]]
        ] = (),
        native_forecast_pv_available_kw: Sequence[
            Sequence[Sequence[float]]
        ] = (),
    ) -> NativeGridControlDecision:
        ...

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
        native_capacitor_states: Optional[Mapping[str, Sequence[int]]] = None,
        native_regulator_taps: Optional[Mapping[str, int]] = None,
        pv_q_fraction_by_phase: Sequence[float] = (0.0, 0.0, 0.0),
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
        native_forecast_background_p_kw: Sequence[
            Sequence[Sequence[float]]
        ],
        native_forecast_background_q_kvar: Sequence[
            Sequence[Sequence[float]]
        ],
        native_forecast_pv_available_kw: Sequence[
            Sequence[Sequence[float]]
        ],
        previous_capacitor_states: Optional[
            Mapping[str, Sequence[int]]
        ] = None,
        previous_regulator_taps: Optional[Mapping[str, int]] = None,
        locked_capacitors: Sequence[str] = (),
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
        self.native_forecast_background_p_kw = tuple(
            tuple(tuple(row) for row in profile)
            for profile in native_forecast_background_p_kw
        )
        self.native_forecast_background_q_kvar = tuple(
            tuple(tuple(row) for row in profile)
            for profile in native_forecast_background_q_kvar
        )
        self.native_forecast_pv_available_kw = tuple(
            tuple(tuple(row) for row in profile)
            for profile in native_forecast_pv_available_kw
        )
        self.previous_capacitor_states = {
            str(name).lower(): tuple(int(value) for value in values)
            for name, values in (previous_capacitor_states or {}).items()
        }
        self.locked_capacitors = tuple(str(name).lower() for name in locked_capacitors)
        self.previous_regulator_taps = {
            str(name).lower(): int(value)
            for name, value in (previous_regulator_taps or {}).items()
        }
        self.native_decision: Optional[NativeGridControlDecision] = None
        self.last_commit: Optional[PhysicalCommit] = None
        self.opendss_runtime_seconds = 0.0

    def _physical_inputs(self, control: FastControl) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
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
        return tuple(facility_p[site] for site in IDCS), mess_p, mess_q

    def select_native_control(self, *, control: FastControl) -> NativeGridControlDecision:
        facility_p, mess_p, mess_q = self._physical_inputs(control)
        selector = getattr(self.backend, "select_native_control", None)
        if selector is None:
            decision = NativeGridControlDecision(
                states=dict(self.previous_capacitor_states),
                raw_metrics={
                    "status": "LEGACY_BACKEND_NO_NATIVE_CONTROL_SELECTOR",
                    "native_grid_control_authority": "NONE",
                },
                fresh_instance=True,
                common_to_all_methods=True,
            )
        else:
            decision = selector(
                issue=self.issue,
                facility_p_kw=facility_p,
                facility_q_kvar=(0.0,) * len(IDCS),
                mess_location=self.mess_location,
                mess_p_kw=mess_p,
                mess_q_kvar=mess_q,
                mess_in_transit=self.mess_in_transit,
                previous_capacitor_states=self.previous_capacitor_states,
                previous_regulator_taps=self.previous_regulator_taps,
                locked_capacitors=self.locked_capacitors,
                native_forecast_background_p_kw=(
                    self.native_forecast_background_p_kw
                ),
                native_forecast_background_q_kvar=(
                    self.native_forecast_background_q_kvar
                ),
                native_forecast_pv_available_kw=(
                    self.native_forecast_pv_available_kw
                ),
            )
        decision.validate()
        self.native_decision = decision
        return decision

    def select_native_control_deep(
        self, *, control: FastControl
    ) -> NativeGridControlDecision:
        facility_p, mess_p, mess_q = self._physical_inputs(control)
        selector = getattr(self.backend, "select_native_control_deep", None)
        if selector is None:
            return self.select_native_control(control=control)
        decision = selector(
            issue=self.issue,
            facility_p_kw=facility_p,
            facility_q_kvar=(0.0,) * len(IDCS),
            mess_location=self.mess_location,
            mess_p_kw=mess_p,
            mess_q_kvar=mess_q,
            mess_in_transit=self.mess_in_transit,
            previous_capacitor_states=self.previous_capacitor_states,
            previous_regulator_taps=self.previous_regulator_taps,
            locked_capacitors=self.locked_capacitors,
            native_forecast_background_p_kw=(
                self.native_forecast_background_p_kw
            ),
            native_forecast_background_q_kvar=(
                self.native_forecast_background_q_kvar
            ),
            native_forecast_pv_available_kw=(
                self.native_forecast_pv_available_kw
            ),
        )
        decision.validate()
        self.native_decision = decision
        return decision

    def verify_fresh(self, *, control: FastControl, **_: Any) -> ExactAcResult:
        facility_p, mess_p, mess_q = self._physical_inputs(control)
        if self.native_decision is None:
            self.select_native_control(control=control)
        started = time.monotonic()
        try:
            self.last_commit = self.backend.verify_fresh(
                issue=self.issue,
                facility_p_kw=facility_p,
                facility_q_kvar=(0.0,) * len(IDCS),
                mess_location=self.mess_location,
                mess_p_kw=mess_p,
                mess_q_kvar=mess_q,
                mess_in_transit=self.mess_in_transit,
                robust_background_p_kw=self.robust_background_p_kw,
                robust_background_q_kvar=self.robust_background_q_kvar,
                robust_pv_available_kw=self.robust_pv_available_kw,
                native_capacitor_states=self.native_decision.states,
                native_regulator_taps=self.native_decision.regulator_taps,
                pv_q_fraction_by_phase=self.native_decision.pv_q_fraction_by_phase,
            )
        finally:
            self.opendss_runtime_seconds += time.monotonic() - started
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
    """Sequential exact-verified projection over a Fresh-AC local envelope.

    The internal voltage margin is only a numerical landing margin.  Earlier
    revisions used a fixed 5e-4-pu engineering margin, which changed the
    feasible set enough to make the projection QPs infeasible at simultaneous
    voltage/thermal boundaries even when the unchanged exact limits still had
    room.  Every accepted action is checked against the original 0.95/1.05
    limits by a fresh OpenDSS instance, so a small solver-scale landing margin
    is sufficient and does not relax physical acceptance.
    """

    def __init__(
        self,
        verifier: _PhysicalVerifierAdapter,
        *,
        allow_mess: bool,
        allow_compute: bool = True,
        compute_site_capacity: Optional[Mapping[str, float]] = None,
    ) -> None:
        self.verifier = verifier
        self.allow_mess = allow_mess
        self.allow_compute = allow_compute
        self.compute_site_capacity = {
            site: float(
                (compute_site_capacity or {}).get(
                    site, MODELED_GPU_CAPACITY_PER_IDC
                )
            )
            for site in IDCS
        }
        if any(value < 0.0 for value in self.compute_site_capacity.values()):
            raise RuntimeContractError("compute site capacity cannot be negative")
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
        # Normalize unlike residuals before comparing successive Fresh-AC
        # iterates.  A 0.05-pu voltage band and a 1.0-pu thermal rating are the
        # physical scales of the four unchanged hard constraints.  This score
        # is a feasibility-restoration merit function only; it is never an
        # acceptance rule.
        violations = (
            max(0.0, 0.95 - exact.minimum_voltage_pu) / 0.05,
            max(0.0, exact.maximum_voltage_pu - 1.05) / 0.05,
            max(0.0, exact.maximum_line_loading_fraction - 1.0),
            max(0.0, exact.maximum_transformer_loading_fraction - 1.0),
        )
        root_sign_penalty = 10.0 if "ROOT_SIGN" in exact.status else 0.0
        return root_sign_penalty + sum(value * value for value in violations)

    @staticmethod
    def _electrical_stress_score(exact: ExactAcResult) -> float:
        return stress_from_extrema(
            minimum_voltage_pu=exact.minimum_voltage_pu,
            maximum_voltage_pu=exact.maximum_voltage_pu,
            maximum_line_loading_fraction=exact.maximum_line_loading_fraction,
            maximum_transformer_loading_fraction=(
                exact.maximum_transformer_loading_fraction
            ),
        ).worst

    def _maximum_compute_rates(
        self, control: FastControl, state: FastLayerState
    ) -> dict[str, float]:
        """Increase flexible compute without changing placement or hard ratings.

        Additional local demand is a legitimate over-voltage actuator for methods
        that own temporal workload flexibility.  The construction preserves job
        work, the 256-GPU site limit, and the unchanged 750-kVA facility rating.
        """
        rates = {
            job_id: float(value)
            for job_id, value in control.job_compute_rate_fraction.items()
        }
        if not self.allow_compute:
            return rates

        def site_gpu(site: str) -> float:
            return sum(
                self.verifier.jobs[job_id].source.requested_gpu * rates[job_id]
                for job_id in rates
                if self.verifier.jobs[job_id].destination_idc == site
            )

        def site_power(site: str) -> float:
            total = 0.0
            for job_id, fraction in rates.items():
                job = self.verifier.jobs[job_id]
                if (
                    job.lifecycle == "COMPLETED"
                    or job.destination_idc != site
                    or fraction <= 0.0
                ):
                    continue
                total += (
                    self.verifier.power_curve.gang_power_kw(
                        job.source.requested_gpu, fraction
                    )
                    + job.source.cpu_request_share_kw
                )
            return total

        for job_id in sorted(
            rates,
            key=lambda uid: (
                self.verifier.jobs[uid].source.deadline_step,
                uid,
            ),
        ):
            job = self.verifier.jobs[job_id]
            gpu = job.source.requested_gpu
            upper = min(
                1.0,
                float(state.remaining_work_gpu_hours[job_id])
                / (gpu * STEP_HOURS),
            )
            lower = min(max(rates[job_id], 0.0), upper)
            rates[job_id] = lower
            site = job.destination_idc
            gpu_headroom = max(0.0, self.compute_site_capacity[site] - site_gpu(site))
            upper = min(upper, lower + gpu_headroom / gpu)
            if upper <= lower + 1e-12:
                continue
            # The power curve need not be treated as linear.  Use a deterministic
            # monotone bisection against the unchanged transformer rating.
            trial_low, trial_high = lower, upper
            rates[job_id] = trial_high
            if site_power(site) <= 750.0 + 1e-9:
                continue
            rates[job_id] = trial_low
            for _ in range(48):
                trial = 0.5 * (trial_low + trial_high)
                rates[job_id] = trial
                if site_power(site) <= 750.0 + 1e-9:
                    trial_low = trial
                else:
                    trial_high = trial
            rates[job_id] = trial_low
        return rates

    def _targets(
        self, control: FastControl, state: FastLayerState, exact: ExactAcResult
    ) -> tuple[FastControl, FastControl]:
        active_compute = {
            key: (0.0 if self.allow_compute else float(value))
            for key, value in control.job_compute_rate_fraction.items()
        }
        active_charge, active_discharge, active_q = {}, {}, {}
        voltage_charge = dict(control.mess_charge_kw)
        voltage_discharge = dict(control.mess_discharge_kw)
        voltage_q = {}
        voltage_compute = dict(control.job_compute_rate_fraction)
        if self.allow_compute and exact.maximum_voltage_pu > 1.05:
            voltage_compute = self._maximum_compute_rates(control, state)
        elif self.allow_compute and exact.minimum_voltage_pu < 0.95:
            voltage_compute = dict(active_compute)
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
                    voltage_charge[mess_id] = min(550.0, max_charge)
                    voltage_discharge[mess_id] = 0.0
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
            voltage_compute, dict(control.site_throughput_fraction),
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
        model.Params.Threads = gurobi_thread_limit()
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
        model.addConstr(
            expressions["vmin"] >= EXACT_AC_PROJECTION_VOLTAGE_MIN_PU,
            name="minimum_voltage",
        )
        model.addConstr(
            expressions["vmax"] <= EXACT_AC_PROJECTION_VOLTAGE_MAX_PU,
            name="maximum_voltage",
        )
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
        model.Params.Threads = gurobi_thread_limit()
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
        model.addConstr(
            expressions["vmin"] >= EXACT_AC_PROJECTION_VOLTAGE_MIN_PU,
            name="minimum_voltage",
        )
        model.addConstr(
            expressions["vmax"] <= EXACT_AC_PROJECTION_VOLTAGE_MAX_PU,
            name="maximum_voltage",
        )
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

    def _joint_pq_sensitivity_step(
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
            raise RuntimeContractError(
                "gurobipy is required by the joint AC P/Q sensitivity QCP"
            ) from exc

        metric_names = ("vmin", "vmax", "line", "transformer")
        base_metrics = {
            "vmin": exact.minimum_voltage_pu,
            "vmax": exact.maximum_voltage_pu,
            "line": exact.maximum_line_loading_fraction,
            "transformer": exact.maximum_transformer_loading_fraction,
        }
        bounds = {}
        derivatives_p = {name: {} for name in metric_names}
        derivatives_q = {name: {} for name in metric_names}
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
                MESS_CHARGE_LIMIT_KW,
                max(
                    0.0,
                    (MESS_CAPACITY_KWH - energy)
                    / (MESS_CHARGE_EFFICIENCY * STEP_HOURS),
                ),
            )
            max_discharge = min(
                MESS_CHARGE_LIMIT_KW,
                max(
                    0.0,
                    (energy - MESS_FLOOR_KWH)
                    * MESS_CHARGE_EFFICIENCY
                    / STEP_HOURS,
                ),
            )
            q_cap = math.sqrt(max(0.0, 700.0**2 - current_p**2))
            lower_p, upper_p = -max_charge, max_discharge
            lower_q, upper_q = -q_cap, q_cap
            bounds[mess_id] = (
                max(lower_p - current_p, -EXACT_AC_P_TRUST_REGION_KW),
                min(upper_p - current_p, EXACT_AC_P_TRUST_REGION_KW),
                max(lower_q - current_q, -EXACT_AC_Q_TRUST_REGION_KVAR),
                min(upper_q - current_q, EXACT_AC_Q_TRUST_REGION_KVAR),
                current_p,
                current_q,
            )
            for axis, negative_delta, positive_delta, derivatives in (
                (
                    "p",
                    max(lower_p - current_p, -50.0),
                    min(upper_p - current_p, 50.0),
                    derivatives_p,
                ),
                (
                    "q",
                    max(lower_q - current_q, -70.0),
                    min(upper_q - current_q, 70.0),
                    derivatives_q,
                ),
            ):
                if positive_delta - negative_delta <= 1e-6:
                    continue
                probe_metrics = []
                for delta in (negative_delta, positive_delta):
                    candidate_p = current_p + (delta if axis == "p" else 0.0)
                    candidate_q = current_q + (delta if axis == "q" else 0.0)
                    candidate_q_cap = math.sqrt(
                        max(0.0, 700.0**2 - candidate_p**2)
                    )
                    candidate_q = min(
                        candidate_q_cap, max(-candidate_q_cap, candidate_q)
                    )
                    candidate = FastControl(
                        {
                            **control.mess_charge_kw,
                            mess_id: max(0.0, -candidate_p),
                        },
                        {
                            **control.mess_discharge_kw,
                            mess_id: max(0.0, candidate_p),
                        },
                        {**control.mess_q_kvar, mess_id: candidate_q},
                        dict(control.job_compute_rate_fraction),
                        dict(control.site_throughput_fraction),
                    )
                    candidate_exact = self.verifier.verify_fresh(
                        control=candidate, state=state, slow_plan=slow_plan
                    )
                    candidate_exact.validate()
                    probe_metrics.append({
                        "vmin": candidate_exact.minimum_voltage_pu,
                        "vmax": candidate_exact.maximum_voltage_pu,
                        "line": candidate_exact.maximum_line_loading_fraction,
                        "transformer": candidate_exact.maximum_transformer_loading_fraction,
                    })
                denominator = positive_delta - negative_delta
                for name in metric_names:
                    derivatives[name][mess_id] = (
                        probe_metrics[1][name] - probe_metrics[0][name]
                    ) / denominator
        if not bounds:
            return None

        model = gp.Model("pfr_exact_ac_joint_pq_sensitivity")
        model.Params.OutputFlag = 0
        model.Params.Threads = gurobi_thread_limit()
        model.Params.Seed = 0
        delta_p = {
            mess_id: model.addVar(
                lb=value[0], ub=value[1], name=f"delta_p[{mess_id}]"
            )
            for mess_id, value in bounds.items()
        }
        delta_q = {
            mess_id: model.addVar(
                lb=value[2], ub=value[3], name=f"delta_q[{mess_id}]"
            )
            for mess_id, value in bounds.items()
        }
        for mess_id, value in bounds.items():
            current_p, current_q = value[4], value[5]
            model.addQConstr(
                (current_p + delta_p[mess_id])
                * (current_p + delta_p[mess_id])
                + (current_q + delta_q[mess_id])
                * (current_q + delta_q[mess_id])
                <= 700.0**2,
                name=f"pcs_circle[{mess_id}]",
            )
        expressions = {
            name: base_metrics[name]
            + gp.quicksum(
                derivatives_p[name].get(mess_id, 0.0) * delta_p[mess_id]
                + derivatives_q[name].get(mess_id, 0.0) * delta_q[mess_id]
                for mess_id in bounds
            )
            for name in metric_names
        }
        # A trust-region subproblem must remain solvable when the current
        # operating point is farther than one trust radius from feasibility.
        # Requiring every linearized hard limit in one step made the sequential
        # method return INFEASIBLE before it could take an improving step.  The
        # elastic residuals below form a convex feasibility-restoration QCP.
        # They do not relax Fresh-AC acceptance: an iterate is committed only
        # after the original 0.95/1.05/1.0 checks pass.
        residual = {
            name: model.addVar(lb=0.0, name=f"elastic_residual[{name}]")
            for name in metric_names
        }
        model.addConstr(
            expressions["vmin"] + residual["vmin"]
            >= EXACT_AC_PROJECTION_VOLTAGE_MIN_PU,
            name="minimum_voltage_elastic",
        )
        model.addConstr(
            expressions["vmax"] - residual["vmax"]
            <= EXACT_AC_PROJECTION_VOLTAGE_MAX_PU,
            name="maximum_voltage_elastic",
        )
        model.addConstr(
            expressions["line"] - residual["line"] <= 1.0,
            name="line_loading_elastic",
        )
        model.addConstr(
            expressions["transformer"] - residual["transformer"] <= 1.0,
            name="transformer_loading_elastic",
        )
        normalized_residual = (
            (residual["vmin"] / 0.05) * (residual["vmin"] / 0.05)
            + (residual["vmax"] / 0.05) * (residual["vmax"] / 0.05)
            + residual["line"] * residual["line"]
            + residual["transformer"] * residual["transformer"]
        )
        normalized_movement = gp.quicksum(
            (delta_p[mess_id] / 550.0) * (delta_p[mess_id] / 550.0)
            + (delta_q[mess_id] / 700.0) * (delta_q[mess_id] / 700.0)
            for mess_id in bounds
        )
        predicted_stress = model.addVar(
            lb=0.0, name="predicted_worst_electrical_stress"
        )
        model.addConstr(
            1.0 - expressions["vmin"] <= 0.05 * predicted_stress,
            name="predicted_voltage_low_stress",
        )
        model.addConstr(
            expressions["vmax"] - 1.0 <= 0.05 * predicted_stress,
            name="predicted_voltage_high_stress",
        )
        model.addConstr(
            expressions["line"] <= predicted_stress,
            name="predicted_line_stress",
        )
        model.addConstr(
            expressions["transformer"] <= predicted_stress,
            name="predicted_transformer_stress",
        )
        # Gurobi multi-objective objectives must be linear, while restoration
        # and movement are quadratic.  Implement the exact hierarchy as three
        # sequential convex solves with optimum-locking constraints.
        def _solve_stage(objective: object) -> bool:
            model.setObjective(objective, GRB.MINIMIZE)
            model.optimize()
            return bool(
                model.Status in {GRB.OPTIMAL, GRB.SUBOPTIMAL}
                and model.SolCount >= 1
                and float(model.MaxVio) <= 1e-6
            )

        if not _solve_stage(normalized_residual):
            model.dispose()
            return None
        optimum_residual = float(normalized_residual.getValue())
        model.addQConstr(
            normalized_residual <= optimum_residual + 1e-10,
            name="lock_feasibility_restoration_optimum",
        )
        if not _solve_stage(predicted_stress):
            model.dispose()
            return None
        optimum_predicted_stress = float(predicted_stress.X)
        model.addConstr(
            predicted_stress <= optimum_predicted_stress + 1e-6,
            name="lock_electrical_stress_optimum",
        )
        if not _solve_stage(normalized_movement):
            model.dispose()
            return None
        solution = {
            mess_id: (float(delta_p[mess_id].X), float(delta_q[mess_id].X))
            for mess_id in bounds
        }
        predicted_residual = {
            name: float(residual[name].X) for name in metric_names
        }
        model.dispose()

        base_score = self._violation_score(exact)
        candidates = []
        for scale in (0.25, 0.5, 0.75, 1.0, 1.05, 1.25):
            charge = dict(control.mess_charge_kw)
            discharge = dict(control.mess_discharge_kw)
            reactive = dict(control.mess_q_kvar)
            for mess_id, (p_delta, q_delta) in solution.items():
                value = bounds[mess_id]
                candidate_p = value[4] + min(
                    value[1], max(value[0], scale * p_delta)
                )
                candidate_q = value[5] + min(
                    value[3], max(value[2], scale * q_delta)
                )
                q_cap = math.sqrt(max(0.0, 700.0**2 - candidate_p**2))
                charge[mess_id] = max(0.0, -candidate_p)
                discharge[mess_id] = max(0.0, candidate_p)
                reactive[mess_id] = min(q_cap, max(-q_cap, candidate_q))
            candidate = FastControl(
                charge,
                discharge,
                reactive,
                dict(control.job_compute_rate_fraction),
                dict(control.site_throughput_fraction),
            )
            candidate_exact = self.verifier.verify_fresh(
                control=candidate, state=state, slow_plan=slow_plan
            )
            candidate_exact.validate()
            candidates.append((candidate, candidate_exact, scale))

        passing = [item for item in candidates if item[1].passed]
        admissible = passing or [
            item
            for item in candidates
            if self._violation_score(item[1]) < base_score - 1e-12
        ]
        if not admissible:
            return None
        selected = min(
            admissible,
            key=(
                (lambda item: (
                    self._electrical_stress_score(item[1]),
                    self._objective_distance(control, item[0]),
                ))
                if passing
                else (lambda item: self._violation_score(item[1]))
            ),
        )
        candidate, candidate_exact, scale = selected
        return candidate, candidate_exact, {
            "status": "FRESH_OPENDSS_ELASTIC_JOINT_PQ_TRUST_REGION_QCP",
            "scale": scale,
            "passed": candidate_exact.passed,
            "predicted_elastic_residual": predicted_residual,
            "predicted_electrical_stress_optimum": optimum_predicted_stress,
            "fresh_exact_violation_score_before": base_score,
            "fresh_exact_violation_score_after": self._violation_score(candidate_exact),
            "fresh_exact_electrical_stress_before": self._electrical_stress_score(exact),
            "fresh_exact_electrical_stress_after": self._electrical_stress_score(candidate_exact),
            "continuous_variables": 2 * len(solution),
            "elastic_variables": len(predicted_residual),
            "integer_variables": 0,
        }

    def _pairwise_q_step(
        self,
        control: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
        exact: ExactAcResult,
        preferred_pair: Optional[tuple[str, str]] = None,
    ) -> Optional[tuple[FastControl, ExactAcResult, Mapping[str, Any]]]:
        if not self.allow_mess:
            return None
        base_score = self._violation_score(exact)
        connected = [
            mess_id
            for mess_index, mess_id in enumerate(MESS_IDS)
            if not self.verifier.mess_in_transit[mess_index]
        ]
        all_pairs = [
            (left_id, right_id)
            for left_index, left_id in enumerate(connected)
            for right_id in connected[left_index + 1:]
        ]
        pairs = (
            [preferred_pair]
            if preferred_pair is not None and preferred_pair in all_pairs
            else all_pairs
        )
        def preserves_satisfied_constraints(candidate_exact: ExactAcResult) -> bool:
            return (
                (exact.minimum_voltage_pu < 0.95 or candidate_exact.minimum_voltage_pu >= 0.95)
                and (exact.maximum_voltage_pu > 1.05 or candidate_exact.maximum_voltage_pu <= 1.05)
                and (exact.maximum_line_loading_fraction > 1.0 or candidate_exact.maximum_line_loading_fraction <= 1.0)
                and (exact.maximum_transformer_loading_fraction > 1.0 or candidate_exact.maximum_transformer_loading_fraction <= 1.0)
                and ("ROOT_SIGN" in exact.status or "ROOT_SIGN" not in candidate_exact.status)
            )

        fraction_batches = (
            ((0.1, 0.1), (0.25, 0.25), (0.5, 0.5), (1.0, 1.0)),
            (
                (0.0125, 0.0125),
                (0.0125, 0.025),
                (0.025, 0.0125),
                (0.025, 0.025),
                (0.025, 0.05),
                (0.05, 0.025),
                (0.05, 0.05),
                (0.05, 0.1),
                (0.1, 0.05),
                (0.1, 0.25),
                (0.25, 0.1),
            ),
        )
        for batch_index, fraction_pairs in enumerate(fraction_batches):
            probes = []
            for left_id, right_id in pairs:
                for left_direction in (-1.0, 1.0):
                    for right_direction in (-1.0, 1.0):
                        for left_fraction, right_fraction in fraction_pairs:
                            q = dict(control.mess_q_kvar)
                            for mess_id, direction, fraction in (
                                (left_id, left_direction, left_fraction),
                                (right_id, right_direction, right_fraction),
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
                                    left_fraction,
                                    right_fraction,
                                )
                            )

            passing = [item for item in probes if item[1].passed]
            admissible = passing or [
                item
                for item in probes
                if preserves_satisfied_constraints(item[1])
                and self._violation_score(item[1]) < base_score - 1e-12
            ]
            if not admissible:
                continue
            selected = min(
                admissible,
                key=(
                    (lambda item: self._objective_distance(control, item[0]))
                    if passing
                    else (lambda item: self._violation_score(item[1]))
                ),
            )
            (
                candidate,
                candidate_exact,
                left_id,
                right_id,
                left_direction,
                right_direction,
                left_fraction,
                right_fraction,
            ) = selected
            return candidate, candidate_exact, {
                "status": "FRESH_OPENDSS_PAIRWISE_Q_SEARCH",
                "search_resolution": "COARSE" if batch_index == 0 else "FINE_ASYMMETRIC",
                "mess_ids": [left_id, right_id],
                "directions": [left_direction, right_direction],
                "fractions": [left_fraction, right_fraction],
                "passed": candidate_exact.passed,
            }
        return None

    def _pairwise_p_step(
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
        bounds = {}
        for mess_id in connected:
            current_p = (
                float(control.mess_discharge_kw[mess_id])
                - float(control.mess_charge_kw[mess_id])
            )
            current_q = float(control.mess_q_kvar[mess_id])
            energy = float(state.mess_soc[mess_id]) * MESS_CAPACITY_KWH
            max_charge = min(
                550.0,
                max(
                    0.0,
                    (MESS_CAPACITY_KWH - energy)
                    / (MESS_CHARGE_EFFICIENCY * STEP_HOURS),
                ),
            )
            max_discharge = min(
                550.0,
                max(
                    0.0,
                    (energy - MESS_FLOOR_KWH)
                    * MESS_CHARGE_EFFICIENCY
                    / STEP_HOURS,
                ),
            )
            apparent_p_cap = math.sqrt(max(0.0, 700.0**2 - current_q**2))
            bounds[mess_id] = (
                current_p,
                max(-max_charge, -apparent_p_cap),
                min(max_discharge, apparent_p_cap),
            )

        pairs = [
            (left_id, right_id)
            for left_index, left_id in enumerate(connected)
            for right_id in connected[left_index + 1:]
        ]

        def preserves_satisfied_constraints(candidate_exact: ExactAcResult) -> bool:
            return (
                (exact.minimum_voltage_pu < 0.95 or candidate_exact.minimum_voltage_pu >= 0.95)
                and (exact.maximum_voltage_pu > 1.05 or candidate_exact.maximum_voltage_pu <= 1.05)
                and (exact.maximum_line_loading_fraction > 1.0 or candidate_exact.maximum_line_loading_fraction <= 1.0)
                and (exact.maximum_transformer_loading_fraction > 1.0 or candidate_exact.maximum_transformer_loading_fraction <= 1.0)
                and ("ROOT_SIGN" in exact.status or "ROOT_SIGN" not in candidate_exact.status)
            )

        fraction_batches = (
            ((0.1, 0.1), (0.25, 0.25), (0.5, 0.5), (1.0, 1.0)),
            (
                (0.025, 0.025),
                (0.025, 0.05),
                (0.05, 0.025),
                (0.05, 0.05),
                (0.05, 0.1),
                (0.1, 0.05),
                (0.1, 0.25),
                (0.25, 0.1),
            ),
        )
        for batch_index, fraction_pairs in enumerate(fraction_batches):
            probes = []
            for left_id, right_id in pairs:
                for left_direction in (-1.0, 1.0):
                    for right_direction in (-1.0, 1.0):
                        for left_fraction, right_fraction in fraction_pairs:
                            charge = dict(control.mess_charge_kw)
                            discharge = dict(control.mess_discharge_kw)
                            for mess_id, direction, fraction in (
                                (left_id, left_direction, left_fraction),
                                (right_id, right_direction, right_fraction),
                            ):
                                current_p, lower_p, upper_p = bounds[mess_id]
                                target_p = lower_p if direction < 0.0 else upper_p
                                candidate_p = current_p + fraction * (
                                    target_p - current_p
                                )
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
                            probes.append(
                                (
                                    candidate,
                                    candidate_exact,
                                    left_id,
                                    right_id,
                                    left_direction,
                                    right_direction,
                                    left_fraction,
                                    right_fraction,
                                )
                            )

            passing = [item for item in probes if item[1].passed]
            admissible = passing or [
                item
                for item in probes
                if preserves_satisfied_constraints(item[1])
                and self._violation_score(item[1]) < base_score - 1e-12
            ]
            if not admissible:
                continue
            selected = min(
                admissible,
                key=(
                    (lambda item: self._objective_distance(control, item[0]))
                    if passing
                    else (lambda item: self._violation_score(item[1]))
                ),
            )
            (
                candidate,
                candidate_exact,
                left_id,
                right_id,
                left_direction,
                right_direction,
                left_fraction,
                right_fraction,
            ) = selected
            return candidate, candidate_exact, {
                "status": "FRESH_OPENDSS_PAIRWISE_P_SEARCH",
                "search_resolution": "COARSE" if batch_index == 0 else "FINE_ASYMMETRIC",
                "mess_ids": [left_id, right_id],
                "directions": [left_direction, right_direction],
                "fractions": [left_fraction, right_fraction],
                "passed": candidate_exact.passed,
            }
        return None

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
            fleet = self._fleet_q_step(
                active_candidate, state, slow_plan, active_exact
            )
            if fleet is not None and fleet[1].passed:
                candidate, candidate_exact, fleet_trace = fleet
                passing.append(
                    (candidate, candidate_exact, active_fraction, fleet_trace)
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
        initial_exact = exact
        for _ in range(24):
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
            # Use the joint continuous P/Q projection first for every AC
            # violation.  It relinearizes from Fresh exact finite differences
            # after each accepted step.  Earlier releases tried coordinate,
            # pairwise and fleet grids before this model; the archived January
            # traces show those greedy steps converging to opposite voltage and
            # line boundaries without finding their narrow feasible
            # intersection.
            formal_steps = (
                (
                    "joint_pq_trust_region_qcp",
                    self._joint_pq_sensitivity_step,
                ),
                ("q_projection_qp", self._sensitivity_qp_step),
                ("p_projection_qp", self._active_sensitivity_qp_step),
            )
            formal_step = None
            for label, builder in formal_steps:
                result = builder(current, state, slow_plan, exact)
                if result is not None:
                    formal_step = (label, *result)
                    break
            if formal_step is not None:
                label, current, exact, formal_trace = formal_step
                trace_row[label] = formal_trace
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
            try:
                import gurobipy as gp
                from gurobipy import GRB
            except ImportError as exc:
                raise RuntimeContractError("gurobipy is required by the AC safety projector") from exc
            model = gp.Model("pfr_ac_safety_projection")
            model.Params.OutputFlag = 0
            model.Params.Threads = gurobi_thread_limit()
            model.Params.Seed = 0
            z_active = model.addVar(lb=0.0, ub=1.0 if active_distance > 1e-18 else 0.0, name="active_relief_fraction")
            z_voltage = model.addVar(lb=0.0, ub=1.0 if voltage_distance > 1e-18 else 0.0, name="voltage_support_fraction")
            metrics = (
                (
                    exact.minimum_voltage_pu,
                    active_probe_exact.minimum_voltage_pu,
                    voltage_probe_exact.minimum_voltage_pu,
                    GRB.GREATER_EQUAL,
                    EXACT_AC_PROJECTION_VOLTAGE_MIN_PU,
                ),
                (
                    exact.maximum_voltage_pu,
                    active_probe_exact.maximum_voltage_pu,
                    voltage_probe_exact.maximum_voltage_pu,
                    GRB.LESS_EQUAL,
                    EXACT_AC_PROJECTION_VOLTAGE_MAX_PU,
                ),
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
        if not self.allow_mess and any(
            candidate != nominal_map
            for candidate, nominal_map in (
                (current.mess_charge_kw, nominal.mess_charge_kw),
                (current.mess_discharge_kw, nominal.mess_discharge_kw),
                (current.mess_q_kvar, nominal.mess_q_kvar),
            )
        ):
            raise RuntimeContractError("AC safety projection changed disabled MESS controls")
        if not self.allow_compute and current.job_compute_rate_fraction != nominal.job_compute_rate_fraction:
            raise RuntimeContractError("AC safety projection changed disabled compute controls")
        return ProjectionCandidate(
            control=current,
            certificate=ProjectionCertificate(
                "CONVEX_CONTINUOUS_QP", True, True, True, True, True, True, True, True
            ),
            slow_plan_fingerprint=slow_plan.fingerprint,
            objective_nominal=self._electrical_stress_score(initial_exact),
            objective_projected=self._electrical_stress_score(exact),
            runtime_seconds=time.monotonic() - started,
        )


def _method_uses_temporal(config: MethodConfig) -> bool:
    return config.temporal_workload_shift


def _admit_arrivals(state: MutableMethodState, frame: CausalExperimentFrame, config: MethodConfig) -> int:
    spatial_blocked = 0
    for source in frame.arrivals:
        if source.job_uid in state.jobs:
            raise RuntimeContractError("duplicate job arrival")
        destination = source.origin_idc
        migration_state = "NOT_REQUESTED"
        checkpoint_state = "NOT_APPLICABLE"
        if config.spatial_workload_migration:
            if source.migration_payload_bytes is None:
                raise RuntimeContractError(
                    "spatial method lacks the frozen migration payload authority"
                )
            migration_state = "ELIGIBLE_AT_AUTHORIZED_CHECKPOINT"
            checkpoint_state = "INTERVAL_PENDING"
        gang = tuple(f"{destination}:PFR-GPU:{source.job_uid}:{index}" for index in range(source.requested_gpu))
        state.jobs[source.job_uid] = RuntimeJobState(
            source=source,
            destination_idc=destination,
            logical_rack_id=f"{destination}:PFR-H100-LOGICAL-POOL",
            gang_membership=gang,
            remaining_work_gpu_hours=source.total_work_gpu_hours,
            checkpoint_state=checkpoint_state,
            migration_state=migration_state,
        )
    return spatial_blocked


def _register_arrivals_in_active_plan(
    state: MutableMethodState,
    frame: CausalExperimentFrame,
) -> tuple[Mapping[str, Any], ...]:
    """Publish an immutable admission-only plan revision for new arrivals.

    A full slow replan optimizes optional placement, migration, and MESS routing.
    Workload admission is a separate common obligation: a job must become
    executable at its current (initially origin) IDC on its causal arrival issue,
    even when the method's slow-plan policy is FIXED or is between refreshes.
    This revision adds only the frozen default placement and gang identity; it
    cannot alter any pre-existing slow decision.
    """

    if state.active_plan is None:
        raise RuntimeContractError("workload admission lacks an active slow plan")
    plan = state.active_plan
    arrived_uids = tuple(source.job_uid for source in frame.arrivals)
    missing = tuple(uid for uid in arrived_uids if uid not in plan.job_idc_placement)
    stale_missing = sorted(
        uid
        for uid, job in state.jobs.items()
        if job.lifecycle != "COMPLETED"
        and uid not in plan.job_idc_placement
        and uid not in missing
    )
    if stale_missing:
        raise RuntimeContractError(
            "active slow plan lost previously admitted jobs: "
            + ",".join(stale_missing)
        )
    if not missing:
        return ()

    placement = dict(plan.job_idc_placement)
    checkpoint = dict(plan.checkpoint_migration)
    gangs = dict(plan.gpu_gang_allocation)
    starts = dict(plan.job_start_issue)
    wan_schedules = dict(plan.job_wan_send_gb)
    wan_requirements = dict(plan.job_wan_required_bytes)
    events = []
    for uid in missing:
        job = state.jobs[uid]
        if job.source.arrival_step != frame.issue:
            raise RuntimeContractError("admission revision is not causal to this issue")
        destination = job.destination_idc
        placement[uid] = destination
        checkpoint[uid] = None
        gangs[uid] = tuple(job.gang_membership)
        starts[uid] = frame.issue
        if wan_schedules:
            wan_schedules[uid] = (0.0,) * PLANNING_HORIZON_STEPS
        if wan_requirements:
            wan_requirements[uid] = 0
        events.append(
            {
                "job_uid": uid,
                "arrival_issue": frame.issue,
                "destination_idc": destination,
                "requested_gpu": job.source.requested_gpu,
                "decision_authority": "DETERMINISTIC_ORIGIN_ADMISSION_NO_OPTIMIZATION",
            }
        )

    revision = state.admission_plan_revision_count + 1
    base_plan_id = plan.plan_id.split("+A", 1)[0]
    revised = SlowDiscretePlan(
        plan_id=f"{base_plan_id}+A{revision}",
        valid_from_issue=plan.valid_from_issue,
        mess_destination=dict(plan.mess_destination),
        mess_native_route_rank=dict(plan.mess_native_route_rank),
        job_idc_placement=placement,
        checkpoint_migration=checkpoint,
        gpu_gang_allocation=gangs,
        job_start_issue=starts,
        coarse_charging_kw=dict(plan.coarse_charging_kw),
        coarse_discharging_kw=dict(plan.coarse_discharging_kw),
        coarse_reactive_kvar=dict(plan.coarse_reactive_kvar),
        mess_departure_issue=dict(plan.mess_departure_issue),
        job_wan_send_gb=wan_schedules,
        job_wan_required_bytes=wan_requirements,
    )
    revised.validate()
    for uid in plan.job_idc_placement:
        if (
            revised.job_idc_placement[uid] != plan.job_idc_placement[uid]
            or revised.checkpoint_migration[uid] != plan.checkpoint_migration[uid]
            or revised.gpu_gang_allocation[uid] != plan.gpu_gang_allocation[uid]
            or revised.job_start_issue[uid] != plan.job_start_issue[uid]
        ):
            raise RuntimeContractError(
                "admission-only revision mutated a pre-existing slow decision"
            )
    state.active_plan = revised
    state.admission_plan_revision_count = revision
    encoded_bytes = len(
        json.dumps(events, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    state.admission_communication_bytes += encoded_bytes
    state.communication_bytes += encoded_bytes
    return tuple(events)


def _compute_fraction(job: RuntimeJobState, frame: CausalExperimentFrame, config: MethodConfig) -> float:
    if job.lifecycle != "RUNNING":
        return 0.0
    # Time shifting belongs to the 54-step start schedule.  Once a whole GPU
    # gang is running, nominal execution is work-conserving and price-neutral.
    return 1.0


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
    *,
    safe: bool,
) -> Tuple[float, ...]:
    """Allocate deterministic lumped-physics energy over the causal ETA.

    The route-total energy has already been recomputed from frozen geometry and
    ETA.  Constant physical power is therefore the only profile assumption;
    learned E4 templates are deliberately outside the runtime authority.
    """
    route.validate()
    eta = route.safe_eta_seconds if safe else route.q50_eta_seconds
    total = route.safe_energy_kwh if safe else route.q50_energy_kwh
    steps = max(1, math.ceil(eta / 300.0))
    if steps > MAX_MESS_TRANSIT_STEPS:
        raise RuntimeContractError(
            "causal planning ETA exceeds the predeclared H54 mobility support"
        )
    durations = tuple(
        min(300.0, max(0.0, eta - 300.0 * index)) for index in range(steps)
    )
    duration_sum = sum(durations)
    if duration_sum <= 0.0 or abs(duration_sum - eta) > 1e-7:
        raise RuntimeContractError("causal ETA cannot be discretized into transit steps")
    profile = tuple(total * duration / duration_sum for duration in durations)
    if abs(sum(profile) - total) > max(1e-8, total * 1e-8):
        raise RuntimeContractError("physics transit profile does not conserve mobility energy")
    return profile


def _realized_mobility_energy_profile(
    realization: MobilityExecutionRealization,
) -> Tuple[float, ...]:
    """Discretize only the post-decision SUMO realization for execution."""
    realization.validate()
    eta = realization.eta_seconds
    total = realization.energy_kwh
    steps = max(1, math.ceil(eta / 300.0))
    durations = tuple(
        min(300.0, max(0.0, eta - 300.0 * index)) for index in range(steps)
    )
    duration_sum = sum(durations)
    if duration_sum <= 0.0 or abs(duration_sum - eta) > 1e-7:
        raise RuntimeContractError("SUMO realized ETA cannot be discretized")
    profile = tuple(total * duration / duration_sum for duration in durations)
    if abs(sum(profile) - total) > max(1e-8, total * 1e-8):
        raise RuntimeContractError("SUMO realized energy profile is not conserved")
    return profile


def _optimize_mess_routes(
    state: MutableMethodState,
    config: MethodConfig,
    frame: CausalExperimentFrame,
    evaluation_steps_remaining: int,
) -> Tuple[dict[str, str], dict[str, int]]:
    """Legacy bounded candidate generator pending H54 joint-plan handoff.

    ETA/energy/workload scores in this function are not electrical stress and
    therefore cannot be a scientific decision authority under the frozen
    objective.  They remain temporarily to preserve the existing executable
    asset and regression path while the retained H54 planner is wired into
    ``SlowDiscretePlan``.
    """
    if evaluation_steps_remaining <= 0:
        raise RuntimeContractError(
            "mobility optimizer lacks remaining evaluation steps"
        )
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
    away_mess = tuple(
        mid
        for mid in MESS_IDS
        if state.mess_location[mid] != MESS_CANONICAL_STAGING[mid]
    )
    if not candidate_sites and not away_mess:
        state.last_slow_miqp_certificate = {
            "status": "NO_ACTIVE_WORKLOAD_DESTINATION",
            "actual_gurobi_used": False,
            "num_integer_variables": 0,
        }
        return destinations, ranks

    candidates: dict[str, list[Tuple[str, int, Optional[MobilityRouteForecast], float]]] = {}
    episode_boundary_blocked_route_count = 0
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
        candidate_destinations = (
            list(candidate_sites)
            if mid in MOBILITY_ELIGIBLE_MESS_IDS
            else []
        )
        canonical_staging = MESS_CANONICAL_STAGING[mid]
        if (
            current != canonical_staging
            and canonical_staging not in candidate_destinations
        ):
            candidate_destinations.append(canonical_staging)
        for destination in candidate_destinations:
            if destination == current:
                continue
            for route in _pareto_routes(frame.routes_for(current, destination), safe=safe):
                eta = route.safe_eta_seconds if safe else route.q50_eta_seconds
                energy = route.safe_energy_kwh if safe else route.q50_energy_kwh
                planned_transit_steps = max(1, math.ceil(eta / 300.0))
                if planned_transit_steps > MAX_MESS_TRANSIT_STEPS:
                    continue
                # Actual SUMO time is execution-only and therefore cannot be
                # consulted here.  Reserve the full predeclared H54 execution
                # support near an independent episode boundary; using only the
                # predicted ETA caused post-decision boundary crossings.
                if evaluation_steps_remaining < MAX_MESS_TRANSIT_STEPS:
                    episode_boundary_blocked_route_count += 1
                    continue
                if state.mess_energy_kwh[mid] - energy < MESS_FLOOR_KWH - 1e-9:
                    continue
                return_to_staging = destination == canonical_staging
                score = (
                    eta / 1800.0
                    + energy / 100.0
                    - demand.get(destination, 0.0) / 25.0
                    - (1000.0 if return_to_staging else 0.0)
                )
                rows.append((destination, route.rank, route, score))
        candidates[mid] = rows

    try:
        import gurobipy as gp
        from gurobipy import GRB
    except Exception as exc:
        raise RuntimeContractError("slow mobility MIQP requires gurobipy") from exc
    model = gp.Model("pfr_slow_mobility_miqp")
    model.Params.OutputFlag = 0
    model.Params.Threads = gurobi_thread_limit()
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
    model.addConstr(
        gp.quicksum(
            variables[mid, index]
            for mid, rows in candidates.items()
            for index, row in enumerate(rows)
            if row[0] != MESS_CANONICAL_STAGING[mid]
        )
        <= 1,
        name="retain_three_canonical_grid_support_mess",
    )
    candidate_destinations = sorted({
        row[0]
        for rows in candidates.values()
        for row in rows
    })
    for destination in candidate_destinations:
        model.addConstr(
            gp.quicksum(
                variables[mid, index]
                for mid, rows in candidates.items()
                for index, row in enumerate(rows)
                if row[0] == destination
            )
            <= 1,
            name=f"single_mess_connection_slot[{destination}]",
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
        "objective_authority": "LEGACY_ROUTE_CANDIDATE_GENERATOR",
        "scientific_decision_authority": False,
        "replacement_required": "ELECTRICAL_STRESS_OBJECTIVE_V1_H54_JOINT_PLANNER",
        "actual_gurobi_used": True,
        "num_integer_variables": len(variables),
        "num_quadratic_objective_terms": len(candidate_sites),
        "destination_mess_occupancy_limit": 1,
        "maximum_mess_away_from_canonical_staging": 1,
        "mobility_eligible_mess_ids": list(MOBILITY_ELIGIBLE_MESS_IDS),
        "joint_safe_eta_energy_used": safe,
        "evaluation_steps_remaining": evaluation_steps_remaining,
        "episode_boundary_blocked_route_count": (
            episode_boundary_blocked_route_count
        ),
        "episode_boundary_eta_authority": (
            "SAFE_ETA" if safe else "Q50_ETA"
        ),
        "episode_boundary_execution_support_authority": (
            "PREDECLARED_H54_SUMO_EXECUTION_SUPPORT"
        ),
        "episode_boundary_execution_support_steps": MAX_MESS_TRANSIT_STEPS,
        "episode_boundary_execution_support_seconds": MAX_MESS_TRANSIT_SECONDS,
    }
    model.dispose()
    return destinations, ranks


def _build_slow_plan(
    state: MutableMethodState,
    config: MethodConfig,
    frame: CausalExperimentFrame,
    migration_authority: Optional[MigrationAuthority],
    evaluation_steps_remaining: int,
    joint_planner: Optional[H54JointPlanner] = None,
) -> SlowDiscretePlan:
    if isinstance(config.comparison_method_id, ElectricalStressMethod):
        if joint_planner is None:
            raise RuntimeContractError(
                "B00-B09 electrical-stress campaign requires the retained H54 joint planner; legacy route/workload heuristics are prohibited"
            )
        if not all(
            (
                frame.planning_forecast_background_p_kw,
                frame.planning_forecast_background_q_kvar,
                frame.planning_forecast_pv_available_kw,
            )
        ):
            raise RuntimeContractError(
                "B00-B09 H54 joint planner lacks the complete causal 54-step grid forecast"
            )
        if not frame.planning_mobility_npz_path:
            raise RuntimeContractError(
                "B00-B09 H54 joint planner lacks the causal 54-step mobility source"
            )
        plan, certificate = joint_planner.solve(
            state=state,
            config=config,
            frame=frame,
            migration_authority=migration_authority,
            evaluation_steps_remaining=evaluation_steps_remaining,
        )
        plan.validate()
        mask = config.h54_capability_mask
        if not mask["mess_dispatch"] and any(
            abs(float(value)) > 1e-9
            for schedules in (
                plan.coarse_charging_kw,
                plan.coarse_discharging_kw,
                plan.coarse_reactive_kvar,
            )
            for schedule in schedules.values()
            for value in schedule
        ):
            raise RuntimeContractError("H54 plan used MESS dispatch while disabled")
        if not mask["mess_mobility"] and any(
            plan.mess_destination[mid] != state.mess_location[mid]
            for mid in MESS_IDS
            if not state.mess_in_transit[mid]
        ):
            raise RuntimeContractError("H54 plan used MESS mobility while disabled")
        if not mask["spatial_compute"] and any(
            plan.job_idc_placement[uid] != _effective_job_site(job)
            for uid, job in state.jobs.items()
            if job.lifecycle != "COMPLETED"
        ):
            raise RuntimeContractError("H54 plan used spatial compute while disabled")
        if not mask["temporal_compute"] and any(
            int(start) != frame.issue for start in plan.job_start_issue.values()
        ):
            raise RuntimeContractError("H54 plan used temporal compute while disabled")
        if certificate.get("objective_authority") != OBJECTIVE_AUTHORITY:
            raise RuntimeContractError("H54 plan lacks frozen objective authority")
        if dict(certificate.get("capability_mask", {})) != dict(mask):
            raise RuntimeContractError("H54 planner certificate capability mask drift")
        state.last_slow_miqp_certificate = dict(certificate)
        return plan
    jobs = {uid: job for uid, job in state.jobs.items() if job.lifecycle != "COMPLETED"}
    destinations, route_ranks = _optimize_mess_routes(
        state,
        config,
        frame,
        evaluation_steps_remaining,
    )
    job_placements, checkpoint_migrations = _optimize_job_migrations(
        state,
        config,
        frame,
        migration_authority,
        evaluation_steps_remaining,
    )
    plan = SlowDiscretePlan(
        plan_id=f"{config.comparison_method_id.value}-{frame.issue}-{state.full_replan_count + 1}",
        valid_from_issue=frame.issue,
        mess_destination=destinations,
        mess_native_route_rank=route_ranks,
        job_idc_placement=job_placements,
        checkpoint_migration=checkpoint_migrations,
        gpu_gang_allocation={
            uid: tuple(
                f"{job_placements[uid]}:PFR-GPU:{uid}:{index}"
                for index in range(job.source.requested_gpu)
            )
            for uid, job in jobs.items()
        },
        job_start_issue={uid: max(frame.issue, job.source.arrival_step) for uid, job in jobs.items()},
        coarse_charging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
        coarse_discharging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
        coarse_reactive_kvar={mid: (0.0,) * 54 for mid in MESS_IDS},
    )
    plan.validate()
    return plan


def _effective_job_site(job: RuntimeJobState) -> str:
    if job.lifecycle == "MIGRATING" and job.migration_destination_idc is not None:
        return job.migration_destination_idc
    return job.destination_idc


def _schedule_capacity_feasible_queued_jobs(
    state: MutableMethodState,
    config: MethodConfig,
    frame: CausalExperimentFrame,
) -> Mapping[str, Any]:
    """Start whole GPU gangs without hiding capacity-blocked workload.

    The dispatcher is common and work-conserving: it never delays a job when
    the complete gang fits at its already-decided placement.  Priority is
    deterministic earliest-latest-start, then deadline, arrival, and UID.
    QUEUED jobs retain all work and remain visible in debt/deadline metrics.
    """

    reserve = {
        site: (
            float(frame.workload_reserve_gpu.get(site, 0.0))
            if config.joint_uncertainty
            else 0.0
        )
        for site in IDCS
    }
    capacity = {
        site: MODELED_GPU_CAPACITY_PER_IDC - reserve[site]
        for site in IDCS
    }
    if any(value < 0.0 for value in capacity.values()):
        raise RuntimeContractError("workload reserve exceeds IDC GPU capacity")
    occupied = {site: 0.0 for site in IDCS}
    for job in state.jobs.values():
        if job.lifecycle not in {"RUNNING", "MIGRATING", "RESTARTING"}:
            continue
        site = _effective_job_site(job)
        occupied[site] += job.source.requested_gpu
    if any(
        occupied[site] > MODELED_GPU_CAPACITY_PER_IDC + 1e-9
        for site in IDCS
    ):
        raise RuntimeContractError(
            "existing GPU gang occupancy exceeds physical IDC capacity"
        )

    started_jobs = 0
    started_gpu = {site: 0 for site in IDCS}
    plan_scheduled_wait_jobs = 0
    capacity_blocked_jobs = 0
    for uid, job in sorted(
        (
            (uid, job)
            for uid, job in state.jobs.items()
            if job.lifecycle == "QUEUED"
            and job.migration_state != "PRESTART_WAN_PENDING"
        ),
        key=lambda row: (
            row[1].source.latest_start_step,
            row[1].source.deadline_step,
            row[1].source.arrival_step,
            row[0],
        ),
    ):
        if state.active_plan is None or uid not in state.active_plan.job_start_issue:
            raise RuntimeContractError("queued job lacks an active H54 start decision")
        planned_start = int(state.active_plan.job_start_issue[uid])
        if frame.issue < planned_start:
            plan_scheduled_wait_jobs += 1
            continue
        site = job.destination_idc
        gpu = job.source.requested_gpu
        if gpu > MODELED_GPU_CAPACITY_PER_IDC:
            raise RuntimeContractError(
                "a GPU gang cannot fit at its fixed planned IDC"
            )
        if occupied[site] + gpu > capacity[site] + 1e-9:
            capacity_blocked_jobs += 1
            continue
        job.lifecycle = "RUNNING"
        job.compute_rate_fraction = 0.0
        job.start_issue = frame.issue
        occupied[site] += gpu
        started_jobs += 1
        started_gpu[site] += gpu

    queued = [job for job in state.jobs.values() if job.lifecycle == "QUEUED"]
    queued_gpu = {
        site: sum(
            job.source.requested_gpu
            for job in queued
            if job.destination_idc == site
        )
        for site in IDCS
    }
    state.scheduler_started_jobs_cumulative += started_jobs
    return {
        "policy": "COMMON_WORK_CONSERVING_LEAST_START_SLACK_EDF_WHOLE_GANG",
        "started_jobs": started_jobs,
        "started_gpu_by_site": started_gpu,
        "running_reserved_gpu_by_site": {
            site: int(occupied[site]) for site in IDCS
        },
        "queued_jobs": len(queued),
        "queued_gpu_by_site": queued_gpu,
        "plan_scheduled_wait_jobs": plan_scheduled_wait_jobs,
        "capacity_blocked_jobs": capacity_blocked_jobs,
        "capacity_blocked": capacity_blocked_jobs > 0,
        "capacity_gpu_by_site": capacity,
    }


def _optimize_job_migrations(
    state: MutableMethodState,
    config: MethodConfig,
    frame: CausalExperimentFrame,
    authority: Optional[MigrationAuthority],
    evaluation_steps_remaining: int,
) -> tuple[dict[str, str], dict[str, Optional[str]]]:
    if evaluation_steps_remaining <= 0:
        raise RuntimeContractError("migration optimizer lacks remaining evaluation steps")
    jobs = {uid: job for uid, job in state.jobs.items() if job.lifecycle != "COMPLETED"}
    placements = {uid: _effective_job_site(job) for uid, job in jobs.items()}
    migrations: dict[str, Optional[str]] = {
        uid: (
            job.migration_destination_idc
            if job.lifecycle == "MIGRATING"
            else None
        )
        for uid, job in jobs.items()
    }
    if not config.spatial_workload_migration:
        state.last_spatial_optimizer_certificate = {
            "status": "NOT_APPLICABLE_METHOD_CAPABILITY_DISABLED",
            "selected_migration": None,
        }
        return placements, migrations
    if authority is None:
        raise RuntimeContractError("spatial method requires migration authority")
    authority.validate()
    if any(
        job.source.migration_authority_sha256 != authority.fingerprint
        for job in jobs.values()
    ):
        raise RuntimeContractError(
            "job migration payload does not match the frozen migration authority"
        )
    reserved = {
        site: float(frame.workload_reserve_gpu.get(site, 0.0))
        if config.joint_uncertainty
        else 0.0
        for site in IDCS
    }
    physical_loads = {site: 0.0 for site in IDCS}
    for uid, job in jobs.items():
        if job.lifecycle != "QUEUED":
            physical_loads[placements[uid]] += job.source.requested_gpu
    if any(
        value > MODELED_GPU_CAPACITY_PER_IDC + 1e-9
        for value in physical_loads.values()
    ):
        raise RuntimeContractError("running GPU gang placement exceeds IDC capacity")
    loads = {
        site: reserved[site] + physical_loads[site]
        for site in IDCS
    }
    prestart_placements = []
    projected_queue_loads = dict(loads)
    for uid, job in sorted(
        (
            (uid, job)
            for uid, job in jobs.items()
            if job.lifecycle == "QUEUED"
        ),
        key=lambda row: (
            row[1].source.latest_start_step,
            row[1].source.deadline_step,
            row[1].source.arrival_step,
            row[0],
        ),
    ):
        gpu = job.source.requested_gpu
        feasible = [
            destination
            for destination in IDCS
            if gpu <= MODELED_GPU_CAPACITY_PER_IDC
        ]
        if not feasible:
            raise RuntimeContractError(
                "queued GPU gang exceeds every individual IDC capacity"
            )
        destination = min(
            feasible,
            key=lambda site: (
                sum(
                    (value + (gpu if candidate == site else 0.0)) ** 2
                    for candidate, value in projected_queue_loads.items()
                ),
                projected_queue_loads[site],
                site,
            ),
        )
        placements[uid] = destination
        projected_queue_loads[destination] += gpu
        if destination != job.destination_idc:
            prestart_placements.append(
                {
                    "job_uid": uid,
                    "source_idc": job.destination_idc,
                    "destination_idc": destination,
                    "requested_gpu": gpu,
                    "wan_bytes": 0,
                    "reason": "DATASET_PRESTAGED_AND_JOB_NOT_STARTED",
                }
            )
    baseline = sum(value * value for value in loads.values())
    candidates = []
    episode_boundary_blocked_candidate_count = 0
    if state.wan_active_transfers < authority.maximum_active_transfers:
        for uid, job in sorted(jobs.items()):
            if (
                job.lifecycle != "RUNNING"
                or job.steps_since_checkpoint < authority.checkpoint_interval_steps
                or job.source.migration_payload_bytes is None
            ):
                continue
            source = job.destination_idc
            gpu = job.source.requested_gpu
            for destination in IDCS:
                if destination == source:
                    continue
                if loads[destination] + gpu > MODELED_GPU_CAPACITY_PER_IDC + 1e-9:
                    continue
                after = dict(loads)
                after[source] -= gpu
                after[destination] += gpu
                improvement = baseline - sum(value * value for value in after.values())
                transfer_steps = authority.transfer_steps(
                    job.source.migration_payload_bytes, source, destination
                )
                downtime_steps = transfer_steps + authority.restart_steps
                net_improvement = improvement - (
                    authority.downtime_penalty_per_gpu_step * gpu * downtime_steps
                )
                if (
                    improvement >= authority.minimum_gpu_squared_improvement
                    and net_improvement > 0.0
                ):
                    if downtime_steps > evaluation_steps_remaining:
                        episode_boundary_blocked_candidate_count += 1
                        continue
                    candidates.append(
                        (
                            -net_improvement,
                            uid,
                            destination,
                            improvement,
                            transfer_steps,
                            downtime_steps,
                        )
                    )
    selected = min(candidates) if candidates else None
    if selected is not None:
        _, uid, destination, improvement, transfer_steps, downtime_steps = selected
        placements[uid] = destination
        migrations[uid] = destination
        selected_payload: Optional[Mapping[str, Any]] = {
            "job_uid": uid,
            "source_idc": jobs[uid].destination_idc,
            "destination_idc": destination,
            "payload_bytes": jobs[uid].source.migration_payload_bytes,
            "gpu_squared_improvement": improvement,
            "transfer_steps": transfer_steps,
            "restart_steps": authority.restart_steps,
            "total_downtime_steps": downtime_steps,
        }
    else:
        selected_payload = None
    state.last_spatial_optimizer_certificate = {
        "status": "OPTIMAL_EXACT_SINGLE_ACTION_ENUMERATION",
        "authority_sha256": authority.fingerprint,
        "eligible_candidate_count": len(candidates),
        "baseline_sum_squared_reserved_gpu": baseline,
        "projected_queue_gpu_by_site": projected_queue_loads,
        "selected_migration": selected_payload,
        "maximum_migrations_per_replan": 1,
        "evaluation_steps_remaining": evaluation_steps_remaining,
        "episode_boundary_blocked_candidate_count": (
            episode_boundary_blocked_candidate_count
        ),
        "prestart_placements": prestart_placements,
    }
    return placements, migrations


def _apply_planned_prestart_placements(
    state: MutableMethodState,
    config: MethodConfig,
) -> tuple[Mapping[str, Any], ...]:
    if not config.spatial_workload_migration:
        return ()
    if state.active_plan is None:
        raise RuntimeContractError("pre-start placement lacks an active slow plan")
    events = []
    for uid, destination in sorted(state.active_plan.job_idc_placement.items()):
        job = state.jobs[uid]
        if job.lifecycle != "QUEUED" or destination == job.destination_idc:
            continue
        source = job.destination_idc
        if state.active_plan.job_wan_required_bytes:
            required = int(state.active_plan.job_wan_required_bytes[uid])
            if required < 0:
                raise RuntimeContractError("prestart WAN requirement is negative")
            if (
                job.prestart_wan_target_idc not in {None, destination}
                and job.prestart_wan_transferred_bytes > 0
            ):
                raise RuntimeContractError(
                    "replan changed a partially transferred prestart destination"
                )
            job.prestart_wan_target_idc = destination
            job.prestart_wan_required_bytes = required
            job.prestart_wan_transferred_bytes = min(
                job.prestart_wan_transferred_bytes, required
            )
            if required > job.prestart_wan_transferred_bytes:
                job.migration_state = "PRESTART_WAN_PENDING"
            else:
                job.destination_idc = destination
                job.logical_rack_id = f"{destination}:PFR-H100-LOGICAL-POOL"
                job.gang_membership = tuple(
                    f"{destination}:PFR-GPU:{uid}:{index}"
                    for index in range(job.source.requested_gpu)
                )
                job.migration_state = "PRESTART_DATA_READY"
        else:
            # Historical B0-B8 read-compatible path.  The new B00-B09 adapter
            # always supplies an explicit causal WAN schedule.
            job.destination_idc = destination
            job.logical_rack_id = f"{destination}:PFR-H100-LOGICAL-POOL"
            job.gang_membership = tuple(
                f"{destination}:PFR-GPU:{uid}:{index}"
                for index in range(job.source.requested_gpu)
            )
            job.migration_state = "PRESTART_PLACED_DATASET_PRESTAGED"
        events.append(
            {
                "job_uid": uid,
                "source_idc": source,
                "destination_idc": destination,
                "requested_gpu": job.source.requested_gpu,
                "wan_bytes": (
                    job.prestart_wan_required_bytes
                    if state.active_plan.job_wan_required_bytes
                    else 0
                ),
                "transfer_pending": job.migration_state == "PRESTART_WAN_PENDING",
            }
        )
    return tuple(events)


def _advance_prestart_wan(
    state: MutableMethodState,
    authority: Optional[MigrationAuthority],
) -> Mapping[str, Any]:
    if state.active_plan is None or not state.active_plan.job_wan_send_gb:
        return {
            "bytes_transferred": 0,
            "bytes_transferred_by_job": {},
            "completed_prefetches": [],
        }
    transferred = 0
    transferred_by_job: dict[str, int] = {}
    completed = []
    index = min(
        max(0, state.active_plan_age_steps), PLANNING_HORIZON_STEPS - 1
    )
    for uid, schedule in sorted(state.active_plan.job_wan_send_gb.items()):
        job = state.jobs[uid]
        if job.lifecycle != "QUEUED" or job.prestart_wan_target_idc is None:
            continue
        scheduled = int(round(float(schedule[min(index, len(schedule) - 1)]) * 1e9))
        if scheduled < 0:
            raise RuntimeContractError("prestart WAN schedule is negative")
        if scheduled:
            if authority is None:
                raise RuntimeContractError("prestart WAN schedule lacks authority")
            source = job.source.origin_idc
            destination = job.prestart_wan_target_idc
            capacity = authority.transfer_capacity_bytes_per_step(
                source, destination
            )
            if scheduled > capacity:
                raise RuntimeContractError(
                    "prestart WAN schedule exceeds frozen path capacity"
                )
            remaining = max(
                0,
                job.prestart_wan_required_bytes
                - job.prestart_wan_transferred_bytes,
            )
            sent = min(scheduled, remaining)
            job.prestart_wan_transferred_bytes += sent
            transferred += sent
            transferred_by_job[uid] = sent
        if (
            job.prestart_wan_transferred_bytes
            >= job.prestart_wan_required_bytes
        ):
            destination = job.prestart_wan_target_idc
            job.destination_idc = destination
            job.logical_rack_id = f"{destination}:PFR-H100-LOGICAL-POOL"
            job.gang_membership = tuple(
                f"{destination}:PFR-GPU:{uid}:{gpu}"
                for gpu in range(job.source.requested_gpu)
            )
            job.migration_state = "PRESTART_DATA_READY"
            completed.append(
                {
                    "job_uid": uid,
                    "destination_idc": destination,
                    "transferred_bytes": job.prestart_wan_transferred_bytes,
                }
            )
            job.prestart_wan_target_idc = None
    state.wan_transferred_bytes_cumulative += transferred
    return {
        "bytes_transferred": transferred,
        "bytes_transferred_by_job": transferred_by_job,
        "completed_prefetches": completed,
    }


def _start_planned_job_migrations(
    state: MutableMethodState,
    config: MethodConfig,
    authority: Optional[MigrationAuthority],
) -> tuple[Mapping[str, Any], ...]:
    if not config.spatial_workload_migration:
        return ()
    if authority is None or state.active_plan is None:
        raise RuntimeContractError("planned spatial action lacks migration authority")
    events = []
    for uid, destination in sorted(state.active_plan.checkpoint_migration.items()):
        if destination is None:
            continue
        job = state.jobs[uid]
        if job.lifecycle == "MIGRATING":
            continue
        if job.lifecycle != "RUNNING":
            raise RuntimeContractError("migration plan selected a non-running job")
        if job.steps_since_checkpoint < authority.checkpoint_interval_steps:
            raise RuntimeContractError("migration plan violated checkpoint interval")
        if job.source.migration_payload_bytes is None:
            raise RuntimeContractError("migration plan lacks payload bytes")
        if state.wan_active_transfers >= authority.maximum_active_transfers:
            raise RuntimeContractError("migration plan exceeds WAN concurrency")
        source = job.destination_idc
        job.lifecycle = "MIGRATING"
        job.compute_rate_fraction = 0.0
        job.migration_source_idc = source
        job.migration_destination_idc = destination
        job.migration_payload_remaining_bytes = job.source.migration_payload_bytes
        job.migration_work_gpu_hours_at_start = job.remaining_work_gpu_hours
        predicted_transfer_steps = authority.transfer_steps(
            job.source.migration_payload_bytes, source, destination
        )
        job.migration_start_issue = state.issue
        job.migration_predicted_transfer_steps = predicted_transfer_steps
        job.migration_predicted_restart_steps = authority.restart_steps
        job.migration_transfer_complete_issue = None
        job.migration_actual_transfer_steps = None
        job.migration_state = "WAN_TRANSFER_ACTIVE"
        job.checkpoint_state = "CONSUMED_BY_MIGRATION"
        state.wan_active_transfers += 1
        state.migration_count_cumulative += 1
        events.append(
            {
                "job_uid": uid,
                "source_idc": source,
                "destination_idc": destination,
                "payload_bytes": job.source.migration_payload_bytes,
                "remaining_work_gpu_hours": job.remaining_work_gpu_hours,
                "checkpoint_steps_at_start": job.steps_since_checkpoint,
                "checkpoint_interval_steps": authority.checkpoint_interval_steps,
                "predicted_transfer_steps": predicted_transfer_steps,
                "predicted_restart_steps": authority.restart_steps,
                "required_transfer_restart_steps": (
                    predicted_transfer_steps + authority.restart_steps
                ),
                "predicted_total_downtime_seconds": (
                    (predicted_transfer_steps + authority.restart_steps)
                    * authority.step_seconds
                ),
            }
        )
    return tuple(events)


def _advance_job_migration_state(
    state: MutableMethodState,
    authority: Optional[MigrationAuthority],
) -> Mapping[str, Any]:
    active = [
        job for job in state.jobs.values() if job.lifecycle == "MIGRATING"
    ]
    restarting_before = {
        uid for uid, job in state.jobs.items() if job.lifecycle == "RESTARTING"
    }
    if not active and not restarting_before:
        state.wan_active_transfers = 0
        return {
            "bytes_transferred": 0,
            "completed_migrations": [],
            "completed_restarts": [],
            "completed_realizations": [],
        }
    if authority is None:
        raise RuntimeContractError("active migration state lacks authority")
    if len(active) > authority.maximum_active_transfers:
        raise RuntimeContractError("active migrations exceed WAN authority")
    transferred = 0
    completed_migrations = []
    completed_realizations = []
    for job in sorted(active, key=lambda item: item.source.job_uid):
        source = job.migration_source_idc
        destination = job.migration_destination_idc
        if source is None or destination is None:
            raise RuntimeContractError("active migration lacks endpoints")
        if (
            job.migration_work_gpu_hours_at_start is None
            or job.remaining_work_gpu_hours
            != job.migration_work_gpu_hours_at_start
        ):
            raise RuntimeContractError(
                "remaining compute work changed during checkpoint migration"
            )
        capacity = authority.transfer_capacity_bytes_per_step(source, destination)
        sent = min(job.migration_payload_remaining_bytes, capacity)
        if sent <= 0:
            raise RuntimeContractError("active migration made no WAN progress")
        job.migration_payload_remaining_bytes -= sent
        transferred += sent
        if job.migration_payload_remaining_bytes == 0:
            if (
                job.migration_start_issue is None
                or job.migration_predicted_transfer_steps is None
                or job.migration_predicted_restart_steps is None
            ):
                raise RuntimeContractError(
                    "active migration lacks prediction/realization audit state"
                )
            actual_transfer_steps = state.issue - job.migration_start_issue + 1
            if actual_transfer_steps <= 0:
                raise RuntimeContractError("migration transfer duration is invalid")
            job.migration_transfer_complete_issue = state.issue
            job.migration_actual_transfer_steps = actual_transfer_steps
            job.destination_idc = destination
            job.logical_rack_id = f"{destination}:PFR-H100-LOGICAL-POOL"
            job.gang_membership = tuple(
                f"{destination}:PFR-GPU:{job.source.job_uid}:{index}"
                for index in range(job.source.requested_gpu)
            )
            job.steps_since_checkpoint = 0
            if authority.restart_steps:
                job.lifecycle = "RESTARTING"
                job.restart_remaining_steps = authority.restart_steps
                job.migration_state = "TRANSFER_COMPLETE_RESTARTING"
            else:
                job.lifecycle = "RUNNING"
                job.restart_remaining_steps = 0
                job.migration_state = "COMPLETED"
            completed_migrations.append(
                {
                    "job_uid": job.source.job_uid,
                    "source_idc": source,
                    "destination_idc": destination,
                    "remaining_work_gpu_hours_before": (
                        job.migration_work_gpu_hours_at_start
                    ),
                    "remaining_work_gpu_hours_after": job.remaining_work_gpu_hours,
                    "work_conserved": True,
                    "predicted_transfer_steps": (
                        job.migration_predicted_transfer_steps
                    ),
                    "realized_transfer_steps": actual_transfer_steps,
                    "transfer_duration_error_steps": (
                        actual_transfer_steps
                        - job.migration_predicted_transfer_steps
                    ),
                    "predicted_transfer_seconds": (
                        job.migration_predicted_transfer_steps
                        * authority.step_seconds
                    ),
                    "realized_transfer_seconds": (
                        actual_transfer_steps * authority.step_seconds
                    ),
                    "transfer_duration_error_seconds": (
                        (actual_transfer_steps - job.migration_predicted_transfer_steps)
                        * authority.step_seconds
                    ),
                }
            )
            if authority.restart_steps == 0:
                predicted_total_steps = job.migration_predicted_transfer_steps
                actual_total_steps = actual_transfer_steps
                completed_realizations.append(
                    {
                        "job_uid": job.source.job_uid,
                        "source_idc": source,
                        "destination_idc": destination,
                        "predicted_payload_bytes": job.source.migration_payload_bytes,
                        "realized_payload_bytes": job.source.migration_payload_bytes,
                        "payload_error_bytes": 0,
                        "predicted_transfer_steps": (
                            job.migration_predicted_transfer_steps
                        ),
                        "predicted_restart_steps": 0,
                        "predicted_total_downtime_steps": predicted_total_steps,
                        "realized_transfer_steps": actual_transfer_steps,
                        "realized_restart_steps": 0,
                        "realized_total_downtime_steps": actual_total_steps,
                        "total_downtime_error_steps": (
                            actual_total_steps - predicted_total_steps
                        ),
                        "predicted_total_downtime_seconds": (
                            predicted_total_steps * authority.step_seconds
                        ),
                        "realized_total_downtime_seconds": (
                            actual_total_steps * authority.step_seconds
                        ),
                        "total_downtime_error_seconds": (
                            (actual_total_steps - predicted_total_steps)
                            * authority.step_seconds
                        ),
                        "prediction_authority": authority.authority_id,
                        "execution_authority": authority.authority_id,
                        "external_observed_wan_telemetry": False,
                    }
                )
                job.migration_start_issue = None
                job.migration_predicted_transfer_steps = None
                job.migration_predicted_restart_steps = None
                job.migration_transfer_complete_issue = None
                job.migration_actual_transfer_steps = None
                job.migration_source_idc = None
                job.migration_destination_idc = None
                job.migration_work_gpu_hours_at_start = None
    state.wan_transferred_bytes_cumulative += transferred
    completed_restarts = []
    for uid in sorted(restarting_before):
        job = state.jobs[uid]
        if job.lifecycle != "RESTARTING" or job.restart_remaining_steps <= 0:
            raise RuntimeContractError("restart state is inconsistent")
        job.restart_remaining_steps -= 1
        if job.restart_remaining_steps == 0:
            if (
                job.migration_work_gpu_hours_at_start is None
                or job.remaining_work_gpu_hours
                != job.migration_work_gpu_hours_at_start
            ):
                raise RuntimeContractError(
                    "remaining compute work changed during migration restart"
                )
            job.lifecycle = "RUNNING"
            job.migration_state = "COMPLETED"
            job.checkpoint_state = "INTERVAL_PENDING"
            if (
                job.migration_start_issue is None
                or job.migration_predicted_transfer_steps is None
                or job.migration_predicted_restart_steps is None
                or job.migration_transfer_complete_issue is None
                or job.migration_actual_transfer_steps is None
            ):
                raise RuntimeContractError(
                    "migration restart lacks prediction/realization audit state"
                )
            actual_restart_steps = state.issue - job.migration_transfer_complete_issue
            predicted_total_steps = (
                job.migration_predicted_transfer_steps
                + job.migration_predicted_restart_steps
            )
            actual_total_steps = state.issue - job.migration_start_issue + 1
            completed_restarts.append(uid)
            completed_realizations.append(
                {
                    "job_uid": uid,
                    "source_idc": job.migration_source_idc,
                    "destination_idc": job.destination_idc,
                    "predicted_payload_bytes": job.source.migration_payload_bytes,
                    "realized_payload_bytes": job.source.migration_payload_bytes,
                    "payload_error_bytes": 0,
                    "predicted_transfer_steps": (
                        job.migration_predicted_transfer_steps
                    ),
                    "predicted_restart_steps": (
                        job.migration_predicted_restart_steps
                    ),
                    "predicted_total_downtime_steps": predicted_total_steps,
                    "realized_transfer_steps": job.migration_actual_transfer_steps,
                    "realized_restart_steps": actual_restart_steps,
                    "realized_total_downtime_steps": actual_total_steps,
                    "total_downtime_error_steps": (
                        actual_total_steps - predicted_total_steps
                    ),
                    "predicted_total_downtime_seconds": (
                        predicted_total_steps * authority.step_seconds
                    ),
                    "realized_total_downtime_seconds": (
                        actual_total_steps * authority.step_seconds
                    ),
                    "total_downtime_error_seconds": (
                        (actual_total_steps - predicted_total_steps)
                        * authority.step_seconds
                    ),
                    "prediction_authority": authority.authority_id,
                    "execution_authority": authority.authority_id,
                    "external_observed_wan_telemetry": False,
                }
            )
            job.migration_work_gpu_hours_at_start = None
            job.migration_source_idc = None
            job.migration_destination_idc = None
            job.migration_start_issue = None
            job.migration_predicted_transfer_steps = None
            job.migration_predicted_restart_steps = None
            job.migration_transfer_complete_issue = None
            job.migration_actual_transfer_steps = None
    state.wan_active_transfers = sum(
        job.lifecycle == "MIGRATING" for job in state.jobs.values()
    )
    return {
        "bytes_transferred": transferred,
        "completed_migrations": completed_migrations,
        "completed_restarts": completed_restarts,
        "completed_realizations": completed_realizations,
    }


def _start_planned_routes(
    state: MutableMethodState,
    config: MethodConfig,
    frame: CausalExperimentFrame,
    execution_authority: Optional[MobilityExecutionAuthority],
    evaluation_steps_remaining: int,
) -> Tuple[Mapping[str, Any], ...]:
    if evaluation_steps_remaining <= 0:
        raise RuntimeContractError(
            "MESS route execution lacks remaining evaluation steps"
        )
    if state.active_plan is None or config.energy_flexibility != "MESS":
        return ()
    events = []
    for mid in MESS_IDS:
        if state.mess_in_transit[mid]:
            continue
        departure_issue = state.active_plan.mess_departure_issue.get(mid)
        if departure_issue is not None and frame.issue < int(departure_issue):
            continue
        source = state.mess_location[mid]
        destination = state.active_plan.mess_destination[mid]
        if source == destination:
            continue
        rank = state.active_plan.mess_native_route_rank[mid]
        routes = [route for route in frame.routes_for(source, destination) if route.rank == rank]
        if len(routes) != 1:
            raise RuntimeContractError("slow plan selected a route outside frozen K=3")
        route = routes[0]
        if execution_authority is None:
            raise RuntimeContractError(
                "MESS route execution requires post-decision SUMO authority"
            )
        # Ordering is scientifically material: the slow optimizer has already
        # committed source/destination/rank above.  Only now may actual 2025
        # SUMO travel time be opened for state transition and SOC deduction.
        realization = execution_authority.realize(issue=frame.issue, route=route)
        profile = _realized_mobility_energy_profile(realization)
        if len(profile) > MAX_MESS_TRANSIT_STEPS:
            raise RuntimeContractError(
                "post-decision SUMO mobility realization exceeds the predeclared "
                "H54 execution support: "
                f"issue={frame.issue} mess_id={mid} source={source} "
                f"destination={destination} rank={rank} "
                f"realized_eta_seconds={realization.eta_seconds:.12g} "
                f"execution_steps={len(profile)} "
                f"support_steps={MAX_MESS_TRANSIT_STEPS}"
            )
        if len(profile) > evaluation_steps_remaining:
            raise RuntimeContractError(
                "post-decision SUMO mobility realization crosses the independent "
                "episode boundary: "
                f"issue={frame.issue} mess_id={mid} source={source} "
                f"destination={destination} rank={rank} "
                f"planning_eta_seconds="
                f"{(route.safe_eta_seconds if config.joint_uncertainty else route.q50_eta_seconds):.12g} "
                f"realized_eta_seconds={realization.eta_seconds:.12g} "
                f"execution_steps={len(profile)} "
                f"evaluation_steps_remaining={evaluation_steps_remaining}"
            )
        realized_terminal_energy_kwh = state.mess_energy_kwh[mid] - sum(profile)
        if realized_terminal_energy_kwh < MESS_PHYSICAL_MIN_KWH - 1e-9:
            raise RuntimeContractError(
                "selected route exhausts physical battery energy under post-decision "
                "SUMO realization: "
                f"issue={frame.issue} mess_id={mid} source={source} "
                f"destination={destination} rank={rank} "
                f"energy_before_kwh={state.mess_energy_kwh[mid]:.12g} "
                f"planned_energy_kwh="
                f"{(route.safe_energy_kwh if config.joint_uncertainty else route.q50_energy_kwh):.12g} "
                f"realized_energy_kwh={sum(profile):.12g} "
                f"realized_terminal_energy_kwh="
                f"{realized_terminal_energy_kwh:.12g}"
            )
        state.mess_in_transit[mid] = True
        state.mess_route_destination[mid] = destination
        state.mess_route_rank[mid] = rank
        state.mess_route_energy_profile_kwh[mid] = profile
        state.mess_route_profile_index[mid] = 0
        events.append(
            {
                "mess_id": mid,
                "source_service_id": source,
                "destination_service_id": destination,
                "od_index": route.od_index,
                "rank": rank,
                "planned_q50_eta_seconds": route.q50_eta_seconds,
                "reserved_safe_eta_seconds": route.safe_eta_seconds,
                "planning_eta_seconds_used": (
                    route.safe_eta_seconds
                    if config.joint_uncertainty
                    else route.q50_eta_seconds
                ),
                "planned_mobility_energy_kwh": route.q50_energy_kwh,
                "reserved_safe_mobility_energy_kwh": route.safe_energy_kwh,
                "planning_mobility_energy_kwh_used": (
                    route.safe_energy_kwh
                    if config.joint_uncertainty
                    else route.q50_energy_kwh
                ),
                "sumo_realized_eta_seconds": realization.eta_seconds,
                "realized_mobility_energy_route_total_kwh": (
                    realization.energy_kwh
                ),
                "realized_terminal_energy_kwh": realized_terminal_energy_kwh,
                "realized_protected_floor_shortfall_kwh": max(
                    0.0, MESS_FLOOR_KWH - realized_terminal_energy_kwh
                ),
                "realized_route_protected_floor_feasible": (
                    realized_terminal_energy_kwh >= MESS_FLOOR_KWH - 1e-9
                ),
                "q50_eta_prediction_error_seconds": (
                    realization.eta_seconds - route.q50_eta_seconds
                ),
                "q50_eta_absolute_error_seconds": abs(
                    realization.eta_seconds - route.q50_eta_seconds
                ),
                "q50_eta_absolute_percentage_error": (
                    abs(realization.eta_seconds - route.q50_eta_seconds)
                    / route.q50_eta_seconds
                    if route.q50_eta_seconds > 0.0
                    else None
                ),
                "planning_eta_prediction_error_seconds": (
                    realization.eta_seconds
                    - (
                        route.safe_eta_seconds
                        if config.joint_uncertainty
                        else route.q50_eta_seconds
                    )
                ),
                "planning_eta_absolute_error_seconds": abs(
                    realization.eta_seconds
                    - (
                        route.safe_eta_seconds
                        if config.joint_uncertainty
                        else route.q50_eta_seconds
                    )
                ),
                "safe_eta_reserve_margin_seconds": (
                    route.safe_eta_seconds - realization.eta_seconds
                ),
                "safe_eta_realization_covered": (
                    realization.eta_seconds <= route.safe_eta_seconds
                ),
                "q50_energy_prediction_error_kwh": (
                    realization.energy_kwh - route.q50_energy_kwh
                ),
                "q50_energy_absolute_error_kwh": abs(
                    realization.energy_kwh - route.q50_energy_kwh
                ),
                "q50_energy_absolute_percentage_error": (
                    abs(realization.energy_kwh - route.q50_energy_kwh)
                    / route.q50_energy_kwh
                    if route.q50_energy_kwh > 0.0
                    else None
                ),
                "planning_energy_prediction_error_kwh": (
                    realization.energy_kwh
                    - (
                        route.safe_energy_kwh
                        if config.joint_uncertainty
                        else route.q50_energy_kwh
                    )
                ),
                "planning_energy_absolute_error_kwh": abs(
                    realization.energy_kwh
                    - (
                        route.safe_energy_kwh
                        if config.joint_uncertainty
                        else route.q50_energy_kwh
                    )
                ),
                "safe_energy_reserve_margin_kwh": (
                    route.safe_energy_kwh - realization.energy_kwh
                ),
                "safe_energy_realization_covered": (
                    realization.energy_kwh <= route.safe_energy_kwh
                ),
                "execution_transit_steps": len(profile),
                "execution_transit_duration_seconds_discrete": len(profile) * 300,
                "evaluation_steps_remaining_at_start": (
                    evaluation_steps_remaining
                ),
                "episode_boundary_execution_support_authority": (
                    "PREDECLARED_H54_SUMO_EXECUTION_SUPPORT"
                ),
                "episode_boundary_execution_support_steps": (
                    MAX_MESS_TRANSIT_STEPS
                ),
                "episode_boundary_completion_guaranteed": True,
                "realized_source_authority": realization.source_authority,
                "realized_source_day_sha256": realization.source_day_sha256,
                "actual_opened_post_decision_only": True,
                "actual_used_by_optimizer": False,
            }
        )
    return tuple(events)


def _risk_constraints(
    state: MutableMethodState,
    frame: CausalExperimentFrame,
    config: MethodConfig,
    *,
    exact_override: Optional[Mapping[str, Any]] = None,
    include_uncertainty: bool = True,
    risk_issue: Optional[int] = None,
) -> Tuple[RiskConstraint, ...]:
    active_jobs = [job for job in state.jobs.values() if job.lifecycle != "COMPLETED"]
    gpu_by_site = {site: sum(job.source.requested_gpu for job in active_jobs if job.destination_idc == site) for site in IDCS}
    if config.joint_uncertainty and include_uncertainty:
        gpu_by_site = {
            site: gpu_by_site[site] + frame.workload_reserve_gpu.get(site, 0.0)
            for site in IDCS
        }
    evaluation_issue = frame.issue if risk_issue is None else int(risk_issue)
    deadline_margin = max(
        (
            job.remaining_work_gpu_hours
            - max(0, job.source.deadline_step - evaluation_issue)
            * job.source.requested_gpu
            * STEP_HOURS
            for job in active_jobs
        ),
        default=-1.0,
    )
    min_energy = min(state.mess_energy_kwh.values())
    exact = exact_override if exact_override is not None else state.last_exact
    if exact is None:
        voltage_margin, thermal_margin = -0.01, -0.10
    else:
        voltage_margin = max(
            0.95 - float(exact["voltage_min_pu"]),
            float(exact["voltage_max_pu"]) - 1.05,
        )
        thermal_margin = max(
            float(exact["line_max_loading_pu"]) - 1.0,
            float(exact["transformer_max_current_loading_pu"]) - 1.0,
        )
        if exact_override is None and config.joint_uncertainty and include_uncertainty:
            # This is the previous issue's causal robust envelope, not a current-h0
            # realization.  It may request a new plan but never substitutes for the
            # current Fresh-OpenDSS commit gate.
            voltage_margin = max(
                voltage_margin,
                0.95
                - float(
                    exact.get(
                        "robust_grid_voltage_min_pu",
                        exact["voltage_min_pu"],
                    )
                ),
                float(
                    exact.get(
                        "robust_grid_voltage_max_pu",
                        exact["voltage_max_pu"],
                    )
                )
                - 1.05,
            )
            thermal_margin = max(
                thermal_margin,
                float(
                    exact.get(
                        "robust_grid_line_max_loading_pu",
                        exact["line_max_loading_pu"],
                    )
                )
                - 1.0,
                float(
                    exact.get(
                        "robust_grid_transformer_max_loading_pu",
                        exact["transformer_max_current_loading_pu"],
                    )
                )
                - 1.0,
            )
    return (
        RiskConstraint("soc", RiskFamily.SOC, MESS_FLOOR_KWH - min_energy, RISK_FAMILY_SCALES[RiskFamily.SOC.value]),
        RiskConstraint("deadline", RiskFamily.DEADLINE, deadline_margin, RISK_FAMILY_SCALES[RiskFamily.DEADLINE.value]),
        RiskConstraint("gpu", RiskFamily.GPU, max(gpu_by_site.values(), default=0) - MODELED_GPU_CAPACITY_PER_IDC, RISK_FAMILY_SCALES[RiskFamily.GPU.value]),
        RiskConstraint("wan", RiskFamily.WAN, -1.0, RISK_FAMILY_SCALES[RiskFamily.WAN.value]),
        RiskConstraint("voltage", RiskFamily.VOLTAGE, voltage_margin, RISK_FAMILY_SCALES[RiskFamily.VOLTAGE.value]),
        RiskConstraint("thermal", RiskFamily.THERMAL, thermal_margin, RISK_FAMILY_SCALES[RiskFamily.THERMAL.value]),
    )


def _risk_decision(
    state: MutableMethodState,
    frame: CausalExperimentFrame,
    config: MethodConfig,
    calibration: Optional[FrozenRiskCalibration],
):
    calibrated = config.risk_interface == "CALIBRATED"
    base_constraints = _risk_constraints(state, frame, config)
    if calibrated and calibration is None:
        raise RuntimeContractError(
            "calibrated B7/B8 risk interface lacks a frozen January-2025 authority"
        )
    constraints = tuple(
        RiskConstraint(
            constraint.name,
            constraint.family,
            constraint.violation_margin,
            constraint.predeclared_scale,
            (
                calibration.increment(constraint.family)
                if calibrated and calibration is not None
                else 0.0
            ),
        )
        for constraint in base_constraints
    )
    decision = PlanValidityRiskMonitor(calibrated=calibrated, maximum_refresh_steps=6).evaluate(
        constraints=constraints,
        expected_replan_benefit=0.0,
        replan_cost=ReplanCost(1.0, 0.0, 0.1, 0.01),
        plan_age_steps=state.active_plan_age_steps,
    )
    return decision, base_constraints


def _risk_calibration_audit(
    *,
    issue: int,
    predicted: Sequence[RiskConstraint],
    actual: Sequence[RiskConstraint],
    source_method: str = "B6",
) -> Mapping[str, Any]:
    if source_method not in {"B6", "B07"}:
        raise RuntimeContractError("risk calibration audit source must be B6 or B07")
    predicted_by_family = {row.family.value: row for row in predicted}
    actual_by_family = {row.family.value: row for row in actual}
    if set(predicted_by_family) != set(RISK_FAMILY_SCALES) or set(
        actual_by_family
    ) != set(RISK_FAMILY_SCALES):
        raise RuntimeContractError("risk calibration family axis is incomplete")
    predicted_margins = {
        family: float(predicted_by_family[family].violation_margin)
        for family in RISK_FAMILY_SCALES
    }
    actual_margins = {
        family: float(actual_by_family[family].violation_margin)
        for family in RISK_FAMILY_SCALES
    }
    positive_underprediction = {
        family: max(0.0, actual_margins[family] - predicted_margins[family])
        for family in RISK_FAMILY_SCALES
    }
    normalized = {
        family: positive_underprediction[family] / RISK_FAMILY_SCALES[family]
        for family in RISK_FAMILY_SCALES
    }
    return {
        "schema_version": "PFR5_EVENT_RISK_CALIBRATION_AUDIT_V1",
        "role": f"{source_method}_RAW_ONE_STEP_PREDECISION_TO_REALIZED_AUDIT",
        "prediction_issue": int(issue),
        "realization_issue": int(issue),
        "horizon_steps": 1,
        "future_actual_used_by_optimizer": False,
        "actual_opened_post_decision_only": True,
        "predicted_violation_margin": predicted_margins,
        "actual_violation_margin": actual_margins,
        "predeclared_scale": dict(RISK_FAMILY_SCALES),
        "positive_underprediction_margin": positive_underprediction,
        "normalized_positive_underprediction": normalized,
        "joint_normalized_score": max(normalized.values()),
    }


def _should_replan(state: MutableMethodState, config: MethodConfig, risk: Any, issue_offset: int) -> Tuple[bool, Tuple[str, ...]]:
    if state.active_plan is None:
        return True, ("INITIAL_PLAN",)
    if (
        config.control_mode == "PERIODIC_MPC"
        and config.periodic_replan_steps is not None
        and state.active_plan_age_steps >= config.periodic_replan_steps
    ):
        minutes = config.periodic_replan_steps * 5
        return True, (f"PERIODIC_{minutes}_MINUTE_REFRESH",)
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
    plan: SlowDiscretePlan,
    plan_age_steps: int,
) -> Tuple[Mapping[str, float], Mapping[str, float]]:
    charge = {mid: 0.0 for mid in MESS_IDS}
    discharge = {mid: 0.0 for mid in MESS_IDS}
    if not energy_enabled:
        return charge, discharge

    for mid in MESS_IDS:
        if in_transit[mid]:
            continue
        index = min(
            max(0, int(plan_age_steps)),
            len(plan.coarse_charging_kw[mid]) - 1,
        )
        planned_charge = float(plan.coarse_charging_kw[mid][index])
        discharging = plan.coarse_discharging_kw.get(mid, ())
        planned_discharge = (
            float(discharging[min(index, len(discharging) - 1)])
            if discharging
            else 0.0
        )
        net = planned_discharge - planned_charge
        energy = float(energy_kwh[mid])
        max_charge_by_soc = max(
            0.0,
            (MESS_CAPACITY_KWH - energy)
            / (MESS_CHARGE_EFFICIENCY * STEP_HOURS),
        )
        max_discharge_by_soc = max(
            0.0,
            (energy - MESS_SAFETY_RESERVE_KWH)
            * MESS_CHARGE_EFFICIENCY
            / STEP_HOURS,
        )
        if net >= 0.0:
            discharge[mid] = min(
                MESS_CHARGE_LIMIT_KW, max_discharge_by_soc, net
            )
        else:
            charge[mid] = min(MESS_CHARGE_LIMIT_KW, max_charge_by_soc, -net)
    return charge, discharge


def _nominal_control(state: MutableMethodState, config: MethodConfig, frame: CausalExperimentFrame) -> FastControl:
    compute = {
        uid: _compute_fraction(job, frame, config)
        for uid, job in state.jobs.items()
        if job.lifecycle == "RUNNING"
    }
    energy_enabled = config.energy_flexibility in {"MESS", "STATIONARY_BESS"}
    charge, discharge = _nominal_mess_dispatch(
        energy_kwh=state.mess_energy_kwh,
        in_transit=state.mess_in_transit,
        energy_enabled=energy_enabled,
        plan=state.active_plan,
        plan_age_steps=state.active_plan_age_steps,
    )
    return FastControl(
        mess_charge_kw=charge,
        mess_discharge_kw=discharge,
        mess_q_kvar={
            mid: (
                float(
                    state.active_plan.coarse_reactive_kvar[mid][
                        min(
                            max(0, state.active_plan_age_steps),
                            len(state.active_plan.coarse_reactive_kvar[mid]) - 1,
                        )
                    ]
                )
                if state.active_plan.coarse_reactive_kvar.get(mid)
                and not state.mess_in_transit[mid]
                else 0.0
            )
            for mid in MESS_IDS
        },
        job_compute_rate_fraction=compute,
        site_throughput_fraction={site: 1.0 for site in IDCS},
    )


def _enforce_compute_modulation_authority(
    config: MethodConfig,
    nominal: FastControl,
    optimized: FastControl,
    state: FastLayerState,
    limits: FastLayerLimits,
) -> None:
    """Prevent an optimizer from granting temporal flexibility to B0/B1."""

    if config.temporal_workload_shift:
        return
    expected = {
        uid: min(
            max(float(nominal.job_compute_rate_fraction[uid]), 0.0),
            float(state.remaining_work_gpu_hours[uid])
            / (int(limits.job_gpu_count[uid]) * STEP_HOURS),
        )
        for uid in nominal.job_compute_rate_fraction
    }
    if set(optimized.job_compute_rate_fraction) != set(expected) or any(
        abs(
            float(optimized.job_compute_rate_fraction[uid])
            - expected[uid]
        )
        > 1e-9
        for uid in expected
    ):
        raise RuntimeContractError(
            "fast optimizer modulated compute for a method without temporal flexibility"
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
        "mess_energy_debt_kwh": state.mess_energy_debt_kwh,
        "wan_transferred_bytes_cumulative": state.wan_transferred_bytes_cumulative,
        "wan_active_transfers": state.wan_active_transfers,
        "migration_count_cumulative": state.migration_count_cumulative,
        "admission_plan_revision_count": state.admission_plan_revision_count,
        "admission_communication_bytes": state.admission_communication_bytes,
        "scheduler_started_jobs_cumulative": state.scheduler_started_jobs_cumulative,
        "capacity_queue_wait_job_steps_cumulative": (
            state.capacity_queue_wait_job_steps_cumulative
        ),
        "planned_temporal_wait_job_steps_cumulative": (
            state.planned_temporal_wait_job_steps_cumulative
        ),
        "native_capacitor_states": state.native_capacitor_states,
        "native_capacitor_dwell_remaining_steps": (
            state.native_capacitor_dwell_remaining_steps
        ),
        "native_capacitor_switch_count": state.native_capacitor_switch_count,
        "native_regulator_tap_numbers": state.native_regulator_tap_numbers,
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
                "steps_since_checkpoint": job.steps_since_checkpoint,
                "migration_source_idc": job.migration_source_idc,
                "migration_destination_idc": job.migration_destination_idc,
                "migration_payload_remaining_bytes": (
                    job.migration_payload_remaining_bytes
                ),
                "restart_remaining_steps": job.restart_remaining_steps,
                "migration_work_gpu_hours_at_start": (
                    job.migration_work_gpu_hours_at_start
                ),
                "migration_start_issue": job.migration_start_issue,
                "migration_predicted_transfer_steps": (
                    job.migration_predicted_transfer_steps
                ),
                "migration_predicted_restart_steps": (
                    job.migration_predicted_restart_steps
                ),
                "migration_transfer_complete_issue": (
                    job.migration_transfer_complete_issue
                ),
                "migration_actual_transfer_steps": (
                    job.migration_actual_transfer_steps
                ),
                "queue_wait_steps": job.queue_wait_steps,
                "prestart_wan_target_idc": job.prestart_wan_target_idc,
                "prestart_wan_required_bytes": job.prestart_wan_required_bytes,
                "prestart_wan_transferred_bytes": (
                    job.prestart_wan_transferred_bytes
                ),
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
        native_control_initial_states: Optional[
            Mapping[str, Sequence[int]]
        ] = None,
        native_control_minimum_dwell_steps: int = 0,
        migration_authority: Optional[MigrationAuthority] = None,
        mobility_execution_authority: Optional[MobilityExecutionAuthority] = None,
        risk_calibration_authority: Optional[FrozenRiskCalibration] = None,
        joint_planner: Optional[H54JointPlanner] = None,
    ) -> None:
        power_curve.validate()
        self.power_curve = power_curve
        self.physical_backend = physical_backend
        self.fast_optimizer = fast_optimizer or IdentityFastControlOptimizer()
        self.controller_id = controller_id
        self.architecture = SlowFastArchitecture()
        self.native_control_initial_states = {
            str(name).lower(): tuple(int(value) for value in values)
            for name, values in (native_control_initial_states or {}).items()
        }
        if native_control_minimum_dwell_steps < 0:
            raise RuntimeContractError("native control dwell steps cannot be negative")
        self.native_control_minimum_dwell_steps = int(
            native_control_minimum_dwell_steps
        )
        if migration_authority is not None:
            migration_authority.validate()
        self.migration_authority = migration_authority
        self.mobility_execution_authority = mobility_execution_authority
        if risk_calibration_authority is not None:
            risk_calibration_authority.validate()
        self.risk_calibration_authority = risk_calibration_authority
        self.joint_planner = joint_planner

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
            native_capacitor_states=dict(self.native_control_initial_states),
            native_capacitor_dwell_remaining_steps={
                name: 0 for name in self.native_control_initial_states
            },
            native_capacitor_switch_count={
                name: 0 for name in self.native_control_initial_states
            },
        )
        records = []
        cumulative_grid_cost_aud = 0.0
        failure: Optional[Mapping[str, Any]] = None
        for offset, frame in enumerate(frames):
            started = time.monotonic()
            slow_solver_time_s = 0.0
            communication_bytes_before = state.communication_bytes
            frame.validate()
            if frame.issue != state.issue:
                raise RuntimeContractError("PRE state issue does not match causal frame")
            blocked_spatial = _admit_arrivals(state, frame, config)
            risk, predicted_risk_constraints = _risk_decision(
                state,
                frame,
                config,
                self.risk_calibration_authority,
            )
            risk_used_previous_grid_envelope = state.last_exact is not None
            replan, replan_causes = _should_replan(state, config, risk, offset)
            migration_started_events: tuple[Mapping[str, Any], ...] = ()
            prestart_placement_events: tuple[Mapping[str, Any], ...] = ()
            admission_plan_events: tuple[Mapping[str, Any], ...] = ()
            mobility_started_events: tuple[Mapping[str, Any], ...] = ()
            if replan:
                slow_started = time.monotonic()
                state.active_plan = _build_slow_plan(
                    state,
                    config,
                    frame,
                    self.migration_authority,
                    len(frames) - offset,
                    self.joint_planner,
                )
                slow_solver_time_s += time.monotonic() - slow_started
                state.active_plan_age_steps = 0
                state.full_replan_count += 1
                state.communication_bytes += len(
                    json.dumps(asdict(state.active_plan), sort_keys=True, separators=(",", ":"))
                )
                prestart_placement_events = _apply_planned_prestart_placements(
                    state, config
                )
                migration_started_events = _start_planned_job_migrations(
                    state, config, self.migration_authority
                )
            if state.active_plan is None:
                raise RuntimeContractError("no active slow plan")
            mobility_started_events = _start_planned_routes(
                state,
                config,
                frame,
                self.mobility_execution_authority,
                len(frames) - offset,
            )
            plan_id_for_action = state.active_plan.plan_id
            plan_origin_issue_for_action = state.active_plan.valid_from_issue
            plan_age_for_action = state.active_plan_age_steps
            if not replan:
                admission_plan_events = _register_arrivals_in_active_plan(
                    state, frame
                )
            workload_schedule = _schedule_capacity_feasible_queued_jobs(
                state, config, frame
            )
            nominal = _nominal_control(state, config, frame)
            fast_state = FastLayerState(
                issue=frame.issue,
                mess_soc={mid: state.mess_energy_kwh[mid] / MESS_CAPACITY_KWH for mid in MESS_IDS},
                remaining_work_gpu_hours={
                    uid: job.remaining_work_gpu_hours
                    for uid, job in state.jobs.items()
                    if job.lifecycle == "RUNNING"
                    and uid in state.active_plan.job_idc_placement
                },
            )
            limits = FastLayerLimits(
                step_minutes=5,
                mess_energy_capacity_kwh={mid: MESS_CAPACITY_KWH for mid in MESS_IDS},
                mess_charge_limit_kw={mid: 0.0 if state.mess_in_transit[mid] else 550.0 for mid in MESS_IDS},
                mess_discharge_limit_kw={mid: 0.0 if state.mess_in_transit[mid] else 550.0 for mid in MESS_IDS},
                mess_pcs_kva={mid: 700.0 for mid in MESS_IDS},
                mess_soc_min={
                    mid: _fast_recourse_soc_min(state.mess_energy_kwh[mid])
                    for mid in MESS_IDS
                },
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
                    compute_modulation_enabled=config.temporal_workload_shift,
                ),
            )
            _enforce_compute_modulation_authority(
                config, nominal, optimized.control, fast_state, limits
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
                frame.native_forecast_background_p_kw,
                frame.native_forecast_background_q_kvar,
                frame.native_forecast_pv_available_kw,
                state.native_capacitor_states,
                state.native_regulator_tap_numbers,
                tuple(
                    name
                    for name, remaining in state.native_capacitor_dwell_remaining_steps.items()
                    if remaining > 0
                ),
            )
            native_decision = verifier.select_native_control(control=fast.control)
            pre_safety_control = fast.control
            accepted_fast_state = fast_state
            accepted_limits = limits
            active_optimization = optimized
            safety_replan = False

            def escalate_for_safety() -> EscalatedCandidate:
                nonlocal accepted_fast_state, accepted_limits, active_optimization, fast, safety_replan, migration_started_events, prestart_placement_events, workload_schedule, slow_solver_time_s, plan_id_for_action, plan_origin_issue_for_action, plan_age_for_action
                slow_started = time.monotonic()
                state.active_plan = _build_slow_plan(
                    state,
                    config,
                    frame,
                    self.migration_authority,
                    len(frames) - offset,
                    self.joint_planner,
                )
                slow_solver_time_s += time.monotonic() - slow_started
                plan_id_for_action = state.active_plan.plan_id
                plan_origin_issue_for_action = state.active_plan.valid_from_issue
                plan_age_for_action = 0
                state.active_plan_age_steps = 0
                state.full_replan_count += 1
                state.communication_bytes += len(
                    json.dumps(asdict(state.active_plan), sort_keys=True, separators=(",", ":"))
                )
                prestart_placement_events += _apply_planned_prestart_placements(
                    state, config
                )
                migration_started_events += _start_planned_job_migrations(
                    state, config, self.migration_authority
                )
                escalated_schedule = _schedule_capacity_feasible_queued_jobs(
                    state, config, frame
                )
                workload_schedule = {
                    **escalated_schedule,
                    "started_jobs": (
                        workload_schedule["started_jobs"]
                        + escalated_schedule["started_jobs"]
                    ),
                    "started_gpu_by_site": {
                        site: (
                            workload_schedule["started_gpu_by_site"][site]
                            + escalated_schedule["started_gpu_by_site"][site]
                        )
                        for site in IDCS
                    },
                }
                safety_replan = True
                accepted_fast_state = FastLayerState(
                    issue=frame.issue,
                    mess_soc={mid: state.mess_energy_kwh[mid] / MESS_CAPACITY_KWH for mid in MESS_IDS},
                    remaining_work_gpu_hours={
                        uid: job.remaining_work_gpu_hours
                        for uid, job in state.jobs.items()
                        if job.lifecycle == "RUNNING"
                        and uid in state.active_plan.job_idc_placement
                    },
                )
                accepted_limits = FastLayerLimits(
                    step_minutes=5,
                    mess_energy_capacity_kwh={mid: MESS_CAPACITY_KWH for mid in MESS_IDS},
                    mess_charge_limit_kw={mid: 0.0 if state.mess_in_transit[mid] else 550.0 for mid in MESS_IDS},
                    mess_discharge_limit_kw={mid: 0.0 if state.mess_in_transit[mid] else 550.0 for mid in MESS_IDS},
                    mess_pcs_kva={mid: 700.0 for mid in MESS_IDS},
                    mess_soc_min={
                        mid: _fast_recourse_soc_min(state.mess_energy_kwh[mid])
                        for mid in MESS_IDS
                    },
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
                        compute_modulation_enabled=config.temporal_workload_shift,
                    ),
                )
                _enforce_compute_modulation_authority(
                    config,
                    escalated_nominal,
                    active_optimization.control,
                    accepted_fast_state,
                    accepted_limits,
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

            safety_projector = _GurobiSensitivityProjector(
                verifier,
                allow_mess=config.energy_flexibility in {"MESS", "STATIONARY_BESS"},
                allow_compute=config.temporal_workload_shift,
                compute_site_capacity={
                    site: MODELED_GPU_CAPACITY_PER_IDC
                    - (
                        frame.workload_reserve_gpu.get(site, 0.0)
                        if config.joint_uncertainty
                        else 0.0
                    )
                    for site in IDCS
                },
            )
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
            native_decision = verifier.native_decision or native_decision
            if not safety.accepted:
                failure = {
                    "status": "FAIL_CLOSED_EXACT_AC",
                    "issue": frame.issue,
                    "comparison_method_id": config.comparison_method_id.value,
                    "exact_ac": dict(verifier.last_commit.raw_metrics),
                    "native_grid_control_decision": dict(
                        native_decision.raw_metrics
                    ),
                    "safety_projection_trace": safety_projector.trace,
                    "partial_results_preserved": True,
                }
                atomic_write_json(method_root / "FAILURE.json", failure)
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
                if job.lifecycle != "RUNNING":
                    raise RuntimeContractError(
                        "fast compute control references a non-running job"
                    )
                job.compute_rate_fraction = fraction
            facility_p, _ = _facility_power(state.jobs.values(), self.power_curve)
            previous_native_states = dict(state.native_capacitor_states)
            state.native_capacitor_states = {
                str(name).lower(): tuple(int(value) for value in values)
                for name, values in native_decision.states.items()
            }
            for name, values in state.native_capacitor_states.items():
                previous = previous_native_states.get(name, values)
                old_remaining = state.native_capacitor_dwell_remaining_steps.get(
                    name, 0
                )
                if tuple(previous) != tuple(values):
                    state.native_capacitor_switch_count[name] = (
                        state.native_capacitor_switch_count.get(name, 0) + 1
                    )
                    state.native_capacitor_dwell_remaining_steps[name] = (
                        self.native_control_minimum_dwell_steps
                    )
                else:
                    state.native_capacitor_dwell_remaining_steps[name] = max(
                        0, old_remaining - 1
                    )
            state.native_regulator_tap_numbers = {
                str(name).lower(): int(value)
                for name, value in native_decision.regulator_taps.items()
            }
            mess_in_transit_before_execution = dict(state.mess_in_transit)
            for mid in MESS_IDS:
                state.mess_energy_kwh[mid] = fast.next_state.mess_soc[mid] * MESS_CAPACITY_KWH
                support = (
                    STEP_HOURS
                    * float(fast.control.mess_discharge_kw[mid])
                    / MESS_CHARGE_EFFICIENCY
                )
                repayment = (
                    STEP_HOURS
                    * float(fast.control.mess_charge_kw[mid])
                    * MESS_CHARGE_EFFICIENCY
                )
                state.mess_energy_debt_kwh[mid] = max(
                    0.0,
                    float(state.mess_energy_debt_kwh[mid])
                    + support
                    - repayment,
                )
            state.energy_debt_kwh = sum(state.mess_energy_debt_kwh.values())
            realized_mobility_energy_kwh = 0.0
            for mid in MESS_IDS:
                if not state.mess_in_transit[mid]:
                    continue
                index = state.mess_route_profile_index[mid]
                profile = state.mess_route_energy_profile_kwh[mid]
                if index >= len(profile):
                    raise RuntimeContractError("transit profile index escaped physics authority")
                movement = profile[index]
                realized_mobility_energy_kwh += movement
                state.mess_energy_kwh[mid] -= movement
                if state.mess_energy_kwh[mid] < MESS_PHYSICAL_MIN_KWH - 1e-9:
                    raise RuntimeContractError(
                        "realized mobility profile exhausted physical battery energy"
                    )
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
            if offset == len(frames) - 1 and any(state.mess_in_transit.values()):
                raise RuntimeContractError(
                    "independent daily episode ended with unfinished MESS transit"
                )
            for uid, remaining in fast.next_state.remaining_work_gpu_hours.items():
                job = state.jobs[uid]
                job.remaining_work_gpu_hours = remaining
                if remaining <= 1e-12:
                    job.remaining_work_gpu_hours = 0.0
                    job.lifecycle = "COMPLETED"
                    job.completion_issue = frame.issue + 1
                    job.checkpoint_state = "NOT_APPLICABLE_COMPLETED"
                elif (
                    job.lifecycle == "RUNNING"
                    and float(fast.control.job_compute_rate_fraction.get(uid, 0.0)) > 0.0
                ):
                    job.steps_since_checkpoint += 1
                    if (
                        config.spatial_workload_migration
                        and self.migration_authority is not None
                        and job.steps_since_checkpoint
                        >= self.migration_authority.checkpoint_interval_steps
                    ):
                        job.checkpoint_state = "READY"
                    elif config.spatial_workload_migration:
                        job.checkpoint_state = "INTERVAL_PENDING"
            prestart_wan_progress = _advance_prestart_wan(
                state, self.migration_authority
            )
            migration_progress = _advance_job_migration_state(
                state, self.migration_authority
            )
            queued_after_step = [
                job for job in state.jobs.values() if job.lifecycle == "QUEUED"
            ]
            for job in queued_after_step:
                job.queue_wait_steps += 1
            planned_wait_uids = {
                uid
                for uid, job in state.jobs.items()
                if job.lifecycle == "QUEUED"
                and state.active_plan is not None
                and uid in state.active_plan.job_start_issue
                and frame.issue < int(state.active_plan.job_start_issue[uid])
            }
            planned_wait_after_step = [
                state.jobs[uid] for uid in sorted(planned_wait_uids)
            ]
            capacity_wait_after_step = [
                job
                for uid, job in state.jobs.items()
                if job.lifecycle == "QUEUED" and uid not in planned_wait_uids
            ]
            state.planned_temporal_wait_job_steps_cumulative += len(
                planned_wait_after_step
            )
            state.capacity_queue_wait_job_steps_cumulative += len(
                capacity_wait_after_step
            )
            state.compute_debt_gpu_hours = sum(
                max(0.0, job.remaining_work_gpu_hours - max(0, job.source.deadline_step - frame.issue - 1) * job.source.requested_gpu * STEP_HOURS)
                for job in state.jobs.values() if job.lifecycle != "COMPLETED"
            )
            risk_calibration_audit: Mapping[str, Any] | None = None
            if config.risk_interface == "RAW_UNCALIBRATED":
                actual_risk_constraints = _risk_constraints(
                    state,
                    frame,
                    config,
                    exact_override=verifier.last_commit.raw_metrics,
                    include_uncertainty=False,
                    risk_issue=frame.issue + 1,
                )
                risk_calibration_audit = _risk_calibration_audit(
                    issue=frame.issue,
                    predicted=predicted_risk_constraints,
                    actual=actual_risk_constraints,
                    source_method=config.comparison_method_id.value,
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
            deadline_missed_job_ids = tuple(
                sorted(
                    uid
                    for uid, job in state.jobs.items()
                    if job.lifecycle != "COMPLETED"
                    and state.issue > job.source.deadline_step
                )
            )
            exact_electrical_stress = stress_from_extrema(
                minimum_voltage_pu=verifier.last_commit.exact.minimum_voltage_pu,
                maximum_voltage_pu=verifier.last_commit.exact.maximum_voltage_pu,
                maximum_line_loading_fraction=(
                    verifier.last_commit.exact.maximum_line_loading_fraction
                ),
                maximum_transformer_loading_fraction=(
                    verifier.last_commit.exact.maximum_transformer_loading_fraction
                ),
            )
            step_grid_cost_aud = (
                float(verifier.last_commit.raw_metrics["root_import_p_kw"])
                * frame.current_price_aud_per_mwh
                * STEP_HOURS
                / 1000.0
            )
            cumulative_grid_cost_aud += step_grid_cost_aud
            record = {
                "schema_version": "K9H7_RESULT_V2.issue_commit.v2",
                "result_uid": identity.result_uid,
                "scientific_framework_id": identity.scientific_framework_id,
                "comparison_method_id": config.comparison_method_id.value,
                "method_order": int(config.comparison_method_id.value[1:]),
                "energy_flex": config.energy_flexibility,
                "temporal_compute": config.temporal_workload_shift,
                "spatial_compute": config.spatial_workload_migration,
                "replan_policy": config.control_mode,
                "risk_calibration": config.risk_interface == "CALIBRATED",
                "objective_id": OBJECTIVE_AUTHORITY,
                "objective_primary": "WORST_PREDICTED_ELECTRICAL_STRESS",
                "h54_capability_mask": dict(config.h54_capability_mask),
                "factorial_energy": (
                    int(config.energy_flexibility == "MESS")
                    if config.comparison_method_id.value
                    in {"B00", "B01", "B04", "B06"}
                    else None
                ),
                "factorial_compute": (
                    int(
                        config.temporal_workload_shift
                        and config.spatial_workload_migration
                    )
                    if config.comparison_method_id.value
                    in {"B00", "B01", "B04", "B06"}
                    else None
                ),
                "predicted_worst_electrical_stress_pu": (
                    state.last_slow_miqp_certificate.get(
                        "objective_worst_predicted_electrical_stress_pu"
                    )
                ),
                "predicted_electrical_stress_exposure_pu_hours": (
                    state.last_slow_miqp_certificate.get(
                        "objective_predicted_stress_exposure_pu_hours"
                    )
                ),
                "predicted_voltage_stress_max": state.last_slow_miqp_certificate.get(
                    "predicted_voltage_stress_max"
                ),
                "predicted_line_stress_max": state.last_slow_miqp_certificate.get(
                    "predicted_line_stress_max"
                ),
                "predicted_transformer_stress_max": state.last_slow_miqp_certificate.get(
                    "predicted_transformer_stress_max"
                ),
                "predicted_worst_stress_type": state.last_slow_miqp_certificate.get(
                    "predicted_worst_stress_type"
                ),
                "predicted_worst_element_id": state.last_slow_miqp_certificate.get(
                    "predicted_worst_element_id"
                ),
                "predicted_worst_phase": state.last_slow_miqp_certificate.get(
                    "predicted_worst_phase"
                ),
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
                "future_actual_used_by_optimizer": False,
                "h0_only_committed": True,
                "slow_plan_fingerprint": state.active_plan.fingerprint,
                "plan_id": plan_id_for_action,
                "replan_id": state.full_replan_count,
                "plan_origin_issue": plan_origin_issue_for_action,
                "plan_age_steps": plan_age_for_action,
                "binary_state_unchanged": fast.binary_state_unchanged,
                "full_replan_executed": replan or safety_replan,
                "replan_causes": replan_causes + (("AC_SAFETY_ESCALATION",) if safety_replan else ()),
                "full_replan_count_cumulative": state.full_replan_count,
                "communication_bytes_cumulative": state.communication_bytes,
                "communication_bytes_step": (
                    state.communication_bytes - communication_bytes_before
                ),
                "admission_plan_revision_executed": bool(admission_plan_events),
                "admission_plan_events": list(admission_plan_events),
                "admission_plan_revision_count_cumulative": (
                    state.admission_plan_revision_count
                ),
                "admission_communication_bytes_cumulative": (
                    state.admission_communication_bytes
                ),
                "workload_scheduler_policy": workload_schedule["policy"],
                "workload_started_jobs": workload_schedule["started_jobs"],
                "workload_started_gpu_by_site": workload_schedule[
                    "started_gpu_by_site"
                ],
                "scheduler_started_jobs_cumulative": (
                    state.scheduler_started_jobs_cumulative
                ),
                "capacity_blocked_queue": bool(capacity_wait_after_step),
                "planned_temporal_wait_jobs": len(planned_wait_after_step),
                "capacity_blocked_jobs": len(capacity_wait_after_step),
                "queued_jobs": len(queued_after_step),
                "queued_gpu_by_site": {
                    site: sum(
                        job.source.requested_gpu
                        for job in queued_after_step
                        if job.destination_idc == site
                    )
                    for site in IDCS
                },
                "running_gpu_by_site": {
                    site: sum(
                        job.source.requested_gpu
                        for job in state.jobs.values()
                        if job.lifecycle == "RUNNING"
                        and job.destination_idc == site
                    )
                    for site in IDCS
                },
                "capacity_queue_wait_job_steps_cumulative": (
                    state.capacity_queue_wait_job_steps_cumulative
                ),
                "planned_temporal_wait_job_steps_cumulative": (
                    state.planned_temporal_wait_job_steps_cumulative
                ),
                "maximum_queue_wait_steps": max(
                    (job.queue_wait_steps for job in state.jobs.values()),
                    default=0,
                ),
                "late_started_jobs": sum(
                    job.start_issue is not None
                    and job.start_issue > job.source.latest_start_step
                    for job in state.jobs.values()
                ),
                "wan_transferred_bytes_cumulative": state.wan_transferred_bytes_cumulative,
                "wan_active_transfers": state.wan_active_transfers,
                "wan_bytes_transferred_step": (
                    migration_progress["bytes_transferred"]
                    + prestart_wan_progress["bytes_transferred"]
                ),
                "prestart_wan_completed": prestart_wan_progress[
                    "completed_prefetches"
                ],
                "prestart_wan_bytes_transferred_step_by_job": (
                    prestart_wan_progress["bytes_transferred_by_job"]
                ),
                "migration_count_cumulative": state.migration_count_cumulative,
                "migration_started": list(migration_started_events),
                "prestart_spatial_placements": list(prestart_placement_events),
                "migration_completed": migration_progress["completed_migrations"],
                "migration_restarts_completed": migration_progress["completed_restarts"],
                "migration_prediction_actual_events": migration_progress[
                    "completed_realizations"
                ],
                "migration_prediction_actual_event_count": len(
                    migration_progress["completed_realizations"]
                ),
                "migration_duration_prediction_error_steps": sum(
                    int(event["total_downtime_error_steps"])
                    for event in migration_progress["completed_realizations"]
                ),
                "migration_duration_absolute_error_steps": sum(
                    abs(int(event["total_downtime_error_steps"]))
                    for event in migration_progress["completed_realizations"]
                ),
                "migration_duration_prediction_error_seconds": sum(
                    int(event["total_downtime_error_seconds"])
                    for event in migration_progress["completed_realizations"]
                ),
                "migration_duration_absolute_error_seconds": sum(
                    abs(int(event["total_downtime_error_seconds"]))
                    for event in migration_progress["completed_realizations"]
                ),
                "migration_job_state_evidence": {
                    uid: {
                        "lifecycle": job.lifecycle,
                        "destination_idc": job.destination_idc,
                        "checkpoint_state": job.checkpoint_state,
                        "migration_state": job.migration_state,
                        "remaining_work_gpu_hours": job.remaining_work_gpu_hours,
                    }
                    for uid, job in sorted(state.jobs.items())
                    if job.migration_state
                    not in {
                        "NOT_REQUESTED",
                        "ELIGIBLE_AT_AUTHORIZED_CHECKPOINT",
                    }
                },
                "wan_transfer_authority": (
                    self.migration_authority.authority_id
                    if config.spatial_workload_migration
                    and self.migration_authority is not None
                    else "NOT_APPLICABLE_METHOD_CAPABILITY_DISABLED"
                ),
                "risk_interface": risk.active_risk_interface,
                "risk": risk.active_risk,
                "risk_components": risk.calibrated_components if config.risk_interface == "CALIBRATED" else risk.raw_components,
                "risk_raw_components": dict(risk.raw_components),
                "risk_calibrated_components": dict(risk.calibrated_components),
                "risk_calibration_authority_id": (
                    self.risk_calibration_authority.authority_id
                    if self.risk_calibration_authority is not None
                    else None
                ),
                "risk_calibration_artifact_sha256": (
                    self.risk_calibration_authority.artifact_sha256
                    if self.risk_calibration_authority is not None
                    else None
                ),
                "risk_calibration_audit": risk_calibration_audit,
                "arrivals": len(frame.arrivals),
                "active_jobs": sum(job.lifecycle == "RUNNING" for job in state.jobs.values()),
                "completed_jobs": sum(job.lifecycle == "COMPLETED" for job in state.jobs.values()),
                "deadline_misses": deadline_misses,
                "deadline_missed_job_ids": deadline_missed_job_ids,
                "remaining_work_gpu_hours": sum(job.remaining_work_gpu_hours for job in state.jobs.values()),
                "spatial_actions_blocked_missing_payload": blocked_spatial,
                "checkpoint_authority": (
                    self.migration_authority.authority_id
                    if config.spatial_workload_migration
                    and self.migration_authority is not None
                    else "NOT_APPLICABLE_METHOD_CAPABILITY_DISABLED"
                ),
                "migration_payload_authority": (
                    self.migration_authority.fingerprint
                    if config.spatial_workload_migration
                    and self.migration_authority is not None
                    else "NOT_APPLICABLE_METHOD_CAPABILITY_DISABLED"
                ),
                "spatial_optimizer_certificate": dict(
                    state.last_spatial_optimizer_certificate
                ),
                "facility_p_kw_total": sum(facility_p),
                "background_root_kw": frame.q50_background_p_kw,
                # No frozen auxiliary-power coefficient exists for WAN equipment.
                # Transfer energy therefore remains explicitly unavailable rather
                # than being assigned an invented electrical load.
                "wan_power_kw": None,
                "mess_p_kw_total": sum(fast.control.mess_discharge_kw.values()) - sum(fast.control.mess_charge_kw.values()),
                "mess_q_kvar_total": sum(fast.control.mess_q_kvar.values()),
                "minimum_mess_energy_kwh": min(state.mess_energy_kwh.values()),
                "planned_mobility_energy_kwh": sum(
                    float(event["planned_mobility_energy_kwh"])
                    for event in mobility_started_events
                ),
                "reserved_safe_mobility_energy_kwh": sum(
                    float(event["reserved_safe_mobility_energy_kwh"])
                    for event in mobility_started_events
                ),
                "realized_mobility_energy_kwh": realized_mobility_energy_kwh,
                "mobility_energy_kwh": realized_mobility_energy_kwh,
                "mobility_realized_route_total_energy_kwh_started_routes": sum(
                    float(event["realized_mobility_energy_route_total_kwh"])
                    for event in mobility_started_events
                ),
                "mobility_realized_protected_floor_shortfall_kwh_started_routes": sum(
                    float(event["realized_protected_floor_shortfall_kwh"])
                    for event in mobility_started_events
                ),
                "mobility_realized_protected_floor_violation_route_count": sum(
                    not bool(event["realized_route_protected_floor_feasible"])
                    for event in mobility_started_events
                ),
                "mobility_q50_eta_prediction_error_seconds_started_routes": sum(
                    float(event["q50_eta_prediction_error_seconds"])
                    for event in mobility_started_events
                ),
                "mobility_q50_eta_absolute_error_seconds_started_routes": sum(
                    float(event["q50_eta_absolute_error_seconds"])
                    for event in mobility_started_events
                ),
                "mobility_planning_eta_prediction_error_seconds_started_routes": sum(
                    float(event["planning_eta_prediction_error_seconds"])
                    for event in mobility_started_events
                ),
                "mobility_planning_eta_absolute_error_seconds_started_routes": sum(
                    float(event["planning_eta_absolute_error_seconds"])
                    for event in mobility_started_events
                ),
                "mobility_q50_energy_prediction_error_kwh_started_routes": sum(
                    float(event["q50_energy_prediction_error_kwh"])
                    for event in mobility_started_events
                ),
                "mobility_q50_energy_absolute_error_kwh_started_routes": sum(
                    float(event["q50_energy_absolute_error_kwh"])
                    for event in mobility_started_events
                ),
                "mobility_planning_energy_prediction_error_kwh_started_routes": sum(
                    float(event["planning_energy_prediction_error_kwh"])
                    for event in mobility_started_events
                ),
                "mobility_planning_energy_absolute_error_kwh_started_routes": sum(
                    float(event["planning_energy_absolute_error_kwh"])
                    for event in mobility_started_events
                ),
                "mobility_safe_eta_covered_started_routes": sum(
                    bool(event["safe_eta_realization_covered"])
                    for event in mobility_started_events
                ),
                "mobility_safe_energy_covered_started_routes": sum(
                    bool(event["safe_energy_realization_covered"])
                    for event in mobility_started_events
                ),
                "mobility_started_route_count": len(mobility_started_events),
                "mobility_started_events": list(mobility_started_events),
                "mobility_execution_actual_used_by_optimizer": False,
                "mobility_execution_actual_opened_post_decision_only": bool(
                    mobility_started_events
                ),
                "mobility_realized_actual_used_by_execution": bool(
                    mobility_started_events
                    or realized_mobility_energy_kwh > 0.0
                ),
                "mobility_execution_authority_sha256": (
                    self.mobility_execution_authority.fingerprint
                    if self.mobility_execution_authority is not None
                    else None
                ),
                "mess_in_transit": dict(state.mess_in_transit),
                "mess_location": dict(state.mess_location),
                "mess_energy_kwh": dict(state.mess_energy_kwh),
                "mess_route_destination": dict(state.mess_route_destination),
                "mess_route_rank": dict(state.mess_route_rank),
                "mobility_completed": {
                    mid: bool(
                        mess_in_transit_before_execution[mid]
                        and not state.mess_in_transit[mid]
                    )
                    for mid in MESS_IDS
                },
                "slow_miqp_certificate": dict(state.last_slow_miqp_certificate),
                "joint_uncertainty_decision_use": config.joint_uncertainty,
                "risk_grid_envelope_source": (
                    "PREVIOUS_ISSUE_CAUSAL_ROBUST_ENVELOPE"
                    if config.joint_uncertainty and risk_used_previous_grid_envelope
                    else "REALIZED_PREVIOUS_ISSUE_OR_INITIAL_DEFAULT"
                ),
                "risk_grid_envelope_lag_steps": (
                    1 if risk_used_previous_grid_envelope else None
                ),
                "workload_reserve_gpu": dict(frame.workload_reserve_gpu) if config.joint_uncertainty else {},
                "robust_grid_fresh_opendss": bool(
                    verifier.last_commit.raw_metrics.get("robust_grid_fresh_opendss", False)
                ),
                "native_grid_control_authority": verifier.last_commit.raw_metrics.get(
                    "native_grid_control_authority"
                ),
                "native_capcontrol_count": int(
                    verifier.last_commit.raw_metrics.get("native_capcontrol_count", 0)
                ),
                "native_capacitor_states": dict(
                    verifier.last_commit.raw_metrics.get(
                        "native_capacitor_states", {}
                    )
                ),
                "native_grid_control_decision": dict(native_decision.raw_metrics),
                "native_grid_control_execution_order": (
                    "COMMON_DISCRETE_TRANSITION_ALTERNATING_WITH_FIXED_STATE_CONTINUOUS_AC_PROJECTION"
                ),
                "native_capacitor_dwell_remaining_steps": dict(
                    state.native_capacitor_dwell_remaining_steps
                ),
                "native_capacitor_switch_count_cumulative": dict(
                    state.native_capacitor_switch_count
                ),
                "native_regulator_tap_numbers": dict(
                    verifier.last_commit.raw_metrics.get(
                        "native_regulator_tap_numbers", {}
                    )
                ),
                "compute_debt_gpu_hours": state.compute_debt_gpu_hours,
                "energy_debt_kwh": state.energy_debt_kwh,
                "recovery_horizon_remaining": max(
                    0, PLANNING_HORIZON_STEPS - int(plan_age_for_action)
                ),
                "compute_debt_target": 0.0,
                "energy_debt_target": 0.0,
                "terminal_recovery_feasible": bool(
                    state.compute_debt_gpu_hours <= 1e-9
                    and state.energy_debt_kwh <= 1e-9
                ) if offset == len(frames) - 1 else None,
                "joint_plan_control": asdict(nominal),
                "planned_control": asdict(pre_safety_control),
                "accepted_control": asdict(fast.control),
                "job_states": {
                    uid: {
                        "origin_idc": job.source.origin_idc,
                        "arrival_issue": job.source.arrival_step,
                        "latest_start_issue": job.source.latest_start_step,
                        "deadline_issue": job.source.deadline_step,
                        "required_gpu": job.source.requested_gpu,
                        "destination_idc": job.destination_idc,
                        "planned_idc": state.active_plan.job_idc_placement.get(uid),
                        "planned_start_issue": state.active_plan.job_start_issue.get(uid),
                        "remaining_work_gpu_hours": job.remaining_work_gpu_hours,
                        "lifecycle": job.lifecycle,
                        "compute_rate_fraction": job.compute_rate_fraction,
                        "checkpoint_state": job.checkpoint_state,
                        "migration_state": job.migration_state,
                        "migration_source_idc": job.migration_source_idc,
                        "migration_destination_idc": job.migration_destination_idc,
                        "migration_payload_remaining_bytes": job.migration_payload_remaining_bytes,
                        "restart_remaining_steps": job.restart_remaining_steps,
                        "prestart_wan_target_idc": job.prestart_wan_target_idc,
                        "prestart_wan_required_bytes": (
                            job.prestart_wan_required_bytes
                        ),
                        "prestart_wan_transferred_bytes": (
                            job.prestart_wan_transferred_bytes
                        ),
                    }
                    for uid, job in sorted(state.jobs.items())
                },
                "slow_solver_time_s": slow_solver_time_s,
                "fast_recourse_runtime_seconds": fast.runtime_seconds,
                "safety_filter_runtime_seconds": safety.filter_runtime_seconds,
                "opendss_runtime_seconds": verifier.opendss_runtime_seconds,
                "safety_filter_intervention": safety.intervention,
                "safety_filter_delta_p_kw": safety.delta_p_kw,
                "safety_filter_delta_q_kvar": safety.delta_q_kvar,
                "safety_filter_compute_throttling_fraction": safety.compute_throttling_fraction,
                "safety_filter_compute_load_increase_fraction": safety.compute_load_increase_fraction,
                "safety_filter_stage": (
                    "ESCALATED_FULL_REPLAN"
                    if safety.escalation_count
                    else ("CONTINUOUS_PROJECTION" if safety.intervention else "NONE")
                ),
                "safety_action_delta_norm": math.sqrt(
                    safety.delta_p_kw * safety.delta_p_kw
                    + safety.delta_q_kvar * safety.delta_q_kvar
                    + safety.compute_throttling_fraction
                    * safety.compute_throttling_fraction
                    + safety.compute_load_increase_fraction
                    * safety.compute_load_increase_fraction
                ),
                "safety_filter_escalation_count": safety.escalation_count,
                "safety_capability_mess_enabled": config.energy_flexibility
                in {"MESS", "STATIONARY_BESS"},
                "safety_capability_compute_throttle_enabled": config.temporal_workload_shift,
                "fresh_exact_opendss": True,
                "actual_gurobi_used": active_optimization.certificate.actual_gurobi_used,
                "optimization_certificate": active_optimization.certificate.as_dict(),
                "actual_fresh_opendss_used": verifier.last_commit.actual_fresh_opendss_used,
                "exact_ac": dict(verifier.last_commit.raw_metrics),
                "optimization_objective_authority": OBJECTIVE_AUTHORITY,
                "realized_exact_electrical_stress": (
                    exact_electrical_stress.as_dict()
                ),
                "price_aud_per_mwh": frame.current_price_aud_per_mwh,
                "realized_grid_cost_aud": step_grid_cost_aud,
                "cumulative_grid_cost_aud": cumulative_grid_cost_aud,
                "attempt_id": identity.result_uid,
                "parent_attempt_id": None,
                "retry_count": 0,
                "runtime_seconds": time.monotonic() - started,
            }
            issue_root = method_root / f"issue_{frame.issue:06d}"
            issue_root.mkdir(parents=True, exist_ok=True)
            atomic_write_json(issue_root / "COMMIT_MARKER.json", record)
            records.append(record)
        summary = {
            "schema_version": "K9H7_RESULT_V2.method_run.v2",
            "status": "PASS" if failure is None and len(records) == len(frames) else "FAIL_CLOSED",
            "comparison_method_id": config.comparison_method_id.value,
            "method_order": int(config.comparison_method_id.value[1:]),
            "factorial_energy": (
                int(config.energy_flexibility == "MESS")
                if config.comparison_method_id.value in {"B00", "B01", "B04", "B06"}
                else None
            ),
            "factorial_compute": (
                int(
                    config.temporal_workload_shift
                    and config.spatial_workload_migration
                )
                if config.comparison_method_id.value in {"B00", "B01", "B04", "B06"}
                else None
            ),
            "representative_week_id": representative_week_id,
            "requested_issues": len(frames),
            "committed_issues": len(records),
            "commit_marker_count": len(records),
            "fresh_exact_opendss_count": sum(row["actual_fresh_opendss_used"] for row in records),
            "actual_gurobi_count": sum(row["actual_gurobi_used"] for row in records),
            "optimization_objective_authority": OBJECTIVE_AUTHORITY,
            "realized_exact_electrical_stress": trajectory_summary(
                (
                    stress_from_extrema(
                        minimum_voltage_pu=float(row["exact_ac"]["voltage_min_pu"]),
                        maximum_voltage_pu=float(row["exact_ac"]["voltage_max_pu"]),
                        maximum_line_loading_fraction=float(
                            row["exact_ac"]["line_max_loading_pu"]
                        ),
                        maximum_transformer_loading_fraction=max(
                            float(
                                row["exact_ac"][
                                    "transformer_max_kva_loading_pu"
                                ]
                            ),
                            float(
                                row["exact_ac"][
                                    "transformer_max_current_loading_pu"
                                ]
                            ),
                        ),
                    )
                    for row in records
                ),
                step_hours=STEP_HOURS,
            ),
            "state_chain_complete": all(
                records[index]["post_state_sha256"] == records[index + 1]["pre_state_sha256"]
                for index in range(max(0, len(records) - 1))
            ),
            "binary_state_unchanged": all(row["binary_state_unchanged"] for row in records),
            "future_actual_used": False,
            "future_actual_used_by_optimizer": False,
            "mobility_execution_authority_sha256": (
                self.mobility_execution_authority.fingerprint
                if self.mobility_execution_authority is not None
                else None
            ),
            "mobility_realized_actual_used_by_execution": any(
                row["mobility_realized_actual_used_by_execution"]
                for row in records
            ),
            "full_replan_count": state.full_replan_count,
            "communication_bytes": state.communication_bytes,
            "admission_plan_revision_count": state.admission_plan_revision_count,
            "admission_communication_bytes": state.admission_communication_bytes,
            "scheduler_started_jobs": state.scheduler_started_jobs_cumulative,
            "capacity_queue_wait_job_steps": (
                state.capacity_queue_wait_job_steps_cumulative
            ),
            "planned_temporal_wait_job_steps": (
                state.planned_temporal_wait_job_steps_cumulative
            ),
            "final_queued_jobs": sum(
                job.lifecycle == "QUEUED" for job in state.jobs.values()
            ),
            "migration_count": state.migration_count_cumulative,
            "wan_transferred_bytes": state.wan_transferred_bytes_cumulative,
            "migration_prediction_actual_event_count": sum(
                int(row["migration_prediction_actual_event_count"])
                for row in records
            ),
            "migration_duration_mean_absolute_error_steps": (
                sum(
                    float(row["migration_duration_absolute_error_steps"])
                    for row in records
                )
                / sum(
                    int(row["migration_prediction_actual_event_count"])
                    for row in records
                )
                if sum(
                    int(row["migration_prediction_actual_event_count"])
                    for row in records
                )
                else None
            ),
            "migration_duration_mean_absolute_error_seconds": (
                sum(
                    float(row["migration_duration_absolute_error_seconds"])
                    for row in records
                )
                / sum(
                    int(row["migration_prediction_actual_event_count"])
                    for row in records
                )
                if sum(
                    int(row["migration_prediction_actual_event_count"])
                    for row in records
                )
                else None
            ),
            "migration_authority_sha256": (
                self.migration_authority.fingerprint
                if self.migration_authority is not None
                else None
            ),
            "mobility_started_route_count": sum(
                int(row["mobility_started_route_count"]) for row in records
            ),
            "mobility_realized_protected_floor_shortfall_kwh_started_routes": sum(
                float(
                    row[
                        "mobility_realized_protected_floor_shortfall_kwh_started_routes"
                    ]
                )
                for row in records
            ),
            "mobility_realized_protected_floor_violation_route_count": sum(
                int(row["mobility_realized_protected_floor_violation_route_count"])
                for row in records
            ),
            "mobility_q50_eta_mean_absolute_error_seconds": (
                sum(
                    float(
                        row[
                            "mobility_q50_eta_absolute_error_seconds_started_routes"
                        ]
                    )
                    for row in records
                )
                / sum(int(row["mobility_started_route_count"]) for row in records)
                if sum(int(row["mobility_started_route_count"]) for row in records)
                else None
            ),
            "mobility_q50_energy_mean_absolute_error_kwh": (
                sum(
                    float(
                        row[
                            "mobility_q50_energy_absolute_error_kwh_started_routes"
                        ]
                    )
                    for row in records
                )
                / sum(int(row["mobility_started_route_count"]) for row in records)
                if sum(int(row["mobility_started_route_count"]) for row in records)
                else None
            ),
            "mobility_planning_eta_mean_absolute_error_seconds": (
                sum(
                    float(
                        row[
                            "mobility_planning_eta_absolute_error_seconds_started_routes"
                        ]
                    )
                    for row in records
                )
                / sum(int(row["mobility_started_route_count"]) for row in records)
                if sum(int(row["mobility_started_route_count"]) for row in records)
                else None
            ),
            "mobility_planning_energy_mean_absolute_error_kwh": (
                sum(
                    float(
                        row[
                            "mobility_planning_energy_absolute_error_kwh_started_routes"
                        ]
                    )
                    for row in records
                )
                / sum(int(row["mobility_started_route_count"]) for row in records)
                if sum(int(row["mobility_started_route_count"]) for row in records)
                else None
            ),
            "mobility_safe_eta_empirical_coverage": (
                sum(
                    int(row["mobility_safe_eta_covered_started_routes"])
                    for row in records
                )
                / sum(int(row["mobility_started_route_count"]) for row in records)
                if sum(int(row["mobility_started_route_count"]) for row in records)
                else None
            ),
            "mobility_safe_energy_empirical_coverage": (
                sum(
                    int(row["mobility_safe_energy_covered_started_routes"])
                    for row in records
                )
                / sum(int(row["mobility_started_route_count"]) for row in records)
                if sum(int(row["mobility_started_route_count"]) for row in records)
                else None
            ),
            "deadline_misses": sum(row["deadline_misses"] for row in records[-1:]),
            "final_compute_debt_gpu_hours": state.compute_debt_gpu_hours,
            "final_energy_debt_kwh": state.energy_debt_kwh,
            "final_minimum_mess_energy_kwh": min(state.mess_energy_kwh.values()),
            "risk_calibration_audit_count": sum(
                row.get("risk_calibration_audit") is not None for row in records
            ),
            "risk_calibration_day_joint_score": max(
                (
                    float(row["risk_calibration_audit"]["joint_normalized_score"])
                    for row in records
                    if row.get("risk_calibration_audit") is not None
                ),
                default=None,
            ),
            "risk_calibration_authority_id": (
                self.risk_calibration_authority.authority_id
                if self.risk_calibration_authority is not None
                else None
            ),
            "risk_calibration_artifact_sha256": (
                self.risk_calibration_authority.artifact_sha256
                if self.risk_calibration_authority is not None
                else None
            ),
            "final_mess_in_transit": dict(state.mess_in_transit),
            "terminal_mobility_complete": not any(state.mess_in_transit.values()),
            "failure": failure,
        }
        if records:
            component_maxima = {
                name: max(
                    float(row["realized_exact_electrical_stress"][key])
                    for row in records
                )
                for name, key in (
                    ("daily_max_voltage_stress", "voltage_stress_pu"),
                    ("daily_max_line_stress", "line_stress_pu"),
                    ("daily_max_transformer_stress", "transformer_stress_pu"),
                )
            }
            runtimes = sorted(float(row["runtime_seconds"]) for row in records)
            solver_runtimes = sorted(
                float(row["slow_solver_time_s"]) for row in records
            )
            p95_index = max(0, math.ceil(0.95 * len(runtimes)) - 1)
            summary.update(
                {
                    **component_maxima,
                    "daily_max_ac_stress": summary[
                        "realized_exact_electrical_stress"
                    ]["worst_electrical_stress_pu"],
                    "daily_ac_stress_exposure": summary[
                        "realized_exact_electrical_stress"
                    ]["electrical_stress_exposure_pu_hours"],
                    "daily_peak_root_import_kw": max(
                        float(row["exact_ac"]["root_import_p_kw"])
                        for row in records
                    ),
                    "daily_rebound_peak_kw": None,
                    "daily_rebound_energy_kwh": None,
                    "grid_cost_aud": sum(
                        float(row["realized_grid_cost_aud"]) for row in records
                    ),
                    "deadline_miss_count": len(
                        {
                            uid
                            for row in records
                            for uid in row["deadline_missed_job_ids"]
                        }
                    ),
                    "total_deadline_misses": len(
                        {
                            uid
                            for row in records
                            for uid in row["deadline_missed_job_ids"]
                        }
                    ),
                    "terminal_compute_debt": float(
                        records[-1]["compute_debt_gpu_hours"]
                    ),
                    "terminal_energy_debt_kwh": float(
                        records[-1]["energy_debt_kwh"]
                    ),
                    "mess_move_count": sum(
                        int(row["mobility_started_route_count"]) for row in records
                    ),
                    "workload_temporal_shift_count": len(
                        {
                            uid
                            for row in records
                            for uid, job in row["job_states"].items()
                            if job.get("planned_start_issue") is not None
                            and job.get("arrival_issue") is not None
                            and int(job["planned_start_issue"])
                            > int(job["arrival_issue"])
                        }
                    ),
                    "planned_temporal_wait_job_steps": int(
                        state.planned_temporal_wait_job_steps_cumulative
                    ),
                    "workload_migration_count": int(
                        state.migration_count_cumulative
                    ),
                    "checkpoint_count": len(
                        {
                            uid
                            for row in records
                            for uid, job in row["job_states"].items()
                            if str(job.get("checkpoint_state"))
                            in {"READY", "CONSUMED_BY_MIGRATION"}
                        }
                    ),
                    "wan_transfer_gb": float(
                        state.wan_transferred_bytes_cumulative
                    ) / 1e9,
                    "fast_recourse_count": len(records),
                    "solver_time_p95_s": solver_runtimes[p95_index],
                    "total_control_time_p95_s": runtimes[p95_index],
                    "safety_filter_intervention_count": sum(
                        bool(row["safety_filter_intervention"])
                        for row in records
                    ),
                    "mobility_completed_count": sum(
                        sum(bool(value) for value in row["mobility_completed"].values())
                        for row in records
                    ),
                }
            )
        atomic_write_json(method_root / "METHOD_SUMMARY.json", summary)
        atomic_write_json(method_root / "DAILY_SUMMARY.json", summary)
        if records:
            fields = tuple(records[0])
            with (method_root / "MATERIALIZED_COMMIT_ROWS.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for row in records:
                    writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list, tuple)) else value for key, value in row.items()})
            materialize_method_results(method_root, records, summary)
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
        method_axis = tuple(config.comparison_method_id for config in configs)
        allowed_axes = (
            MAIN_COMPARISON_METHODS,
            tuple(ElectricalStressMethod(f"B{index:02d}") for index in range(10)),
        )
        if method_axis not in allowed_axes:
            raise RuntimeContractError(
                "runtime matrix must execute historical B0-B7 or stress B00-B09 in frozen order"
            )
        summaries = []
        for config in configs:
            try:
                summary = self.run_method(
                    config=config,
                    frames=frames,
                    initial=initial,
                    representative_week_id=representative_week_id,
                    output=output,
                )
            except Exception as exc:
                method_root = output / config.comparison_method_id.value
                method_root.mkdir(parents=True, exist_ok=True)
                partial_records = []
                invalid_partial_markers = []
                for marker_path in sorted(
                    method_root.glob("issue_*/COMMIT_MARKER.json")
                ):
                    try:
                        candidate = json.loads(marker_path.read_text(encoding="utf-8"))
                        if (
                            candidate.get("status") != "PASS_COMMITTED"
                            or candidate.get("commit_marker") is not True
                            or candidate.get("comparison_method_id")
                            != config.comparison_method_id.value
                        ):
                            raise ValueError("marker contract mismatch")
                        candidate["issue"] = int(candidate["issue"])
                        if not candidate.get("pre_state_sha256") or not candidate.get(
                            "post_state_sha256"
                        ):
                            raise ValueError("marker state-chain hashes are missing")
                        partial_records.append(candidate)
                    except (
                        OSError,
                        KeyError,
                        ValueError,
                        TypeError,
                        json.JSONDecodeError,
                    ) as marker_exc:
                        invalid_partial_markers.append(
                            {
                                "path": str(marker_path),
                                "error": f"{type(marker_exc).__name__}: {marker_exc}",
                            }
                        )
                partial_records.sort(key=lambda row: int(row["issue"]))
                next_issue = (
                    int(partial_records[-1]["issue"]) + 1
                    if partial_records
                    else int(initial.issue)
                )
                failed_attempt_id = canonical_hash(
                    {
                        "output": str(method_root.resolve()),
                        "comparison_method_id": config.comparison_method_id.value,
                        "representative_week_id": representative_week_id,
                        "next_issue": next_issue,
                    }
                )
                failure = {
                    "status": "FAIL_CLOSED_EXCEPTION",
                    "comparison_method_id": config.comparison_method_id.value,
                    "issue": next_issue,
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "failure_stage": "METHOD_RUNTIME",
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                    "last_committed_issue": (
                        int(partial_records[-1]["issue"])
                        if partial_records
                        else None
                    ),
                    "attempt_id": failed_attempt_id,
                    "parent_attempt_id": None,
                    "retry_count": 0,
                    "partial_results_preserved": True,
                    "valid_partial_commit_markers": len(partial_records),
                    "invalid_partial_commit_markers": invalid_partial_markers,
                }
                atomic_write_json(method_root / "FAILURE.json", failure)
                summary = {
                    "schema_version": "K9H7_RESULT_V2.method_run.v2",
                    "status": "FAIL_CLOSED",
                    "comparison_method_id": config.comparison_method_id.value,
                    "representative_week_id": representative_week_id,
                    "requested_issues": len(frames),
                    "committed_issues": len(partial_records),
                    "commit_marker_count": len(partial_records),
                    "fresh_exact_opendss_count": sum(
                        bool(row.get("actual_fresh_opendss_used"))
                        for row in partial_records
                    ),
                    "actual_gurobi_count": sum(
                        bool(row.get("actual_gurobi_used"))
                        for row in partial_records
                    ),
                    "state_chain_complete": bool(partial_records)
                    and all(
                        partial_records[index].get("post_state_sha256")
                        == partial_records[index + 1].get("pre_state_sha256")
                        for index in range(len(partial_records) - 1)
                    ),
                    "binary_state_unchanged": bool(partial_records)
                    and all(
                        bool(row.get("binary_state_unchanged"))
                        for row in partial_records
                    ),
                    "future_actual_used": False,
                    "failure": failure,
                    "failure_stage": failure["failure_stage"],
                    "failure_reason": failure["failure_reason"],
                    "last_committed_issue": failure["last_committed_issue"],
                    "attempt_id": failed_attempt_id,
                    "parent_attempt_id": None,
                    "retry_count": 0,
                }
                atomic_write_json(method_root / "METHOD_SUMMARY.json", summary)
                atomic_write_json(method_root / "DAILY_SUMMARY.json", summary)
                materialize_method_results(method_root, partial_records, summary)
            summaries.append(summary)
        expected = len(frames) * len(configs)
        committed = sum(item["committed_issues"] for item in summaries)
        failed_methods = [
            item["comparison_method_id"]
            for item in summaries
            if item["status"] != "PASS"
        ]
        matrix = {
            "schema_version": "K9H7_RESULT_V2.matrix_run.v1",
            "status": "PASS" if committed == expected and all(item["status"] == "PASS" for item in summaries) else "FAIL_CLOSED",
            "representative_week_id": representative_week_id,
            "method_count": len(configs),
            "issues_per_method": len(frames),
            "expected_commit_markers": expected,
            "valid_commit_markers": committed,
            "all_fresh_exact_opendss": all(item["fresh_exact_opendss_count"] == len(frames) for item in summaries),
            "all_actual_gurobi": all(item["actual_gurobi_count"] == len(frames) for item in summaries),
            "all_state_chains_complete": all(item["state_chain_complete"] for item in summaries),
            "all_binary_states_unchanged_in_fast_layer": all(item["binary_state_unchanged"] for item in summaries),
            "future_actual_used": False,
            "failed_methods": failed_methods,
            "method_failures_isolated": True,
            "continue_to_next_method_after_failure": True,
            "method_execution_order": [
                config.comparison_method_id.value for config in configs
            ],
            "method_summaries": summaries,
        }
        output.mkdir(parents=True, exist_ok=True)
        atomic_write_json(output / "MATRIX_SUMMARY.json", matrix)
        materialize_campaign_summary(output, summaries)
        return matrix
