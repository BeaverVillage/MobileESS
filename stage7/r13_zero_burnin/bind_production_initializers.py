#!/usr/bin/env python3
"""Bind all canonical PRE states to the SHA-locked production state API."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path


GENERIC_CORE_SHA = "c10ed2683ce53c8ee429e0d5c58615ffd09cfeb09febed0f10380d964f036836"
SCIENCE_MAIN_SHA = "1177ac8814f1008907f89ebf513bf9fe3e469d2c09a51ba85303c46c428f76b9"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--generic-core", type=Path, required=True)
    args = parser.parse_args()
    root = args.authority_root.resolve()
    repo = args.repo.resolve()
    core_path = args.generic_core.resolve()
    if sha256(core_path) != GENERIC_CORE_SHA:
        raise RuntimeError("T1 generic production core SHA drift")
    if sha256(repo / "science/main.py") != SCIENCE_MAIN_SHA:
        raise RuntimeError("production science/main.py SHA drift")
    sys.path.insert(0, str(repo / "science"))
    generic = load_module(core_path, "r13_generic_production_core")
    science = generic.load_locked_science(repo)
    manifest = json.loads(
        (root / "INITIAL_STATES/INITIAL_STATE_MANIFEST.json").read_text(encoding="utf-8")
    )

    bindings = []
    production_dir = root / "INITIALIZER_BINDING/production_input"
    production_dir.mkdir(parents=True, exist_ok=True)
    for entry in manifest["files"]:
        source = root / entry["path"]
        record = json.loads(source.read_text(encoding="utf-8"))
        state = record["state"]
        science._build7c_assert_state(state)
        rebuilt = science._build7c_state_snapshot(
            state["issue_step"], state["queue"], state["running"],
            state["inventory_GB"], state["pipeline"], state["dest_commit"],
            state["mess_state"], state["mess_E_kWh"],
            state["mess_support_debt_kWh"], state["workload_debt_GPUh"],
            state["completed"],
        )
        if rebuilt != state:
            raise RuntimeError(f"production state snapshot normalization drift: {entry['candidate_id']}")
        production_hash = science._build7c_state_hash(rebuilt)
        if production_hash != entry["state_sha256"]:
            raise RuntimeError(f"production state hash drift: {entry['candidate_id']}")
        destination = production_dir / f"{entry['candidate_id']}.resume_state.json"
        write_json(destination, {"state": rebuilt, "sha256": production_hash})
        bindings.append({
            "candidate_id": entry["candidate_id"],
            "canonical_pre_state": entry["path"],
            "canonical_pre_state_file_sha256": entry["file_sha256"],
            "causal_frame_pre_state_hash": production_hash,
            "production_resume_state": str(destination.relative_to(root)).replace("\\", "/"),
            "production_resume_state_file_sha256": sha256(destination),
            "production_environment_binding": {
                "MOBILEESS_R25Q_RESUME_STATE_PATH": str(destination),
                "MOBILEESS_RESUME_STATE_SHA256": production_hash,
                "MOBILEESS_R25Q_VERIFIED_PREFIX_ISSUES": "0",
            },
            "production_state_assertion_pass": True,
            "production_state_snapshot_roundtrip_exact": True,
        })

    authority = {
        "schema_version": "conversation_c.stage7.r13.production_initializer_binding.v1",
        "status": "PASS_12_OF_12_LOCKED_PRODUCTION_STATE_API",
        "production_core": str(core_path),
        "production_core_sha256": GENERIC_CORE_SHA,
        "science_main_sha256": SCIENCE_MAIN_SHA,
        "production_functions": [
            "science._build7c_assert_state",
            "science._build7c_state_snapshot",
            "science._build7c_state_hash",
        ],
        "adapter_is_final_authority": False,
        "locked_production_science_is_final_authority": True,
        "controller_burn_in_steps": 0,
        "future_actual_used": False,
        "future_D2_reinjected": False,
        "future_plans_persisted": False,
        "actual_h0_subset_pending": True,
        "bindings": bindings,
    }
    write_json(root / "INITIALIZER_BINDING/PRODUCTION_INITIALIZER_BINDING.json", authority)
    preflight = {
        "schema_version": "conversation_c.stage7.r13.production_initializer_preflight.v1",
        "status": "PASS_READY_FOR_PREREGISTERED_H0_EXECUTION",
        "canonical_states_checked": len(bindings),
        "production_assertion_passed": len(bindings),
        "production_snapshot_roundtrip_exact": len(bindings),
        "production_hash_exact": len(bindings),
        "controller_burn_in_steps": 0,
        "solver_executed": False,
        "opendss_executed": False,
        "future_actual_used": False,
        "future_plans_persisted": False,
    }
    write_json(root / "INITIALIZER_BINDING/PREFLIGHT_RESULT.json", preflight)
    print(json.dumps(preflight, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
