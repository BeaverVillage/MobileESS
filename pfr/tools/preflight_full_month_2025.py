"""Fail-closed preflight for a complete February or March 2025 campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from pfr.migration import load_migration_authority


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    parser.add_argument("--period-id", required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-unmaterialized", action="store_true")
    args = parser.parse_args()

    contract_path = (
        args.repo / "pfr/contracts/FROZEN_2025_FULL_MONTH_VALIDATION_PERIODS_V1.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    matches = [row for row in contract["periods"] if row["period_id"] == args.period_id]
    if len(matches) != 1:
        raise RuntimeError("full-month period is not present exactly once")
    period = matches[0]
    first = int(period["global_issue_first"])
    last = int(period["global_issue_last"])
    days = int(period["days"])

    plan_path = args.shared_root / "SOURCE_MATERIALIZATION_PLAN.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_ok = bool(
        plan.get("status") == "READY_TO_MATERIALIZE"
        and plan.get("period_id") == args.period_id
        and int(plan.get("scored_issue_count", -1)) == days * 288
        and all(plan.get("dependency_checks", {}).values())
    )

    pre_path = args.input_root / "pre/DAILY_CANONICAL_PRE_MANIFEST.json"
    jobs_path = args.input_root / "jobs/INDEPENDENT_JOB_COHORT.parquet"
    jobs_authority_path = args.input_root / "jobs/INDEPENDENT_JOB_COHORT_AUTHORITY.json"
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    jobs = pd.read_parquet(jobs_path, columns=["arrival_step"])
    jobs_authority = json.loads(jobs_authority_path.read_text(encoding="utf-8"))
    input_ok = bool(
        pre.get("status") == "PASS"
        and len(pre.get("calendar_dates", ())) == days
        and int(pre.get("daily_episode_count", -1)) == days * 8
        and len(pre.get("episodes", ())) == days * 8
        and all(
            row.get("daily_state_reset") is True
            and row.get("cross_day_state_carryover") is False
            for row in pre.get("episodes", ())
        )
        and jobs_authority.get("status") == "PASS"
        and jobs_authority.get("campaign_id") == args.period_id
        and int(jobs_authority.get("global_issue_first", -1)) == first
        and int(jobs_authority.get("global_issue_last", -1)) == last
        and jobs_authority.get("cohort_sha256") == sha256(jobs_path)
        and (
            jobs.empty
            or (
                int(jobs["arrival_step"].min()) >= first
                and int(jobs["arrival_step"].max()) <= last
            )
        )
    )

    authority_path = args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"
    source_ready = authority_path.is_file()
    source_checks: dict[str, bool] = {"authority_present": source_ready}
    authority_sha = None
    if source_ready:
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        authority_sha = sha256(authority_path)
        mobility_files = list(
            (args.shared_root / "mobility/mobility_runtime").glob("issue_*.npz")
        )
        mobility_issues = {int(path.name.split("_")[1]) for path in mobility_files}
        expected = set(range(first, last + 1))
        power_ranges = []
        for path in sorted((args.shared_root / "power_price").glob("block_*_*_*")):
            if path.is_dir():
                block = json.loads((path / "BLOCK_AUTHORITY.json").read_text(encoding="utf-8"))
                power_ranges.append((int(block["issue_first"]), int(block["issue_last"])))
        source_last = int(period["source_padding_issue_last"])
        power_issues = {
            issue
            for block_first, block_last in power_ranges
            for issue in range(block_first, block_last + 1)
            if first <= issue <= source_last
        }
        source_checks.update(
            {
                "authority_contract": bool(
                    authority.get("status") == "PASS"
                    and authority.get("candidate_id") == args.period_id
                    and int(authority.get("scored_issue_first", -1)) == first
                    and int(authority.get("scored_issue_last", -1)) == last
                    and authority.get("future_actual_used_by_optimizer") is False
                    and authority.get("period_contract_sha256") == sha256(contract_path)
                ),
                "mobility_exact_scored_coverage": mobility_issues == expected,
                "power_exact_scored_and_padding_coverage": power_issues
                == set(range(first, source_last + 1)),
                "template_bank": (
                    args.shared_root / "mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
                ).is_file(),
            }
        )
    source_ok = source_ready and all(source_checks.values())

    scale = json.loads(
        (args.repo / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json").read_text(
            encoding="utf-8"
        )
    )
    scale_ok = bool(
        scale.get("status") == "FROZEN_POST_HOC_P100_FEEDER_SCALE"
        and scale.get("scientific_authority_version")
        == contract.get("physical_execution_authority_version")
    )
    migration_authority = load_migration_authority(
        args.repo / "pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"
    )
    migration_ok = bool(
        migration_authority.authority_id
        == "PFR_IDC_MIGRATION_ABILENE12_H10080_V1"
        and migration_authority.checkpoint_interval_steps == 6
        and migration_authority.checkpoint_bytes_per_gpu == 80_000_000_000
        and migration_authority.restart_steps == 1
    )
    ready_to_run = plan_ok and input_ok and source_ok and scale_ok and migration_ok
    ready_to_materialize = (
        plan_ok and input_ok and scale_ok and migration_ok and not source_ready
    )
    status = (
        "PASS_READY_TO_RUN"
        if ready_to_run
        else (
            "READY_TO_MATERIALIZE_SOURCES"
            if args.allow_unmaterialized and ready_to_materialize
            else "FAIL_CLOSED"
        )
    )
    report = {
        "schema_version": "PFR_FULL_MONTH_PREFLIGHT_V13_13",
        "status": status,
        "period_id": args.period_id,
        "calendar_start": period["calendar_start"],
        "days": days,
        "expected_commit_markers": int(period["expected_commit_markers"]),
        "checks": {
            "materialization_plan": plan_ok,
            "daily_pre_and_jobs": input_ok,
            "source_ready": source_ok,
            "source": source_checks,
            "feeder_scale_contract": scale_ok,
            "migration_authority": migration_ok,
        },
        "job_count": len(jobs),
        "shared_authority_sha256": authority_sha,
        "migration_authority_sha256": migration_authority.fingerprint,
        "source_plan": str(plan_path),
    }
    atomic_write_json(args.report, report)
    print(json.dumps({"status": status, "report": str(args.report)}))
    if status == "FAIL_CLOSED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
