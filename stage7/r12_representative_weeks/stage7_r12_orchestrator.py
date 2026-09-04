#!/usr/bin/env python3
"""Bounded 4x4 execution and fail-closed final validation for Stage 7 R12."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from validate_r12_stage7 import (
    compare_initializer_endpoints,
    read_json,
    validate_lane,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def week_rows(authority: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with (authority / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    ids = [row["candidate_id"] for row in rows]
    if len(ids) != 12 or len(set(ids)) != 12:
        raise RuntimeError("R12 requires exactly 12 representative weeks")
    return ids, {row["candidate_id"]: row for row in rows}


def initializer_rows(authority: Path) -> dict[tuple[str, str], dict]:
    record = read_json(authority / "C_STAGE7_R12_INITIALIZER_AUTHORITY.json")
    if record.get("status") != "FROZEN_BEFORE_CONTROLLER_OUTCOMES":
        raise RuntimeError("R12 initializer authority is not frozen")
    result = {(row["candidate_id"], row["kind"]): row for row in record["files"]}
    if len(result) != 24:
        raise RuntimeError("R12 initializer file matrix drift")
    for row in result.values():
        path = authority / row["path"]
        if not path.is_file() or sha256(path) != row["file_sha256"]:
            raise RuntimeError(f"R12 initializer SHA drift: {path}")
    return result


def verify_sources(args, candidates: list[str]) -> list[dict]:
    source_root = Path(args.source_root).resolve()
    common = Path(args.common_mobility_cache).resolve()
    cache_authority = read_json(common / "R12_COMMON_MOBILITY_CACHE_AUTHORITY.json")
    if cache_authority.get("status") != "PASS" or int(cache_authority.get("issue_count", -1)) != 6912:
        raise RuntimeError("R12 common mobility cache is not 6,912-issue PASS")
    index = common / "R12_COMMON_MOBILITY_INDEX.csv"
    if cache_authority.get("index_sha256") != sha256(index):
        raise RuntimeError("R12 common mobility index SHA drift")
    bank = common / "E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
    if cache_authority.get("template_bank_sha256") != sha256(bank):
        raise RuntimeError("R12 common mobility template-bank SHA drift")
    mobility_rows = list(csv.DictReader(index.open(encoding="utf-8", newline="")))
    if len(mobility_rows) != 6912 or len({int(row["issue_step"]) for row in mobility_rows}) != 6912:
        raise RuntimeError("R12 common mobility index coverage drift")
    for row in mobility_rows:
        artifact = common / row["file"]
        if not artifact.is_file():
            raise RuntimeError(f"R12 common mobility artifact missing: {artifact}")
    source_results = []
    for candidate in candidates:
        authority_path = source_root / candidate / "R12_EPISODE_SOURCE_AUTHORITY.json"
        record = read_json(authority_path)
        if record.get("status") != "PASS" or record.get("candidate_id") != candidate:
            raise RuntimeError(f"R12 episode source is not PASS: {candidate}")
        if record.get("future_actual_used") is not False or record.get("pilot_splice_used") is not False:
            raise RuntimeError(f"R12 source causality failure: {candidate}")
        for section in ("power", "price"):
            path = Path(record[section]["path"])
            if not path.is_file() or sha256(path) != record[section]["sha256"]:
                raise RuntimeError(f"R12 {candidate} {section} SHA drift")
        source_results.append({
            "candidate_id": candidate,
            "authority_path": str(authority_path),
            "authority_sha256": sha256(authority_path),
            "issue_count": 576,
            "status": "PASS",
        })
    return source_results


def reject_competing_heavy_processes() -> None:
    current = os.getpid()
    output = subprocess.run(
        ["ps", "-eo", "pid=,args="], check=True, text=True, capture_output=True
    ).stdout
    needles = (
        "driver_r25r_stage1",
        "driver_r25s_stage1",
        "driver_r25t_stage1",
        "stage7_r11_monthly_runner.py",
        "stage7_r12_burnin_runner.py",
    )
    conflicts = []
    for line in output.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2:
            continue
        pid, command = int(fields[0]), fields[1]
        if pid != current and any(needle in command for needle in needles):
            conflicts.append({"pid": pid, "command": command})
    if conflicts:
        raise RuntimeError(f"competing heavy process detected: {conflicts}")


def lane_spec(mode: str) -> tuple[str, str, int, int]:
    if mode == "canonical":
        return "canonical", "canonical", 0, 576
    if mode == "restart":
        return "checkpoint_restart", "restart", 288, 288
    if mode == "initializer":
        return "independent_initializer", "initializer", 0, 576
    raise RuntimeError(mode)


def command_for(args, candidate: str, lane: str, lane_kind: str, offset: int, count: int,
                result_dir: Path, initializers: dict[tuple[str, str], dict], burn_in_start: int) -> list[str]:
    if lane_kind == "restart":
        initializer = (
            Path(args.base_work).resolve()
            / "stage7_r12_representative_week_runs"
            / candidate
            / "canonical"
            / f"issue_{burn_in_start + offset - 1:06d}"
            / "BUILD7C_POSTCOMMIT_STATE.json"
        )
        if not initializer.is_file():
            raise RuntimeError(f"canonical checkpoint missing before restart: {initializer}")
    else:
        initializer_kind = "t3_assigned" if lane_kind == "initializer" else "canonical"
        initializer = Path(args.authority_root).resolve() / initializers[(candidate, initializer_kind)]["path"]
    return [
        sys.executable,
        str(Path(args.runner).resolve()),
        "--legacy-runner", str(Path(args.legacy_runner).resolve()),
        "--repo", str(Path(args.repo).resolve()),
        "--base-work", str(Path(args.base_work).resolve()),
        "--authority-root", str(Path(args.authority_root).resolve()),
        "--episode-source", str(Path(args.source_root).resolve() / candidate),
        "--common-mobility-cache", str(Path(args.common_mobility_cache).resolve()),
        "--candidate-id", candidate,
        "--initializer", str(initializer),
        "--lane-kind", lane_kind,
        "--result-dir", str(result_dir),
        "--downloads", str(Path(args.downloads).resolve()),
        "--artifact-root", str(Path(args.artifact_root).resolve()),
        "--run-count", str(count),
        "--start-offset", str(offset),
        "--run-root-name", lane,
    ]


def run_candidate(args, candidate: str, lane: str, lane_kind: str, offset: int, count: int,
                  stamp: str, initializers: dict[tuple[str, str], dict], start: int) -> dict:
    result_dir = Path(args.result_root).resolve() / candidate / lane
    result_dir.mkdir(parents=True, exist_ok=True)
    log_dir = Path(args.result_root).resolve() / "logs" / candidate
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{lane}_{count}_{stamp}.log"
    command = command_for(args, candidate, lane, lane_kind, offset, count, result_dir, initializers, start)
    started = datetime.now(timezone.utc).isoformat()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, text=True)
    run_root = Path(args.base_work).resolve() / "stage7_r12_representative_week_runs" / candidate / lane
    verified = 0
    for issue in range(start + offset, start + offset + count):
        issue_root = run_root / f"issue_{issue:06d}"
        if not (
            (issue_root / "BUILD7C_POSTCOMMIT_STATE.json").is_file()
            and (issue_root / "BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json").is_file()
            and (issue_root / "ConversationA_BUILD7C_R12R1_CERTIFIED_GAP_ACCEPTANCE.json").is_file()
        ):
            break
        verified += 1
    return {
        "candidate_id": candidate,
        "lane": lane,
        "lane_kind": lane_kind,
        "configured_issue_count": count,
        "start_offset": offset,
        "return_code": process.returncode,
        "verified_issue_count": verified,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "log_path": str(log_path),
        "log_sha256": sha256(log_path),
        "status": "PASS" if process.returncode == 0 and verified == count else "INCOMPLETE_OR_FAIL_CLOSED",
    }


def run_bounded(args, candidates: list[str], rows: dict[str, dict[str, str]]) -> int:
    if not 1 <= args.concurrency <= 4:
        raise RuntimeError("R12 concurrency must be 1..4")
    source_results = verify_sources(args, candidates)
    initializers = initializer_rows(Path(args.authority_root).resolve())
    reject_competing_heavy_processes()
    lane, lane_kind, offset, count = lane_spec(args.mode)
    lock_path = Path(args.base_work).resolve() / "locks/stage7_r12_actual.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    progress_path = Path(args.result_root).resolve() / f"R12_{lane}_{offset}_{count}_PROGRESS.json"
    completed = []
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"R12 Stage 7 runtime lock is held: {lock_path}") from exc
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {
                executor.submit(
                    run_candidate, args, candidate, lane, lane_kind, offset, count, stamp,
                    initializers, int(rows[candidate]["burn_in_start_index"]),
                ): candidate
                for candidate in candidates
            }
            for future in concurrent.futures.as_completed(futures):
                candidate = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"candidate_id": candidate, "status": "FAIL_CLOSED", "error": repr(exc)}
                completed.append(result)
                write_json(progress_path, {
                    "status": "RUNNING",
                    "mode": args.mode,
                    "source_results": source_results,
                    "completed": sorted(completed, key=lambda item: item["candidate_id"]),
                })
    passed = len(completed) == len(candidates) and all(row.get("status") == "PASS" for row in completed)
    write_json(progress_path, {
        "status": "PASS" if passed else "INCOMPLETE_OR_FAIL_CLOSED_RESUMABLE",
        "mode": args.mode,
        "source_results": source_results,
        "completed": sorted(completed, key=lambda item: item["candidate_id"]),
    })
    return 0 if passed else 2


def final_validate(args, candidates: list[str], rows: dict[str, dict[str, str]]) -> int:
    authority = Path(args.authority_root).resolve()
    all_ids, _ = week_rows(authority)
    if candidates != all_ids:
        raise RuntimeError("R12 final validation requires all 12 frozen weeks in frozen order")
    source_results = verify_sources(args, candidates)
    initializers = initializer_rows(authority)
    base = Path(args.base_work).resolve()
    results = []
    for candidate in candidates:
        start = int(rows[candidate]["burn_in_start_index"])
        run_base = base / "stage7_r12_representative_week_runs" / candidate
        canonical_root = run_base / "canonical"
        restart_root = run_base / "checkpoint_restart"
        initializer_root = run_base / "independent_initializer"
        canonical = validate_lane(canonical_root, start, 576)
        restart = validate_lane(restart_root, start + 288, 288)
        invocation_root = run_base / "lane_control/checkpoint_restart/invocations"
        invocation_rows = [read_json(path) for path in sorted(invocation_root.glob("*.json"))]
        invocations = [
            row for row in invocation_rows
            if row.get("status") == "FINISHED"
            and row.get("child_return_code") == 0
            and int(row.get("resume_issue", -1)) == start + 288
            and int(row.get("configured_issue_count", -1)) == 288
            and int(row.get("verified_issue_count_after_invocation", -1)) == 288
        ]
        if not invocations:
            raise RuntimeError(f"R12 restart invocation evidence missing: {candidate}")
        if canonical["final_state_sha256"] != restart["final_state_sha256"]:
            raise RuntimeError(f"R12 restart endpoint hash mismatch: {candidate}")
        canonical_initializer = read_json(authority / initializers[(candidate, "canonical")]["path"])
        assigned_initializer = read_json(authority / initializers[(candidate, "t3_assigned")]["path"])
        canonical_pre = read_json(canonical_root / f"issue_{start:06d}/BUILD7C_PRECOMMIT_STATE.json")
        restart_pre = read_json(restart_root / f"issue_{start + 288:06d}/BUILD7C_PRECOMMIT_STATE.json")
        canonical_checkpoint = read_json(canonical_root / f"issue_{start + 287:06d}/BUILD7C_POSTCOMMIT_STATE.json")
        initializer_pre = read_json(initializer_root / f"issue_{start:06d}/BUILD7C_PRECOMMIT_STATE.json")
        if canonical_pre["sha256"] != canonical_initializer["sha256"]:
            raise RuntimeError(f"R12 canonical initializer binding mismatch: {candidate}")
        if restart_pre["sha256"] != canonical_checkpoint["sha256"]:
            raise RuntimeError(f"R12 restart checkpoint binding mismatch: {candidate}")
        if initializer_pre["sha256"] != assigned_initializer["sha256"]:
            raise RuntimeError(f"R12 independent initializer binding mismatch: {candidate}")
        washout = compare_initializer_endpoints(canonical_root, initializer_root, start, 576, 1e-6)
        result = {
            "status": "PASS",
            "candidate_id": candidate,
            "burn_in_start_index": start,
            "evaluation_start_index": int(rows[candidate]["start_index"]),
            "canonical": canonical,
            "checkpoint_restart": restart,
            "checkpoint_restart_hash_exact": True,
            "checkpoint_restart_finished_invocations": len(invocations),
            "checkpoint_reused_from_canonical_step": 288,
            "initializer_equivalence": washout,
            "evaluation_steps_executed": 0,
        }
        write_json(Path(args.result_root).resolve() / candidate / "R12_STAGE7_EPISODE_VALIDATION.json", result)
        results.append(result)
    final = {
        "schema_version": "conversation_c.stage7.r12.final_validation.v1",
        "status": "PASS",
        "C_stage7_complete": True,
        "representative_weeks_passed": len(results),
        "representative_weeks_required": 12,
        "canonical_burnins_passed": 12,
        "checkpoint_restart_pairs_passed": 12,
        "restart_candidate_transition_count": 3456,
        "independent_initializer_pairs_passed": 12,
        "evaluation_steps_executed": 0,
        "lazy_prefetch_pass_gate": False,
        "month_boundary_validation_used": False,
        "old_132_lane_matrix_used": False,
        "future_actual_used": False,
        "future_plans_persisted": False,
        "source_results": source_results,
        "episode_results": results,
    }
    output = Path(args.result_root).resolve() / "R12_STAGE7_FINAL_VALIDATION.json"
    write_json(output, final)
    print(json.dumps(final, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=(
        "canonical", "restart", "initializer", "final-validate"
    ))
    parser.add_argument("--runner", required=True)
    parser.add_argument("--legacy-runner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base-work", required=True)
    parser.add_argument("--authority-root", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--common-mobility-cache", required=True)
    parser.add_argument("--result-root", required=True)
    parser.add_argument("--downloads", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--candidate-ids", nargs="*", default=[])
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    all_ids, rows = week_rows(Path(args.authority_root).resolve())
    candidates = list(args.candidate_ids) if args.candidate_ids else all_ids
    if len(candidates) != len(set(candidates)) or any(candidate not in all_ids for candidate in candidates):
        raise RuntimeError("invalid or duplicate R12 candidate selection")
    if args.mode == "final-validate":
        return final_validate(args, candidates, rows)
    return run_bounded(args, candidates, rows)


if __name__ == "__main__":
    raise SystemExit(main())
