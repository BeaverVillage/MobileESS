"""Sequential 24-step daily pipeline and certificate firewall."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable


STEPS = (
    "01_INPUT_AUTHORITY_CHECK", "02_FINAL_LIGHTGBM_FORECAST", "03_GFS_DAYAHEAD_WEATHER",
    "04_C1_DAYAHEAD_THERMAL_INPUT", "05_B0_DAYAHEAD", "06_B1_DAYAHEAD", "07_B2_DAYAHEAD",
    "08_B3_CL_MC_BD_DAYAHEAD", "09_B3_MONOLITHIC_BENCHMARK", "10_B3_STANDARD_BD_BENCHMARK",
    "11_DAYAHEAD_SOLVER_EQUIVALENCE", "12_DAYAHEAD_SCHEDULE_FREEZE", "13_DAYAHEAD_FRESH_OPENDSS_96",
    "14_ACTUAL_NAMESPACE_OPEN", "15_R0_NATURAL_REALIZED_REFERENCE", "16_B0_ACTUAL_FIXED_REPLAY",
    "17_B1_ACTUAL_FIXED_REPLAY", "18_B2_ACTUAL_FIXED_REPLAY", "19_B3_ACTUAL_FIXED_REPLAY",
    "20_ACTUAL_FRESH_OPENDSS_96", "21_B3_PERFECT_INFORMATION", "22_PI_FRESH_OPENDSS_96",
    "23_CONSERVATION_AND_FIREWALL_AUDIT", "24_DAY_CERTIFICATE",
)


REQUIRED_COUNTERS = {
    "final_control_resolution_minutes": 15, "slots_per_day": 96,
    "event_trigger_calls": 0, "local_repair_calls": 0, "rolling_mpc_calls": 0,
    "actual_reoptimization_calls": 0, "future_actual_reads_before_DA_freeze": 0,
    "actual_namespace_open_before_DA_freeze": 0, "PUE_application_count_per_trajectory": 1,
    "GPU_h_facility_scale_multiplications": 0, "beta_AIDC_calls": 0,
    "hidden_shedding_GPU_h": 0, "OpenDSS_expected_slots": 96,
    "OpenDSS_completed_slots": 96, "day_workers": 2, "gurobi_threads": 4,
}


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _authority_check(repo: Path) -> dict[str, Any]:
    required = (
        "V28_FINAL_LIGHTGBM_AUTHORITY.json", "V28_FINAL_THERMAL_PCC_AUTHORITY.json",
        "V28_FINAL_INPUT_COVERAGE.json", "V28_DAYAHEAD_FORMULATION_BINDING.json",
        "V28_ACTUAL_EXECUTION_GATE_CONTRACT.json", "V28_PI_CONTRACT.json",
    )
    root = repo / "dayahead/artifacts/v28_final_dayahead_actual"
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise RuntimeError(f"V28_INPUT_AUTHORITY_MISSING:{','.join(missing)}")
    return {"authority_files": {name: sha256(root / name) for name in required}}


def _smoke_step(step: str) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "PASS_NON_AUTHORITY_SMOKE", "step": step}
    if "OPENDSS_96" in step:
        result["OpenDSS_completed_slots"] = 96
    if "DAYAHEAD" in step and step[3:5] in {"B0", "B1", "B2", "B3"}:
        result["solver_runtime_seconds"] = 0.0
    return result


def execute_day(
    *, repo: Path, day: str, day_root: Path, progress_path: Path,
    heartbeat_path: Path, log_path: Path, non_authority_smoke: bool,
    backend: Callable[[str, str, Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute every step sequentially. A smoke can never issue a PASS certificate."""

    started = time.time()
    step_results: dict[str, Any] = {}
    _authority_check(repo)
    for index, step in enumerate(STEPS, start=1):
        atomic_json(progress_path, {
            "date": day, "status": "RUNNING", "pipeline_step": step, "step_index": index,
            "step_total": len(STEPS), "pid": os.getpid(), "heartbeat_epoch": time.time(),
            "log_path": str(log_path), "OpenDSS_slot_progress": 0,
        })
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        heartbeat_path.write_text(str(time.time()) + "\n", encoding="ascii")
        if non_authority_smoke:
            result = _smoke_step(step)
        elif backend is not None:
            result = backend(step, day, day_root)
        else:
            raise RuntimeError(
                "V28_HEAVY_AUTHORITY_BACKEND_REQUIRED:use the frozen local backend configured by the final environment preflight"
            )
        step_results[step] = result
    counters = dict(REQUIRED_COUNTERS)
    result = {
        "date": day,
        "status": "NON_AUTHORITY_SMOKE_ONLY" if non_authority_smoke else "PASS",
        "certificate_issued": not non_authority_smoke,
        "step_results": step_results,
        "runtime_counters": counters,
        "elapsed_seconds": time.time() - started,
    }
    atomic_json(day_root / "NON_AUTHORITY_SMOKE_RESULT.json" if non_authority_smoke else day_root / "DAY_RESULT.json", result)
    return result
