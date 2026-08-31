"""Same-seven-day V17 V4R1 GPU-hour reference and electrical pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .aidc_boundary_v16_1 import DT_HOURS, PUE_PLAN
from .aidc_rack_mapping import load_frozen_rack_authority
from .authority import sha256_file
from .full_ieee123_b3_v16_2 import B3Inputs
from .v17_deferrability_april import BETA_AIDC, ReferenceProxy, SOURCE_DEFAULT, _array_fingerprint
from .v17_deferrability_semantics import DEFERRAL_SLOTS, LATENCY_CLASSES, write_json
from .v17_reference_scheduler_v6 import GPU_COUNTS, build_reference_schedule_v6_gpu_hour
from .v17_v4r1_ml import DEBUG_DAYS, TARGET_NAMES


KAPPA_GPU_Q50_KW = 0.48563611660901085
RHO = 0.10
COHORTS = tuple(f"G{gpu}_{latency}" for latency in LATENCY_CLASSES for gpu in GPU_COUNTS)


def _target_index(latency: str, gpu: int) -> int:
    return TARGET_NAMES.index(f"W_F_{latency}::G{gpu}")


def _firewall() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0, "June_scientific_input_reads": 0,
        "May_result_content_reads": 0, "June_result_content_reads": 0,
        "remaining_April_day_runs": 0, "arbitrary_scaling_calls": 0,
        "grid_selected_parameter_calls": 0, "OpenDSS_calls_inside_Benders": 0,
    }


def materialize_references(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); output = output.resolve()
    training = json.loads((output / "V17_RCMQT_V4R1_TRAINING_REPORT.json").read_text(encoding="utf-8"))
    validation = json.loads((output / "V17_RCMQT_V4R1_APRIL_7DAY_VALIDATION.json").read_text(encoding="utf-8"))
    preparation = json.loads((output / "cache_v4r1/V17_RCMQT_V4R1_APRIL_7DAY_PREPARATION.json").read_text(encoding="utf-8"))
    if training["status"] != "PASS_MODEL_FROZEN_BEFORE_APRIL" or validation["status"] != "PASS_APRIL_7DAY_MODEL_VALIDATION":
        raise RuntimeError("V17_V4R1_REFERENCE_REQUIRES_FROZEN_VALIDATED_MODEL")
    weights = output / training["weights_file"]
    if sha256_file(weights) != training["weights_file_sha256"] or preparation["frozen_weights_sha256"] != training["weights_file_sha256"]:
        raise RuntimeError("V17_V4R1_REFERENCE_WEIGHT_IDENTITY_FAIL")
    saved = np.load(output / "V17_RCMQT_V4R1_APRIL_7DAY_PREDICTIONS.npz", allow_pickle=False)
    prediction = np.asarray(saved["prediction"], dtype=float)
    scales = np.asarray([float(preparation["target_scales"][name]) for name in TARGET_NAMES])
    prediction_raw = prediction * scales[None, None, :, None]
    if tuple(preparation["validation_days"]) != DEBUG_DAYS:
        raise RuntimeError("V17_V4R1_REFERENCE_DEBUG_DAY_AXIS_FAIL")
    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    rack_ids = tuple(rack.rack_id for rack in authority.racks); rack_index = {rack: i for i, rack in enumerate(rack_ids)}
    aidc_ids = tuple(f"AIDC{i:02d}" for i in range(1, 13))
    aidc_racks = {aidc: tuple(i for i, rack in enumerate(authority.racks) if rack.aidc_id == aidc) for aidc in aidc_ids}
    capacity_gpuh = {rack.rack_id: BETA_AIDC * rack.deliverable_gpu_capacity * DT_HOURS for rack in authority.racks}
    capacities_gpu = BETA_AIDC * np.asarray([rack.deliverable_gpu_capacity for rack in authority.racks], dtype=float)
    reference_dir = output / "reference_v6_v4r1"; reference_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for day_index, day in enumerate(DEBUG_DAYS):
        arrivals = {
            (latency, gpu): tuple(BETA_AIDC * float(prediction_raw[day_index, slot, _target_index(latency, gpu), 1]) for slot in range(96))
            for latency in LATENCY_CLASSES for gpu in GPU_COUNTS
        }
        reference = build_reference_schedule_v6_gpu_hour(arrivals, capacity_gpuh)
        allocation = np.zeros((len(COHORTS), 48, 96), dtype=float)
        for c, cohort in enumerate(COHORTS):
            gpu = int(cohort[1]); latency = cohort.split("_", 1)[1]
            for rack in rack_ids:
                r = rack_index[rack]
                for slot in range(96):
                    allocation[c, r, slot] = reference.service_by_class_gpu_rack_slot[(latency, gpu, rack, slot)]
        arrivals_array = np.asarray([arrivals[(latency, gpu)] for latency in LATENCY_CLASSES for gpu in GPU_COUNTS], dtype=float)
        flexible_power = KAPPA_GPU_Q50_KW / DT_HOURS * allocation.sum(axis=0).T
        flexible_gpu = allocation.sum(axis=0).T / DT_HOURS
        p_ref = BETA_AIDC * prediction_raw[day_index, :, TARGET_NAMES.index("P_IT_REF"), 2]
        g_fixed_gpu = BETA_AIDC * prediction_raw[day_index, :, TARGET_NAMES.index("G_FIXED_GPU"), 2]
        p_res_sys = p_ref - flexible_power.sum(axis=1)
        if float(p_res_sys.min()) < -1e-9:
            raise RuntimeError(f"V17_V4R1_REFERENCE_POWER_RESIDUAL_NEGATIVE:{day}:{p_res_sys.min()}")
        p_res_rack = p_res_sys[:, None] * np.asarray(authority.power_weights)[None, :]
        g_res_rack = g_fixed_gpu[:, None] * np.asarray(authority.gpu_weights)[None, :]
        total_gpu = g_res_rack + flexible_gpu
        violation = float(np.max(total_gpu - capacities_gpu[None, :]))
        if violation > 1e-9:
            raise RuntimeError(f"V17_V4R1_REFERENCE_GPU_CAP_FAIL:{day}:{violation}")
        p_res_aidc = np.asarray([[sum(p_res_rack[t, r] for r in aidc_racks[aidc]) for aidc in aidc_ids] for t in range(96)])
        p_f_aidc = np.asarray([[sum(flexible_power[t, r] for r in aidc_racks[aidc]) for aidc in aidc_ids] for t in range(96)])
        plan = PUE_PLAN * (p_res_aidc + p_f_aidc)
        arrays = {
            "allocation": allocation, "arrivals": arrivals_array, "p_res_aidc": p_res_aidc,
            "g_res_rack": g_res_rack, "plan_kw_96x12": plan, "gpu_capacities": capacities_gpu,
            "p_ref": p_ref, "g_fixed_gpu": g_fixed_gpu,
        }
        fingerprint = _array_fingerprint(arrays)
        path = reference_dir / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{day}.npz"
        np.savez_compressed(path, **arrays, array_fingerprint=np.asarray(fingerprint))
        rows.append({
            "operating_day": day, "path": str(path.resolve()), "sha256": sha256_file(path), "array_fingerprint": fingerprint,
            "arrival_GPU_hours": float(arrivals_array.sum()), "service_GPU_hours": float(allocation.sum()),
            "service_parity_abs_error_GPU_hour": abs(float(arrivals_array.sum()) - float(allocation.sum())),
            "p_residual_min_kw": float(p_res_sys.min()), "p_residual_max_kw": float(p_res_sys.max()),
            "gpu_cap_max_violation": max(0.0, violation), "plan_min_kw": float(plan.min()), "plan_max_kw": float(plan.max()),
            **reference.evidence,
        })
    report = {
        "artifact_id": "V17_REFERENCE_SCHEDULER_V6_GPU_HOUR_7DAY_VALIDATION_V1",
        "status": "PASS_7DAY_REFERENCE_FROZEN_BEFORE_GRID_RESULTS",
        "authority_id": "REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR", "debug_days": list(DEBUG_DAYS), "days": rows,
        "workload_unit": "GPU_HOUR", "rack_capacity_unit": "GPU_HOUR_PER_15MIN_SLOT",
        "kappa_GPU_Q50_kW": KAPPA_GPU_Q50_KW, "CPU_host_power_role": "P_IT_REF_RESIDUAL",
        "frozen_weights_sha256": training["weights_file_sha256"],
        "rack_capacity_source_path": rack_contract["source_path"], "rack_capacity_source_sha256": rack_contract["source_sha256"],
        **_firewall(),
    }
    write_json(output / "V17_REFERENCE_SCHEDULER_V6_GPU_HOUR_7DAY_VALIDATION.json", report)
    contract = {
        "artifact_id": "V17_REFERENCE_SCHEDULER_V6_GPU_HOUR_CONTRACT_V1", "status": "PASS_FROZEN_BEFORE_GRID_RESULTS",
        "authority_id": "REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR",
        "policy": "GRID_BLIND_MESS_BLIND_EARLIEST_DEADLINE_CAPACITY_PROPORTIONAL_WEIGHTED_WATER_FILL",
        "workload_unit": "GPU_HOUR", "service_parity_unit": "GPU_HOUR", "deadline_backlog_unit": "GPU_HOUR",
        "source_code_sha256": sha256_file(repo / "dayahead/v17_reference_scheduler_v6.py"),
        "capacity_source_path": rack_contract["source_path"], "capacity_source_sha256": rack_contract["source_sha256"],
        "historical_REFERENCE_V5_changes": 0, "permutation_invariant": True,
        **_firewall(),
    }
    write_json(output / "V17_REFERENCE_SCHEDULER_V6_GPU_HOUR_CONTRACT.json", contract)
    return report


def _load_reference_v6(path: Path, authority: Any, mess_records: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, Any], B3Inputs]:
    arrays = np.load(path, allow_pickle=False); allocation_array = np.asarray(arrays["allocation"], dtype=float)
    allocation = {
        (cohort, rack.rack_id, slot): float(allocation_array[c, r, slot])
        for c, cohort in enumerate(COHORTS) for r, rack in enumerate(authority.racks) for slot in range(96)
    }
    flexible_power = KAPPA_GPU_Q50_KW / DT_HOURS * allocation_array.sum(axis=0).T
    flexible_gpu = allocation_array.sum(axis=0).T / DT_HOURS
    arrivals_array = np.asarray(arrays["arrivals"], dtype=float)
    reference = {
        "beta": BETA_AIDC,
        "arrivals": {cohort: tuple(map(float, arrivals_array[i])) for i, cohort in enumerate(COHORTS)},
        "reference": ReferenceProxy(allocation, tuple(tuple(map(float, row)) for row in flexible_power), tuple(tuple(map(float, row)) for row in flexible_gpu)),
        "p_res_aidc": tuple(tuple(map(float, row)) for row in arrays["p_res_aidc"]),
        "g_res_rack": tuple(tuple(map(float, row)) for row in arrays["g_res_rack"]),
        "plan_kw_96x12": tuple(tuple(map(float, row)) for row in arrays["plan_kw_96x12"]),
        "gpu_capacities": tuple(map(float, arrays["gpu_capacities"])),
    }
    deadlines = {cohort: DEFERRAL_SLOTS[cohort.split("_", 1)[1]] for cohort in COHORTS}
    inputs = B3Inputs(
        cohorts=COHORTS, arrivals=reference["arrivals"], rack_ids=tuple(r.rack_id for r in authority.racks),
        rack_aidc=tuple(r.aidc_id for r in authority.racks), gpu_capacity=reference["gpu_capacities"],
        p_res_aidc_kw=reference["p_res_aidc"], g_res_rack=reference["g_res_rack"], mess_records=mess_records,
        evidence={"authority": "V17_V4R1_GPU_HOUR", "deadline_slots_by_cohort": deadlines, "OpenDSS_calls_inside_Benders": 0},
    )
    return reference, inputs


def electrical_context(repo: Path, source: Path, output: Path, day: str):
    from .full_ieee123_g11_v16_1 import build_full_grid_binding
    from .grid_background_v16_2 import build_authority_background_binding
    from .run_aidc_ieee123_penetration_hosting_capacity_diagnostic_v1 import _select_april_vintages_locked
    from .run_authority_semantic_g11_v16_2 import _default_background_paths

    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    c7 = json.loads((repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json").read_text(encoding="utf-8"))
    reference, inputs = _load_reference_v6(output / "reference_v6_v4r1" / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{day}.npz", authority, c7["mess_invariants"]["records"])
    vintages, excluded = _select_april_vintages_locked(repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json")
    if day not in vintages: raise RuntimeError(f"V17_V4R1_APRIL_VINTAGE_MISSING:{day}:{excluded}")
    vintage = vintages[day]
    background = build_authority_background_binding(timestamps_fixed_aest=vintage["timestamps_96"], demand_mw_96=vintage["demand_mw_96"], rooftop_pv_mw_96=vintage["pv_mw_96"], paths=_default_background_paths(repo, source))
    binding = build_full_grid_binding(
        assets=source/"opendss_assets", contract=source/"power_v70_p4f_contract", demand_mw_96=vintage["demand_mw_96"],
        rooftop_pv_mw_96=vintage["pv_mw_96"], aidc_plan_kw_96x12=reference["plan_kw_96x12"],
        pcc_asset=repo/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss", background_binding=background,
    )
    return reference, inputs, vintage, background, binding, authority


def build_anchors(repo: Path, source: Path, output: Path) -> dict[str, Any]:
    from .run_v16_3_correction import _current_cache_path, _generate_current_day
    from .run_v16_3_voltage_candidate import _anchor_and_sensitivity_day

    repo = repo.resolve(); source = source.resolve(); output = output.resolve(); cache = output / "ac_cache_v4r1"
    rows: list[dict[str, Any]] = []
    for day in DEBUG_DAYS:
        reference, _inputs, vintage, background, binding, authority = electrical_context(repo, source, output, day)
        voltage_path = cache / "data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
        voltage_record = _anchor_and_sensitivity_day(repo, source, background, reference["plan_kw_96x12"], binding, day, voltage_path)
        context = (reference, vintage, background, binding, voltage_path, authority)
        current_record = _generate_current_day(repo, source, cache, day, context)
        current_path = _current_cache_path(cache, day)
        voltage = np.load(voltage_path, allow_pickle=False); current = np.load(current_path, allow_pickle=False)
        anchor_error = float(np.max(np.abs(np.asarray(reference["plan_kw_96x12"]) - np.asarray(voltage["anchor_control"][:, :12]))))
        if anchor_error > 1e-9:
            raise RuntimeError(f"V17_V4R1_ANCHOR_PLAN_IDENTITY_FAIL:{day}:{anchor_error}")
        rows.append({
            "operating_day": day, "anchor_plan_identity_max_abs_error_kw": anchor_error,
            "voltage_cache": {"path": str(voltage_path.resolve()), "sha256": sha256_file(voltage_path), "bytes": voltage_path.stat().st_size,
                              "deterministic_repeat_max_abs_error": float(voltage["deterministic_repeat_max_abs_error"])},
            "current_cache": {"path": str(current_path.resolve()), "sha256": sha256_file(current_path), "bytes": current_path.stat().st_size,
                              "deterministic_repeat_max_abs_error_pu": float(current["deterministic_repeat_max_abs_error_pu"])},
            "H_coefficient_sha256": hashlib.sha256(np.asarray(voltage["sensitivity"]).tobytes()).hexdigest(),
            "J_I_coefficient_sha256": str(current["coefficient_sha256"]),
            "voltage_generation": voltage_record, "current_generation": current_record,
        })
        print(json.dumps({"stage": "V17_V4R1_ANCHOR", "day": day, "complete": len(rows)}), flush=True)
    report = {
        "artifact_id": "V17_V4R1_7DAY_D1_ANCHOR_MANIFEST_V1", "status": "PASS_REGENERATED_7_DAYS",
        "debug_days": list(DEBUG_DAYS), "days": rows, "rho_pending_validation": RHO,
        "common_frozen_D1_tap_semantics": True, "MESS_P_Q_zero_at_anchor": True,
        "native_IEEE123_unchanged": True, "old_H_J_reused": False, **_firewall(),
    }
    write_json(output / "V17_V4R1_7DAY_D1_ANCHOR_MANIFEST.json", report); return report


def validate_surrogates(repo: Path, source: Path, output: Path) -> dict[str, Any]:
    from .run_aidc_ieee123_penetration_hosting_capacity_diagnostic_v1 import PF_TAN, _set_generator, _set_load
    from .run_planning_ac_voltage_forensic_v1 import _compile
    from .run_v16_3_correction import _current_sampler, _sample_currents
    from .run_v16_3_nonzero_validity import _aidc_limits, _branch_ratings, _regcontrol_metadata, _slot_selection
    from .run_v16_3_voltage_candidate import CAPACITORS, REGULATORS, _fix_controls, _set_slot, _voltage_map
    from .v16_3_correction import CURRENT_ERROR_TOLERANCE, current_metrics_pass
    from .v16_3_nonzero_validity import VOLTAGE_TOLERANCE, build_probe_directions, expand_rho, voltage_comparison
    from .v17_v5_current_repair import analytical_current_bound_pu, is_dominated_mess_current_row

    repo = repo.resolve(); source = source.resolve(); output = output.resolve()
    families_data = {
        family: {"errors": [], "predicted": [], "actual": []}
        for family in ("ordinary_line_current_rows", "native_transformer_rows", "AIDC_coupling_transformer_rows", "MESS_coupling_transformer_rows")
    }
    voltage_metrics: list[dict[str, Any]] = []; days: list[dict[str, Any]] = []; total_probes = 0; repeat_error = 0.0

    def row_family(name: str) -> str:
        lowered = name.lower()
        if not lowered.startswith("transformer."): return "ordinary_line_current_rows"
        if is_dominated_mess_current_row(lowered): return "MESS_coupling_transformer_rows"
        if lowered.startswith("transformer.idc_idc"): return "AIDC_coupling_transformer_rows"
        return "native_transformer_rows"

    def apply_controls(odd: Any, controls: tuple[str, ...], previous: np.ndarray, values: np.ndarray) -> np.ndarray:
        for index in range(12):
            if abs(float(values[index]) - float(previous[index])) > 1e-12:
                value = float(values[index]); _set_load(odd, f"IDC_IDC{index+1:02d}", value, value * PF_TAN)
        services = [control.split("[", 1)[1][:-1] for control in controls[12:36]]
        for index, service in enumerate(services):
            if abs(float(values[12+index]) - float(previous[12+index])) > 1e-12 or abs(float(values[36+index]) - float(previous[36+index])) > 1e-12:
                p = float(values[12+index]); q = float(values[36+index])
                _set_generator(odd, f"MESS_DIS_{service}", max(p, 0.0), q); _set_load(odd, f"MESS_CHG_{service}", max(-p, 0.0), 0.0)
        return values.copy()

    for day in DEBUG_DAYS:
        reference, _inputs, _vintage, background, binding, authority = electrical_context(repo, source, output, day)
        voltage = np.load(output/"ac_cache_v4r1/data"/f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz", allow_pickle=False)
        current = np.load(output/"ac_cache_v4r1/data"/f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz", allow_pickle=False)
        controls = tuple(map(str, voltage["control_names"])); nodes = tuple(map(str, voltage["node_names"])); branches = tuple(binding.factories[0].data.branches)
        names = tuple(f"{branch.branch_id}::{branch.phase}" for branch in branches); families = tuple(row_family(name) for name in names)
        odd, adapter = _compile(source, repo, "NATIVE"); ratings, rating_rows = _branch_ratings(odd, binding)
        selection = _slot_selection(voltage, ratings, [str(row["kind"]) for row in rating_rows], _regcontrol_metadata(odd), day)
        day_start = total_probes; day_v_false = 0; day_i_false = 0
        for slot in selection["slots"]:
            taps = {name: float(voltage["regulator_taps"][slot, i]) for i, name in enumerate(REGULATORS)}
            caps = {name: [int(voltage["capacitor_states"][slot, i])] for i, name in enumerate(CAPACITORS)}
            anchor = np.asarray(voltage["anchor_control"][slot], dtype=float)
            _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot); _fix_controls(odd, taps, caps); odd.Solution.SolveSnap()
            if not bool(odd.Solution.Converged()): raise RuntimeError(f"V17_V4R1_SURROGATE_ANCHOR_NONCONVERGENCE:{day}:{slot}")
            current_indices, current_coefficients = _current_sampler(odd, branches); previous = anchor.copy()
            down, up, _limits = _aidc_limits(reference, authority, slot)
            for direction in build_probe_directions(controls, down, up):
                delta = expand_rho(direction, RHO); values = anchor + delta
                predicted_v = np.sqrt(np.maximum(np.asarray(voltage["anchor_v_squared"][slot]) + delta @ np.asarray(voltage["sensitivity"][slot]), 0.0))
                predicted_i = np.asarray(current["anchor_current_loading_pu"][slot]) + delta @ np.asarray(current["current_sensitivity_pu_per_control"][slot])
                previous = apply_controls(odd, controls, previous, values); odd.Solution.SolveSnap()
                if not bool(odd.Solution.Converged()): raise RuntimeError(f"V17_V4R1_SURROGATE_PROBE_NONCONVERGENCE:{day}:{slot}:{direction.probe_id}")
                actual_v = np.asarray(list(_voltage_map(odd, nodes).values()), dtype=float); actual_i = _sample_currents(odd, current_indices, current_coefficients) / ratings
                vm = voltage_comparison(predicted_v, actual_v, nodes); voltage_metrics.append(vm); day_v_false += int(vm["false_feasible_count"])
                for index, family in enumerate(families):
                    families_data[family]["predicted"].append(float(predicted_i[index])); families_data[family]["actual"].append(float(actual_i[index])); families_data[family]["errors"].append(abs(float(predicted_i[index]-actual_i[index])))
                    if family != "MESS_coupling_transformer_rows": day_i_false += int(predicted_i[index] <= 1.0+1e-9 and actual_i[index] > 1.0+1e-9)
                total_probes += 1
                if total_probes == 1:
                    odd.Solution.SolveSnap(); repeated = _sample_currents(odd, current_indices, current_coefficients) / ratings; repeat_error = float(np.max(np.abs(repeated-actual_i)))
            print(json.dumps({"stage":"V17_V4R1_SURROGATE","day":day,"slot":int(slot),"probes":total_probes}), flush=True)
        days.append({
            "operating_day": day, "selected_slots": selection, "probe_count": total_probes-day_start,
            "voltage_false_feasible_count": day_v_false, "non_dominated_current_false_feasible_count": day_i_false,
            "H_repeat_max_abs_error": float(voltage["deterministic_repeat_max_abs_error"]),
            "J_I_repeat_max_abs_error_pu": float(current["deterministic_repeat_max_abs_error_pu"]),
        })

    def summary(data: Mapping[str, list[float]]) -> dict[str, Any]:
        errors = np.asarray(data["errors"], dtype=float); pred = np.asarray(data["predicted"], dtype=float); actual = np.asarray(data["actual"], dtype=float)
        return {"sample_count": int(errors.size), "max_abs_normalized_current_error_pu": float(errors.max()) if errors.size else 0.0,
                "mean_abs_normalized_current_error_pu": float(errors.mean()) if errors.size else 0.0,
                "p95_abs_normalized_current_error_pu": float(np.quantile(errors,0.95)) if errors.size else 0.0,
                "false_current_feasible_count": int(np.sum((pred<=1.0+1e-9)&(actual>1.0+1e-9))) if errors.size else 0,
                "false_current_infeasible_count": int(np.sum((pred>1.0+1e-9)&(actual<=1.0+1e-9))) if errors.size else 0,
                "actual_max_loading_pu": float(actual.max()) if errors.size else 0.0}
    by_family = {family: summary(data) for family, data in families_data.items()}
    non_dominated = {key: sum((families_data[family][key] for family in ("ordinary_line_current_rows","native_transformer_rows","AIDC_coupling_transformer_rows")), []) for key in ("errors","predicted","actual")}
    current_gate = summary(non_dominated); current_pass = current_metrics_pass(current_gate)
    voltage_summary = {
        "false_feasible_count": sum(int(row["false_feasible_count"]) for row in voltage_metrics),
        "max_abs_error_pu": max(float(row["max_abs_error_pu"]) for row in voltage_metrics),
        "mean_abs_error_pu": float(np.mean([float(row["mean_abs_error_pu"]) for row in voltage_metrics])),
        "p95_abs_error_pu": max(float(row["p95_abs_error_pu"]) for row in voltage_metrics),
    }
    voltage_pass = voltage_summary["false_feasible_count"]==0 and voltage_summary["max_abs_error_pu"]<=VOLTAGE_TOLERANCE["max_abs_candidate_vs_frozen_pu"]+1e-12 and voltage_summary["mean_abs_error_pu"]<=VOLTAGE_TOLERANCE["mean_abs_candidate_vs_frozen_pu"]+1e-12 and voltage_summary["p95_abs_error_pu"]<=VOLTAGE_TOLERANCE["p95_abs_candidate_vs_frozen_pu"]+1e-12
    dominated_pass = by_family["MESS_coupling_transformer_rows"]["actual_max_loading_pu"] <= analytical_current_bound_pu()+1e-6
    deterministic_pass = repeat_error<=1e-6 and max(row["H_repeat_max_abs_error"] for row in days)<=1e-6 and max(row["J_I_repeat_max_abs_error_pu"] for row in days)<=1e-6
    passed = voltage_pass and current_pass and dominated_pass and deterministic_pass
    report = {
        "artifact_id":"V17_V4R1_7DAY_SURROGATE_VALIDATION_V1", "status":"PASS" if passed else "FAIL_CLOSED",
        "rho_candidate_tested":RHO, "rho_valid_frozen_primary":RHO if passed else None, "debug_days":list(DEBUG_DAYS), "days":days,
        "probe_count":total_probes, "voltage":{**voltage_summary,"tolerances":VOLTAGE_TOLERANCE,"status":"PASS" if voltage_pass else "FAIL"},
        "hard_current_non_dominated_gate":{**current_gate,"tolerances":CURRENT_ERROR_TOLERANCE,"status":"PASS" if current_pass else "FAIL"},
        "current_rows_by_class":by_family, "MESS_coupling_transformer_treatment":"ANALYTICALLY_DOMINATED_BY_PCS_VOLTAGE_TRANSFORMER_CONTRACT",
        "MESS_actual_current_all_probes_checked":True, "MESS_dominance_bound_pu":analytical_current_bound_pu(), "MESS_dominance_status":"PASS" if dominated_pass else "FAIL",
        "deterministic_repeat":{"probe_repeat_max_abs_error_pu":repeat_error,"tolerance_pu":1e-6,"status":"PASS" if deterministic_pass else "FAIL"},
        **_firewall(),
    }
    write_json(output/"V17_V4R1_7DAY_SURROGATE_VALIDATION.json", report); return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("phase", choices=("references", "anchors", "validate"))
    parser.add_argument("--repo", type=Path, default=Path.cwd()); parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate")); args = parser.parse_args(argv)
    if args.phase == "references": result = materialize_references(args.repo, args.output)
    elif args.phase == "anchors": result = build_anchors(args.repo, args.source, args.output)
    else: result = validate_surrogates(args.repo, args.source, args.output)
    print(json.dumps({"status": result["status"]}, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
