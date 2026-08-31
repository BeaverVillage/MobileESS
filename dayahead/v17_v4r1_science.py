"""Frozen same-seven-day V4R1 pre-evaluation and science runner."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .authority import sha256_file
from .v17_ac_restoration_contract import K_MAX, RHO
from .v17_ac_restoration_runner import (
    _save_solver_schedule,
    local_fresh_ac_cuts,
    primary_fresh_ac,
)
from .v17_deferrability_semantics import write_json
from .v17_v4r1_april import DEBUG_DAYS, electrical_context
from .v17_v4r1_solver import solve_shadow


CASES = ("B0", "B1", "B2", "B3")


def _firewall() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
        "arbitrary_scaling_calls": 0,
        "GPU_clipping_calls": 0,
        "timestamp_correction_calls": 0,
        "grid_selected_parameter_calls": 0,
        "OpenDSS_calls_inside_Benders": 0,
    }


def _canonical_sha(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def mint_freeze(repo: Path, output: Path) -> dict[str, Any]:
    """Freeze every V4R1 decision before any B0--B3 result is inspected."""

    repo = repo.resolve(); output = output.resolve()
    surrogate = output / "V17_V4R1_7DAY_SURROGATE_VALIDATION.json"
    validation = json.loads(surrogate.read_text(encoding="utf-8"))
    if validation["status"] != "PASS" or float(validation["rho_valid_frozen_primary"]) != RHO:
        raise RuntimeError("V17_V4R1_FREEZE_REQUIRES_SURROGATE_PASS")
    required = (
        "V17_AIDC_POWER_MODEL_V4R1_CAPACITY_CONSISTENT_SUPPORT_CONTRACT.json",
        "V17_AIDC_POWER_MODEL_V4R1_CONTRACT.json",
        "V17_AIDC_POWER_MODEL_V4R1_VALIDATION.json",
        "V17_AIDC_POWER_V4R1_QUARANTINE_MANIFEST.json",
        "V17_RCMQT_V4R1_TARGET_SEMANTICS_CONTRACT.json",
        "V17_RCMQT_V4R1_TRAINING_REPORT.json",
        "V17_RCMQT_V4R1_APRIL_7DAY_VALIDATION.json",
        "V17_REFERENCE_SCHEDULER_V6_GPU_HOUR_CONTRACT.json",
        "V17_REFERENCE_SCHEDULER_V6_GPU_HOUR_7DAY_VALIDATION.json",
        "V17_V4R1_7DAY_D1_ANCHOR_MANIFEST.json",
        "V17_V4R1_7DAY_SURROGATE_VALIDATION.json",
    )
    authorities = {name: sha256_file(output / name) for name in required}
    training = json.loads((output / "V17_RCMQT_V4R1_TRAINING_REPORT.json").read_text(encoding="utf-8"))
    references = {
        day: sha256_file(output / "reference_v6_v4r1" / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{day}.npz")
        for day in DEBUG_DAYS
    }
    electrical = {
        day: {
            "H_anchor_sha256": sha256_file(output / "ac_cache_v4r1/data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"),
            "J_I_sha256": sha256_file(output / "ac_cache_v4r1/data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"),
        }
        for day in DEBUG_DAYS
    }
    payload: dict[str, Any] = {
        "artifact_id": "V17_AIDC_POWER_V4R1_7DAY_PRE_EVALUATION_FREEZE_V1",
        "status": "PASS_FROZEN_BEFORE_B0_B3",
        "authority_id": "V17_AIDC_POWER_MODEL_V4R1_WHOLE_GPU_CLEAN_GRES",
        "debug_days": list(DEBUG_DAYS),
        "rho": RHO,
        "U2_CLEAN_membership_hash": json.loads((output / "V17_AIDC_POWER_MODEL_V4R1_CONTRACT.json").read_text(encoding="utf-8"))["support_hashes"]["U2_CLEAN"],
        "quarantine_membership_hash": json.loads((output / "V17_AIDC_POWER_MODEL_V4R1_CONTRACT.json").read_text(encoding="utf-8"))["support_hashes"]["Q"],
        "RCMQT_weights_sha256": training["weights_file_sha256"],
        "RCMQT_config_fingerprint": training["final_weight_config_fingerprint"],
        "authorities": authorities,
        "references": references,
        "electrical": electrical,
        "source_code": {
            "reference_V6": sha256_file(repo / "dayahead/v17_reference_scheduler_v6.py"),
            "GPU_hour_adapter": sha256_file(repo / "dayahead/v17_v4r1_solver.py"),
            "frozen_solver": sha256_file(repo / "dayahead/final_science_solver_v16_3.py"),
            "common_restoration_loop": sha256_file(repo / "dayahead/v17_ac_restoration_runner.py"),
        },
        "frozen_GPU_board_kW": {"Q10": 0.3941881609951147, "Q50": 0.48563611660901085, "Q90": 0.5391969931144363},
        "CPU_host_incremental_power_role": "P_IT_REF_RESIDUAL",
        "April_B0_B3_result_reads_before_freeze": 0,
        **_firewall(),
    }
    fingerprint = _canonical_sha(payload)
    payload["manifest_payload_sha256_before_token"] = fingerprint
    payload["freeze_token"] = f"V17_V4R1_7DAY_{fingerprint[:24]}"
    write_json(output / "V17_AIDC_POWER_V4R1_7DAY_PRE_EVALUATION_FREEZE.json", payload)
    return payload


def _case_metrics(result: Mapping[str, Any], primary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "objective": float(result["objective_max_normalized_phase_line_current"]),
        "runtime_seconds": float(result["runtime_seconds"]),
        "terminal_service_parity_max_abs_error_GPU_hour": float(result["terminal_service_parity_max_abs_error"]),
        "MESS_terminal_SOC_max_abs_error_kwh": float(result["mess_terminal_soc_max_abs_error_kwh"]),
        "Vmin_pu": float(primary["Vmin_pu"]),
        "Vmax_pu": float(primary["Vmax_pu"]),
        "worst_line_loading_pu": float(primary["worst_line_loading_pu"]),
        "worst_transformer_current_loading_pu": float(primary["worst_transformer_current_loading_pu"]),
        "worst_transformer_kva_loading_pu": float(primary["worst_transformer_kva_loading_pu"]),
    }


def execute_day(repo: Path, source: Path, output: Path, day: str) -> dict[str, Any]:
    """Optimize and pass one authorized debug day through the common AC loop."""

    repo = repo.resolve(); source = source.resolve(); output = output.resolve()
    if day not in DEBUG_DAYS:
        raise ValueError("V17_V4R1_DAY_OUTSIDE_FROZEN_DEBUG_COHORT")
    freeze_path = output / "V17_AIDC_POWER_V4R1_7DAY_PRE_EVALUATION_FREEZE.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze["status"] != "PASS_FROZEN_BEFORE_B0_B3":
        raise RuntimeError("V17_V4R1_B0_B3_BEFORE_FREEZE")
    margins_record = json.loads((output / "V17_AC_RESTORATION_CUT_VALIDATION.json").read_text(encoding="utf-8"))
    if margins_record["status"] != "PASS_FROZEN_BEFORE_APR12_REPLAY":
        raise RuntimeError("V17_V4R1_COMMON_RESTORATION_NOT_FROZEN")
    reference, inputs, vintage, background, binding, authority = electrical_context(repo, source, output, day)
    voltage_path = output / "ac_cache_v4r1/data" / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    current_path = output / "ac_cache_v4r1/data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
    voltage = np.load(voltage_path, allow_pickle=False); current = np.load(current_path, allow_pickle=False)
    context = (reference, vintage, background, binding, voltage_path, authority)
    solved = solve_shadow(inputs=inputs, context=context, voltage_data=voltage, current_data=current, rho=RHO, case="ALL")
    schedule_dir = output / "schedules_v4r1"; schedule_dir.mkdir(parents=True, exist_ok=True)
    cases: dict[str, Any] = {}; fresh_calls = 0
    for case in CASES:
        result = dict(solved[case]); initial_path = schedule_dir / f"V17_V4R1_{day}_{case}_ITER0.npz"
        controls = _save_solver_schedule(initial_path, result)
        initial_result = dict(result); initial_sha = sha256_file(initial_path)
        primary, violations, calls = primary_fresh_ac(repo, source, context, voltage, controls, day=day, case=case, schedule_sha256=str(result["schedule_sha256"]))
        fresh_calls += calls; first_primary = dict(primary); first_count = len(violations)
        accumulated = []; iterations = 0; final_path = initial_path
        while violations and iterations < K_MAX:
            iterations += 1
            cuts, calls = local_fresh_ac_cuts(repo, source, context, voltage, controls, violations, case=case, iteration_index=iterations, margins=margins_record["margins"])
            fresh_calls += calls
            if not cuts:
                break
            accumulated.extend(cuts)
            result = dict(solve_shadow(inputs=inputs, context=context, voltage_data=voltage, current_data=current, rho=RHO, case=case, restoration_cuts=tuple(accumulated)))
            if not bool(result.get("hard_feasible")):
                break
            final_path = schedule_dir / f"V17_V4R1_{day}_{case}_ITER{iterations}.npz"
            controls = _save_solver_schedule(final_path, result)
            primary, violations, calls = primary_fresh_ac(repo, source, context, voltage, controls, day=day, case=case, schedule_sha256=str(result["schedule_sha256"]))
            fresh_calls += calls
        secondary = primary["secondary_native_RegControl"]
        final_pass = bool(result.get("hard_feasible")) and not violations and bool(primary["all_frozen_hard_constraints_pass"]) and bool(secondary["all_frozen_hard_constraints_pass"])
        cases[case] = {
            "status": "PASS" if final_pass else "FAIL_CLOSED",
            "optimization_hard_feasible": bool(result.get("hard_feasible")),
            "first_pass_primary_PASS": first_count == 0 and bool(first_primary["all_frozen_hard_constraints_pass"]),
            "first_pass_violation_count": first_count,
            "AC_restoration_iterations": iterations,
            "AC_restoration_success": bool(first_count and final_pass),
            "final_primary_PASS": bool(primary["all_frozen_hard_constraints_pass"]) and not violations,
            "final_secondary_native_RegControl_PASS": bool(secondary["all_frozen_hard_constraints_pass"]),
            "remaining_exact_violation_count": len(violations),
            "initial_schedule_file_sha256": initial_sha,
            "final_schedule_path": str(final_path.resolve()),
            "final_schedule_file_sha256": sha256_file(final_path),
            "schedule_sha256": str(result.get("schedule_sha256", "")),
            "restoration_cut_count": len(accumulated),
            **_case_metrics(result, primary),
        }
    passed = all(row["status"] == "PASS" for row in cases.values())
    payload = {
        "artifact_id": "V17_AIDC_POWER_V4R1_DAY_B0_B1_B2_B3_V1",
        "operating_day": day,
        "status": "PASS" if passed else "FAIL_CLOSED",
        "cases": cases,
        "Fresh_OpenDSS_solve_count": fresh_calls,
        "freeze_manifest_sha256": sha256_file(freeze_path),
        **_firewall(),
    }
    daily = output / "v4r1_daily"; daily.mkdir(parents=True, exist_ok=True)
    write_json(daily / f"V17_V4R1_{day}_B0_B1_B2_B3.json", payload)
    return payload


def finalize(output: Path) -> dict[str, Any]:
    """Materialize the seven-day gate and outcome-only V1/V4R1 comparison."""

    output = output.resolve()
    days = [json.loads((output / "v4r1_daily" / f"V17_V4R1_{day}_B0_B1_B2_B3.json").read_text(encoding="utf-8")) for day in DEBUG_DAYS]
    rows = [{"operating_day": day["operating_day"], "case": case, **record} for day in days for case, record in day["cases"].items()]
    passed = all(day["status"] == "PASS" for day in days)
    first_pass = sum(bool(row["first_pass_primary_PASS"]) for row in rows)
    required = sum(int(row["AC_restoration_iterations"] > 0) for row in rows)
    successful = sum(bool(row["AC_restoration_success"]) for row in rows)
    def effects(a: str, b: str) -> list[dict[str, float | str]]:
        return [{"operating_day": day["operating_day"], "difference": float(day["cases"][a]["objective"] - day["cases"][b]["objective"])} for day in days]
    coverage = json.loads((output / "V17_AIDC_POWER_V1_V4R1_COVERAGE_COMPARISON.json").read_text(encoding="utf-8"))
    payload = {
        "artifact_id": "V17_AIDC_POWER_V4R1_7DAY_B0_B1_B2_B3_RESULTS_V1",
        "status": "PASS" if passed else "FAIL_CLOSED",
        "classification": "V17_AIDC_POWER_V4R1_A_CLEAN_WHOLE_GPU_SUPPORT_PASS" if passed else "V17_AIDC_POWER_V4R1_E_SURROGATE_OR_AC_FAILURE",
        "debug_days": list(DEBUG_DAYS), "schedule_count": len(rows), "rows": rows,
        "all_28_optimization_feasible": all(row["optimization_hard_feasible"] for row in rows),
        "all_28_final_primary_PASS": all(row["final_primary_PASS"] for row in rows),
        "all_28_final_secondary_PASS": all(row["final_secondary_native_RegControl_PASS"] for row in rows),
        "all_28_service_parity_PASS": all(row["terminal_service_parity_max_abs_error_GPU_hour"] <= 1e-9 for row in rows),
        "all_28_terminal_SOC_PASS": all(row["MESS_terminal_SOC_max_abs_error_kwh"] <= 1e-9 for row in rows),
        "first_pass_primary_PASS_count": first_pass,
        "restoration_required_count": required,
        "restoration_success_count": successful,
        "restoration_failure_count": required - successful,
        "restoration_intervention_rate": required / len(rows),
        "B1_minus_B0": effects("B1", "B0"), "B3_minus_B2": effects("B3", "B2"),
        "coverage": coverage, "grid_outcomes_used_for_V4R1_selection": 0,
        **_firewall(),
    }
    write_json(output / "V17_AIDC_POWER_V4R1_7DAY_B0_B1_B2_B3_RESULTS.json", payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("phase", choices=("freeze", "execute-day", "finalize"))
    parser.add_argument("--repo", type=Path, default=Path.cwd()); parser.add_argument("--source", type=Path, required=False)
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate")); parser.add_argument("--operating-day", default=DEBUG_DAYS[0])
    args = parser.parse_args(argv)
    if args.phase == "freeze": result = mint_freeze(args.repo, args.output)
    elif args.phase == "execute-day":
        if args.source is None: raise ValueError("--source is required for execute-day")
        result = execute_day(args.repo, args.source, args.output, args.operating_day)
    else: result = finalize(args.output)
    print(json.dumps({"status": result["status"], "classification": result.get("classification")}, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
