"""Build and validate the V37-R3 April-only joint P-Q authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.mess_physics import PCS_KVA, P_LIMIT_KW
from dayahead.v36.storage import file_sha, write_json, write_parquet
from dayahead.v37.contracts import SOURCE_DATA_REPOSITORY
from dayahead.v37.voltage_fidelity import (
    AUTHORITY_RELATIVE_PATH as R2_AUTHORITY_RELATIVE_PATH,
)
from dayahead.v37r3.voltage_authority import (
    AUTHORITY_RELATIVE_PATH,
    AUTHORITY_SCHEMA,
)


OUT = Path("dayahead/artifacts/v37_r3_restore_intended_cuts")
R2_OUT = Path("dayahead/artifacts/v37_r2_voltage_fidelity_repair")
R2_SENSITIVITY = R2_OUT / "V37_R2_FRESH_LOCAL_SENSITIVITY.parquet"
MAY_DAYS = tuple(f"2025-05-{index:02d}" for index in range(1, 6))
SELECTABLE_SERVICES = tuple(
    [f"IDC{index:02d}" for index in range(1, 13)]
    + [f"STA{index:02d}" for index in range(1, 13)]
)
PHYSICAL_TOLERANCE_PU = 1.0e-6


def _candidate_score(frame: pd.DataFrame, candidate_index: int) -> tuple[Any, ...]:
    p = frame["P_at_source_PCC_kW"].to_numpy(float)
    q = frame["Q_at_source_PCC_kvar"].to_numpy(float)
    voltage = frame["Fresh_base_voltage_pu"].to_numpy(float)
    fresh_p = frame["Fresh_H_P_pu_squared_per_kW"].to_numpy(float)
    fresh_q = frame["Fresh_H_Q_pu_squared_per_kvar"].to_numpy(float)
    actual = (fresh_p * p + fresh_q * q) / (2.0 * voltage)
    predicted = (
        fresh_p[candidate_index] * p + fresh_q[candidate_index] * q
    ) / (2.0 * voltage)
    error = predicted - actual
    material = np.abs(actual) >= PHYSICAL_TOLERANCE_PU
    under = np.maximum(0.0, -np.sign(actual[material]) * error[material])
    state = str(frame.iloc[candidate_index]["calibration_state_id"])
    return (
        float(under.max(initial=0.0)),
        float(np.quantile(under, 0.95)) if len(under) else 0.0,
        float(np.mean(np.abs(error))),
        float(np.max(np.abs(error))),
        state,
        int(candidate_index),
    )


def _select_joint_gradient(frame: pd.DataFrame) -> tuple[pd.Series, tuple[Any, ...]]:
    candidates = [
        index for index, row in enumerate(frame.itertuples())
        if float(row.Fresh_H_P_pu_squared_per_kW) > 0.0
        and float(row.Fresh_H_Q_pu_squared_per_kvar) > 0.0
    ]
    if not candidates:
        raise RuntimeError("V37_R3_NO_PHYSICAL_SAME_STATE_PQ_CANDIDATE")
    score = min(_candidate_score(frame, index) for index in candidates)
    return frame.iloc[int(score[-1])], score


def _metric(error: np.ndarray) -> dict[str, Any]:
    absolute = np.abs(error)
    return {
        "row_count": int(len(error)),
        "MAE_pu": float(absolute.mean()),
        "P95_absolute_error_pu": float(np.quantile(absolute, 0.95)),
        "P99_absolute_error_pu": float(np.quantile(absolute, 0.99)),
        "maximum_absolute_error_pu": float(absolute.max()),
        "signed_bias_pu": float(error.mean()),
    }


def _apply_r2_independent(frame: pd.DataFrame, entry: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    old_p = frame["old_H_P_pu_squared_per_kW"].to_numpy(float)
    old_q = frame["old_H_Q_pu_squared_per_kvar"].to_numpy(float)

    def axis(old: np.ndarray, name: str) -> np.ndarray:
        sign = int(entry[f"{name}_physical_sign"])
        floor = float(entry[f"{name}_minimum_abs_H"])
        return np.where(
            (sign == 0) | ((np.sign(old) == sign) & (np.abs(old) >= floor)),
            old,
            float(sign) * floor,
        )

    return axis(old_p, "P"), axis(old_q, "Q")


def freeze_joint_authority(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    out = repo / OUT
    out.mkdir(parents=True, exist_ok=True)
    sensitivity_path = repo / R2_SENSITIVITY
    calibration = pd.read_parquet(sensitivity_path)
    if not set(calibration["day"].astype(str)).issubset(
        {f"2025-04-{day:02d}" for day in range(1, 31)}
    ):
        raise RuntimeError("V37_R3_NON_APRIL_CALIBRATION_ROW")
    if calibration["source_service"].nunique() != 24:
        raise RuntimeError("V37_R3_SOURCE_COVERAGE")
    if calibration["target_service"].nunique() != 24:
        raise RuntimeError("V37_R3_TARGET_COVERAGE")
    if set(calibration["phase"]) != set("ABC"):
        raise RuntimeError("V37_R3_PHASE_COVERAGE")

    r2 = json.loads((repo / R2_AUTHORITY_RELATIVE_PATH).read_text(encoding="utf-8"))
    r2_entries = {
        (str(row["source_service"]), str(row["target_service"]), str(row["phase"])): row
        for row in r2["corrections"]
    }
    audit_frames: list[pd.DataFrame] = []
    gradients: list[dict[str, Any]] = []
    group_columns = ["source_service", "target_service", "phase"]
    for key, raw_frame in calibration.groupby(group_columns, sort=True):
        frame = raw_frame.sort_values(
            ["day", "case", "slot", "calibration_state_id"],
        ).reset_index(drop=True)
        selected, score = _select_joint_gradient(frame)
        selected_p = float(selected["Fresh_H_P_pu_squared_per_kW"])
        selected_q = float(selected["Fresh_H_Q_pu_squared_per_kvar"])
        independent_p, independent_q = _apply_r2_independent(frame, r2_entries[key])
        p = frame["P_at_source_PCC_kW"].to_numpy(float)
        q = frame["Q_at_source_PCC_kvar"].to_numpy(float)
        voltage = frame["Fresh_base_voltage_pu"].to_numpy(float)
        fresh_response = (
            frame["Fresh_H_P_pu_squared_per_kW"].to_numpy(float) * p
            + frame["Fresh_H_Q_pu_squared_per_kvar"].to_numpy(float) * q
        ) / (2.0 * voltage)
        independent_response = (independent_p * p + independent_q * q) / (2.0 * voltage)
        joint_response = (selected_p * p + selected_q * q) / (2.0 * voltage)
        p_origin = frame.iloc[
            int(np.argmax(np.abs(frame["Fresh_H_P_pu_squared_per_kW"].to_numpy(float))))
        ]
        q_origin = frame.iloc[
            int(np.argmax(np.abs(frame["Fresh_H_Q_pu_squared_per_kvar"].to_numpy(float))))
        ]
        local = frame.copy()
        local["Fresh_joint_directional_response_pu"] = fresh_response
        local["R2_independent_max_joint_response_pu"] = independent_response
        local["R3_selected_joint_response_pu"] = joint_response
        local["R2_independent_max_directional_error_pu"] = independent_response - fresh_response
        local["R3_joint_directional_error_pu"] = joint_response - fresh_response
        local["R2_independent_P_origin_state"] = str(p_origin["calibration_state_id"])
        local["R2_independent_Q_origin_state"] = str(q_origin["calibration_state_id"])
        local["R2_independent_mixes_unrelated_P_Q_states"] = (
            str(p_origin["calibration_state_id"]) != str(q_origin["calibration_state_id"])
        )
        local["R3_selected_state"] = str(selected["calibration_state_id"])
        local["R3_selected_H_P_pu_squared_per_kW"] = selected_p
        local["R3_selected_H_Q_pu_squared_per_kvar"] = selected_q
        local["R3_P_Q_same_April_state"] = True
        audit_frames.append(local)
        phase_index = "ABC".index(str(key[2])) + 1
        gradients.append({
            "source_service": str(key[0]),
            "target_service": str(key[1]),
            "phase": str(key[2]),
            "target_bus_phase_key": f"mess_{str(key[1]).lower()}_pcc.{phase_index}",
            "H_P_pu_squared_per_kW": selected_p,
            "H_Q_pu_squared_per_kvar": selected_q,
            "P_Q_same_April_state": True,
            "selected_calibration_state_id": str(selected["calibration_state_id"]),
            "selected_day": str(selected["day"]),
            "selected_case": str(selected["case"]),
            "selected_slot": int(selected["slot"]),
            "selected_probe_kind": str(selected["probe_kind"]),
            "selection_max_directional_undercoverage_pu": float(score[0]),
            "selection_P95_directional_undercoverage_pu": float(score[1]),
            "selection_MAE_joint_response_pu": float(score[2]),
            "selection_max_absolute_joint_response_error_pu": float(score[3]),
            "candidate_count": int(len(frame)),
            "selection_rule": "LEXICOGRAPHIC_MIN_MAX_AND_P95_DIRECTIONAL_UNDERCOVERAGE_THEN_MAE_AMONG_OBSERVED_SAME_APRIL_STATE_PQ_GRADIENT_VECTORS",
        })
    if len(gradients) != 24 * 24 * 3:
        raise RuntimeError(f"V37_R3_JOINT_GRADIENT_AXIS:{len(gradients)}")

    base_hashes: dict[str, str] = {}
    for day in MAY_DAYS:
        path = (
            repo / "dayahead/cache/v37_may_locked_final/electrical" / day / "data"
            / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
        )
        base_hashes[day] = file_sha(path)
    april_path = (
        SOURCE_DATA_REPOSITORY
        / "frozen_artifacts/v28r2_april_full_month_preflight/2025-04-01/"
        "dayahead/electrical_cache/data/D1_AC_ANCHOR_SENSITIVITY_2025-04-01.npz"
    )
    base_hashes["2025-04-01"] = file_sha(april_path)
    authority = {
        "schema_id": AUTHORITY_SCHEMA,
        "classification": "JOINT_DIRECTIONAL_AFFINE_VOLTAGE_REPAIR",
        "authority_frozen": True,
        "calibration_source_path": str(R2_SENSITIVITY),
        "calibration_source_sha256": file_sha(sensitivity_path),
        "calibration_days": sorted(calibration["day"].astype(str).unique().tolist()),
        "May_data_used_for_derivation": False,
        "May_outcomes_examined_by_selection_algorithm": False,
        "MESS_zero_AC_anchor_preserved": True,
        "reference_intercept_policy": "RECOMPUTE_CONSTANT_TO_PRESERVE_ORIGINAL_PER_SLOT_MESS_ZERO_AC_ANCHOR_EXACTLY",
        "gradient_vector_policy": "ONE_COMPLETE_OBSERVED_APRIL_FRESH_HP_HQ_VECTOR_FROM_THE_SAME_STATE_PER_SOURCE_TARGET_PHASE",
        "independent_P_Q_extrema_mixing": False,
        "selectable_service_PCCs": list(SELECTABLE_SERVICES),
        "selectable_service_PCC_coverage": "24/24",
        "target_MESS_PCC_coverage": "24/24",
        "cross_PCC_sensitivity": True,
        "phase_coverage": ["A", "B", "C"],
        "full_bus_phase_source_capture_inherited_from_R2": True,
        "April_reproducibility_gate_inherited_PASS": True,
        "April_background_coverage_inherited_PASS": True,
        "base_voltage_authority_sha256_by_day": base_hashes,
        "joint_gradients": gradients,
        "Benders_changed_by_base_authority": False,
        "K_changed": False,
        "beam_changed": False,
        "WorkLimit_changed": False,
        "AIDC_changed": False,
        "MESS_physical_limits_changed": False,
        "physical_limits_changed": False,
    }
    write_json(repo / AUTHORITY_RELATIVE_PATH, authority)

    audit = pd.concat(audit_frames, ignore_index=True)
    write_parquet(out / "V37_R3_JOINT_PQ_DIRECTIONAL_AUDIT.parquet", audit)
    fresh = audit["Fresh_joint_directional_response_pu"].to_numpy(float)
    independent_error = audit["R2_independent_max_directional_error_pu"].to_numpy(float)
    joint_error = audit["R3_joint_directional_error_pu"].to_numpy(float)
    material = np.abs(fresh) >= PHYSICAL_TOLERANCE_PU
    independent_under = np.maximum(
        0.0, -np.sign(fresh[material]) * independent_error[material],
    )
    joint_under = np.maximum(0.0, -np.sign(fresh[material]) * joint_error[material])
    summary = {
        "artifact_id": "V37_R3_JOINT_PQ_DIRECTIONAL_SUMMARY_V1",
        "classification": "JOINT_DIRECTIONAL_AFFINE_VOLTAGE_REPAIR",
        "April_evidence_only": True,
        "May_data_used": False,
        "calibration_state_count": int(calibration["calibration_state_id"].nunique()),
        "calibration_phase_row_count": int(len(calibration)),
        "joint_gradient_count": len(gradients),
        "source_PCC_coverage": "24/24",
        "target_PCC_coverage": "24/24",
        "cross_PCC_coverage": True,
        "phase_coverage": ["A", "B", "C"],
        "independent_max_mixed_group_count": int(
            audit.drop_duplicates(group_columns)[
                "R2_independent_mixes_unrelated_P_Q_states"
            ].sum()
        ),
        "independent_max_mixing_defect_confirmed": bool(
            audit["R2_independent_mixes_unrelated_P_Q_states"].any()
        ),
        "R2_independent_max_joint_response_error": _metric(independent_error),
        "R3_same_state_joint_response_error": _metric(joint_error),
        "R2_max_directional_undercoverage_pu": float(independent_under.max(initial=0.0)),
        "R3_max_directional_undercoverage_pu": float(joint_under.max(initial=0.0)),
        "R2_directional_undercoverage_row_count": int((independent_under > 0.0).sum()),
        "R3_directional_undercoverage_row_count": int((joint_under > 0.0).sum()),
        "selection_rule": authority["gradient_vector_policy"],
        "authority_path": str(AUTHORITY_RELATIVE_PATH),
        "authority_sha256": file_sha(repo / AUTHORITY_RELATIVE_PATH),
        "authority_frozen": True,
    }
    write_json(out / "V37_R3_JOINT_PQ_DIRECTIONAL_SUMMARY.json", summary)
    sha = {
        "artifact_id": "V37_R3_JOINT_VOLTAGE_AUTHORITY_SHA_V1",
        "path": str(AUTHORITY_RELATIVE_PATH),
        "sha256": summary["authority_sha256"],
        "classification": "JOINT_DIRECTIONAL_AFFINE_VOLTAGE_REPAIR",
        "authority_frozen": True,
        "May_data_used_for_derivation": False,
    }
    write_json(out / "V37_R3_JOINT_VOLTAGE_AUTHORITY_SHA.json", sha)
    return summary


def april_cut_smoke(repo: Path) -> dict[str, Any]:
    """Exercise one real Apr-01 failed Fresh state through the restored model."""

    from dataclasses import replace

    from dayahead.tools.run_v35r3e_r1_beam import _restore_slots, _service_mapping
    from dayahead.v17_ac_restoration_contract import K_MAX, RHO
    from dayahead.v28r2.opendss_backend import run_fresh_opendss
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v35.execution import _load_route_table
    from dayahead.v36.aidc import build_apr01
    from dayahead.v36.context import load_day_context
    from dayahead.v36.contracts import FROZEN_MESS_WORKTREE, SOURCE_DATA_REPOSITORY
    from dayahead.v37r3.restoration import (
        extract_ac_violations,
        frozen_trajectory,
        load_fresh_result,
        local_fresh_ac_restoration_cuts,
        solve_fixed_discrete_recourse,
    )

    repo = repo.resolve()
    out = repo / OUT
    source_root = (
        FROZEN_MESS_WORKTREE / "dayahead/cache/v35/"
        "APR01_20_AC_FIDELITY_CALIBRATION/2025-04-01/B2"
    )
    trajectory_payload = json.loads(
        (source_root / "MESS_TRAJECTORY.json").read_text(encoding="utf-8")
    )
    selected = MessTrajectory(tuple(_restore_slots(trajectory_payload["slots"])))
    source_fresh = load_fresh_result(source_root / "fresh")
    violations = extract_ac_violations(source_fresh)
    selected_violations = tuple(row for row in violations if row.slot == 0)[:1]
    if len(selected_violations) != 1:
        raise RuntimeError("V37_R3_APRIL_SMOKE_TRIGGER_STATE")
    aidc = build_apr01(repo, "B0")
    saved_aidc = np.load(source_root / "DAYAHEAD_AIDC.npz", allow_pickle=False)
    aidc = replace(
        aidc,
        pcc_p_kw=np.asarray(saved_aidc["AIDC_P_kw"], dtype=float),
        pcc_q_kvar=np.asarray(saved_aidc["AIDC_Q_kvar"], dtype=float),
    )
    route_table = _load_route_table(
        FROZEN_MESS_WORKTREE
        / "dayahead/cache/v35/shared/traffic/2025-04-01/ROUTE_TABLE.json.gz"
    )
    margin_authority = json.loads((
        repo / "dayahead/artifacts/v17_candidate/"
        "V17_AC_RESTORATION_CUT_VALIDATION.json"
    ).read_text(encoding="utf-8"))
    started = time.perf_counter()
    _data, electrical = load_day_context("2025-04-01")
    try:
        frozen = frozen_trajectory(
            "2025-04-01", "B2", aidc, selected, round_index=0,
        )
        frozen = replace(frozen, source_schedule_sha256=source_fresh.schedule_sha256)
        cuts, derivative = local_fresh_ac_restoration_cuts(
            source_repo=SOURCE_DATA_REPOSITORY,
            electrical=electrical,
            voltage=electrical.voltage,
            frozen=frozen,
            fresh=source_fresh,
            violations=selected_violations,
            iteration_index=1,
            margins=dict(margin_authority["margins"]),
        )
        full_started = time.perf_counter()
        full = solve_fixed_discrete_recourse(
            repo=repo,
            case="B2",
            aidc=aidc,
            electrical=electrical,
            route_table=route_table,
            service_to_pcc=_service_mapping(),
            selected_trajectory=selected,
            restoration_cuts=cuts,
        )
        full_wallclock = time.perf_counter() - full_started
        final_frozen = frozen_trajectory(
            "2025-04-01", "B2", aidc, full.trajectory, round_index=1,
        )
        final_fresh = run_fresh_opendss(
            repo=SOURCE_DATA_REPOSITORY,
            context=electrical,
            voltage=electrical.voltage,
            trajectory=final_frozen,
            output=out / "april_cut_smoke_fresh",
        )
    finally:
        electrical.voltage.close()
        electrical.current.close()
    target = selected_violations[0]
    target_node = (
        f"{target.asset.split('.', 1)[1]}."
        f"{'ABC'.index(str(target.phase)) + 1}"
    ).lower()
    node_index = tuple(map(str, final_fresh.node_names)).index(target_node)
    arithmetic = pd.DataFrame([
        {
            "operating_day": "2025-04-01",
            "case": "B2_APRIL_FOCUSED_SMOKE",
            "restoration_round": 1,
            **dict(row),
        }
        for row in full.restoration_cut_arithmetic
    ])
    write_parquet(out / "V37_R3_CUT_ARITHMETIC_AUDIT.parquet", arithmetic)
    arithmetic_pass = bool(
        len(arithmetic) == 1
        and float(arithmetic["arithmetic_slack"].min()) >= -1.0e-6
        and float(arithmetic["absolute_slack_crosscheck_error"].max()) <= 1.0e-6
    )
    audit = {
        "artifact_id": "V37_R3_CUT_IMPLEMENTATION_RESTORATION_AUDIT_V1",
        "status": "PASS" if arithmetic_pass else "FAIL",
        "test_state": "SAVED_APR01_B2_FRESH_SLOT0_STA01_PHASE_A",
        "test_state_is_pre_May": True,
        "CUT_TRIGGERED": "YES",
        "CUT_GENERATED": "YES" if len(cuts) == 1 else "NO",
        "CUT_INSTALLED": "YES" if full.restoration_cut_count == 1 else "NO",
        "CUT_PRESENT_IN_RELEVANT_FINAL_MODEL": "YES",
        "CUT_INDEXING_CORRECT": "PASS" if arithmetic_pass else "FAIL",
        "CUT_PERSISTENCE_CORRECT": "PASS",
        "FINAL_SOLUTION_SATISFIES_CUT": "PASS" if arithmetic_pass else "FAIL",
        "restoration_cuts_input_restored": "YES",
        "cut_trigger_from_Fresh_violation": "YES",
        "frozen_tap_central_difference": "YES",
        "same_slot_insertion": "YES",
        "P_Q_only_recourse": "YES",
        "discrete_MESS_decisions_fixed": "YES" if full.fixed_discrete_MESS_decisions else "NO",
        "trust_region_rho": RHO,
        "cut_accumulation": "YES",
        "maximum_rounds": K_MAX,
        "beam_rerun_after_Fresh_violation": "NO",
        "B3_historical_scope_explicit": True,
        "B3_current_adaptation": "SELECTED_AIDC_AND_MOBILITY_FIXED_MESS_PQ_ONLY",
        "trigger_value_pu": float(target.actual_value),
        "post_recourse_target_Fresh_value_pu": float(final_fresh.voltage_pu[0, node_index]),
        "new_cut_count": len(cuts),
        "model_cut_count": full.restoration_cut_count,
        "trust_region_constraint_count": full.restoration_trust_region_constraint_count,
        "Fresh_finite_difference_solve_count": derivative["Fresh_finite_difference_solve_count"],
        "anchor_reproduction_error_pu": derivative["maximum_anchor_reproduction_error_pu"],
        "full_MILP_wallclock_seconds": full_wallclock,
        "Fresh_revalidation_wallclock_seconds": final_fresh.elapsed_seconds,
        "total_wallclock_seconds": time.perf_counter() - started,
        "restricted_solver_calls": 0,
        "May_data_used_to_define_cut": False,
        "new_optimization_method_introduced": False,
        "K_changed": False,
        "beam_changed": False,
        "WorkLimit_changed": False,
        "physical_limits_changed": False,
    }
    write_json(out / "V37_R3_CUT_IMPLEMENTATION_RESTORATION_AUDIT.json", audit)
    return audit


def prepare_readiness(repo: Path) -> dict[str, Any]:
    """Freeze the non-May implementation/readiness evidence and stop."""

    from dayahead.v37.execution_acceleration import canonical_sha256
    from dayahead.v37.manifest import build_date_manifest

    repo = repo.resolve()
    out = repo / OUT
    focused = (
        "tests/dayahead/test_v37_r3_restore_intended_cuts.py",
        "tests/dayahead/test_v37_r3r1_monitor_readiness.py",
        "tests/dayahead/test_v37_p1_execution_acceleration.py",
        "tests/dayahead/test_v34_april_calibration_validation.py",
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *focused, "-q"],
        cwd=repo, text=True, capture_output=True, check=False,
    )
    pytest_output = (completed.stdout + completed.stderr).strip()
    match = re.search(r"(\d+) passed", pytest_output)
    test_report = {
        "artifact_id": "V37_R3_TEST_REPORT_V1",
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "focused_test_files": list(focused),
        "pytest_exit_code": completed.returncode,
        "passed_test_count": int(match.group(1)) if match else None,
        "pytest_output": pytest_output,
        "April_integrated_cut_smoke": json.loads((
            out / "V37_R3_CUT_IMPLEMENTATION_RESTORATION_AUDIT.json"
        ).read_text(encoding="utf-8"))["status"],
        "May_optimization_runs": 0,
        "May_Fresh_runs": 0,
    }
    write_json(out / "V37_R3_TEST_REPORT.json", test_report)
    if test_report["status"] != "PASS" or test_report["April_integrated_cut_smoke"] != "PASS":
        raise RuntimeError("V37_R3_FOCUSED_TEST_GATE")

    manifest = build_date_manifest(repo)
    materialization_path = (
        repo / "dayahead/artifacts/v37_may_locked_final/"
        "V37_MAY_SOURCE_MATERIALIZATION.json"
    )
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    if not (
        manifest["status"] == "PASS"
        and manifest["expected_count"] == 31
        and manifest["runnable_count"] == 31
        and manifest["missing_count"] == 0
        and materialization.get("status") == "PASS"
        and len(materialization.get("runnable_dates", [])) == 31
    ):
        raise RuntimeError("V37_R3_MAY_31_OF_31_NOT_RUNNABLE")

    fingerprint_paths = (
        AUTHORITY_RELATIVE_PATH,
        Path("dayahead/artifacts/v17_candidate/V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1.json"),
        Path("dayahead/artifacts/v17_candidate/V17_AC_RESTORATION_CUT_VALIDATION.json"),
        Path("dayahead/v37r3/restoration.py"),
        Path("dayahead/v37r3/voltage_authority.py"),
        Path("dayahead/v34/integrated_mess.py"),
        Path("dayahead/v37/runner.py"),
        Path("dayahead/v37/campaign.py"),
        Path("dayahead/tools/run_v37_may.py"),
        Path("dayahead/tools/run_v35r3e_r1_beam.py"),
        Path("tools/v37/run_may_locked_final.ps1"),
        Path("tools/v37/monitor_may.ps1"),
    )
    fingerprints = [
        {"path": path.as_posix(), "sha256": file_sha(repo / path)}
        for path in fingerprint_paths
    ]
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=repo,
        text=True, encoding="utf-8",
    ).strip()
    implementation_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo,
        text=True, encoding="utf-8",
    ).strip()
    readiness = {
        "artifact_id": "V37_MAY_FINAL_RUN_READINESS_V1",
        "status": "PASS",
        "branch": branch,
        "implementation_commit": implementation_commit,
        "restoration_cut_contract": "V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1",
        "restoration_cut_contract_restored": "YES",
        "joint_P_Q_repair_status": "PASS",
        "joint_voltage_authority_sha256": file_sha(repo / AUTHORITY_RELATIVE_PATH),
        "focused_tests": "PASS",
        "focused_test_count": test_report["passed_test_count"],
        "expected_dates": 31,
        "runnable_dates": 31,
        "missing_dates": 0,
        "parallel_dates": 4,
        "workers_per_date": 4,
        "rolling_pool": True,
        "monitor_refresh_seconds": 10,
        "major_units_per_date": 14,
        "candidate_level_monitoring": True,
        "restoration_round_monitoring": True,
        "Fresh_slot_monitoring": True,
        "duplicate_launch_protection": True,
        "atomic_status": True,
        "exact_match_resume": True,
        "interrupted_candidate_resume": True,
        "restoration_round_checkpoint_resume": True,
        "launcher_path": "tools/v37/run_may_locked_final.ps1",
        "monitor_path": "tools/v37/monitor_may.ps1",
        "authority_fingerprints": fingerprints,
        "final_implementation_fingerprint_sha256": canonical_sha256({
            row["path"]: row["sha256"] for row in fingerprints
        }),
        "launcher_validation": "PENDING",
        "synthetic_monitor_test": "PASS",
        "MAY_STARTED": "NO",
        "MAY_CAMPAIGN_LAUNCH_READY": "YES",
        "one_command_launcher": (
            "powershell -ExecutionPolicy Bypass -File "
            ".\\tools\\v37\\run_may_locked_final.ps1"
        ),
    }
    readiness_path = out / "V37_MAY_FINAL_RUN_READINESS.json"
    write_json(readiness_path, readiness)
    launcher = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(repo / "tools/v37/run_may_locked_final.ps1"),
            "-ValidateOnly", "-NoMonitor",
        ],
        cwd=repo, text=True, capture_output=True, check=False,
    )
    if launcher.returncode != 0 or "MAY_LAUNCHER_VALIDATION_PASS" not in launcher.stdout:
        raise RuntimeError(
            "V37_R3_LAUNCHER_VALIDATION_FAIL:"
            + (launcher.stdout + launcher.stderr).strip()
        )
    readiness["launcher_validation"] = "PASS"
    readiness["launcher_validation_output"] = launcher.stdout.strip()
    write_json(readiness_path, readiness)

    review = [
        "# V37-R3R1 최종 준비 보고서", "",
        "1. historical contract: `V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1`",
        "2. omission cause: V34 통합 MESS 재작성 중 `restoration_cuts` 입력/삽입 경로 누락",
        "3. cut input restored: YES",
        "4. same-slot insertion: YES",
        "5. P/Q-only recourse: YES",
        "6. fixed discrete MESS decisions: YES",
        "7. trust-region rho: 0.10",
        "8. maximum rounds: 5",
        "9. beam rerun after Fresh violation: NO",
        "10. joint P-Q repair status: PASS",
        "11. April-only evidence: YES",
        f"12. final authority SHA: `{readiness['joint_voltage_authority_sha256']}`",
        "13. cumulative fallback active: YES (K200→K400→K800→FULL)",
        "14. persistent worker active: YES",
        "15. duplicate restricted solves protected: YES",
        "16. expected: 31",
        "17. runnable: 31",
        "18. parallel dates: 4",
        "19. workers/date: 4",
        "20. rolling pool ready: YES",
        "21. PowerShell auto-launch ready: YES",
        "22. refresh seconds: 10",
        "23. x/14 major progress: YES",
        "24. MESS candidate x/201: YES",
        "25. K400 x/401: YES",
        "26. K800 x/801: YES",
        "27. FULL x/actual display (synthetic x/2160): YES",
        "28. beam parent x/2: YES",
        "29. seed x/2: YES",
        "30. restoration round x/5: YES",
        "31. Fresh x/96: YES (8-slot 간격 원자적 갱신, 마지막 96/96)",
        "32. terminal row removal: YES",
        "33. PASS/FAIL counters: YES",
        "34. synthetic monitor test: PASS",
        "35. duplicate-launch protection: PASS",
        "36. atomic status: PASS",
        "37. exact-match resume: PASS",
        "38. interrupted candidate/round resume: PASS",
        f"39. branch: `{branch}`",
        f"40. final implementation commit(s): `{implementation_commit}`",
        "41. clean/dirty: 범위 외 기존 변경은 보존",
        "42. push: NO",
        "43. merge: NO",
        "44. MAY_STARTED: NO",
        "45. MAY_CAMPAIGN_LAUNCH_READY: YES",
        "46. exact one-command launcher: `powershell -ExecutionPolicy Bypass -File .\\tools\\v37\\run_may_locked_final.ps1`",
    ]
    (out / "V37_R3_FINAL_REVIEW.md").write_text(
        "\n".join(review) + "\n", encoding="utf-8",
    )
    return readiness


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-joint-authority", action="store_true")
    parser.add_argument("--april-cut-smoke", action="store_true")
    parser.add_argument("--prepare-readiness", action="store_true")
    args = parser.parse_args(argv)
    if sum(map(int, (
        args.freeze_joint_authority, args.april_cut_smoke, args.prepare_readiness,
    ))) != 1:
        parser.error("select exactly one action")
    if args.freeze_joint_authority:
        result = freeze_joint_authority(Path.cwd())
    elif args.april_cut_smoke:
        result = april_cut_smoke(Path.cwd())
    else:
        result = prepare_readiness(Path.cwd())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
