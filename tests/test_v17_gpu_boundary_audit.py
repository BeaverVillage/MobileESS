import json
from pathlib import Path

from dayahead.v17_gpu_boundary_audit import (
    FINAL_CLASSIFICATION,
    FLEX_COHORT_CLASSIFICATION,
    NEXT_DECISION,
    artifact_fingerprint,
    verify_historical_artifacts,
)


ARTIFACT = (
    Path(__file__).resolve().parents[1]
    / "dayahead"
    / "artifacts"
    / "v17_candidate"
    / "V17_GPU_SUBSYSTEM_BOUNDARY_TRAINING_AUDIT.json"
)


def _artifact():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_training_only_source_and_time_firewall():
    value = _artifact()
    source = value["source"]
    assert source["minimum_member_month"] == 202408
    assert source["maximum_member_month"] == 202503
    assert source["April_member_reads"] == 0
    assert source["May_member_reads"] == 0
    assert source["June_member_reads"] == 0
    assert source["Eagle_rows"] == 0
    assert source["non_H100_rows_in_denominator"] == 0
    assert value["time_contract"]["numerator_denominator_same_interval"]


def test_historical_whole_IT_share_evidence_is_immutable():
    repo_root = Path(__file__).resolve().parents[1]
    observed = verify_historical_artifacts(repo_root)
    assert len(observed) == 2
    assert all(len(sha256) == 64 for sha256 in observed.values())
    assert not _artifact()["checkpoint"]["historical_artifacts_modified"]


def test_same_source_node_equivalent_denominator_is_identifiable():
    value = _artifact()
    gate = value["denominator_authority_gate"]
    share = value["same_source_candidate_share"]
    assert gate["status"] == "PASS_NODE_EQUIVALENT_DENOMINATOR_IDENTIFIABLE"
    assert gate["same_Kestrel_H100_population"]
    assert gate["same_timezone_and_training_interval"]
    assert gate["total_requested_H100_GPU_hours"] > share["qualified_flexible_requested_GPU_hours"] > 0
    assert gate["GPU_per_node_application_count"] == 1
    assert share["node_hour_GPU_hour_identity_error"] <= 1e-8
    assert 0 < share["f_H100_FLEX_NODEH_all_executed_H100"] < 1


def test_energy_weighted_total_fails_closed_without_average_kappa():
    value = _artifact()["same_source_candidate_share"]
    assert value["energy_weighted_candidate"] is None
    assert value["energy_weighted_status"] == "NOT_IDENTIFIABLE_FOR_TOTAL_H100_WITH_FROZEN_KAPPA"
    assert "No average kappa" in value["energy_weighted_failure_reason"]


def test_current_W_F_is_not_a_service_deferrability_label():
    value = _artifact()["flexible_cohort_semantics_audit"]
    assert value["classification"] == FLEX_COHORT_CLASSIFICATION
    assert value["queue_wait_threshold_in_current_rule"] is None
    assert value["deadline_or_slack_threshold_in_current_rule"] is None
    assert value["SLA_preservation_test_in_current_rule"] is None
    assert value["eligible_active_node_hours_wait_le_10_minutes"] > 0
    assert 0 < value["eligible_active_node_hour_fraction_wait_le_10_minutes"] < 1
    assert not value["cohort_broadened"]


def test_caprara_is_plausibility_only_and_not_calibration():
    value = _artifact()["caprara_GPU_scope_plausibility_only"]
    assert value["Caprara_fraction"] == 0.205
    assert not value["forced_equal"]
    assert value["calibration_calls"] == 0


def test_semantics_defect_stops_all_downstream_work():
    value = _artifact()
    assert value["final_classification"] == FINAL_CLASSIFICATION
    assert value["next_decision"] == NEXT_DECISION
    assert not value["same_source_candidate_share"]["accepted_as_scientific_flexible_share"]
    assert value["whole_IT_boundary_actions"]["ESIF_reads"] == 0
    assert not value["whole_IT_boundary_actions"]["P_OTHER_IT_constructed"]
    assert "April B0/B1/B2/B3" in value["downstream_not_run"]
    assert all(count == 0 for count in value["counters"].values())


def test_artifact_fingerprint_is_reproducible():
    value = _artifact()
    frozen = value.pop("artifact_fingerprint")
    assert artifact_fingerprint(value) == frozen
