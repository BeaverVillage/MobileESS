"""One-date V37 runner using the frozen V36 AIDC and MESS authorities."""

from __future__ import annotations

from dataclasses import asdict
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import traceback
from typing import Any, Mapping

import numpy as np
import pandas as pd

from dayahead.v35.contracts import PHASE_CALIBRATION
from dayahead.v35.execution import MESS_INITIAL, daily_traffic_authority
from dayahead.v36 import runner as v36_runner
from dayahead.v36.storage import CASE_FILES, file_sha

from .aidc import build_day
from .context import load_day_context
from .contracts import (
    ARTIFACT_ROOT, BEAM_PROGRESS_BASE, BEAM_WIDTH, BEAM_WIDTH_FALLBACK,
    CACHE_ROOT, DATE_RESULT_ROOT, DEFAULT_K, FIREWALL, K_FALLBACK,
    MAX_WORKERS_PER_DATE, MESS_HEAD, MESS_ORDER,
    OFFICIAL_CASES, PASS_ID, PHASE, PROGRESS_AFTER_CASE, RAW_ROOT,
    SEED_WIDTH, SOURCE_DATA_REPOSITORY, STATUS_ROOT,
)
from .execution_acceleration import (
    COMPATIBILITY_VERSION, canonical_sha256, file_sha256,
)
from .status import atomic_json, read_json, write_status
from dayahead.v37r3.voltage_authority import (
    APPLICABILITY_RELATIVE_PATH,
    AUTHORITY_RELATIVE_PATH,
    joint_repaired_coefficients,
)


ADMISSION = {"status": "PASS", "May_numeric_reads_before_admission": 0}

_LOCAL_FALLBACK_SIGNATURES = (
    "V35R3_FIXED_CANDIDATE_STATUS",
    "V35R3_FIXED_CERTIFICATE_STALLED",
    "V35R3_FIXED_CERTIFICATE_ROUND_LIMIT",
    "V35R3E_R1_TOPK_ID_CONSERVATION",
    "V35R3E_R1_RESTRICTED_COUNT",
    "V35R3E_R1_NO_FEASIBLE_SEED",
)

_FINGERPRINT_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


def _candidate_table_sha(repo: Path, day: str) -> str:
    import dayahead.v35r3.algorithm as r3

    _bundle, _graph, route_table, _files = daily_traffic_authority(
        repo, repo / CACHE_ROOT / "traffic", PHASE, day, ADMISSION,
    )
    original_guard = r3.assert_apr01_only

    def may_only(target: str) -> None:
        if not str(target).startswith("2025-05-"):
            raise PermissionError(f"V37_DATE_OUT_OF_SCOPE:{target}")

    try:
        r3.assert_apr01_only = may_only
        payload = {
            mess_id: [
                asdict(candidate)
                for candidate in r3.enumerate_initial_relocations(
                    day=day, mess_id=mess_id,
                    initial_service=MESS_INITIAL[mess_id], route_table=route_table,
                ).candidates
            ]
            for mess_id in MESS_ORDER
        }
    finally:
        r3.assert_apr01_only = original_guard
    return canonical_sha256(payload)


def case_execution_fingerprint(
    repo: Path, day: str, case: str, aidc: Any,
) -> dict[str, Any]:
    """Fingerprint every science/config input that permits exact case reuse."""

    authority_path = repo / AUTHORITY_RELATIVE_PATH
    applicability_path = repo / APPLICABILITY_RELATIVE_PATH
    aidc_contract_path = repo / "dayahead/v37/aidc.py"
    aidc_sha = canonical_sha256({
        "contract_sha256": str(aidc.contract_sha256),
        "P_sha256": hashlib.sha256(np.asarray(aidc.pcc_p_kw, dtype=float).tobytes()).hexdigest(),
        "Q_sha256": hashlib.sha256(np.asarray(aidc.pcc_q_kvar, dtype=float).tobytes()).hexdigest(),
    })
    voltage_path = (
        repo / CACHE_ROOT / "electrical" / day / "data"
        / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    )
    current_path = (
        repo / CACHE_ROOT / "electrical" / day / "data"
        / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
    )
    cut_contract_path = (
        repo / "dayahead/artifacts/v17_candidate/"
        "V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1.json"
    )
    cut_implementation_path = repo / "dayahead/v37r3/restoration.py"
    cut_fingerprint = canonical_sha256({
        "contract": file_sha(cut_contract_path),
        "implementation": file_sha256(cut_implementation_path),
    })
    cache_key = (day, case, canonical_sha256({
        "joint_authority": file_sha(authority_path),
        "may_applicability": file_sha(applicability_path),
        "aidc_cohort_contract": file_sha256(aidc_contract_path),
        "voltage_anchor": file_sha(voltage_path),
        "current_anchor": file_sha(current_path),
        "cut": cut_fingerprint,
    }))
    cached = _FINGERPRINT_CACHE.get(cache_key)
    if cached is not None and cached["AIDC_authority_sha256"] == aidc_sha:
        return dict(cached)
    identity = {
        "infrastructure_compatibility_version": COMPATIBILITY_VERSION,
        "operating_day": day,
        "case": case,
        "voltage_authority_sha256": file_sha(authority_path),
        "voltage_applicability_sha256": file_sha(applicability_path),
        "restoration_cut_contract_sha256": file_sha(cut_contract_path),
        "restoration_cut_implementation_sha256": file_sha256(cut_implementation_path),
        "restoration_cut_fingerprint_sha256": cut_fingerprint,
        "AIDC_authority_sha256": aidc_sha,
        "AIDC_cohort_contract_sha256": file_sha256(aidc_contract_path),
        "MESS_authority_sha256": MESS_HEAD,
        "K": DEFAULT_K,
        "K_fallback": list(K_FALLBACK),
        "beam": BEAM_WIDTH,
        "beam_fallback": BEAM_WIDTH_FALLBACK,
        "seed": SEED_WIDTH,
        "WorkLimit": 60.0,
        "candidate_table_SHA": _candidate_table_sha(repo, day),
        "network_context_SHA": canonical_sha256({
            "voltage": file_sha(voltage_path), "current": file_sha(current_path),
        }),
        "execution_code_SHA": canonical_sha256({
            relative: file_sha256(repo / relative)
            for relative in (
                "dayahead/v37/runner.py",
                "dayahead/v37/aidc.py",
                "dayahead/v37/execution_acceleration.py",
                "dayahead/v37/voltage_fidelity.py",
                "dayahead/tools/run_v35r3e_r1_beam.py",
                "dayahead/v35r3/algorithm.py",
                "dayahead/v34/integrated_mess.py",
                "dayahead/v37r3/voltage_authority.py",
                "dayahead/v37r3/restoration.py",
            )
        }),
        "solver_relevant_configuration": {
            "restricted": {
                "Threads": 1, "Seed": 20260828,
                "FeasibilityTol": 1.0e-8, "OptimalityTol": 1.0e-8,
                "numeric_retry_NumericFocus": 3,
                "numeric_retry_OptimalityTol": 1.0e-8,
            },
            "full": {
                "Threads": 4, "Seed": 20260828, "MIPGap": 1.0e-3,
                "FeasibilityTol": 1.0e-6, "OptimalityTol": 1.0e-6,
                "TimeLimit": 600.0, "WorkLimit": 60.0,
                "WorkLimit_tiers": [60.0, 180.0, 300.0], "MIPFocus": 1,
                "SoftMemLimit": 8.0, "NodefileStart": 1.0,
            },
        },
    }
    result = {
        **identity,
        "execution_fingerprint_sha256": canonical_sha256(identity),
    }
    _FINGERPRINT_CACHE[cache_key] = dict(result)
    return result


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


def _uncertified_rows(values: pd.DataFrame) -> list[dict[str, Any]]:
    if not len(values) or "exact_optimality_certificate" not in values:
        return []
    failed = values.loc[
        values["exact_optimality_certificate"].astype(str).str.startswith("V37_FAIL_CLOSED:")
    ]
    return failed.to_dict("records")


def _archived_k_attempt(search_root: Path, label: str) -> dict[str, Any] | None:
    archived = list(search_root.glob(f"RESTRICTED_VALUES.K{label}.ATTEMPT*.csv"))
    if not archived:
        return None
    path = max(archived, key=lambda item: (item.stat().st_mtime_ns, item.name))
    values = pd.read_csv(path)
    failure_rows = _uncertified_rows(values)
    if not failure_rows:
        return None
    return {
        "K": label,
        "status": "CERTIFICATION_FAILURE_RESTORED",
        "restricted_candidates": int(len(values)),
        "uncertified_candidate_count": len(failure_rows),
        "uncertified_candidate_ids": [str(row["candidate_id"]) for row in failure_rows],
        "signatures": [str(row["exact_optimality_certificate"]) for row in failure_rows],
        "restored_from": str(path),
        "restricted_solver_calls": 0,
        "restricted_cache_hits": int(len(values)),
        "restricted_cache_misses": 0,
        "restricted_duplicate_solves": 0,
    }


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
            restored = _archived_k_attempt(search_root, label)
            if restored is not None and index < len(levels) - 1:
                attempts.append(restored)
                continue
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
            failure_rows = _uncertified_rows(values)
            attempt = {
                "K": label,
                "status": "CERTIFIED" if not failure_rows else "CERTIFICATION_FAILURE",
                "restricted_candidates": int(len(values)),
                "uncertified_candidate_count": len(failure_rows),
                "uncertified_candidate_ids": [str(row["candidate_id"]) for row in failure_rows],
                "signatures": [str(row["exact_optimality_certificate"]) for row in failure_rows],
                "restricted_solver_calls": int(summary.get("restricted_solver_calls", 0)),
                "restricted_cache_hits": int(summary.get("restricted_cache_hits", 0)),
                "restricted_cache_misses": int(summary.get("restricted_cache_misses", 0)),
                "restricted_duplicate_solves": int(summary.get("restricted_duplicate_solves", 0)),
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
                "restricted_solver_calls_current_attempt": int(
                    summary.get("restricted_solver_calls", 0)
                ),
                "restricted_solver_calls": sum(
                    int(row.get("restricted_solver_calls", 0)) for row in attempts
                ),
                "restricted_cache_hits": sum(
                    int(row.get("restricted_cache_hits", 0)) for row in attempts
                ),
                "restricted_cache_misses": sum(
                    int(row.get("restricted_cache_misses", 0)) for row in attempts
                ),
                "restricted_duplicate_solves": sum(
                    int(row.get("restricted_duplicate_solves", 0)) for row in attempts
                ),
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
        "MESS_voltage_fidelity_authority": repo / AUTHORITY_RELATIVE_PATH,
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


def _beam_root(
    repo: Path, execution_fingerprint_sha256: str, day: str, case: str,
    width: int,
) -> Path:
    return (
        repo / CACHE_ROOT / PASS_ID / "beam"
        / execution_fingerprint_sha256 / day / case / f"B{width}"
    )


def _beam_case(
    repo: Path, day: str, case: str, aidc_b0: Any, aidc_b1: Any,
    execution_fingerprint: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    import dayahead.tools.run_v35r3e_r1_beam as frozen
    import dayahead.v35r3.algorithm as r3
    import dayahead.v35r3e.algorithm as r3e

    data, electrical = load_day_context(repo, day)
    coefficients = joint_repaired_coefficients(repo, electrical)
    selected = aidc_b0 if case == "B2" else aidc_b1
    execution_fingerprint = dict(
        execution_fingerprint
        or case_execution_fingerprint(repo, day, case, selected)
    )
    fingerprint_sha = str(execution_fingerprint["execution_fingerprint_sha256"])
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
        "slot_coefficients": frozen.slot_coefficients,
        "execution_cache_context": frozen.EXECUTION_CACHE_CONTEXT,
        "progress_callback": frozen.PROGRESS_CALLBACK,
    }

    def selected_day(value: str) -> None:
        if not str(value).startswith("2025-05-"):
            raise PermissionError(f"V37_DATE_OUT_OF_SCOPE:{value}")

    frozen.APR01 = day
    # Every stage, local-search file and full-child checkpoint lives below the
    # exact case fingerprint.  A later voltage-authority SHA therefore cannot
    # restore an older stage before the individual cache checks even run.
    frozen.CACHE_ROOT = CACHE_ROOT / PASS_ID / "beam" / fingerprint_sha
    frozen.prepare_aidc_stages = lambda *_args, **_kwargs: (
        data, electrical,
        {"B0": {"planning_pcc_power_kw": aidc_b0.pcc_p_kw},
         "B1": {"planning_pcc_power_kw": aidc_b1.pcc_p_kw}},
    )
    # The frozen beam driver normally reconstructs the legacy coefficient
    # tuple internally.  Bind that factory to the already SHA-verified R2
    # tuple so restricted children and their full-MILP certificates consume
    # the same repaired direct-affine rows as final production reporting.
    frozen.slot_coefficients = (
        lambda _legacy, _voltage, _current, slot: coefficients[int(slot)]
    )
    frozen.EXECUTION_CACHE_CONTEXT = {
        **execution_fingerprint,
        "candidate_cache_root": str(
            (repo / CACHE_ROOT / "p1_candidate_solve_cache").resolve()
        ),
    }
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
    last_progress_write = 0.0
    last_progress_key: tuple[object, ...] | None = None

    def beam_progress(payload: Mapping[str, object]) -> None:
        nonlocal last_progress_write, last_progress_key
        now = time.monotonic()
        event = str(payload.get("event", "MESS"))
        key = (
            event, payload.get("mess_index"), payload.get("parent_index"),
            payload.get("search_level"), payload.get("seed_done"),
            payload.get("full_milp_status"),
        )
        candidate_done = payload.get("candidate_done")
        candidate_total = payload.get("candidate_total")
        terminal_candidate_tick = (
            candidate_done is not None and candidate_done == candidate_total
        )
        if (
            key == last_progress_key and now - last_progress_write < 2.0
            and not terminal_candidate_tick
        ):
            return
        mess_index = int(payload.get("mess_index", 1))
        final_full = event == "FULL_MILP" and mess_index == 4
        units = BEAM_PROGRESS_BASE[case] + mess_index - 1 + int(final_full)
        stage = f"{case}_FINAL_FULL" if final_full else f"{case}_MESS{mess_index:02d}"
        write_status(
            _status_path(repo, day), day, "RUNNING", units, stage,
            extra={
                "case": case, "stage": stage, "mess_index": mess_index,
                "beam_parent_index": payload.get("parent_index"),
                "beam_parent_total": payload.get("parent_total"),
                "search_level": payload.get("search_level"),
                "candidate_done": candidate_done,
                "candidate_total": candidate_total,
                "candidate_new_done": payload.get("candidate_new_done"),
                "candidate_new_total": payload.get("candidate_new_total"),
                "seed_done": payload.get("seed_done"),
                "seed_total": payload.get("seed_total"),
                "full_milp_status": payload.get("full_milp_status"),
                "beam_fallback_width": width,
                "workers": MAX_WORKERS_PER_DATE,
            },
        )
        last_progress_write = now
        last_progress_key = key

    frozen.PROGRESS_CALLBACK = beam_progress
    frozen._local_search = lambda **kwargs: _run_local_with_frozen_k_fallback(
        frozen, original["local_search"], **kwargs,
    )
    try:
        last_error: Exception | None = None
        for width in (BEAM_WIDTH, BEAM_WIDTH_FALLBACK):
            final_path = _beam_root(repo, fingerprint_sha, day, case, width) / "FINAL_RESULT.json"
            if final_path.is_file():
                result = read_json(final_path)
                if result.get("execution_fingerprint_sha256") == fingerprint_sha:
                    k_count, full_count = _beam_k_fallback_counts(final_path.parent)
                    result["V37_K_fallback_count"] = k_count
                    result["V37_FULL_scan_count"] = full_count
                    result["reuse"] = {
                        "REUSED": "YES",
                        "source_artifact": str(final_path.resolve()),
                        "source_SHA": file_sha256(final_path),
                        "authority_SHA": execution_fingerprint["voltage_authority_sha256"],
                        "reason": "EXACT_BEAM_FINGERPRINT_MATCH",
                    }
                    return result, 0 if width == BEAM_WIDTH else 1
            try:
                os.chdir(repo)
                result = frozen._run_case(case, width, MAX_WORKERS_PER_DATE)
                result["execution_fingerprint_sha256"] = fingerprint_sha
                result["reuse"] = {
                    "REUSED": "NO", "source_artifact": None, "source_SHA": None,
                    "authority_SHA": execution_fingerprint["voltage_authority_sha256"],
                    "reason": "NO_EXACT_COMPLETED_BEAM_RESULT",
                }
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
        frozen.slot_coefficients = original["slot_coefficients"]
        frozen.EXECUTION_CACHE_CONTEXT = original["execution_cache_context"]
        frozen.PROGRESS_CALLBACK = original["progress_callback"]
        r3.assert_apr01_only, r3e.assert_apr01_only = original_guards
        electrical.voltage.close(); electrical.current.close()
        os.chdir(repo)


def _case_root(repo: Path, day: str, case: str) -> Path:
    return repo / RAW_ROOT / PASS_ID / day / case


def _checkpoint_path(repo: Path, day: str, case: str) -> Path:
    return repo / CACHE_ROOT / PASS_ID / "case_checkpoints" / day / f"{case}.json"


def _valid_case_checkpoint(
    repo: Path, day: str, case: str,
    execution_fingerprint: Mapping[str, Any],
) -> dict[str, Any] | None:
    path = _checkpoint_path(repo, day, case)
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
        if payload.get("status") != "PASS":
            return None
        expected_sha = str(execution_fingerprint["execution_fingerprint_sha256"])
        if payload.get("execution_fingerprint_sha256") != expected_sha:
            return None
        if payload.get("execution_fingerprint") != dict(execution_fingerprint):
            return None
        root = _case_root(repo, day, case)
        for item in payload["files"]:
            candidate = root / item["relative_path"]
            if (
                not candidate.is_file()
                or candidate.stat().st_size != item["bytes"]
                or file_sha256(candidate) != item["sha256"]
            ):
                return None
        result = dict(payload["result"])
        result["execution_fingerprint_sha256"] = expected_sha
        result["reuse"] = {
            "REUSED": "YES",
            "source_artifact": str(path.resolve()),
            "source_SHA": file_sha256(path),
            "authority_SHA": execution_fingerprint["voltage_authority_sha256"],
            "reason": "EXACT_CASE_FINGERPRINT_AND_FILE_HASH_MATCH",
        }
        return result
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _write_case_checkpoint(
    repo: Path, day: str, case: str, result: Mapping[str, Any],
    execution_fingerprint: Mapping[str, Any],
) -> None:
    root = _case_root(repo, day, case)
    files = [
        {
            "relative_path": relative,
            "bytes": (root / relative).stat().st_size,
            "sha256": file_sha256(root / relative),
        }
        for relative in CASE_FILES if (root / relative).is_file()
    ]
    if len(files) != len(CASE_FILES):
        raise RuntimeError(f"V37_CASE_ARTIFACT_INCOMPLETE:{day}:{case}:{len(files)}")
    atomic_json(_checkpoint_path(repo, day, case), {
        "artifact_id": "V37_CASE_CHECKPOINT_V2", "date": day, "case": case,
        "status": "PASS", "execution_fingerprint": dict(execution_fingerprint),
        "execution_fingerprint_sha256": execution_fingerprint["execution_fingerprint_sha256"],
        "files": files, "result": dict(result),
    })


def _watch_beam(
    repo: Path, day: str, case: str, execution_fingerprint_sha256: str,
    stop: threading.Event,
) -> None:
    base = BEAM_PROGRESS_BASE[case]
    path = _status_path(repo, day)
    while not stop.wait(2.0):
        completed = 0
        current_width = BEAM_WIDTH
        for width in (BEAM_WIDTH, BEAM_WIDTH_FALLBACK):
            root = _beam_root(
                repo, execution_fingerprint_sha256, day, case, width,
            )
            count = sum((root / f"STAGE_{index}.json").is_file() for index in range(1, 5))
            if count >= completed:
                completed, current_width = count, width
        stage = min(4, completed + 1)
        try:
            write_status(
                path, day, "RUNNING", base + completed,
                f"{case}_MESS{stage:02d}" if completed < 4 else f"{case}_FRESH",
                extra={"workers": MAX_WORKERS_PER_DATE, "beam_width_active": current_width},
            )
        except PermissionError:
            # RUNNING telemetry is best-effort; the next two-second tick retries.
            continue


def _run_frozen_case_once(
    repo: Path,
    day: str,
    case: str,
    aidc: Any,
    beam: Mapping[str, Any] | None,
    *,
    restoration_round: int | None = None,
    restoration_new_cuts: int | None = None,
    restoration_total_cuts: int | None = None,
) -> dict[str, Any]:
    original_context = v36_runner.load_day_context
    original_cache = v36_runner.CACHE_ROOT
    original_input = v36_runner._input_authority
    original_coefficients = v36_runner._coefficients
    original_fresh_progress = v36_runner.FRESH_PROGRESS_CALLBACK
    v36_runner.load_day_context = lambda target: load_day_context(repo, target)
    v36_runner.CACHE_ROOT = CACHE_ROOT
    v36_runner._input_authority = _input_authority
    v36_runner._coefficients = lambda electrical: joint_repaired_coefficients(repo, electrical)
    fresh_units = {"B0": 1, "B1": 3, "B2": 8, "B3": 13}[case]

    def fresh_progress(payload: Mapping[str, object]) -> None:
        fresh_done = int(payload.get("OpenDSS_slot", 0))
        fresh_total = int(payload.get("OpenDSS_slots_total", 96))
        if fresh_done != fresh_total and fresh_done % 8 != 0:
            return
        stage = f"{case}_RESTORATION" if restoration_round is not None else f"{case}_FRESH"
        write_status(
            _status_path(repo, day), day, "RUNNING", fresh_units, stage,
            extra={
                "case": case, "stage": stage,
                "restoration_round": restoration_round,
                "restoration_round_max": 5,
                "restoration_new_cuts": restoration_new_cuts,
                "restoration_total_cuts": restoration_total_cuts,
                "fresh_slots_done": fresh_done,
                "fresh_slots_total": fresh_total,
            },
        )

    v36_runner.FRESH_PROGRESS_CALLBACK = fresh_progress
    try:
        os.chdir(repo)
        return v36_runner.run_case(repo, PASS_ID, day, case, aidc, beam)
    finally:
        v36_runner.load_day_context = original_context
        v36_runner.CACHE_ROOT = original_cache
        v36_runner._input_authority = original_input
        v36_runner._coefficients = original_coefficients
        v36_runner.FRESH_PROGRESS_CALLBACK = original_fresh_progress
        os.chdir(repo)


def _run_frozen_case(
    repo: Path,
    day: str,
    case: str,
    aidc: Any,
    beam: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Run normal Planning/Fresh once, then the frozen V17 restoration loop."""

    if case not in {"B2", "B3"} or beam is None:
        return _run_frozen_case_once(repo, day, case, aidc, beam)

    from dayahead.tools.run_v35r3e_r1_beam import _restore_slots, _service_mapping
    from dayahead.v17_ac_restoration_contract import K_MAX, ViolationType
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v36.storage import write_json, write_parquet
    from dayahead.v37r3.restoration import (
        extract_ac_violations,
        frozen_trajectory,
        load_fresh_result,
        local_fresh_ac_restoration_cuts,
        restoration_cut_from_payload,
        solve_fixed_discrete_recourse,
    )

    artifact_root = repo / "dayahead/artifacts/v37_r3_restore_intended_cuts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    fresh_root = repo / CACHE_ROOT / PASS_ID / "fresh" / day / case
    current_beam = copy.deepcopy(dict(beam))
    initial_beam_sha = canonical_sha256(dict(beam))
    resume_root = (
        repo / CACHE_ROOT / PASS_ID / "restoration"
        / initial_beam_sha / day / case
    )
    resume_root.mkdir(parents=True, exist_ok=True)
    resume_payload: dict[str, Any] | None = None
    for round_path in sorted(resume_root.glob("ROUND_*.json"), reverse=True):
        try:
            candidate = read_json(round_path)
            if (
                candidate.get("status") == "FRESH_COMPLETE"
                and candidate.get("initial_beam_sha256") == initial_beam_sha
                and all(
                    (repo / item["relative_path"]).is_file()
                    and file_sha256(repo / item["relative_path"]) == item["sha256"]
                    for item in candidate.get("case_files", [])
                )
            ):
                resume_payload = candidate
                break
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue

    if resume_payload is None:
        current_result = _run_frozen_case_once(repo, day, case, aidc, beam)
        current_trajectory = v36_runner._trajectory(current_beam)
        accumulated = []
        arithmetic_rows: list[dict[str, Any]] = []
        runtime_rows: list[dict[str, Any]] = []
        first_iteration = 1
    else:
        current_result = dict(resume_payload["result"])
        current_trajectory = MessTrajectory(tuple(
            _restore_slots(resume_payload["trajectory_slots"])
        ))
        current_beam["trajectory_slots"] = [
            row.to_dict() for row in current_trajectory.slots
        ]
        accumulated = [
            restoration_cut_from_payload(row) for row in resume_payload["cuts"]
        ]
        arithmetic_rows = list(resume_payload.get("arithmetic_rows", []))
        runtime_rows = list(resume_payload.get("runtime_rows", []))
        first_iteration = int(resume_payload["restoration_round"]) + 1
    margin_authority_path = (
        repo / "dayahead/artifacts/v17_candidate/V17_AC_RESTORATION_CUT_VALIDATION.json"
    )
    margin_authority = read_json(margin_authority_path)
    restoration_margins = dict(margin_authority["margins"])
    _bundle, _graph, route_table, _files = daily_traffic_authority(
        repo, repo / CACHE_ROOT / "traffic", PHASE, day, ADMISSION,
    )
    service_mapping = _service_mapping()
    beam_reruns = 0
    restricted_solves = 0
    final_status = "PASS_WITHOUT_RESTORATION"

    for iteration in range(first_iteration, K_MAX + 1):
        fresh = load_fresh_result(fresh_root)
        summary = fresh.summary
        violations = extract_ac_violations(fresh)
        if not bool(summary["physical_violation"]):
            final_status = "PASS" if accumulated else "PASS_WITHOUT_RESTORATION"
            break
        if not violations:
            raise RuntimeError(f"V37_R3_FRESH_PHYSICAL_VIOLATION_NOT_EXTRACTED:{day}:{case}")

        electrical_started = time.perf_counter()
        write_status(
            _status_path(repo, day), day, "RUNNING",
            {"B2": 8, "B3": 13}[case], f"{case}_RESTORATION",
            extra={
                "case": case, "stage": f"{case}_RESTORATION",
                "restoration_round": iteration,
                "restoration_round_max": K_MAX,
                "restoration_new_cuts": len(violations),
                "restoration_total_cuts": len(accumulated) + len(violations),
                "full_milp_status": "P_Q_FULL_MILP_RUNNING",
            },
        )
        _data, electrical = load_day_context(repo, day)
        try:
            frozen = frozen_trajectory(
                day, case, aidc, current_trajectory, round_index=iteration - 1,
            )
            frozen = frozen.__class__(
                frozen.day, frozen.namespace, frozen.case,
                frozen.pcc_p_kw, frozen.pcc_q_kvar,
                frozen.mess_p_kw, frozen.mess_q_kvar,
                frozen.mess_ids, frozen.mess_locations_96x4,
                fresh.schedule_sha256,
            )
            generated, derivative_audit = local_fresh_ac_restoration_cuts(
                source_repo=SOURCE_DATA_REPOSITORY,
                electrical=electrical,
                voltage=electrical.voltage,
                frozen=frozen,
                fresh=fresh,
                violations=violations,
                iteration_index=iteration,
                margins=restoration_margins,
            )
            if not generated:
                raise RuntimeError("V37_R3_FRESH_VIOLATION_GENERATED_ZERO_CUTS")
            accumulated.extend(generated)
            full_started = time.perf_counter()
            full = solve_fixed_discrete_recourse(
                repo=repo,
                case=case,
                aidc=aidc,
                electrical=electrical,
                route_table=route_table,
                service_to_pcc=service_mapping,
                selected_trajectory=current_trajectory,
                restoration_cuts=tuple(accumulated),
            )
            full_wallclock = time.perf_counter() - full_started
        finally:
            electrical.voltage.close()
            electrical.current.close()

        for row in full.restoration_cut_arithmetic:
            arithmetic_rows.append({
                "operating_day": day,
                "case": case,
                "restoration_round": iteration,
                **dict(row),
            })
        runtime_rows.append({
            "operating_day": day,
            "case": case,
            "restoration_round": iteration,
            "triggered_AC_violation_count": len(violations),
            "triggered_violation_counts": {
                violation_type.value: sum(
                    row.violation_type == violation_type for row in violations
                )
                for violation_type in ViolationType
                if any(row.violation_type == violation_type for row in violations)
            },
            "new_cut_count": len(generated),
            "cumulative_cut_count": len(accumulated),
            "trust_region_constraint_count": full.restoration_trust_region_constraint_count,
            "Fresh_finite_difference_solve_count": derivative_audit[
                "Fresh_finite_difference_solve_count"
            ],
            "maximum_anchor_reproduction_error_pu": derivative_audit[
                "maximum_anchor_reproduction_error_pu"
            ],
            "full_MILP_wallclock_seconds": full_wallclock,
            "full_MILP_solver_seconds": full.solve_seconds,
            "full_MILP_status": full.solver_status,
            "restricted_solver_calls": 0,
            "beam_reruns": 0,
            "round_context_wallclock_seconds": time.perf_counter() - electrical_started,
        })
        current_trajectory = full.trajectory
        current_beam["trajectory_slots"] = [
            row.to_dict() for row in current_trajectory.slots
        ]
        current_beam["trajectory_sha256"] = current_trajectory.canonical_sha256
        selected_state = dict(current_beam["selected_state"])
        selected_state["solver_objective"] = float(full.objective)
        selected_state["current_planning_objective"] = float(full.objective)
        selected_state["trajectory_slots"] = current_beam["trajectory_slots"]
        selected_state["restoration_cut_count"] = len(accumulated)
        selected_state["restoration_round"] = iteration
        current_beam["selected_state"] = selected_state

        current_result = _run_frozen_case_once(
            repo, day, case, aidc, current_beam,
            restoration_round=iteration,
            restoration_new_cuts=len(generated),
            restoration_total_cuts=len(accumulated),
        )
        post = load_fresh_result(fresh_root)
        runtime_rows[-1].update({
            "Fresh_revalidation_wallclock_seconds": float(post.elapsed_seconds),
            "post_Fresh_Vmin_pu": float(post.summary["Vmin_pu"]),
            "post_Fresh_Vmax_pu": float(post.summary["Vmax_pu"]),
            "post_Fresh_voltage_violation_count": int(
                post.summary["voltage_violation_count"]
            ),
            "post_Fresh_line_current_violation_count": int(
                post.summary["line_current_violation_count"]
            ),
            "post_Fresh_transformer_current_violation_count": int(
                post.summary["transformer_current_violation_count"]
            ),
            "post_Fresh_transformer_kva_violation_count": int(
                post.summary["transformer_kva_violation_count"]
            ),
            "post_Fresh_physical_violation": bool(post.summary["physical_violation"]),
        })
        case_files = [
            {
                "relative_path": str(path.relative_to(repo)).replace("\\", "/"),
                "sha256": file_sha256(path),
            }
            for relative in CASE_FILES
            for path in (_case_root(repo, day, case) / relative,)
            if path.is_file()
        ]
        if len(case_files) != len(CASE_FILES):
            raise RuntimeError("V37_R3_RESTORATION_ROUND_CASE_FILES_INCOMPLETE")
        atomic_json(resume_root / f"ROUND_{iteration:02d}.json", {
            "artifact_id": "V37_R3_RESTORATION_ROUND_CHECKPOINT_V1",
            "status": "FRESH_COMPLETE",
            "operating_day": day,
            "case": case,
            "initial_beam_sha256": initial_beam_sha,
            "restoration_round": iteration,
            "cuts": [cut.payload() for cut in accumulated],
            "trajectory_slots": [row.to_dict() for row in current_trajectory.slots],
            "arithmetic_rows": arithmetic_rows,
            "runtime_rows": runtime_rows,
            "result": current_result,
            "case_files": case_files,
            "Fresh_schedule_sha256": post.schedule_sha256,
        })
    else:
        final_status = "FAIL_CLOSED_MAX_RESTORATION_ROUNDS"

    final_fresh = load_fresh_result(fresh_root)
    if bool(final_fresh.summary["physical_violation"]):
        final_status = "FAIL_CLOSED_MAX_RESTORATION_ROUNDS"
    elif accumulated:
        final_status = "PASS"

    existing_arithmetic = artifact_root / "V37_R3_CUT_ARITHMETIC_AUDIT.parquet"
    arithmetic = pd.DataFrame(arithmetic_rows)
    if existing_arithmetic.is_file():
        prior = pd.read_parquet(existing_arithmetic)
        prior = prior.loc[
            ~((prior["operating_day"] == day) & (prior["case"] == case))
        ]
        arithmetic = pd.concat((prior, arithmetic), ignore_index=True)
    if len(arithmetic):
        write_parquet(existing_arithmetic, arithmetic)

    runtime_path = artifact_root / "V37_R3_CUT_RUNTIME_AUDIT.json"
    runtime = read_json(runtime_path) if runtime_path.is_file() else {
        "artifact_id": "V37_R3_CUT_RUNTIME_AUDIT_V1", "cases": {},
    }
    runtime["cases"][f"{day}:{case}"] = {
        "status": final_status,
        "rounds": runtime_rows,
        "restoration_round_count": len(runtime_rows),
        "cut_count": len(accumulated),
        "restricted_solver_calls": restricted_solves,
        "beam_reruns_after_Fresh_violation": beam_reruns,
        "initial_beam_result_sha256": initial_beam_sha,
        "final_beam_discrete_source_sha256": initial_beam_sha,
        "K_MAX": K_MAX,
        "rho": 0.10,
    }
    write_json(runtime_path, runtime)
    write_json(
        artifact_root / f"V37_R3_{day}_{case}_RESTORATION_CUTS.json",
        {
            "artifact_id": "V37_R3_CASE_RESTORATION_CUTS_V1",
            "operating_day": day,
            "case": case,
            "status": final_status,
            "cuts": [cut.payload() for cut in accumulated],
        },
    )
    current_result["restoration"] = runtime["cases"][f"{day}:{case}"]
    if final_status.startswith("FAIL_CLOSED"):
        raise RuntimeError(f"V37_R3_{final_status}:{day}:{case}")
    return current_result


def _case_metrics(repo: Path, day: str, case: str, result: Mapping[str, Any]) -> dict[str, Any]:
    root = _case_root(repo, day, case)
    objective = read_json(root / "summary/OBJECTIVE.json")
    gates = read_json(root / "summary/PHYSICAL_GATES.json")
    compute = read_json(root / "summary/COMPUTE_SUMMARY.json")
    provenance = read_json(root / "inputs/RUN_PROVENANCE.json")
    moves = pd.read_parquet(root / "mess/MESS_MOVE_EVENTS.parquet")
    solvers = pd.read_parquet(root / "solver/SOLVER_RUNS.parquet")
    planning, fresh = gates["Planning"], gates["Fresh"]
    fingerprint_sha = str(result.get("execution_fingerprint_sha256", ""))
    beam_path = _beam_root(repo, fingerprint_sha, day, case, BEAM_WIDTH) / "FINAL_RESULT.json"
    if not beam_path.is_file() and case in {"B2", "B3"}:
        beam_path = _beam_root(
            repo, fingerprint_sha, day, case, BEAM_WIDTH_FALLBACK,
        ) / "FINAL_RESULT.json"
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
        "execution_fingerprint_sha256": fingerprint_sha,
        "reuse": dict(result.get("reuse", {})),
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
    readiness = read_json(
        repo
        / "dayahead/artifacts/v37_r3_restore_intended_cuts/"
        "V37_MAY_FINAL_RUN_READINESS.json"
    )
    payload = {
        "artifact_id": "V37_MAY_DATE_RESULT_V1", "date": day,
        "status": "PASS" if fresh_pass and physical_pass else "FAIL",
        "cases": cases, "effects": effects,
        "Fresh_96_of_96_PASS": fresh_pass, "physical_gates_PASS": physical_pass,
        "workers": MAX_WORKERS_PER_DATE, "wallclock_seconds": elapsed,
        "final_implementation_fingerprint_sha256": readiness[
            "final_implementation_fingerprint_sha256"
        ],
        "firewall": FIREWALL,
    }
    atomic_json(repo / DATE_RESULT_ROOT / f"{day}.json", payload)
    return payload


def run_day(repo: Path, day: str) -> dict[str, Any]:
    started = time.perf_counter()
    status_path = _status_path(repo, day)
    result_path = repo / DATE_RESULT_ROOT / f"{day}.json"
    write_status(status_path, day, "RUNNING", 0, "B0_PLANNING", extra={"workers": MAX_WORKERS_PER_DATE})
    try:
        aidc = {
            "B0": build_day(repo, day, "B0"), "B1": build_day(repo, day, "B1"),
        }
        aidc["B2"], aidc["B3"] = aidc["B0"], aidc["B1"]
        fingerprints = {
            case: case_execution_fingerprint(repo, day, case, aidc[case])
            for case in OFFICIAL_CASES
        }
        results: dict[str, dict[str, Any]] = {}
        for case in OFFICIAL_CASES:
            fingerprint = fingerprints[case]
            cached = _valid_case_checkpoint(repo, day, case, fingerprint)
            if cached is not None:
                results[case] = cached
                write_status(status_path, day, "RUNNING", PROGRESS_AFTER_CASE[case], f"{case}_RESTORED")
                continue
            beam = None
            fallback = 0
            if case in {"B2", "B3"}:
                stop = threading.Event()
                watcher = threading.Thread(
                    target=_watch_beam,
                    args=(
                        repo, day, case,
                        str(fingerprint["execution_fingerprint_sha256"]), stop,
                    ),
                    daemon=True,
                )
                watcher.start()
                try:
                    beam, fallback = _beam_case(
                        repo, day, case, aidc["B0"], aidc["B1"], fingerprint,
                    )
                finally:
                    stop.set(); watcher.join(timeout=5)
                write_status(status_path, day, "RUNNING", BEAM_PROGRESS_BASE[case] + 4, f"{case}_FRESH")
            result = _run_frozen_case(repo, day, case, aidc[case], beam)
            result["beam_fallback"] = bool(fallback)
            result["K_fallback"] = bool(
                beam is not None and int(beam.get("V37_K_fallback_count", 0)) > 0
            )
            result["execution_fingerprint_sha256"] = fingerprint["execution_fingerprint_sha256"]
            result["reuse"] = {
                "REUSED": "NO", "source_artifact": None, "source_SHA": None,
                "authority_SHA": fingerprint["voltage_authority_sha256"],
                "reason": "NO_EXACT_COMPLETED_CASE_CHECKPOINT",
            }
            _write_case_checkpoint(repo, day, case, result, fingerprint)
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
        atomic_json(result_path, failure)
        current = read_json(status_path) if status_path.is_file() else {"completed_units": 0}
        write_status(status_path, day, "FAIL", int(current.get("completed_units", 0)), None,
                     error=failure["error"], extra={"result_path": str((repo / DATE_RESULT_ROOT / f"{day}.json").resolve())})
        raise
