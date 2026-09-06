from __future__ import annotations


def write(path, validation, cal_summary, traj_audit, cap_audit):
    selected = cal_summary.get("selected_mapping_by_horizon", {})
    selected_cv = cal_summary.get("cross_validated_selection_by_horizon", selected)
    selected_text = ", ".join(f"h{h}:{m}" for h, m in selected.items())
    selected_cv_text = ", ".join(f"h{h}:{m}" for h, m in selected_cv.items())
    constant = cal_summary.get("strict_constant_fallback_horizons", [])
    text = f"""# Stage K5-C3 Report

## Status

**{validation['status']}**

## Scientific role

This stage converts the completed forecasting and power-assembly outputs into optimization-ready inputs. It does not retrain GRU, TCN, TiDE, or LightGBM. It performs leakage-free temporal cross-validation of multiple event-probability calibration candidates, constructs a causal 48-step fixed-load trajectory, and rebuilds capacity/rack constraints using pre-2025 data only.

## Flexible-event probability construction

- Source: {cal_summary['source']}
- Candidate selection: {cal_summary['calibration_method']}
- Temporal evaluation: {cal_summary['temporal_evaluation']}
- Application: {cal_summary['analysis_year_application']}
- Temporal-CV winner by horizon: {selected_cv_text}
- Effective final mapping by horizon: {selected_text}
- Dynamic calibrated horizons: {cal_summary.get('dynamic_horizon_count', 0)} / {len(selected)}
- Strict constant-fallback horizons: {constant}
- Pre-monotonicity violation fraction: {cal_summary['pre_monotonicity_violation_fraction']:.6%}
- Hazard knot recovery maximum error: {cal_summary['hazard_max_knot_recovery_error']:.3e}

The calibration target is the probability of at least one positive F30 flexible arrival within each horizon. Candidate mappings are compared only with 2024 rolling out-of-fold rows. Constant prevalence remains an explicit scientifically conservative fallback when no dynamic candidate improves temporal cross-validated Brier score. The effective final mapping is audited separately from the temporal-CV winner, so a failed refit cannot be mislabeled as dynamic calibration.

## Fixed 48-step trajectory

- Origin × IDC rows: {traj_audit['rows']:,}
- Forecast-origin rows expected: {traj_audit['expected_forecast_origin_site_rows']:,}
- Full-year origin × IDC rows: {traj_audit['full_year_origin_site_rows']:,}
- Origins: {traj_audit['origin_count']:,}
- IDCs: {traj_audit['site_count']}
- Steps: {traj_audit['step_count']}
- Storage dtype: {traj_audit['storage_dtype']}
- Persistence maximum serialization error: {traj_audit['persistence_max_error']:.3e}
- Origin range: {traj_audit['origin_start_utc']} to {traj_audit['origin_end_utc']}
- Excluded terminal origins: {traj_audit['excluded_tail_origin_count']} ({traj_audit['excluded_tail_minutes']} minutes)
- Method: {traj_audit['method']}

Steps 1–3 use the observed per-IDC fixed state. Steps 4–48 are piecewise-linear paths through the selected 30/60/120/240-minute forecast knots. Forecast errors are not recursively fed back. The final 48 five-minute origins of the calendar year are not valid 4-hour forecast origins because future target values do not exist beyond the analysis boundary; they remain usable as terminal points inside earlier rolling horizons.

## Capacity and rack sensitivity

- Main scenario: {cap_audit['main_scenario_id']}
- Capacity calibration end: {cap_audit['capacity_calibration_end']}
- Uses 2025 for sizing: {cap_audit['capacity_calibration_uses_analysis_year']}
- Main installed H100-equivalent capacity: {cap_audit['main_installed_gpu_capacity']:,}
- Main deliverable H100-equivalent capacity: {cap_audit['main_deliverable_gpu_capacity']:.3f}
- Deliverable/installed ratio: {cap_audit['main_deliverable_to_installed_ratio']:.3%}
- 2025 unconstrained requested-load exceedance rate: {cap_audit['main_analysis_year_exceedance_rate']:.3%}
- Fixed load exceeding installed-capacity proxy: {cap_audit['main_fixed_capacity_shortfall_rate']:.3%}
- Fixed load requiring nominal rack-policy override: {cap_audit['main_fixed_policy_override_rate']:.3%}
- Minimum flexible deferral implied by the nominal envelope: {cap_audit['minimum_required_flexible_deferral_gpuh']:.3f} GPUh

The 2025 Kestrel trace is an unconstrained workload request, not a capacity-feasible dispatch. Therefore it may exceed a synthetic rack-headroom sensitivity. Such exceedance creates flexible backlog or explicit fixed-load SLA/capacity slack; it is not silently treated as feasible dispatch.

## Main outputs

- `outputs/fixed_48step_trajectory_2025.parquet`
- `scenarios/calibrated_event_probabilities_2025.parquet`
- `scenarios/calibrated_event_hazard_2025_wide.parquet`
- `outputs/capacity_rack_sensitivity_parameters.csv`
- `outputs/capacity_rack_sensitivity_summary.csv`
- `outputs/optimization_main_rack_parameters.csv`
- `outputs/optimization_main_power_envelope_2025_5min.parquet`
- `generate_calibrated_flexible_scenarios.py`
- `load_optimization_window.py`

## Power-envelope column semantics

- `it_power_unconstrained_requested_kw`: observed workload request before rack-capacity enforcement.
- `it_power_min_deliverable_kw`: serviceable non-shiftable fixed-load lower bound.
- `it_power_max_deliverable_kw`: effective upper bound after fixed-load policy override, never above installed capacity.
- `fixed_active_capacity_shortfall_gpus`: non-shiftable fixed work beyond installed capacity; the future optimizer must carry this as SLA/capacity slack with penalty rather than discard it.
- `minimum_required_flexible_deferral_active_gpus`: flexible demand that cannot be served immediately under the nominal case.

## Scope

- The 12 IDCs remain deterministic virtual partitions, not 12 independently measured Melbourne facilities.
- The fixed trajectory is a central forecast path. Fixed-load residual uncertainty is not yet converted into scenarios.
- Flexible-event calibration uses expected-demand scores because K5-B3 did not serialize rolling-OOF event-head probabilities.
- Capacity and rack cases are planning sensitivities, not measurements of installed Melbourne H100 capacity.
"""
    path.write_text(text, encoding="utf-8")
