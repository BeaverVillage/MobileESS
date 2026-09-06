from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class TrajectoryResult:
    trajectory: pd.DataFrame
    audit: dict


def build(k5c2, k5a, cfg):
    year = int(cfg["analysis"]["year"])
    horizons = list(map(int, cfg["analysis"]["horizons_steps"]))
    maxstep = int(cfg["analysis"]["trajectory_steps"])
    persist = int(cfg["trajectory"]["persistence_steps"])

    f = pd.read_parquet(
        k5c2 / "outputs/idc_fixed_forecast_2025_long.parquet",
        columns=["timestamp_utc", "idc_id", "horizon_steps", "fixed_selected_prediction"],
    )
    f["timestamp_utc"] = pd.to_datetime(f.timestamp_utc, utc=True)
    f["idc_id"] = f.idc_id.astype(str)

    site = pd.read_parquet(
        k5a / "outputs/kestrel_12idc_5min_workload.parquet",
        columns=["timestamp_utc", "idc_id", "fixed_avg_active_gpus_F30"],
    )
    site["timestamp_utc"] = pd.to_datetime(site.timestamp_utc, utc=True)
    site["idc_id"] = site.idc_id.astype(str)
    site = site[site.timestamp_utc.dt.year.eq(year)]

    wide = (
        f.pivot_table(
            index=["timestamp_utc", "idc_id"],
            columns="horizon_steps",
            values="fixed_selected_prediction",
            aggfunc="first",
        )
        .reindex(columns=horizons)
        .reset_index()
    )
    x = (
        site.merge(wide, on=["timestamp_utc", "idc_id"], how="inner", validate="one_to_one")
        .sort_values(["timestamp_utc", "idc_id"])
        .reset_index(drop=True)
    )

    # Float32 is adequate for GPU-equivalent trajectories and halves the Parquet
    # footprint.  The origin column is deliberately serialized from the same
    # float32 array so the first three persistence steps are bit-identical.
    current = x.fixed_avg_active_gpus_F30.to_numpy(dtype=np.float32, copy=True)
    n = len(x)
    arr = np.zeros((n, maxstep), dtype=np.float32)
    arr[:, :persist] = current[:, None]

    knot_steps = [persist] + [h for h in horizons if h > persist]
    values = [current] + [x[h].to_numpy(dtype=np.float32, copy=True) for h in horizons if h > persist]
    for seg in range(len(knot_steps) - 1):
        a, b = knot_steps[seg], knot_steps[seg + 1]
        va, vb = values[seg], values[seg + 1]
        for k in range(a + 1, b + 1):
            arr[:, k - 1] = va + (vb - va) * np.float32((k - a) / (b - a))

    if cfg["trajectory"].get("nonnegative_clip", True):
        arr = np.maximum(arr, np.float32(0.0))

    out = pd.DataFrame(
        {
            "timestamp_utc": x["timestamp_utc"].to_numpy(),
            "idc_id": x["idc_id"].to_numpy(),
            "origin_fixed_active_gpus": current,
        }
    )
    for k in range(1, maxstep + 1):
        out[f"fixed_gpu_step_{k:02d}"] = arr[:, k - 1]

    knot_errors = {}
    for h in [z for z in horizons if z > persist]:
        knot_errors[str(h)] = float(
            np.max(np.abs(arr[:, h - 1].astype(np.float64) - x[h].to_numpy(dtype=np.float64)))
        )
    first_err = float(
        np.max(
            np.abs(
                arr[:, :persist].astype(np.float64)
                - out["origin_fixed_active_gpus"].to_numpy(dtype=np.float64)[:, None]
            )
        )
    )
    full_year_rows = site[["timestamp_utc", "idc_id"]].drop_duplicates().shape[0]
    forecast_grid_rows = wide[["timestamp_utc", "idc_id"]].drop_duplicates().shape[0]
    full_origin_count = int(site.timestamp_utc.nunique())
    forecast_origin_count = int(out.timestamp_utc.nunique())
    audit = {
        "rows": len(out),
        "expected_forecast_origin_site_rows": forecast_grid_rows,
        "full_year_origin_site_rows": full_year_rows,
        "excluded_tail_origin_count": full_origin_count - forecast_origin_count,
        "excluded_tail_minutes": (full_origin_count - forecast_origin_count) * int(cfg["analysis"].get("interval_minutes", 5)),
        "origin_start_utc": str(out.timestamp_utc.min()),
        "origin_end_utc": str(out.timestamp_utc.max()),
        "step_count": maxstep,
        "persistence_steps": persist,
        "persistence_max_error": first_err,
        "forecast_knot_max_errors": knot_errors,
        "minimum_prediction": float(arr.min()),
        "maximum_prediction": float(arr.max()),
        "site_count": int(out.idc_id.nunique()),
        "origin_count": int(out.timestamp_utc.nunique()),
        "storage_dtype": "float32",
        "method": (
            "actual per-site state for steps 1-3; piecewise-linear interpolation "
            "through 30/60/120/240-minute K5-B2 selected forecast knots"
        ),
    }
    return TrajectoryResult(out, audit)
