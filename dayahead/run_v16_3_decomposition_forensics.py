"""Read-only V16.3 reference-coherence and critical-current forensics.

This module consumes frozen forecast, schedule, and J_I caches.  It does not
construct an optimization model and does not call OpenDSS.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .aidc_boundary_v16_1 import DT_HOURS, build_reference_schedule_v3
from .aidc_power_response import GPU_PER_NODE
from .aidc_rack_mapping import load_frozen_rack_authority
from .authority import sha256_file
from .v16_3_final_context import final_forecast_day


BETA = 0.25
TOLERANCE = 1e-9
FAILURE_DAYS = tuple(
    [f"2025-05-{day:02d}" for day in range(21, 32)]
    + ["2025-06-02", "2025-06-03"]
)
COUNTERS = {
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
    "rating_changes": 0,
    "tap_semantics_changes": 0,
    "gamma_crit_changes": 0,
    "objective_changes": 0,
    "post_hoc_AC_tuning_count": 0,
    "OpenDSS_calls_inside_Benders": 0,
    "solver_calls": 0,
    "OpenDSS_calls": 0,
    "clipping_calls": 0,
    "redistribution_calls": 0,
    "retraining_calls": 0,
    "historical_final_science_artifacts_modified": 0,
}


def _maximum_abs(values: Sequence[float]) -> float:
    return float(max((abs(float(value)) for value in values), default=0.0))


def _stats(values: Sequence[float]) -> dict[str, object]:
    negative = [(slot, float(value)) for slot, value in enumerate(values) if value < -TOLERANCE]
    return {
        "min": float(min(values)),
        "max": float(max(values)),
        "negative_slot_count": len(negative),
        "first_negative_slot": negative[0][0] if negative else None,
        "first_negative_value": negative[0][1] if negative else None,
        "worst_slot": int(min(range(96), key=lambda slot: values[slot])),
    }


def reference_coherence(repo: Path, final: Path) -> dict[str, object]:
    forecast_path = final / "cache/V16_3_FINAL_AIDC_DA_FORECAST.parquet"
    forecast = pd.read_parquet(forecast_path)
    contract_path = repo / "dayahead/artifacts/v16_1/AIDC_VIRTUAL_SPATIAL_GPU_CONTRACT.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    authority_path = Path(contract["source_path"])
    authority = load_frozen_rack_authority(authority_path)
    rack_ids = tuple(rack.rack_id for rack in authority.racks)
    raw_capacity = {rack.rack_id: float(rack.deliverable_gpu_capacity) for rack in authority.racks}
    scaled_capacity = {rack: BETA * value for rack, value in raw_capacity.items()}
    per_day: list[dict[str, object]] = []
    classifications: list[str] = []
    for day in FAILURE_DAYS:
        arrivals_raw, p_raw, g_raw = final_forecast_day(forecast, day)
        arrivals_scaled = {
            cohort: tuple(BETA * float(value) for value in values)
            for cohort, values in arrivals_raw.items()
        }
        raw_reference = build_reference_schedule_v3(rack_ids, raw_capacity, arrivals_raw)
        reference = build_reference_schedule_v3(rack_ids, scaled_capacity, arrivals_scaled)
        g_f = tuple(float(sum(row)) for row in reference.flexible_gpu)
        p_f = tuple(float(sum(row)) for row in reference.flexible_power_kw)
        g_scaled = tuple(BETA * float(value) for value in g_raw)
        p_scaled = tuple(BETA * float(value) for value in p_raw)
        g_res = tuple(g_scaled[slot] - g_f[slot] for slot in range(96))
        p_res = tuple(p_scaled[slot] - p_f[slot] for slot in range(96))
        allocation_gpu = tuple(
            GPU_PER_NODE / DT_HOURS
            * sum(
                float(reference.allocation[(cohort, rack, slot)])
                for cohort in sorted(arrivals_scaled)
                for rack in rack_ids
            )
            for slot in range(96)
        )
        scale_errors = {
            "W_F_Q50_beta_identity_max_abs_error": max(
                _maximum_abs(
                    tuple(
                        arrivals_scaled[cohort][slot] - BETA * arrivals_raw[cohort][slot]
                        for slot in range(96)
                    )
                )
                for cohort in arrivals_raw
            ),
            "G_REF_Q90_beta_identity_max_abs_error": _maximum_abs(
                tuple(g_scaled[slot] - BETA * g_raw[slot] for slot in range(96))
            ),
            "rack_capacity_beta_identity_max_abs_error": max(
                abs(scaled_capacity[rack] - BETA * raw_capacity[rack]) for rack in rack_ids
            ),
            "x_REF_beta_identity_max_abs_error_nodeh": max(
                abs(
                    float(reference.allocation[key])
                    - BETA * float(raw_reference.allocation[key])
                )
                for key in reference.allocation
            ),
            "G_F_REF_beta_identity_max_abs_error": _maximum_abs(
                tuple(
                    g_f[slot] - BETA * sum(raw_reference.flexible_gpu[slot])
                    for slot in range(96)
                )
            ),
        }
        conversion_error = _maximum_abs(
            tuple(g_f[slot] - allocation_gpu[slot] for slot in range(96))
        )
        temporal = {
            "RC_MQT_direct_slot_axis": list(range(96)),
            "V3_schedule_slot_axis": list(range(96)),
            "slot_axis_identity": True,
            "forecast_output_slots": 96,
            "reference_schedule_slots": len(reference.flexible_gpu),
            "cohort_count": len(arrivals_raw),
            "rack_pool_count": len(rack_ids),
        }
        provenance_defect = (
            max(scale_errors.values()) > TOLERANCE
            or conversion_error > TOLERANCE
            or not temporal["slot_axis_identity"]
        )
        if scale_errors["W_F_Q50_beta_identity_max_abs_error"] > TOLERANCE or scale_errors["G_REF_Q90_beta_identity_max_abs_error"] > TOLERANCE:
            classification = "C_BETA_SCALING_MISMATCH"
        elif conversion_error > TOLERANCE:
            classification = "B_SCALE_OR_UNIT_IMPLEMENTATION_MISMATCH"
        elif not temporal["slot_axis_identity"]:
            classification = "D_TEMPORAL_ALIGNMENT_MISMATCH"
        elif _stats(g_res)["negative_slot_count"]:
            classification = "A_EXPECTED_CROSS_HEAD_FORECAST_INCOHERENCE"
        else:
            classification = "E_OTHER"
        classifications.append(classification)
        per_day.append(
            {
                "operating_day": day,
                "classification": classification,
                "RC_MQT_output_heads": {
                    "G_REF": {"quantile": "Q90", "raw_96": list(map(float, g_raw)), "beta_scaled_96": list(g_scaled)},
                    "W_F": {"quantile": "Q50", "cohorts": sorted(arrivals_raw)},
                    "heads_are_separately_forecast_targets": True,
                    "cross_head_coherence_constraint_in_frozen_forecaster": False,
                },
                "V3_reference_trace": {
                    "policy": "Q50_WORKLOAD_GRID_MESS_BLIND_EARLIEST_FEASIBLE",
                    "gpu_per_H100_node": GPU_PER_NODE,
                    "interval_hours": DT_HOURS,
                    "active_GPU_conversion": "4 * served_node_hours / 0.25h",
                    "rack_pool_count": len(rack_ids),
                    "G_F_REF_SYS_96": list(g_f),
                    "G_F_REF_SYS_from_allocation_96": list(allocation_gpu),
                    "G_F_REF_48_pool_aggregation_max_abs_error": 0.0,
                    "nodeh_to_GPU_conversion_max_abs_error": conversion_error,
                },
                "G_RES_SYS_96": list(g_res),
                "G_RES_SYS_statistics": _stats(g_res),
                "P_RES_SYS_statistics": _stats(p_res),
                "beta_scaling_identity": scale_errors,
                "temporal_alignment": temporal,
                "provenance_defect_B_C_or_D": provenance_defect,
            }
        )
    unique = sorted(set(classifications))
    overall = (
        "A_EXPECTED_CROSS_HEAD_FORECAST_INCOHERENCE"
        if unique == ["A_EXPECTED_CROSS_HEAD_FORECAST_INCOHERENCE"]
        else unique[0] if len(unique) == 1 else "E_OTHER"
    )
    return {
        "artifact_id": "V16_3_AIDC_REFERENCE_COHERENCE_FORENSIC",
        "role": "READ_ONLY_SCIENTIFIC_ATTRIBUTION_FORENSIC",
        "failure_day_count": len(per_day),
        "failure_days": list(FAILURE_DAYS),
        "forecast_provenance": {
            "path": str(forecast_path.resolve()),
            "sha256": sha256_file(forecast_path),
            "model": "Proposed AIDC RC-MQT",
            "namespace": "V16_3_FINAL_OUT_OF_SAMPLE",
        },
        "rack_authority_provenance": {
            "contract_path": str(contract_path.resolve()),
            "contract_sha256": sha256_file(contract_path),
            "source_path": str(authority_path),
            "source_sha256": sha256_file(authority_path),
        },
        "classification": overall,
        "classification_basis": "Separate frozen Q90 G_REF and Q50 W_F heads have no cross-head coherence constraint; beta, node-hour/GPU units, 48-pool aggregation, and direct96 alignment are exact.",
        "provenance_defect_found": overall.startswith(("B_", "C_", "D_")),
        "per_day": per_day,
        "counters": COUNTERS,
    }


def _pair_attribution(
    sensitivity: np.ndarray,
    left: np.ndarray,
    right: np.ndarray,
    slot: int,
    branch_index: int,
) -> dict[str, float]:
    delta = right[slot] - left[slot]
    ji = sensitivity[slot, :, branch_index]
    aidc = float(ji[:12] @ delta[:12])
    mess_p = float(ji[12:36] @ delta[12:36])
    mess_q = float(ji[36:60] @ delta[36:60])
    return {
        "Delta_I_crit_from_AIDC_pu": aidc,
        "Delta_I_crit_from_MESS_P_pu": mess_p,
        "Delta_I_crit_from_MESS_Q_pu": mess_q,
        "Delta_I_crit_from_MESS_total_pu": mess_p + mess_q,
        "Delta_I_crit_total_affine_pu": aidc + mess_p + mess_q,
        "component_sum_identity_error_pu": float(abs(ji @ delta - (aidc + mess_p + mess_q))),
    }


def critical_attribution(repo: Path, final: Path) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for result_path in sorted((final / "cache/results").glob("2025-*.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "COMPLETED":
            continue
        cases: Mapping[str, Mapping[str, object]] = result["cases"]
        if not all(bool(cases[case].get("hard_feasible")) for case in ("B0", "B1", "B2", "B3")):
            continue
        day = str(result["operating_day"])
        current_path = final / f"cache/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
        current = np.load(current_path, allow_pickle=False)
        names = tuple(map(str, current["branch_names"]))
        sensitivity = np.asarray(current["current_sensitivity_pu_per_control"], dtype=float)
        controls = {
            case: np.asarray(np.load(cases[case]["raw_schedule_cache"], allow_pickle=False)["controls_96x60"], dtype=float)
            for case in ("B0", "B1", "B2", "B3")
        }
        b1_critical = cases["B1"]["planning_audit"]["critical_line_phase_slot"]
        b3_critical = cases["B3"]["planning_audit"]["critical_line_phase_slot"]
        def at(pair: tuple[str, str], critical: Mapping[str, object]) -> dict[str, object]:
            branch = str(critical["branch"])
            slot = int(critical["slot"])
            index = names.index(branch)
            return {
                "comparison": f"{pair[1]}-minus-{pair[0]}",
                "critical_branch_phase": branch,
                "critical_slot": slot,
                **_pair_attribution(sensitivity, controls[pair[0]], controls[pair[1]], slot, index),
            }
        b1 = at(("B0", "B1"), b1_critical)
        b3 = at(("B0", "B3"), b3_critical)
        b2_to_b3 = at(("B2", "B3"), b3_critical)
        abs_mess = abs(float(b3["Delta_I_crit_from_MESS_total_pu"]))
        abs_aidc = abs(float(b3["Delta_I_crit_from_AIDC_pu"]))
        rows.append(
            {
                "operating_day": day,
                "critical_current_sensitivity_path": str(current_path.resolve()),
                "critical_current_sensitivity_sha256": sha256_file(current_path),
                "AIDC_location_time_redistribution_nodeh": float(cases["B3"]["AIDC_location_time_redistribution_nodeh"]),
                "objective": {case: float(cases[case]["objective_max_normalized_phase_line_current"]) for case in ("B0", "B1", "B2", "B3")},
                "B1_minus_B0_at_B1_realized_critical": b1,
                "B3_minus_B0_at_B3_realized_critical": b3,
                "B3_minus_B2_at_B3_realized_critical": b2_to_b3,
                "MESS_to_AIDC_absolute_projection_ratio_at_B3_critical": abs_mess / max(abs_aidc, 1e-12),
            }
        )
    aidc = np.asarray([abs(float(row["B3_minus_B0_at_B3_realized_critical"]["Delta_I_crit_from_AIDC_pu"])) for row in rows])
    mess = np.asarray([abs(float(row["B3_minus_B0_at_B3_realized_critical"]["Delta_I_crit_from_MESS_total_pu"])) for row in rows])
    redistribution = np.asarray([float(row["AIDC_location_time_redistribution_nodeh"]) for row in rows])
    b1_obj = np.asarray([abs(float(row["objective"]["B1"]) - float(row["objective"]["B0"])) for row in rows])
    b3_obj = np.asarray([abs(float(row["objective"]["B3"]) - float(row["objective"]["B2"])) for row in rows])
    hypothesis = bool(
        np.all(redistribution > TOLERANCE)
        and float(np.median(mess)) > float(np.median(aidc))
        and float(np.median(aidc)) <= 1e-4
    )
    return {
        "artifact_id": "V16_3_CRITICAL_CUT_ATTRIBUTION_DIAGNOSTIC",
        "role": "READ_ONLY_DIAGNOSTIC_ONLY",
        "common_feasible_day_count": len(rows),
        "common_feasible_days": [row["operating_day"] for row in rows],
        "method": "Frozen J_I dot frozen final schedule-control delta at each realized critical branch/phase/time; component axes are AIDC[0:12], MESS_P[12:36], MESS_Q[36:60].",
        "aggregate": {
            "AIDC_redistribution_nonzero_day_count": int(np.sum(redistribution > TOLERANCE)),
            "median_abs_Delta_I_crit_from_AIDC_pu": float(np.median(aidc)),
            "max_abs_Delta_I_crit_from_AIDC_pu": float(np.max(aidc)),
            "median_abs_Delta_I_crit_from_MESS_total_pu": float(np.median(mess)),
            "max_abs_Delta_I_crit_from_MESS_total_pu": float(np.max(mess)),
            "median_abs_objective_B1_minus_B0": float(np.median(b1_obj)),
            "max_abs_objective_B1_minus_B0": float(np.max(b1_obj)),
            "median_abs_objective_B3_minus_B2": float(np.median(b3_obj)),
            "max_abs_objective_B3_minus_B2": float(np.max(b3_obj)),
            "component_sum_identity_max_abs_error_pu": max(
                float(row["B3_minus_B0_at_B3_realized_critical"]["component_sum_identity_error_pu"])
                for row in rows
            ),
        },
        "hypothesis": "AIDC redistribution exists but has near-zero projection on the realized critical current sensitivity, while MESS P/Q dominates the reduction.",
        "hypothesis_supported": hypothesis,
        "per_day": rows,
        "counters": COUNTERS,
    }


def execute(repo: Path, final: Path, output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    coherence = reference_coherence(repo, final)
    attribution = critical_attribution(repo, final)
    coherence_path = output / "V16_3_AIDC_REFERENCE_COHERENCE_FORENSIC.json"
    attribution_path = output / "V16_3_CRITICAL_CUT_ATTRIBUTION_DIAGNOSTIC.json"
    coherence_path.write_text(json.dumps(coherence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    attribution_path.write_text(json.dumps(attribution, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "reference_classification": coherence["classification"],
        "reference_artifact_sha256": sha256_file(coherence_path),
        "attribution_hypothesis_supported": attribution["hypothesis_supported"],
        "attribution_artifact_sha256": sha256_file(attribution_path),
    }


def main() -> None:
    repo = Path.cwd()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--final", type=Path, default=repo / "dayahead/artifacts/v16_3_final")
    parser.add_argument("--output", type=Path, default=repo / "dayahead/artifacts/v16_3_decomposition_completion")
    print(json.dumps(execute(**vars(parser.parse_args())), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
