"""V32 frontier contract, fail-closed evidence, and preservation gates."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v32_preapril_current_frontier_freshac"
BLOCKER = "NOT_COMPUTABLE_MISSING_FROZEN_JANMAR_STAGE2_AUTHORITY"


def j(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_01_exact_v31_starting_head() -> None:
    assert j("V32_STARTING_AUTHORITY_AUDIT.json")["verified_V31_starting_HEAD"] == "7662c8cc14e0ddfb1d049865cb72b21b6c39faa4"


def test_02_v31_manifest_identity() -> None:
    assert j("V32_STARTING_AUTHORITY_AUDIT.json")["V31_artifact_aggregate_sha256"] == "3dba51dc72ce12eeb79166e15f737e084625b047f9639a57683f18824525eaf6"


def test_03_v30_production_tree_unchanged() -> None:
    assert j("V32_STARTING_AUTHORITY_AUDIT.json")["V30_production_tree"] == "9a33aa0bb56f41df1fdc01e50fbca379b76a8968"


def test_04_official_cases_exact() -> None:
    assert j("V32_STARTING_AUTHORITY_AUDIT.json")["official_cases"] == ["B0", "B1", "B2", "B3"]


def test_05_no_fifth_official_case() -> None:
    assert j("V32_STARTING_AUTHORITY_AUDIT.json")["official_case_count"] == 4


def test_06_constraint_reconstructed() -> None:
    value = j("V32_NOMINAL_CURRENT_CONSTRAINT_AUDIT.json")
    assert value["status"] == "PASS_EXACT_CODE_RECONSTRUCTION"
    assert value["equivalent_delta_form"] == "s·(p_candidate-p_anchor) + (M_CURRENT/peak_control_kw)*||p_candidate-p_anchor||_1 <= 0"


def test_07_b1_anchor() -> None:
    assert j("V32_NOMINAL_CURRENT_CONSTRAINT_AUDIT.json")["B1_anchor"].startswith("B0")


def test_08_b3_anchor() -> None:
    assert j("V32_NOMINAL_CURRENT_CONSTRAINT_AUDIT.json")["B3_anchor"].startswith("B2")


def test_09_no_april_rows() -> None:
    assert all(r["day"] < "2025-04-01" and int(r["April_rows_used"]) == 0 for r in rows("V32_PREAPRIL_PLANNING_FRONTIER_CENSUS.csv"))


def test_10_resource_retains_non_grid_constraints() -> None:
    kept = j("V32_FRONTIER_DEFINITION_CONTRACT.json")["frontiers"]["F_RESOURCE"]["non_grid_constraints_retained"]
    assert len(kept) == 10 and "rack capacity" in kept and "causal information" in kept


def test_11_plan_margin_zero() -> None:
    assert j("V32_FRONTIER_DEFINITION_CONTRACT.json")["frontiers"]["F_PLAN"]["M_pu"] == 0.0


def test_12_plan_envelope_retained() -> None:
    assert j("V32_FRONTIER_DEFINITION_CONTRACT.json")["frontiers"]["F_PLAN"]["nominal_envelope_retained"] is True


def test_13_fresh_policy_exact_geometry() -> None:
    assert "same-slot scalar anchor-relative" in j("V32_FRONTIER_DEFINITION_CONTRACT.json")["frontiers"]["F_AC_POLICY"]["geometry"]


def test_14_trajectory_rho_max() -> None:
    assert "rho_max_AC" in j("V32_FRONTIER_DEFINITION_CONTRACT.json")["frontiers"]["F_AC_TRAJECTORY"]["geometry"]


def test_15_physical_limits_frozen() -> None:
    limits = j("V32_FRONTIER_DEFINITION_CONTRACT.json")["frontiers"]["F_AC_PHYSICAL"]["limits"]
    assert len(limits) == 5 and "line/phase current<=1.0" in limits


def test_16_audit_freeze_before_fresh() -> None:
    value = j("V32_FRESH_FRONTIER_AUDIT_SET_FREEZE.json")
    assert value["freeze_precedes_Fresh"] is True and value["Fresh_solve_count_at_freeze"] == 0


def test_17_selection_planning_only() -> None:
    assert j("V32_FRESH_FRONTIER_AUDIT_SET_FREEZE.json")["planning_side_only"] is True


def test_18_direction_freeze_before_fresh() -> None:
    value = j("V32_FRONTIER_DIRECTION_AUDIT.json")
    assert value["freeze_precedes_Fresh"] is True and value["Fresh_solve_count_at_freeze"] == 0


@pytest.mark.parametrize("constraint", ["nonnegativity", "DA authorization", "source availability", "rack capacity", "compatibility", "same-slot rule"])
def test_19_interpolation_contract(constraint: str) -> None:
    assert constraint in j("V32_FRONTIER_DEFINITION_CONTRACT.json")["interpolation_constraints_to_verify"]


@pytest.mark.parametrize("rule", ["no preemption", "no running-job migration", "same-slot DA authorization", "strict FULL eligibility", "backlog conservation", "rack capacity", "causal information"])
def test_20_resource_rules(rule: str) -> None:
    assert rule in j("V32_FRONTIER_DEFINITION_CONTRACT.json")["frontiers"]["F_RESOURCE"]["non_grid_constraints_retained"]


def test_21_fresh_ex_post_only() -> None:
    assert j("V32_FRONTIER_DEFINITION_CONTRACT.json")["Fresh_ex_post_only"] is True


def test_22_initial_grid_exact() -> None:
    assert j("V32_FRONTIER_DEFINITION_CONTRACT.json")["initial_lambda_grid"] == [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def test_23_refinement_rule_frozen() -> None:
    assert j("V32_FRONTIER_DEFINITION_CONTRACT.json")["adaptive_refinement_stop"] == "lambda_interval<=0.005 OR incremental_service_interval<=0.01_nodeh"


def test_24_nonmonotonic_handling() -> None:
    assert "every feasible/infeasible transition" in j("V32_FRONTIER_DEFINITION_CONTRACT.json")["nonmonotonic_rule"]


def test_25_decomposition_definitions() -> None:
    assert set(j("V32_FRONTIER_GAP_DECOMPOSITION.json")["definitions"]) == {"SURROGATE", "POLICY", "NOREGRET", "PHYSICAL"}


def test_26_constraint_not_absolute_or_branchwise() -> None:
    value = j("V32_NOMINAL_CURRENT_CONSTRAINT_AUDIT.json")
    assert value["absolute_feeder_rating_constraint"] is False and value["branch_phase_constraints_individually"] is False


def test_27_same_slot_scalar() -> None:
    value = j("V32_NOMINAL_CURRENT_CONSTRAINT_AUDIT.json")
    assert value["same_slot"] is True and value["slot_max"] is False and value["whole_day_max"] is False


def test_28_physical_semantics_unchanged() -> None:
    assert "frozen source/regulator/capacitor semantics" in j("V32_FRONTIER_DEFINITION_CONTRACT.json")["frontiers"]["F_AC_PHYSICAL"]["limits"]


def test_29_no_parameter_change() -> None:
    assert not any(j("V32_FINAL_CURRENT_FRONTIER_REVIEW.json")["parameter_changes"].values())


def test_30_preservation_manifest() -> None:
    value = j("V32_PRECHANGE_PRESERVATION_MANIFEST.json")
    assert value["status"] == "PASS" and value["protected_mismatch_count"] == 0 and len(value["protected_git_trees"]) == 6


def test_31_census_complete() -> None:
    data = rows("V32_PREAPRIL_PLANNING_FRONTIER_CENSUS.csv")
    assert len(data) == 90 * 2 * 96 and {r["case"] for r in data} == {"B1", "B3"}


def test_32_unavailable_not_encoded_as_zero() -> None:
    data = rows("V32_PREAPRIL_PLANNING_FRONTIER_CENSUS.csv")
    assert all(r["analysis_status"] == BLOCKER and r["S_PLAN_nodeh"] == "" and r["S_RESOURCE_nodeh"] == "" for r in data)


def test_33_missing_authority_counts() -> None:
    missing = j("V32_FRONTIER_DEFINITION_CONTRACT.json")["source_authority_inventory"]["required_missing_day_counts"]
    assert all(value == 90 for value in missing.values())


def test_34_empty_set_sha_consistent() -> None:
    assert j("V32_FRESH_FRONTIER_AUDIT_SET_FREEZE.json")["audit_set_sha256"] == j("V32_FRONTIER_DIRECTION_SHA256.json")["direction_set_sha256"]


def test_35_zero_fresh_solves() -> None:
    value = j("V32_FRESH_SOLVE_AUDIT.json")
    assert value["total_Fresh_slot_solves"] == value["trajectory_level_Fresh_solves"] == value["failed_or_nonconverged_solves"] == 0


def test_36_required_not_run_zero_contract() -> None:
    assert not (OUT / "V32_TEST_REPORT.json").exists() or j("V32_TEST_REPORT.json")["not_run"] == 0


def test_37_unresolved_classification() -> None:
    assert j("V32_FINAL_CURRENT_FRONTIER_REVIEW.json")["RESULT_CLASSIFICATION"] == "V32_CURRENT_FRONTIER_ROOT_CAUSE_UNRESOLVED"


def test_38_no_production_change_authorized() -> None:
    assert j("V32_FINAL_CURRENT_FRONTIER_REVIEW.json")["production_change_authorized"] is False


def test_39_diagnostics_non_authority() -> None:
    assert set(j("V32_FINAL_CURRENT_FRONTIER_REVIEW.json")["diagnostics"].values()) == {"NON_AUTHORITY_DIAGNOSTIC_ONLY"}


def test_40_numeric_results_null() -> None:
    review = j("V32_FINAL_CURRENT_FRONTIER_REVIEW.json")
    assert review["numeric_frontier_results_available"] is False
    assert all(value is None for case in review["frontier_means"].values() for value in case.values())


def test_41_artifact_namespace_complete() -> None:
    required = {
        "README.md", "V32_STARTING_AUTHORITY_AUDIT.json", "V32_PRECHANGE_PRESERVATION_MANIFEST.json",
        "V32_NOMINAL_CURRENT_CONSTRAINT_AUDIT.json", "V32_NOMINAL_CURRENT_CONSTRAINT_EQUATIONS.md",
        "V32_FRONTIER_DEFINITION_CONTRACT.json", "V32_PREAPRIL_PLANNING_FRONTIER_CENSUS.csv",
        "V32_FRESH_FRONTIER_AUDIT_SET.csv", "V32_FRESH_FRONTIER_AUDIT_SET_FREEZE.json",
        "V32_FRONTIER_DIRECTION_AUDIT.json", "V32_FRONTIER_DIRECTION_SHA256.json",
        "V32_PLAN_DIRECTIONAL_FRONTIER.csv", "V32_FRESH_AC_FRONTIER_RESULTS.csv",
        "V32_FRESH_AC_FRONTIER_SUMMARY.json", "V32_NOREGRET_GEOMETRY_COST.csv",
        "V32_NOREGRET_GEOMETRY_REVIEW.json", "V32_FRONTIER_GAP_STATISTICS.csv",
        "V32_FRONTIER_GAP_DECOMPOSITION.json", "V32_GRID_LEVERAGE_FRONTIER_REVIEW.csv",
        "V32_HEADROOM_FRONTIER_CONNECTION.csv", "V32_FRESH_SOLVE_AUDIT.json",
        "V32_FINAL_CURRENT_FRONTIER_REVIEW.json", "V32_FINAL_CURRENT_FRONTIER_REVIEW.md",
    }
    assert required <= {p.name for p in OUT.iterdir()}


def test_42_fresh_results_empty() -> None:
    assert rows("V32_FRESH_AC_FRONTIER_RESULTS.csv") == []
