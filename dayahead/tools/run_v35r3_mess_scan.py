"""Run the resumable Apr-01 V35R3 restricted MESS opportunity scan."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict
import json
import math
from pathlib import Path
import time

import numpy as np

from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row, slot_coefficients
from dayahead.v34.integrated_mess import solve_integrated_mess
from dayahead.v35.contracts import MESS_IDS, PHASE_CALIBRATION
from dayahead.v35.execution import (
    DEFAULT_SOURCE_REPO,
    MESS_INITIAL,
    _planning_grid,
    _service_mapping,
    daily_traffic_authority,
    prepare_aidc_stages,
)
from dayahead.v35r3.algorithm import (
    APR01,
    build_fixed_candidate_model,
    enumerate_initial_relocations,
    solve_fixed_candidate_certified,
)


FIELDS = (
    "case", "mess_id", "candidate_id", "origin", "destination", "departure_slot",
    "connection_ready_slot", "travel_slots", "q50_eta_seconds", "safe_eta_seconds",
    "safe_energy_kwh", "route_link_ids", "is_stay", "objective", "rho",
    "binding_asset", "binding_slot", "Vmin_pu", "Vmax_pu",
    "post_arrival_sum_abs_p_kw_slots", "post_arrival_sum_abs_q_kvar_slots",
    "terminal_energy_kwh", "exact_optimality_certificate", "runtime_seconds",
)

_WORKER: dict[str, object] = {}


def _init_worker(
    case, aidc, coefficients, services, fixed_p, fixed_q,
    line_states, voltage_states, tx_current_states, tx_kva_states,
):
    _WORKER.update({
        "case": case, "aidc": aidc, "coefficients": coefficients,
        "services": services, "fixed_p": fixed_p, "fixed_q": fixed_q,
        "line_states": line_states, "voltage_states": voltage_states,
        "tx_current_states": tx_current_states, "tx_kva_states": tx_kva_states,
    })


def _solve_worker(candidate):
    started = time.perf_counter()
    item = build_fixed_candidate_model(
        candidate=candidate, aidc_pcc_kw_96x12=_WORKER["aidc"],
        coefficients=_WORKER["coefficients"], services=_WORKER["services"],
        fixed_mess_p_by_service=_WORKER["fixed_p"],
        fixed_mess_q_by_service=_WORKER["fixed_q"],
        line_states=_WORKER["line_states"], voltage_states=_WORKER["voltage_states"],
        transformer_current_states=_WORKER["tx_current_states"],
        transformer_kva_states=_WORKER["tx_kva_states"],
    )
    dispatch, evaluation = solve_fixed_candidate_certified(item)
    item.model.dispose()
    return _row(str(_WORKER["case"]), candidate, dispatch, evaluation, time.perf_counter() - started)


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=float), encoding="utf-8")
    temporary.replace(path)


def _finite(value: float) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def _critical_states(load: np.ndarray, names: np.ndarray) -> tuple[set[tuple[int, int]], dict[str, object]]:
    mask = np.asarray([
        not str(name).startswith("transformer.") and not is_dominated_mess_current_row(str(name))
        for name in names
    ])
    indices = np.flatnonzero(mask)
    values = load[:, mask]
    rho = float(values.max())
    maximum = np.unravel_index(int(np.argmax(values)), values.shape)
    branch_index = int(indices[maximum[1]])
    top_flat = np.argsort(values, axis=None)[-20:]
    states = {
        (int(slot), int(indices[column]))
        for slot, column in zip(*np.unravel_index(top_flat, values.shape))
    }
    states.update(
        (int(slot), int(indices[column]))
        for slot, column in zip(*np.where(values >= 0.98 * rho - 1e-12))
    )
    states.update(
        (slot, branch_index)
        for slot in range(max(0, maximum[0] - 2), min(96, maximum[0] + 3))
    )
    return states, {
        "authority": "D1_PLANNING_ONLY",
        "frozen_near_critical_rule": "GAMMA_CRIT_0.98",
        "predeclared_Top_K": 20,
        "fixed_window": "W5_AROUND_GLOBAL_MAX",
        "rho": rho,
        "binding_asset": str(names[branch_index]),
        "binding_slot": int(maximum[0]),
        "state_count": len(states),
        "states": [
            {"slot": slot, "branch_index": index, "asset": str(names[index]), "loading": float(load[slot, index])}
            for slot, index in sorted(states)
        ],
    }


def _row(case: str, candidate: object, dispatch: dict[str, object], evaluation: dict[str, object], runtime: float) -> dict[str, object]:
    source = asdict(candidate)
    return {
        "case": case,
        "mess_id": source["mess_id"],
        "candidate_id": source["candidate_id"],
        "origin": source["origin"],
        "destination": source["destination"],
        "departure_slot": source["departure_slot"],
        "connection_ready_slot": source["connection_ready_slot"],
        "travel_slots": source["travel_slots"],
        "q50_eta_seconds": source["q50_eta_seconds"],
        "safe_eta_seconds": source["safe_eta_seconds"],
        "safe_energy_kwh": source["safe_energy_kwh"],
        "route_link_ids": ">".join(source["route_link_ids"]),
        "is_stay": source["is_stay"],
        "objective": float(dispatch["objective"]),
        "rho": float(evaluation["rho"]),
        "binding_asset": evaluation["binding_asset"],
        "binding_slot": evaluation["binding_slot"],
        "Vmin_pu": evaluation["Vmin_pu"],
        "Vmax_pu": evaluation["Vmax_pu"],
        "post_arrival_sum_abs_p_kw_slots": dispatch["post_arrival_sum_abs_p_kw_slots"],
        "post_arrival_sum_abs_q_kvar_slots": dispatch["post_arrival_sum_abs_q_kvar_slots"],
        "terminal_energy_kwh": dispatch["terminal_energy_kwh"],
        "exact_optimality_certificate": evaluation["exact_optimality_certificate"],
        "runtime_seconds": runtime,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("B2", "B3"), required=True)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    repo = Path.cwd()
    root = repo / "dayahead/cache/v35r3" / APR01 / args.case
    root.mkdir(parents=True, exist_ok=True)
    data, electrical, bases = prepare_aidc_stages(
        repo, DEFAULT_SOURCE_REPO, repo / "dayahead/cache/v35",
        PHASE_CALIBRATION, APR01, None,
    )
    _bundle, _graph, route_table, _files = daily_traffic_authority(
        repo, repo / "dayahead/cache/v35", PHASE_CALIBRATION, APR01, None,
    )
    coefficients = tuple(
        slot_coefficients(electrical.legacy_context, electrical.voltage, electrical.current, slot)
        for slot in range(96)
    )
    stage = "B0" if args.case == "B2" else "B1"
    aidc = np.asarray(bases[stage]["planning_pcc_power_kw"], dtype=float)
    planning_root = repo / "dayahead/cache/v35" / PHASE_CALIBRATION / APR01 / stage / "PLANNING_GRID.npz"
    with np.load(planning_root, allow_pickle=False) as payload:
        branch_names = np.asarray(payload["branch_names"]).astype(str)
        branch_phases = np.asarray(payload["branch_phases"]).astype(str)
        seed_line, congestion = _critical_states(
            np.asarray(payload["phase_current_loading_pu"]),
            np.asarray([f"{name}::{phase}" for name, phase in zip(branch_names, branch_phases, strict=True)]),
        )
    _json(root / "CONGESTION_MAP.json", congestion)
    services = tuple(
        name[10:-1] for name in map(str, electrical.voltage["control_names"])
        if name.startswith("mess_p_kw[")
    )
    fixed_p: dict[tuple[str, int], float] = {}
    fixed_q: dict[tuple[str, int], float] = {}
    fleet_slots = []
    fleet_records = []
    try:
        for mess_id in MESS_IDS:
            vehicle_result_path = root / f"{mess_id}_RESULT.json"
            if vehicle_result_path.is_file():
                from dayahead.v33m.mess_trajectory import MessTrajectorySlot
                record = json.loads(vehicle_result_path.read_text(encoding="utf-8"))
                restored = []
                for source in record["trajectory_slots"]:
                    source = dict(source); source["route_link_ids"] = tuple(source["route_link_ids"])
                    restored.append(MessTrajectorySlot(**source))
                fleet_slots.extend(restored); fleet_records.append(record)
                for slot in restored:
                    if slot.service_id is not None:
                        key = (slot.service_id, slot.slot)
                        fixed_p[key] = fixed_p.get(key, 0.0) + slot.p_kw
                        fixed_q[key] = fixed_q.get(key, 0.0) + slot.q_kvar
                print(f"{args.case} {mess_id} RESTORED", flush=True)
                continue
            enumeration = enumerate_initial_relocations(
                day=APR01, mess_id=mess_id, initial_service=MESS_INITIAL[mess_id],
                route_table=route_table,
            )
            candidates = enumeration.candidates
            csv_path = root / f"{mess_id}_RESTRICTED_VALUES.csv"
            completed: dict[str, dict[str, str]] = {}
            if csv_path.is_file():
                with csv_path.open(encoding="utf-8", newline="") as stream:
                    completed = {row["candidate_id"]: row for row in csv.DictReader(stream)}
            line_states = set(seed_line)
            voltage_states: set[tuple[int, int]] = set()
            tx_current_states: set[tuple[int, int]] = set()
            tx_kva_states: set[tuple[int, int]] = set()

            # Deterministically enrich the shared cut set with STAY and one
            # median-departure representative per destination.
            representatives = [] if len(completed) == len(candidates) else [candidates[0]]
            if representatives:
                for destination in services:
                    options = [row for row in candidates if row.destination == destination and not row.is_stay]
                    if options:
                        representatives.append(options[len(options) // 2])
            seed_rows = []
            for candidate in representatives:
                started = time.perf_counter()
                item = build_fixed_candidate_model(
                    candidate=candidate, aidc_pcc_kw_96x12=aidc,
                    coefficients=coefficients, services=services,
                    fixed_mess_p_by_service=fixed_p,
                    fixed_mess_q_by_service=fixed_q,
                    line_states=line_states, voltage_states=voltage_states,
                    transformer_current_states=tx_current_states,
                    transformer_kva_states=tx_kva_states,
                )
                dispatch, evaluation = solve_fixed_candidate_certified(item)
                if candidate.candidate_id not in completed:
                    seed_rows.append(_row(args.case, candidate, dispatch, evaluation, time.perf_counter() - started))
                line_states.update(item.added_line_states)
                voltage_states.update(item.added_voltage_states)
                tx_current_states.update(item.added_transformer_current_states)
                tx_kva_states.update(item.added_transformer_kva_states)
                item.model.dispose()
            remaining = [
                row for row in candidates
                if row.candidate_id not in completed
                and all(row.candidate_id != seed["candidate_id"] for seed in seed_rows)
            ]
            mode = "a" if csv_path.is_file() else "w"
            with csv_path.open(mode, encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                if mode == "w":
                    writer.writeheader()
                for row in seed_rows:
                    writer.writerow(row); stream.flush(); completed[row["candidate_id"]] = {key: str(value) for key, value in row.items()}
                with ProcessPoolExecutor(
                    max_workers=args.workers,
                    initializer=_init_worker,
                    initargs=(
                        args.case, aidc, coefficients, services, fixed_p, fixed_q,
                        line_states, voltage_states, tx_current_states, tx_kva_states,
                    ),
                ) as pool:
                    for index, row in enumerate(pool.map(_solve_worker, remaining, chunksize=4), start=1):
                        writer.writerow(row); stream.flush(); completed[row["candidate_id"]] = {key: str(value) for key, value in row.items()}
                        if index % 100 == 0:
                            print(f"{args.case} {mess_id} {len(completed)}/{len(candidates)}", flush=True)
            with csv_path.open(encoding="utf-8", newline="") as stream:
                values = list(csv.DictReader(stream))
            if len(values) != len(candidates):
                raise RuntimeError(f"V35R3_SCAN_INCOMPLETE:{mess_id}:{len(values)}:{len(candidates)}")
            best_row = min(values, key=lambda row: (float(row["objective"]), row["candidate_id"]))
            best_candidate = next(row for row in candidates if row.candidate_id == best_row["candidate_id"])
            best_model = build_fixed_candidate_model(
                candidate=best_candidate, aidc_pcc_kw_96x12=aidc,
                coefficients=coefficients, services=services,
                fixed_mess_p_by_service=fixed_p, fixed_mess_q_by_service=fixed_q,
                line_states=line_states, voltage_states=voltage_states,
                transformer_current_states=tx_current_states,
                transformer_kva_states=tx_kva_states,
            )
            best_dispatch, best_evaluation = solve_fixed_candidate_certified(best_model)
            np.savez_compressed(
                root / f"{mess_id}_BEST_RESTRICTED.npz",
                p_discharge_kw=best_dispatch["p_discharge_kw"],
                p_charge_kw=best_dispatch["p_charge_kw"],
                q_kvar=best_dispatch["q_kvar"], energy_kwh=best_dispatch["energy_kwh"],
            )
            best_model.model.dispose()
            full = solve_integrated_mess(
                case=args.case, aidc_pcc_kw_96x12=aidc,
                electrical_context=electrical.legacy_context,
                voltage_authority=electrical.voltage, current_authority=electrical.current,
                route_table=route_table, service_to_pcc=_service_mapping(),
                initial_service_by_mess={mess_id: MESS_INITIAL[mess_id]},
                fixed_mess_p_by_service=fixed_p, fixed_mess_q_by_service=fixed_q,
                grid_coefficients=coefficients, preferred_restricted_start=best_dispatch,
            )
            fleet_slots.extend(full.trajectory.slots)
            for slot in full.trajectory.slots:
                if slot.service_id is not None:
                    key = (slot.service_id, slot.slot)
                    fixed_p[key] = fixed_p.get(key, 0.0) + slot.p_kw
                    fixed_q[key] = fixed_q.get(key, 0.0) + slot.q_kvar
            record = {
                "case": args.case, "mess_id": mess_id,
                "candidate_count_including_STAY": len(candidates),
                "feasible_MOVE_candidate_count": len(candidates) - 1,
                "rejected_counts": dict(enumeration.rejected_counts),
                "best_restricted_candidate": asdict(best_candidate),
                "best_restricted_objective": best_dispatch["objective"],
                "best_restricted_rho": best_evaluation["rho"],
                "best_restricted_terminal_energy_kwh": best_dispatch["terminal_energy_kwh"],
                "best_restricted_post_arrival_sum_abs_P": best_dispatch["post_arrival_sum_abs_p_kw_slots"],
                "best_restricted_post_arrival_sum_abs_Q": best_dispatch["post_arrival_sum_abs_q_kvar_slots"],
                "full_objective": full.objective, "full_best_bound": _finite(full.best_bound),
                "full_MIP_gap": _finite(full.mip_gap), "full_termination": full.termination,
                "MIPStart_accepted": full.mip_start_accepted,
                "preferred_MIPStart_loaded": full.preferred_mip_start_loaded,
                "natural_MOVE_count": len(full.trajectory.planned_move_commitments()),
                "natural_moves": [asdict(row) for row in full.trajectory.planned_move_commitments()],
                "trajectory_slots": [row.to_dict() for row in full.trajectory.slots],
            }
            fleet_records.append(record)
            _json(vehicle_result_path, record)
            _json(root / "FLEET_PROGRESS.json", fleet_records)
            print(f"{args.case} {mess_id} COMPLETE best={best_candidate.candidate_id} full={full.objective}", flush=True)
        from dayahead.v33m.mess_trajectory import MessTrajectory
        trajectory = MessTrajectory(tuple(fleet_slots))
        arrays, summary = _planning_grid(coefficients, electrical.voltage, aidc, trajectory)
        np.savez_compressed(root / "FINAL_PLANNING_GRID.npz", **arrays)
        _json(root / "FINAL_RESULT.json", {
            "case": args.case, "day": APR01, "vehicles": fleet_records,
            "planning": summary, "trajectory_sha256": trajectory.canonical_sha256,
            "natural_MOVE_count": len(trajectory.planned_move_commitments()),
            "natural_moves": [asdict(row) for row in trajectory.planned_move_commitments()],
            "trajectory_slots": [row.to_dict() for row in trajectory.slots],
        })
    finally:
        electrical.voltage.close(); electrical.current.close()


if __name__ == "__main__":
    main()
