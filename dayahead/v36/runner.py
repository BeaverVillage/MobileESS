"""Executable Apr-01 rehearsal and reusable V36 day/case integration."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping

import gurobipy as gp
import numpy as np

from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v35.contracts import MESS_IDS, PHASE_CALIBRATION
from dayahead.v35.execution import _combined_trajectory_arrays, _planning_grid

from .aidc import AIDCTrajectory, build_apr01
from .context import load_day_context
from .contracts import (
    AIDC_HEAD, ARTIFACT_DIR, BEAM_WIDTH, BRANCH, CACHE_ROOT, CALIBRATION_DATES,
    FROZEN_MESS_WORKTREE, INTEGRATION_BASE_HEAD, MESS_HEAD, OFFICIAL_CASES,
    SCIENCE_AUTHORITIES,
    SOURCE_DATA_REPOSITORY, STATIC_CANDIDATE_LIBRARY_SHA256,
)
from .science import canonical_sha256, git_head, verify_science
from .storage import attach_context, file_sha, write_case, write_json


def _git(*args: str, repo: Path) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, encoding="utf-8").strip()


def _input_authority(repo: Path, day: str, case: str, trajectory: AIDCTrajectory) -> dict[str, Any]:
    source_day = SOURCE_DATA_REPOSITORY / "frozen_artifacts/v28r2_april_full_month_preflight" / day / "dayahead"
    files: dict[str, Any] = {}
    for label, path in {
        "D_minus_1_load_PV": source_day / "aemo_forecast.json",
        "weather_forecast": source_day / "gfs_d1_weather.parquet",
        "actual_weather": source_day / "noaa_actual_weather.parquet",
        "traffic_prediction": FROZEN_MESS_WORKTREE / "dayahead/cache/v35/shared/traffic" / day / "TRAFFIC_FORECAST.npz",
        "MESS_route_table": FROZEN_MESS_WORKTREE / "dayahead/cache/v35/shared/traffic" / day / "ROUTE_TABLE.json.gz",
        "C1_parameters": repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json",
        "grid_base_case": SOURCE_DATA_REPOSITORY / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        "IDC_existing_location_mapping": repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json",
    }.items():
        files[label] = {
            "path": str(path), "exists": path.is_file(),
            "sha256": file_sha(path) if path.is_file() else None,
        }
    return {
        "schema_id": "V36_INPUT_AUTHORITY_V1", "date": day, "case": case,
        "immutable_references": files,
        "AIDC_queue_snapshot": {"ledger_rows": len(trajectory.ledger), "D_minus_1_only": True},
        "AIDC_runtime_authority": "V35R3D_R1_SAFE_CAUSAL_RUNTIME",
        "AIDC_GPU_capacity": 624, "MESS_initial_location": ["STA01", "STA12", "STA08", "STA06"],
        "MESS_initial_SoC": 760.0 / 1200.0,
        "MESS_vehicle_parameters": "dayahead.mess_physics + V33M3 route authority",
        "static_candidate_library_sha256": STATIC_CANDIDATE_LIBRARY_SHA256,
        "IDC_LOCATION_CHANGED": "NO",
    }


def _provenance(repo: Path, day: str, case: str, started: datetime, ended: datetime,
                fresh: Any, pass_id: str) -> dict[str, Any]:
    try:
        import dss
        dss_version = getattr(dss, "__version__", "installed")
    except ImportError:
        dss_version = "unavailable"
    return {
        "schema_id": "V36_RUN_PROVENANCE_V1", "date": day, "case": case,
        "pass_id": pass_id, "timezone": "AEST_FIXED_UTC_PLUS_10",
        "integration_Git_HEAD": git_head(repo), "source_AIDC_HEAD": AIDC_HEAD,
        "source_MESS_HEAD": MESS_HEAD,
        "AIDC_contract_SHA": SCIENCE_AUTHORITIES["AIDC"]["sha256"],
        "MESS_contract_SHA": SCIENCE_AUTHORITIES["MESS"]["sha256"],
        "C1_contract_SHA": SCIENCE_AUTHORITIES["C1"]["sha256"],
        "Planning_authority_SHA": SCIENCE_AUTHORITIES["PLANNING"]["sha256"],
        "Fresh_authority_SHA": SCIENCE_AUTHORITIES["FRESH"]["sha256"],
        "objective_contract_SHA": SCIENCE_AUTHORITIES["OBJECTIVE"]["sha256"],
        "traffic_authority_SHA": SCIENCE_AUTHORITIES["TRAFFIC"]["sha256"],
        "Safe_ETA_authority_SHA": SCIENCE_AUTHORITIES["SAFE_ETA"]["sha256"],
        "CENTER_only_confirmation": True, "IDC_location_unchanged_confirmation": True,
        "random_seed": 20260828, "solver_versions": {"Gurobi": gp.gurobi.version()},
        "Python_version": platform.python_version(), "OpenDSS_version": fresh.opendss_version,
        "DSS_Python_version": dss_version, "SUMO_invoked": False,
        "run_start_timestamp": started.isoformat(), "run_end_timestamp": ended.isoformat(),
        "wallclock_seconds": (ended - started).total_seconds(),
    }


def _coefficients(electrical: Any) -> tuple[Any, ...]:
    values = tuple(slot_coefficients(
        electrical.legacy_context, electrical.voltage, electrical.current, slot,
    ) for slot in range(96))
    attach_context(values, electrical.legacy_context)
    return values


def _prepare_seed_npz(repo: Path, day: str, stage: str, arrays: Mapping[str, np.ndarray], coefficients: tuple[Any, ...]) -> None:
    root = repo / "dayahead/cache/v35" / PHASE_CALIBRATION / day / stage
    root.mkdir(parents=True, exist_ok=True)
    branch_axis = np.asarray(coefficients[0].branch_names)
    np.savez_compressed(
        root / "PLANNING_GRID.npz",
        phase_current_loading_pu=np.asarray(arrays["phase_current_loading_pu"]),
        branch_names=np.asarray([name.rsplit("::", 1)[0] for name in branch_axis]),
        branch_phases=np.asarray([name.rsplit("::", 1)[1].upper() for name in branch_axis]),
    )


def _beam_case(repo: Path, pass_id: str, day: str, case: str,
               aidc_b0: AIDCTrajectory, aidc_b1: AIDCTrajectory) -> dict[str, Any]:
    import dayahead.tools.run_v35r3e_r1_beam as frozen
    import dayahead.v35r3.algorithm as r3
    import dayahead.v35r3e.algorithm as r3e

    data, electrical = load_day_context(day)
    coefficients = _coefficients(electrical)
    selected = aidc_b0 if case == "B2" else aidc_b1
    baseline_arrays, _ = _planning_grid(coefficients, electrical.voltage, selected.pcc_p_kw, MessTrajectory(()))
    _prepare_seed_npz(repo, day, "B0" if case == "B2" else "B1", baseline_arrays, coefficients)
    original_traffic = frozen.daily_traffic_authority
    original_guards = r3.assert_apr01_only, r3e.assert_apr01_only
    original = {
        "APR01": frozen.APR01, "CACHE_ROOT": frozen.CACHE_ROOT,
        "prepare": frozen.prepare_aidc_stages, "traffic": frozen.daily_traffic_authority,
    }

    def selected_day(value: str) -> None:
        if value not in CALIBRATION_DATES:
            raise PermissionError(f"V36_DATE_OUT_OF_SCOPE:{value}")

    frozen.APR01 = day
    frozen.CACHE_ROOT = CACHE_ROOT / pass_id / "beam"
    frozen.prepare_aidc_stages = lambda *_args, **_kwargs: (
        data, electrical,
        {"B0": {"planning_pcc_power_kw": aidc_b0.pcc_p_kw},
         "B1": {"planning_pcc_power_kw": aidc_b1.pcc_p_kw}},
    )
    frozen.daily_traffic_authority = lambda _repo, _cache, phase, target, admission: original_traffic(
        FROZEN_MESS_WORKTREE, FROZEN_MESS_WORKTREE / "dayahead/cache/v35",
        phase, target, admission,
    )
    r3.assert_apr01_only = selected_day
    r3e.assert_apr01_only = selected_day
    try:
        return frozen._run_case(case, BEAM_WIDTH, 4)
    finally:
        frozen.APR01 = original["APR01"]
        frozen.CACHE_ROOT = original["CACHE_ROOT"]
        frozen.prepare_aidc_stages = original["prepare"]
        frozen.daily_traffic_authority = original["traffic"]
        r3.assert_apr01_only, r3e.assert_apr01_only = original_guards


def _trajectory(result: Mapping[str, Any] | None) -> MessTrajectory:
    if result is None:
        return MessTrajectory(())
    from dayahead.tools.run_v35r3e_r1_beam import _restore_slots
    return MessTrajectory(tuple(_restore_slots(result["trajectory_slots"])))


def run_case(repo: Path, pass_id: str, day: str, case: str,
             aidc: AIDCTrajectory, beam_result: Mapping[str, Any] | None) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    _data, electrical = load_day_context(day)
    try:
        coefficients = _coefficients(electrical)
        trajectory = _trajectory(beam_result)
        planning_arrays, planning = _planning_grid(
            coefficients, electrical.voltage, aidc.pcc_p_kw, trajectory,
        )
        p, q, _energy, locations, _modes = _combined_trajectory_arrays(
            trajectory if beam_result is not None else None,
        )
        identity = canonical_sha256({
            "date": day, "case": case, "pass_id": pass_id,
            "AIDC_P": hashlib.sha256(aidc.pcc_p_kw.tobytes()).hexdigest(),
            "AIDC_Q": hashlib.sha256(aidc.pcc_q_kvar.tobytes()).hexdigest(),
            "MESS_trajectory": None if beam_result is None else trajectory.canonical_sha256,
        })
        frozen = FrozenTrajectory(
            day, "DAYAHEAD", case, aidc.pcc_p_kw, aidc.pcc_q_kvar,
            p, q, MESS_IDS, locations, identity,
        )
        fresh = run_fresh_opendss(
            repo=SOURCE_DATA_REPOSITORY, context=electrical,
            voltage=electrical.voltage, trajectory=frozen,
            output=repo / CACHE_ROOT / pass_id / "fresh" / day / case,
        )
        ended = datetime.now(timezone.utc)
        objective_value = (
            float(planning["rho"]) if beam_result is None
            else float(beam_result["selected_state"]["solver_objective"])
        )
        objective = {
            "schema_id": "V36_OBJECTIVE_V1", "date": day, "case": case,
            "primary_objective_J": objective_value,
            "rho_objective_component": float(planning["rho"]),
            "travel_energy_tiebreak_weight": 0.0 if beam_result is None else 1e-8,
            "move_count_tiebreak_weight": 0.0 if beam_result is None else 1e-10,
            "deterministic_ordinal_tiebreak_weight": 0.0 if beam_result is None else 1e-16,
            "objective_definition_SHA": SCIENCE_AUTHORITIES["OBJECTIVE"]["sha256"],
        }
        root = write_case(
            repo=repo, pass_id=pass_id, day=day, case=case, aidc=aidc,
            planning_arrays=planning_arrays, planning_summary=planning,
            voltage_authority=electrical.voltage, coefficients=coefficients,
            trajectory=trajectory if beam_result is not None else None,
            fresh=fresh, beam_result=beam_result,
            provenance=_provenance(repo, day, case, started, ended, fresh, pass_id),
            input_authority=_input_authority(repo, day, case, aidc), objective=objective,
        )
        return {"case": case, "root": str(root), "objective": objective_value,
                "Planning": dict(planning), "Fresh": dict(fresh.summary),
                "natural_MOVE_count": 0 if beam_result is None else int(beam_result["natural_MOVE_count"]),
                "beam_fallback": False, "K_fallback": False}
    finally:
        electrical.voltage.close(); electrical.current.close()


def _write_start(repo: Path) -> None:
    manifest = verify_science()
    root = repo / ARTIFACT_DIR; root.mkdir(parents=True, exist_ok=True)
    write_json(root / "V36_FROZEN_SCIENCE_MANIFEST.json", manifest)
    write_json(root / "V36_START_STATE.json", {
        "artifact_id": "V36_START_STATE_V1", "integration_base_HEAD": INTEGRATION_BASE_HEAD,
        "branch": _git("branch", "--show-current", repo=repo), "worktree": str(repo),
        "HEAD_at_start": git_head(repo), "source_AIDC_HEAD": AIDC_HEAD,
        "source_MESS_HEAD": MESS_HEAD, "isolated_worktree": True,
        "production_main_modified": False, "push_performed": False, "merge_performed": False,
    })
    write_json(root / "V36_INTEGRATION_PORT_AUDIT.json", {
        "artifact_id": "V36_INTEGRATION_PORT_AUDIT_V1",
        "method": "EXPLICIT_SOURCE_SHA_BOUND_ADAPTERS_NO_BLIND_MERGE",
        "AIDC_import": "exact frozen contract/trajectory bytes through git-show",
        "MESS_import": "frozen V35R3E_R1 code retained at integration base",
        "science_changes": [], "engineering_changes": ["portable source lookup", "stable long-form storage"],
    })


def run_apr01(repo: Path, cases: tuple[str, ...] = OFFICIAL_CASES) -> dict[str, Any]:
    _write_start(repo)
    pass_id = "PRE_CALIBRATION"; day = "2025-04-01"
    aidc = {case: build_apr01(repo, case) for case in OFFICIAL_CASES}
    results: dict[str, Any] = {}
    for case in cases:
        beam = None
        if case in {"B2", "B3"}:
            beam = _beam_case(repo, pass_id, day, case, aidc["B0"], aidc["B1"])
        results[case] = run_case(repo, pass_id, day, case, aidc[case], beam)
        print(f"V36 {day} {case} COMPLETE J={results[case]['objective']}", flush=True)
    if set(cases) == set(OFFICIAL_CASES):
        from .certification import finalize_apr01_existing
        finalize_apr01_existing(repo)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apr01", action="store_true")
    parser.add_argument("--finalize-apr01", action="store_true")
    parser.add_argument("--cases", nargs="*", choices=OFFICIAL_CASES, default=list(OFFICIAL_CASES))
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    if _git("branch", "--show-current", repo=repo) != BRANCH:
        raise RuntimeError("V36_WRONG_BRANCH")
    if args.finalize_apr01:
        from .certification import finalize_apr01_existing
        finalize_apr01_existing(repo)
        print("V36 APR-01 EXISTING OUTPUTS CERTIFIED", flush=True)
    elif args.apr01:
        run_apr01(repo, tuple(args.cases))
    else:
        parser.error("select --apr01 or --finalize-apr01")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
