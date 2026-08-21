#!/usr/bin/env python3
"""Freeze canonical and preassigned T3 initializers for all R12 episodes."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


SERVICES = [f"IDC{i:02d}" for i in range(1, 13)] + [f"STA{i:02d}" for i in range(1, 13)]
MESS = [f"MESS{i:02d}" for i in range(1, 5)]
CANONICAL_HOME = {"MESS01": "IDC01", "MESS02": "IDC06", "MESS03": "IDC10", "MESS04": "IDC12"}
E_FLOOR = 440.0
E_MAX = 1080.0
SOC_LEVELS = tuple(E_FLOOR + fraction * (E_MAX - E_FLOOR) for fraction in (0.25, 0.50, 0.75))


def canonical_hash(state: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_state(issue_step: int, locations: dict[str, str], energy: dict[str, float]) -> dict[str, Any]:
    mess_state = {
        mess_id: {
            "phase": "STAY",
            "service_id": locations[mess_id],
            "source_service_id": locations[mess_id],
            "dest_service_id": locations[mess_id],
            "remaining_total_steps": 0,
            "remaining_profile_kWh": [],
        }
        for mess_id in MESS
    }
    return {
        "issue_step": issue_step,
        "queue": {},
        "running": {},
        "inventory_GB": {},
        "pipeline": {},
        "dest_commit": {},
        "mess_state": mess_state,
        "mess_E_kWh": energy,
        "mess_support_debt_kWh": {mess_id: 0.0 for mess_id in MESS},
        "workload_debt_GPUh": {f"IDC{i:02d}": 0.0 for i in range(1, 13)},
        "completed": [],
        "future_plans_persisted": False,
    }


def canonical_initializer(issue_step: int, candidate_id: str) -> dict[str, Any]:
    state = base_state(
        issue_step,
        CANONICAL_HOME,
        {mess_id: 760.0 for mess_id in MESS},
    )
    return {
        "schema_version": "conversation_c.stage7.r12.canonical_initializer.v1",
        "candidate_id": candidate_id,
        "initializer_kind": "CANONICAL_STANDARDIZED_EXPERIMENTAL_INITIAL_CONDITION",
        "state": state,
        "sha256": canonical_hash(state),
    }


def t3_initializer(issue_step: int, candidate_id: str, seed: int) -> dict[str, Any]:
    if not 0 <= seed < 12:
        raise ValueError(seed)
    locations = {mess_id: SERVICES[(seed + 6 * offset) % len(SERVICES)] for offset, mess_id in enumerate(MESS)}
    energy = {mess_id: float(SOC_LEVELS[(seed + offset) % len(SOC_LEVELS)]) for offset, mess_id in enumerate(MESS)}
    state = base_state(issue_step, locations, energy)
    return {
        "schema_version": "conversation_c.stage7.r12.t3_initializer.v1",
        "candidate_id": candidate_id,
        "initializer_kind": "PREASSIGNED_T3_INDEPENDENT_INITIALIZER",
        "ensemble_seed": seed,
        "state": state,
        "sha256": canonical_hash(state),
    }


def write_json(path: Path, value: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    root = Path(__file__).resolve().parent
    with (root / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        weeks = list(csv.DictReader(stream))
    matrix = json.loads((root / "C_STAGE7_R12_TEST_MATRIX.json").read_text(encoding="utf-8"))
    seed_by_candidate = {
        row["candidate_id"]: int(row["t3_ensemble_seed"])
        for row in matrix["initializer_washout_pairs"]
    }
    if len(weeks) != 12 or sorted(seed_by_candidate.values()) != list(range(12)):
        raise RuntimeError("R12 initializer test matrix drift")
    output = root / "frozen_initializers"
    output.mkdir(exist_ok=True)
    files: list[dict[str, object]] = []
    for row in weeks:
        candidate = row["candidate_id"]
        issue = int(row["burn_in_start_index"])
        records = {
            "canonical": canonical_initializer(issue, candidate),
            "t3_assigned": t3_initializer(issue, candidate, seed_by_candidate[candidate]),
        }
        for kind, record in records.items():
            path = output / f"{candidate}.{kind}.json"
            write_json(path, record)
            files.append({
                "candidate_id": candidate,
                "kind": kind,
                "ensemble_seed": record.get("ensemble_seed"),
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "file_sha256": sha256(path),
                "state_sha256": record["sha256"],
            })
    authority = {
        "schema_version": "conversation_c.stage7.r12.initializer_authority.v1",
        "status": "FROZEN_BEFORE_CONTROLLER_OUTCOMES",
        "canonical_rule": "four fixed home IDCs, 760 kWh, empty dynamic containers, zero debts",
        "t3_rule": "frozen 12-seed cyclic location and 25/50/75-percent SOC ensemble",
        "assignment_rule": "medoid_rank r receives seed r-1",
        "copies_continuous_reference_state": False,
        "outcome_based_selection": False,
        "files": files,
    }
    write_json(root / "C_STAGE7_R12_INITIALIZER_AUTHORITY.json", authority)
    print(json.dumps({"status": "PASS", "initializer_files": len(files)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
