"""Run the Apr-01-only adaptive beam over sequential MESS fleet states."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict
import json
import math
from pathlib import Path
import time
from typing import Mapping, Sequence

import numpy as np

from dayahead.tools.run_v35r3_mess_scan import FIELDS, _critical_states, _row
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
    MobilityCandidate,
    build_fixed_candidate_model,
    enumerate_initial_relocations,
    solve_fixed_candidate_certified,
)
from dayahead.v35r3e.algorithm import (
    build_planning_screen_context,
    screen_dynamic_candidates,
)
from dayahead.v35r3e.source_lookup import install_missing_directory_tolerant_lookup
from dayahead.v35r3e_r1.beam import (
    BEAM_WIDTH,
    BEAM_WIDTH_FALLBACK,
    DEFAULT_K,
    SEED_WIDTH,
    BeamState,
    canonical_sha256,
    deduplicate_children,
    prune_beam,
    restricted_trajectory_signature,
    trajectory_equivalence_sha,
)


CACHE_ROOT = Path("dayahead/cache/v35r3e_r1_adaptive_beam_sequential_coordination")
PARENT_ARTIFACT_ROOT = Path(
    "dayahead/artifacts/v35r3e_mess_topk_warmstart_productionization"
)
STATIC_LIBRARY_COUNT = 2209
_WORKER: dict[str, object] = {}


def _json_default(value: object) -> object:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(type(value).__name__)


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _finite(value: object) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def _init_worker(
    case: str,
    aidc: np.ndarray,
    coefficients: Sequence[object],
    services: Sequence[str],
    fixed_p: Mapping[tuple[str, int], float],
    fixed_q: Mapping[tuple[str, int], float],
    line_states: set[tuple[int, int]],
    voltage_states: set[tuple[int, int]],
    tx_current_states: set[tuple[int, int]],
    tx_kva_states: set[tuple[int, int]],
) -> None:
    _WORKER.update({
        "case": case,
        "aidc": aidc,
        "coefficients": tuple(coefficients),
        "services": tuple(services),
        "fixed_p": dict(fixed_p),
        "fixed_q": dict(fixed_q),
        "line_states": set(line_states),
        "voltage_states": set(voltage_states),
        "tx_current_states": set(tx_current_states),
        "tx_kva_states": set(tx_kva_states),
    })


def _solve_item(
    case: str,
    candidate: MobilityCandidate,
    aidc: np.ndarray,
    coefficients: Sequence[object],
    services: Sequence[str],
    fixed_p: Mapping[tuple[str, int], float],
    fixed_q: Mapping[tuple[str, int], float],
    line_states: set[tuple[int, int]],
    voltage_states: set[tuple[int, int]],
    tx_current_states: set[tuple[int, int]],
    tx_kva_states: set[tuple[int, int]],
) -> tuple[
    dict[str, object], dict[str, object], dict[str, object], dict[str, object],
    dict[str, set[tuple[int, int]]],
]:
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
    repair = {"numeric_retry": False, "attempts": 1}
    try:
        try:
            dispatch, evaluation = solve_fixed_candidate_certified(item)
        except RuntimeError as exc:
            if "CERTIFICATE_STALLED" not in str(exc):
                raise
            item.model.dispose()
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
            item.model.Params.NumericFocus = 3
            item.model.Params.OptimalityTol = 1e-8
            repair = {"numeric_retry": True, "attempts": 2, "signature": str(exc)}
            dispatch, evaluation = solve_fixed_candidate_certified(
                item, max_separation_rounds=50,
            )
        row = _row(case, candidate, dispatch, evaluation, time.perf_counter() - started)
        cuts = {
            "line": set(item.added_line_states),
            "voltage": set(item.added_voltage_states),
            "tx_current": set(item.added_transformer_current_states),
            "tx_kva": set(item.added_transformer_kva_states),
        }
        return row, dispatch, evaluation, repair, cuts
    finally:
        item.model.dispose()


def _solve_worker(candidate: MobilityCandidate):
    return _solve_item(
        str(_WORKER["case"]),
        candidate,
        np.asarray(_WORKER["aidc"]),
        _WORKER["coefficients"],
        _WORKER["services"],
        _WORKER["fixed_p"],
        _WORKER["fixed_q"],
        _WORKER["line_states"],
        _WORKER["voltage_states"],
        _WORKER["tx_current_states"],
        _WORKER["tx_kva_states"],
    )


def _restore_slots(slots: Sequence[Mapping[str, object]]) -> list[MessTrajectorySlot]:
    result: list[MessTrajectorySlot] = []
    for source in slots:
        payload = dict(source)
        payload["route_link_ids"] = tuple(payload["route_link_ids"])
        result.append(MessTrajectorySlot(**payload))
    return result


def _fixed_maps(
    slots: Sequence[Mapping[str, object]],
) -> tuple[dict[tuple[str, int], float], dict[tuple[str, int], float]]:
    fixed_p: dict[tuple[str, int], float] = {}
    fixed_q: dict[tuple[str, int], float] = {}
    for slot in _restore_slots(slots):
        if slot.service_id is None:
            continue
        key = (slot.service_id, slot.slot)
        fixed_p[key] = fixed_p.get(key, 0.0) + float(slot.p_kw)
        fixed_q[key] = fixed_q.get(key, 0.0) + float(slot.q_kvar)
    return fixed_p, fixed_q


def _sparse_map(mapping: Mapping[tuple[str, int], float]) -> tuple[dict[str, object], ...]:
    return tuple(
        {"service_id": service, "slot": slot, "value": value}
        for (service, slot), value in sorted(mapping.items())
        if abs(float(value)) > 1e-9
    )


def _dispatch_json(dispatch: Mapping[str, object], signature: str) -> dict[str, object]:
    candidate = dispatch["candidate"]
    return {
        "candidate": asdict(candidate),
        "objective": float(dispatch["objective"]),
        "rho": float(dispatch["rho"]),
        "p_discharge_kw": np.asarray(dispatch["p_discharge_kw"], dtype=float).tolist(),
        "p_charge_kw": np.asarray(dispatch["p_charge_kw"], dtype=float).tolist(),
        "p_kw": np.asarray(dispatch["p_kw"], dtype=float).tolist(),
        "q_kvar": np.asarray(dispatch["q_kvar"], dtype=float).tolist(),
        "energy_kwh": np.asarray(dispatch["energy_kwh"], dtype=float).tolist(),
        "terminal_energy_kwh": float(dispatch["terminal_energy_kwh"]),
        "trajectory_signature": signature,
    }


def _dispatch_from_json(payload: Mapping[str, object]) -> dict[str, object]:
    candidate_payload = dict(payload["candidate"])
    candidate_payload["route_link_ids"] = tuple(candidate_payload["route_link_ids"])
    candidate = MobilityCandidate(**candidate_payload)
    return {
        "candidate": candidate,
        "objective": float(payload["objective"]),
        "rho": float(payload["rho"]),
        "p_discharge_kw": np.asarray(payload["p_discharge_kw"], dtype=float),
        "p_charge_kw": np.asarray(payload["p_charge_kw"], dtype=float),
        "p_kw": np.asarray(payload["p_kw"], dtype=float),
        "q_kvar": np.asarray(payload["q_kvar"], dtype=float),
        "energy_kwh": np.asarray(payload["energy_kwh"], dtype=float),
        "terminal_energy_kwh": float(payload["terminal_energy_kwh"]),
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _local_search(
    *,
    cache: Path,
    case: str,
    mess_id: str,
    sequence_index: int,
    parent: BeamState,
    aidc: np.ndarray,
    coefficients: Sequence[object],
    services: Sequence[str],
    route_table: object,
    seed_line: set[tuple[int, int]],
    workers: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    search_root = cache / f"s{sequence_index + 1}" / parent.beam_state_id
    search_root.mkdir(parents=True, exist_ok=True)
    seed_path = search_root / "SEEDS.json"
    summary_path = search_root / "LOCAL_SEARCH.json"
    if seed_path.is_file() and summary_path.is_file():
        seed_payload = json.loads(seed_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        return [
            {**row, "dispatch": _dispatch_from_json(row["dispatch"])}
            for row in seed_payload
        ], summary

    fixed_p, fixed_q = _fixed_maps(parent.trajectory_slots)
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
        case=case,
        mess_id=mess_id,
        route_table=route_table,
        context=context,
        variant="S4",
    )
    top_move_ids = [
        str(row["candidate_id"])
        for row in screen_rows
        if row["candidate_type"] == "MOVE"
    ][:DEFAULT_K]
    by_id = {candidate.candidate_id: candidate for candidate in enumeration.candidates}
    stay = next(candidate for candidate in enumeration.candidates if candidate.is_stay)
    selected_ids = [stay.candidate_id, *top_move_ids]
    if len(selected_ids) != DEFAULT_K + 1 or len(set(selected_ids)) != DEFAULT_K + 1:
        raise RuntimeError(f"V35R3E_R1_TOPK_ID_CONSERVATION:{case}:{mess_id}")

    line_states = set(seed_line)
    voltage_states: set[tuple[int, int]] = set()
    tx_current_states: set[tuple[int, int]] = set()
    tx_kva_states: set[tuple[int, int]] = set()
    representatives = [stay]
    seen_destinations = {stay.destination}
    for candidate_id in top_move_ids:
        candidate = by_id[candidate_id]
        if candidate.destination not in seen_destinations:
            representatives.append(candidate)
            seen_destinations.add(candidate.destination)

    started = time.perf_counter()
    solved: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
    rows: list[dict[str, object]] = []
    numeric_repairs: list[dict[str, object]] = []
    for candidate in representatives:
        row, dispatch, _evaluation, repair, cuts = _solve_item(
            case,
            candidate,
            aidc,
            coefficients,
            services,
            fixed_p,
            fixed_q,
            line_states,
            voltage_states,
            tx_current_states,
            tx_kva_states,
        )
        rows.append(row)
        solved[candidate.candidate_id] = (row, dispatch)
        if repair["numeric_retry"]:
            numeric_repairs.append({"candidate_id": candidate.candidate_id, **repair})
        line_states.update(cuts["line"])
        voltage_states.update(cuts["voltage"])
        tx_current_states.update(cuts["tx_current"])
        tx_kva_states.update(cuts["tx_kva"])

    representative_ids = {candidate.candidate_id for candidate in representatives}
    remaining = [
        by_id[candidate_id]
        for candidate_id in selected_ids
        if candidate_id not in representative_ids
    ]
    with ProcessPoolExecutor(
        max_workers=max(1, int(workers)),
        initializer=_init_worker,
        initargs=(
            case,
            aidc,
            coefficients,
            services,
            fixed_p,
            fixed_q,
            line_states,
            voltage_states,
            tx_current_states,
            tx_kva_states,
        ),
    ) as pool:
        for index, (row, dispatch, _evaluation, repair, _cuts) in enumerate(
            pool.map(_solve_worker, remaining, chunksize=4), start=1
        ):
            rows.append(row)
            solved[str(row["candidate_id"])] = (row, dispatch)
            if repair["numeric_retry"]:
                numeric_repairs.append({"candidate_id": row["candidate_id"], **repair})
            if index % 50 == 0:
                print(
                    f"{case} width parent={parent.beam_state_id} {mess_id} "
                    f"restricted={len(rows)}/{DEFAULT_K + 1}",
                    flush=True,
                )
    restricted_seconds = time.perf_counter() - started
    if len(rows) != DEFAULT_K + 1 or len(solved) != DEFAULT_K + 1:
        raise RuntimeError(f"V35R3E_R1_RESTRICTED_COUNT:{case}:{mess_id}:{len(rows)}")
    rows.sort(key=lambda row: (float(row["objective"]), str(row["candidate_id"])))
    _write_csv(search_root / "RESTRICTED_VALUES.csv", rows)

    seeds: list[dict[str, object]] = []
    signatures: set[str] = set()
    best_objective = float(rows[0]["objective"])
    for row in rows:
        candidate_id = str(row["candidate_id"])
        dispatch = solved[candidate_id][1]
        signature = restricted_trajectory_signature(dispatch["candidate"], dispatch)
        if signature in signatures:
            continue
        signatures.add(signature)
        seeds.append({
            "seed_index": len(seeds) + 1,
            "candidate_id": candidate_id,
            "restricted_objective": float(row["objective"]),
            "restricted_regret_vs_seed1": float(row["objective"]) - best_objective,
            "trajectory_signature": signature,
            "dispatch": dispatch,
        })
        if len(seeds) == SEED_WIDTH:
            break
    if not seeds:
        raise RuntimeError(f"V35R3E_R1_NO_FEASIBLE_SEED:{case}:{mess_id}")
    serializable_seeds = [
        {
            key: (_dispatch_json(value, seed["trajectory_signature"]) if key == "dispatch" else value)
            for key, value in seed.items()
        }
        for seed in seeds
    ]
    summary = {
        "case": case,
        "mess_id": mess_id,
        "parent_state_id": parent.beam_state_id,
        "K0": DEFAULT_K,
        "screen_variant": "S4",
        "static_candidates_fail_closed_evaluated": STATIC_LIBRARY_COUNT,
        "dynamic_feasible_candidates": len(enumeration.candidates),
        "dynamic_infeasible_candidates": STATIC_LIBRARY_COUNT - len(enumeration.candidates),
        "cheap_screen_wallclock_seconds": screen_seconds,
        "restricted_unique_candidate_state_solves": len(selected_ids),
        "restricted_solver_calls": len(selected_ids) + len(numeric_repairs),
        "restricted_wallclock_seconds": restricted_seconds,
        "selected_candidate_ids": selected_ids,
        "distinct_seed_count": len(seeds),
        "seed_candidate_ids": [seed["candidate_id"] for seed in seeds],
        "seed_trajectory_signatures": [seed["trajectory_signature"] for seed in seeds],
        "screen_authority_sha": context.authority_sha,
        "numeric_repairs": numeric_repairs,
        "Fresh_reads": 0,
        "future_vehicle_reads": 0,
    }
    _json(seed_path, serializable_seeds)
    _json(summary_path, summary)
    return seeds, summary


def _make_child(
    *,
    case: str,
    mess_id: str,
    sequence_index: int,
    parent: BeamState,
    seed: Mapping[str, object],
    aidc: np.ndarray,
    electrical: object,
    route_table: object,
    coefficients: Sequence[object],
) -> BeamState:
    fixed_p, fixed_q = _fixed_maps(parent.trajectory_slots)
    full_started = time.perf_counter()
    full = solve_integrated_mess(
        case=case,
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
        preferred_restricted_start=seed["dispatch"],
    )
    full_wallclock = time.perf_counter() - full_started
    new_slots = [slot.to_dict() for slot in full.trajectory.slots]
    accumulated = tuple((*parent.trajectory_slots, *new_slots))
    combined_p, combined_q = _fixed_maps(accumulated)
    equivalence_sha = trajectory_equivalence_sha(accumulated)
    completed = tuple((*parent.completed_vehicles, mess_id))
    state_sha = canonical_sha256({
        "case": case,
        "completed_vehicles": list(completed),
        "trajectory_equivalence_sha256": equivalence_sha,
    })
    state_id = f"{case}-S{sequence_index + 1}-{state_sha[:16]}"
    vehicle = {
        "case": case,
        "mess_id": mess_id,
        "sequence_index": sequence_index,
        "parent_state_id": parent.beam_state_id,
        "MIPStart_source_candidate": seed["candidate_id"],
        "MIPStart_source_trajectory_signature": seed["trajectory_signature"],
        "MIPStart_restricted_objective": seed["restricted_objective"],
        "MIPStart_seed_index": seed["seed_index"],
        "MIPStart_accepted": bool(full.mip_start_accepted),
        "preferred_MIPStart_loaded": bool(full.preferred_mip_start_loaded),
        "full_solver_objective": float(full.objective),
        "full_planning_objective": float(full.planning_rho),
        "full_best_bound": _finite(full.best_bound),
        "full_gap": _finite(full.mip_gap),
        "solver_status": full.termination,
        "work_limit_tiers_attempted": list(full.work_limit_tiers_attempted),
        "full_MILP_wallclock_seconds": full_wallclock,
        "move_binary_count": int(full.move_binary_count),
        "forced_MOVE_count": 0,
        "natural_MOVE_count": len(full.trajectory.planned_move_commitments()),
        "natural_moves": [asdict(row) for row in full.trajectory.planned_move_commitments()],
        "trajectory_sha256": full.trajectory.canonical_sha256,
        "trajectory_slots": new_slots,
    }
    return BeamState(
        case_id=case,
        beam_state_id=state_id,
        parent_state_id=parent.beam_state_id,
        completed_vehicles=completed,
        vehicles=tuple((*parent.vehicles, vehicle)),
        trajectory_slots=accumulated,
        combined_fixed_p_by_service=_sparse_map(combined_p),
        combined_fixed_q_by_service=_sparse_map(combined_q),
        current_planning_objective=float(full.planning_rho),
        solver_objective=float(full.objective),
        best_bound=_finite(full.best_bound),
        gap=_finite(full.mip_gap),
        state_sha256=state_sha,
        trajectory_equivalence_sha256=equivalence_sha,
    )


def _run_case(case: str, width: int, workers: int) -> dict[str, object]:
    if width not in (BEAM_WIDTH, BEAM_WIDTH_FALLBACK):
        raise ValueError("V35R3E_R1_ONLY_WIDTH_2_OR_4")
    repo = Path.cwd().resolve()
    root = (repo / CACHE_ROOT / APR01 / case / f"B{width}").resolve()
    root.mkdir(parents=True, exist_ok=True)

    install_missing_directory_tolerant_lookup()

    _data, electrical, bases = prepare_aidc_stages(
        repo,
        DEFAULT_SOURCE_REPO,
        (repo / "dayahead/cache/v35").resolve(),
        PHASE_CALIBRATION,
        APR01,
        None,
    )
    _bundle, _graph, route_table, _files = daily_traffic_authority(
        repo,
        (repo / "dayahead/cache/v35").resolve(),
        PHASE_CALIBRATION,
        APR01,
        None,
    )
    coefficients = tuple(
        slot_coefficients(
            electrical.legacy_context, electrical.voltage, electrical.current, slot
        )
        for slot in range(96)
    )
    stage = "B0" if case == "B2" else "B1"
    aidc = np.asarray(bases[stage]["planning_pcc_power_kw"], dtype=float)
    planning_path = (
        repo
        / "dayahead/cache/v35"
        / PHASE_CALIBRATION
        / APR01
        / stage
        / "PLANNING_GRID.npz"
    )
    with np.load(planning_path, allow_pickle=False) as payload:
        branch_names = np.asarray(payload["branch_names"]).astype(str)
        branch_phases = np.asarray(payload["branch_phases"]).astype(str)
        seed_line, congestion = _critical_states(
            np.asarray(payload["phase_current_loading_pu"]),
            np.asarray(
                [
                    f"{name}::{phase}"
                    for name, phase in zip(branch_names, branch_phases, strict=True)
                ]
            ),
        )
    _json(root / "CONGESTION_MAP.json", congestion)
    services = tuple(
        name[10:-1]
        for name in map(str, electrical.voltage["control_names"])
        if name.startswith("mess_p_kw[")
    )
    try:
        _arrays, baseline_planning = _planning_grid(
            coefficients, electrical.voltage, aidc, MessTrajectory(())
        )
        root_state = BeamState(
            case_id=case,
            beam_state_id=f"{case}-ROOT",
            parent_state_id=None,
            completed_vehicles=(),
            vehicles=(),
            trajectory_slots=(),
            combined_fixed_p_by_service=(),
            combined_fixed_q_by_service=(),
            current_planning_objective=float(baseline_planning["rho"]),
            solver_objective=float(baseline_planning["rho"]),
            best_bound=None,
            gap=None,
            state_sha256=canonical_sha256({"case": case, "root": True}),
            trajectory_equivalence_sha256=trajectory_equivalence_sha(()),
        )
        beam = [root_state]
        trace: list[dict[str, object]] = []
        all_dedup: list[dict[str, object]] = []
        run_started = time.perf_counter()
        for sequence_index, mess_id in enumerate(MESS_IDS):
            stage_path = root / f"STAGE_{sequence_index + 1}.json"
            if stage_path.is_file():
                payload = json.loads(stage_path.read_text(encoding="utf-8"))
                beam = [BeamState.from_dict(row) for row in payload["retained_states"]]
                trace.append(dict(payload["trace"]))
                all_dedup.extend(payload["dedup_audit"])
                print(f"{case} beam={width} {mess_id} RESTORED", flush=True)
                continue

            parent_diagnostics: list[dict[str, object]] = []
            children: list[BeamState] = []
            for parent in beam:
                seeds, local = _local_search(
                    cache=root,
                    case=case,
                    mess_id=mess_id,
                    sequence_index=sequence_index,
                    parent=parent,
                    aidc=aidc,
                    coefficients=coefficients,
                    services=services,
                    route_table=route_table,
                    seed_line=seed_line,
                    workers=workers,
                )
                child_ids: list[str] = []
                for seed in seeds:
                    child = _make_child(
                        case=case,
                        mess_id=mess_id,
                        sequence_index=sequence_index,
                        parent=parent,
                        seed=seed,
                        aidc=aidc,
                        electrical=electrical,
                        route_table=route_table,
                        coefficients=coefficients,
                    )
                    children.append(child)
                    child_ids.append(child.beam_state_id)
                    _json(
                        root
                        / f"s{sequence_index + 1}"
                        / parent.beam_state_id
                        / f"CHILD_{seed['seed_index']}.json",
                        child.to_dict(),
                    )
                    print(
                        f"{case} beam={width} {mess_id} parent={parent.beam_state_id} "
                        f"seed={seed['seed_index']} rho={child.current_planning_objective}",
                        flush=True,
                    )
                parent_diagnostics.append({**local, "child_state_ids": child_ids})

            unique, dedup = deduplicate_children(children)
            retained, pruned = prune_beam(unique, width)
            all_dedup.extend(dedup)
            objectives = [state.current_planning_objective for state in retained]
            trace_row = {
                "case": case,
                "beam_width": width,
                "stage": sequence_index + 1,
                "mess_id": mess_id,
                "parent_beam_count": len(beam),
                "cheap_score_candidate_count": sum(
                    int(row["static_candidates_fail_closed_evaluated"])
                    for row in parent_diagnostics
                ),
                "restricted_unique_candidate_state_solves": sum(
                    int(row["restricted_unique_candidate_state_solves"])
                    for row in parent_diagnostics
                ),
                "restricted_solver_calls": sum(
                    int(row["restricted_solver_calls"]) for row in parent_diagnostics
                ),
                "distinct_seed_count": sum(
                    int(row["distinct_seed_count"]) for row in parent_diagnostics
                ),
                "full_MILP_child_solve_count": len(children),
                "deduplicated_child_count": len(unique),
                "duplicate_children_removed": len(children) - len(unique),
                "retained_beam_count": len(retained),
                "retained_state_ids": [state.beam_state_id for state in retained],
                "pruned_state_ids": [state.beam_state_id for state in pruned],
                "current_best_objective": min(objectives),
                "current_worst_retained_objective": max(objectives),
                "beam_objective_spread": max(objectives) - min(objectives),
                "retained_trajectory_SHAs": [
                    state.trajectory_equivalence_sha256 for state in retained
                ],
                "cheap_screen_wallclock_seconds": sum(
                    float(row["cheap_screen_wallclock_seconds"])
                    for row in parent_diagnostics
                ),
                "restricted_wallclock_seconds": sum(
                    float(row["restricted_wallclock_seconds"])
                    for row in parent_diagnostics
                ),
                "full_MILP_wallclock_seconds": sum(
                    float(state.vehicles[-1]["full_MILP_wallclock_seconds"])
                    for state in children
                ),
            }
            payload = {
                "trace": trace_row,
                "parent_diagnostics": parent_diagnostics,
                "retained_states": [state.to_dict() for state in retained],
                "pruned_states": [state.to_dict() for state in pruned],
                "dedup_audit": dedup,
            }
            _json(stage_path, payload)
            trace.append(trace_row)
            beam = retained

        final_state = min(beam, key=lambda state: state.current_planning_objective)
        trajectory = MessTrajectory(tuple(_restore_slots(final_state.trajectory_slots)))
        arrays, planning = _planning_grid(coefficients, electrical.voltage, aidc, trajectory)
        np.savez_compressed(root / "FINAL_PLANNING_GRID.npz", **arrays)
        final = {
            "case": case,
            "day": APR01,
            "beam_width": width,
            "selected_state": final_state.to_dict(),
            "retained_final_states": [state.to_dict() for state in beam],
            "planning": planning,
            "trajectory_sha256": trajectory.canonical_sha256,
            "trajectory_equivalence_sha256": trajectory_equivalence_sha(
                final_state.trajectory_slots
            ),
            "natural_MOVE_count": len(trajectory.planned_move_commitments()),
            "natural_moves": [asdict(row) for row in trajectory.planned_move_commitments()],
            "trajectory_slots": [row.to_dict() for row in trajectory.slots],
            "trace": trace,
            "child_dedup_audit": all_dedup,
            "run_wallclock_seconds": time.perf_counter() - run_started,
            "Fresh_reads": 0,
        }
        _json(root / "FINAL_RESULT.json", final)
        print(
            f"{case} beam={width} COMPLETE rho={planning['rho']} "
            f"state={final_state.beam_state_id}",
            flush=True,
        )
        return final
    finally:
        electrical.voltage.close()
        electrical.current.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("B2", "B3"), required=True)
    parser.add_argument("--beam-width", type=int, choices=(2, 4), default=2)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    _run_case(args.case, args.beam_width, args.workers)


if __name__ == "__main__":
    main()
