#!/usr/bin/env python3
"""Independently rehash and freeze the one permitted V28R2 heavy smoke."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v28r2.backend_contract import sha256_file  # noqa: E402
from dayahead.v28r2.certificate import _verify_code_tree, _verify_embedded_file_manifest  # noqa: E402
from dayahead.v28r2.day_state import DayState  # noqa: E402
from dayahead.v28r2.production_handlers import read_solver_payload  # noqa: E402
from dayahead.v28r2.runtime_ledger import OPENDSS_TRAJECTORIES, PUE_TRAJECTORIES, RuntimeLedger  # noqa: E402
from dayahead.v28r2.schedule_freeze import verify_schedule_manifest  # noqa: E402
from dayahead.v28r2.solver_equivalence import verify_b3_equivalence  # noqa: E402
from dayahead.v28r2.source_manifest import verify_day_manifest  # noqa: E402


DAY = "2025-04-01"
ROOT = REPO / "frozen_artifacts/v28r2_non_authority_heavy_smoke" / DAY
STATE = REPO / "progress/v28r2_non_authority_heavy_smoke" / DAY / "DAY_STATE.json"
STATE_CORRECTION = ROOT / "V28R2_STATE_CHAIN_SHALLOW_COPY_CORRECTION.json"
OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"V28R2_EXPECTED_JSON_OBJECT:{path}")
    return value


def verify_references(smoke: dict[str, object]) -> int:
    references = smoke.get("references")
    if not isinstance(references, dict) or not references:
        raise RuntimeError("V28R2_SMOKE_REFERENCE_AXIS")
    for name, record in references.items():
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "bytes"}:
            raise RuntimeError(f"V28R2_SMOKE_REFERENCE_SCHEMA:{name}")
        path = Path(str(record["path"]))
        if not path.is_file() or sha256_file(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
            raise RuntimeError(f"V28R2_SMOKE_REFERENCE_TAMPER:{name}")
        _verify_embedded_file_manifest(path)
    source_record = references["source_day_manifest"]
    source_path = Path(str(source_record["path"]))
    verify_day_manifest(load(source_path), base_dir=source_path.parent)
    _verify_code_tree(smoke, references)
    return len(references)


def verify_failed_attempt_archive() -> dict[str, object]:
    states = list((STATE.parent / "failed_attempts").glob("*/DAY_STATE.json"))
    rollovers = list((ROOT / "_failed_attempts").glob("*/ROLLOVER.json"))
    if len(states) != 1 or len(rollovers) != 1:
        raise RuntimeError("V28R2_EXPECTED_ONE_PREHEAVY_FAILED_ATTEMPT_ARCHIVE")
    failed = DayState.load(states[0])
    if failed.status != "FAIL" or len(failed.completed_steps) != 4 or failed.failure.get("step") != "05_B0_MONOLITHIC":
        raise RuntimeError("V28R2_PREHEAVY_FAILURE_ARCHIVE_CONTENT")
    snapshot = failed.step_counters[failed.completed_steps[-1]]["_runtime_ledger_snapshot"]
    if snapshot["solver_calls"] or snapshot["opendss_solved_slots"] or any(snapshot["optimizer_calls_by_namespace"].values()):
        raise RuntimeError("V28R2_PREHEAVY_ATTEMPT_PERFORMED_HEAVY_EXECUTION")
    rollover = load(rollovers[0])
    return {
        "count": 1,
        "failed_step": failed.failure["step"],
        "failure": failed.failure["message"],
        "solver_calls": 0,
        "OpenDSS_solved_slots": 0,
        "old_run_spec_sha256": rollover["old_run_spec_sha256"],
        "new_run_spec_sha256": rollover["new_run_spec_sha256"],
    }


def verify_state_correction(state: DayState) -> dict[str, object]:
    correction = load(STATE_CORRECTION)
    current_state = load(STATE)
    required = {
        "status": "PASS",
        "scope": "SERIALIZABLE_STATE_METADATA_ONLY",
        "scientific_artifact_bytes_modified": 0,
        "solver_calls_added": 0,
        "OpenDSS_solves_added": 0,
    }
    for field, expected in required.items():
        if correction.get(field) != expected:
            raise RuntimeError(f"V28R2_STATE_CORRECTION_INVALID:{field}")
    if correction.get("postcorrection_state_sha256") != current_state.get("state_sha256"):
        raise RuntimeError("V28R2_STATE_CORRECTION_ROOT_MISMATCH")
    if correction.get("new_step_sha256") != state.step_sha256:
        raise RuntimeError("V28R2_STATE_CORRECTION_STEP_CHAIN_MISMATCH")
    if int(correction.get("artifact_file_sha256_reverified_count", 0)) <= 0:
        raise RuntimeError("V28R2_STATE_CORRECTION_NO_ARTIFACT_REHASH")
    return {
        "artifact_sha256": sha256_file(STATE_CORRECTION),
        "precorrection_state_sha256": correction["precorrection_state_sha256"],
        "postcorrection_state_sha256": correction["postcorrection_state_sha256"],
        "artifact_file_sha256_reverified_count": correction["artifact_file_sha256_reverified_count"],
        "scientific_artifact_bytes_modified": 0,
        "solver_calls_added": 0,
        "OpenDSS_solves_added": 0,
    }


def verify() -> dict[str, object]:
    smoke_path = ROOT / "V28R2_NON_AUTHORITY_HEAVY_SMOKE_RESULT.json"
    smoke = load(smoke_path)
    if smoke.get("status") != "PASS" or smoke.get("day") != DAY or smoke.get("non_authority_smoke") is not True:
        raise RuntimeError("V28R2_SMOKE_RESULT_STATUS")
    if smoke.get("April_PASS_certificate_issued") is not False or list(ROOT.glob("APRIL_DAY_CERTIFICATE_*.json")):
        raise RuntimeError("V28R2_SMOKE_ISSUED_APRIL_PASS")
    reference_count = verify_references(smoke)
    state = DayState.load(STATE)
    if state.status != "PASS" or len(state.completed_steps) != 30 or state.reusable_prefix_length() != 30:
        raise RuntimeError("V28R2_SMOKE_STATE_OR_STEP_HASH")
    state_correction = verify_state_correction(state)
    ledger_path = ROOT / "RUNTIME_LEDGER.json"
    ledger = RuntimeLedger.load(ledger_path)
    ledger.validate_complete()
    if ledger.optimizer_calls_by_namespace != {"DAYAHEAD": 6, "ACTUAL": 0, "PI": 1}:
        raise RuntimeError("V28R2_SMOKE_OPTIMIZER_LEDGER")
    if ledger.pue_calls != {name: 1 for name in PUE_TRAJECTORIES}:
        raise RuntimeError("V28R2_SMOKE_PUE_LEDGER")
    if ledger.opendss_solved_slots != {name: 96 for name in OPENDSS_TRAJECTORIES}:
        raise RuntimeError("V28R2_SMOKE_OPENDSS_LEDGER")
    if ledger.opendss_engine_count != {name: 1 for name in OPENDSS_TRAJECTORIES}:
        raise RuntimeError("V28R2_SMOKE_CLEAN_ENGINE_LEDGER")
    payloads = {
        solver: read_solver_payload(ROOT / "dayahead/solvers" / f"B3_{solver}" / "SOLVER_PAYLOAD.json")
        for solver in ("CL_MC_BD", "MONOLITHIC", "STANDARD_BD")
    }
    equivalence = verify_b3_equivalence(payloads)
    schedule = verify_schedule_manifest(ROOT / "dayahead/schedules/DAYAHEAD_SCHEDULE_MANIFEST.json")
    actual = {
        case: load(ROOT / "actual/replay" / case / "ACTUAL_REPLAY_SUMMARY.json")
        for case in ("R0", "B0", "B1", "B2", "B3")
    }
    if any(row["actual_reoptimization_calls"] != 0 or row["hidden_shedding_nodeh"] != 0 for row in actual.values()):
        raise RuntimeError("V28R2_SMOKE_ACTUAL_FIREWALL")
    mass_error = max(abs(float(row["workload_mass_error_nodeh"])) for row in actual.values())
    if mass_error > 1e-9:
        raise RuntimeError("V28R2_SMOKE_WORKLOAD_MASS")
    opendss_summaries = {}
    for namespace, cases in (("dayahead", ("B0", "B1", "B2", "B3")), ("actual", ("R0", "B0", "B1", "B2", "B3"))):
        for case in cases:
            row = load(ROOT / namespace / "opendss" / case / "OPENDSS_SUMMARY.json")
            if row["OpenDSS_solve_count"] != 96 or row["convergence_count"] != 96:
                raise RuntimeError(f"V28R2_SMOKE_OPENDSS_SUMMARY:{namespace}:{case}")
            opendss_summaries[f"{namespace}/{case}"] = row
    pi_opendss = load(ROOT / "pi/opendss/B3/OPENDSS_SUMMARY.json")
    if pi_opendss["OpenDSS_solve_count"] != 96 or pi_opendss["convergence_count"] != 96:
        raise RuntimeError("V28R2_SMOKE_PI_OPENDSS_SUMMARY")
    pi = read_solver_payload(ROOT / "pi/PI_B3_SOLVER_PAYLOAD.json")
    if pi.solver != "CL_MC_BD" or not pi.hard_feasible:
        raise RuntimeError("V28R2_SMOKE_PI_SOLVER")
    failure_archive = verify_failed_attempt_archive()
    return {
        "artifact_id": "V28R2_END_TO_END_HEAVY_SMOKE_VERIFICATION_V1",
        "status": "PASS",
        "END_TO_END_HEAVY_SMOKE_PASS": True,
        "date": DAY,
        "non_authority_smoke": True,
        "April_PASS_certificate_issued": False,
        "heavy_completed_steps": 30,
        "solver_calls": len(ledger.solver_calls),
        "optimizer_calls_by_namespace": ledger.optimizer_calls_by_namespace,
        "B3_equivalence": equivalence,
        "schedule_root_sha256": schedule["schedule_root_sha256"],
        "schedule_hashes": smoke["schedule_hashes"],
        "OpenDSS_real_solved_slots": ledger.opendss_solved_slots,
        "OpenDSS_clean_engine_count": ledger.opendss_engine_count,
        "PUE_ledger": ledger.pue_calls,
        "actual_optimizer_calls": 0,
        "hidden_shedding_nodeh": 0.0,
        "workload_mass_error_nodeh": mass_error,
        "SoC_error_kwh": smoke["SoC_error_kwh"],
        "elapsed_seconds": smoke["elapsed_seconds"],
        "peak_RSS_bytes": ledger.peak_rss_bytes,
        "Gurobi_version": smoke["Gurobi_version"],
        "OpenDSS_versions": smoke["OpenDSS_versions"],
        "reference_count_rehashed": reference_count,
        "state_step_artifact_hashes_recomputed": True,
        "runtime_ledger_recomputed": True,
        "source_day_manifest_recursively_verified": True,
        "code_tree_verified_against_git_commit": True,
        "failed_preheavy_attempt_archive": failure_archive,
        "state_chain_correction": state_correction,
        "evidence_sha256": {
            "smoke_result": sha256_file(smoke_path),
            "final_audit": sha256_file(ROOT / "V28R2_FINAL_AUDIT.json"),
            "runtime_ledger": sha256_file(ledger_path),
            "day_state": sha256_file(STATE),
            "state_chain_correction": sha256_file(STATE_CORRECTION),
        },
        "smoke_git_head": smoke["git_head"],
    }


def update_contracts(verification: dict[str, object]) -> None:
    equivalence = verification["B3_equivalence"]
    write("V28R2_END_TO_END_HEAVY_SMOKE_VERIFICATION.json", verification)
    write("V28R2_B3_SOLVER_EQUIVALENCE.json", {
        "artifact_id": "V28R2_B3_SOLVER_EQUIVALENCE_V1",
        **equivalence,
        "smoke_date": DAY,
        "evidence_sha256": verification["evidence_sha256"]["smoke_result"],
    })
    updates = (
        ("V28R2_DAYAHEAD_SCHEDULE_MANIFEST_SCHEMA.json", {"DAYAHEAD_SCHEDULE_FREEZE_READY": True, "smoke_schedule_root_sha256": verification["schedule_root_sha256"], "status": "PASS"}),
        ("V28R2_OPENDSS_PRODUCTION_CONTRACT.json", {"FRESH_OPENDSS_BACKEND_READY": True, "smoke_real_solved_slots": verification["OpenDSS_real_solved_slots"], "status": "PASS"}),
        ("V28R2_ACTUAL_REPLAY_CONTRACT.json", {"ACTUAL_FULL_REPLAY_READY": True, "smoke_actual_optimizer_calls": 0, "smoke_workload_mass_error_nodeh": verification["workload_mass_error_nodeh"], "status": "PASS"}),
        ("V28R2_PI_EXECUTION_CONTRACT.json", {"PI_FULL_EXECUTION_READY": True, "smoke_PI_solver": "CL_MC_BD", "smoke_PI_OpenDSS_slots": 96, "status": "PASS"}),
        ("V28R2_RUNTIME_LEDGER_CONTRACT.json", {"MEASURED_RUNTIME_LEDGER_READY": True, "smoke_solver_calls": verification["solver_calls"], "smoke_OpenDSS_real_solved_slots": verification["OpenDSS_real_solved_slots"], "status": "PASS"}),
    )
    for filename, fields in updates:
        payload = load(OUT / filename)
        payload.update(fields)
        write(filename, payload)


def main() -> None:
    verification = verify()
    update_contracts(verification)
    print(json.dumps({
        "status": verification["status"],
        "END_TO_END_HEAVY_SMOKE_PASS": verification["END_TO_END_HEAVY_SMOKE_PASS"],
        "date": verification["date"],
        "solver_calls": verification["solver_calls"],
        "OpenDSS_trajectories": len(verification["OpenDSS_real_solved_slots"]),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
