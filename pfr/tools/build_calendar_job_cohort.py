"""Materialize a frozen calendar-period job cohort on the global 2025 issue axis."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from math import ceil
from pathlib import Path

import pandas as pd

from pfr.tools.build_january_job_cohort import CANONICAL_SHA256


GLOBAL_EPOCH = pd.Timestamp("2024-12-31T14:00:00Z")
STEP_SECONDS = 300


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def fixed_aest_utc(day: date) -> pd.Timestamp:
    local = datetime.combine(day, time.min, tzinfo=timezone(timedelta(hours=10)))
    return pd.Timestamp(local.astimezone(timezone.utc))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authority-output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.days <= 31:
        parser.error("--days must be in [1, 31]")
    if sha256(args.canonical) != CANONICAL_SHA256:
        raise RuntimeError("canonical Kestrel F30 SHA drift")

    canonical = pd.read_parquet(args.canonical)
    start = fixed_aest_utc(args.start_date)
    end = fixed_aest_utc(args.start_date + timedelta(days=args.days))
    arrivals = pd.to_datetime(canonical["arrival_timestamp_ns"], unit="us", utc=True)
    latest_start = pd.to_datetime(
        canonical["latest_start_timestamp_ns"], unit="us", utc=True
    )
    completion = pd.to_datetime(
        canonical["latest_completion_timestamp_ns"], unit="us", utc=True
    )
    mask = (
        (arrivals >= start)
        & (arrivals < end)
        & canonical["job_power_prefreeze_authorized"].fillna(False).astype(bool)
        & canonical["scheduler_wan_valid"].fillna(False).astype(bool)
        & canonical["rack_power_valid"].fillna(False).astype(bool)
        & canonical["origin_IDC_id"].notna()
        & canonical["requested_gpu"].notna()
    )
    selected = canonical.loc[
        mask, ["job_uid", "origin_IDC_id", "requested_gpu"]
    ].copy()
    selected["arrival_step"] = (
        (arrivals.loc[mask] - GLOBAL_EPOCH).dt.total_seconds()
    ).map(lambda value: int(ceil(value / STEP_SECONDS)))
    selected["latest_start_step"] = (
        (latest_start.loc[mask] - GLOBAL_EPOCH).dt.total_seconds() // STEP_SECONDS
    ).astype(int)
    selected["latest_start_step"] = selected[
        ["arrival_step", "latest_start_step"]
    ].max(axis=1)
    selected["latest_completion_step"] = (
        (completion.loc[mask] - GLOBAL_EPOCH).dt.total_seconds() // STEP_SECONDS
    ).astype(int)
    period_first = int((start - GLOBAL_EPOCH).total_seconds() // STEP_SECONDS)
    period_last = period_first + args.days * 288 - 1
    selected = selected[selected["arrival_step"] <= period_last].copy()
    selected["requested_gpu"] = selected["requested_gpu"].astype(int)
    selected["job_uid"] = selected["job_uid"].astype(str)
    selected = selected.sort_values(["arrival_step", "job_uid"]).reset_index(drop=True)
    if selected["job_uid"].duplicated().any():
        raise RuntimeError("calendar cohort job_uid is not unique")
    if not selected["arrival_step"].between(period_first, period_last).all():
        raise RuntimeError("calendar cohort arrival escaped the frozen period")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.authority_output.parent.mkdir(parents=True, exist_ok=True)
    selected.to_parquet(args.output, index=False)
    authority = {
        "schema_version": "PFR_CALENDAR_JOB_COHORT_V13_13",
        "status": "PASS",
        "campaign_id": args.campaign_id,
        "calendar_timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        "calendar_start_utc": str(start),
        "calendar_end_exclusive_utc": str(end),
        "global_issue_first": period_first,
        "global_issue_last": period_last,
        "five_minute_issue_count": args.days * 288,
        "authorized_valid_rows": int(len(selected)),
        "synthetic_date_shift": False,
        "cross_day_state_carryover": False,
        "day_end_unfinished_job_policy": "RIGHT_CENSORED_NOT_CARRIED",
        "canonical_source_sha256": CANONICAL_SHA256,
        "cohort_sha256": sha256(args.output),
    }
    atomic_write_json(args.authority_output, authority)
    print(json.dumps({"status": "PASS", "rows": len(selected), **authority}))


if __name__ == "__main__":
    main()
