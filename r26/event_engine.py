"""Configurable HARD/SOFT route replanning event engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping, MutableMapping, Optional, Tuple


@dataclass(frozen=True)
class SoftMetricRule:
    name: str
    direction: str
    trigger: float
    release: float
    units: str
    tier: str = "PREDICTION_DEVIATION"

    def validate(self) -> None:
        if self.direction not in {"ABOVE", "BELOW"}:
            raise ValueError(f"{self.name}: direction must be ABOVE or BELOW")
        if not (math.isfinite(self.trigger) and math.isfinite(self.release)):
            raise ValueError(f"{self.name}: thresholds must be finite")
        if self.direction == "ABOVE" and self.release >= self.trigger:
            raise ValueError(f"{self.name}: ABOVE release must be below trigger")
        if self.direction == "BELOW" and self.release <= self.trigger:
            raise ValueError(f"{self.name}: BELOW release must be above trigger")
        if not self.units:
            raise ValueError(f"{self.name}: units are required")
        if self.tier not in {"SECURITY_MARGIN", "PREDICTION_DEVIATION", "ECONOMIC"}:
            raise ValueError(f"{self.name}: invalid event tier {self.tier}")


@dataclass(frozen=True)
class EventConfig:
    hard_flags: Tuple[str, ...]
    soft_rules: Tuple[SoftMetricRule, ...]
    soft_dwell_steps: int
    max_refresh_steps: int

    def validate(self) -> None:
        if not self.hard_flags or len(set(self.hard_flags)) != len(self.hard_flags):
            raise ValueError("hard_flags must be nonempty and unique")
        if self.soft_dwell_steps < 1 or self.max_refresh_steps < 1:
            raise ValueError("dwell and refresh steps must be positive")
        names = [rule.name for rule in self.soft_rules]
        if len(names) != len(set(names)):
            raise ValueError("soft metric names must be unique")
        for rule in self.soft_rules:
            rule.validate()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EventConfig":
        config = cls(
            hard_flags=tuple(str(item) for item in data["hard_flags"]),
            soft_rules=tuple(SoftMetricRule(**item) for item in data["soft_rules"]),
            soft_dwell_steps=int(data["soft_dwell_steps"]),
            max_refresh_steps=int(data["max_refresh_steps"]),
        )
        config.validate()
        return config


@dataclass(frozen=True)
class EventDecision:
    issue: int
    request_replan: bool
    severity: str
    reasons: Tuple[str, ...]
    hard_reasons: Tuple[str, ...]
    soft_reasons: Tuple[str, ...]
    soft_dwell_count: int
    steps_since_plan: int
    metric_state: Mapping[str, bool]

    def as_record(self) -> Mapping[str, Any]:
        return asdict(self)


class EventEngine:
    def __init__(self, config: EventConfig) -> None:
        config.validate()
        self.config = config
        self._active: MutableMapping[str, bool] = {
            rule.name: False for rule in config.soft_rules
        }
        self._soft_since_issue: Optional[int] = None

    def _update_metric(self, rule: SoftMetricRule, value: float) -> bool:
        if not math.isfinite(value):
            raise ValueError(f"non-finite event metric: {rule.name}")
        active = self._active[rule.name]
        if rule.direction == "ABOVE":
            active = value > rule.release if active else value >= rule.trigger
        else:
            active = value < rule.release if active else value <= rule.trigger
        self._active[rule.name] = active
        return active

    def evaluate(
        self,
        *,
        issue: int,
        hard_flags: Mapping[str, bool],
        soft_metrics: Mapping[str, float],
        steps_since_plan: int,
    ) -> EventDecision:
        unknown_hard = set(hard_flags) - set(self.config.hard_flags)
        if unknown_hard:
            raise ValueError(f"unconfigured hard flags: {sorted(unknown_hard)}")
        hard_reasons = tuple(
            f"HARD:{name}" for name in self.config.hard_flags if hard_flags.get(name, False)
        )
        active_soft = []
        for rule in self.config.soft_rules:
            if rule.name not in soft_metrics:
                raise ValueError(f"missing configured soft metric: {rule.name}")
            if self._update_metric(rule, float(soft_metrics[rule.name])):
                active_soft.append(f"SOFT:{rule.tier}:{rule.name}")

        if active_soft:
            if self._soft_since_issue is None:
                self._soft_since_issue = issue
            dwell = issue - self._soft_since_issue + 1
        else:
            self._soft_since_issue = None
            dwell = 0

        max_refresh = steps_since_plan >= self.config.max_refresh_steps
        soft_ready = bool(active_soft) and dwell >= self.config.soft_dwell_steps
        request = bool(hard_reasons) or soft_ready or max_refresh
        reasons = list(hard_reasons)
        if soft_ready:
            reasons.extend(active_soft)
        if max_refresh:
            reasons.append("MAX_REFRESH")
        severity = "HARD" if hard_reasons else ("SOFT" if request else "NONE")
        return EventDecision(
            issue=issue,
            request_replan=request,
            severity=severity,
            reasons=tuple(reasons),
            hard_reasons=hard_reasons,
            soft_reasons=tuple(active_soft),
            soft_dwell_count=dwell,
            steps_since_plan=steps_since_plan,
            metric_state=dict(self._active),
        )

    def mark_request_accepted(self, issue: int) -> None:
        """Restart the SOFT dwell window after a request is accepted/coalesced."""

        if any(self._active.values()):
            self._soft_since_issue = issue + 1
