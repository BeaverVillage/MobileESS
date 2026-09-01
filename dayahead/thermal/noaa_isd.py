"""NOAA Global Hourly CSV decoder for Melbourne Airport actual weather."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .psychrometrics import relative_humidity_from_dewpoint, validate_psychrometrics, wet_bulb_temperature_c
from .utils import sha256_file


GOOD_QC = frozenset("01459M")


def _decode_pair(value: object, scale: float, sentinel: str) -> tuple[float, str | None]:
    """Decode ISD ``value,qc`` with explicit scale and missing sentinel."""
    if not isinstance(value, str) or not value:
        return np.nan, None
    parts = value.split(",")
    raw = parts[0]
    qc = parts[1] if len(parts) > 1 else None
    if raw.lstrip("+-") == sentinel or qc not in GOOD_QC:
        return np.nan, qc
    try:
        return float(raw) / scale, qc
    except ValueError:
        return np.nan, qc


def _decode_ma1(value: object) -> tuple[float, str | None, float, str | None]:
    """Decode MA1 altimeter and station pressure [hPa] per NOAA ISD spec."""
    if not isinstance(value, str) or not value:
        return np.nan, None, np.nan, None
    parts = value.split(",")
    if len(parts) < 4:
        return np.nan, None, np.nan, None
    alt = np.nan if parts[0] == "99999" or parts[1] not in GOOD_QC else float(parts[0]) / 10.0
    station = np.nan if parts[2] == "99999" or parts[3] not in GOOD_QC else float(parts[2]) / 10.0
    return alt, parts[1], station, parts[3]


def _decode_wnd(value: object) -> tuple[float, str | None, str | None, float, str | None]:
    """Decode WND direction [deg] and speed [m/s] per NOAA ISD spec."""
    if not isinstance(value, str) or not value:
        return np.nan, None, None, np.nan, None
    parts = value.split(",")
    if len(parts) < 5:
        return np.nan, None, None, np.nan, None
    direction = np.nan if parts[0] == "999" or parts[1] not in GOOD_QC else float(parts[0])
    speed = np.nan if parts[3] == "9999" or parts[4] not in GOOD_QC else float(parts[3]) / 10.0
    return direction, parts[1], parts[2], speed, parts[4]


def decode_global_hourly(path: Path) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Decode and hourly-deduplicate Melbourne actual weather in SI units."""
    raw = pd.read_csv(path, low_memory=False)
    if set(raw["STATION"].astype(str).unique()) != {"94866099999"}:
        raise ValueError("NOAA file is not exclusively station 94866099999")
    if not raw["NAME"].str.contains("MELBOURNE", case=False, na=False).all():
        raise ValueError("NOAA file is not Melbourne Airport")
    records: list[dict[str, Any]] = []
    for row in raw.itertuples(index=False):
        data = row._asdict()
        temp, temp_qc = _decode_pair(data.get("TMP"), 10.0, "9999")
        dew, dew_qc = _decode_pair(data.get("DEW"), 10.0, "9999")
        slp, slp_qc = _decode_pair(data.get("SLP"), 10.0, "99999")
        alt, alt_qc, station, station_qc = _decode_ma1(data.get("MA1"))
        direction, direction_qc, wind_type, speed, speed_qc = _decode_wnd(data.get("WND"))
        pressure_hpa = station if np.isfinite(station) else slp
        records.append(
            {
                "ts": pd.to_datetime(data["DATE"], utc=True),
                "t_db_c": temp,
                "t_db_qc": temp_qc,
                "t_dew_c": dew,
                "t_dew_qc": dew_qc,
                "slp_hpa": slp,
                "slp_qc": slp_qc,
                "altimeter_hpa": alt,
                "altimeter_qc": alt_qc,
                "station_pressure_hpa": station,
                "station_pressure_qc": station_qc,
                "pressure_hpa": pressure_hpa,
                "pressure_source": "MA1_STATION_PRESSURE" if np.isfinite(station) else "SLP_SEA_LEVEL",
                "wind_direction_deg": direction,
                "wind_direction_qc": direction_qc,
                "wind_type": wind_type,
                "wind_speed_mps": speed,
                "wind_speed_qc": speed_qc,
                "report_type": data.get("REPORT_TYPE"),
                "source": data.get("SOURCE"),
                "quality_control": data.get("QUALITY_CONTROL"),
            }
        )
    decoded = pd.DataFrame.from_records(records)
    decoded["complete"] = decoded[["t_db_c", "t_dew_c", "pressure_hpa", "wind_speed_mps"]].notna().sum(axis=1)
    decoded = (
        decoded.sort_values(["ts", "complete"], ascending=[True, False], kind="stable")
        .drop_duplicates("ts", keep="first")
        .drop(columns="complete")
        .sort_values("ts")
        .reset_index(drop=True)
    )
    valid_td = decoded["t_dew_c"] <= decoded["t_db_c"] + 0.2
    decoded.loc[~valid_td, "t_dew_c"] = np.nan
    decoded["rh_pct"] = relative_humidity_from_dewpoint(decoded["t_db_c"], decoded["t_dew_c"])
    decoded["pressure_pa"] = decoded["pressure_hpa"] * 100.0
    good = decoded[["t_db_c", "t_dew_c", "rh_pct", "pressure_pa"]].notna().all(axis=1)
    decoded["t_wb_c"] = np.nan
    decoded.loc[good, "t_wb_c"] = wet_bulb_temperature_c(
        decoded.loc[good, "t_db_c"], decoded.loc[good, "rh_pct"], decoded.loc[good, "pressure_pa"]
    )
    station_meta = {
        "artifact_id": "V24T_MELBOURNE_ACTUAL_WEATHER_AUTHORITY",
        "authority_label": "REALIZED_WEATHER_VALIDATION_AUTHORITY",
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "station_id": "94866099999",
        "name_values": sorted(raw["NAME"].dropna().unique().tolist()),
        "latitude": float(raw["LATITUDE"].iloc[0]),
        "longitude": float(raw["LONGITUDE"].iloc[0]),
        "elevation_m": float(raw["ELEVATION"].iloc[0]),
        "timestamp_start": decoded["ts"].min().isoformat(),
        "timestamp_end": decoded["ts"].max().isoformat(),
        "source_row_count": len(raw),
        "unique_timestamp_count": len(decoded),
        "duplicate_timestamp_removed_count": len(raw) - len(decoded),
        "decoded_variables": ["TMP", "DEW", "SLP", "MA1 station pressure", "WND", "derived RH", "derived wet bulb"],
        "d1_optimization_input": False,
    }
    psych_mask = decoded[["t_db_c", "t_dew_c", "rh_pct", "t_wb_c", "pressure_pa"]].notna().all(axis=1)
    audit = {
        "artifact_id": "V24T_NOAA_ISD_DECODE_AUDIT",
        "specification": "NOAA ISD format document, mandatory TMP/DEW/SLP/WND and additional MA1",
        "encoding": {
            "TMP": {"scale": 10, "unit": "degC", "missing": "+9999/-9999"},
            "DEW": {"scale": 10, "unit": "degC", "missing": "+9999/-9999"},
            "SLP": {"scale": 10, "unit": "hPa", "missing": "99999"},
            "MA1": {"fields": "altimeter,qc,station_pressure,qc", "scale": 10, "unit": "hPa", "missing": "99999"},
            "WND": {"fields": "direction,qc,type,speed,qc", "speed_scale": 10, "speed_unit": "m/s", "missing": ["999", "9999"]},
        },
        "quality_codes_accepted": sorted(GOOD_QC),
        "quality_fields_preserved": True,
        "missing_fraction": {c: float(decoded[c].isna().mean()) for c in ["t_db_c", "t_dew_c", "slp_hpa", "station_pressure_hpa", "pressure_hpa", "wind_speed_mps", "rh_pct", "t_wb_c"]},
        "pressure_priority": "MA1 station pressure > SLP sea-level pressure",
        "pressure_source_counts": decoded["pressure_source"].value_counts(dropna=False).to_dict(),
        "psychrometric_validation": validate_psychrometrics(
            decoded.loc[psych_mask, "t_db_c"], decoded.loc[psych_mask, "t_dew_c"],
            decoded.loc[psych_mask, "rh_pct"], decoded.loc[psych_mask, "t_wb_c"],
            decoded.loc[psych_mask, "pressure_pa"],
        ),
    }
    return decoded, station_meta, audit
