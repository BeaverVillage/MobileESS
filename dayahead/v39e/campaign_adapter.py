"""Load frozen V39E DA decisions into the accepted V37 Actual/Fresh runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading
import time
import traceback
from typing import Any

import numpy as np
import pandas as pd

from dayahead.v38.authority import canonical_sha256
from dayahead.v39c.freeze import atomic_json, sha256_file
from dayahead.v37.aidc import AIDCTrajectory, validate_cohort_contract
from dayahead.v37.aidc_materializer import load_day_manifest

from .full_preflight import FULL_ROOT


PASS_ID = "MAY_2025_V39E_FROZEN_DA"
STATUS_ROOT = FULL_ROOT / "status"
DATE_RESULT_ROOT = FULL_ROOT / "dates"
LOG_ROOT = Path("logs/v39e_may_2025")


def freeze_path(repo: Path, day: str, case: str) -> Path:
    return repo / FULL_ROOT / f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json"


def build_day(repo: Path, day: str, case: str) -> AIDCTrajectory:
    """Compatibility adapter; this function performs no optimization."""

    path = freeze_path(repo, day, case)
    if not path.is_file():
        raise RuntimeError(f"DA_PLAN_UNAVAILABLE_UNDER_FROZEN_SCIENCE:{day}:{case}")
    freeze = json.loads(path.read_text(encoding="utf-8"))
    decision = dict(freeze["decision"])
    if decision.get("status") != "PASS":
        raise RuntimeError(f"DA_PLAN_UNAVAILABLE_UNDER_FROZEN_SCIENCE:{day}:{case}")
    digest = canonical_sha256(decision)
    if digest != freeze.get("DA_decision_SHA256"):
        raise RuntimeError(f"V39E_DA_FREEZE_SHA_MISMATCH:{day}:{case}")

    pcc = pd.DataFrame(decision["site_PCC_power_trajectory"])
    pcc = pcc.sort_values(["slot", "AIDC"]).reset_index(drop=True)
    if len(pcc) != 96 * 12:
        raise RuntimeError(f"V39E_DA_PCC_AXIS:{day}:{case}")
    pcc_p = pcc["PCC_P_kW"].to_numpy(float).reshape(96, 12)
    pcc_q = pcc["PCC_Q_kvar"].to_numpy(float).reshape(96, 12)
    it = pd.DataFrame(decision["site_IT_power_trajectory"])
    aggregate_it = (
        it.groupby("slot", sort=True)["IT_power_kW"].sum().to_numpy(float)
    )
    gpu = pd.DataFrame(decision["site_GPU_trajectory"])
    aggregate_gpu = (
        gpu.groupby("slot", sort=True)["active_GPU"].sum().to_numpy(float)
    )
    source_root = repo / "dayahead/artifacts/v37_r4a_per_day_aidc/days" / day
    source_trajectory = pd.read_parquet(source_root / "V37_R4A_GPU_IT_TRAJECTORY.parquet")
    rw_it = source_trajectory["P_IT_RW_kW"].to_numpy(float)
    mode = str(decision["temporal_mode"])
    power = pd.DataFrame({
        "slot": np.arange(96, dtype=int),
        "timestamp": source_trajectory["timestamp"],
        "N_active_GPU": aggregate_gpu,
        "N_idle_GPU": 624.0 - aggregate_gpu,
        "P_IT_RW_kW": rw_it,
        "P_IT_case_kW": aggregate_it,
        "Delta_P_AIDC_kW": aggregate_it - rw_it,
        "AIDC_flexibility": "ON" if mode == "RSP" else "OFF",
        "official_scenario": "CENTER" if mode == "RSP" else "RW_FROZEN_REFERENCE",
        "CENTER_swing_W_per_GPU": 547.7239090195797,
        "C1_effective_PUE": pcc_p.sum(axis=1) / aggregate_it,
        "aggregate_PCC_P_kW": pcc_p.sum(axis=1),
        "aggregate_PCC_Q_kvar": pcc_q.sum(axis=1),
    })
    manifest = load_day_manifest(repo, day)
    ledger = pd.read_parquet(source_root / "V37_R4A_JOB_LEDGER.parquet")
    ledger["source_snapshot_sha256"] = manifest["source_snapshot_sha256"]
    ledger.attrs["cohort_census"] = dict(manifest["cohort_census"])
    validate_cohort_contract(ledger, day)
    site = pcc.rename(columns={"AIDC": "AIDC_id"}).copy()
    fingerprints = {
        "operating_day": day,
        "V39E_DA_freeze_SHA256": sha256_file(path),
        "V39E_DA_decision_SHA256": digest,
        "V39E_common_initial_state_SHA256": str(decision["common_initial_state_SHA256"]),
        "V39E_temporal_schedule_SHA256": str(decision["temporal_schedule_SHA256"]),
        "V39E_AIDC_assignment_SHA256": canonical_sha256(decision["AIDC_assignments"]),
        "V39E_adapter_source_SHA256": sha256_file(Path(__file__)),
        "source_snapshot_sha256": manifest["source_snapshot_sha256"],
        "legacy_IDC_field_alias": "AIDC_id->historical downstream IDC-compatible schema",
    }
    contract = canonical_sha256({
        "semantics": "V39E_FROZEN_DA_FIXED_REPLAY",
        "decision_SHA256": digest,
        "P_SHA256": hashlib.sha256(pcc_p.tobytes()).hexdigest(),
        "Q_SHA256": hashlib.sha256(pcc_q.tobytes()).hexdigest(),
    })
    return AIDCTrajectory(
        day=day,
        power=power,
        ledger=ledger,
        site=site,
        pcc_p_kw=pcc_p,
        pcc_q_kvar=pcc_q,
        contract_sha256=contract,
        fingerprints=fingerprints,
    )


def configure_v37_runner() -> Any:
    """Bind the accepted Actual/MESS/Fresh implementation to V39E DA inputs."""

    import dayahead.v37.runner as runner

    runner.build_day = build_day
    runner.PASS_ID = PASS_ID
    runner.STATUS_ROOT = STATUS_ROOT
    runner.DATE_RESULT_ROOT = DATE_RESULT_ROOT
    runner.ARTIFACT_ROOT = FULL_ROOT
    runner.PRODUCTION_PREFLIGHT = FULL_ROOT / "V39E_FULL_PREFLIGHT.json"
    runner.FIREWALL = {
        "May_result_used_to_tune_CENTER": "NO",
        "May_result_used_to_tune_MESS": "NO",
        "AIDC_location_changed_after_DA_freeze": "NO",
        "Fresh_used_for_AIDC_or_MESS_initial_decisions": "NO",
        "Fresh_used_for_post_selection_AC_feasibility_detection": "YES",
        "Fresh_used_by_frozen_fixed_discrete_PQ_restoration": "YES",
        "Fresh_changes_MESS_destination_route_departure_or_move": "NO",
        "Actual_temporal_reoptimization_calls": 0,
        "Actual_AIDC_reoptimization_calls": 0,
        "Actual_migration_reoptimization_calls": 0,
        "Actual_WAN_reroute_calls": 0,
    }
    return runner


def run_day_with_unavailable_da(repo: Path, day: str) -> dict[str, Any]:
    """Run every case with a valid freeze and fail closed only for missing DA."""

    runner = configure_v37_runner()
    unavailable = {
        case for case in ("B0", "B1", "B2", "B3")
        if not freeze_path(repo, day, case).is_file()
        or json.loads(freeze_path(repo, day, case).read_text(encoding="utf-8"))
        .get("decision", {}).get("status") != "PASS"
    }
    if not unavailable:
        return runner.run_day(repo, day)

    started = time.perf_counter()
    status_path = repo / STATUS_ROOT / f"{day}.json"
    result_path = repo / DATE_RESULT_ROOT / f"{day}.json"
    runner.write_status(
        status_path, day, "RUNNING", 0, "PARTIAL_DA_FIXED_REPLAY",
        extra={"workers": runner.MAX_WORKERS_PER_DATE},
    )
    trajectories: dict[str, Any] = {}
    for case in runner.OFFICIAL_CASES:
        if case not in unavailable:
            trajectories[case] = build_day(repo, day, case)

    cases: dict[str, dict[str, Any]] = {}
    raw_results: dict[str, dict[str, Any]] = {}
    for case in runner.OFFICIAL_CASES:
        if case in unavailable:
            cases[case] = {
                "status": "DA_PLAN_UNAVAILABLE_UNDER_FROZEN_SCIENCE",
                "operating_day": day,
                "case": case,
                "Actual_temporal_reoptimization_calls": 0,
                "Actual_AIDC_reoptimization_calls": 0,
                "Actual_migration_reoptimization_calls": 0,
                "Actual_WAN_reroute_calls": 0,
            }
            continue
        try:
            trajectory = trajectories[case]
            fingerprint = runner.case_execution_fingerprint(
                repo, day, case, trajectory
            )
            cached = runner._valid_case_checkpoint(repo, day, case, fingerprint)
            if cached is not None:
                result = cached
            else:
                beam = None
                fallback = 0
                if case in {"B2", "B3"}:
                    counterpart = "B0" if case == "B2" else "B1"
                    stop = threading.Event()
                    watcher = threading.Thread(
                        target=runner._watch_beam,
                        args=(
                            repo, day, case,
                            str(fingerprint["execution_fingerprint_sha256"]), stop,
                        ),
                        daemon=True,
                    )
                    watcher.start()
                    try:
                        beam, fallback = runner._beam_case(
                            repo, day, case,
                            trajectories.get("B0", trajectories[counterpart]),
                            trajectories.get("B1", trajectories[counterpart]),
                            fingerprint,
                        )
                    finally:
                        stop.set()
                        watcher.join(timeout=5)
                result = runner._run_frozen_case(
                    repo, day, case, trajectory, beam
                )
                result["beam_fallback"] = bool(fallback)
                result["execution_fingerprint_sha256"] = fingerprint[
                    "execution_fingerprint_sha256"
                ]
                result["reuse"] = {
                    "REUSED": "NO", "source_artifact": None,
                    "source_SHA": None,
                    "authority_SHA": fingerprint["voltage_authority_sha256"],
                    "reason": "NO_EXACT_COMPLETED_CASE_CHECKPOINT",
                }
                runner._write_case_checkpoint(
                    repo, day, case, result, fingerprint
                )
            raw_results[case] = result
            cases[case] = runner._case_metrics(repo, day, case, result)
        except Exception as error:
            cases[case] = {
                "status": "FAIL",
                "error": f"{type(error).__name__}:{error}",
                "traceback": traceback.format_exc(),
            }
        runner.write_status(
            status_path, day, "RUNNING", runner.PROGRESS_AFTER_CASE[case],
            f"{case}_COMPLETE_OR_UNAVAILABLE",
        )

    payload = {
        "artifact_id": "V39E_MAY_DATE_PARTIAL_RESULT_V1",
        "date": day,
        "status": "FAIL",
        "error": "DA_PLAN_UNAVAILABLE_UNDER_FROZEN_SCIENCE",
        "unavailable_cases": sorted(unavailable),
        "cases": cases,
        "Fresh_96_of_96_PASS": False,
        "physical_gates_PASS": False,
        "wallclock_seconds": time.perf_counter() - started,
        "firewall": runner.FIREWALL,
    }
    atomic_json(result_path, payload)
    runner.write_status(
        status_path, day, "FAIL", 14, None,
        error=payload["error"], extra={"result_path": str(result_path.resolve())},
    )
    return payload


__all__ = [
    "DATE_RESULT_ROOT", "LOG_ROOT", "PASS_ID", "STATUS_ROOT", "build_day",
    "configure_v37_runner", "freeze_path", "run_day_with_unavailable_da",
]
