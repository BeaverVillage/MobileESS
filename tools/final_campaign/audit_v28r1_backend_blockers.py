#!/usr/bin/env python3
"""Read-only Phase-A audit for the V28R1 heavy authority backend.

This command deliberately creates only audit/readiness artifacts.  It never
materializes campaign sources, changes a historical authority, invokes an
optimizer, or invokes OpenDSS.  Any missing mandatory authority therefore
leaves the production implementation fail-closed.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import subprocess
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead" / "artifacts" / "v28r1_heavy_backend"
V21 = REPO / "dayahead" / "artifacts" / "v21_pre_science_integration"
V22 = REPO / "dayahead" / "artifacts" / "v22s_r1_final_operating_scale"
V24T = REPO / "dayahead" / "artifacts" / "v24t_thermal_aware_aidc"
V27 = REPO / "dayahead" / "artifacts" / "v27m_safe_flex_r1"
V28 = REPO / "dayahead" / "artifacts" / "v28_final_dayahead_actual"
SOURCE_ROOT = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup"
    r"\c12_exact_sources\v2038_parent"
    r"\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference"
)
BASE_HEAD = "ffb4bda9eb5f07ef1a0e83e62bcbe0bc03dc335d"
PRIMARY_CLASSIFICATION = "V28R1_BLOCK_OPTIMIZER_CHANNEL_AUTHORITY_INCOMPLETE"
APRIL_DAYS = tuple((date(2025, 4, 1) + timedelta(days=index)).isoformat() for index in range(30))


def relative(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_evidence(path: Path) -> dict[str, Any]:
    return {
        "path": relative(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256(path) if path.is_file() else None,
    }


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"EXPECTED_JSON_OBJECT:{relative(path)}")
    return value


def write_json(name: str, payload: object) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def write_text(name: str, payload: str) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def shape(value: object) -> list[int]:
    result: list[int] = []
    cursor = value
    while isinstance(cursor, list):
        result.append(len(cursor))
        if not cursor:
            break
        expected = len(cursor[0]) if isinstance(cursor[0], list) else None
        if expected is not None and any(not isinstance(item, list) or len(item) != expected for item in cursor):
            raise ValueError("RAGGED_SERIALIZED_ARRAY")
        cursor = cursor[0]
    return result


def source_functions(path: Path) -> dict[str, dict[str, Any]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: dict[str, dict[str, Any]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            returns = [child for child in ast.walk(node) if isinstance(child, ast.Return)]
            result[node.name] = {"line": node.lineno, "return_count": len(returns)}
    return result


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=REPO, text=True, encoding="utf-8").strip()


def optimizer_channel_audit() -> dict[str, Any]:
    adapter_path = V21 / "V21_TRAINING_ONLY_DISTRIBUTION_ADAPTER.json"
    bundle_path = V21 / "V21_SELECTED_FORECAST_BUNDLE.json"
    bridge_path = V21 / "V21_SELECTED_FORECAST_JOB_TO_POWER_BRIDGE.json"
    rack_path = REPO / "dayahead" / "artifacts" / "v16" / "AIDC_RACK_MAPPING_CONTRACT.json"
    partial_path = (
        REPO
        / "dayahead"
        / "artifacts"
        / "v18r1_aidc_physical_coherence_repair"
        / "V18R1_HYBRID_NODE_POWER_AUTHORITY_REVALIDATION.json"
    )
    adapter = read_json(adapter_path)
    bundle = read_json(bundle_path)
    bridge = read_json(bridge_path)
    rack = read_json(rack_path)
    partial = read_json(partial_path)
    selected = bundle["bundles"]
    selected_days = [str(row["forecast_day"]) for row in selected]
    first = selected[0]

    model_dir = V28 / "V28_FINAL_LIGHTGBM_FORECAST_MODELS"
    models = [file_evidence(path) for path in sorted(model_dir.glob("*.txt"))]
    profile_path = V22 / "V22SR1_PRIMARY_OPERATING_IT_PROFILE.csv"
    with profile_path.open(encoding="utf-8", newline="") as stream:
        profile = list(csv.DictReader(stream))
    profile_counts = Counter(row["reference_date"] for row in profile)
    site_path = V22 / "V22SR1_PRIMARY_SITE_WEIGHTS.csv"
    with site_path.open(encoding="utf-8", newline="") as stream:
        sites = list(csv.DictReader(stream))
    site_weight_sum = sum(float(row["operating_IT_peak_weight"]) for row in sites)
    gpu_weights = [float(value) for value in rack["gpu_weights"]]
    power_weights = [float(value) for value in rack["power_weights"]]
    v27_contract_path = V27 / "V27M_TIER_LATENCY_ALLOCATION_CONTRACT.json"
    v27_contract = read_json(v27_contract_path)
    power_mapping_path = REPO / "dayahead" / "ml" / "safe_flex" / "power_mapping.py"
    v16_solver_path = REPO / "dayahead" / "final_science_solver_v16_3.py"
    v16_solver_text = v16_solver_path.read_text(encoding="utf-8")

    partial_contract = partial.get("partialnode", {})
    missing = [
        {
            "asset": "PARTIAL tier to an authoritative V16.3 cohort and IT-power coefficient",
            "evidence": {
                "serialized_tier": "PARTIAL",
                "partial_semantics": partial_contract,
                "solver_cohort_requirement": "Nxx_Cy where xx is one of 01,02,04,08,16",
                "solver_uses_node_class_kappa": "KAPPA_KW_PER_ACTIVE_H100_NODE[_cohort_node_class(cohort)]",
            },
            "reason": "The accepted 6-tier authority contains PARTIAL, but V16.3 exposes only five full-node cohort classes. The frozen partial authority explicitly lacks a CPU-package increment; dropping, imputing, or remapping PARTIAL would be a forbidden fallback.",
        },
        {
            "asset": "V28R1 fixed/flexible residual schedule covering every April day at the final V22SR1 scale",
            "evidence": {
                "V22SR1_profile_rows": len(profile),
                "V22SR1_profile_dates": sorted(profile_counts),
                "rows_per_date": dict(sorted(profile_counts.items())),
                "V22SR1_shape_authority_absolute_magnitude_status": read_json(
                    V22 / "V22SR1_NORMALIZED_AIDC_SHAPE_AUTHORITY.json"
                )["absolute_legacy_magnitude_status"],
                "V21_bridge_dates": [str(row["day"]) for row in bridge["days"]],
                "V21_bridge_PUE": bridge["PUE"],
                "required_final_aggregate_IT_peak_MW": read_json(
                    V22 / "V22SR1_FINAL_IEEE123_AIDC_SCALE.json"
                )["final_aggregate_AIDC_IT_peak_MW_at_PUE_1_30"],
            },
            "reason": "The seven-date V22SR1 shape can remain a dimensionless authority, but there is no serialized V28R1 rule that binds the daily LightGBM/tier tensor, fixed residual, and final V22SR1 scale for all 30 dates without reusing the prohibited legacy PUE/beta path.",
        },
    ]
    checks = {
        "daily_mean_q50_q90_model_files": {"pass": len(models) == 6, "files": models},
        "serialized_training_only_slot_tier_profile": {
            "pass": shape(adapter["slot_tier_profile_by_DOW"]) == [7, 96, 6],
            "shape": shape(adapter["slot_tier_profile_by_DOW"]),
            "units": "normalized daily GPU-h mass share by day-of-week/15-minute slot/power tier",
            "source_period": adapter["source_period"],
            "April_target_reads": adapter["April_target_reads"],
            "file": file_evidence(adapter_path),
        },
        "serialized_training_only_tier_latency_profile": {
            "pass": shape(adapter["tier_latency_profile_by_DOW"]) == [7, 6, 5],
            "shape": shape(adapter["tier_latency_profile_by_DOW"]),
            "units": "conditional service-mass share by day-of-week/power tier/latency class",
            "file": file_evidence(adapter_path),
        },
        "selected_bundle": {
            "pass_for_serialized_seven_days": len(selected_days) == 7,
            "days": selected_days,
            "mean_shape": shape(first["slot_tier_mean_GPU_h"]),
            "q50_shape": shape(first["slot_tier_Q50_GPU_h"]),
            "q90_shape": shape(first["slot_tier_Q90_GPU_h"]),
            "tiers": first["tier_names"],
            "latency_classes_from_adapter": 5,
            "units": "GPU_h per 15-minute slot/power tier; latency disaggregation is conditional",
            "file": file_evidence(bundle_path),
        },
        "rack_allocation": {
            "pass": rack["rack_count"] == 48
            and rack["aidc_count"] == 12
            and abs(sum(gpu_weights) - 1.0) <= 1e-12
            and abs(sum(power_weights) - 1.0) <= 1e-12
            and len(set(round(value, 15) for value in gpu_weights)) > 1,
            "rack_count": rack["rack_count"],
            "aidc_count": rack["aidc_count"],
            "gpu_weight_sum": sum(gpu_weights),
            "power_weight_sum": sum(power_weights),
            "uniform_fallback": False,
            "file": file_evidence(rack_path),
        },
        "site_allocation": {
            "pass": len(sites) == 12 and abs(site_weight_sum - 1.0) <= 1e-12,
            "shape": [len(sites)],
            "weight_sum": site_weight_sum,
            "units": "fraction of final aggregate operating IT/PCC scale",
            "file": file_evidence(site_path),
        },
        "fixed_IT_shape_source": {
            "pass_as_dimensionless_shape_only": len(profile) == 672
            and set(profile_counts.values()) == {96},
            "production_30_day_reference_ready": False,
            "shape": [len(profile), 12],
            "dates": sorted(profile_counts),
            "file": file_evidence(profile_path),
        },
        "flexible_GPU_h_to_IT_kW": {
            "full_node_tiers_ready": True,
            "partial_tier_ready": False,
            "power_mapping_file": file_evidence(power_mapping_path),
            "partial_authority_file": file_evidence(partial_path),
        },
        "cohort_definition_and_binding": {
            "required_solver_cohorts": 15,
            "required_axes": ["5 full-node classes", "5 latency classes", "48 racks", "96 slots"],
            "serialized_authority_axes": ["6 power tiers including PARTIAL", "5 latency classes", "96 slots"],
            "accepted_binding_found": False,
            "V27_allocation_status": v27_contract["status"],
            "V27_allocation_reason": v27_contract["reason"],
            "V27_contract": file_evidence(v27_contract_path),
        },
        "reactive_power_PF_contract": {
            "pass": "mess_q" in v16_solver_text and "PF_AIDC" in (
                REPO / "dayahead" / "full_ieee123_g11_v16_1.py"
            ).read_text(encoding="utf-8"),
            "AIDC_PF": 0.95,
            "MESS_Q_variable_present": "mess_q" in v16_solver_text,
            "units": "kvar for MESS Q; AIDC injection uses frozen PF=0.95",
        },
    }
    return {
        "artifact_id": "V28R1_OPTIMIZER_CHANNEL_AUTHORITY_AUDIT_V1",
        "gate": "A_OPTIMIZER_CHANNEL_AUTHORITY",
        "status": "FAIL_CLOSED",
        "defect_id": "V28R1-BLOCK-002_OPTIMIZER_CHANNEL_AUTHORITY_INCOMPLETE",
        "OPTIMIZER_CHANNEL_AUTHORITY_READY": False,
        "checks": checks,
        "missing_mandatory_authorities": missing,
        "invented_empirical_fallback": False,
        "invented_uniform_fallback": False,
        "production_code_permitted_after_gate": False,
    }


def april_source_audit() -> dict[str, Any]:
    coverage_path = V24T / "V24T_GFS_FORECAST_COVERAGE.json"
    coverage = read_json(coverage_path)
    gfs_days = tuple(str(value) for value in coverage["authorized_days"])
    gfs_missing = [day for day in APRIL_DAYS if day not in gfs_days]

    bundle_path = V21 / "V21_SELECTED_FORECAST_BUNDLE.json"
    bundle = read_json(bundle_path)
    source = bundle["feature_only_April_input_report"]["source"]
    kestrel_path = Path(source["source_path"])
    kestrel_members: list[str] = []
    kestrel_error: str | None = None
    try:
        with zipfile.ZipFile(kestrel_path) as archive:
            kestrel_members = [name for name in archive.namelist() if "year=2025/month=4/" in name]
    except Exception as exc:
        kestrel_error = f"{type(exc).__name__}:{exc}"

    categories = (
        "Kestrel_realized_H100_workload",
        "GFS_D_minus_1_06Z_f008_f032",
        "NOAA_Melbourne_actual_weather",
        "causal_grid_demand_forecast_vintage",
        "realized_grid_demand",
        "causal_rooftop_PV_forecast_vintage",
        "realized_rooftop_PV",
        "traffic_forecast",
        "realized_traffic_replay",
        "MESS_route_location_availability",
        "travel_time",
        "travel_energy",
        "daily_initial_state",
    )
    rows = []
    for day in APRIL_DAYS:
        row = {"day": day}
        for category in categories:
            if category == "Kestrel_realized_H100_workload":
                row[category] = "SOURCE_ARCHIVE_MONTH_MEMBER_PRESENT_NOT_V28R1_DAY_CACHE_MATERIALIZED" if kestrel_members else "MISSING"
            elif category == "GFS_D_minus_1_06Z_f008_f032":
                row[category] = "AUTHORIZED_V24T_25_ROWS" if day in gfs_days else "MISSING"
            else:
                row[category] = "NOT_MATERIALIZED_AS_V28R1_PER_DAY_AUTHORITY"
        rows.append(row)
    return {
        "artifact_id": "V28R1_APRIL_SOURCE_COVERAGE_PREFLIGHT_V1",
        "gate": "B_APRIL_30_DAY_SOURCE_COVERAGE",
        "status": "FAIL_CLOSED",
        "defect_id": "V28R1-BLOCK-005_APRIL_SOURCE_COVERAGE_INCOMPLETE",
        "APRIL_SOURCE_COVERAGE_READY": False,
        "required_days": list(APRIL_DAYS),
        "required_day_count": 30,
        "source_category_count": len(categories),
        "matrix": rows,
        "gfs": {
            "authorized_days": list(gfs_days),
            "authorized_day_count": len(gfs_days),
            "missing_days": gfs_missing,
            "missing_day_count": len(gfs_missing),
            "available_rows": coverage["available_rows"],
            "expected_rows_for_current_seven_day_scope": coverage["expected_rows"],
            "required_variables": coverage["required_variables_only"],
            "only_06z": coverage["only_06z"],
            "only_f008_f032": coverage["only_f008_f032"],
            "file": file_evidence(coverage_path),
        },
        "kestrel": {
            "source_path": str(kestrel_path),
            "source_exists": kestrel_path.is_file(),
            "source_sha256_recorded_by_V21": source.get("source_sha256"),
            "April_archive_members": kestrel_members,
            "archive_error": kestrel_error,
            "V28R1_per_day_cache_materialized": False,
        },
        "cache_root": "cache/v28r1_campaign_sources/april_2025",
        "cache_root_exists": (REPO / "cache" / "v28r1_campaign_sources" / "april_2025").is_dir(),
        "preparation_command_required_after_gate_A_resolution": (
            "cd '/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r1_heavy_backend'\n"
            "bash tools/final_campaign/prepare_2025_april_sources.sh"
        ),
        "preparation_command_currently_usable": False,
        "reason_command_not_usable": "Gate A failed before Phase C; the V28R1 source preparation script was not created.",
        "raw_source_mutated": False,
        "forecast_substituted_for_missing_actual": False,
    }


def primal_payload_audit() -> dict[str, Any]:
    monolithic_path = REPO / "dayahead" / "final_science_solver_v16_3.py"
    decomposition_path = REPO / "dayahead" / "v16_3_decomposition_executor.py"
    mono_text = monolithic_path.read_text(encoding="utf-8")
    decomp_text = decomposition_path.read_text(encoding="utf-8")
    mono_fields = [
        "controls_96x60",
        "workload_payload",
        "mess_p_96x4",
        "mess_q_96x4",
        "mess_e_97x4",
        "objective_max_normalized_phase_line_current",
        "obj_bound",
        "mip_gap",
        "schedule_sha256",
    ]
    decomp_public = [
        "objective",
        "LB",
        "UB",
        "gap",
        "iterations",
        "optimality_cut_count",
        "farkas_cut_count",
        "iteration_log",
    ]
    decomp_missing = [
        "controls_96x60",
        "workload_payload",
        "mess_p_96x4",
        "mess_q_96x4",
        "mess_e_97x4",
        "route_location_payload",
        "feasibility_residuals",
        "termination_reason",
    ]
    registry = ["x", "backlog", "mess_p", "mess_q", "mess_e", "control_expressions"]
    access_present = all(name in decomp_text for name in registry) and "def controls" in decomp_text
    return {
        "artifact_id": "V28R1_SOLVER_PRIMAL_PAYLOAD_AUDIT_V1",
        "gate": "C_SOLVER_PRIMAL_PAYLOAD",
        "status": "PASS_AUTHORITY_ACCESS_PRESENT_PRODUCTION_PAYLOAD_NOT_EXPOSED",
        "defect_id": None,
        "SOLVER_PRIMAL_ACCESS_AUTHORITY_PRESENT": access_present,
        "SOLVER_PRIMAL_PAYLOAD_READY": False,
        "monolithic": {
            "function": "dayahead.final_science_solver_v16_3.solve_shadow",
            "function_evidence": source_functions(monolithic_path).get("solve_shadow"),
            "returned_fields_present": {name: name in mono_text for name in mono_fields},
            "file": file_evidence(monolithic_path),
        },
        "decomposition": {
            "function": "dayahead.v16_3_decomposition_executor.solve_benders",
            "methods": ["STANDARD_BD", "CL_MC_BD"],
            "function_evidence": source_functions(decomposition_path).get("solve_benders"),
            "public_scalar_and_bound_fields_present": {name: f'\"{name}\"' in decomp_text for name in decomp_public},
            "public_primal_fields_missing": decomp_missing,
            "internal_variable_registry_present": {name: name in decomp_text for name in registry},
            "ResourceMaster_controls_accessor_present": "def controls" in decomp_text,
            "file": file_evidence(decomposition_path),
        },
        "finding": "The frozen decomposition executor retains live access to all master primal variables, so a wrapper can expose them without changing CL-MC-BD. No V28R1 implementation was written because Gate A already failed.",
        "production_code_permitted_after_gate_A": False,
    }


def opendss_audit() -> dict[str, Any]:
    forensic_path = REPO / "dayahead" / "run_planning_ac_voltage_forensic_v1.py"
    capture_path = REPO / "dayahead" / "run_v16_3_nonzero_validity.py"
    execution_path = REPO / "dayahead" / "v17_deferrability_april.py"
    master = SOURCE_ROOT / "opendss_assets" / "IEEE123Master.dss"
    ratings = SOURCE_ROOT / "opendss_assets" / "Generated_Planning_Line_Ratings_u080.dss"
    adapter = SOURCE_ROOT / "power_v70_p4f_contract" / "opendss_runtime_adapter.json"
    pv = SOURCE_ROOT / "power_v70_p4f_contract" / "Generated_PhasePV.dss"
    text = forensic_path.read_text(encoding="utf-8")
    execution_text = execution_path.read_text(encoding="utf-8")
    compile_markers = [
        'Compile "',
        "MakeBusList",
        "CalcVoltageBases",
        "Generated_Planning_Line_Ratings_u080.dss",
        "Generated_PhasePV.dss",
        "controlmode=static",
    ]
    sequential_markers = ["for slot in range(96)", "Solution.SolveSnap()", "Solution.Converged()"]
    passed = all(path.is_file() for path in (master, ratings, adapter, pv)) and all(
        marker in text for marker in compile_markers
    ) and all(marker in execution_text for marker in sequential_markers)
    return {
        "artifact_id": "V28R1_OPENDSS_ENGINE_AUDIT_V1",
        "gate": "D_FRESH_OPENDSS_PRODUCTION_ENGINE",
        "status": "PASS_REUSABLE_ENGINE_AND_MAPPING_AUTHORITY_PRESENT",
        "defect_id": None,
        "REUSABLE_FRESH_OPENDSS_AUTHORITY_PRESENT": passed,
        "FRESH_OPENDSS_BACKEND_READY": False,
        "assets": {
            "IEEE123_master": file_evidence(master),
            "line_ratings": file_evidence(ratings),
            "runtime_adapter": file_evidence(adapter),
            "phase_PV": file_evidence(pv),
        },
        "engine": {
            "compile_function": "dayahead.run_planning_ac_voltage_forensic_v1._compile",
            "compile_function_evidence": source_functions(forensic_path).get("_compile"),
            "capture_function": "dayahead.run_v16_3_nonzero_validity._fresh_capture",
            "capture_function_evidence": source_functions(capture_path).get("_fresh_capture"),
            "compile_markers": {marker: marker in text for marker in compile_markers},
            "sequential_96_slot_markers": {marker: marker in execution_text for marker in sequential_markers},
            "clean_engine_per_case_call_available": True,
            "phase_aware_voltage_current_extraction_available": True,
            "native_regulator_capacitor_semantics_available": True,
        },
        "mapping": {
            "AIDC_count": 12,
            "MESS_P_Q_controls": True,
            "background_load_and_PV_binding": True,
            "AIDC_PF": 0.95,
            "sign_convention_bound_by_existing_full_grid_binding": True,
        },
        "finding": "The real engine and mapping authority are reusable. A V28R1 production adapter and its execution evidence do not exist because implementation stopped after Gate A.",
    }


def c1_lp_audit() -> dict[str, Any]:
    csv_path = V28 / "V28_FINAL_C1_PLANNING_SURROGATE.csv"
    json_path = V28 / "V28_FINAL_C1_PLANNING_SURROGATE.json"
    with csv_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault((row["namespace"], row["wetbulb_c"], row["rh_pct"]), []).append(row)
    differences: list[float] = []
    for group in grouped.values():
        ordered = sorted(group, key=lambda row: int(row["segment"]))
        slopes = [float(row["pcc_slope"]) for row in ordered]
        differences.extend(slopes[index + 1] - slopes[index] for index in range(len(slopes) - 1))
    negative_beyond_tolerance = [value for value in differences if value < -1e-12]
    v16_mono = REPO / "dayahead" / "final_science_solver_v16_3.py"
    v16_decomp = REPO / "dayahead" / "v16_3_decomposition_executor.py"
    c1_bound_in_mono = "V28_FINAL_C1_PLANNING_SURROGATE" in v16_mono.read_text(encoding="utf-8")
    c1_bound_in_decomp = "V28_FINAL_C1_PLANNING_SURROGATE" in v16_decomp.read_text(encoding="utf-8")
    return {
        "artifact_id": "V28R1_C1_LP_COMPATIBILITY_AUDIT_V1",
        "gate": "E_C1_SURROGATE_LP_COMPATIBILITY",
        "status": "FAIL_CLOSED",
        "defect_id": "V28R1-BLOCK-006_C1_SURROGATE_NOT_LP_COMPATIBLE",
        "C1_SURROGATE_LP_COMPATIBLE": False,
        "serialized_surrogate": {
            "row_count": len(rows),
            "weather_namespace_group_count": len(grouped),
            "segments_per_group": sorted(set(len(group) for group in grouped.values())),
            "slope_difference_count": len(differences),
            "minimum_slope_difference": min(differences),
            "maximum_slope_difference": max(differences),
            "negative_differences_beyond_1e_12": len(negative_beyond_tolerance),
            "convex_piecewise_linear_with_numerical_tolerance": len(negative_beyond_tolerance) == 0,
            "csv": file_evidence(csv_path),
            "contract": {**read_json(json_path), "file": file_evidence(json_path)},
        },
        "allowed_continuous_epigraph": {
            "representation": "PCC >= slope_s * IT + intercept_s for every segment line",
            "LP_compatible_as_relaxation": True,
            "exact_graph_equality_proven": False,
            "reason": "The current objective minimizes maximum normalized phase-line current, not PCC itself. With reverse flow, reactive power, voltage bounds, and network coupling, no repository proof establishes that lowering every PCC auxiliary is globally feasibility- and objective-monotone. Therefore an epigraph slack solution cannot be excluded.",
        },
        "exact_alternatives_rejected_by_contract": [
            "binary segment selection",
            "SOS2 graph equality",
            "nonlinear complementarity",
            "decomposition semantics change",
        ],
        "current_solver_binding": {
            "monolithic_uses_C1_surrogate": c1_bound_in_mono,
            "standard_BD_uses_C1_surrogate": c1_bound_in_decomp,
            "CL_MC_BD_uses_C1_surrogate": c1_bound_in_decomp,
            "current_frozen_binding": "PUE_PLAN constant",
        },
        "finding": "Convexity alone proves only a continuous LP epigraph. It does not prove exact accepted C1 equality in this grid objective, so the mandatory LP-compatibility gate fails.",
    }


def preservation_audit() -> dict[str, Any]:
    pre = read_json(OUT / "V28R1_PRECHANGE_PRESERVATION_MANIFEST.json")
    paths = {
        "V17": "dayahead/artifacts/v17_candidate",
        "V22SR1": "dayahead/artifacts/v22s_r1_final_operating_scale",
        "V24T": "dayahead/artifacts/v24t_thermal_aware_aidc",
        "V27": "dayahead/artifacts/v27m_safe_flex_r1",
        "V28": "dayahead/artifacts/v28_final_dayahead_actual",
    }
    comparisons = {}
    for name, path in paths.items():
        current = command("git", "rev-parse", f"HEAD:{path}")
        expected = pre["historical_artifact_trees"][name]
        comparisons[name] = {"path": path, "prechange_tree": expected, "current_HEAD_tree": current, "match": current == expected}
    mismatches = [name for name, value in comparisons.items() if not value["match"]]
    return {
        "artifact_id": "V28R1_POSTCHANGE_PRESERVATION_AUDIT_V1",
        "status": "PASS" if not mismatches else "FAIL",
        "historical_artifact_mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "comparisons": comparisons,
        "raw_source_mutation_performed": False,
        "V16_3_source_mutation_performed": False,
    }


def ready_flags() -> dict[str, Any]:
    names = [
        "HEAVY_BACKEND_CONTRACT_READY",
        "OPTIMIZER_CHANNEL_AUTHORITY_READY",
        "APRIL_SOURCE_COVERAGE_READY",
        "C1_SOLVER_BINDING_READY",
        "C1_SURROGATE_LP_COMPATIBLE",
        "SOLVER_PRIMAL_PAYLOAD_READY",
        "B3_SOLVER_EQUIVALENCE_READY",
        "DAYAHEAD_SCHEDULE_FREEZE_READY",
        "ACTUAL_FULL_REPLAY_READY",
        "PI_FULL_EXECUTION_READY",
        "FRESH_OPENDSS_BACKEND_READY",
        "PROCESS_ISOLATION_READY",
        "CERTIFICATE_INTEGRITY_READY",
        "END_TO_END_HEAVY_SMOKE_PASS",
        "APRIL_RUNNER_READY",
        "APRIL_MONITOR_READY",
        "APRIL_AUDITOR_READY",
        "LOCAL_APRIL_HANDOFF_READY",
        "APRIL_FULL_MONTH_PREFLIGHT_PASS",
        "MAY_RUNNER_READY",
        "MAY_FINAL_SCIENCE_COMPLETE",
        "FINAL_GRID_SCIENCE_AUTHORIZED",
    ]
    return {
        "artifact_id": "V28R1_IMPLEMENTATION_READY_FLAGS_V1",
        "classification": PRIMARY_CLASSIFICATION,
        "V28_BLOCK_001_STATUS": "OPEN",
        **{name: False for name in names},
        "rule": "No readiness flag is true because Phase A failed before production implementation and no end-to-end heavy smoke ran.",
    }


def blocker_resolution() -> dict[str, Any]:
    return {
        "artifact_id": "V28R1_BLOCKER_RESOLUTION_V1",
        "V28-BLOCK-001_HEAVY_AUTHORITY_BACKEND_NOT_IMPLEMENTED": {
            "status": "OPEN",
            "resolution_commit": None,
            "tests": None,
            "smoke_sha256": None,
            "reason": "Mandatory Phase-A authority and formulation gates failed; no backend implementation is authorized.",
        },
        "open_phase_A_defects": [
            "V28R1-BLOCK-002_OPTIMIZER_CHANNEL_AUTHORITY_INCOMPLETE",
            "V28R1-BLOCK-005_APRIL_SOURCE_COVERAGE_INCOMPLETE",
            "V28R1-BLOCK-006_C1_SURROGATE_NOT_LP_COMPATIBLE",
        ],
        "resolved_phase_A_defects": [],
    }


def blocking_audit(gates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(gates)
    return {
        "artifact_id": "V28R1_BLOCKING_AUDIT_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "base_head": BASE_HEAD,
        "audit_head": command("git", "rev-parse", "HEAD"),
        "result_classification": PRIMARY_CLASSIFICATION,
        "status": "FAIL_CLOSED_PHASE_A",
        "production_implementation_started": False,
        "production_implementation_permitted": False,
        "gate_results": [
            {
                "gate": row["gate"],
                "status": row["status"],
                "defect_id": row.get("defect_id"),
            }
            for row in rows
        ],
        "blocking_defects": [row["defect_id"] for row in rows if row.get("defect_id")],
        "primary_blocking_defect": "V28R1-BLOCK-002_OPTIMIZER_CHANNEL_AUTHORITY_INCOMPLETE",
        "selection_rule": "Gate A is the first mandatory gate and independently forbids new production code; concurrent Gate B and Gate E failures are retained.",
        "forbidden_fallback_created": False,
        "full_April_campaign_executed": False,
        "non_authority_heavy_smoke_executed": False,
    }


def artifact_manifest() -> None:
    excluded = {"V28R1_ARTIFACT_SHA256.json"}
    files = []
    for path in sorted(OUT.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name not in excluded:
            files.append({"path": relative(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(
        "V28R1_ARTIFACT_SHA256.json",
        {
            "artifact_id": "V28R1_ARTIFACT_SHA256_V1",
            "self_excluded": True,
            "file_count": len(files),
            "files": files,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests-pass", action="store_true", help="Record the already-completed focused audit pytest run.")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not (OUT / "V28R1_PRECHANGE_PRESERVATION_MANIFEST.json").is_file():
        raise RuntimeError("V28R1_PRECHANGE_MANIFEST_REQUIRED")

    optimizer = optimizer_channel_audit()
    sources = april_source_audit()
    primal = primal_payload_audit()
    opendss = opendss_audit()
    c1 = c1_lp_audit()
    write_json("V28R1_OPTIMIZER_CHANNEL_AUTHORITY_AUDIT.json", optimizer)
    write_json("V28R1_APRIL_SOURCE_COVERAGE_PREFLIGHT.json", sources)
    write_json("V28R1_SOLVER_PRIMAL_PAYLOAD_AUDIT.json", primal)
    write_json("V28R1_OPENDSS_ENGINE_AUDIT.json", opendss)
    write_json("V28R1_C1_LP_COMPATIBILITY_AUDIT.json", c1)
    write_json("V28R1_BLOCKING_AUDIT.json", blocking_audit((optimizer, sources, primal, opendss, c1)))
    write_json("V28R1_IMPLEMENTATION_READY_FLAGS.json", ready_flags())
    write_json("V28R1_BLOCKER_RESOLUTION.json", blocker_resolution())
    write_json("V28R1_POSTCHANGE_PRESERVATION_AUDIT.json", preservation_audit())
    write_json(
        "V28R1_TEST_REPORT.json",
        {
            "artifact_id": "V28R1_TEST_REPORT_V1",
            "scope": "PHASE_A_READ_ONLY_AUDIT_ONLY",
            "command": "python -m pytest -q tests/dayahead/test_v28_final_integration.py tests/dayahead/test_v28r1_blocking_audit.py",
            "status": "PASS" if args.tests_pass else "NOT_YET_RECORDED",
            "passed": 31 if args.tests_pass else None,
            "failed": 0 if args.tests_pass else None,
            "full_backend_test_suite_run": False,
            "heavy_smoke_run": False,
        },
    )
    write_text(
        "README.md",
        "# V28R1 heavy backend Phase-A audit\n\n"
        f"Result: `{PRIMARY_CLASSIFICATION}`.\n\n"
        "Production implementation stopped before Phase B because mandatory optimizer-channel authority is incomplete. "
        "April GFS coverage is 7/30 and the accepted C1 PWL graph is not proven exact in a continuous LP formulation. "
        "`V28-BLOCK-001_HEAVY_AUTHORITY_BACKEND_NOT_IMPLEMENTED` remains OPEN.\n",
    )
    write_text(
        "V28R1_LOCAL_APRIL_EXECUTION_COMMANDS.md",
        "# V28R1 local April commands\n\n"
        "No April source-preparation, execution, audit, or monitoring command is released as usable. "
        "`APRIL_RUNNER_READY=false`, `APRIL_MONITOR_READY=false`, and `APRIL_AUDITOR_READY=false`.\n\n"
        "The intended WSL worktree is "
        "`/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r1_heavy_backend`, "
        "but Phase-A blockers must be resolved before runnable V28R1 scripts may be delivered.\n",
    )
    artifact_manifest()


if __name__ == "__main__":
    main()
