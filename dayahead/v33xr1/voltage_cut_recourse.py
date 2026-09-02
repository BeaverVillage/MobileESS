"""Causal E1 suffix replay with isolated local voltage-feasibility cuts.

This decision module has no Fresh/OpenDSS import.  A development driver owns
Fresh evaluation and passes frozen affine cuts into this solver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from scipy.sparse import csr_matrix, vstack

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.grid_lp import LINE_POLYGON_FACES, V_MAX_SQUARED, V_MIN_SQUARED
from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.electrical_subproblem import SlotCoefficients, is_dominated_mess_current_row
from dayahead.v30.actual_recourse import CausalReadLedger, RecourseResult, _classify_execution
from dayahead.v30.recourse_accounting import SlotLedger, aggregate_ledgers
from dayahead.v33x.full_grid_recourse import (
    FullGridRecourseResult,
    LEX_GRID_TOL,
    LEX_SERVICE_TOL,
    TOL,
    _solve,
)

from .contracts import MASS_TOLERANCE_NODEH


@dataclass(frozen=True)
class LocalVoltageCut:
    """One upper-voltage cut, represented as ``a @ p_site <= rhs``."""

    cut_id: str
    iteration: int
    case: str
    slot: int
    node_index: int
    node: str
    bus: str
    phase: str
    p_anchor_kw: tuple[float, ...]
    sensitivity_pu_per_kw: tuple[float, ...]
    rhs_pu: float

    def validate(self) -> None:
        if self.case != "B1" or not 0 <= self.slot < 96 or not 0 <= self.node_index < 386:
            raise ValueError("V33XR1_LOCAL_CUT_AXIS")
        if len(self.p_anchor_kw) != 12 or len(self.sensitivity_pu_per_kw) != 12:
            raise ValueError("V33XR1_LOCAL_CUT_SITE_AXIS")
        if not all(np.isfinite(value) for value in (*self.p_anchor_kw, *self.sensitivity_pu_per_kw, self.rhs_pu)):
            raise ValueError("V33XR1_LOCAL_CUT_NONFINITE")


class LocalVoltageCutInfeasible(RuntimeError):
    """Raised when a requested local cut lies outside the frozen E1 feasible set."""

    def __init__(self, details: Sequence[Mapping[str, object]]):
        self.details = tuple(dict(row) for row in details)
        super().__init__(f"V33XR1_LOCAL_VOLTAGE_CUT_INFEASIBLE:{self.details}")


def assess_local_cut_feasibility(
    da_service_nodeh: np.ndarray,
    actual_arrivals_nodeh: np.ndarray,
    capacity_nodeh: np.ndarray,
    rack_aidc: Sequence[str],
    residual_rack_it_kw_96x48: np.ndarray,
    c1_by_site_slot: Mapping[tuple[str, int], object],
    frozen_controls_96x60: np.ndarray,
    electrical_coefficients: Sequence[SlotCoefficients],
    previous: FullGridRecourseResult,
    cut: LocalVoltageCut,
) -> dict[str, object]:
    """Test one cut at its slot against the frozen E1 feasible set."""

    cut.validate()
    slot = cut.slot
    da = np.asarray(da_service_nodeh, dtype=float)
    arrivals = np.asarray(actual_arrivals_nodeh, dtype=float)
    capacity = np.asarray(capacity_nodeh, dtype=float)
    residual = np.asarray(residual_rack_it_kw_96x48, dtype=float)
    frozen_controls = np.asarray(frozen_controls_96x60, dtype=float)
    aidc_ids = tuple(dict.fromkeys(rack_aidc))
    rack_site = np.asarray([aidc_ids.index(value) for value in rack_aidc], dtype=int)
    kappa = np.asarray([KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] for cohort in COHORT_IDS])
    available = np.asarray(previous.recourse.backlog_nodeh[slot], dtype=float) + arrivals[slot]
    c1 = [c1_by_site_slot[(aidc, slot)] for aidc in aidc_ids]
    site_residual = np.asarray([residual[slot, rack_site == site].sum() for site in range(12)])
    try:
        _slot_problem_with_cuts(
            da[:, :, slot], available, capacity[slot], rack_site, kappa, c1,
            site_residual, frozen_controls[slot], electrical_coefficients[slot], (cut,),
        )
    except LocalVoltageCutInfeasible as error:
        return {"feasible": False, **dict(error.details[0])}
    return {
        "feasible": True,
        "cut_id": cut.cut_id,
        "minimum_achievable_LHS_pu": "",
        "required_RHS_pu": cut.rhs_pu,
        "shortfall_pu": 0.0,
    }


def _slot_problem_with_cuts(
    da_slot: np.ndarray,
    available: np.ndarray,
    capacity: np.ndarray,
    rack_site: np.ndarray,
    kappa: np.ndarray,
    c1_by_site: Sequence[object],
    residual_site_it: np.ndarray,
    frozen_controls: np.ndarray,
    electrical: SlotCoefficients,
    cuts: Sequence[LocalVoltageCut],
) -> tuple[np.ndarray, float, float, dict[str, object], int]:
    cohorts, racks = da_slot.shape
    n_y = cohorts * racks
    n = n_y + 1
    rho_index = n_y
    control_matrix = np.zeros((60, n))
    control_constant = np.asarray(frozen_controls, dtype=float).copy()
    for site, coefficient in enumerate(c1_by_site):
        control_constant[site] = float(coefficient.slope) * float(residual_site_it[site]) + float(coefficient.intercept_kw)
        for cohort in range(cohorts):
            indices = np.flatnonzero(rack_site == site)
            control_matrix[site, cohort * racks + indices] = float(coefficient.slope) * kappa[cohort] / 0.25

    resource_rows: list[np.ndarray] = []
    resource_rhs: list[float] = []
    for cohort in range(cohorts):
        row = np.zeros(n)
        row[cohort * racks:(cohort + 1) * racks] = 1.0
        resource_rows.append(row)
        resource_rhs.append(float(min(available[cohort], da_slot[cohort].sum())))
    for rack in range(racks):
        row = np.zeros(n)
        row[rack:n_y:racks] = 1.0
        resource_rows.append(row)
        resource_rhs.append(float(capacity[rack]))
    resource_a = csr_matrix(np.asarray(resource_rows))
    resource_b = np.asarray(resource_rhs)

    grid_rows: list[np.ndarray] = list(resource_rows)
    grid_rhs: list[float] = list(resource_rhs)
    v_constant = np.asarray(electrical.voltage_constant) + np.asarray(electrical.voltage_matrix).T @ control_constant
    v_matrix = np.asarray(electrical.voltage_matrix).T @ control_matrix
    for constant, row0 in zip(v_constant, v_matrix, strict=True):
        grid_rows.append(row0.copy())
        grid_rhs.append(float(V_MAX_SQUARED - constant))
        grid_rows.append(-row0.copy())
        grid_rhs.append(float(constant - V_MIN_SQUARED))

    i_constant = np.asarray(electrical.current_constant) + np.asarray(electrical.current_matrix).T @ control_constant
    i_matrix = np.asarray(electrical.current_matrix).T @ control_matrix
    for index, name in enumerate(electrical.branch_names):
        if is_dominated_mess_current_row(name):
            continue
        grid_rows.append(i_matrix[index].copy())
        grid_rhs.append(float(1.0 - i_constant[index]))
        if not name.startswith("transformer."):
            row = i_matrix[index].copy()
            row[rho_index] = -1.0
            grid_rows.append(row)
            grid_rhs.append(float(-i_constant[index]))

    p_constant = np.asarray(electrical.flow_p_constant) + np.asarray(electrical.flow_p_matrix) @ control_constant
    q_constant = np.asarray(electrical.flow_q_constant) + np.asarray(electrical.flow_q_matrix) @ control_constant
    p_matrix = np.asarray(electrical.flow_p_matrix) @ control_matrix
    q_matrix = np.asarray(electrical.flow_q_matrix) @ control_matrix
    transformer_indices: list[int] = []
    for index, rating in enumerate(electrical.transformer_ratings):
        if rating is None:
            continue
        transformer_indices.append(index)
        apothem = float(rating) * math.cos(math.pi / LINE_POLYGON_FACES)
        for face in range(LINE_POLYGON_FACES):
            angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
            row = math.cos(angle) * p_matrix[index] + math.sin(angle) * q_matrix[index]
            constant = math.cos(angle) * p_constant[index] + math.sin(angle) * q_constant[index]
            grid_rows.append(row)
            grid_rhs.append(float(apothem - constant))

    base_grid_a = csr_matrix(np.asarray(grid_rows))
    base_grid_b = np.asarray(grid_rhs)
    infeasible_details: list[dict[str, object]] = []
    for cut in cuts:
        cut.validate()
        if cut.slot != electrical.slot:
            raise RuntimeError("V33XR1_CUT_SLOT_MISMATCH")
        sensitivity = np.asarray(cut.sensitivity_pu_per_kw, dtype=float)
        row = sensitivity @ control_matrix[:12]
        variable_rhs = float(cut.rhs_pu - sensitivity @ control_constant[:12])
        minimum = _solve(np.asarray(row, dtype=float), base_grid_a, base_grid_b)
        minimum_site_lhs = float(sensitivity @ control_constant[:12] + minimum.fun)
        if minimum_site_lhs > cut.rhs_pu + 1e-9:
            infeasible_details.append({
                "cut_id": cut.cut_id,
                "minimum_achievable_LHS_pu": minimum_site_lhs,
                "required_RHS_pu": cut.rhs_pu,
                "shortfall_pu": minimum_site_lhs - cut.rhs_pu,
            })
        grid_rows.append(np.asarray(row, dtype=float))
        grid_rhs.append(variable_rhs)

    if infeasible_details:
        raise LocalVoltageCutInfeasible(infeasible_details)

    grid_a = csr_matrix(np.asarray(grid_rows))
    grid_b = np.asarray(grid_rhs)
    service_objective = np.zeros(n)
    service_objective[:n_y] = -1.0
    physical = _solve(service_objective, resource_a, resource_b)
    full = _solve(service_objective, grid_a, grid_b)
    service = float(full.x[:n_y].sum())
    service_floor = np.zeros((1, n))
    service_floor[0, :n_y] = -1.0
    lex_a = vstack((grid_a, csr_matrix(service_floor)), format="csr")
    lex_b = np.concatenate((grid_b, [-(service - LEX_SERVICE_TOL)]))
    grid_objective = np.zeros(n)
    grid_objective[rho_index] = 1.0
    minimized = _solve(grid_objective, lex_a, lex_b)
    rho_opt = float(minimized.x[rho_index])
    rho_row = np.zeros((1, n))
    rho_row[0, rho_index] = 1.0
    final_a = vstack((lex_a, csr_matrix(rho_row)), format="csr")
    final_b = np.concatenate((lex_b, [rho_opt + LEX_GRID_TOL]))
    placement = np.zeros(n)
    original = da_slot > TOL
    original_sites = np.zeros((cohorts, 12), dtype=bool)
    for cohort in range(cohorts):
        for rack in np.flatnonzero(original[cohort]):
            original_sites[cohort, rack_site[rack]] = True
    for cohort in range(cohorts):
        for rack in range(racks):
            placement[cohort * racks + rack] = (
                0.0 if original[cohort, rack]
                else 1.0 if original_sites[cohort, rack_site[rack]]
                else 2.0
            ) + rack * 1e-10
    final = _solve(placement, final_a, final_b)
    y = np.asarray(final.x[:n_y]).reshape(cohorts, racks)
    controls = control_constant + control_matrix @ final.x
    voltage_squared = np.asarray(electrical.voltage_constant) + np.asarray(electrical.voltage_matrix).T @ controls
    current = np.asarray(electrical.current_constant) + np.asarray(electrical.current_matrix).T @ controls
    flow_p = np.asarray(electrical.flow_p_constant) + np.asarray(electrical.flow_p_matrix) @ controls
    flow_q = np.asarray(electrical.flow_q_constant) + np.asarray(electrical.flow_q_matrix) @ controls
    tx_loading = [
        math.hypot(float(flow_p[index]), float(flow_q[index])) / float(electrical.transformer_ratings[index])
        for index in transformer_indices
    ]
    supported_current = [
        float(current[index]) for index, name in enumerate(electrical.branch_names)
        if not is_dominated_mess_current_row(name)
    ]
    site_p = np.asarray(controls[:12], dtype=float)
    cut_slacks = {
        cut.cut_id: float(cut.rhs_pu - np.asarray(cut.sensitivity_pu_per_kw) @ site_p)
        for cut in cuts
    }
    diagnostics = {
        "planning_Vmin_pu": float(math.sqrt(max(0.0, float(voltage_squared.min())))),
        "planning_Vmax_pu": float(math.sqrt(max(0.0, float(voltage_squared.max())))),
        "planning_rho_max": max(supported_current, default=0.0),
        "planning_transformer_kva_loading_max": max(tx_loading, default=0.0),
        "planning_voltage_violation": bool(voltage_squared.min() < V_MIN_SQUARED - 1e-7 or voltage_squared.max() > V_MAX_SQUARED + 1e-7),
        "planning_current_violation": bool(max(supported_current, default=0.0) > 1.0 + 1e-7),
        "planning_transformer_violation": bool(max(tx_loading, default=0.0) > 1.0 + 1e-7),
        "planning_voltage_pu_by_node": tuple(map(float, np.sqrt(np.maximum(voltage_squared, 0.0)))),
        "site_p_kw": tuple(map(float, site_p)),
        "local_voltage_cut_slack_pu": cut_slacks,
    }
    return y, float(physical.x[:n_y].sum()), rho_opt, diagnostics, 4


def solve_causal_suffix_with_voltage_cuts(
    da_service_nodeh: np.ndarray,
    actual_arrivals_nodeh: np.ndarray,
    capacity_nodeh: np.ndarray,
    rack_aidc: Sequence[str],
    residual_rack_it_kw_96x48: np.ndarray,
    c1_by_site_slot: Mapping[tuple[str, int], object],
    frozen_controls_96x60: np.ndarray,
    electrical_coefficients: Sequence[SlotCoefficients],
    cuts: Sequence[LocalVoltageCut],
    initial_backlog_nodeh: np.ndarray | None = None,
    *,
    previous: FullGridRecourseResult | None = None,
    start_slot: int = 0,
) -> FullGridRecourseResult:
    """Reuse a causal prefix and recompute every slot from ``start_slot`` onward."""

    da = np.asarray(da_service_nodeh, dtype=float)
    arrivals = np.asarray(actual_arrivals_nodeh, dtype=float)
    capacity = np.asarray(capacity_nodeh, dtype=float)
    residual = np.asarray(residual_rack_it_kw_96x48, dtype=float)
    frozen_controls = np.asarray(frozen_controls_96x60, dtype=float)
    if da.shape != (15, 48, 96) or arrivals.shape != (96, 15) or capacity.shape != (96, 48):
        raise ValueError("V33XR1_RECOURSE_INPUT_AXIS")
    if residual.shape != (96, 48) or frozen_controls.shape != (96, 60) or len(electrical_coefficients) != 96:
        raise ValueError("V33XR1_RECOURSE_ELECTRICAL_AXIS")
    if not 0 <= start_slot < 96 or (start_slot and previous is None):
        raise ValueError("V33XR1_CAUSAL_SUFFIX_START")
    cuts_by_slot: dict[int, list[LocalVoltageCut]] = {}
    for cut in cuts:
        cut.validate()
        cuts_by_slot.setdefault(cut.slot, []).append(cut)

    aidc_ids = tuple(dict.fromkeys(rack_aidc))
    rack_site = np.asarray([aidc_ids.index(value) for value in rack_aidc], dtype=int)
    kappa = np.asarray([KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] for cohort in COHORT_IDS])
    initial = np.zeros(15) if initial_backlog_nodeh is None else np.asarray(initial_backlog_nodeh, dtype=float)
    backlog = np.zeros((97, 15))
    backlog[0] = initial
    executed = np.zeros_like(da)
    ledgers: list[SlotLedger] = []
    diagnostics: list[Mapping[str, object]] = []
    grid_metric = np.zeros(96)
    prefix_reads: list[dict[str, int | str]] = []
    if previous is not None and start_slot:
        executed[:, :, :start_slot] = np.asarray(previous.recourse.executed_nodeh)[:, :, :start_slot]
        backlog[:start_slot + 1] = np.asarray(previous.recourse.backlog_nodeh)[:start_slot + 1]
        ledgers.extend(previous.recourse.slot_ledgers[:start_slot])
        diagnostics.extend(previous.slot_diagnostics[:start_slot])
        grid_metric[:start_slot] = np.asarray(previous.recourse.phase_grid_metric)[:start_slot]
        prefix_reads = [dict(row) for row in previous.recourse.read_ledger if int(row["current_slot"]) < start_slot]
    read_ledger = CausalReadLedger(prefix_reads)
    subcalls = 4 * start_slot
    for slot in range(start_slot, 96):
        arrival = read_ledger.read("workload_arrivals", arrivals, slot, slot)
        rack_capacity = read_ledger.read("rack_residual_capacity", capacity, slot, slot)
        residual_slot = read_ledger.read("residual_rack_it_kw", residual, slot, slot)
        controls_slot = read_ledger.read("frozen_MESS_controls", frozen_controls, slot, slot)
        coefficient = electrical_coefficients[slot]
        if coefficient.slot != slot:
            raise RuntimeError("V33XR1_ELECTRICAL_SLOT_ORDER")
        backlog[slot + 1] = backlog[slot] + arrival
        da_slot = da[:, :, slot]
        available = backlog[slot + 1].copy()
        c1 = [c1_by_site_slot[(aidc, slot)] for aidc in aidc_ids]
        site_residual = np.asarray([residual_slot[rack_site == site].sum() for site in range(12)])
        y, physical_service, rho, slot_grid, calls = _slot_problem_with_cuts(
            da_slot, available, rack_capacity, rack_site, kappa, c1, site_residual,
            controls_slot, coefficient, cuts_by_slot.get(slot, ()),
        )
        subcalls += calls
        service = float(y.sum())
        executed[:, :, slot] = y
        backlog[slot + 1] -= y.sum(axis=1)
        original, same, cross = _classify_execution(y, da_slot, rack_site)
        authorized = float(da_slot.sum())
        available_auth = float(np.minimum(available, da_slot.sum(axis=1)).sum())
        source_unavailable = authorized - available_auth
        rack_blocked = max(0.0, available_auth - physical_service)
        grid_blocked = max(0.0, physical_service - service)
        other = authorized - (service + source_unavailable + rack_blocked + grid_blocked)
        if abs(other) < 1e-8:
            other = 0.0
        ledgers.append(SlotLedger(
            slot, authorized, available_auth, original, same, cross,
            source_unavailable, rack_blocked, grid_blocked, other,
            float(backlog[slot + 1].sum()),
        ))
        diagnostics.append({"slot": slot, **slot_grid})
        grid_metric[slot] = rho
    source_error = float(initial.sum() + arrivals.sum() - executed.sum() - backlog[-1].sum())
    mass = aggregate_ledgers(ledgers)
    if abs(source_error) > MASS_TOLERANCE_NODEH or abs(mass["authorization_mass_identity_error_nodeh"]) > MASS_TOLERANCE_NODEH:
        raise RuntimeError("V33XR1_RECOURSE_MASS_IDENTITY")
    recourse = RecourseResult(
        executed, backlog, tuple(ledgers), tuple(read_ledger.reads),
        read_ledger.future_actual_reads, 96, subcalls, 0, 0, grid_metric,
    )
    return FullGridRecourseResult(
        recourse, tuple(diagnostics), tuple(row.coefficient_sha256 for row in electrical_coefficients),
    )
