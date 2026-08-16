#!/usr/bin/env python3
"""One-step production controller runner for R13 cold-start/restart evidence."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


SCIENCE_MAIN_SHA = "1177ac8814f1008907f89ebf513bf9fe3e469d2c09a51ba85303c46c428f76b9"
GENERIC_CORE_SHA = "c10ed2683ce53c8ee429e0d5c58615ffd09cfeb09febed0f10380d964f036836"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--r12-runner-core", type=Path, required=True)
    parser.add_argument("--legacy-runner", type=Path, required=True)
    parser.add_argument("--generic-core", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base-work", type=Path, required=True)
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--mobility-root", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--initializer", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--lane", choices=("canonical_h0", "restart_restore"), required=True)
    parser.add_argument("--start-offset", type=int, choices=(0, 1), required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    base = args.base_work.resolve()
    authority = args.authority_root.resolve()
    source_root = args.source_root.resolve()
    mobility_root = args.mobility_root.resolve()
    initializer = args.initializer.resolve()
    result_dir = args.result_dir.resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    r12 = __import__("importlib.util").util.spec_from_file_location(
        "r13_r12_production_core", args.r12_runner_core.resolve()
    )
    if r12 is None or r12.loader is None:
        raise RuntimeError("cannot import R12 production runner core")
    r12_module = __import__("importlib.util").util.module_from_spec(r12)
    sys.modules[r12.name] = r12_module
    r12.loader.exec_module(r12_module)
    legacy = r12_module.load_module(args.legacy_runner.resolve(), "r13_legacy_actual_runner")
    generic_path = args.generic_core.resolve()
    if r12_module.sha256(generic_path) != GENERIC_CORE_SHA:
        raise RuntimeError("generic production core SHA drift")
    generic = r12_module.load_module(generic_path, "r13_generic_actual_core")
    if r12_module.sha256(repo / "science/main.py") != SCIENCE_MAIN_SHA:
        raise RuntimeError("science/main.py SHA drift")

    with (authority / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = {row["candidate_id"]: row for row in csv.DictReader(stream)}
    row = rows.get(args.candidate_id)
    if row is None:
        raise RuntimeError("candidate absent from frozen authority")
    week_start = int(row["start_index"])
    start = week_start + args.start_offset
    if args.lane == "canonical_h0" and args.start_offset != 0:
        raise RuntimeError("canonical h0 must start at offset 0")
    if args.lane == "restart_restore" and args.start_offset != 1:
        raise RuntimeError("restart restore must start at offset 1")

    source_auth_path = source_root / args.candidate_id / "R13_RESTART_SOURCE_AUTHORITY.json"
    source_auth = json.loads(source_auth_path.read_text(encoding="utf-8"))
    if source_auth.get("status") != "PASS" or source_auth.get("controller_burn_in_steps") != 0:
        raise RuntimeError("R13 source authority is not zero-burn-in PASS")
    power_path = Path(source_auth["power"]["path"])
    price_path = Path(source_auth["price"]["path"])
    if r12_module.sha256(power_path) != source_auth["power"]["sha256"]:
        raise RuntimeError("power source SHA drift")
    if r12_module.sha256(price_path) != source_auth["price"]["sha256"]:
        raise RuntimeError("price source SHA drift")
    power = r12_module.load_npz_slice(power_path, args.start_offset, 1)
    price = r12_module.load_npz_slice(price_path, args.start_offset, 1)

    mobility_auth = json.loads(
        (mobility_root / "R13_RESTART_MOBILITY_AUTHORITY.json").read_text(encoding="utf-8")
    )
    index = mobility_root / "R13_RESTART_MOBILITY_INDEX.csv"
    if mobility_auth.get("status") != "PASS" or mobility_auth.get("artifact_issue_count") != 8:
        raise RuntimeError("R13 mobility authority is not PASS")
    if mobility_auth.get("index_sha256") != r12_module.sha256(index):
        raise RuntimeError("R13 mobility index SHA drift")
    index_rows = list(csv.DictReader(index.open(encoding="utf-8", newline="")))
    selected = [entry for entry in index_rows if int(entry["issue_step"]) == start]
    if len(selected) != 1:
        raise RuntimeError("R13 mobility row coverage drift")
    selected[0]["path"] = str(mobility_root / selected[0]["file"])
    if r12_module.sha256(Path(selected[0]["path"])) != selected[0]["sha256"]:
        raise RuntimeError("R13 mobility artifact SHA drift")
    runtime_index = result_dir / "R13_RUNTIME_INDEX_ACTIVE.csv"
    with runtime_index.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[key for key in selected[0] if key != "path"])
        writer.writeheader(); writer.writerow({key: value for key, value in selected[0].items() if key != "path"})
    bank = mobility_root / "E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
    if mobility_auth.get("template_bank_sha256") != r12_module.sha256(bank):
        raise RuntimeError("template bank SHA drift")

    init_record = json.loads(initializer.read_text(encoding="utf-8"))
    if int(init_record["state"]["issue_step"]) != start:
        raise RuntimeError("initializer issue axis mismatch")
    if init_record["state"].get("future_plans_persisted") is not False:
        raise RuntimeError("initializer persists future plans")

    legacy.START_ISSUE = start
    legacy.END_ISSUE = start
    legacy.ISSUE_COUNT = 1
    legacy.validate_science_manifest(repo)
    sys.path.insert(0, str(repo / "science"))
    old_env = os.environ.copy()
    restore = lambda: None
    temporary = Path(tempfile.mkdtemp(prefix="r13_coldstart_runner_"))
    try:
        r12_module.preload_kkt_certified_decomposition(repo, result_dir)
        science = generic.load_locked_science(repo)
        r12_module.install_full_year_rack_binding(science, base, result_dir, start, 1)
        production_main = r12_module.transform_science(legacy, science, result_dir)
        restore = r12_module.configure_bindings(
            legacy, science, power, price, {start: selected[0]}, bank, result_dir, start, 1
        )
        work = base / "stage7_r13_zero_burnin_runs" / args.candidate_id
        run_root = work / args.lane
        run_root.mkdir(parents=True, exist_ok=True)
        records = legacy.scan_contiguous(run_root)
        resume_issue = start + len(records)
        if resume_issue > start:
            return 0
        legacy.quarantine_incomplete(
            run_root, resume_issue, work / "interrupted_attempts" / args.lane
        )
        control_root = work / "lane_control" / args.lane
        resume, state_hash = r12_module.representative_week_resume_authority(
            legacy, initializer, run_root, start, resume_issue, control_root
        )
        env = r12_module.build_runtime_env(
            legacy, start, 1, resume_issue, resume, state_hash, runtime_index
        )
        os.environ.clear(); os.environ.update(env)
        legacy.deep_preflight(production_main, science, base, result_dir)
        boundary = json.loads(
            (result_dir / "C_STAGE7_DEEP_PREFLIGHT_BUILD_FULL_BOUNDARY.json").read_text(encoding="utf-8")
        )
        if boundary.get("issue") != start or boundary.get("solver_executed") is not False:
            raise RuntimeError("production build_full boundary preflight failed")
        preflight = {
            "schema_version": "conversation_c.stage7.r13.coldstart_preflight.v1",
            "status": "PASS_RESTORED_NEXT_PRE" if args.lane == "restart_restore" else "PASS_READY_FOR_ONE_H0",
            "candidate_id": args.candidate_id,
            "lane": args.lane,
            "issue_step": start,
            "causal_frame_pre_state_hash": state_hash,
            "production_build_full_boundary_reached": True,
            "controller_burn_in_steps": 0,
            "solver_executed": False,
            "opendss_executed": False,
            "future_actual_used": False,
            "future_D2_reinjected": False,
            "future_plans_persisted": False,
        }
        write_json(result_dir / "R13_COLDSTART_PREFLIGHT_RESULT.json", preflight)
        if args.preflight_only:
            print(json.dumps(preflight, indent=2, sort_keys=True))
            return 0

        os.environ.clear(); os.environ.update(env)
        rc = int(production_main(run_root, base))
        records = legacy.scan_contiguous(run_root)
        complete = rc == 0 and len(records) == 1
        result = {
            "schema_version": "conversation_c.stage7.r13.one_h0_result.v1",
            "status": "PASS" if complete else "INCOMPLETE_OR_FAIL_CLOSED_RESUMABLE",
            "candidate_id": args.candidate_id,
            "lane": args.lane,
            "issue_step": start,
            "verified_issue_count": len(records),
            "child_return_code": rc,
            "controller_burn_in_steps": 0,
            "controller_transitions_executed": 1 if complete else len(records),
            "gurobi_executed": True,
            "opendss_executed": True,
            "future_actual_used": False,
            "future_D2_reinjected": False,
            "future_plans_persisted": False,
            "run_root": str(run_root),
        }
        write_json(result_dir / "R13_ONE_H0_RUN_RESULT.json", result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if complete else 2
    finally:
        restore()
        os.environ.clear(); os.environ.update(old_env)
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
