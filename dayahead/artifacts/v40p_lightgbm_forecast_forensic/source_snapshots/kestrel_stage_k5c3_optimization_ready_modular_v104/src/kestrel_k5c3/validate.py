from __future__ import annotations
import numpy as np


def validate(art, cfg):
    prob = art["probabilities"]
    hz = art["hazard"]
    traj = art["trajectory"]
    cap = art["capacity"]
    ca = art["calibration_audit"]
    traj_audit = art.get("trajectory_audit", {})
    cal_summary = art.get("calibration_summary", {})
    checks = {}

    pw = prob.pivot(index="timestamp_utc", columns="horizon_steps", values="event_probability_calibrated").sort_index(axis=1)
    checks["calibrated_probability_range"] = bool(pw.min().min() >= 0 and pw.max().max() <= 1)
    checks["calibrated_probability_monotone"] = bool((np.diff(pw.to_numpy(float), axis=1) >= -1e-10).all())

    lam = hz.filter(like="lambda_step_").to_numpy(float)
    checks["hazard_nonnegative"] = bool(lam.min() >= -1e-12)
    cum = np.cumsum(lam, axis=1)
    horizons = list(map(int, cfg["analysis"]["horizons_steps"]))
    errs = []
    for h in horizons:
        errs.append(np.max(np.abs(1 - np.exp(-cum[:, h - 1]) - pw[h].to_numpy(float))))
    checks["hazard_probability_recovery"] = bool(max(errs) < 1e-6)

    stepcols = [c for c in traj if c.startswith("fixed_gpu_step_")]
    checks["fixed_trajectory_48_steps"] = len(stepcols) == int(cfg["analysis"]["trajectory_steps"])
    checks["fixed_trajectory_nonnegative"] = bool(traj[stepcols].min().min() >= -1e-8)
    persist = int(cfg["trajectory"]["persistence_steps"])
    persistence_error = float(np.max(np.abs(traj[stepcols[:persist]].to_numpy(float) - traj.origin_fixed_active_gpus.to_numpy(float)[:, None])))
    checks["fixed_persistence_exact"] = bool(persistence_error == 0.0)
    expected_forecast_rows = int(traj_audit.get("expected_forecast_origin_site_rows", len(traj)))
    checks["fixed_trajectory_matches_forecast_origin_grid"] = bool(len(traj) == expected_forecast_rows)
    excluded = int(traj_audit.get("excluded_tail_origin_count", -1))
    full_rows = int(traj_audit.get("full_year_origin_site_rows", len(traj)))
    checks["fixed_tail_exclusion_explicit"] = bool(
        excluded >= 0
        and full_rows - len(traj) == excluded * int(cfg["analysis"].get("idc_count", traj.idc_id.nunique()))
    )

    checks["capacity_scenario_count"] = len(cap.summary) == (
        len(cfg["capacity_sensitivity"]["quantiles"])
        * len(cfg["capacity_sensitivity"]["target_utilizations"])
        * len(cfg["capacity_sensitivity"]["rack_active_fractions"])
    )
    checks["capacity_pre2025_only"] = bool(not cap.audit["capacity_calibration_uses_analysis_year"])
    checks["main_rack_pool_count"] = bool(cap.main_rack.groupby("idc_id").size().eq(int(cfg["analysis"].get("rack_pool_count", 4))).all())
    checks["main_deliverable_le_installed"] = bool((cap.main_rack.deliverable_active_gpu_capacity <= cap.main_rack.installed_gpu_capacity + 1e-8).all())

    env = cap.main_envelope
    checks["main_envelope_bounds_order"] = bool((env.it_power_min_deliverable_kw <= env.it_power_max_deliverable_kw + 1e-8).all())
    checks["main_nominal_reference_inside_envelope"] = bool(
        (env.it_power_min_deliverable_kw <= env.it_power_nominal_reference_kw + 1e-8).all()
        and (env.it_power_nominal_reference_kw <= env.it_power_max_deliverable_kw + 1e-8).all()
    )
    reported_exceedance = float(env.observed_active_exceeds_deliverable.mean())
    checks["observed_demand_exceedance_reported"] = bool(abs(reported_exceedance - float(cap.audit["main_analysis_year_exceedance_rate"])) < 1e-12)
    checks["fixed_shortfall_metric_reported"] = bool("main_fixed_capacity_shortfall_rate" in cap.audit and np.isfinite(float(cap.audit["main_fixed_capacity_shortfall_rate"])))

    selected = ca[ca.candidate.eq(ca.selected_final_mapping)] if {"candidate", "selected_final_mapping"}.issubset(ca.columns) else ca
    checks["calibration_cross_validation_present"] = bool(
        selected.horizon_steps.nunique() == len(horizons)
        and selected.brier.notna().all()
        and ca.groupby("horizon_steps").candidate.nunique().min() >= 2
    )
    selected_map = cal_summary.get("selected_mapping_by_horizon", {})
    selected_cv = cal_summary.get("cross_validated_selection_by_horizon", {})
    probability_std = cal_summary.get("probability_std_by_horizon", {})
    checks["calibration_selection_recorded"] = bool(
        len(selected_map) == len(horizons) and len(selected_cv) == len(horizons)
    )
    checks["constant_fallback_explicit"] = bool("strict_constant_fallback_horizons" in cal_summary)
    expected_dynamic = sum(
        selected_map.get(str(h), "constant") != "constant"
        and float(probability_std.get(str(h), 0.0)) > 1e-10
        for h in horizons
    )
    checks["dynamic_calibration_count_truthful"] = bool(
        int(cal_summary.get("dynamic_horizon_count", -1)) == int(expected_dynamic)
    )
    calendar_counts = cal_summary.get("calendar_rate_count_by_horizon", {})
    checks["calendar_mapping_not_silently_constant"] = bool(all(
        selected_map.get(str(h)) != "calendar"
        or (
            int(calendar_counts.get(str(h), 0)) >= 2
            and float(probability_std.get(str(h), 0.0)) > 1e-10
        )
        for h in horizons
    ))

    status = "success" if all(checks.values()) else "failed"
    return {
        "status": status,
        "checks": checks,
        "metrics": {
            "calibrated_probability_rows": len(prob),
            "hazard_rows": len(hz),
            "fixed_trajectory_rows": len(traj),
            "main_envelope_rows": len(env),
            "hazard_max_recovery_error": float(max(errs)),
            "fixed_persistence_max_error": persistence_error,
            "fixed_excluded_tail_origin_count": int(traj_audit.get("excluded_tail_origin_count", 0)),
            "main_deliverable_to_installed_ratio": float(cap.audit["main_deliverable_to_installed_ratio"]),
            "main_analysis_year_exceedance_rate": float(cap.audit["main_analysis_year_exceedance_rate"]),
            "main_fixed_capacity_shortfall_rate": float(cap.audit["main_fixed_capacity_shortfall_rate"]),
            "minimum_required_flexible_deferral_gpuh": float(cap.audit["minimum_required_flexible_deferral_gpuh"]),
            "mean_selected_cross_validated_brier": float(selected.brier.mean()),
            "mean_selected_brier_improvement_vs_constant": float(selected.brier_improvement_vs_constant.mean()),
            "dynamic_calibration_horizon_count": int(cal_summary.get("dynamic_horizon_count", 0)),
        },
    }
