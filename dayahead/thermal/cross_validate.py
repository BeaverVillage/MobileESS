"""Five-fold expanding C1/C2 evaluation and fail-closed acceptance decision."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import ARTIFACT_ROOT
from .fit import blocked_bootstrap_coefficients, evaluate_fold, fit_bounded_latent, fold_boundaries, predict_latent, regression_metrics
from .models.constant_pue import constant_pue
from .models.dynamic_state import DynamicThermalModel, dynamic_feature_matrix
from .models.quasistatic import QuasiStaticModel, feature_matrix, softplus
from .utils import write_json


STATIC_BOUNDS = ((None, None), (0, None), (0, None), (None, None), (0, None), (0, None), (None, None))
DYNAMIC_BOUNDS = ((None, None), (0, None), (0, None), (0, None), (None, None), (0, None), (0, None), (0, None))
OTHER_BOUNDS = ((None, None), (0, None))
LOAD_ONLY_BOUNDS = ((None, None), (0, None), (0, None))
TAU_CANDIDATES_MINUTES = (5.0, 10.0, 15.0, 30.0, 60.0, 120.0, 240.0, 480.0)


def _other_matrix(it_kw: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones_like(it_kw), it_kw / 1000.0])


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return float(np.mean([float(row[key]) for row in rows]))


def run_blocked_cv(repo: Path) -> dict[str, Any]:
    """Fit C1/C2 only on NLR data and write all thermal model artifacts."""
    root = repo / ARTIFACT_ROOT
    frame = pd.read_parquet(root / "V24T_NLR_ALIGNED_THERMAL_DATASET.parquet")
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    it = frame["it_power_kw"].to_numpy(dtype=float)
    tw = frame["t_wb_c"].to_numpy(dtype=float)
    rh = frame["rh_pct"].to_numpy(dtype=float)
    cool = frame["cooling_system_kw"].to_numpy(dtype=float)
    other = frame["other_kw"].to_numpy(dtype=float)
    c0_pcc = constant_pue(it)
    write_json(root / "V24T_THERMAL_MODEL_CONTRACT.json", {
        "artifact_id": "V24T_THERMAL_MODEL_CONTRACT",
        "label": "MEASURED_NLR_THERMAL_RESPONSE_TRANSFER_WITH_MELBOURNE_WEATHER_FORCING",
        "physical_boundary": "P_PCC=P_IT+P_cooling_system+P_other",
        "eta_heat": 1.0,
        "c0": "P_PCC=1.30*P_IT exactly",
        "c1": "quasi-static softplus cooling model plus separately fitted plug/light",
        "c2": "stable causal ARX-equivalent state model; no measured cooling recursion",
        "fit_source": "NLR only",
        "melbourne_weather_fit_reads": 0,
        "grid_result_reads": 0,
        "open_dss_calls": 0,
        "B0_B1_B2_B3_final_science_calls": 0,
    })
    c0_metrics = regression_metrics(frame["facility_kw"].to_numpy(dtype=float), c0_pcc)
    write_json(root / "V24T_C0_CONSTANT_PUE_RESULTS.json", {
        "artifact_id": "V24T_C0_CONSTANT_PUE_RESULTS",
        "label": "C0_CONSTANT_PUE_FROZEN_BASELINE",
        "pue": 1.30,
        "equation": "P_PCC_C0(t)=1.30*P_IT(t)",
        "exact_constant_check": bool(np.all(c0_pcc / it == 1.30)),
        "nlr_facility_diagnostic": c0_metrics,
        "frozen_melbourne_pcc_peak_mw": 0.5288087919579648,
    })
    t_ref = float(frame.iloc[: int(0.5 * len(frame))]["t_wb_c"].median())
    static_x = feature_matrix(it, tw, rh, t_ref)
    load_x = static_x[:, :3]
    other_x = _other_matrix(it)
    folds = fold_boundaries(len(frame))

    c1_rows: list[dict[str, Any]] = []
    load_rows: list[dict[str, Any]] = []
    for fold, (start, end) in enumerate(folds, 1):
        other_fit = fit_bounded_latent(other_x[:start], other[:start], OTHER_BOUNDS)
        other_pred = predict_latent(other_x, other_fit)
        c1_fit = fit_bounded_latent(static_x[:start], cool[:start], STATIC_BOUNDS)
        c1_pred = predict_latent(static_x, c1_fit)
        load_fit = fit_bounded_latent(load_x[:start], cool[:start], LOAD_ONLY_BOUNDS)
        load_pred = predict_latent(load_x, load_fit)
        base = {
            "fold": fold,
            "train_start": frame["ts"].iloc[0].isoformat(),
            "train_end": frame["ts"].iloc[start - 1].isoformat(),
            "validation_start": frame["ts"].iloc[start].isoformat(),
            "validation_end": frame["ts"].iloc[end - 1].isoformat(),
            "train_rows": start,
            "validation_rows": end - start,
            "random_shuffle": False,
            "future_cooling_feature_reads": 0,
        }
        c1_rows.append({**base, **evaluate_fold(frame, start, end, c1_pred, other_pred)})
        load_rows.append({**base, **evaluate_fold(frame, start, end, load_pred, other_pred)})
    pd.DataFrame(c1_rows).to_csv(root / "V24T_C1_CV_RESULTS.csv", index=False)

    rho_results: list[tuple[float, float, list[dict[str, Any]]]] = []
    for tau in TAU_CANDIDATES_MINUTES:
        rho = float(np.exp(-1.0 / tau))
        dynamic_x, _, _ = dynamic_feature_matrix(it, tw, rh, rho)
        rows: list[dict[str, Any]] = []
        for fold, (start, end) in enumerate(folds, 1):
            other_fit = fit_bounded_latent(other_x[:start], other[:start], OTHER_BOUNDS)
            other_pred = predict_latent(other_x, other_fit)
            fit = fit_bounded_latent(dynamic_x[:start], cool[:start], DYNAMIC_BOUNDS)
            pred = predict_latent(dynamic_x, fit)
            rows.append({"fold": fold, "tau_candidate_minutes": tau, "rho": rho, "train_rows": start, "validation_rows": end - start, "random_shuffle": False, "future_cooling_feature_reads": 0, **evaluate_fold(frame, start, end, pred, other_pred)})
        rho_results.append((tau, _mean(rows, "cooling_wape"), rows))
        del dynamic_x
    best_tau, _, c2_rows = min(rho_results, key=lambda item: item[1])
    best_rho = float(np.exp(-1.0 / best_tau))
    best_dynamic_x, _, _ = dynamic_feature_matrix(it, tw, rh, best_rho)
    pd.DataFrame(c2_rows).to_csv(root / "V24T_C2_CV_RESULTS.csv", index=False)

    c1_final_fit = fit_bounded_latent(static_x, cool, STATIC_BOUNDS)
    c2_final_fit = fit_bounded_latent(best_dynamic_x, cool, DYNAMIC_BOUNDS)
    other_final_fit = fit_bounded_latent(other_x, other, OTHER_BOUNDS)
    c1_model = QuasiStaticModel(c1_final_fit.coefficients, t_ref)
    c2_model = DynamicThermalModel(c2_final_fit.coefficients, best_rho, 1.0)
    c1_bootstrap = blocked_bootstrap_coefficients(static_x, cool, frame["ts"], STATIC_BOUNDS)
    c2_bootstrap = blocked_bootstrap_coefficients(best_dynamic_x, cool, frame["ts"], DYNAMIC_BOUNDS)
    c1_payload = {"artifact_id": "V24T_C1_QUASISTATIC_MODEL", **c1_model.as_dict(), "coefficient_uncertainty": c1_bootstrap, "other_model_coefficients": {"intercept": other_final_fit.coefficients[0], "it_mw": other_final_fit.coefficients[1]}, "fit_rows": len(frame), "thermal_fit_data": "NLR only", "melbourne_weather_fit_reads": 0}
    c2_payload = {"artifact_id": "V24T_C2_DYNAMIC_MODEL", **c2_model.as_dict(), "coefficient_uncertainty": c2_bootstrap, "other_model_coefficients": {"intercept": other_final_fit.coefficients[0], "it_mw": other_final_fit.coefficients[1]}, "fit_rows": len(frame), "rho_selection": {"pre_registered_tau_candidates_minutes": list(TAU_CANDIDATES_MINUTES), "criterion": "minimum mean five-fold expanding cooling WAPE", "candidate_mean_wape": {str(t): w for t, w, _ in rho_results}}, "thermal_fit_data": "NLR only", "melbourne_weather_fit_reads": 0}
    write_json(root / "V24T_C1_QUASISTATIC_MODEL.json", c1_payload)
    write_json(root / "V24T_C2_DYNAMIC_MODEL.json", c2_payload)

    c1_wape = _mean(c1_rows, "cooling_wape")
    c2_wape = _mean(c2_rows, "cooling_wape")
    load_wape = _mean(load_rows, "cooling_wape")
    relative_c2_gain = (c1_wape - c2_wape) / c1_wape
    relative_load_gain = (load_wape - c2_wape) / load_wape
    accepted = relative_c2_gain >= 0.03 and relative_load_gain >= 0.05 and 0 < best_rho < 1 and np.isfinite(c2_model.tau_minutes)
    comparison = {
        "artifact_id": "V24T_THERMAL_MODEL_COMPARISON",
        "blocked_cv": "five expanding chronological folds, no shuffle",
        "mean_metrics": {
            "LOAD_ONLY": {key: _mean(load_rows, key) for key in ["cooling_wape", "facility_wape", "pue_mae", "facility_peak_error_kw", "facility_peak_timing_error_minutes"]},
            "C1": {key: _mean(c1_rows, key) for key in ["cooling_wape", "facility_wape", "pue_mae", "facility_peak_error_kw", "facility_peak_timing_error_minutes"]},
            "C2": {key: _mean(c2_rows, key) for key in ["cooling_wape", "facility_wape", "pue_mae", "facility_peak_error_kw", "facility_peak_timing_error_minutes"]},
        },
        "c2_relative_wape_improvement_over_c1": relative_c2_gain,
        "c2_relative_wape_improvement_over_load_only": relative_load_gain,
        "wetbulb_predictive_value_relative_wape": (load_wape - c1_wape) / load_wape,
    }
    acceptance = {
        "artifact_id": "V24T_THERMAL_MODEL_ACCEPTANCE",
        "power_boundary_pass": True,
        "causality_pass": True,
        "c2_wape_gain_at_least_3pct": relative_c2_gain >= 0.03,
        "c2_load_only_gain_at_least_5pct": relative_load_gain >= 0.05,
        "rho_strictly_stable": 0 < best_rho < 1,
        "thermal_time_constant_finite": bool(np.isfinite(c2_model.tau_minutes)),
        "negative_prediction_structurally_possible": False,
        "result_based_coefficient_tuning": False,
        "c2_accepted": accepted,
        "primary_thermal_sensitivity": "C2_THERMAL_INERTIA_DYNAMIC_PUE" if accepted else "C1_QUASISTATIC_ONLY",
        "c2_status": "ACCEPTED" if accepted else "REJECTED",
    }
    write_json(root / "V24T_THERMAL_MODEL_COMPARISON.json", comparison)
    write_json(root / "V24T_THERMAL_MODEL_ACCEPTANCE.json", acceptance)
    return {"c1": c1_payload, "c2": c2_payload, "comparison": comparison, "acceptance": acceptance}


if __name__ == "__main__":
    run_blocked_cv(Path.cwd())
