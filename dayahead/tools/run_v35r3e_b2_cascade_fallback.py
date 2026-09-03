"""Cascade the recorded B2 regression fallback from MESS03 through MESS04."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import time

import numpy as np

from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v33m.mess_trajectory import MessTrajectory
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
    _row,
)
from dayahead.tools.run_v35r3e_full_fallback import (
    ARTIFACT_ROOT,
    CACHE_ROOT,
    _add,
    _finite,
    _json,
    _safe_worker,
    _slots,
)


def _full_scan(
    *,
    case_root: Path,
    mess_id: str,
    seed_path: Path | None,
    aidc: np.ndarray,
    coefficients: tuple[object, ...],
    services: tuple[str, ...],
    fixed_p: dict[tuple[str, int], float],
    fixed_q: dict[tuple[str, int], float],
    route_table: object,
    line_states: set[tuple[int, int]],
    workers: int,
) -> tuple[dict[str, object], dict[str, object], float, int, Path]:
    enumeration = enumerate_initial_relocations(
        day=APR01,
        mess_id=mess_id,
        initial_service=MESS_INITIAL[mess_id],
        route_table=route_table,
    )
    by_id = {row.candidate_id: row for row in enumeration.candidates}
    path = case_root / f"{mess_id}_CASCADE_FULL_VALUES.csv"
    if not path.is_file() and seed_path is not None:
        shutil.copy2(seed_path, path)
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as stream:
            completed = {row["candidate_id"]: row for row in csv.DictReader(stream)}
    else:
        completed = {}
    if not set(completed).issubset(by_id):
        raise RuntimeError(f"V35R3E_CASCADE_AUTHORITY:{mess_id}")
    initial_count = len(completed)
    remaining = [row for row in enumeration.candidates if row.candidate_id not in completed]
    started = time.perf_counter()
    with path.open("a" if path.is_file() else "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        if initial_count == 0:
            writer.writeheader()
        retries = []
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(
                "B2", aidc, coefficients, services, fixed_p, fixed_q,
                line_states, set(), set(), set(),
            ),
        ) as pool:
            for index, result in enumerate(
                pool.map(_safe_worker, remaining, chunksize=4), start=1,
            ):
                if result["status"] == "RETRY":
                    retries.append(result)
                    continue
                row = result["row"]
                writer.writerow(row)
                stream.flush()
                completed[str(row["candidate_id"])] = row
                if index % 100 == 0:
                    print(
                        f"B2 {mess_id} CASCADE {len(completed)}/{len(enumeration.candidates)}",
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
            row = _row(
                "B2", candidate, dispatch, evaluation,
                time.perf_counter() - retry_started,
            )
            item.model.dispose()
            writer.writerow(row)
            stream.flush()
            completed[str(row["candidate_id"])] = row
            print(f"B2 {mess_id} NUMERIC_RETRY {candidate.candidate_id}", flush=True)
    elapsed = time.perf_counter() - started
    with path.open(encoding="utf-8", newline="") as stream:
        values = list(csv.DictReader(stream))
    if len(values) != len(enumeration.candidates):
        raise RuntimeError(f"V35R3E_CASCADE_INCOMPLETE:{mess_id}:{len(values)}")
    best_row = min(values, key=lambda row: (float(row["objective"]), row["candidate_id"]))
    candidate = by_id[best_row["candidate_id"]]
    model = build_fixed_candidate_model(
        candidate=candidate,
        aidc_pcc_kw_96x12=aidc,
        coefficients=coefficients,
        services=services,
        fixed_mess_p_by_service=fixed_p,
        fixed_mess_q_by_service=fixed_q,
        line_states=line_states,
    )
    dispatch, evaluation = solve_fixed_candidate_certified(model)
    model.model.dispose()
    return dispatch, evaluation, elapsed, len(enumeration.candidates) - initial_count, path


def main() -> None:
    repo = Path.cwd().resolve()
    root = (repo / CACHE_ROOT / APR01 / "B2").resolve()
    artifact = (repo / ARTIFACT_ROOT).resolve()
    records = [
        json.loads((root / f"{mess_id}_RESULT.json").read_text(encoding="utf-8"))
        for mess_id in MESS_IDS[:2]
    ]
    fixed_p: dict[tuple[str, int], float] = {}
    fixed_q: dict[tuple[str, int], float] = {}
    fleet_slots = []
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
    with np.load(
        repo / "dayahead/cache/v35" / PHASE_CALIBRATION / APR01 / "B0" / "PLANNING_GRID.npz",
        allow_pickle=False,
    ) as payload:
        line_states, _ = _critical_states(
            np.asarray(payload["phase_current_loading_pu"]),
            np.asarray([
                f"{name}::{phase}" for name, phase in zip(
                    np.asarray(payload["branch_names"]).astype(str),
                    np.asarray(payload["branch_phases"]).astype(str), strict=True,
                )
            ]),
        )

    for mess_id in MESS_IDS[2:]:
        seed = root / f"{mess_id}_TOPK_VALUES.csv" if mess_id == "MESS03" else None
        dispatch, evaluation, scan_seconds, incremental, values_path = _full_scan(
            case_root=root,
            mess_id=mess_id,
            seed_path=seed,
            aidc=aidc,
            coefficients=coefficients,
            services=services,
            fixed_p=fixed_p,
            fixed_q=fixed_q,
            route_table=route_table,
            line_states=line_states,
            workers=8,
        )
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
            preferred_restricted_start=dispatch,
        )
        full_seconds = time.perf_counter() - full_started
        old = json.loads((root / f"{mess_id}_RESULT.json").read_text(encoding="utf-8"))
        backup = root / f"{mess_id}_PRE_CASCADE_RESULT.json"
        if not backup.is_file():
            shutil.copy2(root / f"{mess_id}_RESULT.json", backup)
        candidate = dispatch["candidate"]
        record = {
            **old,
            "fallback_level": "FULL_CASCADE_FINAL_REGRESSION",
            "fallback_trigger": "FULL_MILP_INCUMBENT_REGRESSED_VS_VALIDATED_APR01_AUTHORITY",
            "restricted_exact_solve_count": int(sum(1 for _ in csv.DictReader(values_path.open(encoding="utf-8")))),
            "fallback_incremental_exact_solve_count": incremental,
            "fallback_incremental_wallclock_seconds": scan_seconds,
            "restricted_exact_solve_wallclock_seconds": scan_seconds,
            "best_restricted_candidate": asdict(candidate),
            "best_restricted_objective": float(dispatch["objective"]),
            "best_restricted_rho": float(evaluation["rho"]),
            "full_first_incumbent": float(dispatch["objective"]),
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
            "total_MESS_search_wallclock_seconds": scan_seconds + full_seconds,
            "full_values_path": str(values_path.relative_to(repo)).replace("\\", "/"),
        }
        _json(root / f"{mess_id}_RESULT.json", record)
        records.append(record)
        slots = list(full.trajectory.slots)
        fleet_slots.extend(slots)
        _add(slots, fixed_p, fixed_q)
        print(
            f"B2 {mess_id} CASCADE_COMPLETE best={candidate.candidate_id} full={full.objective}",
            flush=True,
        )

    trajectory = MessTrajectory(tuple(fleet_slots))
    arrays, planning = _planning_grid(coefficients, electrical.voltage, aidc, trajectory)
    np.savez_compressed(root / "FINAL_PLANNING_GRID.npz", **arrays)
    final = {
        "case": "B2", "day": APR01, "vehicles": records,
        "planning": planning, "trajectory_sha256": trajectory.canonical_sha256,
        "natural_MOVE_count": len(trajectory.planned_move_commitments()),
        "natural_moves": [asdict(row) for row in trajectory.planned_move_commitments()],
        "trajectory_slots": [row.to_dict() for row in trajectory.slots],
    }
    _json(root / "FINAL_RESULT.json", final)
    _json(artifact / "V35R3E_B2_SEQUENTIAL_FINAL.json", final)
    electrical.voltage.close()
    electrical.current.close()
    print(json.dumps({"final_planning_rho": planning["rho"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
