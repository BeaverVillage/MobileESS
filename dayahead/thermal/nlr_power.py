"""NLR ESIF power loading, schema audit, and component semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .utils import sha256_file


POWER_COLUMNS = (
    "ts",
    "cooling_kw",
    "energy_reuse",
    "ere",
    "hvac_kw",
    "it_power_kw",
    "plug_and_light_kw",
    "pue",
    "pump_kw",
)
POWER_UNITS = {
    "ts": "naive source timestamp; interpreted as UTC per NLR Influx export",
    "cooling_kw": "kW",
    "hvac_kw": "kW",
    "it_power_kw": "kW",
    "plug_and_light_kw": "kW",
    "pump_kw": "kW",
    "pue": "dimensionless",
    "ere": "dimensionless",
    "energy_reuse": "source field; documented as energy reuse effectiveness",
}


def load_nlr_power(path: Path) -> pd.DataFrame:
    """Load NLR facility power with all electrical quantities in kW."""
    frame = pd.read_parquet(path, columns=list(POWER_COLUMNS))
    frame["ts"] = pd.to_datetime(frame["ts"], errors="coerce", utc=True)
    return frame.sort_values("ts", kind="stable").reset_index(drop=True)


def _numeric_summary(series: pd.Series) -> dict[str, float | None]:
    values = pd.to_numeric(series, errors="coerce")
    quant = values.quantile([0.01, 0.5, 0.99])
    return {
        "missing_fraction": float(values.isna().mean()),
        "min": float(values.min()) if values.notna().any() else None,
        "p01": float(quant.loc[0.01]) if values.notna().any() else None,
        "p50": float(quant.loc[0.5]) if values.notna().any() else None,
        "p99": float(quant.loc[0.99]) if values.notna().any() else None,
        "max": float(values.max()) if values.notna().any() else None,
    }


def schema_audit(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    """Audit NLR power timestamps, units, missingness, and numeric ranges."""
    ts = frame["ts"]
    unique = ts.dropna().drop_duplicates().sort_values()
    cadence = unique.diff().dt.total_seconds().dropna()
    mode = float(cadence.mode().iloc[0]) if not cadence.empty else None
    expected = int((unique.iloc[-1] - unique.iloc[0]).total_seconds() // mode + 1) if mode else 0
    return {
        "artifact_id": "V24T_NLR_POWER_SCHEMA",
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "row_count": len(frame),
        "timestamp_start": unique.iloc[0].isoformat(),
        "timestamp_end": unique.iloc[-1].isoformat(),
        "timezone": "UTC_ASSUMED_FROM_NLR_INFLUX_EXPORT_NAIVE_SOURCE",
        "inferred_cadence_seconds": mode,
        "duplicate_timestamp_count": int(ts.duplicated().sum()),
        "missing_timestamp_count": int(ts.isna().sum()),
        "estimated_missing_native_timestamp_count": max(0, expected - len(unique)),
        "monotonic": bool(ts.is_monotonic_increasing),
        "column_units": POWER_UNITS,
        "columns": {name: _numeric_summary(frame[name]) for name in POWER_COLUMNS if name != "ts"},
        "quality_flags": "no dedicated quality columns; physical filters reported in alignment audit",
    }


def quality_filter(frame: pd.DataFrame) -> pd.DataFrame:
    """Retain physically usable NLR power rows without clipping targets [kW]."""
    required = ["it_power_kw", "cooling_kw", "hvac_kw", "pump_kw", "plug_and_light_kw", "pue"]
    valid = frame.dropna(subset=["ts", *required]).copy()
    valid = valid.loc[
        (valid["it_power_kw"] > 0)
        & (valid["it_power_kw"] < 10_000)
        & (valid[required[1:5]] >= 0).all(axis=1)
        & valid["pue"].between(1.0, 3.0)
    ]
    return valid
