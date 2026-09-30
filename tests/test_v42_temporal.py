from dataclasses import replace
from itertools import product
import subprocess
import numpy as np
import pandas as pd
import gurobipy as gp
import pytest
from v42_temporal.common import ROOT,OUT,OLD,BASE,read,sha
from v42_temporal.timeshift import WaitAuthority,dimensions,LEVELS
from v42_temporal.envelope import construct
from v42_temporal.service import bind_service,bind_forecast,slot_minima,objective_order,validate_envelope
from v42_temporal.resource import known_bounds
from v42_temporal.native import temporal_domain,native_jobs
from v42_final.workload import ForecastBook
from v42_final.gates import require_kernel,require_next
from v42_may01.state import cohort_key
from v42_native.service import boundary
from v42_job_capability import Job,Resources

CUTOFF=pd.Timestamp('2024-10-18T00:00:00Z')

def frame(n=100,wait=3600,qos='normal',partition='p',gpu=1,wall=3600,nodes=1):
    f=pd.DataFrame(dict(submit_time=[pd.Timestamp('2024-01-01T00:00:00Z')]*n,
        qos=qos,partition=partition,num_gpus_req=gpu,requested_seconds=wall,num_nodes_req=nodes))
    f['start_time']=f.submit_time+pd.to_timedelta(np.broadcast_to(wait,n),unit='s')
    f['end_time']=f.start_time+pd.Timedelta(minutes=15);f['event']=True
    return f

def key(qos='normal',partition='p',gpu=1,wall=3600,nodes=1):
    return cohort_key(qos,partition,gpu,wall,nodes)

@pytest.mark.parametrize('other',['standby','high','urgent','unknown'])
def test_qos_is_never_merged(other):
    f=pd.concat([frame(99),frame(300,qos=other)])
    r=WaitAuthority(f,CUTOFF).evaluate('PENDING',key(),0)
    assert not r['can_timeshift'] and r['attempted_N_cond']==[99]*5

@pytest.mark.parametrize('state,qos',[('RUNNING','normal'),('PENDING','high'),('PENDING','urgent'),('PENDING','unknown')])
def test_state_protection_fail_closed(state,qos):
    r=WaitAuthority(frame(200,qos=qos),CUTOFF).evaluate(state,key(qos=qos),0)
    assert not r['can_timeshift'] and r['fail_reason']=='STATE_OR_PROTECTION'

def test_explicit_protection_never_combines_with_nonprotected():
    c=key().split('|');c[3]='True'
    r=WaitAuthority(frame(200),CUTOFF).evaluate('PENDING','|'.join(c),0)
    assert not r['can_timeshift']
    assert all('protected' in l and 'qos' in l for l in LEVELS)

@pytest.mark.parametrize('n,eligible',[(99,False),(100,True)])
def test_exact_support_threshold(n,eligible):
    r=WaitAuthority(frame(n),CUTOFF).evaluate('PENDING',key(),0)
    assert r['can_timeshift']==eligible

def test_finest_supported_level_and_same_selected_cap():
    f=pd.concat([frame(99,wait=3600),frame(1,wait=7200,nodes=2),frame(100,wait=999999,partition='other')])
    r=WaitAuthority(f,CUTOFF).evaluate('PENDING',key(),900)
    assert r['selected_backoff_level']=='L1' and r['N_cond']==100
    assert r['residual_Q50_seconds']==2700 and r['total_wait_Q90_seconds']==3600
    assert r['TS_slots']==3

@pytest.mark.parametrize('age',[3600,3601])
def test_strict_wait_condition(age):
    r=WaitAuthority(frame(100,wait=3600),CUTOFF).evaluate('PENDING',key(),age)
    assert not r['can_timeshift'] and r['N_cond']==0

def test_q90_cap_cannot_be_bypassed_with_coarser_level():
    f=frame(1100,wait=np.r_[np.full(1000,100.),np.full(100,100000.)])
    r=WaitAuthority(f,CUTOFF).evaluate('PENDING',key(),200)
    assert r['N_cond']==100 and r['residual_Q50_seconds']==99800
    assert r['final_budget_seconds']==0 and r['selected_backoff_level']=='L0'
    assert r['fail_reason']=='AGE_CAP_BELOW_ONE_SLOT'

def test_budget_bounded_by_total_wait_q90_residual():
    f=frame(1000,wait=np.arange(1000)*60)
    r=WaitAuthority(f,CUTOFF).evaluate('PENDING',key(),45000)
    assert r['final_budget_seconds']<=max(0,r['total_wait_Q90_seconds']-45000)

def test_runtime_length_and_may_outcome_columns_do_not_affect_rule():
    f=frame();a=WaitAuthority(f,CUTOFF).evaluate('PENDING',key(),0)
    f['runtime_seconds']=1e9;f['May_outcome']=True
    assert a==WaitAuthority(f,CUTOFF).evaluate('PENDING',key(),0)

@pytest.mark.parametrize('column',['submit_time','start_time'])
def test_wait_rejects_future_rows(column):
    f=frame();f.loc[0,column]=pd.Timestamp('2025-05-01T00:00:00Z')
    with pytest.raises(ValueError,match='TRAIN_ONLY'):WaitAuthority(f,CUTOFF)

def test_no_standby_shortcut_or_target_share():
    assert not WaitAuthority(frame(99,qos='standby'),CUTOFF).evaluate('PENDING',key(qos='standby'),0)['can_timeshift']
    p=read(OUT/'PREREGISTRATION.json')
    assert p['target_TS_share'] is None and not p['runtime_eligibility_criterion']
    assert [list(l) for l in LEVELS]==p['TS_levels']

@pytest.fixture
def model():
    m=gp.Model();m.Params.OutputFlag=0
    yield m
    m.dispose()

def service(m,work=(10.,),end=3):
    return bind_service(m,work,[.2,.3,.5],[.1,.2,.4],[.4,.7,1.],end=end)

def test_service_nonnegative_no_pre_submission_and_conservation(model):
    s=service(model,work=(0.,10.),end=7);model.optimize()
    assert all(t>=4*h for h,t in s['x'])
    assert all(v.X>=0 for v in s['x'].values())
    assert sum(v.X for v in s['x'].values())+s['carryout'][1].X==pytest.approx(10)

def test_full_cumulative_envelope_and_carryout(model):
    s=service(model,end=2);model.setObjective(-s['carryout'][0]);model.optimize()
    assert s['carryout'][0].X==pytest.approx(8)
    cumulative=0
    for t in range(2):
        cumulative+=s['x'][0,t].X
        assert [.1,.2][t]*10-1e-8<=cumulative<=[.4,.7][t]*10+1e-8

def test_fixed_kernel_equality_removed(model):
    s=service(model);model.addConstr(s['x'][0,0]==4);model.optimize()
    assert model.Status==gp.GRB.OPTIMAL and s['x'][0,0].X!=2

def test_deviation_is_soft_after_P1_P2(model):
    s=service(model);rho=model.addVar(lb=0)
    model.addConstr(rho>=4-s['x'][0,0]);shortfall=gp.LinExpr(0)
    objs=objective_order([('rho',rho),('reserve_shortfall',shortfall)],s['deviation'],[('tie',gp.LinExpr(0))])
    assert [n for n,_ in objs]==['rho','reserve_shortfall','CC4_reference_deviation','tie']
    model.setObjective(rho);model.optimize();model.addConstr(rho<=model.ObjVal+1e-8)
    model.setObjective(s['deviation']);model.optimize()
    assert s['x'][0,0].X==pytest.approx(4,abs=1e-6)

def test_unsupported_tail_is_not_fabricated_service(model):
    s=service(model,end=9);model.optimize()
    assert max(t for h,t in s['x'])==2 and s['carryout'][0].X>=0

@pytest.mark.parametrize('lower,upper',[([.2,.1],[.5,.8]),([.1,.3],[.2,.2]),([-.1],[.9]),([.9],[.8])])
def test_invalid_envelope_rejected(lower,upper):
    with pytest.raises(ValueError):validate_envelope(lower,upper)

def test_observed_cohort_hour_cdf_and_no_censored_partial_cohort():
    f=frame(2,wait=[0,900]);f.loc[1,'submit_time']+=pd.Timedelta(minutes=5)
    records,q,n,a=construct(f,CUTOFF)
    assert a['completed_cohorts']==1 and q[0,0]==pytest.approx(.5)
    assert records[-1]['cumulative_fraction']==1
    f.loc[1,'event']=False
    with pytest.raises(ValueError,match='NO_COMPLETED'):construct(f,CUTOFF)

def test_envelope_rejects_May():
    f=frame();f['submit_time']=pd.Timestamp('2025-05-01T00:00:00Z')
    with pytest.raises(ValueError,match='TRAIN_ONLY'):construct(f,CUTOFF)

def test_depletion_and_reserve_are_separate_from_load(model):
    b=ForecastBook(tuple([10.]*24),tuple([15.]*24),0)
    b.submit('j',0,0,4,3600)
    s=bind_forecast(model,b,0,[.2,.3,.5],[.1,.2,.4],[.4,.7,1.],end=3)
    assert s['nominal']['work'][0]==6 and s['reserve']['work'][0]==5
    assert not s['reserve_is_realized_load']
    assert not {v.VarName for v in []} # Model variable identities checked below.
    assert set(map(id,s['nominal']['x'].values())).isdisjoint(map(id,s['reserve']['x'].values()))
    with pytest.raises(ValueError,match='DUPLICATE'):b.submit('j',0,0,4,3600)
    assert b.row(0,3600)['remaining_CC4_Q50_GPUh']==0

def test_midcohort_requires_explicit_history(model):
    with pytest.raises(ValueError,match='HISTORY'):
        bind_service(model,[10],[.2,.3,.5],[.1,.2,.4],[.4,.7,1.],begin=1,end=3)

def test_slot_minimum_formula_matches_separate_LPs(model):
    lo=[.1,.5,.7];hi=[.2,.6,.9]
    s=bind_service(model,[10],[.2,.3,.5],lo,hi,end=3)
    expected=slot_minima(lo,hi)*10
    for t in range(3):
        model.setObjective(s['x'][0,t]);model.optimize()
        assert model.ObjVal==pytest.approx(expected[t])

def test_native_start_adapter_grants_only_bounded_TS():
    j=Job('j','PENDING',0,0,0,'A',2,1,initial_sites=('A',),duration_authority='test')
    r=Resources({'A':4},{'A':(4,)},{},{},8,80,{},{},{})
    b=boundary(j,(0,1,2),'a'*64,'b'*64,H=8)
    opts,_=temporal_domain(j,b,r)
    assert {o.start for o in opts}=={0,1,2}
    assert all(sum(b-a for s,a,b in o.segments)==2 for o in opts)

def test_known_TS_bound_below_every_legal_start():
    j=dict(job_uid='j',reference_start_if_authorized=24,reference_end=30,GPU_gang=4)
    rows=known_bounds([j],{'j':{'TS_slots':2}},begin=24,end=33)
    for r in rows:
        for start in (24,25,26):
            assert r['known_GPU_lower_bound']<=4*(start<=r['issue_slot']<start+6)

def test_saved_native_authorities_unchanged():
    b=read(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json')
    assert sum(b['capacities'].values())==780 and b['runtime_reserve_gamma']==2.423057443558147
    assert not b['Actual_duplicate_runtime_reserve'] and b['current_RUNNING_GPU_is_hard']
    files=['v42_final/runtime.py','v42_final/reserve.py','v42_final/workload.py','v42_final/state.py',
        'v42_native/mess.py','v42_native/coordinator.py','v42_native/aidc.py','v42_job_capability.py',
        'docs/v42_final_integration/MAY01_RESUMED_SERVICE_CERTIFICATE.json',
        'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv']
    for name in files:
        import hashlib
        old=subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT)
        # Repository preserves existing mixed endings. Hash comparisons use
        # the original checkout bytes in the preservation report as well.
        assert old.replace(b'\r\n',b'\n')==(ROOT/name).read_bytes().replace(b'\r\n',b'\n')

def test_saved_envelope_and_necessary_witness():
    e=pd.read_csv(OUT/'CC4_SERVICE_TIMING_ENVELOPE.csv');validate_envelope(e.Q10,e.Q90)
    assert e.historical_submission_cohorts.min()>0
    a=read(OUT/'CC4_SERVICE_TIMING_ENVELOPE_AUDIT.json')
    assert not a['May_outcomes_used'] and not a['VALID_used']
    assert a['reference_kernel_mass']==pytest.approx(1)
    w=pd.read_csv(OUT/'NECESSARY_ANONYMOUS_WITNESS.csv');carry=read(OUT/'NECESSARY_CARRYOUT_WITNESS.json')
    b=read(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json');bounds=pd.read_csv(OUT/'MAY01_TS_CC4_RESOURCE_BOUND.csv')
    for h,g in w.groupby('hour'):
        assert g.GPUh.sum()+carry[str(h)]==pytest.approx(b['C0_Q50'][h])
        cumulative=0
        for r in g.itertuples():
            cumulative+=r.GPUh;lag=r.slot-4*h
            assert e.Q10[lag]*b['C0_Q50'][h]-1e-6<=cumulative<=e.Q90[lag]*b['C0_Q50'][h]+1e-6
    served=w.groupby('slot').GPUh.sum()
    assert all(r.known_GPU_lower_bound+4*served.get(r.Dday_slot,0)<=780+1e-6 for r in bounds.itertuples())

def test_stage_order_and_fresh_AC_guard():
    with pytest.raises(ValueError):require_next('M1',{})
    with pytest.raises(ValueError):require_kernel(dict(stage='M2',accepted_native_plan=True,sha256='a'*64),dict(PASS=False),{})
    assert not (OUT/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists()
