"""Research QoS authority and causal boundary regression tests (no solver)."""
from dataclasses import replace
import json

import pytest

from v42_capacity.actual import Request
from v42_integration.qos import (POLICY_ID, SLOT_SECONDS, TrainingStatistics,
    ObservedJob, QoSWindowProvider, CausalReferenceScheduler, receipt_slot_domain,
    gpu_bucket, walltime_bucket)


def train(n=100, *, waits=None, partition="gpu-h100", protected=False, qos="normal"):
    return [dict(uid=str(i), submit_seconds=100000., start_seconds=100000.+(4500 if waits is None else waits[i]),
                 end_seconds=100000.+(4500 if waits is None else waits[i])+900.,
                 observed_at_seconds=110000., request_provenance="SUBMISSION_VERSION_VERIFIED",
                 qos=qos, protected=protected, partition=partition, gpu=1,
                 requested_walltime_seconds=3600) for i in range(n)]


def stats(rows=None):
    return TrainingStatistics.from_records(train() if rows is None else rows, source_sha="frozen-train-sha")


def job(**kwargs):
    return replace(ObservedJob("job", 0, 0, 900, 900, batch_eligible=True,
        partition="gpu-h100", representation_starts_seconds=tuple(range(0, 9000, 900)),
        provider_sha="provider", reference_sha="reference"), **kwargs)


def provider(stat=None, receipts=None):
    return QoSWindowProvider(stats() if stat is None else stat, case_sha="case", provider_sha="provider", receipts=receipts)


def test_known_and_observed_unknown_have_same_budget_and_origin_provenance():
    p = provider()
    known = p.issue(job(uid="known"))
    unknown = p.issue(job(uid="unknown", origin_unknown=True))
    assert known.budget_seconds == unknown.budget_seconds == 3600
    assert known.allowed_starts_seconds == unknown.allowed_starts_seconds
    assert unknown.origin_unknown is True and unknown.policy_id == POLICY_ID


def test_pre_submission_rejected_and_no_realized_fields_exist():
    with pytest.raises(ValueError, match="NOT_YET_SUBMITTED"):
        job(submit_seconds=1)
    with pytest.raises(TypeError):
        ObservedJob("x", 0, 0, 0, 900, actual_runtime=1)
    with pytest.raises(TypeError):
        ObservedJob("x", 0, 0, 0, 900, future_completion=1)


def test_higher_quantile_seconds_floor_and_minimum_duration_only_normalize():
    s = stats(train(waits=[i*50 for i in range(100)]))
    # Q90_higher uses sorted index ceil(.9*99)=90; 4500/900=5.
    assert s.select(job()).q90_higher_z == 5
    receipt = provider(s).issue(job(t50_seconds=1, reference_start_seconds=900))
    assert receipt.empirical_wait_seconds == 4500
    assert receipt.budget_seconds == 3600
    assert receipt.t50_seconds == 1
    s = stats(train(waits=[1799]*100))
    assert provider(s).issue(job(reference_start_seconds=0)).budget_seconds == 900


def test_backoff_support_counts_unique_uids_and_keeps_qos_protected_separate():
    records = train(60, partition="one") + [dict(r, uid="b"+r["uid"], partition="two") for r in train(40)]
    records += records[:20]
    s = stats(records)
    selected = s.select(job(partition="one"))
    assert selected.level == 1 and selected.n_unique_uids == 100
    assert s.exclusions["DUPLICATE_UID_ROW"] == 20
    assert provider(stats(train(99))).issue(job()).status == "UNSUPPORTED_COHORT"
    assert provider(s).issue(job(qos="standby")).budget_seconds == 0
    assert provider(s).issue(job(protected=True)).budget_seconds == 0


def test_protected_unconfirmed_batch_baseline_excess_empty_contract_window():
    p = provider()
    assert p.issue(job(uid="protected", protected=True)).budget_seconds == 0
    assert p.issue(job(uid="batch", batch_eligible=None)).budget_seconds == 0
    excess = p.issue(job(uid="excess", reference_start_seconds=5400))
    assert excess.budget_seconds == 0 and "BASELINE_QOS_EXCESS" in excess.reasons
    impossible = p.issue(job(uid="empty", hard_earliest_start_seconds=5400, hard_latest_start_seconds=4500))
    assert impossible.allowed_starts_seconds == () and impossible.status == "EMPTY_AUTHORIZED_WINDOW"


def test_no_budget_reissue_across_stage_event_and_json_restart():
    p = provider()
    first = p.issue(job(origin_unknown=True))
    assert p.issue(job(event_seconds=1800, state="RUNNING", origin_unknown=False)) is first
    restored = provider(receipts=json.loads(json.dumps(p.export_ledger())))
    again = restored.issue(job(event_seconds=2700, state="RUNNING", origin_unknown=False))
    assert again.budget_seconds == first.budget_seconds and again.origin_unknown is True
    assert restored.allowed_starts(job(event_seconds=2700)) == (2700, 3600, 4500)
    with pytest.raises(ValueError, match="AUTHORITY_CHANGED"):
        restored.issue(job(reference_start_seconds=1800))
    corrupted = json.loads(json.dumps(p.export_ledger()))
    corrupted["job"]["budget_seconds"] += 900
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        provider(receipts=corrupted)


def test_contract_and_representation_intersection_never_creates_starts():
    p = provider()
    j = job(representation_starts_seconds=(900, 1800, 2700), release_seconds=1000,
            completion_deadline_seconds=3500, nominal_service_seconds=1000)
    receipt = p.issue(j)
    assert receipt.allowed_starts_seconds == (1800,)
    assert receipt_slot_domain(receipt, axis_origin_seconds=0, axis_start_slot=24) == (26,)
    assert receipt.budget_seconds == 3600
    # Neither requested walltime nor a midnight representation boundary creates a contract.
    assert job().completion_deadline_seconds is None
    assert p.allowed_starts(j, interruption_seconds=3601) == ()


def test_shared_delay_and_interruption_budget_intersection():
    p = provider()
    j = job()
    receipt = p.issue(j)
    assert p.allowed_starts(j, interruption_seconds=1800) == (0, 900, 1800, 2700)
    assert receipt.budget_seconds == 3600


def test_train_exclusion_and_descriptive_proxy_cannot_authorize():
    rows = train(3)
    rows[0]["request_provenance"] = "UNVERIFIED"
    rows[1].pop("observed_at_seconds")
    rows[2]["end_seconds"] = rows[2]["start_seconds"]-1
    s = stats(rows)
    assert len(s.accepted_uids) == 0
    assert s.exclusions["UNSUPPORTED_REQUEST_PROVENANCE"] == 1
    assert s.exclusions["MISSING_OBSERVATION_TIME"] == 1
    assert s.exclusions["INVALID_TIME_ORDER_OR_ZERO_RUNTIME"] == 1
    descriptive = TrainingStatistics.from_records(rows, source_sha="raw", descriptive_only=True)
    with pytest.raises(ValueError, match="DESCRIPTIVE_STATS"):
        provider(descriptive)


def test_duplicate_conflicting_uid_does_not_choose_a_convenient_label():
    records = train()
    records.append(dict(records[0], start_seconds=105000, end_seconds=105900))
    s = stats(records)
    assert len(s.accepted_uids) == 99 and s.exclusions["CONFLICTING_UID_EXCLUDED"] == 1
    assert s.select(job()) is None


def test_pr75_bucket_boundaries_are_fixed():
    assert [gpu_bucket(n) for n in (1, 2, 4, 5, 16, 17, 64, 65)] == ["1", "2-4", "2-4", "5-16", "5-16", "17-64", "17-64", "65+"]
    assert [walltime_bucket(t) for t in (3600, 3601, 14400, 14401, 86400, 86401)] == ["<=1h", "1-4h", "1-4h", "4-24h", "4-24h", ">24h"]


def test_reference_uses_frozen_nominal_only_fifo_and_restart():
    shadow = CausalReferenceScheduler({"A": 4}, reference_sha="shadow")
    requests = [Request("b", 0, 4, ("A",), 1800), Request("a", 0, 4, ("A",), 900)]
    result = shadow.submit_batch(requests, event_seconds=0)
    assert [(r["uid"], r["reference_start_seconds"]) for r in result] == [("a", 0), ("b", 900)]
    restored = CausalReferenceScheduler.from_dict(json.loads(json.dumps(shadow.to_dict())))
    receipt = restored.submit(Request("c", 1800, 4, ("A",), 900), event_seconds=1800)
    assert receipt["reference_start_seconds"] == 2700
    assert receipt["realized_completion_reads"] == receipt["grid_reads"] == 0
    with pytest.raises(ValueError, match="NOT_YET_SUBMITTED"):
        restored.submit(Request("future", 9000, 1, ("A",), 1), event_seconds=2700)
