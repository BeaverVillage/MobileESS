"""Causal same-slot recourse under the frozen full planning grid model.

This decision module deliberately has no Fresh/OpenDSS import.  It substitutes
the current-slot AIDC variables and the frozen MESS controls into the exact
affine objects consumed by ``add_grid_rows``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, vstack

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.grid_lp import LINE_POLYGON_FACES, V_MAX_SQUARED, V_MIN_SQUARED
from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.electrical_subproblem import SlotCoefficients, is_dominated_mess_current_row
from dayahead.v30.actual_recourse import CausalReadLedger, RecourseResult, _classify_execution
from dayahead.v30.recourse_accounting import SlotLedger, aggregate_ledgers


TOL = 1e-9
LEX_SERVICE_TOL = 1e-7
LEX_GRID_TOL = 1e-7
HIGHS_THREADS = 4


@dataclass(frozen=True)
class FullGridRecourseResult:
    recourse: RecourseResult
    slot_diagnostics: tuple[Mapping[str, object], ...]
    coefficient_sha256: tuple[str, ...]


def _solve(c: np.ndarray, aub: csr_matrix, bub: np.ndarray, aeq: csr_matrix | None = None, beq: np.ndarray | None = None):
    result = linprog(
        c,
        A_ub=aub,
        b_ub=bub,
        A_eq=aeq,
        b_eq=beq,
        bounds=[(0.0, None)] * len(c),
        method="highs-ds",
        options={
            "dual_feasibility_tolerance": 1e-9,
            "primal_feasibility_tolerance": 1e-9,
            "threads": HIGHS_THREADS,
        },
    )
    if not result.success:
        raise RuntimeError(f"V33X_FULL_GRID_RECOURSE_LP:{result.message}")
    return result


def _slot_problem(
    da_slot: np.ndarray,
    available: np.ndarray,
    capacity: np.ndarray,
    rack_site: np.ndarray,
    kappa: np.ndarray,
    c1_by_site: Sequence[object],
    residual_site_it: np.ndarray,
    frozen_controls: np.ndarray,
    electrical: SlotCoefficients,
    planning_vmax_pu: float | None = None,
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
    planning_vmax_squared = V_MAX_SQUARED if planning_vmax_pu is None else float(planning_vmax_pu) ** 2
    if not math.isfinite(planning_vmax_squared) or planning_vmax_squared <= V_MIN_SQUARED:
        raise ValueError("V33X_PLANNING_VMAX_RANGE")

    v_constant = np.asarray(electrical.voltage_constant) + np.asarray(electrical.voltage_matrix).T @ control_constant
    v_matrix = np.asarray(electrical.voltage_matrix).T @ control_matrix
    for constant, row0 in zip(v_constant, v_matrix, strict=True):
        grid_rows.append(row0.copy())
        upper_rhs = V_MAX_SQUARED - constant if planning_vmax_pu is None else planning_vmax_squared - constant
        grid_rhs.append(float(upper_rhs))
        grid_rows.append(-row0.copy())
        grid_rhs.append(float(constant - V_MIN_SQUARED))

    i_constant = np.asarray(electrical.current_constant) + np.asarray(electrical.current_matrix).T @ control_constant
    i_matrix = np.asarray(electrical.current_matrix).T @ control_matrix
    monitored_line_indices: list[int] = []
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
            monitored_line_indices.append(index)

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
    voltage = np.asarray(electrical.voltage_constant) + np.asarray(electrical.voltage_matrix).T @ controls
    current = np.asarray(electrical.current_constant) + np.asarray(electrical.current_matrix).T @ controls
    flow_p = np.asarray(electrical.flow_p_constant) + np.asarray(electrical.flow_p_matrix) @ controls
    flow_q = np.asarray(electrical.flow_q_constant) + np.asarray(electrical.flow_q_matrix) @ controls
    tx_loading = [
        math.hypot(float(flow_p[index]), float(flow_q[index])) / float(electrical.transformer_ratings[index])
        for index in transformer_indices
    ]
    supported_current = [float(current[index]) for index, name in enumerate(electrical.branch_names) if not is_dominated_mess_current_row(name)]
    diagnostics = {
        "planning_Vmin_pu": float(math.sqrt(max(0.0, float(voltage.min())))),
        "planning_Vmax_pu": float(math.sqrt(max(0.0, float(voltage.max())))),
        "planning_rho_max": max(supported_current, default=0.0),
        "planning_transformer_kva_loading_max": max(tx_loading, default=0.0),
        "planning_voltage_violation": bool(voltage.min() < V_MIN_SQUARED - 1e-7 or voltage.max() > planning_vmax_squared + 1e-7),
        "planning_vmax_pu": math.sqrt(planning_vmax_squared),
        "planning_current_violation": bool(max(supported_current, default=0.0) > 1.0 + 1e-7),
        "planning_transformer_violation": bool(max(tx_loading, default=0.0) > 1.0 + 1e-7),
    }
    return y, float(physical.x[:n_y].sum()), rho_opt, diagnostics, 4


def solve_causal_day_full_grid(
    da_service_nodeh: np.ndarray,
    actual_arrivals_nodeh: np.ndarray,
    capacity_nodeh: np.ndarray,
    rack_aidc: Sequence[str],
    residual_rack_it_kw_96x48: np.ndarray,
    c1_by_site_slot: Mapping[tuple[str, int], object],
    frozen_controls_96x60: np.ndarray,
    electrical_coefficients: Sequence[SlotCoefficients],
    initial_backlog_nodeh: np.ndarray | None = None,
    *,
    planning_vmax_pu: float | None = None,
) -> FullGridRecourseResult:
    da = np.asarray(da_service_nodeh, dtype=float)
    arrivals = np.asarray(actual_arrivals_nodeh, dtype=float)
    capacity = np.asarray(capacity_nodeh, dtype=float)
    residual = np.asarray(residual_rack_it_kw_96x48, dtype=float)
    frozen_controls = np.asarray(frozen_controls_96x60, dtype=float)
    if da.shape != (15, 48, 96) or arrivals.shape != (96, 15) or capacity.shape != (96, 48):
        raise ValueError("V33X_RECOURSE_INPUT_AXIS")
    if residual.shape != (96, 48) or frozen_controls.shape != (96, 60) or len(electrical_coefficients) != 96:
        raise ValueError("V33X_RECOURSE_ELECTRICAL_AXIS")
    aidc_ids = tuple(dict.fromkeys(rack_aidc))
    rack_site = np.asarray([aidc_ids.index(value) for value in rack_aidc], dtype=int)
    kappa = np.asarray([KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] for cohort in COHORT_IDS])
    initial = np.zeros(15) if initial_backlog_nodeh is None else np.asarray(initial_backlog_nodeh, dtype=float)
    backlog = np.zeros((97, 15))
    backlog[0] = initial
    executed = np.zeros_like(da)
    ledgers: list[SlotLedger] = []
    read_ledger = CausalReadLedger([])
    diagnostics: list[Mapping[str, object]] = []
    grid_metric = np.zeros(96)
    subcalls = 0
    for slot in range(96):
        arrival = read_ledger.read("workload_arrivals", arrivals, slot, slot)
        rack_capacity = read_ledger.read("rack_residual_capacity", capacity, slot, slot)
        residual_slot = read_ledger.read("residual_rack_it_kw", residual, slot, slot)
        controls_slot = read_ledger.read("frozen_MESS_controls", frozen_controls, slot, slot)
        coefficient = electrical_coefficients[slot]
        if coefficient.slot != slot:
            raise RuntimeError("V33X_ELECTRICAL_SLOT_ORDER")
        backlog[slot + 1] = backlog[slot] + arrival
        da_slot = da[:, :, slot]
        available = backlog[slot + 1].copy()
        c1 = [c1_by_site_slot[(aidc, slot)] for aidc in aidc_ids]
        site_residual = np.asarray([residual_slot[rack_site == site].sum() for site in range(12)])
        y, physical_service, rho, slot_grid, calls = _slot_problem(
            da_slot, available, rack_capacity, rack_site, kappa, c1, site_residual,
            controls_slot, coefficient, planning_vmax_pu,
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
    if abs(source_error) > 1e-8 or abs(mass["authorization_mass_identity_error_nodeh"]) > 1e-8:
        raise RuntimeError("V33X_RECOURSE_MASS_IDENTITY")
    recourse = RecourseResult(
        executed, backlog, tuple(ledgers), tuple(read_ledger.reads),
        read_ledger.future_actual_reads, 96, subcalls, 0, 0, grid_metric,
    )
    return FullGridRecourseResult(
        recourse, tuple(diagnostics), tuple(row.coefficient_sha256 for row in electrical_coefficients),
    )
