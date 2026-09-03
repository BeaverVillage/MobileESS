from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dayahead.v35r3a.contracts import (
    ACTIVE_V35R3_WORKTREE,
    EXPECTED_BRANCH,
    FIXED_PROTECTED,
    GPU_CAPACITY,
    HIGH_PROTECTED,
    ISSUE_TIME,
    NORMAL_QUEUE_CONTROLLED,
    PREEMPTIVE,
    RUNNING_FIXED,
    SOURCE_BASELINE,
    SPATIO_TEMPORAL_CANDIDATE,
    STANDBY_QUEUE_CONTROLLED,
    TARGET_END,
    TARGET_START,
    TEMPORAL_QUEUE_CONTROLLED,
    W1,
    W3,
    W5,
    classify_pending,
    require_apr01,
    submission_complete,
)
from dayahead.v35r3a.pipeline import (
    ARTIFACT_DIRNAME,
    EXPECTED_DATACARD_SHA256,
    EXPECTED_KESREL_SHA256,
)
from dayahead.v35r3a.scheduler_twin import (
    SchedulerJob,
    ScheduleRow,
    deterministic_control,
    minimum_sitefactor_for_pair,
    schedule_hash,
    schedule_known_queue,
    service_noninferiority,
    target_gpu_profile,
    window_metrics,
)


REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "dayahead" / "artifacts" / ARTIFACT_DIRNAME


def _request(**updates):
    row = {
        "nodes_req": 1,
        "gpus_requested": 2.0,
        "wallclock_seconds": 3600.0,
        "qos": "normal",
        "partition": "gpu-h100",
    }
    row.update(updates)
    return row


def _job(job_id: str, **updates) -> SchedulerJob:
    values = {
        "job_id": job_id,
        "submit_time": ISSUE_TIME - timedelta(hours=1),
        "partition": "gpu-h100",
        "qos": "normal",
        "requested_nodes": 1,
        "requested_gpus": 2.0,
        "duration_slots": 4,
        "processors_requested": 16,
        "memory_request": "16G",
        "workload_class": NORMAL_QUEUE_CONTROLLED,
        "protected": False,
    }
    values.update(updates)
    return SchedulerJob(**values)


def _row(job_id: str, **updates) -> ScheduleRow:
    values = {
        "job_id": job_id,
        "state_at_issue": "PENDING",
        "workload_class": NORMAL_QUEUE_CONTROLLED,
        "protected": False,
        "qos": "normal",
        "partition": "gpu-h100",
        "submit_time": (ISSUE_TIME - timedelta(hours=1)).isoformat(),
        "requested_nodes": 1,
        "requested_gpus": 2.0,
        "duration_slots": 4,
        "scheduled_start_slot": 0,
        "scheduled_end_slot": 4,
        "wait_hours": 1.0,
        "request_gpu_hours": 2.0,
        "priority_rank": 0,
        "sitefactor": 0,
        "policy": "baseline",
    }
    values.update(updates)
    return ScheduleRow(**values)


def _json(name: str):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_apr01_fixed_aest_boundary():
    assert require_apr01(TARGET_START) == TARGET_START
    assert require_apr01(TARGET_END - timedelta(seconds=1)).date().isoformat() == "2025-04-01"


def test_apr02_and_naive_times_rejected():
    with pytest.raises(PermissionError, match="APR01_ONLY"):
        require_apr01(TARGET_END)
    with pytest.raises(ValueError, match="NAIVE"):
        require_apr01(TARGET_START.replace(tzinfo=None))


def test_complete_normal_submission_is_temporal():
    assert submission_complete(_request())
    assert classify_pending(_request())[0] == NORMAL_QUEUE_CONTROLLED


def test_partial_normal_submission_can_be_temporal_only():
    request = _request(gpus_requested=1.0)
    assert classify_pending(request)[0] == NORMAL_QUEUE_CONTROLLED
    assert request["gpus_requested"] < 4 * request["nodes_req"]


def test_high_qos_is_fixed_protected():
    classification, reasons = classify_pending(_request(qos="high"))
    assert classification == HIGH_PROTECTED
    assert "PROTECTED_HIGH_OR_URGENT_QOS" in reasons


def test_standby_qos_is_controlled_but_partition_name_does_not_define_qos():
    assert classify_pending(_request(qos="standby"))[0] == STANDBY_QUEUE_CONTROLLED
    assert classify_pending(_request(qos="standby", gpus_requested=1.0))[0] == STANDBY_QUEUE_CONTROLLED
    classification, reasons = classify_pending(_request(partition="gpu-h100-stdby"))
    assert classification == NORMAL_QUEUE_CONTROLLED
    assert "PARTITION_NAME_NOT_QOS_AUTHORITY" in reasons


def test_missing_gpu_request_fails_closed():
    assert not submission_complete(_request(gpus_requested=np.nan))
    assert classify_pending(_request(gpus_requested=np.nan))[0] == FIXED_PROTECTED


def test_running_reservation_is_fixed_and_nonpreemptive():
    running = _job(
        "r",
        workload_class=RUNNING_FIXED,
        protected=True,
        running_at_issue=True,
        fixed_remaining_slots=8,
        requested_gpus=4.0,
    )
    rows, _ = schedule_known_queue([running], [])
    assert rows[0].scheduled_start_slot == 0
    assert rows[0].scheduled_end_slot == 8
    assert PREEMPTIVE == "PREEMPTIVE_NOT_AUTHORIZED"


def test_requested_walltime_controls_reservation_length():
    rows, _ = schedule_known_queue([], [_job("a", duration_slots=7)])
    assert rows[0].scheduled_end_slot - rows[0].scheduled_start_slot == 7


def test_resource_capacity_and_no_double_counting():
    rows, occupancy = schedule_known_queue(
        [],
        [_job("a", requested_gpus=400.0, requested_nodes=100), _job("b", requested_gpus=400.0, requested_nodes=100)],
    )
    assert occupancy.max() <= GPU_CAPACITY
    assert rows[1].scheduled_start_slot >= rows[0].scheduled_end_slot


def test_stable_replay_and_tie_breaking():
    jobs = [_job("b"), _job("a")]
    first, _ = schedule_known_queue([], jobs)
    second, _ = schedule_known_queue([], list(reversed(jobs)))
    assert schedule_hash(first) == schedule_hash(second)
    assert [row.job_id for row in first] == ["a", "b"]


def test_minimum_sitefactor_pair_perturbation():
    factors = minimum_sitefactor_for_pair({"a": 2, "b": 7}, "a", "b")
    assert factors == {"a": 0, "b": 6}
    assert sum(abs(value) for value in factors.values()) == 6


def test_deterministic_control_fails_closed_below_two_candidates():
    baseline, _ = schedule_known_queue([], [_job("a", workload_class=FIXED_PROTECTED, protected=True)])
    controlled, trace, changes = deterministic_control(baseline, [], [])
    assert schedule_hash(controlled) != schedule_hash(baseline)  # policy label is intentionally part of identity
    assert not changes
    assert trace[0]["reason"] == "FEWER_THAN_TWO_STANDBY_QUEUE_CONTROLLED_JOBS"


def test_identity_schedule_passes_strict_service_gate():
    baseline = [_row("a")]
    gate = service_noninferiority(baseline, [replace(baseline[0], policy="controlled")])
    assert gate.passed
    assert all(value == 0.0 for value in gate.deltas.values())


def test_high_qos_delay_fails_service_gate():
    baseline = [_row("h", qos="high", protected=True)]
    controlled = [replace(baseline[0], scheduled_start_slot=1, scheduled_end_slot=5, wait_hours=1.25)]
    gate = service_noninferiority(baseline, controlled)
    assert not gate.passed
    assert gate.deltas["high_urgent_delay_count"] == 1.0


def test_standby_reordering_may_change_wait_without_failing_tier_gate():
    baseline = [
        _row("s1", qos="standby", workload_class=STANDBY_QUEUE_CONTROLLED),
        _row(
            "s2",
            qos="standby",
            workload_class=STANDBY_QUEUE_CONTROLLED,
            scheduled_start_slot=4,
            scheduled_end_slot=8,
            wait_hours=2.0,
            priority_rank=1,
        ),
    ]
    controlled = [
        replace(baseline[0], scheduled_start_slot=4, scheduled_end_slot=8, wait_hours=2.0),
        replace(baseline[1], scheduled_start_slot=0, scheduled_end_slot=4, wait_hours=1.0),
    ]
    gate = service_noninferiority(baseline, controlled)
    assert gate.passed
    assert gate.deltas["standby_advanced_job_count"] == 1.0
    assert gate.deltas["standby_delayed_job_count"] == 1.0


def test_standby_control_cannot_delay_normal_job():
    baseline = [_row("n", qos="normal", workload_class=NORMAL_QUEUE_CONTROLLED)]
    controlled = [
        replace(baseline[0], scheduled_start_slot=1, scheduled_end_slot=5, wait_hours=1.25)
    ]
    gate = service_noninferiority(baseline, controlled)
    assert not gate.passed
    assert not gate.checks["standby_never_delays_high_or_normal"]


def test_standby_completion_conservation_is_hard_gate():
    baseline = [
        _row("s", qos="standby", workload_class=STANDBY_QUEUE_CONTROLLED)
    ]
    controlled = [
        replace(
            baseline[0],
            scheduled_start_slot=120,
            scheduled_end_slot=124,
            wait_hours=31.0,
        )
    ]
    gate = service_noninferiority(baseline, controlled)
    assert not gate.passed
    assert not gate.checks["standby_completed_jobs_not_lower"]
    assert not gate.checks["standby_completed_GPU_hours_not_lower"]
    assert not gate.checks["standby_terminal_pending_GPU_hours_not_higher"]


def test_raw_qos_tier_precedence_ignores_stdby_partition_substring():
    normal = _job("n", partition="gpu-h100-stdby", qos="normal")
    standby = _job(
        "s",
        qos="standby",
        workload_class=STANDBY_QUEUE_CONTROLLED,
    )
    rows, _ = schedule_known_queue(
        [],
        [standby, normal],
        rank_override={"s": -1000, "n": 1000},
    )
    assert [row.job_id for row in rows] == ["n", "s"]


def test_wait_increase_fails_service_gate():
    baseline = [_row("a")]
    controlled = [replace(baseline[0], wait_hours=1.25)]
    gate = service_noninferiority(baseline, controlled)
    assert not gate.passed
    assert not gate.checks["mean_normal_wait_not_higher"]


def test_target_profile_has_96_slots():
    profile = target_gpu_profile([_row("a", scheduled_start_slot=24, scheduled_end_slot=28)])
    assert profile.shape == (96,)
    assert profile[:4].tolist() == [2.0] * 4
    assert profile[4:].sum() == 0.0


def test_w1_w3_w5_accounting():
    profile = np.arange(96, dtype=float)
    metrics = window_metrics(profile)
    assert metrics["W1_mean_kW"] == pytest.approx(np.mean(profile[list(W1)]))
    assert metrics["W3_mean_kW"] == pytest.approx(np.mean(profile[list(W3)]))
    assert metrics["W5_mean_kW"] == pytest.approx(np.mean(profile[list(W5)]))


def test_exact_starting_lineage_and_branch():
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    merge_base = subprocess.check_output(["git", "merge-base", "HEAD", SOURCE_BASELINE], cwd=REPO, text=True).strip()
    assert branch == EXPECTED_BRANCH
    assert merge_base == SOURCE_BASELINE


def test_isolation_artifact_records_separate_worktree_and_zero_writes():
    audit = _json("V35R3A_ISOLATION_AUDIT.json")
    assert audit["worktree_separate"]
    assert audit["active_V35R3_files_changed_by_this_task"] == 0
    assert audit["active_worktree_write_operations"] == 0
    assert not audit["paths_shared_with_active_V35R3"]


def test_source_integrity_and_vendor_heads_captured():
    source = _json("V35R3A_KESREL_SOURCE_AUDIT.json")
    heads = _json("V35R3A_VENDOR_REPO_HEADS.json")
    assert source["archive_sha256"] == EXPECTED_KESREL_SHA256
    assert source["datacard_sha256"] == EXPECTED_DATACARD_SHA256
    assert source["archive_integrity"] == "PASS"
    assert all(value["HEAD"] for value in heads["repositories"].values())


def test_causality_firewall_counts_are_zero():
    source = _json("V35R3A_KESREL_SOURCE_AUDIT.json")
    review = _json("V35R3A_FINAL_REVIEW.json")["numbered_report"]
    assert source["KQ0_access"]["future_job_identity_rows_returned_to_KQ0"] == 0
    assert source["PR1_access"]["future_actual_start_end_runtime_columns_read"] == 0
    assert all(review[str(number)]["value"] == 0 for number in range(53, 58))


def test_queue_partition_conservation_and_spatial_subset():
    snapshot = _json("V35R3A_APR01_QUEUE_SNAPSHOT.json")
    census = pd.read_csv(ARTIFACTS / "V35R3A_WORKLOAD_CLASS_CENSUS.csv")
    assert snapshot["partition_conservation"]
    spatial = census.loc[census.workload_class.eq(SPATIO_TEMPORAL_CANDIDATE)].iloc[0]
    assert bool(spatial.subset_of_temporal)


def test_actual_kq0_uses_raw_standby_qos_and_audits_partition_ambiguity():
    snapshot = _json("V35R3A_APR01_QUEUE_SNAPSHOT.json")
    assert snapshot["P_tau"]["qos_counts"]["standby"] == 420
    assert snapshot["P_tau"]["temporal_queue_controlled_count"] > 0
    assert snapshot["P_tau"]["partial_temporal_queue_controlled_count"] > 0
    assert snapshot["P_tau"]["partition_only_stdby_without_standby_qos_count"] == 1
    assert snapshot["P_tau"]["qos_resource_summary"]["standby"]["schedulable_job_count"] == 338
    assert snapshot["P_tau"]["qos_resource_summary"]["standby"]["partial_shared_request_count"] == 336
    assert snapshot["P_tau"]["temporal_queue_controlled_count"] == 339
    audit = pd.read_parquet(ARTIFACTS / "V35R3A_PENDING_FIELD_AUDIT.parquet")
    assert len(audit) == snapshot["P_tau"]["job_count"] == 421
    assert (audit.qos_raw == "standby").sum() == 420
    assert (
        audit.qos_partition_semantics_relation
        == "PARTITION_ONLY_STDBY_NAME_WITH_NONSTANDBY_QOS"
    ).sum() == 1


def test_standby_authority_is_qos_specific_and_locally_hashed():
    correction = _json("V35R3A_STANDBY_SEMANTICS_CORRECTION.json")
    authority = correction["qos_authority"]
    assert authority["standby"] == "runs only when nodes are idle"
    assert not authority["partition_to_qos_mapping_present"]
    assert len(authority["source_sha256"]) == 64


def test_pre_correction_result_is_superseded_and_firewall_remains_zero():
    old = _json("V35R3A_PRE_STANDBY_SEMANTICS_CORRECTION_DIAGNOSTIC.json")
    correction = _json("V35R3A_STANDBY_SEMANTICS_CORRECTION.json")
    assert old["status"] == "SUPERSEDED_PRE_CORRECTION_EVIDENCE"
    assert not old["may_be_used_as_final_scientific_conclusion"]
    assert set(correction["causality_counters"].values()) == {0}
    assert not correction["Fresh_used_to_choose_policy"]
    assert not correction["unsupported_per_job_deadline_assumed"]


def test_corrected_control_preserves_tier_service_and_resource_feasibility():
    baseline = pd.read_parquet(ARTIFACTS / "V35R3A_BASELINE_SCHEDULE.parquet")
    controlled = pd.read_parquet(ARTIFACTS / "V35R3A_KQ0_CONTROLLED_SCHEDULE.parquet")
    gate = _json("V35R3A_KQ0_SERVICE_GATE.json")
    assert set(baseline.job_id) == set(controlled.job_id)
    assert gate["passed"]
    assert gate["contract"] == "TIER_AWARE_HIGH_NORMAL_STANDBY"
    assert gate["deltas"]["high_normal_delay_count"] == 0
    assert gate["checks"]["standby_never_delays_high_or_normal"]


def test_no_fresh_run_without_exact_binding():
    grid = _json("V35R3A_KQ0_GRID_EFFECT.json")
    assert not grid["exact_grid_binding"]
    assert grid["Fresh_status"] == "GRID_BINDING_AUTHORITY_INCOMPLETE"
    assert not (ARTIFACTS / "V35R3A_FRESH_REVALIDATION.json").exists()


def test_pr1_is_separate_and_submission_side_only():
    replay = _json("V35R3A_PR1_POLICY_REPLAY.json")
    assert replay["status"] == "EXECUTED_SEPARATELY_FROM_KQ0"
    assert replay["submission_side_fields_only"]
    assert replay["future_actual_start_end_runtime_reads"] == 0
    assert not replay["combined_with_KQ0_authority"]


def test_production_science_preserved_and_no_merge_push():
    integration = _json("V35R3A_PRODUCTION_INTEGRATION_PLAN.json")
    impact = _json("V35R3A_WT_WST_TARGET_IMPACT.json")
    isolation = _json("V35R3A_ISOLATION_AUDIT.json")
    assert integration["production_files_modified"] == 0
    assert integration["PRODUCTION_CHANGE_RECOMMENDED"] == "NO"
    assert not impact["current_W_F_modified"]
    assert not isolation["push_performed"] and not isolation["merge_performed"]


def test_changes_are_confined_to_prototype_namespaces():
    output = subprocess.check_output(["git", "status", "--short"], cwd=REPO, text=True)
    allowed = (
        "dayahead/artifacts/v35r3a_kestrel_scheduler_temporal/",
        "dayahead/v35r3a/",
        "tools/v35r3a/",
        "tests/dayahead/test_v35r3a_",
    )
    for line in output.splitlines():
        path = line[3:].replace("\\", "/")
        assert path.startswith(allowed), path


def test_required_artifacts_exist():
    required = {
        "V35R3A_START_STATE.json",
        "V35R3A_ISOLATION_AUDIT.json",
        "V35R3A_DOWNLOADED_AUTHORITY_INVENTORY.json",
        "V35R3A_VENDOR_REPO_HEADS.json",
        "V35R3A_KESREL_SOURCE_AUDIT.json",
        "V35R3A_SCHEDULER_POLICY_AUTHORITY.json",
        "V35R3A_FIELD_CAUSALITY_AUDIT.csv",
        "V35R3A_CAUSALITY_LEDGER.csv",
        "V35R3A_APR01_QUEUE_SNAPSHOT.json",
        "V35R3A_WORKLOAD_CLASS_CENSUS.csv",
        "V35R3A_SCHEDULER_TWIN_CONTRACT.json",
        "V35R3A_BASELINE_FIDELITY.csv",
        "V35R3A_BASELINE_SCHEDULE.parquet",
        "V35R3A_BASELINE_SERVICE_METRICS.json",
        "V35R3A_CRITICAL_SET.json",
        "V35R3A_JOB_CRITICAL_EXPOSURE.parquet",
        "V35R3A_SITEFACTOR_POLICY.json",
        "V35R3A_PRIORITY_CHANGE_LOG.csv",
        "V35R3A_SEARCH_TRACE.csv",
        "V35R3A_KQ0_CONTROLLED_SCHEDULE.parquet",
        "V35R3A_KQ0_SERVICE_GATE.json",
        "V35R3A_KQ0_GRID_EFFECT.json",
        "V35R3A_PR1_POLICY_REPLAY.json",
        "V35R3A_WT_WST_TARGET_IMPACT.json",
        "V35R3A_PRODUCTION_INTEGRATION_PLAN.json",
        "V35R3A_INVALIDATION_FORECAST.json",
        "V35R3A_TEST_REPORT.json",
        "V35R3A_FINAL_REVIEW.json",
        "V35R3A_FINAL_REVIEW.md",
        "V35R3A_PRE_STANDBY_SEMANTICS_CORRECTION_DIAGNOSTIC.json",
        "V35R3A_PENDING_FIELD_AUDIT.parquet",
        "V35R3A_STANDBY_SEMANTICS_CORRECTION.json",
    }
    assert required <= {path.name for path in ARTIFACTS.iterdir()}


def test_primary_classification_is_recomputed_after_standby_correction():
    review = _json("V35R3A_FINAL_REVIEW.json")
    assert review["numbered_report"]["68"]["value"] != "V35R3A_KNOWN_QUEUE_TEMPORAL_MASS_INSUFFICIENT"
    assert review["numbered_report"]["68"]["value"].startswith("V35R3A_STANDBY_")
    assert len(review["standby_semantics_correction_addendum"]) == 14
    assert review["questions"]["Q8"].startswith("NO")
    assert review["questions"]["Q9"].startswith("NO")
