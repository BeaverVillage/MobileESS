"""Capacity authority, adversarial ledger mutations and independent accounting."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from dayahead.paper_analysis.storage import read
from dayahead.v40d_actual.capacity_audit import (EXPECTED, VECTOR, SITES, require_current_capacity,
    recalculate_occupancy, compare_occupancy, check_it_power, audit_gangs, headroom_rows)
from dayahead.v40d_actual.contracts import ReplayError
from dayahead.v40d_actual.rack_dispatch import Rack, RackDispatcher
from dayahead.v40d_actual.job_replay import replay_jobs
from dayahead.v40d_actual.inputs import capacity, frozen_jobs, legacy_digest

REPO = Path(__file__).resolve().parents[1]
ISSUE = datetime(2025,4,30,18,tzinfo=timezone(timedelta(hours=10)))
RACKS = [Rack(s,f"{s}_LP{r:02d}",EXPECTED[s]) for s in SITES for r in range(1,5)]


def j(uid, gpu, site="AIDC01", start=24, **kw):
    return {"job_uid":uid,"requested_GPU":gpu,"AIDC_site":site,"state_at_issue":"PENDING",
        "start_slot":start,"end_slot":start+1,"qos":"normal","submit_time":ISSUE.isoformat(),
        "requested_walltime_seconds":900,"migration_selected":False,"Rack_label":None,
        "accepted_A0_assignment_and_WAN":{},**kw}


def execute(jobs, seconds=2700):
    obs={r["job_uid"]:{"start_time":ISSUE+timedelta(days=2),
        "end_time":ISSUE+timedelta(days=2,seconds=seconds),"gpus_requested":r["requested_GPU"]} for r in jobs}
    return replay_jobs(jobs,obs,issue_time=ISSUE,site_capacity=EXPECTED,racks=RACKS)


@pytest.mark.parametrize("site,cap", [("AIDC01",64),("AIDC02",32),("AIDC05",80)])
def test_exact_site_boundary_admitted(site,cap):
    x=execute([j("a",cap,site)])
    occ,_,_=compare_occupancy(x,EXPECTED)
    assert occ[0,SITES.index(site)] == cap


@pytest.mark.parametrize("site,cap", [("AIDC01",64),("AIDC02",32),("AIDC05",80)])
def test_one_gpu_over_site_cap_waits_at_same_site(site,cap):
    jobs=[j("a",cap,site),j("b",1,site,start=25)]
    x=execute(jobs)
    b=x["job_ledger"][1]
    assert b["actual_execution_start"]==27 and b["AIDC_site"]==site
    assert b["delayed_by_GPU_capacity"]
    occ,_,_=compare_occupancy(x,EXPECTED)
    assert occ[:,SITES.index(site)].max()==cap
    assert audit_gangs(jobs,x,RACKS)["ACTUAL_GANG_SPLIT_COUNT"]==0


def test_sixty_active_plus_eight_gang_waits_whole():
    jobs=[j("a",60),j("b",8,start=25)]
    x=execute(jobs)
    occ,_,_=compare_occupancy(x,EXPECTED)
    assert occ[:3,0].tolist()==[60,60,60] and occ[3,0]==8
    assert x["job_ledger"][1]["actual_execution_start"]==27
    assert audit_gangs(jobs,x,RACKS)["status"]=="PASS"


def test_running_overrun_not_truncated_to_planned_end():
    jobs=[j("a",64,start=0,state_at_issue="RUNNING",end_slot=25),j("b",8,start=25)]
    obs={"a":{"start_time":ISSUE-timedelta(hours=1),"end_time":ISSUE+timedelta(hours=8),"gpus_requested":64},
         "b":{"start_time":ISSUE+timedelta(days=1),"end_time":ISSUE+timedelta(days=1,hours=1),"gpus_requested":8}}
    x=replay_jobs(jobs,obs,issue_time=ISSUE,site_capacity=EXPECTED,racks=RACKS)
    assert x["job_ledger"][1]["actual_execution_start"]==32
    occ,_,_=compare_occupancy(x,EXPECTED)
    assert occ[:8,0].tolist()==[64]*8


def test_alternate_site_is_hard_failure_in_dispatcher_and_audit():
    d=RackDispatcher(EXPECTED,RACKS)
    with pytest.raises(ReplayError,match="ALTERNATE_AIDC"):
        d.admit(j("a",8,site="AIDC02",frozen_AIDC_site="AIDC01"),24,25,())
    x=execute([j("a",8)]);x["job_ledger"][0]["AIDC_site"]="AIDC02"
    with pytest.raises(ReplayError,match="ALTERNATE_AIDC"):
        recalculate_occupancy(x["job_ledger"])


def test_four_rack_labels_cannot_multiply_site_capacity():
    d=RackDispatcher(EXPECTED,RACKS)
    assert d.admit(j("a",64),24,30,())[0] is not None
    assert d.admit(j("b",1),24,30,())[0] is None
    changed={s:c*4 for s,c in EXPECTED.items()}
    with pytest.raises(ReplayError,match="CURRENT_SITE_CAPACITY"):
        require_current_capacity(changed)


def test_compatibility_labels_never_create_capacity_or_false_bins():
    d=RackDispatcher({"AIDC01":64},[Rack("AIDC01","R",8)])
    for k in range(8):
        assert d.admit(j(str(k),8),24,30,())[0]=="R"
    assert d.admit(j("overflow",1),24,30,())[0] is None
    with pytest.raises(ReplayError,match="GANG_EXCEEDS"):
        RackDispatcher({"AIDC01":64},[Rack("AIDC01","R",4)]).admit(j("g",8),24,30,())


def test_pre_day_complete_is_absent_and_injected_interval_hard_fails():
    row=j("p",4,site="UNASSIGNED",start=0,end_slot=24)
    obs={"p":{"start_time":ISSUE,"end_time":ISSUE+timedelta(hours=6),"gpus_requested":4}}
    x=replay_jobs([row],obs,issue_time=ISSUE,site_capacity=EXPECTED,racks=RACKS)
    occ,_,_=compare_occupancy(x,EXPECTED)
    assert occ.sum()==0
    x["job_ledger"][0]["actual_residual_start"]=24
    with pytest.raises(ReplayError,match="PRE_DAY_COMPLETE_GPU"):
        recalculate_occupancy(x["job_ledger"])


def test_independent_recalculation_detects_missing_and_double_counted_gpu():
    x=execute([j("a",8)])
    assert compare_occupancy(x,EXPECTED)[2]["max_abs_gpu_occupancy_error"]==0
    bad=deepcopy(x);bad["site_occupancy"][0]["occupied_GPU_slots"]+=8
    with pytest.raises(ReplayError,match="RECALCULATION_MISMATCH"):
        compare_occupancy(bad,EXPECTED)
    bad=deepcopy(x);bad["job_ledger"].append(deepcopy(bad["job_ledger"][0]))
    with pytest.raises(ReplayError,match="UID_DUPLICATE"):
        recalculate_occupancy(bad["job_ledger"])
    bad=deepcopy(x);bad["site_occupancy"].append(deepcopy(bad["site_occupancy"][0]))
    with pytest.raises(ReplayError,match="AXIS_DUPLICATE"):
        compare_occupancy(bad,EXPECTED)


def test_capacity_sha_exact_vector_and_site_denominators():
    a,cap,_,ref=capacity(REPO)
    assert tuple(a["frozen_V39C_site_capacity"].values())==VECTOR and sum(VECTOR)==624
    assert cap["canonical_SHA256"]=="6af48aa50f4cfbaa42f40eedb966fdc99c77656ec5a415c2d84089baccfb99ce"
    wrong=dict(EXPECTED);wrong["AIDC01"]-=1;wrong["AIDC02"]+=1
    with pytest.raises(ReplayError,match="CURRENT_SITE_CAPACITY"):
        require_current_capacity(wrong)


def test_analytic_gpu_power_identity_and_injected_wrong_coefficients():
    from dayahead.v39a.power import site_it_power_kw
    rng=np.random.default_rng(20)
    occ=np.column_stack([rng.integers(0,c+1,96) for c in VECTOR])
    it=np.asarray([[float(site_it_power_kw(c,int(n))) for c,n in zip(VECTOR,row)] for row in occ])
    a=check_it_power(EXPECTED,occ,it)
    assert a["GPU_TO_IT_POWER_MAX_ERROR_KW"]==0
    assert a["aggregate_analytic_max_error_kW"]<=float(a["preregistered_tolerance_kW"])
    it[0,0]+=1e-8
    with pytest.raises(ReplayError,match="POWER_CONSERVATION_FAIL"):
        check_it_power(EXPECTED,occ,it)


def test_facility_weights_are_not_called_by_capacity_or_power(monkeypatch):
    import dayahead.v39a.power as p
    def forbidden(*a,**k):
        raise AssertionError("facility weight must not enter admission capacity")
    monkeypatch.setattr(p,"_site_weights",forbidden)
    a,_,*_=capacity(REPO)
    require_current_capacity(a["frozen_V39C_site_capacity"])
    assert p.site_it_power_kw(64,8)>0
    with pytest.raises(ReplayError,match="CURRENT_SITE_CAPACITY"):
        require_current_capacity({s:52 for s in SITES})


def test_headroom_and_delay_gpu_hours_are_day_scoped_and_not_duplicated():
    jobs=[j("a",64),j("b",8,start=25)]
    x=execute(jobs)
    occ,_,_=compare_occupancy(x,EXPECTED)
    rows=headroom_rows("2025-05-01","B0",x,occ)
    assert rows[0]["min_headroom_GPU"]==0
    assert rows[0]["waiting_jobs_due_to_site_capacity"]==1
    assert rows[0]["delayed_GPU_hours_due_to_site_capacity"]==4


def test_gang_split_and_runtime_truncation_in_ledger_are_rejected():
    jobs=[j("a",8)];x=execute(jobs)
    bad=deepcopy(x);bad["rack_ledger"][0]["requested_GPU"]=4
    with pytest.raises(ReplayError,match="GANG_ADMISSION_MISMATCH"):
        audit_gangs(jobs,bad,RACKS)
    bad=deepcopy(x);bad["rack_ledger"][0]["release_slot"]-=1
    with pytest.raises(ReplayError,match="TRUNCATED_OR_PREEMPTED"):
        audit_gangs(jobs,bad,RACKS)


def test_all_31_B3_bind_to_accepted_A1_even_when_A0_values_equal():
    bindings=read(REPO/"dayahead/artifacts/v40d_actual_realized_replay/V40D_ACTUAL_DECISION_BINDING_AUDIT.json")["cases"]
    count=0
    for b in bindings:
        if b["case"]!="B3":continue
        jobs,_=frozen_jobs(REPO,b)
        cp=read(Path(b["AIDC_decision_source"]).parent/"COOPT_PLANNING_CHECKPOINT.json")
        # The loader adds provenance fields; compare every original A1 field exactly.
        assert legacy_digest([{k:r[k] for k in cp["a1"][i]} for i,r in enumerate(jobs)])==legacy_digest(cp["a1"])
        count+=1
    assert count==31


def test_B3_A1_identity_guard_rejects_mismatched_checkpoint(monkeypatch):
    import dayahead.v40d_actual.inputs as inputs
    b=next(b for b in read(REPO/"dayahead/artifacts/v40d_actual_realized_replay/V40D_ACTUAL_DECISION_BINDING_AUDIT.json")["cases"] if b["case"]=="B3")
    original=inputs.read
    def tampered(path):
        x=original(path)
        if Path(path).name=="COOPT_PLANNING_CHECKPOINT.json":
            x["a1"][0]["AIDC_site"]="AIDC12"
        return x
    monkeypatch.setattr(inputs,"read",tampered)
    with pytest.raises(ReplayError,match="B3_FINAL_A1_DECISION_MISMATCH"):
        frozen_jobs(REPO,b)


def test_protected_planning_and_fresh_static_integration_gate():
    audit=read(REPO/"dayahead/artifacts/v40d_actual_realized_replay/capacity_audit/PROTECTED_PLANNING_FRESH_DIFF.json")
    assert audit["status"]=="PASS" and audit["changed_count"]==0 and audit["checked_files"]==3887
