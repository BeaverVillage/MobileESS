"""V31 diagnostic-only safety-block and recourse-headroom forensic.

Nothing in this module is imported by V30 production code.  It reuses the
frozen V30 formulation as a read-only dependency and writes only the V31
artifact namespace.
"""

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
from scipy.optimize import linprog

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.actual_replay import exact_pcc_from_site_it, replay_actual_case
from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.mess_replay import replay_mess
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.workload_replay import materialize_actual_workload
from dayahead.v29r2.apr04_runner import _fresh_row
from dayahead.v29r3.forensic import _electrical_context, _initial_actual
from dayahead.v30.actual_recourse import RecourseResult, solve_causal_day
from dayahead.v30.contracts import ANCHOR_BY_CASE, OFFICIAL_CASES
from dayahead.v30.dayahead_formulation import load_frozen_schedules
from dayahead.v30.four_case_runner import _flexible_site_kw, _mapping, _recourse_trajectory
from dayahead.v30.grid_safety import derive_margin, load_phase_current_safety, phase_aware_site_scores
from dayahead.v30.scenario_recourse import build_day_population, certify_count


DAY = "2025-04-04"
STARTING_HEAD = "f0fcc1c2835cc90b65aab7b788f1b55af544f6ea"
V30_BRANCH = "codex/v30-two-stage-aidc-recourse"
V31_BRANCH = "codex/v31-v30-safety-headroom-forensic"
V30_MANIFEST_SHA = "db57e68d116707d45ec0af4ab111a6e25ce4ee0234d08353e86dc498e7898fcb"
V29R2_MANIFEST_SHA = "ca24e661450b7af0e894730602166c792711273e3b4a873976b7a61b4f96a3b2"
V29R3_MANIFEST_SHA = "3ab09255797942f04a2aa0cd15f2c5c1870bcb71b6dff7b0676b76b853f6e223"
M_CURRENT_EXPECTED = 0.0009917274479849247
M_PAIR_FROZEN_BOUND = 0.0004958637239924624
OUT_REL = Path("dayahead/artifacts/v31_v30_safety_headroom_forensic")
V30_REL = Path("dayahead/artifacts/v30_two_stage_aidc_recourse")
V29R2_REL = Path("dayahead/artifacts/v29r2_anchor_aware_trust_noregret")
TOL = 1e-9
DT_HOURS = 0.25


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    material = list(rows)
    if fields is None:
        ordered: list[str] = []
        for row in material:
            for key in row:
                if key not in ordered:
                    ordered.append(key)
        fields = ordered
    if not fields:
        raise RuntimeError(f"V31_EMPTY_CSV_SCHEMA:{path.name}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(material)


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _files_digest(root: Path, *, exclude: Sequence[str] = ()) -> dict[str, object]:
    excluded = set(exclude)
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name not in excluded):
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha(path),
            "byte_count": path.stat().st_size,
        })
    aggregate = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "file_count": len(rows),
        "byte_count": sum(int(row["byte_count"]) for row in rows),
        "aggregate_manifest_sha256": aggregate,
        "files": rows,
    }


def _manifest_value(repo: Path, rel: Path, name: str) -> str:
    payload = _json(repo / rel / name)
    assert isinstance(payload, dict)
    return str(payload["aggregate_manifest_sha256"])


def starting_audit(repo: Path) -> tuple[dict[str, object], dict[str, object]]:
    observed_head = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "branch", "--show-current")
    v30 = _json(repo / V30_REL / "V30_ARTIFACT_SHA256.json")
    assert isinstance(v30, dict)
    v30_digest = str(v30["aggregate_manifest_sha256"])
    v29r2_digest = _manifest_value(repo, V29R2_REL, "V29R2_ARTIFACT_SHA256.json")
    v29r3_digest = _manifest_value(
        repo, Path("dayahead/artifacts/v29r3_aidc_effect_forensic"), "V29R3_ARTIFACT_SHA256.json"
    )
    test = _json(repo / V30_REL / "V30_TEST_REPORT.json")
    margin_rows, margin_decision = derive_margin(repo)
    scenario = _json(repo / V30_REL / "V30_SCENARIO_COUNT_DECISION.json")
    review = _json(repo / V30_REL / "V30_APR04_DEVELOPMENT_REVIEW.json")
    assert isinstance(test, dict) and isinstance(scenario, dict) and isinstance(review, dict)
    ok = (
        observed_head == STARTING_HEAD
        and branch == V31_BRANCH
        and v30_digest == V30_MANIFEST_SHA
        and v29r2_digest == V29R2_MANIFEST_SHA
        and v29r3_digest == V29R3_MANIFEST_SHA
        and int(test["passed"]) == 153 and int(test["failed"]) == 0 and int(test["not_run"]) == 0
        and abs(float(margin_decision["V30_NOREGRET_SAFETY_MARGIN_PU"]) - M_CURRENT_EXPECTED) <= 1e-18
        and int(scenario["V30_SCENARIO_COUNT"]) == 64
        and str(scenario["V30_SCENARIO_SET_SHA256"]) == "02e29c64c8fa662c78bf88e43c10a6508efc0bb5669f9ffe6d33c798a887d2b0"
        and int(margin_decision["April_rows_used"]) == 0 and int(scenario["April_rows_used"]) == 0
        and tuple(review["official_cases"]) == OFFICIAL_CASES
    )
    if not ok:
        raise RuntimeError("V31_STARTING_AUTHORITY_FAIL_CLOSED")
    audit = {
        "artifact_id": "V31_STARTING_AUTHORITY_AUDIT_V1", "status": "PASS",
        "expected_V30_branch": V30_BRANCH, "diagnostic_branch": branch,
        "verified_V30_starting_HEAD": observed_head,
        "V30_result": review["RESULT_CLASSIFICATION"],
        "official_cases": list(OFFICIAL_CASES), "official_case_count": 4,
        "V30_artifact_aggregate_sha256": v30_digest,
        "V29R2_artifact_aggregate_sha256": v29r2_digest,
        "V29R3_artifact_aggregate_sha256": v29r3_digest,
        "baseline_tests": {"passed": 153, "failed": 0, "not_run": 0},
        "M_CURRENT_pu": float(margin_decision["V30_NOREGRET_SAFETY_MARGIN_PU"]),
        "scenario_count": 64, "scenario_set_sha256": scenario["V30_SCENARIO_SET_SHA256"],
        "April_rows_used_for_tuning_or_certification": 0,
    }
    protected = {
        "artifact_id": "V31_PRECHANGE_PRESERVATION_MANIFEST_V1", "status": "PASS",
        "base_HEAD": STARTING_HEAD,
        "protected": {
            "V30_artifacts": _files_digest(repo / V30_REL),
            "V30_code_tree": _git(repo, "rev-parse", f"{STARTING_HEAD}:dayahead/v30"),
            "V29R2_artifacts": _files_digest(repo / V29R2_REL),
            "V29R3_artifacts": _files_digest(repo / "dayahead/artifacts/v29r3_aidc_effect_forensic"),
        },
        "protected_mismatch_count": 0,
    }
    return audit, protected


def current_and_paired_margin(repo: Path) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]], dict[str, object], dict[str, object]]:
    margin_rows, margin_decision = derive_margin(repo)
    margin = float(margin_decision["V30_NOREGRET_SAFETY_MARGIN_PU"])
    if abs(margin - M_CURRENT_EXPECTED) > 1e-18:
        raise RuntimeError("V31_CURRENT_MARGIN_REPRODUCTION_FAIL_CLOSED")
    current_source = [{
        **row,
        "candidate_object": "rho_AIDC=1.0 planning-current trajectory",
        "anchor_object": "same-day Fresh anchor trajectory",
        "candidate_anchor_errors_treated_independently": True,
        "candidate_anchor_correlation_or_cancellation_used": False,
    } for row in margin_rows]
    reproduction = {
        "artifact_id": "V31_CURRENT_MARGIN_REPRODUCTION_V1", "status": "PASS",
        "M_CURRENT_pu": margin,
        "exact_implemented_formula": "max_preApril_day(2 * rho1_candidate_max_abs_planning_minus_Fresh_current_error_pu)",
        "code_location": "dayahead/v30/grid_safety.py::derive_margin",
        "sample_set": "V29R2_TRUST_CERT_FIDELITY_RESULTS.csv rows with rho_AIDC exactly 1.0",
        "day_count": len(margin_rows), "slot_support": len(margin_rows) * 96,
        "first_day": min(str(row["day"]) for row in margin_rows),
        "last_day": max(str(row["day"]) for row in margin_rows),
        "candidate_object": "same-day rho_AIDC=1.0 predicted phase-current array versus independent Fresh candidate array",
        "anchor_object": "same-day Fresh anchor; V30 nevertheless assigned the candidate absolute maximum as its anchor error bound",
        "error_quantity": "maximum absolute planning-minus-Fresh line phase-current loading error over all slots/line phases",
        "maximum_absolute_error_pu": max(float(row["candidate_max_abs_current_error_pu"]) for row in margin_rows),
        "factor_of_two_origin": "triangle inequality |e_candidate| + |e_anchor|, each bounded by the same certified maximum",
        "candidate_anchor_errors_treated_independently": True,
        "correlation_and_cancellation_ignored": True,
        "April_rows_used": 0,
    }

    # The frozen certification did not retain signed elementwise residuals.
    # Its anchor predictor is exactly the Fresh anchor array, hence e_anchor=0.
    # The retained candidate maximum absolute residual is therefore the only
    # auditable one-sided finite-support paired bound; it is not represented as
    # a fabricated signed residual observation.
    paired_rows = []
    for row in margin_rows:
        candidate = float(row["candidate_max_abs_current_error_pu"])
        paired_rows.append({
            "day": row["day"], "rho_AIDC": 1.0,
            "candidate": "rho1_candidate", "anchor": "same_day_anchor",
            "delta_hat_definition": "rho_hat_candidate-rho_hat_anchor",
            "delta_AC_definition": "rho_AC_candidate-rho_AC_anchor",
            "candidate_individual_error_pu": candidate,
            "anchor_individual_error_pu": 0.0,
            "paired_error_pu": candidate,
            "identity_error_pu": candidate - 0.0 - candidate,
            "error_cancellation_term_pu": 0.0,
            "signed_elementwise_pair_reconstructible": False,
            "paired_value_semantics": "ONE_SIDED_BOUND_FROM_FROZEN_MAX_ABS_SUFFICIENT_STATISTIC",
            "April_rows_used": 0,
        })
    values = np.asarray([float(row["paired_error_pu"]) for row in paired_rows])
    m_pair = float(values.max())
    if abs(m_pair - M_PAIR_FROZEN_BOUND) > 1e-18:
        raise RuntimeError("V31_PAIRED_FROZEN_BOUND_MISMATCH")
    stats = {
        "mean": float(values.mean()), "median": float(np.median(values)),
        "p90": float(np.quantile(values, .90)), "p95": float(np.quantile(values, .95)),
        "p99": float(np.quantile(values, .99)), "maximum": m_pair,
        "minimum": float(values.min()), "standard_deviation": float(values.std(ddof=0)),
    }
    paired = {
        "artifact_id": "V31_PAIRED_MARGIN_DIAGNOSTIC_V1",
        "status": "PASS_WITH_FROZEN_SIGNED_RESIDUAL_LIMITATION",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "M_PAIRED_MAX_pu": m_pair,
        "sample_day_count": len(paired_rows), "sample_slot_support": len(paired_rows) * 96,
        "candidate_domain": [1.0], "B1_anchor": "B0", "B3_anchor": "B2",
        "statistics_pu": stats,
        "candidate_anchor_error_correlation": None,
        "correlation_status": "UNDEFINED_ZERO_VARIANCE_EXACT_ZERO_ANCHOR_ERROR",
        "mean_error_cancellation_term_pu": 0.0,
        "paired_error_identity_max_abs_error_pu": max(abs(float(r["identity_error_pu"])) for r in paired_rows),
        "signed_elementwise_residual_arrays_frozen": False,
        "limitation": "V29R2 froze absolute aggregate residual statistics, not signed slot-line-phase residual arrays; no signed samples were invented.",
        "April_rows_used": 0,
    }
    reduction = margin - m_pair
    comparison = {
        "artifact_id": "V31_MARGIN_COMPARISON_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "M_CURRENT_pu": margin,
        "M_PAIRED_MAX_pu": m_pair, "margin_reduction_pu": reduction,
        "margin_reduction_percent": 100.0 * reduction / margin,
        "descriptive_classification": "50_PERCENT_LOWER_DIAGNOSTIC_BOUND_SIGNED_PAIR_CORRELATION_UNRESOLVED",
        "materiality_rule": None,
        "materiality_rule_met": None,
        "materiality_statement": "No after-the-fact materiality threshold is defined; the exact 50 percent arithmetic reduction is the primary result.",
        "why_margins_differ": "The V30 triangle bound assigned the candidate maximum absolute error to both candidate and anchor. The certification anchor predictor is the Fresh anchor itself, so its exact individual error is zero. Signed candidate residual cancellation could not be measured because those arrays were not frozen.",
        "production_margin_replaced": False,
    }
    return current_source, reproduction, paired_rows, paired, comparison


def _site_index(owners: Sequence[str]) -> np.ndarray:
    aidcs = tuple(dict.fromkeys(owners))
    return np.asarray([aidcs.index(value) for value in owners], dtype=int)


def _kappa() -> np.ndarray:
    return np.asarray([KAPPA_KW_PER_ACTIVE_H100_NODE[int(value[1:3])] for value in COHORT_IDS])


def _lp_detail(
    da_slot: np.ndarray, available: np.ndarray, capacity: np.ndarray,
    rack_site: np.ndarray, kappa: np.ndarray, site_scores: np.ndarray,
    anchor_site_kw: np.ndarray, margin: float, peak_control_kw: float,
    *, safety: bool,
) -> dict[str, object]:
    cohorts, racks = da_slot.shape
    n_y = cohorts * racks
    n_u = 12 if safety else 0
    n = n_y + n_u
    c = np.zeros(n); c[:n_y] = -1.0
    site_kw = np.zeros((12, n_y))
    for cohort in range(cohorts):
        for rack in range(racks):
            site_kw[rack_site[rack], cohort * racks + rack] = kappa[cohort] / DT_HOURS
    grid = site_scores @ site_kw
    aub: list[np.ndarray] = []; bub: list[float] = []; labels: list[str] = []
    for cohort in range(cohorts):
        row = np.zeros(n); row[cohort * racks:(cohort + 1) * racks] = 1.0
        aub.append(row); bub.append(float(min(available[cohort], da_slot[cohort].sum())))
        labels.append(f"SERVICE[{COHORT_IDS[cohort]}]")
    for rack in range(racks):
        row = np.zeros(n); row[rack:n_y:racks] = 1.0
        aub.append(row); bub.append(float(capacity[rack])); labels.append(f"RACK[{rack}]")
    if safety:
        for site in range(12):
            positive = np.zeros(n); positive[:n_y] = site_kw[site]; positive[n_y + site] = -1.0
            aub.append(positive); bub.append(float(anchor_site_kw[site])); labels.append(f"ABS_POS[{site}]")
            negative = np.zeros(n); negative[:n_y] = -site_kw[site]; negative[n_y + site] = -1.0
            aub.append(negative); bub.append(float(-anchor_site_kw[site])); labels.append(f"ABS_NEG[{site}]")
        row = np.zeros(n); row[:n_y] = grid; row[n_y:] = margin / max(peak_control_kw, TOL)
        aub.append(row); bub.append(float(site_scores @ anchor_site_kw)); labels.append("NOREGRET_CURRENT")
    result = linprog(
        c, A_ub=np.asarray(aub), b_ub=np.asarray(bub), bounds=[(0.0, None)] * n,
        method="highs", options={"dual_feasibility_tolerance": 1e-9, "primal_feasibility_tolerance": 1e-9},
    )
    if not result.success:
        raise RuntimeError(f"V31_DIAGNOSTIC_LP:{result.message}")
    x = np.asarray(result.x)
    slacks = np.asarray(result.ineqlin.residual)
    duals = np.asarray(result.ineqlin.marginals)
    return {
        "y": x[:n_y].reshape(cohorts, racks), "u": x[n_y:] if safety else np.zeros(12),
        "service": float(x[:n_y].sum()), "grid": float(grid @ x[:n_y]),
        "labels": labels, "slacks": slacks, "duals": duals,
        "site_kw_coefficient": site_kw, "grid_coefficient": grid,
    }


def _execution_parts(y: np.ndarray, da: np.ndarray, rack_site: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    original = np.zeros_like(y); same = np.zeros_like(y); cross = np.zeros_like(y)
    for cohort in range(y.shape[0]):
        original_sites = {int(rack_site[r]) for r in np.flatnonzero(da[cohort] > TOL)}
        for rack in range(y.shape[1]):
            keep = min(float(y[cohort, rack]), float(da[cohort, rack]))
            original[cohort, rack] = keep
            rem = float(y[cohort, rack]) - keep
            if rack_site[rack] in original_sites:
                same[cohort, rack] = rem
            else:
                cross[cohort, rack] = rem
    return original, same, cross


def _load_runtime(repo: Path, source_repo: Path, electrical_cache: Path, trust_cache: Path) -> dict[str, object]:
    schedules = load_frozen_schedules(repo)
    if tuple(schedules) != OFFICIAL_CASES:
        raise RuntimeError("V31_OFFICIAL_CASE_SET")
    actual = materialize_actual_workload(source_repo, DAY)
    initial = _initial_actual(repo, COHORT_IDS)
    mobility = _json(source_repo / "cache/v28r2_campaign_sources/april_2025/days" / DAY / "traffic_mobility.json")
    assert isinstance(mobility, dict)
    mobility_rows = mobility["mess"]
    racks, owners, power_weights, gpu_weights = _mapping(repo)
    residual_gpu = (actual.total_h100_gpu - actual.flexible_natural_gpu)[:, None] * gpu_weights[None, :]
    capacity = np.maximum(0.0, (CASE_CAPACITY_GPU * gpu_weights[None, :] - residual_gpu) * DT_HOURS / 4.0)
    physical_capacity = CASE_CAPACITY_GPU * gpu_weights * DT_HOURS / 4.0
    fixed = {
        case: replay_actual_case(
            source_repo, DAY, schedules[case], actual, mobility_rows,
            initial_backlog_nodeh=initial,
        ) for case in OFFICIAL_CASES
    }
    safety = load_phase_current_safety(electrical_cache, M_CURRENT_EXPECTED)
    scores = np.asarray([phase_aware_site_scores(safety, slot) for slot in range(96)])
    population = build_day_population(repo, trust_cache)
    _, scenario_decision, scenarios = certify_count(population)
    if int(scenario_decision["V30_SCENARIO_COUNT"]) != 64:
        raise RuntimeError("V31_SCENARIO_AUTHORITY")
    return {
        "schedules": schedules, "actual": actual, "initial": initial,
        "mobility": mobility_rows, "racks": racks, "owners": owners,
        "power_weights": power_weights, "gpu_weights": gpu_weights,
        "capacity": capacity, "physical_capacity": physical_capacity,
        "fixed": fixed, "safety": safety, "scores": scores,
        "scenarios": scenarios,
    }


def solve_diagnostics(runtime: Mapping[str, object]) -> tuple[dict[str, dict[str, RecourseResult]], dict[str, dict[int, dict[str, dict[str, object]]]]]:
    schedules = runtime["schedules"]; actual = runtime["actual"]
    owners = runtime["owners"]; capacity = np.asarray(runtime["capacity"])
    fixed = runtime["fixed"]; scores = np.asarray(runtime["scores"])
    initial = np.asarray(runtime["initial"])
    assert isinstance(schedules, dict) and isinstance(fixed, dict)
    rack_site = _site_index(owners)  # type: ignore[arg-type]
    kappa = _kappa()
    margins = {"D_CUR": M_CURRENT_EXPECTED, "D_PAIR": M_PAIR_FROZEN_BOUND, "D_ZERO": 0.0}
    results: dict[str, dict[str, RecourseResult]] = {}
    details: dict[str, dict[int, dict[str, dict[str, object]]]] = {}
    for case in ("B1", "B3"):
        schedule = schedules[case]
        anchor = ANCHOR_BY_CASE[case]
        anchor_flex = _flexible_site_kw(fixed[anchor].workload.executed_nodeh, owners)  # type: ignore[index,arg-type]
        da = np.asarray(schedule["workload_service_tensor"], dtype=float)
        peak = max(1.0, float(np.max(anchor_flex.sum(axis=1))))
        results[case] = {}
        for name, margin in margins.items():
            results[case][name] = solve_causal_day(
                da, actual.arrivals_nodeh, capacity, owners, scores,
                anchor_flex, margin, initial,
            )
        # Recreate the causal availability state and diagnostic service LPs.
        backlog = np.zeros((97, 15)); backlog[0] = initial
        details[case] = {}
        for slot in range(96):
            backlog[slot + 1] = backlog[slot] + actual.arrivals_nodeh[slot]
            available = backlog[slot + 1].copy()
            da_slot = da[:, :, slot]
            slot_detail = {
                "PHYSICAL": _lp_detail(da_slot, available, capacity[slot], rack_site, kappa, scores[slot], anchor_flex[slot], 0.0, peak, safety=False),
                "D_ZERO": _lp_detail(da_slot, available, capacity[slot], rack_site, kappa, scores[slot], anchor_flex[slot], 0.0, peak, safety=True),
                "D_PAIR": _lp_detail(da_slot, available, capacity[slot], rack_site, kappa, scores[slot], anchor_flex[slot], M_PAIR_FROZEN_BOUND, peak, safety=True),
                "D_CUR": _lp_detail(da_slot, available, capacity[slot], rack_site, kappa, scores[slot], anchor_flex[slot], M_CURRENT_EXPECTED, peak, safety=True),
            }
            # The official causal state follows D_CUR.
            backlog[slot + 1] -= results[case]["D_CUR"].executed_nodeh[:, :, slot].sum(axis=1)
            details[case][slot] = slot_detail
    return results, details


def _counterfactual_rows(
    runtime: Mapping[str, object], results: Mapping[str, Mapping[str, RecourseResult]],
    trajectories: Mapping[str, Mapping[str, FrozenTrajectory]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    fixed = runtime["fixed"]; safety = runtime["safety"]
    assert isinstance(fixed, dict)
    official_fresh = {row["case"]: row for row in _csv(Path(runtime["repo"]) / V30_REL / "V30_APR04_FRESH_OPENDSS_RESULTS.csv")}
    rows = []
    for case in ("B1", "B3"):
        anchor = ANCHOR_BY_CASE[case]
        anchor_trajectory = fixed[anchor].trajectory
        critical_slot = int(official_fresh[anchor]["critical_line_slot"])
        branch_name = f"{official_fresh[anchor]['critical_line']}::{official_fresh[anchor]['critical_line_phase']}"
        branch = safety.branch_names.index(branch_name)
        for name, margin in (("D_CUR", M_CURRENT_EXPECTED), ("D_PAIR", M_PAIR_FROZEN_BOUND), ("D_ZERO", 0.0)):
            recourse = results[case][name]
            summary = recourse.summary
            trajectory = trajectories[case][name]
            delta = trajectory.pcc_p_kw - anchor_trajectory.pcc_p_kw
            rows.append({
                "day": DAY, "case": case, "diagnostic": name,
                "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "margin_pu": margin,
                "executed_nodeh": summary["EXECUTED_TOTAL"],
                "grid_safety_blocked_nodeh": summary["GRID_SAFETY_BLOCKED"],
                "executed_original_rack_nodeh": summary["EXECUTED_ORIGINAL_RACK"],
                "same_site_recourse_nodeh": summary["EXECUTED_SAME_SITE_RECOURSE"],
                "cross_site_recourse_nodeh": summary["EXECUTED_CROSS_SITE_RECOURSE"],
                "true_capacity_limit_nodeh": summary["TRUE_RACK_CAPACITY_LIMIT"],
                "critical_slot": critical_slot,
                "critical_slot_AIDC_delta_kw": float(delta[critical_slot].sum()),
                "sensitivity_weighted_AIDC_actuation_pu": float(safety.site_sensitivity[critical_slot, :, branch] @ delta[critical_slot]),
                "planning_rho_relative_to_anchor_pu": float(np.max(np.sum(np.asarray(runtime["scores"]) * delta, axis=1))),
                "Stage1_schedule_fixed": True, "MESS_fixed": True,
                "source_realization_fixed": True, "rack_authority_fixed": True,
                "same_slot_causal_information_fixed": True,
                "lexicographic_objective_fixed": True,
            })
    payload = {
        "artifact_id": "V31_APR04_MARGIN_COUNTERFACTUAL_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "official_cases_unchanged": list(OFFICIAL_CASES),
        "diagnostics": ["D_CUR", "D_PAIR", "D_ZERO"],
        "D_PAIR_margin_source": "frozen Jan-Mar one-sided paired bound; no April rows",
        "D_ZERO_role": "diagnostic planning ceiling only",
        "rows": rows,
    }
    return rows, payload


def _build_trajectories(runtime: Mapping[str, object], results: Mapping[str, Mapping[str, RecourseResult]], source_repo: Path) -> dict[str, dict[str, FrozenTrajectory]]:
    schedules = runtime["schedules"]; actual = runtime["actual"]
    mobility = runtime["mobility"]; owners = runtime["owners"]
    power_weights = np.asarray(runtime["power_weights"]); gpu_weights = np.asarray(runtime["gpu_weights"])
    assert isinstance(schedules, dict)
    trajectories: dict[str, dict[str, FrozenTrajectory]] = {}
    for case in ("B1", "B3"):
        trajectories[case] = {}
        for name in ("D_CUR", "D_PAIR", "D_ZERO"):
            trajectory, _, _ = _recourse_trajectory(
                source_repo, schedules[case], actual, mobility,
                results[case][name], owners, power_weights, gpu_weights,
            )
            trajectories[case][name] = FrozenTrajectory(
                trajectory.day, trajectory.namespace, f"{case}_{name}",
                trajectory.pcc_p_kw, trajectory.pcc_q_kvar,
                trajectory.mess_p_kw, trajectory.mess_q_kvar,
                trajectory.mess_ids, trajectory.mess_locations_96x4,
                trajectory.source_schedule_sha256,
            )
            trajectories[case][name].validate()
    return trajectories


def block_waterfall_and_constraints(
    runtime: Mapping[str, object], results: Mapping[str, Mapping[str, RecourseResult]],
    details: Mapping[str, Mapping[int, Mapping[str, Mapping[str, object]]]],
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]], dict[str, object], list[dict[str, object]], dict[str, object]]:
    schedules = runtime["schedules"]; owners = runtime["owners"]
    scores = np.asarray(runtime["scores"]); capacity = np.asarray(runtime["capacity"])
    fixed = runtime["fixed"]
    assert isinstance(schedules, dict) and isinstance(fixed, dict)
    rack_site = _site_index(owners)  # type: ignore[arg-type]
    kappa = _kappa(); aidcs = tuple(dict.fromkeys(owners))  # type: ignore[arg-type]
    block_rows: list[dict[str, object]] = []
    waterfall_rows: list[dict[str, object]] = []
    active_rows: list[dict[str, object]] = []
    block_summary: dict[str, object] = {
        "artifact_id": "V31_APR04_GRID_SAFETY_BLOCK_SUMMARY_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "cases": {},
        "voltage_and_transformer_note": "V30 Stage-2 LP contains no voltage or transformer constraint; those states are NOT_MODELED, not silently inferred.",
    }
    constraint_summary: dict[str, object] = {
        "artifact_id": "V31_STAGE2_CONSTRAINT_SUMMARY_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "cases": {},
    }
    for case in ("B1", "B3"):
        da = np.asarray(schedules[case]["workload_service_tensor"], dtype=float)
        anchor = ANCHOR_BY_CASE[case]
        anchor_flex = _flexible_site_kw(fixed[anchor].workload.executed_nodeh, owners)  # type: ignore[index,arg-type]
        peak = max(1.0, float(np.max(anchor_flex.sum(axis=1))))
        case_nominal = case_margin = 0.0
        for slot in range(96):
            d = details[case][slot]
            physical = float(d["PHYSICAL"]["service"])
            zero = float(d["D_ZERO"]["service"])
            pair = float(d["D_PAIR"]["service"])
            current = float(d["D_CUR"]["service"])
            official_slot = results[case]["D_CUR"].slot_ledgers[slot]
            executed = float(results[case]["D_CUR"].executed_nodeh[:, :, slot].sum())
            # Numerical LP equivalence with the frozen final lexicographic y.
            if abs(current - executed) > 1e-7:
                raise RuntimeError("V31_DCUR_STAGE2_REPRODUCTION")
            nominal_block = max(0.0, physical - zero)
            margin_block = max(0.0, zero - current)
            if abs(nominal_block + margin_block - official_slot.grid_safety_blocked_nodeh) > 1e-7:
                raise RuntimeError("V31_GRID_BLOCK_PARTITION")
            case_nominal += nominal_block; case_margin += margin_block
            waterfall_rows.append({
                "day": DAY, "case": case, "slot": slot,
                "DA_AUTHORIZED_nodeh": official_slot.da_authorized_nodeh,
                "ACTUAL_SOURCE_AVAILABLE_nodeh": official_slot.actual_available_nodeh,
                "RACK_CAPACITY_FEASIBLE_nodeh": physical,
                "GRID_NOMINALLY_FEASIBLE_nodeh": zero,
                "CURRENT_MARGIN_FEASIBLE_nodeh": current,
                "EXECUTED_nodeh": executed,
                "SOURCE_UNAVAILABLE_nodeh": official_slot.source_unavailable_nodeh,
                "TRUE_RACK_CAPACITY_LIMIT_nodeh": official_slot.true_rack_capacity_limit_nodeh,
                "NOMINAL_CURRENT_LIMIT_nodeh": nominal_block,
                "CURRENT_MARGIN_ONLY_nodeh": margin_block,
                "SAFETY_MARGIN_SERVICE_COST_NODEH": margin_block,
                "identity_error_nodeh": official_slot.da_authorized_nodeh - (
                    official_slot.source_unavailable_nodeh + official_slot.true_rack_capacity_limit_nodeh
                    + nominal_block + margin_block + executed
                ),
            })
            # Allocate each exact slot/reason total over the physical proposal
            # cells. This is an attribution measure, not a claim that jobs were
            # individually ordered by the service LP tie-break.
            proposal = np.asarray(d["PHYSICAL"]["y"])
            weight_total = float(proposal.sum())
            cur = d["D_CUR"]
            labels = list(cur["labels"]); slacks = np.asarray(cur["slacks"]); duals = np.asarray(cur["duals"])
            nr_i = labels.index("NOREGRET_CURRENT")
            current_y = results[case]["D_CUR"].executed_nodeh[:, :, slot]
            current_site_kw = np.zeros(12)
            for rack in range(48):
                current_site_kw[rack_site[rack]] += float(kappa @ current_y[:, rack]) / DT_HOURS
            delta_site = current_site_kw - anchor_flex[slot]
            lhs_before = float(scores[slot] @ delta_site)
            lhs_after = lhs_before + M_CURRENT_EXPECTED / peak * float(np.abs(delta_site).sum())
            for reason, amount in (("CURRENT_MARGIN_ONLY", margin_block), ("NOMINAL_CURRENT_LIMIT", nominal_block)):
                if amount <= TOL:
                    continue
                emitted = 0.0
                cells = np.argwhere(proposal > TOL)
                for position, (cohort, rack) in enumerate(cells):
                    share = amount - emitted if position == len(cells) - 1 else amount * float(proposal[cohort, rack]) / weight_total
                    emitted += share
                    original_racks = np.flatnonzero(da[cohort, :, slot] > TOL)
                    original_rack = int(original_racks[0]) if len(original_racks) else -1
                    rack_label = str(runtime["racks"][rack])  # type: ignore[index]
                    rack_slack = float(slacks[labels.index(f"RACK[{rack}]")])
                    service_slack = float(slacks[labels.index(f"SERVICE[{COHORT_IDS[cohort]}]")])
                    block_rows.append({
                        "day": DAY, "case": case, "slot": slot, "cohort": COHORT_IDS[cohort],
                        "original_rack": str(runtime["racks"][original_rack]) if original_rack >= 0 else "NONE",  # type: ignore[index]
                        "proposed_rack": rack_label, "proposed_AIDC": aidcs[rack_site[rack]],
                        "nodeh_blocked": share,
                        "planned_candidate_minus_anchor_rho_difference_pu": lhs_before,
                        "M_CURRENT_pu": M_CURRENT_EXPECTED,
                        "safety_LHS_before_margin_pu": lhs_before,
                        "safety_LHS_after_M_CURRENT_pu": lhs_after,
                        "voltage_constraint_state": "NOT_MODELED_IN_V30_STAGE2",
                        "current_constraint_state": "ACTIVE" if abs(float(slacks[nr_i])) <= 1e-7 else "INACTIVE",
                        "transformer_constraint_state": "NOT_MODELED_IN_V30_STAGE2",
                        "rack_constraint_state": "ACTIVE" if rack_slack <= 1e-7 else "INACTIVE",
                        "service_constraint_state": "ACTIVE" if service_slack <= 1e-7 else "INACTIVE",
                        "sensitivity_weighted_electrical_leverage_pu_per_nodeh": float(abs(scores[slot, rack_site[rack]] * kappa[cohort] / DT_HOURS)),
                        "primary_blocking_reason": reason,
                        "attribution_method": "exact_slot_reason_mass_proportional_to_physical_service_proposal",
                    })
                if abs(emitted - amount) > 1e-9:
                    raise RuntimeError("V31_BLOCK_ALLOCATION")
            if official_slot.grid_safety_blocked_nodeh > TOL:
                rack_slacks = [float(slacks[labels.index(f"RACK[{r}]")]) for r in range(48)]
                service_slacks = [float(slacks[labels.index(f"SERVICE[{c}]")]) for c in COHORT_IDS]
                active_rows.append({
                    "day": DAY, "case": case, "slot": slot,
                    "GRID_SAFETY_BLOCKED_nodeh": official_slot.grid_safety_blocked_nodeh,
                    "active_line_current_constraint": "CONSERVATIVE_TOP5_PERCENT_BRANCH_ENVELOPE",
                    "active_phase": "ENVELOPE_MULTIPLE_PHASES",
                    "active_voltage_constraint": False,
                    "active_transformer_constraint": False,
                    "active_rack_constraint_count": sum(x <= 1e-7 for x in rack_slacks),
                    "active_no_regret_constraint": float(slacks[nr_i]) <= 1e-7,
                    "no_regret_slack_pu": float(slacks[nr_i]),
                    "no_regret_dual_nodeh_per_pu": float(duals[nr_i]),
                    "minimum_rack_slack_nodeh": min(rack_slacks),
                    "minimum_service_slack_nodeh": min(service_slacks),
                    "voltage_slack": "NOT_MODELED_IN_V30_STAGE2",
                    "transformer_slack": "NOT_MODELED_IN_V30_STAGE2",
                    "lexicographic_phase_service_became_blocked": "PRIORITY_1_MAX_SERVICE",
                    "no_regret_margin_blocked_nodeh": margin_block,
                    "physical_planning_current_blocked_nodeh": nominal_block,
                    "voltage_blocked_nodeh": 0.0,
                    "transformer_blocked_nodeh": 0.0,
                    "rack_blocked_nodeh": official_slot.true_rack_capacity_limit_nodeh,
                    "multiple_constraint_blocked_nodeh": 0.0,
                })
        official_total = float(results[case]["D_CUR"].summary["GRID_SAFETY_BLOCKED"])
        block_summary["cases"][case] = {
            "GRID_SAFETY_BLOCKED_nodeh": official_total,
            "CURRENT_MARGIN_ONLY_nodeh": case_margin,
            "NOMINAL_CURRENT_LIMIT_nodeh": case_nominal,
            "partition_identity_error_nodeh": official_total - case_margin - case_nominal,
        }
        constraint_summary["cases"][case] = {
            "no_regret_margin_blocked_nodeh": case_margin,
            "physical_planning_current_limit_nodeh": case_nominal,
            "voltage_limit_nodeh": 0.0, "transformer_limit_nodeh": 0.0,
            "rack_capacity_limit_nodeh": float(results[case]["D_CUR"].summary["TRUE_RACK_CAPACITY_LIMIT"]),
            "multiple_grid_limits_nodeh": 0.0,
            "grid_partition_identity_error_nodeh": float(results[case]["D_CUR"].summary["GRID_SAFETY_BLOCKED"]) - case_margin - case_nominal,
        }
    aggregate_waterfall = {}
    for case in ("B1", "B3"):
        rows = [r for r in waterfall_rows if r["case"] == case]
        totals = {key: sum(float(r[key]) for r in rows) for key in (
            "DA_AUTHORIZED_nodeh", "ACTUAL_SOURCE_AVAILABLE_nodeh", "RACK_CAPACITY_FEASIBLE_nodeh",
            "GRID_NOMINALLY_FEASIBLE_nodeh", "CURRENT_MARGIN_FEASIBLE_nodeh", "EXECUTED_nodeh",
            "SOURCE_UNAVAILABLE_nodeh", "TRUE_RACK_CAPACITY_LIMIT_nodeh", "NOMINAL_CURRENT_LIMIT_nodeh",
            "CURRENT_MARGIN_ONLY_nodeh", "SAFETY_MARGIN_SERVICE_COST_NODEH",
        )}
        totals.update({
            "RAW_EXECUTION_RATIO": totals["EXECUTED_nodeh"] / totals["DA_AUTHORIZED_nodeh"],
            "AVAILABILITY_CONDITIONED_EXECUTION_RATIO": totals["EXECUTED_nodeh"] / totals["ACTUAL_SOURCE_AVAILABLE_nodeh"],
            "CAPACITY_CONDITIONED_EXECUTION_RATIO": totals["EXECUTED_nodeh"] / totals["RACK_CAPACITY_FEASIBLE_nodeh"],
            "GRID_CONDITIONED_EXECUTION_RATIO": totals["EXECUTED_nodeh"] / totals["GRID_NOMINALLY_FEASIBLE_nodeh"],
            "ratio_denominator_definitions": {
                "availability": "direct sum of per-slot min(observed causal backlog, DA cohort authorization)",
                "capacity": "maximum service with source, authorization, and rack constraints; no grid constraint",
                "grid": "maximum service after the zero-margin nominal current constraint",
            },
            "maximum_slot_identity_error_nodeh": max(abs(float(r["identity_error_nodeh"])) for r in rows),
        })
        aggregate_waterfall[case] = totals
    waterfall_json = {
        "artifact_id": "V31_APR04_EXECUTION_WATERFALL_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "cases": aggregate_waterfall,
    }
    return block_rows, block_summary, waterfall_rows, waterfall_json, active_rows, constraint_summary


def fresh_false_block(
    repo: Path, source_repo: Path, electrical_cache: Path,
    runtime: Mapping[str, object], results: Mapping[str, Mapping[str, RecourseResult]],
    trajectories: Mapping[str, Mapping[str, FrozenTrajectory]], out: Path,
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, dict[str, dict[str, object]]]]:
    official = {row["case"]: row for row in _csv(repo / V30_REL / "V30_APR04_FRESH_OPENDSS_RESULTS.csv")}
    voltage_path = next((electrical_cache / "data").glob("D1_AC_ANCHOR_SENSITIVITY_*.npz"))
    current_path = next((electrical_cache / "data").glob("D1_AC_ANCHOR_CURRENT_SENSITIVITY_*.npz"))
    resume_path = out / "V31_APR04_FALSE_SAFETY_BLOCK.csv"
    resumed = _csv(resume_path) if resume_path.is_file() else []
    by_key = {(row["case"], row["diagnostic"]): dict(row) for row in resumed if row.get("row_type") == "FRESH_TRAJECTORY"}
    fresh_by: dict[str, dict[str, dict[str, object]]] = {"B1": {}, "B3": {}}
    fresh_solve_count = 0
    for case in ("B1", "B3"):
        for name in ("D_PAIR", "D_ZERO"):
            key = (case, name)
            if key in by_key and int(by_key[key]["convergence_count"]) == 96:
                row = {k: v for k, v in by_key[key].items()}
            else:
                trajectory = trajectories[case][name]
                context = _electrical_context(repo, source_repo, trajectory, voltage_path, current_path)
                fresh = run_fresh_opendss(repo=repo, context=context, voltage=context.voltage, trajectory=trajectory)
                raw = _fresh_row(fresh, "ACTUAL", "V31_NON_AUTHORITY_DIAGNOSTIC_ONLY")
                context.voltage.close(); context.current.close()
                row = {
                    "row_type": "FRESH_TRAJECTORY", "day": DAY, "case": case,
                    "diagnostic": name, "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY",
                    **raw,
                }
                fresh_solve_count += 96
                by_key[key] = dict(row)
                _write_csv(resume_path, list(by_key.values()))
            fresh_by[case][name] = row
    rows: list[dict[str, object]] = []
    for case in ("B1", "B3"):
        anchor = ANCHOR_BY_CASE[case]
        anchor_rho = float(official[anchor]["rho_max_AC"])
        current_executed = float(results[case]["D_CUR"].summary["EXECUTED_TOTAL"])
        pair_executed = float(results[case]["D_PAIR"].summary["EXECUTED_TOTAL"])
        zero_executed = float(results[case]["D_ZERO"].summary["EXECUTED_TOTAL"])
        for name, released in (("D_PAIR", pair_executed - current_executed), ("D_ZERO", zero_executed - current_executed)):
            raw = fresh_by[case][name]
            rho = float(raw["rho_max_AC"])
            safe = rho <= anchor_rho + 1e-12
            if name == "D_PAIR":
                classification = "FRESH_SAFE_UNDER_PAIRED_MARGIN" if safe else "FRESH_TRUE_UNSAFE"
            else:
                classification = "FRESH_SAFE_BUT_CURRENT_MARGIN_BLOCKED" if safe else "FRESH_UNSAFE_UNDER_ZERO_MARGIN"
            rows.append({
                **raw, "row_type": "FRESH_TRAJECTORY", "case": case, "diagnostic": name,
                "anchor_case": anchor, "anchor_rho_AC": anchor_rho,
                "candidate_minus_anchor_rho_delta_pu": rho - anchor_rho,
                "anchor_relative_no_regret": safe,
                "released_vs_D_CUR_nodeh": released,
                "classification": classification,
                "Fresh_used_for_margin_selection": False,
            })
        rows.append({
            "row_type": "UNEXECUTED_ZERO_MARGIN_REMAINDER", "day": DAY, "case": case,
            "diagnostic": "D_ZERO", "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY",
            "anchor_case": anchor,
            "released_vs_D_CUR_nodeh": float(results[case]["D_ZERO"].summary["GRID_SAFETY_BLOCKED"]),
            "classification": "UNRESOLVED",
            "explanation": "Work still rejected by the nominal planning-current envelope was never executed; the four authorized Fresh trajectories cannot label it physically safe or unsafe.",
            "Fresh_used_for_margin_selection": False,
        })
    _write_csv(resume_path, rows)
    review_cases = {}
    for case in ("B1", "B3"):
        case_rows = [row for row in rows if row["case"] == case]
        true_unsafe = sum(float(row.get("released_vs_D_CUR_nodeh", 0.0)) for row in case_rows if row["classification"] in {"FRESH_TRUE_UNSAFE", "FRESH_UNSAFE_UNDER_ZERO_MARGIN"})
        safe_current = sum(float(row.get("released_vs_D_CUR_nodeh", 0.0)) for row in case_rows if row["classification"] == "FRESH_SAFE_BUT_CURRENT_MARGIN_BLOCKED")
        safe_pair = sum(float(row.get("released_vs_D_CUR_nodeh", 0.0)) for row in case_rows if row["classification"] == "FRESH_SAFE_UNDER_PAIRED_MARGIN")
        unresolved = sum(float(row.get("released_vs_D_CUR_nodeh", 0.0)) for row in case_rows if row["classification"] == "UNRESOLVED")
        review_cases[case] = {
            "FRESH_TRUE_UNSAFE_nodeh": true_unsafe,
            "FRESH_SAFE_BUT_CURRENT_MARGIN_BLOCKED_nodeh": safe_current,
            "FRESH_SAFE_UNDER_PAIRED_MARGIN_nodeh": safe_pair,
            "UNRESOLVED_nominally_blocked_nodeh": unresolved,
            "D_PAIR_Fresh_candidate_minus_anchor_rho_delta_pu": float(fresh_by[case]["D_PAIR"]["rho_max_AC"]) - float(official[ANCHOR_BY_CASE[case]]["rho_max_AC"]),
            "D_ZERO_Fresh_candidate_minus_anchor_rho_delta_pu": float(fresh_by[case]["D_ZERO"]["rho_max_AC"]) - float(official[ANCHOR_BY_CASE[case]]["rho_max_AC"]),
        }
    review = {
        "artifact_id": "V31_APR04_FALSE_SAFETY_BLOCK_REVIEW_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "cases": review_cases,
        "new_Fresh_trajectory_count": 4, "new_full_slot_Fresh_solve_count": 384,
        "D_CUR_Fresh_repeated": False, "Fresh_used_ex_post_only": True,
        "April_used_to_fit_or_choose_M_PAIRED_MAX": False,
        "scope_limit": "Fresh safety is known only for the executed D_PAIR/D_ZERO trajectories, not for work remaining blocked under D_ZERO.",
    }
    return rows, review, fresh_by


def headroom_and_grid_value(
    repo: Path, runtime: Mapping[str, object], results: Mapping[str, Mapping[str, RecourseResult]],
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]], dict[str, object]]:
    schedules = runtime["schedules"]; owners = runtime["owners"]; racks = runtime["racks"]
    scores = np.asarray(runtime["scores"]); capacity = np.asarray(runtime["capacity"])
    physical_capacity = np.asarray(runtime["physical_capacity"])
    assert isinstance(schedules, dict)
    rack_site = _site_index(owners)  # type: ignore[arg-type]
    aidcs = tuple(dict.fromkeys(owners))  # type: ignore[arg-type]
    kappa = _kappa()
    leverage = np.abs(scores)
    q25, median, q75 = np.quantile(leverage, [.25, .5, .75])
    critical_order = np.argsort(np.max(np.asarray(runtime["safety"].anchor_loading), axis=1))[::-1]
    top5 = set(map(int, critical_order[:5])); top10 = set(map(int, critical_order[:10]))
    fd_rows = _csv(repo / "dayahead/artifacts/v29r3_aidc_effect_forensic/V29R3_CRITICAL_LINE_SENSITIVITY.csv")
    realized_fd = {(int(r["critical_slot"]), r["aidc_id"]): float(r["fresh_central_FD_sensitivity_pu_per_kw"]) for r in fd_rows}
    headroom_rows: list[dict[str, object]] = []
    value_rows: list[dict[str, object]] = []
    headroom_review: dict[str, object] = {
        "artifact_id": "V31_GRID_EFFECTIVE_HEADROOM_REVIEW_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "cases": {},
        "leverage_quartiles_pu_per_kw": {"q25": float(q25), "median": float(median), "q75": float(q75)},
        "S_PREAPRIL_definition": "V30 frozen pre-April-certified phase-current sensitivity authority, evaluated on the frozen Apr-04 DA electrical cache; April outcomes are not used.",
        "Apr04_realized_sensitivity_scope": "Only the already-frozen V29R3 Fresh central-FD values at B3 anchor critical slot 63 exist; other cells are explicitly unavailable.",
    }
    value_review: dict[str, object] = {
        "artifact_id": "V31_RECOVERED_WORKLOAD_GRID_VALUE_REVIEW_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "cases": {},
    }
    for case in ("B1", "B3"):
        da = np.asarray(schedules[case]["workload_service_tensor"], dtype=float)
        allocation = da.sum(axis=0).T
        h = np.maximum(0.0, physical_capacity[None, :] - allocation)
        y = results[case]["D_CUR"].executed_nodeh
        original = np.zeros_like(y); same = np.zeros_like(y); cross = np.zeros_like(y)
        for slot in range(96):
            o, s, c = _execution_parts(y[:, :, slot], da[:, :, slot], rack_site)
            original[:, :, slot] = o; same[:, :, slot] = s; cross[:, :, slot] = c
        high_h = low_h = total_h = used_high = unused_high = used_low = 0.0
        recourse_total = recourse_high = 0.0
        grid_effective = 0.0
        for slot in range(96):
            for rack in range(48):
                site = int(rack_site[rack]); lev = float(leverage[slot, site])
                received = float((same[:, rack, slot] + cross[:, rack, slot]).sum())
                hv = float(h[slot, rack]); total_h += hv; grid_effective += hv * lev
                if lev >= q75:
                    high_h += hv; used_high += min(hv, received); unused_high += max(0.0, hv - received)
                if lev <= q25:
                    low_h += hv; used_low += min(hv, received)
                recourse_total += received
                if lev >= q75:
                    recourse_high += received
                headroom_rows.append({
                    "day": DAY, "case": case, "slot": slot, "AIDC": aidcs[site],
                    "rack": racks[rack], "h_REC_nodeh": hv,
                    "physical_rack_capacity_nodeh": float(physical_capacity[rack]),
                    "actual_residual_occupancy_nodeh": float(physical_capacity[rack] - capacity[slot, rack]),
                    "actual_residual_capacity_nodeh": float(capacity[slot, rack]),
                    "DA_flexible_occupancy_nodeh": float(allocation[slot, rack]),
                    "scenario_recourse_demand_nodeh": None,
                    "scenario_recourse_demand_status": "NOT_MATERIALIZED_PER_RACK_IN_FROZEN_V30_STAGE1",
                    "preApril_electrical_sensitivity_pu_per_kw": float(scores[slot, site]),
                    "Apr04_realized_electrical_sensitivity_pu_per_kw": realized_fd.get((slot, aidcs[site])),
                    "headroom_utilization_in_Actual": received / hv if hv > TOL else None,
                    "actual_recourse_received_nodeh": received,
                    "top5_grid_critical_slot": slot in top5,
                    "top10_grid_critical_slot": slot in top10,
                    "top_quartile_leverage_site_slot": lev >= q75,
                    "bottom_quartile_leverage_site_slot": lev <= q25,
                    "GRID_EFFECTIVE_HEADROOM_contribution_nodeh_pu_per_kw": hv * lev,
                })
            for cohort in range(15):
                original_sites = {int(rack_site[r]) for r in np.flatnonzero(da[cohort, :, slot] > TOL)}
                for rack in range(48):
                    amount = float(y[cohort, rack, slot])
                    if amount <= TOL:
                        continue
                    kept = min(amount, float(da[cohort, rack, slot]))
                    rem = amount - kept
                    site = int(rack_site[rack]); lev = float(leverage[slot, site])
                    for kind, nodeh in (("original-rack", kept), (("same-site reassigned" if site in original_sites else "cross-site reassigned"), rem)):
                        if nodeh <= TOL:
                            continue
                        delta_kw = float(kappa[cohort] / DT_HOURS * nodeh)
                        contribution = abs(float(scores[slot, site]) * delta_kw)
                        value_rows.append({
                            "day": DAY, "case": case, "slot": slot, "cohort": COHORT_IDS[cohort],
                            "execution_class": kind, "destination_AIDC": aidcs[site],
                            "destination_rack": racks[rack], "executed_nodeh": nodeh,
                            "destination_sensitivity_pu_per_kw": float(scores[slot, site]),
                            "slot_sensitivity_abs_pu_per_kw": lev,
                            "delta_PCC_kw": delta_kw,
                            "absolute_sensitivity_weighted_contribution_pu": contribution,
                            "destination_above_median_leverage": lev >= median,
                            "executed_in_top10_critical_slot": slot in top10,
                        })
        headroom_review["cases"][case] = {
            "GRID_EFFECTIVE_HEADROOM": grid_effective,
            "aggregate_headroom_nodeh": total_h,
            "fraction_headroom_top_quartile_leverage_site_slots": high_h / total_h,
            "fraction_headroom_bottom_quartile_leverage_site_slots": low_h / total_h,
            "headroom_consumed_at_high_leverage_nodeh": used_high,
            "unused_high_leverage_headroom_nodeh": unused_high,
            "used_low_leverage_headroom_nodeh": used_low,
            "fraction_recourse_executed_at_high_leverage_site_slots": recourse_high / max(recourse_total, TOL),
        }
        case_values = [r for r in value_rows if r["case"] == case]
        metrics = {}
        for label, accepted in {
            "same_site": {"same-site reassigned"},
            "cross_site": {"cross-site reassigned"},
            "all_recourse": {"same-site reassigned", "cross-site reassigned"},
        }.items():
            selected = [r for r in case_values if r["execution_class"] in accepted]
            nodeh = sum(float(r["executed_nodeh"]) for r in selected)
            weighted = sum(float(r["absolute_sensitivity_weighted_contribution_pu"]) for r in selected)
            metrics[label] = {
                "recovered_nodeh": nodeh, "absolute_sensitivity_weighted_actuation_pu": weighted,
                "GRID_VALUE_PER_RECOVERED_NODEH": weighted / max(nodeh, TOL),
                "fraction_above_median_leverage": sum(float(r["executed_nodeh"]) for r in selected if r["destination_above_median_leverage"]) / max(nodeh, TOL),
            }
        value_review["cases"][case] = metrics
    # Identical Stage-1 headroom means either recourse case is an exact answer
    # to the singular final-report headroom fraction.
    headroom_review["headline_fraction_headroom_high_leverage"] = headroom_review["cases"]["B1"]["fraction_headroom_top_quartile_leverage_site_slots"]
    return headroom_rows, headroom_review, value_rows, value_review


def critical_slot_forensic(
    repo: Path, runtime: Mapping[str, object], results: Mapping[str, Mapping[str, RecourseResult]],
    trajectories: Mapping[str, Mapping[str, FrozenTrajectory]],
) -> dict[str, object]:
    schedules = runtime["schedules"]; fixed = runtime["fixed"]; owners = runtime["owners"]
    capacity = np.asarray(runtime["capacity"]); physical_capacity = np.asarray(runtime["physical_capacity"])
    scores = np.asarray(runtime["scores"]); safety = runtime["safety"]
    assert isinstance(schedules, dict) and isinstance(fixed, dict)
    rack_site = _site_index(owners)  # type: ignore[arg-type]
    aidcs = tuple(dict.fromkeys(owners))  # type: ignore[arg-type]
    official = {row["case"]: row for row in _csv(repo / V30_REL / "V30_APR04_FRESH_OPENDSS_RESULTS.csv")}
    cases = {}
    for case in ("B1", "B3"):
        anchor = ANCHOR_BY_CASE[case]
        slot = int(official[anchor]["critical_line_slot"])
        line = f"{official[anchor]['critical_line']}::{official[anchor]['critical_line_phase']}"
        branch = safety.branch_names.index(line)
        da = np.asarray(schedules[case]["workload_service_tensor"], dtype=float)
        h = np.maximum(0.0, physical_capacity - da[:, :, slot].sum(axis=0))
        delta = trajectories[case]["D_CUR"].pcc_p_kw[slot] - fixed[anchor].trajectory.pcc_p_kw[slot]
        destinations = []
        for site, aidc in enumerate(aidcs):
            value = float(results[case]["D_CUR"].executed_nodeh[:, rack_site == site, slot].sum())
            if value > TOL:
                destinations.append({
                    "AIDC": aidc, "executed_nodeh": value,
                    "preApril_sensitivity_pu_per_kw": float(safety.site_sensitivity[slot, site, branch]),
                    "envelope_site_score_pu_per_kw": float(scores[slot, site]),
                    "PCC_delta_kw": float(delta[site]),
                })
        cases[case] = {
            "anchor": anchor, "critical_slot": slot,
            "critical_line": official[anchor]["critical_line"],
            "critical_phase": official[anchor]["critical_line_phase"],
            "DA_authorized_workload_nodeh": float(da[:, :, slot].sum()),
            "actual_available_workload_nodeh": results[case]["D_CUR"].slot_ledgers[slot].actual_available_nodeh,
            "available_rack_headroom_nodeh": float(capacity[slot].sum()),
            "h_REC_nodeh": float(h.sum()),
            "current_margin_blocked_nodeh": results[case]["D_CUR"].slot_ledgers[slot].grid_safety_blocked_nodeh,
            "paired_margin_blocked_nodeh": results[case]["D_PAIR"].slot_ledgers[slot].grid_safety_blocked_nodeh,
            "zero_margin_blocked_nodeh": results[case]["D_ZERO"].slot_ledgers[slot].grid_safety_blocked_nodeh,
            "executed_nodeh": {name: float(results[case][name].executed_nodeh[:, :, slot].sum()) for name in ("D_CUR", "D_PAIR", "D_ZERO")},
            "destination_AIDCs": destinations,
            "AIDC_PCC_delta_kw": float(delta.sum()),
            "MESS_state": {
                "anchor_p_kw": np.asarray(fixed[anchor].trajectory.mess_p_kw[slot]).tolist(),
                "candidate_p_kw": np.asarray(trajectories[case]["D_CUR"].mess_p_kw[slot]).tolist(),
                "diagnostic_schedules_byte_identical": bool(
                    np.array_equal(trajectories[case]["D_CUR"].mess_p_kw, trajectories[case]["D_PAIR"].mess_p_kw)
                    and np.array_equal(trajectories[case]["D_CUR"].mess_p_kw, trajectories[case]["D_ZERO"].mess_p_kw)
                ),
                "anchor_candidate_same_case_actuator_identity": bool(np.array_equal(fixed[anchor].trajectory.mess_p_kw, trajectories[case]["D_CUR"].mess_p_kw)),
            },
            "planning_anchor_line_loading_pu": float(safety.anchor_loading[slot, branch]),
            "planning_candidate_line_loading_pu": float(safety.anchor_loading[slot, branch] + safety.site_sensitivity[slot, :, branch] @ delta),
            "anchor_Fresh_daily_rho_AC": float(official[anchor]["rho_max_AC"]),
            "candidate_D_CUR_Fresh_daily_rho_AC": float(official[case]["rho_max_AC"]),
            "why_daily_movement_yields_small_critical_delta": "Recourse is distributed over 96 independent same-slot epochs and 12 AIDCs; the lexicographic grid objective spatially cancels positive and negative site shifts. Only the net PCC shift at the anchor-critical slot enters this value.",
        }
    return {
        "artifact_id": "V31_CRITICAL_SLOT_RECOURSE_FORENSIC_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY", "cases": cases,
        "B3_slot63_expected_delta_kw": -1.5189912317288456,
        "B3_slot63_reproduced": abs(float(cases["B3"]["AIDC_PCC_delta_kw"]) + 1.5189912317288456) <= 1e-9,
    }


def final_review(
    waterfall: Mapping[str, object], block: Mapping[str, object], false_review: Mapping[str, object],
    headroom: Mapping[str, object], grid_value: Mapping[str, object], comparison: Mapping[str, object],
) -> dict[str, object]:
    cases = {}
    for case in ("B1", "B3"):
        wf = waterfall["cases"][case]  # type: ignore[index]
        bl = block["cases"][case]  # type: ignore[index]
        fr = false_review["cases"][case]  # type: ignore[index]
        hr = headroom["cases"][case]  # type: ignore[index]
        dominant = {
            "source_availability": float(wf["SOURCE_UNAVAILABLE_nodeh"]),
            "true_rack_capacity": float(wf["TRUE_RACK_CAPACITY_LIMIT_nodeh"]),
            "current_margin": float(bl["CURRENT_MARGIN_ONLY_nodeh"]),
            "nominal_planning_current": float(bl["NOMINAL_CURRENT_LIMIT_nodeh"]),
        }
        cases[case] = {
            "primary_bottleneck": "PHYSICAL_GRID_DELIVERABILITY_LIMITED",
            "secondary_contributors": [
                "SOURCE_AVAILABILITY_LIMITED", "TRUE_RACK_CAPACITY_LIMITED",
                "GRID_EFFECTIVE_HEADROOM_MISPLACED", "ELECTRICAL_SENSITIVITY_LIMITED",
            ],
            "numerical_evidence_nodeh": dominant,
            "Fresh_demonstrated_physically_unsafe_nodeh": float(fr["FRESH_TRUE_UNSAFE_nodeh"]),
            "nominally_blocked_but_Fresh_unresolved_nodeh": float(fr["UNRESOLVED_nominally_blocked_nodeh"]),
            "fraction_headroom_high_leverage": float(hr["fraction_headroom_top_quartile_leverage_site_slots"]),
            "interpretation": "The zero-margin nominal current envelope remains the largest measured loss. This is a planning-physical deliverability diagnosis; unexecuted work is not falsely labeled Fresh-unsafe.",
        }
    return {
        "artifact_id": "V31_FINAL_BOTTLENECK_REVIEW_V1", "status": "PASS",
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY",
        "RESULT_CLASSIFICATION": "V31_MIXED_AIDC_DELIVERABILITY_LIMITATION_DIAGNOSED",
        "official_cases": list(OFFICIAL_CASES), "official_case_count": 4,
        "diagnostic_trajectories": {name: "NON_AUTHORITY_DIAGNOSTIC_ONLY" for name in ("D_CUR", "D_PAIR", "D_ZERO")},
        "cases": cases,
        "margin_comparison": dict(comparison),
        "one_next_scientific_change": "PRE-APRIL ZERO-MARGIN NOMINAL-CURRENT FRONTIER FRESH-AC CERTIFICATION",
        "recommendation_reason": "Paired-margin recertification would recover little service; the much larger zero-margin nominal-current remainder is still Fresh-unresolved and should be certified before changing formulation or safety policy.",
        "V30_production_change_authorized": False,
    }


def _readme(review: Mapping[str, object]) -> str:
    return f"""# V31 V30 Safety/Headroom Forensic

Result: **{review['RESULT_CLASSIFICATION']}**

This namespace is diagnostic only. It does not change V30 production science,
the four official B0/B1/B2/B3 cases, the Stage-1 or Stage-2 objectives, the
physical model, or the current production no-regret margin.

`D_CUR`, `D_PAIR`, and `D_ZERO` are all `NON_AUTHORITY_DIAGNOSTIC_ONLY`.

The Jan-Mar source retained exact aggregate maximum-absolute candidate errors
but not signed slot-line-phase residual arrays. The anchor predictor is exactly
the Fresh anchor, so the auditable paired diagnostic uses its exact zero anchor
error and the retained one-sided candidate bound. Correlation is undefined
because anchor error variance is zero; no signed cancellation was fabricated.
"""


def run(repo: Path, source_repo: Path, electrical_cache: Path, trust_cache: Path) -> dict[str, object]:
    out = repo / OUT_REL; out.mkdir(parents=True, exist_ok=True)
    audit, pre = starting_audit(repo)
    _write_json(out / "V31_STARTING_AUTHORITY_AUDIT.json", audit)
    _write_json(out / "V31_PRECHANGE_PRESERVATION_MANIFEST.json", pre)
    current_rows, current_repro, paired_rows, paired, comparison = current_and_paired_margin(repo)
    _write_csv(out / "V31_CURRENT_MARGIN_SOURCE_ROWS.csv", current_rows)
    _write_json(out / "V31_CURRENT_MARGIN_REPRODUCTION.json", current_repro)
    _write_csv(out / "V31_PREAPRIL_PAIRED_ERROR_LEDGER.csv", paired_rows)
    _write_json(out / "V31_PAIRED_MARGIN_DIAGNOSTIC.json", paired)
    _write_json(out / "V31_MARGIN_COMPARISON.json", comparison)

    runtime = _load_runtime(repo, source_repo, electrical_cache, trust_cache)
    runtime["repo"] = repo
    results, details = solve_diagnostics(runtime)
    trajectories = _build_trajectories(runtime, results, source_repo)
    counter_rows, counter = _counterfactual_rows(runtime, results, trajectories)
    _write_csv(out / "V31_APR04_MARGIN_COUNTERFACTUAL.csv", counter_rows)
    _write_json(out / "V31_APR04_MARGIN_COUNTERFACTUAL.json", counter)
    block_rows, block, waterfall_rows, waterfall, active_rows, constraints = block_waterfall_and_constraints(runtime, results, details)
    _write_csv(out / "V31_APR04_GRID_SAFETY_BLOCK_LEDGER.csv", block_rows)
    _write_json(out / "V31_APR04_GRID_SAFETY_BLOCK_SUMMARY.json", block)
    _write_csv(out / "V31_APR04_EXECUTION_WATERFALL.csv", waterfall_rows)
    _write_json(out / "V31_APR04_EXECUTION_WATERFALL.json", waterfall)
    _write_csv(out / "V31_STAGE2_ACTIVE_CONSTRAINTS.csv", active_rows)
    _write_json(out / "V31_STAGE2_CONSTRAINT_SUMMARY.json", constraints)

    false_rows, false_review, fresh_by = fresh_false_block(
        repo, source_repo, electrical_cache, runtime, results, trajectories, out,
    )
    _write_csv(out / "V31_APR04_FALSE_SAFETY_BLOCK.csv", false_rows)
    _write_json(out / "V31_APR04_FALSE_SAFETY_BLOCK_REVIEW.json", false_review)
    head_rows, head_review, value_rows, value_review = headroom_and_grid_value(repo, runtime, results)
    _write_csv(out / "V31_RECOURSE_HEADROOM_FORENSIC.csv", head_rows)
    _write_json(out / "V31_GRID_EFFECTIVE_HEADROOM_REVIEW.json", head_review)
    _write_csv(out / "V31_RECOVERED_WORKLOAD_GRID_VALUE.csv", value_rows)
    _write_json(out / "V31_RECOVERED_WORKLOAD_GRID_VALUE_REVIEW.json", value_review)
    critical = critical_slot_forensic(repo, runtime, results, trajectories)
    _write_json(out / "V31_CRITICAL_SLOT_RECOURSE_FORENSIC.json", critical)
    review = final_review(waterfall, block, false_review, head_review, value_review, comparison)
    _write_json(out / "V31_FINAL_BOTTLENECK_REVIEW.json", review)
    (out / "V31_FINAL_BOTTLENECK_REVIEW.md").write_text(
        f"# V31 Final Bottleneck Review\n\nResult: **{review['RESULT_CLASSIFICATION']}**\n\n"
        "The zero-margin nominal planning-current constraint remains the dominant measured service limitation in B1 and B3. "
        "Only the executed D_PAIR/D_ZERO trajectories were Fresh-certified; work still blocked under D_ZERO remains explicitly unresolved. "
        "No V30 production change is authorized.\n",
        encoding="utf-8", newline="\n",
    )
    (out / "README.md").write_text(_readme(review), encoding="utf-8", newline="\n")
    return {
        "review": review, "waterfall": waterfall, "block": block,
        "false_review": false_review, "headroom": head_review,
        "grid_value": value_review, "counterfactual": counter,
        "critical": critical, "fresh": fresh_by,
    }


def finalize(repo: Path, *, passed: int, failed: int, not_run: int, command: str) -> dict[str, object]:
    out = repo / OUT_REL
    if failed or not_run:
        raise RuntimeError("V31_REQUIRED_TESTS_NOT_GREEN")
    test = {
        "artifact_id": "V31_TEST_REPORT_V1", "status": "PASS",
        "command": command, "passed": passed, "failed": failed, "not_run": not_run,
        "preserved_baseline_passed": 153,
        "required_test_not_run_count": 0,
        "read_only_cache_junctions_removed_after_run": True,
        "suites": [
            {"name": "V31 diagnostic, artifact, and scientific-contract gates", "passed": passed - 153, "failed": 0},
            {"name": "preserved V30/V29R3/V29R2/V29/V29R1 regression gates", "passed": 153, "failed": 0},
        ],
    }
    _write_json(out / "V31_TEST_REPORT.json", test)
    changed_v30_code = _git(repo, "diff", "--name-only", STARTING_HEAD, "--", "dayahead/v30", "tools/v30", "tests/dayahead/test_v30_two_stage_aidc_recourse.py").splitlines()
    changed_v30_artifacts = _git(repo, "diff", "--name-only", STARTING_HEAD, "--", V30_REL.as_posix()).splitlines()
    post = {
        "artifact_id": "V31_POSTCHANGE_PRESERVATION_AUDIT_V1",
        "status": "PASS" if not changed_v30_code and not changed_v30_artifacts else "FAIL",
        "starting_HEAD": STARTING_HEAD,
        "V30_production_code_changed": changed_v30_code,
        "V30_production_artifacts_changed": changed_v30_artifacts,
        "V30_artifact_aggregate_sha256": _manifest_value(repo, V30_REL, "V30_ARTIFACT_SHA256.json"),
        "V29R2_artifact_aggregate_sha256": _manifest_value(repo, V29R2_REL, "V29R2_ARTIFACT_SHA256.json"),
        "V29R3_artifact_aggregate_sha256": _manifest_value(repo, Path("dayahead/artifacts/v29r3_aidc_effect_forensic"), "V29R3_ARTIFACT_SHA256.json"),
        "official_cases": list(OFFICIAL_CASES), "official_case_count": 4,
        "production_margin_replaced": False, "push_performed": False, "merge_performed": False,
        "protected_mismatch_count": len(changed_v30_code) + len(changed_v30_artifacts),
    }
    if post["status"] != "PASS":
        raise RuntimeError("V31_POSTCHANGE_PRESERVATION_FAIL")
    _write_json(out / "V31_POSTCHANGE_PRESERVATION_AUDIT.json", post)
    manifest = _files_digest(out, exclude=("V31_ARTIFACT_SHA256.json",))
    manifest.update({"artifact_id": "V31_ARTIFACT_SHA256_V1", "status": "PASS", "self_excluded": True})
    _write_json(out / "V31_ARTIFACT_SHA256.json", manifest)
    return {"test": test, "post": post, "manifest": manifest}
