#!/usr/bin/env python3
"""Freeze the twelve deterministic Stage-7 zero-burn-in PRE states."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCIENCE_MAIN_SHA = "1177ac8814f1008907f89ebf513bf9fe3e469d2c09a51ba85303c46c428f76b9"
HOME_MAPPING_SOURCE_SHA = "b5b648356135abaa89ab08feab7b49786d9d32681cf1af422e2699aa8bf5adb2"
WEEK_SELECTION_SHA = "0e32d3257fdc1fafc0bbdd95ca01f270b164a9be18ffa45c060e3c490bed2577"
MESS_IDS = tuple(f"MESS{i:02d}" for i in range(1, 5))
IDC_IDS = tuple(f"IDC{i:02d}" for i in range(1, 13))
STATE_FIELDS = (
    "issue_step", "queue", "running", "inventory_GB", "pipeline",
    "dest_commit", "mess_state", "mess_E_kWh", "mess_support_debt_kWh",
    "workload_debt_GPUh", "completed", "future_plans_persisted",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(state: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            matches.append(ast.literal_eval(node.value))
    if len(matches) != 1:
        raise RuntimeError(f"expected one literal assignment for {name}, got {len(matches)}")
    return matches[0]


def state_for(issue: int, homes: dict[str, str], energy: float) -> dict[str, Any]:
    return {
        "issue_step": int(issue),
        "queue": {},
        "running": {},
        "inventory_GB": {},
        "pipeline": {},
        "dest_commit": {},
        "mess_state": {
            mess: {
                "phase": "STAY",
                "service_id": homes[mess],
                "source_service_id": homes[mess],
                "dest_service_id": homes[mess],
                "remaining_total_steps": 0,
                "remaining_profile_kWh": [],
            }
            for mess in MESS_IDS
        },
        "mess_E_kWh": {mess: float(energy) for mess in MESS_IDS},
        "mess_support_debt_kWh": {mess: 0.0 for mess in MESS_IDS},
        "workload_debt_GPUh": {idc: 0.0 for idc in IDC_IDS},
        "completed": [],
        "future_plans_persisted": False,
    }


def emit(authority: Path, repo: Path, r12: Path, output: Path) -> dict[str, Any]:
    science = repo / "science/main.py"
    mapping_source = r12 / "freeze_r12_initializers.py"
    selection = authority / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv"
    if sha256(science) != SCIENCE_MAIN_SHA:
        raise RuntimeError("pinned science/main.py SHA drift")
    if sha256(mapping_source) != HOME_MAPPING_SOURCE_SHA:
        raise RuntimeError("frozen pre-outcome MESS home mapping source SHA drift")
    if sha256(selection) != WEEK_SELECTION_SHA:
        raise RuntimeError("representative-week selection SHA drift")

    e_floor = float(literal_assignment(science, "E_FLOOR"))
    e_max = float(literal_assignment(science, "E_MAX"))
    homes = {str(k): str(v) for k, v in literal_assignment(mapping_source, "CANONICAL_HOME").items()}
    if set(homes) != set(MESS_IDS) or any(service not in IDC_IDS for service in homes.values()):
        raise RuntimeError("frozen MESS home mapping is not four valid IDC services")
    if not e_floor < e_max:
        raise RuntimeError("invalid scientific energy interval")
    e_init = (e_floor + e_max) / 2.0

    with selection.open(encoding="utf-8", newline="") as stream:
        weeks = list(csv.DictReader(stream))
    if len(weeks) != 12 or len({row["candidate_id"] for row in weeks}) != 12:
        raise RuntimeError("representative-week cardinality drift")

    state_dir = output / "INITIAL_STATES"
    state_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for row in weeks:
        candidate = row["candidate_id"]
        issue = int(row["start_index"])
        state = state_for(issue, homes, e_init)
        record = {
            "schema_version": "conversation_c.stage7.r13.canonical_cold_start.v1",
            "candidate_id": candidate,
            "week_start_aest": row["week_start_aest"],
            "initialization_mode": "DETERMINISTIC_CANONICAL_COLD_START",
            "experimental_initialization_assumption": True,
            "controller_burn_in_steps": 0,
            "selection_window_pre_history_steps": 576,
            "scientific_constants": {
                "E_FLOOR_kWh": e_floor,
                "E_MAX_kWh": e_max,
                "E_init_formula": "(E_FLOOR + E_MAX) / 2",
                "E_init_kWh": e_init,
                "science_main_sha256": SCIENCE_MAIN_SHA,
            },
            "initial_service_authority": {
                "mapping": homes,
                "source": "stage7/r12_representative_weeks/freeze_r12_initializers.py:CANONICAL_HOME",
                "source_sha256": HOME_MAPPING_SOURCE_SHA,
                "frozen_before_controller_outcomes": True,
            },
            "state": state,
            "state_sha256": canonical_hash(state),
            "future_actual_used": False,
            "future_D2_reinjected": False,
            "future_plans_persisted": False,
        }
        name = f"CANONICAL_PRE_STATE_{candidate}.json"
        path = state_dir / name
        write_json(path, record)
        files.append({
            "candidate_id": candidate,
            "week_start_index": issue,
            "path": f"INITIAL_STATES/{name}",
            "file_sha256": sha256(path),
            "state_sha256": record["state_sha256"],
        })

    manifest = {
        "schema_version": "conversation_c.stage7.r13.initial_state_manifest.v1",
        "status": "PASS_12_OF_12_FROZEN_BEFORE_CONTROLLER_OUTCOMES",
        "initialization_mode": "DETERMINISTIC_CANONICAL_COLD_START",
        "controller_burn_in_steps": 0,
        "selection_window_pre_history_steps": 576,
        "method_independent_initial_state": True,
        "same_initialization_rule_across_all_12_representative_weeks": True,
        "canonical_state_fields": list(STATE_FIELDS),
        "canonical_serialization": "json.dumps(state,sort_keys=True,separators=(',',':'),default=str)",
        "science_main_sha256": SCIENCE_MAIN_SHA,
        "home_mapping_source_sha256": HOME_MAPPING_SOURCE_SHA,
        "E_FLOOR_kWh": e_floor,
        "E_MAX_kWh": e_max,
        "E_init_kWh": e_init,
        "deterministic_clean_process_regeneration": True,
        "controller_outcomes_used": False,
        "files": files,
    }
    write_json(state_dir / "INITIAL_STATE_MANIFEST.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--r12-authority-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--emit-only", action="store_true")
    args = parser.parse_args()
    authority, repo, r12, output = map(Path.resolve, (
        args.authority_root, args.repo, args.r12_authority_root, args.output_root
    ))
    manifest = emit(authority, repo, r12, output)
    if not args.emit_only:
        temporary = Path(tempfile.mkdtemp(prefix="stage7_r13_regenerate_"))
        try:
            subprocess.run([
                sys.executable, str(Path(__file__).resolve()),
                "--authority-root", str(authority), "--repo", str(repo),
                "--r12-authority-root", str(r12), "--output-root", str(temporary),
                "--emit-only",
            ], check=True)
            first = output / "INITIAL_STATES"
            second = temporary / "INITIAL_STATES"
            names = sorted(path.name for path in first.glob("*.json"))
            if names != sorted(path.name for path in second.glob("*.json")):
                raise RuntimeError("clean-process regeneration file set drift")
            for name in names:
                if (first / name).read_bytes() != (second / name).read_bytes():
                    raise RuntimeError(f"clean-process deterministic regeneration drift: {name}")
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps({
        "status": manifest["status"],
        "initial_state_count": len(manifest["files"]),
        "E_init_kWh": manifest["E_init_kWh"],
        "deterministic_regeneration": True,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
