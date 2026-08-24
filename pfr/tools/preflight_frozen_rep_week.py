"""Read-only fail-closed preflight for a frozen February/March period."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
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
    args = parser.parse_args()

    contract_path = (
        args.repo / "pfr/contracts/FROZEN_2025_REP_WEEK_VALIDATION_PERIODS_V1.json"
    )
    scale_path = args.repo / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    scale = json.loads(scale_path.read_text(encoding="utf-8"))
    matches = [row for row in contract["periods"] if row["period_id"] == args.period_id]
    if len(matches) != 1:
        raise RuntimeError("period is not present exactly once in frozen authority")
    period = matches[0]
    first = int(period["global_issue_first"])
    last = int(period["global_issue_last"])
    expected = set(range(first, last + 1))

    shared_authority_path = args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"
    shared_authority = json.loads(shared_authority_path.read_text(encoding="utf-8"))
    authority_ok = bool(
        sha256(shared_authority_path) == period["shared_exogenous_authority_sha256"]
        and shared_authority.get("status") == "PASS"
        and shared_authority.get("candidate_id") == args.period_id
        and shared_authority.get("future_actual_used_by_optimizer") is False
        and int(shared_authority.get("scored_issue_first", -1)) == first
        and int(shared_authority.get("scored_issue_last", -1)) == last
    )

    power_counts: Counter[int] = Counter()
    for path in sorted((args.shared_root / "power_price").glob("**/power__issues.npy")):
        power_counts.update(int(value) for value in np.load(path, allow_pickle=False))
    missing_power = sorted(expected - set(power_counts))
    duplicate_power = sorted(issue for issue in expected if power_counts[issue] != 1)

    mobility_issues = {
        int(path.stem.split("_")[1])
        for path in (args.shared_root / "mobility/mobility_runtime").glob("issue_*.npz")
    }
    missing_mobility = sorted(expected - mobility_issues)

    template_path = args.shared_root / "mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
    template = pd.read_parquet(template_path)
    template_ok = all(f"u{index:03d}" in template.columns for index in range(129))

    pre_path = args.input_root / "pre/DAILY_CANONICAL_PRE_MANIFEST.json"
    jobs_path = args.input_root / "jobs/INDEPENDENT_JOB_COHORT.parquet"
    jobs_authority_path = (
        args.input_root / "jobs/INDEPENDENT_JOB_COHORT_AUTHORITY.json"
    )
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    jobs = pd.read_parquet(jobs_path, columns=["arrival_step"])
    jobs_in_range = bool(
        jobs.empty
        or (
            int(jobs["arrival_step"].min()) >= first
            and int(jobs["arrival_step"].max()) <= last
        )
    )
    jobs_authority = json.loads(jobs_authority_path.read_text(encoding="utf-8"))
    days = int(period["days"])
    expected_dates = {
        row["calendar_date"]
        for row in pre.get("episodes", ())
        if isinstance(row, dict) and "calendar_date" in row
    }
    daily_pre_ok = bool(
        pre.get("status") == "PASS"
        and len(pre.get("calendar_dates", ())) == days
        and len(expected_dates) == days
        and int(pre.get("daily_episode_count", -1)) == days * 8
        and len(pre.get("episodes", ())) == days * 8
        and all(
            row.get("daily_state_reset") is True
            and row.get("cross_day_state_carryover") is False
            and int(row.get("controller_burn_in_steps", -1)) == 0
            for row in pre.get("episodes", ())
        )
    )
    jobs_ok = bool(
        jobs_in_range
        and jobs_authority.get("status") == "PASS"
        and jobs_authority.get("campaign_id") == args.period_id
        and int(jobs_authority.get("global_issue_first", -1)) == first
        and int(jobs_authority.get("global_issue_last", -1)) == last
        and jobs_authority.get("cohort_sha256") == sha256(jobs_path)
        and jobs_authority.get("cross_day_state_carryover") is False
    )
    scale_ok = bool(
        scale.get("status") == "FROZEN_POST_HOC_P100_FEEDER_SCALE"
        and scale.get("scientific_authority_version")
        == contract.get("physical_execution_authority_version")
        and abs(float(scale.get("alpha_grid")) - 7100.2615 / 9490.53) <= 1e-15
    )

    checks = {
        "shared_authority": authority_ok,
        "power_issue_exact_coverage": not missing_power and not duplicate_power,
        "mobility_issue_coverage": not missing_mobility,
        "template_bank": template_ok,
        "daily_pre": daily_pre_ok,
        "job_cohort": jobs_ok,
        "feeder_scale_contract": scale_ok,
    }
    status = "PASS" if all(checks.values()) else "FAIL_CLOSED"
    report = {
        "schema_version": "FROZEN_REP_WEEK_PREFLIGHT_V13_13",
        "status": status,
        "period_id": args.period_id,
        "global_issue_first": first,
        "global_issue_last": last,
        "expected_issue_count": len(expected),
        "checks": checks,
        "missing_power_issues": missing_power,
        "duplicate_power_issues": duplicate_power,
        "missing_mobility_issues": missing_mobility,
        "mobility_artifact_count": len(mobility_issues),
        "job_count": len(jobs),
        "feeder_absolute_scale_alpha": float(scale["alpha_grid"]),
        "source_hashes": {
            "period_contract": sha256(contract_path),
            "shared_authority": sha256(shared_authority_path),
            "daily_pre": sha256(pre_path),
            "jobs": sha256(jobs_path),
            "jobs_authority": sha256(jobs_authority_path),
            "template_bank": sha256(template_path),
            "feeder_scale_contract": sha256(scale_path),
        },
    }
    write_report(args.report, report)
    print(json.dumps({"status": status, "report": str(args.report)}), flush=True)
    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
