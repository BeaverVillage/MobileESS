"""Midnight source projection and fail-closed queue gate; no replay or solver."""
from copy import deepcopy

import pandas as pd
import pytest

from v42_integration.dday_boundary import (prefix_events, build_boundary_candidate,
    assert_full96_authority, DdayInitialStateBlocked, EXCLUSION_STATUS, ARMS)
from v42_integration.policy import digest


@pytest.fixture
def fixture():
    begin = pd.Timestamp("2025-05-01", tz="Etc/GMT-10").timestamp()
    issue = begin-21600
    def source(uid, gpu, submit, q50=900):
        return dict(job_uid=uid, GPU_gang=gpu, submit_time=submit,
            compatible_sites=["A", "B"], Q50_total_seconds=q50,
            source_member="fixture", source_row=len(uid))
    known = [source("gone1",2,issue-10000),source("gone2",1,issue-10000),
        source("fixed-running",4,issue-10000,50),source("fixed-completed",2,issue-10000),
        source("pending-started",1,issue-10000),source("pending-remains",1,issue-10000)]
    arrivals = [source("prefix-pending",1,begin-1200),source("future-submit",1,begin+900)]
    starts = {"gone1":issue-1800,"gone2":issue-900,"fixed-running":issue-900,
        "fixed-completed":issue-1000,"pending-started":begin-450,
        "pending-remains":begin+100,"prefix-pending":begin+100,"future-submit":begin+2000}
    ends = dict(gone1=begin-1,gone2=begin)
    ends.update({"fixed-running":begin+86400+900,"fixed-completed":begin-900,
        "pending-started":begin+1000,"pending-remains":begin+1000,
        "prefix-pending":begin+1000,"future-submit":begin+5000})
    truth = {uid:dict(start_time=start,end_time=ends[uid],realized_seconds=ends[uid]-start)
        for uid,start in starts.items()}
    native = dict(known_population=[dict(row,state="RUNNING" if i<4 else "PENDING",
        current_site_if_running=("A" if i==2 else "B" if i==3 else None),
        elapsed_seconds=issue-starts[row["job_uid"]] if i<4 else 0)
        for i,row in enumerate(known)])
    plan = dict(day="2025-05-01",issue_time=issue, known_population=known,
        capacities={"A":8,"B":8},rack_compatibility={"A":[8],"B":[8]})
    actual = dict(post_issue_arrivals=arrivals)
    return plan,native,actual,truth,begin


def build(fixture):
    plan,native,actual,truth,begin = fixture
    events = prefix_events(truth,plan["known_population"]+actual["post_issue_arrivals"],begin)
    return build_boundary_candidate(plan,native,actual,events,{"gone1","gone2"})


def test_pre_dday_excluded_original_uid_gang_preserved_zero_active(fixture):
    candidate,audit,excluded = build(fixture)
    assert {row["job_uid"] for row in excluded} == {"gone1","gone2"}
    assert sum(row["GPU_gang"] for row in excluded) == 3
    assert all(row["exclusion_status"]==EXCLUSION_STATUS and row["original_native_site"] is None
               and row["Dday_active_GPU"]==0 for row in excluded)
    assert all(not row["origin_unknown"] and not row["reregistered_as_unknown"]
               and row["cc4_depletion_at_boundary"]==0 for row in excluded)
    assert audit["excluded_Dday_IT_swing_contribution_kW"]==0
    assert audit["raw_population_jobs"]==8 and audit["observed_boundary_roster_jobs"]==7
    assert all(row["preserved_in_source_roster"] for row in candidate["initial_source_roster"])


def test_pending_roster_kept_and_prior_start_does_not_invent_site_or_queue(fixture):
    candidate,audit,_ = build(fixture)
    rows = {row["job_uid"]:row for row in candidate["initial_source_roster"]}
    assert audit["original_issue_pending_jobs"]==audit["original_issue_pending_roster_retained"]==2
    assert audit["PENDING_roster_deleted"]==0
    assert rows["pending-remains"]["boundary_source_state"]=="PENDING"
    assert rows["pending-started"]["boundary_source_state"]=="RUNNING"
    assert rows["pending-started"]["current_model_site"] is None
    assert rows["prefix-pending"]["origin_unknown"]
    assert rows["prefix-pending"]["cc4_depletion_at_boundary"]==0
    assert audit["active_running_unverified_site_jobs"]==1
    assert not audit["initial_queue_verified"] and not audit["full96_actual_authorized"]


def test_other_running_site_and_elapsed_service_preserved_q50_overrun_held(fixture):
    candidate,audit,_ = build(fixture)
    rows = {row["job_uid"]:row for row in candidate["initial_source_roster"]}
    running=rows["fixed-running"]
    assert running["current_model_site"]=="A" and running["Dday_active_GPU"]==4
    assert running["elapsed_compute_seconds_at_boundary"]==22500
    assert running["Q50_nominal_remaining_seconds"]==0
    assert running["boundary_source_state"]=="RUNNING"
    assert running["observed_completion_seconds"] is None
    assert running["private_realized_remaining_service"]=="PRESERVED_IN_SIMULATOR_ONLY_NOT_EXPOSED_HERE"
    assert rows["fixed-completed"]["original_native_site"]=="B"
    assert rows["fixed-completed"]["Dday_active_GPU"]==0
    assert audit["original_fixed_site_changes"]==0
    assert audit["initial_known_site_GPU_use"]=={"A":4,"B":0}


def test_future_post00_truth_changes_do_not_change_candidate_or_shared_sha(fixture):
    plan,native,actual,truth,begin=fixture
    before=deepcopy(fixture)
    expected=build(fixture)
    changed=deepcopy(truth)
    for values in changed.values():
        if values["start_time"]>begin:values["start_time"]+=100000
        if values["end_time"]>begin:values["end_time"]+=200000
        values["realized_seconds"]=-999
        values["future_queue"]="PRIVATE_POST00_OUTCOME"
    assert build((plan,native,actual,changed,begin))==expected
    candidate,audit,_=expected
    assert "future-submit" not in {r["job_uid"] for r in candidate["initial_source_roster"]}
    assert audit["Arm_initial_state_SHA"]=={arm:audit["common_initial_state_sha"] for arm in ARMS}
    assert digest({k:v for k,v in candidate.items() if k!="initial_state_sha"})==candidate["initial_state_sha"]
    assert fixture==before


def test_direct_future_event_or_missing_exclusion_not_admitted(fixture):
    plan,native,actual,truth,begin=fixture
    events=prefix_events(truth,plan["known_population"]+actual["post_issue_arrivals"],begin)
    events["fixed-running"]["observed_completion_seconds"]=begin+1
    with pytest.raises(ValueError,match="FUTURE_EVENT"):
        build_boundary_candidate(plan,native,actual,events,{"gone1","gone2"})
    events=prefix_events(truth,plan["known_population"]+actual["post_issue_arrivals"],begin)
    with pytest.raises(ValueError,match="EXCLUSION_ROSTER_INCOMPLETE"):
        build_boundary_candidate(plan,native,actual,events,{"gone1","gone2","absent"})


def test_no_exclusion_for_incomplete_running_or_new_site_assignment(fixture):
    plan,native,actual,truth,begin=fixture
    events=prefix_events(truth,plan["known_population"]+actual["post_issue_arrivals"],begin)
    with pytest.raises(ValueError,match="EXCLUSION_REQUIRES"):
        build_boundary_candidate(plan,native,actual,events,{"fixed-running"})
    native=deepcopy(native)
    native["known_population"][0]["current_site_if_running"]="A"
    with pytest.raises(ValueError,match="EXCLUSION_REQUIRES"):
        build_boundary_candidate(plan,native,actual,events,{"gone1","gone2"})


def test_initial_queue_candidate_cannot_be_promoted_by_pass_flag(fixture):
    _,audit,_=build(fixture)
    with pytest.raises(DdayInitialStateBlocked,match="INITIAL_QUEUE_UNVERIFIED"):
        assert_full96_authority(audit)
    with pytest.raises(DdayInitialStateBlocked):
        assert_full96_authority(dict(audit,full96_actual_authorized=True))
    assert audit["Native_Optimize_calls"]==audit["Actual_runs"]==audit["Fresh_AC_runs"]==0
    assert not audit["Apr30_queue_replay_performed"] and not audit["synthetic_initialization_used"]


def test_duplicate_or_incomplete_source_roster_and_fixed_capacity_fail_closed(fixture):
    plan,native,actual,truth,begin=fixture
    with pytest.raises(ValueError,match="DUPLICATE_SOURCE_UID"):
        prefix_events(truth,plan["known_population"]*2,begin)
    events=prefix_events(truth,plan["known_population"]+actual["post_issue_arrivals"],begin)
    incomplete=dict(events);incomplete.pop("pending-remains")
    with pytest.raises(ValueError,match="PREFIX_EVENT_ROSTER_INCOMPLETE"):
        build_boundary_candidate(plan,native,actual,incomplete,{"gone1","gone2"})
    changed=deepcopy(plan);changed["capacities"]["A"]=3
    with pytest.raises(ValueError,match="SITE_CAPACITY"):
        build_boundary_candidate(changed,native,actual,events,{"gone1","gone2"})
