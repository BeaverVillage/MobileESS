"""Reconstruct 2024 global workload residuals and recalibrate new spatial reserve."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from pfr.workload_uncertainty import WorkloadResidual, calibrate_daily_joint_workload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_mapping(path: Path, key: str, value: str) -> dict[str, float]:
    frame = pd.read_csv(path)
    return {str(row[key]): float(row[value]) for _, row in frame.iterrows()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--spatial-weights", type=Path, required=True)
    parser.add_argument("--power-component", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    weights = read_mapping(args.spatial_weights, "idc_id", "spatial_weight")
    power = pd.read_csv(args.power_component)
    adapters = power.groupby("idc_id")["incremental_it_kw_per_gpu"].first().astype(float).to_dict()
    total_capacity = float(power["installed_gpu_capacity"].sum())

    actual = pd.read_parquet(
        args.actual, columns=["timestamp_utc", "origin_fixed_active_gpus", "calibration_year"]
    )
    if set(actual["calibration_year"].astype(int)) != {2024}:
        raise RuntimeError("actual workload calibration axis is not 2024-only")
    actual_global = (
        actual.groupby("timestamp_utc", as_index=False)["origin_fixed_active_gpus"]
        .sum()
        .rename(columns={"timestamp_utc": "target_time_utc", "origin_fixed_active_gpus": "actual"})
    )

    parquet = pq.ParquetFile(args.forecast)
    partial: list[pd.DataFrame] = []
    columns = ["issue_time_utc", "target_time_utc", "lead_step", "forecast_gpu_q50"]
    for index in range(parquet.metadata.num_row_groups):
        frame = parquet.read_row_group(index, columns=columns).to_pandas()
        partial.append(
            frame.groupby(["issue_time_utc", "target_time_utc", "lead_step"], as_index=False)[
                "forecast_gpu_q50"
            ].sum()
        )
    forecast_global = (
        pd.concat(partial, ignore_index=True)
        .groupby(["issue_time_utc", "target_time_utc", "lead_step"], as_index=False)[
            "forecast_gpu_q50"
        ]
        .sum()
    )
    joined = forecast_global.merge(actual_global, on="target_time_utc", how="left", validate="many_to_one")
    if joined["actual"].isna().any():
        raise RuntimeError("forecast target lacks aligned 2024 actual workload")
    joined["issue_date"] = pd.to_datetime(joined["issue_time_utc"], utc=True).dt.date.astype(str)
    residuals = tuple(
        WorkloadResidual(row.issue_date, float(row.actual), float(row.forecast_gpu_q50), total_capacity)
        for row in joined.itertuples(index=False)
    )
    calibration = calibrate_daily_joint_workload(
        residuals,
        target_coverage=0.95,
        spatial_weights=weights,
        incremental_it_kw_per_gpu=adapters,
    )
    joined["normalized_score"] = (
        joined["actual"] - joined["forecast_gpu_q50"]
    ) / total_capacity
    daily = joined.groupby("issue_date", as_index=False)["normalized_score"].max()
    covered = int((daily["normalized_score"] <= calibration.normalized_daily_joint_quantile).sum())

    args.output_root.mkdir(parents=True, exist_ok=True)
    daily_path = args.output_root / "WORKLOAD_DAILY_BLOCK_MAX_RESIDUALS_2024.csv"
    daily.to_csv(daily_path, index=False, quoting=csv.QUOTE_MINIMAL)
    result = {
        "schema_version": "PFR3_WORKLOAD_UNCERTAINTY_V13_2",
        "status": "PASS",
        "calibration_year": 2024,
        "old_idc_residual_reused": False,
        "global_actual_reconstructed_by_sum": True,
        "global_q50_reconstructed_by_sum": True,
        "new_spatial_operator_applied_after_global_calibration": True,
        "joint_scope": "MAX_OVER_ALL_ISSUES_AND_48_LEADS_WITHIN_UTC_DATE",
        "target_coverage": calibration.target_coverage,
        "day_block_count": calibration.day_block_count,
        "finite_sample_rank": calibration.finite_sample_rank,
        "normalized_daily_joint_quantile": calibration.normalized_daily_joint_quantile,
        "empirical_daily_joint_coverage": covered / len(daily),
        "total_installed_gpu_capacity": total_capacity,
        "global_gpu_reserve": calibration.global_gpu_reserve,
        "idc_gpu_reserve": calibration.idc_gpu_reserve,
        "idc_incremental_it_reserve_kw": calibration.idc_incremental_it_reserve_kw,
        "no_2025_recalibration": True,
        "source_sha256": {
            "source_zip": sha256(args.source_zip),
            "actual": sha256(args.actual),
            "forecast": sha256(args.forecast),
            "spatial_weights": sha256(args.spatial_weights),
            "power_component": sha256(args.power_component),
            "daily_block_residuals": sha256(daily_path),
        },
    }
    output = args.output_root / "PFR3_WORKLOAD_UNCERTAINTY_V13_2.json"
    temporary = output.with_name(f"{output.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
