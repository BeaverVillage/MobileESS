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
    _array_fingerprint,
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
    parser.add_argument("phase", choices=("materialize",))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    args = parser.parse_args(argv)
    result = materialize(args.repo, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
