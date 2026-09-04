from __future__ import annotations

import json
from pathlib import Path

import pytest

from dayahead.v35r3e.algorithm import assert_apr01_only
from dayahead.v35r3e_r1.beam import (
    BEAM_WIDTH,
    BEAM_WIDTH_FALLBACK,
    DEFAULT_K,
    EXACT_RESTRICTED_CANDIDATE_ID_REQUIRED_FOR_PASS,
    SEED_WIDTH,
    BeamState,
    canonical_sha256,
    deduplicate_children,
    objective_epsilon,
    prune_beam,
)


ROOT = Path("dayahead/artifacts/v35r3e_r1_adaptive_beam_sequential_coordination")
CACHE = Path("dayahead/cache/v35r3e_r1_adaptive_beam_sequential_coordination/2025-04-01")


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def dummy(identifier: str, rho: float, trajectory_sha: str, bound=None, gap=None):
    return BeamState(
        case_id="B2",
        beam_state_id=identifier,
        parent_state_id="ROOT",
        completed_vehicles=("MESS01",),
        vehicles=(),
        trajectory_slots=(),
        combined_fixed_p_by_service=(),
        combined_fixed_q_by_service=(),
        current_planning_objective=rho,
        solver_objective=rho,
        best_bound=bound,
        gap=gap,
        state_sha256=identifier,
        trajectory_equivalence_sha256=trajectory_sha,
    )


def test_frozen_primary_parameters_and_candidate_id_diagnostic_only():
    assert (DEFAULT_K, BEAM_WIDTH, SEED_WIDTH, BEAM_WIDTH_FALLBACK) == (200, 2, 2, 4)
    assert EXACT_RESTRICTED_CANDIDATE_ID_REQUIRED_FOR_PASS is False


def test_apr01_scope_fails_closed():
    assert_apr01_only("2025-04-01")
    for day in ("2025-04-02", "2025-04-20", "2025-04-21", "2025-05-01"):
        with pytest.raises(PermissionError):
            assert_apr01_only(day)


def test_objective_epsilon_uses_committed_numerical_scale():
    assert objective_epsilon(0.4746103541326161) == pytest.approx(1e-6)
    assert objective_epsilon(2.0) == pytest.approx(2e-6)


def test_canonical_state_hash_is_deterministic_and_order_stable():
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})


def test_duplicate_children_keep_better_objective():
    children = [dummy("z", 0.5, "same"), dummy("a", 0.4, "same")]
    unique, audit = deduplicate_children(children)
    assert [row.beam_state_id for row in unique] == ["a"]
    assert audit[0]["removed_state_id"] == "z"


def test_beam_pruning_is_bounded_and_objective_first():
    children = [dummy("c", 0.3, "c"), dummy("a", 0.1, "a"), dummy("b", 0.2, "b")]
    retained, pruned = prune_beam(children, 2)
    assert [row.beam_state_id for row in retained] == ["a", "b"]
    assert [row.beam_state_id for row in pruned] == ["c"]
    with pytest.raises(ValueError):
        prune_beam(children, 5)


def test_exact_parent_branch_and_isolated_worktree():
    audit = load("V35R3E_R1_ISOLATION_AUDIT.json")
    assert audit["parent_HEAD"] == "67265b62f6ab0510fd0b249771fb26346ef37c61"
    assert audit["branch"] == "codex/v35r3e-r1-adaptive-beam-sequential-coordination"
    assert audit["isolated_worktree"] is True
    assert audit["AIDC_worktrees_modified"] is False
    assert audit["push_performed"] is audit["merge_performed"] is False


def test_v35r3e_input_authority_is_conserved_without_exhaustive_rerun():
    audit = load("V35R3E_R1_V35R3E_INPUT_SHA_AUDIT.json")
    assert audit["V35R3E_INPUT_AUTHORITY_SHA_CONSERVATION"] == "PASS"
    assert audit["candidate_library_SHA"] == (
        "6b9006f1d062f2207d4fc77f716cbe24a96735453ac1e460f8433c87f792a443"
    )
    assert audit["S4_reused"] is True and audit["K0_reused"] == 200
    assert audit["exhaustive_ground_truth_recomputed_cases"] == 0


def test_beam_trace_has_serial_vehicle_order_and_width_two():
    trace = load("V35R3E_R1_BEAM_TRACE.json")
    assert trace["vehicle_order"] == ["MESS01", "MESS02", "MESS03", "MESS04"]
    assert trace["cross_case_state_sharing"] is False
    for case in ("B2", "B3"):
        rows = trace["cases"][case]
        assert [row["mess_id"] for row in rows] == trace["vehicle_order"]
        assert [row["retained_beam_count"] for row in rows] == [2, 2, 2, 2]
        assert all(row["beam_width"] == 2 for row in rows)


def test_each_parent_uses_top200_plus_stay_and_two_distinct_seeds():
    for case in ("B2", "B3"):
        for path in (CACHE / case / "B2").rglob("LOCAL_SEARCH.json"):
            row = json.loads(path.read_text(encoding="utf-8"))
            assert row["restricted_unique_candidate_state_solves"] == 201
            assert row["distinct_seed_count"] == 2
            assert len(set(row["seed_trajectory_signatures"])) == 2
            assert row["selected_candidate_ids"][0].split(":")[1] == "STAY"
            assert row["Fresh_reads"] == row["future_vehicle_reads"] == 0


def test_state_lineage_and_sha_are_complete():
    for case in ("B2", "B3"):
        beam = load(f"V35R3E_R1_{case}_FINAL_BEAM.json")
        state = beam["selected_state"]
        assert state["completed_vehicles"] == ["MESS01", "MESS02", "MESS03", "MESS04"]
        assert len(state["vehicles"]) == 4
        assert len(state["state_sha256"]) == len(state["trajectory_equivalence_sha256"]) == 64
        assert state["combined_fixed_p_by_service"]
        assert state["combined_fixed_q_by_service"]


def test_child_dedup_contract_uses_trajectory_not_candidate_id():
    audit = load("V35R3E_R1_CHILD_DEDUP_AUDIT.json")
    seed = load("V35R3E_R1_SEED_SELECTION_CONTRACT.json")
    assert audit["full_MILP_children"] == 28
    assert audit["unique_children"] + audit["duplicate_children_removed"] == 28
    assert seed["candidate_ID_alone_defines_distinctness"] is False
    assert seed["Apr01_tuned_near_tie_threshold"] is None


def test_chosen_chain_mipstarts_all_accepted_and_worklimit_unchanged():
    review = load("V35R3E_R1_FINAL_REVIEW.json")
    feasible = load("V35R3E_R1_FULL_MODEL_FEASIBLE_SPACE_AUDIT.json")
    assert review["chosen_chain_MIPStart_accepted"] == 8
    assert feasible["WorkLimit_tiers"] == [60.0, 180.0, 300.0]
    assert feasible["WorkLimit_changed"] is False


def test_original_full_multi_move_feasible_space_is_unchanged():
    audit = load("V35R3E_R1_FULL_MODEL_FEASIBLE_SPACE_AUDIT.json")
    assert audit["FULL_MULTI_MOVE_FEASIBLE_SPACE_UNCHANGED"] is True
    assert audit["MOVE_binary_count_per_vehicle"] == [51909]
    assert audit["seed_variables_fixed_in_final_solve"] == 0
    assert audit["forced_MOVE_count"] == 0
    assert audit["STAY_still_feasible"] is True
    assert audit["multiple_relocation_still_allowed"] is True


def test_fallback_order_and_move_zero_rule_are_frozen():
    audit = load("V35R3E_R1_K_BEAM_FALLBACK_AUDIT.json")
    assert audit["path_regression_triggers_beam_before_K"] is True
    assert audit["K_fallback_sequence_if_local_failure"] == [200, 400, 800, "FULL"]
    assert audit["MOVE_ZERO_is_trigger"] is False
    assert audit["beam4_used"] is audit["K_fallback_used"] is audit["full_scan_used"] is False


def test_b2_and_b3_non_regression_pass_at_numerical_tolerance():
    result = load("V35R3E_R1_OBJECTIVE_REGRESSION.json")
    for case in ("B2", "B3"):
        assert result[case]["PASS"] is True
        assert result[case]["V35R3E_R1_beam_Planning_rho"] <= (
            result[case]["trusted_V35R3_Planning_rho"] + result[case]["epsilon_obj"]
        )
        assert result[case]["fallback_formula_needed"] is False


def test_previous_b2_regression_cannot_pass_epsilon():
    result = load("V35R3E_R1_OBJECTIVE_REGRESSION.json")["B2"]
    assert result["V35R3E_greedy_Planning_rho"] > (
        result["trusted_V35R3_Planning_rho"] + result["epsilon_obj"]
    )


def test_path_dependence_is_confirmed_by_controlled_downstream_divergence():
    audit = load("V35R3E_R1_PATH_DEPENDENCE_AUDIT.json")
    assert audit["classification"] == "SEQUENTIAL_PATH_DEPENDENCE_CONFIRMED"
    assert audit["K_enlargement_alone_insufficient"] is True
    assert audit["prior_full_scan_fallback_count"] == 3
    assert audit["cases"]["B2"]["first_greedy_beam_divergence"] == "MESS01"


def test_planning_physical_feasibility_and_natural_moves_hold():
    for case in ("B2", "B3"):
        trajectory = load(f"V35R3E_R1_{case}_FINAL_TRAJECTORY.json")
        assert trajectory["planning"]["pass"] is True
        assert trajectory["planning"]["line_current_violation_count"] == 0
        assert trajectory["planning"]["voltage_violation_count"] == 0
        assert trajectory["natural_MOVE_count"] == 4


def test_compute_is_bounded_well_below_exhaustive_and_v35r3e():
    compute = load("V35R3E_R1_COMPUTE_SUMMARY.json")
    assert compute["restricted_candidate_state_solves"] == 2814
    assert compute["full_unrestricted_MILP_solves"] == 28
    assert compute["reduction_vs_exhaustive_17276_percent"] > 80
    assert compute["reduction_vs_V35R3E_11287_percent"] > 70


def test_nominal_forecast_accounts_for_beam_branching():
    forecast = load("V35R3E_R1_APR1_20_COMPUTE_FORECAST.json")
    assert forecast["nominal_case"]["restricted_candidate_state_solves_two_cases_per_day"] == 2814
    assert forecast["nominal_Apr1_20_restricted_candidate_state_solves"] == 56280
    assert forecast["nominal_case"]["full_MILP_solves_two_cases_per_day"] == 28
    assert forecast["bounded_beam4_case"]["full_MILP_solves_two_cases_per_day"] == 44
    assert forecast["ACTUAL_FUTURE_BEAM_FALLBACK_FREQUENCY"] == "UNKNOWN_BEFORE_CAMPAIGN"
    assert forecast["ACTUAL_FUTURE_K_FALLBACK_FREQUENCY"] == "UNKNOWN_BEFORE_CAMPAIGN"


def test_fresh_and_aidc_firewalls_and_search_only_change():
    review = load("V35R3E_R1_FINAL_REVIEW.json")
    contract = load("V35R3E_R1_PRODUCTION_SEARCH_CONTRACT.json")
    source = Path("dayahead/tools/run_v35r3e_r1_beam.py").read_text(encoding="utf-8")
    assert "run_fresh_opendss" not in source
    assert review["Fresh_search_reads"] == 0
    assert review["AIDC_science_changed"] is False
    assert review["production_science_meaning_changed"] is False
    assert contract["FRESH_SELECTION"] == "NO"


def test_final_authority_is_pass_and_ready():
    review = load("V35R3E_R1_FINAL_REVIEW.json")
    assert review["primary_classification"] == "V35R3E_R1_ADAPTIVE_BEAM_PRODUCTIONIZATION_PASS"
    assert review["MESS_PRODUCTION_READY"] == "YES"
