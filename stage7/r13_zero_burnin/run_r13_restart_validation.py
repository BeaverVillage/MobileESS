#!/usr/bin/env python3
"""Run preregistered four-season h0 and clean-process restore checks."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


SELECTED = (
    ("W02_2025-01-13", 3456),
    ("W10_2025-03-10", 19584),
    ("W25_2025-06-23", 49824),
    ("W38_2025-09-22", 76032),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def command(args, candidate: str, initializer: Path, result: Path, lane: str, offset: int, preflight: bool):
    value = [
        sys.executable, str(args.runner.resolve()),
        "--r12-runner-core", str(args.r12_runner_core.resolve()),
        "--legacy-runner", str(args.legacy_runner.resolve()),
        "--generic-core", str(args.generic_core.resolve()),
        "--repo", str(args.repo.resolve()),
        "--base-work", str(args.base_work.resolve()),
        "--authority-root", str(args.authority_root.resolve()),
        "--source-root", str(args.source_root.resolve()),
        "--mobility-root", str(args.mobility_root.resolve()),
        "--candidate-id", candidate,
        "--initializer", str(initializer),
        "--result-dir", str(result),
        "--lane", lane,
        "--start-offset", str(offset),
    ]
    if preflight:
        value.append("--preflight-only")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--r12-runner-core", type=Path, required=True)
    parser.add_argument("--legacy-runner", type=Path, required=True)
    parser.add_argument("--generic-core", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base-work", type=Path, required=True)
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--mobility-root", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    authority = args.authority_root.resolve()
    result_root = args.result_root.resolve()
    lock_path = args.base_work.resolve() / "locks/stage7_r13_zero_burnin_actual.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f"R13 actual runtime lock is held: {lock_path}") from exc
    process_table = subprocess.run(
        ["ps", "-eo", "pid=,args="], check=True, text=True, capture_output=True
    ).stdout
    competing_needles = (
        "driver_r25r_stage1", "driver_r25s_stage1", "driver_r25t_stage1",
        "stage7_r11_monthly_runner.py", "stage7_r12_burnin_runner.py", "gurobi_cl",
    )
    conflicts = []
    for line in process_table.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2 or int(fields[0]) == os.getpid():
            continue
        if any(needle in fields[1] for needle in competing_needles):
            conflicts.append(line.strip())
    if conflicts:
        raise RuntimeError(f"competing heavy solver process detected: {conflicts}")
    rows = []
    for candidate, start in SELECTED:
        canonical_initializer = (
            authority / "INITIALIZER_BINDING/production_input"
            / f"{candidate}.resume_state.json"
        )
        canonical_result = result_root / candidate / "canonical_h0"
        subprocess.run(
            command(args, candidate, canonical_initializer, canonical_result, "canonical_h0", 0, args.preflight_only),
            check=True,
        )
        if args.preflight_only:
            rows.append({"candidate_id": candidate, "canonical_preflight": "PASS"})
            continue
        post = (
            args.base_work.resolve() / "stage7_r13_zero_burnin_runs" / candidate
            / "canonical_h0" / f"issue_{start:06d}" / "BUILD7C_POSTCOMMIT_STATE.json"
        )
        if not post.is_file():
            raise RuntimeError(f"canonical POST missing: {candidate}")
        post_record = json.loads(post.read_text(encoding="utf-8"))
        restore_result = result_root / candidate / "restart_restore"
        subprocess.run(
            command(args, candidate, post, restore_result, "restart_restore", 1, True),
            check=True,
        )
        restored = json.loads(
            (restore_result / "R13_COLDSTART_PREFLIGHT_RESULT.json").read_text(encoding="utf-8")
        )
        same = post_record["sha256"] == restored["causal_frame_pre_state_hash"]
        if not same:
            raise RuntimeError(f"POST/restarted PRE hash mismatch: {candidate}")
        checkpoint_copy = authority / "RESTART/checkpoints" / f"{candidate}.POST.json"
        checkpoint_copy.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_copy.write_bytes(post.read_bytes())
        rows.append({
            "candidate_id": candidate,
            "week_start_index": start,
            "canonical_post_sha256": post_record["sha256"],
            "restarted_next_pre_sha256": restored["causal_frame_pre_state_hash"],
            "hash_exact": same,
            "checkpoint_path": str(checkpoint_copy.relative_to(authority)).replace("\\", "/"),
            "checkpoint_file_sha256": sha256(checkpoint_copy),
            "h0_only_commit": True,
            "future_actual_used": False,
            "future_D2_reinjected": False,
            "future_plans_persisted": False,
            "gurobi_executed_transitions": 1,
            "opendss_executed_transitions": 1,
        })
    result = {
        "schema_version": "conversation_c.stage7.r13.restart_results.v1",
        "status": "PASS_PREFLIGHT_ONLY" if args.preflight_only else "PASS",
        "preregistered_count": 4,
        "pass_count": len(rows),
        "controller_burn_in_steps": 0,
        "total_controller_transitions_executed": 0 if args.preflight_only else 4,
        "results": rows,
    }
    name = "RESTART_PREFLIGHT_RESULTS.json" if args.preflight_only else "RESTART_RESULTS.json"
    write_json(authority / "RESTART" / name, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
