"""Materialize the source-timestamped January 2025 independent job cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
from math import ceil
from pathlib import Path

import pandas as pd


CANONICAL_SHA256 = "0fe9399ece73e4e6906d036f3322697bd3c73b1498cf3e9c49b836631e19c98f"
EPOCH = pd.Timestamp("2024-12-31T14:00:00Z")
END = pd.Timestamp("2025-01-31T14:00:00Z")
STEP_SECONDS = 300


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize(canonical: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    required = {
        "job_uid", "origin_IDC_id", "arrival_timestamp_ns",
        "latest_start_timestamp_ns", "latest_completion_timestamp_ns",
        "requested_gpu", "job_power_prefreeze_authorized", "scheduler_wan_valid",
        "rack_power_valid",
    }
    missing = sorted(required - set(canonical.columns))
    if missing:
        raise ValueError(f"canonical workload missing columns: {missing}")
    arrivals = pd.to_datetime(canonical["arrival_timestamp_ns"], unit="us", utc=True)
    latest_start = pd.to_datetime(canonical["latest_start_timestamp_ns"], unit="us", utc=True)
    completion = pd.to_datetime(canonical["latest_completion_timestamp_ns"], unit="us", utc=True)
    mask = (
        (arrivals >= EPOCH)
        & (arrivals < END)
        & canonical["job_power_prefreeze_authorized"].fillna(False).astype(bool)
        & canonical["scheduler_wan_valid"].fillna(False).astype(bool)
        & canonical["rack_power_valid"].fillna(False).astype(bool)
        & canonical["origin_IDC_id"].notna()
        & canonical["requested_gpu"].notna()
    )
    selected = canonical.loc[mask, ["job_uid", "origin_IDC_id", "requested_gpu"]].copy()
    arrival_seconds = (arrivals.loc[mask] - EPOCH).dt.total_seconds()
    latest_seconds = (latest_start.loc[mask] - EPOCH).dt.total_seconds()
    completion_seconds = (completion.loc[mask] - EPOCH).dt.total_seconds()
    selected["arrival_step"] = arrival_seconds.map(
        lambda value: int(ceil(value / STEP_SECONDS))
    )
    selected["latest_start_step"] = (latest_seconds // STEP_SECONDS).astype(int)
    selected["latest_start_step"] = selected[["arrival_step", "latest_start_step"]].max(axis=1)
    selected["latest_completion_step"] = (completion_seconds // STEP_SECONDS).astype(int)
    quantized_after_period = selected["arrival_step"] >= 31 * 288
    selected = selected.loc[~quantized_after_period].copy()
    selected["requested_gpu"] = selected["requested_gpu"].astype(int)
    selected["job_uid"] = selected["job_uid"].astype(str)
    selected = selected.sort_values(["arrival_step", "job_uid"]).reset_index(drop=True)
    if selected["job_uid"].duplicated().any():
        raise ValueError("January cohort job_uid is not unique")
    if not selected["arrival_step"].between(0, 31 * 288 - 1).all():
        raise ValueError("January arrival escaped the 31-day issue range")
    if (selected["latest_start_step"] < selected["arrival_step"]).any():
        raise ValueError("latest start precedes arrival")
    if (selected["latest_completion_step"] <= selected["arrival_step"]).any():
        raise ValueError("completion deadline does not follow arrival")
    audit = {
        "schema_version": "PFR_JAN2025_INDEPENDENT_JOB_COHORT_V13_2",
        "status": "PASS",
        "timestamp_storage_unit": "microseconds_since_epoch_despite_legacy_ns_suffix",
        "calendar_timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        "calendar_start_utc": str(EPOCH),
        "calendar_end_exclusive_utc": str(END),
        "timestamp_quantization": {
            "arrival": "CEIL_TO_FIVE_MINUTE_ISSUE",
            "latest_start": "FLOOR_TO_FIVE_MINUTE_ISSUE",
            "latest_completion": "FLOOR_TO_FIVE_MINUTE_ISSUE"
        },
        "five_minute_issue_count": 31 * 288,
        "source_january_arrival_rows": int(((arrivals >= EPOCH) & (arrivals < END)).sum()),
        "authorized_valid_rows": int(len(selected)),
        "quantized_after_period_excluded_rows": int(quantized_after_period.sum()),
        "synthetic_date_shift": False,
        "cross_day_state_carryover": False,
        "day_end_unfinished_job_policy": "RIGHT_CENSORED_NOT_CARRIED",
    }
    return selected, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authority-output", type=Path, required=True)
    args = parser.parse_args()
    if sha256(args.canonical) != CANONICAL_SHA256:
        raise RuntimeError("canonical Kestrel F30 SHA drift")
    cohort, audit = materialize(pd.read_parquet(args.canonical))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cohort.to_parquet(args.output, index=False)
    audit["canonical_source_sha256"] = CANONICAL_SHA256
    audit["cohort_sha256"] = sha256(args.output)
    args.authority_output.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "rows": len(cohort), "output": str(args.output)}))


if __name__ == "__main__":
    main()
