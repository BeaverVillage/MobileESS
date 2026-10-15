from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import pytest

from test_v42_integration_m import fixture, validator, cert
from v42_integration import m_engine, m_warm
from v42_integration.m_adaptive import pool_identity


class Budget:
    def __init__(self,value=400.):self.value=value;self.consumed=0.;self.calls=[]
    def remaining(self):return self.value-self.consumed
    def used(self):return self.consumed


def test_repeat_distinct_pools_monotonic_full_ub_and_native_cap(tmp_path):
    case,p=fixture(tmp_path);graph=m_engine.PathGraph(case);budget=Budget(300)
    def generate(c,point,bank,b):
        epoch=c.mess_search_state['epoch']
        if epoch>2:return None
        return {u:[graph.complete(u,[8] if epoch==1 else [8,9])] for u in graph.origins}
    caps=[]
    def solve(c,b,packet,folder,seconds):
        caps.append(seconds);b.parent.consumed+=120
        candidate=p(True) if len(caps)==1 else p(False,4.)
        return dict(executed=True,Native_Runtime=120,current_pool_ObjVal=float(candidate[0])),[dict(point=candidate)]
    case.candidate_generator=generate;case.joint_solver=solve
    result,point=m_engine.optimize_mess(case,p(False),[],budget)
    search=result['adaptive_search']
    assert search['joint_calls']==search['unique_pools']==2
    assert [(r['FULL_verified_UB_before'],r['FULL_verified_UB_after']) for r in search['history']]==[(3.,2.),(2.,2.)]
    assert caps==[140.,140.]
    assert point[0]==2. and budget.used()==240.
    assert result['certified_Global_LB'] is None and not result['global_gap_certified']
    assert len(list(tmp_path.glob('COMMON_M_PR222/ITERATION_*/INCUMBENT/BEST_GLOBAL_INCUMBENT.npz')))==2


def test_reordered_pool_is_same_mathematics():
    assert pool_identity({'u':[[1,2],[3,4]]})==pool_identity({'u':[[3,4],[1,2]]})


def test_duplicate_pool_does_not_enter_native_again(tmp_path):
    case,p=fixture(tmp_path);budget=Budget();count=[]
    def generate(c,*args):
        if c.mess_search_state['epoch']>3:return None
        return {}
    def solve(c,b,*args):
        count.append(1);b.parent.consumed+=1
        return dict(executed=True,Native_Runtime=1),[]
    case.candidate_generator=generate;case.joint_solver=solve
    result,_=m_engine.optimize_mess(case,p(False),[],budget)
    assert len(count)==1 and result['adaptive_search']['joint_calls']==1
    assert any(r['status']=='DUPLICATE_POOL_SKIPPED' for r in result['adaptive_search']['history'])


def test_native_error_preserves_prior_full_raw(tmp_path):
    case,p=fixture(tmp_path);case.candidate_pools={}
    case.joint_solver=lambda *args:(_ for _ in ()).throw(RuntimeError('fixture interrupt'))
    result,point=m_engine.optimize_mess(case,p(True),[],Budget())
    assert result['FULL_validated'] and point[0]==2.
    assert 'PRESERVED' in result['adaptive_search']['stop_reason']
    assert Path(result['incumbent_registry'][0]['raw']['path']).is_file()


def test_joint_return_reserve_limits_last_call(tmp_path):
    case,p=fixture(tmp_path);case.candidate_pools={};caps=[]
    def solver(c,b,packet,folder,seconds):
        caps.append(seconds);b.parent.consumed+=seconds
        return dict(executed=True,Native_Runtime=seconds),[]
    case.joint_solver=solver
    m_engine.optimize_mess(case,p(False),[],Budget(33))
    assert caps==[23.]


def test_static_cache_sha_invalidates_objective_and_revalidates_start(tmp_path):
    case,p=fixture(tmp_path);bank=m_engine.IncumbentBank(case);bank.offer(p(False),cert(case,p(False)))
    pools=m_engine.pin_pools(case,p(False),bank)
    first=m_engine.direct_joint(case,p(False),pools)[-1]
    second=m_engine.direct_joint(case,p(False),pools)[-1]
    assert not first['static_cache_hit'] and second['static_cache_hit']
    case.d['objective'][0]=.5
    third=m_engine.direct_joint(case,p(False),pools)[-1]
    assert not third['static_cache_hit'] and third['dynamic_links_and_start_reverified']


def warm_fixture(tmp_path,monkeypatch):
    case,p=fixture(tmp_path/'M1');case.output.mkdir()
    case.identity.update(arm='B3',stage='M1',day='2025-05-01',D0_source_sha='source',D0_parent_case_sha='D0')
    raw=case.output/'M1.npz';np.savez_compressed(raw,point=p(True))
    acceptance=dict(raw_point=m_engine.file_record(raw),result_sha='result',stage_case_sha=case.case_sha)
    result=dict(day='2025-05-01',D0_source_identity={'case_sha':'D0'},mess={'routes':m_engine.PathGraph(case).paths(p(True))})
    monkeypatch.setattr('v42_integration.table_v_mess.require_m_acceptance',lambda *a,**k:acceptance)
    monkeypatch.setattr(m_warm,'strict_full',lambda *a,**k:cert(case,p(True)))
    descriptor=m_warm.save_m1(case,p(True),result,acceptance)
    target,_=fixture(tmp_path/'M2');target.output.mkdir();target.identity.update(case.identity,stage='M2');target.case_sha='M2'
    target.forward=lambda x:x.copy()
    return target,p,descriptor


def test_warm_m2_replays_its_new_full_objective(tmp_path,monkeypatch):
    target,p,record=warm_fixture(tmp_path,monkeypatch)
    target.d['objective'][0]=2.
    def check(case,path,evidence):
        c=validator(case,path,evidence)
        with np.load(path) as z:value=2*z['point'][0]
        c.update(Global_UB=value,exact_Global_UB=str(int(value)));return c
    point,receipt=m_warm.admit_m1(target,record,validator=check)
    assert point is not None and receipt['admitted'] and receipt['M2_FULL_certificate']['Global_UB']==4.
    assert not receipt['old_bound_imported']


def test_warm_rejected_new_rhs_retains_legal_routes_for_cold(tmp_path,monkeypatch):
    target,p,record=warm_fixture(tmp_path,monkeypatch)
    target.d['rhs'][-1]=-9.
    point,receipt=m_warm.admit_m1(target,record,validator=validator)
    assert point is None and receipt['cold_fallback_required'] and receipt['route_seed_admitted']
    assert target.warm_route_seed


@pytest.mark.parametrize('tamper',['bytes','source','axis'])
def test_warm_wrong_raw_source_or_names_rejected(tmp_path,monkeypatch,tamper):
    target,p,record=warm_fixture(tmp_path,monkeypatch)
    if tamper=='bytes':Path(record['path']).write_text('{}')
    if tamper=='source':target.identity['D0_source_sha']='other'
    if tamper=='axis':target.original_d['names'][0]='other'
    point,receipt=m_warm.admit_m1(target,record,validator=validator)
    assert point is None and not receipt['admitted']


@pytest.mark.parametrize('arm',['B0','B1','B2','B3'])
def test_common_qos_deadline_and_throughput_apply_to_all_arms(arm):
    from v42_integration.table_v_evaluation import evaluate
    data=dict(carryout={'controller':dict(metadata={'j':dict(origin_unknown=True,completion_deadline_seconds=10.)},
        episode_jobs={'j':dict(start_time=1.,submit_time=0.,completion_observed_time=None)})},
        compute_occupancy_GPU=np.ones((2,1)),occupancy_GPU=np.ones((2,1))*2,receipt={})
    row,failures=evaluate(data,arm=arm,begin=0.,end=20.)
    assert row['Compute_GPUh']==.5 and row['Occupation_GPUh']==1.
    assert row['Source_deadline_violation_jobs']==1 and failures==['ACTUAL_SOURCE_HARD_DEADLINE:j']
    assert row['groups']['all']['conservation_PASS'] and row['groups']['all']['carry']==1
    assert row['E1_applicable']==(arm in ('B1','B3'))


def test_pr222_joint_redispatch_reverses_stay_biased_route_score(tmp_path):
    """A zero-dispatch route score is tied; coupled P/Q/SOC sees B's benefit."""
    from v42_integration.m_candidates import SignedMinimax,JointDispatchScore
    case,p=fixture(tmp_path);case.graph[3].terminal=2.
    from scipy import sparse
    extra=[f'{f}[{u},{site},{t}]' for u in case.graph[1] for site in ('A','B') for t in range(4) for f in ('Pch','Pdis','Q')]
    n=len(extra);old=p(False)
    case.d=dict(case.d,names=np.r_[case.d['names'],extra],types=np.r_[case.d['types'],['C']*n],
        lower=np.r_[case.d['lower'],[-10.]*n],upper=np.r_[case.d['upper'],[10.]*n],objective=np.r_[case.d['objective'],np.zeros(n)])
    case.original_d=case.d;case.A=sparse.hstack([case.A,sparse.csr_matrix((case.A.shape[0],n))],format='csr');case.original_A=case.A
    center=np.r_[old,np.zeros(n)]
    rows=[]
    for t in range(4):
        coeff={'rho_max':'-1'}
        for unit in case.graph[1]:
            # At the origin discharging worsens the line. At B it relieves it.
            coeff[f'Pdis[{unit},A,{t}]']='1'
            coeff[f'Pdis[{unit},B,{t}]']='-1'
            coeff[f'Pch[{unit},A,{t}]']='1'
            coeff[f'Pch[{unit},B,{t}]']='1'
        rows.append(dict(slot=t,current_loading=3. if t==2 else 0.,coeff=coeff,rhs='-3' if t==2 else '0'))
    scorer=SignedMinimax(case,center,{'rows':rows},np.array([[-1.,-1.],[-1.,1.],[1.,-1.],[1.,1.]]))
    parent=Budget(50);parent.record_external=lambda *a,**k:None
    lp=JointDispatchScore(scorer,parent);graph=m_engine.PathGraph(case)
    stay={u:graph.complete(u) for u in graph.origins}
    moving={u:graph.complete(u,[8]) for u in graph.origins}
    a,b=lp.score(stay),lp.score(moving)
    assert a['LP_status']==b['LP_status']==0
    assert b['score']<a['score']
    assert b['all_four_PQ_SOC_redispatched'] and not b['FULL_UB'] and not b['Global_LB']


def test_each_next_pool_pins_best_moving_even_when_global_stay_wins(tmp_path):
    case,p=fixture(tmp_path);graph=m_engine.PathGraph(case);bank=m_engine.IncumbentBank(case)
    bank.offer(p(True,4.),cert(case,p(True,4.)))
    bank.offer(p(False),cert(case,p(False)))
    for _ in range(3):
        pool=m_engine.pin_pools(case,bank.best[0],bank,{})
        for unit in graph.origins:
            assert graph.paths(p(True))[unit] in pool[unit]
            assert graph.complete(unit) in pool[unit]
        bank.offer(p(False,5.),cert(case,p(False,5.)))
    assert bank.fields()==dict(BEST_GLOBAL_UB=3.,BEST_MOVING_FEASIBLE_UB=4.)


def test_rejected_warm_enters_cold_initializer(tmp_path,monkeypatch):
    target,p,record=warm_fixture(tmp_path,monkeypatch)
    target.d['rhs'][-1]=-9.
    point,receipt=m_warm.admit_m1(target,record,validator=validator)
    assert point is None
    invoked=[]
    def cold(c,b,v):invoked.append(1);return None,None,[]
    target.cold_initializer=cold
    result,_=m_engine.optimize_mess(target,point,[],Budget(33))
    assert invoked==[1] and result['cold_initializer_used'] and not result['FULL_validated']
