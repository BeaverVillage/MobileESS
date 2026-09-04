"""Targeted Apr-01 V34 MESS zero-MOVE functionality audit."""

from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
import time

import gurobipy as gp
from gurobipy import GRB
import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v28r2.electrical_context import build_electrical_context
from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v28r2.formulation import materialize_formulation_data
from dayahead.v33m import MessMobilityInputs, ServicePCCMapping, add_mess_mobility_block, extract_mess_trajectory
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v34.integrated_mess import solve_integrated_mess
from dayahead.v34.traffic_authority import build_april_route_table
from tools.v34.run_integration_smoke import (
    DAY,
    OUT,
    SOURCE_DAY,
    SOURCE_REPO,
    _aggregate_grid_audit,
    _base_schedule,
    _mapping,
    _mess_actuation_audit,
    _write,
)


MESS_IDS = ("MESS01", "MESS02", "MESS03", "MESS04")
INITIAL = {mess: f"STA{index:02d}" for index, mess in enumerate(MESS_IDS, 1)}


def _pruning_audit(route_table) -> dict[str, object]:
    horizon = len(route_table.departure_slots)
    services = route_table.service_ids
    before = horizon * len(services) * len(services)
    self_duplicates = horizon * len(services)
    unreachable = 0
    beyond = 0
    retained = []
    for slot in range(horizon):
        for origin in services:
            for destination in services:
                if origin == destination:
                    continue
                route = route_table[slot, origin, destination]
                if not route.route_link_ids or route.connection_ready_slots_15min <= 0:
                    unreachable += 1
                elif slot + route.connection_ready_slots_15min > horizon:
                    beyond += 1
                else:
                    retained.append((slot, origin, destination))
    return {
        "candidate_MOVE_count_before_exact_pruning": before,
        "candidate_MOVE_count_after_exact_pruning": len(retained),
        "removed_self_STAY_duplicate": self_duplicates,
        "removed_ready_arrival_beyond_horizon": beyond,
        "removed_unreachable": unreachable,
        "fixed_to_zero_by_construction": 0,
        "unique_destination_count_represented": len({key[2] for key in retained}),
        "unique_departure_slot_count_represented": len({key[0] for key in retained}),
    }


def _resource_only_probe(route_table, mapping: dict[str, str], mess_id: str) -> tuple[dict[str, object], object]:
    inputs = MessMobilityInputs.create(
        route_table,
        96,
        {mess_id: INITIAL[mess_id]},
        ServicePCCMapping(mapping, "V34_FROZEN_C376_MAPPING"),
        electrical_authority=MessElectricalAuthority.from_repository(),
    )
    model = gp.Model(f"v34_zero_move_resource_probe_{mess_id}")
    model.Params.OutputFlag = 0
    model.Params.Threads = 4
    model.Params.Seed = 20260828
    model.Params.TimeLimit = 120.0
    model.Params.SolutionLimit = 1
    model.Params.MIPFocus = 1
    block = add_mess_mobility_block(model, inputs)
    model.addConstr(block.number_move_departures >= 1, name="diagnostic_at_least_one_MOVE")
    max_route = max(route.energy_safe_kwh for route in block.move_route.values())
    model.setObjective(
        (96.0 * max_route + 1.0) * block.number_move_departures
        + block.total_travel_energy
        + 1e-12 * block.deterministic_move_ordinal,
        GRB.MINIMIZE,
    )
    started = time.perf_counter()
    model.optimize()
    runtime = time.perf_counter() - started
    feasible = model.SolCount > 0
    trajectory = extract_mess_trajectory(block) if feasible else None
    commitments = () if trajectory is None else trajectory.planned_move_commitments()
    trace = None
    binding = False
    if commitments:
        move = commitments[0]
        key = (mess_id, move.departure_slot, move.origin_service_id, move.destination_service_id)
        route = route_table[move.departure_slot, move.origin_service_id, move.destination_service_id]
        bound_route = block.move_route[key]
        binding = bound_route == route and key in block.move
        trace = {
            "origin": move.origin_service_id,
            "destination": move.destination_service_id,
            "departure_slot": move.departure_slot,
            "route_link_count": len(move.route_link_ids),
            "Q50_ETA_seconds": move.planned_q50_eta_sec,
            "Safe_ETA_seconds": move.planned_safe_eta_sec,
            "connection_ready_slot": move.planned_connection_ready_slot,
            "travel_energy_kWh": move.planned_safe_energy_kwh,
            "same_route_record_reaches_MOVE_binary": binding,
            "travel_debit_coefficient_matches_route": abs(bound_route.energy_safe_kwh - move.planned_safe_energy_kwh) <= 1e-9,
            "flow_constraint_names_present": all(
                model.getConstrByName(name) is not None
                for name in (
                    f"mess_flow_out[{mess_id},{move.departure_slot},{move.origin_service_id}]",
                    f"mess_flow_in[{mess_id},{move.planned_connection_ready_slot},{move.destination_service_id}]",
                )
            ),
        }
    result = {
        "mess_id": mess_id,
        "classification": "MESS_MOVE_FEASIBLE_WITHOUT_GRID" if feasible else "MESS_MOBILITY_PHYSICS_OR_FLOW_OVERCONSTRAINED",
        "feasible": feasible,
        "solver_status": int(model.Status),
        "termination": "OPTIMAL" if model.Status == GRB.OPTIMAL else f"STATUS_{model.Status}",
        "runtime_seconds": runtime,
        "MOVE_binary_count": len(block.move),
        "STAY_variable_count": len(block.stay),
        "binary_count": int(model.NumBinVars),
        "constraint_count": int(model.NumConstrs),
        "selected_MOVE_count": len(commitments),
        "route_to_MILP_binding_PASS": binding,
        "trace": trace,
    }
    return result, trajectory


def _grid_coupling(coefficients, voltage_authority, aidc: np.ndarray) -> dict[str, object]:
    names = tuple(map(str, voltage_authority["control_names"]))
    p_index = names.index("mess_p_kw[STA01]")
    q_index = names.index("mess_q_kvar[STA01]")
    coefficient = coefficients[0]
    base = np.r_[aidc[0], np.zeros(48)]
    imposed = base.copy()
    imposed[p_index] = 100.0
    imposed[q_index] = 50.0
    v0_sq = coefficient.voltage_constant + coefficient.voltage_matrix.T @ base
    v1_sq = coefficient.voltage_constant + coefficient.voltage_matrix.T @ imposed
    i0 = coefficient.current_constant + coefficient.current_matrix.T @ base
    i1 = coefficient.current_constant + coefficient.current_matrix.T @ imposed
    delta = imposed - base
    v_predicted = coefficient.voltage_matrix.T @ delta
    i_predicted = coefficient.current_matrix.T @ delta
    residual = max(float(np.max(np.abs((v1_sq - v0_sq) - v_predicted))), float(np.max(np.abs((i1 - i0) - i_predicted))))
    return {
        "diagnostic_injection": {"service": "STA01", "slot": 0, "P_kW": 100.0, "Q_kvar": 50.0},
        "voltage_squared_delta_min": float((v1_sq - v0_sq).min()),
        "voltage_squared_delta_max": float((v1_sq - v0_sq).max()),
        "current_delta_min_pu": float((i1 - i0).min()),
        "current_delta_max_pu": float((i1 - i0).max()),
        "matrix_identity_max_abs_residual": residual,
        "sign_and_unit_trace": "delta_grid = J_P*(+100 kW injection) + J_Q*(+50 kvar injection)",
        "pass": bool(np.max(np.abs(v1_sq - v0_sq)) > 1e-10 and np.max(np.abs(i1 - i0)) > 1e-10 and residual < 1e-12),
    }


def main() -> int:
    smoke_path = OUT / "V34_INTEGRATION_SMOKE.json"
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    normal = {row["case"]: row for row in smoke["cases"]}
    if not all("objective_value" in run for case in ("B2", "B3") for run in normal[case]["mess"]["per_MESS_runtime"]):
        raise RuntimeError("V34_ZERO_MOVE_AUDIT_REQUIRES_REFRESHED_NORMAL_SMOKE")

    route_started = time.perf_counter()
    bundle, graph, route_table = build_april_route_table(REPO, DAY)
    route_seconds = time.perf_counter() - route_started
    mapping = _mapping()
    pruning = _pruning_audit(route_table)
    resource_probes = []
    for mess_id in MESS_IDS:
        probe, _ = _resource_only_probe(route_table, mapping, mess_id)
        resource_probes.append(probe)

    data = materialize_formulation_data(SOURCE_REPO, DAY)
    electrical = build_electrical_context(SOURCE_REPO, data, SOURCE_DAY / "dayahead/electrical_cache")
    try:
        coefficients = tuple(
            slot_coefficients(electrical.legacy_context, electrical.voltage, electrical.current, slot)
            for slot in range(96)
        )
        b2 = _base_schedule("B2")
        aidc = np.asarray(b2["planning_pcc_power_kw"], dtype=float)
        coupling = _grid_coupling(coefficients, electrical.voltage, aidc)
        forced = solve_integrated_mess(
            case="B2",
            aidc_pcc_kw_96x12=aidc,
            electrical_context=electrical.legacy_context,
            voltage_authority=electrical.voltage,
            current_authority=electrical.current,
            route_table=route_table,
            service_to_pcc=mapping,
            initial_service_by_mess={"MESS01": INITIAL["MESS01"]},
            grid_coefficients=coefficients,
            force_at_least_one_move=True,
        )
    finally:
        electrical.voltage.close(); electrical.current.close()

    normal_b2_first = normal["B2"]["mess"]["per_MESS_runtime"][0]
    forced_moves = forced.trajectory.planned_move_commitments()
    forced_move = forced_moves[0] if forced_moves else None
    all_normal_optimal = all(
        run["termination"] == "OPTIMAL"
        for case in ("B2", "B3")
        for run in normal[case]["mess"]["per_MESS_runtime"]
    )
    construction_pass = pruning["candidate_MOVE_count_after_exact_pruning"] > 100 and pruning["unique_destination_count_represented"] > 1 and pruning["unique_departure_slot_count_represented"] > 1
    resource_pass = all(row["feasible"] for row in resource_probes)
    binding_pass = all(row["route_to_MILP_binding_PASS"] for row in resource_probes)
    forced_pass = bool(forced_moves)
    sequential_pass = all(
        run["future_vehicle_variable_count"] == 0 and run["current_vehicle_free_variable_count"] > 0
        for case in ("B2", "B3") for run in normal[case]["mess"]["per_MESS_runtime"]
    )
    if not construction_pass:
        primary = "V34_MESS_MOVE_VARIABLE_CONSTRUCTION_DEFECT"
    elif not binding_pass:
        primary = "V34_MESS_ROUTE_TO_MILP_BINDING_DEFECT"
    elif not resource_pass:
        primary = "V34_MESS_MOBILITY_FLOW_OVERCONSTRAINED"
    elif not coupling["pass"]:
        primary = "V34_MESS_GRID_COUPLING_DEFECT"
    elif not sequential_pass:
        primary = "V34_MESS_SEQUENTIAL_INTEGRATION_DEFECT"
    elif not all_normal_optimal:
        primary = "V34_MESS_ZERO_MOVE_FEASIBLE_INCUMBENT_NOT_OPTIMAL"
    elif forced_pass and forced.objective >= float(normal_b2_first["objective_value"]) - 1e-9:
        primary = "V34_MESS_ZERO_MOVE_LEGITIMATE_STAY_OPTIMUM"
    else:
        primary = "V34_MESS_ZERO_MOVE_INCONCLUSIVE"

    result = {
        "artifact_id": "V34_FAST_MESS_ZERO_MOVE_DEFECT_AUDIT_V1",
        "status": "PASS" if all((construction_pass, binding_pass, resource_pass, forced_pass)) else "FAIL_DEFECT",
        "day": DAY,
        "diagnostic_only": True,
        "science_parameters_changed": False,
        "route_table_build_seconds": route_seconds,
        "traffic_bundle_sha256": bundle.canonical_sha256,
        "route_table_sha256": route_table.canonical_sha256,
        "route_graph_nodes": graph.node_count,
        "route_graph_links": graph.link_count,
        "move_construction": {mess_id: dict(pruning, MOVE_binaries_actually_added=resource_probes[index]["MOVE_binary_count"], STAY_variable_count=resource_probes[index]["STAY_variable_count"]) for index, mess_id in enumerate(MESS_IDS)},
        "normal_B2_B3": {case: normal[case]["mess"] for case in ("B2", "B3")},
        "normal_solver_interpretation": (
            "OPTIMAL_STAY_INTERPRETABLE" if all_normal_optimal
            else "ZERO_MOVE_NOT_SCIENTIFICALLY_INTERPRETABLE_SOLVER_INCOMPLETE"
        ),
        "resource_only_mobility_probes": resource_probes,
        "route_to_MILP_binding_PASS": binding_pass,
        "grid_coupling": coupling,
        "sequential_cumulative_PQ_PASS": sequential_pass,
        "forced_MOVE_B2_MESS01": {
            "feasible": bool(forced_moves),
            "solver": {
                "termination": forced.termination,
                "incumbent_available": forced.incumbent_available,
                "objective_value": forced.objective,
                "best_bound": forced.best_bound,
                "MIP_gap": forced.mip_gap,
                "runtime_seconds": forced.solve_seconds,
                "variable_count": forced.variable_count,
                "binary_count": forced.binary_count,
                "constraint_count": forced.constraint_count,
            },
            "selected_MOVE_count": len(forced_moves),
            "selected_MOVE": None if forced_move is None else asdict(forced_move),
            "objective_delta_vs_normal_STAY_incumbent": forced.objective - float(normal_b2_first["objective_value"]),
            "rho_delta_vs_normal_STAY_incumbent": forced.planning_rho - float(normal_b2_first["planning_rho"]),
            "travel_energy_increase_kWh": sum(move.planned_safe_energy_kwh for move in forced_moves),
            "terminal_SoC": MessElectricalAuthority.from_repository().terminal_energy_kwh / MessElectricalAuthority.from_repository().capacity_kwh,
            "actuation": _mess_actuation_audit(forced.trajectory, ("MESS01",)),
            "Fresh_OpenDSS_run": False,
        },
        "primary_classification": primary,
        "mobility_functionally_enabled": all((construction_pass, binding_pass, resource_pass, forced_pass)),
        "V34_April_campaign_may_continue": all((construction_pass, binding_pass, resource_pass, forced_pass)),
    }
    _write(OUT / "V34_FAST_MESS_ZERO_MOVE_DEFECT_AUDIT.json", result)
    print(json.dumps({
        "status": result["status"],
        "primary_classification": primary,
        "normal_solver_interpretation": result["normal_solver_interpretation"],
        "resource_probes": [{"mess_id": row["mess_id"], "feasible": row["feasible"], "moves": row["selected_MOVE_count"]} for row in resource_probes],
        "forced_move_feasible": bool(forced_moves),
        "grid_coupling_PASS": coupling["pass"],
        "sequential_PASS": sequential_pass,
        "campaign_may_continue": result["V34_April_campaign_may_continue"],
    }, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
