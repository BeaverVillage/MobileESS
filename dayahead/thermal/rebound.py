"""Cooling/PCC lag and post-IT-peak rebound diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def rebound_diagnostic(frame: pd.DataFrame) -> dict[str, Any]:
    """Return peak times, lags [minutes], rebound power [kW], and energy [kWh]."""
    it_index = int(frame["it_kw"].to_numpy().argmax())
    cool_index = int(frame["overhead_raw_kw"].to_numpy().argmax())
    pcc_index = int(frame["pcc_kw"].to_numpy().argmax())
    after = frame.iloc[it_index:]
    cooling_rebound = max(0.0, float(after["overhead_raw_kw"].max() - frame["overhead_raw_kw"].iloc[it_index]))
    pcc_rebound = max(0.0, float(after["pcc_kw"].max() - frame["pcc_kw"].iloc[it_index]))
    baseline = float(frame["overhead_raw_kw"].iloc[it_index])
    rebound_energy = float(np.maximum(after["overhead_raw_kw"].to_numpy() - baseline, 0).sum() * 5.0 / 60.0)
    return {
        "it_peak_time": pd.Timestamp(frame["ts_aest"].iloc[it_index]).isoformat(),
        "cooling_peak_time": pd.Timestamp(frame["ts_aest"].iloc[cool_index]).isoformat(),
        "pcc_peak_time": pd.Timestamp(frame["ts_aest"].iloc[pcc_index]).isoformat(),
        "cooling_lag_minutes": 5 * (cool_index - it_index),
        "pcc_lag_minutes": 5 * (pcc_index - it_index),
        "peak_cooling_rebound_kw": cooling_rebound,
        "peak_pcc_rebound_kw": pcc_rebound,
        "rebound_energy_kwh": rebound_energy,
    }
