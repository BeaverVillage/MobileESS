"""Precommitted V16.3 final-science execution protocol.

This module contains declarations only.  Importing it cannot open May or June
data, run a solver, or invoke OpenDSS.
"""

from __future__ import annotations


AUTHORITY_ID = "V16_3_DA_AIDC_ICPS_AC_ANCHORED_FROZEN_D1_CONTROL"
AUTHORITY_COMMIT = "2246063175977f152f3ac8df8f65a861cc7bbd22"
SCIENTIFIC_AUTHORITY_SHA256 = "9f43711b586172a784709fa501301d1506d127d5c98d9ab0dcce634bb43d65a6"
REFREEZE_MANIFEST_SHA256 = "42b277f16b3beb425c6d298aafed142700418b4ecfb69220e02dd0aa17abec1e"

EVALUATION_PERIODS = {
    "MAY_PRIMARY": {"start": "2025-05-01", "end": "2025-05-31"},
    "JUNE_REPLICATION": {"start": "2025-06-01", "end": "2025-06-25"},
}

CASES = {
    "B0": {"compute_flexibility": False, "mess_flexibility": False, "label": "NO_FLEXIBILITY"},
    "B1": {"compute_flexibility": True, "mess_flexibility": False, "label": "AIDC_COMPUTE_FLEXIBILITY_ONLY"},
    "B2": {"compute_flexibility": False, "mess_flexibility": True, "label": "MOBILE_ESS_FLEXIBILITY_ONLY"},
    "B3": {"compute_flexibility": True, "mess_flexibility": True, "label": "JOINT_AIDC_AND_MOBILE_ESS_FLEXIBILITY"},
}

GUROBI_VERSION = "13.0.3"
GUROBI_PARAMETERS = {
    "OutputFlag": 0,
    "Threads": 1,
    "Seed": 20260828,
    "Method": 1,
    "NumericFocus": 1,
    "DualReductions": 0,
    "InfUnbdInfo": 1,
    "FeasibilityTol": 1e-6,
    "OptimalityTol": 1e-6,
    "MIPGap": 1e-3,
    "TimeLimit_seconds": 1800.0,
}

BENDERS = {
    "certification_tolerance": 1e-3,
    "max_iterations": 200,
    "method_time_limit_seconds": 1800.0,
    "gamma_crit": 0.98,
    "initialization": "FROZEN_B3_REFERENCE_MASTER_TRAJECTORY",
    "standard_optimality_cut": "WORST_TIME_SINGLE_FULL_LP_CUT",
    "cl_mc_bd_optimality_cut": "ALL_CRITICAL_TIME_FULL_LP_CUTS",
    "feasibility_cut": "FARKAS_CUT_FOR_EVERY_INFEASIBLE_TIME",
    "lower_bound": "MONOTONE_MAXIMUM_OF_GUROBI_MASTER_OBJBOUND",
    "upper_bound": "MINIMUM_FULLY_FEASIBLE_96_LP_INCUMBENT_OBJECTIVE",
    "gap": "max(0,(UB-LB)/max(abs(UB),1e-6))",
    "stopping_rule": "STOP_ON_CERTIFIED_GAP_LE_1E_3_OR_PRECOMMITTED_TIME_OR_ITERATION_LIMIT",
    "benchmark_day_rule": "LEXICOGRAPHICALLY_FIRST_ELIGIBLE_DAY_IN_EACH_PERIOD",
}

FRESH_AC = {
    "primary": "FRESH_OPENDSS_EXACT_COMMON_FROZEN_D1_TAPS",
    "secondary": "FRESH_OPENDSS_NATIVE_REGCONTROL_ON",
    "required_converged_slots": 96,
    "voltage_min_pu": 0.95,
    "voltage_max_pu": 1.05,
    "phase_current_max_pu": 1.0,
    "transformer_total_kva_max_pu": 1.0,
    "hard_tolerance": 1e-9,
    "physically_validated": "PRIMARY_PASS_AND_SECONDARY_PASS",
    "post_hoc_tuning_allowed": False,
}

ELIGIBILITY = {
    "candidate_day_rule": "EVERY_CALENDAR_DAY_IN_PREDECLARED_PERIOD",
    "d1_cutoff": "PREVIOUS_DAY_18:00:00_FIXED_AEST",
    "aemo_demand": "ONE_LATEST_COMPLETE_48_SLOT_VIC1_PREDISPATCH_VINTAGE_AT_OR_BEFORE_CUTOFF_NO_SLOT_MIXING",
    "aemo_rooftop_pv": "ONE_LATEST_COMPLETE_48_SLOT_VIC1_ROOFTOP_PV_VINTAGE_AT_OR_BEFORE_CUTOFF_NO_SLOT_MIXING",
    "mapping": "FROZEN_PWC_HOLD_30_TO_15_EXACTLY_96_SLOTS",
    "aidc_forecast": "FROZEN_PRODUCTION_RC_MQT_DIRECT96_Q10_Q50_Q90_FINITE_ORDERED_D1_OUTPUT",
    "admission": "D1_FORECAST_COHORT_FIELDS_ONLY_EXPOST_FIELD_ACCESS_ZERO",
    "supporting_inputs": "FROZEN_BACKGROUND_PV_PCC_TRAFFIC_SAFE_ETA_AND_MESS_MOBILITY_INPUTS_COMPLETE",
    "allowed_exclusion_reasons": [
        "NO_COMPLETE_CAUSAL_AEMO_DEMAND_VINTAGE",
        "NO_COMPLETE_CAUSAL_AEMO_PV_VINTAGE",
        "FROZEN_RC_MQT_DIRECT96_INPUT_OR_OUTPUT_INCOMPLETE",
        "FROZEN_SUPPORTING_INPUT_INCOMPLETE",
    ],
    "result_dependent_exclusion_allowed": False,
    "june_outage_interval": "2025-06-26_THROUGH_2025-07-03_OUTSIDE_PREDECLARED_COHORT",
}

OUTPUT_SCHEMA = {
    "day_case_key": ["period", "operating_day", "case"],
    "planning_fields": [
        "optimization_status", "objective_lambda", "runtime_seconds", "mip_gap",
        "maximum_normalized_phase_line_current", "critical_line", "critical_phase",
        "critical_slot", "Vmin", "Vmax", "worst_transformer_phase_current_loading",
        "worst_transformer_total_kva_loading", "trust_region_maximum_utilization",
        "trust_region_boundary_variable_count", "trust_region_active_slot_count",
        "aidc_flexible_workload_shifted", "aidc_redistribution_summary",
        "mess_charge_energy_kwh", "mess_discharge_energy_kwh",
        "mess_reactive_utilization", "mess_travel_connectivity_schedule",
        "initial_soc_kwh", "terminal_soc_kwh", "service_parity_residual",
        "hard_constraint_residuals",
    ],
    "ac_fields": [
        "convergence_count", "Vmin", "Vmax", "maximum_normalized_phase_line_current",
        "maximum_transformer_phase_current_loading", "maximum_transformer_kva_loading",
        "voltage_violation_count", "phase_current_violation_count",
        "transformer_kva_violation_count",
    ],
    "secondary_extra_fields": [
        "tap_change_slots", "changes_by_regulator", "max_tap_deviation",
    ],
    "large_schedule_policy": "REPRODUCIBLE_CACHE_PLUS_SHA256_MANIFEST_NOT_NORMAL_GIT",
}

STATISTICS = {
    "periods_reported_separately_before_pooling": True,
    "daily_improvement": "(B0_metric-Bk_metric)/max(abs(B0_metric),1e-6)",
    "absolute_improvement": "B0_metric-Bk_metric",
    "complementarity_B3_vs_B1": "B1_metric-B3_metric",
    "complementarity_B3_vs_B2": "B2_metric-B3_metric",
    "synergy_test": "(B0-B3)>((B0-B1)+(B0-B2)); REPORT_ONLY_NO_DEFAULT_CLAIM",
    "aggregates": ["count", "mean", "median", "p25", "p75", "min", "max"],
    "infeasible_and_AC_failed_days": "PRESERVE_STATUS_AND_EXCLUDE_ONLY_FROM_UNDEFINED_NUMERIC_PAIR",
    "required_counts": ["eligible_days", "planning_feasible_days", "dual_AC_validated_days"],
}

NO_TUNING_COUNTERS = {
    "scientific_authority_changes": 0,
    "beta_changes": 0,
    "rho_changes": 0,
    "H_changes": 0,
    "J_I_changes": 0,
    "PUE_changes": 0,
    "PF_changes": 0,
    "kappa_changes": 0,
    "alpha_grid_changes": 0,
    "voltage_limit_changes": 0,
    "current_rating_changes": 0,
    "transformer_rating_changes": 0,
    "tap_semantics_changes": 0,
    "native_ieee123_changes": 0,
    "gamma_crit_changes": 0,
    "objective_changes": 0,
    "post_hoc_AC_tuning_count": 0,
    "OpenDSS_calls_inside_Benders": 0,
}
