"""NLR outside-weather loading and schema audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .utils import sha256_file


WEATHER_UNITS = {
    "ts": "naive source timestamp; interpreted as UTC per NLR Influx export",
    "outdoor_air_temp": "degrees Fahrenheit",
    "outdoor_air_humidity": "relative humidity percent",
}


def load_nlr_weather(path: Path) -> pd.DataFrame:
    """Load NLR outside weather; source temperature remains degrees Fahrenheit."""
    frame = pd.read_parquet(path, columns=["ts", "outdoor_air_temp", "outdoor_air_humidity"])
    frame["ts"] = pd.to_datetime(frame["ts"], errors="coerce", utc=True)
    return frame.sort_values("ts", kind="stable").reset_index(drop=True)


def schema_audit(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    """Audit NLR weather timestamps, source units, gaps, and ranges."""
    ts = frame["ts"]
    unique = ts.dropna().drop_duplicates().sort_values()
    cadence = unique.diff().dt.total_seconds().dropna()
    mode = float(cadence.mode().iloc[0]) if not cadence.empty else None
    result: dict[str, Any] = {
        "artifact_id": "V24T_NLR_WEATHER_SCHEMA",
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "row_count": len(frame),
        "timestamp_start": unique.iloc[0].isoformat(),
        "timestamp_end": unique.iloc[-1].isoformat(),
        "timezone": "UTC_ASSUMED_FROM_NLR_INFLUX_EXPORT_NAIVE_SOURCE",
        "inferred_cadence_seconds": mode,
        "duplicate_timestamp_count": int(ts.duplicated().sum()),
        "missing_timestamp_count": int(ts.isna().sum()),
        "monotonic": bool(ts.is_monotonic_increasing),
        "column_units": WEATHER_UNITS,
        "quality_flags": "no dedicated quality columns; 1970 epoch sentinel removed",
        "columns": {},
    }
    for name in ("outdoor_air_temp", "outdoor_air_humidity"):
        values = pd.to_numeric(frame[name], errors="coerce")
        q = values.quantile([0.01, 0.5, 0.99])
        result["columns"][name] = {
            "missing_fraction": float(values.isna().mean()),
            "min": float(values.min()),
            "p01": float(q.loc[0.01]),
            "p50": float(q.loc[0.5]),
            "p99": float(q.loc[0.99]),
            "max": float(values.max()),
        }
    return result


def quality_filter(frame: pd.DataFrame) -> pd.DataFrame:
    """Return physical NLR outside weather with temperature converted to degC."""
    valid = frame.dropna(subset=["ts", "outdoor_air_temp", "outdoor_air_humidity"]).copy()
    valid = valid.loc[
        (valid["ts"].dt.year >= 2010)
        & valid["outdoor_air_temp"].between(-80, 140)
        & valid["outdoor_air_humidity"].between(0, 100)
    ]
    valid["t_db_c"] = (valid["outdoor_air_temp"] - 32.0) * 5.0 / 9.0
    valid["rh_pct"] = valid["outdoor_air_humidity"]
    return valid[["ts", "t_db_c", "rh_pct"]]
