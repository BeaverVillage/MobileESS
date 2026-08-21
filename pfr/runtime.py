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
class CausalExperimentFrame:
    issue: int
    current_price_aud_per_mwh: float
    horizon_price_median_aud_per_mwh: float
    q50_background_p_kw: float
    q50_background_q_kvar: float
    arrivals: Tuple[OperationalTrainingJob, ...]
    exogenous_sha256: str
    future_actual_used: bool = False

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
    compute_debt_gpu_hours: float = 0.0
    energy_debt_kwh: float = 0.0
    last_exact: Optional[Mapping[str, Any]] = None


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
        facility_p_kw: Sequence[float],
        facility_q_kvar: Sequence[float],
        mess_location: Sequence[str],
    ) -> None:
        self.backend = backend
        self.issue = issue
        self.facility_p_kw = tuple(facility_p_kw)
        self.facility_q_kvar = tuple(facility_q_kvar)
        self.mess_location = tuple(mess_location)
        self.last_commit: Optional[PhysicalCommit] = None

    def verify_fresh(self, *, control: FastControl, **_: Any) -> ExactAcResult:
        mess_p = tuple(
            control.mess_discharge_kw.get(mid, 0.0) - control.mess_charge_kw.get(mid, 0.0)
            for mid in MESS_IDS
        )
        mess_q = tuple(control.mess_q_kvar.get(mid, 0.0) for mid in MESS_IDS)
        self.last_commit = self.backend.verify_fresh(
            issue=self.issue,
            facility_p_kw=self.facility_p_kw,
            facility_q_kvar=self.facility_q_kvar,
            mess_location=self.mess_location,
            mess_p_kw=mess_p,
            mess_q_kvar=mess_q,
        )
        if not self.last_commit.actual_fresh_opendss_used:
            raise RuntimeContractError("physical backend did not execute Fresh OpenDSS")
        return self.last_commit.exact


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


def _build_slow_plan(state: MutableMethodState, config: MethodConfig, issue: int) -> SlowDiscretePlan:
    jobs = {uid: job for uid, job in state.jobs.items() if job.lifecycle != "COMPLETED"}
    plan = SlowDiscretePlan(
        plan_id=f"{config.comparison_method_id.value}-{issue}-{state.full_replan_count + 1}",
        valid_from_issue=issue,
        mess_destination=dict(state.mess_location),
        mess_native_route_rank={mid: 1 for mid in MESS_IDS},
        job_idc_placement={uid: job.destination_idc for uid, job in jobs.items()},
        checkpoint_migration={uid: None for uid in jobs},
        gpu_gang_allocation={uid: job.gang_membership for uid, job in jobs.items()},
        job_start_issue={uid: max(issue, job.source.arrival_step) for uid, job in jobs.items()},
        coarse_charging_kw={mid: (0.0,) * 54 for mid in MESS_IDS},
    )
    plan.validate()
    return plan


def _risk_decision(state: MutableMethodState, frame: CausalExperimentFrame, config: MethodConfig):
    active_jobs = [job for job in state.jobs.values() if job.lifecycle != "COMPLETED"]
    gpu_by_site = {site: sum(job.source.requested_gpu for job in active_jobs if job.destination_idc == site) for site in IDCS}
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


def _nominal_control(state: MutableMethodState, config: MethodConfig, frame: CausalExperimentFrame) -> FastControl:
    compute = {
        uid: _compute_fraction(job, frame, config)
        for uid, job in state.jobs.items()
        if job.lifecycle != "COMPLETED"
    }
    energy_enabled = config.energy_flexibility in {"MESS", "STATIONARY_BESS"}
    discharge = {
        mid: 20.0 if energy_enabled and state.mess_energy_kwh[mid] > MESS_FLOOR_KWH + 20.0 else 0.0
        for mid in MESS_IDS
    }
    return FastControl(
        mess_charge_kw={mid: 0.0 for mid in MESS_IDS},
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
                state.active_plan = _build_slow_plan(state, config, frame.issue)
                state.active_plan_age_steps = 0
                state.full_replan_count += 1
                state.communication_bytes += len(
                    json.dumps(asdict(state.active_plan), sort_keys=True, separators=(",", ":"))
                )
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
                mess_charge_limit_kw={mid: 550.0 for mid in MESS_IDS},
                mess_discharge_limit_kw={mid: 550.0 for mid in MESS_IDS},
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
                    site_gpu_capacity={site: MODELED_GPU_CAPACITY_PER_IDC for site in IDCS},
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
            for uid, fraction in fast.control.job_compute_rate_fraction.items():
                job = state.jobs[uid]
                job.compute_rate_fraction = fraction
                if fraction > 0.0 and job.lifecycle == "QUEUED":
                    job.lifecycle = "RUNNING"
                    job.start_issue = frame.issue
            facility_p, facility_q = _facility_power(state.jobs.values(), self.power_curve)
            verifier = _PhysicalVerifierAdapter(
                self.physical_backend,
                frame.issue,
                facility_p,
                facility_q,
                tuple(state.mess_location[mid] for mid in MESS_IDS),
            )
            safety = AcSafetyFilter(projector=_IdentityProjector(), verifier=verifier).filter(
                nominal=fast.control,
                state=fast.next_state,
                slow_plan=state.active_plan,
            )
            if verifier.last_commit is None:
                raise RuntimeContractError("Fresh physical verifier produced no commit evidence")
            if not safety.accepted:
                failure = {
                    "status": "FAIL_CLOSED_EXACT_AC",
                    "issue": frame.issue,
                    "comparison_method_id": config.comparison_method_id.value,
                    "exact_ac": dict(verifier.last_commit.raw_metrics),
                    "partial_results_preserved": True,
                }
                (method_root / "FAILURE.json").write_text(
                    json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                break
            for mid in MESS_IDS:
                state.mess_energy_kwh[mid] = fast.next_state.mess_soc[mid] * MESS_CAPACITY_KWH
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
                "slow_plan_fingerprint": slow_fingerprint,
                "binary_state_unchanged": fast.binary_state_unchanged,
                "full_replan_executed": replan,
                "replan_causes": replan_causes,
                "full_replan_count_cumulative": state.full_replan_count,
                "communication_bytes_cumulative": state.communication_bytes,
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
                "minimum_mess_energy_kwh": min(state.mess_energy_kwh.values()),
                "compute_debt_gpu_hours": state.compute_debt_gpu_hours,
                "energy_debt_kwh": state.energy_debt_kwh,
                "fast_recourse_runtime_seconds": fast.runtime_seconds,
                "safety_filter_runtime_seconds": safety.filter_runtime_seconds,
                "safety_filter_intervention": safety.intervention,
                "fresh_exact_opendss": True,
                "actual_gurobi_used": optimized.certificate.actual_gurobi_used,
                "optimization_certificate": optimized.certificate.as_dict(),
                "actual_fresh_opendss_used": verifier.last_commit.actual_fresh_opendss_used,
                "exact_ac": dict(verifier.last_commit.raw_metrics),
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
