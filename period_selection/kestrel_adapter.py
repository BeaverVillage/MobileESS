"""Reproduce the frozen F30 Job cohort and derive exogenous WAN demand."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


F30_SOURCE = Path(os.environ.get(
    "MOBILE_ESS_F30_SOURCE",
    "data/processed/kestrel_12idc_jobs_flexibility.parquet",
))
F30_SOURCE_SHA256 = "cce8be2fd20fda1191c0773e6a37786409e49e15e0a31444b024b71f7eb5233e"
F30_SOURCE_ROWS = 625_201
EXPECTED_2025_F30_ROWS = 59_901
CANONICAL_2025_PATH = Path(os.environ.get(
    "MOBILE_ESS_CANONICAL_2025_JOBS",
    "data/frozen/PER_JOB_RUNTIME_SOURCE_CANONICAL_V2044R5.parquet",
))
STEP_SECONDS = 300
AEST = timezone(timedelta(hours=10), name="AEST")


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_bounds(year: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(year=year, month=1, day=1, tz=AEST).tz_convert("UTC")
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz=AEST).tz_convert("UTC")
    return start, end


def load_f30_source(path: Path = F30_SOURCE, verify_hash: bool = True) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    source_sha = sha256_file(path) if verify_hash else None
    if verify_hash and source_sha != F30_SOURCE_SHA256:
        raise ValueError(f"F30 source SHA-256 mismatch: {source_sha}")
    columns = [
        "id", "job_id", "submit_time_utc", "start_time_utc", "end_time_utc",
        "runtime_s", "queue_wait_s_calc", "gpus_requested", "gpu_hours",
        "is_flexible_F30", "quality_status", "q_submit_present",
        "q_runtime_positive", "q_gpu_positive", "q_gpu_integer_like",
    ]
    frame = pd.read_parquet(path, columns=columns)
    if len(frame) != F30_SOURCE_ROWS:
        raise ValueError(f"F30 source row count {len(frame)} != {F30_SOURCE_ROWS}")
    calculated = (frame["runtime_s"] >= 30 * 60) & (frame["queue_wait_s_calc"] >= 15 * 60)
    mismatch = int((calculated != frame["is_flexible_F30"].astype(bool)).sum())
    if mismatch:
        raise ValueError(f"F30 flag differs from frozen rule in {mismatch} rows")
    audit = {
        "source_path": str(path),
        "source_sha256": source_sha,
        "source_rows": len(frame),
        "f30_rule": "runtime_s >= 1800 AND queue_wait_s_calc >= 900",
        "f30_flag_mismatch_rows": mismatch,
        "upstream_cleaning_contract": [
            "H100 partition", "COMPLETED state", "positive GPU",
            "valid submit/start/end order", "standby excluded", "deduplicated by id",
        ],
    }
    return frame, audit


def adapt_f30_year(source: pd.DataFrame, year: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    start, end = _utc_bounds(year)
    submit = pd.to_datetime(source["submit_time_utc"], utc=True)
    rule = (source["runtime_s"] >= 1800) & (source["queue_wait_s_calc"] >= 900)
    cohort = source.loc[rule & submit.ge(start) & submit.lt(end)].copy()
    cohort["submit_time_utc"] = pd.to_datetime(cohort["submit_time_utc"], utc=True)
    cohort["start_time_utc"] = pd.to_datetime(cohort["start_time_utc"], utc=True)
    cohort["end_time_utc"] = pd.to_datetime(cohort["end_time_utc"], utc=True)
    arrival_seconds = (cohort["submit_time_utc"] - start).dt.total_seconds().to_numpy(dtype=float)
    cohort["arrival_step"] = np.ceil(arrival_seconds / STEP_SECONDS).astype(np.int64)
    cohort["nonpreemptive_duration_steps"] = np.ceil(
        cohort["runtime_s"].to_numpy(dtype=float) / STEP_SECONDS
    ).astype(np.int64)
    latest_start = cohort["submit_time_utc"] + pd.Timedelta(minutes=30)
    cohort["latest_start_step"] = np.floor(
        (latest_start - start).dt.total_seconds().to_numpy(dtype=float) / STEP_SECONDS
    ).astype(np.int64)
    # The frozen F30 deadline is latest start plus the conservative, ceiled
    # non-preemptive duration.  Because the duration is an integer step count,
    # flooring the final timestamp is exactly floor(latest_start)+duration.
    cohort["latest_completion_step"] = (
        cohort["latest_start_step"] + cohort["nonpreemptive_duration_steps"]
    ).astype(np.int64)
    cohort["requested_gpu"] = cohort["gpus_requested"].astype(np.int64)
    cohort["arriving_gpuh"] = cohort["gpu_hours"].astype(float)
    cohort["arriving_wan_nominal_gb"] = cohort["arriving_gpuh"] * 3.0
    cohort["job_uid"] = cohort["id"].astype(str)
    output_columns = [
        "job_uid", "job_id", "submit_time_utc", "start_time_utc", "end_time_utc",
        "arrival_step", "nonpreemptive_duration_steps", "latest_start_step",
        "latest_completion_step", "requested_gpu", "runtime_s", "queue_wait_s_calc",
        "arriving_gpuh", "arriving_wan_nominal_gb",
    ]
    cohort = cohort[output_columns].sort_values(
        ["arrival_step", "submit_time_utc", "job_uid"], kind="stable"
    ).reset_index(drop=True)
    if cohort["job_uid"].nunique() != len(cohort):
        raise ValueError(f"{year} F30 cohort contains duplicate job_uid")
    if year == 2025 and len(cohort) != EXPECTED_2025_F30_ROWS:
        raise ValueError(f"2025 F30 reproduction {len(cohort)} != {EXPECTED_2025_F30_ROWS}")
    audit = {
        "year": year,
        "fixed_axis": "AEST UTC+10 no DST",
        "arrival_window_start_utc": start.isoformat(),
        "arrival_window_end_exclusive_utc": end.isoformat(),
        "rows": len(cohort),
        "unique_job_uid": int(cohort["job_uid"].nunique()),
        "arrival_quantization": "ceil_to_prevent_prearrival_execution",
        "duration_quantization": "ceil_source_seconds_to_5min",
        "latest_start_quantization": "floor_to_prevent_latest_start_violation",
        "latest_completion_quantization": "floor(latest_start + ceiled nonpreemptive duration)",
        "arrival_step_min": int(cohort["arrival_step"].min()) if len(cohort) else None,
        "arrival_step_max": int(cohort["arrival_step"].max()) if len(cohort) else None,
        "source_gpuh_total": float(cohort["arriving_gpuh"].sum()),
        "wan_nominal_gb_total": float(cohort["arriving_wan_nominal_gb"].sum()),
        "wan_contract": "source GPUh * 3 GB/GPUh",
        "reproduces_frozen_2025_count": year == 2025 and len(cohort) == EXPECTED_2025_F30_ROWS,
    }
    return cohort, audit


def aggregate_job_features(cohort: pd.DataFrame, year: int) -> pd.DataFrame:
    steps = (366 if year % 4 == 0 else 365) * 288
    index = cohort["arrival_step"].to_numpy(dtype=np.int64)
    if len(index) and (index.min() < 0 or index.max() >= steps):
        raise ValueError("arrival step outside fixed annual axis")

    def aggregate(values: np.ndarray | None = None) -> np.ndarray:
        weights = np.ones(len(cohort), dtype=float) if values is None else values
        return np.bincount(index, weights=weights, minlength=steps).astype(float)

    gpuh = cohort["arriving_gpuh"].to_numpy(dtype=float)
    frame = pd.DataFrame({
        "job_arrival_count": aggregate(),
        "arriving_gpu": aggregate(cohort["requested_gpu"].to_numpy(dtype=float)),
        "arriving_gpuh": aggregate(gpuh),
        "arriving_wan_nominal_gb": aggregate(gpuh * 3.0),
    })
    if not np.allclose(frame["arriving_wan_nominal_gb"], frame["arriving_gpuh"] * 3.0, rtol=0, atol=1e-10):
        raise AssertionError("WAN feature does not equal GPUh * 3")
    return frame


def write_years(source_path: Path, output_dir: Path, verify_hash: bool = True) -> dict[str, Any]:
    source, source_audit = load_f30_source(source_path, verify_hash)
    output_dir.mkdir(parents=True, exist_ok=True)
    audits = []
    artifacts: dict[str, dict[str, Any]] = {}
    canonical_parity: dict[str, Any] = {"checked": False}
    for year in (2024, 2025):
        cohort, audit = adapt_f30_year(source, year)
        cohort_path = output_dir / f"F30_JOBS_{year}_AEST.parquet"
        feature_path = output_dir / f"F30_JOB_WAN_FEATURES_{year}_5MIN.parquet"
        cohort.to_parquet(cohort_path, index=False, compression="zstd")
        features = aggregate_job_features(cohort, year)
        features.to_parquet(feature_path, index=False, compression="zstd")
        artifacts[cohort_path.name] = {"sha256": sha256_file(cohort_path), "rows": len(cohort)}
        artifacts[feature_path.name] = {"sha256": sha256_file(feature_path), "rows": len(features)}
        if year == 2025 and CANONICAL_2025_PATH.is_file():
            columns = [
                "job_uid", "arrival_step", "nonpreemptive_duration_steps",
                "latest_start_step", "latest_completion_step", "requested_gpu",
            ]
            frozen = pd.read_parquet(CANONICAL_2025_PATH, columns=columns)
            joined = cohort[columns].merge(frozen, on="job_uid", validate="one_to_one", suffixes=("_new", "_frozen"))
            mismatches = {
                name: int((joined[f"{name}_new"] != joined[f"{name}_frozen"]).sum())
                for name in columns[1:]
            }
            canonical_parity = {
                "checked": True,
                "canonical_path": str(CANONICAL_2025_PATH),
                "joined_rows": len(joined),
                "mismatch_rows_by_field": mismatches,
                "pass": len(joined) == EXPECTED_2025_F30_ROWS and not any(mismatches.values()),
            }
        audits.append(audit)
    payload = {
        "schema_version": "f30_same_adapter_2024_2025_v1",
        "source": source_audit,
        "years": audits,
        "artifacts": artifacts,
        "frozen_2025_rowwise_parity": canonical_parity,
    }
    (output_dir / "F30_ADAPTER_AUDIT_2024_2025.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=F30_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=Path("period_selection/output"))
    parser.add_argument("--skip-source-hash", action="store_true")
    args = parser.parse_args()
    payload = write_years(args.source, args.output_dir, not args.skip_source_hash)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
