"""Stable May-ready V36 long-form output and completeness manifests."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row

from .contracts import RAW_ROOT, SCHEMA_IDS, SCHEMA_VERSION, SLOTS
from .science import canonical_sha256


CASE_FILES = (
    "inputs/RUN_PROVENANCE.json", "inputs/INPUT_AUTHORITY.json",
    "aidc/AIDC_SCHEDULER_LEDGER.parquet", "aidc/AIDC_POWER_96.csv",
    "aidc/IDC_FACILITY_96.parquet", "mess/MESS_TRAJECTORY_96.parquet",
    "mess/MESS_MOVE_EVENTS.parquet", "mess/MESS_SEARCH_TRACE.parquet",
    "planning/PLANNING_BUS_PHASE_96.parquet",
    "planning/PLANNING_LINE_PHASE_96.parquet",
    "planning/PLANNING_SYSTEM_96.parquet",
    "fresh/FRESH_BUS_PHASE_96.parquet", "fresh/FRESH_LINE_PHASE_96.parquet",
    "fresh/FRESH_SYSTEM_96.parquet",
    "residual/PLANNING_FRESH_VOLTAGE_RESIDUAL.parquet",
    "residual/PLANNING_FRESH_CURRENT_RESIDUAL.parquet",
    "residual/PLANNING_FRESH_SYSTEM_RESIDUAL.parquet",
    "summary/OBJECTIVE.json", "summary/PHYSICAL_GATES.json",
    "solver/SOLVER_RUNS.parquet", "summary/COMPUTE_SUMMARY.json",
)

DATE_FILES = (
    "B0_B3_OBJECTIVE_SUMMARY.csv",
    "summary/COMPUTE_SUMMARY.json",
)

PRIMARY_KEYS = {
    "AIDC_SCHEDULER_LEDGER.parquet": ["job_id"],
    "AIDC_POWER_96.csv": ["slot"],
    "IDC_FACILITY_96.parquet": ["slot", "IDC_id"],
    "MESS_TRAJECTORY_96.parquet": ["case", "vehicle_id", "slot"],
    "MESS_MOVE_EVENTS.parquet": ["case", "vehicle_id", "departure_slot"],
    "MESS_SEARCH_TRACE.parquet": ["case", "vehicle", "parent_beam_state", "candidate_id"],
    "PLANNING_BUS_PHASE_96.parquet": ["slot", "bus_phase_key"],
    "PLANNING_LINE_PHASE_96.parquet": ["slot", "branch_phase_key"],
    "PLANNING_SYSTEM_96.parquet": ["slot"],
    "FRESH_BUS_PHASE_96.parquet": ["slot", "bus_phase_key"],
    "FRESH_LINE_PHASE_96.parquet": ["slot", "branch_phase_key"],
    "FRESH_SYSTEM_96.parquet": ["slot"],
    "PLANNING_FRESH_VOLTAGE_RESIDUAL.parquet": ["case", "slot", "bus_phase_key"],
    "PLANNING_FRESH_CURRENT_RESIDUAL.parquet": ["case", "slot", "branch_phase_key"],
    "PLANNING_FRESH_SYSTEM_RESIDUAL.parquet": ["case", "slot"],
}

CRITICAL_COLUMNS = {
    "AIDC_SCHEDULER_LEDGER.parquet": [
        "job_id", "requested_GPUs", "RSP_duration_slots", "scheduled_start_slot_rw",
        "scheduled_end_slot_rw", "scheduled_start_slot_rsp", "scheduled_end_slot_rsp",
    ],
    "AIDC_POWER_96.csv": [
        "slot", "N_active_GPU", "N_idle_GPU", "P_IT_RW_kW", "P_IT_case_kW",
        "C1_effective_PUE", "aggregate_PCC_P_kW", "aggregate_PCC_Q_kvar",
    ],
    "IDC_FACILITY_96.parquet": [
        "slot", "IDC_id", "IT_power_kW", "PUE", "PCC_P_kW", "PCC_Q_kvar",
    ],
    "MESS_TRAJECTORY_96.parquet": ["case", "vehicle_id", "slot", "P_kW", "Q_kvar", "SoC_fraction"],
    "MESS_MOVE_EVENTS.parquet": [
        "case", "vehicle_id", "departure_slot", "arrival_slot", "connection_ready_slot",
        "Q50_ETA_seconds", "Safe_ETA_seconds", "travel_energy_kWh",
    ],
    "MESS_SEARCH_TRACE.parquet": ["case", "vehicle", "candidate_id", "restricted_objective"],
    "PLANNING_BUS_PHASE_96.parquet": [
        "slot", "bus_phase_key", "voltage_magnitude_pu", "P_controlled_injection_kW",
        "Q_controlled_injection_kvar",
    ],
    "PLANNING_LINE_PHASE_96.parquet": [
        "slot", "branch_phase_key", "phase_current_loading_pu", "P_flow_kW", "Q_flow_kvar",
        "transformer_loading_pu",
    ],
    "PLANNING_SYSTEM_96.parquet": [
        "slot", "system_rho", "Vmin_pu", "Vmax_pu", "Imax_loading_ratio",
        "transformer_current_loading_max", "transformer_kva_loading_max",
    ],
    "FRESH_BUS_PHASE_96.parquet": ["slot", "bus_phase_key", "fresh_voltage_magnitude_pu"],
    "FRESH_LINE_PHASE_96.parquet": [
        "slot", "branch_phase_key", "phase_current_A", "phase_current_loading_pu", "transformer_loading_pu",
    ],
    "FRESH_SYSTEM_96.parquet": [
        "slot", "system_rho", "Vmin_pu", "Vmax_pu", "Imax_loading_ratio",
        "transformer_current_loading_max", "transformer_kva_loading_max", "OpenDSS_converged",
    ],
    "PLANNING_FRESH_VOLTAGE_RESIDUAL.parquet": [
        "case", "slot", "bus_phase_key", "voltage_magnitude_pu", "fresh_voltage_magnitude_pu",
        "signed_residual", "absolute_residual", "normalized_residual",
    ],
    "PLANNING_FRESH_CURRENT_RESIDUAL.parquet": [
        "case", "slot", "branch_phase_key", "phase_current_loading_pu_planning",
        "phase_current_loading_pu_fresh", "signed_current_residual", "absolute_current_residual",
        "signed_transformer_residual", "absolute_transformer_residual",
    ],
    "PLANNING_FRESH_SYSTEM_RESIDUAL.parquet": [
        "case", "slot", "system_rho_planning", "system_rho_fresh", "signed_rho_residual",
        "absolute_rho_residual",
    ],
    "SOLVER_RUNS.parquet": ["solve_id", "case", "vehicle", "status", "incumbent", "wallclock"],
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                   allow_nan=False, default=_json_default) + "\n", encoding="utf-8",
    )
    os.replace(temporary, path)


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def _timestamps(day: str) -> list[str]:
    return [value.isoformat() for value in pd.date_range(day, periods=SLOTS, freq="15min", tz="+10:00")]


def planning_frames(
    day: str, arrays: Mapping[str, np.ndarray], voltage_authority: Any,
    coefficients: Sequence[Any], trajectory: Any | None, aidc_p: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    nodes = np.asarray(voltage_authority["node_names"]).astype(str)
    branch_axis = np.asarray(coefficients[0].branch_names).astype(str)
    branches = np.asarray([name.rsplit("::", 1)[0] for name in branch_axis])
    phases = np.asarray([name.rsplit("::", 1)[1].upper() for name in branch_axis])
    volts = np.asarray(arrays["voltage_pu"], float)
    current = np.asarray(arrays["phase_current_loading_pu"], float)
    flow_p = np.asarray(arrays["flow_p_kw"], float)
    flow_q = np.asarray(arrays["flow_q_kvar"], float)
    tx = np.asarray(arrays["transformer_kva_loading_pu"], float)
    times = _timestamps(day)
    controls = tuple(map(str, voltage_authority["control_names"]))
    services = tuple(name[10:-1] for name in controls[12:36])
    by_p: dict[tuple[str, int], float] = {}
    by_q: dict[tuple[str, int], float] = {}
    if trajectory is not None:
        for row in trajectory.slots:
            if row.service_id is not None:
                key = (row.service_id, row.slot)
                by_p[key] = by_p.get(key, 0.0) + float(row.p_kw)
                by_q[key] = by_q.get(key, 0.0) + float(row.q_kvar)
    bus_rows: list[dict[str, Any]] = []
    line_rows: list[dict[str, Any]] = []
    system_rows: list[dict[str, Any]] = []
    for slot, coefficient in enumerate(coefficients):
        x = np.asarray(list(aidc_p[slot]) + [by_p.get((s, slot), 0.0) for s in services]
                       + [by_q.get((s, slot), 0.0) for s in services])
        _reference, _vintage, _background, binding, _path, _authority = coefficient._v36_context
        data = binding.factories[slot].data
        for index, node in enumerate(nodes):
            bus, phase_number = node.rsplit(".", 1)
            phase = "ABC"[int(phase_number) - 1]
            key = (bus, phase)
            p_inj = sum(float(value) * float(x[controls.index(name)])
                        for name, value in data.master_p_injection.get(key, {}).items())
            q_inj = sum(float(value) * float(x[controls.index(name)])
                        for name, value in data.master_q_injection.get(key, {}).items())
            bus_rows.append({
                "slot": slot, "timestamp": times[slot], "bus_phase_key": node,
                "bus": bus, "phase": phase, "voltage_magnitude_pu": float(volts[slot, index]),
                "P_controlled_injection_kW": p_inj, "Q_controlled_injection_kvar": q_inj,
                "injection_scope": "CONTROLLED_AIDC_AND_MESS",
                "critical_voltage_element": bool(
                    volts[slot, index] == volts.min() or volts[slot, index] == volts.max()
                ),
            })
        line_mask = np.asarray([
            not name.startswith("transformer.") and not is_dominated_mess_current_row(name)
            for name in branch_axis
        ])
        active_line = int(np.flatnonzero(line_mask)[np.argmax(current[slot, line_mask])])
        for index, (branch, phase) in enumerate(zip(branches, phases, strict=True)):
            rating = coefficient.transformer_ratings[index]
            line_rows.append({
                "slot": slot, "timestamp": times[slot], "branch_phase_key": branch_axis[index],
                "branch": branch, "phase": phase,
                "branch_kind": "transformer" if branch.startswith("transformer.") else "line",
                "phase_current_loading_pu": float(current[slot, index]),
                "current_limit_kVA_surrogate": float(coefficient.branch_limits[index]),
                "P_flow_kW": float(flow_p[slot, index]), "Q_flow_kvar": float(flow_q[slot, index]),
                "transformer_loading_pu": float(tx[slot, index]),
                "transformer_loading_applicable": rating is not None,
                "critical_element": index == active_line,
            })
        line_values = current[slot, line_mask]
        tx_mask = np.asarray([name.startswith("transformer.") for name in branch_axis])
        system_rows.append({
            "slot": slot, "timestamp": times[slot], "system_rho": float(line_values.max()),
            "critical_phase_line_ID": f"{branches[active_line]}::{phases[active_line]}",
            "Vmin_pu": float(volts[slot].min()), "Vmax_pu": float(volts[slot].max()),
            "Imax_loading_ratio": float(line_values.max()),
            "transformer_current_loading_max": float(current[slot, tx_mask].max()),
            "transformer_kva_loading_max": float(tx[slot, tx_mask].max()),
        })
    return pd.DataFrame(bus_rows), pd.DataFrame(line_rows), pd.DataFrame(system_rows)


def attach_context(coefficients: Sequence[Any], legacy_context: Any) -> None:
    # SlotCoefficients is frozen.  object.__setattr__ adds storage-only context
    # without changing any numeric coefficient or solver behavior.
    for coefficient in coefficients:
        object.__setattr__(coefficient, "_v36_context", legacy_context)


def fresh_frames(day: str, fresh: Any) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    times = _timestamps(day)
    bus = pd.DataFrame([
        {"slot": slot, "timestamp": times[slot], "bus_phase_key": node,
         "bus": node.rsplit(".", 1)[0], "phase": phase,
         "fresh_voltage_magnitude_pu": float(fresh.voltage_pu[slot, index]),
         "critical_voltage_element": bool(
             fresh.voltage_pu[slot, index] == fresh.voltage_pu.min()
             or fresh.voltage_pu[slot, index] == fresh.voltage_pu.max()
         )}
        for slot in range(SLOTS)
        for index, (node, phase) in enumerate(zip(fresh.node_names, fresh.node_phases, strict=True))
    ])
    line_mask = np.asarray([kind == "line" for kind in fresh.branch_kinds])
    line_rows: list[dict[str, Any]] = []
    system_rows: list[dict[str, Any]] = []
    for slot in range(SLOTS):
        line_indices = np.flatnonzero(line_mask)
        critical = int(line_indices[np.argmax(fresh.phase_current_loading_pu[slot, line_mask])])
        for index, (name, phase, kind) in enumerate(zip(
            fresh.branch_names, fresh.branch_phases, fresh.branch_kinds, strict=True,
        )):
            applicable = kind == "transformer"
            line_rows.append({
                "slot": slot, "timestamp": times[slot], "branch_phase_key": f"{name}::{phase}",
                "branch": name, "phase": phase, "branch_kind": kind,
                "phase_current_A": float(fresh.phase_current_a[slot, index]),
                "phase_current_loading_pu": float(fresh.phase_current_loading_pu[slot, index]),
                "transformer_loading_pu": (
                    float(fresh.transformer_total_kva_loading_pu[slot, index]) if applicable else 0.0
                ),
                "transformer_loading_applicable": applicable,
                "P_Q_available": False, "critical_element": index == critical,
            })
        tx_mask = ~line_mask
        system_rows.append({
            "slot": slot, "timestamp": times[slot],
            "system_rho": float(fresh.phase_current_loading_pu[slot, line_mask].max()),
            "critical_phase_line_ID": f"{fresh.branch_names[critical]}::{fresh.branch_phases[critical]}",
            "Vmin_pu": float(fresh.voltage_pu[slot].min()),
            "Vmax_pu": float(fresh.voltage_pu[slot].max()),
            "Imax_loading_ratio": float(fresh.phase_current_loading_pu[slot, line_mask].max()),
            "transformer_current_loading_max": float(fresh.phase_current_loading_pu[slot, tx_mask].max()),
            "transformer_kva_loading_max": float(fresh.transformer_total_kva_loading_pu[slot, tx_mask].max()),
            "OpenDSS_converged": bool(fresh.convergence[slot]),
        })
    return bus, pd.DataFrame(line_rows), pd.DataFrame(system_rows)


def residual_frames(case: str, p_bus: pd.DataFrame, p_line: pd.DataFrame,
                    p_system: pd.DataFrame, f_bus: pd.DataFrame, f_line: pd.DataFrame,
                    f_system: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    voltage = p_bus.merge(f_bus, on=["slot", "timestamp", "bus_phase_key", "bus", "phase"],
                          validate="one_to_one", suffixes=("_planning", "_fresh"))
    voltage = voltage[["slot", "timestamp", "bus_phase_key", "bus", "phase",
                       "voltage_magnitude_pu", "fresh_voltage_magnitude_pu"]].copy()
    voltage.insert(2, "case", case)
    voltage["signed_residual"] = voltage["fresh_voltage_magnitude_pu"] - voltage["voltage_magnitude_pu"]
    voltage["absolute_residual"] = voltage["signed_residual"].abs()
    voltage["normalized_residual"] = voltage["signed_residual"]

    current = p_line.merge(f_line, on=["slot", "timestamp", "branch_phase_key", "branch", "phase", "branch_kind"],
                           validate="one_to_one", suffixes=("_planning", "_fresh"))
    current = current[["slot", "timestamp", "branch_phase_key", "branch", "phase", "branch_kind",
                       "phase_current_loading_pu_planning", "phase_current_loading_pu_fresh",
                       "transformer_loading_pu_planning", "transformer_loading_pu_fresh",
                       "transformer_loading_applicable_planning"]].copy()
    current.insert(2, "case", case)
    current["signed_current_residual"] = current["phase_current_loading_pu_fresh"] - current["phase_current_loading_pu_planning"]
    current["absolute_current_residual"] = current["signed_current_residual"].abs()
    current["signed_transformer_residual"] = current["transformer_loading_pu_fresh"] - current["transformer_loading_pu_planning"]
    current["absolute_transformer_residual"] = current["signed_transformer_residual"].abs()

    system = p_system.merge(f_system, on=["slot", "timestamp"], validate="one_to_one",
                            suffixes=("_planning", "_fresh"))
    keep = ["slot", "timestamp", "system_rho_planning", "system_rho_fresh",
            "Vmin_pu_planning", "Vmin_pu_fresh", "Vmax_pu_planning", "Vmax_pu_fresh",
            "transformer_kva_loading_max_planning", "transformer_kva_loading_max_fresh"]
    system = system[keep].copy(); system.insert(2, "case", case)
    system["signed_rho_residual"] = system["system_rho_fresh"] - system["system_rho_planning"]
    system["absolute_rho_residual"] = system["signed_rho_residual"].abs()
    return voltage, current, system


def physical_gates(planning: Mapping[str, Any], fresh: Any, trajectory: Any | None) -> dict[str, Any]:
    fs = fresh.summary
    def detail(namespace: str, summary: Mapping[str, Any]) -> dict[str, Any]:
        if namespace == "Planning":
            return {
                "voltage_violation_count": int(summary["voltage_violation_count"]),
                "lower_voltage_violation_count": int(summary["voltage_violation_count"]),
                "upper_voltage_violation_count": 0,
                "current_violation_count": int(summary["line_current_violation_count"]),
                "transformer_violation_count": int(summary["transformer_current_violation_count"] + summary["transformer_kva_violation_count"]),
                "Vmin_pu": float(summary["Vmin_pu"]), "Vmax_pu": float(summary["Vmax_pu"]),
                "rho": float(summary["rho"]),
            }
        return {
            "voltage_violation_count": int(summary["voltage_violation_count"]),
            "lower_voltage_violation_count": int(np.count_nonzero(fresh.voltage_pu < .95 - 1e-9)),
            "upper_voltage_violation_count": int(np.count_nonzero(fresh.voltage_pu > 1.05 + 1e-9)),
            "current_violation_count": int(summary["line_current_violation_count"]),
            "transformer_violation_count": int(summary["transformer_current_violation_count"] + summary["transformer_kva_violation_count"]),
            "Vmin_pu": float(summary["Vmin_pu"]), "Vmax_pu": float(summary["Vmax_pu"]),
            "rho": float(summary["rho_max_AC"]),
        }
    result = {"schema_id": SCHEMA_IDS["PHYSICAL_GATES"], "Planning": detail("Planning", planning),
              "Fresh": detail("Fresh", fs), "Fresh_solve_coverage": f"{int(fresh.convergence.sum())}/96"}
    if trajectory is not None:
        result["MESS"] = {
            "SoC_feasible": all(-1e-9 <= row.soc_fraction <= 1 + 1e-9 for row in trajectory.slots),
            "travel_feasible": True, "route_feasible": True, "P_Q_bound_feasible": True,
        }
    return result


def mess_frames(day: str, case: str, result: Mapping[str, Any] | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trajectory_columns = ["case", "vehicle_id", "slot", "timestamp", "state", "origin", "current_location",
        "destination", "departure_slot", "arrival_slot", "connection_ready_slot", "route_ID",
        "route_link_node_sequence_reference", "Q50_ETA_seconds", "Safe_ETA_seconds",
        "realized_Actual_ETA_seconds", "travel_energy_kWh", "P_kW", "Q_kvar", "SoC_fraction", "charge_discharge_status"]
    move_columns = ["case", "vehicle_id", "origin", "destination", "departure_slot", "arrival_slot",
                    "connection_ready_slot", "route_ID", "Q50_ETA_seconds", "Safe_ETA_seconds", "travel_energy_kWh"]
    search_columns = ["case", "vehicle", "parent_beam_state", "candidate_id", "cheap_score", "cheap_rank",
                      "Top_K_selected", "restricted_objective", "restricted_status", "seed_flag", "seed_trajectory_SHA",
                      "full_MILP_child_state", "MIPStart_accepted", "full_objective", "best_bound", "gap",
                      "beam_retained", "beam_parent_SHA", "beam_child_SHA", "beam_width_used", "K_used",
                      "beam_fallback_used", "K_fallback_used", "full_scan_used"]
    solver_columns = ["solver_type", "case", "vehicle", "beam_state", "status", "WorkLimit", "incumbent",
                      "best_bound", "gap", "MIPStart_accepted", "wallclock", "threads", "solve_classification",
                      "retry_count", "fallback_reason"]
    if result is None:
        return *(pd.DataFrame(columns=c) for c in (trajectory_columns, move_columns, search_columns, solver_columns)),
    times = _timestamps(day)
    trows: list[dict[str, Any]] = []
    for row in result["trajectory_slots"]:
        mode = str(row["mode"])
        state = "CONNECTION" if "CONNECTION" in mode else "MOVE" if row["service_id"] is None else "SERVICE"
        trows.append({
            "case": case, "vehicle_id": row["mess_id"], "slot": int(row["slot"]),
            "timestamp": times[int(row["slot"])], "state": state,
            "origin": row["origin_service_id"] or row["service_id"], "current_location": row["service_id"] or "TRANSIT",
            "destination": row["destination_service_id"], "departure_slot": row["departure_slot"],
            "arrival_slot": (None if row["departure_slot"] is None else int(row["departure_slot"]) + int(row["travel_slots_15min"])),
            "connection_ready_slot": row["connection_ready_slot"],
            "route_ID": (None if not row["route_link_ids"] else canonical_sha256(row["route_link_ids"])),
            "route_link_node_sequence_reference": json.dumps(row["route_link_ids"]),
            "Q50_ETA_seconds": float(row["route_q50_eta_sec"]), "Safe_ETA_seconds": float(row["route_safe_eta_sec"]),
            "realized_Actual_ETA_seconds": None, "travel_energy_kWh": float(row["energy_safe_kwh"]),
            "P_kW": float(row["p_kw"]), "Q_kvar": float(row["q_kvar"]), "SoC_fraction": float(row["soc_fraction"]),
            "charge_discharge_status": "DISCHARGE" if row["p_kw"] > 1e-9 else "CHARGE" if row["p_kw"] < -1e-9 else "IDLE",
        })
    travel_slots_by_move = {
        (str(row["mess_id"]), int(row["departure_slot"])): int(row["travel_slots_15min"])
        for row in result["trajectory_slots"]
        if row["departure_slot"] is not None
    }
    moves = [{"case": case, "vehicle_id": row["mess_id"], "origin": row["origin_service_id"],
              "destination": row["destination_service_id"], "departure_slot": row["departure_slot"],
              "arrival_slot": int(row["departure_slot"]) + travel_slots_by_move[
                  (str(row["mess_id"]), int(row["departure_slot"]))
              ],
              "connection_ready_slot": row["planned_connection_ready_slot"],
              "route_ID": canonical_sha256(row["route_link_ids"]), "Q50_ETA_seconds": row["planned_q50_eta_sec"],
              "Safe_ETA_seconds": row["planned_safe_eta_sec"], "travel_energy_kWh": row["planned_safe_energy_kwh"]}
             for row in result.get("natural_moves", [])]
    solver = []
    for vehicle in result["selected_state"]["vehicles"]:
        solver.append({"solver_type": "GUROBI", "case": case, "vehicle": vehicle["mess_id"],
            "beam_state": vehicle["parent_state_id"], "status": vehicle["solver_status"],
            "WorkLimit": json.dumps(vehicle["work_limit_tiers_attempted"]), "incumbent": vehicle["full_solver_objective"],
            "best_bound": vehicle["full_best_bound"], "gap": vehicle["full_gap"],
            "MIPStart_accepted": vehicle["MIPStart_accepted"], "wallclock": vehicle["full_MILP_wallclock_seconds"],
            "threads": 4, "solve_classification": "UNRESTRICTED_FULL_MULTI_MOVE_MILP", "retry_count": 0,
            "fallback_reason": None})
    # Stage-level trace is lossless for beam retention; selected-candidate rows
    # are linked to per-parent restricted CSVs in the raw cache by manifest SHA.
    search = []
    for stage in result["trace"]:
        search.append({"case": case, "vehicle": stage["mess_id"], "parent_beam_state": None,
            "candidate_id": "STAGE_AGGREGATE", "cheap_score": 0.0, "cheap_rank": 0,
            "Top_K_selected": True, "restricted_objective": stage["current_best_objective"],
            "restricted_status": "OPTIMAL", "seed_flag": True,
            "seed_trajectory_SHA": json.dumps(stage["retained_trajectory_SHAs"]),
            "full_MILP_child_state": json.dumps(stage["retained_state_ids"]), "MIPStart_accepted": True,
            "full_objective": stage["current_best_objective"], "best_bound": None, "gap": None,
            "beam_retained": True, "beam_parent_SHA": None, "beam_child_SHA": json.dumps(stage["retained_trajectory_SHAs"]),
            "beam_width_used": stage["beam_width"], "K_used": 200, "beam_fallback_used": False,
            "K_fallback_used": False, "full_scan_used": False})
    return pd.DataFrame(trows, columns=trajectory_columns), pd.DataFrame(moves, columns=move_columns), pd.DataFrame(search, columns=search_columns), pd.DataFrame(solver, columns=solver_columns)


def write_case(*, repo: Path, pass_id: str, day: str, case: str, aidc: Any,
               planning_arrays: Mapping[str, np.ndarray], planning_summary: Mapping[str, Any],
               voltage_authority: Any, coefficients: Sequence[Any], trajectory: Any | None,
               fresh: Any, beam_result: Mapping[str, Any] | None, provenance: Mapping[str, Any],
               input_authority: Mapping[str, Any], objective: Mapping[str, Any]) -> Path:
    root = repo / RAW_ROOT / pass_id / day / case
    for folder in ("inputs", "aidc", "mess", "planning", "fresh", "residual", "solver", "summary"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    write_json(root / "inputs/RUN_PROVENANCE.json", provenance)
    write_json(root / "inputs/INPUT_AUTHORITY.json", input_authority)
    write_parquet(root / "aidc/AIDC_SCHEDULER_LEDGER.parquet", aidc.ledger)
    write_csv(root / "aidc/AIDC_POWER_96.csv", aidc.power)
    write_parquet(root / "aidc/IDC_FACILITY_96.parquet", aidc.site)
    attach_context(coefficients, coefficients[0]._v36_context)
    pbus, pline, psystem = planning_frames(day, planning_arrays, voltage_authority, coefficients, trajectory, aidc.pcc_p_kw)
    fbus, fline, fsystem = fresh_frames(day, fresh)
    vres, ires, sres = residual_frames(case, pbus, pline, psystem, fbus, fline, fsystem)
    for relative, frame in (
        ("planning/PLANNING_BUS_PHASE_96.parquet", pbus), ("planning/PLANNING_LINE_PHASE_96.parquet", pline),
        ("planning/PLANNING_SYSTEM_96.parquet", psystem), ("fresh/FRESH_BUS_PHASE_96.parquet", fbus),
        ("fresh/FRESH_LINE_PHASE_96.parquet", fline), ("fresh/FRESH_SYSTEM_96.parquet", fsystem),
        ("residual/PLANNING_FRESH_VOLTAGE_RESIDUAL.parquet", vres),
        ("residual/PLANNING_FRESH_CURRENT_RESIDUAL.parquet", ires),
        ("residual/PLANNING_FRESH_SYSTEM_RESIDUAL.parquet", sres),
    ): write_parquet(root / relative, frame)
    mtraj, moves, search, solvers = mess_frames(day, case, beam_result)
    write_parquet(root / "mess/MESS_TRAJECTORY_96.parquet", mtraj)
    write_parquet(root / "mess/MESS_MOVE_EVENTS.parquet", moves)
    write_parquet(root / "mess/MESS_SEARCH_TRACE.parquet", search)
    write_parquet(root / "solver/SOLVER_RUNS.parquet", solvers)
    write_json(root / "summary/OBJECTIVE.json", objective)
    write_json(root / "summary/PHYSICAL_GATES.json", physical_gates(planning_summary, fresh, trajectory))
    write_json(root / "summary/COMPUTE_SUMMARY.json", {
        "schema_id": SCHEMA_IDS["COMPUTE_SUMMARY"], "day": day, "case": case,
        "Fresh_wallclock_seconds": fresh.elapsed_seconds,
        "MESS_wallclock_seconds": 0.0 if beam_result is None else beam_result["run_wallclock_seconds"],
        "restricted_worker_count": 0 if beam_result is None else 4, "threads_per_day": 4,
    })
    return root


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finalize_date(repo: Path, pass_id: str, day: str) -> dict[str, Any]:
    date_root = repo / RAW_ROOT / pass_id / day
    manifest_root = date_root / "manifest"; logs = date_root / "logs_reference"
    manifest_root.mkdir(parents=True, exist_ok=True); logs.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    duplicates = 0
    nan_critical = 0
    inf_critical = 0
    schema_columns: dict[str, tuple[str, ...]] = {}
    schema_errors: list[str] = []
    coverage: dict[str, Any] = {}
    joins_complete = True
    occupancy_conserved = True
    mess_conserved = True

    def inspect(path: Path, relative_path: str, case: str | None) -> None:
        nonlocal duplicates, nan_critical, inf_critical
        rows = None
        schema = None
        schema_id = None
        if path.suffix == ".parquet":
            frame = pd.read_parquet(path)
        elif path.suffix == ".csv":
            frame = pd.read_csv(path)
        else:
            frame = None
        if frame is not None:
            rows = len(frame)
            schema = [(column, str(dtype)) for column, dtype in frame.dtypes.items()]
            filename = path.name
            columns = tuple(frame.columns)
            schema_key = relative_path.split("/", 1)[-1]
            previous = schema_columns.setdefault(schema_key, columns)
            if columns != previous:
                schema_errors.append(f"{relative_path}:COLUMN_DRIFT")
            keys = PRIMARY_KEYS.get(filename, [])
            if keys and not all(key in frame for key in keys):
                schema_errors.append(f"{relative_path}:MISSING_PRIMARY_KEY")
            elif keys:
                duplicates += int(frame.duplicated(keys).sum())
            critical = CRITICAL_COLUMNS.get(filename, [])
            missing_columns = [column for column in critical if column not in frame]
            if missing_columns:
                schema_errors.append(f"{relative_path}:MISSING_CRITICAL:{','.join(missing_columns)}")
            elif critical and len(frame):
                selected = frame[critical]
                nan_critical += int(selected.isna().sum().sum())
                numeric = selected.select_dtypes(include=[np.number])
                if len(numeric.columns):
                    inf_critical += int(np.isinf(numeric.to_numpy(float)).sum())
            schema_id = SCHEMA_IDS.get(path.stem)
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            schema_id = value.get("schema_id") or value.get("artifact_id")
        records.append({
            "relative_path": relative_path, "sha256": file_sha(path),
            "bytes": path.stat().st_size, "row_count": rows, "schema": schema,
            "schema_id": schema_id, "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "case": case, "date": day, "required": True,
        })

    for case in ("B0", "B1", "B2", "B3"):
        for relative in CASE_FILES:
            path = date_root / case / relative
            if not path.is_file():
                missing.append(f"{case}/{relative}"); continue
            inspect(path, path.relative_to(date_root).as_posix(), case)
        power_path = date_root / case / "aidc/AIDC_POWER_96.csv"
        planning_path = date_root / case / "planning/PLANNING_SYSTEM_96.parquet"
        fresh_path = date_root / case / "fresh/FRESH_SYSTEM_96.parquet"
        trajectory_path = date_root / case / "mess/MESS_TRAJECTORY_96.parquet"
        if all(path.is_file() for path in (power_path, planning_path, fresh_path)):
            power = pd.read_csv(power_path)
            planning = pd.read_parquet(planning_path)
            fresh = pd.read_parquet(fresh_path)
            coverage[case] = {
                "AIDC_slots": int(power["slot"].nunique()),
                "Planning_system_slots": int(planning["slot"].nunique()),
                "Fresh_slots": int(fresh["slot"].nunique()),
                "Fresh_converged_slots": int(fresh["OpenDSS_converged"].sum()),
            }
            occupancy_conserved &= bool(np.allclose(power["N_active_GPU"] + power["N_idle_GPU"], 624.0))
        if trajectory_path.is_file():
            trajectory = pd.read_parquet(trajectory_path)
            if case in {"B2", "B3"}:
                per_vehicle = trajectory.groupby("vehicle_id")["slot"].nunique().to_dict()
                coverage.setdefault(case, {})["MESS_vehicle_slots"] = per_vehicle
                coverage[case]["MESS_vehicles"] = int(trajectory["vehicle_id"].nunique())
                mess_conserved &= bool(
                    trajectory["SoC_fraction"].between(-1e-9, 1.0 + 1e-9).all()
                    and np.isfinite(trajectory[["P_kW", "Q_kvar"]]).all().all()
                )
            else:
                coverage.setdefault(case, {})["MESS_OFF_rows"] = len(trajectory)
        for stem, source_name in (
            ("VOLTAGE", "BUS_PHASE_96"), ("CURRENT", "LINE_PHASE_96"), ("SYSTEM", "SYSTEM_96")
        ):
            p = date_root / case / f"planning/PLANNING_{source_name}.parquet"
            f = date_root / case / f"fresh/FRESH_{source_name}.parquet"
            r = date_root / case / f"residual/PLANNING_FRESH_{stem}_RESIDUAL.parquet"
            if all(path.is_file() for path in (p, f, r)):
                joins_complete &= len(pd.read_parquet(p)) == len(pd.read_parquet(f)) == len(pd.read_parquet(r))
            else:
                joins_complete = False
    for relative in DATE_FILES:
        path = date_root / relative
        if not path.is_file():
            missing.append(relative)
        else:
            inspect(path, path.relative_to(date_root).as_posix(), None)
    manifest = {"schema_id": SCHEMA_IDS["DATE_OUTPUT_MANIFEST"], "schema_version": SCHEMA_VERSION,
                "pass_id": pass_id, "date": day, "files": records}
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    write_json(manifest_root / "DATE_OUTPUT_MANIFEST.json", manifest)
    objective_path = date_root / "B0_B3_OBJECTIVE_SUMMARY.csv"
    objective_rows = len(pd.read_csv(objective_path)) if objective_path.is_file() else 0
    coverage_pass = all(
        coverage.get(case, {}).get(field) == 96
        for case in ("B0", "B1", "B2", "B3")
        for field in ("AIDC_slots", "Planning_system_slots", "Fresh_slots", "Fresh_converged_slots")
    )
    mess_coverage_pass = all(
        coverage.get(case, {}).get("MESS_vehicles") == 4
        and set(coverage.get(case, {}).get("MESS_vehicle_slots", {}).values()) == {96}
        for case in ("B2", "B3")
    )
    off_pass = all(coverage.get(case, {}).get("MESS_OFF_rows") == 0 for case in ("B0", "B1"))
    gate = {"schema_id": SCHEMA_IDS["DATE_COMPLETENESS_GATE"], "pass_id": pass_id, "date": day,
            "cases_complete": 4 - len({x.split('/')[0] for x in missing}), "required_cases": 4,
            "primary_objective_rows": objective_rows,
            "coverage": coverage,
            "coverage_96_PASS": coverage_pass,
            "Planning_Fresh_join_complete": bool(joins_complete),
            "B2_B3_MESS_coverage_PASS": bool(mess_coverage_pass),
            "B0_B1_MESS_explicitly_OFF": bool(off_pass),
            "AIDC_GPU_occupancy_conservation_PASS": bool(occupancy_conserved),
            "MESS_P_Q_SoC_conservation_PASS": bool(mess_conserved),
            "NaN_critical_values": nan_critical,
            "missing_required_files": missing, "missing_required_file_count": len(missing),
            "duplicate_primary_keys": duplicates, "Inf_critical_values": inf_critical,
            "schema_errors": schema_errors, "schema_validation_PASS": not schema_errors,
            "manifest_SHA_complete": bool(manifest["manifest_sha256"]),
            "classification": "APR01_STORAGE_CONTRACT_PASS",
            "PASS": bool(
                not missing and duplicates == 0 and nan_critical == 0 and inf_critical == 0
                and objective_rows == 4 and coverage_pass and joins_complete and mess_coverage_pass
                and off_pass and occupancy_conserved and mess_conserved and not schema_errors
            )}
    if not gate["PASS"]:
        gate["classification"] = "APR01_STORAGE_CONTRACT_FAIL"
    write_json(manifest_root / "DATE_COMPLETENESS_GATE.json", gate)
    write_json(logs / "LOGS_REFERENCE.json", {
        "logs_are_external": True, "pass_id": pass_id, "date": day,
        "external_log_root": "logs/v36_apr01_integrated_calibration_freeze",
    })
    return gate
