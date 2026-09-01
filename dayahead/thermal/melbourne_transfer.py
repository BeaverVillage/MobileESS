"""Transfer normalized NLR thermal response to Melbourne weather and IT shape."""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import ARTIFACT_ROOT, AUTHORIZED_DAYS, FIXED_AEST, NORMALIZATION_LABEL, TRANSFER_LABEL
from .marginal_pue import finite_difference_mpue
from .models.dynamic_state import DYNAMIC_FEATURE_NAMES, DynamicThermalModel, dynamic_feature_matrix
from .models.quasistatic import FEATURE_NAMES, QuasiStaticModel, feature_matrix, softplus
from .normalize import reference_pue_normalize
from .rebound import rebound_diagnostic
from .simulate import FROZEN_C0_PCC_PEAK_MW, causal_forecast_with_warmup, frozen_it_profile_5min, interpolate_weather_5min
from .utils import write_json


def _load_models(root: Path) -> tuple[QuasiStaticModel, DynamicThermalModel, tuple[float, float]]:
    c1 = json.loads((root / "V24T_C1_QUASISTATIC_MODEL.json").read_text(encoding="utf-8"))
    c2 = json.loads((root / "V24T_C2_DYNAMIC_MODEL.json").read_text(encoding="utf-8"))
    c1_model = QuasiStaticModel(tuple(float(c1["coefficients"][name]) for name in FEATURE_NAMES), float(c1["t_ref_c"]))
    # Preserve the identified time constant when moving from 1-minute fitting
    # to 5-minute simulation: rho_5min = rho_1min ** 5.
    c2_model = DynamicThermalModel(tuple(float(c2["coefficients"][name]) for name in DYNAMIC_FEATURE_NAMES), float(c2["rho"]) ** 5, 5.0)
    other = (float(c1["other_model_coefficients"]["intercept"]), float(c1["other_model_coefficients"]["it_mw"]))
    return c1_model, c2_model, other


def _other_kw(it_nlr_kw: np.ndarray, coefficients: tuple[float, float]) -> np.ndarray:
    return softplus(coefficients[0] + coefficients[1] * it_nlr_kw / 1000.0)


def _equivalent_nlr_it(it_mel_kw: np.ndarray, nlr_median_kw: float) -> np.ndarray:
    """Map only relative Melbourne load shape onto NLR median facility scale [kW]."""
    return nlr_median_kw * it_mel_kw / np.mean(it_mel_kw)


def _raw_case(
    model_name: str,
    it_mel_kw: np.ndarray,
    it_nlr_kw: np.ndarray,
    weather: pd.DataFrame,
    c1: QuasiStaticModel,
    c2: DynamicThermalModel,
    other_coefficients: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    other = _other_kw(it_nlr_kw, other_coefficients)
    if model_name == "C1":
        cool = c1.predict_cooling_kw(it_nlr_kw, weather["t_wb_c"], weather["rh_pct"])
        theta = np.full(len(cool), np.nan)
        x = feature_matrix(it_nlr_kw, weather["t_wb_c"], weather["rh_pct"], c1.t_ref_c)
        x_delta = feature_matrix(it_nlr_kw * 1.01, weather["t_wb_c"], weather["rh_pct"], c1.t_ref_c)
        cool_delta = softplus(x_delta @ np.asarray(c1.coefficients))
    else:
        x, theta_it, theta_tw = dynamic_feature_matrix(it_nlr_kw, weather["t_wb_c"], weather["rh_pct"], c2.rho)
        cool = softplus(x @ np.asarray(c2.coefficients))
        theta = theta_it + theta_tw / max(np.std(theta_tw), 1e-9)
        x_delta = x.copy()
        it_delta_mw = it_nlr_kw * 1.01 / 1000.0
        x_delta[:, 1] = it_delta_mw
        x_delta[:, 2] = it_delta_mw**2
        x_delta[:, 5] = it_delta_mw * weather["t_wb_c"].to_numpy()
        cool_delta = softplus(x_delta @ np.asarray(c2.coefficients))
    other_delta = _other_kw(it_nlr_kw * 1.01, other_coefficients)
    overhead = cool + other
    overhead_delta = cool_delta + other_delta
    return overhead, overhead_delta, cool, theta


def run_melbourne_transfer(repo: Path) -> dict[str, Any]:
    """Simulate C0/C1/C2 at 5 min for actual and causal D-1 weather."""
    root = repo / ARTIFACT_ROOT
    actual = pd.read_parquet(root / "V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet")
    gfs = pd.read_parquet(root / "V24T_GFS_D1_FORECAST.parquet")
    aligned = pd.read_parquet(root / "V24T_NLR_ALIGNED_THERMAL_DATASET.parquet", columns=["it_power_kw"])
    nlr_median_kw = float(aligned["it_power_kw"].median())
    c1, c2, other_coefficients = _load_models(root)
    profile_csv = repo / "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_PRIMARY_OPERATING_IT_PROFILE.csv"
    all_raw: dict[tuple[str, int, str], list[pd.DataFrame]] = {}
    warmups = (12, 24, 48)
    for weather_case in ("NOAA_ACTUAL", "GFS_D1"):
        for warmup in warmups:
            for model_name in ("C1", "C2"):
                all_raw[(weather_case, warmup, model_name)] = []
            for day in AUTHORIZED_DAYS:
                it_day = frozen_it_profile_5min(profile_csv, day)
                day_start_utc = it_day["ts_aest"].iloc[0].tz_convert("UTC")
                warm_start = day_start_utc - pd.Timedelta(hours=warmup)
                day_end_utc = it_day["ts_aest"].iloc[-1].tz_convert("UTC")
                if weather_case == "NOAA_ACTUAL":
                    weather = interpolate_weather_5min(actual, warm_start, day_end_utc)
                    weather["forcing_label"] = "INTERPOLATED_WEATHER_FORCING_NOAA_ACTUAL"
                else:
                    init_day = pd.Timestamp(day) - pd.Timedelta(days=1)
                    day_forecast = gfs[pd.to_datetime(gfs["initialization_utc"], utc=True).dt.date == init_day.date()]
                    weather = causal_forecast_with_warmup(actual, day_forecast, day, warmup)
                warm_slots = warmup * 12
                day_it_kw = it_day["it_mw"].to_numpy() * 1000.0
                repeat_count = int(np.ceil(warm_slots / len(day_it_kw))) + 1
                warm_it_kw = np.tile(day_it_kw, repeat_count)[-warm_slots:]
                full_it_mel = np.concatenate([warm_it_kw, day_it_kw])
                if len(weather) != len(full_it_mel):
                    raise AssertionError((weather_case, day, warmup, len(weather), len(full_it_mel)))
                full_it_nlr = _equivalent_nlr_it(full_it_mel, nlr_median_kw)
                for model_name in ("C1", "C2"):
                    overhead, overhead_delta, cool, theta = _raw_case(
                        model_name, full_it_mel, full_it_nlr, weather, c1, c2, other_coefficients
                    )
                    part = pd.DataFrame({
                        "day": str(day), "ts_aest": it_day["ts_aest"].to_numpy(),
                        "it_kw": day_it_kw, "it_nlr_equivalent_kw": full_it_nlr[warm_slots:],
                        "t_db_c": weather["t_db_c"].to_numpy()[warm_slots:],
                        "t_dew_c": weather["t_dew_c"].to_numpy()[warm_slots:],
                        "rh_pct": weather["rh_pct"].to_numpy()[warm_slots:],
                        "t_wb_c": weather["t_wb_c"].to_numpy()[warm_slots:],
                        "pressure_pa": weather["pressure_pa"].to_numpy()[warm_slots:],
                        "overhead_raw_kw": overhead[warm_slots:],
                        "overhead_raw_delta_kw": overhead_delta[warm_slots:],
                        "cooling_raw_kw": cool[warm_slots:], "theta": theta[warm_slots:],
                    })
                    all_raw[(weather_case, warmup, model_name)].append(part)
    profiles: list[pd.DataFrame] = []
    normalization_audits: dict[str, Any] = {}
    marginal_rows: list[pd.DataFrame] = []
    rebound_rows: list[dict[str, Any]] = []
    for key, parts in all_raw.items():
        weather_case, warmup, model_name = key
        frame = pd.concat(parts, ignore_index=True)
        raw_ratio = frame["overhead_raw_kw"].to_numpy() / frame["it_nlr_equivalent_kw"].to_numpy()
        overhead_shape_on_melbourne_kw = frame["it_kw"].to_numpy() * raw_ratio
        pue, pcc, audit = reference_pue_normalize(frame["it_kw"], overhead_shape_on_melbourne_kw)
        norm_factor = float(audit["normalization_factor"])
        overhead_delta_eq = frame["overhead_raw_delta_kw"].to_numpy() * norm_factor * frame["it_kw"].to_numpy() * 1.01 / (frame["it_nlr_equivalent_kw"].to_numpy() * 1.01)
        # Equivalent normalized PCC uses the Melbourne IT boundary exactly once.
        pcc_delta = frame["it_kw"].to_numpy() * 1.01 + overhead_delta_eq
        mpue = finite_difference_mpue(frame["it_kw"], pcc, pcc_delta)
        frame["weather_case"] = weather_case
        frame["warmup_hours"] = warmup
        frame["model"] = model_name
        frame["pue"] = pue
        frame["pcc_kw"] = pcc
        frame["mpue"] = mpue
        frame["overhead_eq_kw"] = pcc - frame["it_kw"]
        profiles.append(frame)
        marginal_rows.append(frame[["day", "ts_aest", "weather_case", "warmup_hours", "model", "pue", "mpue", "it_kw"]])
        normalization_audits[f"{weather_case}_{warmup}h_{model_name}"] = audit
        if warmup == 24:
            for day, group in frame.groupby("day"):
                rebound_rows.append({"weather_case": weather_case, "model": model_name, "day": day, **rebound_diagnostic(group.reset_index(drop=True))})
    dynamic = pd.concat(profiles, ignore_index=True)
    c0 = dynamic[(dynamic["weather_case"] == "NOAA_ACTUAL") & (dynamic["warmup_hours"] == 24) & (dynamic["model"] == "C1")][["day", "ts_aest", "it_kw"]].copy()
    c0["weather_case"] = "WEATHER_INDEPENDENT"
    c0["warmup_hours"] = 24
    c0["model"] = "C0"
    c0["pue"] = 1.30
    c0["pcc_kw"] = 1.30 * c0["it_kw"]
    c0["mpue"] = 1.30
    c0["overhead_eq_kw"] = 0.30 * c0["it_kw"]
    c0["overhead_raw_kw"] = c0["overhead_eq_kw"]
    dynamic_out = pd.concat([c0, dynamic], ignore_index=True, sort=False)
    dynamic_out.to_csv(root / "V24T_DYNAMIC_PUE_PROFILE.csv", index=False)
    pd.concat(marginal_rows, ignore_index=True).to_csv(root / "V24T_MARGINAL_PUE_PROFILE.csv", index=False)
    write_json(root / "V24T_REFERENCE_PUE_NORMALIZATION.json", {
        "artifact_id": "V24T_REFERENCE_PUE_NORMALIZATION", "label": NORMALIZATION_LABEL,
        "audits": normalization_audits, "double_pue_count": 0, "extra_1p30_multiplier_count": 0,
    })
    summaries: dict[str, Any] = {}
    for (weather_case, warmup, model), group in dynamic.groupby(["weather_case", "warmup_hours", "model"]):
        summaries[f"{weather_case}_{warmup}h_{model}"] = {
            "pue_min": float(group["pue"].min()), "pue_p05": float(group["pue"].quantile(.05)),
            "pue_p50": float(group["pue"].median()), "pue_p95": float(group["pue"].quantile(.95)),
            "pue_max": float(group["pue"].max()),
            "it_weighted_mean_pue": float(np.sum(group["it_kw"] * group["pue"]) / np.sum(group["it_kw"])),
            "mpue_p05": float(group["mpue"].quantile(.05)), "mpue_p50": float(group["mpue"].median()),
            "mpue_p95": float(group["mpue"].quantile(.95)), "mpue_peak": float(group["mpue"].max()),
            "pcc_peak_mw": float(group["pcc_kw"].max() / 1000.0),
        }
    transfer = {
        "artifact_id": "V24T_MELBOURNE_THERMAL_TRANSFER", "label": TRANSFER_LABEL,
        "not_a_measured_melbourne_cooling_model": True,
        "nlr_absolute_size_transfer": False,
        "load_mapping": "Melbourne dimensionless IT shape mapped to NLR median IT only for response evaluation; normalized overhead shape then applied to frozen Melbourne-equivalent IT",
        "weather_resolution": "INTERPOLATED_WEATHER_FORCING at 5 minutes",
        "summaries": summaries,
    }
    write_json(root / "V24T_MELBOURNE_THERMAL_TRANSFER.json", transfer)
    # Pre-registered engineering step/shift diagnostic: +20% IT for one hour,
    # then return to baseline. It is diagnostic only and never enters fitting.
    step_slots = 72
    step_start, step_end = 12, 24
    base_nlr = np.full(step_slots, nlr_median_kw)
    shifted_nlr = base_nlr.copy()
    shifted_nlr[step_start:step_end] *= 1.20
    step_weather = pd.DataFrame({"t_wb_c": np.full(step_slots, float(actual["t_wb_c"].median())), "rh_pct": np.full(step_slots, float(actual["rh_pct"].median()))})
    synthetic = []
    for model_name in ("C1", "C2"):
        base_overhead, _, _, _ = _raw_case(model_name, base_nlr, base_nlr, step_weather, c1, c2, other_coefficients)
        shifted_overhead, _, _, _ = _raw_case(model_name, shifted_nlr, shifted_nlr, step_weather, c1, c2, other_coefficients)
        rebound_kw = np.maximum(shifted_overhead[step_end:] - base_overhead[step_end:], 0.0)
        peak_index = int(np.argmax(rebound_kw))
        norm = normalization_audits[f"NOAA_ACTUAL_24h_{model_name}"]["normalization_factor"]
        equivalent_rebound_kw = rebound_kw * norm * (400.0 / nlr_median_kw)
        synthetic.append({
            "model": model_name,
            "input_step": "+20% NLR-equivalent IT for 60 minutes then return to baseline",
            "step_end_to_peak_rebound_minutes": peak_index * 5,
            "peak_cooling_rebound_raw_kw": float(rebound_kw.max()),
            "peak_pcc_rebound_melbourne_equivalent_kw": float(equivalent_rebound_kw.max()),
            "rebound_energy_melbourne_equivalent_kwh": float(equivalent_rebound_kw.sum() * 5.0 / 60.0),
            "policy_authority": False,
        })
    write_json(root / "V24T_COOLING_REBOUND_DIAGNOSTIC.json", {"artifact_id": "V24T_COOLING_REBOUND_DIAGNOSTIC", "natural_profile_rows": rebound_rows, "synthetic_step_shift": synthetic})
    triggers = dynamic[(dynamic["warmup_hours"] == 24) & (dynamic["model"] == "C2")][["day", "ts_aest", "weather_case", "theta", "mpue", "overhead_eq_kw"]].copy()
    triggers["normalized_overhead_stress"] = triggers.groupby("weather_case")["overhead_eq_kw"].transform(lambda x: (x - x.min()) / max(x.max() - x.min(), 1e-9))
    write_json(root / "V24T_THERMAL_TRIGGER_CANDIDATE_SIGNALS.json", {
        "artifact_id": "V24T_THERMAL_TRIGGER_CANDIDATE_SIGNALS", "label": "CANDIDATE_ONLY_NOT_POLICY_AUTHORITY",
        "signals": ["normalized_overhead_stress", "mpue", "theta"], "policy_changes": 0,
        "summary": triggers[["normalized_overhead_stress", "mpue", "theta"]].describe(percentiles=[.05,.5,.95]).to_dict(),
    })
    primary = "C2" if json.loads((root / "V24T_THERMAL_MODEL_ACCEPTANCE.json").read_text(encoding="utf-8"))["c2_accepted"] else "C1"
    actual_primary = summaries[f"NOAA_ACTUAL_24h_{primary}"]
    gfs_primary = summaries[f"GFS_D1_24h_{primary}"]
    scale = {
        "artifact_id": "V24T_THERMAL_SCALE_COMPARISON", "primary_model": primary,
        "c0_frozen_peak_mw": FROZEN_C0_PCC_PEAK_MW,
        "actual_weather_dynamic_peak_mw": actual_primary["pcc_peak_mw"],
        "gfs_d1_dynamic_peak_mw": gfs_primary["pcc_peak_mw"],
        "actual_minus_c0_mw": actual_primary["pcc_peak_mw"] - FROZEN_C0_PCC_PEAK_MW,
        "gfs_minus_c0_mw": gfs_primary["pcc_peak_mw"] - FROZEN_C0_PCC_PEAK_MW,
        "peak_force_fit_count": 0, "frozen_scale_overwrite_count": 0,
    }
    write_json(root / "V24T_THERMAL_SCALE_COMPARISON.json", scale)
    return {"transfer": transfer, "scale": scale, "rebound": rebound_rows}


if __name__ == "__main__":
    run_melbourne_transfer(Path.cwd())
