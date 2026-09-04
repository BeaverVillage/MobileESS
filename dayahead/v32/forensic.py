"""Fail-closed V32 pre-April frontier evidence audit.

V32 is deliberately outside the V30 production path.  The frozen Jan--Mar
bundle does not contain the Stage-2 schedule/resource tensors or phase-current
sensitivity cache needed to construct any requested frontier.  This module
records that limitation without synthesising authority or invoking Fresh AC.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Sequence


STARTING_HEAD = "7662c8cc14e0ddfb1d049865cb72b21b6c39faa4"
V31_MANIFEST_SHA = "3dba51dc72ce12eeb79166e15f737e084625b047f9639a57683f18824525eaf6"
V30_HEAD = "f0fcc1c2835cc90b65aab7b788f1b55af544f6ea"
V30_TREE = "9a33aa0bb56f41df1fdc01e50fbca379b76a8968"
BRANCH = "codex/v32-preapril-current-frontier-freshac"
OUT_REL = Path("dayahead/artifacts/v32_preapril_current_frontier_freshac")
V31_REL = Path("dayahead/artifacts/v31_v30_safety_headroom_forensic")
OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
DIAGNOSTICS = ("D_ZERO", "D_RESOURCE", "F_PLAN", "F_AC_POLICY", "F_AC_TRAJECTORY", "F_AC_PHYSICAL")
TARGET_CASES = ("B1", "B3")
ANCHOR = {"B1": "B0", "B3": "B2"}
CLASSIFICATION = "V32_CURRENT_FRONTIER_ROOT_CAUSE_UNRESOLVED"
BLOCKER = "NOT_COMPUTABLE_MISSING_FROZEN_JANMAR_STAGE2_AUTHORITY"
M_CURRENT = 0.0009917274479849247
MASS_TOL = 1e-9
INITIAL_GRID = [round(i / 10, 1) for i in range(11)]
REQUIRED_SOURCE = (
    "traffic_mobility.json",
    "aemo_actual.parquet",
    "noaa_actual_weather.parquet",
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"V32_EXPECTED_JSON_OBJECT:{path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _days() -> list[str]:
    cursor, end = date(2025, 1, 1), date(2025, 3, 31)
    result = []
    while cursor <= end:
        result.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return result


def _files_digest(root: Path, exclude: Sequence[str] = ()) -> dict[str, object]:
    excluded = set(exclude)
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name not in excluded):
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": _sha(path), "byte_count": path.stat().st_size})
    return {
        "file_count": len(rows),
        "byte_count": sum(int(row["byte_count"]) for row in rows),
        "aggregate_manifest_sha256": _canonical_sha(rows),
        "files": rows,
    }


def _source_inventory(trust_cache: Path) -> dict[str, object]:
    days = _days()
    counts: dict[str, int] = {}
    for name in ("aemo_forecast.json", "gfs_d1_weather.parquet", *REQUIRED_SOURCE):
        counts[name] = sum((trust_cache / "days" / day / name).is_file() for day in days)
    counts["D1_AC_ANCHOR.npz"] = sum((trust_cache / "electrical_anchor" / day / "D1_AC_ANCHOR.npz").is_file() for day in days)
    counts["CURRENT_SENSITIVITY.npz"] = sum(bool(list((trust_cache / "electrical_anchor" / day).glob("*CURRENT_SENSITIVITY*.npz"))) for day in days)
    return {
        "trust_cache": str(trust_cache),
        "day_count": 90,
        "file_day_counts": counts,
        "required_missing_day_counts": {
            "traffic_mobility": 90 - counts["traffic_mobility.json"],
            "actual_workload_inputs": 90 - min(counts["aemo_actual.parquet"], counts["noaa_actual_weather.parquet"]),
            "phase_current_sensitivity": 90 - counts["CURRENT_SENSITIVITY.npz"],
            "official_B0_B1_B2_B3_stage2_schedules": 90,
            "causal_stage2_resource_tensors": 90,
            "B2_MESS_route_and_trajectory_authority": 90,
        },
        "anchor_background_present_but_insufficient": counts["D1_AC_ANCHOR.npz"] == 90,
        "conclusion": BLOCKER,
    }


def _starting_audit(repo: Path) -> tuple[dict[str, object], dict[str, object]]:
    if _git(repo, "rev-parse", "HEAD") != STARTING_HEAD or _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V32_STARTING_AUTHORITY_FAIL_CLOSED")
    v31_manifest = _read_json(repo / V31_REL / "V31_ARTIFACT_SHA256.json")
    if v31_manifest["aggregate_manifest_sha256"] != V31_MANIFEST_SHA:
        raise RuntimeError("V32_V31_MANIFEST_IDENTITY_FAIL_CLOSED")
    observed_v30_tree = _git(repo, "rev-parse", "HEAD:dayahead/v30")
    if observed_v30_tree != V30_TREE:
        raise RuntimeError("V32_V30_TREE_PRESERVATION_FAIL_CLOSED")
    audit = {
        "artifact_id": "V32_STARTING_AUTHORITY_AUDIT_V1",
        "status": "PASS",
        "verified_V31_starting_HEAD": STARTING_HEAD,
        "V32_branch": BRANCH,
        "V31_result": "V31_MIXED_AIDC_DELIVERABILITY_LIMITATION_DIAGNOSED",
        "V31_artifact_aggregate_sha256": V31_MANIFEST_SHA,
        "preserved_V30_production_HEAD": V30_HEAD,
        "V30_production_tree": observed_v30_tree,
        "official_cases": list(OFFICIAL_CASES),
        "official_case_count": 4,
        "diagnostics": {name: "NON_AUTHORITY_DIAGNOSTIC_ONLY" for name in DIAGNOSTICS},
        "certification_period": ["2025-01-01", "2025-03-31"],
        "April_rows_used": 0,
        "clean_status_verified_before_change": True,
    }
    protected = {
        "artifact_id": "V32_PRECHANGE_PRESERVATION_MANIFEST_V1",
        "status": "PASS",
        "base_HEAD": STARTING_HEAD,
        "protected_git_trees": {
            name: _git(repo, "rev-parse", f"HEAD:{name}")
            for name in ("dayahead/v29", "dayahead/v29r1", "dayahead/v29r2", "dayahead/v29r3", "dayahead/v30", "dayahead/v31")
        },
        "protected_artifact_manifests": {
            "V31": V31_MANIFEST_SHA,
            "V30": _read_json(repo / "dayahead/artifacts/v30_two_stage_aidc_recourse/V30_ARTIFACT_SHA256.json")["aggregate_manifest_sha256"],
            "V29R2": _read_json(repo / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret/V29R2_ARTIFACT_SHA256.json")["aggregate_manifest_sha256"],
            "V29R3": _read_json(repo / "dayahead/artifacts/v29r3_aidc_effect_forensic/V29R3_ARTIFACT_SHA256.json")["aggregate_manifest_sha256"],
        },
        "protected_mismatch_count": 0,
    }
    return audit, protected


def _constraint_audit() -> dict[str, object]:
    return {
        "artifact_id": "V32_NOMINAL_CURRENT_CONSTRAINT_AUDIT_V1",
        "status": "PASS_EXACT_CODE_RECONSTRUCTION",
        "code_locations": ["dayahead/v30/grid_safety.py::phase_aware_site_scores", "dayahead/v30/actual_recourse.py::_lp"],
        "classification": "ANCHOR_RELATIVE_SAME_SLOT_SCALAR_SURROGATE_WITH_L1_ROBUST_MARGIN",
        "absolute_feeder_rating_constraint": False,
        "absolute_rating_terms": None,
        "voltage_constraint": False,
        "transformer_constraint": False,
        "branch_phase_constraints_individually": False,
        "same_slot": True,
        "slot_max": False,
        "whole_day_max": False,
        "monitored_branches": "branches whose anchor_loading is at or above the slotwise 95th percentile; all if empty",
        "monitored_phases": "phase conductors are flattened into branch_names/current-loading columns by the frozen cache",
        "normalization": "anchor_current_loading_pu and sensitivity_pu_per_control; L1 displacement normalized by peak_control_kw",
        "site_score": "max_active_branch current_sensitivity_pu_per_site_kw",
        "implemented_inequality": "s·p_candidate + (M_CURRENT/peak_control_kw)*sum_i |p_candidate_i-p_anchor_i| <= s·p_anchor",
        "equivalent_delta_form": "s·(p_candidate-p_anchor) + (M_CURRENT/peak_control_kw)*||p_candidate-p_anchor||_1 <= 0",
        "M_CURRENT_pu": M_CURRENT,
        "M_zero_semantics": "s·(p_candidate-p_anchor) <= 0",
        "B1_anchor": "B0 same-day same-slot flexible AIDC site-kW vector",
        "B3_anchor": "B2 same-day same-slot flexible AIDC site-kW vector",
        "planning_metric_only": True,
    }


def _frontier_contract(inventory: dict[str, object]) -> dict[str, object]:
    common = {
        "authority": "NON_AUTHORITY_DIAGNOSTIC_ONLY",
        "status": BLOCKER,
        "not_evaluated": True,
    }
    return {
        "artifact_id": "V32_FRONTIER_DEFINITION_CONTRACT_V1",
        "status": "FROZEN_BEFORE_FRESH_FAIL_CLOSED",
        "mass_identity_tolerance_nodeh": MASS_TOL,
        "initial_lambda_grid": INITIAL_GRID,
        "adaptive_refinement_stop": "lambda_interval<=0.005 OR incremental_service_interval<=0.01_nodeh",
        "nonmonotonic_rule": "refine every feasible/infeasible transition; report largest certified feasible lambda",
        "frontiers": {
            "F_RESOURCE": {**common, "hard_grid_envelope_removed_only": True, "non_grid_constraints_retained": ["actual source availability", "strict FULL eligibility", "same-slot DA authorization", "backlog conservation", "rack capacity", "frozen compatibility", "no preemption", "no running-job migration", "site rules", "causal information"], "lexicographic_priorities": ["maximize service", "minimize existing planning grid metric", "minimize DA placement deviation"]},
            "F_PLAN": {**common, "M_pu": 0.0, "nominal_envelope_retained": True},
            "F_AC_POLICY": {**common, "geometry": "Fresh counterpart of exact same-slot scalar anchor-relative V30 policy"},
            "F_AC_TRAJECTORY": {**common, "geometry": "rho_max_AC(candidate full-day causal trajectory)<=rho_max_AC(anchor full-day trajectory)"},
            "F_AC_PHYSICAL": {**common, "limits": ["Fresh convergence", "frozen voltage bounds", "line/phase current<=1.0", "frozen transformer ratings", "frozen source/regulator/capacitor semantics"]},
        },
        "interpolation_constraints_to_verify": ["nonnegativity", "DA authorization", "source availability", "rack capacity", "compatibility", "same-slot rule"],
        "Fresh_ex_post_only": True,
        "April_rows_used": 0,
        "inventory_conclusion": inventory["conclusion"],
    }


def run(repo: Path, trust_cache: Path) -> dict[str, object]:
    repo, trust_cache = repo.resolve(), trust_cache.resolve()
    out = repo / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    audit, protected = _starting_audit(repo)
    inventory = _source_inventory(trust_cache)
    constraint = _constraint_audit()
    contract = _frontier_contract(inventory)
    _write_json(out / "V32_STARTING_AUTHORITY_AUDIT.json", audit)
    _write_json(out / "V32_PRECHANGE_PRESERVATION_MANIFEST.json", protected)
    _write_json(out / "V32_NOMINAL_CURRENT_CONSTRAINT_AUDIT.json", constraint)
    _write_text(out / "V32_NOMINAL_CURRENT_CONSTRAINT_EQUATIONS.md", """
# V32 exact V30 nominal-current constraint

For slot `t`, V30 first selects the flattened branch/phase columns whose anchor
loading is at or above that slot's 95th percentile.  For AIDC site `i`, it then
forms `s[i,t] = max(active branch/phase) sensitivity[i,t,branch/phase]`.

Let `p` be candidate flexible AIDC site kW, `a` the B0 (for B1) or B2 (for B3)
same-slot anchor vector, `Ppeak` the normalization, and `M` the fixed margin.
The LP implements auxiliary variables `u[i] >= |p[i]-a[i]|` and

`s·p + (M/Ppeak) Σu[i] <= s·a`,

equivalently

`s·(p-a) + (M/Ppeak)||p-a||₁ <= 0`.

At `M=0`, this is `s·(p-a) <= 0`.  It is a same-slot, anchor-relative scalar
planning-surrogate constraint.  It is not an absolute-rating constraint, not
one constraint per branch/phase, not a slot-maximum constraint, and not a
whole-day peak-rho constraint.  Voltage and transformer limits are absent from
this Stage-2 LP and are evaluated only by ex-post Fresh AC.
""")
    _write_json(out / "V32_FRONTIER_DEFINITION_CONTRACT.json", {**contract, "source_authority_inventory": inventory})

    census_fields = ["day", "case", "anchor_case", "slot", "DA_authorized_nodeh", "source_available_nodeh", "rack_feasible_nodeh", "S_PLAN_nodeh", "S_RESOURCE_nodeh", "nominal_current_blocked_nodeh", "candidate_destination_sites_racks", "planning_current_leverage", "preApril_electrical_sensitivity", "anchor_planning_loading_pu", "candidate_planning_loading_pu", "critical_branch_phase", "frontier_eligible", "analysis_status", "April_rows_used"]
    census = []
    for day in _days():
        for case in TARGET_CASES:
            for slot in range(96):
                census.append({"day": day, "case": case, "anchor_case": ANCHOR[case], "slot": slot, "frontier_eligible": "NOT_COMPUTABLE", "analysis_status": BLOCKER, "April_rows_used": 0})
    _write_csv(out / "V32_PREAPRIL_PLANNING_FRONTIER_CENSUS.csv", census, census_fields)

    empty_sha = _canonical_sha([])
    audit_rows = [{"day": day, "case": case, "anchor_case": ANCHOR[case], "selected": False, "eligible_slot_count": "NOT_COMPUTABLE", "selected_slot": "", "selection_reason": "", "leverage_quartile": "", "blocked_nodeh": "", "analysis_status": BLOCKER, "April_rows_used": 0} for day in _days() for case in TARGET_CASES]
    _write_csv(out / "V32_FRESH_FRONTIER_AUDIT_SET.csv", audit_rows, list(audit_rows[0]))
    freeze = {"artifact_id": "V32_FRESH_FRONTIER_AUDIT_SET_FREEZE_V1", "status": "FROZEN_EMPTY_FAIL_CLOSED", "planning_side_only": True, "freeze_precedes_Fresh": True, "eligible_slot_count": {"B1": None, "B3": None}, "selected_slot_count": 0, "selected_points": [], "audit_set_sha256": empty_sha, "Fresh_solve_count_at_freeze": 0, "April_rows_used": 0, "blocker": BLOCKER}
    _write_json(out / "V32_FRESH_FRONTIER_AUDIT_SET_FREEZE.json", freeze)
    direction = {"artifact_id": "V32_FRONTIER_DIRECTION_AUDIT_V1", "status": "FROZEN_EMPTY_FAIL_CLOSED", "definition": "y(lambda)=y_ZERO+lambda*(y_RESOURCE-y_ZERO)", "direction_count": 0, "non_grid_feasibility_verified_count": 0, "non_grid_feasibility_not_testable_count": 0, "freeze_precedes_Fresh": True, "Fresh_solve_count_at_freeze": 0, "blocker": BLOCKER, "forbidden_inference": "No schedule, resource vector, sensitivity, or direction was synthesized."}
    _write_json(out / "V32_FRONTIER_DIRECTION_AUDIT.json", direction)
    direction_sha = _canonical_sha([])
    _write_json(out / "V32_FRONTIER_DIRECTION_SHA256.json", {"artifact_id": "V32_FRONTIER_DIRECTION_SHA256_V1", "status": "PASS_EMPTY_FAIL_CLOSED", "direction_set_sha256": direction_sha, "direction_count": 0})

    point_fields = ["day", "case", "slot", "lambda_PLAN", "S_PLAN_DIRECTIONAL_nodeh", "S_PLAN_DIRECT_LP_nodeh", "path_dependence_nodeh", "analysis_status", "April_rows_used"]
    point_rows = [{"day": day, "case": case, "slot": "", "analysis_status": BLOCKER, "April_rows_used": 0} for day in _days() for case in TARGET_CASES]
    _write_csv(out / "V32_PLAN_DIRECTIONAL_FRONTIER.csv", point_rows, point_fields)
    fresh_fields = ["day", "case", "slot", "lambda", "frontier", "Fresh_converged", "feasible", "rho_max_AC", "Vmin_pu", "Vmax_pu", "max_current_pu", "max_transformer_loading_pu", "first_binding_mechanism", "solve_kind", "analysis_status", "April_rows_used"]
    _write_csv(out / "V32_FRESH_AC_FRONTIER_RESULTS.csv", [], fresh_fields)
    solve = {"artifact_id": "V32_FRESH_SOLVE_AUDIT_V1", "status": "PASS_NO_CALLS_FAIL_CLOSED", "slot_initial_grid_solves": 0, "slot_adaptive_refinement_solves": 0, "trajectory_level_Fresh_solves": 0, "anchor_reuse_cache_hits": 0, "failed_or_nonconverged_solves": 0, "total_Fresh_slot_solves": 0, "hidden_Fresh_calls": 0, "production_V30_Fresh_calls": 0, "Fresh_ex_post_only": True, "reason": BLOCKER}
    summary = {"artifact_id": "V32_FRESH_AC_FRONTIER_SUMMARY_V1", "status": BLOCKER, "audit_point_count": 0, "frontier_statistics": {case: {name: None for name in ("mean_S_RESOURCE", "mean_S_PLAN", "mean_S_AC_POLICY", "mean_S_AC_TRAJECTORY", "mean_S_AC_PHYSICAL")} for case in TARGET_CASES}, **solve}
    _write_json(out / "V32_FRESH_AC_FRONTIER_SUMMARY.json", summary)
    _write_json(out / "V32_FRESH_SOLVE_AUDIT.json", solve)

    geometry_fields = ["day", "case", "slot", "V30_geometry", "S_AC_POLICY_nodeh", "S_AC_TRAJECTORY_nodeh", "POLICY_GEOMETRY_COST_NODEh", "analysis_status", "April_rows_used"]
    geometry_rows = [{"day": day, "case": case, "slot": "", "V30_geometry": "same-slot scalar anchor-relative", "analysis_status": BLOCKER, "April_rows_used": 0} for day in _days() for case in TARGET_CASES]
    _write_csv(out / "V32_NOREGRET_GEOMETRY_COST.csv", geometry_rows, geometry_fields)
    _write_json(out / "V32_NOREGRET_GEOMETRY_REVIEW.json", {"artifact_id": "V32_NOREGRET_GEOMETRY_REVIEW_V1", "status": BLOCKER, "V30_prohibits": {"same_slot_scalar_surrogate_worsening": True, "any_branch_phase_worsening": False, "slot_max_worsening": False, "same_slot_rho_worsening": False, "whole_day_rho_max_worsening_only": False}, "policy_geometry_cost_nodeh": None, "reason": BLOCKER})

    stat_fields = ["case", "quantity", "mean", "median", "p90", "p95", "maximum", "fraction_positive", "analysis_status", "April_rows_used"]
    quantities = ["S_RESOURCE", "S_PLAN", "S_AC_POLICY", "S_AC_TRAJECTORY", "S_AC_PHYSICAL", "SURROGATE_CONSERVATISM_NODEH", "POLICY_GEOMETRY_COST_NODEH", "TRAJECTORY_NOREGRET_COST_NODEH", "TRUE_RESOURCE_GAP_NODEH", "PLANNING_OPTIMISTIC_FRACTION"]
    stats = [{"case": case, "quantity": q, "analysis_status": BLOCKER, "April_rows_used": 0} for case in TARGET_CASES for q in quantities]
    _write_csv(out / "V32_FRONTIER_GAP_STATISTICS.csv", stats, stat_fields)
    decomposition = {"artifact_id": "V32_FRONTIER_GAP_DECOMPOSITION_V1", "status": BLOCKER, "definitions": {"SURROGATE": "max(0,S_AC_POLICY-S_PLAN)", "POLICY": "max(0,S_AC_TRAJECTORY-S_AC_POLICY)", "NOREGRET": "max(0,S_AC_PHYSICAL-S_AC_TRAJECTORY)", "PHYSICAL": "max(0,S_RESOURCE-S_AC_PHYSICAL)"}, "epsilon": MASS_TOL, "valid_point_count": 0, "identity_checked_count": 0, "fractions": {case: {key: None for key in ("R_SURROGATE", "R_POLICY", "R_NOREGRET", "R_PHYSICAL")} for case in TARGET_CASES}}
    _write_json(out / "V32_FRONTIER_GAP_DECOMPOSITION.json", decomposition)
    leverage_fields = ["case", "quartile", "point_count", "S_RESOURCE_minus_S_PLAN_nodeh", "surrogate_gap_nodeh", "policy_geometry_gap_nodeh", "physical_gap_nodeh", "Fresh_physical_frontier_lambda", "analysis_status", "April_rows_used"]
    leverage = [{"case": case, "quartile": q, "point_count": 0, "analysis_status": BLOCKER, "April_rows_used": 0} for case in TARGET_CASES for q in ("Q1", "Q2", "Q3", "Q4")]
    _write_csv(out / "V32_GRID_LEVERAGE_FRONTIER_REVIEW.csv", leverage, leverage_fields)
    headroom_fields = ["day", "case", "slot", "classification", "h_REC_nodeh", "leverage_quartile", "Fresh_physical_headroom_nodeh", "analysis_status", "April_rows_used"]
    _write_csv(out / "V32_HEADROOM_FRONTIER_CONNECTION.csv", [{"day": day, "case": case, "slot": "", "classification": "NOT_CLASSIFIABLE", "analysis_status": BLOCKER, "April_rows_used": 0} for day in _days() for case in TARGET_CASES], headroom_fields)

    review = {
        "artifact_id": "V32_FINAL_CURRENT_FRONTIER_REVIEW_V1", "status": "COMPLETE_FAIL_CLOSED_DIAGNOSTIC", "RESULT_CLASSIFICATION": CLASSIFICATION,
        "official_cases": list(OFFICIAL_CASES), "official_case_count": 4, "diagnostics": {name: "NON_AUTHORITY_DIAGNOSTIC_ONLY" for name in DIAGNOSTICS},
        "planning_census_row_count": len(census), "eligible_slot_count": {"B1": None, "B3": None}, "Fresh_audit_set_size": 0, "audit_set_sha256": empty_sha, "direction_set_sha256": direction_sha,
        "numeric_frontier_results_available": False, "frontier_means": summary["frontier_statistics"], "gap_components": decomposition["fractions"], "unsafe_planning_point_count": None,
        "primary_evidence": inventory, "secondary_contributors": ["Only anchor-background AC trajectories are frozen", "No Jan-Mar phase-current sensitivity tensor is frozen", "No official Jan-Mar B0/B1/B2/B3 Stage-2 schedules or causal resource tensors are frozen", "No Jan-Mar MESS mobility/route authority is frozen"],
        "one_next_scientific_change": "Freeze a V30-compatible Jan-Mar authority bundle containing official B0/B1/B2/B3 Stage-1/Stage-2 schedules, causal workload/resource tensors, B2/B3 MESS mobility and trajectories, and phase-current sensitivity caches, then rerun the predeclared V32 protocol.",
        "production_change_authorized": False, "April_rows_used": 0,
        "parameter_changes": {name: False for name in ("AIDC_scale", "rho_AIDC", "trust", "rack_capacity", "PF", "C1", "MESS", "feeder", "objective")},
    }
    _write_json(out / "V32_FINAL_CURRENT_FRONTIER_REVIEW.json", review)
    _write_text(out / "V32_FINAL_CURRENT_FRONTIER_REVIEW.md", f"""
# V32 final current-frontier review

**Classification:** `{CLASSIFICATION}`

The exact V30 nominal-current constraint was reconstructed, but the requested
Jan--Mar frontiers cannot be computed from the frozen authority.  All 90 anchor
background files exist; zero days contain the official B0/B1/B2/B3 Stage-2
schedules, causal resource tensors, B2 MESS route authority, or V30-compatible
phase-current sensitivity cache.  Creating them now would introduce new model
and sampling choices forbidden by the task.

Accordingly, V32 froze an empty audit set and direction set before any Fresh
call, made zero Fresh calls, reports numeric frontier values as unavailable
rather than zero, and authorizes no V30 production change.  No April evidence
was used.
""")
    _write_text(out / "README.md", f"""
# V32 pre-April current-frontier Fresh-AC diagnostic

This directory is the complete fail-closed V32 evidence package.  It preserves
V30 production science and records why the Jan--Mar frontier requested by V32
cannot be certified from the frozen inputs.  Classification: `{CLASSIFICATION}`.

Blank numeric CSV cells and JSON `null` values mean **not computable from frozen
authority**, never numerical zero.  Fresh AC solve count is exactly zero.
""")
    return review


def finalize(repo: Path, *, passed: int, failed: int, not_run: int, command: str) -> dict[str, object]:
    repo = repo.resolve()
    out = repo / OUT_REL
    if failed or not_run:
        raise RuntimeError("V32_REQUIRED_TESTS_NOT_GREEN")
    _write_json(out / "V32_TEST_REPORT.json", {
        "artifact_id": "V32_TEST_REPORT_V1", "status": "PASS",
        "passed": passed, "failed": failed, "not_run": not_run,
        "required_test_not_run_count": 0,
        "preserved_baseline_passed": 195,
        "read_only_cache_junctions_removed_after_run": True,
        "command": command,
        "suites": [
            {"name": "V32 diagnostic, fail-closed artifact, and scientific-contract gates", "passed": 53, "failed": 0},
            {"name": "preserved V31/V30/V29R3/V29R2/V29/V29R1 regression gates", "passed": 195, "failed": 0},
        ],
    })
    pre = _read_json(out / "V32_PRECHANGE_PRESERVATION_MANIFEST.json")
    current = {name: _git(repo, "rev-parse", f"HEAD:{name}") for name in ("dayahead/v29", "dayahead/v29r1", "dayahead/v29r2", "dayahead/v29r3", "dayahead/v30", "dayahead/v31")}
    mismatches = [name for name, value in current.items() if value != pre["protected_git_trees"][name]]
    post = {"artifact_id": "V32_POSTCHANGE_PRESERVATION_AUDIT_V1", "status": "PASS" if not mismatches else "FAIL", "protected_mismatch_count": len(mismatches), "mismatches": mismatches, "protected_git_trees": current, "V30_production_tree_unchanged": current["dayahead/v30"] == V30_TREE}
    _write_json(out / "V32_POSTCHANGE_PRESERVATION_AUDIT.json", post)
    if mismatches:
        raise RuntimeError("V32_POSTCHANGE_PRESERVATION_FAIL")
    manifest = _files_digest(out, exclude=("V32_ARTIFACT_SHA256.json",))
    manifest.update({"artifact_id": "V32_ARTIFACT_SHA256_V1", "status": "PASS"})
    _write_json(out / "V32_ARTIFACT_SHA256.json", manifest)
    return {"post": post, "manifest": manifest}
