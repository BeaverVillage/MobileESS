"""Five-minute IT and weather forcing construction for Melbourne transfer."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .contracts import FIXED_AEST
from .psychrometrics import relative_humidity_from_dewpoint, wet_bulb_temperature_c


FROZEN_C0_PCC_PEAK_MW = 0.5288087919579648
FROZEN_C0_IT_PEAK_MW = FROZEN_C0_PCC_PEAK_MW / 1.30


def five_minute_axis(day: date) -> pd.DatetimeIndex:
    """Return the 288-slot operating axis in fixed AEST."""
    start = pd.Timestamp(datetime.combine(day, time.min, tzinfo=FIXED_AEST))
    return pd.date_range(start, periods=288, freq="5min")


def frozen_it_profile_5min(profile_csv: Path, day: date) -> pd.DataFrame:
    """Interpolate frozen V22SR1 dimensionless shape to 5 min and preserve C0 peak."""
    source = pd.read_csv(profile_csv)
    subset = source[source["reference_date"] == str(day)].sort_values("slot_15min")
    if len(subset) != 96:
        raise ValueError(f"missing frozen 96-slot shape for {day}")
    global_peak = float(source["normalized_shape_factor"].max())
    source_minutes = subset["slot_15min"].to_numpy(dtype=float) * 15.0
    target_minutes = np.arange(288, dtype=float) * 5.0
    factor = np.interp(target_minutes, source_minutes, subset["normalized_shape_factor"].to_numpy(dtype=float))
    it_mw = FROZEN_C0_IT_PEAK_MW * factor / global_peak
    return pd.DataFrame({"ts_aest": five_minute_axis(day), "it_mw": it_mw, "shape_factor": factor})


def interpolate_weather_5min(
    hourly: pd.DataFrame, start_utc: pd.Timestamp, end_utc: pd.Timestamp
) -> pd.DataFrame:
    """Linearly interpolate T/dew/pressure/wind components to a 5-min forcing grid."""
    source = hourly.copy()
    timestamp = "valid_time_utc" if "valid_time_utc" in source else "ts"
    source[timestamp] = pd.to_datetime(source[timestamp], utc=True)
    source = source.set_index(timestamp).sort_index()
    pad_start = start_utc.floor("h") - pd.Timedelta(hours=1)
    pad_end = end_utc.ceil("h") + pd.Timedelta(hours=1)
    source = source.loc[(source.index >= pad_start) & (source.index <= pad_end)].copy()
    if "u10_mps" not in source:
        radians = np.deg2rad(source["wind_direction_deg"].astype(float))
        source["u10_mps"] = -source["wind_speed_mps"].astype(float) * np.sin(radians)
        source["v10_mps"] = -source["wind_speed_mps"].astype(float) * np.cos(radians)
    target = pd.date_range(start_utc, end_utc, freq="5min")
    columns = ["t_db_c", "t_dew_c", "pressure_pa", "u10_mps", "v10_mps"]
    union = source[columns].reindex(source.index.union(target)).sort_index().interpolate(method="time", limit_area="inside")
    result = union.reindex(target).copy()
    if result.isna().any().any():
        raise ValueError("weather interpolation lacks bracketing observations")
    result["rh_pct"] = relative_humidity_from_dewpoint(result["t_db_c"], result["t_dew_c"])
    result["t_wb_c"] = wet_bulb_temperature_c(result["t_db_c"], result["rh_pct"], result["pressure_pa"])
    result["wind_speed_mps"] = np.sqrt(result["u10_mps"] ** 2 + result["v10_mps"] ** 2)
    result.index.name = "ts_utc"
    return result.reset_index()


def causal_forecast_with_warmup(
    actual: pd.DataFrame,
    forecast_day: pd.DataFrame,
    day: date,
    warmup_hours: int,
) -> pd.DataFrame:
    """Build causal warm-up: actual through cutoff, then available forecast bridge."""
    day_start = pd.Timestamp(datetime.combine(day, time.min, tzinfo=FIXED_AEST)).tz_convert("UTC")
    cutoff = day_start - pd.Timedelta(hours=6)
    warm_start = day_start - pd.Timedelta(hours=warmup_hours)
    day_end = day_start + pd.Timedelta(hours=23, minutes=55)
    actual_part = interpolate_weather_5min(actual, warm_start, cutoff)
    forecast_part = interpolate_weather_5min(forecast_day, day_start, day_end)
    last_actual = actual_part.iloc[-1]
    first_forecast = forecast_part.iloc[0]
    bridge_axis = pd.date_range(cutoff + pd.Timedelta(minutes=5), day_start - pd.Timedelta(minutes=5), freq="5min")
    bridge = pd.DataFrame({"ts_utc": bridge_axis})
    for column in ["t_db_c", "t_dew_c", "pressure_pa", "u10_mps", "v10_mps"]:
        bridge[column] = np.linspace(float(last_actual[column]), float(first_forecast[column]), len(bridge_axis) + 2)[1:-1]
    bridge["rh_pct"] = relative_humidity_from_dewpoint(bridge["t_db_c"], bridge["t_dew_c"])
    bridge["t_wb_c"] = wet_bulb_temperature_c(bridge["t_db_c"], bridge["rh_pct"], bridge["pressure_pa"])
    bridge["wind_speed_mps"] = np.sqrt(bridge["u10_mps"] ** 2 + bridge["v10_mps"] ** 2)
    result = pd.concat([actual_part, bridge, forecast_part], ignore_index=True)
    result["forcing_label"] = "D1_CAUSAL_ACTUAL_TO_CUTOFF_THEN_GFS_06Z"
    return result
