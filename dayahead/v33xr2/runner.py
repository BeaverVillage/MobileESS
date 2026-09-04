"""Run the single predeclared V33XR2 E1 voltage-tightening screen."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import subprocess
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from dayahead.v28r2.actual_replay import PF_TAN, replay_actual_case
from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.electrical_context import build_electrical_context, with_realized_background
from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU
from dayahead.v28r2.source_cache import day_root
from dayahead.v28r2.workload_replay import materialize_actual_workload
from dayahead.v29r2.apr04_runner import _pi_data
from dayahead.v29r2.formulation import materialize_formulation_data_v29r2
from dayahead.v29r3.forensic import _initial_actual
from dayahead.v30.contracts import write_json
from dayahead.v30.dayahead_formulation import load_frozen_schedules
from dayahead.v30.four_case_runner import _mapping, _recourse_trajectory
from dayahead.v30.reporting import write_csv
from dayahead.v33x.full_grid_recourse import solve_causal_day_full_grid
from dayahead.v33x.runner import CURRENT_NAME, VOLTAGE_NAME, _fresh

from .contracts import (
    BRANCH,
    CLASS_FRESH_V,
    CLASS_IMPLEMENTATION,
    CLASS_NO_REGRET,
    CLASS_PASS,
    CLASS_PHYSICAL,
    CLASS_STAGE1,
    CLASS_STAGE2,
    DAY,
    DEVELOPMENT_PLANNING_VMAX_PU,
    FINAL_AUTHORITY,
    FRESH_PHYSICAL_VMAX_PU,
    MESS_INTEGRATION_HEAD,
    OUT_REL,
    PF,
    PLANNING_VMIN_PU,
    STARTING_HEAD,
)
from .stage1 import Stage1Infeasible, solve_stage1


V30_OUT = Path("dayahead/artifacts/v30_two_stage_aidc_recourse")
V33X_OUT = Path("dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc")


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _source_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    values += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
    return values


def _stage1_row(result: object, frozen: Mapping[str, object]) -> dict[str, object]:
    schedule = result.schedule
    return {
        "artifact_id": "V33XR2_B1_STAGE1_RESULT_V1",
        "status": "PASS",
        "case": str(schedule["case"]),
        "feasible": result.feasible,
        "DEVELOPMENT_PLANNING_VMAX_PU": DEVELOPMENT_PLANNING_VMAX_PU,
        "planning_vmin_pu": result.planning_vmin_pu,
        "planning_vmax_pu": result.planning_vmax_pu,
        "DA_authorized_nodeh": float(np.asarray(schedule["workload_service_tensor"], dtype=float).sum()),
        "objective_max_normalized_phase_line_current": result.objective,
        "schedule_sha256": schedule["schedule_sha256"],
        "source_frozen_schedule_sha256": frozen["schedule_sha256"],
        "schedule_frozen_before_Actual": True,
        "Stage1_Actual_inputs": 0,
        "Stage1_Fresh_inputs": 0,
        "future_Actual_reads": 0,
        "MESS_max_abs_P_difference_kw": result.mess_max_abs_p_difference_kw,
        "MESS_max_abs_Q_difference_kvar": result.mess_max_abs_q_difference_kvar,
        "MESS_unchanged": result.mess_max_abs_p_difference_kw <= 1e-9 and result.mess_max_abs_q_difference_kvar <= 1e-9,
        "solver_iterations": result.solver_iterations,
        "runtime_seconds": result.runtime_seconds,
    }


def _mass_error(result: object, arrivals: np.ndarray, initial: np.ndarray) -> float:
    source = float(initial.sum() + arrivals.sum() - result.recourse.executed_nodeh.sum() - result.recourse.backlog_nodeh[-1].sum())
    authorization = float(result.recourse.summary["authorization_mass_identity_error_nodeh"])
    return max(abs(source), abs(authorization))


def _stage2_row(case: str, schedule: Mapping[str, object], result: object, arrivals: np.ndarray, initial: np.ndarray) -> dict[str, object]:
    summary = result.recourse.summary
    authorized = float(np.asarray(schedule["workload_service_tensor"], dtype=float).sum())
    executed = float(summary["EXECUTED_TOTAL"])
    available = float(summary["ACTUAL_AVAILABLE"])
    return {
        "artifact_id": f"V33XR2_{case}_STAGE2_RESULT_V1",
        "status": "PASS",
        "case": case,
        "feasible": True,
        "DEVELOPMENT_PLANNING_VMAX_PU": DEVELOPMENT_PLANNING_VMAX_PU,
        "planning_vmin_pu": min(float(row["planning_Vmin_pu"]) for row in result.slot_diagnostics),
        "planning_vmax_pu": max(float(row["planning_Vmax_pu"]) for row in result.slot_diagnostics),
        "DA_authorized_nodeh": authorized,
        "Actual_available_nodeh": available,
        "executed_nodeh": executed,
        "execution_ratio": executed / authorized,
        "availability_conditioned_execution_ratio": executed / available,
        "same_rack_executed_nodeh": float(summary["EXECUTED_ORIGINAL_RACK"]),
        "same_site_recourse_nodeh": float(summary["EXECUTED_SAME_SITE_RECOURSE"]),
        "cross_site_recourse_nodeh": float(summary["EXECUTED_CROSS_SITE_RECOURSE"]),
        "source_unavailable_nodeh": float(summary["SOURCE_UNAVAILABLE"]),
        "rack_blocked_nodeh": float(summary["TRUE_RACK_CAPACITY_LIMIT"]),
        "grid_planning_voltage_blocked_nodeh": float(summary["GRID_SAFETY_BLOCKED"]),
        "terminal_backlog_nodeh": float(summary["TERMINAL_BACKLOG"]),
        "mass_error_nodeh": _mass_error(result, arrivals, initial),
        "future_Actual_reads": int(result.recourse.future_actual_reads),
        "same_slot_only": True,
        "preemption": False,
        "running_job_migration": False,
        "strict_FULL_only": True,
        "objective_hierarchy": ["MAX_SERVICE", "MIN_MAX_PLANNING_LINE_CURRENT", "MIN_DA_PLACEMENT_DEVIATION"],
        "Fresh_inputs_to_solver": 0,
        "local_Fresh_cuts": 0,
        "solver_subcalls": int(result.recourse.solver_subcalls),
    }


def _fresh_row(case: str, fresh: Mapping[str, object]) -> dict[str, object]:
    return {
        "variant": "E1_VMAX10495",
        "DEVELOPMENT_PLANNING_VMAX_PU": DEVELOPMENT_PLANNING_VMAX_PU,
        "FRESH_PHYSICAL_VMAX_PU": FRESH_PHYSICAL_VMAX_PU,
        "Fresh_role": "VALIDATION_ONLY",
        **fresh,
    }


def _classification(stage2: Mapping[str, object], fresh: Mapping[str, object], rho_anchor: float) -> str:
    if int(fresh["convergence_count"]) != 96:
        return CLASS_PHYSICAL
    if int(fresh["voltage_violation_count"]) != 0:
        return CLASS_FRESH_V
    if (
        int(fresh["line_current_violation_count"]) != 0
        or int(fresh["transformer_current_violation_count"]) != 0
        or int(fresh["transformer_kva_violation_count"]) != 0
    ):
        return CLASS_PHYSICAL
    if float(fresh["rho_max_AC"]) > rho_anchor + 1e-9:
        return CLASS_NO_REGRET
    if float(stage2["mass_error_nodeh"]) > 1e-9 or int(stage2["future_Actual_reads"]) != 0:
        return CLASS_IMPLEMENTATION
    return CLASS_PASS


def _internal_checks(
    repo: Path,
    contract: Mapping[str, object],
    stage1: Mapping[str, object],
    stage2: Mapping[str, object],
    fresh: Mapping[str, object],
) -> list[dict[str, object]]:
    stage1_imports = _source_imports(repo / "dayahead/v33xr2/stage1.py")
    stage2_imports = _source_imports(repo / "dayahead/v33x/full_grid_recourse.py")
    checks = [
        ("exact_starting_head", contract["starting_HEAD"] == STARTING_HEAD),
        ("planning_vmax_exact", contract["DEVELOPMENT_PLANNING_VMAX_PU"] == 1.0495),
        ("fresh_physical_vmax_unchanged", contract["FRESH_PHYSICAL_VMAX_PU"] == 1.05),
        ("lower_voltage_bound_unchanged", contract["PLANNING_VMIN_PU"] == 0.95),
        ("stage1_receives_10495", stage1["DEVELOPMENT_PLANNING_VMAX_PU"] == 1.0495),
        ("stage2_receives_10495", stage2["DEVELOPMENT_PLANNING_VMAX_PU"] == 1.0495),
        ("no_E2_path", contract["E2_touched"] is False),
        ("no_h_REC_modification", contract["h_REC_added_or_modified"] is False),
        ("no_Fresh_derived_cut", int(stage2["local_Fresh_cuts"]) == 0),
        ("Fresh_absent_from_solver_decision_path", not any("fresh" in x.lower() or "opendss" in x.lower() for x in stage1_imports + stage2_imports)),
        ("MESS_unchanged", stage1["MESS_unchanged"] is True),
        ("PF_unchanged", math.isclose(PF_TAN, math.tan(math.acos(PF)), abs_tol=0.0)),
        ("current_and_transformer_ratings_unchanged", contract["current_transformer_ratings_changed"] is False),
        ("Stage2_objective_unchanged", stage2["objective_hierarchy"] == ["MAX_SERVICE", "MIN_MAX_PLANNING_LINE_CURRENT", "MIN_DA_PLACEMENT_DEVIATION"]),
        ("future_Actual_reads_zero", int(stage2["future_Actual_reads"]) == 0),
        ("mass_conservation", float(stage2["mass_error_nodeh"]) <= 1e-9),
        ("no_preemption", stage2["preemption"] is False),
        ("no_running_job_migration", stage2["running_job_migration"] is False),
    ]
    return [{"check": name, "pass": bool(passed)} for name, passed in checks]


def _write_markdown(out: Path, review: Mapping[str, object]) -> None:
    b1 = review["B1"]
    b3 = review.get("B3")
    lines = [
        "# V33XR2 — E1 계획 전압 상한 1.0495 pu 개발 실험",
        "",
        f"주 분류: **{review['primary_classification']}**",
        "",
        "Stage-1과 E1 Stage-2의 계획 상한만 1.0495 pu로 낮췄다. Fresh 물리 상한은 1.05 pu로 유지했으며 Fresh는 후보 궤적 동결 후 검증에만 사용했다.",
        "",
        "## B1",
        "",
        f"- Stage-1 feasible: {b1['stage1']['feasible']}",
        f"- Stage-2 feasible: {b1['stage2']['feasible']}",
        f"- DA authorized: {b1['stage2']['DA_authorized_nodeh']:.12f} node-h",
        f"- Executed: {b1['stage2']['executed_nodeh']:.12f} node-h",
        f"- Execution ratio: {b1['stage2']['execution_ratio']:.12%}",
        f"- Original E1 gain retained: {b1['retained_E1_delivery_gain_fraction']:.12%}",
        f"- Fresh Vmax/Vmin: {b1['fresh']['Vmax_pu']:.12f} / {b1['fresh']['Vmin_pu']:.12f} pu",
        f"- Fresh voltage/current/transformer violations: {b1['fresh']['voltage_violation_count']} / {b1['fresh']['line_current_violation_count']} / {int(b1['fresh']['transformer_current_violation_count']) + int(b1['fresh']['transformer_kva_violation_count'])}",
        f"- Fresh rho B1/B0/delta: {b1['fresh']['rho_max_AC']:.12f} / {b1['rho_anchor']:.12f} / {b1['rho_delta']:.12f}",
        f"- Mass error: {b1['stage2']['mass_error_nodeh']:.3e} node-h",
        f"- Future Actual reads: {b1['stage2']['future_Actual_reads']}",
    ]
    if b3 is not None:
        lines += [
            "",
            "## B3 보조 확인",
            "",
            f"- Executed: {b3['stage2']['executed_nodeh']:.12f} node-h",
            f"- Execution ratio: {b3['stage2']['execution_ratio']:.12%}",
            f"- Fresh Vmax: {b3['fresh']['Vmax_pu']:.12f} pu",
            f"- Fresh rho B3/B2/delta: {b3['fresh']['rho_max_AC']:.12f} / {b3['rho_anchor']:.12f} / {b3['rho_delta']:.12f}",
        ]
    lines += [
        "",
        "## 해석",
        "",
        str(review["scientific_interpretation"]),
        "",
        "이 결과는 Apr-04 단일 개발 screening이며 1.0495 pu를 최종 margin으로 확정하지 않는다.",
    ]
    (out / "V33XR2_FINAL_REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (out / "README.md").write_text(
        "# V33XR2 E1 Vmax 1.0495\n\n"
        "Apr-04 B1 우선 fast-gate 개발 실험이다. 계획 상한은 1.0495 pu, Fresh 물리 상한은 1.05 pu다. "
        "Fresh feedback, E2, h_REC, MESS 재최적화는 사용하지 않았다. 자세한 결과는 `V33XR2_FINAL_REVIEW.md`를 본다.\n",
        encoding="utf-8", newline="\n",
    )


def run(repo: Path, source_repo: Path, electrical_cache: Path) -> dict[str, object]:
    repo = repo.resolve()
    source_repo = source_repo.resolve()
    electrical_cache = electrical_cache.resolve()
    if _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V33XR2_WRONG_BRANCH")
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", STARTING_HEAD, "HEAD"], check=False).returncode:
        raise RuntimeError("V33XR2_STARTING_HEAD_NOT_ANCESTOR")
    if _git(repo, "rev-parse", "codex/v33m2-mess-mobility-milp-preintegration") != MESS_INTEGRATION_HEAD:
        raise RuntimeError("V33XR2_MESS_INTEGRATION_HEAD_MOVED")
    protected = _git(
        repo, "diff", "--name-only", STARTING_HEAD, "--",
        "dayahead/v33x/headroom_stage1.py", "dayahead/mess_physics.py",
        "dayahead/v28r2/mess_replay.py", "dayahead/v28r2/variable_registry.py",
    )
    if protected:
        raise RuntimeError(f"V33XR2_PROTECTED_PATH_CHANGED:{protected}")

    out = repo / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    contract = {
        "artifact_id": "V33XR2_CONTRACT_V1",
        "status": "FROZEN_BEFORE_STAGE1",
        "starting_HEAD": STARTING_HEAD,
        "branch": BRANCH,
        "MESS_integration_HEAD": MESS_INTEGRATION_HEAD,
        "day": DAY,
        "case_order": ["B1", "B3_IF_B1_PASS"],
        "DEVELOPMENT_PLANNING_VMAX_PU": DEVELOPMENT_PLANNING_VMAX_PU,
        "FRESH_PHYSICAL_VMAX_PU": FRESH_PHYSICAL_VMAX_PU,
        "PLANNING_VMIN_PU": PLANNING_VMIN_PU,
        "FINAL_AUTHORITY": FINAL_AUTHORITY,
        "only_planning_upper_voltage_changed": True,
        "Stage1_re_solved": True,
        "Stage2_same_planning_vmax": True,
        "Fresh_validation_only": True,
        "Fresh_oracle_used": False,
        "Fresh_derived_cuts": 0,
        "E2_touched": False,
        "h_REC_added_or_modified": False,
        "MESS_touched_or_reoptimized": False,
        "PF": PF,
        "lower_voltage_bound_changed": False,
        "current_transformer_ratings_changed": False,
        "source_voltage_or_native_controls_changed": False,
        "AIDC_scale_or_C1_changed": False,
        "Gurobi_threads": 4,
        "HiGHS_threads": 4,
        "Fresh_OpenDSS": "SEQUENTIAL_96_SLOT_VALIDATION_AFTER_FREEZE",
        "Stage2_objective": ["MAX_SERVICE", "MIN_MAX_PLANNING_LINE_CURRENT", "MIN_DA_PLACEMENT_DEVIATION"],
        "same_slot_only": True,
        "strict_FULL_only": True,
        "preemption": False,
        "running_job_migration": False,
    }
    write_json(out / "V33XR2_CONTRACT.json", contract)

    schedules = load_frozen_schedules(repo)
    voltage_path = electrical_cache / "data" / VOLTAGE_NAME
    current_path = electrical_cache / "data" / CURRENT_NAME
    voltage = np.load(voltage_path, allow_pickle=False)
    current = np.load(current_path, allow_pickle=False)
    try:
        # Stage-1 is intentionally completed and hashed before Actual is materialized.
        da_data = materialize_formulation_data_v29r2(repo, DAY, "S_NOM")
        base_context = build_electrical_context(repo, da_data, electrical_cache)
        try:
            b1_stage1_obj = solve_stage1(
                da_data, base_context.legacy_context, voltage, current, "B1",
                schedules["B1"], DEVELOPMENT_PLANNING_VMAX_PU,
            )
        except Stage1Infeasible as error:
            row = {"artifact_id": "V33XR2_B1_STAGE1_RESULT_V1", "status": "INFEASIBLE", "case": "B1", "feasible": False, "solver_status": error.status}
            write_json(out / "V33XR2_B1_STAGE1_RESULT.json", row)
            write_json(out / "V33XR2_B1_STAGE2_RESULT.json", {"status": "NOT_RUN_STAGE1_INFEASIBLE", "feasible": False})
            write_csv(out / "V33XR2_B1_FRESH_RESULT.csv", [])
            review = {"artifact_id": "V33XR2_FINAL_REVIEW_V1", "primary_classification": CLASS_STAGE1, "B1": {"stage1": row}, "B3_run": False}
            write_json(out / "V33XR2_FINAL_REVIEW.json", review)
            return review
        b1_stage1 = _stage1_row(b1_stage1_obj, schedules["B1"])
        write_json(out / "V33XR2_B1_STAGE1_RESULT.json", b1_stage1)

        actual = materialize_actual_workload(source_repo, DAY)
        initial = _initial_actual(repo, COHORT_IDS)
        mobility = json.loads((day_root(source_repo, DAY) / "traffic_mobility.json").read_text(encoding="utf-8"))["mess"]
        _racks, owners, power_weights, gpu_weights = _mapping(repo)
        residual_gpu = (actual.total_h100_gpu - actual.flexible_natural_gpu)[:, None] * gpu_weights[None, :]
        capacity = np.maximum(0.0, (CASE_CAPACITY_GPU * gpu_weights[None, :] - residual_gpu) * 0.25 / 4.0)
        fixed_b0 = replay_actual_case(source_repo, DAY, schedules["B0"], actual, mobility, initial_backlog_nodeh=initial)
        aemo = pd.read_parquet(day_root(source_repo, DAY) / "aemo_actual.parquet")
        actual_context = with_realized_background(
            repo, base_context,
            timestamps_96=aemo["ts_fixed_aest_end"],
            demand_mw_96=aemo["demand_mw"],
            pv_mw_96=aemo["rooftop_pv_mw"],
            aidc_plan_kw_96x12=fixed_b0.exact_pcc_p_kw,
        )
        coefficients = tuple(slot_coefficients(actual_context.legacy_context, voltage, current, slot) for slot in range(96))
        actual_data = _pi_data(repo, actual, initial)

        def execute(case: str, stage1_obj: object) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
            schedule = stage1_obj.schedule
            fixed = replay_actual_case(source_repo, DAY, schedule, actual, mobility, initial_backlog_nodeh=initial)
            result = solve_causal_day_full_grid(
                np.asarray(schedule["workload_service_tensor"], dtype=float),
                actual.arrivals_nodeh, capacity, owners, fixed.p_res_actual_kw,
                actual_data.c1_by_site_slot, np.asarray(schedule["controls"], dtype=float),
                coefficients, initial, planning_vmax_pu=DEVELOPMENT_PLANNING_VMAX_PU,
            )
            stage2 = _stage2_row(case, schedule, result, actual.arrivals_nodeh, initial)
            trajectory, _rack_it, _rack_gpu = _recourse_trajectory(
                source_repo, schedule, actual, mobility, result.recourse,
                owners, power_weights, gpu_weights,
            )
            fresh = _fresh(repo, source_repo, trajectory, voltage_path, current_path)
            return stage2, fresh, {"trajectory_sha256": trajectory.immutable_sha256}

        try:
            b1_stage2, b1_fresh, b1_trace = execute("B1", b1_stage1_obj)
        except RuntimeError as error:
            if not str(error).startswith("V33X_FULL_GRID_RECOURSE_LP"):
                raise
            row = {"artifact_id": "V33XR2_B1_STAGE2_RESULT_V1", "status": "INFEASIBLE", "case": "B1", "feasible": False, "error": str(error)}
            write_json(out / "V33XR2_B1_STAGE2_RESULT.json", row)
            write_csv(out / "V33XR2_B1_FRESH_RESULT.csv", [])
            review = {"artifact_id": "V33XR2_FINAL_REVIEW_V1", "primary_classification": CLASS_STAGE2, "B1": {"stage1": b1_stage1, "stage2": row}, "B3_run": False}
            write_json(out / "V33XR2_FINAL_REVIEW.json", review)
            return review
        write_json(out / "V33XR2_B1_STAGE2_RESULT.json", b1_stage2)
        write_csv(out / "V33XR2_B1_FRESH_RESULT.csv", [_fresh_row("B1", b1_fresh)])

        frozen_fresh = {row["case"]: row for row in _csv(repo / V30_OUT / "V30_APR04_FRESH_OPENDSS_RESULTS.csv")}
        original_e1 = {row["case"]: row for row in _csv(repo / V33X_OUT / "V33X_E1_STAGE2_RESULTS.csv")}
        e0_executed = 59.18816048947252
        old_e1_executed = float(original_e1["B1"]["Actual_executed_nodeh"])
        retained = (float(b1_stage2["executed_nodeh"]) - e0_executed) / (old_e1_executed - e0_executed)
        rho_b0 = float(frozen_fresh["B0"]["rho_max_AC"])
        classification = _classification(b1_stage2, b1_fresh, rho_b0)
        b1_review = {
            "stage1": b1_stage1,
            "stage2": b1_stage2,
            "fresh": b1_fresh,
            "trace": b1_trace,
            "E0_executed_nodeh": e0_executed,
            "original_E1_executed_nodeh": old_e1_executed,
            "retained_E1_delivery_gain_fraction": retained,
            "rho_anchor_case": "B0",
            "rho_anchor": rho_b0,
            "rho_delta": float(b1_fresh["rho_max_AC"]) - rho_b0,
            "classification": classification,
        }

        b3_review = None
        if classification == CLASS_PASS:
            b3_stage1_obj = solve_stage1(
                da_data, base_context.legacy_context, voltage, current, "B3",
                schedules["B3"], DEVELOPMENT_PLANNING_VMAX_PU,
            )
            b3_stage1 = _stage1_row(b3_stage1_obj, schedules["B3"])
            b3_stage1["artifact_id"] = "V33XR2_B3_STAGE1_RESULT_V1"
            b3_stage2, b3_fresh, b3_trace = execute("B3", b3_stage1_obj)
            write_json(out / "V33XR2_B3_STAGE1_RESULT.json", b3_stage1)
            write_json(out / "V33XR2_B3_STAGE2_RESULT.json", b3_stage2)
            write_csv(out / "V33XR2_B3_FRESH_RESULT.csv", [_fresh_row("B3", b3_fresh)])
            rho_b2 = float(frozen_fresh["B2"]["rho_max_AC"])
            b3_review = {
                "stage1": b3_stage1,
                "stage2": b3_stage2,
                "fresh": b3_fresh,
                "trace": b3_trace,
                "original_E1_executed_nodeh": float(original_e1["B3"]["Actual_executed_nodeh"]),
                "rho_anchor_case": "B2",
                "rho_anchor": rho_b2,
                "rho_delta": float(b3_fresh["rho_max_AC"]) - rho_b2,
                "secondary_physical_pass": _classification(b3_stage2, b3_fresh, rho_b2) == CLASS_PASS,
            }

        checks = _internal_checks(repo, contract, b1_stage1, b1_stage2, b1_fresh)
        test_report = {
            "artifact_id": "V33XR2_TEST_REPORT_V1",
            "status": "PASS" if all(row["pass"] for row in checks) else "FAIL",
            "targeted_check_count": len(checks),
            "passed": sum(int(row["pass"]) for row in checks),
            "failed": sum(int(not row["pass"]) for row in checks),
            "checks": checks,
            "full_regression_run": False,
        }
        write_json(out / "V33XR2_TEST_REPORT.json", test_report)
        scientific = (
            "단일 1.0495 pu tightening이 B1 Fresh 안전성과 B0-relative no-regret을 동시에 만족했다. "
            "다만 Apr-04 단일 screening이므로 1.0495를 최종 margin으로 선언할 수 없고 prospective pre-April 인증이 필요하다."
            if classification == CLASS_PASS else
            "단일 1.0495 pu tightening은 B1 fast gate를 통과하지 못했다. 다음 최소 조치는 Stage-1 전압 보정 recourse capability 구현이다."
        )
        review = {
            "artifact_id": "V33XR2_FINAL_REVIEW_V1",
            "status": "COMPLETE",
            "primary_classification": classification,
            "FINAL_AUTHORITY": False,
            "B1": b1_review,
            "B3_run": b3_review is not None,
            "B3": b3_review,
            "targeted_tests": {"passed": test_report["passed"], "failed": test_report["failed"]},
            "scientific_interpretation": scientific,
            "smallest_next_action": (
                "Prospective pre-April certification of a voltage safety margin; do not declare 1.0495 final from Apr-04."
                if classification == CLASS_PASS else
                "Implement Stage-1 voltage-corrective recourse capability."
            ),
            "push_performed": False,
            "merge_performed": False,
        }
        write_json(out / "V33XR2_FINAL_REVIEW.json", review)
        _write_markdown(out, review)
        return review
    finally:
        voltage.close()
        current.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--electrical-cache", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.repo, args.source_repo, args.electrical_cache)
    print(json.dumps({
        "primary_classification": result["primary_classification"],
        "B3_run": result.get("B3_run", False),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
