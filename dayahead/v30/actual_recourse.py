"""Causal AIDC-only same-slot spatial recourse.

This module intentionally has no OpenDSS import.  Fresh AC is an ex-post
certifier owned by the four-case runner, never a decision oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import linprog

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.authority import COHORT_IDS

from .recourse_accounting import SlotLedger, aggregate_ledgers


TOL = 1e-9


@dataclass
class CausalReadLedger:
    reads: list[dict[str, int | str]]
    future_actual_reads: int = 0

    def read(self, name: str, array: np.ndarray, current_slot: int, requested_slot: int) -> np.ndarray:
        if requested_slot > current_slot:
            self.future_actual_reads += 1
            raise RuntimeError("V30_CAUSAL_FIREWALL_FUTURE_READ")
        self.reads.append({"field": name, "current_slot": current_slot, "requested_slot": requested_slot})
        return np.asarray(array[requested_slot])


@dataclass(frozen=True)
class RecourseResult:
    executed_nodeh: np.ndarray
    backlog_nodeh: np.ndarray
    slot_ledgers: tuple[SlotLedger, ...]
    read_ledger: tuple[dict[str, int | str], ...]
    future_actual_reads: int
    recourse_epochs: int
    solver_subcalls: int
    mess_reoptimization_calls: int
    full_system_reoptimization_calls: int
    phase_grid_metric: np.ndarray

    @property
    def summary(self) -> dict[str, object]:
        mass = aggregate_ledgers(list(self.slot_ledgers))
        source_mass_error = float(self.backlog_nodeh[0].sum() + sum(
            row.actual_available_nodeh + row.source_unavailable_nodeh for row in self.slot_ledgers
        ) - mass["EXECUTED_TOTAL"] - self.backlog_nodeh[-1].sum())
        # The availability ledger is authorization-capped, so source conservation
        # is independently checked by the caller using raw arrivals.
        return {
            **mass,
            "AIDC_SECOND_STAGE_RECOURSE_EPOCHS": self.recourse_epochs,
            "AIDC_SECOND_STAGE_SOLVER_SUBCALLS": self.solver_subcalls,
            "ACTUAL_MESS_REOPTIMIZATION_CALLS": self.mess_reoptimization_calls,
            "ACTUAL_FULL_SYSTEM_REOPTIMIZATION_CALLS": self.full_system_reoptimization_calls,
            "future_Actual_reads": self.future_actual_reads,
            "maximum_same_slot_authorization_excess_nodeh": 0.0,
            "decision_module_Fresh_OpenDSS_calls": 0,
            "availability_ledger_diagnostic_error_nodeh": source_mass_error,
        }


def _lp(
    da_slot: np.ndarray,
    available: np.ndarray,
    capacity: np.ndarray,
    rack_aidc_index: np.ndarray,
    kappa: np.ndarray,
    site_scores: np.ndarray,
    anchor_site_flexible_kw: np.ndarray,
    margin_pu: float,
    peak_control_kw: float,
    *,
    safety: bool,
    service_eq: float | None = None,
    grid_eq: float | None = None,
    objective: str = "service",
) -> tuple[np.ndarray, float]:
    cohorts, racks = da_slot.shape
    n_y = cohorts * racks
    n_u = 12 if safety else 0
    n = n_y + n_u
    c = np.zeros(n)
    site_kw_coefficient = np.zeros((12, n_y))
    for cohort in range(cohorts):
        for rack in range(racks):
            site_kw_coefficient[rack_aidc_index[rack], cohort * racks + rack] = kappa[cohort] / 0.25
    grid_coefficient = site_scores @ site_kw_coefficient
    if objective == "service":
        c[:n_y] = -1.0
    elif objective == "grid":
        c[:n_y] = grid_coefficient
    elif objective == "placement":
        original = da_slot > TOL
        original_sites = np.zeros((cohorts, 12), dtype=bool)
        for cohort in range(cohorts):
            for rack in np.flatnonzero(original[cohort]):
                original_sites[cohort, rack_aidc_index[rack]] = True
        for cohort in range(cohorts):
            for rack in range(racks):
                cost = 0.0 if original[cohort, rack] else 1.0 if original_sites[cohort, rack_aidc_index[rack]] else 2.0
                c[cohort * racks + rack] = cost + rack * 1e-10
    else:
        raise ValueError("V30_UNKNOWN_LEXICOGRAPHIC_PHASE")

    aub: list[np.ndarray] = []
    bub: list[float] = []
    for cohort in range(cohorts):
        row = np.zeros(n); row[cohort * racks:(cohort + 1) * racks] = 1.0
        aub.append(row); bub.append(float(min(available[cohort], da_slot[cohort].sum())))
    for rack in range(racks):
        row = np.zeros(n); row[rack:n_y:racks] = 1.0
        aub.append(row); bub.append(float(capacity[rack]))
    if safety:
        delta_constant = -np.asarray(anchor_site_flexible_kw, dtype=float)
        # u >= +/- delta_site_kw
        for site in range(12):
            positive = np.zeros(n); positive[:n_y] = site_kw_coefficient[site]; positive[n_y + site] = -1.0
            aub.append(positive); bub.append(float(anchor_site_flexible_kw[site]))
            negative = np.zeros(n); negative[:n_y] = -site_kw_coefficient[site]; negative[n_y + site] = -1.0
            aub.append(negative); bub.append(float(-anchor_site_flexible_kw[site]))
        safe = np.zeros(n); safe[:n_y] = grid_coefficient
        safe[n_y:] = margin_pu / max(peak_control_kw, TOL)
        aub.append(safe)
        bub.append(float(site_scores @ anchor_site_flexible_kw))

    aeq: list[np.ndarray] = []
    beq: list[float] = []
    if service_eq is not None:
        row = np.zeros(n); row[:n_y] = 1.0
        aeq.append(row); beq.append(float(service_eq))
    if grid_eq is not None:
        row = np.zeros(n); row[:n_y] = grid_coefficient
        aeq.append(row); beq.append(float(grid_eq))
    result = linprog(
        c, A_ub=np.asarray(aub), b_ub=np.asarray(bub),
        A_eq=np.asarray(aeq) if aeq else None, b_eq=np.asarray(beq) if beq else None,
        bounds=[(0.0, None)] * n, method="highs",
        options={"dual_feasibility_tolerance": 1e-9, "primal_feasibility_tolerance": 1e-9},
    )
    if not result.success:
        raise RuntimeError(f"V30_RECOURSE_LP_{objective.upper()}:{result.message}")
    y = np.asarray(result.x[:n_y]).reshape(cohorts, racks)
    return y, float(grid_coefficient @ y.ravel())


def _classify_execution(y: np.ndarray, da: np.ndarray, rack_aidc_index: np.ndarray) -> tuple[float, float, float]:
    original = same = cross = 0.0
    for cohort in range(y.shape[0]):
        original_sites = {int(rack_aidc_index[r]) for r in np.flatnonzero(da[cohort] > TOL)}
        for rack in range(y.shape[1]):
            amount = float(y[cohort, rack])
            kept = min(amount, float(da[cohort, rack]))
            original += kept
            remainder = amount - kept
            if int(rack_aidc_index[rack]) in original_sites:
                same += remainder
            else:
                cross += remainder
    return original, same, cross


def solve_causal_day(
    da_service_nodeh: np.ndarray,
    actual_arrivals_nodeh: np.ndarray,
    capacity_nodeh: np.ndarray,
    rack_aidc: Sequence[str],
    site_scores_96x12: np.ndarray,
    anchor_site_flexible_kw_96x12: np.ndarray,
    margin_pu: float,
    initial_backlog_nodeh: np.ndarray | None = None,
) -> RecourseResult:
    da = np.asarray(da_service_nodeh, dtype=float)
    arrivals = np.asarray(actual_arrivals_nodeh, dtype=float)
    capacity = np.asarray(capacity_nodeh, dtype=float)
    scores = np.asarray(site_scores_96x12, dtype=float)
    anchor = np.asarray(anchor_site_flexible_kw_96x12, dtype=float)
    if da.shape != (15, 48, 96) or arrivals.shape != (96, 15) or capacity.shape != (96, 48):
        raise ValueError("V30_RECOURSE_INPUT_AXIS")
    if scores.shape != (96, 12) or anchor.shape != (96, 12) or len(rack_aidc) != 48:
        raise ValueError("V30_RECOURSE_GRID_AXIS")
    aidc_ids = tuple(dict.fromkeys(rack_aidc))
    rack_site = np.asarray([aidc_ids.index(value) for value in rack_aidc], dtype=int)
    kappa = np.asarray([KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] for cohort in COHORT_IDS])
    initial = np.zeros(15) if initial_backlog_nodeh is None else np.asarray(initial_backlog_nodeh, dtype=float)
    backlog = np.zeros((97, 15)); backlog[0] = initial
    executed = np.zeros_like(da)
    ledgers: list[SlotLedger] = []
    reads = CausalReadLedger([])
    grid_metric = np.zeros(96)
    subcalls = 0
    peak_control_kw = max(1.0, float(np.max(np.sum(anchor, axis=1))))
    for slot in range(96):
        arrival = reads.read("workload_arrivals", arrivals, slot, slot)
        rack_capacity = reads.read("rack_residual_capacity", capacity, slot, slot)
        score = reads.read("phase_current_site_score", scores, slot, slot)
        anchor_slot = reads.read("anchor_site_flexible_kw", anchor, slot, slot)
        backlog[slot + 1] = backlog[slot] + arrival
        da_slot = da[:, :, slot]
        available = backlog[slot + 1].copy()
        physical_y, _ = _lp(da_slot, available, rack_capacity, rack_site, kappa, score, anchor_slot, margin_pu, peak_control_kw, safety=False)
        subcalls += 1
        physical_service = float(physical_y.sum())
        service_y, _ = _lp(da_slot, available, rack_capacity, rack_site, kappa, score, anchor_slot, margin_pu, peak_control_kw, safety=True)
        subcalls += 1
        service = float(service_y.sum())
        grid_y, grid_opt = _lp(da_slot, available, rack_capacity, rack_site, kappa, score, anchor_slot, margin_pu, peak_control_kw, safety=True, service_eq=service, objective="grid")
        subcalls += 1
        final_y, final_grid = _lp(da_slot, available, rack_capacity, rack_site, kappa, score, anchor_slot, margin_pu, peak_control_kw, safety=True, service_eq=service, grid_eq=grid_opt, objective="placement")
        subcalls += 1
        if abs(final_y.sum() - service) > 1e-7 or abs(final_grid - grid_opt) > 1e-7:
            raise RuntimeError("V30_LEXICOGRAPHIC_CARRY_FORWARD")
        executed[:, :, slot] = final_y
        backlog[slot + 1] -= final_y.sum(axis=1)
        original, same, cross = _classify_execution(final_y, da_slot, rack_site)
        authorized = float(da_slot.sum())
        available_auth = float(np.minimum(available, da_slot.sum(axis=1)).sum())
        source_unavailable = authorized - available_auth
        true_capacity = max(0.0, available_auth - physical_service)
        grid_blocked = max(0.0, physical_service - service)
        other = authorized - (service + source_unavailable + true_capacity + grid_blocked)
        if abs(other) < 1e-8:
            other = 0.0
        ledgers.append(SlotLedger(slot, authorized, available_auth, original, same, cross, source_unavailable, true_capacity, grid_blocked, other, float(backlog[slot + 1].sum())))
        grid_metric[slot] = final_grid
    source_error = float(initial.sum() + arrivals.sum() - executed.sum() - backlog[-1].sum())
    mass = aggregate_ledgers(ledgers)
    if abs(source_error) > 1e-9 or abs(mass["authorization_mass_identity_error_nodeh"]) > 1e-8:
        raise RuntimeError("V30_RECOURSE_MASS_IDENTITY")
    return RecourseResult(executed, backlog, tuple(ledgers), tuple(reads.reads), reads.future_actual_reads, 96, subcalls, 0, 0, grid_metric)
