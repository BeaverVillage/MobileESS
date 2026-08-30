from dayahead.v17_flexible_share_precheck import (
    BLOCK_STATUS,
    FINAL_CLASSIFICATION,
    NEXT_DECISION,
    build_gap,
    build_precheck,
)


def test_precheck_fails_closed_without_adopting_a_number():
    value = build_precheck()
    assert value["status"] == BLOCK_STATUS
    assert value["exact_adopted_main_value"] is None
    assert value["eta_FLEX"] is None
    assert not value["scientific_refreeze_started"]
    assert value["final_classification"] == FINAL_CLASSIFICATION
    assert value["next_decision"] == NEXT_DECISION


def test_all_source_candidates_are_scope_audited_and_rejected():
    value = build_precheck()
    assert len(value["audited_sources"]) >= 6
    assert all("facility_scope" in source for source in value["audited_sources"])
    assert all("temporal_scope" in source for source in value["audited_sources"])
    assert all("schedulable_or_deferrable_share" in source for source in value["audited_sources"])
    assert not any(source["admissible_main_authority"] for source in value["audited_sources"])


def test_dataset312_utilization_is_not_misrepresented_as_flexible_share():
    value = build_precheck()
    dataset312 = next(source for source in value["audited_sources"] if source["source_id"] == "NLR_DATASET312")
    assert "utilization is not a schedulable energy share" in dataset312["rejection_reason"]
    assert dataset312["measured_vs_assumed"] == "workload power measured; whole-facility profiles simulated"


def test_firewall_and_execution_counters_are_zero():
    value = build_precheck()
    assert value["counters"]
    assert all(counter == 0 for counter in value["counters"].values())


def test_gap_artifact_stops_all_downstream_science():
    gap = build_gap(build_precheck())
    assert gap["status"] == BLOCK_STATUS
    assert "April B0/B1/B2/B3" in gap["downstream_actions_not_run"]
    assert "RC-MQT retraining" in gap["downstream_actions_not_run"]
    assert gap["final_classification"] == FINAL_CLASSIFICATION
    assert gap["next_decision"] == NEXT_DECISION
