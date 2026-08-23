"""Fail closed before a scientific campaign can leave preprocessing."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from pfr.methods import ComparisonMethod, ExperimentAuthority, MethodFactory
from pfr.migration import load_migration_authority


def git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ("git", "-C", str(repo), *args),
        check=True,
        capture_output=True,
        text=True,
    )
    return process.stdout.strip()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--expected-full-commit-sha", required=True)
    parser.add_argument("--expected-branch", required=True)
    parser.add_argument("--migration-authority", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    observed_commit = git(repo, "rev-parse", "HEAD")
    observed_branch = git(repo, "branch", "--show-current")
    porcelain = git(repo, "status", "--porcelain")
    authority = load_migration_authority(args.migration_authority.resolve())
    hashes = tuple(format(index, "064x") for index in range(1, 8))
    factory = MethodFactory(ExperimentAuthority(*hashes))
    b7 = factory.create(ComparisonMethod.B7)
    b8 = factory.create(ComparisonMethod.B8)
    common_capabilities = (
        "energy_flexibility",
        "temporal_workload_shift",
        "spatial_workload_migration",
        "risk_interface",
        "ai_training_aware",
        "joint_uncertainty",
        "slow_fast_control",
        "ac_safety_filter",
        "authority_fingerprint",
    )
    b7_b8_common = all(
        getattr(b7, name) == getattr(b8, name) for name in common_capabilities
    )
    passed = bool(
        len(args.expected_full_commit_sha) == 40
        and observed_commit == args.expected_full_commit_sha
        and observed_branch == args.expected_branch
        and not porcelain
        and authority.checkpoint_payload_occupancy_factor == 1.0
        and authority.sensitivity_factors == (0.25, 0.5, 1.0)
        and b7_b8_common
        and b7.control_mode == "EVENT_TRIGGERED"
        and b8.control_mode == "PERIODIC_MPC"
        and b8.periodic_replan_steps == 1
    )
    report = {
        "status": "PASS" if passed else "ABORT_MAIN_CAMPAIGN",
        "expected_full_commit_sha": args.expected_full_commit_sha,
        "observed_full_commit_sha": observed_commit,
        "expected_branch": args.expected_branch,
        "observed_branch": observed_branch,
        "git_worktree_clean": not porcelain,
        "migration_contract_sha256": authority.contract_fingerprint,
        "migration_parameterization_sha256": authority.fingerprint,
        "checkpoint_payload_occupancy_factor": (
            authority.checkpoint_payload_occupancy_factor
        ),
        "b7_b8_common_capabilities": b7_b8_common,
        "b7_control_mode": b7.control_mode,
        "b8_control_mode": b8.control_mode,
        "b8_periodic_replan_steps": b8.periodic_replan_steps,
    }
    atomic_write_json(args.report, report)
    print(json.dumps(report), flush=True)
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
