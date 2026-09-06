"""Targeted diagnostic algebra tests; do not run a campaign or preflight."""
import itertools
from pathlib import Path
import numpy as np
import pandas as pd
import gurobipy as gp
from gurobipy import GRB
from dayahead.tools import run_v39g_day17_shadow as shadow
from dayahead.tools.v39g_shadow_grid import inequalities,load_coefficients
from dayahead.v28r2.electrical_subproblem import anchored_polygon_loading,is_dominated_mess_current_row

def test_complete_interval_objective_no_target_horizon_escape():
    for lo,d,delay,g in itertools.product((0,63,115),(1,10,25),(0,1,23,100),(1,4)):
        left=set(range(lo,lo+d));right=set(range(lo+delay,lo+delay+d))
        assert shadow.occupancy_cost(lo,d,lo+delay,g)==g*len(left.symmetric_difference(right))

def test_universal_eligibility_and_uid_authority():
    a,_=shadow.inputs()
    assert len(a)==2281 and a.job_uid.nunique()==2281
    assert a.eligible.sum()==379
    assert a.loc[a.eligible,"qos"].eq("standby").all()
    # Early eligible job does not intersect the offending slot in either RSP
    # or most possible starts. It still belongs to the universal feasible set.
    r=a.set_index("job_uid").loc["8772829"]
    assert r.eligible and r.RSP_scheduled_completion==10 and r.latest_start==149
    assert (~a.eligible & a.latest_start.ne(a.RSP_scheduled_start)).sum()==0

def test_eligibility_rejects_missing_authority_and_negative_slack():
    a,_=shadow.inputs();r=a.loc[a.eligible].iloc[[0]].copy()
    for column,value in [("D1_visible",False),("qos","normal"),("state_at_issue","RUNNING"),
                         ("duration_authority","UNKNOWN"),("RW_scheduled_completion",-1)]:
        x=r.copy();x[column]=value
        assert not shadow.eligible_mask(x).any()
    r["RW_scheduled_completion"]=r.RSP_scheduled_start+r.RSP_duration_slots
    assert shadow.eligible_mask(r).all()

def test_cohort_symmetry_preserves_every_job_and_all_domains():
    a,_=shadow.inputs();cs=shadow.cohorts(a)
    uids=[u for c in cs for u in c["members"]]
    assert sorted(uids)==sorted(a.job_uid) and len(set(uids))==2281
    assert max(c["hi"]+c["d"] for c in cs)==638
    assert all(c["lo"]==c["hi"] for c in cs if not c["eligible"])
    assert all(c["fixed_site"] for c in cs if c["state"]=="RUNNING")

def test_rejected_previous_day_site_extension_has_arithmetic_explanation():
    a,_=shadow.inputs();cap,_=shadow._load_capacity(shadow.REPO)
    for t in (11,12,13):
        active=a.RSP_scheduled_start.le(t)&a.RSP_scheduled_completion.gt(t)
        running=a.loc[active&a.state_at_issue.eq("RUNNING")].groupby("initial_AIDC").requested_gpus.sum()
        fit=sum((int(cap.site_capacity[s])-int(running.get(s,0)))//2 for s in cap.aidc_ids)
        normal=a.loc[active&a.state_at_issue.eq("PENDING")&a.qos.eq("normal")]
        assert normal.requested_gpus.eq(2).all()
        assert len(normal)==174 and fit==173
        assert normal.RW_scheduled_start.eq(normal.RSP_scheduled_start).all()
        assert t<24  # outside accepted production spatial operating day

def test_exact_lex_matches_bruteforce_with_interleaved_cohorts(tmp_path,monkeypatch):
    monkeypatch.setattr(shadow,"OUT",tmp_path)
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=4;m.Params.Seed=20260905;m.Params.MIPGap=0;m.Params.MIPGapAbs=0
    cs=[{"members":["a","d"]},{"members":["b","c"]}]
    vs={(k,s,t):m.addVar(vtype=GRB.INTEGER,ub=2) for k in range(2) for s,t in [("A",0),("A",1),("B",0)]}
    for k in range(2):m.addConstr(gp.quicksum(v for key,v in vs.items() if key[0]==k)==2)
    m.addConstr(vs[0,"A",0]+vs[1,"A",0]<=1)
    m.addConstr(vs[0,"A",1]+vs[1,"A",1]<=1)
    m.addConstr(vs[0,"B",0]+vs[1,"B",0]<=2)
    m.update();selected=shadow.exact_tie({"model":m,"cohorts":cs,"variables":vs})
    combos=[]
    for choices in itertools.product([("A",0),("A",1),("B",0)],repeat=4):
        if choices.count(("A",0))<=1 and choices.count(("A",1))<=1 and choices.count(("B",0))<=2:combos.append(choices)
    assert tuple(selected[u] for u in "abcd")==min(combos)
    m.dispose()

def test_frozen_grid_inequalities_match_original_algebra():
    cs,_=load_coefficients(shadow.OUT)
    for t in (0,40,82,95):
        c=cs[t];aa,bb,names=inequalities(c)
        for scale in (0,.5,1):
            p=c.anchor[:12]*scale;x=np.r_[p,np.zeros(48)]
            residual=aa@p-bb
            v=c.voltage_constant+c.voltage_matrix.T@x
            line=anchored_polygon_loading(c,x)
            current=c.current_constant+c.current_matrix.T@x
            pf=c.flow_p_constant+c.flow_p_matrix@x;qf=c.flow_q_constant+c.flow_q_matrix@x
            for index,name in enumerate(names):
                parts=name.split("[")[1][:-1].split(",");k=int(parts[1])
                if name.startswith("voltage_upper"):expected=v[k]-1.05**2
                elif name.startswith("voltage_lower"):expected=.95**2-v[k]
                elif name.startswith("transformer_current"):expected=current[k]-1
                elif name.startswith("transformer_kva"):
                    theta=2*np.pi*int(parts[2])/16
                    expected=np.cos(theta)*pf[k]+np.sin(theta)*qf[k]-c.transformer_ratings[k]*np.cos(np.pi/16)
                else:continue
                assert abs(residual[index]-expected)<1e-8
            for k,b in enumerate(c.branch_names):
                if b.startswith("transformer.") or is_dominated_mess_current_row(b):continue
                indices=[i for i,n in enumerate(names) if n.startswith(f"line_current[{t},{k},")]
                assert abs(max(residual[indices])-(line[k]-1))<1e-8

def test_production_sources_preserved():
    start=shadow.read("V39G_START_STATE.json")["production_source_SHA256"]
    assert shadow.source_hashes()==start

def test_final_witness_invariants_when_present():
    path=shadow.OUT/"V39G_MAY17_SHADOW_A_SCHEDULE.parquet"
    if not path.exists():return
    a=pd.read_parquet(path)
    assert a.job_uid.is_unique and len(a)==2281
    assert a.duration_slots.dtype.kind in "iu"
    assert np.array_equal(a.scheduled_end_slot-a.scheduled_start_slot,a.duration_slots)
    assert np.array_equal(a.duration_slots,a.RSP_duration_slots)
    assert (a.loc[~a.eligible,"start_delay_slots"]==0).all()
    assert (a.loc[a.eligible,"scheduled_end_slot"]<=a.loc[a.eligible,"RW_scheduled_completion"]).all()
    assert (a.loc[a.state_at_issue.eq("RUNNING"),"AIDC"]==a.loc[a.state_at_issue.eq("RUNNING"),"initial_AIDC"]).all()

def test_final_certificate_hierarchy_matches_expanded_witness():
    path=shadow.OUT/"V39G_MAY17_SHADOW_A_RESULT.json"
    if not path.exists():return
    r=shadow.read(path.name);a=pd.read_parquet(shadow.OUT/"V39G_MAY17_SHADOW_A_SCHEDULE.parquet")
    metrics=[0,int(a.occupancy_deviation_GPU_slots.sum()),int(a.start_delay_slots.ne(0).sum()),int((a.requested_gpus*a.start_delay_slots).sum())]
    for stage,value in zip(r["stages"],metrics):
        assert stage["optimal"] and stage["objective"]==stage["bound"]==value
        assert stage["Threads"]==4 and stage["MIPGap_setting"]==0
    assert r["all_hard_constraints_pass"]
    lex=shadow.read("V39G_EXACT_LEX_CERTIFICATES.json")
    assert all(s["optimal"] and s["Threads"]==4 for s in lex["stages"])
    aux=shadow.read("V39G_MAY17_SLOT106_LOAD_RESTORATION.json")
    assert aux["stage"]["objective"]==aux["stage"]["bound"]==152
    assert aux["same_original_feasible_set_as_A"] and aux["A_primary_secondary_tertiary_optima_NOT_fixed"]

def test_exact_C1_tables_are_monotone_for_box_elimination_proof():
    cap,_=shadow._load_capacity(shadow.REPO)
    with np.load(shadow.OUT/"V39G_C1_INTEGER_TABLES.npz") as raw:
        for s in cap.aidc_ids:
            table=raw[s]
            assert table.shape==(96,cap.site_capacity[s]+1)
            assert np.isfinite(table).all() and np.all(np.diff(table,axis=1)>0)
            assert np.array_equal(table.min(axis=1),table[:,0])
            assert np.array_equal(table.max(axis=1),table[:,-1])
