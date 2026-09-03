"""One-date V37 runner using the frozen V36 AIDC and MESS authorities."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import traceback
from typing import Any, Mapping

import pandas as pd

from dayahead.v35.contracts import PHASE_CALIBRATION
from dayahead.v35.execution import daily_traffic_authority
from dayahead.v36 import runner as v36_runner
from dayahead.v36.storage import CASE_FILES, file_sha

from .aidc import build_day
from .context import load_day_context
from .contracts import (
    ARTIFACT_ROOT, BEAM_PROGRESS_BASE, BEAM_WIDTH, BEAM_WIDTH_FALLBACK,
    CACHE_ROOT, DATE_RESULT_ROOT, FIREWALL, MAX_WORKERS_PER_DATE,
    OFFICIAL_CASES, PASS_ID, PHASE, PROGRESS_AFTER_CASE, RAW_ROOT,
    SOURCE_DATA_REPOSITORY, STATUS_ROOT,
)
from .status import atomic_json, read_json, write_status


ADMISSION = {"status": "PASS", "May_numeric_reads_before_admission": 0}

_LOCAL_FALLBACK_SIGNATURES = (
    "V35R3_FIXED_CANDIDATE_STATUS",
    "V35R3_FIXED_CERTIFICATE_STALLED",
    "V35R3_FIXED_CERTIFICATE_ROUND_LIMIT",
    "V35R3E_R1_TOPK_ID_CONSERVATION",
    "V35R3E_R1_RESTRICTED_COUNT",
    "V35R3E_R1_NO_FEASIBLE_SEED",
)


def _local_fallback_allowed(error: Exception) -> bool:
    return any(signature in str(error) for signature in _LOCAL_FALLBACK_SIGNATURES)


def _failed_candidate_result(
    case: str, candidate: Any, error: Exception, elapsed: float,
) -> tuple[dict[str, Any], None, dict[str, Any], dict[str, Any], dict[str, set[tuple[int, int]]]]:
    """Represent an explicitly uncertified restricted candidate as fail-closed."""

    source = asdict(candidate)
    signature = f"{type(error).__name__}:{error}"
    row = {
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
        "objective": 1.0e300,
        "rho": 1.0e300,
        "binding_asset": "UNCERTIFIED_FAIL_CLOSED",
        "binding_slot": -1,
        "Vmin_pu": 0.0,
        "Vmax_pu": 0.0,
        "post_arrival_sum_abs_p_kw_slots": 0.0,
        "post_arrival_sum_abs_q_kvar_slots": 0.0,
        "terminal_energy_kwh": 0.0,
        "exact_optimality_certificate": f"V37_FAIL_CLOSED:{signature}",
        "runtime_seconds": float(elapsed),
    }
    repair = {
        "numeric_retry": False,
        "attempts": 2,
        "fail_closed": True,
        "signature": signature,
    }
    empty_cuts = {name: set() for name in ("line", "voltage", "tx_current", "tx_kva")}
    return row, None, {}, repair, empty_cuts


def _v37_safe_restricted_worker(candidate: Any) -> tuple[Any, ...]:
    """Process-pool entry that contains only frozen certification failures."""

    import dayahead.tools.run_v35r3e_r1_beam as frozen

    started = time.perf_counter()
    try:
        return frozen._solve_item(
            str(frozen._WORKER["case"]),
            candidate,
            frozen._WORKER["aidc"],
            frozen._WORKER["coefficients"],
            frozen._WORKER["services"],
            frozen._WORKER["fixed_p"],
            frozen._WORKER["fixed_q"],
            frozen._WORKER["line_states"],
            frozen._WORKER["voltage_states"],
            frozen._WORKER["tx_current_states"],
            frozen._WORKER["tx_kva_states"],
        )
    except Exception as error:
        if not _local_fallback_allowed(error):
            raise
        return _failed_candidate_result(
            str(frozen._WORKER["case"]), candidate, error,
            time.perf_counter() - started,
        )


def _beam_fallback_allowed(error: Exception) -> bool:
    """Keep B=2 -> B=4 limited to an explicit frozen beam-path failure."""

    message = str(error)
    return any(signature in message for signature in (
        "V35R3E_R1_PATH_REGRESSION",
        "V35R3E_R1_BEAM_PATH_FAILURE",
    ))


def _archive_local_attempt(search_root: Path, level: str) -> None:
    for name in ("RESTRICTED_VALUES.csv", "SEEDS.json", "LOCAL_SEARCH.json"):
        source = search_root / name
        if not source.is_file():
            continue
        suffix = Path(name).suffix
        stem = Path(name).stem
        index = 1
        while True:
            target = search_root / f"{stem}.K{level}.ATTEMPT{index}{suffix}"
            if not target.exists():
                source.replace(target)
                break
            index += 1


def _run_local_with_frozen_k_fallback(
    frozen: Any, original_local: Any, **kwargs: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply the frozen 200 -> 400 -> 800 -> FULL local-search hierarchy."""

    enumeration = frozen.enumerate_initial_relocations(
        day=frozen.APR01,
        mess_id=kwargs["mess_id"],
        initial_service=frozen.MESS_INITIAL[kwargs["mess_id"]],
        route_table=kwargs["route_table"],
    )
    full_k = max(0, len(enumeration.candidates) - 1)
    numeric_levels = [level for level in (200, 400, 800) if level <= full_k]
    levels = [*numeric_levels]
    if full_k not in levels:
        levels.append(full_k)
    attempts: list[dict[str, Any]] = []
    search_root = (
        kwargs["cache"]
        / f"s{int(kwargs['sequence_index']) + 1}"
        / kwargs["parent"].beam_state_id
    )
    original_k = frozen.DEFAULT_K
    try:
        for index, level in enumerate(levels):
            label = "FULL" if level == full_k else str(level)
            frozen.DEFAULT_K = level
            try:
                seeds, summary = original_local(**kwargs)
            except Exception as error:
                if not _local_fallback_allowed(error) or index == len(levels) - 1:
                    raise
                attempts.append({
                    "K": label,
                    "status": "EXPLICIT_LOCAL_SEARCH_FAILURE",
                    "signature": f"{type(error).__name__}:{error}",
                })
                _archive_local_attempt(search_root, label)
                continue

            values_path = search_root / "RESTRICTED_VALUES.csv"
            values = pd.read_csv(values_path) if values_path.is_file() else pd.DataFrame()
            failed = values.loc[
                values.get("exact_optimality_certificate", pd.Series(dtype=str))
                .astype(str).str.startswith("V37_FAIL_CLOSED:")
            ] if len(values) else values
            failure_rows = failed.to_dict("records") if len(failed) else []
            attempt = {
                "K": label,
                "status": "CERTIFIED" if not failure_rows else "CERTIFICATION_FAILURE",
                "restricted_candidates": int(len(values)),
                "uncertified_candidate_count": len(failure_rows),
                "uncertified_candidate_ids": [str(row["candidate_id"]) for row in failure_rows],
                "signatures": [str(row["exact_optimality_certificate"]) for row in failure_rows],
            }
            attempts.append(attempt)
            if failure_rows and index < len(levels) - 1:
                _archive_local_attempt(search_root, label)
                continue

            updated = dict(summary)
            updated.update({
                "K0": 200,
                "selected_K": label,
                "K_fallback_used": index > 0,
                "full_scan_used": label == "FULL",
                "uncertified_candidates_fail_closed": len(failure_rows),
                "K_fallback_attempts": attempts,
                "K_fallback_sequence": [200, 400, 800, "FULL"],
            })
            frozen._json(search_root / "LOCAL_SEARCH.json", updated)
            return seeds, updated
        raise RuntimeError("V37_FROZEN_K_FALLBACK_EXHAUSTED")
    finally:
        frozen.DEFAULT_K = original_k


def _beam_k_fallback_counts(root: Path) -> tuple[int, int]:
    fallback_count = 0
    full_count = 0
    for stage_path in sorted(root.glob("STAGE_*.json")):
        stage = read_json(stage_path)
        for local in stage.get("parent_diagnostics", []):
            fallback_count += int(bool(local.get("K_fallback_used")))
            full_count += int(bool(local.get("full_scan_used")))
    return fallback_count, full_count


def _status_path(repo: Path, day: str) -> Path:
    return repo / STATUS_ROOT / f"{day}.json"


def _input_authority(repo: Path, day: str, case: str, trajectory: Any) -> dict[str, Any]:
    from dayahead.v28r2.source_cache import day_root
    source_day = day_root(SOURCE_DATA_REPOSITORY, day)
    paths = {
        "D_minus_1_load_PV": source_day / "aemo_forecast.json",
        "weather_forecast": source_day / "gfs_d1_weather.parquet",
        "traffic_prediction": repo / CACHE_ROOT / "traffic/shared/traffic" / day / "TRAFFIC_FORECAST.npz",
        "MESS_route_table": repo / CACHE_ROOT / "traffic/shared/traffic" / day / "ROUTE_TABLE.json.gz",
        "C1_parameters": repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json",
        "grid_base_case": SOURCE_DATA_REPOSITORY / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        "IDC_existing_location_mapping": repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json",
    }
    files = {
        label: {"path": str(path), "exists": path.is_file(), "sha256": file_sha(path) if path.is_file() else None}
        for label, path in paths.items()
    }
    return {
        "schema_id": "V37_INPUT_AUTHORITY_V1", "date": day, "case": case,
        "immutable_references": files,
        "AIDC_queue_snapshot": {
            "ledger_rows": len(trajectory.ledger), "D_minus_1_only": True,
            "frozen_daily_template": "V36_APR01_EXPANDED_TEMPORAL_PROFILE",
        },
        "AIDC_runtime_authority": "V35R3D_R1_SAFE_CAUSAL_RUNTIME",
        "AIDC_GPU_capacity": 624,
        "MESS_initial_location": ["STA01", "STA12", "STA08", "STA06"],
        "MESS_initial_SoC": 760.0 / 1200.0,
        "MESS_vehicle_parameters": "dayahead.mess_physics + V33M3 route authority",
        "IDC_LOCATION_CHANGED": "NO", "Fresh_used_for_decisions": "NO",
    }


def _beam_case(repo: Path, day: str, case: str, aidc_b0: Any, aidc_b1: Any) -> tuple[dict[str, Any], int]:
    import dayahead.tools.run_v35r3e_r1_beam as frozen
    import dayahead.v35r3.algorithm as r3
    import dayahead.v35r3e.algorithm as r3e

    data, electrical = load_day_context(repo, day)
    coefficients = v36_runner._coefficients(electrical)
    selected = aidc_b0 if case == "B2" else aidc_b1
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v35.execution import _planning_grid
    baseline_arrays, _ = _planning_grid(coefficients, electrical.voltage, selected.pcc_p_kw, MessTrajectory(()))
    v36_runner._prepare_seed_npz(repo, day, "B0" if case == "B2" else "B1", baseline_arrays, coefficients)
    original_traffic = frozen.daily_traffic_authority
    original_guards = r3.assert_apr01_only, r3e.assert_apr01_only
    original = {
        "APR01": frozen.APR01, "CACHE_ROOT": frozen.CACHE_ROOT,
        "prepare": frozen.prepare_aidc_stages, "traffic": frozen.daily_traffic_authority,
        "local_search": frozen._local_search, "solve_item": frozen._solve_item,
        "solve_worker": frozen._solve_worker, "DEFAULT_K": frozen.DEFAULT_K,
    }

    def selected_day(value: str) -> None:
        if not str(value).startswith("2025-05-"):
            raise PermissionError(f"V37_DATE_OUT_OF_SCOPE:{value}")

    frozen.APR01 = day
    frozen.CACHE_ROOT = CACHE_ROOT / PASS_ID / "beam"
    frozen.prepare_aidc_stages = lambda *_args, **_kwargs: (
        data, electrical,
        {"B0": {"planning_pcc_power_kw": aidc_b0.pcc_p_kw},
         "B1": {"planning_pcc_power_kw": aidc_b1.pcc_p_kw}},
    )
    frozen.daily_traffic_authority = lambda _repo, _cache, _phase, target, _admission: daily_traffic_authority(
        repo, repo / CACHE_ROOT / "traffic", PHASE, target, ADMISSION,
    )
    r3.assert_apr01_only = selected_day
    r3e.assert_apr01_only = selected_day

    def safe_parent_solve(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        started = time.perf_counter()
        try:
            return original["solve_item"](*args, **kwargs)
        except Exception as error:
            if not _local_fallback_allowed(error):
                raise
            return _failed_candidate_result(
                str(args[0]), args[1], error, time.perf_counter() - started,
            )

    frozen._solve_item = safe_parent_solve
    frozen._solve_worker = _v37_safe_restricted_worker
    frozen._local_search = lambda **kwargs: _run_local_with_frozen_k_fallback(
        frozen, original["local_search"], **kwargs,
    )
    try:
        last_error: Exception | None = None
        for width in (BEAM_WIDTH, BEAM_WIDTH_FALLBACK):
            final_path = repo / CACHE_ROOT / PASS_ID / "beam" / day / case / f"B{width}" / "FINAL_RESULT.json"
            if final_path.is_file():
                result = read_json(final_path)
                k_count, full_count = _beam_k_fallback_counts(final_path.parent)
                result["V37_K_fallback_count"] = k_count
                result["V37_FULL_scan_count"] = full_count
                return result, 0 if width == BEAM_WIDTH else 1
            try:
                os.chdir(repo)
                result = frozen._run_case(case, width, MAX_WORKERS_PER_DATE)
                k_count, full_count = _beam_k_fallback_counts(final_path.parent)
                result["V37_K_fallback_count"] = k_count
                result["V37_FULL_scan_count"] = full_count
                frozen._json(final_path, result)
                return result, 0 if width == BEAM_WIDTH else 1
            except Exception as error:
                last_error = error
                os.chdir(repo)
                if width == BEAM_WIDTH and _beam_fallback_allowed(error):
                    continue
                raise
        raise RuntimeError("V37_BEAM_EXHAUSTED") from last_error
    finally:
        frozen.APR01 = original["APR01"]
        frozen.CACHE_ROOT = original["CACHE_ROOT"]
        frozen.prepare_aidc_stages = original["prepare"]
        frozen.daily_traffic_authority = original_traffic
        frozen._local_search = original["local_search"]
        frozen._solve_item = original["solve_item"]
        frozen._solve_worker = original["solve_worker"]
        frozen.DEFAULT_K = original["DEFAULT_K"]
        r3.assert_apr01_only, r3e.assert_apr01_only = original_guards
        electrical.voltage.close(); electrical.current.close()
        os.chdir(repo)


def _case_root(repo: Path, day: str, case: str) -> Path:
    return repo / RAW_ROOT / PASS_ID / day / case


def _checkpoint_path(repo: Path, day: str, case: str) -> Path:
    return repo / CACHE_ROOT / PASS_ID / "case_checkpoints" / day / f"{case}.json"


def _valid_case_checkpoint(repo: Path, day: str, case: str) -> dict[str, Any] | None:
    path = _checkpoint_path(repo, day, case)
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
        if payload.get("status") != "PASS":
            return None
        root = _case_root(repo, day, case)
        for item in payload["files"]:
            candidate = root / item["relative_path"]
            if not candidate.is_file() or candidate.stat().st_size != item["bytes"]:
                return None
        return dict(payload["result"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _write_case_checkpoint(repo: Path, day: str, case: str, result: Mapping[str, Any]) -> None:
    root = _case_root(repo, day, case)
    files = [
        {"relative_path": relative, "bytes": (root / relative).stat().st_size}
        for relative in CASE_FILES if (root / relative).is_file()
    ]
    if len(files) != len(CASE_FILES):
        raise RuntimeError(f"V37_CASE_ARTIFACT_INCOMPLETE:{day}:{case}:{len(files)}")
    atomic_json(_checkpoint_path(repo, day, case), {
        "artifact_id": "V37_CASE_CHECKPOINT_V1", "date": day, "case": case,
        "status": "PASS", "files": files, "result": dict(result),
    })


def _watch_beam(repo: Path, day: str, case: str, stop: threading.Event) -> None:
    base = BEAM_PROGRESS_BASE[case]
    path = _status_path(repo, day)
    while not stop.wait(2.0):
        completed = 0
        current_width = BEAM_WIDTH
        for width in (BEAM_WIDTH, BEAM_WIDTH_FALLBACK):
            root = repo / CACHE_ROOT / PASS_ID / "beam" / day / case / f"B{width}"
            count = sum((root / f"STAGE_{index}.json").is_file() for index in range(1, 5))
            if count >= completed:
                completed, current_width = count, width
        stage = min(4, completed + 1)
        write_status(
            path, day, "RUNNING", base + completed,
            f"{case}_MESS{stage:02d}" if completed < 4 else f"{case}_FRESH",
            extra={"workers": MAX_WORKERS_PER_DATE, "beam_width_active": current_width},
        )


def _run_frozen_case(repo: Path, day: str, case: str, aidc: Any, beam: Mapping[str, Any] | None) -> dict[str, Any]:
    original_context = v36_runner.load_day_context
    original_cache = v36_runner.CACHE_ROOT
    original_input = v36_runner._input_authority
    v36_runner.load_day_context = lambda target: load_day_context(repo, target)
    v36_runner.CACHE_ROOT = CACHE_ROOT
    v36_runner._input_authority = _input_authority
    try:
        os.chdir(repo)
        return v36_runner.run_case(repo, PASS_ID, day, case, aidc, beam)
    finally:
        v36_runner.load_day_context = original_context
        v36_runner.CACHE_ROOT = original_cache
        v36_runner._input_authority = original_input
        os.chdir(repo)


def _case_metrics(repo: Path, day: str, case: str, result: Mapping[str, Any]) -> dict[str, Any]:
    root = _case_root(repo, day, case)
    objective = read_json(root / "summary/OBJECTIVE.json")
    gates = read_json(root / "summary/PHYSICAL_GATES.json")
    compute = read_json(root / "summary/COMPUTE_SUMMARY.json")
    provenance = read_json(root / "inputs/RUN_PROVENANCE.json")
    moves = pd.read_parquet(root / "mess/MESS_MOVE_EVENTS.parquet")
    solvers = pd.read_parquet(root / "solver/SOLVER_RUNS.parquet")
    planning, fresh = gates["Planning"], gates["Fresh"]
    beam_path = repo / CACHE_ROOT / PASS_ID / "beam" / day / case / f"B{BEAM_WIDTH}" / "FINAL_RESULT.json"
    if not beam_path.is_file() and case in {"B2", "B3"}:
        beam_path = repo / CACHE_ROOT / PASS_ID / "beam" / day / case / f"B{BEAM_WIDTH_FALLBACK}" / "FINAL_RESULT.json"
    trace = read_json(beam_path).get("trace", []) if beam_path.is_file() else []
    total = float(provenance["wallclock_seconds"])
    fresh_seconds = float(compute["Fresh_wallclock_seconds"])
    return {
        "J": float(objective["primary_objective_J"]),
        "Planning_rho": float(planning["rho"]), "Fresh_rho": float(fresh["rho"]),
        "Fresh_convergence": gates["Fresh_solve_coverage"],
        "voltage_violations": {"Planning": int(planning["voltage_violation_count"]), "Fresh": int(fresh["voltage_violation_count"])},
        "current_violations": {"Planning": int(planning["current_violation_count"]), "Fresh": int(fresh["current_violation_count"])},
        "transformer_violations": {"Planning": int(planning["transformer_violation_count"]), "Fresh": int(fresh["transformer_violation_count"])},
        "physical_violation_count": sum(int(block[key]) for block in (planning, fresh) for key in (
            "voltage_violation_count", "current_violation_count", "transformer_violation_count"
        )),
        "relocation_transitions": int(len(moves)),
        "relocations_by_vehicle": {str(k): int(v) for k, v in moves.groupby("vehicle_id").size().to_dict().items()},
        "fallback_count": int(result.get("beam_fallback", False)) + int(result.get("K_fallback", False)),
        "beam_fallback_count": int(result.get("beam_fallback", False)),
        "K_fallback_count": int(result.get("K_fallback", False)),
        "restricted_solve_count": sum(int(row.get("restricted_solver_calls", 0)) for row in trace),
        "full_MILP_count": sum(int(row.get("full_MILP_child_solve_count", 0)) for row in trace),
        "candidate_screen_wallclock_seconds": sum(float(row.get("cheap_screen_wallclock_seconds", 0.0)) for row in trace),
        "restricted_solve_wallclock_seconds": sum(float(row.get("restricted_wallclock_seconds", 0.0)) for row in trace),
        "full_MILP_wallclock_seconds": sum(float(row.get("full_MILP_wallclock_seconds", 0.0)) for row in trace),
        "Planning_wallclock_seconds": max(0.0, total - fresh_seconds),
        "Fresh_wallclock_seconds": fresh_seconds, "total_wallclock_seconds": total,
        "solver_statuses": sorted(set(map(str, solvers["status"]))) if len(solvers) else ["NOT_APPLICABLE"],
    }


def _finalize_day(repo: Path, day: str, results: Mapping[str, Mapping[str, Any]], started: float) -> dict[str, Any]:
    cases = {case: _case_metrics(repo, day, case, results[case]) for case in OFFICIAL_CASES}
    effects = {
        label: {
            "J": cases[left]["J"] - cases[right]["J"],
            "Planning_rho": cases[left]["Planning_rho"] - cases[right]["Planning_rho"],
            "Fresh_rho": cases[left]["Fresh_rho"] - cases[right]["Fresh_rho"],
        }
        for label, (left, right) in {
            "B1-B0": ("B1", "B0"), "B2-B0": ("B2", "B0"),
            "B3-B0": ("B3", "B0"), "B3-B2": ("B3", "B2"), "B3-B1": ("B3", "B1"),
        }.items()
    }
    fresh_pass = all(cases[case]["Fresh_convergence"] == "96/96" for case in OFFICIAL_CASES)
    physical_pass = all(cases[case]["physical_violation_count"] == 0 for case in OFFICIAL_CASES)
    elapsed = time.perf_counter() - started
    payload = {
        "artifact_id": "V37_MAY_DATE_RESULT_V1", "date": day,
        "status": "PASS" if fresh_pass and physical_pass else "FAIL",
        "cases": cases, "effects": effects,
        "Fresh_96_of_96_PASS": fresh_pass, "physical_gates_PASS": physical_pass,
        "workers": MAX_WORKERS_PER_DATE, "wallclock_seconds": elapsed,
        "firewall": FIREWALL,
    }
    atomic_json(repo / DATE_RESULT_ROOT / f"{day}.json", payload)
    return payload


def run_day(repo: Path, day: str) -> dict[str, Any]:
    started = time.perf_counter()
    status_path = _status_path(repo, day)
    previous = read_json(status_path) if status_path.is_file() else {}
    if previous.get("status") == "PASS" and (repo / DATE_RESULT_ROOT / f"{day}.json").is_file():
        return read_json(repo / DATE_RESULT_ROOT / f"{day}.json")
    write_status(status_path, day, "RUNNING", 0, "B0_PLANNING", extra={"workers": MAX_WORKERS_PER_DATE})
    try:
        aidc = {
            "B0": build_day(repo, day, "B0"), "B1": build_day(repo, day, "B1"),
        }
        aidc["B2"], aidc["B3"] = aidc["B0"], aidc["B1"]
        results: dict[str, dict[str, Any]] = {}
        for case in OFFICIAL_CASES:
            cached = _valid_case_checkpoint(repo, day, case)
            if cached is not None:
                results[case] = cached
                write_status(status_path, day, "RUNNING", PROGRESS_AFTER_CASE[case], f"{case}_RESTORED")
                continue
            beam = None
            fallback = 0
            if case in {"B2", "B3"}:
                stop = threading.Event()
                watcher = threading.Thread(target=_watch_beam, args=(repo, day, case, stop), daemon=True)
                watcher.start()
                try:
                    beam, fallback = _beam_case(repo, day, case, aidc["B0"], aidc["B1"])
                finally:
                    stop.set(); watcher.join(timeout=5)
                write_status(status_path, day, "RUNNING", BEAM_PROGRESS_BASE[case] + 4, f"{case}_FRESH")
            result = _run_frozen_case(repo, day, case, aidc[case], beam)
            result["beam_fallback"] = bool(fallback)
            result["K_fallback"] = bool(
                beam is not None and int(beam.get("V37_K_fallback_count", 0)) > 0
            )
            _write_case_checkpoint(repo, day, case, result)
            results[case] = result
            write_status(status_path, day, "RUNNING", PROGRESS_AFTER_CASE[case], f"{case}_COMPLETE")
        final = _finalize_day(repo, day, results, started)
        write_status(
            status_path, day, final["status"], 14, None,
            error=None if final["status"] == "PASS" else "FINAL_PHYSICAL_OR_FRESH_GATE_FAIL",
            extra={"result_path": str((repo / DATE_RESULT_ROOT / f"{day}.json").resolve())},
        )
        return final
    except Exception as error:
        failure = {
            "artifact_id": "V37_MAY_DATE_RESULT_V1", "date": day, "status": "FAIL",
            "error": f"{type(error).__name__}:{error}", "traceback": traceback.format_exc(),
            "wallclock_seconds": time.perf_counter() - started, "firewall": FIREWALL,
        }
        atomic_json(repo / DATE_RESULT_ROOT / f"{day}.json", failure)
        current = read_json(status_path) if status_path.is_file() else {"completed_units": 0}
        write_status(status_path, day, "FAIL", int(current.get("completed_units", 0)), None,
                     error=failure["error"], extra={"result_path": str((repo / DATE_RESULT_ROOT / f"{day}.json").resolve())})
        raise
