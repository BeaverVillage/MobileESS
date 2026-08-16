#!/usr/bin/env python3
"""Prospectively rebase the 12 Stage-7 cold-start PRE states to selected PCCs.

The Stage-7 authority is immutable forensic input.  Only location-dependent
fields and their hashes are changed.  Every other physical/scientific field is
byte-semantically checked against the Stage-7 record before the new authority
is emitted.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


MESS_IDS = tuple(f"MESS{i:02d}" for i in range(1, 5))
ALLOWED_RECORD_DIFFS = {
    "initial_service_authority.source",
    "initial_service_authority.source_sha256",
    "state_sha256",
    *(f"initial_service_authority.mapping.{mid}" for mid in MESS_IDS),
    *(f"state.mess_state.{mid}.{field}" for mid in MESS_IDS for field in (
        "service_id", "source_service_id", "dest_service_id"
    )),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def diff_paths(left: Any, right: Any, prefix: str = "") -> set[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        paths: set[str] = set()
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in left or key not in right:
                paths.add(path)
            else:
                paths.update(diff_paths(left[key], right[key], path))
        return paths
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return {prefix}
        paths: set[str] = set()
        for index, (a, b) in enumerate(zip(left, right)):
            paths.update(diff_paths(a, b, f"{prefix}[{index}]"))
        return paths
    return set() if left == right else {prefix}


def emit(stage7_dir: Path, site_authority_path: Path, output_root: Path) -> dict[str, Any]:
    old_manifest_path = stage7_dir / "INITIAL_STATE_MANIFEST.json"
    old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
    if old_manifest.get("status") != "PASS_12_OF_12_FROZEN_BEFORE_CONTROLLER_OUTCOMES":
        raise RuntimeError("Stage7 initial-state manifest is not the accepted 12/12 authority")
    old_files = old_manifest.get("files", [])
    if len(old_files) != 12 or len({row["candidate_id"] for row in old_files}) != 12:
        raise RuntimeError("Stage7 initial-state cardinality drift")

    site_authority = json.loads(site_authority_path.read_text(encoding="utf-8"))
    if site_authority.get("status") != "PASS_EXACTLY_FOUR_SITES":
        raise RuntimeError("selected-site authority is not PASS_EXACTLY_FOUR_SITES")
    homes = {str(k): str(v) for k, v in site_authority.get("assignment", {}).items()}
    if set(homes) != set(MESS_IDS) or len(set(homes.values())) != 4:
        raise RuntimeError(f"selected-site assignment is not one distinct service per MESS: {homes}")
    authority_sha = sha256(site_authority_path)
    source_text = "performance/post_stage15_runtime_acceleration/SITING/FIXED_ESS_FINAL_SITE_AUTHORITY.json:assignment"

    output_dir = output_root / "INITIAL_STATES"
    resume_dir = output_root / "PRODUCTION_INPUT"
    output_dir.mkdir(parents=True, exist_ok=True)
    resume_dir.mkdir(parents=True, exist_ok=True)
    expected_names = {Path(row["path"]).name for row in old_files} | {"INITIAL_STATE_MANIFEST.json"}
    unexpected = sorted(p.name for p in output_dir.glob("*.json") if p.name not in expected_names)
    if unexpected:
        raise RuntimeError(f"unexpected pre-existing JSON in prospective output: {unexpected}")

    new_files = []
    for old_row in old_files:
        old_path = stage7_dir / Path(old_row["path"]).name
        if sha256(old_path) != old_row["file_sha256"]:
            raise RuntimeError(f"Stage7 file SHA drift: {old_path}")
        old_record = json.loads(old_path.read_text(encoding="utf-8"))
        if canonical_hash(old_record["state"]) != old_record["state_sha256"]:
            raise RuntimeError(f"Stage7 state SHA drift: {old_path}")

        record = copy.deepcopy(old_record)
        record["initial_service_authority"]["mapping"] = homes
        record["initial_service_authority"]["source"] = source_text
        record["initial_service_authority"]["source_sha256"] = authority_sha
        for mid, service in homes.items():
            mess_state = record["state"]["mess_state"][mid]
            if mess_state["phase"] != "STAY" or int(mess_state["remaining_total_steps"]) != 0 or mess_state["remaining_profile_kWh"] != []:
                raise RuntimeError(f"Stage7 {mid} is not a stationary PRE state in {old_path}")
            mess_state["service_id"] = service
            mess_state["source_service_id"] = service
            mess_state["dest_service_id"] = service
        record["state_sha256"] = canonical_hash(record["state"])

        differences = diff_paths(old_record, record)
        if not differences or not differences.issubset(ALLOWED_RECORD_DIFFS):
            raise RuntimeError(
                f"non-location Stage7 field drift for {old_row['candidate_id']}: "
                f"actual={sorted(differences)} allowed={sorted(ALLOWED_RECORD_DIFFS)}"
            )
        expected_differences = ALLOWED_RECORD_DIFFS
        if differences != expected_differences:
            raise RuntimeError(
                f"not every required location binding changed for {old_row['candidate_id']}: "
                f"actual={sorted(differences)} expected={sorted(expected_differences)}"
            )

        new_path = output_dir / old_path.name
        write_json(new_path, record)
        resume_path = resume_dir / f"{old_row['candidate_id']}.resume_state.json"
        write_json(resume_path, {"sha256": record["state_sha256"], "state": record["state"]})
        new_files.append({
            "candidate_id": old_row["candidate_id"],
            "week_start_index": old_row["week_start_index"],
            "path": f"INITIAL_STATES/{new_path.name}",
            "file_sha256": sha256(new_path),
            "state_sha256": record["state_sha256"],
            "production_resume_relpath": f"PRODUCTION_INPUT/{resume_path.name}",
            "production_resume_file_sha256": sha256(resume_path),
            "superseded_stage7_file_sha256": old_row["file_sha256"],
            "superseded_stage7_state_sha256": old_row["state_sha256"],
            "changed_record_paths": sorted(differences),
        })

    manifest = copy.deepcopy(old_manifest)
    manifest.update({
        "schema_version": "mobileess.post_stage15.prospective_siting_initial_state_manifest.v1",
        "status": "PASS_12_OF_12_PROSPECTIVE_OUTCOME_BLIND_SITING_SUPERSESSION",
        "home_mapping_source_sha256": authority_sha,
        "initial_service_authority_path": str(site_authority_path.resolve()),
        "initial_service_authority_sha256": authority_sha,
        "initial_service_assignment": homes,
        "supersedes_stage7_manifest_path": str(old_manifest_path.resolve()),
        "supersedes_stage7_manifest_sha256": sha256(old_manifest_path),
        "stage7_files_modified": False,
        "physical_state_change_scope": "MESS location identity only; energy, debts, queues, jobs, commitments, and issue indices unchanged",
        "controller_outcomes_used_for_siting": False,
        "prospective_for_main_method_matrix": True,
        "files": new_files,
    })
    manifest_path = output_dir / "INITIAL_STATE_MANIFEST.json"
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage7-initial-state-dir", type=Path, required=True)
    parser.add_argument("--site-authority", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--emit-only", action="store_true")
    args = parser.parse_args()
    stage7_dir = args.stage7_initial_state_dir.resolve()
    site_authority = args.site_authority.resolve()
    output_root = args.output_root.resolve()
    manifest = emit(stage7_dir, site_authority, output_root)

    if not args.emit_only:
        with tempfile.TemporaryDirectory(prefix="post_stage15_siting_pre_") as temporary:
            second = emit(stage7_dir, site_authority, Path(temporary))
            first_dir = output_root / "INITIAL_STATES"
            second_dir = Path(temporary) / "INITIAL_STATES"
            for relative in ("INITIAL_STATES", "PRODUCTION_INPUT"):
                first_dir = output_root / relative
                second_dir = Path(temporary) / relative
                names = sorted(p.name for p in first_dir.glob("*.json"))
                if names != sorted(p.name for p in second_dir.glob("*.json")):
                    raise RuntimeError(f"clean-process regeneration file-set drift: {relative}")
                for name in names:
                    if (first_dir / name).read_bytes() != (second_dir / name).read_bytes():
                        raise RuntimeError(f"deterministic regeneration drift: {relative}/{name}")

    print(json.dumps({
        "status": manifest["status"],
        "initial_state_count": len(manifest["files"]),
        "assignment": manifest["initial_service_assignment"],
        "deterministic_regeneration": True,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
