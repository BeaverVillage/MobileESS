"""Aligned H0 surrogate-versus-Fresh-AC fidelity audit.

The paper-facing horizon maximum and the realized H0 stress are different
estimands.  This module deliberately accepts only paired candidate scores from
the same causal state and compares each candidate with a designated reference
action at H0.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping


class H0FidelityError(ValueError):
    """Raised when a paired H0 audit is incomplete or non-causal."""


@dataclass(frozen=True)
class H0CandidateScore:
    state_id: str
    candidate_id: str
    surrogate_h0_stress: float
    fresh_ac_h0_stress: float
    is_reference: bool = False

    def validate(self) -> None:
        if not self.state_id or not self.candidate_id:
            raise H0FidelityError("state and candidate identifiers are required")
        if any(
            not math.isfinite(float(value)) or float(value) < 0.0
            for value in (
                self.surrogate_h0_stress,
                self.fresh_ac_h0_stress,
            )
        ):
            raise H0FidelityError("H0 stress scores must be finite and non-negative")


def _direction(value: float, tolerance: float) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def audit_h0_candidate_fidelity(
    rows: Iterable[H0CandidateScore],
    *,
    tie_tolerance: float,
    minimum_states: int,
    minimum_sign_agreement: float,
    minimum_pairwise_concordance: float,
) -> Mapping[str, object]:
    """Evaluate same-state H0 direction and candidate ranking fidelity."""

    if tie_tolerance < 0.0 or minimum_states <= 0:
        raise H0FidelityError("tie tolerance and minimum state count are invalid")
    if not 0.0 <= minimum_sign_agreement <= 1.0:
        raise H0FidelityError("sign agreement threshold must lie in [0,1]")
    if not 0.0 <= minimum_pairwise_concordance <= 1.0:
        raise H0FidelityError("ranking threshold must lie in [0,1]")

    grouped: dict[str, list[H0CandidateScore]] = {}
    for row in rows:
        row.validate()
        grouped.setdefault(row.state_id, []).append(row)
    if not grouped:
        raise H0FidelityError("H0 fidelity audit requires candidate observations")

    direction_total = 0
    direction_matches = 0
    pair_total = 0
    pair_concordant = 0
    absolute_errors: list[float] = []
    state_summaries: list[dict[str, object]] = []
    for state_id, candidates in sorted(grouped.items()):
        ids = [row.candidate_id for row in candidates]
        if len(ids) != len(set(ids)):
            raise H0FidelityError(f"duplicate candidate in state {state_id}")
        references = [row for row in candidates if row.is_reference]
        if len(references) != 1 or len(candidates) < 2:
            raise H0FidelityError(
                f"state {state_id} requires one reference and at least two candidates"
            )
        reference = references[0]
        local_direction_total = 0
        local_direction_matches = 0
        for candidate in candidates:
            absolute_errors.append(
                abs(candidate.fresh_ac_h0_stress - candidate.surrogate_h0_stress)
            )
            if candidate.is_reference:
                continue
            surrogate_delta = (
                candidate.surrogate_h0_stress
                - reference.surrogate_h0_stress
            )
            fresh_delta = (
                candidate.fresh_ac_h0_stress
                - reference.fresh_ac_h0_stress
            )
            surrogate_direction = _direction(surrogate_delta, tie_tolerance)
            fresh_direction = _direction(fresh_delta, tie_tolerance)
            local_direction_total += 1
            local_direction_matches += int(
                surrogate_direction == fresh_direction
            )
        direction_total += local_direction_total
        direction_matches += local_direction_matches

        local_pairs = 0
        local_concordant = 0
        for left_index, left in enumerate(candidates):
            for right in candidates[left_index + 1 :]:
                surrogate_direction = _direction(
                    left.surrogate_h0_stress - right.surrogate_h0_stress,
                    tie_tolerance,
                )
                fresh_direction = _direction(
                    left.fresh_ac_h0_stress - right.fresh_ac_h0_stress,
                    tie_tolerance,
                )
                local_pairs += 1
                local_concordant += int(
                    surrogate_direction == fresh_direction
                )
        pair_total += local_pairs
        pair_concordant += local_concordant
        state_summaries.append(
            {
                "state_id": state_id,
                "candidate_count": len(candidates),
                "reference_candidate_id": reference.candidate_id,
                "direction_matches": local_direction_matches,
                "direction_comparisons": local_direction_total,
                "pairwise_concordant": local_concordant,
                "pairwise_comparisons": local_pairs,
            }
        )

    sign_agreement = direction_matches / direction_total if direction_total else 0.0
    pairwise_concordance = pair_concordant / pair_total if pair_total else 0.0
    state_gate = len(grouped) >= minimum_states
    sign_gate = sign_agreement >= minimum_sign_agreement
    ranking_gate = pairwise_concordance >= minimum_pairwise_concordance
    return {
        "schema_version": "H0_SURROGATE_FIDELITY_AUDIT_V1",
        "comparison": "SAME_CAUSAL_STATE_SAME_H0_CANDIDATE_VS_REFERENCE",
        "state_count": len(grouped),
        "candidate_count": sum(len(rows) for rows in grouped.values()),
        "direction_comparisons": direction_total,
        "sign_agreement": sign_agreement,
        "pairwise_comparisons": pair_total,
        "pairwise_concordance": pairwise_concordance,
        "mean_absolute_level_error": (
            sum(absolute_errors) / len(absolute_errors)
        ),
        "maximum_absolute_level_error": max(absolute_errors),
        "tie_tolerance": tie_tolerance,
        "thresholds": {
            "minimum_states": minimum_states,
            "minimum_sign_agreement": minimum_sign_agreement,
            "minimum_pairwise_concordance": minimum_pairwise_concordance,
        },
        "gates": {
            "minimum_states": state_gate,
            "sign_agreement": sign_gate,
            "pairwise_concordance": ranking_gate,
        },
        "status": "PASS" if state_gate and sign_gate and ranking_gate else "FAIL",
        "state_summaries": state_summaries,
    }
