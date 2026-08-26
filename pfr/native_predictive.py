"""Common predictive-native helpers with no access to realized future data."""

from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from typing import Any, Mapping, Sequence


PREDICTIVE_NATIVE_HORIZON_STEPS = 12


def normalized_hard_violation(metrics: Mapping[str, Any]) -> float:
    """Return a dimensionless merit score; Fresh AC remains the only gate."""

    residuals = (
        max(0.0, (0.95 - float(metrics["voltage_min_pu"])) / 0.05),
        max(0.0, (float(metrics["voltage_max_pu"]) - 1.05) / 0.05),
        max(0.0, float(metrics["line_max_loading_pu"]) - 1.0),
        max(0.0, float(metrics["transformer_max_loading_pu"]) - 1.0),
    )
    return sum(value * value for value in residuals)


@dataclass(frozen=True)
class PredictivePathScore:
    violation_steps: int
    maximum_violation: float
    cumulative_violation: float

    @classmethod
    def from_metrics(
        cls, rows: Sequence[Mapping[str, Any]]
    ) -> "PredictivePathScore":
        if not rows:
            raise ValueError("predictive path score requires at least one row")
        scores = tuple(normalized_hard_violation(row) for row in rows)
        if any(not math.isfinite(value) or value < 0.0 for value in scores):
            raise ValueError("predictive path violation score is invalid")
        return cls(
            violation_steps=sum(
                not bool(row.get("hard_constraint_pass", False)) for row in rows
            ),
            maximum_violation=max(scores),
            cumulative_violation=sum(scores),
        )

    def rank(self) -> tuple[int, float, float]:
        return (
            self.violation_steps,
            self.maximum_violation,
            self.cumulative_violation,
        )


def intermediate_capacitor_states(
    previous: Mapping[str, Sequence[int]],
    proposed: Mapping[str, Sequence[int]],
    locked: Sequence[str],
) -> tuple[dict[str, tuple[int, ...]], ...]:
    """Enumerate legal subsets of one proposed simultaneous cap transition."""

    prior = {
        str(name).lower(): tuple(int(value) for value in values)
        for name, values in previous.items()
    }
    target = {
        str(name).lower(): tuple(int(value) for value in values)
        for name, values in proposed.items()
    }
    if set(prior) != set(target):
        raise ValueError("previous and proposed capacitor domains differ")
    locked_names = {str(name).lower() for name in locked}
    if any(prior[name] != target[name] for name in locked_names):
        raise ValueError("proposed transition changes a dwell-locked capacitor")
    changed = tuple(
        name for name in sorted(prior) if prior[name] != target[name]
    )
    if not changed:
        return (dict(target),)
    candidates = []
    for choices in itertools.product((0, 1), repeat=len(changed)):
        state = dict(prior)
        for name, use_proposed in zip(changed, choices):
            state[name] = target[name] if use_proposed else prior[name]
        candidates.append(state)
    candidates.sort(
        key=lambda state: tuple(state[name] for name in sorted(state))
    )
    return tuple(candidates)


def capacitor_switch_count(
    previous: Mapping[str, Sequence[int]],
    candidate: Mapping[str, Sequence[int]],
) -> int:
    return sum(
        tuple(int(value) for value in candidate[name])
        != tuple(int(value) for value in previous[name])
        for name in previous
    )
