"""Pure V35R1 forensic helpers for aligned case-table authorities."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


CASES = ("B0", "B1", "B2", "B3")
COMPARISONS = {
    "B1-B0": ("B0", "B1"),
    "B2-B0": ("B0", "B2"),
    "B3-B1": ("B1", "B3"),
    "B3-B2": ("B2", "B3"),
}
METRICS: Mapping[str, Callable[[Mapping[str, Any]], float]] = {
    "planning_objective": lambda case: float(case["objective"]),
    "planning_rho": lambda case: float(case["planning"]["rho"]),
    "fresh_rho_AC": lambda case: float(case["fresh"]["rho_max_AC"]),
    "fresh_losses_kWh": lambda case: float(case["fresh"]["losses_kwh"]),
}


@dataclass(frozen=True)
class Closure:
    metric: str
    d10: float
    d20: float
    d31: float
    d32: float
    d30: float
    left_residual: float
    right_residual: float

    @property
    def max_abs_residual(self) -> float:
        return max(abs(self.left_residual), abs(self.right_residual))


def algebraic_closure(
    cases: Mapping[str, Mapping[str, Any]],
    metric: str,
) -> Closure:
    """Compute all deltas from one same-day, same-metric case mapping."""

    if tuple(sorted(cases)) != CASES:
        raise ValueError("V35R1_CANONICAL_CASE_SET")
    try:
        getter = METRICS[metric]
    except KeyError as error:
        raise ValueError("V35R1_UNKNOWN_CLOSURE_METRIC") from error
    values = {case: getter(cases[case]) for case in CASES}
    if not np.isfinite(tuple(values.values())).all():
        raise ValueError("V35R1_NONFINITE_CLOSURE_INPUT")
    d10 = values["B1"] - values["B0"]
    d20 = values["B2"] - values["B0"]
    d31 = values["B3"] - values["B1"]
    d32 = values["B3"] - values["B2"]
    d30 = values["B3"] - values["B0"]
    return Closure(
        metric=metric,
        d10=d10,
        d20=d20,
        d31=d31,
        d32=d32,
        d30=d30,
        left_residual=(d10 + d31) - d30,
        right_residual=(d20 + d32) - d30,
    )


def aligned_day_results(
    results: Sequence[Mapping[str, Any]],
    *,
    expected_days: Sequence[str],
) -> tuple[Mapping[str, Any], ...]:
    """Fail closed on missing, duplicate, out-of-cohort, or incomplete days."""

    by_day: dict[str, Mapping[str, Any]] = {}
    for result in results:
        day = str(result["day"])
        if day in by_day:
            raise ValueError("V35R1_DUPLICATE_DAY")
        if tuple(sorted(result["cases"])) != CASES:
            raise ValueError("V35R1_INCOMPLETE_DAY_CASE_SET")
        by_day[day] = result
    if set(by_day) != set(expected_days):
        raise ValueError("V35R1_DAY_COHORT_MISMATCH")
    return tuple(by_day[day] for day in expected_days)


def validate_calibration_provenance(
    candidates: Sequence[Mapping[str, Any]],
    freeze: Mapping[str, Any],
    *,
    expected_days: Sequence[str],
) -> dict[str, Any]:
    """Prove all numerical candidate provenance ends on Apr-20."""

    expected = tuple(expected_days)
    candidate_rows = []
    leakage = []
    for artifact in candidates:
        correction = artifact["correction"]
        days = tuple(map(str, correction["calibration_days"]))
        family = str(correction["family"])
        if days != expected:
            leakage.append(family)
        candidate_rows.append({
            "family": family,
            "calibration_days": list(days),
            "max_calibration_source_date": max(days),
            "fallback_count": int(correction["fallback_count"]),
            "numeric_authority": correction.get("numeric_authority"),
        })
    if tuple(map(str, freeze["calibration_date_range"])) != (expected[0], expected[-1]):
        leakage.append("FREEZE_DATE_RANGE")
    if int(freeze.get("prospective_residual_reads_before_freeze", -1)) != 0:
        leakage.append("PROSPECTIVE_READ_COUNTER")
    return {
        "status": "PASS" if not leakage else "FAIL",
        "leakage_count": len(leakage),
        "leakage_sources": leakage,
        "max_calibration_source_date": max(row["max_calibration_source_date"] for row in candidate_rows),
        "candidate_provenance": candidate_rows,
    }


def b3_lineage_valid(
    cases: Mapping[str, Mapping[str, Any]],
    *,
    b1_b3_aidc_arrays_equal: bool,
    b0_b2_aidc_arrays_equal: bool,
    code_head_descends_fix: bool,
) -> bool:
    return bool(
        code_head_descends_fix
        and b1_b3_aidc_arrays_equal
        and b0_b2_aidc_arrays_equal
        and cases["B3"]["aidc_schedule_sha256"] == cases["B1"]["aidc_schedule_sha256"]
        and cases["B2"]["aidc_schedule_sha256"] == cases["B0"]["aidc_schedule_sha256"]
    )


def zero_mess_equivalence(
    *,
    move_count: int,
    p_kw: np.ndarray,
    q_kvar: np.ndarray,
    baseline_physical_input_sha: str,
    enabled_physical_input_sha: str,
    baseline_planning_rho: float,
    enabled_planning_rho: float,
    tolerance: float = 1e-10,
) -> dict[str, Any]:
    """Apply the physical-equivalence gate only to truly zero MESS cases."""

    p = np.asarray(p_kw, dtype=float)
    q = np.asarray(q_kvar, dtype=float)
    zero = int(move_count) == 0 and not np.any(np.abs(p) > 1e-7) and not np.any(np.abs(q) > 1e-7)
    if not zero:
        return {"applicable": False, "status": "NOT_APPLICABLE_NONZERO_MESS_ACTUATION"}
    equivalent = (
        baseline_physical_input_sha == enabled_physical_input_sha
        and abs(float(enabled_planning_rho) - float(baseline_planning_rho)) <= tolerance
    )
    return {
        "applicable": True,
        "status": "PASS" if equivalent else "FAIL",
        "physical_input_SHA_equal": baseline_physical_input_sha == enabled_physical_input_sha,
        "planning_rho_delta": float(enabled_planning_rho) - float(baseline_planning_rho),
    }


def aidc_small_effect_classification(
    effect: Mapping[str, Any],
    *,
    same_binding_asset: bool,
) -> str:
    coupling_alive = all(
        float(effect.get(name, 0.0)) > 0.0
        for name in (
            "shifted_workload_node_hours",
            "changed_workload_cells",
            "changed_execution_slot_count",
            "changed_site_count",
            "changed_rack_count",
            "sum_abs_Delta_P_AIDC",
            "sum_abs_Delta_Q_AIDC",
            "planning_grid_changed_cells",
            "fresh_grid_changed_cells",
        )
    )
    exact = (
        effect.get("solver_status_off") == "OPTIMAL"
        and effect.get("solver_status_on") == "OPTIMAL"
        and float(effect.get("unresolved_solver_gap_floor", 1.0)) == 0.0
    )
    if coupling_alive and exact and same_binding_asset:
        return "AIDC_SMALL_EFFECT_PHYSICALLY_EXPLAINED"
    return "AIDC_EFFECT_REQUIRES_DEFECT_DIAGNOSIS"


def distribution(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("V35R1_DISTRIBUTION_INPUT")
    return {
        "count": int(array.size),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "P05": float(np.quantile(array, 0.05)),
        "P95": float(np.quantile(array, 0.95)),
        "min": float(array.min()),
        "max": float(array.max()),
    }
