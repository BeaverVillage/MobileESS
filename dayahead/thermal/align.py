"""Native-cadence NLR power/weather alignment without pseudo-sample inflation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .psychrometrics import dewpoint_from_relative_humidity, validate_psychrometrics, wet_bulb_temperature_c


def align_nlr_native_minute(
    power: pd.DataFrame, weather: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Aggregate both jittered ~60 s NLR streams to observed 1-minute bins.

    Each output row requires at least one source observation from both streams;
    no interpolation, forward fill, or upsampling is performed.
    """
    pcols = [
        "it_power_kw", "cooling_kw", "hvac_kw", "pump_kw", "plug_and_light_kw",
        "pue", "facility_kw", "overhead_kw", "cooling_system_kw", "other_kw",
    ]
    wcols = ["t_db_c", "rh_pct"]
    p = power.set_index("ts")[pcols].resample("1min").mean().dropna()
    w = weather.set_index("ts")[wcols].resample("1min").mean().dropna()
    joined = p.join(w, how="inner").dropna().sort_index()
    joined["pressure_pa"] = 101325.0
    joined["t_dew_c"] = dewpoint_from_relative_humidity(joined["t_db_c"], joined["rh_pct"])
    joined["t_wb_c"] = wet_bulb_temperature_c(
        joined["t_db_c"], joined["rh_pct"], joined["pressure_pa"]
    )
    joined = joined.reset_index()
    psych = validate_psychrometrics(
        joined["t_db_c"], joined["t_dew_c"], joined["rh_pct"], joined["t_wb_c"], joined["pressure_pa"]
    )
    contract = {
        "artifact_id": "V24T_PSYCHROMETRIC_CONTRACT",
        "formula": "Buck 1981 saturation vapor pressure; inverse Magnus dewpoint; pressure-aware ventilated psychrometer equation solved by 32-step bounded bisection",
        "units": {"temperature": "degC", "relative_humidity": "percent", "pressure": "Pa"},
        "nlr_pressure_source": "standard atmosphere 101325 Pa because NLR outside parquet has no pressure",
        "melbourne_pressure_priority": "MA1 station pressure, then SLP sea-level pressure",
        "validation": psych,
    }
    audit = {
        "artifact_id": "V24T_NLR_ALIGNMENT_AUDIT",
        "power_native_cadence_seconds": 60,
        "weather_native_cadence_seconds": 60,
        "primary_fit_cadence_seconds": 60,
        "alignment_method": "observed samples averaged into 1-minute bins then inner join",
        "interpolation_count": 0,
        "pseudo_sample_count": 0,
        "row_count": len(joined),
        "timestamp_start": joined["ts"].iloc[0].isoformat(),
        "timestamp_end": joined["ts"].iloc[-1].isoformat(),
        "monotonic": bool(joined["ts"].is_monotonic_increasing),
        "duplicate_timestamp_count": int(joined["ts"].duplicated().sum()),
        "missing_fraction": {c: float(joined[c].isna().mean()) for c in joined.columns},
        "psychrometric_validation": psych,
    }
    return joined, contract, audit
