"""Execute a recorded Apr-01 full restricted-scan fallback for B2 MESS04."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict
import json
import math
from pathlib import Path
import shutil
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
from dayahead.v35r3e.source_lookup import install_missing_directory_tolerant_lookup
from dayahead.tools.run_v35r3_mess_scan import (
    FIELDS,
    _critical_states,
    _init_worker,
    _solve_worker,
)


CACHE_ROOT = Path("dayahead/cache/v35r3e_mess_topk_warmstart_productionization")
ARTIFACT_ROOT = Path("dayahead/artifacts/v35r3e_mess_topk_warmstart_productionization")


def _safe_worker(candidate):
    try:
        return {"status": "OK", "row": _solve_worker(candidate)}
    except Exception as error:  # worker isolation is part of fallback resilience
        return {
            "status": "RETRY",
            "candidate": candidate,
            "error": f"{type(error).__name__}:{error}",
        }


def _json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=float, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def _slots(record: dict[str, object]) -> list[MessTrajectorySlot]:
    result = []
    for source in record["trajectory_slots"]:
        payload = dict(source)
        payload["route_link_ids"] = tuple(payload["route_link_ids"])
        result.append(MessTrajectorySlot(**payload))
    return result


def _add(
    slots: list[MessTrajectorySlot],
    p: dict[tuple[str, int], float],
    q: dict[tuple[str, int], float],
) -> None:
    for row in slots:
        if row.service_id is None:
            continue
        key = (row.service_id, row.slot)
        p[key] = p.get(key, 0.0) + row.p_kw
        q[key] = q.get(key, 0.0) + row.q_kvar


def _finite(value: float) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    root = (repo / CACHE_ROOT / APR01 / "B2").resolve()
    artifact = (repo / ARTIFACT_ROOT).resolve()
    records = [
        json.loads((root / f"{mess_id}_RESULT.json").read_text(encoding="utf-8"))
        for mess_id in MESS_IDS[:3]
    ]
    fixed_p: dict[tuple[str, int], float] = {}
    fixed_q: dict[tuple[str, int], float] = {}
    fleet_slots: list[MessTrajectorySlot] = []
    for record in records:
        restored = _slots(record)
        fleet_slots.extend(restored)
        _add(restored, fixed_p, fixed_q)

    install_missing_directory_tolerant_lookup()
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
    aidc = np.asarray(bases["B0"]["planning_pcc_power_kw"], dtype=float)
    services = tuple(
        name[10:-1] for name in map(str, electrical.voltage["control_names"])
        if name.startswith("mess_p_kw[")
    )
    planning_path = (
        repo / "dayahead/cache/v35" / PHASE_CALIBRATION / APR01 / "B0" / "PLANNING_GRID.npz"
    )
    with np.load(planning_path, allow_pickle=False) as payload:
        branch_names = np.asarray(payload["branch_names"]).astype(str)
        branch_phases = np.asarray(payload["branch_phases"]).astype(str)
        line_states, _congestion = _critical_states(
            np.asarray(payload["phase_current_loading_pu"]),
            np.asarray([
                f"{name}::{phase}"
                for name, phase in zip(branch_names, branch_phases, strict=True)
            ]),
        )
    mess_id = "MESS04"
    enumeration = enumerate_initial_relocations(
        day=APR01,
        mess_id=mess_id,
        initial_service=MESS_INITIAL[mess_id],
        route_table=route_table,
    )
    by_id = {row.candidate_id: row for row in enumeration.candidates}
    topk_path = root / f"{mess_id}_TOPK_VALUES.csv"
    full_path = root / f"{mess_id}_FULL_VALUES.csv"
    if not full_path.is_file():
        shutil.copy2(topk_path, full_path)
    with full_path.open(encoding="utf-8", newline="") as stream:
        completed = {row["candidate_id"]: row for row in csv.DictReader(stream)}
    if not set(completed).issubset(by_id):
        raise RuntimeError("V35R3E_FULL_FALLBACK_CANDIDATE_AUTHORITY")
    remaining = [row for row in enumeration.candidates if row.candidate_id not in completed]
    started = time.perf_counter()
    with full_path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        with ProcessPoolExecutor(
            max_workers=args.workers,
            initializer=_init_worker,
            initargs=(
                "B2", aidc, coefficients, services, fixed_p, fixed_q,
                line_states, set(), set(), set(),
            ),
        ) as pool:
            retries = []
            for index, result in enumerate(
                pool.map(_safe_worker, remaining, chunksize=4), start=1,
            ):
                if result["status"] == "RETRY":
                    retries.append(result)
                    continue
                row = result["row"]
                writer.writerow(row)
                stream.flush()
                completed[str(row["candidate_id"])] = {
                    key: str(value) for key, value in row.items()
                }
                if index % 100 == 0:
                    print(
                        f"B2 MESS04 FULL {len(completed)}/{len(enumeration.candidates)}",
                        flush=True,
                    )
        for retry in retries:
            candidate = retry["candidate"]
            item = build_fixed_candidate_model(
                candidate=candidate,
                aidc_pcc_kw_96x12=aidc,
                coefficients=coefficients,
                services=services,
                fixed_mess_p_by_service=fixed_p,
                fixed_mess_q_by_service=fixed_q,
                line_states=line_states,
            )
            item.model.Params.NumericFocus = 3
            item.model.Params.OptimalityTol = 1e-8
            retry_started = time.perf_counter()
            dispatch, evaluation = solve_fixed_candidate_certified(
                item, max_separation_rounds=50,
            )
            from dayahead.tools.run_v35r3_mess_scan import _row
            row = _row(
                "B2", candidate, dispatch, evaluation,
                time.perf_counter() - retry_started,
            )
            item.model.dispose()
            writer.writerow(row)
            stream.flush()
            completed[str(row["candidate_id"])] = {
                key: str(value) for key, value in row.items()
            }
            print(
                f"B2 MESS04 NUMERIC_RETRY {candidate.candidate_id} "
                f"after={retry['error']}",
                flush=True,
            )
    fallback_scan_seconds = time.perf_counter() - started
    with full_path.open(encoding="utf-8", newline="") as stream:
        values = list(csv.DictReader(stream))
    if len(values) != len(enumeration.candidates):
        raise RuntimeError(f"V35R3E_FULL_FALLBACK_INCOMPLETE:{len(values)}")
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
    )
    best_dispatch, best_evaluation = solve_fixed_candidate_certified(best_model)
    best_model.model.dispose()
    full_started = time.perf_counter()
    full = solve_integrated_mess(
        case="B2",
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
    full_seconds = time.perf_counter() - full_started
    old_record = json.loads((root / f"{mess_id}_RESULT.json").read_text(encoding="utf-8"))
    k800_record = root / f"{mess_id}_K800_RESULT.json"
    if not k800_record.is_file():
        shutil.copy2(root / f"{mess_id}_RESULT.json", k800_record)
    record = {
        **old_record,
        "fallback_level": "FULL_FULL_MILP_INCUMBENT_REGRESSED",
        "fallback_trigger": "FULL_MILP_INCUMBENT_REGRESSED_VS_VALIDATED_APR01_AUTHORITY",
        "restricted_exact_solve_count": len(enumeration.candidates),
        "restricted_exact_solve_wallclock_seconds": (
            float(old_record["restricted_exact_solve_wallclock_seconds"])
            + fallback_scan_seconds
        ),
        "fallback_incremental_exact_solve_count": len(remaining),
        "fallback_incremental_wallclock_seconds": fallback_scan_seconds,
        "best_restricted_candidate": asdict(best_candidate),
        "best_restricted_objective": float(best_dispatch["objective"]),
        "best_restricted_rho": float(best_evaluation["rho"]),
        "full_first_incumbent": float(best_dispatch["objective"]),
        "full_objective": float(full.objective),
        "full_best_bound": _finite(full.best_bound),
        "full_MIP_gap": _finite(full.mip_gap),
        "full_termination": full.termination,
        "full_MILP_wallclock_seconds": full_seconds,
        "MIPStart_accepted": bool(full.mip_start_accepted),
        "preferred_MIPStart_loaded": bool(full.preferred_mip_start_loaded),
        "natural_MOVE_count": len(full.trajectory.planned_move_commitments()),
        "natural_moves": [asdict(row) for row in full.trajectory.planned_move_commitments()],
        "trajectory_sha256": full.trajectory.canonical_sha256,
        "trajectory_slots": [row.to_dict() for row in full.trajectory.slots],
        "total_MESS_search_wallclock_seconds": (
            float(old_record["cheap_screen_wallclock_seconds"])
            + float(old_record["restricted_exact_solve_wallclock_seconds"])
            + fallback_scan_seconds + full_seconds
        ),
    }
    _json(root / f"{mess_id}_RESULT.json", record)
    records.append(record)
    new_slots = list(full.trajectory.slots)
    fleet_slots.extend(new_slots)
    trajectory = MessTrajectory(tuple(fleet_slots))
    arrays, planning = _planning_grid(coefficients, electrical.voltage, aidc, trajectory)
    np.savez_compressed(root / "FINAL_PLANNING_GRID.npz", **arrays)
    final = {
        "case": "B2",
        "day": APR01,
        "vehicles": records,
        "planning": planning,
        "trajectory_sha256": trajectory.canonical_sha256,
        "natural_MOVE_count": len(trajectory.planned_move_commitments()),
        "natural_moves": [asdict(row) for row in trajectory.planned_move_commitments()],
        "trajectory_slots": [row.to_dict() for row in trajectory.slots],
    }
    _json(root / "FINAL_RESULT.json", final)
    _json(artifact / "V35R3E_B2_SEQUENTIAL_FINAL.json", final)
    electrical.voltage.close()
    electrical.current.close()
    print(json.dumps({
        "best": best_candidate.candidate_id,
        "planning_rho": planning["rho"],
        "fallback_incremental_solves": len(remaining),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
