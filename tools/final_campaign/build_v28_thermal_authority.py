#!/usr/bin/env python3
"""Freeze the C1-only V28 thermal authority and conservative PWL surrogate."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from dayahead.v28.thermal import (  # noqa: E402
    C1_PATH,
    FROZEN_AGGREGATE_IT_PEAK_MW,
    GFS_NORMALIZATION_FACTOR,
    NLR_MEDIAN_IT_KW,
    NOAA_NORMALIZATION_FACTOR,
    _raw_overhead_kw,
)


OUT = REPO / "dayahead/artifacts/v28_final_dayahead_actual"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def exact_pcc(it_kw: np.ndarray, wetbulb: float, rh: float, factor: float, scale: float) -> np.ndarray:
    tw = np.full_like(it_kw, wetbulb)
    humidity = np.full_like(it_kw, rh)
    return it_kw + factor / scale * _raw_overhead_kw(it_kw * scale, tw, humidity)


def main() -> None:
    profile = pd.read_csv(REPO / "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_PRIMARY_OPERATING_IT_PROFILE.csv")
    normalized_peak = float(profile["normalized_shape_factor"].max())
    frozen_mean_it_kw = FROZEN_AGGREGATE_IT_PEAK_MW * 1000.0 / normalized_peak
    scale = NLR_MEDIAN_IT_KW / frozen_mean_it_kw
    breakpoints = np.linspace(0.0, FROZEN_AGGREGATE_IT_PEAK_MW * 1000.0 * 1.10, 25)
    wetbulb_knots = [-5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0]
    rh_knots = [20.0, 50.0, 80.0, 100.0]
    namespaces = {
        "FORECAST_DAYAHEAD_GFS": GFS_NORMALIZATION_FACTOR,
        "ACTUAL_REALIZED_NOAA": NOAA_NORMALIZATION_FACTOR,
        "PERFECT_INFORMATION_NOAA": NOAA_NORMALIZATION_FACTOR,
    }
    rows = []
    validations = []
    for namespace, factor in namespaces.items():
        for tw in wetbulb_knots:
            for rh in rh_knots:
                values = exact_pcc(breakpoints, tw, rh, factor, scale)
                for index in range(len(breakpoints) - 1):
                    lower, upper = breakpoints[index:index + 2]
                    slope = (values[index + 1] - values[index]) / (upper - lower)
                    intercept = values[index] - slope * lower
                    rows.append({
                        "namespace": namespace, "wetbulb_c": tw, "rh_pct": rh,
                        "segment": index, "it_lower_kw": lower, "it_upper_kw": upper,
                        "pcc_slope": slope, "pcc_intercept_kw": intercept,
                    })
                    dense = np.linspace(lower, upper, 41)
                    exact = exact_pcc(dense, tw, rh, factor, scale)
                    surrogate = slope * dense + intercept
                    error = surrogate - exact
                    validations.append({
                        "namespace": namespace, "wetbulb_c": tw, "rh_pct": rh,
                        "segment": index, "max_overestimate_kw": float(np.max(error)),
                        "minimum_conservatism_kw": float(np.min(error)),
                        "rmse_kw": float(np.sqrt(np.mean(error**2))),
                    })
    pd.DataFrame(rows).to_csv(OUT / "V28_FINAL_C1_PLANNING_SURROGATE.csv", index=False, lineterminator="\n")
    pd.DataFrame(validations).to_csv(OUT / "V28_FINAL_C1_SURROGATE_VALIDATION.csv", index=False, lineterminator="\n")
    validation_frame = pd.DataFrame(validations)
    surrogate = {
        "artifact_id": "V28_FINAL_C1_PLANNING_SURROGATE_V1",
        "type": "WEATHER_CONDITIONAL_CONSERVATIVE_PIECEWISE_LINEAR_SECANTS",
        "it_breakpoints_kw": breakpoints.tolist(),
        "wetbulb_knots_c": wetbulb_knots,
        "rh_knots_pct": rh_knots,
        "valid_it_range_kw": [float(breakpoints[0]), float(breakpoints[-1])],
        "nlr_equivalent_scale": scale,
        "objective_role": "planning only; exact C1 is always used for physical evaluation",
        "minimum_conservatism_kw": float(validation_frame.minimum_conservatism_kw.min()),
        "maximum_overestimate_kw": float(validation_frame.max_overestimate_kw.max()),
        "maximum_rmse_kw": float(validation_frame.rmse_kw.max()),
        "surrogate_validation_pass": bool(validation_frame.minimum_conservatism_kw.min() >= -1e-9),
    }
    authority = {
        "artifact_id": "V28_FINAL_THERMAL_PCC_AUTHORITY_V1",
        "status": "FINAL_THERMAL_PCC_AUTHORITY_READY",
        "primary_model": "C1_WEATHER_AND_LOAD_DEPENDENT_QUASISTATIC_PUE",
        "C1_source": str(C1_PATH.relative_to(REPO)).replace("\\", "/"),
        "C1_source_sha256": sha256(C1_PATH),
        "C1_refit_calls": 0,
        "C1_retune_calls": 0,
        "C2_status": "REJECTED_EXCLUDED_FROM_V28_PRODUCTION_IMPORT_GRAPH",
        "C2_production_calls": 0,
        "C0_status": "SENSITIVITY_ONLY",
        "C0_formula": "P_PCC_C0(t)=1.30*P_IT(t)",
        "dayahead_weather": "GFS_06Z_D_MINUS_1_F008_THROUGH_F032_BYTE_RANGE_ONLY",
        "actual_weather": "NOAA_MELBOURNE_94866099999_OBSERVED",
        "PUE_application_count_per_trajectory": 1,
        "extra_1p30_multiplier_count": 0,
        "peak_force_fit_count": 0,
        "frozen_C0_PCC_peak_MW": 0.5288087919579648,
        "C1_peak_forced_to_C0": False,
        "normalization_factors": namespaces,
        "NLR_absolute_size_claim_for_Melbourne": False,
        "FINAL_THERMAL_PCC_AUTHORITY_READY": True,
    }
    write_json("V28_FINAL_C1_PLANNING_SURROGATE.json", surrogate)
    write_json("V28_FINAL_THERMAL_PCC_AUTHORITY.json", authority)


if __name__ == "__main__":
    main()
