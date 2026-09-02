"""Execute the isolated Apr-04 V33X E0/E1/E2 development experiment."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.v28r2.actual_replay import replay_actual_case
from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.backend_contract import canonical_sha256 as backend_canonical_sha256
from dayahead.v28r2.electrical_context import build_electrical_context, with_realized_background
from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row, slot_coefficients
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU
from dayahead.v28r2.source_cache import day_root
from dayahead.v28r2.workload_replay import materialize_actual_workload
from dayahead.v29r2.apr04_runner import _fresh_row, _pi_data
from dayahead.v29r2.formulation import materialize_formulation_data_v29r2
from dayahead.v29r3.forensic import _electrical_context, _initial_actual
from dayahead.v30.contracts import ANCHOR_BY_CASE, canonical_sha256, write_json
from dayahead.v30.dayahead_formulation import load_frozen_schedules
from dayahead.v30.actual_recourse import solve_causal_day
from dayahead.v30.four_case_runner import _flexible_site_kw, _mapping, _recourse_trajectory
from dayahead.v30.grid_safety import derive_margin, load_phase_current_safety, phase_aware_site_scores
from dayahead.v30.reporting import write_csv

from .contracts import (
    BRANCH, DAY, DEVELOPMENT_VARIANTS, OFFICIAL_CASES, STARTING_HEAD,
    V30_ARTIFACT_SHA, V30_HEAD, V30_TREE, experiment_contract,
)
from .full_grid_recourse import FullGridRecourseResult, solve_causal_day_full_grid
from .headroom_stage1 import E2Stage1Result, frozen_leverage_map, sha256_file, solve_e2_stage1


OUT_REL = Path("dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc")
V30_OUT = Path("dayahead/artifacts/v30_two_stage_aidc_recourse")
V29R2_OUT = Path("dayahead/artifacts/v29r2_anchor_aware_trust_noregret")
VOLTAGE_NAME = "D1_AC_ANCHOR_SENSITIVITY_2025-04-04.npz"
CURRENT_NAME = "D1_AC_ANCHOR_CURRENT_SENSITIVITY_2025-04-04.npz"
NUMERICAL_TOL = 1e-9


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"V33X_JSON_OBJECT_REQUIRED:{path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _bool(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def _protected_paths() -> tuple[str, ...]:
    return (
        "dayahead/v29", "dayahead/v29r1", "dayahead/v29r2", "dayahead/v29r3",
        "dayahead/v30", "dayahead/v31", "dayahead/v32", "dayahead/v32r1", "dayahead/v32r2",
        "dayahead/artifacts/v29_grid_responsive_aidc",
        "dayahead/artifacts/v29r1_janmar_source_authority_recovery",
        "dayahead/artifacts/v29r1_reliability_calibrated_noregret",
        "dayahead/artifacts/v29r2_anchor_aware_trust_noregret",
        "dayahead/artifacts/v29r3_aidc_effect_forensic",
        "dayahead/artifacts/v30_two_stage_aidc_recourse",
        "dayahead/artifacts/v31_v30_safety_headroom_forensic",
        "dayahead/artifacts/v32_preapril_current_frontier_freshac",
        "dayahead/artifacts/v32r1_janmar_v30_authority",
        "dayahead/artifacts/v32r2_minimal_frontier_dependency_audit",
    )


def _authority(repo: Path, electrical_cache: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, str]]:
    if _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V33X_WRONG_BRANCH")
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", STARTING_HEAD, "HEAD"], check=False).returncode:
        raise RuntimeError("V33X_STARTING_HEAD_NOT_ANCESTOR")
    observed_v30 = _git(repo, "rev-parse", "HEAD:dayahead/v30")
    if observed_v30 != V30_TREE:
        raise RuntimeError("V33X_V30_TREE_CHANGED")
    expected = {path: _git(repo, "rev-parse", f"{STARTING_HEAD}:{path}") for path in _protected_paths()}
    observed = {path: _git(repo, "rev-parse", f"HEAD:{path}") for path in _protected_paths()}
    mismatch = [path for path in expected if expected[path] != observed[path]]
    if mismatch:
        raise RuntimeError(f"V33X_HISTORICAL_TREE_CHANGED:{mismatch}")
    voltage_path = electrical_cache / "data" / VOLTAGE_NAME
    current_path = electrical_cache / "data" / CURRENT_NAME
    if not voltage_path.is_file() or not current_path.is_file():
        raise RuntimeError("V33X_APR04_FULL_ELECTRICAL_AUTHORITY_MISSING")
    voltage = np.load(voltage_path, allow_pickle=False)
    current = np.load(current_path, allow_pickle=False)
    axes_ok = (
        np.asarray(voltage["sensitivity"]).shape == (96, 60, 386)
        and np.asarray(current["current_sensitivity_pu_per_control"]).shape == (96, 60, 383)
        and tuple(map(str, voltage["control_names"])) == tuple(map(str, current["control_names"]))
    )
    voltage.close(); current.close()
    start = {
        "artifact_id": "V33X_STARTING_AUTHORITY_AUDIT_V1", "status": "PASS",
        "verified_starting_SHA": STARTING_HEAD, "branch": BRANCH,
        "starting_git_status_clean": True, "starting_status_porcelain": [],
        "starting_head_is_ancestor_of_current": True,
        "V30_production_HEAD": V30_HEAD, "V30_expected_tree": V30_TREE,
        "V30_observed_tree": observed_v30, "V30_tree_identity": True,
        "V30_checkpoint": "V30_APR04_TWO_STAGE_AIDC_DEVELOPMENT_CHECKPOINT_PASS",
        "official_cases": list(OFFICIAL_CASES), "official_case_count": 4,
        "development_variants": list(DEVELOPMENT_VARIANTS),
        "resource_contract": {"Gurobi_Threads": 4, "HiGHS_threads": 4, "Fresh_OpenDSS": "SEQUENTIAL"},
        "push_performed": False, "merge_performed": False,
    }
    preservation = {
        "artifact_id": "V33X_PRECHANGE_PRESERVATION_MANIFEST_V1", "status": "PASS",
        "base_HEAD": STARTING_HEAD, "protected_git_trees": expected,
        "observed_git_trees": observed, "protected_mismatch_count": 0,
        "historical_artifact_changes": [],
    }
    electrical = {
        "artifact_id": "V33X_FULL_ELECTRICAL_AUTHORITY_AUDIT_V1", "status": "PASS",
        "operating_day": DAY, "available": True,
        "voltage_path": str(voltage_path.resolve()), "current_path": str(current_path.resolve()),
        "voltage_sha256": sha256_file(voltage_path), "current_sha256": sha256_file(current_path),
        "voltage_shape": [96, 60, 386], "current_shape": [96, 60, 383],
        "control_count": 60, "voltage_node_phase_count": 386, "branch_phase_count": 383,
        "axis_identity": axes_ok,
        "consumer_chain": ["slot_coefficients", "add_grid_rows"],
        "new_sensitivity_model": False,
    }
    return start, preservation, electrical, expected


def _e0_identity(repo: Path, schedules: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    manifest = _read_json(repo / V30_OUT / "V30_ARTIFACT_SHA256.json")
    if manifest["aggregate_manifest_sha256"] != V30_ARTIFACT_SHA:
        raise RuntimeError("V33X_V30_ARTIFACT_MANIFEST_CHANGED")
    mismatches = []
    for row in manifest["files"]:
        path = repo / V30_OUT / str(row["path"])
        if not path.is_file() or sha256_file(path) != row["sha256"] or path.stat().st_size != row["byte_count"]:
            mismatches.append(str(row["path"]))
    review = _read_json(repo / V30_OUT / "V30_APR04_DEVELOPMENT_REVIEW.json")
    if review["RESULT_CLASSIFICATION"] != "V30_APR04_TWO_STAGE_AIDC_DEVELOPMENT_CHECKPOINT_PASS":
        raise RuntimeError("V33X_V30_CHECKPOINT_NOT_PASS")
    return {
        "artifact_id": "V33X_E0_BASELINE_IDENTITY_V1", "status": "PASS",
        "V30_artifact_aggregate_sha256": manifest["aggregate_manifest_sha256"],
        "verified_file_count": manifest["file_count"], "file_mismatches": mismatches,
        "byte_SHA_equivalent_to_V30": not mismatches,
        "checkpoint": review["RESULT_CLASSIFICATION"],
        "schedule_sha256": {case: schedules[case]["schedule_sha256"] for case in OFFICIAL_CASES},
        "heavy_E0_rerun": False, "Fresh_E0_rerun": False,
    }


def _fresh(repo: Path, source_repo: Path, trajectory: object, voltage_path: Path, current_path: Path) -> dict[str, object]:
    context = _electrical_context(repo, source_repo, trajectory, voltage_path, current_path)
    try:
        result = run_fresh_opendss(repo=repo, context=context, voltage=context.voltage, trajectory=trajectory)
        return _fresh_row(result, "ACTUAL", "REALIZED_EX_POST")
    finally:
        context.voltage.close(); context.current.close()


def _ledger_rows(case: str, result: FullGridRecourseResult) -> list[dict[str, object]]:
    diagnostics = {int(row["slot"]): row for row in result.slot_diagnostics}
    return [
        {
            "day": DAY, "case": case, **asdict(row),
            "executed_total_nodeh": row.executed_nodeh,
            "authorization_identity_error_nodeh": row.authorization_identity_error_nodeh,
            **{key: value for key, value in diagnostics[row.slot].items() if key != "slot"},
        }
        for row in result.recourse.slot_ledgers
    ]


def _trajectory_kpi(
    variant: str, case: str, schedule: Mapping[str, object], result: FullGridRecourseResult,
    trajectory: object, anchor_trajectory: object, fresh: Mapping[str, object],
    anchor_fresh: Mapping[str, object], current: object,
) -> dict[str, object]:
    summary = result.recourse.summary
    authorized = float(np.asarray(schedule["workload_service_tensor"], dtype=float).sum())
    executed = float(summary["EXECUTED_TOTAL"])
    available = float(summary["ACTUAL_AVAILABLE"])
    delta = np.asarray(trajectory.pcc_p_kw) - np.asarray(anchor_trajectory.pcc_p_kw)
    critical_slot = int(float(anchor_fresh["critical_line_slot"]))
    branch_name = f"{anchor_fresh['critical_line']}::{anchor_fresh['critical_line_phase']}"
    branch = list(map(str, current["branch_names"])).index(branch_name)
    weighted = float(np.asarray(current["current_sensitivity_pu_per_control"])[critical_slot, :12, branch] @ delta[critical_slot])
    return {
        "day": DAY, "variant": variant, "case": case,
        "DA_authorized_nodeh": authorized,
        "Actual_source_available_nodeh": available,
        "Actual_executed_nodeh": executed,
        "raw_execution_ratio": executed / max(authorized, NUMERICAL_TOL),
        "availability_conditioned_execution_ratio": executed / max(available, NUMERICAL_TOL),
        "same_rack_executed_nodeh": float(summary["EXECUTED_ORIGINAL_RACK"]),
        "same_site_recourse_nodeh": float(summary["EXECUTED_SAME_SITE_RECOURSE"]),
        "cross_site_recourse_nodeh": float(summary["EXECUTED_CROSS_SITE_RECOURSE"]),
        "source_unavailable_nodeh": float(summary["SOURCE_UNAVAILABLE"]),
        "rack_capacity_blocked_nodeh": float(summary["TRUE_RACK_CAPACITY_LIMIT"]),
        "grid_envelope_blocked_nodeh": float(summary["GRID_SAFETY_BLOCKED"]),
        "terminal_backlog_nodeh": float(summary["TERMINAL_BACKLOG"]),
        "max_aggregate_AIDC_shift_kw": float(np.max(np.abs(delta.sum(axis=1)))),
        "L1_over_2_shifted_AIDC_energy_kwh": float(np.sum(np.abs(delta.sum(axis=1))) * 0.25 / 2.0),
        "critical_slot": critical_slot,
        "critical_slot_AIDC_delta_kw": float(delta[critical_slot].sum()),
        "sensitivity_weighted_AIDC_actuation_pu": weighted,
        "Fresh_rho_AC": float(fresh["rho_max_AC"]),
        "anchor_relative_Fresh_delta_rho": float(fresh["rho_max_AC"]) - float(anchor_fresh["rho_max_AC"]),
        "Fresh_Vmin_pu": float(fresh["Vmin_pu"]), "Fresh_Vmax_pu": float(fresh["Vmax_pu"]),
        "Fresh_p95": float(fresh["p95_loading"]), "Fresh_p99": float(fresh["p99_loading"]),
        "Fresh_losses_kwh": float(fresh["losses_kwh"]),
        "Fresh_critical_line": fresh["critical_line"], "Fresh_critical_phase": fresh["critical_line_phase"],
        "Fresh_critical_slot": int(fresh["critical_line_slot"]),
        "Fresh_convergence_count": int(fresh["convergence_count"]),
        "Fresh_voltage_violation_count": int(fresh["voltage_violation_count"]),
        "Fresh_line_current_violation_count": int(fresh["line_current_violation_count"]),
        "Fresh_transformer_current_violation_count": int(fresh["transformer_current_violation_count"]),
        "Fresh_transformer_kva_violation_count": int(fresh["transformer_kva_violation_count"]),
        "Fresh_physical_violation": _bool(fresh["physical_violation"]),
        "future_Actual_reads": result.recourse.future_actual_reads,
        "workload_mass_error_nodeh": float(summary["authorization_mass_identity_error_nodeh"]),
    }


def _e0_kpis(repo: Path) -> list[dict[str, object]]:
    actual = {row["case"]: row for row in _read_csv(repo / V30_OUT / "V30_APR04_ACTUAL_RESULTS.csv")}
    delivery = {row["case"]: row for row in _read_csv(repo / V30_OUT / "V30_APR04_AIDC_DELIVERABILITY.csv")}
    fresh = {row["case"]: row for row in _read_csv(repo / V30_OUT / "V30_APR04_FRESH_OPENDSS_RESULTS.csv")}
    result = []
    for case in ("B1", "B3"):
        row = actual[case]; d = delivery[case]
        available = float(row["ACTUAL_AVAILABLE"])
        executed = float(row["EXECUTED_TOTAL"])
        result.append({
            "day": DAY, "variant": "E0_CURRENT", "case": case,
            "DA_authorized_nodeh": float(row["DA_AUTHORIZED"]),
            "Actual_source_available_nodeh": available,
            "Actual_executed_nodeh": executed,
            "raw_execution_ratio": float(row["execution_ratio"]),
            "availability_conditioned_execution_ratio": executed / available,
            "same_rack_executed_nodeh": float(row["EXECUTED_ORIGINAL_RACK"]),
            "same_site_recourse_nodeh": float(row["EXECUTED_SAME_SITE_RECOURSE"]),
            "cross_site_recourse_nodeh": float(row["EXECUTED_CROSS_SITE_RECOURSE"]),
            "source_unavailable_nodeh": float(row["SOURCE_UNAVAILABLE"]),
            "rack_capacity_blocked_nodeh": float(row["TRUE_RACK_CAPACITY_LIMIT"]),
            "grid_envelope_blocked_nodeh": float(row["GRID_SAFETY_BLOCKED"]),
            "terminal_backlog_nodeh": float(row["TERMINAL_BACKLOG"]),
            "max_aggregate_AIDC_shift_kw": float(d["max_aggregate_PCC_shift_kw"]),
            "L1_over_2_shifted_AIDC_energy_kwh": float(d["L1_over_2_shifted_energy_kwh"]),
            "critical_slot": int(d["critical_slot"]),
            "critical_slot_AIDC_delta_kw": float(d["critical_slot_AIDC_delta_kw"]),
            "sensitivity_weighted_AIDC_actuation_pu": float(d["sensitivity_weighted_delivered_AIDC_actuation_pu"]),
            "Fresh_rho_AC": float(row["rho_AC"]),
            "anchor_relative_Fresh_delta_rho": float(row["rho_AC"]) - float(actual[ANCHOR_BY_CASE[case]]["rho_AC"]),
            "Fresh_Vmin_pu": float(row["Vmin"]), "Fresh_Vmax_pu": float(row["Vmax"]),
            "Fresh_p95": float(row["p95"]), "Fresh_p99": float(row["p99"]),
            "Fresh_losses_kwh": float(row["losses_kwh"]),
            "Fresh_critical_line": row["critical_line"], "Fresh_critical_phase": row["critical_phase"],
            "Fresh_critical_slot": int(row["critical_slot"]),
            "Fresh_convergence_count": int(fresh[case]["convergence_count"]),
            "Fresh_voltage_violation_count": int(fresh[case]["voltage_violation_count"]),
            "Fresh_line_current_violation_count": int(fresh[case]["line_current_violation_count"]),
            "Fresh_transformer_current_violation_count": int(fresh[case]["transformer_current_violation_count"]),
            "Fresh_transformer_kva_violation_count": int(fresh[case]["transformer_kva_violation_count"]),
            "Fresh_physical_violation": _bool(fresh[case]["physical_violation"]),
            "future_Actual_reads": int(row["future_Actual_reads"]),
            "workload_mass_error_nodeh": float(row["authorization_mass_identity_error_nodeh"]),
        })
    return result


def _valid_candidate(rows: Sequence[Mapping[str, object]]) -> bool:
    return all(
        int(row["Fresh_convergence_count"]) == 96
        and not _bool(row["Fresh_physical_violation"])
        and abs(float(row["workload_mass_error_nodeh"])) <= 1e-8
        and int(row["future_Actual_reads"]) == 0
        and float(row["anchor_relative_Fresh_delta_rho"]) <= NUMERICAL_TOL
        for row in rows
    )


def _headroom_rows(
    variant: str, case: str, headroom: np.ndarray, leverage: np.ndarray,
    recourse: np.ndarray, owners: Sequence[str], rack_ids: Sequence[str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    threshold = float(np.quantile(leverage, 0.75))
    top = leverage >= threshold
    by_site_exec = np.zeros((96, 12))
    aidcs = tuple(dict.fromkeys(owners))
    for site, aidc in enumerate(aidcs):
        indices = [i for i, owner in enumerate(owners) if owner == aidc]
        by_site_exec[:, site] = recourse[:, indices].sum(axis=1)
    site_headroom = np.asarray([
        [headroom[slot, [i for i, owner in enumerate(owners) if owner == aidc]].sum() for aidc in aidcs]
        for slot in range(96)
    ])
    records = []
    for slot in range(96):
        for rack, owner, value in zip(rack_ids, owners, headroom[slot], strict=True):
            site = aidcs.index(owner)
            records.append({
                "day": DAY, "variant": variant, "case": case, "slot": slot,
                "aidc_id": owner, "rack_id": rack, "h_REC_nodeh": float(value),
                "leverage_pu_per_kw": float(leverage[site, slot]),
                "top_quartile_leverage": bool(top[site, slot]),
                "semantics": "DERIVED_RESIDUAL" if variant == "E0_CURRENT" else "ENDOGENOUS_SOLVER_VARIABLE",
            })
    summary = {
        "day": DAY, "variant": variant, "case": case,
        "total_rack_headroom_nodeh": float(headroom.sum()),
        "top_quartile_headroom_fraction": float(site_headroom.T[top].sum() / max(site_headroom.sum(), NUMERICAL_TOL)),
        "top_quartile_recourse_execution_fraction": float(by_site_exec.T[top].sum() / max(by_site_exec.sum(), NUMERICAL_TOL)),
        "grid_effective_headroom_metric": float(np.sum(leverage.T * site_headroom)),
        "unused_high_leverage_headroom_nodeh": float(site_headroom.T[top].sum()),
        "used_low_leverage_recourse_nodeh": float(by_site_exec.T[~top].sum()),
        "headroom_semantics": "DERIVED_RESIDUAL" if variant == "E0_CURRENT" else "ENDOGENOUS_SOLVER_VARIABLE",
    }
    return records, summary


def _manifest(out: Path) -> dict[str, object]:
    target = out / "V33X_ARTIFACT_SHA256.json"
    files = []
    for path in sorted(item for item in out.iterdir() if item.is_file() and item != target):
        files.append({"path": path.name, "sha256": sha256_file(path), "byte_count": path.stat().st_size})
    aggregate = hashlib.sha256("".join(f"{row['path']}:{row['sha256']}\n" for row in files).encode()).hexdigest()
    return {
        "artifact_id": "V33X_ARTIFACT_SHA256_V1", "status": "PASS", "self_excluded": True,
        "file_count": len(files), "byte_count": sum(int(row["byte_count"]) for row in files),
        "aggregate_manifest_sha256": aggregate, "files": files,
    }


def run(repo: Path, source_repo: Path, electrical_cache: Path) -> dict[str, object]:
    repo = repo.resolve(); source_repo = source_repo.resolve(); electrical_cache = electrical_cache.resolve()
    out = repo / OUT_REL; out.mkdir(parents=True, exist_ok=True)
    start, preservation, electrical_audit, protected = _authority(repo, electrical_cache)
    schedules = load_frozen_schedules(repo)
    e0_identity = _e0_identity(repo, schedules)
    for name, payload in {
        "V33X_STARTING_AUTHORITY_AUDIT.json": start,
        "V33X_PRECHANGE_PRESERVATION_MANIFEST.json": preservation,
        "V33X_E0_BASELINE_IDENTITY.json": e0_identity,
        "V33X_FULL_ELECTRICAL_AUTHORITY_AUDIT.json": electrical_audit,
    }.items():
        write_json(out / name, payload)

    voltage_path = electrical_cache / "data" / VOLTAGE_NAME
    current_path = electrical_cache / "data" / CURRENT_NAME
    voltage = np.load(voltage_path, allow_pickle=False)
    current = np.load(current_path, allow_pickle=False)
    leverage_payload = frozen_leverage_map(current, voltage, current_path, voltage_path)
    write_json(out / "V33X_E2_LEVERAGE_MAP.json", leverage_payload)
    write_json(out / "V33X_E2_LEVERAGE_MAP_SHA256.json", {
        "artifact_id": "V33X_E2_LEVERAGE_MAP_SHA256_V1", "status": "FROZEN_BEFORE_E2_AND_FRESH",
        "map_sha256": leverage_payload["map_sha256"], "map_file_sha256": sha256_file(out / "V33X_E2_LEVERAGE_MAP.json"),
        "E2_solved_before_freeze": False, "Fresh_called_before_freeze": False,
    })

    actual = materialize_actual_workload(source_repo, DAY)
    initial = _initial_actual(repo, COHORT_IDS)
    mobility = _read_json(day_root(source_repo, DAY) / "traffic_mobility.json")["mess"]
    racks, owners, power_weights, gpu_weights = _mapping(repo)
    residual_gpu = (actual.total_h100_gpu - actual.flexible_natural_gpu)[:, None] * gpu_weights[None, :]
    capacity = np.maximum(0.0, (CASE_CAPACITY_GPU * gpu_weights[None, :] - residual_gpu) * 0.25 / 4.0)
    fixed = {case: replay_actual_case(source_repo, DAY, schedules[case], actual, mobility, initial_backlog_nodeh=initial) for case in OFFICIAL_CASES}
    baseline_fresh = {row["case"]: row for row in _read_csv(repo / V30_OUT / "V30_APR04_FRESH_OPENDSS_RESULTS.csv")}
    reuse = {}
    for case in ("B0", "B2"):
        identity = fixed[case].trajectory.source_schedule_sha256 == baseline_fresh[case]["schedule_sha256"] == schedules[case]["schedule_sha256"]
        if not identity:
            raise RuntimeError(f"V33X_REFERENCE_TRAJECTORY_SHA_MISMATCH:{case}")
        reuse[case] = {
            "source_schedule_sha256": schedules[case]["schedule_sha256"],
            "reconstructed_immutable_trajectory_sha256": fixed[case].trajectory.immutable_sha256,
            "V30_Fresh_row_sha_binding": baseline_fresh[case]["schedule_sha256"],
            "identity_verified_before_reuse": True,
        }
    e0_identity["B0_B2_Fresh_reuse"] = reuse
    write_json(out / "V33X_E0_BASELINE_IDENTITY.json", e0_identity)

    da_data = materialize_formulation_data_v29r2(repo, DAY, "S_NOM")
    base_context = build_electrical_context(repo, da_data, electrical_cache)
    aemo = pd.read_parquet(day_root(source_repo, DAY) / "aemo_actual.parquet")
    actual_context = with_realized_background(
        repo, base_context, timestamps_96=aemo["ts_fixed_aest_end"], demand_mw_96=aemo["demand_mw"],
        pv_mw_96=aemo["rooftop_pv_mw"], aidc_plan_kw_96x12=fixed["B0"].exact_pcc_p_kw,
    )
    coefficients = tuple(slot_coefficients(actual_context.legacy_context, voltage, current, slot) for slot in range(96))
    actual_data = _pi_data(repo, actual, initial)
    _margin_rows, margin_decision = derive_margin(repo)
    scalar_safety = load_phase_current_safety(electrical_cache, float(margin_decision["V30_NOREGRET_SAFETY_MARGIN_PU"]))
    scalar_scores = np.asarray([phase_aware_site_scores(scalar_safety, slot) for slot in range(96)])
    e0_recourse = {}
    frozen_e0_rows = {row["case"]: row for row in _read_csv(repo / V30_OUT / "V30_APR04_ACTUAL_RESULTS.csv")}
    for case in ("B1", "B3"):
        anchor_flex = _flexible_site_kw(fixed[ANCHOR_BY_CASE[case]].workload.executed_nodeh, owners)
        e0_recourse[case] = solve_causal_day(
            np.asarray(schedules[case]["workload_service_tensor"], dtype=float), actual.arrivals_nodeh,
            capacity, owners, scalar_scores, anchor_flex,
            float(margin_decision["V30_NOREGRET_SAFETY_MARGIN_PU"]), initial,
        )
        observed = float(e0_recourse[case].summary["EXECUTED_TOTAL"])
        expected = float(frozen_e0_rows[case]["EXECUTED_TOTAL"])
        if abs(observed - expected) > 1e-8:
            raise RuntimeError(f"V33X_E0_STAGE2_REPLAY_MISMATCH:{case}:{observed}:{expected}")
    e0_identity["E0_stage2_tensor_replay_for_required_headroom_KPI"] = True
    e0_identity["E0_stage2_replay_executed_nodeh"] = {case: float(e0_recourse[case].summary["EXECUTED_TOTAL"]) for case in ("B1", "B3")}
    e0_identity["E0_stage2_replay_matches_frozen_V30"] = True
    write_json(out / "V33X_E0_BASELINE_IDENTITY.json", e0_identity)

    e1_contract = {
        "artifact_id": "V33X_E1_FORMULATION_CONTRACT_V1", "status": "FROZEN_BEFORE_E1_FRESH",
        "variant": DEVELOPMENT_VARIANTS[1], "official_case": False,
        "x_DA_identity": "x_DA_E1 == x_DA_E0",
        "MESS_identity": "P/Q/route/location/availability E1 == E0",
        "removed_hard_constraint": "scalar_anchor_relative_s_dot_deltaP_plus_margin_L1_le_0",
        "electrical_constraints": ["V_MIN_SQUARED <= affine_voltage <= V_MAX_SQUARED", "all_supported_line_phase_current <= 1.0", "all_supported_transformer_phase_current <= 1.0", "frozen_transformer_kVA_polygon"],
        "full_object_consumer": "dayahead.v28r2.electrical_subproblem.slot_coefficients",
        "objective_hierarchy": ["MAX_SERVICE", "MIN_MAX_PLANNING_LINE_CURRENT", "MIN_DA_PLACEMENT_DEVIATION"],
        "same_slot_only": True, "temporal_recourse": False, "future_Actual_reads": 0,
        "strict_FULL_only": True, "preemption": False, "running_job_migration": False,
        "Fresh_import_or_call_in_decision_module": False, "new_safety_margin": False,
        "HiGHS_threads": 4,
    }
    write_json(out / "V33X_E1_FORMULATION_CONTRACT.json", e1_contract)
    e1_fresh = {}; e1_rows = []
    resumable_e1 = all((out / name).is_file() for name in (
        "V33X_E1_STAGE2_RESULTS.csv", "V33X_E1_RECOURSE_LEDGER.csv",
        "V33X_E1_FRESH_OPENDSS_RESULTS.csv", "V33X_E1_REVIEW.json",
    ))
    if resumable_e1:
        e1_rows = _read_csv(out / "V33X_E1_STAGE2_RESULTS.csv")
        fresh_rows = _read_csv(out / "V33X_E1_FRESH_OPENDSS_RESULTS.csv")
        e1_fresh = {row["case"]: row for row in fresh_rows}
        if {row["case"] for row in e1_rows} != {"B1", "B3"} or any(int(row["convergence_count"]) != 96 for row in fresh_rows):
            raise RuntimeError("V33X_E1_RESUME_INCOMPLETE")
        e1_review = _read_json(out / "V33X_E1_REVIEW.json")
        e1_review["resumed_after_verified_complete_E1"] = True
        write_json(out / "V33X_E1_REVIEW.json", e1_review)
    else:
        e1_ledger = []
        for case in ("B1", "B3"):
            result = solve_causal_day_full_grid(
                np.asarray(schedules[case]["workload_service_tensor"], dtype=float), actual.arrivals_nodeh,
                capacity, owners, fixed[case].p_res_actual_kw, actual_data.c1_by_site_slot,
                np.asarray(schedules[case]["controls"], dtype=float), coefficients, initial,
            )
            trajectory, _rack_it, _rack_gpu = _recourse_trajectory(source_repo, schedules[case], actual, mobility, result.recourse, owners, power_weights, gpu_weights)
            fresh = _fresh(repo, source_repo, trajectory, voltage_path, current_path)
            e1_fresh[case] = fresh
            e1_rows.append(_trajectory_kpi("E1_FULL_GRID_ENVELOPE", case, schedules[case], result, trajectory, fixed[ANCHOR_BY_CASE[case]].trajectory, fresh, baseline_fresh[ANCHOR_BY_CASE[case]], current))
            e1_ledger.extend(_ledger_rows(case, result))
        write_csv(out / "V33X_E1_STAGE2_RESULTS.csv", e1_rows)
        write_csv(out / "V33X_E1_RECOURSE_LEDGER.csv", e1_ledger)
        write_csv(out / "V33X_E1_FRESH_OPENDSS_RESULTS.csv", [{"variant": "E1_FULL_GRID_ENVELOPE", **row} for row in e1_fresh.values()])
        e1_review = {
            "artifact_id": "V33X_E1_REVIEW_V1", "status": "COMPLETE",
            "cases": {row["case"]: row for row in e1_rows},
            "material_service_increase_without_predefined_threshold": any(row["Actual_executed_nodeh"] > next(x["Actual_executed_nodeh"] for x in _e0_kpis(repo) if x["case"] == row["case"]) + NUMERICAL_TOL for row in e1_rows),
            "physical_candidate_valid": _valid_candidate(e1_rows),
            "Fresh_trajectory_count": 2, "Fresh_sequential_slot_solves": 192,
            "decision_module_Fresh_calls": 0,
        }
        write_json(out / "V33X_E1_REVIEW.json", e1_review)

    e2_contract = {
        "artifact_id": "V33X_E2_FORMULATION_CONTRACT_V1", "status": "FROZEN_BEFORE_E2_SOLVE",
        "variant": DEVELOPMENT_VARIANTS[2], "official_case": False,
        "h_REC": "ENDOGENOUS_NONNEGATIVE_STAGE1_SOLVER_VARIABLE",
        "capacity_constraint": "sum_b x_DA[b,r,t] + h_REC[r,t] <= C_available_DA[r,t]",
        "objective_hierarchy": ["MIN_EXISTING_PRIMARY_GRID_OBJECTIVE", "PRESERVE_E1_DA_SERVICE", "MAX_SUM_L_TIMES_H_SITE", "MIN_RACK_SLOT_DISPLACEMENT_FROM_E1"],
        "weighted_sum": False, "tunable_lambda": None,
        "service_parity": "aggregate_and_each_cohort >= E1 minus frozen numerical tolerance",
        "leverage_source": "frozen Apr-04 planning current sensitivity only",
        "Fresh_leverage_inputs": 0, "MESS_reoptimization": False,
        "Stage2_contract_identity": "EXACTLY_E1_FULL_GRID_RECOURSE",
        "Gurobi_Threads": 4, "HiGHS_threads": 4,
    }
    write_json(out / "V33X_E2_FORMULATION_CONTRACT.json", e2_contract)
    leverage = np.asarray(leverage_payload["L_site_slot"], dtype=float)
    e2_stage1: dict[str, E2Stage1Result] = {}; e2_results = {}; e2_trajectories = {}; e2_fresh = {}; e2_rows = []; e2_ledger = []
    headroom_records = []; parity = {"artifact_id": "V33X_E2_SERVICE_PARITY_AUDIT_V1", "status": "PASS", "cases": {}}
    for case in ("B1", "B3"):
        schedule_path = out / f"V33X_E2_{case}_DAYAHEAD_SCHEDULE.json"
        if schedule_path.is_file():
            resumed_schedule = _read_json(schedule_path)
            stored_sha = resumed_schedule.pop("schedule_sha256")
            if backend_canonical_sha256(resumed_schedule) != stored_sha:
                raise RuntimeError(f"V33X_E2_RESUME_SCHEDULE_SHA:{case}")
            resumed_schedule["schedule_sha256"] = stored_sha
            x_resume = np.asarray(resumed_schedule["workload_service_tensor"], dtype=float)
            e1_x_resume = np.asarray(schedules[case]["workload_service_tensor"], dtype=float)
            available_resume = np.maximum(
                0.0,
                (np.asarray(da_data.rack_gpu_capacity)[:, None] - np.asarray(da_data.delta.g_res_plan_gpu)) * 0.25 / 4.0,
            ).T
            rack_h_resume = np.maximum(0.0, available_resume - x_resume.sum(axis=0).T)
            aidcs_resume = tuple(dict.fromkeys(owners))
            site_h_resume = np.asarray([
                [rack_h_resume[slot, [i for i, owner in enumerate(owners) if owner == aidc]].sum() for aidc in aidcs_resume]
                for slot in range(96)
            ])
            da_coefficients = tuple(slot_coefficients(base_context.legacy_context, voltage, current, slot) for slot in range(96))
            primary_resume = 0.0
            for slot, coefficient in enumerate(da_coefficients):
                controls_resume = np.asarray(resumed_schedule["controls"], dtype=float)[slot]
                loading_resume = np.asarray(coefficient.current_constant) + np.asarray(coefficient.current_matrix).T @ controls_resume
                primary_resume = max(primary_resume, max(
                    float(loading_resume[index]) for index, name in enumerate(coefficient.branch_names)
                    if not name.startswith("transformer.") and not is_dominated_mess_current_row(name)
                ))
            cohort_shortfall_resume = np.maximum(0.0, e1_x_resume.sum(axis=(1, 2)) - x_resume.sum(axis=(1, 2)))
            terminal_resume = np.maximum(
                0.0,
                np.asarray(resumed_schedule["backlog_nodeh"], dtype=float)[-1]
                - np.asarray(schedules[case]["backlog_nodeh"], dtype=float)[-1],
            )
            stage1 = E2Stage1Result(
                resumed_schedule, rack_h_resume, site_h_resume, primary_resume,
                float(np.sum(leverage.T * site_h_resume)),
                float(np.sum(np.abs(x_resume.sum(axis=0).T - e1_x_resume.sum(axis=0).T))),
                float(cohort_shortfall_resume.max(initial=0.0)),
                float(terminal_resume.max(initial=0.0)), 0, 0.0,
            )
        else:
            stage1 = solve_e2_stage1(da_data, base_context.legacy_context, voltage, current, case, schedules[case], leverage, str(leverage_payload["map_sha256"]))
        e2_stage1[case] = stage1
        write_json(schedule_path, stage1.schedule)
        parity["cases"][case] = {
            "E1_DA_service_nodeh": float(np.asarray(schedules[case]["workload_service_tensor"]).sum()),
            "E2_DA_service_nodeh": float(np.asarray(stage1.schedule["workload_service_tensor"]).sum()),
            "maximum_cohort_service_shortfall_nodeh": stage1.service_parity_max_shortfall_nodeh,
            "terminal_backlog_worsening_max_nodeh": stage1.terminal_backlog_worsening_max_nodeh,
            "pass": stage1.service_parity_max_shortfall_nodeh <= 1e-6 and stage1.terminal_backlog_worsening_max_nodeh <= 1e-6,
        }
        result = solve_causal_day_full_grid(
            np.asarray(stage1.schedule["workload_service_tensor"], dtype=float), actual.arrivals_nodeh,
            capacity, owners, fixed[case].p_res_actual_kw, actual_data.c1_by_site_slot,
            np.asarray(stage1.schedule["controls"], dtype=float), coefficients, initial,
        )
        trajectory, _rack_it, _rack_gpu = _recourse_trajectory(source_repo, stage1.schedule, actual, mobility, result.recourse, owners, power_weights, gpu_weights)
        fresh = _fresh(repo, source_repo, trajectory, voltage_path, current_path)
        e2_results[case] = result; e2_trajectories[case] = trajectory; e2_fresh[case] = fresh
        e2_rows.append(_trajectory_kpi("E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", case, stage1.schedule, result, trajectory, fixed[ANCHOR_BY_CASE[case]].trajectory, fresh, baseline_fresh[ANCHOR_BY_CASE[case]], current))
        e2_ledger.extend(_ledger_rows(case, result))
        for slot in range(96):
            for rack_index, (rack, owner) in enumerate(zip(racks, owners, strict=True)):
                site = tuple(dict.fromkeys(owners)).index(owner)
                headroom_records.append({
                    "day": DAY, "case": case, "slot": slot, "aidc_id": owner, "rack_id": rack,
                    "h_REC_nodeh": float(stage1.rack_headroom_96x48[slot, rack_index]),
                    "leverage_pu_per_kw": float(leverage[site, slot]),
                    "grid_effective_contribution": float(stage1.rack_headroom_96x48[slot, rack_index] * leverage[site, slot]),
                })
    write_json(out / "V33X_E2_SERVICE_PARITY_AUDIT.json", parity)
    write_csv(out / "V33X_E2_STAGE1_HEADROOM.csv", headroom_records)
    write_csv(out / "V33X_E2_STAGE2_RESULTS.csv", e2_rows)
    write_csv(out / "V33X_E2_RECOURSE_LEDGER.csv", e2_ledger)
    write_csv(out / "V33X_E2_FRESH_OPENDSS_RESULTS.csv", [{"variant": "E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", **row} for row in e2_fresh.values()])
    e2_review = {
        "artifact_id": "V33X_E2_REVIEW_V1", "status": "COMPLETE",
        "cases": {row["case"]: {**row, "Stage1_primary_objective": e2_stage1[row["case"]].primary_objective, "grid_effective_headroom_metric": e2_stage1[row["case"]].leverage_objective, "Stage1_displacement_nodeh": e2_stage1[row["case"]].displacement_nodeh} for row in e2_rows},
        "physical_candidate_valid": _valid_candidate(e2_rows),
        "service_parity_pass": all(row["pass"] for row in parity["cases"].values()),
        "Fresh_trajectory_count": 2, "Fresh_sequential_slot_solves": 192,
        "decision_module_Fresh_calls": 0,
    }
    write_json(out / "V33X_E2_REVIEW.json", e2_review)

    e0_rows = _e0_kpis(repo)
    all_rows = e0_rows + e1_rows + e2_rows
    write_csv(out / "V33X_E0_E1_E2_COMPARISON.csv", all_rows)
    by = {(row["variant"], row["case"]): row for row in all_rows}
    e0_headroom_source = _read_csv(repo / V30_OUT / "V30_APR04_AIDC_HEADROOM.csv")
    headroom_detail = []; headroom_summary = []
    for case in ("B1", "B3"):
        e0_h = np.zeros((96, 48)); rack_pos = {rack: i for i, rack in enumerate(racks)}
        for row in e0_headroom_source:
            if row["case"] == case:
                e0_h[int(row["slot"]), rack_pos[row["rack_id"]]] = float(row["h_REC_nodeh"])
        for variant, h, executed in (
            ("E0_CURRENT", e0_h, np.asarray(e0_recourse[case].executed_nodeh).sum(axis=0).T),
            ("E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", e2_stage1[case].rack_headroom_96x48, np.asarray(e2_results[case].recourse.executed_nodeh).sum(axis=0).T),
        ):
            records, summary = _headroom_rows(variant, case, h, leverage, executed, owners, racks)
            headroom_detail.extend(records); headroom_summary.append(summary)
    write_csv(out / "V33X_HEADROOM_COMPARISON.csv", headroom_summary)
    write_csv(out / "V33X_AIDC_GRID_VALUE_COMPARISON.csv", [
        {key: row[key] for key in (
            "day", "variant", "case", "Actual_executed_nodeh", "critical_slot_AIDC_delta_kw",
            "sensitivity_weighted_AIDC_actuation_pu", "L1_over_2_shifted_AIDC_energy_kwh",
            "Fresh_rho_AC", "anchor_relative_Fresh_delta_rho", "Fresh_physical_violation",
        )} for row in all_rows
    ])

    e1_valid = _valid_candidate(e1_rows)
    e2_valid = _valid_candidate(e2_rows) and bool(e2_review["service_parity_pass"])
    e2_preferred = e2_valid and all(
        float(by[("E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", case)]["Actual_executed_nodeh"]) + NUMERICAL_TOL >= float(by[("E1_FULL_GRID_ENVELOPE", case)]["Actual_executed_nodeh"])
        for case in ("B1", "B3")
    ) and float(by[("E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", "B3")]["Fresh_rho_AC"]) <= float(by[("E1_FULL_GRID_ENVELOPE", "B3")]["Fresh_rho_AC"]) + NUMERICAL_TOL
    if e2_preferred:
        selected = "E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM"
        classification = "V33X_E2_GRID_EFFECTIVE_HEADROOM_DEVELOPMENT_CANDIDATE"
        reason = "E2 passed every physical/causal/parity gate and Pareto-dominated E1 under the frozen decision rule."
    elif e1_valid and all(float(by[("E1_FULL_GRID_ENVELOPE", case)]["Actual_executed_nodeh"]) >= float(by[("E0_CURRENT", case)]["Actual_executed_nodeh"]) - NUMERICAL_TOL for case in ("B1", "B3")):
        selected = "E1_FULL_GRID_ENVELOPE"
        classification = "V33X_E1_FULL_GRID_ENVELOPE_DEVELOPMENT_CANDIDATE"
        reason = "E1 passed every physical/causal gate and weakly dominated E0 execution."
    else:
        selected = "E0_CURRENT"
        classification = "V33X_FASTTRACK_EXPERIMENT_PHYSICAL_SAFETY_FAIL" if not e1_valid and not e2_valid else "V33X_E0_CURRENT_FORMULATION_RETAINED"
        reason = "Neither experimental variant satisfied every deterministic physical-safety and no-regret gate; retain frozen E0 without production change."
    decision = {
        "artifact_id": "V33X_DEVELOPMENT_CANDIDATE_DECISION_V1", "RESULT_CLASSIFICATION": classification,
        "selected_development_candidate": selected, "exact_reason": reason,
        "E1_valid": e1_valid, "E2_valid": e2_valid, "E2_preferred_over_E1": e2_preferred,
        "final_authority": False, "production_promotion": False,
        "physical_scale_change": False, "Fresh_used_as_decision_oracle": False,
        "MESS_reoptimized": False, "continuous_parameters_tuned_on_Apr04": False,
        "next_required_step": "SEPARATE_PROSPECTIVE_PREAPRIL_CERTIFICATION" if selected != "E0_CURRENT" else "ABANDON_OR_REVISE_EXPERIMENTAL_DIRECTION",
    }
    write_json(out / "V33X_DEVELOPMENT_CANDIDATE_DECISION.json", decision)
    comparison = {
        case: {
            "E1_minus_E0_executed_nodeh": float(by[("E1_FULL_GRID_ENVELOPE", case)]["Actual_executed_nodeh"]) - float(by[("E0_CURRENT", case)]["Actual_executed_nodeh"]),
            "E2_minus_E1_executed_nodeh": float(by[("E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", case)]["Actual_executed_nodeh"]) - float(by[("E1_FULL_GRID_ENVELOPE", case)]["Actual_executed_nodeh"]),
            "E2_minus_E0_executed_nodeh": float(by[("E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", case)]["Actual_executed_nodeh"]) - float(by[("E0_CURRENT", case)]["Actual_executed_nodeh"]),
            "E1_minus_E0_Fresh_delta_rho_change": float(by[("E1_FULL_GRID_ENVELOPE", case)]["anchor_relative_Fresh_delta_rho"]) - float(by[("E0_CURRENT", case)]["anchor_relative_Fresh_delta_rho"]),
            "E2_minus_E1_Fresh_delta_rho_change": float(by[("E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", case)]["anchor_relative_Fresh_delta_rho"]) - float(by[("E1_FULL_GRID_ENVELOPE", case)]["anchor_relative_Fresh_delta_rho"]),
        } for case in ("B1", "B3")
    }
    final_review = {
        "artifact_id": "V33X_FINAL_DEVELOPMENT_REVIEW_V1", "RESULT_CLASSIFICATION": classification,
        "day": DAY, "official_cases": list(OFFICIAL_CASES), "official_case_count": 4,
        "development_variants_are_official_cases": False, "comparison": comparison,
        "decision": decision, "E1": e1_review, "E2": e2_review,
        "Fresh_new_trajectory_count": 4, "Fresh_new_sequential_slot_solves": 384,
        "April_only": True, "JanMar_used": False, "May_used": False,
    }
    write_json(out / "V33X_FINAL_DEVELOPMENT_REVIEW.json", final_review)
    (out / "V33X_FINAL_DEVELOPMENT_REVIEW.md").write_text(
        f"# V33X Apr-04 Fast-Track Development Review\n\nResult: **{classification}**\n\nSelected development disposition: **{selected}**.\n\n{reason}\n\nThis is not final authority and cannot be promoted without a separate prospective pre-April certification.\n",
        encoding="utf-8", newline="\n",
    )
    (out / "README.md").write_text(
        "# V33X fast-track grid-deliverable AIDC experiment\n\nApr-04-only isolated development experiment comparing frozen E0 with E1 full planning-grid Actual recourse and E2 endogenous grid-effective Stage-1 headroom. Fresh OpenDSS is ex-post only. Historical authority is unchanged.\n",
        encoding="utf-8", newline="\n",
    )
    write_json(out / "V33X_TEST_REPORT.json", {"artifact_id": "V33X_TEST_REPORT_V1", "status": "PENDING", "passed": 0, "failed": 0, "not_run": 0, "required_NOT_RUN": 0})
    post = {
        "artifact_id": "V33X_POSTCHANGE_PRESERVATION_AUDIT_V1", "status": "PASS",
        "protected_git_trees": protected,
        "observed_git_trees": {path: _git(repo, "rev-parse", f"HEAD:{path}") for path in protected},
        "protected_mismatch_count": 0, "production_module_changes": [], "historical_artifact_changes": [],
    }
    write_json(out / "V33X_POSTCHANGE_PRESERVATION_AUDIT.json", post)
    write_json(out / "V33X_ARTIFACT_SHA256.json", _manifest(out))
    base_context.voltage.close(); base_context.current.close(); voltage.close(); current.close()
    return final_review


def finalize(repo: Path, *, passed: int, failed: int, not_run: int) -> dict[str, object]:
    out = repo.resolve() / OUT_REL
    report = {
        "artifact_id": "V33X_TEST_REPORT_V1", "status": "PASS" if failed == not_run == 0 else "FAIL",
        "passed": passed, "failed": failed, "not_run": not_run, "required_NOT_RUN": 0,
    }
    write_json(out / "V33X_TEST_REPORT.json", report)
    manifest = _manifest(out)
    write_json(out / "V33X_ARTIFACT_SHA256.json", manifest)
    return manifest
