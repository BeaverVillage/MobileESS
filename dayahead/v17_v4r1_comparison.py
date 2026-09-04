"""Outcome-only V1 versus frozen V4R1 seven-day comparison."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from .aidc_boundary_v16_1 import DT_HOURS, PUE_PLAN
from .aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import sha256_file
from .v17_aidc_actuation_forensic import _aidc_only_upper_bound, _derived_matrices
from .v17_deferrability_semantics import LATENCY_CLASSES, write_json
from .v17_v4r1_april import DEBUG_DAYS, KAPPA_GPU_Q50_KW, electrical_context
from .v17_v5_current_repair import is_dominated_mess_current_row


def _controls(path: Path) -> np.ndarray:
    return np.asarray(np.load(path, allow_pickle=False)["controls_96x60"], dtype=float)


def _effects(base: np.ndarray, candidate: np.ndarray, relief: float) -> dict[str, float]:
    delta = candidate[:, :12] - base[:, :12]
    peak = float(np.max(np.abs(delta)))
    shifted_pcc_energy = 0.5 * float(np.sum(np.abs(delta))) * DT_HOURS
    return {
        "objective_relief_pu": float(relief),
        "peak_AIDC_PCC_shift_kw": peak,
        "shifted_AIDC_PCC_energy_kwh_L1_half": shifted_pcc_energy,
        "relief_per_peak_shifted_kw_pu_per_kw": float(relief / peak) if peak > 1e-12 else 0.0,
    }


def run(repo: Path, source: Path, output: Path) -> dict:
    repo = repo.resolve(); source = source.resolve(); output = output.resolve()
    coverage = json.loads((output / "V17_AIDC_POWER_V1_V4R1_COVERAGE_COMPARISON.json").read_text(encoding="utf-8"))
    v4_results = json.loads((output / "V17_AIDC_POWER_V4R1_7DAY_B0_B1_B2_B3_RESULTS.json").read_text(encoding="utf-8"))
    v1_results = json.loads((output / "V17_V5_CURRENT_REPAIR_7DAY_B0_B1_B2_B3_RESULTS.json").read_text(encoding="utf-8"))
    v1_by_day = {row["operating_day"]: row for row in v1_results["daily"]}
    v4_by_day = {
        day: json.loads((output / "v4r1_daily" / f"V17_V4R1_{day}_B0_B1_B2_B3.json").read_text(encoding="utf-8"))
        for day in DEBUG_DAYS
    }
    aliases = tuple(f"N{gpu:02d}_{latency}" for latency in LATENCY_CLASSES for gpu in range(1, 5))
    rows = []; v1_energy = 0.0; v4_energy = 0.0
    for day in DEBUG_DAYS:
        ref4 = np.load(output / "reference_v6_v4r1" / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{day}.npz", allow_pickle=False)
        ref1 = np.load(output / "reference_v5" / f"REFERENCE_COMPUTE_SCHEDULE_V5_{day}.npz", allow_pickle=False)
        v4_energy_day = float(np.sum(ref4["allocation"])) * KAPPA_GPU_Q50_KW
        v1_matrices = _derived_matrices(np.asarray(ref1["allocation"], dtype=float), np.asarray(ref1["p_res_aidc"], dtype=float), tuple(f"AIDC{i:02d}" for i in range(1,13) for _ in range(4)))
        v1_energy_day = float(np.sum(v1_matrices["AIDC_RACK_FLEX_POWER_KW"])) * DT_HOURS
        v1_energy += v1_energy_day; v4_energy += v4_energy_day
        d4 = v4_by_day[day]; d1 = v1_by_day[day]
        p4 = lambda case: Path(d4["cases"][case]["final_schedule_path"])
        p1 = lambda case: output / "schedules_v5_current_repair" / f"V17_V5_CURRENT_REPAIR_{day}_{case}.npz"
        v4_b1 = _effects(_controls(p4("B0")), _controls(p4("B1")), float(d4["cases"]["B0"]["objective"] - d4["cases"]["B1"]["objective"]))
        v4_b3 = _effects(_controls(p4("B2")), _controls(p4("B3")), float(d4["cases"]["B2"]["objective"] - d4["cases"]["B3"]["objective"]))
        v1_b1 = _effects(_controls(p1("B0")), _controls(p1("B1")), float(d1["B1_minus_B0_relief"]))
        v1_b3 = _effects(_controls(p1("B2")), _controls(p1("B3")), float(d1["B3_minus_B2_relief"]))

        reference, _inputs, vintage, background, binding, authority = electrical_context(repo, source, output, day)
        voltage = np.load(output / "ac_cache_v4r1/data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz", allow_pickle=False)
        current = np.load(output / "ac_cache_v4r1/data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz", allow_pickle=False)
        with (
            patch("dayahead.v17_aidc_actuation_forensic.COHORTS", aliases),
            patch("dayahead.v17_aidc_actuation_forensic.GPU_PER_NODE", 1.0),
            patch.dict(KAPPA_KW_PER_ACTIVE_H100_NODE, {gpu: KAPPA_GPU_Q50_KW for gpu in range(1,5)}, clear=True),
        ):
            upper = _aidc_only_upper_bound(
                arrivals=np.asarray(ref4["arrivals"], dtype=float), reference_cube=np.asarray(ref4["allocation"], dtype=float),
                p_res_aidc=np.asarray(ref4["p_res_aidc"], dtype=float), g_res_rack=np.asarray(ref4["g_res_rack"], dtype=float),
                gpu_capacities=np.asarray(ref4["gpu_capacities"], dtype=float), rack_aidc=tuple(r.aidc_id for r in authority.racks),
                current=current, voltage=voltage, base_controls=_controls(p4("B0")), skip_current_row=is_dominated_mess_current_row,
            )
        upper_relief = None if upper["status"] != "OPTIMAL" else float(d4["cases"]["B0"]["objective"] - upper["objective_max_normalized_phase_line_current"])
        rows.append({
            "operating_day": day, "V1_flexible_IT_energy_kwh": v1_energy_day, "V4R1_flexible_IT_energy_kwh": v4_energy_day,
            "V1_B1_minus_B0": v1_b1, "V1_B3_minus_B2": v1_b3,
            "V4R1_B1_minus_B0": v4_b1, "V4R1_B3_minus_B2": v4_b3,
            "V4R1_AIDC_only_upper_bound": {"status": upper["status"], "objective": upper.get("objective_max_normalized_phase_line_current"), "best_possible_relief_pu": upper_relief, "runtime_seconds": upper.get("runtime_seconds")},
        })
    semantic = coverage["semantic_flexible"]
    v1 = coverage["V1"]; v4 = coverage["V1_plus_V4R1_U2_CLEAN"]
    def aggregate(which: str) -> dict:
        pairs1 = [row[f"{which}_B1_minus_B0"] for row in rows]; pairs3 = [row[f"{which}_B3_minus_B2"] for row in rows]
        return {
            "B1_minus_B0_relief_range_pu": [min(x["objective_relief_pu"] for x in pairs1), max(x["objective_relief_pu"] for x in pairs1)],
            "B3_minus_B2_relief_range_pu": [min(x["objective_relief_pu"] for x in pairs3), max(x["objective_relief_pu"] for x in pairs3)],
            "peak_AIDC_PCC_shift_kw": max(max(x["peak_AIDC_PCC_shift_kw"] for x in pairs1), max(x["peak_AIDC_PCC_shift_kw"] for x in pairs3)),
            "relief_per_peak_shifted_kw_range_pu_per_kw": [min(x["relief_per_peak_shifted_kw_pu_per_kw"] for x in pairs1+pairs3), max(x["relief_per_peak_shifted_kw_pu_per_kw"] for x in pairs1+pairs3)],
        }
    payload = {
        "artifact_id": "V17_AIDC_POWER_V1_V4R1_7DAY_SCIENCE_COMPARISON_V1", "status": "PASS",
        "classification": v4_results["classification"], "debug_days": list(DEBUG_DAYS),
        "V1": {"modelable_job_fraction": v1["jobs"]/semantic["jobs"], "modelable_GPU_hour_fraction": v1["GPU_hours"]/semantic["GPU_hours"], "modelable_node_equivalent_hour_fraction": v1["GPU_hours"]/semantic["GPU_hours"], "seven_day_flexible_IT_energy_kwh": v1_energy, **aggregate("V1")},
        "V4R1": {"modelable_job_fraction": v4["jobs"]/semantic["jobs"], "modelable_GPU_hour_fraction": v4["GPU_hours"]/semantic["GPU_hours"], "modelable_node_equivalent_hour_fraction": v4["GPU_hours"]/semantic["GPU_hours"], "seven_day_flexible_IT_energy_kwh": v4_energy, "AIDC_only_best_possible_relief_range_pu": [min(row["V4R1_AIDC_only_upper_bound"]["best_possible_relief_pu"] for row in rows), max(row["V4R1_AIDC_only_upper_bound"]["best_possible_relief_pu"] for row in rows)], "restoration_intervention_rate": v4_results["restoration_intervention_rate"], **aggregate("V4R1")},
        "rows": rows, "grid_outcomes_used_for_model_selection": 0,
        "May_scientific_input_reads": 0, "June_scientific_input_reads": 0, "remaining_April_day_runs": 0,
    }
    write_json(output / "V17_AIDC_POWER_V1_V4R1_7DAY_SCIENCE_COMPARISON.json", payload)
    return payload

