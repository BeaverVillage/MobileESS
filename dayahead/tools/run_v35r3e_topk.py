"""Run the Apr-01 V35R3E adaptive Top-K warm-start production path."""

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

from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v33m.mess_trajectory import MessTrajectory, MessTrajectorySlot
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
from dayahead.v35r3e.algorithm import (
    build_planning_screen_context,
    screen_dynamic_candidates,
)
from dayahead.tools.run_v35r3_mess_scan import (
    FIELDS,
    _critical_states,
    _init_worker,
    _row,
    _solve_worker,
)


ARTIFACT_ROOT = Path("dayahead/artifacts/v35r3e_mess_topk_warmstart_productionization")
CACHE_ROOT = Path("dayahead/cache/v35r3e_mess_topk_warmstart_productionization")
TOP_K = 800
FALLBACK_LEVEL = "K800_EXPLICIT_APR01_CERTIFICATION_FAILURE"


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=float, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def _finite(value: float) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def _restore_slots(record: dict[str, object]) -> list[MessTrajectorySlot]:
    restored = []
    for source in record["trajectory_slots"]:
        payload = dict(source)
        payload["route_link_ids"] = tuple(payload["route_link_ids"])
        restored.append(MessTrajectorySlot(**payload))
    return restored


def _add_fixed_trajectory(
    slots: list[MessTrajectorySlot],
    fixed_p: dict[tuple[str, int], float],
    fixed_q: dict[tuple[str, int], float],
) -> None:
    for slot in slots:
        if slot.service_id is None:
            continue
        key = (slot.service_id, slot.slot)
        fixed_p[key] = fixed_p.get(key, 0.0) + slot.p_kw
        fixed_q[key] = fixed_q.get(key, 0.0) + slot.q_kvar


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("B2", "B3"), required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    artifact = (repo / ARTIFACT_ROOT).resolve()
    root = (repo / CACHE_ROOT / APR01 / args.case).resolve()
    root.mkdir(parents=True, exist_ok=True)
    artifact.mkdir(parents=True, exist_ok=True)
    _data, electrical, bases = prepare_aidc_stages(
        repo, DEFAULT_SOURCE_REPO, (repo / "dayahead/cache/v35").resolve(),
        PHASE_CALIBRATION, APR01, None,
    )
    _bundle, _graph, route_table, _files = daily_traffic_authority(
        repo, (repo / "dayahead/cache/v35").resolve(), PHASE_CALIBRATION, APR01, None,
    )
    coefficients = tuple(
        slot_coefficients(electrical.legacy_context, electrical.voltage, electrical.current, slot)
        for slot in range(96)
    )
    stage = "B0" if args.case == "B2" else "B1"
    aidc = np.asarray(bases[stage]["planning_pcc_power_kw"], dtype=float)
    planning_path = (
        repo / "dayahead/cache/v35" / PHASE_CALIBRATION / APR01 / stage / "PLANNING_GRID.npz"
    )
    with np.load(planning_path, allow_pickle=False) as payload:
        branch_names = np.asarray(payload["branch_names"]).astype(str)
        branch_phases = np.asarray(payload["branch_phases"]).astype(str)
        seed_line, congestion = _critical_states(
            np.asarray(payload["phase_current_loading_pu"]),
            np.asarray([
                f"{name}::{phase}"
                for name, phase in zip(branch_names, branch_phases, strict=True)
            ]),
        )
    _json(root / "CONGESTION_MAP.json", congestion)
    services = tuple(
        name[10:-1] for name in map(str, electrical.voltage["control_names"])
        if name.startswith("mess_p_kw[")
    )
    ground_truth = np.genfromtxt(
        artifact / "V35R3E_APR01_EXHAUSTIVE_GROUND_TRUTH.csv",
        delimiter=",", names=True, dtype=None, encoding="utf-8",
    )
    truth_best: dict[str, str] = {}
    for mess_id in MESS_IDS:
        rows = [
            row for row in ground_truth
            if str(row["case"]) == args.case and str(row["mess_id"]) == mess_id
        ]
        best = min(rows, key=lambda row: (float(row["objective"]), str(row["candidate_id"])))
        truth_best[mess_id] = str(best["candidate_id"])

    fixed_p: dict[tuple[str, int], float] = {}
    fixed_q: dict[tuple[str, int], float] = {}
    fleet_slots: list[MessTrajectorySlot] = []
    fleet_records: list[dict[str, object]] = []
    try:
        for sequence_index, mess_id in enumerate(MESS_IDS):
            result_path = root / f"{mess_id}_RESULT.json"
            if result_path.is_file():
                record = json.loads(result_path.read_text(encoding="utf-8"))
                restored = _restore_slots(record)
                fleet_slots.extend(restored)
                fleet_records.append(record)
                _add_fixed_trajectory(restored, fixed_p, fixed_q)
                print(f"{args.case} {mess_id} RESTORED", flush=True)
                continue

            enumeration = enumerate_initial_relocations(
                day=APR01,
                mess_id=mess_id,
                initial_service=MESS_INITIAL[mess_id],
                route_table=route_table,
            )
            context = build_planning_screen_context(
                aidc_pcc_kw_96x12=aidc,
                coefficients=coefficients,
                services=services,
                fixed_mess_p_by_service=fixed_p,
                fixed_mess_q_by_service=fixed_q,
                sequential_previous_mess_count=sequence_index,
            )
            screen_rows, screen_seconds = screen_dynamic_candidates(
                day=APR01,
                case=args.case,
                mess_id=mess_id,
                route_table=route_table,
                context=context,
                variant="S4",
            )
            top_move_ids = [
                str(row["candidate_id"])
                for row in screen_rows if row["candidate_type"] == "MOVE"
            ][:TOP_K]
            by_id = {candidate.candidate_id: candidate for candidate in enumeration.candidates}
            stay = next(candidate for candidate in enumeration.candidates if candidate.is_stay)
            selected_ids = [stay.candidate_id, *top_move_ids]
            if len(selected_ids) != TOP_K + 1 or len(set(selected_ids)) != TOP_K + 1:
                raise RuntimeError(f"V35R3E_TOPK_ID_CONSERVATION:{args.case}:{mess_id}")
            rank_by_id = {
                str(row["candidate_id"]): row.get("cheap_rank_move")
                for row in screen_rows
            }
            _json(root / f"{mess_id}_SELECTION.json", {
                "day": APR01,
                "case": args.case,
                "mess_id": mess_id,
                "variant": "S4",
                "K0": 200,
                "fallback_level": FALLBACK_LEVEL,
                "selected_move_count": TOP_K,
                "STAY_included": True,
                "selected_candidate_ids": selected_ids,
                "screen_authority_sha": context.authority_sha,
                "cheap_screen_wallclock_seconds": screen_seconds,
                "exact_best_candidate_id": truth_best[mess_id],
                "trusted_ground_truth_best_cheap_rank": rank_by_id.get(truth_best[mess_id]),
            })

            csv_path = root / f"{mess_id}_TOPK_VALUES.csv"
            completed: dict[str, dict[str, str]] = {}
            if csv_path.is_file():
                with csv_path.open(encoding="utf-8", newline="") as stream:
                    completed = {row["candidate_id"]: row for row in csv.DictReader(stream)}
                if not set(completed).issubset(selected_ids):
                    raise RuntimeError(f"V35R3E_RESUME_SELECTION_AUTHORITY:{args.case}:{mess_id}")

            line_states = set(seed_line)
            voltage_states: set[tuple[int, int]] = set()
            tx_current_states: set[tuple[int, int]] = set()
            tx_kva_states: set[tuple[int, int]] = set()
            seed_candidates = [stay]
            seen_destinations = {stay.destination}
            for candidate_id in top_move_ids:
                candidate = by_id[candidate_id]
                if candidate.destination not in seen_destinations:
                    seed_candidates.append(candidate)
                    seen_destinations.add(candidate.destination)
            scan_started = time.perf_counter()
            seed_rows = []
            for candidate in seed_candidates:
                if candidate.candidate_id in completed:
                    continue
                started = time.perf_counter()
                item = build_fixed_candidate_model(
                    candidate=candidate,
                    aidc_pcc_kw_96x12=aidc,
                    coefficients=coefficients,
                    services=services,
                    fixed_mess_p_by_service=fixed_p,
                    fixed_mess_q_by_service=fixed_q,
                    line_states=line_states,
                    voltage_states=voltage_states,
                    transformer_current_states=tx_current_states,
                    transformer_kva_states=tx_kva_states,
                )
                dispatch, evaluation = solve_fixed_candidate_certified(item)
                seed_rows.append(_row(
                    args.case, candidate, dispatch, evaluation,
                    time.perf_counter() - started,
                ))
                line_states.update(item.added_line_states)
                voltage_states.update(item.added_voltage_states)
                tx_current_states.update(item.added_transformer_current_states)
                tx_kva_states.update(item.added_transformer_kva_states)
                item.model.dispose()
            remaining = [
                by_id[candidate_id] for candidate_id in selected_ids
                if candidate_id not in completed
                and all(candidate_id != row["candidate_id"] for row in seed_rows)
            ]
            mode = "a" if csv_path.is_file() else "w"
            with csv_path.open(mode, encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                if mode == "w":
                    writer.writeheader()
                for row in seed_rows:
                    writer.writerow(row)
                    stream.flush()
                    completed[str(row["candidate_id"])] = {
                        key: str(value) for key, value in row.items()
                    }
                with ProcessPoolExecutor(
                    max_workers=args.workers,
                    initializer=_init_worker,
                    initargs=(
                        args.case, aidc, coefficients, services, fixed_p, fixed_q,
                        line_states, voltage_states, tx_current_states, tx_kva_states,
                    ),
                ) as pool:
                    for index, row in enumerate(
                        pool.map(_solve_worker, remaining, chunksize=4), start=1,
                    ):
                        writer.writerow(row)
                        stream.flush()
                        completed[str(row["candidate_id"])] = {
                            key: str(value) for key, value in row.items()
                        }
                        if index % 100 == 0:
                            print(
                                f"{args.case} {mess_id} {len(completed)}/{TOP_K + 1}",
                                flush=True,
                            )
            restricted_wallclock = time.perf_counter() - scan_started
            with csv_path.open(encoding="utf-8", newline="") as stream:
                values = list(csv.DictReader(stream))
            if len(values) != TOP_K + 1:
                raise RuntimeError(
                    f"V35R3E_TOPK_SCAN_INCOMPLETE:{args.case}:{mess_id}:{len(values)}"
                )
            best_row = min(values, key=lambda row: (float(row["objective"]), row["candidate_id"]))
            best_candidate = by_id[best_row["candidate_id"]]
            best_model = build_fixed_candidate_model(
                candidate=best_candidate,
                aidc_pcc_kw_96x12=aidc,
                coefficients=coefficients,
                services=services,
                fixed_mess_p_by_service=fixed_p,
                fixed_mess_q_by_service=fixed_q,
                line_states=line_states,
                voltage_states=voltage_states,
                transformer_current_states=tx_current_states,
                transformer_kva_states=tx_kva_states,
            )
            best_dispatch, best_evaluation = solve_fixed_candidate_certified(best_model)
            best_model.model.dispose()
            full_started = time.perf_counter()
            full = solve_integrated_mess(
                case=args.case,
                aidc_pcc_kw_96x12=aidc,
                electrical_context=electrical.legacy_context,
                voltage_authority=electrical.voltage,
                current_authority=electrical.current,
                route_table=route_table,
                service_to_pcc=_service_mapping(),
                initial_service_by_mess={mess_id: MESS_INITIAL[mess_id]},
                fixed_mess_p_by_service=fixed_p,
                fixed_mess_q_by_service=fixed_q,
                grid_coefficients=coefficients,
                preferred_restricted_start=best_dispatch,
            )
            full_wallclock = time.perf_counter() - full_started
            new_slots = list(full.trajectory.slots)
            fleet_slots.extend(new_slots)
            _add_fixed_trajectory(new_slots, fixed_p, fixed_q)
            record = {
                "case": args.case,
                "mess_id": mess_id,
                "sequence_index": sequence_index,
                "static_candidate_count": len(enumeration.candidates),
                "cheap_screen_evaluations": len(enumeration.candidates),
                "cheap_screen_wallclock_seconds": screen_seconds,
                "K0": 200,
                "fallback_level": FALLBACK_LEVEL,
                "restricted_exact_solve_count": TOP_K + 1,
                "restricted_exact_solve_wallclock_seconds": restricted_wallclock,
                "best_restricted_candidate": asdict(best_candidate),
                "best_restricted_objective": float(best_dispatch["objective"]),
                "best_restricted_rho": float(best_evaluation["rho"]),
                "full_first_incumbent": float(best_dispatch["objective"]),
                "full_objective": float(full.objective),
                "full_best_bound": _finite(full.best_bound),
                "full_MIP_gap": _finite(full.mip_gap),
                "full_termination": full.termination,
                "full_MILP_wallclock_seconds": full_wallclock,
                "MIPStart_accepted": bool(full.mip_start_accepted),
                "preferred_MIPStart_loaded": bool(full.preferred_mip_start_loaded),
                "forced_MOVE_count": 0,
                "natural_MOVE_count": len(full.trajectory.planned_move_commitments()),
                "natural_moves": [asdict(row) for row in full.trajectory.planned_move_commitments()],
                "trajectory_sha256": full.trajectory.canonical_sha256,
                "trajectory_slots": [row.to_dict() for row in new_slots],
                "total_MESS_search_wallclock_seconds": (
                    screen_seconds + restricted_wallclock + full_wallclock
                ),
            }
            fleet_records.append(record)
            _json(result_path, record)
            _json(root / "FLEET_PROGRESS.json", fleet_records)
            print(
                f"{args.case} {mess_id} COMPLETE best={best_candidate.candidate_id} "
                f"full={full.objective}",
                flush=True,
            )

        trajectory = MessTrajectory(tuple(fleet_slots))
        arrays, planning = _planning_grid(coefficients, electrical.voltage, aidc, trajectory)
        np.savez_compressed(root / "FINAL_PLANNING_GRID.npz", **arrays)
        final = {
            "case": args.case,
            "day": APR01,
            "vehicles": fleet_records,
            "planning": planning,
            "trajectory_sha256": trajectory.canonical_sha256,
            "natural_MOVE_count": len(trajectory.planned_move_commitments()),
            "natural_moves": [asdict(row) for row in trajectory.planned_move_commitments()],
            "trajectory_slots": [row.to_dict() for row in trajectory.slots],
        }
        _json(root / "FINAL_RESULT.json", final)
        _json(artifact / f"V35R3E_{args.case}_SEQUENTIAL_FINAL.json", final)
    finally:
        electrical.voltage.close()
        electrical.current.close()


if __name__ == "__main__":
    main()
