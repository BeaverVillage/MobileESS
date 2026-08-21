#!/usr/bin/env python3
"""Fail-closed validation of the R13 zero-burn-in authority and PRE states."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


STATE_FIELDS = {
    "issue_step", "queue", "running", "inventory_GB", "pipeline",
    "dest_commit", "mess_state", "mess_E_kWh", "mess_support_debt_kWh",
    "workload_debt_GPUh", "completed", "future_plans_persisted",
}
MESS = {f"MESS{i:02d}" for i in range(1, 5)}
IDCS = {f"IDC{i:02d}" for i in range(1, 13)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_hash(state: dict) -> str:
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    root = args.authority_root.resolve()
    contract = load(root / "C_STAGE7_ZERO_BURNIN_EXECUTION_CONTRACT.json")
    supersession = load(root / "C_STAGE7_BURNIN_REMOVAL_SUPERSESSION.json")
    prereg = load(root / "RESTART/RESTART_TEST_PREREGISTRATION.json")
    manifest = load(root / "INITIAL_STATES/INITIAL_STATE_MANIFEST.json")
    with (root / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        weeks = list(csv.DictReader(stream))
    week_by_id = {row["candidate_id"]: row for row in weeks}

    checks = {
        "twelve_frozen_representative_weeks": len(weeks) == len(week_by_id) == 12,
        "controller_burn_in_zero": contract.get("controller_burn_in_steps") == 0,
        "selection_pre_history_distinct_576": contract.get("selection_window_pre_history_steps") == 576,
        "deterministic_cold_start": contract.get("initialization_mode") == "DETERMINISTIC_CANONICAL_COLD_START",
        "old_burnin_not_retroactively_passed": supersession.get("retroactive_old_E7A_E7B_PASS_claimed") is False,
        "manifest_12": len(manifest.get("files", [])) == 12,
        "clean_process_regeneration": manifest.get("deterministic_clean_process_regeneration") is True,
        "restart_preregistered_four_seasons": len(prereg.get("selected", [])) == 4
        and {row["season"] for row in prereg["selected"]} == {"summer", "autumn", "winter", "spring"},
    }
    files_ok = True
    for entry in manifest.get("files", []):
        candidate = entry["candidate_id"]
        path = root / entry["path"]
        if candidate not in week_by_id or not path.is_file() or sha256(path) != entry["file_sha256"]:
            files_ok = False
            continue
        record = load(path)
        state = record.get("state", {})
        files_ok &= set(state) == STATE_FIELDS
        files_ok &= int(state.get("issue_step", -1)) == int(week_by_id[candidate]["start_index"])
        files_ok &= record.get("controller_burn_in_steps") == 0
        files_ok &= record.get("selection_window_pre_history_steps") == 576
        files_ok &= record.get("future_actual_used") is False
        files_ok &= record.get("future_D2_reinjected") is False
        files_ok &= state.get("future_plans_persisted") is False
        files_ok &= record.get("state_sha256") == entry["state_sha256"] == state_hash(state)
        files_ok &= all(state.get(key) == {} for key in (
            "queue", "running", "inventory_GB", "pipeline", "dest_commit"
        ))
        files_ok &= state.get("completed") == []
        files_ok &= set(state.get("mess_state", {})) == MESS
        files_ok &= set(state.get("mess_E_kWh", {})) == MESS
        files_ok &= set(state.get("mess_support_debt_kWh", {})) == MESS
        files_ok &= set(state.get("workload_debt_GPUh", {})) == IDCS
        files_ok &= all(float(value) == float(manifest["E_init_kWh"]) for value in state["mess_E_kWh"].values())
        files_ok &= all(float(value) == 0.0 for value in state["mess_support_debt_kWh"].values())
        files_ok &= all(float(value) == 0.0 for value in state["workload_debt_GPUh"].values())
        for mess_state in state["mess_state"].values():
            files_ok &= mess_state.get("phase") == "STAY"
            files_ok &= mess_state.get("remaining_total_steps") == 0
            files_ok &= mess_state.get("remaining_profile_kWh") == []
            files_ok &= mess_state.get("service_id") in IDCS
    checks["canonical_pre_states_12_of_12"] = bool(files_ok)
    failed = sorted(name for name, passed in checks.items() if not passed)
    result = {
        "schema_version": "conversation_c.stage7.r13.zero_burnin_authority_validation.v1",
        "status": "PASS_READY_FOR_PRODUCTION_INITIALIZER_PREFLIGHT" if not failed else "FAIL_CLOSED",
        "checks": checks,
        "failed_checks": failed,
        "canonical_pre_state_count": len(manifest.get("files", [])),
        "controller_burn_in_steps": 0,
        "gurobi_executed": False,
        "opendss_executed": False,
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write_result:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
