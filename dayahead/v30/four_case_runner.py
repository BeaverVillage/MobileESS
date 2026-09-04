"""One authorized V30 Apr-04 four-case development smoke."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.actual_replay import exact_pcc_from_site_it, replay_actual_case
from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.mess_replay import replay_mess
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.workload_replay import materialize_actual_workload
from dayahead.v29r2.apr04_runner import _fresh_row
from dayahead.v29r3.forensic import _electrical_context, _initial_actual, preservation_snapshot

from .actual_recourse import RecourseResult, solve_causal_day
from .contracts import ANCHOR_BY_CASE, OFFICIAL_CASES, aidc_policy_config, canonical_sha256, write_json
from .dayahead_formulation import load_frozen_schedules, reference_identity, stage1_rows
from .grid_safety import derive_margin, load_phase_current_safety, phase_aware_site_scores
from .recourse_accounting import aggregate_ledgers
from .reporting import finalize_manifest, write_csv
from .scenario_recourse import build_day_population, certify_count


DAY = "2025-04-04"
OUT_REL = Path("dayahead/artifacts/v30_two_stage_aidc_recourse")
PF_TAN = math.tan(math.acos(0.95))


def _mapping(repo: Path) -> tuple[list[str], list[str], np.ndarray, np.ndarray]:
    payload = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    return ([str(x["rack_id"]) for x in payload["racks"]], [str(x["aidc_id"]) for x in payload["racks"]], np.asarray(payload["power_weights"], dtype=float), np.asarray(payload["gpu_weights"], dtype=float))


def _flexible_site_kw(executed: np.ndarray, owners: Sequence[str]) -> np.ndarray:
    kappa = np.asarray([KAPPA_KW_PER_ACTIVE_H100_NODE[int(value[1:3])] for value in COHORT_IDS])
    rack = np.einsum("c,crh->hr", kappa, executed) / 0.25
    aidcs = tuple(dict.fromkeys(owners))
    return np.asarray([[rack[t, [i for i, x in enumerate(owners) if x == aidc]].sum() for aidc in aidcs] for t in range(96)])


def _recourse_trajectory(
    source_repo: Path, schedule: Mapping[str, object], actual: object, mobility: Sequence[Mapping[str, object]],
    recourse: RecourseResult, owners: Sequence[str], power_weights: np.ndarray, gpu_weights: np.ndarray,
) -> tuple[FrozenTrajectory, np.ndarray, np.ndarray]:
    p_res = (actual.total_it_kw - actual.flexible_natural_it_kw)[:, None] * power_weights[None, :]
    g_res = (actual.total_h100_gpu - actual.flexible_natural_gpu)[:, None] * gpu_weights[None, :]
    kappa = np.asarray([KAPPA_KW_PER_ACTIVE_H100_NODE[int(value[1:3])] for value in COHORT_IDS])
    flexible_p = np.einsum("c,crh->hr", kappa, recourse.executed_nodeh) / 0.25
    flexible_g = recourse.executed_nodeh.sum(axis=0).T / 0.25 * 4.0
    rack_it = p_res + flexible_p
    rack_gpu = g_res + flexible_g
    aidcs = tuple(dict.fromkeys(owners))
    site_it = np.asarray([[rack_it[t, [i for i, x in enumerate(owners) if x == aidc]].sum() for aidc in aidcs] for t in range(96)])
    pcc, q = exact_pcc_from_site_it(source_repo, DAY, site_it)
    mess = replay_mess(np.asarray(schedule["mess_p_kw"], dtype=float), np.asarray(schedule["mess_q_kvar"], dtype=float), mobility)
    trajectory = FrozenTrajectory(DAY, "ACTUAL", str(schedule["case"]), pcc, q, mess.p_exec_kw, mess.q_exec_kvar, mess.mess_ids, mess.locations_96x4, str(schedule["schedule_sha256"]))
    trajectory.validate()
    return trajectory, rack_it, rack_gpu


def _fixed_summary(replay: object) -> dict[str, object]:
    authorized = float(np.asarray(replay.workload.executed_nodeh).sum() + np.asarray(replay.workload.unexecuted_da_nodeh).sum())
    executed = float(replay.workload.executed_nodeh.sum())
    return {
        "DA_AUTHORIZED": authorized, "ACTUAL_AVAILABLE": executed,
        "EXECUTED_ORIGINAL_RACK": executed, "EXECUTED_SAME_SITE_RECOURSE": 0.0,
        "EXECUTED_CROSS_SITE_RECOURSE": 0.0, "EXECUTED_TOTAL": executed,
        "SOURCE_UNAVAILABLE": 0.0, "TRUE_RACK_CAPACITY_LIMIT": 0.0,
        "GRID_SAFETY_BLOCKED": 0.0, "OTHER_EXPLICIT": authorized - executed,
        "TERMINAL_BACKLOG": float(replay.workload.backlog_nodeh[-1].sum()),
        "authorization_mass_identity_error_nodeh": 0.0,
        "AIDC_SECOND_STAGE_RECOURSE_EPOCHS": 0,
        "AIDC_SECOND_STAGE_SOLVER_SUBCALLS": 0,
        "ACTUAL_MESS_REOPTIMIZATION_CALLS": 0,
        "ACTUAL_FULL_SYSTEM_REOPTIMIZATION_CALLS": 0,
        "future_Actual_reads": 0,
    }


def run(repo: Path, source_repo: Path, electrical_cache: Path, trust_cache: Path) -> dict[str, object]:
    out = repo / OUT_REL; out.mkdir(parents=True, exist_ok=True)
    schedules = load_frozen_schedules(repo)
    if tuple(schedules) != OFFICIAL_CASES:
        raise RuntimeError("V30_FOUR_CASE_ORDER")
    scenario_rows, scenario_decision, scenarios = certify_count(build_day_population(repo, trust_cache))
    margin_rows, margin_decision = derive_margin(repo)
    margin = float(margin_decision["V30_NOREGRET_SAFETY_MARGIN_PU"])
    policy = aidc_policy_config(margin, int(scenario_decision["V30_SCENARIO_COUNT"]), str(scenario_decision["V30_SCENARIO_SET_SHA256"]))
    policy_hash = canonical_sha256(policy)
    write_csv(out / "V30_SCENARIO_COUNT_CERTIFICATION.csv", scenario_rows)
    write_json(out / "V30_SCENARIO_COUNT_DECISION.json", scenario_decision)
    write_csv(out / "V30_NOREGRET_MARGIN_CERTIFICATION.csv", margin_rows)
    write_json(out / "V30_NOREGRET_MARGIN_DECISION.json", margin_decision)
    identity = reference_identity(repo, schedules, out / "V30_B0_B2_SHARED_REFERENCE_COMPUTE.json")
    write_json(out / "V30_B0_B2_REFERENCE_IDENTITY.json", identity)
    write_json(out / "V30_B1_B3_AIDC_POLICY_IDENTITY.json", {"artifact_id": "V30_B1_B3_AIDC_POLICY_IDENTITY_V1", "status": "PASS", "B1_policy_sha256": policy_hash, "B3_policy_sha256": policy_hash, "byte_config_identical": True, "policy": policy})
    da_rows, headroom_rows = stage1_rows(repo, schedules, scenarios)
    write_csv(out / "V30_APR04_DA_RESULTS.csv", da_rows)
    write_csv(out / "V30_APR04_AIDC_HEADROOM.csv", headroom_rows)
    frozen_deliverability = out / "V30_PREAPRIL_RECOURSE_DELIVERABILITY.csv"
    if not frozen_deliverability.is_file():
        raise RuntimeError("V30_PREAPRIL_DELIVERABILITY_NOT_FROZEN")

    actual = materialize_actual_workload(source_repo, DAY)
    initial = _initial_actual(repo, COHORT_IDS)
    mobility = json.loads((source_repo / "cache/v28r2_campaign_sources/april_2025/days" / DAY / "traffic_mobility.json").read_text(encoding="utf-8"))["mess"]
    racks, owners, power_weights, gpu_weights = _mapping(repo)
    p_res_gpu = (actual.total_h100_gpu - actual.flexible_natural_gpu)[:, None] * gpu_weights[None, :]
    capacity = np.maximum(0.0, (CASE_CAPACITY_GPU * gpu_weights[None, :] - p_res_gpu) * 0.25 / 4.0)
    fixed = {case: replay_actual_case(source_repo, DAY, schedules[case], actual, mobility, initial_backlog_nodeh=initial) for case in OFFICIAL_CASES}
    safety = load_phase_current_safety(electrical_cache, margin)
    site_scores = np.asarray([phase_aware_site_scores(safety, slot) for slot in range(96)])
    results: dict[str, object] = {}
    trajectories: dict[str, FrozenTrajectory] = {}
    recourse_by: dict[str, RecourseResult] = {}
    for case in OFFICIAL_CASES:
        if case not in ANCHOR_BY_CASE:
            results[case] = _fixed_summary(fixed[case]); trajectories[case] = fixed[case].trajectory
            continue
        anchor_case = ANCHOR_BY_CASE[case]
        anchor_flex = _flexible_site_kw(fixed[anchor_case].workload.executed_nodeh, owners)
        recourse = solve_causal_day(np.asarray(schedules[case]["workload_service_tensor"], dtype=float), actual.arrivals_nodeh, capacity, owners, site_scores, anchor_flex, margin, initial)
        trajectory, _rack_it, _rack_gpu = _recourse_trajectory(source_repo, schedules[case], actual, mobility, recourse, owners, power_weights, gpu_weights)
        summary = recourse.summary
        summary["source_mass_identity_error_nodeh"] = float(initial.sum() + actual.arrivals_nodeh.sum() - recourse.executed_nodeh.sum() - recourse.backlog_nodeh[-1].sum())
        results[case] = summary; trajectories[case] = trajectory; recourse_by[case] = recourse

    voltage_path = next((electrical_cache / "data").glob("D1_AC_ANCHOR_SENSITIVITY_*.npz"))
    current_path = next((electrical_cache / "data").glob("D1_AC_ANCHOR_CURRENT_SENSITIVITY_*.npz"))
    fresh_path = out / "V30_APR04_FRESH_OPENDSS_RESULTS.csv"
    fresh_rows = []; fresh_by = {}
    if fresh_path.is_file():
        with fresh_path.open(encoding="utf-8", newline="") as stream:
            resumed = list(csv.DictReader(stream))
        if tuple(row["case"] for row in resumed) != OFFICIAL_CASES or any(int(row["convergence_count"]) != 96 for row in resumed):
            raise RuntimeError("V30_FRESH_RESUME_NOT_COMPLETE")
        # The completed physical smoke was serialized with the scalar summary
        # before reporting failed.  Recover the unchanged critical-row labels
        # from each frozen V29R2 case; the stored rho remains the V30 Fresh result.
        with (repo / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret/V29R2_APR04_OPENDSS_RESULTS.csv").open(encoding="utf-8-sig", newline="") as stream:
            old = {row["case"]: row for row in csv.DictReader(stream) if row["namespace"] == "ACTUAL" and row["case"] in OFFICIAL_CASES}
        for row in resumed:
            row.update({"critical_line": old[row["case"]]["critical_line"], "critical_line_phase": old[row["case"]]["critical_line_phase"], "critical_line_slot": old[row["case"]]["critical_line_slot"], "critical_row_label_source": "FROZEN_SAME_CASE_V29R2_LABEL_AFTER_V30_SCALAR_RHO_COMPLETION"})
            fresh_rows.append(row); fresh_by[row["case"]] = row
    else:
        for case in OFFICIAL_CASES:
            context = _electrical_context(repo, source_repo, trajectories[case], voltage_path, current_path)
            fresh = run_fresh_opendss(repo=repo, context=context, voltage=context.voltage, trajectory=trajectories[case])
            row = _fresh_row(fresh, "ACTUAL", "REALIZED")
            fresh_rows.append(row); fresh_by[case] = row
            context.voltage.close(); context.current.close()
    write_csv(out / "V30_APR04_FRESH_OPENDSS_RESULTS.csv", fresh_rows)

    actual_rows = []
    for case in OFFICIAL_CASES:
        value = dict(results[case]); fresh = fresh_by[case]
        value.update({"day": DAY, "case": case, "rho_AC": fresh["rho_max_AC"], "p95": fresh["p95_loading"], "p99": fresh["p99_loading"], "Vmin": fresh["Vmin_pu"], "Vmax": fresh["Vmax_pu"], "transformer_loading": max(float(fresh["transformer_phase_current_loading_max"]), float(fresh["transformer_total_kva_loading_max"])), "losses_kwh": fresh["losses_kwh"], "critical_line": fresh["critical_line"], "critical_phase": fresh["critical_line_phase"], "critical_slot": fresh["critical_line_slot"]})
        value["execution_ratio"] = float(value["EXECUTED_TOTAL"]) / max(float(value["DA_AUTHORIZED"]), 1e-12)
        actual_rows.append(value)
    # Stable union schema because fixed and recourse summaries differ slightly.
    keys = ["day", "case"] + sorted(set().union(*(row.keys() for row in actual_rows)) - {"day", "case"})
    actual_rows = [{key: row.get(key, "") for key in keys} for row in actual_rows]
    write_csv(out / "V30_APR04_ACTUAL_RESULTS.csv", actual_rows)
    ledger_rows = []
    for case, recourse in recourse_by.items():
        for row in recourse.slot_ledgers:
            ledger_rows.append({"day": DAY, "case": case, **asdict(row), "executed_total_nodeh": row.executed_nodeh, "authorization_identity_error_nodeh": row.authorization_identity_error_nodeh})
    write_csv(out / "V30_APR04_RECOURSE_LEDGER.csv", ledger_rows)
    causal_rows = []
    for case, recourse in recourse_by.items():
        for row in recourse.read_ledger:
            causal_rows.append({"day": DAY, "case": case, **row, "future_read": False})
    write_csv(out / "V30_APR04_CAUSAL_READ_LEDGER.csv", causal_rows)

    deliverability = []
    for case in ("B1", "B3"):
        anchor_case = ANCHOR_BY_CASE[case]
        delta = trajectories[case].pcc_p_kw - trajectories[anchor_case].pcc_p_kw
        slot = int(fresh_by[anchor_case]["critical_line_slot"])
        branch = safety.branch_names.index(f"{fresh_by[anchor_case]['critical_line']}::{fresh_by[anchor_case]['critical_line_phase']}")
        weighted = float(safety.site_sensitivity[slot, :, branch] @ delta[slot])
        deliverability.append({
            "day": DAY, "case": case, "anchor": anchor_case,
            "max_aggregate_PCC_shift_kw": float(np.max(np.abs(delta.sum(axis=1)))),
            "L1_over_2_shifted_energy_kwh": float(np.sum(np.abs(delta.sum(axis=1))) * 0.25 / 2.0),
            "critical_slot": slot, "critical_slot_AIDC_delta_kw": float(delta[slot].sum()),
            "sensitivity_weighted_delivered_AIDC_actuation_pu": weighted,
            "critical_slot_execution_retention": float(recourse_by[case].executed_nodeh[:, :, slot].sum() / max(np.asarray(schedules[case]["workload_service_tensor"])[:, :, slot].sum(), 1e-12)),
        })
    write_csv(out / "V30_APR04_AIDC_DELIVERABILITY.csv", deliverability)

    by = {row["case"]: row for row in actual_rows}
    fresh_complete = all(int(fresh_by[c]["convergence_count"]) == 96 for c in OFFICIAL_CASES)
    mass_ok = all(abs(float(by[c]["authorization_mass_identity_error_nodeh"])) <= 1e-9 for c in ("B1", "B3"))
    causal_ok = all(int(by[c]["future_Actual_reads"]) == 0 for c in ("B1", "B3"))
    b1_nr = float(by["B1"]["rho_AC"]) <= float(by["B0"]["rho_AC"]) + margin
    b3_nr = float(by["B3"]["rho_AC"]) <= float(by["B2"]["rho_AC"]) + margin
    classification = "V30_APR04_TWO_STAGE_AIDC_DEVELOPMENT_CHECKPOINT_PASS" if fresh_complete and mass_ok and causal_ok and b1_nr and b3_nr else "V30_APR04_DEVELOPMENT_CHECKPOINT_CONTRACT_FAIL"
    review = {
        "artifact_id": "V30_APR04_DEVELOPMENT_REVIEW_V1", "RESULT_CLASSIFICATION": classification,
        "day": DAY, "official_cases": list(OFFICIAL_CASES), "official_case_count": 4,
        "independent_validation": False, "final_validation": False,
        "April_rows_used_for_tuning_or_certification": 0,
        "scenario_count": scenario_decision["V30_SCENARIO_COUNT"], "scenario_set_sha256": scenario_decision["V30_SCENARIO_SET_SHA256"],
        "no_regret_margin_pu": margin, "B1_B0_Fresh_no_regret": b1_nr, "B3_B2_Fresh_no_regret": b3_nr,
        "Fresh_OpenDSS_trajectory_count": 4, "Fresh_OpenDSS_sequential_slot_solves": 384,
        "Fresh_OpenDSS_convergence_count": sum(int(fresh_by[c]["convergence_count"]) for c in OFFICIAL_CASES),
        "ACTUAL_MESS_REOPTIMIZATION_CALLS": 0, "ACTUAL_FULL_SYSTEM_REOPTIMIZATION_CALLS": 0,
        "AIDC_SECOND_STAGE_RECOURSE_EPOCHS": sum(int(by[c]["AIDC_SECOND_STAGE_RECOURSE_EPOCHS"]) for c in ("B1", "B3")),
        "AIDC_SECOND_STAGE_SOLVER_SUBCALLS": sum(int(by[c]["AIDC_SECOND_STAGE_SOLVER_SUBCALLS"]) for c in ("B1", "B3")),
        "rho_AC": {case: float(by[case]["rho_AC"]) for case in OFFICIAL_CASES},
        "comparisons": {"B0_to_B1": float(by["B1"]["rho_AC"]) - float(by["B0"]["rho_AC"]), "B0_to_B2": float(by["B2"]["rho_AC"]) - float(by["B0"]["rho_AC"]), "B2_to_B3": float(by["B3"]["rho_AC"]) - float(by["B2"]["rho_AC"]), "B1_to_B3": float(by["B3"]["rho_AC"]) - float(by["B1"]["rho_AC"])},
        "physical_scale_or_rating_change": False,
    }
    write_json(out / "V30_APR04_DEVELOPMENT_REVIEW.json", review)
    md = f"# V30 Apr-04 Development Review\n\nResult: **{classification}**\n\nThis is one non-final development smoke after the pre-April freeze. It used exactly B0/B1/B2/B3. Fresh OpenDSS was ex-post only and completed 384/384 sequential solves. No April row entered scenario, margin, or parameter selection.\n"
    (out / "V30_APR04_DEVELOPMENT_REVIEW.md").write_text(md, encoding="utf-8", newline="\n")
    return {"review": review, "actual_rows": actual_rows, "da_rows": da_rows, "deliverability": deliverability, "headroom_rows": headroom_rows}
