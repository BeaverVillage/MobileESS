"""Numerically explicit AIDC/MESS effect watchdogs for V35."""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

import numpy as np


def _array(value: object, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.size == 0 or not np.isfinite(result).all():
        raise ValueError(f"V35_EFFECT_ARRAY_INVALID:{name}")
    return result


def _different(a: np.ndarray, b: np.ndarray, tolerance: float = 1e-9) -> np.ndarray:
    if a.shape != b.shape:
        raise ValueError("V35_EFFECT_AXIS_MISMATCH")
    return np.abs(a - b) > tolerance


def aidc_effect_watchdog(
    *,
    comparison: str,
    off_workload: object,
    on_workload: object,
    off_p: object,
    on_p: object,
    off_q: object,
    on_q: object,
    off_planning: object,
    on_planning: object,
    off_fresh: object,
    on_fresh: object,
    objective_off: float,
    objective_on: float,
    unresolved_gap_off: float,
    unresolved_gap_on: float,
    solver_objective_tolerance: float = 1e-6,
    free_workload_count: int = 0,
    rack_site_ids: Sequence[str] | None = None,
    solver_status_off: str = "UNKNOWN",
    solver_status_on: str = "UNKNOWN",
    planning_rho_off: float | None = None,
    planning_rho_on: float | None = None,
    fresh_rho_off: float | None = None,
    fresh_rho_on: float | None = None,
) -> dict[str, object]:
    workload_off = _array(off_workload, "off_workload")
    workload_on = _array(on_workload, "on_workload")
    p_off, p_on = _array(off_p, "off_p"), _array(on_p, "on_p")
    q_off, q_on = _array(off_q, "off_q"), _array(on_q, "on_q")
    planning_off, planning_on = _array(off_planning, "off_planning"), _array(on_planning, "on_planning")
    fresh_off, fresh_on = _array(off_fresh, "off_fresh"), _array(on_fresh, "on_fresh")
    changed_workload = _different(workload_off, workload_on)
    changed_p = _different(p_off, p_on, 1e-10)
    changed_q = _different(q_off, q_on, 1e-10)
    changed_planning = _different(planning_off, planning_on, 1e-12)
    changed_fresh = _different(fresh_off, fresh_on, 1e-12)
    delta_objective = float(objective_on) - float(objective_off)
    unresolved_solver_gap_floor = abs(float(unresolved_gap_off)) + abs(float(unresolved_gap_on))
    resolution_floor = max(float(solver_objective_tolerance), unresolved_solver_gap_floor)
    resolved = abs(delta_objective) > resolution_floor
    if resolved:
        objective_effect_classification = "RESOLVED_ABOVE_SOLVER_AND_REPORTING_FLOOR"
    elif unresolved_solver_gap_floor > 0.0 and abs(delta_objective) <= unresolved_solver_gap_floor:
        objective_effect_classification = "UNRESOLVED_WITHIN_SOLVER_GAP"
    else:
        objective_effect_classification = "BELOW_REPORTING_RESOLUTION_ZERO_SOLVER_GAP"
    red_flags: list[str] = []
    if free_workload_count > 0 and not changed_workload.any():
        red_flags.append("AIDC_ON_CONTROLLABLE_DECISIONS_IDENTICAL_DESPITE_FREE_WORKLOAD")
    if changed_workload.any() and not (changed_p.any() or changed_q.any()):
        red_flags.append("AIDC_DECISIONS_DIFFER_BUT_PQ_IDENTICAL")
    if (changed_p.any() or changed_q.any()) and not changed_planning.any():
        red_flags.append("AIDC_PQ_DIFFERS_BUT_PLANNING_GRID_UNRESPONSIVE")
    if (changed_p.any() or changed_q.any()) and not changed_fresh.any():
        red_flags.append("AIDC_PQ_DIFFERS_BUT_FRESH_GRID_UNRESPONSIVE")
    if abs(delta_objective) > 0.0 and objective_effect_classification == "UNRESOLVED_WITHIN_SOLVER_GAP":
        red_flags.append("AIDC_OBJECTIVE_EFFECT_UNRESOLVED_RELATIVE_TO_SOLVER_GAP")

    changed_slots = 0
    changed_racks = 0
    changed_sites = 0
    if workload_off.ndim == 3:
        changed_slots = int(np.count_nonzero(np.any(changed_workload, axis=(0, 1))))
        changed_racks_mask = np.any(changed_workload, axis=(0, 2))
        changed_racks = int(np.count_nonzero(changed_racks_mask))
        if rack_site_ids is not None:
            if len(rack_site_ids) != workload_off.shape[1]:
                raise ValueError("V35_AIDC_RACK_SITE_AXIS")
            changed_sites = len({rack_site_ids[index] for index in np.flatnonzero(changed_racks_mask)})

    delta_workload = workload_on - workload_off
    delta_p = p_on - p_off
    delta_q = q_on - q_off
    return {
        "comparison": comparison,
        "objective_delta_on_minus_off": delta_objective,
        "objective_improvement_off_minus_on": -delta_objective,
        "relative_objective_delta": delta_objective / max(abs(float(objective_off)), 1e-12),
        "effect_resolution_floor": resolution_floor,
        "unresolved_solver_gap_floor": unresolved_solver_gap_floor,
        "objective_effect_classification": objective_effect_classification,
        "resolved_effect": resolved,
        "planning_rho_delta": float(
            np.max(planning_on) - np.max(planning_off)
            if planning_rho_off is None or planning_rho_on is None
            else float(planning_rho_on) - float(planning_rho_off)
        ),
        "fresh_rho_AC_delta": float(
            np.max(fresh_on) - np.max(fresh_off)
            if fresh_rho_off is None or fresh_rho_on is None
            else float(fresh_rho_on) - float(fresh_rho_off)
        ),
        "shifted_workload_node_hours": float(0.5 * np.sum(np.abs(delta_workload))),
        "changed_workload_cells": int(np.count_nonzero(changed_workload)),
        "changed_execution_slot_count": changed_slots,
        "changed_site_count": changed_sites,
        "changed_rack_count": changed_racks,
        "sum_abs_Delta_P_AIDC": float(np.sum(np.abs(delta_p))),
        "max_abs_Delta_P_AIDC": float(np.max(np.abs(delta_p))),
        "sum_abs_Delta_Q_AIDC": float(np.sum(np.abs(delta_q))),
        "max_abs_Delta_Q_AIDC": float(np.max(np.abs(delta_q))),
        "planning_grid_changed_cells": int(np.count_nonzero(changed_planning)),
        "fresh_grid_changed_cells": int(np.count_nonzero(changed_fresh)),
        "solver_status_off": solver_status_off,
        "solver_status_on": solver_status_on,
        "unresolved_absolute_solver_gap_off": float(unresolved_gap_off),
        "unresolved_absolute_solver_gap_on": float(unresolved_gap_on),
        "red_flags": red_flags,
        "status": "PASS" if not red_flags else "DIAGNOSE",
    }


def mess_effect_watchdog(
    *,
    comparison: str,
    p_kw: object,
    q_kvar: object,
    move_count: int,
    objective_off: float,
    objective_on: float,
    planning_rho_off: float,
    planning_rho_on: float,
    fresh_rho_off: float,
    fresh_rho_on: float,
    travel_energy_kwh: float,
    terminal_soc: Sequence[float],
    solver_records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    p = _array(p_kw, "MESS_P")
    q = _array(q_kvar, "MESS_Q")
    if p.shape != q.shape:
        raise ValueError("V35_MESS_PQ_AXIS")
    nonzero_p = np.abs(p) > 1e-7
    nonzero_q = np.abs(q) > 1e-7
    red_flags: list[str] = []
    restricted_beats_full = []
    for record in solver_records:
        restricted = record.get("restricted_stationary_objective")
        incumbent = record.get("objective_value", record.get("incumbent"))
        if restricted is None or incumbent is None:
            continue
        if float(incumbent) > float(restricted) + 1e-6:
            restricted_beats_full.append(str(record.get("mess_id", "UNKNOWN")))
    if restricted_beats_full:
        red_flags.append("MESS_FULL_MODEL_WORSE_THAN_RESTRICTED_FEASIBLE_INCUMBENT")
    if any(bool(record.get("restricted_incumbent_improves_zero", False)) and not bool(record.get("MIPStart_accepted", False)) for record in solver_records):
        red_flags.append("MESS_RESTRICTED_IMPROVEMENT_MIPSTART_NOT_ACCEPTED")
    zero_actuation = int(move_count) == 0 and not nonzero_p.any() and not nonzero_q.any()
    statuses = Counter(str(record.get("termination", record.get("solver_status", "UNKNOWN"))) for record in solver_records)
    return {
        "comparison": comparison,
        "MOVE_count": int(move_count),
        "PQ_nonzero_slot_count": int(np.count_nonzero(np.any(nonzero_p | nonzero_q, axis=tuple(range(1, p.ndim))) if p.ndim > 1 else nonzero_p | nonzero_q)),
        "sum_abs_P_kW_slots": float(np.sum(np.abs(p))),
        "sum_abs_Q_kvar_slots": float(np.sum(np.abs(q))),
        "charge_energy_kWh": float(0.25 * np.sum(np.maximum(-p, 0.0))),
        "discharge_energy_kWh": float(0.25 * np.sum(np.maximum(p, 0.0))),
        "throughput_kWh": float(0.25 * np.sum(np.abs(p))),
        "objective_delta_on_minus_off": float(objective_on) - float(objective_off),
        "planning_rho_delta": float(planning_rho_on) - float(planning_rho_off),
        "fresh_rho_AC_delta": float(fresh_rho_on) - float(fresh_rho_off),
        "travel_energy_kWh": float(travel_energy_kwh),
        "terminal_SoC": [float(value) for value in terminal_soc],
        "vehicle_solver_evidence": [dict(record) for record in solver_records],
        "solver_status_distribution": dict(sorted(statuses.items())),
        "zero_actuation": zero_actuation,
        "restricted_beats_full_vehicle_ids": restricted_beats_full,
        "red_flags": red_flags,
        "status": "PASS" if not red_flags else "DIAGNOSE",
    }


def repeated_zero_effect_sentinel(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    consecutive_zero = 0
    consecutive_unresolved = 0
    trigger_reasons: list[str] = []
    for row in rows:
        consecutive_zero = consecutive_zero + 1 if bool(row.get("zero_actuation")) else 0
        consecutive_unresolved = consecutive_unresolved + 1 if not bool(row.get("resolved_effect", True)) else 0
        if bool(row.get("unexpected_identical_injection_SHA", False)):
            trigger_reasons.append("UNEXPECTED_IDENTICAL_ON_OFF_INJECTION_SHA")
        if bool(row.get("case_equivalence_invariant_failed", False)):
            trigger_reasons.append("ZERO_MESS_CASE_EQUIVALENCE_FAILED")
        if bool(row.get("restricted_better_than_full", False)):
            trigger_reasons.append("RESTRICTED_FEASIBLE_INCUMBENT_BEATS_FULL")
    if consecutive_zero >= 3:
        trigger_reasons.append("THREE_CONSECUTIVE_UNEXPLAINED_ZERO_ACTUATION_DAYS")
    if consecutive_unresolved >= 3:
        trigger_reasons.append("THREE_CONSECUTIVE_SOLVER_UNRESOLVED_EFFECT_DAYS")
    unique = list(dict.fromkeys(trigger_reasons))
    return {"triggered": bool(unique), "reasons": unique}
