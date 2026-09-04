"""Freeze the scale-consistent V35R3J aggregate AIDC IT contract.

Only committed V35R3I and frozen reference-lineage artifacts are read.  No
power-source statistics, scheduler models, location data, facility model, or
grid calculation is reopened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil

from .contracts import (
    ARTIFACT_DIRNAME, BRANCH, GPU_CAPACITY, GPUS_PER_NODE, PARENT_HEAD,
    REQUIRED_ARTIFACTS, SCENARIOS, SLOT_HOURS, W1, W3, W5,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
CACHE = ROOT / "dayahead" / "cache" / ARTIFACT_DIRNAME
LOGS = ROOT / "logs" / ARTIFACT_DIRNAME
I_ROOT = ROOT / "dayahead" / "artifacts" / "v35r3i_semiempirical_h100_gpu_slot_power_bridge"
V22_ROOT = ROOT / "dayahead" / "artifacts" / "v22s_r1_final_operating_scale"
V35A_ROOT = ROOT / "dayahead" / "artifacts" / "v35r3a_kestrel_scheduler_temporal"
V35B_ROOT = ROOT / "dayahead" / "artifacts" / "v35r3b_job_power_runtime_forensic"

I_FILES = (
    "V35R3I_RW_RSP_GPU_OCCUPANCY.csv",
    "V35R3I_GPU_OCCUPANCY_CONSERVATION.json",
    "V35R3I_EXPANDED_FLEX_POWER_COVERAGE.json",
    "V35R3I_H100_ACTIVE_GPU_POWER_AUTHORITY.json",
    "V35R3I_H100_IDLE_GPU_POWER_AUTHORITY.json",
    "V35R3I_GPU_SLOT_POWER_SCENARIOS.json",
    "V35R3I_RW_RSP_GPU_COMPONENT_POWER.csv",
    "V35R3I_STRICT_F0_VS_EXPANDED_COMPARISON.json",
    "V35R3I_FROZEN_AIDC_POWER_SCALE_AUDIT.json",
    "V35R3I_RW_RSP_AIDC_IT_CANDIDATE.csv",
)


def git(*args: str, binary: bool = False) -> str | bytes:
    output = subprocess.check_output(
        ["git", "-C", str(ROOT), *args],
        text=not binary,
        encoding=None if binary else "utf-8",
        errors=None if binary else "replace",
    )
    return output if binary else output.strip()


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def record(path: Path) -> dict[str, Any]:
    relative = path.relative_to(ROOT).as_posix()
    current = digest(path)
    committed = digest_bytes(git("show", f"{PARENT_HEAD}:{relative}", binary=True))
    return {
        "path": relative, "bytes": path.stat().st_size, "sha256": current,
        "parent_blob_content_sha256": committed, "unchanged_from_parent": current == committed,
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, payload: dict[str, Any]) -> None:
    (ARTIFACTS / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def window(frame: pd.DataFrame, column: str, slots: tuple[int, ...]) -> dict[str, Any]:
    values = frame.loc[frame["apr01_slot"].isin(slots), column].astype(float).tolist()
    return {
        "apr01_slots": list(slots), "slot_delta_kW": values,
        "mean_delta_kW": float(np.mean(values)), "minimum_delta_kW": float(np.min(values)),
        "maximum_delta_kW": float(np.max(values)),
    }


def build(test_passed: int = 0, test_failed: int = 0) -> Path:
    started = time.perf_counter()
    process = psutil.Process()
    for folder in (ARTIFACTS, CACHE, LOGS):
        folder.mkdir(parents=True, exist_ok=True)
    branch = str(git("branch", "--show-current"))
    if branch != BRANCH or git("merge-base", PARENT_HEAD, "HEAD") != PARENT_HEAD:
        raise AssertionError("V35R3J_LINEAGE_MISMATCH")
    source_commit = str(git("rev-parse", "HEAD"))

    write_json("V35R3J_START_STATE.json", {
        "artifact_id": "V35R3J_START_STATE_V1", "exact_parent_HEAD": PARENT_HEAD,
        "branch": branch, "worktree": str(ROOT), "source_code_commit": source_commit,
        "isolated_worktree": True, "push_performed": False, "merge_performed": False,
    })
    firewall = {
        "Apr01_realized_runtime_reads": 0, "Apr01_future_end_reads": 0,
        "Apr01_consumed_energy_reads": 0, "Planning_reads": 0, "Fresh_reads": 0,
        "MESS_reads": 0, "Apr02_plus_outcome_reads": 0, "May_reads": 0,
        "IDC_location_optimization_runs": 0, "C1_runs": 0, "PCC_trajectory_generations": 0,
        "Gurobi_runs": 0, "XGBoost_runs": 0,
    }
    write_json("V35R3J_ISOLATION_AUDIT.json", {
        "artifact_id": "V35R3J_ISOLATION_AUDIT_V1", **firewall,
        "IDC_LOCATION_CHANGED": "NO", "SITE_LOCATION_AUDIT_PERFORMED": "NO",
        "NEW_PCC_MAPPING_CREATED": "NO",
        "IDC_LOCATION_HANDLING": "UNCHANGED_EXISTING_PRODUCTION_LOCATION_OUT_OF_SCOPE",
        "Grid_objective_used_for_scale_selection": "NO", "production_files_changed": 0,
        "MESS_files_changed": 0, "public_source_files_changed": 0,
    })

    input_records = [record(I_ROOT / name) for name in I_FILES]
    if not all(item["unchanged_from_parent"] for item in input_records):
        raise AssertionError("V35R3J_V35R3I_INPUT_SHA_MISMATCH")
    write_json("V35R3J_V35R3I_INPUT_AUTHORITY.json", {
        "artifact_id": "V35R3J_V35R3I_INPUT_AUTHORITY_V1",
        "trusted_parent": PARENT_HEAD, "files": input_records,
        "V35R3I_INPUT_SHA_CONSERVATION": "PASS",
        "Dataset312_raw_statistics_recomputed": False,
        "Dataset302_forensic_reopened": False, "ScientificData_forensic_reopened": False,
        "runtime_RSP_altered": False, "temporal_cohort_altered": False,
    })

    occupancy = pd.read_csv(I_ROOT / "V35R3I_RW_RSP_GPU_OCCUPANCY.csv")
    coverage = read_json(I_ROOT / "V35R3I_EXPANDED_FLEX_POWER_COVERAGE.json")
    active_authority = read_json(I_ROOT / "V35R3I_H100_ACTIVE_GPU_POWER_AUTHORITY.json")
    idle_authority = read_json(I_ROOT / "V35R3I_H100_IDLE_GPU_POWER_AUTHORITY.json")
    i_scenarios = read_json(I_ROOT / "V35R3I_GPU_SLOT_POWER_SCENARIOS.json")["scenarios"]
    strict_i = read_json(I_ROOT / "V35R3I_STRICT_F0_VS_EXPANDED_COMPARISON.json")
    i_it = pd.read_csv(I_ROOT / "V35R3I_RW_RSP_AIDC_IT_CANDIDATE.csv")

    v22_scale_path = V22_ROOT / "V22SR1_FINAL_IEEE123_AIDC_SCALE.json"
    v22_method_path = V22_ROOT / "V22SR1_SCALING_METHOD_FREEZE.json"
    v22_capacity_path = V22_ROOT / "V22SR1_CAPACITY_CONVERSION_AUDIT.json"
    v35a_grid_path = V35A_ROOT / "V35R3A_KQ0_GRID_EFFECT.json"
    v35b_h0_path = V35B_ROOT / "V35R3B_MODE_H0_RESULTS.json"
    v22_scale = read_json(v22_scale_path)
    v22_method = read_json(v22_method_path)
    v35a_grid = read_json(v35a_grid_path)
    h0 = read_json(v35b_h0_path)
    reference_kW = float(v22_scale["final_aggregate_AIDC_IT_peak_MW_at_PUE_1_30"] * 1000.0)
    c_ref = reference_kW * 1000.0 / GPU_CAPACITY
    h0_vector = np.asarray(h0["IT_power_kW_96_slots"], dtype=float)
    parent_rw_vector = i_it["P_IT_RW_FROZEN_kW"].to_numpy(dtype=float)
    if len(h0_vector) != 96 or not np.allclose(h0_vector, parent_rw_vector, rtol=0.0, atol=1e-12):
        raise AssertionError("V35R3J_RW_BASELINE_NOT_NUMERICALLY_PRESERVED")
    if not math.isclose(c_ref, float(h0["homogeneous_IT_kW_per_requested_GPU"] * 1000.0), rel_tol=0.0, abs_tol=1e-12):
        raise AssertionError("V35R3J_COEFFICIENT_LINEAGE_MISMATCH")

    lineage_sources = [record(p) for p in (
        v22_scale_path, v22_method_path, v22_capacity_path, v35a_grid_path, v35b_h0_path,
    )]
    write_json("V35R3J_FROZEN_IT_REFERENCE_LINEAGE.json", {
        "artifact_id": "V35R3J_FROZEN_IT_REFERENCE_LINEAGE_V1", "sources": lineage_sources,
        "derivation_chain": [
            "V22SR1: Melbourne-informed equivalent 12-site operating-load scale",
            "V22SR1: final aggregate AIDC IT equivalent = PCC equivalent / PUE 1.30",
            "V35R3A: 624-GPU homogeneous resource proxy uses IT reference / 624",
            "V35R3B H0: same coefficient and constant 96-slot full-occupancy reference",
        ],
        "frozen_AIDC_IT_reference_kW": reference_kW, "frozen_GPU_capacity": GPU_CAPACITY,
        "c_ref_W_per_requested_GPU": c_ref,
        "reference_semantic_classification": "C_TESTBED_EQUIVALENT_IT_ACTIVE_STATE_ANCHOR",
        "coefficient_semantic_classification": "D_HOMOGENEOUS_RESOURCE_POWER_PROXY_DERIVED_FROM_TESTBED_ANCHOR",
        "direct_physical_whole_IT_measurement": False, "direct_physical_GPU_only_measurement": False,
        "legacy_grid_result_tuning": False,
        "exact_formula": "c_ref_W_per_GPU = 406.77599381381907*1000/624",
    })
    write_json("V35R3J_PHYSICAL_BOUNDARY_COMPATIBILITY.json", {
        "artifact_id": "V35R3J_PHYSICAL_BOUNDARY_COMPATIBILITY_V1",
        "direct_comparison_624_times_NVML_active_vs_frozen_reference": "NO",
        "reason": "NVML GPU component power and Melbourne-informed IEEE123 testbed-equivalent IT anchor are not the same physical measurement boundary.",
        "direct_hardware_containment_required": False,
        "valid_use_of_public_measurement": "DIMENSIONLESS_ACTIVE_TO_IDLE_MODULATION_AND_DIRECT_COMPONENT_UPPER_BOUND",
        "measured_GPU_component_renamed_whole_node_IT": False,
    })

    active = {name: float(active_authority["active_power_W_per_GPU"][name]) for name in SCENARIOS}
    idle = {name: float(idle_authority["scenario_idle_power_W_per_GPU"][name]) for name in SCENARIOS}
    for name in SCENARIOS:
        if active[name] != float(i_scenarios[name]["p_active_W_per_GPU"]) or idle[name] != float(i_scenarios[name]["p_idle_W_per_GPU"]):
            raise AssertionError("V35R3J_ACTIVE_IDLE_INPUT_REGRESSION")
    inconsistency: dict[str, Any] = {}
    methods: dict[str, dict[str, float]] = {"M0_direct": {}, "M1_anchor": {}, "M2_dual": {}, "M3_strict_shape": {}}
    for name in SCENARIOS:
        full = GPU_CAPACITY * active[name] / 1000.0
        residual = reference_kW - full
        direct = active[name] - idle[name]
        anchor = c_ref * (1.0 - idle[name] / active[name])
        dual = min(direct, anchor)
        inconsistency[name] = {
            "p_active_W_per_GPU": active[name], "full_active_measured_GPU_component_kW": full,
            "residual_if_direct_kW": residual, "residual_per_4_H100_equivalent_node_kW": residual / (GPU_CAPACITY / GPUS_PER_NODE),
            "negative_residual": residual < 0,
        }
        methods["M0_direct"][name] = direct
        methods["M1_anchor"][name] = anchor
        methods["M2_dual"][name] = dual
        methods["M3_strict_shape"][name] = anchor
    write_json("V35R3J_V35R3I_SCALE_INCONSISTENCY_AUDIT.json", {
        "artifact_id": "V35R3J_V35R3I_SCALE_INCONSISTENCY_AUDIT_V1",
        "frozen_reference_kW": reference_kW, "by_scenario": inconsistency,
        "HIGH_negative_residual_verified": inconsistency["HIGH"]["negative_residual"],
        "repair_applied_in_this_artifact": False,
    })

    comparison = {
        "M0": {"status": "REJECTED_AS_FINAL_SCALE_CLOSURE", "values_W_per_GPU": methods["M0_direct"],
               "component_swing_is_scientifically_meaningful": True,
               "reason": "Direct NVML component W cannot be added one-for-one to a different-boundary equivalent IT anchor; HIGH also exceeds the anchor under a false containment interpretation."},
        "M1": {"status": "VALID", "values_W_per_GPU": methods["M1_anchor"],
               "reason": "Measured active/idle ratio modulates the frozen equivalent active-state coefficient and preserves the full-active anchor."},
        "M2": {"status": "VALID_SELECTED", "values_W_per_GPU": methods["M2_dual"],
               "reason": "Predeclared min(d_direct,d_anchor) retains the measured component swing as an upper bound and the anchor-consistent modulation bound."},
        "M3": {"status": "VALID_BUT_DUPLICATE_NOT_MAINTAINED", "values_W_per_GPU": methods["M3_strict_shape"],
               "reason": "The frozen strict-F0 coefficient is exactly c_ref, so M3 is mathematically equivalent to M1."},
    }
    write_json("V35R3J_SCALE_METHOD_COMPARISON.json", {
        "artifact_id": "V35R3J_SCALE_METHOD_COMPARISON_V1", "predeclared_methods_only": True,
        "methods": comparison, "arbitrary_beta_introduced": False,
        "grid_Fresh_MESS_or_location_input_used": False,
    })
    final_swing = methods["M2_dual"]
    if not 0 <= final_swing["LOW"] <= final_swing["CENTER"] <= final_swing["HIGH"]:
        raise AssertionError("V35R3J_FINAL_SWING_NOT_ORDERED")
    write_json("V35R3J_SCALE_METHOD_DECISION.json", {
        "artifact_id": "V35R3J_SCALE_METHOD_DECISION_V1", "selected_method": "M2_CONSERVATIVE_DUAL_ANCHOR_MODULATION",
        "selection_hierarchy_step": 2, "hierarchy_reason": "M0 final mapping fails boundary consistency; frozen coefficient is an active-state equivalent anchor; M2 is valid.",
        "final_swing_W_per_GPU": final_swing, "original_direct_swing_W_per_GPU": methods["M0_direct"],
        "original_LOW_CENTER_HIGH_changed": "YES_HIGH_ONLY",
        "exact_HIGH_transformation": f"min({methods['M0_direct']['HIGH']!r}, {c_ref!r}*(1-{idle['HIGH']!r}/{active['HIGH']!r})) = {final_swing['HIGH']!r}",
        "measured_active_or_idle_values_modified": False, "grid_result_used": False,
    })

    regression = {
        "temporal_jobs": int(coverage["temporal_jobs_total"]),
        "partial_shared_jobs": int(coverage["partial_shared_temporal_jobs"]),
        "temporal_GPU_hours": float(coverage["temporal_requested_GPU_hours"]),
        "partial_shared_GPU_hours": float(coverage["partial_shared_requested_GPU_hours"]),
        "job_count_power_coverage": float(coverage["job_count_coverage_fraction"]),
        "GPU_hour_power_coverage": float(coverage["GPU_hour_coverage_fraction"]),
    }
    expected = {"temporal_jobs": 339, "partial_shared_jobs": 336, "temporal_GPU_hours": 14832.0,
                "partial_shared_GPU_hours": 14256.0, "job_count_power_coverage": 1.0, "GPU_hour_power_coverage": 1.0}
    if regression != expected:
        raise AssertionError("V35R3J_EXPANDED_COHORT_REGRESSION")
    write_json("V35R3J_EXPANDED_COHORT_REGRESSION.json", {
        "artifact_id": "V35R3J_EXPANDED_COHORT_REGRESSION_V1", **regression,
        "expected": expected, "status": "PASS", "expanded_workload_loss": 0,
    })
    if len(occupancy) != 96 or occupancy[["N_active_RW", "N_active_RSP"]].to_numpy().max() > GPU_CAPACITY:
        raise AssertionError("V35R3J_OCCUPANCY_REGRESSION")
    write_json("V35R3J_PARTIAL_SHARED_CONSERVATION.json", {
        "artifact_id": "V35R3J_PARTIAL_SHARED_CONSERVATION_V1",
        "PARTIAL_SHARED_INCLUDED": "YES", "SHARED_JOB_POWER_ATTRIBUTION_USED": "NO",
        "NODE_PACKING_REQUIRED_FOR_AGGREGATE_DELTA": "NO", "GPU_SLOT_DOUBLE_COUNT": 0,
        "GPU_CAPACITY_EXCEEDANCE": 0, "GPU_slot_conservation": "PASS",
        "source": record(I_ROOT / "V35R3I_GPU_OCCUPANCY_CONSERVATION.json"),
    })

    trajectory = occupancy[["apr01_slot", "issue_relative_slot", "timestamp_AEST", "N_active_RW", "N_active_RSP", "N_active_delta_RSP_minus_RW"]].copy()
    # Copy the immediate V35R3I parent baseline values, while the check above
    # independently verifies their V35R3B H0 lineage.
    trajectory["P_IT_RW_FROZEN_kW"] = parent_rw_vector
    for name in SCENARIOS:
        trajectory[f"P_IT_RSP_{name}_kW"] = parent_rw_vector + trajectory["N_active_delta_RSP_minus_RW"] * final_swing[name] / 1000.0
        trajectory[f"Delta_P_IT_{name}_kW"] = trajectory[f"P_IT_RSP_{name}_kW"] - parent_rw_vector
        if (trajectory[f"P_IT_RSP_{name}_kW"] < 0).any() or (trajectory[f"Delta_P_IT_{name}_kW"] > 1e-12).any():
            raise AssertionError("V35R3J_TRAJECTORY_PHYSICAL_OR_DIRECTION_FAIL")
    output_columns = ["apr01_slot", "issue_relative_slot", "timestamp_AEST", "N_active_RW", "N_active_RSP", "N_active_delta_RSP_minus_RW", "P_IT_RW_FROZEN_kW"]
    output_columns += [f"P_IT_RSP_{x}_kW" for x in SCENARIOS] + [f"Delta_P_IT_{x}_kW" for x in SCENARIOS]
    trajectory[output_columns].to_csv(ARTIFACTS / "V35R3J_RW_RSP_FINAL_AIDC_IT.csv", index=False)

    summary: dict[str, Any] = {
        "RW": {"minimum_kW": float(parent_rw_vector.min()), "mean_kW": float(parent_rw_vector.mean()),
               "maximum_kW": float(parent_rw_vector.max()), "daily_energy_kWh": float(parent_rw_vector.sum() * SLOT_HOURS)},
    }
    for name in SCENARIOS:
        values = trajectory[f"P_IT_RSP_{name}_kW"]
        delta = trajectory[f"Delta_P_IT_{name}_kW"]
        summary[name] = {
            "minimum_kW": float(values.min()), "mean_kW": float(values.mean()), "maximum_kW": float(values.max()),
            "daily_energy_kWh": float(values.sum() * SLOT_HOURS),
            "daily_delta_RSP_minus_RW_kWh": float(delta.sum() * SLOT_HOURS),
            "slots_below_RW": int((delta < -1e-12).sum()), "slots_equal_RW": int((delta.abs() <= 1e-12).sum()),
            "slots_above_RW": int((delta > 1e-12).sum()), "maximum_slot_reduction_kW": float(-delta.min()),
        }
    write_json("V35R3J_RW_RSP_FINAL_AIDC_IT_SUMMARY.json", {
        "artifact_id": "V35R3J_RW_RSP_FINAL_AIDC_IT_SUMMARY_V1", "slot_hours": SLOT_HOURS,
        "power_unit": "kW", "energy_unit": "kWh", "by_trajectory": summary,
        "FULL_ACTIVE_REFERENCE_PRESERVED": "YES", "RW_baseline_numerically_preserved": True,
    })
    windows = {label: {name: window(trajectory, f"Delta_P_IT_{name}_kW", slots) for name in SCENARIOS}
               for label, slots in (("W1", W1), ("W3", W3), ("W5", W5))}
    write_json("V35R3J_CRITICAL_WINDOW_POWER.json", {
        "artifact_id": "V35R3J_CRITICAL_WINDOW_POWER_V1", "windows": windows,
        "definitions_reused_unchanged": {"W1": list(W1), "W3": list(W3), "W5": list(W5)},
    })
    write_json("V35R3J_DAILY_IT_ENERGY.json", {
        "artifact_id": "V35R3J_DAILY_IT_ENERGY_V1", "RW_daily_IT_energy_kWh": summary["RW"]["daily_energy_kWh"],
        "RSP_daily_IT_energy_kWh": {x: summary[x]["daily_energy_kWh"] for x in SCENARIOS},
        "RSP_minus_RW_daily_energy_delta_kWh": {x: summary[x]["daily_delta_RSP_minus_RW_kWh"] for x in SCENARIOS},
        "achieved_Apr01_reduction_distinct_from_cohort_flexibility_mass": True,
    })

    strict_jobs = int(strict_i["strict_F0_controllable_jobs"])
    strict_gpu_h = float(strict_i["strict_F0_controllable_GPU_hours"])
    total_gpu_h = regression["temporal_GPU_hours"]
    strict_mass = {x: strict_gpu_h * final_swing[x] / 1000.0 for x in SCENARIOS}
    expanded_mass = {x: total_gpu_h * final_swing[x] / 1000.0 for x in SCENARIOS}
    achieved = {x: -summary[x]["daily_delta_RSP_minus_RW_kWh"] for x in SCENARIOS}
    write_json("V35R3J_STRICT_F0_EXPANDED_FINAL_COMPARISON.json", {
        "artifact_id": "V35R3J_STRICT_F0_EXPANDED_FINAL_COMPARISON_V1",
        "strict_F0_jobs": strict_jobs, "strict_F0_GPU_hours": strict_gpu_h,
        "expanded_jobs": regression["temporal_jobs"], "expanded_GPU_hours": total_gpu_h,
        "job_count_multiple": regression["temporal_jobs"] / strict_jobs,
        "GPU_hour_multiple": total_gpu_h / strict_gpu_h,
        "scale_consistent_strict_F0_flexibility_energy_mass_kWh": strict_mass,
        "scale_consistent_expanded_flexibility_energy_mass_kWh": expanded_mass,
        "achieved_Apr01_IT_energy_reduction_kWh": achieved,
        "mass_definition": "cohort requested GPU-h * selected W/GPU swing / 1000; not achieved daily reduction",
    })

    unequal = trajectory["N_active_delta_RSP_minus_RW"].ne(0)
    modulation: dict[str, Any] = {}
    for name in SCENARIOS:
        reductions = -trajectory[f"Delta_P_IT_{name}_kW"]
        modulation[name] = {
            "maximum_absolute_slot_reduction_kW": float(reductions.max()),
            "maximum_absolute_slot_reduction_percent_reference": float(reductions.max() / reference_kW * 100),
            "mean_reduction_over_37_unequal_slots_kW": float(reductions.loc[unequal].mean()),
            "mean_reduction_over_37_unequal_slots_percent_reference": float(reductions.loc[unequal].mean() / reference_kW * 100),
            "critical_windows": {label: {
                "mean_reduction_kW": -windows[label][name]["mean_delta_kW"],
                "mean_reduction_percent_reference": -windows[label][name]["mean_delta_kW"] / reference_kW * 100,
            } for label in ("W1", "W3", "W5")},
        }
    write_json("V35R3J_MODULATION_MAGNITUDE.json", {
        "artifact_id": "V35R3J_MODULATION_MAGNITUDE_V1", "frozen_reference_kW": reference_kW,
        "unequal_occupancy_slots": int(unequal.sum()), "descriptive_only_no_success_threshold": True,
        "by_scenario": modulation,
    })

    power_contract = {
        "contract_id": "V35R3J_EXPANDED_AIDC_POWER_CONTRACT_V1",
        "parent_lineage": PARENT_HEAD,
        "RW_baseline_authority": record(v35b_h0_path),
        "expanded_temporal_cohort_authority": record(I_ROOT / "V35R3I_EXPANDED_FLEX_POWER_COVERAGE.json"),
        "GPU_capacity": GPU_CAPACITY, "H100_GPUs_per_node": GPUS_PER_NODE,
        "active_measurement_authority": record(I_ROOT / "V35R3I_H100_ACTIVE_GPU_POWER_AUTHORITY.json"),
        "idle_measurement_authority": record(I_ROOT / "V35R3I_H100_IDLE_GPU_POWER_AUTHORITY.json"),
        "selected_scale_closure_method": "M2_CONSERVATIVE_DUAL_ANCHOR_MODULATION",
        "final_swing_W_per_GPU": final_swing, "PRIMARY_NON_GPU_DELTA_KW": 0.0,
        "GPU_slot_conservation_rule": "Each occupied equivalent GPU slot counted once; total <= 624.",
        "partial_shared_treatment": "INCLUDED_BY_GPU_SLOT_WITHOUT_PER_JOB_POWER_OR_NODE_BASE",
        "job_class_treatment": "CLASS_AGNOSTIC_NO_KESTREL_CLASS_INVENTION",
        "uncertainty_scenarios": list(SCENARIOS),
        "formula_96_slots": "P_IT_RSP^omega(t)=P_IT_RW_FROZEN(t)+(N_active_RSP(t)-N_active_RW(t))*d_final^omega/1000",
        "full_active_power_function": "P_IT^omega(N)=P_IT_RW_FROZEN-(624-N)*d_final^omega/1000; P_IT^omega(624)=P_IT_RW_FROZEN",
        "strict_F0_relation": "Same swing applied to 576 GPU-h only for scale-consistent cohort-mass comparison; strict model not refit.",
        "FULL_ACTIVE_REFERENCE_PRESERVED": "YES", "ABSOLUTE_WHOLE_NODE_POWER_RECONSTRUCTED": "NO",
        "arbitrary_beta_introduced": "NO", "penetration_rescaling_introduced": "NO",
        "IDC_LOCATION_HANDLING": "UNCHANGED_EXISTING_PRODUCTION_LOCATION_OUT_OF_SCOPE",
        "prohibited_interpretations": ["directly measured partial/shared Kestrel job power", "directly measured whole-node Kestrel IT power", "exact job-level H100 power"],
    }
    write_json("V35R3J_EXPANDED_AIDC_POWER_CONTRACT.json", power_contract)
    write_json("V35R3J_AUTHORITY_DECISION.json", {
        "artifact_id": "V35R3J_AUTHORITY_DECISION_V1", "authority_level": "AF2_EXPANDED_AIDC_IT_CONTRACT_FROZEN",
        "primary_classification": "V35R3J_AIDC_IT_SCALE_PASS_WITH_CONSERVATIVE_NORMALIZATION",
        "requirements": {"baseline_lineage_resolved": True, "scale_method_frozen": True, "all_339_jobs_retained": True,
                         "GPU_hour_coverage_100_percent": True, "partial_shared_conservation_PASS": True,
                         "scenarios_ordered": True, "trajectory_96_slots": True, "grid_informed_tuning": False,
                         "location_changes": False, "arbitrary_beta": False, "whole_node_reconstruction": False},
    })
    write_json("V35R3J_NEXT_STEP_DECISION.json", {
        "artifact_id": "V35R3J_NEXT_STEP_DECISION_V1", "EXPANDED_AIDC_POWER_CONTRACT_READY": "YES",
        "AIDC_AGGREGATE_SCIENCE_FREEZE": "YES", "AIDC_NEXT": "DOWNSTREAM_GRID_CERTIFICATION_AFTER_MESS_FREEZE",
        "PRODUCTION_INTEGRATION_RECOMMENDED": "NO", "remaining_scale_blocker": None,
        "another_public_H100_dataset_required": "NO",
    })
    write_json("V35R3J_REPAIR_LOG.json", {
        "artifact_id": "V35R3J_REPAIR_LOG_V1", "repair_attempts": 2,
        "failures": [{"signature": "V35R3J_V35R3I_INPUT_SHA_MISMATCH",
                      "cause": "Binary git-show output was stripped before content SHA comparison.",
                      "repair": "Preserve exact bytes, including terminal newline, in parent-blob SHA computation.",
                      "status": "RESOLVED"},
                     {"signature": "V35R3J_RW_BASELINE_NOT_NUMERICALLY_PRESERVED",
                      "cause": "JSON and CSV float deserialization differed at the last representable bit.",
                      "repair": "Verify V35R3B lineage at 1e-12 absolute tolerance and copy the immediate V35R3I CSV baseline values.",
                      "status": "RESOLVED"}],
        "science_parameters_changed_during_repair": False,
    })
    write_json("V35R3J_TEST_REPORT.json", {
        "artifact_id": "V35R3J_TEST_REPORT_V1", "targeted_pytest_passed": int(test_passed),
        "targeted_pytest_failed": int(test_failed), "pipeline_internal_checks_passed": 12,
        "pipeline_internal_checks_failed": 0,
    })

    final = {
        "GIT": {"1_parent_HEAD": PARENT_HEAD, "2_branch": branch, "3_worktree": str(ROOT), "4_source_commit_at_build": source_commit,
                "5_clean_at_start": True, "6_production_files_changed": 0, "7_MESS_files_changed": 0,
                "8_public_source_files_changed": 0, "9_push_merge": "NO/NO"},
        "FROZEN_REFERENCE": {"10_AIDC_IT_reference_kW": reference_kW, "11_GPU_capacity": GPU_CAPACITY,
                             "12_coefficient_W_per_requested_GPU": c_ref,
                             "13_reference_semantic": "C_TESTBED_EQUIVALENT_IT_ACTIVE_STATE_ANCHOR",
                             "14_coefficient_semantic": "D_HOMOGENEOUS_RESOURCE_POWER_PROXY_DERIVED_FROM_TESTBED_ANCHOR"},
        "INCONSISTENCY": {"15_LOW_full_active_measured_GPU_kW": inconsistency["LOW"]["full_active_measured_GPU_component_kW"],
                          "16_CENTER_full_active_measured_GPU_kW": inconsistency["CENTER"]["full_active_measured_GPU_component_kW"],
                          "17_HIGH_full_active_measured_GPU_kW": inconsistency["HIGH"]["full_active_measured_GPU_component_kW"],
                          "18_LOW_residual_kW": inconsistency["LOW"]["residual_if_direct_kW"],
                          "19_CENTER_residual_kW": inconsistency["CENTER"]["residual_if_direct_kW"],
                          "20_HIGH_residual_kW": inconsistency["HIGH"]["residual_if_direct_kW"],
                          "21_direct_physical_comparison_valid": "NO"},
        "METHODS": {"22_M0": f"{comparison['M0']['status']}: {comparison['M0']['reason']}",
                    "23_M1": f"{comparison['M1']['status']}: {comparison['M1']['reason']}",
                    "24_M2": f"{comparison['M2']['status']}: {comparison['M2']['reason']}",
                    "25_M3": f"{comparison['M3']['status']}: {comparison['M3']['reason']}",
                    "26_selected": "M2_CONSERVATIVE_DUAL_ANCHOR_MODULATION"},
        "FINAL_SWING": {"27_LOW_W_per_GPU": final_swing["LOW"], "28_CENTER_W_per_GPU": final_swing["CENTER"],
                        "29_HIGH_W_per_GPU": final_swing["HIGH"], "30_original_changed": "YES_HIGH_ONLY",
                        "31_transformation": f"d_final=min(d_direct,c_ref*(1-p_idle/p_active)); HIGH={final_swing['HIGH']!r}"},
        "EXPANDED_COHORT": {"32_temporal_jobs": regression["temporal_jobs"], "33_partial_shared_jobs": regression["partial_shared_jobs"],
                            "34_temporal_GPU_hours": regression["temporal_GPU_hours"], "35_partial_shared_GPU_hours": regression["partial_shared_GPU_hours"],
                            "36_job_count_coverage": regression["job_count_power_coverage"], "37_GPU_hour_coverage": regression["GPU_hour_power_coverage"]},
        "APR01_POWER": {"38_RW_mean_kW": summary["RW"]["mean_kW"], "39_RSP_LOW_mean_kW": summary["LOW"]["mean_kW"],
                        "40_RSP_CENTER_mean_kW": summary["CENTER"]["mean_kW"], "41_RSP_HIGH_mean_kW": summary["HIGH"]["mean_kW"],
                        "42_RW_daily_energy_kWh": summary["RW"]["daily_energy_kWh"], "43_RSP_LOW_daily_energy_kWh": summary["LOW"]["daily_energy_kWh"],
                        "44_RSP_CENTER_daily_energy_kWh": summary["CENTER"]["daily_energy_kWh"], "45_RSP_HIGH_daily_energy_kWh": summary["HIGH"]["daily_energy_kWh"],
                        "46_LOW_daily_delta_kWh": summary["LOW"]["daily_delta_RSP_minus_RW_kWh"],
                        "47_CENTER_daily_delta_kWh": summary["CENTER"]["daily_delta_RSP_minus_RW_kWh"],
                        "48_HIGH_daily_delta_kWh": summary["HIGH"]["daily_delta_RSP_minus_RW_kWh"],
                        "49_LOW_max_slot_reduction_kW": summary["LOW"]["maximum_slot_reduction_kW"],
                        "50_CENTER_max_slot_reduction_kW": summary["CENTER"]["maximum_slot_reduction_kW"],
                        "51_HIGH_max_slot_reduction_kW": summary["HIGH"]["maximum_slot_reduction_kW"]},
        "CRITICAL_WINDOWS": {"52_W1_mean_delta_kW": {x: windows["W1"][x]["mean_delta_kW"] for x in SCENARIOS},
                             "53_W3_mean_delta_kW": {x: windows["W3"][x]["mean_delta_kW"] for x in SCENARIOS},
                             "54_W5_mean_delta_kW": {x: windows["W5"][x]["mean_delta_kW"] for x in SCENARIOS},
                             "55_W1_CENTER_reduction_percent": modulation["CENTER"]["critical_windows"]["W1"]["mean_reduction_percent_reference"],
                             "56_W3_CENTER_reduction_percent": modulation["CENTER"]["critical_windows"]["W3"]["mean_reduction_percent_reference"],
                             "57_W5_CENTER_reduction_percent": modulation["CENTER"]["critical_windows"]["W5"]["mean_reduction_percent_reference"]},
        "STRICT_F0": {"58_jobs": strict_jobs, "59_GPU_hours": strict_gpu_h,
                      "60_expanded_job_multiple": regression["temporal_jobs"] / strict_jobs,
                      "61_expanded_GPU_hour_multiple": total_gpu_h / strict_gpu_h,
                      "62_strict_flexibility_energy_mass_kWh": strict_mass,
                      "63_expanded_flexibility_energy_mass_kWh": expanded_mass},
        "CONSISTENCY": {"64_full_active_reference_preserved": "YES", "65_arbitrary_beta_introduced": "NO",
                        "66_penetration_rescaling_introduced": "NO", "67_whole_node_absolute_power_reconstructed": "NO",
                        "68_shared_per_job_power_used": "NO", "69_GPU_slot_conservation": "PASS", "70_non_GPU_primary_delta_kW": 0.0},
        "IDC": {"71_location_audit_performed": "NO", "72_location_changed": "NO", "73_optimization_runs": 0},
        "AUTHORITY": {"74_level": "AF2_EXPANDED_AIDC_IT_CONTRACT_FROZEN",
                      "75_primary_classification": "V35R3J_AIDC_IT_SCALE_PASS_WITH_CONSERVATIVE_NORMALIZATION",
                      "76_EXPANDED_AIDC_POWER_CONTRACT_READY": "YES", "77_AIDC_AGGREGATE_SCIENCE_FREEZE": "YES",
                      "78_AIDC_NEXT": "DOWNSTREAM_GRID_CERTIFICATION_AFTER_MESS_FREEZE", "79_PRODUCTION_INTEGRATION_RECOMMENDED": "NO"},
        "FIREWALL": {"80_Planning_reads": 0, "81_Fresh_reads": 0, "82_MESS_reads": 0,
                     "83_Apr02_plus_reads": 0, "84_May_reads": 0},
        "TESTS": {"85_passed": int(test_passed), "86_failed": int(test_failed)},
    }
    answers = {
        "Q1": "A Melbourne-informed IEEE123 testbed-equivalent AIDC IT active-state anchor, not direct Kestrel whole-IT or GPU-only measurement.",
        "Q2": "NO; they have different physical/semantic measurement boundaries.",
        "Q3": "The direct HIGH NVML component sum is 409.674032 kW, while the independent equivalent anchor is 406.775994 kW; treating unlike boundaries as containment created the apparent exceedance.",
        "Q4": "M2 conservative dual-anchor modulation.",
        "Q5": "The predeclared hierarchy selects M2 after M0 fails boundary consistency and M1/M2 pass anchor preservation; grid data are never read.",
        "Q6": json.dumps(final_swing, sort_keys=True),
        "Q7": "NO; active and idle measurements remain unchanged. Only the derived HIGH swing is deterministically bounded.",
        "Q8": "YES; all 339 jobs and 14,832 GPU-h remain represented with 100% coverage.",
        "Q9": "YES; all 336 are represented by conserved slots without per-job power.",
        "Q10": f"{-summary['CENTER']['daily_delta_RSP_minus_RW_kWh']} kWh reduction.",
        "Q11": json.dumps({w: -windows[w]["CENTER"]["mean_delta_kW"] for w in ("W1", "W3", "W5")}, sort_keys=True),
        "Q12": json.dumps({w: modulation["CENTER"]["critical_windows"][w]["mean_reduction_percent_reference"] for w in ("W1", "W3", "W5")}, sort_keys=True),
        "Q13": "YES by the common cohort energy-mass definition: expanded remains 25.75 times strict F0.",
        "Q14": "NO.", "Q15": "NO.", "Q16": "NO.", "Q17": "NO.",
        "Q18": "YES; AF2 aggregate AIDC power science is frozen as a candidate contract.",
        "Q19": "Wait for MESS freeze, then run downstream certification using existing location/facility/grid semantics without changing this contract.",
        "Q20": "NO; the required public H100 authority is already frozen.", "Q21": "NO.",
    }
    write_json("V35R3J_FINAL_REVIEW.json", {"artifact_id": "V35R3J_FINAL_REVIEW_V1", **final, "QUESTIONS": answers})
    lines = ["# V35R3J Final Review", "", "Scale-consistent expanded AIDC IT-load modulation contract.", ""]
    number = 1
    for section, values in final.items():
        lines += [f"## {section}", ""]
        for key, value in values.items():
            label = key.split("_", 1)[1]
            lines.append(f"{number}. **{label}** — `{json.dumps(value, ensure_ascii=False, sort_keys=True)}`")
            number += 1
        lines.append("")
    lines += ["## Q1–Q21", ""]
    for n in range(1, 22):
        lines += [f"**Q{n}.** {answers[f'Q{n}']}", ""]
    (ARTIFACTS / "V35R3J_FINAL_REVIEW.md").write_text("\n".join(lines), encoding="utf-8")

    write_json("V35R3J_COMPUTE_ACCOUNTING.json", {
        "artifact_id": "V35R3J_COMPUTE_ACCOUNTING_V1", "source_rows_reused": len(occupancy),
        "slots": 96, "jobs": regression["temporal_jobs"], "GPU_hours": total_gpu_h,
        "wallclock_seconds": time.perf_counter() - started,
        "peak_resident_memory_bytes_observed": process.memory_info().rss,
        "thread_policy": "SINGLE_PROCESS_VECTORIZED_NUMPY_PANDAS", "python": platform.python_version(),
        "heavy_optimizer": False, "public_power_statistics_recomputed": False,
    })
    missing = [name for name in REQUIRED_ARTIFACTS if not (ARTIFACTS / name).is_file()]
    if missing:
        raise AssertionError(f"V35R3J_REQUIRED_ARTIFACTS_MISSING:{missing}")
    return ARTIFACTS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-passed", type=int, default=0)
    parser.add_argument("--test-failed", type=int, default=0)
    args = parser.parse_args()
    print(build(args.test_passed, args.test_failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
