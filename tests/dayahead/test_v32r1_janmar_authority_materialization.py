"""V32R1 Phase-I fail-closed and protected-history gates."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v32r1_janmar_v30_authority"
FRONTIER = ROOT / "dayahead/artifacts/v32r1_preapril_current_frontier_freshac"


def j(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_01_exact_v32_starting_head() -> None:
    assert j("V32R1_STARTING_AUTHORITY_AUDIT.json")["verified_starting_SHA"] == "e604d8f41e6207fa2881dd06ba944bd5479cd228"


def test_02_selected_base_sha() -> None:
    assert j("V32R1_STARTING_AUTHORITY_AUDIT.json")["selected_base_SHA"] == "e604d8f41e6207fa2881dd06ba944bd5479cd228"


def test_03_v32_manifest_preserved() -> None:
    assert j("V32R1_STARTING_AUTHORITY_AUDIT.json")["V32_manifest_sha256"] == "9462b2b46d151a0084817172d20d49e53c04c8f02a18b98384a7b56fe4aaa95d"


def test_04_v30_tree_identity() -> None:
    value = j("V32R1_V30_PRODUCTION_TREE_IDENTITY.json")
    assert value["status"] == "PASS" and value["byte_tree_identical"] is True


def test_05_official_cases_exact() -> None:
    assert j("V32R1_STARTING_AUTHORITY_AUDIT.json")["official_cases"] == ["B0", "B1", "B2", "B3"]


def test_06_no_fifth_case() -> None:
    assert j("V32R1_STARTING_AUTHORITY_AUDIT.json")["official_case_count"] == 4


def test_07_calendar_is_90_days() -> None:
    data = rows("V32R1_JANMAR_SOURCE_CENSUS.csv")
    assert len(data) == 90 and data[0]["day"] == "2025-01-01" and data[-1]["day"] == "2025-03-31"


def test_08_slots_per_day_contract() -> None:
    assert "slot=96" in j("V32R1_STAGE2_CAUSAL_RESOURCE_SCHEMA.json")["axes"]


def test_09_source_census_fails_closed() -> None:
    value = j("V32R1_JANMAR_SOURCE_MANIFEST.json")
    assert value["status"] == "FAIL" and value["complete_day_count"] == 89


def test_10_exact_missing_source_day() -> None:
    bad = [row for row in rows("V32R1_JANMAR_SOURCE_CENSUS.csv") if row["classification"] != "COMPLETE"]
    assert len(bad) == 1 and bad[0]["day"] == "2025-02-28" and bad[0]["traffic_mobility"] == "MISSING_REALIZED_TRAFFIC"


def test_11_source_not_inferred_from_filename() -> None:
    data = rows("V32R1_JANMAR_SOURCE_CENSUS.csv")
    assert all(row["semantic_shape_validation"] == "True" and row["hash_identity"] == "True" for row in data)


def test_12_raw_hashes_match_frozen_preflight() -> None:
    value = j("V32R1_JANMAR_SOURCE_MANIFEST.json")
    assert value["all_raw_hashes_match_frozen_preflight"] is True and value["raw_authority_hash_count"] == 12


@pytest.mark.parametrize("case", ["B0", "B1", "B2", "B3"])
def test_13_da_not_materialized_after_source_gate(case: str) -> None:
    selected = [row for row in rows("V32R1_DA_SCHEDULE_COVERAGE.csv") if row["case"] == case]
    assert len(selected) == 90 and all(row["status"] == "NOT_MATERIALIZED" for row in selected)


def test_14_b0_b2_identity_not_fabricated() -> None:
    value = j("V32R1_B0_B2_REFERENCE_IDENTITY.json")
    assert value["status"] == "NOT_EVALUATED_PHASE_I_BLOCKED" and value["day_coverage"] == 0


def test_15_b1_b3_contract_identity_only() -> None:
    value = j("V32R1_B1_B3_AIDC_POLICY_IDENTITY.json")
    assert value["B1_policy_sha256"] == value["B3_policy_sha256"] and value["operational_day_coverage"] == 0


def test_16_b1_stage2_not_run() -> None:
    value = j("V32R1_STAGE2_CAUSAL_RESOURCE_MANIFEST.json")
    assert value["B1_day_coverage"] == 0 and value["B1_epochs"] == 0


def test_17_b3_stage2_not_run() -> None:
    value = j("V32R1_STAGE2_CAUSAL_RESOURCE_MANIFEST.json")
    assert value["B3_day_coverage"] == 0 and value["B3_epochs"] == 0


def test_18_future_reads_zero() -> None:
    assert j("V32R1_CAUSAL_READ_AUDIT.json")["future_Actual_reads"] == 0


@pytest.mark.parametrize("field,expected", [("strict_FULL_only", True), ("PARTIAL_shared_controllable", False), ("preemption", False), ("running_job_migration", False), ("same_slot_only", True), ("hidden_creation_or_deletion", False)])
def test_19_workload_contract_frozen(field: str, expected: bool) -> None:
    assert j("V32R1_MASS_CONSERVATION_AUDIT.json")[field] is expected


def test_20_mass_not_fabricated() -> None:
    value = j("V32R1_MASS_CONSERVATION_AUDIT.json")
    assert value["status"] == "NOT_EVALUATED_PHASE_I_BLOCKED" and value["maximum_workload_mass_error_nodeh"] is None


@pytest.mark.parametrize("case", ["B2", "B3"])
def test_21_mess_not_materialized(case: str) -> None:
    value = j("V32R1_MESS_TRAJECTORY_MANIFEST.json")
    assert value[f"{case}_day_coverage"] == 0 and value["Actual_MESS_reoptimization_calls"] == 0


def test_22_sensitivity_not_materialized() -> None:
    value = j("V32R1_CURRENT_SENSITIVITY_MANIFEST.json")
    assert value["day_coverage"] == 0 and value["aggregate_sha256"] is None


def test_23_sensitivity_compatibility_not_claimed() -> None:
    value = j("V32R1_CURRENT_SENSITIVITY_COMPATIBILITY_AUDIT.json")
    assert value["status"] == "NOT_EVALUATED_REQUIRED_V30_S_VECTOR_UNAVAILABLE" and value["compatible_day_slot_count"] == 0


def test_24_no_fresh_before_freeze() -> None:
    assert j("V32R1_CAUSAL_READ_AUDIT.json")["Fresh_frontier_calls"] == 0


def test_25_no_april_or_may() -> None:
    start = j("V32R1_STARTING_AUTHORITY_AUDIT.json")
    assert start["April_rows_used"] == 0 and start["May_rows_used"] == 0


def test_26_k_and_scenario_set_frozen() -> None:
    value = j("V32R1_STARTING_AUTHORITY_AUDIT.json")
    assert value["K"] == 64 and value["scenario_set_sha256"] == "02e29c64c8fa662c78bf88e43c10a6508efc0bb5669f9ffe6d33c798a887d2b0"


def test_27_margin_frozen() -> None:
    assert j("V32R1_STARTING_AUTHORITY_AUDIT.json")["M_CURRENT_pu"] == 0.0009917274479849247


def test_28_coverage_fails_closed() -> None:
    value = j("V32R1_AUTHORITY_COVERAGE_AUDIT.json")
    assert value["status"] == "FAIL_CLOSED_INCOMPLETE" and value["source_days"] == 89


@pytest.mark.parametrize("field", ["B0_DA_days", "B1_DA_days", "B2_DA_days", "B3_DA_days", "B0_Actual_anchor_days", "B1_Stage2_days", "B2_Actual_anchor_days", "B3_Stage2_days", "B2_MESS_days", "B3_MESS_days", "planning_sensitivity_days"])
def test_29_downstream_coverage_zero(field: str) -> None:
    assert j("V32R1_AUTHORITY_COVERAGE_AUDIT.json")[field] == 0


def test_30_authority_not_frozen() -> None:
    value = j("V32R1_JANMAR_AUTHORITY_FREEZE.json")
    assert value["status"] == "FAIL_CLOSED_NOT_FROZEN" and value["freeze_pass"] is False and value["complete_authority_aggregate_sha256"] is None


def test_31_frontier_not_authorized() -> None:
    assert j("V32R1_JANMAR_AUTHORITY_FREEZE.json")["frontier_phase_authorized"] is False


def test_32_frontier_namespace_absent() -> None:
    assert not FRONTIER.exists()


def test_33_v30_general_day_gap_documented() -> None:
    evidence = j("V32R1_AUTHORITY_COVERAGE_AUDIT.json")["code_evidence"]
    assert "Apr-04" in evidence["loader_scope"] and "does not solve a general-day" in evidence["V30_stage1_behavior"]


def test_34_no_production_change() -> None:
    assert j("V32R1_FINAL_REVIEW.json")["production_V30_changed"] is False


def test_35_blocked_classification() -> None:
    assert j("V32R1_FINAL_REVIEW.json")["RESULT_CLASSIFICATION"] == "V32R1_JANMAR_AUTHORITY_MATERIALIZATION_BLOCKED"


def test_36_required_not_run_zero_contract() -> None:
    assert not (OUT / "V32R1_TEST_REPORT.json").exists() or j("V32R1_TEST_REPORT.json")["not_run"] == 0


def test_37_prechange_history_manifest() -> None:
    value = j("V32R1_PRECHANGE_PRESERVATION_MANIFEST.json")
    assert value["status"] == "PASS" and value["protected_mismatch_count"] == 0 and len(value["protected_git_trees"]) == 15


def test_38_source_manifest_has_no_april() -> None:
    assert j("V32R1_JANMAR_SOURCE_MANIFEST.json")["April_rows_used"] == 0


def test_39_schedule_rows_exact() -> None:
    assert len(rows("V32R1_DA_SCHEDULE_COVERAGE.csv")) == 90 * 4


def test_40_resource_schema_axes() -> None:
    assert j("V32R1_STAGE2_CAUSAL_RESOURCE_SCHEMA.json")["axes"] == ["day=90", "case=B1/B3", "slot=96", "cohort=15", "rack=48"]


def test_41_sensitivity_schema() -> None:
    value = j("V32R1_CURRENT_SENSITIVITY_SCHEMA.json")
    assert value["shape"][:3] == [90, 96, 12] and value["selection_use"] == "planning-side only before Fresh frontier"


def test_42_primary_blocker_exact() -> None:
    assert j("V32R1_FINAL_REVIEW.json")["primary_blocker"] == "MISSING_REALIZED_TRAFFIC_AUTHORITY_2025-02-28"


def test_43_no_scientific_parameter_changes() -> None:
    assert j("V32R1_FINAL_REVIEW.json")["scientific_parameter_changes"] is False


def test_44_no_operational_authority_mislabel() -> None:
    assert j("V32R1_FINAL_REVIEW.json")["operational_authority_frozen"] is False


def test_45_frontier_never_started() -> None:
    value = j("V32R1_FINAL_REVIEW.json")
    assert value["frontier_phase_started"] is False and value["Fresh_frontier_calls"] == 0
