from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from dayahead.v28r2.backend_contract import canonical_sha256 as backend_sha
from dayahead.v30.contracts import OFFICIAL_CASES
from dayahead.v30.dayahead_formulation import load_frozen_schedules
from dayahead.v33x.contracts import BRANCH, DEVELOPMENT_VARIANTS, STARTING_HEAD, V30_ARTIFACT_SHA, V30_TREE
from dayahead.v33x.full_grid_recourse import HIGHS_THREADS, LEX_GRID_TOL, LEX_SERVICE_TOL


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v33x_fasttrack_grid_deliverable_aidc"


def j(name: str) -> dict[str, object]:
    value = json.loads((OUT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def by_variant_case() -> dict[tuple[str, str], dict[str, str]]:
    return {(row["variant"], row["case"]): row for row in rows("V33X_E0_E1_E2_COMPARISON.csv")}


def test_01_exact_starting_head_and_branch() -> None:
    value = j("V33X_STARTING_AUTHORITY_AUDIT.json")
    assert value["verified_starting_SHA"] == STARTING_HEAD
    assert value["branch"] == BRANCH
    assert value["starting_git_status_clean"] is True
    assert value["starting_head_is_ancestor_of_current"] is True


def test_02_v30_production_tree_identity() -> None:
    value = j("V33X_STARTING_AUTHORITY_AUDIT.json")
    assert value["V30_expected_tree"] == value["V30_observed_tree"] == V30_TREE
    assert value["V30_tree_identity"] is True


def test_03_official_cases_exactly_four() -> None:
    value = j("V33X_STARTING_AUTHORITY_AUDIT.json")
    assert tuple(value["official_cases"]) == OFFICIAL_CASES == ("B0", "B1", "B2", "B3")
    assert value["official_case_count"] == 4


def test_04_development_variants_are_not_cases() -> None:
    value = j("V33X_FINAL_DEVELOPMENT_REVIEW.json")
    assert tuple(DEVELOPMENT_VARIANTS) == ("E0_CURRENT", "E1_FULL_GRID_ENVELOPE", "E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM")
    assert value["development_variants_are_official_cases"] is False
    assert not set(DEVELOPMENT_VARIANTS) & set(OFFICIAL_CASES)


def test_05_e0_byte_sha_reproduction() -> None:
    value = j("V33X_E0_BASELINE_IDENTITY.json")
    assert value["V30_artifact_aggregate_sha256"] == V30_ARTIFACT_SHA
    assert value["byte_SHA_equivalent_to_V30"] is True
    assert value["file_mismatches"] == []


def test_06_e0_stage2_replay_matches_frozen_result() -> None:
    value = j("V33X_E0_BASELINE_IDENTITY.json")
    assert value["E0_stage2_tensor_replay_for_required_headroom_KPI"] is True
    assert value["E0_stage2_replay_matches_frozen_V30"] is True
    assert value["E0_stage2_replay_executed_nodeh"]["B1"] == pytest.approx(59.18816048947252, abs=1e-8)
    assert value["E0_stage2_replay_executed_nodeh"]["B3"] == pytest.approx(62.38843607314548, abs=1e-8)


@pytest.mark.parametrize("case", ["B1", "B3"])
def test_07_e1_da_schedule_is_e0(case: str) -> None:
    schedules = load_frozen_schedules(REPO)
    contract = j("V33X_E1_FORMULATION_CONTRACT.json")
    assert contract["x_DA_identity"] == "x_DA_E1 == x_DA_E0"
    assert j("V33X_E0_BASELINE_IDENTITY.json")["schedule_sha256"][case] == schedules[case]["schedule_sha256"]


@pytest.mark.parametrize("case", ["B1", "B3"])
def test_08_e1_mess_is_frozen_e0(case: str) -> None:
    assert j("V33X_E1_FORMULATION_CONTRACT.json")["MESS_identity"] == "P/Q/route/location/availability E1 == E0"
    source = (REPO / "dayahead/v33x/runner.py").read_text(encoding="utf-8")
    assert 'np.asarray(schedules[case]["controls"]' in source


def test_09_e1_removes_scalar_anchor_constraint() -> None:
    contract = j("V33X_E1_FORMULATION_CONTRACT.json")
    assert contract["removed_hard_constraint"] == "scalar_anchor_relative_s_dot_deltaP_plus_margin_L1_le_0"
    assert contract["new_safety_margin"] is False


@pytest.mark.parametrize("constraint", [
    "V_MIN_SQUARED <= affine_voltage <= V_MAX_SQUARED",
    "all_supported_line_phase_current <= 1.0",
    "all_supported_transformer_phase_current <= 1.0",
    "frozen_transformer_kVA_polygon",
])
def test_10_e1_uses_full_frozen_electrical_constraints(constraint: str) -> None:
    assert constraint in j("V33X_E1_FORMULATION_CONTRACT.json")["electrical_constraints"]


def test_11_full_electrical_authority_is_available() -> None:
    value = j("V33X_FULL_ELECTRICAL_AUTHORITY_AUDIT.json")
    assert value["status"] == "PASS" and value["available"] is True
    assert value["voltage_shape"] == [96, 60, 386]
    assert value["current_shape"] == [96, 60, 383]
    assert value["axis_identity"] is True and value["new_sensitivity_model"] is False


def test_12_e1_absolute_rating_constraints_exist_in_code() -> None:
    source = (REPO / "dayahead/v33x/full_grid_recourse.py").read_text(encoding="utf-8")
    assert "1.0 - i_constant[index]" in source
    assert "V_MAX_SQUARED - constant" in source
    assert "constant - V_MIN_SQUARED" in source
    assert "transformer_ratings" in source


@pytest.mark.parametrize("module", ["dayahead/v33x/full_grid_recourse.py", "dayahead/v33x/headroom_stage1.py"])
def test_13_no_fresh_or_opendss_import_in_decision_modules(module: str) -> None:
    tree = ast.parse((REPO / module).read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
    assert not any("opendss" in name.lower() or "fresh" in name.lower() for name in imports)


@pytest.mark.parametrize("field,expected", [
    ("same_slot_only", True), ("temporal_recourse", False), ("strict_FULL_only", True),
    ("preemption", False), ("running_job_migration", False), ("future_Actual_reads", 0),
])
def test_14_e1_causal_resource_contract(field: str, expected: object) -> None:
    assert j("V33X_E1_FORMULATION_CONTRACT.json")[field] == expected


def test_15_e1_workload_mass_and_capacity() -> None:
    for row in rows("V33X_E1_STAGE2_RESULTS.csv"):
        assert abs(float(row["workload_mass_error_nodeh"])) <= 1e-8
        assert float(row["rack_capacity_blocked_nodeh"]) >= 0
        assert int(row["future_Actual_reads"]) == 0


def test_16_e2_hrec_is_a_real_solver_variable() -> None:
    value = j("V33X_E2_FORMULATION_CONTRACT.json")
    source = (REPO / "dayahead/v33x/headroom_stage1.py").read_text(encoding="utf-8")
    assert value["h_REC"] == "ENDOGENOUS_NONNEGATIVE_STAGE1_SOLVER_VARIABLE"
    assert 'model.addVar(lb=0.0, name=f"v33x_h_REC' in source


def test_17_e2_hrec_capacity_constraint() -> None:
    assert j("V33X_E2_FORMULATION_CONTRACT.json")["capacity_constraint"] == "sum_b x_DA[b,r,t] + h_REC[r,t] <= C_available_DA[r,t]"
    assert "v33x_headroom_capacity" in (REPO / "dayahead/v33x/headroom_stage1.py").read_text(encoding="utf-8")


def test_18_e2_hrec_participates_in_lexicographic_objective() -> None:
    value = j("V33X_E2_FORMULATION_CONTRACT.json")
    assert value["weighted_sum"] is False and value["tunable_lambda"] is None
    assert value["objective_hierarchy"][2] == "MAX_SUM_L_TIMES_H_SITE"


@pytest.mark.parametrize("case", ["B1", "B3"])
def test_19_e2_service_parity(case: str) -> None:
    value = j("V33X_E2_SERVICE_PARITY_AUDIT.json")["cases"][case]
    assert value["pass"] is True
    assert value["maximum_cohort_service_shortfall_nodeh"] <= 1.1e-7
    assert value["terminal_backlog_worsening_max_nodeh"] <= 1.1e-7


def test_20_leverage_map_was_frozen_before_e2_and_fresh() -> None:
    value = j("V33X_E2_LEVERAGE_MAP_SHA256.json")
    assert value["status"] == "FROZEN_BEFORE_E2_AND_FRESH"
    assert value["E2_solved_before_freeze"] is False
    assert value["Fresh_called_before_freeze"] is False
    assert len(value["map_sha256"]) == 64


def test_21_leverage_uses_planning_sensitivity_only() -> None:
    value = j("V33X_E2_LEVERAGE_MAP.json")
    assert value["shape"] == [12, 96]
    assert value["fresh_inputs"] == 0
    assert value["formula"] == "max_over_supported_line_phase(abs(d_normalized_current_loading/d_P_AIDC_i))"
    assert len(value["line_phase_set"]) == value["supported_line_phase_count"]


def test_22_e2_stage2_is_identical_to_e1() -> None:
    value = j("V33X_E2_FORMULATION_CONTRACT.json")
    source = (REPO / "dayahead/v33x/runner.py").read_text(encoding="utf-8")
    assert value["Stage2_contract_identity"] == "EXACTLY_E1_FULL_GRID_RECOURSE"
    assert source.count("solve_causal_day_full_grid(") == 2


@pytest.mark.parametrize("case", ["B1", "B3"])
def test_23_e2_mess_arrays_equal_e0(case: str) -> None:
    e0 = load_frozen_schedules(REPO)[case]
    e2 = j(f"V33X_E2_{case}_DAYAHEAD_SCHEDULE.json")
    assert np.array_equal(np.asarray(e2["mess_p_kw"]), np.asarray(e0["mess_p_kw"]))
    assert np.array_equal(np.asarray(e2["mess_q_kvar"]), np.asarray(e0["mess_q_kvar"]))
    assert e2["mess_route_location"] == e0["mess_route_location"]


@pytest.mark.parametrize("case", ["B1", "B3"])
def test_24_e2_schedule_hash_is_valid(case: str) -> None:
    value = j(f"V33X_E2_{case}_DAYAHEAD_SCHEDULE.json")
    stored = value.pop("schedule_sha256")
    assert backend_sha(value) == stored


def test_25_b0_b2_unchanged_and_fresh_reused_after_identity() -> None:
    value = j("V33X_E0_BASELINE_IDENTITY.json")
    for case in ("B0", "B2"):
        assert value["B0_B2_Fresh_reuse"][case]["identity_verified_before_reuse"] is True
        assert len(value["B0_B2_Fresh_reuse"][case]["reconstructed_immutable_trajectory_sha256"]) == 64


@pytest.mark.parametrize("variant_file", ["V33X_E1_FRESH_OPENDSS_RESULTS.csv", "V33X_E2_FRESH_OPENDSS_RESULTS.csv"])
def test_26_fresh_b1_b3_complete(variant_file: str) -> None:
    value = rows(variant_file)
    assert {row["case"] for row in value} == {"B1", "B3"}
    assert all(int(row["OpenDSS_solve_count"]) == int(row["convergence_count"]) == 96 for row in value)


def test_27_physical_violation_accounting_is_complete() -> None:
    value = by_variant_case()
    for variant in DEVELOPMENT_VARIANTS:
        for case in ("B1", "B3"):
            row = value[(variant, case)]
            total = sum(int(row[field]) for field in (
                "Fresh_voltage_violation_count", "Fresh_line_current_violation_count",
                "Fresh_transformer_current_violation_count", "Fresh_transformer_kva_violation_count",
            ))
            assert (total > 0) == (row["Fresh_physical_violation"].lower() == "true")


def test_28_e1_materially_recovers_service() -> None:
    value = by_variant_case()
    for case in ("B1", "B3"):
        assert float(value[("E1_FULL_GRID_ENVELOPE", case)]["Actual_executed_nodeh"]) > float(value[("E0_CURRENT", case)]["Actual_executed_nodeh"])


def test_29_e2_moves_headroom_to_top_leverage_quartile() -> None:
    value = {(row["variant"], row["case"]): row for row in rows("V33X_HEADROOM_COMPARISON.csv")}
    for case in ("B1", "B3"):
        assert float(value[("E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", case)]["top_quartile_headroom_fraction"]) > float(value[("E0_CURRENT", case)]["top_quartile_headroom_fraction"])


def test_30_e2_b1_does_not_dominate_e1_b1_execution() -> None:
    value = by_variant_case()
    assert float(value[("E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM", "B1")]["Actual_executed_nodeh"]) < float(value[("E1_FULL_GRID_ENVELOPE", "B1")]["Actual_executed_nodeh"])


def test_31_b1_physical_voltage_failure_is_not_hidden() -> None:
    value = by_variant_case()
    for variant in ("E1_FULL_GRID_ENVELOPE", "E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM"):
        row = value[(variant, "B1")]
        assert int(row["Fresh_voltage_violation_count"]) == 4
        assert row["Fresh_physical_violation"].lower() == "true"


def test_32_b3_experimental_trajectories_are_physically_safe() -> None:
    value = by_variant_case()
    for variant in ("E1_FULL_GRID_ENVELOPE", "E2_FULL_GRID_ENVELOPE_PLUS_ENDOGENOUS_HEADROOM"):
        row = value[(variant, "B3")]
        assert row["Fresh_physical_violation"].lower() == "false"
        assert float(row["anchor_relative_Fresh_delta_rho"]) <= 0


def test_33_decision_follows_fail_closed_pareto_rule() -> None:
    value = j("V33X_DEVELOPMENT_CANDIDATE_DECISION.json")
    assert value["E1_valid"] is value["E2_valid"] is False
    assert value["selected_development_candidate"] == "E0_CURRENT"
    assert value["RESULT_CLASSIFICATION"] == "V33X_FASTTRACK_EXPERIMENT_PHYSICAL_SAFETY_FAIL"


@pytest.mark.parametrize("field", ["physical_scale_change", "Fresh_used_as_decision_oracle", "MESS_reoptimized", "continuous_parameters_tuned_on_Apr04", "final_authority", "production_promotion"])
def test_34_forbidden_changes_are_false(field: str) -> None:
    assert j("V33X_DEVELOPMENT_CANDIDATE_DECISION.json")[field] is False


def test_35_april_only_no_janmar_or_may() -> None:
    value = j("V33X_FINAL_DEVELOPMENT_REVIEW.json")
    assert value["April_only"] is True
    assert value["JanMar_used"] is value["May_used"] is False


def test_36_four_thread_contract() -> None:
    start = j("V33X_STARTING_AUTHORITY_AUDIT.json")["resource_contract"]
    assert start == {"Gurobi_Threads": 4, "HiGHS_threads": 4, "Fresh_OpenDSS": "SEQUENTIAL"}
    assert HIGHS_THREADS == 4
    assert LEX_SERVICE_TOL == LEX_GRID_TOL == 1e-7


def test_37_historical_preservation_passes() -> None:
    for name in ("V33X_PRECHANGE_PRESERVATION_MANIFEST.json", "V33X_POSTCHANGE_PRESERVATION_AUDIT.json"):
        value = j(name)
        assert value["status"] == "PASS"
        assert value["protected_mismatch_count"] == 0


def test_38_all_required_artifacts_exist() -> None:
    required = {
        "README.md", "V33X_STARTING_AUTHORITY_AUDIT.json", "V33X_PRECHANGE_PRESERVATION_MANIFEST.json",
        "V33X_E0_BASELINE_IDENTITY.json", "V33X_FULL_ELECTRICAL_AUTHORITY_AUDIT.json",
        "V33X_E1_FORMULATION_CONTRACT.json", "V33X_E1_STAGE2_RESULTS.csv", "V33X_E1_RECOURSE_LEDGER.csv",
        "V33X_E1_FRESH_OPENDSS_RESULTS.csv", "V33X_E1_REVIEW.json", "V33X_E2_FORMULATION_CONTRACT.json",
        "V33X_E2_LEVERAGE_MAP.json", "V33X_E2_LEVERAGE_MAP_SHA256.json", "V33X_E2_STAGE1_HEADROOM.csv",
        "V33X_E2_SERVICE_PARITY_AUDIT.json", "V33X_E2_STAGE2_RESULTS.csv", "V33X_E2_RECOURSE_LEDGER.csv",
        "V33X_E2_FRESH_OPENDSS_RESULTS.csv", "V33X_E2_REVIEW.json", "V33X_E0_E1_E2_COMPARISON.csv",
        "V33X_HEADROOM_COMPARISON.csv", "V33X_AIDC_GRID_VALUE_COMPARISON.csv",
        "V33X_DEVELOPMENT_CANDIDATE_DECISION.json", "V33X_FINAL_DEVELOPMENT_REVIEW.json",
        "V33X_FINAL_DEVELOPMENT_REVIEW.md", "V33X_TEST_REPORT.json",
        "V33X_POSTCHANGE_PRESERVATION_AUDIT.json", "V33X_ARTIFACT_SHA256.json",
    }
    assert required <= {path.name for path in OUT.iterdir() if path.is_file()}


def test_39_artifact_manifest_is_self_consistent() -> None:
    value = j("V33X_ARTIFACT_SHA256.json")
    assert value["file_count"] == len(value["files"])
    for row in value["files"]:
        payload = (OUT / row["path"]).read_bytes()
        assert len(payload) == row["byte_count"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]


def test_40_required_not_run_is_zero() -> None:
    value = j("V33X_TEST_REPORT.json")
    assert value["failed"] == value["not_run"] == value["required_NOT_RUN"] == 0
