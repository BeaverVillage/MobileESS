"""Predeclared static AC-fidelity correction families for V34.

Calibration accepts only Apr 1--20 B1/B3 Day-Ahead Planning/Fresh pairs.
Prospective rows may evaluate and select a family but can never alter numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable, Mapping, Sequence

import numpy as np

from .contracts import (
    CALIBRATION_CASES,
    CALIBRATION_DAYS,
    PLANNING_VMAX_PU,
    PLANNING_VMIN_PU,
    VALIDATION_DAYS,
)


def _sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _node_phase(node: str, phase: str) -> str:
    return f"{node}|{phase}"


def _node_phase_block(node: str, phase: str, block: int) -> str:
    return f"{node}|{phase}|{block}"


@dataclass(frozen=True)
class ResidualRow:
    day: str
    case: str
    slot: int
    node: str
    phase: str
    schedule_sha: str
    planning_schedule_sha: str
    fresh_schedule_sha: str
    v_plan_pu: float
    v_fresh_pu: float
    namespace: str = "DAYAHEAD"

    def validate(self) -> None:
        if self.namespace != "DAYAHEAD":
            raise ValueError("V34_ACTUAL_RESIDUAL_FORBIDDEN")
        if not 0 <= self.slot < 96 or not self.node or self.phase not in {"A", "B", "C"}:
            raise ValueError("V34_RESIDUAL_AXIS")
        if len(self.schedule_sha) != 64:
            raise ValueError("V34_RESIDUAL_SCHEDULE_SHA")
        if not (
            self.schedule_sha == self.planning_schedule_sha == self.fresh_schedule_sha
        ):
            raise ValueError("V34_PLANNING_FRESH_SCHEDULE_SHA_MISMATCH")
        if not math.isfinite(self.v_plan_pu) or not math.isfinite(self.v_fresh_pu):
            raise ValueError("V34_RESIDUAL_NONFINITE")

    @property
    def e_signed(self) -> float:
        return self.v_fresh_pu - self.v_plan_pu

    @property
    def e_up(self) -> float:
        return max(0.0, self.e_signed)

    @property
    def e_low(self) -> float:
        return max(0.0, -self.e_signed)

    @property
    def e_abs(self) -> float:
        return abs(self.e_signed)

    @property
    def block(self) -> int:
        return self.slot // 24


@dataclass(frozen=True)
class StaticCorrection:
    family: str
    up: Mapping[str, float]
    low: Mapping[str, float]
    fallback_count: int
    calibration_days: tuple[str, ...] = CALIBRATION_DAYS
    calibration_cases: tuple[str, ...] = CALIBRATION_CASES

    def value_for(self, node: str, phase: str, slot: int) -> tuple[float, float]:
        if not 0 <= slot < 96:
            raise ValueError("V34_CORRECTION_SLOT")
        if self.family == "M1":
            key = "GLOBAL"
        elif self.family == "M2":
            key = _node_phase(node, phase)
        elif self.family == "M3":
            key = _node_phase_block(node, phase, slot // 24)
        else:
            raise ValueError("V34_UNKNOWN_CORRECTION_FAMILY")
        return float(self.up[key]), float(self.low[key])

    def value(self, row: ResidualRow) -> tuple[float, float]:
        return self.value_for(row.node, row.phase, row.slot)

    def payload(self) -> dict[str, object]:
        return {
            "family": self.family,
            "up": dict(sorted(self.up.items())),
            "low": dict(sorted(self.low.items())),
            "fallback_count": self.fallback_count,
            "calibration_days": list(self.calibration_days),
            "calibration_cases": list(self.calibration_cases),
            "numeric_authority": "APR01_20_B1_B3_DAYAHEAD_ONLY",
        }

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.payload())


@dataclass(frozen=True)
class CorrectionCandidates:
    m1: StaticCorrection
    m2: StaticCorrection
    m3: StaticCorrection

    def __post_init__(self) -> None:
        if (self.m1.family, self.m2.family, self.m3.family) != ("M1", "M2", "M3"):
            raise ValueError("V34_CANDIDATE_FAMILY_ORDER")

    @property
    def freeze_sha256(self) -> str:
        return _sha({
            "calibration_end": "2025-04-20",
            "candidate_sha256": {
                "M1": self.m1.canonical_sha256,
                "M2": self.m2.canonical_sha256,
                "M3": self.m3.canonical_sha256,
            },
        })


def _checked_rows(rows: Iterable[ResidualRow], allowed_days: Sequence[str]) -> tuple[ResidualRow, ...]:
    values = tuple(rows)
    if not values:
        raise ValueError("V34_EMPTY_RESIDUAL_COHORT")
    allowed = set(allowed_days)
    for row in values:
        row.validate()
        if row.day not in allowed or row.case not in CALIBRATION_CASES:
            raise ValueError("V34_RESIDUAL_OUTSIDE_PREDECLARED_DAY_CASE_COHORT")
    return values


def calibrate_candidates(
    rows: Iterable[ResidualRow],
    expected_node_phases: Iterable[tuple[str, str]] | None = None,
) -> CorrectionCandidates:
    values = _checked_rows(rows, CALIBRATION_DAYS)
    support = set((row.node, row.phase) for row in values)
    axis = tuple(sorted(support if expected_node_phases is None else set(expected_node_phases)))
    if not support.issubset(axis):
        raise ValueError("V34_RESIDUAL_OUTSIDE_EXPECTED_NODE_PHASE_AXIS")

    global_up = max(row.e_up for row in values)
    global_low = max(row.e_low for row in values)
    m1 = StaticCorrection("M1", {"GLOBAL": global_up}, {"GLOBAL": global_low}, 0)

    m2_up: dict[str, float] = {}
    m2_low: dict[str, float] = {}
    m2_fallback = 0
    for node, phase in axis:
        local = [row for row in values if (row.node, row.phase) == (node, phase)]
        key = _node_phase(node, phase)
        if local:
            m2_up[key] = max(row.e_up for row in local)
            m2_low[key] = max(row.e_low for row in local)
        else:
            m2_up[key], m2_low[key] = global_up, global_low
            m2_fallback += 1
    m2 = StaticCorrection("M2", m2_up, m2_low, m2_fallback)

    m3_up: dict[str, float] = {}
    m3_low: dict[str, float] = {}
    m3_fallback = 0
    for node, phase in axis:
        m2_key = _node_phase(node, phase)
        for block in range(4):
            local = [
                row for row in values
                if (row.node, row.phase, row.block) == (node, phase, block)
            ]
            key = _node_phase_block(node, phase, block)
            if local:
                m3_up[key] = max(row.e_up for row in local)
                m3_low[key] = max(row.e_low for row in local)
            else:
                m3_up[key] = m2_up.get(m2_key, global_up)
                m3_low[key] = m2_low.get(m2_key, global_low)
                m3_fallback += 1
    m3 = StaticCorrection("M3", m3_up, m3_low, m3_fallback)
    return CorrectionCandidates(m1, m2, m3)


def coverage(candidate: StaticCorrection, rows: Iterable[ResidualRow]) -> dict[str, object]:
    values = _checked_rows(rows, VALIDATION_DAYS)
    up_applied, low_applied, up_excess, low_excess = [], [], [], []
    for row in values:
        up, low = candidate.value(row)
        up_applied.append(up)
        low_applied.append(low)
        up_excess.append(max(0.0, row.e_up - up))
        low_excess.append(max(0.0, row.e_low - low))
    upper_count = sum(value > 0.0 for value in up_excess)
    lower_count = sum(value > 0.0 for value in low_excess)

    def metrics(values_: list[float]) -> tuple[float, float, float]:
        array = np.asarray(values_, dtype=float)
        return float(array.mean()), float(np.quantile(array, 0.95)), float(array.max())

    up_mean, up_p95, up_max = metrics(up_applied)
    low_mean, low_p95, low_max = metrics(low_applied)
    return {
        "family": candidate.family,
        "upper_exceedance_count": upper_count,
        "lower_exceedance_count": lower_count,
        "worst_upper_exceedance": max(up_excess),
        "worst_lower_exceedance": max(low_excess),
        "mean_applied_upper_correction": up_mean,
        "p95_applied_upper_correction": up_p95,
        "max_applied_upper_correction": up_max,
        "mean_applied_lower_correction": low_mean,
        "p95_applied_lower_correction": low_p95,
        "max_applied_lower_correction": low_max,
        "mean_applied_total_correction": up_mean + low_mean,
        "fallback_count": candidate.fallback_count,
        "covering": upper_count == 0 and lower_count == 0,
        "candidate_sha256_before_validation": candidate.canonical_sha256,
    }


def evaluate_and_select(
    candidates: CorrectionCandidates,
    rows: Iterable[ResidualRow],
) -> tuple[StaticCorrection | None, dict[str, dict[str, object]], str]:
    values = tuple(rows)
    before = {item.family: item.canonical_sha256 for item in (candidates.m1, candidates.m2, candidates.m3)}
    reports = {
        item.family: coverage(item, values)
        for item in (candidates.m1, candidates.m2, candidates.m3)
    }
    covering = [item for item in (candidates.m1, candidates.m2, candidates.m3) if reports[item.family]["covering"]]
    if not covering:
        return None, reports, "STATIC_AC_FIDELITY_CORRECTION_INSUFFICIENT"
    simplest = covering[0]
    baseline = float(reports[simplest.family]["mean_applied_total_correction"])
    selected = simplest
    reason = "SIMPLEST_COVERING_FAMILY"
    if baseline > 0.0:
        for item in covering[1:]:
            value = float(reports[item.family]["mean_applied_total_correction"])
            if value <= 0.75 * baseline:
                selected = item
                reason = "MORE_COMPLEX_COVERING_FAMILY_AT_LEAST_25_PERCENT_LESS_MEAN_CORRECTION"
                break
    after = {item.family: item.canonical_sha256 for item in (candidates.m1, candidates.m2, candidates.m3)}
    if before != after:
        raise RuntimeError("V34_VALIDATION_MUTATED_CANDIDATE_NUMBERS")
    return selected, reports, reason


def bind_squared_voltage_bounds(up_correction_pu: float, low_correction_pu: float) -> tuple[float, float]:
    up = float(up_correction_pu)
    low = float(low_correction_pu)
    if not math.isfinite(up) or not math.isfinite(low) or up < 0 or low < 0:
        raise ValueError("V34_CORRECTION_MUST_BE_FINITE_NONNEGATIVE_PU")
    upper_pu = PLANNING_VMAX_PU - up
    lower_pu = PLANNING_VMIN_PU + low
    if lower_pu > upper_pu:
        raise ValueError("V34_CORRECTION_MAKES_VOLTAGE_INTERVAL_EMPTY")
    return lower_pu**2, upper_pu**2
