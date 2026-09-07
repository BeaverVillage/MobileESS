from collections import Counter
from copy import deepcopy
from itertools import product
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import pytest
from dayahead.v41r1.feasible_seed import row_audit
from dayahead.v41r1.exact_aggregation import signature,disaggregate
from dayahead.v41r1.bounded_solver import PolicyBudget,BoundedLex,relative_gap
from dayahead.v40g.domain import Option


def test_complete_substitution_checks_linear_bound_integer_indicator_max_pwl():
    m=gp.Model();m.Params.OutputFlag=0
    x=m.addVar(vtype=GRB.BINARY,name='x');p=m.addVar(name='p');z=m.addVar(name='z')
    m.addConstr(x<=1);m.addGenConstrPWL(x,p,[0,1],[2,4]);m.addGenConstrMax(z,[p],constant=3)
    m.addGenConstrIndicator(x,True,z==4);m.update()
    assert row_audit(m,[1,4,4])['status']=='PASS'
    for wrong in ([.5,3,3],[1,3,4],[0,2,2],[1,4,5],[2,4,4]):
        assert row_audit(m,wrong)['status']=='FAIL'
    m.dispose()


@pytest.mark.parametrize('start,end',[(0,20),(0,30),(24,25),(96,144),(120,200),(25,100)])
def test_gpu_audit_has_exactly_the_original_independent_day_horizon(start,end):
    from dayahead.v41r1.feasible_seed import modeled_capacity_interval
    from dayahead.v41r1.migration_load import add_interval
    from collections import defaultdict
    segment=dict(site='A',start=start,end=end);before=deepcopy(segment)
    load=defaultdict(float);add_interval(load,'A',start,end,2,96,event_form=False)
    expected={t+24 for (t,site),v in load.items() if v}
    window=modeled_capacity_interval(segment)
    assert (set(range(*window)) if window else set())==expected
    assert segment==before  # No job duration or cross-midnight segment clipping.


def test_exact_count_aggregation_bijection_all_objectives_and_resource_trajectories():
    # Two identical jobs, three placement columns. Count vectors represent all
    # job-level assignments; deterministic canonicalization preserves columns.
    opts=[Option('A',24,26),Option('B',24,26),Option('C',24,26)]
    original=set();aggregated=set()
    def physics(chosen):
        gpu=np.zeros((3,4),dtype=int)
        for o in chosen:gpu['ABC'.index(o.site),:2]+=1
        rack=gpu.copy();wan=np.zeros(4,dtype=int);p=2*gpu;q=gpu
        vector=(int(gpu.max()),int((2-gpu).sum()),0,sum(o.site!='A' for o in chosen)*4,sum(opts.index(o)+1 for o in chosen))
        return vector,tuple(gpu.flat),tuple(rack.flat),tuple(wan),tuple(p.flat),tuple(q.flat)
    for chosen in product(opts,repeat=2):original.add(physics(chosen))
    for counts in product(range(3),repeat=3):
        if sum(counts)!=2:continue
        rows=disaggregate(['b','a'],zip(opts,counts));assert [u for u,_ in rows]==['a','b']
        assert rows==disaggregate(['a','b'],zip(opts,counts))
        aggregated.add(physics([o for _,o in rows]))
    assert original==aggregated


@pytest.mark.parametrize('field',['state_at_issue','requested_GPU','safe_duration_slots','AIDC_site','Rack_label','r1_first_valid_checkpoint','common_terminal_obligation','qos'])
def test_scientific_difference_forbids_aggregation(field):
    cap=SimpleNamespace(aidc_ids=('A','B'),site_capacity={'A':4,'B':4},eligible_racks=lambda s,g:[SimpleNamespace(rack_pool_id=s+'1',historical_gpu_capacity=4)])
    row=dict(job_uid='a',state_at_issue='PENDING',requested_GPU=1,safe_duration_slots=2,AIDC_site='A',Rack_label='A1',r1_first_valid_checkpoint=26,common_terminal_obligation={},qos='normal')
    opts=(Option('A',24,26),Option('B',24,26));other=deepcopy(row);other['job_uid']='b'
    assert signature(row,opts,(0,4),cap)==signature(other,opts,(0,4),cap)
    other[field]={'changed':True} if field=='common_terminal_obligation' else str(row[field])+'_different'
    assert signature(row,opts,(0,4),cap)!=signature(other,opts,(0,4),cap)


def test_uid_serial_migration_jobs_cannot_be_count_aggregated():
    cap=SimpleNamespace(aidc_ids=('A','B'),site_capacity={'A':4,'B':4},eligible_racks=lambda s,g:[SimpleNamespace(rack_pool_id=s+'1',historical_gpu_capacity=4)])
    a=dict(job_uid='a',requested_GPU=1);b=dict(a,job_uid='b')
    opts=(Option('B',24,29,26,26,27,'A'),)
    assert signature(a,opts,(1,),cap)!=signature(b,opts,(1,),cap)


def test_p5_is_not_pure_job_disaggregation():
    # Equal P1-P4 can still have different IDC injections. Native P5 ranks
    # entire option columns and therefore cannot be discarded post-solve.
    a=dict(P1=1.,P2=0.,P3=0,P4=4,P5=1,GPU=(1,0))
    b=dict(P1=1.,P2=0.,P3=0,P4=4,P5=2,GPU=(0,1))
    assert [a[k] for k in ('P1','P2','P3','P4')]==[b[k] for k in ('P1','P2','P3','P4')]
    assert a['P5']!=b['P5'] and a['GPU']!=b['GPU']


def test_f_and_o_retains_full_domain_capacity_locks_and_reports_no_global_gap(tmp_path):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=4;m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9
    choices={}
    for i in range(4):
        choices[i]=[m.addVar(vtype=GRB.BINARY,name=f'choice[{i},{k}]') for k in range(2)]
        m.addConstr(sum(choices[i])==1)
    # Receiving GPU/rack and shared WAN remain active throughout neighborhoods.
    moved=sum(choices[i][1] for i in choices);m.addConstr(moved<=2,name='rack_GPU_capacity');m.addConstr(moved<=2,name='WAN_capacity')
    rho=m.addVar(lb=0,name='rho');m.addConstr(rho>=4-moved)
    tie=sum((i+1)*(k+1)*v for i,vs in choices.items() for k,v in enumerate(vs))
    m.setObjective(rho);m.update();seed=np.zeros(m.NumVars)
    for vs in choices.values():seed[vs[0].index]=1
    seed[rho.index]=4
    engine=BoundedLex(m,seed,tmp_path,PolicyBudget(2),allocation=[1,1],objective_expressions=[rho,moved,tie],
        metadata={i:dict(members=[f'job{i}'],candidate_count=2,can_migrate=True) for i in choices})
    first=engine.optimize('P1');lock=engine.value(rho);assert lock<=4
    m.addConstr(rho<=lock+1e-9,name='PRIMARY_EXACT_VALUE_LOCK');m.setObjective(moved)
    second=engine.optimize('P2')
    assert engine.value(rho)<=lock+1e-9 and row_audit(m,engine.values)['status']=='PASS'
    assert engine.value(moved)<=2
    assert first['bound'] is None and second['achieved_relative_gap'] is None
    assert all(v.LB==0 and v.UB==1 for vs in choices.values() for v in vs)
    coverage=json.loads((tmp_path/'CANDIDATE_COVERAGE_REPORT.json').read_text())
    assert coverage['scientific_candidate_pruning']==0 and coverage['fraction_candidates_visited']==1
    assert engine.budget.used<=2.5
    m.dispose()


def test_gap_does_not_mean_incumbent_degradation_and_unknown_bound_not_zero():
    assert relative_gap(100,97)==.03
    assert relative_gap(100,None) is None
    assert relative_gap(0,-1) is None
    b=PolicyBudget(1800);b.charge(360,'P1');assert b.remaining==1440
    with pytest.raises(ValueError):PolicyBudget(1801)


@pytest.mark.parametrize('residual',[2.8e-9,.25])
def test_invalid_solver_proposal_is_preserved_rejected_and_never_materialized(tmp_path,monkeypatch,residual):
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=4
    m.Params.FeasibilityTol=1e-9;m.Params.IntFeasTol=1e-9
    x=m.addVar(vtype=GRB.BINARY,name='choice[0,0]');p=m.addVar(name='PCC')
    m.addGenConstrPWL(x,p,[0,1],[1,2],name='GPU_to_PCC');m.setObjective(-x);m.update()
    seed=np.asarray([0.,1.]);engine=BoundedLex(m,seed,tmp_path,PolicyBudget(1),allocation=[1])
    original=gp.Model.getAttr
    def returned_values(model,attr,*args):
        value=original(model,attr,*args)
        if model is m and attr=='X':value[p.index]+=residual
        return value
    monkeypatch.setattr(gp.Model,'getAttr',returned_values)
    def materialize():
        assert np.array_equal(engine.values,seed)
        assert row_audit(m,engine.values)['status']=='PASS'
        return {'status':'PASS'}
    engine.validator=materialize
    result=engine.optimize('P1')
    assert result['feasibility']['status']=='PASS' and np.array_equal(engine.values,seed)
    assert engine.history and all(not row['accepted'] and row['candidate_rejection'] for row in engine.history)
    rejected=json.loads(Path(engine.history[0]['candidate_rejection']['path']).read_text())
    assert rejected['candidate_audit']['status']=='FAIL' and rejected['retained_incumbent_audit']['status']=='PASS'
    assert rejected['physical_constraints_relaxed'] is False
    with np.load(rejected['candidate']['path']) as values:
        assert row_audit(m,values['values'])['status']=='FAIL'
    assert m.Params.FeasibilityTol==1e-9 and engine.coverage()['fraction_candidates_visited']==1
    m.dispose()


def test_full_candidate_rotation_covers_every_block_before_any_second_visit(tmp_path):
    m=gp.Model();m.Params.OutputFlag=0
    for i in range(9):
        for k in range(2):m.addVar(vtype=GRB.BINARY,name=f'choice[{i},{k}]')
    m.update();engine=BoundedLex(m,np.zeros(m.NumVars),tmp_path)
    engine.target_free=4
    for step in range(5):
        groups,_=engine._choose(0)
        assert all(engine.visits[g]==0 for g in groups)
        for g in groups:engine.visits[g]+=1
        engine.iteration+=1
    assert min(engine.visits.values())==1
    assert engine.coverage()['fraction_candidates_visited']==1
    m.dispose()


def test_m1_array_fingerprint_uses_the_consumers_digest(monkeypatch):
    from dayahead.v41 import execution
    from dayahead.v40a.invariants import digest as expected
    import dayahead.v40h.cache as cache
    inventory=dict(traffic={'test':dict(forecast={'graph_SHA':'road'},route_table={})},road_graph={'service_nodes':{}},
        MESS_mobility={},MESS_electrical={},service_PCC_mapping={})
    monkeypatch.setattr(execution,'read',lambda p:inventory)
    monkeypatch.setattr(execution,'identities',lambda jobs:dict(canonical_decision_SHA='j',segment_and_event_SHA='s'))
    monkeypatch.setattr(execution,'planning_power',lambda jobs,ctx:dict(gpu=np.array([[1,2]])))
    monkeypatch.setattr(execution,'science',lambda:dict(manifest_SHA='source'))
    monkeypatch.setattr(cache,'execution_identity',lambda value:value)
    ctx=SimpleNamespace(v41_ml_snapshot_sha256='ml',coefficients=[]);pcc=np.array([[1.25,2.5]])
    result=execution.m1_identity('test',[],pcc,ctx)
    assert result['A0_PCC_SHA']==expected(pcc)
    assert result['A0_GPU_SHA']==expected(np.array([[1,2]]))
    assert result['road_graph']['canonical_SHA']=='road'
