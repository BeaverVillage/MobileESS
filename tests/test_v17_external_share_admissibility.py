from pathlib import Path

from dayahead.v17_external_share_admissibility import (
    BLOCK_STATUS,
    FINAL_CLASSIFICATION,
    MAIN_AUTHORITY_RULE,
    NEXT_DECISION,
    build_admissibility,
    build_resolution,
    verify_archives,
)


def test_caprara_full_paper_fails_only_scope_gates():
    value = build_admissibility()
    caprara = value["caprara_full_paper_forensic"]
    gates = caprara["admissibility_gates"]
    assert caprara["full_paper_inspected"]
    assert caprara["reported_approximately_20_percent"]["exact_table_sum_fraction"] == 0.205
    assert gates["1_peer_reviewed_SCIE"] == "PASS"
    assert gates["2_real_trace_or_measurement_basis"] == "PASS_REAL_TRACE"
    assert gates["5_service_deferred_not_removed"] == "PASS_WITH_REBOUND_LIMITATION"
    assert gates["6_denominator_close_to_V17_IT_envelope"] == "FAIL_GPU_ONLY_SCOPE"
    assert gates["7_no_denominator_conversion_required"].startswith("FAIL_")
    assert caprara["CAPRARA_MAIN_AUTHORITY"] == "REJECTED_SCOPE_MISMATCH"


def test_cao_is_supporting_only_and_no_forbidden_percentage_product():
    source = build_admissibility()["cao_supporting_source"]
    findings = source["full_text_findings"]
    assert findings["supporting_evidence_only"]
    assert not findings["prohibited_derivation_used"]
    assert findings["main_authority_decision"] == "REJECTED_NO_DIRECT_SCOPE_MATCHED_SINGLE_SHARE"
    assert "periodic-job power" in findings["denominator_problem"]


def test_selection_rule_is_frozen_and_no_value_is_adopted():
    value = build_admissibility()
    assert value["main_authority_rule"] == MAIN_AUTHORITY_RULE
    assert value["rule_frozen_before_April_execution"]
    assert value["exact_adopted_main_value"] is None
    assert not value["external_authority_artifact_created"]
    assert value["eta_FLEX"] is None
    assert not value["scientific_refreeze_resumed"]


def test_gap_remains_blocked_and_historical_hashes_are_preserved():
    value = build_admissibility()
    resolution = build_resolution(value)
    assert resolution["status"] == BLOCK_STATUS
    assert resolution["historical_artifacts_immutable"]
    assert len(resolution["parents"]) == 2
    assert all(len(parent["sha256"]) == 64 for parent in resolution["parents"])
    assert resolution["gap_mark"] == "RETAINED_NOT_RESOLVED"
    assert resolution["final_classification"] == FINAL_CLASSIFICATION
    assert resolution["next_decision"] == NEXT_DECISION


def test_all_firewall_and_execution_counters_are_zero():
    value = build_admissibility()
    assert value["counters"]
    assert all(counter == 0 for counter in value["counters"].values())
    assert "April B0/B1/B2/B3" in value["downstream_actions_not_run"]


def test_archived_sources_and_parent_evidence_match_frozen_hashes():
    repo_root = Path(__file__).resolve().parents[1]
    observed = verify_archives(repo_root)
    assert len(observed) == 6
    assert all(len(value) == 64 for value in observed.values())
