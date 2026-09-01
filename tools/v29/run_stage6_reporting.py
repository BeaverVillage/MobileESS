"""Aggregate the frozen V29 four-day development/regression evidence.

This program is reporting-only.  It does not alter a frozen schedule or use
any result to tune the scientific formulation.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.electrical_context import build_electrical_context
from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v28r2.solver_runner import add_grid_rows
from dayahead.v28r2.variable_registry import build_resource_model
from dayahead.v29.carryin import carryin_by_cohort
from dayahead.v29.formulation import materialize_formulation_data_v29


DAYS = ("2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04")
CASES = ("B0", "B1", "B2", "B3")
OUT_NAME = "v29_development_regression_apr01_04"
CAMPAIGN_NAME = "v28r2_april_full_month_preflight"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )


def timestamp(day: str, slot: int) -> str:
    return f"{day}T{slot // 4:02d}:{(slot % 4) * 15:02d}:00+10:00"


def critical_physical(npz_path: Path) -> dict[str, object]:
    with np.load(npz_path) as arrays:
        load = np.asarray(arrays["phase_current_loading_pu"], dtype=float)
        names = np.asarray(arrays["branch_names"]).astype(str)
        phases = np.asarray(arrays["branch_phases"]).astype(str)
        line_indices = np.flatnonzero(np.char.startswith(names, "line."))
        local = np.unravel_index(int(np.argmax(load[:, line_indices])), load[:, line_indices].shape)
        slot, branch = int(local[0]), int(line_indices[local[1]])
        return {
            "critical_row_rho_max": float(load[slot, branch]),
            "critical_line": names[branch].split("::", 1)[0],
            "critical_phase": phases[branch],
            "critical_slot": slot,
        }


def planning_critical(context: object, controls: np.ndarray) -> tuple[float, int, int, str, object]:
    candidates = []
    for slot in range(96):
        coefficient = slot_coefficients(context.legacy_context, context.voltage, context.current, slot)
        current = coefficient.current_constant + controls[slot] @ coefficient.current_matrix
        for branch, name in enumerate(coefficient.branch_names):
            if name.startswith("line."):
                candidates.append((float(current[branch]), slot, branch, str(name), coefficient))
    return max(candidates, key=lambda row: row[0])


def dual_audit(data: object, context: object) -> dict[str, object]:
    from gurobipy import GRB

    registry = build_resource_model(data, context.voltage, "B1", rho=0.1)
    add_grid_rows(registry, context.legacy_context, context.voltage, context.current)
    registry.model.optimize()
    if registry.model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V29_STAGE6_DUAL_AUDIT_STATUS:{data.day}:{registry.model.Status}")
    rack = [constraint for constraint in registry.model.getConstrs() if constraint.ConstrName.startswith("rack_gpu_hard[")]
    terminal = [constraint for constraint in registry.model.getConstrs() if constraint.ConstrName.startswith("service_terminal_reference_parity[")]
    result = {
        "rack_gpu_constraint_count": len(rack),
        "rack_gpu_active_count": sum(abs(float(row.Slack)) <= 1e-6 for row in rack),
        "rack_gpu_max_abs_dual": max((abs(float(row.Pi)) for row in rack), default=0.0),
        "terminal_constraint_count": len(terminal),
        "terminal_max_abs_dual": max((abs(float(row.Pi)) for row in terminal), default=0.0),
    }
    registry.model.dispose()
    return result


def fifo_carryin_usage(initial: np.ndarray, service: np.ndarray, critical_slot: int) -> tuple[float, float, float, float]:
    remaining = initial.astype(float).copy()
    before = at = after = 0.0
    for slot in range(96):
        served = service[:, :, slot].sum(axis=1)
        carry_served = np.minimum(remaining, served)
        amount = float(carry_served.sum())
        if slot < critical_slot:
            before += amount
        elif slot == critical_slot:
            at += amount
        else:
            after += amount
        remaining -= carry_served
    return before, at, after, float(remaining.sum())


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def aggregate(repo: Path, campaign: Path, forensic: Path) -> dict[str, object]:
    artifact = repo / "dayahead/artifacts/v29_grid_responsive_aidc"
    result_root = repo / "frozen_artifacts" / OUT_NAME
    forensic_artifact = forensic / "dayahead/artifacts/v28r2_aidc_grid_value_forensic"
    stage2 = list(csv.DictReader((artifact / "V29_CRITICAL_TIME_FLEXIBILITY_UPPER_BOUND.csv").open(encoding="utf-8-sig")))
    v28_l1 = {row["day"]: float(row["actual_V28_B1_critical_time_L1_action_kw"]) for row in stage2 if float(row["rho_AIDC"]) == 0.1}
    v28_grid_rows = list(csv.DictReader((forensic_artifact / "V28R2_AIDC_VS_MESS_GRID_VALUE.csv").open(encoding="utf-8-sig")))
    v28_weighted = {row["day"]: float(row["AIDC_critical_row_sensitivity_weighted_action"]) for row in v28_grid_rows}

    objective_rows: list[dict[str, object]] = []
    actuation_rows: list[dict[str, object]] = []
    carry_rows: list[dict[str, object]] = []
    movement_rows: list[dict[str, object]] = []
    sensitivity_rows: list[dict[str, object]] = []
    solver_rows: list[dict[str, object]] = []
    opendss_rows: list[dict[str, object]] = []
    actual_rows: list[dict[str, object]] = []
    pi_rows: list[dict[str, object]] = []
    comparison_rows: list[dict[str, object]] = []
    day_summaries: dict[str, object] = {}

    for day in DAYS:
        day_root = result_root / day
        result = load_json(day_root / "V29_DAY_RESULT.json")
        schedules = {
            case: load_json(day_root / "dayahead/schedules" / f"DAYAHEAD_{case}_SCHEDULE.json")
            for case in CASES
        }
        objectives = {case: float(result["objectives"][case]) for case in CASES}
        reductions = {
            "B0_to_B1": objectives["B0"] - objectives["B1"],
            "B0_to_B2": objectives["B0"] - objectives["B2"],
            "B2_to_B3": objectives["B2"] - objectives["B3"],
            "B0_to_B3": objectives["B0"] - objectives["B3"],
        }
        objective_rows.append({
            "day": day, **{f"J_{case}": objectives[case] for case in CASES},
            **{f"{name}_absolute_relief": value for name, value in reductions.items()},
            **{f"{name}_relative_pct": 100.0 * value / objectives[name.split("_to_")[0]] for name, value in reductions.items()},
            "dominance_pass": all(bool(value) for value in result["dominance"].values()),
        })

        data = materialize_formulation_data_v29(repo, day)
        cache = campaign / "frozen_artifacts" / CAMPAIGN_NAME / day / "dayahead/electrical_cache"
        context = build_electrical_context(repo, data, cache)
        b0_controls = np.asarray(schedules["B0"]["controls"], dtype=float)
        critical_value, critical_slot, critical_branch, branch_name, coefficient = planning_critical(context, b0_controls)
        b0_pcc = np.asarray(schedules["B0"]["planning_pcc_power_kw"], dtype=float)
        b1_pcc = np.asarray(schedules["B1"]["planning_pcc_power_kw"], dtype=float)
        delta = b0_pcc[critical_slot] - b1_pcc[critical_slot]
        sensitivity = np.asarray(context.current["current_sensitivity_pu_per_control"], dtype=float)[critical_slot, :12, critical_branch]
        weighted = float(sensitivity @ delta)
        abs_weighted = float(np.abs(sensitivity * delta).sum())
        line, phase = branch_name.rsplit("::", 1)
        actuation = {
            "day": day, "baseline_case": "B0", "optimized_case": "B1",
            "critical_line": line, "critical_phase": phase, "critical_slot": critical_slot,
            "critical_timestamp_fixed_aest": timestamp(day, critical_slot),
            "baseline_planning_normalized_current": critical_value,
            "critical_time_AIDC_L1_action_kw": float(np.abs(delta).sum()),
            "critical_time_aggregate_downshift_kw": float(delta.sum()),
            "critical_time_signed_sensitivity_weighted_relief_pu": weighted,
            "critical_time_absolute_sensitivity_weighted_action_pu": abs_weighted,
            "per_site_B0_minus_B1_pcc_kw": json.dumps(dict(zip(data.aidc_ids, map(float, delta), strict=True)), sort_keys=True),
        }
        actuation_rows.append(actuation)
        for aidc, site_delta, site_sensitivity in zip(data.aidc_ids, delta, sensitivity, strict=True):
            sensitivity_rows.append({
                "day": day, "critical_line": line, "critical_phase": phase, "critical_slot": critical_slot,
                "aidc_id": aidc, "sensitivity_normalized_current_per_kw": float(site_sensitivity),
                "B0_minus_B1_pcc_kw": float(site_delta),
                "signed_contribution_normalized_current": float(site_sensitivity * site_delta),
                "absolute_contribution_normalized_current": abs(float(site_sensitivity * site_delta)),
            })

        initial = carryin_by_cohort(repo, day)
        for case in ("B1", "B3"):
            service = np.asarray(schedules[case]["workload_service_tensor"], dtype=float)
            before, at, after, remaining = fifo_carryin_usage(initial, service, critical_slot)
            carry_rows.append({
                "day": day, "case": case, "attribution_rule": "within-cohort FIFO diagnostic",
                "carryin_queue_nodeh": float(initial.sum()), "carryin_scheduled_before_critical_nodeh": before,
                "carryin_scheduled_at_critical_nodeh": at, "carryin_scheduled_after_critical_nodeh": after,
                "carryin_terminal_unserved_nodeh": remaining,
                "carryin_conservation_error_nodeh": float(initial.sum()) - before - at - after - remaining,
            })

        duals = dual_audit(data, context)
        kappa = np.asarray([KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] for cohort in data.cohort_ids], dtype=float)
        for pair, flexible, reference in (("B0_TO_B1", "B1", "B0"), ("B2_TO_B3", "B3", "B2")):
            x_flex = np.asarray(schedules[flexible]["workload_service_tensor"], dtype=float)
            x_ref = np.asarray(schedules[reference]["workload_service_tensor"], dtype=float)
            flexible_energy = float(np.einsum("c,crt->", kappa, x_flex))
            flexible_peak = float(np.max(np.einsum("c,crt->t", kappa, x_flex) / 0.25))
            total_it_energy = float(np.asarray(schedules[flexible]["site_it_power_kw"], dtype=float).sum() * 0.25)
            change = np.asarray(schedules[flexible]["planning_pcc_power_kw"], dtype=float) - np.asarray(schedules[reference]["planning_pcc_power_kw"], dtype=float)
            boundary_count = 0
            for slot in range(96):
                for index, aidc in enumerate(data.aidc_ids):
                    c1 = data.c1_by_site_slot[(aidc, slot)]
                    low = c1.slope * c1.p_min_kw + c1.intercept_kw
                    high = c1.slope * c1.p_max_kw + c1.intercept_kw
                    ref = b0_pcc[slot, index]
                    limit = 0.1 * ((high - ref) if change[slot, index] >= 0 else (ref - low))
                    if limit > 1e-8 and abs(change[slot, index]) >= limit - 2e-6:
                        boundary_count += 1
            movement_rows.append({
                "day": day, "pair": pair,
                "temporal_relocation_nodeh": float(0.5 * np.abs(x_flex.sum(axis=1) - x_ref.sum(axis=1)).sum()),
                "spatial_slot_relocation_nodeh": float(0.5 * np.abs(x_flex.sum(axis=0) - x_ref.sum(axis=0)).sum()),
                "flexible_IT_energy_kwh": flexible_energy, "flexible_IT_peak_kw": flexible_peak,
                "flexible_IT_share_pct": 100.0 * flexible_energy / total_it_energy,
                "trust_bound_active_site_slots": boundary_count, "trust_bound_total_site_slots": 1152,
                **duals,
            })
        context.voltage.close(); context.current.close()

        equivalence = result["B3_equivalence"]
        resolution = result["increment_resolution"]
        solver_rows.append({
            "day": day, "B3_CL_MC_BD": float(result["B3_solver_objectives"]["CL_MC_BD"]),
            "B3_MONOLITHIC": float(result["B3_solver_objectives"]["MONOLITHIC"]),
            "B3_STANDARD_BD": float(result["B3_solver_objectives"]["STANDARD_BD"]),
            "B3_absolute_solver_spread": max(map(float, result["B3_solver_objectives"].values())) - min(map(float, result["B3_solver_objectives"].values())),
            "B3_relative_solver_range": float(equivalence["relative_objective_range"]),
            "equivalence_tolerance": float(equivalence["tolerance"]), "equivalence_status": equivalence["status"],
            "operational_B2_minus_B3_increment": reductions["B2_to_B3"],
            "increment_resolution_status": resolution["status"],
            "all_solver_improvement_signs_identical": resolution["all_improvement_signs_identical"],
        })

        for key, summary in result["OpenDSS"].items():
            namespace, case = key.split("/")
            folder_namespace = {"DA": "dayahead", "ACT": "actual", "PI": "pi"}[namespace]
            physical = critical_physical(day_root / folder_namespace / "opendss" / case / "OPENDSS_PHASE_ARRAYS.npz")
            opendss_rows.append({
                "day": day, "namespace": namespace, "case": case,
                "rho_max_AC": float(summary["rho_max_AC"]), "p95_loading": float(summary["p95_loading"]),
                "p99_loading": float(summary["p99_loading"]), "Vmin_pu": float(summary["Vmin_pu"]),
                "Vmax_pu": float(summary["Vmax_pu"]), "losses_kwh": float(summary["losses_kwh"]),
                **physical, "critical_timestamp_fixed_aest": timestamp(day, int(physical["critical_slot"])),
                "convergence_count": int(summary["convergence_count"]), "clean_engine_count": int(summary["clean_engine_count"]),
                "physical_violation_observed": bool(summary["physical_violation"]),
            })

        for case in ("R0", "B0", "B1", "B2", "B3"):
            with np.load(day_root / "actual/replay" / case / "ACTUAL_REPLAY_ARRAYS.npz") as arrays:
                executed = float(np.asarray(arrays["workload_executed_nodeh"]).sum())
                missed = float(np.asarray(arrays["workload_unexecuted_da_nodeh"]).sum())
                backlog = float(np.asarray(arrays["workload_backlog_nodeh"])[-1].sum())
                terminal_soc = np.asarray(arrays["mess_energy_kwh"])[-1]
                reasons = np.asarray(arrays["mess_reasons_96x4"]).astype(str)
                planned_p = np.asarray(schedules[case]["mess_p_kw"], dtype=float) if case != "R0" else np.zeros((96, 4))
                planned_q = np.asarray(schedules[case]["mess_q_kvar"], dtype=float) if case != "R0" else np.zeros((96, 4))
                command = (np.abs(planned_p) + np.abs(planned_q)) > 1e-8
                missed_commands = int(np.count_nonzero(command & (reasons != "EXECUTED")))
            actual_rows.append({
                "day": day, "case": case, "executed_workload_nodeh": executed,
                "missed_workload_nodeh": missed, "terminal_backlog_nodeh": backlog,
                "MESS_missed_command_count": missed_commands,
                "terminal_MESS_soc_kwh": json.dumps(list(map(float, terminal_soc))),
                "terminal_MESS_soc_error_from_DA_target_kwh": float(result["actual"][case]["terminal_mess_energy_error_from_DA_target_kwh"]),
                "actual_rho_max_AC": float(result["OpenDSS"][f"ACT/{case}"]["rho_max_AC"]),
                "actual_optimizer_calls": int(result["actual"][case]["actual_reoptimization_calls"]),
                "workload_mass_error_nodeh": float(result["actual"][case]["workload_mass_error_nodeh"]),
            })

        da_b3_ac = float(result["OpenDSS"]["DA/B3"]["rho_max_AC"])
        act_b3_ac = float(result["OpenDSS"]["ACT/B3"]["rho_max_AC"])
        pi_b3_ac = float(result["OpenDSS"]["PI/B3"]["rho_max_AC"])
        pi_rows.append({
            "day": day, "DA_B3_planning_objective": objectives["B3"], "PI_B3_planning_objective": float(result["PI"]["objective"]),
            "PI_minus_DA_planning_objective": float(result["PI"]["objective"]) - objectives["B3"],
            "DA_B3_rho_max_AC": da_b3_ac, "ACT_B3_rho_max_AC": act_b3_ac, "PI_B3_rho_max_AC": pi_b3_ac,
            "ACT_minus_PI_rho_max_AC_regret": act_b3_ac - pi_b3_ac,
            "DA_minus_PI_rho_max_AC": da_b3_ac - pi_b3_ac,
        })

        comparison = {
            "day": day, "carryin_queue_nodeh": float(result["carryin_nodeh"]),
            "V28_critical_time_AIDC_L1_action_kw": v28_l1[day],
            "V29_critical_time_AIDC_L1_action_kw": actuation["critical_time_AIDC_L1_action_kw"],
            "V29_minus_V28_L1_action_kw": float(actuation["critical_time_AIDC_L1_action_kw"]) - v28_l1[day],
            "V28_signed_sensitivity_weighted_action_pu": v28_weighted[day],
            "V29_signed_sensitivity_weighted_action_pu": weighted,
            "V29_minus_V28_signed_weighted_action_pu": weighted - v28_weighted[day],
            "carryin_positive_and_action_decreased": float(result["carryin_nodeh"]) > 0 and float(actuation["critical_time_AIDC_L1_action_kw"]) < v28_l1[day],
        }
        comparison_rows.append(comparison)
        day_summaries[day] = {"objectives": objectives, "reductions": reductions, "actuation": actuation, "comparison": comparison}

    pooled_v28_l1 = float(np.mean([row["V28_critical_time_AIDC_L1_action_kw"] for row in comparison_rows]))
    pooled_v29_l1 = float(np.mean([row["V29_critical_time_AIDC_L1_action_kw"] for row in comparison_rows]))
    pooled_v28_weighted = float(np.mean([row["V28_signed_sensitivity_weighted_action_pu"] for row in comparison_rows]))
    pooled_v29_weighted = float(np.mean([row["V29_signed_sensitivity_weighted_action_pu"] for row in comparison_rows]))
    mechanism_improved = pooled_v29_l1 > pooled_v28_l1 and pooled_v29_weighted > pooled_v28_weighted
    comparison_rows.append({
        "day": "POOLED_MEAN", "carryin_queue_nodeh": float(np.mean([row["carryin_queue_nodeh"] for row in comparison_rows])),
        "V28_critical_time_AIDC_L1_action_kw": pooled_v28_l1, "V29_critical_time_AIDC_L1_action_kw": pooled_v29_l1,
        "V29_minus_V28_L1_action_kw": pooled_v29_l1 - pooled_v28_l1,
        "V28_signed_sensitivity_weighted_action_pu": pooled_v28_weighted,
        "V29_signed_sensitivity_weighted_action_pu": pooled_v29_weighted,
        "V29_minus_V28_signed_weighted_action_pu": pooled_v29_weighted - pooled_v28_weighted,
        "carryin_positive_and_action_decreased": "N/A", "MECHANISM_IMPROVED": mechanism_improved,
    })

    outputs = {
        "V29_4DAY_OBJECTIVE_RESULTS.csv": objective_rows,
        "V29_4DAY_AIDC_ACTUATION.csv": actuation_rows,
        "V29_4DAY_CARRYIN_USAGE.csv": carry_rows,
        "V29_4DAY_WORKLOAD_MOVEMENT.csv": movement_rows,
        "V29_4DAY_CRITICAL_SENSITIVITY.csv": sensitivity_rows,
        "V29_4DAY_SOLVER_RESOLUTION.csv": solver_rows,
        "V29_4DAY_OPENDSS_RESULTS.csv": opendss_rows,
        "V29_4DAY_ACTUAL_RESULTS.csv": actual_rows,
        "V29_4DAY_PI_REGRET.csv": pi_rows,
        "V29_V28_VS_V29_MECHANISM_COMPARISON.csv": comparison_rows,
    }
    for name, rows in outputs.items():
        write_csv(artifact / name, rows)
    summary = {
        "artifact_id": "V29_STAGE6_AGGREGATE_V1", "evaluation_name": "V29_DEVELOPMENT_REGRESSION_APR01_04",
        "status": "PASS", "days": day_summaries,
        "pooled": {
            "V28_critical_time_AIDC_L1_action_kw": pooled_v28_l1,
            "V29_critical_time_AIDC_L1_action_kw": pooled_v29_l1,
            "V28_signed_sensitivity_weighted_action_pu": pooled_v28_weighted,
            "V29_signed_sensitivity_weighted_action_pu": pooled_v29_weighted,
            "MECHANISM_IMPROVED": mechanism_improved,
        },
        "increment_resolution_statuses": {row["day"]: row["increment_resolution_status"] for row in solver_rows},
        "opendss_trajectory_count": len(opendss_rows),
        "opendss_solve_count": sum(int(row["convergence_count"]) for row in opendss_rows),
        "scientific_retuning_after_result": False,
        "git_head_at_reporting": git(repo, "rev-parse", "HEAD"),
    }
    write_json(artifact / "V29_STAGE6_AGGREGATE.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-repo", type=Path, required=True)
    parser.add_argument("--forensic-repo", type=Path, required=True)
    args = parser.parse_args()
    summary = aggregate(REPO, args.campaign_repo.resolve(), args.forensic_repo.resolve())
    print(json.dumps(summary["pooled"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
