"""Tiny native/synthetic and adversarial Phase-I scientific qualification."""
from dataclasses import replace
from fractions import Fraction
import json
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.domain import physical_domain,graph_content_hash
from v42_a_stage_domain_v2.active import _graph,prepare_fast_active,ActivePolicy
from v42_a_stage_phase1.core import (elastic_master,verify_zero,primal_replay,
    verify_sign_convention,exact_local_bound,interval_box_bound)
from v42_a_stage_phase1.producer import complete_graph,native_block,price_snapshot
from test_v42_a_stage_fast_active import fixture


def snapshot(columns,capacity=0):
    a=np.asarray(columns,dtype=float).T
    return LinearSnapshot(sp.csr_matrix(a),np.zeros(a.shape[1]),np.ones(a.shape[1]),
        np.asarray(['=','<']),np.asarray([1.,capacity]),np.full(a.shape[1],'C'),
        (Objective('rho',(),0),)).require()


def solve(snap,tmp_path,name):
    m=gp.Model('EXPLICIT_TINY_PHASE1_FIXTURE');m.Params.OutputFlag=0
    m.Params.Threads=1;m.Params.Method=2;m.Params.TimeLimit=5
    x=m.addMVar(snap.matrix.shape[1],lb=snap.lower,ub=snap.upper)
    m.addMConstr(snap.matrix,x,snap.senses,snap.rhs)
    objective=snap.objectives[0];c=np.zeros(snap.matrix.shape[1])
    for j,value in objective.coefficients().items():c[j]=float(value)
    m.setObjective(c@x+float(objective.constant));m.optimize()
    arrays={n:np.asarray(m.getAttr(n)) for n in ('X','Pi','RC','Slack')} if m.SolCount else {}
    # Raw persistence precedes ALL sign/primal/closure assertions.
    np.savez_compressed(tmp_path/(name+'.npz'),**arrays)
    (tmp_path/(name+'.json')).write_text(json.dumps(dict(status=m.Status,objective=m.ObjVal if m.SolCount else None)),encoding='utf8')
    status=m.Status;objective=m.ObjVal if m.SolCount else None;m.dispose()
    return status,objective,arrays


def price(columns,pi):
    return tuple(-sum((Fraction(float(p))*Fraction(float(a)) for p,a in zip(pi,column)),Fraction(0)) for column in columns)


@pytest.mark.parametrize('family',('STAY','MIGRATION'))
def test_A_E_F_one_omitted_hard_valid_column_recovers_zero(tmp_path,family):
    active=snapshot([(1,1)]);master=elastic_master(active,(0,1))
    status,phi,raw=solve(master.snapshot,tmp_path,'before_'+family)
    assert status==gp.GRB.OPTIMAL and phi>0
    assert verify_sign_convention(master.snapshot,raw['Pi'],raw['RC'])['PASS']
    rc=price([(1,0)],raw['Pi'])[0]
    assert rc<0
    expanded=elastic_master(snapshot([(1,1),(1,0)]),(0,1))
    _,phi,point=solve(expanded.snapshot,tmp_path,'after_'+family)
    assert phi==0 and verify_zero(expanded,point['X'])['PASS']
    assert (tmp_path/('before_'+family+'.npz')).exists()


def test_B_true_full_infeasibility_requires_positive_exact_bound_and_full_cover(tmp_path):
    full=elastic_master(snapshot([(1,1),(1,2)]),(0,1))
    _,phi,raw=solve(full.snapshot,tmp_path,'full_infeasible')
    assert phi>0
    bound=exact_local_bound(full.snapshot,raw['Pi'])
    assert bound['PASS'] and Fraction(bound['lower_bound'])>0
    assert all(rc>=0 for rc in price([(1,2)],raw['Pi']))
    assert not verify_zero(full,raw['X'])['PASS']


def test_C_already_feasible_original_has_zero_artificials(tmp_path):
    master=elastic_master(snapshot([(1,0)]),(0,1))
    _,phi,raw=solve(master.snapshot,tmp_path,'already_feasible')
    assert phi==0 and verify_zero(master,raw['X'])['PASS']


def test_D_two_omitted_columns_select_only_correct_candidate(tmp_path):
    master=elastic_master(snapshot([(1,1)]),(0,1))
    _,_,raw=solve(master.snapshot,tmp_path,'choose_correct')
    costs=price([(1,0),(1,2)],raw['Pi'])
    assert costs[0]<0 and costs[1]>=0


def test_G_mixed_two_columns_recover_together(tmp_path):
    a=LinearSnapshot(sp.csr_matrix([[1.],[0.],[1.]]),np.zeros(1),np.ones(1),
        np.asarray(['=','=','<']),np.asarray([1.,1.,0.]),np.full(1,'C'),(Objective('rho',(),0),))
    first=elastic_master(a,(0,1,2));_,phi,raw=solve(first.snapshot,tmp_path,'mixed_before')
    assert phi>0
    costs=price([(1,0,0),(0,1,0)],raw['Pi'])
    assert all(c<0 for c in costs)
    full=replace(a,matrix=sp.csr_matrix([[1.,1.,0.],[0.,0.,1.],[1.,0.,0.]]),
        lower=np.zeros(3),upper=np.ones(3),vtypes=np.full(3,'C'))
    master=elastic_master(full,(0,1,2));_,phi,raw=solve(master.snapshot,tmp_path,'mixed_after')
    assert phi==0 and verify_zero(master,raw['X'])['PASS']


def test_H_corrupted_dual_sign_rejected_independently(tmp_path):
    master=elastic_master(snapshot([(1,1)]),(0,1));_,_,raw=solve(master.snapshot,tmp_path,'sign')
    assert not verify_sign_convention(master.snapshot,-raw['Pi'],raw['RC'])['PASS']


def test_I_hidden_negative_complete_block_member_is_found(tmp_path):
    columns=[(1,1)]*19+[(1,0)]+[(1,2)]*7
    master=elastic_master(snapshot([columns[0]]),(0,1));_,_,raw=solve(master.snapshot,tmp_path,'hidden')
    costs=price(columns,raw['Pi'])
    assert min(range(len(costs)),key=lambda j:(costs[j],j))==19
    # A bound on a scanned prefix cannot cover the declared complete roster.
    assert min(costs[:19])>=0 and min(costs)<0


def test_J_false_closure_and_artificial_physics_mutation_rejected(tmp_path):
    master=elastic_master(snapshot([(1,1)]),(0,1));_,_,raw=solve(master.snapshot,tmp_path,'false_closure')
    assert not verify_zero(master,raw['X'])['PASS']
    signs=tuple(-s for s in master.artificial_signs)
    changed=replace(master,artificial_signs=signs)
    with pytest.raises(ValueError,match='SIGN_MUTATION'):changed.verify()
    rhs=master.snapshot.rhs.copy();rhs[0]=0
    with pytest.raises(ValueError,match='ROW_AUTHORITY'):replace(master,snapshot=replace(master.snapshot,rhs=rhs)).verify()


def test_all_three_row_senses_and_bounds_persistence(tmp_path):
    a=LinearSnapshot(sp.csr_matrix([[1.],[1.],[1.]]),np.asarray([0.]),np.asarray([0.]),
        np.asarray(['=','<','>']),np.asarray([1.,-1.,1.]),np.asarray(['C']),(Objective('rho',(),0),))
    master=elastic_master(a,(0,1,2));_,phi,raw=solve(master.snapshot,tmp_path,'senses')
    assert phi==3 and verify_sign_convention(master.snapshot,raw['Pi'],raw['RC'])['PASS']
    assert primal_replay(master.snapshot,raw['X'])['PASS']
    assert not primal_replay(a,raw['X'][:1])['PASS']


def test_full_graph_matches_independent_naive_all_physical_paths():
    data=fixture();job=data[1]['j0'];domain=physical_domain(job,data[2]['j0'],data[3])
    full=complete_graph(job,domain,True)
    naive=_graph(job,set(domain.stays),tuple(o for o in domain if o.migrated),domain,True)
    assert graph_content_hash(full)==graph_content_hash(naive)
    assert full.compatible==naive.compatible and full.physical==naive.physical


def block_fixture(N):
    data=list(fixture(N));data[0]=dict(runtime_survival_kernel=[1.,.5,.25],runtime_reserve_gamma=1.)
    data[4]={u:dict(risk_nominal_completion_issue_slot=24,reference_end=8) for u in data[1]}
    active,domains,_=prepare_fast_active(tuple(data),policy=ActivePolicy(0,0))
    axes=tuple([('GPU',site,t) for site in data[3].capacities for t in range(12)]+
        [('RUNTIME',site,t) for site in data[3].capacities for t in range(24,120)]+
        [('WAN',link,t) for link,t in data[3].wan_capacities]+[('ACTIVE','',t) for t in range(12)])
    full=complete_graph(data[1]['j0'],domains['j0'])
    return active,full,axes


@pytest.mark.parametrize('N',(1,2,3))
def test_complete_native_sum_lane_LP_equals_all_original_lanes(tmp_path,N):
    data,full,axes=block_fixture(N)
    compact,B,_,_=native_block(data,'c',full,axes,averaged=True)
    original,C,_,_=native_block(data,'c',full,axes,averaged=False)
    # Frozen deterministic coupling dual; exercises states, WAN and Runtime.
    pi=np.asarray([((i*17)%11-5)/8 for i in range(len(axes))])
    first=price_snapshot(compact,B,pi);second=price_snapshot(original,C,pi)
    _,x,a=solve(first,tmp_path,'sum_lane_'+str(N));_,y,b=solve(second,tmp_path,'all_lanes_'+str(N))
    assert abs(x-y)<1e-7
    assert primal_replay(first,a['X'])['PASS'] and primal_replay(second,b['X'])['PASS']
    cert=exact_local_bound(first,a['Pi']);assert cert['PASS']
    assert float(Fraction(cert['lower_bound']))<=x+1e-8
    assert verify_sign_convention(first,a['Pi'],a['RC'])['PASS']
    if N>1:assert compact.matrix.shape[1]<original.matrix.shape[1]


def test_interval_global_box_bound_is_conservative():
    A=sp.csr_matrix([[.1,.2],[.3,-.4]])
    p=np.asarray([.125,-.75]);c=np.asarray([0.,.5]);l=np.asarray([0.,-2.]);u=np.asarray([3.,4.]);b=np.asarray([1.,2.])
    got=interval_box_bound(A,c,p,l,u,b)
    residual=[Fraction(float(c[j]))-sum((Fraction(float(A[i,j]))*Fraction(float(p[i])) for i in range(2)),Fraction(0)) for j in range(2)]
    exact=sum((Fraction(float(b[i]))*Fraction(float(p[i])) for i in range(2)),Fraction(0))+sum(
        (r*Fraction(float(l[j] if r>=0 else u[j])) for j,r in enumerate(residual)),Fraction(0))
    assert Fraction(got)<=exact


@pytest.mark.parametrize('N',(1,2,3))
def test_fractional_full_native_support_activates_and_replays_without_rounding(tmp_path,N):
    from v42_a_stage_phase1.producer import support_graph
    from v42_a_stage_phase1.backend import project_local_point
    data,full,axes=block_fixture(N)
    block,B,_,units=native_block(data,'c',full,axes)
    pi=np.asarray([((i*17)%11-5)/8 for i in range(len(axes))])
    priced=price_snapshot(block,B,pi);_,_,raw=solve(priced,tmp_path,'direction_'+str(N))
    graph=support_graph(data[5]['j0'],full,units,raw['X'],job=data[1]['j0'])
    target,C,_,target_units=native_block(data,'c',graph,axes)
    projected=project_local_point(units,raw['X'],target_units,target.matrix.shape[1])
    assert primal_replay(target,projected)['PASS']
    assert np.max(abs(B@raw['X']-C@projected),initial=0)<1e-7
    for family in graph.events:assert set(graph.events[family])<=set(full.events[family])
    for family in graph.states:assert set(graph.states[family])<=set(full.states[family])


def test_weight_policy_remains_frozen_when_native_coefficients_expand():
    old=elastic_master(snapshot([(1,1)]),(0,1))
    weights=dict(zip(old.artificial_rows,old.weights))
    expanded=snapshot([(1,1),(1,128)])
    fixed=elastic_master(expanded,(0,1),weights_by_row=weights)
    assert fixed.weights==old.weights
    assert elastic_master(expanded,(0,1)).weights!=old.weights


def test_complete_coverage_recomputes_and_rejects_forged_bound(tmp_path):
    import gzip,pickle,copy
    from v42_pr134_b1.common import record
    from v42_a_stage_phase1.oracle import corrected_certificate,validate_coverage
    local=snapshot([(1,0)],capacity=1);B=sp.csr_matrix([[1.]])
    pi=np.asarray([0.]);local_pi=np.zeros(2);certificate=corrected_certificate(local,B,pi,local_pi)
    cache=tmp_path/'block.pkl.gz'
    with gzip.open(cache,'wb') as f:pickle.dump(dict(snapshot=local,B=B),f)
    want=dict(complete_local_snapshot_sha256=local.fingerprint(),complete_graph_sha256='graph',
        full_physical_STAY=1,full_physical_migration=0,external_full_block_cache=record(cache))
    receipt=dict(class_id='class',full_snapshot_sha256=local.fingerprint(),graph_sha256='graph',
        physical_STAY=1,physical_migration=0,certificate=certificate,local_raw_pi=local_pi,global_coupling_pi=pi)
    assert validate_coverage({'class':want},[receipt],pi)
    with pytest.raises(ValueError,match='COVERAGE'):validate_coverage({'class':want},[],pi)
    forged=copy.deepcopy(receipt);forged['certificate']['exact_lower_bound']='1'
    with pytest.raises(ValueError,match='FALSE_COMPLETE_BLOCK'):validate_coverage({'class':want},[forged],pi)
    forged=copy.deepcopy(receipt);forged['global_coupling_pi']=np.ones(1)
    with pytest.raises(ValueError,match='GLOBAL_PRICING_DUAL'):validate_coverage({'class':want},[forged],pi)


def test_pricing_inflight_budget_is_charged_and_cannot_be_restarted(monkeypatch):
    from v42_a_stage_phase1.native import Native,BudgetStop
    from v42_a_stage_phase1.setup import POLICY
    import v42_a_stage_phase1.native as module
    obj=Native.__new__(Native);obj.native_seconds=290.;obj.pricing_wall_seconds=295.;obj.pricing_started=90.
    monkeypatch.setattr(module,'perf_counter',lambda:100.)
    assert obj.remaining()==2.5
    obj.native_seconds=POLICY['cumulative_native_seconds']
    with pytest.raises(BudgetStop):obj.remaining()


def test_speed_gate_rejects_false_acceptance_without_root_or_complete_pricing():
    from types import SimpleNamespace
    from v42_a_stage_phase1.runner import speed_gate
    result=dict(final_original_model=dict(rows=10,cols=10,nnz=20),FULL_LP_FEASIBILITY_CLOSED=True,
        FULL_LP_DOMAIN_INFEASIBLE=False,LP_PRICING_CLOSED=False)
    gate=speed_gate(result,SimpleNamespace(calls=[],native_seconds=1.,pricing_wall_seconds=0.))
    assert not gate['PASS'] and not gate['checks']['D_complete_actual_pricing_certified']
    assert not gate['checks']['G_original_P1_practical']


def test_native_wrapper_persists_each_available_attribute_before_bad_replay(tmp_path,monkeypatch):
    from contextlib import nullcontext
    import v42_a_stage_phase1.native as module
    from v42_pr134_b1.common import atomic,read
    out=tmp_path/'EXPLICIT_TINY_FIXTURE';out.mkdir()
    atomic(out/'PHASE1_SOURCE_FREEZE.json',dict(git_head='EXPLICIT_TINY_FIXTURE_SOURCE'))
    obj=module.Native.__new__(module.Native);obj.permit=object();obj.policy=read(module.HISTORY/'SOLVER_POLICY.json')
    obj.native_seconds=0.;obj.pricing_wall_seconds=0.;obj.pricing_started=None;obj.calls=[];obj.resources=[]
    obj.verify=lambda:True
    monkeypatch.setattr(module,'OUT',out);monkeypatch.setattr(module,'STATIC',tmp_path/'STATIC')
    # Only this explicitly tiny fixture bypasses the external source receipt;
    # the production Native wrapper and backstop are unchanged.
    monkeypatch.setattr(module,'fast_run_scope',lambda p:nullcontext())
    monkeypatch.setattr(module,'fast_native_scope',lambda *a,**k:nullcontext())
    monkeypatch.setattr(module,'guard_model_optimize',lambda m:None)
    real_materialize=module.materialize
    def fixture_materialize(snap,day):
        m,obj=real_materialize(snap,day);m._v42_a_stage_day='EXPLICIT_TINY_FIXTURE';return m,obj
    monkeypatch.setattr(module,'materialize',fixture_materialize)
    master=elastic_master(snapshot([(1,1)]),(0,1))
    folder=out/'MAY19/TINY'
    receipt,raw=obj.solve(master.snapshot,folder,'PHASE_I')
    assert receipt['all_available_attributes_persisted_before_assertions']
    stored=np.load(receipt['raw_attributes']['path'])
    for name in ('X','Pi','RC','Slack'):assert np.array_equal(stored[name],raw[name])
    assert not verify_sign_convention(master.snapshot,-raw['Pi'],raw['RC'])['PASS']
    assert (folder/'NATIVE_RESULT.json').exists() and (folder/'MODEL_IDENTITY.json').exists()
    with pytest.raises(PermissionError,match='LP_ONLY'):obj.solve(master.snapshot,folder,'MILP')
