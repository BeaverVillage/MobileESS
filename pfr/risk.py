"""PFR5 normalized plan-validity risk and event-trigger contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable, Mapping, Tuple


class RiskContractError(ValueError):
    """Raised when risk quantities are not comparable under the frozen contract."""


class RiskFamily(str, Enum):
    SOC = "R_SOC"
    DEADLINE = "R_deadline"
    GPU = "R_GPU"
    WAN = "R_WAN"
    VOLTAGE = "R_voltage"
    THERMAL = "R_thermal"


@dataclass(frozen=True)
class RiskConstraint:
    name: str
    family: RiskFamily
    violation_margin: float
    predeclared_scale: float
    calibrated_worst_case_increment: float = 0.0
    scale_authority: str = "PFR5_PREDECLARED"

    def validate(self) -> None:
        values = (self.violation_margin, self.predeclared_scale, self.calibrated_worst_case_increment)
        if not self.name or any(not math.isfinite(float(value)) for value in values):
            raise RiskContractError("risk constraint contains missing or non-finite values")
        if self.predeclared_scale <= 0.0:
            raise RiskContractError("risk normalization scale must be positive")
        if self.calibrated_worst_case_increment < 0.0:
            raise RiskContractError("calibrated uncertainty increment cannot be negative")
        if self.scale_authority != "PFR5_PREDECLARED":
            raise RiskContractError("outcome-selected normalization scales are prohibited")

    @property
    def raw_normalized(self) -> float:
        self.validate()
        return self.violation_margin / self.predeclared_scale

    @property
    def calibrated_normalized(self) -> float:
        self.validate()
        return (self.violation_margin + self.calibrated_worst_case_increment) / self.predeclared_scale


@dataclass(frozen=True)
class ReplanCost:
    solve: float
    migration: float
    communication: float
    epsilon: float

    @property
    def total(self) -> float:
        values = (self.solve, self.migration, self.communication, self.epsilon)
        if any(not math.isfinite(float(value)) or value < 0.0 for value in values):
            raise RiskContractError("replan cost terms must be finite and non-negative")
        return sum(values)


@dataclass(frozen=True)
class RiskDecision:
    request_full_replan: bool
    trigger_causes: Tuple[str, ...]
    active_risk_interface: str
    active_risk: float
    raw_risk: float
    calibrated_risk: float
    raw_components: Mapping[str, float]
    calibrated_components: Mapping[str, float]
    expected_replan_benefit: float
    replan_cost: float
    plan_age_steps: int


class PlanValidityRiskMonitor:
    """Evaluate raw and calibrated risk without unit-mixing or tuned thresholds."""

    def __init__(self, *, calibrated: bool, maximum_refresh_steps: int) -> None:
        if maximum_refresh_steps <= 0:
            raise RiskContractError("maximum refresh must be positive")
        self.calibrated = calibrated
        self.maximum_refresh_steps = maximum_refresh_steps

    @staticmethod
    def _components(constraints: Tuple[RiskConstraint, ...], *, calibrated: bool) -> Mapping[str, float]:
        result = {family.value: -math.inf for family in RiskFamily}
        for constraint in constraints:
            value = constraint.calibrated_normalized if calibrated else constraint.raw_normalized
            result[constraint.family.value] = max(result[constraint.family.value], value)
        missing = [name for name, value in result.items() if value == -math.inf]
        if missing:
            raise RiskContractError(f"missing required risk families: {missing}")
        return result

    def evaluate(
        self,
        *,
        constraints: Iterable[RiskConstraint],
        expected_replan_benefit: float,
        replan_cost: ReplanCost,
        plan_age_steps: int,
    ) -> RiskDecision:
        frozen = tuple(constraints)
        if not frozen:
            raise RiskContractError("at least one risk constraint is required")
        if not math.isfinite(float(expected_replan_benefit)) or expected_replan_benefit < 0.0:
            raise RiskContractError("expected benefit must be finite and non-negative")
        if plan_age_steps < 0:
            raise RiskContractError("plan age cannot be negative")
        raw = self._components(frozen, calibrated=False)
        calibrated = self._components(frozen, calibrated=True)
        raw_risk = max(raw.values())
        calibrated_risk = max(calibrated.values())
        active = calibrated_risk if self.calibrated else raw_risk
        causes = []
        if active > 0.0:
            causes.append("SAFETY_RISK_POSITIVE")
        if expected_replan_benefit > replan_cost.total:
            causes.append("OPPORTUNITY_NET_BENEFIT_POSITIVE")
        if plan_age_steps >= self.maximum_refresh_steps:
            causes.append("MAXIMUM_REFRESH")
        return RiskDecision(
            request_full_replan=bool(causes),
            trigger_causes=tuple(causes),
            active_risk_interface="CALIBRATED" if self.calibrated else "RAW_UNCALIBRATED",
            active_risk=active,
            raw_risk=raw_risk,
            calibrated_risk=calibrated_risk,
            raw_components=raw,
            calibrated_components=calibrated,
            expected_replan_benefit=expected_replan_benefit,
            replan_cost=replan_cost.total,
            plan_age_steps=plan_age_steps,
        )


@dataclass(frozen=True)
class EventAudit:
    decision: RiskDecision
    communication_bytes: int
    realized_replan_was_needed: bool
    realized_event_regret: float

    def validate(self) -> None:
        if self.communication_bytes < 0:
            raise RiskContractError("communication bytes cannot be negative")
        if not math.isfinite(float(self.realized_event_regret)) or self.realized_event_regret < 0.0:
            raise RiskContractError("event regret must be finite and non-negative")


@dataclass(frozen=True)
class EventMetricsSummary:
    full_replan_count: int
    communication_bytes: int
    event_precision: float
    event_regret: float
    false_trigger_count: int
    late_trigger_count: int
    trigger_cause_counts: Mapping[str, int]
    risk_component_maxima: Mapping[str, float]

    @classmethod
    def from_audits(cls, audits: Iterable[EventAudit]) -> "EventMetricsSummary":
        frozen = tuple(audits)
        for item in frozen:
            item.validate()
        triggered = [item for item in frozen if item.decision.request_full_replan]
        true_triggers = sum(item.realized_replan_was_needed for item in triggered)
        causes: dict[str, int] = {}
        maxima = {family.value: -math.inf for family in RiskFamily}
        for item in frozen:
            for cause in item.decision.trigger_causes:
                causes[cause] = causes.get(cause, 0) + 1
            for name, value in item.decision.calibrated_components.items():
                maxima[name] = max(maxima[name], value)
        return cls(
            full_replan_count=len(triggered),
            communication_bytes=sum(item.communication_bytes for item in frozen),
            event_precision=true_triggers / len(triggered) if triggered else 1.0,
            event_regret=sum(item.realized_event_regret for item in frozen),
            false_trigger_count=sum(not item.realized_replan_was_needed for item in triggered),
            late_trigger_count=sum(
                item.realized_replan_was_needed and not item.decision.request_full_replan
                for item in frozen
            ),
            trigger_cause_counts=causes,
            risk_component_maxima=maxima,
        )
