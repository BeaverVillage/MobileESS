from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from dayahead.v30.contracts import CASE_ACTUATORS, OFFICIAL_CASES
from dayahead.v32r2.dependency_audit import (
    BRANCH, CLASSES, K, M_CURRENT, SCENARIO_SHA, STARTING_HEAD, V30_TREE,
)


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v32r2_minimal_frontier_dependency_audit"


def j(name: str) -> dict[str, object]:
    value = json.loads((OUT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_starting_authority_exact() -> None:
    value = j("V32R2_STARTING_AUTHORITY_AUDIT.json")
    assert value["status"] == "PASS"
    assert value["verified_starting_SHA"] == STARTING_HEAD
    assert value["branch"] == BRANCH


def test_v30_production_tree_identity() -> None:
    value = j("V32R2_STARTING_AUTHORITY_AUDIT.json")
    assert value["V30_expected_tree"] == value["V30_observed_tree"] == V30_TREE
    assert value["V30_production_tree_identity"] is True


def test_official_cases_are_exactly_four() -> None:
    value = j("V32R2_FINAL_DEPENDENCY_REVIEW.json")
    assert tuple(value["official_cases"]) == OFFICIAL_CASES == ("B0", "B1", "B2", "B3")
    assert value["official_case_count"] == 4
    assert set(CASE_ACTUATORS) == set(OFFICIAL_CASES)


def test_no_production_science_change() -> None:
    value = j("V32R2_POSTCHANGE_PRESERVATION_AUDIT.json")
    assert value["status"] == "PASS"
    assert value["protected_mismatch_count"] == 0
    assert value["production_science_changes"] == []
    assert value["V30_tree_identity"] is True


def test_static_graph_is_complete_and_separated() -> None:
    value = j("V32R2_STATIC_DEPENDENCY_GRAPH.json")
    assert value["status"] == "PASS" and value["paths_separated"] is True
    assert value["dependency_count"] == len(value["dependencies"]) >= 20
    paths = {row["frontier_paths"] for row in value["dependencies"]}
    assert any("B1/B0" in path for path in paths)
    assert any("B3/B2" in path for path in paths)


def test_every_static_dependency_has_exactly_one_allowed_class() -> None:
    value = j("V32R2_STATIC_DEPENDENCY_GRAPH.json")
    for row in value["dependencies"]:
        assert row["classification"] in CLASSES
        assert isinstance(row["classification"], str)


def test_dynamic_read_trace_is_read_only_and_on_declared_dates() -> None:
    value = j("V32R2_DYNAMIC_READ_SUMMARY.json")
    ledger = rows("V32R2_DYNAMIC_READ_LEDGER.csv")
    assert value["status"] == "PASS_READ_ONLY"
    assert value["proof_days"] == ["2025-01-15", "2025-02-15", "2025-03-15"]
    assert value["substitutions"] == []
    assert value["file_mutations"] == value["optimization_calls"] == value["Fresh_calls"] == 0
    assert value["ledger_row_count"] == len(ledger) > 0
    assert {row["case_path"] for row in ledger} == {"B1/B0", "B3/B2"}


@pytest.mark.parametrize("path", ["B1/B0", "B3/B2"])
def test_scats_actual_is_not_read_by_frontier(path: str) -> None:
    value = j("V32R2_FEB28_SCATS_DEPENDENCY_AUDIT.json")
    assert value[path.replace("/", "_") + "_realized_SCATS_read"] is False
    assert value["functions_reading_actual_volume_on_frontier_path"] == []
    assert value["exact_numerical_quantity_affected"] is None


@pytest.mark.parametrize(
    "effect",
    ["MESS_route", "MESS_location", "MESS_availability", "travel_energy", "AIDC_recourse", "feeder_injection", "Fresh_trajectory"],
)
def test_scats_actual_affects_no_numerical_frontier_quantity(effect: str) -> None:
    assert j("V32R2_FEB28_SCATS_DEPENDENCY_AUDIT.json")["effects"][effect] is False


def test_feb28_scats_class_and_readiness() -> None:
    value = j("V32R2_FEB28_SCATS_DEPENDENCY_AUDIT.json")
    assert value["final_classification"] == "DIAGNOSTIC_ONLY"
    assert value["V32_frontier_classification"] == "NOT_REQUIRED_BY_V32_FRONTIER"
    assert value["frontier_source_ready"] == {"B1_B0": True, "B3_B2": True}
    assert value["replacement_downloaded"] is value["interpolated"] is value["synthesized"] is False


def test_no_scats_replacement_code_or_artifact() -> None:
    text = (REPO / "dayahead/v32r2/dependency_audit.py").read_text(encoding="utf-8")
    assert "requests.get" not in text and "urlopen(" not in text and "np.interp(" not in text
    assert not list(OUT.glob("*FEB28*REPLACEMENT*"))


def test_b1_b0_mess_is_common_fixed_physical_dependency() -> None:
    value = j("V32R2_MESS_DEPENDENCY_AUDIT.json")["B1_B0"]
    assert value["controllable_MESS"] is False
    assert value["separate_case_schedule_required"] is False
    assert value["fixed_reference_injection_remains"] is True
    assert value["candidate_anchor_identical"] is True


def test_b3_b2_mess_trajectories_are_distinct_authority_objects() -> None:
    value = j("V32R2_MESS_DEPENDENCY_AUDIT.json")["B3_B2"]
    assert value["trajectories_can_differ"] is True
    assert value["both_P_Q_trajectories_required"] is True
    assert "solve_case(B2)" == value["B2_producer"]
    assert "select_first_safe_rung" in value["B3_producer"]


def test_mess_general_day_rule_is_already_frozen() -> None:
    value = j("V32R2_MESS_DEPENDENCY_AUDIT.json")
    assert value["classification"] == "MESS_GENERAL_DAY_RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY"
    assert value["new_MESS_scientific_rule_required"] is False
    assert value["policy_invented"] is value["route_changed"] is value["ratings_changed"] is False


def test_no_new_mess_policy_was_added() -> None:
    assert not (REPO / "dayahead/v32r2/mess_policy.py").exists()
    assert j("V32R2_FINAL_DEPENDENCY_REVIEW.json")["new_MESS_rules"] == 0


def test_stage1_loader_is_distinguished_from_solver() -> None:
    data = {row["entry_point"]: row for row in rows("V32R2_GENERAL_DAY_STAGE1_AUDIT.csv")}
    loader = data["dayahead.v30.dayahead_formulation.load_frozen_schedules"]
    assert loader["kind"] == "APR04_SCHEDULE_LOADER"
    assert loader["reads_Apr04"] == "YES" and loader["fresh_optimization"] == "NO"
    primitive = data["dayahead.v29r2.apr04_runner.solve_case"]
    assert primitive["kind"] == "GENERIC_LOWER_LEVEL_OPTIMIZATION_PRIMITIVE"
    assert primitive["reads_Apr04"] == "NO" and primitive["produces_x_DA"] == "YES_IN_PAYLOAD"


def test_no_genuine_v30_arbitrary_day_entry_point_but_primitives_exist() -> None:
    value = j("V32R2_GENERAL_DAY_STAGE1_REVIEW.json")
    assert value["genuine_arbitrary_day_V30_entry_point_exists"] is False
    assert value["exact_V30_entry_point"] is None
    assert value["lower_level_arbitrary_day_primitives_exist"] is True
    assert value["gap_classification"] == "SCIENCE_NEUTRAL_ENGINEERING"


def test_stage1_k64_role_is_not_misstated() -> None:
    value = j("V32R2_GENERAL_DAY_STAGE1_REVIEW.json")
    assert value["uses_K64_to_change_x_DA"] is False
    assert value["depends_on_Apr04_schedules_in_current_V30_loader"] is True
    start = j("V32R2_STARTING_AUTHORITY_AUDIT.json")
    assert start["K"] == K == 64 and start["scenario_set_sha256"] == SCENARIO_SHA


def test_hrec_is_derived_not_endogenous() -> None:
    value = j("V32R2_HREC_ENDOGENEITY_AUDIT.json")
    assert value["classification"] == "DERIVED_POST_SOLVE"
    assert value["solver_variable_declaration"] is None
    assert value["objective_participation"] is value["constraint_participation"] is False
    assert value["scenario_coupling"] is value["solver_output_extraction"] is False
    assert "max(0" in value["exact_relationship"]


def test_frozen_margin_is_unchanged() -> None:
    assert j("V32R2_STARTING_AUTHORITY_AUDIT.json")["M_CURRENT_pu"] == M_CURRENT


def test_scalar_s_is_the_minimum_sensitivity_authority() -> None:
    value = j("V32R2_SENSITIVITY_MINIMUM_AUTHORITY_AUDIT.json")
    assert value["full_line_phase_cache_required"] is False
    assert value["frozen_scalar_s_sufficient"] is True
    assert value["minimum_object"]["shape_per_day"] == [96, 12]
    assert value["operation_requiring_full_S_tensor"] is None
    assert value["classification"] == "FULL_SENSITIVITY_CACHE_NOT_REQUIRED"


@pytest.mark.parametrize(
    "operation",
    ["frontier-eligible slot identification", "AIDC leverage ranking", "leverage quartiles", "audit-set freeze", "candidate direction", "S_PLAN", "S_AC_POLICY"],
)
def test_scalar_s_supports_every_planning_side_operation(operation: str) -> None:
    value = j("V32R2_SENSITIVITY_MINIMUM_AUTHORITY_AUDIT.json")
    assert operation in value["V32_operations_supported"]


def test_minimum_schema_keeps_paths_separate() -> None:
    value = j("V32R2_MINIMUM_FRONTIER_AUTHORITY_SCHEMA.json")
    assert set(value) >= {"B1_B0", "B3_B2", "shared_reduction", "explicitly_excluded"}
    b10 = value["B1_B0"]["required_fields"]
    b32 = value["B3_B2"]["required_fields"]
    assert "one_common_fixed_MESS_P_Q[96,4]" in b10
    assert "B2_MESS_P_Q[96,4]" in b32 and "B3_MESS_P_Q[96,4]" in b32
    assert "B2_MESS_P_Q[96,4]" not in b10


def test_schema_excludes_unproven_or_derived_payloads() -> None:
    excluded = j("V32R2_MINIMUM_FRONTIER_AUTHORITY_SCHEMA.json")["explicitly_excluded"]
    assert excluded["SCATS_actual"] == "DIAGNOSTIC_ONLY"
    assert excluded["SCATS_forecast"] == "NOT_REQUIRED"
    assert "scalar s" in excluded["full_line_phase_sensitivity_cache"]
    assert excluded["materialized_h_REC"] == "exactly derived"


def test_shared_reference_reduces_four_to_three_workload_tensors() -> None:
    value = j("V32R2_MINIMUM_FRONTIER_AUTHORITY_SCHEMA.json")
    assert "three workload tensors" in value["shared_reduction"]
    assert "B0 and B2" in value["shared_reduction"]


def test_minimal_source_recensus_has_exactly_90_days() -> None:
    data = rows("V32R2_MINIMAL_SOURCE_COVERAGE.csv")
    assert len(data) == 90
    assert data[0]["day"] == "2025-01-01" and data[-1]["day"] == "2025-03-31"
    assert len({row["day"] for row in data}) == 90


@pytest.mark.parametrize("column", ["B1_B0_FRONTIER_SOURCE_READY", "B3_B2_FRONTIER_SOURCE_READY"])
def test_all_90_days_are_frontier_source_ready(column: str) -> None:
    assert all(row[column] == "True" for row in rows("V32R2_MINIMAL_SOURCE_COVERAGE.csv"))


def test_missing_not_required_does_not_fail_source_readiness() -> None:
    feb = next(row for row in rows("V32R2_MINIMAL_SOURCE_COVERAGE.csv") if row["day"] == "2025-02-28")
    assert feb["SCATS_actual"] == "DIAGNOSTIC_MISSING"
    assert feb["SCATS_forecast"] == "MISSING_NOT_REQUIRED"
    assert feb["missing_required_count"] == "0"
    assert feb["B1_B0_FRONTIER_SOURCE_READY"] == feb["B3_B2_FRONTIER_SOURCE_READY"] == "True"


def test_coverage_summary_separates_source_from_operational_authority() -> None:
    value = j("V32R2_MINIMAL_SOURCE_COVERAGE_SUMMARY.json")
    assert value["B1_B0_frontier_source_ready_days"] == value["B3_B2_frontier_source_ready_days"] == 90
    assert value["remaining_required_source_missing_days"] == []
    assert value["remaining_diagnostic_only_missing_days"] == ["2025-02-28"]
    assert value["operational_authority_materialized"] is False


@pytest.mark.parametrize("case", ["B0", "B1", "B2", "B3"])
def test_each_general_day_xda_is_reconstructable(case: str) -> None:
    data = {row["object"]: row for row in rows("V32R2_RECONSTRUCTABILITY_AUDIT.csv")}
    value = data[f"{case} x_DA"]
    assert value["classification"] == "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY"
    assert value["new_scientific_choice"] == "NO"


@pytest.mark.parametrize(
    "name",
    ["B1 causal Stage-2 resources", "B3 causal Stage-2 resources", "B0 anchor electrical trajectory", "B2 anchor electrical trajectory", "B1 candidate electrical trajectory", "B3 candidate electrical trajectory", "V30 scalar s"],
)
def test_operational_object_reconstructability(name: str) -> None:
    data = {row["object"]: row for row in rows("V32R2_RECONSTRUCTABILITY_AUDIT.csv")}
    assert data[name]["classification"] == "RECONSTRUCTABLE_FROM_FROZEN_AUTHORITY"
    assert data[name]["new_scientific_choice"] == "NO"


def test_no_general_day_or_frontier_proof_run_was_smuggled_in() -> None:
    review = j("V32R2_RECONSTRUCTABILITY_REVIEW.json")
    final = j("V32R2_FINAL_DEPENDENCY_REVIEW.json")
    assert review["full_JanMar_materialization_performed"] is False
    assert review["proof_dates_optimized"] == 0
    assert final["Fresh_frontier_calls"] == final["full_campaign_runs"] == 0


def test_gaps_are_science_neutral_or_non_gap() -> None:
    value = j("V32R2_GAP_CLASSIFICATION.json")
    assert value["new_scientific_authority_required"] is False
    assert value["production_change_authorized"] is False
    assert {row["classification"] for row in value["gaps"]} <= {"SCIENCE_NEUTRAL_ENGINEERING", "NO_FRONTIER_GAP_DIAGNOSTIC_ONLY"}


def test_final_classification_and_one_action() -> None:
    value = j("V32R2_FINAL_DEPENDENCY_REVIEW.json")
    assert value["RESULT_CLASSIFICATION"] == "V32R2_MINIMAL_AUTHORITY_RECONSTRUCTABLE"
    assert isinstance(value["one_next_recommended_action"], str)
    assert value["one_next_recommended_action"].startswith("Implement science-neutral")


def test_prohibitions_are_all_respected() -> None:
    value = j("V32R2_FINAL_DEPENDENCY_REVIEW.json")
    assert value["production_science_changed"] is False
    assert value["source_downloads"] == 0
    assert value["SCATS_interpolations_or_synthesis"] == 0
    assert value["new_MESS_rules"] == 0


def test_no_april_evidence_drives_scientific_choice() -> None:
    assert j("V32R2_STARTING_AUTHORITY_AUDIT.json")["April_evidence_used_for_scientific_choice"] is False


def test_push_and_merge_are_absent() -> None:
    value = j("V32R2_STARTING_AUTHORITY_AUDIT.json")
    assert value["push_performed"] is value["merge_performed"] is False


def test_required_artifact_set_is_complete() -> None:
    required = {
        "README.md", "V32R2_STARTING_AUTHORITY_AUDIT.json", "V32R2_PRECHANGE_PRESERVATION_MANIFEST.json",
        "V32R2_STATIC_DEPENDENCY_GRAPH.json", "V32R2_STATIC_DEPENDENCY_GRAPH.md",
        "V32R2_DYNAMIC_READ_LEDGER.csv", "V32R2_DYNAMIC_READ_SUMMARY.json",
        "V32R2_FEB28_SCATS_DEPENDENCY_AUDIT.json", "V32R2_MESS_DEPENDENCY_AUDIT.json",
        "V32R2_GENERAL_DAY_STAGE1_AUDIT.csv", "V32R2_GENERAL_DAY_STAGE1_REVIEW.json",
        "V32R2_HREC_ENDOGENEITY_AUDIT.json", "V32R2_SENSITIVITY_MINIMUM_AUTHORITY_AUDIT.json",
        "V32R2_MINIMUM_FRONTIER_AUTHORITY_SCHEMA.json", "V32R2_MINIMAL_SOURCE_COVERAGE.csv",
        "V32R2_MINIMAL_SOURCE_COVERAGE_SUMMARY.json", "V32R2_RECONSTRUCTABILITY_AUDIT.csv",
        "V32R2_RECONSTRUCTABILITY_REVIEW.json", "V32R2_GAP_CLASSIFICATION.json",
        "V32R2_FINAL_DEPENDENCY_REVIEW.json", "V32R2_FINAL_DEPENDENCY_REVIEW.md",
        "V32R2_TEST_REPORT.json", "V32R2_POSTCHANGE_PRESERVATION_AUDIT.json",
        "V32R2_ARTIFACT_SHA256.json",
    }
    assert {path.name for path in OUT.iterdir() if path.is_file()} == required


def test_artifact_manifest_hashes_every_payload_file() -> None:
    manifest = j("V32R2_ARTIFACT_SHA256.json")
    assert manifest["status"] == "PASS" and manifest["file_count"] == 23
    assert {row["path"] for row in manifest["files"]} == {path.name for path in OUT.iterdir() if path.is_file() and path.name != "V32R2_ARTIFACT_SHA256.json"}
    for row in manifest["files"]:
        assert hashlib.sha256((OUT / row["path"]).read_bytes()).hexdigest() == row["sha256"]


def test_test_report_has_no_required_not_run() -> None:
    value = j("V32R2_TEST_REPORT.json")
    assert value["status"] == "PASS"
    assert value["failed"] == value["not_run"] == value["required_NOT_RUN"] == 0
