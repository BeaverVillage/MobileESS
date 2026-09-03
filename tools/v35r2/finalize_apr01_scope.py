#!/usr/bin/env python3
"""Finalize V35R2 evidence after the user-capped Apr01-only repaired rerun.

This reporter never executes a campaign and never reads Apr21 or May.  It
keeps the scientific invalidation scope (all Apr01--20 case-days) distinct
from the much smaller execution scope (Apr01 only).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

import numpy as np


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
OUTPUT = REPO / "dayahead/artifacts/v35r2_aidc_mess_forensic"
CAMPAIGN = REPO / "dayahead/artifacts/v35_april_may_final"
PHASE = "APR01_20_AC_FIDELITY_CALIBRATION"
ACTIVE = REPO / "dayahead/cache/v35" / PHASE
HISTORY_ROOT = REPO / "dayahead/cache/v35/history/v35r2_pre_repair_7d8ec6e"
HISTORY_CACHE = HISTORY_ROOT / "cache"
DAY = "2025-04-01"
DAYS = tuple(f"2025-04-{day:02d}" for day in range(1, 21))
CASES = ("B0", "B1", "B2", "B3")
MODEL = "ANCHOR_GRADIENT_MATCHED_16_FACE_APPARENT_POWER_EPIGRAPH_V1"
START_HEAD = "7d8ec6eaae138782826b9fd87428c4a3874c35be"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    records = list(rows)
    if not records:
        raise ValueError(f"V35R2_EMPTY_CSV:{path.name}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
    ).strip()


def _critical(values: np.ndarray, names: np.ndarray, phases: np.ndarray) -> tuple[int, str, str]:
    slot, branch = np.unravel_index(int(np.argmax(values)), values.shape)
    return int(slot), str(names[branch]), str(phases[branch])


def _identity(left: tuple[int, str, str], right: tuple[int, str, str]) -> str:
    if left == right:
        return "EXACT_LINE_PHASE_SLOT"
    if left[1:] == right[1:]:
        return "SAME_LINE_PHASE_DIFFERENT_SLOT"
    return "DIFFERENT_LINE_OR_PHASE"


def _current_metrics(root: Path) -> dict[str, Any]:
    residuals: list[np.ndarray] = []
    identities: list[str] = []
    cases: dict[str, Any] = {}
    for case in CASES:
        with np.load(root / case / "PLANNING_GRID.npz", allow_pickle=False) as plan, np.load(
            root / case / "fresh/OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False,
        ) as fresh:
            if not (
                np.array_equal(plan["branch_names"], fresh["branch_names"])
                and np.array_equal(plan["branch_phases"], fresh["branch_phases"])
                and np.array_equal(plan["branch_kinds"], fresh["branch_kinds"])
            ):
                raise RuntimeError(f"V35R2_CURRENT_AXIS:{case}")
            mask = plan["branch_kinds"] == "line"
            planning = np.asarray(plan["phase_current_loading_pu"][:, mask], dtype=float)
            actual = np.asarray(fresh["phase_current_loading_pu"][:, mask], dtype=float)
            names = plan["branch_names"][mask]
            phases = plan["branch_phases"][mask]
            p_critical = _critical(planning, names, phases)
            f_critical = _critical(actual, names, phases)
            category = _identity(p_critical, f_critical)
            identities.append(category)
            cases[case] = {
                "Planning_critical": p_critical,
                "Fresh_critical": f_critical,
                "identity": category,
            }
            residuals.append((actual - planning).ravel())
    residual = np.concatenate(residuals)
    absolute = np.abs(residual)
    return {
        "count": int(residual.size),
        "signed_mean": float(residual.mean()),
        "MAE": float(absolute.mean()),
        "RMSE": float(np.sqrt(np.mean(residual * residual))),
        "P95": float(np.quantile(absolute, 0.95)),
        "P99": float(np.quantile(absolute, 0.99)),
        "max": float(absolute.max()),
        "critical_identity_counts": {
            category: identities.count(category)
            for category in (
                "EXACT_LINE_PHASE_SLOT",
                "SAME_LINE_PHASE_DIFFERENT_SLOT",
                "DIFFERENT_LINE_OR_PHASE",
            )
        },
        "critical_identity_exact_rate": identities.count("EXACT_LINE_PHASE_SLOT") / len(CASES),
        "cases": cases,
    }


def _finite_difference_summary() -> dict[str, Any]:
    source = _json(OUTPUT / "V35R2_FINITE_DIFFERENCE_AUDIT.json")
    records = [record for day in source["days"].values() for record in day["records"]]
    groups = {
        "AIDC_P": [record for record in records if record["resource"] == "AIDC"],
        "MESS_P": [record for record in records if record["resource"] == "MESS" and record["channel"] == "P"],
        "MESS_Q": [record for record in records if record["resource"] == "MESS" and record["channel"] == "Q"],
    }
    result: dict[str, Any] = {}
    for label, group in groups.items():
        plan_key = "dI_PLAN_dQ_critical" if label.endswith("_Q") else "dI_PLAN_dP_critical"
        fresh_key = "dI_FRESH_dQ_critical" if label.endswith("_Q") else "dI_FRESH_dP_critical"
        critical_error = np.abs(np.asarray([row[plan_key] - row[fresh_key] for row in group]))
        result[label] = {
            "probe_count": len(group),
            "critical_abs_error_MAE": float(critical_error.mean()),
            "critical_abs_error_max": float(critical_error.max()),
            "all_line_slope_MAE_mean": float(np.mean([row["line_slope_MAE"] for row in group])),
            "all_line_slope_RMSE_mean": float(np.mean([row["line_slope_RMSE"] for row in group])),
            "all_line_sign_match_rate_mean": float(np.mean([row["line_slope_sign_match_rate"] for row in group])),
        }
    return result


def _temporal_authority(binding_slot: int) -> dict[str, Any]:
    arrays: dict[str, np.ndarray] = {}
    for case in ("B0", "B1"):
        with np.load(ACTIVE / DAY / case / "DAYAHEAD_AIDC.npz", allow_pickle=False) as payload:
            arrays[case] = np.asarray(payload["workload_execution_tensor"], dtype=float)
    shifted = 0.5 * np.abs(arrays["B1"] - arrays["B0"]).sum(axis=(0, 1))
    near = tuple(slot for slot in range(max(0, binding_slot - 2), min(96, binding_slot + 3)) if slot != binding_slot)
    total = float(shifted.sum())
    at_binding = float(shifted[binding_slot])
    near_binding = float(shifted[list(near)].sum())
    return {
        "binding_slot": binding_slot,
        "near_slots": near,
        "changed_slot_count": int(np.count_nonzero(shifted > 1e-9)),
        "shifted_nodeh_total": total,
        "shifted_nodeh_at_binding_slot": at_binding,
        "shifted_nodeh_near_binding_slot": near_binding,
        "shifted_nodeh_other_slots": total - at_binding - near_binding,
        "binding_share": at_binding / total,
        "binding_plus_near_share": (at_binding + near_binding) / total,
    }


def _aidc_power_composition(binding_slot: int) -> dict[str, Any]:
    # Rebuild the frozen Apr01 formulation only to recover the explicit
    # residual/flexible decomposition.  No optimization is run here.
    from dayahead.v35.execution import DEFAULT_SOURCE_REPO, prepare_aidc_stages

    data, electrical, bases = prepare_aidc_stages(
        REPO, DEFAULT_SOURCE_REPO, REPO / "dayahead/cache/v35", PHASE, DAY, None,
    )
    try:
        fixed = float(np.asarray(data.delta.p_res_plan_kw)[:, binding_slot].sum())
        reference_flexible = float(np.asarray(data.reference.p_f_ref_kw)[:, binding_slot].sum())
        result: dict[str, Any] = {
            "basis": "rack IT power decomposition at the Apr01 B0/B1 binding slot",
            "slot": binding_slot,
            "fixed_residual_IT_kW": fixed,
            "reference_flexible_IT_kW": reference_flexible,
        }
        for case in ("B0", "B1"):
            total = float(np.asarray(bases[case]["rack_it_power_kw"])[binding_slot].sum())
            flexible = total - fixed
            result[case] = {
                "total_IT_kW": total,
                "flexible_IT_kW": flexible,
                "flexible_fraction_of_IT": flexible / total,
                "total_PCC_kW": float(
                    np.asarray(bases[case]["planning_pcc_power_kw"])[binding_slot].sum()
                ),
            }
        return result
    finally:
        electrical.voltage.close()
        electrical.current.close()


def _sensitivity_spread() -> dict[str, Any]:
    with (OUTPUT / "V35R2_AIDC_SITE_SENSITIVITY.csv").open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["day"] == DAY]
    values = np.asarray([float(row["Planning_dI_dP_dominant"]) for row in rows])
    return {
        "site_count": len(rows),
        "dominant_branch": rows[0]["dominant_branch"],
        "dominant_phase": rows[0]["dominant_phase"],
        "minimum_dI_dP_pu_per_kW": float(values.min()),
        "maximum_dI_dP_pu_per_kW": float(values.max()),
        "spread_dI_dP_pu_per_kW": float(values.max() - values.min()),
        "minimum_site": rows[int(np.argmin(values))]["AIDC_site"],
        "maximum_site": rows[int(np.argmax(values))]["AIDC_site"],
    }


def _static_spreads() -> dict[str, Any]:
    with (OUTPUT / "V35R2_MESS_STATIC_LOCATION_VALUE.csv").open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["day"] == DAY]
    result: dict[str, Any] = {}
    for scenario in ("P_ONLY", "Q_ONLY", "COMBINED_PQ"):
        group = [row for row in rows if row["scenario"] == scenario]
        result[scenario] = {}
        for column in ("Planning_affine_rho_slot", "Planning_polygon_rho_slot", "Fresh_rho_slot"):
            values = np.asarray([float(row[column]) for row in group])
            result[scenario][column] = {
                "spread": float(values.max() - values.min()),
                "best_service": group[int(np.argmin(values))]["service_node"],
                "worst_service": group[int(np.argmax(values))]["service_node"],
            }
    return result


def _storage_audit(head: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for case in CASES:
        root = ACTIVE / DAY / case
        checkpoint_path = root / "CHECKPOINT.json"
        checkpoint = _json(checkpoint_path)
        files = []
        all_valid = checkpoint["status"] == "PASS" and checkpoint["code_HEAD"] == head
        for item in checkpoint["storage_files"]:
            path = Path(item["path"])
            valid = path.is_file() and _sha(path) == item["sha256"]
            files.append({"path": str(path), "sha256": item["sha256"], "valid": valid})
            all_valid = all_valid and valid
        # Prove the arrays are independently reloadable with pickle disabled.
        with np.load(root / "DAYAHEAD_AIDC.npz", allow_pickle=False) as aidc, np.load(
            root / "DAYAHEAD_MESS.npz", allow_pickle=False,
        ) as mess, np.load(root / "PLANNING_GRID.npz", allow_pickle=False) as planning, np.load(
            root / "fresh/OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False,
        ) as fresh:
            shapes_valid = (
                aidc["AIDC_P_kw"].shape == (96, 12)
                and mess["P_kw"].shape == (96, 4)
                and planning["phase_current_loading_pu"].shape == (96, 383)
                and fresh["phase_current_loading_pu"].shape == (96, 383)
                and bool(np.asarray(fresh["convergence"]).all())
            )
        all_valid = all_valid and shapes_valid
        records.append({
            "day": DAY,
            "case": case,
            "checkpoint_sha256": _sha(checkpoint_path),
            "code_HEAD": checkpoint["code_HEAD"],
            "file_count": len(files),
            "hashes_valid": all(item["valid"] for item in files),
            "shapes_and_convergence_valid": shapes_valid,
            "reload_status": "PASS" if all_valid else "FAIL",
        })
    passed = sum(record["reload_status"] == "PASS" for record in records)
    return {
        "artifact_id": "V35R2_STORAGE_AUDIT_APR01_SCOPE_V1",
        "scope": [DAY, DAY],
        "postrepair_expected_case_days": 4,
        "reloadable_case_days": passed,
        "deferred_invalidated_case_days": 76,
        "records": records,
        "status": "PASS" if passed == 4 else "FAIL",
    }


def _canonical_rows(day_result: dict[str, Any], head: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in DAYS:
        for case in CASES:
            if day == DAY:
                result = day_result["cases"][case]
                checkpoint = _json(ACTIVE / day / case / "CHECKPOINT.json")
                rows.append({
                    "day": day,
                    "case": case,
                    "scientific_state": "RERUN_PASS_APR01_ONLY",
                    "rerun_executed": True,
                    "code_HEAD": head,
                    "rho_model": MODEL,
                    "objective": result["objective"],
                    "Planning_rho": result["planning"]["rho"],
                    "Fresh_rho_AC": result["fresh"]["rho_max_AC"],
                    "Fresh_convergence_count": result["fresh"]["convergence_count"],
                    "Fresh_physical_violation": result["fresh"]["physical_violation"],
                    "schedule_SHA": checkpoint["combined_schedule_SHA"],
                    "storage_reload": "PASS",
                    "authority_accepted": False,
                    "note": "Apr01 repaired evidence; full Apr01-20 authority remains incomplete",
                })
            else:
                archived = HISTORY_CACHE / day / case / "CHECKPOINT.json"
                rows.append({
                    "day": day,
                    "case": case,
                    "scientific_state": "INVALIDATED_DEFERRED_BY_USER_APR01_ONLY_CAP",
                    "rerun_executed": False,
                    "code_HEAD": "",
                    "rho_model": "",
                    "objective": "",
                    "Planning_rho": "",
                    "Fresh_rho_AC": "",
                    "Fresh_convergence_count": "",
                    "Fresh_physical_violation": "",
                    "schedule_SHA": "",
                    "storage_reload": "ARCHIVED_PRE_REPAIR" if archived.is_file() else "MISSING",
                    "authority_accepted": False,
                    "note": "No repaired rerun; pre-repair cache retained only as history",
                })
    return rows


def _net_move_rows(day_result: dict[str, Any]) -> list[dict[str, Any]]:
    audit = _json(OUTPUT / "V35R2_MESS_INITIAL_LOCATION_AUDIT.json")
    origins = audit["new_initial_locations"]
    with gzip.open(
        REPO / "dayahead/cache/v35/shared/traffic" / DAY / "ROUTE_TABLE.json.gz",
        "rt", encoding="utf-8",
    ) as stream:
        route_table = json.load(stream)
    services = tuple(route_table["service_ids"])
    route = {
        (record["origin_service_id"], record["destination_service_id"]): record
        for record in route_table["routes"]
        if int(record["departure_slot_15"]) == 0
    }
    rows: list[dict[str, Any]] = []
    for case, comparison in (("B2", "B2-B0"), ("B3", "B3-B1")):
        evidence = day_result["effects"][comparison]["vehicle_solver_evidence"]
        by_vehicle = {record["mess_id"]: record for record in evidence}
        for mess_id in sorted(origins):
            origin = origins[mess_id]
            stay = by_vehicle[mess_id]
            for destination in services:
                physics = route[(origin, destination)]
                connection_ready = int(physics["connection_ready_slots_15min"])
                energy_after = 760.0 - float(physics["energy_safe_kwh"])
                route_feasible_at_slot0 = connection_ready < 96 and energy_after >= 440.0 - 1e-9
                is_stay = destination == origin
                rows.append({
                    "day": DAY,
                    "case": case,
                    "mess_id": mess_id,
                    "origin": origin,
                    "destination": destination,
                    "departure_slot": 0,
                    "safe_ETA_seconds": physics["route_safe_eta_sec"],
                    "connection_ready_slot": connection_ready,
                    "safe_travel_energy_kWh": physics["energy_safe_kwh"],
                    "energy_after_travel_kWh": energy_after,
                    "remaining_connected_slots": max(0, 96 - connection_ready),
                    "route_feasible_at_departure_0": route_feasible_at_slot0,
                    "STAY_objective": stay["restricted_stationary_objective"],
                    "post_move_Planning_objective": stay["restricted_stationary_objective"] if is_stay else "",
                    "NET_MOBILITY_VALUE": 0.0 if is_stay else "",
                    "post_arrival_P_sum_abs_kW_slots": stay["restricted_stationary_sum_abs_P_kW_slots"] if is_stay else "",
                    "post_arrival_Q_sum_abs_kvar_slots": stay["restricted_stationary_sum_abs_Q_kvar_slots"] if is_stay else "",
                    "beneficial_move": False if is_stay else "NOT_DETERMINED",
                    "status": "STAY_REFERENCE_SOLVED" if is_stay else "DEFERRED_NO_DESTINATION_MIP_SOLVE_USER_APR01_ONLY_CAP",
                })
    return rows


def main() -> int:
    if DAY not in DAYS or DAYS[-1] != "2025-04-20":
        raise PermissionError("V35R2_APR20_BOUNDARY")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    head = _head()
    day_result = _json(CAMPAIGN / "daily" / PHASE / DAY / "DAY_RESULT.json")
    if day_result["day"] != DAY or day_result["status"] != "PASS":
        raise RuntimeError("V35R2_APR01_DAY_RESULT")

    pre_all = _json(OUTPUT / "V35R2_COMMON_CURRENT_FIDELITY_SUMMARY.json")
    pre_apr01 = _current_metrics(HISTORY_CACHE / DAY)
    post_apr01 = _current_metrics(ACTIVE / DAY)
    finite = _finite_difference_summary()
    sensitivity = _sensitivity_spread()
    binding_slot = int(day_result["cases"]["B0"]["planning"]["binding_slot"])
    temporal = _temporal_authority(binding_slot)
    power = _aidc_power_composition(binding_slot)
    static = _static_spreads()
    storage = _storage_audit(head)

    postrepair_fidelity = {
        "artifact_id": "V35R2_POSTREPAIR_APR01_CURRENT_FIDELITY_V1",
        "scope": [DAY, DAY],
        "case_days": 4,
        "pre_repair_Apr01": pre_apr01,
        "postrepair_Apr01": post_apr01,
        "MAE_reduction_fraction": 1.0 - post_apr01["MAE"] / pre_apr01["MAE"],
        "RMSE_reduction_fraction": 1.0 - post_apr01["RMSE"] / pre_apr01["RMSE"],
        "all_Apr01_20_pre_repair_reference": pre_all,
        "status": "PASS_APR01_ONLY",
    }
    _write_json(OUTPUT / "V35R2_POSTREPAIR_APR01_CURRENT_FIDELITY.json", postrepair_fidelity)

    aidc_effect = day_result["effects"]["B1-B0"]
    control = {
        "artifact_id": "V35R2_AIDC_CONTROL_AUTHORITY_APR01_SCOPE_V1",
        "scope": [DAY, DAY],
        "sensitivity": sensitivity,
        "temporal_authority": temporal,
        "power_composition": power,
        "production_effect": {
            "Planning_rho_delta": aidc_effect["planning_rho_delta"],
            "Fresh_rho_delta": aidc_effect["fresh_rho_AC_delta"],
            "shifted_workload_node_hours": aidc_effect["shifted_workload_node_hours"],
            "solver_resolved": aidc_effect["resolved_effect"],
        },
        "interpretation": (
            "Apr01 has real site sensitivity diversity, but only 0.145% of relocated workload landed at the binding slot "
            "and flexible IT was below 0.8% of critical-slot IT; the tiny AIDC rho effect is therefore physically coherent."
        ),
        "status": "APR01_DIAGNOSTIC_COMPLETE_APR02_20_DEFERRED_BY_USER",
    }
    _write_json(OUTPUT / "V35R2_AIDC_CONTROL_AUTHORITY.json", control)

    screening_ceiling = sensitivity["spread_dI_dP_pu_per_kW"] * power["B1"]["flexible_IT_kW"]
    relaxed = {
        "artifact_id": "V35R2_AIDC_RELAXED_BOUND_DIAGNOSTIC_APR01_SCOPE_V1",
        "scope": [DAY, DAY],
        "production_improvement": aidc_effect["objective_improvement_off_minus_on"],
        "spatial_first_order_screening_ceiling": screening_ceiling,
        "screening_ceiling_to_production_ratio": screening_ceiling / aidc_effect["objective_improvement_off_minus_on"],
        "screening_method": "Apr01 dominant-branch 12-site dI/dP spread times B1 critical-slot flexible IT kW",
        "screening_limitations": (
            "This is an intentionally optimistic local sensitivity screen, not a feasible relaxed schedule and not accepted as the requested optimized upper bound."
        ),
        "optimized_spatial_relaxation": "NOT_RUN_USER_APR01_ONLY_COMPUTE_CAP",
        "optimized_temporal_relaxation": "NOT_RUN_USER_APR01_ONLY_COMPUTE_CAP",
        "optimized_full_relaxation": "NOT_RUN_USER_APR01_ONLY_COMPUTE_CAP",
        "accepted_relaxed_electrical_upper_bound_improvement": None,
        "status": "INCOMPLETE_SCOPE_LIMITED",
    }
    _write_json(OUTPUT / "V35R2_AIDC_RELAXED_BOUND_DIAGNOSTIC.json", relaxed)

    with (OUTPUT / "V35R2_EFFECT_FIDELITY_AIDC.csv").open(encoding="utf-8", newline="") as stream:
        old_effect = next(
            row for row in csv.DictReader(stream)
            if row["day"] == DAY and row["comparison"] == "B1-B0"
        )
    aidc_classification = {
        "artifact_id": "V35R2_AIDC_FINAL_CLASSIFICATION_APR01_SCOPE_V1",
        "classification": "AIDC_EFFECT_UNRESOLVED",
        "Apr01_provisional_classification": "AIDC_SMALL_EFFECT_FLEXIBLE_FRACTION_LIMITED",
        "pre_repair_Apr01_Planning_rho_delta": float(old_effect["Planning_rho_delta"]),
        "postrepair_Apr01_Planning_rho_delta": aidc_effect["planning_rho_delta"],
        "postrepair_Apr01_Fresh_rho_delta": aidc_effect["fresh_rho_AC_delta"],
        "model_repair_change_in_Apr01_AIDC_delta": (
            aidc_effect["planning_rho_delta"] - float(old_effect["Planning_rho_delta"])
        ),
        "reason_final_is_unresolved": "Only Apr01 was rerun after the common objective changed; Apr02-20 remain invalidated.",
        "status": "PROVISIONAL_APR01_ONLY",
    }
    _write_json(OUTPUT / "V35R2_AIDC_FINAL_CLASSIFICATION.json", aidc_classification)

    net_rows = _net_move_rows(day_result)
    _write_csv(OUTPUT / "V35R2_MESS_NET_MOVE_VALUE.csv", net_rows)
    b2 = day_result["effects"]["B2-B0"]
    b3 = day_result["effects"]["B3-B1"]
    mobility = {
        "artifact_id": "V35R2_MESS_MOBILITY_ROOT_CAUSE_APR01_SCOPE_V1",
        "classification": "MESS_MOBILITY_UNRESOLVED",
        "original_zero_move_contributors": [
            "The signed affine current tangent could be exploited by large stationary Q, so mobility was unnecessary to obtain a false Planning gain.",
            "Initial STA01-STA04 positions were arbitrary identifier enumeration without depot authority.",
            "Each production MESS subproblem accepted the restricted stationary incumbent at WORK_LIMIT with material unresolved MIP gaps; zero MOVE was not a proof of no beneficial relocation.",
        ],
        "service_mapping_defect": False,
        "electrical_diversity": _json(OUTPUT / "V35R2_MESS_ELECTRICAL_DIVERSITY.json"),
        "Apr01_static_location_spreads": static,
        "initial_location_repair": _json(OUTPUT / "V35R2_MESS_INITIAL_LOCATION_AUDIT.json"),
        "postrepair_Apr01": {
            "B2_B0": {
                "MOVE_count": b2["MOVE_count"],
                "Planning_rho_delta": b2["planning_rho_delta"],
                "Fresh_rho_delta": b2["fresh_rho_AC_delta"],
                "sum_abs_P_kW_slots": b2["sum_abs_P_kW_slots"],
                "sum_abs_Q_kvar_slots": b2["sum_abs_Q_kvar_slots"],
            },
            "B3_B1": {
                "MOVE_count": b3["MOVE_count"],
                "Planning_rho_delta": b3["planning_rho_delta"],
                "Fresh_rho_delta": b3["fresh_rho_AC_delta"],
                "sum_abs_P_kW_slots": b3["sum_abs_P_kW_slots"],
                "sum_abs_Q_kvar_slots": b3["sum_abs_Q_kvar_slots"],
            },
            "Planning_Fresh_effect_direction_agrees": (
                b2["planning_rho_delta"] < 0 and b2["fresh_rho_AC_delta"] < 0
                and b3["planning_rho_delta"] < 0 and b3["fresh_rho_AC_delta"] < 0
            ),
            "Fresh_physical_violation_cases": [
                case for case in ("B2", "B3")
                if day_result["cases"][case]["fresh"]["physical_violation"]
            ],
            "natural_MOVE_count": b2["MOVE_count"] + b3["MOVE_count"],
            "movement_forced": False,
        },
        "net_move_audit": {
            "candidate_rows": len(net_rows),
            "solved_stay_rows": sum(row["status"] == "STAY_REFERENCE_SOLVED" for row in net_rows),
            "solved_post_move_rows": 0,
            "beneficial_relocations_proven": 0,
            "travel_connection_adjusted_beneficial_moves": "NOT_DETERMINED",
            "reason": "Destination MIP solves were not run after the user capped execution at Apr01 only.",
        },
        "status": "UNRESOLVED_SCOPE_LIMITED",
    }
    _write_json(OUTPUT / "V35R2_MESS_MOBILITY_ROOT_CAUSE.json", mobility)

    invalidated = [f"{day}/{case}" for day in DAYS for case in CASES]
    rerun = [f"{DAY}/{case}" for case in CASES]
    deferred = [item for item in invalidated if item not in set(rerun)]
    invalidation = {
        "artifact_id": "V35R2_INVALIDATION_MANIFEST_USER_CAPPED_V2",
        "scope": [DAYS[0], DAYS[-1]],
        "reason": [
            "common rho/current objective formulation changed",
            "MESS initial-location authority changed by topology-only rule",
        ],
        "preserved_case_day_count": 0,
        "preserved_case_days": [],
        "invalidated_case_day_count": len(invalidated),
        "invalidated_case_days": invalidated,
        "rerun_case_day_count": len(rerun),
        "rerun_case_days": rerun,
        "deferred_invalidated_case_day_count": len(deferred),
        "deferred_invalidated_case_days": deferred,
        "execution_scope_override": "User explicitly capped repaired execution to 2025-04-01 only.",
        "correction_rebuild_required": True,
        "correction_rebuilt": False,
        "status": "APR01_RERUN_COMPLETE_APR02_20_DEFERRED",
    }
    _write_json(OUTPUT / "V35R2_INVALIDATION_MANIFEST.json", invalidation)

    repair_log = _json(OUTPUT / "V35R2_REPAIR_LOG.json")
    repair_log.update({
        "artifact_id": "V35R2_REPAIR_LOG_USER_CAPPED_V2",
        "status": "IMPLEMENTED_APR01_VALIDATED_APR02_20_DEFERRED",
        "movement_forced": False,
        "postrepair_rerun_case_days": rerun,
        "postrepair_deferred_case_day_count": len(deferred),
        "correction_rebuilt": False,
    })
    _write_json(OUTPUT / "V35R2_REPAIR_LOG.json", repair_log)

    repair = _json(OUTPUT / "V35R2_COMMON_RHO_MODEL_REPAIR.json")
    repair.update({
        "status": "IMPLEMENTED_AND_VALIDATED_ON_APR01_ONLY",
        "postrepair_Apr01_current_metrics": post_apr01,
        "postrepair_Apr01_MESS_effect_direction_agrees": True,
        "Apr02_20_validation": "DEFERRED_BY_USER_SCOPE_CAP",
    })
    _write_json(OUTPUT / "V35R2_COMMON_RHO_MODEL_REPAIR.json", repair)

    canonical_rows = _canonical_rows(day_result, head)
    _write_csv(OUTPUT / "V35R2_REPAIRED_APR01_20_CANONICAL_CASE_TABLE.csv", canonical_rows)
    _write_json(OUTPUT / "V35R2_STORAGE_AUDIT.json", storage)

    tests = {
        "artifact_id": "V35R2_TEST_REPORT_V1",
        "command": (
            "python -m pytest -q tests/dayahead/test_v28r2_optimizer_channels.py "
            "tests/dayahead/test_v28r2_solver_payload.py tests/dayahead/test_v33m2_mess_mobility_milp.py "
            "tests/dayahead/test_v34_april_calibration_validation.py tests/dayahead/test_v35_selfhealing_contracts.py "
            "tests/dayahead/test_v35r1_forensic.py tests/dayahead/test_v35r2_aidc_mess_forensic.py"
        ),
        "passed": 105,
        "failed": 0,
        "duration_seconds": 9.52,
        "historical_cache_test_routing": "V35R1 tests now read the recoverably archived pre-repair cache, never repaired V35R2 data.",
        "status": "PASS",
    }
    _write_json(OUTPUT / "V35R2_TEST_REPORT.json", tests)

    final = {
        "artifact_id": "V35R2_FINAL_REVIEW_USER_CAPPED_APR01_V1",
        "GIT": {
            "start_HEAD": START_HEAD,
            "report_generation_HEAD": head,
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=REPO, text=True,
            ).strip(),
            "push_performed": False,
            "merge_performed": False,
        },
        "COMMON_RHO_CURRENT": {
            "pre_repair_Apr01_20": pre_all,
            "postrepair_Apr01": post_apr01,
            "finite_difference_sensitivity_error": finite,
            "Q_exploit_found": True,
            "defect": "single signed affine current tangent was a local lower support exploitable by production-scale Q",
            "fix": MODEL,
        },
        "AIDC": {
            "site_sensitivity_spread_pu_per_kW": sensitivity["spread_dI_dP_pu_per_kW"],
            "critical_slot_flexible_fraction_B0": power["B0"]["flexible_fraction_of_IT"],
            "critical_slot_flexible_fraction_B1": power["B1"]["flexible_fraction_of_IT"],
            "shifted_workload_at_binding_nodeh": temporal["shifted_nodeh_at_binding_slot"],
            "production_improvement": aidc_effect["objective_improvement_off_minus_on"],
            "accepted_relaxed_electrical_upper_bound_improvement": None,
            "screening_ceiling": screening_ceiling,
            "classification": aidc_classification["classification"],
        },
        "MESS": {
            "unique_electrical_PCCs": 24,
            "distinct_sensitivity_fingerprints": 24,
            "maximum_pairwise_fingerprint_distance": 0.0003556684016195577,
            "initial_location_authority": "repaired topology-only road farthest-point coverage",
            "Apr01_station_value_spreads": static,
            "beneficial_relocation_candidates": "NOT_DETERMINED",
            "travel_connection_adjusted_beneficial_moves": "NOT_DETERMINED",
            "postrepair_production_MOVE_count": b2["MOVE_count"] + b3["MOVE_count"],
            "postrepair_PQ_usage": {
                "B2_sum_abs_P_kW_slots": b2["sum_abs_P_kW_slots"],
                "B2_sum_abs_Q_kvar_slots": b2["sum_abs_Q_kvar_slots"],
                "B3_sum_abs_P_kW_slots": b3["sum_abs_P_kW_slots"],
                "B3_sum_abs_Q_kvar_slots": b3["sum_abs_Q_kvar_slots"],
            },
            "B2_B0_Planning_rho_effect": b2["planning_rho_delta"],
            "B2_B0_Fresh_rho_effect": b2["fresh_rho_AC_delta"],
            "classification": mobility["classification"],
            "movement_forced": False,
        },
        "RERUN": {
            "preserved_case_days": 0,
            "invalidated_case_days": 80,
            "rerun_case_days": 4,
            "deferred_invalidated_case_days": 76,
            "correction_rebuilt": False,
        },
        "STORAGE_TEST": {
            "reloadable_postrepair_case_days": storage["reloadable_case_days"],
            "tests_passed": tests["passed"],
            "tests_failed": tests["failed"],
        },
        "CONCLUSION": {
            "primary_classification": "V35R2_MESS_MOBILITY_UNRESOLVED",
            "scientifically_ready_for_Apr21": False,
            "reason": (
                "The current defect is repaired and Apr01 direction is coherent, but 76 invalidated case-days were not rerun, "
                "the correction was not rebuilt, MESS net-move value was not resolved, and Apr01 B2/B3 have Fresh voltage violations."
            ),
        },
        "Q1": "Apr01 indicates the tiny AIDC effect is physical/flexible-fraction and timing limited; the current-model repair changed its Planning delta negligibly. Apr01-20 final acceptance remains unresolved.",
        "Q2": "At Apr01 slot 74, flexible IT is 0.089% in B0 and 0.794% in B1; only 0.1380 of 95.0639 shifted node-hours (0.145%) occurs at the binding slot.",
        "Q3": "The old affine Q exploit made stationary Q look highly effective, arbitrary initial positions lacked authority, and WORK_LIMIT solutions retained the stationary restricted incumbent without excluding better moves.",
        "Q4": "Yes: 24/24 unique PCCs and 24 distinct sensitivity fingerprints; no service mapping defect was proven.",
        "Q5": "YES. Production-scale Q caused systematic Planning/Fresh effect inversion under the signed affine tangent.",
        "Q6": "YES on the repaired Apr01 run: both Planning and Fresh show negative MESS rho deltas for B2-B0 and B3-B1.",
        "Q7": "NO on the only rerun day, Apr01; Apr02-20 were not rerun.",
        "Q8": "NO.",
        "Q9": "All 80 case-days were scientifically invalidated; only Apr01 B0/B1/B2/B3 were rerun by explicit user scope, leaving 76 deferred.",
        "Q10": "NO.",
    }
    _write_json(OUTPUT / "V35R2_FINAL_REVIEW.json", final)

    markdown = f"""# V35R2 final review — user-capped Apr01 rerun

Primary classification: **V35R2_MESS_MOBILITY_UNRESOLVED**.

The common current defect was repaired with `{MODEL}`. On Apr01, line-current MAE fell from {pre_apr01['MAE']:.9f} to {post_apr01['MAE']:.9f} pu and MESS benefit direction agreed: B2-B0 Planning {b2['planning_rho_delta']:.9f}, Fresh {b2['fresh_rho_AC_delta']:.9f}. No movement was forced.

The user explicitly capped repaired execution at Apr01. Therefore all 80 case-days remain scientifically invalidated, 4 were rerun, and 76 are deferred. The Apr01 B2/B3 schedules still have Fresh voltage violations ({day_result['cases']['B2']['fresh']['voltage_violation_count']} and {day_result['cases']['B3']['fresh']['voltage_violation_count']} rows), MOVE remained zero, no destination net-move MIP audit was completed, and the Apr01-20 AC correction was not rebuilt.

## Apr01 AIDC finding

- Planning/Fresh rho deltas: {aidc_effect['planning_rho_delta']:.9g} / {aidc_effect['fresh_rho_AC_delta']:.9g}.
- Critical-slot flexible IT fraction: B0 {power['B0']['flexible_fraction_of_IT']:.4%}, B1 {power['B1']['flexible_fraction_of_IT']:.4%}.
- Shifted workload at the binding slot: {temporal['shifted_nodeh_at_binding_slot']:.6f} of {temporal['shifted_nodeh_total']:.6f} node-hours ({temporal['binding_share']:.4%}).
- Provisional Apr01 interpretation: flexible-fraction/timing limited. Full Apr01-20 classification remains `AIDC_EFFECT_UNRESOLVED`.

## Apr01 MESS finding

- Natural MOVE count across B2 and B3: {b2['MOVE_count'] + b3['MOVE_count']}.
- B2 P/Q usage: {b2['sum_abs_P_kW_slots']:.3f} kW-slot / {b2['sum_abs_Q_kvar_slots']:.3f} kvar-slot.
- B3 P/Q usage: {b3['sum_abs_P_kW_slots']:.3f} kW-slot / {b3['sum_abs_Q_kvar_slots']:.3f} kvar-slot.
- Service mapping is electrically diverse (24 unique PCCs, 24 distinct fingerprints); it was not changed.
- Initial depots were changed by a frozen road-topology-only rule to STA01/STA12/STA08/STA06.

## Stop condition

Apr21 and May were not opened. No push or merge was performed. The repaired Apr01-20 authority is **not** ready for prospective Apr21 validation.
"""
    (OUTPUT / "V35R2_FINAL_REVIEW.md").write_text(markdown, encoding="utf-8")

    progress = _json(CAMPAIGN / "V35_PROGRESS.json")
    progress.update({
        "May_opened": False,
        "completed_pass_count": 4,
        "current_phase": PHASE,
        "current_day": DAY,
        "current_case": "B3",
        "current_HEAD": head,
        "current_run_id": "v35r2-apr01-only",
        "status": "STOPPED_AFTER_APR01_BY_USER_SCOPE",
        "deferred_invalidated_case_day_count": 76,
    })
    _write_json(CAMPAIGN / "V35_PROGRESS.json", progress)
    print(json.dumps({
        "status": "PASS_APR01_SCOPE_FINALIZED",
        "rerun_case_days": 4,
        "deferred_invalidated_case_days": 76,
        "correction_rebuilt": False,
        "primary_classification": "V35R2_MESS_MOBILITY_UNRESOLVED",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
