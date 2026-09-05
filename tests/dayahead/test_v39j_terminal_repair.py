"""Boundary equivalence, source/IO isolation, and exact analytic certificates."""
import ast
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from dayahead.v39j import terminal as t
from dayahead.tools import run_v39j_terminal_repair as j


def row(uid="a",start=1,duration=3,site="AIDC01",gpu=2,latest=8,eligible=True):
    return dict(job_uid=uid,job_id=uid,state_at_issue="PENDING",initial_AIDC="",
        requested_gpus=gpu,RSP_duration_slots=duration,RSP_duration_seconds=duration*900,
        RSP_scheduled_start=start,RSP_scheduled_completion=start+duration,
        RW_scheduled_completion=latest+duration,latest_start=latest,eligible=eligible,
        baseline_terminal_site=site)


def candidate(a):
    b=a.copy()
    b["scheduled_start_slot"]=a.RSP_scheduled_start
    b["scheduled_end_slot"]=a.RSP_scheduled_completion
    b["duration_slots"]=a.RSP_duration_slots
    b["terminal_site_state"]=a.baseline_terminal_site
    return b


def explicit(start,duration,site,boundary=5):
    return {(slot,site) for slot in range(max(start,boundary),start+duration)}


def test_compact_equivalent_to_full_per_slot_site_profile_exhaustively():
    for start,duration,new_start,site,new_site in itertools.product(
            range(9),range(1,6),range(13),("A","B",t.UNASSIGNED),("A","B",t.UNASSIGNED)):
        full=explicit(start,duration,site)==explicit(new_start,duration,new_site)
        assert full == t.compact_allowed(start,duration,site,new_start,new_site,boundary=5)


def test_baseline_in_day_cannot_finish_after_H_and_can_finish_at_H():
    assert t.compact_allowed(110,5,"A",115,"B")
    assert not t.compact_allowed(110,5,"A",116,"A")


@pytest.mark.parametrize("start",[115,120,130])
def test_legitimate_overnight_work_kept_exactly(start):
    assert t.compact_allowed(start,10,"A",start,"A")
    assert not t.compact_allowed(start,10,"A",start+1,"A")
    assert not t.compact_allowed(start,10,"A",start,"B")


def test_post_H_UNASSIGNED_cannot_acquire_physical_site():
    a=pd.DataFrame([row(start=120,duration=3,site=t.UNASSIGNED,latest=150,eligible=False)])
    b=candidate(a)
    assert t.terminal_audit(a,b)[1]["PASS"]
    b.loc[0,"terminal_site_state"]="AIDC01"
    assert t.terminal_audit(a,b)[1]["POST_H_SITE_STATE_CHANGED_JOBS"]==1


def test_aggregate_cancellation_cannot_hide_job_changes():
    a=pd.DataFrame([row("a",118,2,latest=125),row("b",119,2,latest=125)])
    b=candidate(a)
    b.loc[0,["scheduled_start_slot","scheduled_end_slot"]]=[119,121]
    b.loc[1,["scheduled_start_slot","scheduled_end_slot"]]=[118,120]
    audit=t.terminal_audit(a,b)[1]
    assert audit["INCREMENTAL_POST_MIDNIGHT_GPU_H_FROM_REPAIR"]==0
    assert audit["POST_H_RESERVATION_PROFILE_CHANGED_JOBS"]==2
    assert not audit["PASS"]


def test_equal_tail_GPU_hours_do_not_hide_tail_shift():
    a=pd.DataFrame([row(start=122,duration=3,latest=130)])
    b=candidate(a)
    b.loc[0,["scheduled_start_slot","scheduled_end_slot"]]=[125,128]
    audit=t.terminal_audit(a,b)[1]
    assert audit["INCREMENTAL_POST_MIDNIGHT_GPU_H_FROM_REPAIR"]==0
    assert audit["POST_H_RESERVATION_PROFILE_CHANGED_JOBS"]==1


@pytest.mark.parametrize("field,new",[("duration_slots",4),("RSP_duration_seconds",2699),("requested_gpus",3)])
def test_safe_runtime_and_GPU_requests_exact(field,new):
    a=pd.DataFrame([row()]);b=candidate(a);b.loc[0,field]=new
    assert not t.terminal_audit(a,b)[1]["PASS"]


def test_RW_completion_noninferiority():
    a=pd.DataFrame([row(start=10,duration=3,latest=12)]);b=candidate(a)
    b.loc[0,["scheduled_start_slot","scheduled_end_slot"]]=[13,16]
    audit=t.terminal_audit(a,b)[1]
    assert not audit["RW_COMPLETION_NONINFERIORITY_PASS"]
    assert audit["NEW_RW_COMPLETION_VIOLATIONS"]==1


def test_cohorts_split_distinct_terminal_site_and_safe_seconds():
    rows=[row("a",115,10,"A",latest=140),row("b",115,10,"B",latest=140),
          row("c",120,10,t.UNASSIGNED,latest=140),row("d",115,10,"A",latest=140)]
    rows[3]["RSP_duration_seconds"]=8999
    cs=t.terminal_cohorts(pd.DataFrame(rows))
    assert len(cs)==4
    assert all(c["hi"]==c["lo"] for c in cs)
    assert {c["terminal_category"] for c in cs}=={"CROSS_BOUNDARY","POST_H_ONLY"}


def test_post_H_model_option_does_not_invent_AIDC():
    a=pd.DataFrame([row(start=120,duration=10,site=t.UNASSIGNED,latest=140,eligible=False)])
    c=t.terminal_cohorts(a)[0]
    assert list(j.terminal_options(c,("AIDC01","AIDC02")))==[(t.UNASSIGNED,120)]
    bundle=dict(cohorts=[c],variables={(0,t.UNASSIGNED,120):SimpleNamespace(X=1.0)})
    b=j.expand_schedule(a,bundle)
    assert b.AIDC.tolist()==[t.UNASSIGNED]
    assert b.scheduled_start_slot.tolist()==[120]


def test_upper_bound_valid_for_all_small_terminal_safe_schedules():
    # Use H=120 with three short intervals near the boundary. Exhaust every
    # duration/GPU combination and every allowed integer start tuple.
    for durations in itertools.product((1,2,3),repeat=3):
        a=pd.DataFrame([row(str(k),s,d,latest=123,gpu=k+1)
                        for k,(s,d) in enumerate(zip((115,118,120),durations))])
        bound=t.primary_upper_certificate(a,0)["terminal_domain_objective_upper"]
        ranges=[range(int(r.RSP_scheduled_start),t.terminal_latest(int(r.RSP_scheduled_start),int(r.RSP_duration_slots),int(r.latest_start))+1) for r in a.itertuples()]
        actual_max=0
        for starts in itertools.product(*ranges):
            total=0
            for r,s in zip(a.itertuples(),starts):
                base=set(range(int(r.RSP_scheduled_start),int(r.RSP_scheduled_completion)))
                new=set(range(s,s+int(r.RSP_duration_slots)))
                total+=int(r.requested_gpus)*len(base.symmetric_difference(new))
            assert total<=bound
            actual_max=max(actual_max,total)
        assert actual_max<=bound


def test_original_objective_has_factor_two_and_no_site_term():
    for base,d,delta,g in itertools.product(range(4),range(1,6),range(8),range(1,4)):
        explicit_cost=g*len(set(range(base,base+d)) ^ set(range(base+delta,base+delta+d)))
        assert explicit_cost==j.h.v39g.occupancy_cost(base,d,base+delta,g)


def test_analytic_inequality_requires_strict_upper_below_old_lower():
    a=pd.DataFrame([row(start=118,duration=2,latest=123)])
    assert t.primary_upper_certificate(a,1)["infeasible_by_lower_greater_than_upper"]
    assert not t.primary_upper_certificate(a,0)["infeasible_by_lower_greater_than_upper"]


def test_three_day_scope_only():
    assert t.DAYS==("2025-05-24","2025-05-25","2025-05-26")
    for day in ("2025-05-17","2025-05-23","2025-05-27"):
        with pytest.raises(AssertionError):j.prepare(day)


def test_no_live_write_or_Actual_Fresh_other_day_input():
    for path in (r"C:\codex_mobileess_workspace\MobileESS_v39a_causal_aidc\dayahead\x.py",j.REPO/"x.json"):
        with pytest.raises(PermissionError):j.guard_path(path,writing=True)
    for path in (j.REPO/"actual/result.json",j.REPO/"fresh/result.npz",j.REPO/"data/2025-05-27.parquet"):
        with pytest.raises(PermissionError):j.guard_path(path)
    j.guard_path(j.ROOT/"tests/result.json",writing=True)


def test_runtime_budget_reserves_production_threads():
    workers=[dict(day=f"2025-05-{d:02}") for d in (10,11,12,13)]
    assert not j.numerical_capacity_available(workers,set())
    assert j.numerical_capacity_available(workers,{"2025-05-13"})


def test_no_migration_solver_or_campaign_execution_path():
    tree=ast.parse(Path(j.__file__).read_text(encoding="utf-8"))
    names={node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id
           for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,(ast.Name,ast.Attribute))}
    assert not names.intersection({"optimize","run_campaign","run_preflight","solve_migration","kill","terminate"})


def test_accepted_source_snapshot_matches_seal():
    m=j.read(j.ROOT/"V39J_SOURCE_AUTHORITY_MANIFEST.json")
    assert m["V39J_SOURCE_BASE"]=="SEALED_ACCEPTED_PRODUCTION_SOURCE_SNAPSHOT"
    assert all(j.sha(j.REPO/name)==expected for name,expected in m["accepted_source_SHA256"].items())


def test_live_source_and_May17_May23_authorities_unchanged():
    m=j.read(j.ROOT/"V39J_SOURCE_AUTHORITY_MANIFEST.json");live=Path(m["LIVE_ROOT"])
    assert all(j.sha(live/name)==expected for name,expected in m["live_source_SHA256"].items())
    protected={n:s for n,s in m["sealed_live_authority_SHA256"].items() if "2025-05-17" in n or "2025-05-23" in n}
    assert protected and all(j.sha(live/n)==s for n,s in protected.items())


def test_independent_capacity_checker_rejects_fabricated_or_duplicate_jobs():
    a=pd.DataFrame([row(start=115,duration=10,site="A",gpu=2,latest=130)])
    rsp={"AIDC_assignments":[dict(job_uid="a",state_at_issue="PENDING",migration_selected=False,destination_AIDC="A")]}
    proof=t.mandatory_capacity_certificate(a,{"A":1})
    assert j.verify_capacity_proof(a,rsp,proof,{"A":1})["status"]=="PASS"
    proof["violations"][0]["jobs"].append(proof["violations"][0]["jobs"][0])
    with pytest.raises(AssertionError):j.verify_capacity_proof(a,rsp,proof,{"A":1})


def test_analytic_days_never_construct_a_Gurobi_model(monkeypatch,tmp_path):
    # Execute the real dispatch, bound, and independent capacity checker.
    # Numerical verification is stubbed here; real fallback verification is
    # performed by the certification run and checked separately below.
    a=pd.DataFrame([row(start=115,duration=10,site="A",gpu=2,latest=130)])
    old=candidate(a)
    old["start_delay_slots"]=0
    rsp={"AIDC_assignments":[dict(job_uid="a",state_at_issue="PENDING",migration_selected=False,destination_AIDC="A")]}
    out=tmp_path;cap=SimpleNamespace(site_capacity={"A":1})
    monkeypatch.setattr(j,"ROOT",tmp_path)
    monkeypatch.setattr(j,"read",lambda _:dict(PRIMARY_OBJECTIVE_IDENTITY_PASS="YES",exact_J="test",witnesses=[dict(day=d) for d in t.DAYS]))
    monkeypatch.setattr(j,"prepare",lambda _: (a,old,rsp,out))
    monkeypatch.setattr(j.h,"_load_capacity",lambda _: (cap,{}))
    monkeypatch.setattr(j,"verifier_bundle",lambda _:dict(capacity=cap))
    monkeypatch.setattr(j,"verify_fallback",lambda *args:dict(terminal={"PASS":True},grid={"pass":True}))
    def forbidden(*args,**kwargs):raise AssertionError("Gurobi called despite analytic contradiction")
    monkeypatch.setattr(j,"build_model",forbidden)
    monkeypatch.setattr(j.h.gp,"Model",forbidden)
    for day in t.DAYS[1:]:
        result=j.run_day(day)
        assert result["Gurobi_optimize_calls"]==result["Gurobi_models_assembled"]==0
        assert result["TERMINAL_SAFE_REPAIR"]=="INFEASIBLE_PROVEN_ANALYTICALLY"
