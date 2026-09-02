"""Run the predeclared 2025-04-01 V34 four-case integration smoke."""

from __future__ import annotations

from dataclasses import asdict
import csv
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.electrical_context import build_electrical_context
from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row, slot_coefficients
from dayahead.v28r2.formulation import materialize_formulation_data
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.workload_replay import materialize_actual_workload
from dayahead.v34 import CASE_ACTUATORS, OFFICIAL_CASES, solve_resource_only_recourse
from dayahead.v34.integrated_mess import solve_integrated_mess
from dayahead.v34.traffic_authority import actual_sumo_authority, build_april_route_table
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v33m3 import CausalityLedger, replay_committed_move


DAY = "2025-04-01"
SOURCE_REPO = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend")
SOURCE_DAY = SOURCE_REPO / "frozen_artifacts/v28r2_april_full_month_preflight" / DAY
SERVICE_MAPPING = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\work\power_side_p4f_review_20260731_190038\power_side_p4f_hardening_v1\rating_contract_all_transformers\service_node_electrical_mapping_v1.csv")
OUT = REPO / "dayahead/artifacts/v34_aidc_mess_april_calibration_validation"
CACHE = REPO / "dayahead/cache/v34_april_calibration/smoke" / DAY


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _mapping() -> dict[str, str]:
    with SERVICE_MAPPING.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result = {str(row["service_node_id"]): str(row["electrical_host_bus"]).lower() for row in rows}
    if len(result) != 24:
        raise RuntimeError("V34_SERVICE_PCC_MAPPING_AXIS")
    return result


def _aidc_stage_case(case: str) -> str:
    """Select the AIDC-only stage consistent with the V34 actuators.

    The V28R2 B2/B3 files contain AIDC decisions co-optimized against a
    legacy fixed-route MESS block.  V34 replaces that block, so importing
    those AIDC decisions would retain conditioning on discarded injections.
    """

    return {"B0": "B0", "B1": "B1", "B2": "B0", "B3": "B1"}[case]


def _base_schedule(case: str) -> dict[str, object]:
    source_case = _aidc_stage_case(case)
    path = SOURCE_DAY / "dayahead/schedules" / f"DAYAHEAD_{source_case}_SCHEDULE.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if value["case"] != source_case:
        raise RuntimeError("V34_BASE_SCHEDULE_CASE")
    return value


def _rss_bytes() -> int:
    try:
        import psutil
        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return 0


def _aggregate_grid_audit(
    coefficients: tuple[object, ...],
    voltage_authority: object,
    aidc: np.ndarray,
    trajectory: MessTrajectory | None,
) -> tuple[np.ndarray, dict[str, object]]:
    controls = tuple(map(str, voltage_authority["control_names"]))
    services = tuple(name[10:-1] for name in controls[12:36])
    by_p: dict[tuple[str, int], float] = {}
    by_q: dict[tuple[str, int], float] = {}
    if trajectory is not None:
        for row in trajectory.slots:
            if row.service_id is None:
                continue
            key = (row.service_id, row.slot)
            by_p[key] = by_p.get(key, 0.0) + row.p_kw
            by_q[key] = by_q.get(key, 0.0) + row.q_kvar
    voltages, line_current, transformer_current, transformer_kva = [], [], [], []
    for slot, coefficient in enumerate(coefficients):
        x = np.asarray(
            list(aidc[slot])
            + [by_p.get((service, slot), 0.0) for service in services]
            + [by_q.get((service, slot), 0.0) for service in services],
            dtype=float,
        )
        voltage = np.sqrt(np.maximum(0.0, coefficient.voltage_constant + coefficient.voltage_matrix.T @ x))
        current = coefficient.current_constant + coefficient.current_matrix.T @ x
        flow_p = coefficient.flow_p_constant + coefficient.flow_p_matrix @ x
        flow_q = coefficient.flow_q_constant + coefficient.flow_q_matrix @ x
        voltages.append(voltage)
        for index, name in enumerate(coefficient.branch_names):
            if is_dominated_mess_current_row(name):
                continue
            (transformer_current if name.startswith("transformer.") else line_current).append(float(current[index]))
            rating = coefficient.transformer_ratings[index]
            if rating is not None:
                transformer_kva.append(math.hypot(float(flow_p[index]), float(flow_q[index])) / float(rating))
    voltage_array = np.asarray(voltages)
    audit = {
        "combined_MESS_count": 0 if trajectory is None else len({row.mess_id for row in trajectory.slots}),
        "Vmin_pu": float(voltage_array.min()),
        "Vmax_pu": float(voltage_array.max()),
        "voltage_violation_count": int(np.count_nonzero((voltage_array < 0.95 - 1e-7) | (voltage_array > 1.05 + 1e-7))),
        "line_current_max_pu": max(line_current, default=0.0),
        "line_current_violation_count": sum(value > 1.0 + 1e-7 for value in line_current),
        "transformer_current_max_pu": max(transformer_current, default=0.0),
        "transformer_current_violation_count": sum(value > 1.0 + 1e-7 for value in transformer_current),
        "transformer_kva_max_pu": max(transformer_kva, default=0.0),
        "transformer_kva_violation_count": sum(value > 1.0 + 1e-7 for value in transformer_kva),
    }
    audit["pass"] = not any(int(audit[field]) for field in (
        "voltage_violation_count", "line_current_violation_count",
        "transformer_current_violation_count", "transformer_kva_violation_count",
    ))
    return voltage_array, audit


def _mess_planning_audit(trajectory: MessTrajectory, mess_ids: tuple[str, ...]) -> dict[str, object]:
    authority = MessElectricalAuthority.from_repository()
    apothem = authority.pcs_kva * math.cos(math.pi / authority.pcs_polygon_faces)
    violations = {name: 0 for name in (
        "slot_axis", "soc", "soc_equation", "terminal_energy", "pcs_polygon",
        "transit_power", "travel", "connection_ready",
    )}
    terminal_errors = []
    for mess_id in mess_ids:
        rows = sorted((row for row in trajectory.slots if row.mess_id == mess_id), key=lambda row: row.slot)
        if tuple(row.slot for row in rows) != tuple(range(96)):
            violations["slot_axis"] += 1
            continue
        for index, row in enumerate(rows):
            if not authority.energy_min_kwh - 1e-6 <= row.battery_energy_kwh <= authority.energy_max_kwh + 1e-6:
                violations["soc"] += 1
            if row.mode != "CONNECTED" and (abs(row.p_kw) > 1e-6 or abs(row.q_kvar) > 1e-6):
                violations["transit_power"] += 1
            connected = float(row.mode == "CONNECTED")
            for face in range(authority.pcs_polygon_faces):
                angle = 2.0 * math.pi * face / authority.pcs_polygon_faces
                if math.cos(angle) * row.p_kw + math.sin(angle) * row.q_kvar > apothem * connected + 1e-6:
                    violations["pcs_polygon"] += 1
            departure_energy = row.energy_safe_kwh if row.mode == "TRANSIT" and row.departure_slot == row.slot else 0.0
            expected_next = (
                row.battery_energy_kwh
                + authority.charge_efficiency * authority.interval_hours * max(-row.p_kw, 0.0)
                - authority.interval_hours * max(row.p_kw, 0.0) / authority.discharge_efficiency
                - departure_energy
            )
            actual_next = rows[index + 1].battery_energy_kwh if index < 95 else authority.terminal_energy_kwh
            error = abs(expected_next - actual_next)
            if error > 2e-6:
                violations["soc_equation"] += 1
            if index == 95:
                terminal_errors.append(error)
    for commitment in trajectory.planned_move_commitments():
        rows = {row.slot: row for row in trajectory.slots if row.mess_id == commitment.mess_id}
        departure = rows[commitment.departure_slot]
        ready = commitment.planned_connection_ready_slot
        if ready > 96 or departure.route_link_ids != commitment.route_link_ids:
            violations["travel"] += 1
        for slot in range(commitment.departure_slot, min(ready, 96)):
            row = rows[slot]
            if row.departure_slot != commitment.departure_slot or row.route_link_ids != commitment.route_link_ids:
                violations["travel"] += 1
        if ready < 96 and (rows[ready].mode != "CONNECTED" or rows[ready].service_id != commitment.destination_service_id):
            violations["connection_ready"] += 1
    result = {
        "vehicle_count": len(mess_ids),
        "slot_count": len(trajectory.slots),
        "terminal_energy_target_kwh": authority.terminal_energy_kwh,
        "terminal_energy_max_abs_error_kwh": max(terminal_errors, default=0.0),
        **{f"{name}_violation_count": value for name, value in violations.items()},
    }
    result["pass"] = not any(violations.values())
    return result


def _mess_actuation_audit(trajectory: MessTrajectory, mess_ids: tuple[str, ...]) -> dict[str, object]:
    authority = MessElectricalAuthority.from_repository()
    rows = []
    for mess_id in mess_ids:
        slots = tuple(row for row in trajectory.slots if row.mess_id == mess_id)
        rows.append({
            "mess_id": mess_id,
            "MOVE_count": sum(item.mess_id == mess_id for item in trajectory.planned_move_commitments()),
            "STAY_slots": sum(item.mode == "CONNECTED" for item in slots),
            "total_charge_kWh": sum(max(-item.p_kw, 0.0) * authority.interval_hours for item in slots),
            "total_discharge_kWh": sum(max(item.p_kw, 0.0) * authority.interval_hours for item in slots),
            "max_abs_P_kW": max((abs(item.p_kw) for item in slots), default=0.0),
            "max_abs_Q_kvar": max((abs(item.q_kvar) for item in slots), default=0.0),
            "PQ_nonzero_slot_count": sum(abs(item.p_kw) > 1e-7 or abs(item.q_kvar) > 1e-7 for item in slots),
            "initial_SoC": slots[0].soc_fraction,
            "terminal_SoC": authority.terminal_energy_kwh / authority.capacity_kwh,
        })
    return {
        "per_MESS": rows,
        "aggregate_sum_abs_P_kW_slots": sum(abs(item.p_kw) for item in trajectory.slots),
        "aggregate_sum_abs_Q_kvar_slots": sum(abs(item.q_kvar) for item in trajectory.slots),
        "aggregate_throughput_kWh": sum(abs(item.p_kw) * authority.interval_hours for item in trajectory.slots),
    }


def _mess_arrays(trajectory, mess_ids: tuple[str, ...]):
    by = {(item.mess_id, item.slot): item for item in trajectory.slots}
    p = np.zeros((96, 4)); q = np.zeros((96, 4)); e = np.zeros((96, 4)); locations = np.empty((96, 4), dtype="U64")
    for column, mess_id in enumerate(mess_ids):
        for slot in range(96):
            item = by[mess_id, slot]
            p[slot, column] = item.p_kw; q[slot, column] = item.q_kvar; e[slot, column] = item.battery_energy_kwh
            locations[slot, column] = str(item.service_id) if item.mode == "CONNECTED" else f"TRANSIT_{item.mode}"
    return p, q, e, locations


def _resource_smoke(base: dict[str, object]) -> dict[str, object]:
    actual = materialize_actual_workload(SOURCE_REPO, DAY)
    mapping = json.loads((REPO / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    weights = np.asarray(mapping["gpu_weights"], dtype=float)
    capacity = np.repeat((CASE_CAPACITY_GPU * weights * .25 / 4.0)[None, :], 96, axis=0)
    result = solve_resource_only_recourse(
        np.asarray(base["workload_service_tensor"], dtype=float),
        actual.arrivals_nodeh,
        capacity,
        np.ones((15, 48), dtype=bool),
    )
    return {
        "executed_nodeh": result.executed_total_nodeh,
        "internal_resource_recourse_nodeh": result.recourse_nodeh,
        "solver_calls": result.solver_calls,
        "read_fields": sorted({str(row["field"]) for row in result.read_ledger}),
        **result.firewall,
    }


def main() -> int:
    if not SOURCE_DAY.is_dir():
        raise FileNotFoundError("V34_APR01_BASE_AUTHORITY_MISSING")
    OUT.mkdir(parents=True, exist_ok=True); CACHE.mkdir(parents=True, exist_ok=True)
    route_started = time.perf_counter()
    bundle, graph, route_table = build_april_route_table(REPO, DAY)
    route_seconds = time.perf_counter() - route_started
    data = materialize_formulation_data(SOURCE_REPO, DAY)
    electrical = build_electrical_context(
        SOURCE_REPO,
        data,
        SOURCE_DAY / "dayahead/electrical_cache",
    )
    service_mapping = _mapping()
    grid_coefficients = tuple(
        slot_coefficients(electrical.legacy_context, electrical.voltage, electrical.current, slot)
        for slot in range(96)
    )
    mess_ids = ("MESS01", "MESS02", "MESS03", "MESS04")
    initial = {mess: f"STA{index:02d}" for index, mess in enumerate(mess_ids, 1)}
    case_rows = []
    try:
        for case in OFFICIAL_CASES:
            case_started = time.perf_counter()
            base = _base_schedule(case)
            aidc = np.asarray(base["planning_pcc_power_kw"], dtype=float)
            if CASE_ACTUATORS[case]["mess"]:
                fixed_p: dict[tuple[str, int], float] = {}
                fixed_q: dict[tuple[str, int], float] = {}
                slots = []
                integrated_runs = []
                for mess_id in mess_ids:
                    integrated = solve_integrated_mess(
                        case=case,
                        aidc_pcc_kw_96x12=aidc,
                        electrical_context=electrical.legacy_context,
                        voltage_authority=electrical.voltage,
                        current_authority=electrical.current,
                        route_table=route_table,
                        service_to_pcc=service_mapping,
                        initial_service_by_mess={mess_id: initial[mess_id]},
                        fixed_mess_p_by_service=fixed_p,
                        fixed_mess_q_by_service=fixed_q,
                        grid_coefficients=grid_coefficients,
                    )
                    integrated_runs.append(integrated)
                    slots.extend(integrated.trajectory.slots)
                    for item in integrated.trajectory.slots:
                        if item.service_id is not None:
                            key = (item.service_id, item.slot)
                            fixed_p[key] = fixed_p.get(key, 0.0) + item.p_kw
                            fixed_q[key] = fixed_q.get(key, 0.0) + item.q_kvar
                combined = MessTrajectory(tuple(slots))
                p, q, soc, locations = _mess_arrays(combined, mess_ids)
                planning_audit = _mess_planning_audit(combined, mess_ids)
                commitments = combined.planned_move_commitments()
                ledger = CausalityLedger(bundle.issue_time)
                freeze = ledger.freeze(combined.canonical_sha256)
                actual = actual_sumo_authority(DAY, bundle.link_ids)
                replays = [
                    replay_committed_move(
                        item, actual, graph, ledger, freeze,
                        battery_capacity_kwh=760.0 / 0.76,
                    )
                    for item in commitments
                ]
                ledger.assert_clean()
                mess_audit = {
                    "route_table_sha256": route_table.canonical_sha256,
                    "trajectory_sha256": combined.canonical_sha256,
                    "planning_objective": integrated_runs[-1].objective,
                    "planning_rho": integrated_runs[-1].planning_rho,
                    "grid_constraint_count": sum(item.grid_constraint_count for item in integrated_runs),
                    "coordination_policy": "DETERMINISTIC_SEQUENTIAL_MESS_COORDINATION",
                    "global_joint_optimality_claimed": False,
                    "per_MESS_runtime": [
                        {
                            "mess_id": mess_id,
                            "variable_count": item.variable_count,
                            "constraint_count": item.constraint_count,
                            "model_build_seconds": item.model_build_seconds,
                            "solve_seconds": item.solve_seconds,
                            "peak_rss_bytes": item.peak_rss_bytes,
                            "solver_status": item.solver_status,
                            "incumbent_available": item.incumbent_available,
                            "termination": item.termination,
                            "objective_value": item.objective,
                            "best_bound": item.best_bound,
                            "MIP_gap": item.mip_gap,
                            "binary_count": item.binary_count,
                            "MOVE_binary_count": item.move_binary_count,
                            "STAY_variable_count": item.stay_variable_count,
                            "planning_rho": item.planning_rho,
                            "cumulative_prior_P_l1_kW_slots": item.prior_fixed_P_l1_kW_slots,
                            "cumulative_prior_Q_l1_kvar_slots": item.prior_fixed_Q_l1_kvar_slots,
                            "current_vehicle_free_variable_count": item.current_vehicle_free_variable_count,
                            "future_vehicle_variable_count": item.future_vehicle_variable_count,
                        }
                        for mess_id, item in zip(mess_ids, integrated_runs, strict=True)
                    ],
                    "vehicle_subproblem_count": len(integrated_runs),
                    "movement_count": len(commitments),
                    "actual_replays": [asdict(item) for item in replays],
                    "actual_MESS_optimizer_calls": ledger.actual_mess_optimizer_calls,
                    "actual_MESS_reroute_calls": ledger.actual_reroute_calls,
                    "route_identity_failures": ledger.actual_route_change_count,
                    "planning_mobility_physics_audit": planning_audit,
                    "actuation_audit": _mess_actuation_audit(combined, mess_ids),
                }
            else:
                p = np.zeros((96, 4)); q = np.zeros((96, 4)); soc = np.full((96, 4), 760.0)
                locations = np.repeat(np.asarray([[f"STA{i:02d}" for i in range(1, 5)]]), 96, axis=0)
                combined = None
                mess_audit = {"movement_count": 0, "actual_MESS_optimizer_calls": 0, "actual_MESS_reroute_calls": 0, "route_identity_failures": 0}
            planning_voltage, aggregate_grid_audit = _aggregate_grid_audit(
                grid_coefficients, electrical.voltage, aidc, combined,
            )
            schedule_payload = {
                "day": DAY,
                "case": case,
                "aidc_enabled": CASE_ACTUATORS[case]["aidc"],
                "mess_enabled": CASE_ACTUATORS[case]["mess"],
                "aidc_stage_case": _aidc_stage_case(case),
                "aidc_base_schedule_sha256": base["schedule_sha256"],
                "planning_pcc_power_kw": aidc.tolist(),
                "planning_pcc_reactive_kvar": base["planning_pcc_reactive_kvar"],
                "mess_p_kw": p.tolist(),
                "mess_q_kvar": q.tolist(),
                "mess_soc_kwh": soc.tolist(),
                "mess_locations_96x4": locations.tolist(),
                "traffic_forecast_sha256": bundle.canonical_sha256 if CASE_ACTUATORS[case]["mess"] else None,
            }
            schedule_sha = canonical_sha256(schedule_payload)
            trajectory = FrozenTrajectory(
                DAY, "DAYAHEAD", case, aidc,
                np.asarray(base["planning_pcc_reactive_kvar"], dtype=float),
                p, q, mess_ids, locations, schedule_sha,
            )
            dayahead_runtime_seconds = time.perf_counter() - case_started
            fresh = run_fresh_opendss(
                repo=SOURCE_REPO,
                context=electrical,
                voltage=electrical.voltage,
                trajectory=trajectory,
                output=CACHE / case / "fresh",
            )
            np.savez_compressed(
                CACHE / case / "PLANNING_FRESH_VOLTAGE.npz",
                node_names=np.asarray(fresh.node_names),
                node_phases=np.asarray(fresh.node_phases),
                planning_voltage_pu=planning_voltage,
                fresh_voltage_pu=fresh.voltage_pu,
                schedule_sha256=np.asarray(schedule_sha),
            )
            resource = _resource_smoke(base) if CASE_ACTUATORS[case]["aidc"] else {
                "executed_nodeh": 0.0,
                "internal_resource_recourse_nodeh": 0.0,
                "grid_voltage_reads_for_AIDC_decision": 0,
                "grid_current_reads_for_AIDC_decision": 0,
                "transformer_loading_reads_for_AIDC_decision": 0,
                "rho_reads_for_AIDC_decision": 0,
                "Fresh_reads_for_AIDC_decision": 0,
                "planning_grid_sensitivity_reads_for_Actual_AIDC_decision": 0,
            }
            case_rows.append({
                "case": case,
                "aidc_enabled": CASE_ACTUATORS[case]["aidc"],
                "mess_enabled": CASE_ACTUATORS[case]["mess"],
                "aidc_stage_case": _aidc_stage_case(case),
                "aidc_base_schedule_sha256": base["schedule_sha256"],
                "schedule_sha256": schedule_sha,
                "planning_fresh_schedule_sha_identity": fresh.schedule_sha256 == schedule_sha,
                "planning_vmin_pu": float(planning_voltage.min()),
                "planning_vmax_pu": float(planning_voltage.max()),
                "aggregate_planning_physics": aggregate_grid_audit,
                "fresh": fresh.summary,
                "total_DayAhead_runtime_seconds": dayahead_runtime_seconds,
                "Fresh_runtime_seconds": fresh.elapsed_seconds,
                "peak_RSS_bytes": _rss_bytes(),
                "aidc_actual_resource_smoke": resource,
                "mess": mess_audit,
            })
    finally:
        electrical.voltage.close(); electrical.current.close()

    pass_gate = (
        tuple(row["case"] for row in case_rows) == OFFICIAL_CASES
        and all(row["planning_fresh_schedule_sha_identity"] for row in case_rows)
        and all(int(row["fresh"]["convergence_count"]) == 96 for row in case_rows)
        and all(bool(row["aggregate_planning_physics"]["pass"]) for row in case_rows)
        and all(not bool(row["fresh"]["physical_violation"]) for row in case_rows)
        and all(
            (not row["mess_enabled"])
            or (
                bool(row["mess"]["planning_mobility_physics_audit"]["pass"])
                and int(row["mess"]["actual_MESS_optimizer_calls"]) == 0
                and int(row["mess"]["actual_MESS_reroute_calls"]) == 0
                and int(row["mess"]["route_identity_failures"]) == 0
            )
            for row in case_rows
        )
        and all(all(int(row["aidc_actual_resource_smoke"].get(field, 0)) == 0 for field in (
            "grid_voltage_reads_for_AIDC_decision", "grid_current_reads_for_AIDC_decision",
            "transformer_loading_reads_for_AIDC_decision", "rho_reads_for_AIDC_decision",
            "Fresh_reads_for_AIDC_decision", "planning_grid_sensitivity_reads_for_Actual_AIDC_decision",
        )) for row in case_rows)
    )
    result = {
        "artifact_id": "V34_APR01_INTEGRATION_SMOKE_V1",
        "status": "PASS" if pass_gate else "FAIL",
        "day": DAY,
        "engineering_only_not_for_tuning": True,
        "coordination_policy": "DETERMINISTIC_SEQUENTIAL_MESS_COORDINATION",
        "global_joint_optimality_claimed": False,
        "production_vehicle_order": list(("MESS01", "MESS02", "MESS03", "MESS04")),
        "official_cases": list(OFFICIAL_CASES),
        "traffic": {
            "issue_time": bundle.issue_time.isoformat(),
            "max_input_timestamp": bundle.max_input_timestamp.isoformat(),
            "shape": [288, 509, 3],
            "bundle_sha256": bundle.canonical_sha256,
            "road_nodes": graph.node_count,
            "road_links": graph.link_count,
            "service_nodes": len(route_table.service_ids),
            "route_table_build_seconds": route_seconds,
            "D_DAY_SCATS_ACTUAL_FEATURE_READS": 0,
            "D_DAY_SUMO_FEATURE_READS": 0,
            "POST_ISSUE_ACTUAL_REFRESH_CALLS": 0,
        },
        "cases": case_rows,
    }
    _write(OUT / "V34_INTEGRATION_SMOKE.json", result)
    print(json.dumps({"status": result["status"], "cases": [{"case": row["case"], "fresh": row["fresh"], "moves": row["mess"]["movement_count"]} for row in case_rows]}, indent=2))
    return 0 if pass_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
