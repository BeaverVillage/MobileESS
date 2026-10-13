"""May01 midnight boundary audit; no preday queue replay or new assignment.

Retrospective events are projected onto the boundary inside this audit. Only
events at or before midnight enter the candidate; private duration and future
completion values never become Planning inputs. Raw Kestrel job state does not
establish a modeled 12-AIDC site or queue, so this candidate fails closed.
"""
import argparse
from collections import Counter
import csv
import math
from pathlib import Path

import pandas as pd

from .actual_validation import read, record, checked, write
from .policy import digest

POLICY_ID = "PREDAY_COMPLETED_EXCLUDED_FROM_DDAY_ACTUAL_V1"
EXCLUSION_STATUS = "PRE_DDAY_COMPLETED_EXCLUDED_FROM_DDAY_ACTUAL"
QUEUE_STATUS = "INITIAL_QUEUE_UNVERIFIED"
ARMS = ("B0", "B1", "B2", "B3")


class DdayInitialStateBlocked(ValueError):
    def __init__(self, audit):
        self.audit = audit
        super().__init__("DDAY_FULL96_NOT_AUTHORIZED:" + audit["status"])


def assert_full96_authority(audit):
    """A consumer cannot convert an audit candidate into execution authority."""
    sha = audit.get("common_initial_state_sha")
    if (audit.get("full96_actual_authorized") is not True or
            audit.get("status") != "DDAY_INITIAL_STATE_AUTHORIZED" or
            audit.get("initial_queue_verified") is not True or
            audit.get("active_running_site_authority") is not True or not sha or
            audit.get("Arm_initial_state_SHA") != {arm: sha for arm in ARMS}):
        raise DdayInitialStateBlocked(audit)


def seconds(value):
    return float(value) if isinstance(value, (int, float)) else pd.Timestamp(value).timestamp()


def prefix_events(truth, population, boundary_seconds):
    """Private source projection; output contains no post-boundary values."""
    if len({r["job_uid"] for r in population}) != len(population):
        raise ValueError("DDAY_DUPLICATE_SOURCE_UID")
    output = {}
    for row in population:
        uid = row["job_uid"]
        submit = seconds(row["submit_time"])
        if submit > boundary_seconds:
            continue
        private = truth[uid]
        start, end = seconds(private["start_time"]), seconds(private["end_time"])
        if end < start or start < submit:
            raise ValueError("DDAY_PRIVATE_SOURCE_EVENT_ORDER")
        # No future timestamp or realized duration is retained. An absent event
        # means the boundary has not observed it, rather than a predicted time.
        output[uid] = dict(submit_seconds=submit,
            observed_start_seconds=start if start <= boundary_seconds else None,
            observed_completion_seconds=end if end <= boundary_seconds else None,
            event_source_member=row["source_member"], event_source_row=row["source_row"])
    return output


def build_boundary_candidate(plan, native, actual, events, excluded_uids, *, source_receipts=()):
    """Preserve complete observed roster without guessing AIDC queue or site.

    Original issue PENDING records remain in the boundary roster, with a raw
    source transition only when its start has already occurred. Model site is
    inherited only from original issue RUNNING location, never from R0/PR79 or
    synthetic initialization. Actual remaining service stays simulator-private.
    """
    issue = seconds(plan["issue_time"])
    begin = pd.Timestamp(plan["day"], tz="Etc/GMT-10").timestamp()
    end = begin + 86400
    source_known = {row["job_uid"]: row for row in plan["known_population"]}
    native_known = {row["job_uid"]: row for row in native["known_population"]}
    population = plan["known_population"] + actual["post_issue_arrivals"]
    if len(source_known) != len(plan["known_population"]) or len(native_known) != len(native["known_population"]):
        raise ValueError("DDAY_DUPLICATE_KNOWN_UID")
    if set(source_known) != set(native_known):
        raise ValueError("DDAY_PLANNING_NATIVE_UID_MISMATCH")
    expected = {row["job_uid"] for row in population if seconds(row["submit_time"]) <= begin}
    if set(events) != expected:
        raise ValueError("DDAY_PREFIX_EVENT_ROSTER_INCOMPLETE")
    if len({row["job_uid"] for row in population}) != len(population):
        raise ValueError("DDAY_DUPLICATE_POPULATION_UID")
    excluded_uids = set(excluded_uids)
    roster, exclusions, active_use = [], [], Counter()
    for source in sorted(population, key=lambda row: row["job_uid"]):
        uid = source["job_uid"]
        if uid not in expected:
            continue
        event = events[uid]
        start, completion = event["observed_start_seconds"], event["observed_completion_seconds"]
        if any(value is not None and value > begin for value in (start, completion)):
            raise ValueError("DDAY_FUTURE_EVENT_IN_BOUNDARY_INPUT")
        if event["submit_seconds"] != seconds(source["submit_time"]):
            raise ValueError("DDAY_SUBMISSION_SOURCE_DRIFT")
        if completion is not None and (start is None or completion < start):
            raise ValueError("DDAY_COMPLETION_WITHOUT_OBSERVED_START")
        original = native_known.get(uid)
        original_state = None if original is None else original["state"]
        original_site = None if original is None else original.get("current_site_if_running")
        if original is not None and original["GPU_gang"] != source["GPU_gang"]:
            raise ValueError("DDAY_ORIGINAL_GPU_GANG_CHANGED")
        if original_state == "RUNNING" and (start is None or
                abs(start - (issue - original["elapsed_seconds"])) > 1e-6):
            raise ValueError("DDAY_ORIGINAL_RUNNING_HISTORY_CHANGED")
        release = None if completion is None else math.ceil(completion / 900) * 900
        state = "COMPLETED" if completion is not None else "RUNNING" if start is not None else "PENDING"
        # Boundary is a 900-second aligned tick. Completion <=00 has released
        # by this tick under original PR125 control-release semantics.
        if completion is not None and release > begin:
            raise ValueError("DDAY_COMPLETED_CONTROL_RELEASE_NOT_REACHED")
        elapsed = None if start is None else (completion if completion is not None else begin) - start
        item = dict(job_uid=uid, source_state_at_issue=original_state or "NOT_YET_SUBMITTED_AT_PLANNING_ISSUE",
            boundary_source_state=state, GPU_gang=int(source["GPU_gang"]),
            origin_unknown=uid not in source_known, cc4_depletion_at_boundary=0,
            source_submit_seconds=event["submit_seconds"], observed_start_seconds=start,
            observed_completion_seconds=completion, observed_control_release_seconds=release,
            elapsed_compute_seconds_at_boundary=elapsed,
            frozen_Q50_total_seconds=source["Q50_total_seconds"],
            Q50_nominal_remaining_seconds=None if elapsed is None else max(source["Q50_total_seconds"]-elapsed, 0),
            private_realized_remaining_service="PRESERVED_IN_SIMULATOR_ONLY_NOT_EXPOSED_HERE",
            original_native_site=original_site,
            current_model_site=original_site if state == "RUNNING" else None,
            model_site_authority="ORIGINAL_SOURCE18R_RUNNING_SITE_PRESERVED" if state == "RUNNING" and original_site else
                "UNVERIFIED_12AIDC_SITE" if state == "RUNNING" else "NO_ACTIVE_SITE_REQUIRED",
            raw_Kestrel_observed_AIDC_site=None,
            compatible_sites=list(source["compatible_sites"]),
            source_member=source["source_member"], source_row=source["source_row"],
            initial_queue_order=None, initial_queue_authority=QUEUE_STATUS if state == "PENDING" else None,
            preserved_in_source_roster=True, excluded_from_Dday_active=state == "COMPLETED",
            Dday_active_GPU=int(source["GPU_gang"]) if state == "RUNNING" else 0,
            reference_site_or_synthetic_assignment_used=False)
        if uid in excluded_uids:
            if original_state != "RUNNING" or original_site is not None or completion is None or release > begin:
                raise ValueError("DDAY_EXCLUSION_REQUIRES_ORIGINAL_UNASSIGNED_COMPLETED_RUNNING")
            item["exclusion_status"] = EXCLUSION_STATUS
            item["reregistered_as_unknown"] = False
            item["Dday_IT_swing_contribution_kW"] = 0
            item["Dday_PCC_job_occupancy_contribution"] = 0
            exclusions.append(item.copy())
        if state == "RUNNING" and original_site is not None:
            if (original_site not in source["compatible_sites"] or original_site not in plan["capacities"]
                    or source["GPU_gang"] > max(plan["rack_compatibility"][original_site])):
                raise ValueError("DDAY_PRESERVED_SITE_GPU_RACK_CONTRACT")
            active_use[original_site] += source["GPU_gang"]
        roster.append(item)
    if {r["job_uid"] for r in exclusions} != excluded_uids:
        raise ValueError("DDAY_EXCLUSION_ROSTER_INCOMPLETE")
    if any(active_use[s] > plan["capacities"][s] for s in active_use):
        raise ValueError("DDAY_PRESERVED_RUNNING_SITE_CAPACITY")
    initial_running = [r for r in roster if r["boundary_source_state"] == "RUNNING"]
    pending = [r for r in roster if r["boundary_source_state"] == "PENDING"]
    unknown_sites = [r for r in initial_running if r["current_model_site"] is None]
    candidate = dict(schema="V42_DDAY_BOUNDARY_CANDIDATE_V1", policy_id=POLICY_ID,
        day=plan["day"], planning_issue_seconds=issue, Actual_begin_seconds=begin, Actual_end_seconds=end,
        slots=96, dt_seconds=900, initial_source_roster=roster,
        excluded_UIDs=sorted(excluded_uids), source_receipts=list(source_receipts),
        independent_12AIDC_queue_authority=False, independent_12AIDC_boundary_snapshot=False,
        Apr30_queue_replay_performed=False, new_site_assignment_calls=0,
        post_D00_arrival_UIDs_in_candidate=False, private_future_runtime_or_completion_values_in_candidate=False)
    initial_sha = digest(candidate)
    candidate["initial_state_sha"] = initial_sha
    counts = Counter(r["source_state_at_issue"]+":"+r["boundary_source_state"] for r in roster)
    gpu_counts = {key: sum(r["GPU_gang"] for r in roster
                          if r["source_state_at_issue"]+":"+r["boundary_source_state"] == key) for key in counts}
    issue_pending = {uid for uid, row in native_known.items() if row["state"] == "PENDING"}
    fixed = {uid: row["current_site_if_running"] for uid, row in native_known.items()
             if row["state"] == "RUNNING" and row.get("current_site_if_running") is not None}
    audit = dict(schema="V42_DDAY_INITIAL_STATE_AUDIT_V1", policy_id=POLICY_ID, day=plan["day"],
        status=QUEUE_STATUS, full96_actual_authorized=False, initial_state_sha=initial_sha,
        common_initial_state_sha=initial_sha, initial_queue_verified=False,
        active_running_site_authority=not unknown_sites,
        day_begin_epoch_seconds=begin, end_epoch_seconds=end, excluded_44uids=sorted(excluded_uids),
        Arm_initial_state_SHA={arm: initial_sha for arm in ARMS},
        evaluation_begin_UTC=pd.Timestamp(begin, unit="s", tz="UTC").isoformat(),
        evaluation_end_UTC=pd.Timestamp(end, unit="s", tz="UTC").isoformat(),
        evaluation_fixed_AEST="2025-05-01T00:00:00+10:00..2025-05-02T00:00:00+10:00" if plan["day"] == "2025-05-01" else None,
        evaluation_slots=96, raw_population_jobs=len(population),
        observed_boundary_roster_jobs=len(roster), active_running_jobs=len(initial_running),
        active_running_GPU=sum(r["GPU_gang"] for r in initial_running),
        active_running_preserved_site_jobs=len(initial_running)-len(unknown_sites),
        active_running_preserved_site_GPU=sum(r["GPU_gang"] for r in initial_running if r["current_model_site"]),
        active_running_unverified_site_jobs=len(unknown_sites),
        active_running_unverified_site_GPU=sum(r["GPU_gang"] for r in unknown_sites),
        initial_pending_jobs=len(pending), initial_pending_GPU=sum(r["GPU_gang"] for r in pending),
        completed_by_boundary_jobs=sum(r["boundary_source_state"] == "COMPLETED" for r in roster),
        state_transition_counts=dict(counts), state_transition_GPU=gpu_counts,
        original_issue_pending_jobs=len(issue_pending), original_issue_pending_roster_retained=len(issue_pending.intersection(expected)),
        PENDING_roster_deleted=0, original_fixed_site_records_preserved=len(fixed), original_fixed_site_changes=0,
        excluded_pre_Dday_jobs=len(exclusions), excluded_pre_Dday_GPU=sum(r["GPU_gang"] for r in exclusions),
        excluded_Dday_active_GPU=0, excluded_Dday_IT_swing_contribution_kW=0,
        excluded_unknown_reregistrations=0, excluded_CC4_depletions=0, duplicated_UIDs=0,
        initial_known_site_GPU_use={s: active_use[s] for s in sorted(plan["capacities"])},
        preserved_site_capacity_and_per_gang_rack_check=True,
        full_12AIDC_GPU_rack_check="NOT_ESTABLISHED_FOR_UNVERIFIED_RUNNING_SITES",
        independent_D00_12AIDC_queue_order="UNAVAILABLE", initial_queue_status=QUEUE_STATUS,
        full96_blockers=[QUEUE_STATUS]+(["INITIAL_RUNNING_12AIDC_SITE_UNVERIFIED"] if unknown_sites else []),
        raw_source_state_is_not_modeled_AIDC_assignment=True,
        source_completion_events_projected_only_at_or_before_D00=True,
        private_future_completion_values_delivered_to_Planning=0, source_receipts=list(source_receipts),
        Apr30_queue_replay_performed=False, synthetic_initialization_used=False,
        R0_or_PR79_reference_regenerated=False, Native_Optimize_calls=0, Actual_runs=0, Fresh_AC_runs=0,
        original_raw_files_modified=0, carryover_service_and_Q50_overrun_not_released=True)
    return candidate, audit, exclusions


def audit_dday_initial_state(folder, output=None, *, previous_boundary_audit=None, previous_exclusion_ledger=None):
    """Re-audit exact source events and save the requested non-executable gate."""
    from v42_voltage_control.b0_new import _truth
    folder = Path(folder)
    output = None if output is None else Path(output)
    names = ("PLANNING_INPUT_BUNDLE.json", "ACTUAL_INPUT_BUNDLE.json", "NATIVE_INPUT_TEMPLATE_B1.json", "SOURCE_PROVENANCE.json")
    plan, actual, native, provenance = [read(folder/name) for name in names]
    receipts = [record(folder/name) for name in names]
    population = plan["known_population"]+actual["post_issue_arrivals"]
    if plan["day"] != actual["day"] or plan["capacities"] != actual["capacities"]:
        raise ValueError("DDAY_PLANNING_ACTUAL_SOURCE_CASE_DRIFT")
    truth, archive = _truth(population, provenance["archive"])
    receipts.append(archive)
    begin = pd.Timestamp(plan["day"], tz="Etc/GMT-10").timestamp()
    events = prefix_events(truth, population, begin)
    exclusions = {r["job_uid"] for r in native["known_population"]
                  if r["state"] == "RUNNING" and r["current_site_if_running"] is None}
    previous_rows = {}
    independent_inventory = []
    historical_replay_rejections = []
    if previous_exclusion_ledger is not None:
        with Path(previous_exclusion_ledger).open(encoding="utf-8-sig", newline="") as stream:
            previous_rows = {r["job_uid"]: r for r in csv.DictReader(stream)}
        if set(previous_rows) != exclusions:
            raise ValueError("DDAY_PREVIOUS_AUDITED_44_IDENTITY_DRIFT")
        receipts.append(record(previous_exclusion_ledger))
    if previous_boundary_audit is not None:
        previous = read(previous_boundary_audit)
        if previous["day"] != plan["day"] or previous["missing_Dday_GPUh"] != 0:
            raise ValueError("DDAY_PREVIOUS_COMPLETION_BOUNDARY_AUDIT_DRIFT")
        independent_inventory = previous.get("independent_D00_state_inventory", [])
        historical_replay_rejections = previous.get("historical_policy_replays", [])
        receipts.append(record(previous_boundary_audit))
    reference_path = checked(native["reference"])
    reference = {r["job_uid"]: r for r in read(reference_path)}
    receipts.append(record(reference_path))
    candidate, audit, ledger = build_boundary_candidate(plan, native, actual, events, exclusions, source_receipts=receipts)
    if len(exclusions) != 44 or sum(r["GPU_gang"] for r in ledger) != 59:
        raise ValueError("DDAY_MAY01_44_UID_59_GPU_DRIFT")
    for row in ledger:
        prior = previous_rows.get(row["job_uid"], {})
        row.update(exclusion_status=EXCLUSION_STATUS,
            observed_start_UTC=pd.Timestamp(row["observed_start_seconds"], unit="s", tz="UTC").isoformat(),
            observed_completion_UTC=pd.Timestamp(row["observed_completion_seconds"], unit="s", tz="UTC").isoformat(),
            observed_control_release_UTC=pd.Timestamp(row["observed_control_release_seconds"], unit="s", tz="UTC").isoformat(),
            prior_episode_id_evidence=prior.get("episode_id") or None,
            prior_recovered_model_site_evidence_only=prior.get("recovered_model_site") or None,
            prior_site_recovery_source_audit_sha=prior.get("recovery_source_audit_sha") or None,
            prior_recovered_site_connected_to_new_Actual=False,
            original_reference_expected_end_issue_slot=reference[row["job_uid"]]["end_slot"],
            original_reference_expected_end_is_actual=False,
            actual_source_sha=archive["sha256"], native_source_sha=receipts[2]["sha256"])
    candidate_receipt = ledger_receipt = None
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        ledger_path = output/"PREDAY_COMPLETED_EXCLUSION_LEDGER.csv"
        with ledger_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(ledger[0]))
            writer.writeheader()
            writer.writerows(ledger)
        candidate_path = output/"DDAY_INITIAL_STATE_CANDIDATE.json"
        write(candidate_path, candidate)
        candidate_receipt, ledger_receipt = record(candidate_path), record(ledger_path)
    audit.update(boundary_candidate=candidate_receipt, exclusion_ledger=ledger_receipt,
        boundary_event_source=archive, exact_private_source_join_count=len(truth),
        real_scheduler_observation_watermark=None,
        source_completion_visibility_contract="SOURCE_TRACE_EVENTS_ONLY_WHEN_SIMULATOR_CLOCK_REACHES_EVENT",
        current_initial_state_is_a_candidate_not_execution_authority=True,
        prior_independent_D00_snapshot_search=independent_inventory,
        historical_policy_specific_replays_not_promoted=historical_replay_rejections)
    if output is not None:
        write(output/"DDAY_INITIAL_STATE_AUDIT.json", audit)
    causal = dict(schema="V42_PLANNING_ACTUAL_CAUSAL_BOUNDARY_AUDIT_V1", policy_id=POLICY_ID,
        day=plan["day"], planning_issue_seconds=seconds(plan["issue_time"]), Actual_begin_seconds=begin,
        Actual_end_seconds=begin+86400, Actual_slots=96, initial_state_sha=candidate["initial_state_sha"],
        Planning_source=receipts[0], original_native_source=receipts[2], original_reference=record(reference_path),
        original_Planning_44_expected_Dday_inactive_jobs=sum(reference[uid]["end_slot"] <= 24 for uid in exclusions),
        Planning_inactivity_authority="UNCHANGED_ISSUE_TIME_REFERENCE_EXPECTED_END_ONLY",
        Actual_exclusion_authority="OBSERVED_SOURCE_COMPLETION_AND_CONTROL_RELEASE_AT_OR_BEFORE_DDAY_00",
        real_scheduler_observation_watermark=None, raw_Kestrel_12AIDC_queue_authority=False,
        actual_post_D00_events_delivered_to_boundary=0, actual_completion_values_delivered_to_Planning=0,
        private_realized_remaining_service_delivered_to_Planning=0,
        future_post_D00_arrival_UIDs_delivered_to_boundary=0,
        excluded_UIDs_reclassified_as_Unknown=0, excluded_UIDs_CC4_depletions=0,
        issue_PENDING_source_records_retained=audit["original_issue_pending_roster_retained"],
        Apr30_18_to_24_queue_replay_performed=False, Apr30_queue_accuracy_claimed=False,
        new_AIDC_site_assignment_calls=0, synthetic_initialization_used=False,
        old_reference_regeneration_calls=0, initial_Arm_SHA=audit["Arm_initial_state_SHA"],
        initial_queue_status=QUEUE_STATUS, full96_actual_authorized=False,
        remaining_service_simulator_private=True, Q50_expiry_is_not_GPU_release=True,
        out_of_Dday_scope_execution_certified=False, Native_Optimize_calls=0, Actual_runs=0, Fresh_AC_runs=0,
        old_campaign_or_monitor_modified=False, source_receipts=receipts)
    if output is not None:
        write(output/"PLANNING_ACTUAL_CAUSAL_BOUNDARY_AUDIT.json", causal)
    if any(record(receipt["path"]) != receipt for receipt in receipts):
        raise ValueError("DDAY_INPUT_SOURCE_CHANGED_DURING_AUDIT")
    return audit


def audit_dday_state(folder, output=None):
    """Public source-audited execution gate, with optional evidence outputs."""
    docs = Path(__file__).parents[1]/"docs/v42_common_am_qos_integration"
    boundary = docs/"PREDAY_DDAY_BOUNDARY_AUDIT.json"
    ledger = docs/"UNASSIGNED_RUNNING_44_LEDGER.csv"
    return audit_dday_initial_state(folder, output,
        previous_boundary_audit=boundary if boundary.is_file() else None,
        previous_exclusion_ledger=ledger if ledger.is_file() else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--previous-boundary-audit")
    parser.add_argument("--previous-exclusion-ledger")
    args = parser.parse_args()
    result = audit_dday_initial_state(args.folder, args.output,
        previous_boundary_audit=args.previous_boundary_audit, previous_exclusion_ledger=args.previous_exclusion_ledger)
    print({key: result[key] for key in ("status", "excluded_pre_Dday_jobs", "excluded_pre_Dday_GPU",
        "active_running_jobs", "initial_pending_jobs", "active_running_unverified_site_jobs", "full96_actual_authorized")})


if __name__ == "__main__":
    main()
