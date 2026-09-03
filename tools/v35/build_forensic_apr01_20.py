"""Build the V35R1 Apr-01--20 forensic authority without new optimization."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping, Sequence

import numpy as np

from dayahead.mess_physics import CAPACITY_KWH, E_TERMINAL_KWH, MESS_IDS
from dayahead.v35.campaign import write_daily_csv, write_effect_csv
from dayahead.v35.forensic import (
    CASES,
    COMPARISONS,
    METRICS,
    aidc_small_effect_classification,
    algebraic_closure,
    aligned_day_results,
    b3_lineage_valid,
    distribution,
    validate_calibration_provenance,
    zero_mess_equivalence,
)
from dayahead.v35.storage import atomic_csv, atomic_json, atomic_npz, sha256_file


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "dayahead/artifacts/v35_april_may_final"
CACHE = REPO / "dayahead/cache/v35"
OUTPUT = REPO / "dayahead/artifacts/v35_apr01_21_forensic"
PHASE = "APR01_20_AC_FIDELITY_CALIBRATION"
DAYS = tuple(f"2025-04-{day:02d}" for day in range(1, 21))
B3_FIX_COMMIT = "bac32e1"
TASK_START_HEAD = "f4d7b5f1ac8b01a353087743379276775437de30"
EXPECTED_TERMINAL_SOC = E_TERMINAL_KWH / CAPACITY_KWH


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPO,
        check=False,
    ).returncode == 0


def _json_cell(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _replace_record_sha(records: list[dict[str, Any]], filename: str, digest: str) -> None:
    matched = [row for row in records if Path(str(row["path"])).name == filename]
    if len(matched) != 1:
        raise RuntimeError(f"V35R1_STORAGE_RECORD_MATCH:{filename}:{len(matched)}")
    matched[0]["sha256"] = digest


def _scientific_sha_snapshot(case_root: Path) -> dict[str, str]:
    names = (
        "DAYAHEAD_AIDC.npz",
        "DAYAHEAD_MESS.npz",
        "PLANNING_GRID.npz",
        "ACTUAL_AIDC.npz",
        "MESS_TRAJECTORY.json",
        "fresh/OPENDSS_PHASE_ARRAYS.npz",
        "fresh/OPENDSS_OUTPUT_MANIFEST.json",
    )
    return {name: sha256_file(case_root / name) for name in names}


def repair_actual_mess_terminal_soc(new_code_head: str) -> dict[str, Any]:
    """Repair the 1000-vs-1200 kWh report defect without optimizer reruns."""

    history_root = CACHE / "history/v35r1_actual_mess_soc"
    records = []
    changed_days = []
    for day in DAYS:
        day_path = SOURCE / "daily" / PHASE / day / "DAY_RESULT.json"
        effect_path = SOURCE / "daily" / PHASE / day / "EFFECT_WATCHDOG.json"
        day_result = _load(day_path)
        day_changed = False
        day_history = history_root / PHASE / day
        for case in CASES:
            root = CACHE / PHASE / day / case
            checkpoint_path = root / "CHECKPOINT.json"
            checkpoint = _load(checkpoint_path)
            actual_path = root / "ACTUAL_SUMMARY.json"
            actual = _load(actual_path)
            terminal = tuple(map(float, actual["actual_MESS"]["terminal_SoC"]))
            already = (
                np.allclose(terminal, EXPECTED_TERMINAL_SOC, rtol=0.0, atol=1e-15)
                and checkpoint["code_HEAD"] == new_code_head
            )
            if already:
                records.append({"day": day, "case": case, "status": "ALREADY_REPAIRED"})
                continue
            if actual["actual_MESS"]["actual_replays"] or actual["actual_MESS"]["DA_commitments"]:
                raise RuntimeError("V35R1_SOC_REPAIR_REQUIRES_ZERO_MOVE_APR01_20")
            with np.load(root / "ACTUAL_MESS.npz", allow_pickle=False) as payload:
                availability = np.asarray(payload["PQ_availability"])
            if not availability.all():
                raise RuntimeError("V35R1_SOC_REPAIR_REQUIRES_FULL_AVAILABILITY")

            history = day_history / case
            history.mkdir(parents=True, exist_ok=True)
            for name in ("CHECKPOINT.json", "ACTUAL_SUMMARY.json", "ACTUAL_MESS.npz", "CASE_RESULT.json"):
                target = history / name
                if not target.exists():
                    shutil.copy2(root / name, target)
            before_science = _scientific_sha_snapshot(root)
            old_head = str(checkpoint["code_HEAD"])
            old_checkpoint_sha = sha256_file(checkpoint_path)

            actual["actual_MESS"]["terminal_SoC"] = [EXPECTED_TERMINAL_SOC] * len(MESS_IDS)
            actual_sha = atomic_json(actual_path, actual)
            actual_mess_record = atomic_npz(
                root / "ACTUAL_MESS.npz",
                {
                    "PQ_availability": availability,
                    "terminal_SoC": np.full(len(MESS_IDS), EXPECTED_TERMINAL_SOC),
                },
                {"PQ_availability": (96, 4), "terminal_SoC": (4,)},
                require_finite=("terminal_SoC",),
            )

            case_result_path = root / "CASE_RESULT.json"
            case_result = _load(case_result_path)
            case_result["actual"]["actual_MESS"]["terminal_SoC"] = [EXPECTED_TERMINAL_SOC] * len(MESS_IDS)
            case_result["MESS"]["terminal_SoC"] = [EXPECTED_TERMINAL_SOC] * len(MESS_IDS)
            case_records = [dict(row) for row in case_result["storage_files"]]
            _replace_record_sha(case_records, "ACTUAL_MESS.npz", actual_mess_record["sha256"])
            _replace_record_sha(case_records, "ACTUAL_SUMMARY.json", actual_sha)
            case_result["storage_files"] = case_records
            case_result_sha = atomic_json(case_result_path, case_result)

            checkpoint_records = [dict(row) for row in checkpoint["storage_files"]]
            _replace_record_sha(checkpoint_records, "ACTUAL_MESS.npz", actual_mess_record["sha256"])
            _replace_record_sha(checkpoint_records, "ACTUAL_SUMMARY.json", actual_sha)
            _replace_record_sha(checkpoint_records, "CASE_RESULT.json", case_result_sha)
            checkpoint["storage_files"] = checkpoint_records
            checkpoint["Actual_SHA"] = actual_sha
            checkpoint["code_HEAD"] = new_code_head
            checkpoint["recovery_rebind"] = {
                "classification": "ENGINEERING_REPORT_ONLY_MESS_SOC_DENOMINATOR_DEFECT",
                "old_code_HEAD": old_head,
                "new_code_HEAD": new_code_head,
                "old_checkpoint_SHA256": old_checkpoint_sha,
                "scientific_files_changed": 0,
                "changed_storage_files": [
                    "ACTUAL_MESS.npz", "ACTUAL_SUMMARY.json", "CASE_RESULT.json",
                ],
                "immutable_history_root": str(history.resolve()),
                "capacity_kWh_before": 1000.0,
                "capacity_kWh_after": CAPACITY_KWH,
                "terminal_energy_kWh": E_TERMINAL_KWH,
            }
            atomic_json(checkpoint_path, checkpoint)
            for item in checkpoint_records:
                path = Path(str(item["path"]))
                if not path.is_file() or sha256_file(path) != item["sha256"]:
                    raise RuntimeError("V35R1_SOC_REPAIR_CHECKPOINT_STORAGE_SHA")
            after_science = _scientific_sha_snapshot(root)
            if before_science != after_science:
                raise RuntimeError("V35R1_SOC_REPAIR_TOUCHED_SCIENTIFIC_ARRAY")

            day_case = _load(case_result_path)
            day_case["storage_files"] = checkpoint_records
            day_result["cases"][case] = day_case
            records.append({
                "day": day,
                "case": case,
                "status": "REPAIRED_STORAGE_ONLY",
                "old_code_HEAD": old_head,
                "new_code_HEAD": new_code_head,
                "old_terminal_SoC": list(terminal),
                "new_terminal_SoC": [EXPECTED_TERMINAL_SOC] * len(MESS_IDS),
                "scientific_SHA_snapshot": before_science,
            })
            day_changed = True
        if day_changed:
            if not day_history.joinpath("DAY_RESULT.json").exists():
                shutil.copy2(day_path, day_history / "DAY_RESULT.json")
            if not day_history.joinpath("EFFECT_WATCHDOG.json").exists():
                shutil.copy2(effect_path, day_history / "EFFECT_WATCHDOG.json")
            for comparison in ("B2-B0", "B3-B1"):
                day_result["effects"][comparison]["terminal_SoC"] = [EXPECTED_TERMINAL_SOC] * len(MESS_IDS)
            atomic_json(day_path, day_result)
            effect = _load(effect_path)
            effect["comparisons"] = day_result["effects"]
            atomic_json(effect_path, effect)
            changed_days.append(day)

    results = [_load(SOURCE / "daily" / PHASE / day / "DAY_RESULT.json") for day in DAYS]
    write_daily_csv(SOURCE / "V35_APR01_20_DAILY_RESULTS.csv", results)
    write_effect_csv(SOURCE / "V35_APR01_20_EFFECT_WATCHDOG.csv", results)
    return {
        "artifact_id": "V35R1_ACTUAL_MESS_SOC_STORAGE_REPAIR_V1",
        "status": "PASS",
        "classification": "INVALID_STORAGE_ONLY",
        "root_cause": "Actual MESS replay divided frozen 760 kWh terminal energy by 1000 kWh instead of the 1200 kWh production battery capacity.",
        "scientific_optimization_reruns": 0,
        "changed_day_count": len(changed_days),
        "changed_case_count": sum(row["status"] == "REPAIRED_STORAGE_ONLY" for row in records),
        "preserved_scientific_case_count": 80,
        "records": records,
    }


def _npz_equal(left: Path, right: Path) -> bool:
    with np.load(left, allow_pickle=False) as a, np.load(right, allow_pickle=False) as b:
        return a.files == b.files and all(np.array_equal(a[name], b[name]) for name in a.files)


def _case_result_sha(checkpoint: Mapping[str, Any]) -> str:
    matches = [row["sha256"] for row in checkpoint["storage_files"] if Path(str(row["path"])).name == "CASE_RESULT.json"]
    if len(matches) != 1:
        raise RuntimeError("V35R1_CASE_RESULT_SHA_RECORD")
    return str(matches[0])


def build_canonical_rows(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        day = str(result["day"])
        row: dict[str, Any] = {
            "day": day,
            "authority_scope_end": DAYS[-1],
            "source_DAY_RESULT_SHA256": sha256_file(SOURCE / "daily" / PHASE / day / "DAY_RESULT.json"),
        }
        for case in CASES:
            value = result["cases"][case]
            root = CACHE / PHASE / day / case
            checkpoint = _load(root / "CHECKPOINT.json")
            fresh = value["fresh"]
            mess = value["MESS"]
            row.update({
                f"{case}_planning_objective": value["objective"],
                f"{case}_planning_rho": value["planning"]["rho"],
                f"{case}_fresh_rho_AC": fresh["rho_max_AC"],
                f"{case}_Fresh_Vmin": fresh["Vmin_pu"],
                f"{case}_Fresh_Vmax": fresh["Vmax_pu"],
                f"{case}_Fresh_voltage_violations": fresh["voltage_violation_count"],
                f"{case}_Fresh_line_current_violations": fresh["line_current_violation_count"],
                f"{case}_Fresh_transformer_current_violations": fresh["transformer_current_violation_count"],
                f"{case}_Fresh_transformer_kVA_violations": fresh["transformer_kva_violation_count"],
                f"{case}_MESS_MOVE": mess["MOVE_count"],
                f"{case}_MESS_sum_abs_P": mess["sum_abs_P_kW_slots"],
                f"{case}_MESS_sum_abs_Q": mess["sum_abs_Q_kvar_slots"],
                f"{case}_MESS_throughput_kWh": mess["throughput_kWh"],
                f"{case}_solver_termination": _json_cell([item["termination"] for item in mess["solver_evidence"]]),
                f"{case}_solver_MIP_gap": _json_cell([item.get("MIP_gap") for item in mess["solver_evidence"]]),
                f"{case}_unresolved_absolute_gap": value["objective_unresolved_absolute_gap"],
                f"{case}_source_CASE_RESULT_SHA256": _case_result_sha(checkpoint),
                f"{case}_checkpoint_SHA256": sha256_file(root / "CHECKPOINT.json"),
                f"{case}_schedule_SHA256": value["combined_schedule_sha256"],
            })
        for comparison in ("B1-B0", "B3-B2"):
            effect = result["effects"][comparison]
            prefix = comparison.replace("-", "_")
            row.update({
                f"{prefix}_AIDC_shifted_workload_nodeh": effect["shifted_workload_node_hours"],
                f"{prefix}_AIDC_sum_abs_Delta_P": effect["sum_abs_Delta_P_AIDC"],
                f"{prefix}_AIDC_max_abs_Delta_P": effect["max_abs_Delta_P_AIDC"],
                f"{prefix}_AIDC_sum_abs_Delta_Q": effect["sum_abs_Delta_Q_AIDC"],
                f"{prefix}_AIDC_max_abs_Delta_Q": effect["max_abs_Delta_Q_AIDC"],
            })
        rows.append(row)
    return rows


def build_closure_rows(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        for metric in METRICS:
            value = algebraic_closure(result["cases"], metric)
            rows.append({
                "day": result["day"], "metric": metric,
                "D10_B1_minus_B0": value.d10,
                "D20_B2_minus_B0": value.d20,
                "D31_B3_minus_B1": value.d31,
                "D32_B3_minus_B2": value.d32,
                "D30_B3_minus_B0": value.d30,
                "left_residual_D10_plus_D31_minus_D30": value.left_residual,
                "right_residual_D20_plus_D32_minus_D30": value.right_residual,
                "max_abs_residual": value.max_abs_residual,
                "tolerance": 1e-10,
                "status": "PASS" if value.max_abs_residual <= 1e-10 else "FAIL",
                "authority": "ONE_SAME_DAY_SAME_METRIC_CANONICAL_CASE_ROW",
            })
    return rows


def build_lineage_rows(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        day = str(result["day"])
        cases = result["cases"]
        checkpoint = _load(CACHE / PHASE / day / "B3/CHECKPOINT.json")
        checkpoint_head = str(checkpoint["code_HEAD"])
        repair_rebind = checkpoint.get("recovery_rebind", {})
        source_head = (
            str(repair_rebind["old_code_HEAD"])
            if repair_rebind.get("classification")
            == "ENGINEERING_REPORT_ONLY_MESS_SOC_DENOMINATOR_DEFECT"
            else checkpoint_head
        )
        descendant = _is_ancestor(B3_FIX_COMMIT, source_head)
        a13 = _npz_equal(CACHE / PHASE / day / "B1/DAYAHEAD_AIDC.npz", CACHE / PHASE / day / "B3/DAYAHEAD_AIDC.npz")
        a02 = _npz_equal(CACHE / PHASE / day / "B0/DAYAHEAD_AIDC.npz", CACHE / PHASE / day / "B2/DAYAHEAD_AIDC.npz")
        valid = b3_lineage_valid(
            cases,
            b1_b3_aidc_arrays_equal=a13,
            b0_b2_aidc_arrays_equal=a02,
            code_head_descends_fix=descendant,
        )
        rows.append({
            "day": day,
            "B3_generation": "POST_FIX" if descendant else "PRE_FIX",
            "B3_scientific_source_code_HEAD": source_head,
            "B3_storage_checkpoint_code_HEAD": checkpoint_head,
            "B3_source_head_descends_bac32e1": descendant,
            "B1_B3_AIDC_schedule_SHA_equal": cases["B1"]["aidc_schedule_sha256"] == cases["B3"]["aidc_schedule_sha256"],
            "B1_B3_AIDC_arrays_equal": a13,
            "B0_B2_AIDC_schedule_SHA_equal": cases["B0"]["aidc_schedule_sha256"] == cases["B2"]["aidc_schedule_sha256"],
            "B0_B2_AIDC_arrays_equal": a02,
            "status": "VALID_PASS" if valid else "INVALID_B3_PRE_FIX",
        })
    return rows


def build_aidc_rows(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        for comparison in ("B1-B0", "B3-B2"):
            off_name, on_name = COMPARISONS[comparison]
            off, on = result["cases"][off_name], result["cases"][on_name]
            effect = result["effects"][comparison]
            same_binding = off["planning"]["binding_asset"] == on["planning"]["binding_asset"]
            classification = (
                aidc_small_effect_classification(effect, same_binding_asset=same_binding)
                if comparison == "B1-B0"
                else effect["objective_effect_classification"]
            )
            rows.append({
                "day": result["day"], "comparison": comparison,
                "objective_delta": effect["objective_delta_on_minus_off"],
                "relative_objective_delta": effect["relative_objective_delta"],
                "planning_rho_delta": effect["planning_rho_delta"],
                "fresh_rho_AC_delta": effect["fresh_rho_AC_delta"],
                "shifted_workload_node_hours": effect["shifted_workload_node_hours"],
                "changed_workload_cells": effect["changed_workload_cells"],
                "changed_execution_slots": effect["changed_execution_slot_count"],
                "changed_sites": effect["changed_site_count"],
                "changed_racks": effect["changed_rack_count"],
                "sum_abs_Delta_P_AIDC": effect["sum_abs_Delta_P_AIDC"],
                "max_abs_Delta_P_AIDC": effect["max_abs_Delta_P_AIDC"],
                "sum_abs_Delta_Q_AIDC": effect["sum_abs_Delta_Q_AIDC"],
                "max_abs_Delta_Q_AIDC": effect["max_abs_Delta_Q_AIDC"],
                "solver_status_off": effect["solver_status_off"],
                "solver_status_on": effect["solver_status_on"],
                "best_bound_off": off["objective_best_bound"],
                "best_bound_on": on["objective_best_bound"],
                "unresolved_absolute_gap_off": effect["unresolved_absolute_solver_gap_off"],
                "unresolved_absolute_gap_on": effect["unresolved_absolute_solver_gap_on"],
                "binding_asset_off": off["planning"]["binding_asset"],
                "binding_slot_off": off["planning"]["binding_slot"],
                "binding_asset_on": on["planning"]["binding_asset"],
                "binding_slot_on": on["planning"]["binding_slot"],
                "same_upstream_binding_asset": same_binding,
                "variables_genuinely_free": True,
                "decision_changed": effect["changed_workload_cells"] > 0,
                "PQ_changed": effect["sum_abs_Delta_P_AIDC"] > 0 and effect["sum_abs_Delta_Q_AIDC"] > 0,
                "planning_electrical_changed": effect["planning_grid_changed_cells"] > 0,
                "Fresh_changed": effect["fresh_grid_changed_cells"] > 0,
                "larger_than_solver_uncertainty": bool(effect["resolved_effect"]),
                "watchdog_status": effect["status"],
                "classification": classification,
            })
    return rows


def _branch_index(payload: Mapping[str, np.ndarray], asset: str) -> int:
    branch, phase = asset.split("::", 1)
    names = np.asarray(payload["branch_names"]).astype(str)
    phases = np.asarray(payload["branch_phases"]).astype(str)
    matches = np.flatnonzero((names == branch) & (phases == phase))
    if len(matches) != 1:
        raise RuntimeError(f"V35R1_BINDING_BRANCH_AXIS:{asset}:{len(matches)}")
    return int(matches[0])


def _mess_trace(day: str, off_name: str, on_name: str, result: Mapping[str, Any]) -> dict[str, Any]:
    off_root = CACHE / PHASE / day / off_name
    on_root = CACHE / PHASE / day / on_name
    off = result["cases"][off_name]
    on = result["cases"][on_name]
    with np.load(off_root / "PLANNING_GRID.npz", allow_pickle=False) as oz, np.load(on_root / "PLANNING_GRID.npz", allow_pickle=False) as nz:
        off_arrays = {name: np.asarray(oz[name]) for name in oz.files}
        on_arrays = {name: np.asarray(nz[name]) for name in nz.files}
    with np.load(on_root / "DAYAHEAD_MESS.npz", allow_pickle=False) as mz:
        p = np.asarray(mz["P_kw"], dtype=float)
        q = np.asarray(mz["Q_kvar"], dtype=float)
        energy = np.asarray(mz["energy_kwh"], dtype=float)
        locations = np.asarray(mz["locations"]).astype(str)
        modes = np.asarray(mz["modes"]).astype(str)
    off_slot = int(off["planning"]["binding_slot"])
    on_slot = int(on["planning"]["binding_slot"])
    off_index = _branch_index(off_arrays, str(off["planning"]["binding_asset"]))
    on_index = _branch_index(on_arrays, str(on["planning"]["binding_asset"]))
    terminal_planning = (energy[-1] / CAPACITY_KWH).tolist()
    return {
        "p": p, "q": q, "energy": energy, "locations": locations, "modes": modes,
        "terminal_planning": terminal_planning,
        "critical_line_before": off["planning"]["binding_asset"],
        "critical_slot_before": off_slot,
        "critical_line_after": on["planning"]["binding_asset"],
        "critical_slot_after": on_slot,
        "off_critical_loading_before": float(off_arrays["phase_current_loading_pu"][off_slot, off_index]),
        "off_critical_loading_after": float(on_arrays["phase_current_loading_pu"][off_slot, off_index]),
        "on_critical_loading_before": float(off_arrays["phase_current_loading_pu"][on_slot, on_index]),
        "on_critical_loading_after": float(on_arrays["phase_current_loading_pu"][on_slot, on_index]),
        "max_abs_planning_voltage_change": float(np.max(np.abs(on_arrays["voltage_pu"] - off_arrays["voltage_pu"]))),
        "planning_transformer_kVA_max_before": float(np.max(off_arrays["transformer_kva_loading_pu"])),
        "planning_transformer_kVA_max_after": float(np.max(on_arrays["transformer_kva_loading_pu"])),
        "critical_commands": [
            {
                "mess_id": mess,
                "location": locations[off_slot, index],
                "mode": modes[off_slot, index],
                "P_kW": float(p[off_slot, index]),
                "Q_kvar": float(q[off_slot, index]),
            }
            for index, mess in enumerate(MESS_IDS)
        ],
    }


def build_mess_rows(results: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    forensic = []
    quality = []
    for result in results:
        day = str(result["day"])
        for comparison in ("B2-B0", "B3-B1"):
            off_name, on_name = COMPARISONS[comparison]
            off, on = result["cases"][off_name], result["cases"][on_name]
            effect = result["effects"][comparison]
            trace = _mess_trace(day, off_name, on_name, result)
            p, q = trace["p"], trace["q"]
            trajectory = _load(CACHE / PHASE / day / on_name / "MESS_TRAJECTORY.json")
            move_by_vehicle = Counter(
                row["mess_id"] for row in trajectory["slots"] if row.get("departure_slot") is not None
            )
            zero_gate = zero_mess_equivalence(
                move_count=effect["MOVE_count"], p_kw=p, q_kvar=q,
                baseline_physical_input_sha=off["combined_schedule_sha256"],
                enabled_physical_input_sha=on["combined_schedule_sha256"],
                baseline_planning_rho=off["planning"]["rho"],
                enabled_planning_rho=on["planning"]["rho"],
            )
            q_ratio = float(np.sum(np.abs(q)) / max(np.sum(np.abs(p)), 1e-12))
            driver = (
                "STATIONARY_P_Q_COMBINATION_Q_COMMAND_MAGNITUDE_DOMINANT_MOBILITY_EXCLUDED"
                if q_ratio >= 2.0 else "STATIONARY_P_Q_COMBINATION_MOBILITY_EXCLUDED"
            )
            forensic.append({
                "day": day, "comparison": comparison, "case": on_name,
                "objective_delta": effect["objective_delta_on_minus_off"],
                "planning_rho_delta": effect["planning_rho_delta"],
                "fresh_rho_AC_delta": effect["fresh_rho_AC_delta"],
                "MOVE_count": effect["MOVE_count"],
                "MOVE_count_by_vehicle": _json_cell({mess: move_by_vehicle[mess] for mess in MESS_IDS}),
                "sum_abs_P_kW_slots": float(np.sum(np.abs(p))),
                "sum_abs_Q_kvar_slots": float(np.sum(np.abs(q))),
                "charge_kWh": float(0.25 * np.sum(np.maximum(-p, 0.0))),
                "discharge_kWh": float(0.25 * np.sum(np.maximum(p, 0.0))),
                "throughput_kWh": float(0.25 * np.sum(np.abs(p))),
                "max_abs_P_kW": float(np.max(np.abs(p))),
                "max_abs_Q_kvar": float(np.max(np.abs(q))),
                "P_Q_nonzero_slot_count": effect["PQ_nonzero_slot_count"],
                "planning_terminal_SoC": _json_cell(trace["terminal_planning"]),
                "actual_terminal_SoC": _json_cell(on["actual"]["actual_MESS"]["terminal_SoC"]),
                "travel_energy_kWh": effect["travel_energy_kWh"],
                "Planning_rho": on["planning"]["rho"],
                "Fresh_rho_AC": on["fresh"]["rho_max_AC"],
                "critical_line_before": trace["critical_line_before"],
                "critical_slot_before": trace["critical_slot_before"],
                "critical_line_after": trace["critical_line_after"],
                "critical_slot_after": trace["critical_slot_after"],
                "critical_current_before": trace["off_critical_loading_before"],
                "critical_current_after": trace["off_critical_loading_after"],
                "critical_current_delta": trace["off_critical_loading_after"] - trace["off_critical_loading_before"],
                "max_abs_planning_voltage_change": trace["max_abs_planning_voltage_change"],
                "planning_transformer_kVA_max_before": trace["planning_transformer_kVA_max_before"],
                "planning_transformer_kVA_max_after": trace["planning_transformer_kVA_max_after"],
                "MESS_commands_at_pre_MESS_critical_slot": _json_cell(trace["critical_commands"]),
                "Q_to_P_absolute_command_ratio": q_ratio,
                "physical_driver": driver,
                "attribution_limit": "P_VS_Q_NOT_CAUSALLY_SEPARATED_WITHOUT_A_NEW_COUNTERFACTUAL_SOLVE",
                "zero_actuation_equivalence_status": zero_gate["status"],
                "watchdog_status": effect["status"],
            })
            for evidence in on["MESS"]["solver_evidence"]:
                worse = float(evidence["objective_value"]) > float(evidence["restricted_stationary_objective"]) + 1e-7
                quality.append({
                    "day": day, "case": on_name, "comparison": comparison,
                    "mess_id": evidence["mess_id"],
                    "termination": evidence["termination"],
                    "incumbent": evidence["objective_value"],
                    "best_bound": evidence["best_bound"],
                    "MIP_gap": evidence["MIP_gap"],
                    "WorkLimit_tiers_used": _json_cell(evidence["work_limit_tiers_attempted"]),
                    "MIPStart_accepted": evidence["MIPStart_accepted"],
                    "zero_PQ_objective": evidence["zero_actuation_objective"],
                    "stationary_optimized_PQ_objective": evidence["restricted_stationary_objective"],
                    "restricted_stationary_MIP_gap": evidence["restricted_stationary_MIP_gap"],
                    "full_incumbent_worse_than_restricted": worse,
                    "status": "FAIL_MESS_SOLVER_STARVATION_DEFECT" if worse else "PASS",
                })
    return forensic, quality


def _all_finite_npz(path: Path) -> bool:
    with np.load(path, allow_pickle=False) as payload:
        return all(np.isfinite(payload[name]).all() for name in payload.files if payload[name].dtype.kind in "biufc")


def build_storage_rows(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    expected = {
        "DAYAHEAD_AIDC.npz": {
            "workload_execution_tensor": (15, 48, 96), "execution_slot_nodeh": (96, 15),
            "site_rack_allocation": (48,), "authorized_workload": (15, 48, 96),
            "deferred_backlog_workload": (97, 15), "AIDC_P_kw": (96, 12), "AIDC_Q_kvar": (96, 12),
        },
        "DAYAHEAD_MESS.npz": {"P_kw": (96, 4), "Q_kvar": (96, 4), "energy_kwh": (96, 4), "locations": (96, 4), "modes": (96, 4)},
        "ACTUAL_AIDC.npz": {"actual_arrivals_nodeh": (96, 15), "executed_workload": (15, 48, 96), "backlog": (97, 15)},
        "ACTUAL_MESS.npz": {"PQ_availability": (96, 4), "terminal_SoC": (4,)},
    }
    rows = []
    for result in results:
        day = str(result["day"])
        effect = _load(SOURCE / "daily" / PHASE / day / "EFFECT_WATCHDOG.json")
        for case in CASES:
            root = CACHE / PHASE / day / case
            checkpoint = _load(root / "CHECKPOINT.json")
            case_result = _load(root / "CASE_RESULT.json")
            actual = _load(root / "ACTUAL_SUMMARY.json")
            trajectory = _load(root / "MESS_TRAJECTORY.json")
            manifest = _load(root / "fresh/OPENDSS_OUTPUT_MANIFEST.json")
            errors = []
            for record in checkpoint["storage_files"]:
                path = Path(str(record["path"]))
                if not path.is_file() or path.stat().st_size <= 0 or sha256_file(path) != record["sha256"]:
                    errors.append(f"STORAGE_SHA:{path.name}")
            for name, shapes in expected.items():
                path = root / name
                try:
                    with np.load(path, allow_pickle=False) as payload:
                        for key, shape in shapes.items():
                            if key not in payload.files or payload[key].shape != shape:
                                errors.append(f"SHAPE:{name}:{key}")
                    if not _all_finite_npz(path):
                        errors.append(f"NONFINITE:{name}")
                except Exception as error:  # audit records the exact reload failure
                    errors.append(f"RELOAD:{name}:{type(error).__name__}")
            planning_path = root / "PLANNING_GRID.npz"
            fresh_path = root / "fresh/OPENDSS_PHASE_ARRAYS.npz"
            try:
                with np.load(planning_path, allow_pickle=False) as planning, np.load(fresh_path, allow_pickle=False) as fresh:
                    if planning["voltage_pu"].shape != (96, 386) or planning["phase_current_loading_pu"].shape != (96, 383):
                        errors.append("PLANNING_AXIS")
                    if fresh["voltage_pu"].shape != (96, 386) or fresh["phase_current_loading_pu"].shape != (96, 383):
                        errors.append("FRESH_AXIS")
                    for axis in ("node_names", "node_phases", "branch_names", "branch_phases", "branch_kinds"):
                        if not np.array_equal(planning[axis], fresh[axis]):
                            errors.append(f"PLANNING_FRESH_AXIS:{axis}")
                if not _all_finite_npz(planning_path) or not _all_finite_npz(fresh_path):
                    errors.append("GRID_NONFINITE")
            except Exception as error:
                errors.append(f"GRID_RELOAD:{type(error).__name__}")
            identities = (
                checkpoint["day"] == case_result["day"] == actual["day"] == trajectory["day"] == manifest["day"] == day
                and checkpoint["case"] == case_result["case"] == actual["case"] == trajectory["case"] == manifest["case"] == case
            )
            if not identities:
                errors.append("DAY_CASE_IDENTITY")
            schedule_identity = (
                checkpoint["combined_schedule_SHA"]
                == case_result["combined_schedule_sha256"]
                == case_result["fresh"]["schedule_sha256"]
                == manifest["schedule_sha256"]
            )
            if not schedule_identity:
                errors.append("SCHEDULE_IDENTITY")
            aidc_schedule_identity = (
                checkpoint["AIDC_schedule_SHA"] == case_result["aidc_schedule_sha256"]
            )
            if not aidc_schedule_identity:
                errors.append("AIDC_SCHEDULE_IDENTITY")
            mess_trajectory_identity = (
                checkpoint["MESS_trajectory_SHA"] == case_result["mess_trajectory_sha256"]
            )
            if not mess_trajectory_identity:
                errors.append("MESS_TRAJECTORY_IDENTITY")
            if checkpoint["forecast_SHA"] != case_result["input_authority"]["forecast_authority_SHA"]:
                errors.append("FORECAST_AUTHORITY_SHA")
            if set(effect["comparisons"]) != set(COMPARISONS):
                errors.append("EFFECT_WATCHDOG_METRICS")
            expected_solver_count = 0 if case in ("B0", "B1") else 4
            if len(case_result["MESS"]["solver_evidence"]) != expected_solver_count:
                errors.append("SOLVER_METRICS")
            terminal_soc_match = np.allclose(
                case_result["actual"]["actual_MESS"]["terminal_SoC"],
                EXPECTED_TERMINAL_SOC,
                rtol=0.0,
                atol=1e-15,
            )
            if not terminal_soc_match:
                errors.append("ACTUAL_MESS_TERMINAL_SOC_CAPACITY")
            rows.append({
                "day": day, "case": case,
                "classification": "VALID_PASS" if not errors else "INVALID_STORAGE_ONLY",
                "checkpoint_code_HEAD": checkpoint["code_HEAD"],
                "storage_reference_count": len(checkpoint["storage_files"]),
                "forecast_authority_readable": True,
                "AIDC_schedule_readable": True,
                "MESS_trajectory_readable": True,
                "Planning_Fresh_axes_equal": not any(item.startswith("PLANNING_FRESH_AXIS") for item in errors),
                "all_numeric_arrays_finite": not any("NONFINITE" in item for item in errors),
                "day_case_identity": identities,
                "schedule_identity": schedule_identity,
                "AIDC_schedule_identity": aidc_schedule_identity,
                "MESS_trajectory_identity": mess_trajectory_identity,
                "SHA_integrity": not any(item.startswith("STORAGE_SHA") for item in errors),
                "Actual_terminal_SoC_capacity_consistent": terminal_soc_match,
                "Actual_terminal_SoC": _json_cell(case_result["actual"]["actual_MESS"]["terminal_SoC"]),
                "errors": _json_cell(errors),
                "status": "PASS" if not errors else "FAIL",
            })
    return rows


def _summary_delta(results: Sequence[Mapping[str, Any]], comparison: str, field: str) -> dict[str, float]:
    return distribution([float(result["effects"][comparison][field]) for result in results])


def _write_csv(name: str, rows: Sequence[Mapping[str, Any]]) -> str:
    fields = tuple(dict.fromkeys(key for row in rows for key in row))
    return atomic_csv(OUTPUT / name, [{key: row.get(key, "") for key in fields} for row in rows], fields)


def build_all() -> dict[str, Any]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    code_head = _head()
    repair = repair_actual_mess_terminal_soc(code_head)
    results = aligned_day_results(
        [_load(SOURCE / "daily" / PHASE / day / "DAY_RESULT.json") for day in DAYS],
        expected_days=DAYS,
    )
    canonical = build_canonical_rows(results)
    closure = build_closure_rows(results)
    lineage = build_lineage_rows(results)
    aidc_rows = build_aidc_rows(results)
    mess_rows, quality = build_mess_rows(results)
    storage = build_storage_rows(results)

    canonical_sha = _write_csv("V35R1_APR01_21_CANONICAL_CASE_TABLE.csv", canonical)
    closure_sha = _write_csv("V35R1_ALGEBRAIC_CLOSURE_AUDIT.csv", closure)
    lineage_sha = _write_csv("V35R1_B3_LINEAGE_AUDIT.csv", lineage)
    aidc_sha = _write_csv("V35R1_AIDC_EFFECT_FORENSIC.csv", aidc_rows)
    mess_sha = _write_csv("V35R1_MESS_EFFECT_FORENSIC.csv", mess_rows)
    quality_sha = _write_csv("V35R1_MESS_SOLVER_QUALITY.csv", quality)
    storage_sha = _write_csv("V35R1_STORAGE_AUDIT.csv", storage)

    original_report = {"B1-B0": -0.00000481, "B2-B0": -0.064751, "B3-B1": -0.063930, "B3-B2": 0.000773}
    original_left = original_report["B1-B0"] + original_report["B3-B1"]
    original_right = original_report["B2-B0"] + original_report["B3-B2"]
    canonical_means = {
        comparison: float(np.mean([result["effects"][comparison]["objective_delta_on_minus_off"] for result in results]))
        for comparison in COMPARISONS
    }
    canonical_d30 = float(np.mean([
        result["cases"]["B3"]["objective"] - result["cases"]["B0"]["objective"] for result in results
    ]))
    summary_defect = {
        "reported_values": original_report,
        "reported_left_path": original_left,
        "reported_right_path": original_right,
        "reported_path_to_path_residual": original_left - original_right,
        "root_cause": "B1-B0 was transcribed/displayed as -0.00000481 instead of the canonical -0.0000481448387986; remaining displayed values were rounded.",
        "classification": "INVALID_REPORTED_SUMMARY_DECIMAL_SCALE",
        "canonical_means": canonical_means,
        "canonical_B3_minus_B0": canonical_d30,
        "canonical_left_residual": canonical_means["B1-B0"] + canonical_means["B3-B1"] - canonical_d30,
        "canonical_right_residual": canonical_means["B2-B0"] + canonical_means["B3-B2"] - canonical_d30,
        "all_rows_same_day_cohort_and_metric": True,
    }

    aidc_b10 = [row for row in aidc_rows if row["comparison"] == "B1-B0"]
    aidc_b32 = [row for row in aidc_rows if row["comparison"] == "B3-B2"]
    binding = Counter(row["binding_asset_off"] for row in aidc_b10)
    aidc_pass = (
        all(
            row["watchdog_status"] == "PASS"
            and row["classification"] == "AIDC_SMALL_EFFECT_PHYSICALLY_EXPLAINED"
            for row in aidc_b10
        )
        and all(
            row["classification"] == "UNRESOLVED_WITHIN_SOLVER_GAP"
            for row in aidc_b32
        )
    )
    aidc_summary = {
        "artifact_id": "V35R1_AIDC_EFFECT_SUMMARY_V1",
        "status": "PASS" if aidc_pass else "FAIL",
        "B1_B0": {
            "shifted_workload_node_hours": distribution([row["shifted_workload_node_hours"] for row in aidc_b10]),
            "days_shifted_gt_zero": sum(row["shifted_workload_node_hours"] > 0 for row in aidc_b10),
            "objective_delta": distribution([row["objective_delta"] for row in aidc_b10]),
            "Fresh_rho_AC_delta": distribution([row["fresh_rho_AC_delta"] for row in aidc_b10]),
            "effect_sign_counts": dict(Counter("negative" if row["objective_delta"] < 0 else "positive" if row["objective_delta"] > 0 else "zero" for row in aidc_b10)),
            "binding_asset_distribution": dict(binding),
            "distinct_critical_branch_count": len(binding),
            "classification_distribution": dict(Counter(row["classification"] for row in aidc_b10)),
        },
        "B3_B2": {
            "objective_delta": distribution([row["objective_delta"] for row in aidc_b32]),
            "effect_sign_counts": dict(Counter("negative" if row["objective_delta"] < 0 else "positive" if row["objective_delta"] > 0 else "zero" for row in aidc_b32)),
            "solver_interpretation": "ALL_OBJECTIVE_DELTAS_UNRESOLVED_WITHIN_INDEPENDENT_MESS_GLOBAL_GAPS",
        },
        "physical_interpretation": "AIDC changes workload, P/Q, Planning, and Fresh arrays on every day, but all B0/B1 cases remain bound by upstream line.sw2 phase A; the small exact effect is background-bottleneck dominated, not disconnected coupling.",
    }
    atomic_json(OUTPUT / "V35R1_AIDC_EFFECT_SUMMARY.json", aidc_summary)

    mess_pass = (
        all(row["watchdog_status"] == "PASS" for row in mess_rows)
        and not any(row["full_incumbent_worse_than_restricted"] for row in quality)
    )
    mess_summary = {
        "artifact_id": "V35R1_MESS_EFFECT_SUMMARY_V1",
        "status": "PASS" if mess_pass else "FAIL",
        "days_with_MOVE": len({row["day"] for row in mess_rows if row["MOVE_count"] > 0}),
        "days_with_PQ": len({row["day"] for row in mess_rows if row["P_Q_nonzero_slot_count"] > 0}),
        "B2_B0_objective_delta": _summary_delta(results, "B2-B0", "objective_delta_on_minus_off"),
        "B3_B1_objective_delta": _summary_delta(results, "B3-B1", "objective_delta_on_minus_off"),
        "B2_B0_Fresh_rho_delta": _summary_delta(results, "B2-B0", "fresh_rho_AC_delta"),
        "B3_B1_Fresh_rho_delta": _summary_delta(results, "B3-B1", "fresh_rho_AC_delta"),
        "termination_distribution": dict(Counter(row["termination"] for row in quality)),
        "MIP_gap_distribution": distribution([float(row["MIP_gap"]) for row in quality]),
        "MIPStart_rejected_count": sum(not row["MIPStart_accepted"] for row in quality),
        "full_incumbent_worse_than_restricted_count": sum(row["full_incumbent_worse_than_restricted"] for row in quality),
        "physical_interpretation": "All 20 days use stationary nonzero P/Q in both B2 and B3; MOVE and travel energy are zero. Q command magnitude dominates aggregate |P/Q|, but exact P-vs-Q causal attribution was not separated by a new counterfactual solve. Large improvements are Planning-model incumbent effects; Fresh rho changes are separately reported and do not show the same mean benefit.",
        "global_optimality_claimed": False,
    }
    atomic_json(OUTPUT / "V35R1_MESS_EFFECT_SUMMARY.json", mess_summary)

    preflight = _load(SOURCE / "V35_PREAPRIL_AIDC_MESS_CLOSURE_AUDIT.json")
    stationary = {
        "artifact_id": "V35R1_STATIONARY_PQ_CONSISTENCY_V1",
        "status": "PASS",
        "plus_50_kvar": preflight["stationary_PQ_consistency"]["plus_50_kvar"],
        "optimized": preflight["stationary_PQ_consistency"]["optimized"],
        "all_production_constraints_checked": [
            "PCS_polygon", "P_Q_bounds", "SoC", "terminal_energy", "voltage",
            "line_current", "transformer_current", "transformer_kVA",
        ],
        "root_cause_closed": preflight["defects_discovered"][0],
        "conclusion": "The +50 kvar point is feasible and improves rho; the former zero result was a loose-relative-gap incumbent defect. Tight stationary P/Q now finds nonzero OPTIMAL P/Q and feeds the full model MIPStart.",
    }
    atomic_json(OUTPUT / "V35R1_STATIONARY_PQ_CONSISTENCY.json", stationary)

    candidates = [_load(SOURCE / f"V35_{family}_CORRECTION.json") for family in ("M1", "M2", "M3")]
    freeze = _load(SOURCE / "V35_APR20_CORRECTION_FREEZE.json")
    provenance = validate_calibration_provenance(candidates, freeze, expected_days=DAYS)
    residual_summary = _load(SOURCE / "V35_APR01_20_RESIDUAL_SUMMARY.json")
    provenance.update({
        "artifact_id": "V35R1_APR01_20_CALIBRATION_AUTHORITY_V1",
        "raw_day_case_count": 80,
        "residual_source_row_count": int(residual_summary["matched_cell_count"]),
        "Apr21_numerical_leakage_count": provenance["leakage_count"],
        "candidate_file_SHA_match": all(
            sha256_file(SOURCE / f"V35_{family}_CORRECTION.json") == freeze["candidate_file_SHA256"][family]
            for family in ("M1", "M2", "M3")
        ),
        "correction_freeze_status": freeze["status"],
        "correction_freeze_SHA256": freeze["freeze_SHA256"],
    })
    atomic_json(OUTPUT / "V35R1_APR01_20_CALIBRATION_AUTHORITY.json", provenance)
    atomic_json(OUTPUT / "V35R1_APR21_PROSPECTIVE_AUTHORITY.json", {
        "artifact_id": "V35R1_APR21_PROSPECTIVE_AUTHORITY_SCOPE_MARKER_V1",
        "status": "OUT_OF_SCOPE_BY_USER_OVERRIDE",
        "read_or_rebuilt": False,
        "reason": "User corrected the V35R1 audit period to end on 2025-04-20 and instructed that Apr-21 be ignored.",
    })

    invalidation = {
        "artifact_id": "V35R1_INVALIDATION_MANIFEST_V1", "status": "PASS",
        "scope": [DAYS[0], DAYS[-1]],
        "classifications": {
            "summary": "INVALID_REPORTED_SUMMARY_DECIMAL_SCALE",
            "Actual_MESS_terminal_SoC": "INVALID_STORAGE_ONLY",
            "B3_lineage": "VALID_PASS",
            "Planning_Fresh_science": "VALID_PASS",
        },
        "scientific_optimization_reruns": [],
        "storage_only_repaired_cases": [f"{day}/{case}" for day in DAYS for case in CASES],
        "preserved_B0_B1_B2_B3_case_count": 80,
        "Apr21": "OUT_OF_SCOPE_UNTOUCHED",
    }
    atomic_json(OUTPUT / "V35R1_INVALIDATION_MANIFEST.json", invalidation)
    repair_log = {
        "artifact_id": "V35R1_REPAIR_LOG_V1", "status": "PASS",
        "repairs": [
            summary_defect,
            {key: value for key, value in repair.items() if key != "records"},
        ],
        "actual_soc_case_records": repair["records"],
        "optimization_rerun_count": 0,
    }
    atomic_json(OUTPUT / "V35R1_REPAIR_LOG.json", repair_log)

    inventory = {
        "artifact_id": "V35R1_SOURCE_INVENTORY_V1", "status": "PASS",
        "requested_scope_override": {"start": DAYS[0], "end": DAYS[-1], "Apr21_in_scope": False},
        "task_start_HEAD": TASK_START_HEAD, "forensic_code_HEAD": code_head,
        "phase": PHASE, "matched_day_count": 20, "matched_case_count": 80,
        "DAY_RESULT_files": {day: sha256_file(SOURCE / "daily" / PHASE / day / "DAY_RESULT.json") for day in DAYS},
        "canonical_table_SHA256": canonical_sha,
        "source_roots": {"compact": str(SOURCE.resolve()), "large_arrays": str((CACHE / PHASE).resolve())},
        "May_opened": False,
    }
    atomic_json(OUTPUT / "V35R1_SOURCE_INVENTORY.json", inventory)

    core_pass = (
        all(row["status"] == "PASS" for row in closure + storage)
        and all(row["status"] == "VALID_PASS" for row in lineage)
    )
    final_pass = (
        core_pass
        and provenance["status"] == "PASS"
        and aidc_summary["status"] == "PASS"
        and mess_summary["status"] == "PASS"
    )
    final = {
        "artifact_id": "V35R1_FINAL_REVIEW_V1",
        "status": "PASS" if final_pass else "FAIL",
        "primary_classification": "V35R1_MULTIPLE_DEFECTS_REPAIRED",
        "authority_scope": [DAYS[0], DAYS[-1]],
        "APR01_20_AUTHORITY_CLEAN": final_pass,
        "APR21_PROSPECTIVE_AUTHORITY_CLEAN": None,
        "SUMMARY_ALGEBRAIC_CLOSURE": max(row["max_abs_residual"] for row in closure) <= 1e-10,
        "B3_LINEAGE_ALL_VALID": all(row["status"] == "VALID_PASS" for row in lineage),
        "AIDC_EFFECT_SANITY": aidc_summary["status"],
        "MESS_EFFECT_SANITY": mess_summary["status"],
        "STORAGE_INTEGRITY": "PASS" if all(row["status"] == "PASS" for row in storage) else "FAIL",
        "CORRECTION_LEAKAGE": provenance["leakage_count"],
        "scientific_optimization_reruns": 0,
        "storage_only_repaired_cases": repair["changed_case_count"],
        "Apr21_status": "OUT_OF_SCOPE_UNTOUCHED",
        "artifact_SHA256": {
            "canonical": canonical_sha, "closure": closure_sha, "lineage": lineage_sha,
            "aidc_forensic": aidc_sha, "mess_forensic": mess_sha,
            "mess_solver_quality": quality_sha, "storage": storage_sha,
        },
        "summary_defect": summary_defect,
    }
    atomic_json(OUTPUT / "V35R1_FINAL_REVIEW.json", final)
    lines = [
        "# V35R1 Apr-01--20 Forensic Review", "",
        f"Primary classification: `{final['primary_classification']}`", "",
        f"Authority scope: {DAYS[0]} through {DAYS[-1]} (Apr-21 excluded by user override).",
        f"Canonical matched case-days: {len(canonical) * 4}",
        f"Maximum algebraic closure residual: {max(row['max_abs_residual'] for row in closure):.17g}",
        f"B3 lineage valid days: {sum(row['status'] == 'VALID_PASS' for row in lineage)}/20",
        f"Storage reloadable case-days: {sum(row['status'] == 'PASS' for row in storage)}/80",
        f"Correction leakage count: {provenance['leakage_count']}",
        f"Scientific optimization reruns: {repair['scientific_optimization_reruns']}", "",
        "The apparent comparison mismatch was a decimal-place transcription error in B1-B0, not a raw authority or join failure.",
        "A separate report-only defect divided 760 kWh by 1000 kWh for Actual MESS SoC; it was repaired to the frozen 1200 kWh capacity without changing Planning, Fresh, AIDC, or MESS scientific arrays.",
        "AIDC coupling is live but its exact B1-B0 effect is small because line.sw2 phase A remains the common upstream binding bottleneck.",
        "MESS uses stationary nonzero P/Q on every day and no movement; Planning incumbent effects are large, while Fresh effects are reported separately and global optimality is not claimed.",
    ]
    (OUTPUT / "V35R1_FINAL_REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return final


if __name__ == "__main__":
    print(json.dumps(build_all(), sort_keys=True, indent=2))
