"""Forecast-quality diagnostics only: GFS D-1 versus NOAA actual weather."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import ARTIFACT_ROOT
from .utils import write_json


VARIABLES = {
    "t_db_c": "Tdb",
    "t_wb_c": "Twb",
    "rh_pct": "RH",
    "pressure_pa": "pressure",
    "wind_speed_mps": "wind_speed",
    "t_dew_c": "Tdew",
}


def _metrics(error: pd.Series) -> dict[str, float | int]:
    values = error.dropna().to_numpy(dtype=float)
    return {
        "n": len(values),
        "mae": float(np.mean(np.abs(values))) if len(values) else float("nan"),
        "rmse": float(np.sqrt(np.mean(values**2))) if len(values) else float("nan"),
        "bias": float(np.mean(values)) if len(values) else float("nan"),
    }


def validate_gfs_against_noaa(repo: Path) -> dict[str, Any]:
    """Compare forecast and realized weather without fitting thermal parameters."""
    root = repo / ARTIFACT_ROOT
    forecast = pd.read_parquet(root / "V24T_GFS_D1_FORECAST.parquet")
    actual = pd.read_parquet(root / "V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet")
    forecast["valid_time_utc"] = pd.to_datetime(forecast["valid_time_utc"], utc=True)
    actual["ts"] = pd.to_datetime(actual["ts"], utc=True)
    merged = forecast.merge(actual, left_on="valid_time_utc", right_on="ts", suffixes=("_gfs", "_noaa"), how="left")
    overall: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for column, label in VARIABLES.items():
        error = merged[f"{column}_gfs"] - merged[f"{column}_noaa"]
        overall[label] = _metrics(error)
        for lead, group in merged.assign(error=error).groupby("lead_hours"):
            rows.append({"variable": label, "lead_hours": int(lead), **_metrics(group["error"])})
    by_lead = pd.DataFrame(rows).sort_values(["variable", "lead_hours"])
    by_lead.to_csv(root / "V24T_GFS_VS_NOAA_BY_LEAD.csv", index=False)
    selected = by_lead[by_lead["lead_hours"].isin([8, 12, 18, 24, 30, 32])]
    report = {
        "artifact_id": "V24T_GFS_VS_NOAA_VALIDATION",
        "purpose": "weather forecast quality diagnostic only; excluded from thermal coefficient fitting",
        "joined_row_count": len(merged),
        "actual_match_count": int(merged["t_db_c_noaa"].notna().sum()),
        "overall": overall,
        "selected_leads": selected.to_dict(orient="records"),
        "thermal_parameter_fit_reads": 0,
    }
    write_json(root / "V24T_GFS_VS_NOAA_VALIDATION.json", report)
    return report


if __name__ == "__main__":
    validate_gfs_against_noaa(Path.cwd())
