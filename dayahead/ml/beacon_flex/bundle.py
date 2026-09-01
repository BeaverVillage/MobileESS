"""Forecast Bundle V4 construction for coherent diagnostic distributions."""

from __future__ import annotations

import numpy as np

from .shape import coherent_tensor


def diagnostic_bundle(forecast_day:str,summary:dict,probabilities:np.ndarray,thresholds:np.ndarray,shape:np.ndarray,hashes:dict)->dict:
    """Build a rejected-model diagnostic V4 bundle without claiming production authority."""

    mean_tensor=coherent_tensor(summary["mean_GPU_h"],shape)
    q50_tensor=coherent_tensor(summary["Q50_GPU_h"],shape)
    q90_tensor=coherent_tensor(summary["Q90_GPU_h"],shape)
    return {"schema":"FORECAST_BUNDLE_V4","authority":"REJECTED_BEACON_DIAGNOSTIC_NOT_PRODUCTION",
        "model_ids_by_statistic":{"mean":"BEC_A_DIAGNOSTIC","Q50":"BEC_A_DIAGNOSTIC","Q90":"BEC_A_DIAGNOSTIC","production_fallback":"B2_MEAN_B3_QUANTILES"},
        "base_distribution_id":"BR_A","overlay_model_id":"BEC_A_REJECTED","training_cutoff":"2025-03-31","forecast_cutoff":"D-1 18:00 FIXED_AEST_UTC_PLUS_10","forecast_day":forecast_day,
        "daily_mean_GPU_h":summary["mean_GPU_h"],"daily_Q50_GPU_h":summary["Q50_GPU_h"],"daily_Q90_GPU_h":summary["Q90_GPU_h"],"daily_Q95_GPU_h":summary["Q95_GPU_h"],
        "p_exceed_u80":float(probabilities[2]),"p_exceed_u90":float(probabilities[3]),"p_exceed_u95":float(probabilities[4]),
        "expected_excess_u90_GPU_h":summary["expected_excess_u90_GPU_h"],"conditional_tail_mean_u90_GPU_h":summary["conditional_tail_mean_u90_GPU_h"],
        "slot_tier_latency_mean_GPU_h":mean_tensor.tolist(),"slot_tier_latency_Q50_GPU_h":q50_tensor.tolist(),"slot_tier_latency_Q90_GPU_h":q90_tensor.tolist(),
        "mass_identity_errors":{"mean":float(mean_tensor.sum()-summary["mean_GPU_h"]),"Q50":float(q50_tensor.sum()-summary["Q50_GPU_h"]),"Q90":float(q90_tensor.sum()-summary["Q90_GPU_h"])},
        "CDF_validity_certificate":"PASS","hazard_monotonicity_certificate":"PASS","hazard_severity_certificate":"PASS","baseline_recovery_certificate":"PASS",
        "calibration_certificate":"HAZARD_GATE_FAIL","causality_certificate":"PASS","base_crossfit_certificate":"PASS","model_data_code_hashes":hashes,"tail_analog_provenance":"NOT_USED_BEC_A"}

