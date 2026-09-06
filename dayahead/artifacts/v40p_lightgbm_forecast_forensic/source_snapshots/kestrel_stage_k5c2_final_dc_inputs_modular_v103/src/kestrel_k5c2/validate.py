from __future__ import annotations

import numpy as np
import pandas as pd


def validate_artifacts(art: dict, cfg: dict) -> dict:
    paired = art["paired"]
    rack = art["rack"]
    env = art["envelope"]
    fixed = art["fixed_forecast"]
    flex = art["flex_forecast"]
    probs = art["event_probabilities"]
    hazard_audit = art["hazard_audit"]
    inf_cons = art["inference_conservation"]
    site_caps = art["site_capacities"]
    inference = art["inference"]
    burst_summary = art["burst_group_summary"]
    event_audit = art.get("event_audit", {})
    checks = {}
    checks["paired_identity"] = bool(np.max(np.abs(paired.gross_it_kw_per_gpu - paired.incremental_it_kw_per_gpu - paired.idle_it_kw_per_gpu)) < 1e-9)
    checks["paired_effective_order"] = bool(np.all(np.diff(paired.effective_it_kw_per_gpu_at_u_ref.to_numpy(float)) >= -1e-12))
    checks["rack_pool_count"] = bool(rack.groupby("idc_id").size().eq(int(cfg["analysis"]["rack_pool_count"])).all())
    cap_sum = rack.groupby("idc_id").installed_gpu_capacity.sum().sort_index()
    expected = site_caps.set_index("idc_id").installed_gpu_capacity.sort_index()
    checks["rack_capacity_conservation"] = bool(np.array_equal(cap_sum.reindex(expected.index).to_numpy(int), expected.to_numpy(int)))
    checks["envelope_order"] = bool((env.it_power_min_deliverable_kw <= env.it_power_realized_kw + 1e-8).all() and (env.it_power_realized_kw <= env.it_power_max_deliverable_kw + 1e-8).mean() >= 0.99)
    checks["envelope_nonnegative"] = bool(env.filter(regex="power|flex").select_dtypes(include=[np.number]).min().min() >= -1e-8)
    checks["fixed_share_conservation"] = bool(np.max(np.abs(fixed.groupby(["timestamp_utc", "horizon_steps"]).fixed_site_share.sum() - 1)) < 1e-8)
    checks["flex_share_conservation"] = bool(np.max(np.abs(flex.groupby(["timestamp_utc", "horizon_steps"]).flex_site_share.sum() - 1)) < 1e-8)
    pwide = probs.pivot(index="timestamp_utc", columns="horizon_steps", values="event_probability").sort_index(axis=1)
    checks["event_probability_range"] = bool(pwide.min().min() >= 0 and pwide.max().max() <= 1)
    checks["event_probability_monotone"] = bool((np.diff(pwide.to_numpy(float), axis=1) >= -1e-8).all())
    checks["hazard_probability_recovery"] = bool(hazard_audit.absolute_error.max() < 1e-6)
    checks["inference_energy_conservation"] = bool(inf_cons.relative_error.max() < 1e-10)
    expected_sites = int(cfg["analysis"]["idc_count"])
    checks["burst_trace_site_coverage"] = bool(burst_summary.site_count.astype(int).eq(expected_sites).all())
    checks["inference_site_coverage"] = bool(inference.idc_id.nunique() == expected_sites)
    per_timestamp_sites = inference.groupby("timestamp_utc").idc_id.nunique()
    checks["inference_complete_site_time_grid"] = bool(len(per_timestamp_sites) > 0 and per_timestamp_sites.eq(expected_sites).all())
    checks["inference_idle_positive_all_sites"] = bool(inference.groupby("idc_id").inference_idle_kw.median().gt(0).all())
    checks["analysis_year_only"] = bool(pd.to_datetime(env.timestamp_utc, utc=True).dt.year.eq(int(cfg["analysis"]["year"])).all())
    checks["no_null_critical"] = bool(not env[["it_power_realized_kw", "it_power_min_deliverable_kw", "it_power_max_deliverable_kw"]].isna().any().any())
    status = "success" if all(checks.values()) else "failed"
    return {
        "status": status,
        "checks": checks,
        "metrics": {
            "envelope_rows": len(env), "fixed_forecast_rows": len(fixed), "flex_forecast_rows": len(flex),
            "event_probability_rows": len(probs), "hazard_max_recovery_error": float(hazard_audit.absolute_error.max()),
            "inference_max_energy_relative_error": float(inf_cons.relative_error.max()),
            "observed_active_exceeds_deliverable_rate": float(env.observed_active_exceeds_deliverable.mean()),
            "burst_trace_min_site_count": int(burst_summary.site_count.min()),
            "inference_site_count": int(inference.idc_id.nunique()),
            "rack_power_limited_pool_fraction": float((rack.deliverable_active_gpu_capacity < rack.installed_gpu_capacity - 1e-8).mean()),
            "rack_deliverable_to_installed_ratio": float(rack.deliverable_active_gpu_capacity.sum() / rack.installed_gpu_capacity.sum()),
            "mean_active_to_installed_capacity_ratio": float(env.total_avg_active_gpus.mean() / max(site_caps.installed_gpu_capacity.sum() / int(cfg["analysis"]["idc_count"]), 1e-12)),
            "raw_event_probability_monotonicity_violation_fraction": float(event_audit.get("raw_monotonicity_violation_fraction", np.nan)),
            "event_probability_calibration": event_audit.get("probability_calibration", "unknown"),
        },
    }
