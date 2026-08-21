"""Authority-safe opportunity-gap trigger for hierarchical replanning."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class GlobalRelaxationBound:
    value: float
    authority: str
    source_state_hash: str
    globally_valid: bool

    def validate(self, *, expected_state_hash: str) -> None:
        if not self.globally_valid:
            raise ValueError("opportunity-gap lower bound is not globally valid")
        if not math.isfinite(self.value):
            raise ValueError("opportunity-gap lower bound must be finite")
        if not self.authority:
            raise ValueError("opportunity-gap lower-bound authority is required")
        if self.source_state_hash != expected_state_hash:
            raise ValueError("opportunity-gap lower bound belongs to a different state")


@dataclass(frozen=True)
class OpportunityGapDecision:
    keep_objective: float
    global_relaxation_lower_bound: float
    opportunity_gap: float
    trigger_threshold: float
    request_full_replan: bool
    lower_bound_authority: str


def evaluate_opportunity_gap(
    *,
    keep_objective: float,
    lower_bound: GlobalRelaxationBound,
    source_state_hash: str,
    trigger_threshold: float,
) -> OpportunityGapDecision:
    """Compare the kept plan with a valid global relaxation lower bound.

    A restricted-master bound is deliberately inadmissible here unless its
    producer explicitly certifies it as global for the same causal state.
    """

    lower_bound.validate(expected_state_hash=source_state_hash)
    if not math.isfinite(keep_objective):
        raise ValueError("keep objective must be finite")
    if lower_bound.value > keep_objective:
        raise ValueError("global lower bound cannot exceed the feasible keep objective")
    if not (0.0 <= trigger_threshold < 1.0):
        raise ValueError("opportunity-gap threshold must be in [0, 1)")
    gap = max(0.0, (keep_objective - lower_bound.value) / max(1.0, abs(keep_objective)))
    return OpportunityGapDecision(
        keep_objective=float(keep_objective),
        global_relaxation_lower_bound=float(lower_bound.value),
        opportunity_gap=float(gap),
        trigger_threshold=float(trigger_threshold),
        request_full_replan=bool(gap >= trigger_threshold),
        lower_bound_authority=lower_bound.authority,
    )
