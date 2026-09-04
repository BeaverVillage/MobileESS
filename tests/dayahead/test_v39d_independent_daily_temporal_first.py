from __future__ import annotations

import inspect
import json
from pathlib import Path

import pandas as pd

from dayahead.v39c.freeze import load_facility_prior, sha256_file
from dayahead.v39d.actual import validate_actual_fixed_replay
from dayahead.v39d.contracts import (
    ARTIFACT_ROOT,
    CAPACITY_FILE_SHA256,
    EXPECTED_DATES,
    EXPECTED_GPU_CAPACITY,
    RACK_AUTHORITY_PATH,
    RACK_FREEZE_CERTIFICATE_PATH,
    REQUIRED_ARTIFACTS,
    V37_DAY_ROOT,
)
from dayahead.v39d.spatial import build_common_initial_state


REPO = Path(__file__).resolve().parents[2]
ARTIFACT = REPO / ARTIFACT_ROOT


def j(name: str) -> dict:
    return json.loads((ARTIFACT / name).read_text(encoding="utf-8"))


def test_all_required_artifacts_and_124_da_freezes_exist() -> None:
    assert all((ARTIFACT / name).is_file() for name in REQUIRED_ARTIFACTS)
    assert len(list(ARTIFACT.glob("V39D_DAYAHEAD_DECISION_FREEZE_*.json"))) == 31 * 4


def test_independent_daily_contract_has_zero_cross_day_reads() -> None:
    contract = j("V39D_INDEPENDENT_DAILY_CONTRACT.json")
    assert contract["independent_days"] == 31
    assert contract["inter_day_state_carry_count"] == 0
    assert contract["cross_day_result_read_count"] == 0
    assert contract["cross_day_AIDC_state_read_count"] == 0
    assert contract["cross_day_migration_state_read_count"] == 0
    assert contract["INTER_DAY"] == "INDEPENDENT"
    assert contract["INTRA_DAY"] == "STATEFUL"


def test_initialization_api_cannot_accept_rw_or_rsp_schedule() -> None:
    parameters = set(inspect.signature(build_common_initial_state).parameters)
    assert parameters == {"running_jobs", "site_capacity", "site_prior", "name"}


def test_initial_state_firewall_and_freeze_order_pass_all_days() -> None:
    fairness = j("V39D_DAILY_INITIAL_STATE_FAIRNESS_AUDIT.json")
    assert fairness["PASS_count"] == fairness["expected_count"] == 31
    assert fairness["initial_state_reads_RW_future_schedule"] == 0
    assert fairness["initial_state_reads_RSP_future_schedule"] == 0
    assert fairness["initial_state_reads_grid_or_Fresh"] == 0
    assert fairness["initial_state_frozen_before_RW_evaluation"] == "YES"
    assert fairness["initial_state_frozen_before_RSP_evaluation"] == "YES"
    for day in EXPECTED_DATES:
        freeze = j(f"V39D_INITIAL_STATE_FREEZE_{day}.json")
        assert freeze["initial_state_reads_RW_future_schedule"] == 0
        assert freeze["initial_state_reads_RSP_future_schedule"] == 0
        assert freeze["initial_state_frozen_before_RW_evaluation"] == "YES"
        assert freeze["initial_state_frozen_before_RSP_evaluation"] == "YES"


def test_common_initial_state_contains_only_modeled_running_cohort() -> None:
    frame = pd.read_parquet(ARTIFACT / "V39D_COMMON_DAILY_INITIAL_AIDC_STATE.parquet")
    assert set(frame["operating_day"]) == set(EXPECTED_DATES)
    assert frame["D1_visible"].all()
    assert frame["synthetic_site_claim"].all()
    assert not frame["measured_site_claim"].any()
    for day in EXPECTED_DATES:
        ledger = pd.read_parquet(REPO / V37_DAY_ROOT / day / "V37_R4A_JOB_LEDGER.parquet")
        expected = set(ledger.loc[ledger["state_at_issue"].eq("RUNNING"), "job_id"].astype(str))
        actual = set(frame.loc[frame["operating_day"].eq(day), "job_uid"].astype(str))
        assert actual == expected


def test_common_initial_state_is_capacity_feasible() -> None:
    frame = pd.read_parquet(ARTIFACT / "V39D_COMMON_DAILY_INITIAL_AIDC_STATE.parquet")
    loads = frame.groupby(["operating_day", "initial_AIDC"])["requested_GPU"].sum()
    assert all(int(value) <= EXPECTED_GPU_CAPACITY[site] for (_day, site), value in loads.items())


def test_policy_blind_initialization_is_deterministically_repeatable() -> None:
    day = EXPECTED_DATES[0]
    ledger = pd.read_parquet(REPO / V37_DAY_ROOT / day / "V37_R4A_JOB_LEDGER.parquet")
    running = tuple(
        (str(row.job_id), int(row.requested_GPUs))
        for row in ledger.loc[ledger["state_at_issue"].eq("RUNNING")].itertuples(index=False)
    )
    prior, _ = load_facility_prior(REPO)
    left = build_common_initial_state(running, EXPECTED_GPU_CAPACITY, prior, name="LEFT")
    right = build_common_initial_state(running, EXPECTED_GPU_CAPACITY, prior, name="RIGHT")
    assert left["state"] == right["state"]
    assert left["optimization_objective_used"] is False
    assert left["RW_future_schedule_reads"] == left["RSP_future_schedule_reads"] == 0


def test_all_cases_and_modes_share_each_daily_initial_sha() -> None:
    audit = j("V39D_DAILY_INITIAL_STATE_FAIRNESS_AUDIT.json")
    assert audit["B0_B1_B2_B3_initial_state_identity"] is True
    assert audit["RW_RSP_initial_running_state_identity"] is True
    for row in audit["days"]:
        hashes = {value for key, value in row.items() if key.endswith("initial_state_SHA")}
        assert len(hashes) == 1


def test_temporal_first_hierarchy_never_uses_weighted_sum() -> None:
    policy = j("V39D_TEMPORAL_FIRST_POLICY_CONTRACT.json")
    assert policy["weighted_sum_used"] is False
    assert policy["arbitrary_migration_penalty_used"] is False
    assert policy["migration_solver_called_only_after_temporal_only_infeasibility"] is True
    assert policy["RSP_schedule_mutation_inside_migration_stage"] == 0


def test_migration_solver_call_is_exactly_conditioned_on_temporal_failure() -> None:
    frame = pd.read_parquet(ARTIFACT / "V39D_TEMPORAL_FIRST_ESCALATION_AUDIT.parquet")
    rsp = frame.loc[frame["temporal_mode"].eq("RSP")]
    assert len(frame) == 62 and len(rsp) == 31
    assert (
        rsp["migration_solver_calls"]
        == rsp["temporal_only_status"].eq("INFEASIBLE").astype(int)
    ).all()


def test_pending_placement_is_not_counted_as_migration() -> None:
    witness = j("V39D_MIGRATION_MINIMUM_WITNESS_AUDIT.json")
    assert witness["PENDING_initial_placement_counted_as_migration"] is False
    assert witness["V39C_chain_migration_count"] == 211
    assert witness["V39C_211_used_as_V39D_decision"] is False


def test_rw_failure_is_not_rescued_or_hidden() -> None:
    frame = pd.read_parquet(ARTIFACT / "V39D_TEMPORAL_FIRST_ESCALATION_AUDIT.parquet")
    rw = frame.loc[frame["temporal_mode"].eq("RW")]
    failed = rw.loc[rw["temporal_only_status"].eq("INFEASIBLE")]
    assert len(failed) > 0
    assert failed["final_status"].eq(
        "RW_REFERENCE_INFEASIBLE_UNDER_FROZEN_SYNTHETIC_INITIAL_STATE"
    ).all()
    assert not failed["migration_escalated"].any()
    assert failed["migration_solver_calls"].eq(0).all()


def test_b0_b2_and_b1_b3_identity_firewalls_hold() -> None:
    audit = j("V39D_B0_B3_IDENTITY_AUDIT.json")
    assert audit["B0_equals_B2_AIDC_schedule"] is True
    assert audit["B1_equals_B3_AIDC_schedule"] is True
    assert audit["MESS_feedback_to_AIDC_count"] == 0


def test_actual_has_no_time_aidc_migration_or_wan_reoptimization() -> None:
    audit = j("V39D_ACTUAL_NO_REOPTIMIZATION_AUDIT.json")
    assert audit["Actual_temporal_reoptimization_calls"] == 0
    assert audit["Actual_AIDC_reoptimization_calls"] == 0
    assert audit["Actual_migration_reoptimization_calls"] == 0
    assert audit["Actual_WAN_rerouting_calls"] == 0
    assert audit["Actual_realized_input_decision_mutation_count"] == 0


def test_every_da_freeze_sha_is_self_consistent() -> None:
    for path in ARTIFACT.glob("V39D_DAYAHEAD_DECISION_FREEZE_*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = validate_actual_fixed_replay(payload, payload["DA_decision_SHA256"])
        assert result["status"] == "PASS"


def test_refrozen_rack_authority_is_committed_and_site_consistent() -> None:
    authority = json.loads((REPO / RACK_AUTHORITY_PATH).read_text(encoding="utf-8"))
    certificate = json.loads(
        (REPO / RACK_FREEZE_CERTIFICATE_PATH).read_text(encoding="utf-8")
    )
    audit = j("V39D_RACK_SITE_CONSISTENCY_AUDIT.json")
    assert authority["classification"] == "POSTHOC_ENGINEERING_RACK_AUTHORITY_REFREEZE"
    assert authority["semantics"] == "SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_CAPACITY"
    assert authority["measured_physical_Rack_census_claim"] is False
    assert authority["numeric_Rack_construction_May_result_reads"] == 0
    assert authority["logical_Rack_pool_count"] == 48
    assert authority["effective_Rack_deliverability_total"] == 624
    assert certificate["rack_mutation_count"] == 0
    assert sha256_file(REPO / RACK_AUTHORITY_PATH) == certificate["rack_authority_SHA256"]
    assert audit["legacy_total_Rack_deliverability"] == 609
    assert audit["new_total_Rack_deliverability"] == 624
    assert audit["hidden_609_GPU_ceiling_remaining"] is False
    assert audit["gang_split_count"] == 0
    assert audit["total_32GPU_host_positions"] == 19
    assert audit["sites_capable_of_hosting_60GPU_gang"] == [
        "AIDC01", "AIDC03", "AIDC05", "AIDC06", "AIDC08", "AIDC10", "AIDC12"
    ]


def test_same_input_rack_regression_repairs_only_the_legacy_blocker() -> None:
    audit = j("V39D_RACK_AUTHORITY_REGRESSION_AUDIT.json")
    may01 = audit["May01_RW_same_input_regression"]
    assert audit["established_root_cause"] == (
        "LEGACY_LOGICAL_RACK_AUTHORITY_INCONSISTENT_WITH_V39C_SITE_CAPACITY"
    )
    assert audit["used_as_Rack_numeric_construction_input"] is False
    assert may01["exact_legacy_first_failing_slot"] == 0
    assert may01["aggregate_active_GPU_at_legacy_failing_slot"] == 624
    assert may01["same_input_site_only_status"] == "PASS"
    assert may01["same_input_legacy_Rack_hard_status"] == "FAIL"
    assert may01["same_input_refrozen_Rack_hard_status"] == "PASS"
    assert may01["WAN_stage_entered"] is False
    assert audit["RW_31day"]["slot_count"] == 2155
    assert audit["RW_31day"]["day_count"] == 29
    assert audit["RSP_31day"]["slot_count"] == 1998
    assert audit["RSP_31day"]["day_count"] == 29


def test_capacity_authority_bytes_remain_exactly_frozen() -> None:
    path = (
        REPO / "dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/"
        "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    )
    assert sha256_file(path) == CAPACITY_FILE_SHA256


def test_fail_closed_preflight_never_launches_may() -> None:
    preflight = j("V39D_MAY_31DAY_INPUT_PREFLIGHT.json")
    assert preflight["READY"] + preflight["NOT_READY"] == 31
    assert preflight["missing"] == 0
    assert preflight["MAY_STARTED"] == "NO"
    if preflight["NOT_READY"]:
        assert preflight["status"] == "FAIL_CLOSED"
        assert preflight["MAY_CAMPAIGN_LAUNCH_READY"] == "NO"


def test_final_review_reports_independent_policy_and_no_may_start() -> None:
    review = (ARTIFACT / "V39D_FINAL_REVIEW.md").read_text(encoding="utf-8")
    assert "INDEPENDENT_DAILY_EVALUATION = YES" in review
    assert "TEMPORAL_FIRST_MIGRATION_POLICY = YES" in review
    assert review.rstrip().endswith("MAY_STARTED = NO")
