"""PFR6 three-phase AC safety projection and exact commit gate."""

from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
import time
from typing import Callable, Iterable, Optional, Protocol, Tuple

from .slow_fast import FastControl, FastLayerState, SlowDiscretePlan


class SafetyFilterContractError(ValueError):
    """Raised when a safety candidate bypasses a required physical gate."""


@dataclass(frozen=True)
class ProjectionCertificate:
    formulation: str
    phase_voltage_constraints: bool
    line_thermal_constraints: bool
    transformer_constraints: bool
    mess_pcs_circle: bool
    soc_constraints: bool
    plug_d2_constraints: bool
    training_throttle_envelope: bool
    fixed_slow_discrete_state: bool

    def validate(self) -> None:
        if self.formulation not in {"CONVEX_CONTINUOUS_QP", "CONVEX_CONTINUOUS_SOCP"}:
            raise SafetyFilterContractError("safety projection must be convex and continuous")
        gates = (
            self.phase_voltage_constraints,
            self.line_thermal_constraints,
            self.transformer_constraints,
            self.mess_pcs_circle,
            self.soc_constraints,
            self.plug_d2_constraints,
            self.training_throttle_envelope,
            self.fixed_slow_discrete_state,
        )
        if not all(gates):
            raise SafetyFilterContractError("projection certificate omits a mandatory constraint")


@dataclass(frozen=True)
class ProjectionCandidate:
    control: FastControl
    certificate: ProjectionCertificate
    slow_plan_fingerprint: str
    objective_nominal: float
    objective_projected: float
    runtime_seconds: float

    def validate(self) -> None:
        self.certificate.validate()
        values = (self.objective_nominal, self.objective_projected, self.runtime_seconds)
        if any(not math.isfinite(float(value)) for value in values) or self.runtime_seconds < 0.0:
            raise SafetyFilterContractError("projection metrics must be finite")


@dataclass(frozen=True)
class ExactAcResult:
    passed: bool
    status: str
    fresh_instance: bool
    exact_three_phase_authority: bool
    minimum_voltage_pu: float
    maximum_voltage_pu: float
    maximum_line_loading_fraction: float
    maximum_transformer_loading_fraction: float
    final_ac_violation_count: int

    def validate(self) -> None:
        values = (
            self.minimum_voltage_pu,
            self.maximum_voltage_pu,
            self.maximum_line_loading_fraction,
            self.maximum_transformer_loading_fraction,
        )
        if any(not math.isfinite(float(value)) for value in values):
            raise SafetyFilterContractError("Fresh OpenDSS metrics must be finite")
        if not self.fresh_instance or not self.exact_three_phase_authority:
            raise SafetyFilterContractError("every candidate requires Fresh Exact three-phase OpenDSS")
        if self.final_ac_violation_count < 0:
            raise SafetyFilterContractError("AC violation count cannot be negative")
        physically_safe = (
            0.95 <= self.minimum_voltage_pu <= self.maximum_voltage_pu <= 1.05
            and self.maximum_line_loading_fraction <= 1.0
            and self.maximum_transformer_loading_fraction <= 1.0
            and self.final_ac_violation_count == 0
        )
        if self.passed != physically_safe:
            raise SafetyFilterContractError("OpenDSS PASS flag conflicts with exact hard limits")


class ProjectionBackend(Protocol):
    def project(
        self,
        *,
        nominal: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
    ) -> ProjectionCandidate:
        ...


class FreshExactAcVerifier(Protocol):
    def verify_fresh(
        self,
        *,
        control: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
    ) -> ExactAcResult:
        ...


@dataclass(frozen=True)
class EscalatedCandidate:
    slow_plan: SlowDiscretePlan
    state: FastLayerState
    nominal: FastControl
    full_slow_replan_completed: bool
    fast_recourse_completed: bool


FullReplanEscalation = Callable[[], EscalatedCandidate]


@dataclass(frozen=True)
class SafetyFilterResult:
    accepted: bool
    status: str
    safe_control: Optional[FastControl]
    exact_ac: ExactAcResult
    intervention: bool
    control_distance_l2: float
    delta_p_kw: float
    delta_q_kvar: float
    compute_throttling_fraction: float
    compute_load_increase_fraction: float
    objective_degradation: float
    filter_runtime_seconds: float
    escalation_count: int
    slow_plan_fingerprint: str


def _values(control: FastControl) -> Tuple[float, ...]:
    maps = (
        control.mess_charge_kw,
        control.mess_discharge_kw,
        control.mess_q_kvar,
        control.job_compute_rate_fraction,
        control.site_throughput_fraction,
    )
    return tuple(float(value) for mapping in maps for _, value in sorted(mapping.items()))


def _difference(
    nominal: FastControl, safe: FastControl
) -> Tuple[float, float, float, float, float]:
    nominal_values, safe_values = _values(nominal), _values(safe)
    if len(nominal_values) != len(safe_values):
        raise SafetyFilterContractError("nominal and projected control dimensions differ")
    distance = math.sqrt(sum((left - right) ** 2 for left, right in zip(nominal_values, safe_values)))
    mess_ids = set(nominal.mess_charge_kw) | set(nominal.mess_discharge_kw)
    delta_p = sum(
        abs(
            (safe.mess_discharge_kw.get(key, 0.0) - safe.mess_charge_kw.get(key, 0.0))
            - (nominal.mess_discharge_kw.get(key, 0.0) - nominal.mess_charge_kw.get(key, 0.0))
        )
        for key in mess_ids
    )
    delta_q = sum(
        abs(safe.mess_q_kvar.get(key, 0.0) - nominal.mess_q_kvar.get(key, 0.0))
        for key in set(nominal.mess_q_kvar) | set(safe.mess_q_kvar)
    )
    jobs = set(nominal.job_compute_rate_fraction) | set(safe.job_compute_rate_fraction)
    throttle = max(
        (nominal.job_compute_rate_fraction.get(key, 0.0) - safe.job_compute_rate_fraction.get(key, 0.0) for key in jobs),
        default=0.0,
    )
    increase = max(
        (
            safe.job_compute_rate_fraction.get(key, 0.0)
            - nominal.job_compute_rate_fraction.get(key, 0.0)
            for key in jobs
        ),
        default=0.0,
    )
    return distance, delta_p, delta_q, max(0.0, throttle), max(0.0, increase)


class AcSafetyFilter:
    def __init__(self, *, projector: ProjectionBackend, verifier: FreshExactAcVerifier) -> None:
        self.projector = projector
        self.verifier = verifier

    def _attempt(
        self, *, nominal: FastControl, state: FastLayerState, slow_plan: SlowDiscretePlan
    ) -> Tuple[ProjectionCandidate, ExactAcResult]:
        active_nominal = nominal
        for _ in range(4):
            candidate = self.projector.project(
                nominal=active_nominal, state=state, slow_plan=slow_plan
            )
            candidate.validate()
            if candidate.slow_plan_fingerprint != slow_plan.fingerprint:
                raise SafetyFilterContractError(
                    "projection changed a fixed slow decision"
                )
            exact = self.verifier.verify_fresh(
                control=candidate.control, state=state, slow_plan=slow_plan
            )
            exact.validate()
            if exact.passed:
                return candidate, exact
            if candidate.control == active_nominal:
                break

            # The common feeder devices are discrete while the method-scoped
            # safety projection is continuous.  A projected P/Q or compute
            # action changes the physical operating point, so the native
            # device state selected before projection is no longer generally
            # valid.  Alternate the two layers, fixing the discrete state
            # during each continuous projection and Fresh-exact checking every
            # iterate.  No method capability is added by this common step.
            selector = getattr(self.verifier, "select_native_control", None)
            if selector is None:
                return candidate, exact
            previous_decision = getattr(self.verifier, "native_decision", None)
            refreshed_decision = selector(control=candidate.control)
            refreshed_exact = self.verifier.verify_fresh(
                control=candidate.control, state=state, slow_plan=slow_plan
            )
            refreshed_exact.validate()
            if refreshed_exact.passed:
                return candidate, refreshed_exact
            if (
                previous_decision is not None
                and refreshed_decision.states == previous_decision.states
                and refreshed_decision.regulator_taps
                == previous_decision.regulator_taps
            ):
                return candidate, refreshed_exact
            exact = refreshed_exact
            active_nominal = candidate.control
        # Only after the online common native search and every authorized
        # method-scoped continuous attempt remain unresolved, use the common
        # deep native restoration profile.  This adds no MESS/compute/load-
        # shedding capability and prevents native-only enumeration from
        # delaying a method's normal continuous actuator.
        deep_selector = getattr(self.verifier, "select_native_control_deep", None)
        if deep_selector is not None and not exact.passed:
            deep_selector(control=candidate.control)
            exact = self.verifier.verify_fresh(
                control=candidate.control, state=state, slow_plan=slow_plan
            )
            exact.validate()
        return candidate, exact

    def filter(
        self,
        *,
        nominal: FastControl,
        state: FastLayerState,
        slow_plan: SlowDiscretePlan,
        escalate_full_replan: Optional[FullReplanEscalation] = None,
    ) -> SafetyFilterResult:
        started = time.monotonic()
        candidate, exact = self._attempt(nominal=nominal, state=state, slow_plan=slow_plan)
        escalation_count = 0
        active_nominal, active_plan = nominal, slow_plan
        if not exact.passed and escalate_full_replan is not None:
            escalated = escalate_full_replan()
            if not escalated.full_slow_replan_completed or not escalated.fast_recourse_completed:
                raise SafetyFilterContractError("escalation must complete full replan then fast recourse")
            active_nominal, active_plan = escalated.nominal, escalated.slow_plan
            candidate, exact = self._attempt(
                nominal=active_nominal, state=escalated.state, slow_plan=active_plan
            )
            escalation_count = 1
        distance, delta_p, delta_q, throttle, compute_increase = _difference(
            active_nominal, candidate.control
        )
        accepted = exact.passed and exact.final_ac_violation_count == 0
        return SafetyFilterResult(
            accepted=accepted,
            status="AC_SAFE_ACCEPTED" if accepted else "FAIL_CLOSED_EXACT_AC_UNRESOLVED",
            safe_control=candidate.control if accepted else None,
            exact_ac=exact,
            intervention=distance > 1e-12,
            control_distance_l2=distance,
            delta_p_kw=delta_p,
            delta_q_kvar=delta_q,
            compute_throttling_fraction=throttle,
            compute_load_increase_fraction=compute_increase,
            objective_degradation=max(0.0, candidate.objective_projected - candidate.objective_nominal),
            filter_runtime_seconds=time.monotonic() - started,
            escalation_count=escalation_count,
            slow_plan_fingerprint=active_plan.fingerprint,
        )


@dataclass(frozen=True)
class FilterMetricsSummary:
    intervention_count: int
    intervention_rate: float
    control_distance_l2_sum: float
    delta_p_kw_sum: float
    delta_q_kvar_sum: float
    compute_throttling_sum: float
    compute_load_increase_sum: float
    objective_degradation_sum: float
    runtime_p50_seconds: float
    runtime_p95_seconds: float
    runtime_max_seconds: float
    final_ac_violations: int

    @classmethod
    def from_results(cls, results: Iterable[SafetyFilterResult]) -> "FilterMetricsSummary":
        frozen = tuple(results)
        if not frozen:
            raise SafetyFilterContractError("filter summary requires at least one result")
        runtimes = sorted(item.filter_runtime_seconds for item in frozen)
        p95_index = max(0, math.ceil(0.95 * len(runtimes)) - 1)
        return cls(
            intervention_count=sum(item.intervention for item in frozen),
            intervention_rate=sum(item.intervention for item in frozen) / len(frozen),
            control_distance_l2_sum=sum(item.control_distance_l2 for item in frozen),
            delta_p_kw_sum=sum(item.delta_p_kw for item in frozen),
            delta_q_kvar_sum=sum(item.delta_q_kvar for item in frozen),
            compute_throttling_sum=sum(item.compute_throttling_fraction for item in frozen),
            compute_load_increase_sum=sum(
                item.compute_load_increase_fraction for item in frozen
            ),
            objective_degradation_sum=sum(item.objective_degradation for item in frozen),
            runtime_p50_seconds=statistics.median(runtimes),
            runtime_p95_seconds=runtimes[p95_index],
            runtime_max_seconds=max(runtimes),
            final_ac_violations=sum(item.exact_ac.final_ac_violation_count for item in frozen if item.accepted),
        )
