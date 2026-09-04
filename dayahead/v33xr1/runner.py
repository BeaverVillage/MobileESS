"""Run the isolated Apr-04 V33X-R1 E1 Fresh-voltage-cut repair."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.grid_lp import V_MAX_SQUARED
from dayahead.v28r2.actual_replay import replay_actual_case
from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.electrical_context import build_electrical_context, with_realized_background
from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU
from dayahead.v28r2.source_cache import day_root
from dayahead.v28r2.workload_replay import materialize_actual_workload
from dayahead.v29r2.apr04_runner import _fresh_row, _pi_data
from dayahead.v29r2.formulation import materialize_formulation_data_v29r2
from dayahead.v29r3.forensic import _electrical_context, _initial_actual
from dayahead.v30.contracts import write_json
from dayahead.v30.dayahead_formulation import load_frozen_schedules
from dayahead.v30.four_case_runner import _mapping, _recourse_trajectory
from dayahead.v30.reporting import write_csv
from dayahead.v33x.full_grid_recourse import FullGridRecourseResult
from dayahead.v33x.runner import VOLTAGE_NAME, CURRENT_NAME

from .contracts import BRANCH, DAY, MASS_TOLERANCE_NODEH, MAX_REPAIR_ITERATIONS, STARTING_HEAD, V_MAX_PU
from .voltage_cut_recourse import (
    LocalVoltageCut,
    LocalVoltageCutInfeasible,
    assess_local_cut_feasibility,
    solve_causal_suffix_with_voltage_cuts,
)


OUT_REL = Path("dayahead/artifacts/v33x_r1_e1_voltage_cuts")
V33X_OUT = Path("dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc")
V30_OUT = Path("dayahead/artifacts/v30_two_stage_aidc_recourse")
CUT_ACTIVE_TOLERANCE_PU = 1e-7


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"V33XR1_JSON_OBJECT_REQUIRED:{path}")
    return value


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _bool(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def _sha_array(value: object) -> str:
    return canonical_sha256(np.asarray(value).tolist())


def _e2_untouched(repo: Path) -> bool:
    paths = (
        "dayahead/v33x/headroom_stage1.py",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_B1_DAYAHEAD_SCHEDULE.json",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_B3_DAYAHEAD_SCHEDULE.json",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_FORMULATION_CONTRACT.json",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_FRESH_OPENDSS_RESULTS.csv",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_LEVERAGE_MAP.json",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_LEVERAGE_MAP_SHA256.json",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_RECOURSE_LEDGER.csv",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_REVIEW.json",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_SERVICE_PARITY_AUDIT.json",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_STAGE1_HEADROOM.csv",
        "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc/V33X_E2_STAGE2_RESULTS.csv",
    )
    return not bool(_git(repo, "diff", "--name-only", STARTING_HEAD, "--", *paths))


def _fresh_raw(repo: Path, source_repo: Path, trajectory: object, voltage_path: Path, current_path: Path):
    context = _electrical_context(repo, source_repo, trajectory, voltage_path, current_path)
    try:
        return run_fresh_opendss(repo=repo, context=context, voltage=context.voltage, trajectory=trajectory)
    finally:
        context.voltage.close()
        context.current.close()


def _mass_error(result: FullGridRecourseResult, arrivals: np.ndarray, initial: np.ndarray) -> float:
    summary = result.recourse.summary
    source = float(initial.sum() + arrivals.sum() - result.recourse.executed_nodeh.sum() - result.recourse.backlog_nodeh[-1].sum())
    return max(abs(source), abs(float(summary["authorization_mass_identity_error_nodeh"])))


def _iteration_row(
    iteration: int,
    result: FullGridRecourseResult,
    fresh: object,
    arrivals: np.ndarray,
    initial: np.ndarray,
    *,
    cuts_added: int,
    cumulative_cuts: int,
    replay_start_slot: int,
    prefix_reused: bool,
) -> dict[str, object]:
    summary = result.recourse.summary
    authorized = float(summary["DA_AUTHORIZED"])
    available = float(summary["ACTUAL_AVAILABLE"])
    executed = float(summary["EXECUTED_TOTAL"])
    fresh_summary = fresh.summary
    return {
        "iteration": iteration,
        "case": "B1",
        "status": "INITIAL_UNCUT" if iteration == 0 else "CUT_REPAIRED",
        "replay_start_slot": replay_start_slot,
        "causal_prefix_reused": prefix_reused,
        "cuts_added": cuts_added,
        "cumulative_cuts": cumulative_cuts,
        "DA_authorized_nodeh": authorized,
        "Actual_source_available_nodeh": available,
        "executed_nodeh": executed,
        "execution_ratio": executed / authorized,
        "availability_conditioned_execution_ratio": executed / available,
        "same_site_recourse_nodeh": float(summary["EXECUTED_SAME_SITE_RECOURSE"]),
        "cross_site_recourse_nodeh": float(summary["EXECUTED_CROSS_SITE_RECOURSE"]),
        "rack_blocked_nodeh": float(summary["TRUE_RACK_CAPACITY_LIMIT"]),
        "grid_cut_blocked_nodeh": float(summary["GRID_SAFETY_BLOCKED"]),
        "terminal_backlog_nodeh": float(summary["TERMINAL_BACKLOG"]),
        "mass_conservation_error_nodeh": _mass_error(result, arrivals, initial),
        "future_Actual_reads": int(result.recourse.future_actual_reads),
        "Fresh_rho_AC": float(fresh_summary["rho_max_AC"]),
        "Fresh_Vmin_pu": float(fresh_summary["Vmin_pu"]),
        "Fresh_Vmax_pu": float(fresh_summary["Vmax_pu"]),
        "Fresh_voltage_violation_count": int(fresh_summary["voltage_violation_count"]),
        "Fresh_line_current_violation_count": int(fresh_summary["line_current_violation_count"]),
        "Fresh_transformer_current_violation_count": int(fresh_summary["transformer_current_violation_count"]),
        "Fresh_transformer_kva_violation_count": int(fresh_summary["transformer_kva_violation_count"]),
        "Fresh_convergence_count": int(fresh_summary["convergence_count"]),
    }


def _make_cuts(
    iteration: int,
    result: FullGridRecourseResult,
    fresh: object,
    coefficients: Sequence[object],
    trajectory: object,
) -> tuple[list[LocalVoltageCut], list[dict[str, object]]]:
    rows = [row for row in fresh.violation_rows() if row["kind"] == "VOLTAGE"]
    node_lookup = {str(name).lower(): index for index, name in enumerate(fresh.node_names)}
    cuts: list[LocalVoltageCut] = []
    audits: list[dict[str, object]] = []
    for ordinal, violation in enumerate(rows, start=1):
        value = float(violation["value"])
        if value <= V_MAX_PU:
            raise RuntimeError("V33XR1_LOWER_VOLTAGE_CUT_NOT_AUTHORIZED")
        slot = int(violation["slot"])
        node = str(violation["asset"])
        node_index = node_lookup[node.lower()]
        diagnostics = result.slot_diagnostics[slot]
        planning_model_p = np.asarray(diagnostics["site_p_kw"], dtype=float)
        p_anchor = np.asarray(trajectory.pcc_p_kw[slot], dtype=float)
        squared_gradient = np.asarray(coefficients[slot].voltage_matrix, dtype=float)[:12, node_index]
        planning_model_voltage = float(diagnostics["planning_voltage_pu_by_node"][node_index])
        planning_voltage_squared = planning_model_voltage**2 + squared_gradient @ (p_anchor - planning_model_p)
        planning_voltage = float(np.sqrt(max(planning_voltage_squared, 0.0)))
        sensitivity = squared_gradient / (2.0 * planning_voltage)
        rhs = float(V_MAX_PU - value + sensitivity @ p_anchor)
        cut_id = f"I{iteration:02d}_B1_T{slot:02d}_N{node_index:03d}_{ordinal:02d}"
        bus = node.rsplit(".", 1)[0] if "." in node else node
        cut = LocalVoltageCut(
            cut_id, iteration, "B1", slot, node_index, node, bus,
            str(violation["phase"]), tuple(map(float, p_anchor)),
            tuple(map(float, sensitivity)), rhs,
        )
        cut.validate()
        cuts.append(cut)
        audits.append({
            "cut_id": cut_id,
            "iteration": iteration,
            "case": "B1",
            "bus": bus,
            "node": node,
            "phase": str(violation["phase"]),
            "slot": slot,
            "Fresh_voltage_before_cut_pu": value,
            "planning_voltage_before_cut_pu": planning_voltage,
            "Fresh_minus_planning_residual_pu": value - planning_voltage,
            "AIDC_p_k_vector_kw": json.dumps(list(map(float, p_anchor)), separators=(",", ":")),
            "planning_model_AIDC_p_vector_kw": json.dumps(list(map(float, planning_model_p)), separators=(",", ":")),
            "planning_sensitivity_vector_pu_per_kw": json.dumps(list(map(float, sensitivity)), separators=(",", ":")),
            "cut_RHS_pu": rhs,
            "cut_formula": "V_FRESH_k + a_k^T(p_t-p_k) <= 1.05",
            "arbitrary_margin_pu": 0.0,
        })
    return cuts, audits


def _stage_inputs(repo: Path, source_repo: Path, electrical_cache: Path):
    schedules = load_frozen_schedules(repo)
    actual = materialize_actual_workload(source_repo, DAY)
    initial = _initial_actual(repo, COHORT_IDS)
    mobility = _json(day_root(source_repo, DAY) / "traffic_mobility.json")["mess"]
    _racks, owners, power_weights, gpu_weights = _mapping(repo)
    residual_gpu = (actual.total_h100_gpu - actual.flexible_natural_gpu)[:, None] * gpu_weights[None, :]
    capacity = np.maximum(0.0, (CASE_CAPACITY_GPU * gpu_weights[None, :] - residual_gpu) * 0.25 / 4.0)
    fixed = {
        case: replay_actual_case(source_repo, DAY, schedules[case], actual, mobility, initial_backlog_nodeh=initial)
        for case in ("B0", "B1")
    }
    voltage_path = electrical_cache / "data" / VOLTAGE_NAME
    current_path = electrical_cache / "data" / CURRENT_NAME
    voltage = np.load(voltage_path, allow_pickle=False)
    current = np.load(current_path, allow_pickle=False)
    da_data = materialize_formulation_data_v29r2(repo, DAY, "S_NOM")
    base_context = build_electrical_context(repo, da_data, electrical_cache)
    aemo = pd.read_parquet(day_root(source_repo, DAY) / "aemo_actual.parquet")
    actual_context = with_realized_background(
        repo, base_context, timestamps_96=aemo["ts_fixed_aest_end"], demand_mw_96=aemo["demand_mw"],
        pv_mw_96=aemo["rooftop_pv_mw"], aidc_plan_kw_96x12=fixed["B0"].exact_pcc_p_kw,
    )
    coefficients = tuple(slot_coefficients(actual_context.legacy_context, voltage, current, slot) for slot in range(96))
    actual_data = _pi_data(repo, actual, initial)
    return schedules, actual, initial, mobility, owners, power_weights, gpu_weights, capacity, fixed, coefficients, actual_data, voltage, current, base_context, actual_context, voltage_path, current_path


def run(repo: Path, source_repo: Path, electrical_cache: Path) -> dict[str, object]:
    repo = repo.resolve()
    source_repo = source_repo.resolve()
    electrical_cache = electrical_cache.resolve()
    if _git(repo, "branch", "--show-current") != BRANCH or _git(repo, "rev-parse", "HEAD") != STARTING_HEAD:
        raise RuntimeError("V33XR1_STARTING_AUTHORITY_MISMATCH")
    if not _e2_untouched(repo):
        raise RuntimeError("V33XR1_E2_CHANGED")
    out = repo / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    original_v33x_tree = _git(repo, "rev-parse", f"{STARTING_HEAD}:{V33X_OUT.as_posix()}")
    original_e1_rows = {row["case"]: row for row in _csv(repo / V33X_OUT / "V33X_E1_STAGE2_RESULTS.csv")}
    original_e1_fresh = {row["case"]: row for row in _csv(repo / V33X_OUT / "V33X_E1_FRESH_OPENDSS_RESULTS.csv")}
    e0_rows = {row["case"]: row for row in _csv(repo / V33X_OUT / "V33X_E0_E1_E2_COMPARISON.csv") if row["variant"] == "E0_CURRENT"}
    baseline_fresh = {row["case"]: row for row in _csv(repo / V30_OUT / "V30_APR04_FRESH_OPENDSS_RESULTS.csv")}

    stage = _stage_inputs(repo, source_repo, electrical_cache)
    schedules, actual, initial, mobility, owners, power_weights, gpu_weights, capacity, fixed, coefficients, actual_data, voltage, current, base_context, actual_context, voltage_path, current_path = stage
    try:
        b1_da_sha = str(schedules["B1"]["schedule_sha256"])
        contract = {
            "artifact_id": "V33XR1_CUT_CONTRACT_V1",
            "status": "FROZEN_BEFORE_REPAIR",
            "day": DAY,
            "starting_SHA": STARTING_HEAD,
            "branch": BRANCH,
            "scope": "E1_ONLY",
            "FRESH_AC_CUT_GENERATION_USED": True,
            "FINAL_AUTHORITY": False,
            "maximum_additional_repair_iterations": MAX_REPAIR_ITERATIONS,
            "cut_scope": "VIOLATED_BUS_PHASE_SLOT_ONLY",
            "cut_formula": "V_FRESH_k + a_k^T(p_t-p_k) <= V_MAX",
            "V_MAX_pu": V_MAX_PU,
            "arbitrary_voltage_margin": False,
            "planning_gradient_source": "frozen Apr-04 voltage_matrix with fixed-PF coupled AIDC control",
            "planning_gradient_voltage_conversion": "dV/dP = d(V_squared)/dP / (2*planning_V_at_p_k)",
            "Stage2_objective": ["MAX_SERVICE", "MIN_MAX_PLANNING_LINE_CURRENT", "MIN_DA_PLACEMENT_DEVIATION"],
            "same_slot_only": True,
            "causal_suffix_replay": True,
            "future_Actual_reads": 0,
            "strict_FULL_only": True,
            "preemption": False,
            "running_job_migration": False,
            "physical_limit_changes": 0,
            "continuous_parameter_tuning": False,
            "E2_touched": False,
            "Stage1_touched": False,
            "h_REC_endogenized": False,
            "MESS_reoptimized": False,
            "HiGHS_threads": 4,
            "Fresh_OpenDSS": "SEQUENTIAL",
            "E1_DA_schedule_sha256": b1_da_sha,
            "E1_DA_schedule_identity": b1_da_sha == _json(repo / V33X_OUT / "V33X_E0_BASELINE_IDENTITY.json")["schedule_sha256"]["B1"],
            "MESS_P_sha256": _sha_array(schedules["B1"]["mess_p_kw"]),
            "MESS_Q_sha256": _sha_array(schedules["B1"]["mess_q_kvar"]),
            "MESS_route_sha256": canonical_sha256(schedules["B1"]["mess_route_location"]),
            "V33X_artifact_tree": original_v33x_tree,
        }
        write_json(out / "V33XR1_CUT_CONTRACT.json", contract)

        common_args = (
            np.asarray(schedules["B1"]["workload_service_tensor"], dtype=float),
            actual.arrivals_nodeh, capacity, owners, fixed["B1"].p_res_actual_kw,
            actual_data.c1_by_site_slot, np.asarray(schedules["B1"]["controls"], dtype=float),
            coefficients,
        )
        current_result = solve_causal_suffix_with_voltage_cuts(*common_args, (), initial)
        reproduced_original_executed = float(current_result.recourse.summary["EXECUTED_TOTAL"])
        original_executed = float(original_e1_rows["B1"]["Actual_executed_nodeh"])
        if abs(reproduced_original_executed - original_executed) > 1e-6:
            raise RuntimeError(
                f"V33XR1_ORIGINAL_E1_STAGE2_REPRODUCTION:{reproduced_original_executed}:{original_executed}"
            )
        current_trajectory, _rack_it, _rack_gpu = _recourse_trajectory(
            source_repo, schedules["B1"], actual, mobility, current_result.recourse,
            owners, power_weights, gpu_weights,
        )
        current_fresh = _fresh_raw(repo, source_repo, current_trajectory, voltage_path, current_path)
        if abs(float(current_fresh.summary["Vmax_pu"]) - float(original_e1_fresh["B1"]["Vmax_pu"])) > 1e-8:
            raise RuntimeError("V33XR1_ORIGINAL_E1_FRESH_REPRODUCTION")

        iteration_rows = [_iteration_row(
            0, current_result, current_fresh, actual.arrivals_nodeh, initial,
            cuts_added=0, cumulative_cuts=0, replay_start_slot=0, prefix_reused=False,
        )]
        all_cuts: list[LocalVoltageCut] = []
        cut_audits: list[dict[str, object]] = []
        completed_iterations = 0
        cut_set_infeasible = False
        for iteration in range(1, MAX_REPAIR_ITERATIONS + 1):
            violations = [row for row in current_fresh.violation_rows() if row["kind"] == "VOLTAGE"]
            if not violations:
                break
            new_cuts, new_audits = _make_cuts(
                iteration, current_result, current_fresh, coefficients, current_trajectory,
            )
            if not new_cuts:
                break
            write_csv(out / "V33XR1_CUT_LEDGER.csv", new_audits)
            before_result = current_result
            before_executed = float(before_result.recourse.summary["EXECUTED_TOTAL"])
            all_cuts.extend(new_cuts)
            earliest = min(cut.slot for cut in new_cuts)
            feasibility = {
                cut.cut_id: assess_local_cut_feasibility(*common_args, before_result, cut)
                for cut in new_cuts
            }
            if any(not bool(row["feasible"]) for row in feasibility.values()):
                for cut, audit in zip(new_cuts, new_audits, strict=True):
                    detail = feasibility[cut.cut_id]
                    audit.update({
                        "cut_feasibility": "FEASIBLE" if detail["feasible"] else "INFEASIBLE",
                        "minimum_achievable_LHS_pu": detail["minimum_achievable_LHS_pu"],
                        "required_RHS_pu": detail["required_RHS_pu"],
                        "feasibility_shortfall_pu": detail["shortfall_pu"],
                        "cut_LHS_after_resolve_pu": "",
                        "cut_slack_after_resolve_pu": "",
                        "cut_active_after_resolve": False,
                        "iteration_total_service_loss_nodeh": 0.0,
                        "service_loss_attributable_to_cut_nodeh": 0.0,
                        "Fresh_voltage_after_resolve_pu": float(current_fresh.voltage_pu[cut.slot, cut.node_index]),
                    })
                    cut_audits.append(audit)
                completed_iterations = iteration
                failed_row = _iteration_row(
                    iteration, current_result, current_fresh, actual.arrivals_nodeh, initial,
                    cuts_added=len(new_cuts), cumulative_cuts=len(all_cuts),
                    replay_start_slot=earliest, prefix_reused=earliest > 0,
                )
                failed_row["status"] = "CUT_SET_INFEASIBLE_NO_TRAJECTORY_CHANGE"
                iteration_rows.append(failed_row)
                cut_set_infeasible = True
                break
            try:
                current_result = solve_causal_suffix_with_voltage_cuts(
                    *common_args, all_cuts, initial, previous=before_result, start_slot=earliest,
                )
            except LocalVoltageCutInfeasible as error:
                detail_by_id = {str(row["cut_id"]): row for row in error.details}
                for cut, audit in zip(new_cuts, new_audits, strict=True):
                    detail = detail_by_id.get(cut.cut_id)
                    audit.update({
                        "cut_feasibility": "INFEASIBLE" if detail else "NOT_REACHED_DUE_TO_PEER_INFEASIBILITY",
                        "minimum_achievable_LHS_pu": "" if detail is None else detail["minimum_achievable_LHS_pu"],
                        "required_RHS_pu": cut.rhs_pu,
                        "feasibility_shortfall_pu": "" if detail is None else detail["shortfall_pu"],
                        "cut_LHS_after_resolve_pu": "",
                        "cut_slack_after_resolve_pu": "",
                        "cut_active_after_resolve": False,
                        "iteration_total_service_loss_nodeh": 0.0,
                        "service_loss_attributable_to_cut_nodeh": 0.0,
                        "Fresh_voltage_after_resolve_pu": float(current_fresh.voltage_pu[cut.slot, cut.node_index]),
                    })
                    cut_audits.append(audit)
                completed_iterations = iteration
                failed_row = _iteration_row(
                    iteration, current_result, current_fresh, actual.arrivals_nodeh, initial,
                    cuts_added=len(new_cuts), cumulative_cuts=len(all_cuts),
                    replay_start_slot=earliest, prefix_reused=earliest > 0,
                )
                failed_row["status"] = "CUT_SET_INFEASIBLE_NO_TRAJECTORY_CHANGE"
                iteration_rows.append(failed_row)
                cut_set_infeasible = True
                break
            current_trajectory, _rack_it, _rack_gpu = _recourse_trajectory(
                source_repo, schedules["B1"], actual, mobility, current_result.recourse,
                owners, power_weights, gpu_weights,
            )
            current_fresh = _fresh_raw(repo, source_repo, current_trajectory, voltage_path, current_path)
            after_executed = float(current_result.recourse.summary["EXECUTED_TOTAL"])
            node_lookup = {str(name).lower(): index for index, name in enumerate(current_fresh.node_names)}
            for cut, audit in zip(new_cuts, new_audits, strict=True):
                conditional = solve_causal_suffix_with_voltage_cuts(
                    *common_args, [item for item in all_cuts if item.cut_id != cut.cut_id], initial,
                    previous=before_result, start_slot=earliest,
                )
                conditional_executed = float(conditional.recourse.summary["EXECUTED_TOTAL"])
                site_p_after = np.asarray(current_result.slot_diagnostics[cut.slot]["site_p_kw"], dtype=float)
                lhs_after = float(np.asarray(cut.sensitivity_pu_per_kw) @ site_p_after)
                node_index = node_lookup[cut.node.lower()]
                audit.update({
                    "cut_LHS_after_resolve_pu": lhs_after,
                    "cut_slack_after_resolve_pu": cut.rhs_pu - lhs_after,
                    "cut_active_after_resolve": abs(cut.rhs_pu - lhs_after) <= CUT_ACTIVE_TOLERANCE_PU,
                    "iteration_total_service_loss_nodeh": before_executed - after_executed,
                    "service_loss_attributable_to_cut_nodeh": max(0.0, conditional_executed - after_executed),
                    "Fresh_voltage_after_resolve_pu": float(current_fresh.voltage_pu[cut.slot, node_index]),
                })
                cut_audits.append(audit)
            completed_iterations = iteration
            iteration_rows.append(_iteration_row(
                iteration, current_result, current_fresh, actual.arrivals_nodeh, initial,
                cuts_added=len(new_cuts), cumulative_cuts=len(all_cuts),
                replay_start_slot=earliest, prefix_reused=earliest > 0,
            ))
            summary = current_fresh.summary
            if (
                int(summary["voltage_violation_count"]) == 0
                and int(summary["line_current_violation_count"]) == 0
                and int(summary["transformer_current_violation_count"]) == 0
                and int(summary["transformer_kva_violation_count"]) == 0
            ):
                break

        final_summary = current_fresh.summary
        fresh_b1 = _fresh_row(
            current_fresh, "ACTUAL",
            "V33XR1_UNCUT_RETAINED_CUT_INFEASIBLE" if cut_set_infeasible else "V33XR1_FINAL_REPAIRED",
        )
        b0_rho = float(baseline_fresh["B0"]["rho_max_AC"])
        b2_rho = float(baseline_fresh["B2"]["rho_max_AC"])
        repaired_executed = float(current_result.recourse.summary["EXECUTED_TOTAL"])
        e0_b1_executed = float(e0_rows["B1"]["Actual_executed_nodeh"])
        retained_gain_fraction = (
            1.0 if cut_set_infeasible
            else (repaired_executed - e0_b1_executed) / (original_executed - e0_b1_executed)
        )
        b1_safe = (
            int(final_summary["convergence_count"]) == 96
            and int(final_summary["voltage_violation_count"]) == 0
            and int(final_summary["line_current_violation_count"]) == 0
            and int(final_summary["transformer_current_violation_count"]) == 0
            and int(final_summary["transformer_kva_violation_count"]) == 0
            and float(final_summary["rho_max_AC"]) <= b0_rho + 1e-9
            and _mass_error(current_result, actual.arrivals_nodeh, initial) <= MASS_TOLERANCE_NODEH
            and current_result.recourse.future_actual_reads == 0
        )
        b3_safe = (
            int(original_e1_fresh["B3"]["convergence_count"]) == 96
            and int(original_e1_fresh["B3"]["voltage_violation_count"]) == 0
            and int(original_e1_fresh["B3"]["line_current_violation_count"]) == 0
            and int(original_e1_fresh["B3"]["transformer_current_violation_count"]) == 0
            and int(original_e1_fresh["B3"]["transformer_kva_violation_count"]) == 0
            and float(original_e1_fresh["B3"]["rho_max_AC"]) <= b2_rho + 1e-9
        )
        if int(final_summary["line_current_violation_count"]) or int(final_summary["transformer_current_violation_count"]) or int(final_summary["transformer_kva_violation_count"]):
            classification = "V33XR1_E1_NEW_PHYSICAL_VIOLATION_CREATED"
        elif int(final_summary["voltage_violation_count"]):
            classification = "V33XR1_E1_CUTS_FAILED_TO_CLOSE_VOLTAGE"
        elif b1_safe and b3_safe and repaired_executed <= e0_b1_executed + 1e-9:
            classification = "V33XR1_E1_CUTS_SAFE_BUT_DELIVERY_COLLAPSED"
        elif b1_safe and b3_safe:
            classification = "V33XR1_E1_FRESH_VOLTAGE_CUT_DEVELOPMENT_PASS"
        else:
            classification = "V33XR1_E1_NEW_PHYSICAL_VIOLATION_CREATED"

        final_b1 = {
            "artifact_id": "V33XR1_FINAL_B1_RESULTS_V1",
            "RESULT_CLASSIFICATION": classification,
            "case": "B1",
            "initial": iteration_rows[0],
            "uncut_solver_reproduction_delta_nodeh": reproduced_original_executed - original_executed,
            "final": iteration_rows[-1],
            "repaired_candidate_exists": not cut_set_infeasible,
            "frozen_original_E1_executed_nodeh": original_executed,
            "frozen_original_E1_execution_ratio": float(original_e1_rows["B1"]["raw_execution_ratio"]),
            "frozen_original_E1_Fresh_rho_AC": float(original_e1_fresh["B1"]["rho_max_AC"]),
            "frozen_original_E1_Fresh_Vmax_pu": float(original_e1_fresh["B1"]["Vmax_pu"]),
            "cut_iterations": completed_iterations,
            "total_cuts_generated": len(all_cuts),
            "unique_bus_phase_slot_cuts": len({(cut.bus, cut.phase, cut.slot) for cut in all_cuts}),
            "service_loss_from_original_E1_nodeh": 0.0 if cut_set_infeasible else original_executed - repaired_executed,
            "cut_induced_service_loss_nodeh": 0.0 if cut_set_infeasible else original_executed - repaired_executed,
            "retained_original_E1_gain_fraction": retained_gain_fraction,
            "Fresh_B1_minus_B0_rho": float(final_summary["rho_max_AC"]) - b0_rho,
            "final_trajectory_sha256": current_trajectory.immutable_sha256,
            "DA_schedule_sha256": b1_da_sha,
            "DA_schedule_identity": True,
            "MESS_trajectory_identity": (
                np.array_equal(current_trajectory.mess_p_kw, fixed["B1"].trajectory.mess_p_kw)
                and np.array_equal(current_trajectory.mess_q_kvar, fixed["B1"].trajectory.mess_q_kvar)
                and np.array_equal(current_trajectory.mess_locations_96x4, fixed["B1"].trajectory.mess_locations_96x4)
            ),
            "future_Actual_reads": current_result.recourse.future_actual_reads,
            "mass_conservation_error_nodeh": _mass_error(current_result, actual.arrivals_nodeh, initial),
            "FRESH_AC_CUT_GENERATION_USED": True,
            "cut_set_infeasible": cut_set_infeasible,
            "FINAL_AUTHORITY": False,
        }
        b3_row = original_e1_rows["B3"]
        final_b3 = {
            "artifact_id": "V33XR1_FINAL_B3_RESULTS_V1",
            "case": "B3",
            "cut_iterations": 0,
            "cuts_generated": 0,
            "trajectory_unchanged_by_construction": True,
            "source_schedule_sha256": schedules["B3"]["schedule_sha256"],
            "V33X_Fresh_schedule_binding_sha256": original_e1_fresh["B3"]["schedule_sha256"],
            "Fresh_result_reused": True,
            "executed_nodeh": float(b3_row["Actual_executed_nodeh"]),
            "execution_ratio": float(b3_row["raw_execution_ratio"]),
            "availability_conditioned_execution_ratio": float(b3_row["availability_conditioned_execution_ratio"]),
            "Fresh_rho_AC": float(original_e1_fresh["B3"]["rho_max_AC"]),
            "Fresh_B3_minus_B2_rho": float(original_e1_fresh["B3"]["rho_max_AC"]) - b2_rho,
            "Fresh_Vmax_pu": float(original_e1_fresh["B3"]["Vmax_pu"]),
            "Fresh_voltage_violation_count": int(original_e1_fresh["B3"]["voltage_violation_count"]),
            "Fresh_line_current_violation_count": int(original_e1_fresh["B3"]["line_current_violation_count"]),
            "Fresh_transformer_current_violation_count": int(original_e1_fresh["B3"]["transformer_current_violation_count"]),
            "Fresh_transformer_kva_violation_count": int(original_e1_fresh["B3"]["transformer_kva_violation_count"]),
            "Fresh_convergence_count": int(original_e1_fresh["B3"]["convergence_count"]),
            "DA_schedule_identity": True,
            "MESS_trajectory_identity": True,
        }
        b3_iteration = {
            "iteration": 0, "case": "B3", "status": "FROZEN_V33X_REUSED_NO_VIOLATION",
            "replay_start_slot": "", "causal_prefix_reused": True, "cuts_added": 0, "cumulative_cuts": 0,
            "DA_authorized_nodeh": float(b3_row["DA_authorized_nodeh"]),
            "Actual_source_available_nodeh": float(b3_row["Actual_source_available_nodeh"]),
            "executed_nodeh": float(b3_row["Actual_executed_nodeh"]),
            "execution_ratio": float(b3_row["raw_execution_ratio"]),
            "availability_conditioned_execution_ratio": float(b3_row["availability_conditioned_execution_ratio"]),
            "same_site_recourse_nodeh": float(b3_row["same_site_recourse_nodeh"]),
            "cross_site_recourse_nodeh": float(b3_row["cross_site_recourse_nodeh"]),
            "rack_blocked_nodeh": float(b3_row["rack_capacity_blocked_nodeh"]),
            "grid_cut_blocked_nodeh": float(b3_row["grid_envelope_blocked_nodeh"]),
            "terminal_backlog_nodeh": float(b3_row["terminal_backlog_nodeh"]),
            "mass_conservation_error_nodeh": abs(float(b3_row["workload_mass_error_nodeh"])),
            "future_Actual_reads": int(b3_row["future_Actual_reads"]),
            "Fresh_rho_AC": float(original_e1_fresh["B3"]["rho_max_AC"]),
            "Fresh_Vmin_pu": float(original_e1_fresh["B3"]["Vmin_pu"]),
            "Fresh_Vmax_pu": float(original_e1_fresh["B3"]["Vmax_pu"]),
            "Fresh_voltage_violation_count": 0,
            "Fresh_line_current_violation_count": 0,
            "Fresh_transformer_current_violation_count": 0,
            "Fresh_transformer_kva_violation_count": 0,
            "Fresh_convergence_count": 96,
        }
        iteration_rows.append(b3_iteration)
        b1_variant = "E1_UNCUT_RETAINED_CUT_INFEASIBLE" if cut_set_infeasible else "E1_REPAIRED_LOCAL_VOLTAGE_CUTS"
        final_fresh_rows = [
            {"variant": b1_variant, "Fresh_result_reused": False, **fresh_b1},
            {"variant": "E1_REPAIRED_LOCAL_VOLTAGE_CUTS", "Fresh_result_reused": True, **original_e1_fresh["B3"]},
        ]
        final_review = {
            "artifact_id": "V33XR1_FINAL_REVIEW_V1",
            "RESULT_CLASSIFICATION": classification,
            "FRESH_AC_CUT_GENERATION_USED": True,
            "FINAL_AUTHORITY": False,
            "cases": {"B1": final_b1, "B3": final_b3},
            "E2_touched": False,
            "Stage1_touched": False,
            "MESS_reoptimized": False,
            "physical_limit_changes": 0,
            "continuous_parameter_tuning": False,
            "Fresh_new_B1_trajectories": completed_iterations + 1 if not cut_set_infeasible else 1,
            "Fresh_OpenDSS_sequential": True,
            "development_candidate": classification == "V33XR1_E1_FRESH_VOLTAGE_CUT_DEVELOPMENT_PASS",
            "next_required_step": "PROSPECTIVE_PRE_APRIL_CERTIFICATION" if classification == "V33XR1_E1_FRESH_VOLTAGE_CUT_DEVELOPMENT_PASS" else "REVISE_OR_ABANDON",
        }
        write_csv(out / "V33XR1_CUT_LEDGER.csv", cut_audits)
        write_csv(out / "V33XR1_ITERATION_RESULTS.csv", iteration_rows)
        write_json(out / "V33XR1_FINAL_B1_RESULTS.json", final_b1)
        write_json(out / "V33XR1_FINAL_B3_RESULTS.json", final_b3)
        write_csv(out / "V33XR1_FINAL_FRESH_OPENDSS_RESULTS.csv", final_fresh_rows)
        write_json(out / "V33XR1_FINAL_REVIEW.json", final_review)
        outcome = (
            f"B1 generated {len(all_cuts)} local cuts in repair iteration {completed_iterations}, but every cut "
            "was outside the frozen E1 feasible set; no repaired trajectory was created and cut-induced service loss was zero. "
            if cut_set_infeasible else
            f"B1 applied {len(all_cuts)} local cuts over {completed_iterations} repair iterations; "
            f"execution changed from {original_executed:.12f} to {repaired_executed:.12f} node-h. "
        )
        (out / "V33XR1_FINAL_REVIEW.md").write_text(
            f"# V33X-R1 E1 local Fresh-voltage-cut repair\n\nResult: **{classification}**\n\n"
            f"{outcome}Final Vmax was {float(final_summary['Vmax_pu']):.12f} pu with "
            f"{int(final_summary['voltage_violation_count'])} voltage violations. "
            "Fresh AC generated development cuts; this is not final authority. E2 and MESS were untouched.\n",
            encoding="utf-8", newline="\n",
        )
        (out / "README.md").write_text(
            "# V33X-R1 E1 Fresh-AC voltage cuts\n\nApr-04-only isolated development repair of E1. "
            "Fresh AC is used only by the development cut loop; the ordinary recourse solver remains Fresh-free. "
            "E2, Stage-1, MESS, and physical limits are unchanged.\n",
            encoding="utf-8", newline="\n",
        )
        write_json(out / "V33XR1_TEST_REPORT.json", {
            "artifact_id": "V33XR1_TEST_REPORT_V1", "status": "PENDING",
            "passed": 0, "failed": 0, "not_run": 0,
        })
        if not _e2_untouched(repo):
            raise RuntimeError("V33XR1_E2_CHANGED_AFTER_RUN")
        return final_review
    finally:
        base_context.voltage.close()
        base_context.current.close()
        actual_context.voltage.close()
        actual_context.current.close()
        voltage.close()
        current.close()


def finalize(repo: Path, *, passed: int, failed: int, not_run: int) -> dict[str, object]:
    report = {
        "artifact_id": "V33XR1_TEST_REPORT_V1",
        "status": "PASS" if failed == 0 and not_run == 0 else "FAIL",
        "passed": int(passed), "failed": int(failed), "not_run": int(not_run),
    }
    write_json(repo.resolve() / OUT_REL / "V33XR1_TEST_REPORT.json", report)
    return report
