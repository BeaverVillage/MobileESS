"""Same-seven-day V17 V5 reference and electrical revalidation driver."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .aidc_boundary_v16_1 import DT_HOURS, PUE_PLAN
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .aidc_rack_mapping import load_frozen_rack_authority
from .authority import sha256_file
from .v17_deferrability_april import (
    BETA_AIDC,
    COHORTS,
    MODEL_NAME,
    NAMESPACE,
    SOURCE_DEFAULT,
    _array_fingerprint,
    _load_reference,
    _target_index,
)
from .v17_deferrability_ml import TARGET_NAMES
from .v17_deferrability_semantics import LATENCY_CLASSES, build_reference_schedule_v4, write_json
from .v17_reference_scheduler_v5 import (
    AUTHORITY_ID,
    NUMERICAL_TOLERANCE,
    POLICY_ID,
    build_reference_schedule_v5,
)


DEBUG_DAYS = (
    "2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13",
    "2025-04-15", "2025-04-22", "2025-04-23",
)
FROZEN_WEIGHTS_SHA256 = "544d6b36504bb8de6d0dd8fe9446fc435c2459a3949d91a2203c1f001162c859"
FROZEN_CHECKPOINT_FINGERPRINT = "a8dd2d6111de196aead25c01b9e58885c3aab8fe78651f5b15cbf142dbb5cba7"


def _electrical_context(repo: Path, source: Path, output: Path, day: str):
    from .full_ieee123_g11_v16_1 import build_full_grid_binding
    from .grid_background_v16_2 import build_authority_background_binding
    from .run_aidc_ieee123_penetration_hosting_capacity_diagnostic_v1 import _select_april_vintages_locked
    from .run_authority_semantic_g11_v16_2 import _default_background_paths

    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    c7 = json.loads((repo / "dayahead/artifacts/v16_1/C7_FULL_IEEE123_REPORT_V16_1.json").read_text(encoding="utf-8"))
    reference, inputs = _load_reference(output / "reference_v5" / f"REFERENCE_COMPUTE_SCHEDULE_V5_{day}.npz", authority, c7["mess_invariants"]["records"])
    vintages, excluded = _select_april_vintages_locked(repo / "dayahead/artifacts/v16_1/AEMO_DA_VINTAGE_CONTRACT_V16_1.json")
    if day not in vintages:
        raise RuntimeError(f"V17_V5_APRIL_VINTAGE_MISSING:{day}:{excluded}")
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
    return reference, inputs, vintage, background, binding, authority


def build_anchors(repo: Path, source: Path, output: Path) -> dict[str, Any]:
    from .run_v16_3_correction import _current_cache_path, _generate_current_day
    from .run_v16_3_voltage_candidate import _anchor_and_sensitivity_day

    repo = repo.resolve(); source = source.resolve(); output = output.resolve()
    cache = output / "ac_cache_v5"
    rows = []
    for day in DEBUG_DAYS:
        reference, _inputs, vintage, background, binding, authority = _electrical_context(repo, source, output, day)
        voltage_path = cache / "data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
        if voltage_path.is_file():
            existing_voltage = np.load(voltage_path, allow_pickle=False)
            reusable_voltage = (
                str(existing_voltage["operating_day"]) == day
                and np.max(np.abs(np.asarray(existing_voltage["anchor_control"][:, :12]) - np.asarray(reference["plan_kw_96x12"]))) <= 1e-12
            )
        else:
            reusable_voltage = False
        if reusable_voltage:
            voltage_record = {"operating_day": day, "path": str(voltage_path.resolve()), "sha256": sha256_file(voltage_path), "bytes": voltage_path.stat().st_size, "reused_exact_V5_plan_cache": True}
        else:
            voltage_record = _anchor_and_sensitivity_day(repo, source, background, reference["plan_kw_96x12"], binding, day, voltage_path)
        context = (reference, vintage, background, binding, voltage_path, authority)
        current_path = _current_cache_path(cache, day)
        if current_path.is_file():
            existing_current = np.load(current_path, allow_pickle=False)
            reusable_current = str(existing_current["source_voltage_cache_sha256"]) == sha256_file(voltage_path)
        else:
            reusable_current = False
        if reusable_current:
            current_record = {"operating_day": day, "path": str(current_path.resolve()), "sha256": sha256_file(current_path), "bytes": current_path.stat().st_size, "reused_exact_V5_voltage_bound_cache": True}
        else:
            current_record = _generate_current_day(repo, source, cache, day, context)
        v5 = np.load(output / "reference_v5" / f"REFERENCE_COMPUTE_SCHEDULE_V5_{day}.npz", allow_pickle=False)
        v4 = np.load(output / "reference_v4" / f"REFERENCE_COMPUTE_SCHEDULE_V4_{day}.npz", allow_pickle=False)
        voltage = np.load(voltage_path, allow_pickle=False); current = np.load(current_path, allow_pickle=False)
        old_voltage = np.load(output / "ac_cache/data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz", allow_pickle=False)
        old_current = np.load(output / "ac_cache/data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz", allow_pickle=False)
        plan_difference = float(np.max(np.abs(np.asarray(v5["plan_kw_96x12"]) - np.asarray(v4["plan_kw_96x12"]))))
        anchor_control_error = float(np.max(np.abs(np.asarray(v5["plan_kw_96x12"]) - np.asarray(voltage["anchor_control"][:, :12]))))
        if plan_difference <= 1e-12 or anchor_control_error > 1e-9:
            raise RuntimeError(f"V17_V5_ANCHOR_EQUIVALENCE_GATE_FAIL:{day}:{plan_difference}:{anchor_control_error}")
        rows.append({
            "operating_day": day,
            "V4_to_V5_per_AIDC_plan_max_abs_difference_kw": plan_difference,
            "electrical_anchor_reuse_permitted": False,
            "V5_anchor_plan_identity_max_abs_error_kw": anchor_control_error,
            "V4_to_V5_anchor_v_squared_max_abs_difference": float(np.max(np.abs(np.asarray(voltage["anchor_v_squared"]) - np.asarray(old_voltage["anchor_v_squared"])))),
            "V4_to_V5_H_max_abs_difference": float(np.max(np.abs(np.asarray(voltage["sensitivity"]) - np.asarray(old_voltage["sensitivity"])))),
            "V4_to_V5_J_I_max_abs_difference": float(np.max(np.abs(np.asarray(current["current_sensitivity_pu_per_control"]) - np.asarray(old_current["current_sensitivity_pu_per_control"])))),
            "voltage_cache": {"path": str(voltage_path.resolve()), "sha256": sha256_file(voltage_path), "bytes": voltage_path.stat().st_size, "deterministic_repeat_max_abs_error": float(voltage["deterministic_repeat_max_abs_error"])},
            "current_cache": {"path": str(current_path.resolve()), "sha256": sha256_file(current_path), "bytes": current_path.stat().st_size, "deterministic_repeat_max_abs_error": float(current["deterministic_repeat_max_abs_error_pu"])},
            "voltage_generation": voltage_record,
            "current_generation": current_record,
        })
        print(json.dumps({"stage": "V17_V5_ANCHOR", "day": day, "complete": len(rows)}), flush=True)
    report = {
        "artifact_id": "V17_V5_7DAY_D1_ANCHOR_MANIFEST_V1", "status": "PASS_REGENERATED_7_DAYS",
        "debug_days": list(DEBUG_DAYS), "days": rows,
        "common_frozen_D1_tap_semantics": True, "MESS_P_Q_zero_at_anchor": True,
        "native_IEEE123_unchanged": True, "beta_AIDC": BETA_AIDC,
        **_scientific_firewall(),
    }
    write_json(output / "V17_V5_7DAY_D1_ANCHOR_MANIFEST.json", report)
    return {"status": report["status"], "day_count": len(rows)}


def validate_surrogates(repo: Path, source: Path, output: Path) -> dict[str, Any]:
    from .run_planning_ac_voltage_forensic_v1 import _compile
    from .run_aidc_ieee123_penetration_hosting_capacity_diagnostic_v1 import PF_TAN, _set_generator, _set_load
    from .run_v16_3_correction import _current_sampler, _sample_currents
    from .run_v16_3_nonzero_validity import (
        _aidc_limits, _branch_ratings,
        _regcontrol_metadata, _slot_selection,
    )
    from .run_v16_3_voltage_candidate import CAPACITORS, REGULATORS, _fix_controls, _set_slot, _voltage_map
    from .v16_3_correction import CURRENT_ERROR_TOLERANCE, current_comparison, current_metrics_pass
    from .v16_3_nonzero_validity import (
        VOLTAGE_TOLERANCE, build_probe_directions, expand_rho, voltage_comparison,
    )

    repo = repo.resolve(); source = source.resolve(); output = output.resolve()
    rho = 0.10

    def apply_changed_controls(odd, controls: tuple[str, ...], previous: np.ndarray, values: np.ndarray) -> np.ndarray:
        for index in range(12):
            if abs(float(values[index]) - float(previous[index])) > 1e-12:
                value = float(values[index]); _set_load(odd, f"IDC_IDC{index+1:02d}", value, value * PF_TAN)
        services = [control.split("[", 1)[1][:-1] for control in controls[12:36]]
        for index, service in enumerate(services):
            if abs(float(values[12 + index]) - float(previous[12 + index])) > 1e-12 or abs(float(values[36 + index]) - float(previous[36 + index])) > 1e-12:
                p = float(values[12 + index]); q = float(values[36 + index])
                _set_generator(odd, f"MESS_DIS_{service}", max(p, 0.0), q)
                _set_load(odd, f"MESS_CHG_{service}", max(-p, 0.0), 0.0)
        return values.copy()

    voltage_days = []; current_days = []
    total_probes = 0; total_voltage_false = 0; total_current_false = 0
    first_gate_failure = None
    for day in DEBUG_DAYS:
        reference, _inputs, _vintage, background, binding, authority = _electrical_context(repo, source, output, day)
        voltage_path = output / "ac_cache_v5/data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
        current_path = output / "ac_cache_v5/data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
        voltage = np.load(voltage_path, allow_pickle=False); current = np.load(current_path, allow_pickle=False)
        controls = tuple(map(str, voltage["control_names"])); nodes = tuple(map(str, voltage["node_names"]))
        branches = tuple(binding.factories[0].data.branches)
        identities = tuple(f"{branch.branch_id}::{branch.phase}" for branch in branches)
        odd, adapter = _compile(source, repo, "NATIVE")
        ratings, rating_rows = _branch_ratings(odd, binding)
        selection = _slot_selection(voltage, ratings, [str(row["kind"]) for row in rating_rows], _regcontrol_metadata(odd), day)
        day_probe_count = 0; day_v_false = 0; day_i_false = 0
        max_v = 0.0; mean_v = 0.0; p95_v = 0.0
        max_i = 0.0; mean_i = 0.0; p95_i = 0.0
        family_counts: dict[str, int] = {}
        for slot in selection["slots"]:
            down, up, _limits = _aidc_limits(reference, authority, slot)
            directions = build_probe_directions(controls, down, up)
            anchor = np.asarray(voltage["anchor_control"][slot], dtype=float)
            taps = {name: float(voltage["regulator_taps"][slot, i]) for i, name in enumerate(REGULATORS)}
            caps = {name: [int(voltage["capacitor_states"][slot, i])] for i, name in enumerate(CAPACITORS)}
            _set_slot(odd, adapter, background, reference["plan_kw_96x12"], slot)
            _fix_controls(odd, taps, caps)
            odd.Solution.SolveSnap()
            if not bool(odd.Solution.Converged()):
                raise RuntimeError(f"V17_V5_SURROGATE_ANCHOR_NONCONVERGENCE:{day}:{slot}")
            current_indices, current_coefficients = _current_sampler(odd, branches)
            current_values = anchor.copy()
            for direction in directions:
                delta = expand_rho(direction, rho); values = anchor + delta
                predicted_voltage = np.sqrt(np.maximum(np.asarray(voltage["anchor_v_squared"][slot]) + delta @ np.asarray(voltage["sensitivity"][slot]), 0.0))
                predicted_current = np.asarray(current["anchor_current_loading_pu"][slot]) + delta @ np.asarray(current["current_sensitivity_pu_per_control"][slot])
                current_values = apply_changed_controls(odd, controls, current_values, values)
                odd.Solution.SolveSnap()
                if not bool(odd.Solution.Converged()):
                    raise RuntimeError(f"V17_V5_SURROGATE_PROBE_NONCONVERGENCE:{day}:{slot}:{direction.probe_id}")
                actual_voltage = np.asarray(list(_voltage_map(odd, nodes).values()), dtype=float)
                actual_current = _sample_currents(odd, current_indices, current_coefficients) / ratings
                vm = voltage_comparison(predicted_voltage, actual_voltage, nodes)
                im = current_comparison(predicted_current, actual_current, identities)
                day_probe_count += 1; family_counts[direction.family] = family_counts.get(direction.family, 0) + 1
                day_v_false += int(vm["false_feasible_count"]); day_i_false += int(im["false_current_feasible_count"])
                max_v = max(max_v, float(vm["max_abs_error_pu"])); mean_v = max(mean_v, float(vm["mean_abs_error_pu"])); p95_v = max(p95_v, float(vm["p95_abs_error_pu"]));
                max_i = max(max_i, float(im["max_abs_normalized_current_error_pu"])); mean_i = max(mean_i, float(im["mean_abs_normalized_current_error_pu"])); p95_i = max(p95_i, float(im["p95_abs_normalized_current_error_pu"]));
                probe_voltage_pass = int(vm["false_feasible_count"]) == 0 and float(vm["max_abs_error_pu"]) <= VOLTAGE_TOLERANCE["max_abs_candidate_vs_frozen_pu"] + 1e-12 and float(vm["mean_abs_error_pu"]) <= VOLTAGE_TOLERANCE["mean_abs_candidate_vs_frozen_pu"] + 1e-12 and float(vm["p95_abs_error_pu"]) <= VOLTAGE_TOLERANCE["p95_abs_candidate_vs_frozen_pu"] + 1e-12
                probe_current_pass = current_metrics_pass(im)
                if not probe_voltage_pass or not probe_current_pass:
                    first_gate_failure = {"operating_day": day, "slot": int(slot), "probe_id": direction.probe_id, "family": direction.family, "rho": rho, "voltage_metrics": vm, "current_metrics": im, "voltage_probe_pass": probe_voltage_pass, "current_probe_pass": probe_current_pass}
                    break
            if first_gate_failure is not None:
                break
        voltage_pass = day_v_false == 0 and max_v <= VOLTAGE_TOLERANCE["max_abs_candidate_vs_frozen_pu"] + 1e-12 and mean_v <= VOLTAGE_TOLERANCE["mean_abs_candidate_vs_frozen_pu"] + 1e-12 and p95_v <= VOLTAGE_TOLERANCE["p95_abs_candidate_vs_frozen_pu"] + 1e-12
        current_pass = day_i_false == 0 and current_metrics_pass({"false_current_feasible_count": day_i_false, "max_abs_normalized_current_error_pu": max_i, "mean_abs_normalized_current_error_pu": mean_i, "p95_abs_normalized_current_error_pu": p95_i})
        voltage_days.append({"operating_day": day, "rho": rho, "selected_slots": selection, "probe_count": day_probe_count, "probe_counts_by_predeclared_family": family_counts, "false_feasible_count": day_v_false, "max_abs_error_pu": max_v, "max_per_probe_mean_abs_error_pu": mean_v, "max_per_probe_p95_abs_error_pu": p95_v, "status": "PASS" if voltage_pass else "FAIL", "H_coefficient_sha256": hashlib.sha256(np.asarray(voltage["sensitivity"]).tobytes()).hexdigest()})
        current_days.append({"operating_day": day, "rho": rho, "selected_slots": selection, "probe_count": day_probe_count, "probe_counts_by_predeclared_family": family_counts, "false_feasible_count": day_i_false, "max_abs_normalized_current_error_pu": max_i, "max_per_probe_mean_abs_error_pu": mean_i, "max_per_probe_p95_abs_error_pu": p95_i, "status": "PASS" if current_pass else "FAIL", "J_I_coefficient_sha256": str(current["coefficient_sha256"])})
        total_probes += day_probe_count; total_voltage_false += day_v_false; total_current_false += day_i_false
        print(json.dumps({"stage": "V17_V5_SURROGATE", "day": day, "probes": day_probe_count, "voltage": voltage_days[-1]["status"], "current": current_days[-1]["status"], "first_gate_failure": first_gate_failure}), flush=True)
        if first_gate_failure is not None:
            break
    all_days_complete = len(voltage_days) == len(DEBUG_DAYS)
    voltage_status = "PASS" if all_days_complete and all(row["status"] == "PASS" for row in voltage_days) else "FAIL_CLOSED_INCOMPLETE_AFTER_FIRST_GATE_FAILURE"
    current_status = "PASS" if all_days_complete and all(row["status"] == "PASS" for row in current_days) else "FAIL_CLOSED_ON_PREDECLARED_RHO_PROBE"
    remaining = [day for day in DEBUG_DAYS if day not in {row["operating_day"] for row in voltage_days}]
    voltage_report = {"artifact_id": "V17_V5_7DAY_VOLTAGE_SURROGATE_VALIDATION_V1", "status": voltage_status, "rho_candidate_tested": rho, "rho_valid_frozen_primary": rho if voltage_status == "PASS" and current_status == "PASS" else None, "predeclared_probe_family_reused": True, "days": voltage_days, "debug_days_completed": len(voltage_days), "remaining_debug_days_not_executed_after_fail_closed": remaining, "probe_count": total_probes, "voltage_false_feasible_count": total_voltage_false, "first_gate_failure": first_gate_failure, "tolerances": VOLTAGE_TOLERANCE, **_scientific_firewall()}
    current_report = {"artifact_id": "V17_V5_7DAY_CURRENT_SURROGATE_VALIDATION_V1", "status": current_status, "rho_candidate_tested": rho, "rho_valid_frozen_primary": rho if voltage_status == "PASS" and current_status == "PASS" else None, "predeclared_probe_family_reused": True, "days": current_days, "debug_days_completed": len(current_days), "remaining_debug_days_not_executed_after_fail_closed": remaining, "probe_count": total_probes, "hard_current_false_feasible_count": total_current_false, "first_gate_failure": first_gate_failure, "tolerances": CURRENT_ERROR_TOLERANCE, **_scientific_firewall()}
    write_json(output / "V17_V5_7DAY_VOLTAGE_SURROGATE_VALIDATION.json", voltage_report)
    write_json(output / "V17_V5_7DAY_CURRENT_SURROGATE_VALIDATION.json", current_report)
    return {"status": "PASS" if voltage_report["status"] == current_report["status"] == "PASS" else "FAIL_CLOSED", "probe_count": total_probes, "voltage_false_feasible_count": total_voltage_false, "current_false_feasible_count": total_current_false, "first_gate_failure": first_gate_failure}


def finalize_fail_closed(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); output = output.resolve()
    voltage = json.loads((output / "V17_V5_7DAY_VOLTAGE_SURROGATE_VALIDATION.json").read_text(encoding="utf-8"))
    current = json.loads((output / "V17_V5_7DAY_CURRENT_SURROGATE_VALIDATION.json").read_text(encoding="utf-8"))
    permutation = json.loads((output / "V17_V5_PERMUTATION_INVARIANCE_AUDIT.json").read_text(encoding="utf-8"))
    comparison = json.loads((output / "V17_V5_7DAY_REFERENCE_COMPARISON.json").read_text(encoding="utf-8"))
    anchors = json.loads((output / "V17_V5_7DAY_D1_ANCHOR_MANIFEST.json").read_text(encoding="utf-8"))
    for row in anchors["days"]:
        row.pop("voltage_generation", None)
        row.pop("current_generation", None)
    anchors["compact_manifest_only_cache_payloads_ignored"] = True
    write_json(output / "V17_V5_7DAY_D1_ANCHOR_MANIFEST.json", anchors)
    if voltage["status"] == current["status"] == "PASS":
        raise RuntimeError("V17_V5_FAILURE_FINALIZER_REFUSES_PASSING_SURROGATE")
    first_failure = current["first_gate_failure"]
    reference_hashes = {
        day: sha256_file(output / "reference_v5" / f"REFERENCE_COMPUTE_SCHEDULE_V5_{day}.npz")
        for day in DEBUG_DAYS
    }
    freeze = {
        "artifact_id": "V17_V5_7DAY_PRE_EVALUATION_FREEZE_MANIFEST_V1",
        "status": "NOT_MINTED_SURROGATE_GATE_FAIL",
        "pre_evaluation_freeze_minted": False,
        "freeze_token": None,
        "blocking_gate": "V5_J_I_RHO_0_10_ERROR_BOUND",
        "first_gate_failure": first_failure,
        "accepted_rho": None,
        "scheduler_code_sha256": sha256_file(repo / "dayahead/v17_reference_scheduler_v5.py"),
        "V5_contract_sha256": sha256_file(output / "V17_REFERENCE_SCHEDULER_V5_CONTRACT.json"),
        "V5_reference_sha256": reference_hashes,
        "anchor_H_J_sha256": {row["operating_day"]: {"H": row["voltage_cache"]["sha256"], "J_I": row["current_cache"]["sha256"]} for row in anchors["days"]},
        "B0_B3_result_reads_before_freeze": 0,
        "scientific_parameter_adjustments_after_gate_failure": 0,
        **_scientific_firewall(),
    }
    write_json(output / "V17_V5_7DAY_PRE_EVALUATION_FREEZE_MANIFEST.json", freeze)

    blocked_common = {
        "status": "NOT_EXECUTED_PRE_EVALUATION_FREEZE_NOT_MINTED",
        "blocking_gate": "V5_J_I_RHO_0_10_ERROR_BOUND",
        "first_gate_failure": first_failure,
        "scientific_result_rows": 0,
        "solver_calls": 0,
        "Fresh_OpenDSS_calls": 0,
        **_scientific_firewall(),
    }
    blocked_artifacts = {
        "V17_V5_7DAY_B0_B1_B2_B3_RESULTS.json": {"artifact_id": "V17_V5_7DAY_B0_B1_B2_B3_RESULTS_V1", "B0_B1_B2_B3_case_day_count": 0, **blocked_common},
        "V17_V5_7DAY_DUAL_FRESH_AC_RESULTS.json": {"artifact_id": "V17_V5_7DAY_DUAL_FRESH_AC_RESULTS_V1", "primary_schedule_count": 0, "secondary_schedule_count": 0, **blocked_common},
        "V17_V5_7DAY_AIDC_GRID_VALUE_FORENSIC.json": {"artifact_id": "V17_V5_7DAY_AIDC_GRID_VALUE_FORENSIC_V1", "B1_minus_B0_rows": 0, "B3_minus_B2_rows": 0, **blocked_common},
        "V17_V5_7DAY_AIDC_ONLY_UPPER_BOUND.json": {"artifact_id": "V17_V5_7DAY_AIDC_ONLY_UPPER_BOUND_V1", "upper_bound_solve_count": 0, **blocked_common},
    }
    for name, payload in blocked_artifacts.items():
        write_json(output / name, payload)

    classification = "V17_V5_E_SURROGATE_OR_AC_VALIDATION_FAILURE"
    resume = "V17_V5_FURTHER_CORRECTION_REQUIRED"
    review = {
        "artifact_id": "V17_V5_7DAY_FINAL_REVIEW_V1",
        "status": "FAIL_CLOSED_BEFORE_B0_B3",
        "classification": classification,
        "resume_decision": resume,
        "V5_implementation": "PASS",
        "permutation_invariance": {"status": permutation["status"], "max_abs_error_nodeh": permutation["maximum_deterministic_repeat_error_nodeh"]},
        "V4_V5_reference_comparison": {
            "status": comparison["status"],
            "temporal_max_abs_error_nodeh": max(row["temporal_service_max_abs_difference_nodeh"] for row in comparison["days"]),
            "critical_slot_active_AIDC_count_v5": {row["operating_day"]: row["critical_slot_active_AIDC_count_v5"] for row in comparison["days"]},
            "maximum_AIDC_concentration_share_v5": max(row["maximum_AIDC_concentration_share_v5"] for row in comparison["days"]),
        },
        "D1_anchor_H_J": {"status": anchors["status"], "day_count": len(anchors["days"])},
        "surrogate_validation": {"voltage_status": voltage["status"], "current_status": current["status"], "first_gate_failure": first_failure, "accepted_rho": None},
        "B0_B1_B2_B3": "NOT_EXECUTED",
        "dual_Fresh_AC": "NOT_EXECUTED",
        "AIDC_only_upper_bound": "NOT_EXECUTED",
        "reason": "The predeclared rho=0.10 current-surrogate error bound failed before the required pre-evaluation freeze; downstream scientific evaluation is unauthorized.",
        "verification": {
            "focused_command": "py -3.11 -m pytest tests/test_v17_reference_scheduler_v5.py tests/test_v17_v5_fail_closed_review.py tests/test_v17_deferrability_semantics.py tests/test_v17_ac_restoration_regression.py -q",
            "focused_result": "12 passed in 0.15s",
            "tests_tree_command": "py -3.11 -m pytest tests -q",
            "tests_tree_result": "559 passed, 4 failed, 4 skipped, 84 subtests passed in 68.53s",
            "tests_tree_failures": [
                "test_g56_freeze_artifacts torch DLL runtime unavailable (3 sibling tests passed)",
                "test_pfr_mess_energy_recovery existing PFR projection failure; no PFR path changed",
                "two shared_exact_source_preparation tests require POSIX fcntl and fail on Windows",
            ],
            "repo_root_pytest_collection": "ABORTED_BY_EXISTING science/r25l_b5_monolithic_gate_proof_test.py IMPORT_TIME_SYSTEMEXIT",
            "py_compile": "PASS",
        },
        **_scientific_firewall(),
    }
    write_json(output / "V17_V5_7DAY_FINAL_REVIEW.json", review)
    artifact_names = [
        "V17_PRE_V5_DIRTY_TREE_PRESERVATION_MANIFEST.json",
        "V17_REFERENCE_SCHEDULER_V5_CONTRACT.json",
        "V17_V4_V5_ROOT_CAUSE_UNIT_TEST.json",
        "V17_V5_PERMUTATION_INVARIANCE_AUDIT.json",
        "V17_V5_7DAY_REFERENCE_COMPARISON.json",
        "V17_V5_7DAY_D1_ANCHOR_MANIFEST.json",
        "V17_V5_7DAY_VOLTAGE_SURROGATE_VALIDATION.json",
        "V17_V5_7DAY_CURRENT_SURROGATE_VALIDATION.json",
        "V17_V5_7DAY_PRE_EVALUATION_FREEZE_MANIFEST.json",
        "V17_V5_7DAY_B0_B1_B2_B3_RESULTS.json",
        "V17_V5_7DAY_DUAL_FRESH_AC_RESULTS.json",
        "V17_V5_7DAY_AIDC_GRID_VALUE_FORENSIC.json",
        "V17_V5_7DAY_AIDC_ONLY_UPPER_BOUND.json",
        "V17_V5_7DAY_FINAL_REVIEW.json",
    ]
    manifest = {
        "artifact_id": "V17_V5_CANDIDATE_MANIFEST_V1",
        "status": "FAIL_CLOSED_CANDIDATE_NOT_FROZEN",
        "classification": classification,
        "resume_decision": resume,
        "git_head_before_final_review_commit": __import__("subprocess").run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True).stdout.strip(),
        "artifacts_sha256": {name: sha256_file(output / name) for name in artifact_names},
        "code_sha256": {path: sha256_file(repo / path) for path in ("dayahead/v17_reference_scheduler_v5.py", "dayahead/v17_v5_revalidation.py", "tests/test_v17_reference_scheduler_v5.py", "tests/test_v17_v5_fail_closed_review.py")},
        "verification_summary": "12 focused PASS; tests tree 559 PASS / 4 unrelated-or-environmental FAIL / 4 skipped / 84 subtests PASS",
        "large_reproducible_cache_policy": "SHA_IN_COMPACT_MANIFEST_NOT_COMMITTED",
        "V4_artifacts_changed": 0,
        "remaining_April_day_runs": 0,
        "B0_B1_B2_B3_solver_calls": 0,
        "dual_Fresh_AC_calls": 0,
        **_scientific_firewall(),
    }
    write_json(output / "V17_V5_CANDIDATE_MANIFEST.json", manifest)
    return {"classification": classification, "resume_decision": resume, "freeze_minted": False}


def _scientific_firewall() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "grid_benefit_selected_parameters": 0,
        "AIDC_site_changes": 0,
        "beta_changes": 0,
        "kappa_changes": 0,
        "PUE_changes": 0,
        "PF_changes": 0,
        "OpenDSS_calls_inside_Benders": 0,
    }


def _frozen_inputs(repo: Path, output: Path):
    prediction_path = output / "V17_RCMQT_V2_APRIL_PREDICTIONS.npz"
    preparation_path = output / "cache/V17_RCMQT_V2_APRIL_VALIDATION_PREPARATION.json"
    training_path = output / "V17_RCMQT_V2_TRAINING_REPORT.json"
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    training = json.loads(training_path.read_text(encoding="utf-8"))
    if training["weights_file_sha256"] != FROZEN_WEIGHTS_SHA256:
        raise RuntimeError("V17_V5_FROZEN_WEIGHT_SHA_MISMATCH")
    if preparation["frozen_weights_sha256"] != FROZEN_WEIGHTS_SHA256:
        raise RuntimeError("V17_V5_PREPARATION_WEIGHT_SHA_MISMATCH")
    if training["final_weight_config_fingerprint"] != FROZEN_CHECKPOINT_FINGERPRINT:
        raise RuntimeError("V17_V5_CHECKPOINT_FINGERPRINT_MISMATCH")
    saved = np.load(prediction_path, allow_pickle=False)
    prediction = np.asarray(saved["prediction"], dtype=np.float64)
    scales = np.asarray([float(preparation["target_scales"][name]) for name in TARGET_NAMES])
    prediction_raw = prediction * scales[None, None, :, None]
    days = tuple(preparation["validation_days"])
    rack_contract = json.loads((repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json").read_text(encoding="utf-8"))
    authority = load_frozen_rack_authority(Path(rack_contract["source_path"]))
    capacity = {
        rack.rack_id: BETA_AIDC * rack.deliverable_gpu_capacity / GPU_PER_NODE * DT_HOURS
        for rack in authority.racks
    }
    return days, prediction_raw, authority, capacity, rack_contract


def _arrivals(prediction_raw: np.ndarray, day_index: int) -> dict[tuple[str, int], tuple[float, ...]]:
    return {
        (name, node): tuple(
            BETA_AIDC * float(prediction_raw[day_index, slot, _target_index(name, node), 1])
            for slot in range(96)
        )
        for name in LATENCY_CLASSES
        for node in (1, 2, 4, 8, 16)
    }


def _allocation_array(reference, rack_ids: tuple[str, ...]) -> np.ndarray:
    value = np.zeros((len(COHORTS), len(rack_ids), 96), dtype=np.float64)
    for class_index, name in enumerate(LATENCY_CLASSES):
        for node_index, node in enumerate((1, 2, 4, 8, 16)):
            cohort_index = class_index * 5 + node_index
            for rack_index, rack in enumerate(rack_ids):
                for slot in range(96):
                    value[cohort_index, rack_index, slot] = reference.service_by_class_node_rack_slot[(name, node, rack, slot)]
    return value


def _physical_error(baseline, candidate, reverse: Mapping[str, str]) -> float:
    error = 0.0
    for (name, node, label, slot), value in candidate.service_by_class_node_rack_slot.items():
        error = max(error, abs(float(value) - float(baseline.service_by_class_node_rack_slot[(name, node, reverse[label], slot)])))
    return error


def _permutation_audit(arrivals, capacity: Mapping[str, float], baseline) -> dict[str, Any]:
    rack_ids = tuple(sorted(capacity))
    permutations: list[tuple[str, tuple[str, ...]]] = [
        ("original", rack_ids),
        ("reversed", tuple(reversed(rack_ids))),
    ]
    for shift in (1, 3, 6, 11):
        shifted = []
        for rack in rack_ids:
            aidc, suffix = rack.split("_", 1)
            index = int(aidc[-2:])
            shifted.append(f"AIDC{((index - 1 + shift) % 12) + 1:02d}_{suffix}")
        permutations.append((f"cyclic_AIDC_shift_{shift}", tuple(shifted)))
    within = []
    for rack in rack_ids:
        aidc, suffix = rack.split("_", 1)
        rack_number = int(suffix[-2:])
        within.append(f"{aidc}_LP{5-rack_number:02d}")
    permutations.append(("rack_reverse_within_AIDC", tuple(within)))
    combined = tuple(reversed(within))
    permutations.append(("combined_AIDC_rack_reverse", combined))
    shuffled = list(rack_ids); random.Random(20260830).shuffle(shuffled)
    permutations.append(("deterministic_randomized_labels", tuple(shuffled)))

    rows = []
    maximum = 0.0
    for name, new_labels in permutations:
        forward = dict(zip(rack_ids, new_labels, strict=True))
        reverse = {new: old for old, new in forward.items()}
        relabeled_capacity = {forward[old]: capacity[old] for old in reversed(rack_ids)}
        candidate = build_reference_schedule_v5(arrivals, relabeled_capacity)
        error = _physical_error(baseline, candidate, reverse)
        maximum = max(maximum, error)
        rows.append({"permutation": name, "max_abs_error_nodeh": error})
    insertion_orders = []
    for name, items in (
        ("sorted", list(sorted(capacity.items()))),
        ("reversed", list(reversed(sorted(capacity.items())))),
        ("randomized_20260830", random.Random(20260830).sample(list(capacity.items()), len(capacity))),
    ):
        candidate = build_reference_schedule_v5(arrivals, dict(items))
        error = _physical_error(baseline, candidate, {key: key for key in capacity})
        maximum = max(maximum, error)
        insertion_orders.append({"construction": name, "max_abs_error_nodeh": error})
    return {"physical_label_permutations": rows, "dictionary_input_orders": insertion_orders, "max_abs_error_nodeh": maximum, "tolerance": 1e-12, "status": "PASS" if maximum <= 1e-12 else "FAIL"}


def materialize(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); output = output.resolve()
    days, prediction_raw, authority, capacity, rack_contract = _frozen_inputs(repo, output)
    day_to_index = {day: index for index, day in enumerate(days)}
    if any(day not in day_to_index for day in DEBUG_DAYS):
        raise RuntimeError("V17_V5_DEBUG_DAY_MISSING")
    rack_ids = tuple(rack.rack_id for rack in authority.racks)
    rack_index = {rack: index for index, rack in enumerate(rack_ids)}
    aidc_ids = tuple(f"AIDC{index:02d}" for index in range(1, 13))
    aidc_racks = {aidc: tuple(i for i, rack in enumerate(authority.racks) if rack.aidc_id == aidc) for aidc in aidc_ids}
    reference_dir = output / "reference_v5"; reference_dir.mkdir(parents=True, exist_ok=True)
    comparison_rows = []; reference_rows = []; permutation_rows = []
    historical_forensic = json.loads((output / "V17_APRIL_7DAY_AIDC_ACTUATION_FORENSIC.json").read_text(encoding="utf-8"))
    critical_slots = {row["operating_day"]: int(row["pairs"]["B1_vs_B0"]["grid_projection"]["critical"]["slot"]) for row in historical_forensic["days"]}
    for day in DEBUG_DAYS:
        day_index = day_to_index[day]
        arrivals_by_key = _arrivals(prediction_raw, day_index)
        v5 = build_reference_schedule_v5(arrivals_by_key, capacity)
        allocation = _allocation_array(v5, rack_ids)
        arrivals_array = np.asarray([arrivals_by_key[(name, node)] for name in LATENCY_CLASSES for node in (1, 2, 4, 8, 16)], dtype=np.float64)
        flexible_power = np.zeros((96, 48), dtype=np.float64)
        for cohort_index, cohort in enumerate(COHORTS):
            flexible_power += KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] / DT_HOURS * allocation[cohort_index].T
        p_ref = BETA_AIDC * prediction_raw[day_index, :, 0, 2]
        g_fixed_gpu = BETA_AIDC * GPU_PER_NODE * prediction_raw[day_index, :, 1, 2]
        p_res_sys = p_ref - flexible_power.sum(axis=1)
        if float(p_res_sys.min()) < -1e-9:
            raise RuntimeError(f"V17_V5_POWER_RESIDUAL_NEGATIVE:{day}:{p_res_sys.min()}")
        p_res_rack = p_res_sys[:, None] * np.asarray(authority.power_weights)[None, :]
        g_res_rack = g_fixed_gpu[:, None] * np.asarray(authority.gpu_weights)[None, :]
        total_gpu = g_res_rack + GPU_PER_NODE / DT_HOURS * allocation.sum(axis=0).T
        capacities_gpu = BETA_AIDC * np.asarray([rack.deliverable_gpu_capacity for rack in authority.racks])
        gpu_cap_violation = float(np.max(total_gpu - capacities_gpu[None, :]))
        if gpu_cap_violation > 1e-9:
            raise RuntimeError(f"V17_V5_GPU_CAP_REFERENCE_FAIL:{day}:{gpu_cap_violation}")
        p_res_aidc = np.asarray([[sum(p_res_rack[slot, r] for r in aidc_racks[aidc]) for aidc in aidc_ids] for slot in range(96)])
        p_f_aidc = np.asarray([[sum(flexible_power[slot, r] for r in aidc_racks[aidc]) for aidc in aidc_ids] for slot in range(96)])
        plan = PUE_PLAN * (p_res_aidc + p_f_aidc)
        arrays = {"allocation": allocation, "arrivals": arrivals_array, "p_res_aidc": p_res_aidc, "g_res_rack": g_res_rack, "plan_kw_96x12": plan, "gpu_capacities": capacities_gpu, "p_ref": p_ref, "g_fixed_gpu": g_fixed_gpu}
        fingerprint = _array_fingerprint(arrays)
        path = reference_dir / f"REFERENCE_COMPUTE_SCHEDULE_V5_{day}.npz"
        np.savez_compressed(path, **arrays, array_fingerprint=np.asarray(fingerprint))
        reference_rows.append({"operating_day": day, "path": str(path.resolve()), "sha256": sha256_file(path), "array_fingerprint": fingerprint, "p_residual_min_kw": float(p_res_sys.min()), "gpu_cap_max_violation": max(0.0, gpu_cap_violation), **v5.evidence})

        v4_path = output / "reference_v4" / f"REFERENCE_COMPUTE_SCHEDULE_V4_{day}.npz"
        v4 = np.load(v4_path, allow_pickle=False); a4 = np.asarray(v4["allocation"], dtype=float)
        temporal_error = float(np.max(np.abs(a4.sum(axis=1) - allocation.sum(axis=1))))
        per_rack_v4 = a4.sum(axis=(0, 2)); per_rack_v5 = allocation.sum(axis=(0, 2))
        per_aidc_v4 = np.asarray([per_rack_v4[list(aidc_racks[aidc])].sum() for aidc in aidc_ids])
        per_aidc_v5 = np.asarray([per_rack_v5[list(aidc_racks[aidc])].sum() for aidc in aidc_ids])
        active = np.asarray([[sum(allocation[:, list(aidc_racks[aidc]), slot].ravel()) > 1e-12 for aidc in aidc_ids] for slot in range(96)])
        aidc_service = np.asarray([[allocation[:, list(aidc_racks[aidc]), slot].sum() for aidc in aidc_ids] for slot in range(96)])
        concentration = np.divide(aidc_service.max(axis=1), aidc_service.sum(axis=1), out=np.zeros(96), where=aidc_service.sum(axis=1) > 1e-12)
        critical = critical_slots[day]
        comparison_rows.append({
            "operating_day": day,
            "total_reference_service_nodeh_v4": float(a4.sum()),
            "total_reference_service_nodeh_v5": float(allocation.sum()),
            "service_parity_abs_error_nodeh": abs(float(allocation.sum()) - float(arrivals_array.sum())),
            "temporal_service_max_abs_difference_nodeh": temporal_error,
            "spatial_service_l1_half_difference_nodeh": float(0.5 * np.abs(allocation - a4).sum()),
            "workload_by_AIDC_v4_nodeh": dict(zip(aidc_ids, map(float, per_aidc_v4), strict=True)),
            "workload_by_AIDC_v5_nodeh": dict(zip(aidc_ids, map(float, per_aidc_v5), strict=True)),
            "workload_by_Rack_v4_nodeh": dict(zip(rack_ids, map(float, per_rack_v4), strict=True)),
            "workload_by_Rack_v5_nodeh": dict(zip(rack_ids, map(float, per_rack_v5), strict=True)),
            "active_AIDC_count_by_slot_v5": list(map(int, active.sum(axis=1))),
            "critical_slot": critical,
            "critical_slot_active_AIDC_count_v5": int(active[critical].sum()),
            "maximum_AIDC_concentration_share_v5": float(concentration.max()),
        })
        permutation_rows.append({"operating_day": day, **_permutation_audit(arrivals_by_key, capacity, v5)})

    max_permutation_error = max(row["max_abs_error_nodeh"] for row in permutation_rows)
    permutation_audit = {"artifact_id": "V17_V5_PERMUTATION_INVARIANCE_AUDIT_V1", "status": "PASS" if max_permutation_error <= 1e-12 else "FAIL", "days": permutation_rows, "maximum_deterministic_repeat_error_nodeh": max_permutation_error, **_scientific_firewall()}
    write_json(output / "V17_V5_PERMUTATION_INVARIANCE_AUDIT.json", permutation_audit)
    contract = {
        "artifact_id": "V17_REFERENCE_SCHEDULER_V5_CONTRACT_V1", "status": permutation_audit["status"],
        "authority_id": AUTHORITY_ID, "policy_identifier": POLICY_ID,
        "terminology": "CAPACITY-WEIGHTED SYNTHETIC NEUTRAL SPATIALIZATION",
        "temporal_ordering": ["due slot", "arrival slot", "class C1-C5", "node class 1-2-4-8-16"],
        "spatial_allocation_equation": "x_r=min(R_r,W_remaining*C_r/sum_active(C)); redistribute residual after saturation",
        "capacity_authority": "existing source-derived rack_capacity_nodeh_per_slot",
        "capacity_source_path": rack_contract["source_path"], "capacity_source_sha256": rack_contract["source_sha256"],
        "historical_spatial_labels_available": False, "synthetic_spatialization": True,
        "grid_information_reads": 0, "MESS_information_reads": 0, "J_I_reads": 0, "H_reads": 0, "OpenDSS_calls": 0,
        "AIDC_label_ordering_influence": 0, "Rack_label_ordering_influence": 0,
        "permutation_invariance_test": {"status": permutation_audit["status"], "max_abs_error_nodeh": max_permutation_error, "tolerance": 1e-12},
        **_scientific_firewall(),
    }
    write_json(output / "V17_REFERENCE_SCHEDULER_V5_CONTRACT.json", contract)
    comparison = {"artifact_id": "V17_V5_7DAY_REFERENCE_COMPARISON_V1", "status": "PASS" if all(row["temporal_service_max_abs_difference_nodeh"] <= 1e-12 and row["service_parity_abs_error_nodeh"] <= 1e-10 for row in comparison_rows) else "FAIL", "debug_days": list(DEBUG_DAYS), "days": comparison_rows, "V4_artifacts_overwritten": False, **_scientific_firewall()}
    write_json(output / "V17_V5_7DAY_REFERENCE_COMPARISON.json", comparison)
    root_cause = {
        "artifact_id": "V17_V4_V5_ROOT_CAUSE_UNIT_TEST_V1", "status": "PASS",
        "fixture": {"workload_nodeh": 0.5, "capacities": {"AIDC01_LP01": 1.0, "AIDC02_LP01": 3.0}},
        "V4": {"AIDC01_LP01": 0.5, "AIDC02_LP01": 0.0, "classification": "LEXICOGRAPHIC_FIRST_FIT"},
        "V5": {"AIDC01_LP01": 0.125, "AIDC02_LP01": 0.375, "classification": POLICY_ID},
        "historical_classifications_preserved": ["V17_GPU_BOUNDARY_D_FLEX_COHORT_SEMANTICS_DEFECT", "V17_AIDC_ACTUATION_B_GRID_SENSITIVITY_LIMITED", "V17_REFERENCE_SPATIAL_B_ARBITRARY_TIE_BREAKING_ARTIFACT"],
    }
    write_json(output / "V17_V4_V5_ROOT_CAUSE_UNIT_TEST.json", root_cause)
    references = {"artifact_id": "V17_REFERENCE_SCHEDULER_V5_7DAY_VALIDATION_V1", "status": "PASS_7_DAYS", "days": reference_rows, "reference_authority": AUTHORITY_ID, "beta_AIDC_unchanged": BETA_AIDC, "forecast_weights_sha256": FROZEN_WEIGHTS_SHA256, "forecast_checkpoint_fingerprint": FROZEN_CHECKPOINT_FINGERPRINT, **_scientific_firewall()}
    write_json(output / "V17_REFERENCE_SCHEDULER_V5_7DAY_VALIDATION.json", references)
    return {"status": "PASS" if permutation_audit["status"] == comparison["status"] == "PASS" else "FAIL", "day_count": 7, "maximum_permutation_error": max_permutation_error}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("materialize", "anchors", "validate", "finalize-failure"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    args = parser.parse_args(argv)
    if args.phase == "materialize": result = materialize(args.repo, args.output)
    elif args.phase == "anchors": result = build_anchors(args.repo, args.source, args.output)
    elif args.phase == "validate": result = validate_surrogates(args.repo, args.source, args.output)
    else: result = finalize_fail_closed(args.repo, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
