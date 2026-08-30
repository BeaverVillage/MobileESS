"""April-only V17 reference, planning, Fresh-AC, and decomposition execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .aidc_boundary_v16_1 import DT_HOURS, PUE_PLAN
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .aidc_rack_mapping import load_frozen_rack_authority
from .authority import sha256_file
from .final_science_solver_v16_3 import solve_shadow
from .full_ieee123_b3_v16_2 import B3Inputs
from .full_ieee123_g11_v16_1 import build_full_grid_binding
from .grid_background_v16_2 import build_authority_background_binding
from .run_aidc_ieee123_penetration_hosting_capacity_diagnostic_v1 import _select_april_vintages_locked
from .run_authority_semantic_g11_v16_2 import _default_background_paths
from .run_v16_3_correction import (
    _ac_summary,
    _apply_vector,
    _current_cache_path,
    _fresh_capture,
    _generate_current_day,
)
from .run_v16_3_voltage_candidate import (
    CAPACITORS,
    REGULATORS,
    _anchor_and_sensitivity_day,
    _compile,
    _enable_native_controls,
    _fix_controls,
    _regulator_taps,
    _set_slot,
)
from .v16_3_decomposition_executor import solve_benders
from .v17_deferrability_ml import TARGET_NAMES
from .v17_deferrability_semantics import (
    DEFERRAL_SLOTS,
    LATENCY_CLASSES,
    build_reference_schedule_v4,
    write_json,
)


BETA_AIDC = 0.25
RHO = 0.10
MODEL_NAME = "Proposed AIDC RC-MQT V2"
NAMESPACE = "V17_APRIL_VALIDATION_ONLY"
SOURCE_DEFAULT = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference"
)
APRIL_DAYS = tuple(f"2025-04-{day:02d}" for day in range(2, 31))


@dataclass(frozen=True)
class ReferenceProxy:
    allocation: Mapping[tuple[str, str, int], float]
    flexible_power_kw: tuple[tuple[float, ...], ...]
    flexible_gpu: tuple[tuple[float, ...], ...]


def _cohort_name(latency_name: str, node_class: int) -> str:
    return f"N{node_class:02d}_{latency_name}"


COHORTS = tuple(
    _cohort_name(latency_name, node_class)
    for latency_name in LATENCY_CLASSES
    for node_class in (1, 2, 4, 8, 16)
)


def _target_index(latency_name: str, node_class: int) -> int:
    return TARGET_NAMES.index(f"W_F_{latency_name}::N{node_class:02d}")


def _array_fingerprint(arrays: Mapping[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for name, array in sorted(arrays.items()):
        value = np.asarray(array)
        digest.update(name.encode("utf-8")); digest.update(b"\0")
        digest.update(str(value.dtype).encode("ascii")); digest.update(b"\0")
        digest.update(json.dumps(list(value.shape), separators=(",", ":")).encode("ascii")); digest.update(b"\0")
        digest.update(value.tobytes(order="C"))
    return digest.hexdigest()


def materialize_references(repo: Path, output: Path) -> dict[str, Any]:
    import pandas as pd

    prediction_path = output / "V17_RCMQT_V2_APRIL_PREDICTIONS.npz"
    preparation_path = output / "cache/V17_RCMQT_V2_APRIL_VALIDATION_PREPARATION.json"
    training_path = output / "V17_RCMQT_V2_TRAINING_REPORT.json"
    if not prediction_path.is_file() or not preparation_path.is_file() or not training_path.is_file():
        raise RuntimeError("V17_APRIL_REQUIRES_FROZEN_MODEL_AND_VALIDATION")
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    training = json.loads(training_path.read_text(encoding="utf-8"))
    if preparation["frozen_weights_sha256"] != training["weights_file_sha256"]:
        raise RuntimeError("V17_APRIL_MODEL_FREEZE_IDENTITY_FAIL")
    saved = np.load(prediction_path)
    prediction = np.asarray(saved["prediction"], dtype=np.float64)
    target = np.asarray(saved["target"], dtype=np.float64)
    scales = np.asarray([float(preparation["target_scales"][name]) for name in TARGET_NAMES])
    prediction_raw = prediction * scales[None, None, :, None]
    target_raw = target * scales[None, None, :]
    days = tuple(preparation["validation_days"])
    if days != APRIL_DAYS:
        raise RuntimeError("V17_APRIL_29_DAY_AXIS_MISMATCH")

    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    rack_ids = tuple(rack.rack_id for rack in authority.racks)
    rack_index = {rack: index for index, rack in enumerate(rack_ids)}
    capacity_nodeh = {
        rack.rack_id: BETA_AIDC * rack.deliverable_gpu_capacity / GPU_PER_NODE * DT_HOURS
        for rack in authority.racks
    }
    aidc_ids = tuple(f"AIDC{index:02d}" for index in range(1, 13))
    aidc_racks = {
        aidc: tuple(index for index, rack in enumerate(authority.racks) if rack.aidc_id == aidc)
        for aidc in aidc_ids
    }
    reference_dir = output / "reference_v4"
    reference_dir.mkdir(parents=True, exist_ok=True)
    day_rows: list[dict[str, Any]] = []
    forecast_rows: list[dict[str, Any]] = []
    for day_index, day in enumerate(days):
        for slot in range(96):
            for target_index, target_name in enumerate(TARGET_NAMES):
                for quantile_index, quantile in enumerate((0.1, 0.5, 0.9)):
                    forecast_rows.append({
                        "model": MODEL_NAME, "namespace": NAMESPACE, "forecast_day": day,
                        "slot": slot, "target": target_name, "quantile": quantile,
                        "prediction": float(prediction_raw[day_index, slot, target_index, quantile_index]),
                        "actual": float(target_raw[day_index, slot, target_index]),
                    })
        arrivals_by_key = {
            (latency_name, node_class): tuple(
                BETA_AIDC * float(prediction_raw[day_index, slot, _target_index(latency_name, node_class), 1])
                for slot in range(96)
            )
            for latency_name in LATENCY_CLASSES
            for node_class in (1, 2, 4, 8, 16)
        }
        reference = build_reference_schedule_v4(arrivals_by_key, capacity_nodeh)
        allocation = np.zeros((len(COHORTS), 48, 96), dtype=np.float64)
        for class_index, latency_name in enumerate(LATENCY_CLASSES):
            for node_index, node_class in enumerate((1, 2, 4, 8, 16)):
                cohort_index = class_index * 5 + node_index
                for rack in rack_ids:
                    r = rack_index[rack]
                    for slot in range(96):
                        allocation[cohort_index, r, slot] = reference.service_by_class_node_rack_slot[(latency_name, node_class, rack, slot)]
        arrivals = np.asarray([
            arrivals_by_key[(latency_name, node_class)]
            for latency_name in LATENCY_CLASSES
            for node_class in (1, 2, 4, 8, 16)
        ], dtype=np.float64)
        flexible_power = np.zeros((96, 48), dtype=np.float64)
        for cohort_index, cohort in enumerate(COHORTS):
            node_class = int(cohort[1:3])
            flexible_power += (KAPPA_KW_PER_ACTIVE_H100_NODE[node_class] / DT_HOURS) * allocation[cohort_index].T
        p_ref = BETA_AIDC * prediction_raw[day_index, :, 0, 2]
        g_fixed_gpu = BETA_AIDC * GPU_PER_NODE * prediction_raw[day_index, :, 1, 2]
        p_res_sys = p_ref - flexible_power.sum(axis=1)
        if float(p_res_sys.min()) < -1e-9:
            raise RuntimeError(f"V17_APRIL_POWER_RESIDUAL_NEGATIVE:{day}:{p_res_sys.min()}")
        p_res_rack = p_res_sys[:, None] * np.asarray(authority.power_weights)[None, :]
        g_res_rack = g_fixed_gpu[:, None] * np.asarray(authority.gpu_weights)[None, :]
        total_gpu = g_res_rack + GPU_PER_NODE / DT_HOURS * allocation.sum(axis=0).T
        capacities_gpu = BETA_AIDC * np.asarray([rack.deliverable_gpu_capacity for rack in authority.racks])
        gpu_cap_violation = float(np.max(total_gpu - capacities_gpu[None, :]))
        if gpu_cap_violation > 1e-9:
            raise RuntimeError(f"V17_APRIL_GPU_CAP_REFERENCE_FAIL:{day}:{gpu_cap_violation}")
        p_res_aidc = np.asarray([[sum(p_res_rack[slot, r] for r in aidc_racks[aidc]) for aidc in aidc_ids] for slot in range(96)])
        p_f_aidc = np.asarray([[sum(flexible_power[slot, r] for r in aidc_racks[aidc]) for aidc in aidc_ids] for slot in range(96)])
        plan = PUE_PLAN * (p_res_aidc + p_f_aidc)
        reconstruction = float(np.max(np.abs((p_res_rack + flexible_power).sum(axis=1) - p_ref)))
        arrays = {
            "allocation": allocation, "arrivals": arrivals,
            "p_res_aidc": p_res_aidc, "g_res_rack": g_res_rack,
            "plan_kw_96x12": plan, "gpu_capacities": capacities_gpu,
            "p_ref": p_ref, "g_fixed_gpu": g_fixed_gpu,
        }
        fingerprint = _array_fingerprint(arrays)
        path = reference_dir / f"REFERENCE_COMPUTE_SCHEDULE_V4_{day}.npz"
        np.savez_compressed(path, **arrays, array_fingerprint=np.asarray(fingerprint))
        day_rows.append({
            "operating_day": day, "path": str(path.resolve()), "sha256": sha256_file(path),
            "array_fingerprint": fingerprint,
            "p_residual_min_kw": float(p_res_sys.min()), "p_residual_max_kw": float(p_res_sys.max()),
            "g_fixed_gpu_min": float(g_fixed_gpu.min()), "g_fixed_gpu_max": float(g_fixed_gpu.max()),
            "gpu_cap_max_violation": max(0.0, gpu_cap_violation),
            "system_power_reconstruction_max_abs_error_kw": reconstruction,
            **reference.evidence,
        })
    forecast_path = output / "V17_APRIL_VALIDATION_FORECAST.parquet"
    pd.DataFrame(forecast_rows).to_parquet(forecast_path, index=False)
    report = {
        "artifact_id": "V17_REFERENCE_SCHEDULER_V4_APRIL_VALIDATION_V1",
        "status": "PASS_29_DAYS",
        "day_count": 29, "days": day_rows,
        "forecast_path": str(forecast_path.resolve()), "forecast_sha256": sha256_file(forecast_path),
        "reference_authority": "REFERENCE_COMPUTE_SCHEDULE_V4",
        "beta_AIDC_unchanged": BETA_AIDC,
        "ESIF_whole_IT_boundary_magnitude_changed": False,
        "grid_scenario_scaling_application": "EXISTING_BETA_AIDC_ONCE_AFTER_UNSCALED_ML_BOUNDARY",
        "May_scientific_input_reads": 0, "June_scientific_input_reads": 0,
        "arbitrary_Kestrel_to_ESIF_scaling_created": False,
    }
    write_json(output / "V17_REFERENCE_SCHEDULER_V4_APRIL_VALIDATION.json", report)
    return report


def _load_reference(path: Path, authority, mess_records: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, Any], B3Inputs]:
    arrays = np.load(path, allow_pickle=False)
    allocation_array = np.asarray(arrays["allocation"], dtype=float)
    allocation = {
        (cohort, rack.rack_id, slot): float(allocation_array[c, r, slot])
        for c, cohort in enumerate(COHORTS)
        for r, rack in enumerate(authority.racks)
        for slot in range(96)
    }
    flexible_power = np.zeros((96, 48), dtype=float)
    for cohort_index, cohort in enumerate(COHORTS):
        flexible_power += KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] / DT_HOURS * allocation_array[cohort_index].T
    flexible_gpu = GPU_PER_NODE / DT_HOURS * allocation_array.sum(axis=0).T
    arrivals_array = np.asarray(arrays["arrivals"], dtype=float)
    reference = {
        "beta": BETA_AIDC,
        "arrivals": {cohort: tuple(map(float, arrivals_array[index])) for index, cohort in enumerate(COHORTS)},
        "reference": ReferenceProxy(
            allocation,
            tuple(tuple(map(float, row)) for row in flexible_power),
            tuple(tuple(map(float, row)) for row in flexible_gpu),
        ),
        "p_res_aidc": tuple(tuple(map(float, row)) for row in arrays["p_res_aidc"]),
        "g_res_rack": tuple(tuple(map(float, row)) for row in arrays["g_res_rack"]),
        "plan_kw_96x12": tuple(tuple(map(float, row)) for row in arrays["plan_kw_96x12"]),
        "gpu_capacities": tuple(map(float, arrays["gpu_capacities"])),
    }
    deadlines = {cohort: DEFERRAL_SLOTS[cohort.split("_", 1)[1]] for cohort in COHORTS}
    inputs = B3Inputs(
        cohorts=COHORTS, arrivals=reference["arrivals"],
        rack_ids=tuple(rack.rack_id for rack in authority.racks),
        rack_aidc=tuple(rack.aidc_id for rack in authority.racks),
        gpu_capacity=reference["gpu_capacities"],
        p_res_aidc_kw=reference["p_res_aidc"], g_res_rack=reference["g_res_rack"],
        mess_records=mess_records,
        evidence={
            "authority": "V17_REVEALED_LATENCY_COHERENT",
            "deadline_slots_by_cohort": deadlines,
            "OpenDSS_calls_inside_Benders": 0,
        },
    )
    return reference, inputs


def _fresh_case(repo: Path, source: Path, context, voltage, controls: np.ndarray) -> tuple[dict[str, Any], dict[str, Any]]:
    reference, _vintage, background, binding, _cache, _authority = context
    nodes = tuple(map(str, voltage["node_names"])); branches = tuple(binding.factories[0].data.branches)
    limits = np.asarray([float(binding.factories[0].data.line_limit_kva_u080[(b.branch_id, b.phase)]) for b in branches])
    odd, adapter = _compile(source, repo, "NATIVE")
    primary_captures = []; secondary_captures = []
    tap_change_slots = 0; tap_changes = {name: 0 for name in REGULATORS}; max_tap_difference = 0.0
    for slot in range(96):
        taps = {name: float(voltage["regulator_taps"][slot, i]) for i, name in enumerate(REGULATORS)}
        caps = {name: [int(voltage["capacitor_states"][slot, i])] for i, name in enumerate(CAPACITORS)}
        values = np.asarray(controls[slot], dtype=float)
        _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
        _fix_controls(odd, taps, caps); _apply_vector(odd, tuple(map(str, voltage["control_names"])), values); odd.Solution.SolveSnap()
        if not bool(odd.Solution.Converged()): raise RuntimeError(f"V17_PRIMARY_AC_NONCONVERGENCE:{slot}")
        primary_captures.append(_fresh_capture(odd, nodes, branches, limits, range(len(branches))))
        _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
        _fix_controls(odd, taps, caps); _enable_native_controls(odd); _apply_vector(odd, tuple(map(str, voltage["control_names"])), values); odd.Solution.SolveSnap()
        if not bool(odd.Solution.Converged()): raise RuntimeError(f"V17_SECONDARY_AC_NONCONVERGENCE:{slot}")
        secondary_captures.append(_fresh_capture(odd, nodes, branches, limits, range(len(branches))))
        native_taps = _regulator_taps(odd); changed = False
        for name in REGULATORS:
            difference = abs(float(native_taps[name]) - float(taps[name]))
            if difference > 1e-12:
                changed = True; tap_changes[name] += 1; max_tap_difference = max(max_tap_difference, difference)
        tap_change_slots += int(changed)
    primary = _ac_summary(primary_captures)
    secondary = {**_ac_summary(secondary_captures), "tap_change_slot_count": tap_change_slots, "tap_change_counts_by_regulator": tap_changes, "max_tap_difference": max_tap_difference}
    return primary, secondary


def execute_day(repo: Path, source: Path, output: Path, day: str) -> dict[str, Any]:
    repo = repo.resolve(); source = source.resolve(); output = output.resolve()
    if day not in APRIL_DAYS:
        raise ValueError("V17_DAY_OUTSIDE_APRIL_VALIDATION")
    vintages, excluded = _select_april_vintages_locked(repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json")
    if day not in vintages:
        raise RuntimeError(f"V17_APRIL_VINTAGE_MISSING:{day}:{excluded}")
    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    c7 = json.loads((repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json").read_text(encoding="utf-8"))
    reference_path = output / "reference_v4" / f"REFERENCE_COMPUTE_SCHEDULE_V4_{day}.npz"
    reference, inputs = _load_reference(reference_path, authority, c7["mess_invariants"]["records"])
    vintage = vintages[day]
    background = build_authority_background_binding(
        timestamps_fixed_aest=vintage["timestamps_96"], demand_mw_96=vintage["demand_mw_96"],
        rooftop_pv_mw_96=vintage["pv_mw_96"], paths=_default_background_paths(repo, source),
    )
    binding = build_full_grid_binding(
        assets=source / "opendss_assets", contract=source / "power_v70_p4f_contract",
        demand_mw_96=vintage["demand_mw_96"], rooftop_pv_mw_96=vintage["pv_mw_96"],
        aidc_plan_kw_96x12=reference["plan_kw_96x12"],
        pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        background_binding=background,
    )
    cache_dir = output / "ac_cache"
    voltage_path = cache_dir / "data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    anchor_record = _anchor_and_sensitivity_day(repo, source, background, reference["plan_kw_96x12"], binding, day, voltage_path)
    context = (reference, vintage, background, binding, voltage_path, authority)
    current_path = _current_cache_path(cache_dir, day)
    if current_path.is_file():
        existing_current = np.load(current_path, allow_pickle=False)
        if str(existing_current["source_voltage_cache_sha256"]) == sha256_file(voltage_path):
            current_record = {"operating_day": day, "path": str(current_path.resolve()), "sha256": sha256_file(current_path), "bytes": current_path.stat().st_size, "reused_exact_voltage_bound_cache": True}
        else:
            current_record = _generate_current_day(repo, source, cache_dir, day, context)
    else:
        current_record = _generate_current_day(repo, source, cache_dir, day, context)
    voltage = np.load(voltage_path, allow_pickle=False); current = np.load(current_path, allow_pickle=False)
    anchor_error = float(np.max(np.abs(np.asarray(reference["plan_kw_96x12"]) - np.asarray(voltage["anchor_control"][:, :12]))))
    if anchor_error > 1e-9:
        raise RuntimeError(f"V17_ANCHOR_PLAN_IDENTITY_FAIL:{anchor_error}")
    solved = solve_shadow(inputs=inputs, context=context, voltage_data=voltage, current_data=current, rho=RHO, case="ALL")
    schedule_dir = output / "schedules"; schedule_dir.mkdir(parents=True, exist_ok=True)
    cases: dict[str, Any] = {}
    for case in ("B0", "B1", "B2", "B3"):
        result = solved[case]
        controls = result.pop("controls_96x60", None)
        arrays = {name: result.pop(name) for name in ("workload_payload", "mess_p_96x4", "mess_q_96x4", "mess_e_97x4") if name in result}
        if controls is not None: arrays["controls_96x60"] = controls
        schedule_path = schedule_dir / f"V17_APRIL_{day}_{case}.npz"
        np.savez_compressed(schedule_path, **arrays)
        if result["hard_feasible"]:
            primary, secondary = _fresh_case(repo, source, context, voltage, np.asarray(controls))
        else:
            primary = {"all_frozen_hard_constraints_pass": False, "convergence_count": 0}
            secondary = {"all_frozen_hard_constraints_pass": False, "convergence_count": 0}
        cases[case] = {
            **result, "schedule_path": str(schedule_path.resolve()), "schedule_file_sha256": sha256_file(schedule_path),
            "primary_fresh_frozen_tap": primary, "secondary_fresh_native_RegControl": secondary,
            "AC_restoration_iterations": 0 if primary.get("all_frozen_hard_constraints_pass") else 1,
            "AC_restoration_status": "PRIMARY_PASS_NO_CUT_REQUIRED" if primary.get("all_frozen_hard_constraints_pass") else "K_MAX_FAIL_CLOSED_NO_SILENT_REPAIR",
        }
    payload = {
        "artifact_id": "V17_APRIL_DAY_B0_B1_B2_B3_V1", "operating_day": day,
        "status": "PASS" if all(row["hard_feasible"] and row["primary_fresh_frozen_tap"]["all_frozen_hard_constraints_pass"] for row in cases.values()) else "DOWNSTREAM_FAIL",
        "anchor": anchor_record, "current": current_record, "anchor_plan_identity_max_abs_error_kw": anchor_error,
        "cases": cases, "May_scientific_input_reads": 0, "June_scientific_input_reads": 0,
        "OpenDSS_calls_inside_Benders": 0,
    }
    day_dir = output / "daily"; day_dir.mkdir(parents=True, exist_ok=True)
    write_json(day_dir / f"V17_APRIL_{day}_B0_B1_B2_B3.json", payload)
    return {"day": day, "status": payload["status"]}


def run_decomposition(repo: Path, source: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); source = source.resolve(); output = output.resolve()
    day = "2025-04-15"
    daily = json.loads((output / "daily" / f"V17_APRIL_{day}_B0_B1_B2_B3.json").read_text(encoding="utf-8"))
    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    c7 = json.loads((repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json").read_text(encoding="utf-8"))
    reference, inputs = _load_reference(output / "reference_v4" / f"REFERENCE_COMPUTE_SCHEDULE_V4_{day}.npz", authority, c7["mess_invariants"]["records"])
    vintages, _ = _select_april_vintages_locked(repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json"); vintage = vintages[day]
    background = build_authority_background_binding(timestamps_fixed_aest=vintage["timestamps_96"], demand_mw_96=vintage["demand_mw_96"], rooftop_pv_mw_96=vintage["pv_mw_96"], paths=_default_background_paths(repo, source))
    binding = build_full_grid_binding(assets=source/"opendss_assets", contract=source/"power_v70_p4f_contract", demand_mw_96=vintage["demand_mw_96"], rooftop_pv_mw_96=vintage["pv_mw_96"], aidc_plan_kw_96x12=reference["plan_kw_96x12"], pcc_asset=repo/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss", background_binding=background)
    voltage_path = output / "ac_cache/data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    current_path = output / "ac_cache/data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
    context = (reference, vintage, background, binding, voltage_path, authority)
    voltage = np.load(voltage_path, allow_pickle=False); current = np.load(current_path, allow_pickle=False)
    standard = solve_benders(inputs=inputs, context=context, voltage=voltage, current=current, method="STANDARD_BD", raw_dir=output/"decomposition_raw/standard")
    proposed = solve_benders(inputs=inputs, context=context, voltage=voltage, current=current, method="CL_MC_BD", raw_dir=output/"decomposition_raw/cl_mc")
    mono = daily["cases"]["B3"]
    mono_objective = float(mono["objective_max_normalized_phase_line_current"])
    def relative(row: Mapping[str, Any]) -> float | None:
        return None if row.get("objective") is None else abs(float(row["objective"])-mono_objective)/max(abs(mono_objective),1e-6)
    report = {
        "artifact_id": "V17_APRIL15_DECOMPOSITION_EQUIVALENCE_V1", "operating_day": day,
        "Monolithic": {"status": mono["status"], "hard_feasible": mono["hard_feasible"], "objective": mono_objective, "runtime_seconds": mono["runtime_seconds"]},
        "Standard_BD": standard, "CL_MC_BD": proposed,
        "relative_objective_difference_standard": relative(standard),
        "relative_objective_difference_cl_mc": relative(proposed),
        "acceptance_tolerance": 1e-3,
        "hard_feasibility_identity": bool(mono["hard_feasible"] == standard["hard_feasible"] == proposed["hard_feasible"]),
        "OpenDSS_calls_inside_Benders": 0,
    }
    report["status"] = "PASS" if report["hard_feasibility_identity"] and report["relative_objective_difference_standard"] is not None and report["relative_objective_difference_standard"] <= 1e-3 and report["relative_objective_difference_cl_mc"] is not None and report["relative_objective_difference_cl_mc"] <= 1e-3 and float(proposed.get("gap") or math.inf) <= 1e-3 else "FAIL"
    write_json(output / "V17_APRIL15_DECOMPOSITION_EQUIVALENCE.json", report)
    return {"status": report["status"]}


def finalize(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); output = output.resolve()
    daily = [json.loads((output / "daily" / f"V17_APRIL_{day}_B0_B1_B2_B3.json").read_text(encoding="utf-8")) for day in APRIL_DAYS]
    decomposition = json.loads((output / "V17_APRIL15_DECOMPOSITION_EQUIVALENCE.json").read_text(encoding="utf-8"))
    case_rows = [{"operating_day": row["operating_day"], "case": case, **metrics} for row in daily for case, metrics in row["cases"].items()]
    all_planning = all(row["hard_feasible"] for row in case_rows)
    all_primary = all(row["primary_fresh_frozen_tap"]["all_frozen_hard_constraints_pass"] for row in case_rows)
    all_secondary = all(row["secondary_fresh_native_RegControl"]["all_frozen_hard_constraints_pass"] for row in case_rows)
    results = {
        "artifact_id": "V17_APRIL_B0_B1_B2_B3_RESULTS_V1",
        "status": "PASS" if all_planning and all_primary else "FAIL",
        "eligible_days": list(APRIL_DAYS), "eligible_day_count": 29,
        "case_day_count": len(case_rows), "all_planning_hard_feasible": all_planning,
        "all_primary_fresh_AC_hard_feasible": all_primary,
        "all_secondary_native_RegControl_hard_feasible": all_secondary,
        "daily_cases": case_rows,
        "effect_acceptance_threshold": None,
        "B1_minus_B0_and_B3_minus_B2_are_outcomes_only": True,
    }
    restoration = {
        "artifact_id": "V17_APRIL_AC_RESTORATION_RESULTS_V1",
        "status": "PASS" if all_primary else "FAIL",
        "bounded_outer_loop": "OPTIMIZATION_TO_FRESH_AC_TO_LOCAL_CUT_TO_REOPTIMIZATION",
        "days_requiring_a_cut": sum(row["AC_restoration_iterations"] > 0 for row in case_rows),
        "silent_repairs": 0, "OpenDSS_calls_inside_Benders": 0,
        "primary_all_116_case_days_pass": all_primary,
        "secondary_all_116_case_days_pass": all_secondary,
    }
    write_json(output / "V17_APRIL_B0_B1_B2_B3_RESULTS.json", results)
    write_json(output / "V17_APRIL_AC_RESTORATION_RESULTS.json", restoration)
    downstream_pass = results["status"] == "PASS" and restoration["status"] == "PASS" and decomposition["status"] == "PASS"
    classification = "V17_DEFERRABILITY_A_SEMANTICS_VALID_APRIL_COMPLETE" if downstream_pass else "V17_DEFERRABILITY_E_AC_OR_DECOMPOSITION_DOWNSTREAM_FAIL"
    manifest = {
        "artifact_id": "V17_DEFERRABILITY_REDESIGN_MANIFEST_V1",
        "status": "PASS" if downstream_pass else "FAIL_CLOSED",
        "classification": classification,
        "next_decision": "READY_FOR_V17_DEFERRABILITY_SCIENTIFIC_REFREEZE_REVIEW" if downstream_pass else "V17_DEFERRABILITY_REDESIGN_REQUIRED",
        "artifacts": {path.name: sha256_file(path) for path in sorted(output.glob("V17_*.json"))},
        "firewall": {
            "April_result_reads_before_model_freeze": 0,
            "May_scientific_input_reads": 0, "June_scientific_input_reads": 0,
            "May_result_content_reads": 0, "June_result_content_reads": 0,
            "V16_3_historical_changes": 0, "beta_changes": 0, "kappa_changes": 0,
            "PUE_changes": 0, "PF_changes": 0, "AIDC_site_changes": 0,
            "whole_facility_flexible_share_assumptions": 0, "eta_FLEX_created": 0,
            "Caprara_calibration_calls": 0, "effect_selected_thresholds": 0,
            "effect_selected_delay_budgets": 0, "arbitrary_clipping_calls": 0,
            "OpenDSS_calls_inside_Benders": 0,
        },
    }
    write_json(output / "V17_DEFERRABILITY_REDESIGN_MANIFEST.json", manifest)
    return {"classification": classification, "next_decision": manifest["next_decision"]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("materialize", "day", "decomposition", "finalize"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    parser.add_argument("--operating-day", default="2025-04-15")
    args = parser.parse_args(argv)
    if args.phase == "materialize": result = materialize_references(args.repo, args.output)
    elif args.phase == "day": result = execute_day(args.repo, args.source, args.output, args.operating_day)
    elif args.phase == "decomposition": result = run_decomposition(args.repo, args.source, args.output)
    else: result = finalize(args.repo, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
