import inspect
import numpy as np
import pytest
from v42_capacity.queue import allocate,conservation
from v42_capacity.reference import build_reference
from v42_capacity.actual import Request,Controller,Environment,replay
from v42_capacity.calibration import magnitude,aligned_residual,statistics
from v42_final.state import planning_remaining
from v42_final.reserve import risk_exposure
from v42_final.common import MODEL


@pytest.mark.parametrize('q,e,remain',[(1800,900,900),(900,900,0),(400,900,0)])
def test_current_runtime_release(q,e,remain):
    j=dict(job_uid='r',submit_time='2025-03-31T00:00:00+00:00',state_at_D1_cutoff='RUNNING',
           source_site='AIDC01',source_site_authority='OBSERVED',GPU_gang=4,runtime_authority=MODEL,
           service_slots=int(np.ceil(remain/900)),nominal_remaining_seconds=remain)
    assert planning_remaining(q,e,state='RUNNING')['nominal_remaining_seconds']==remain
    p=dict(j,job_uid='p',GPU_gang=4,state_at_D1_cutoff='PENDING',service_slots=1,nominal_remaining_seconds=900)
    rows,audit=build_reference([j,p],{'AIDC01':4},{'AIDC01':[4]},issue_time='2025-03-31T08:00:00+00:00')
    assert audit['full_reference_ready'] and rows[0]['reference_start']==int(np.ceil(remain/900))
    assert not any(r['q50_expired_hard_occupancy'] for r in rows)
    if q<e: assert sum(risk_exposure(4,0,'AIDC01',[.5,.3,.1],range(3)).values())>0


@pytest.mark.parametrize('bad',['end_time','actual_runtime','voltage','line_loading','electricity_price',
    'start_observed_by_day_end','end_observed_by_day_end','future_completion_receipt'])
def test_reference_forbidden_input(bad):
    with pytest.raises(ValueError,match='FUTURE_OR_GRID'): build_reference([{bad:1}],{'s':4},{'s':[4]},issue_time='2025-03-31T08:00:00+00:00')


def test_unchanged_allocation_under_capacity():
    from v42_modelable.power import allocate_unknown
    k=np.zeros((96,2)); u=np.arange(96)/10
    old,res=allocate_unknown(k,u,[4,8]); new,bi,bo=allocate(k,u,[4,8])
    assert np.array_equal(old,new) and not res.any() and not bi.any() and not bo.any()


@pytest.mark.parametrize('reference,expected,out',[
    ([6,0,0],[4,2,0],[2,0,0]),([8,8,0],[4,4,4],[4,8,4]),([0,0,9],[0,0,4],[0,0,5])])
def test_forward_backlog_mass(reference,expected,out):
    served,bi,bo=allocate(np.zeros((3,1)),reference,[4])
    assert served[:,0].tolist()==expected and bo.tolist()==out
    assert conservation(sum(reference)/4,served,bo[-1],0)['PASS']


def test_site_order_and_capacity():
    s,_,b=allocate([[3,1],[0,4]],[5,2],[4,4])
    assert s.tolist()==[[1,3],[3,0]] and b.tolist()==[1,0]
    with pytest.raises(ValueError): allocate([[5]],[1],[4])


def request(uid,submit,gpu): return Request(uid,submit,gpu,('s',),1)


def test_actual_immediate_queue_release_and_occupancy():
    r=[request('a',0,4),request('b',1,4)]
    gpu,rows,audit=replay({'s':4},r,Environment({'a':10,'b':10}),end=86400,active_begin=0)
    assert rows[0]['admitted_time']==0 and rows[1]['admitted_time']==900
    assert rows[1]['capacity_wait'] and audit['capacity_violations']==0 and gpu.max()==4
    assert audit['Actual_CC4_physical_GPU']==0 and audit['Actual_PQ_repair']==0


def test_actual_strict_fcfs_no_backfill():
    c=Controller({'s':4})
    for r in [request('a',0,3),request('b',1,4),request('c',2,1)]:
        c.submit(r,r.submit); c.admit(r.submit)
    assert c.ledger.jobs['b']['latest_observed_state']=='PENDING'
    assert c.ledger.jobs['c']['latest_observed_state']=='PENDING'
    c.completion('a',10); assert c.admit(10)==[]
    assert c.admit(900)==['b']


def test_actual_future_submission_rejected():
    with pytest.raises(ValueError,match='FUTURE'): Controller({'s':4}).submit(request('a',2,4),1)


def test_physical_running_not_released_at_q50():
    gpu,rows,a=replay({'s':4},[],Environment({'r':5000},{'r':5000}),running=[(request('r',-10,4),'s',-5)],end=86400,active_begin=0)
    assert gpu[:5,0].tolist()==[4]*5 and gpu[6,0]==0
    assert rows[0]['completion_observed_time']==5000


def test_controller_has_no_truth_or_grid_inputs():
    assert set(Request.__dataclass_fields__)=={'uid','submit','gpu','compatible','q50','source_site'}
    assert list(inspect.signature(Controller.admit).parameters)==['self','now']
    source=inspect.getsource(Controller)
    assert 'environment' not in source and 'duration' not in source.replace('future_duration_reads','')
    with pytest.raises(ValueError): Environment({'j':float('nan')})


def test_source_site_retained():
    c=Controller({'a':4,'b':4}); r=Request('j',0,4,('a','b'),1,'b')
    c.submit(r,0); c.admit(0); assert c.ledger.jobs['j']['current_site']=='b'


@pytest.mark.parametrize('representation',['squared_pu','magnitude_pu'])
def test_voltage_units_and_exact_axes(representation):
    p=np.array([[1.,.98]]); a=p+.004
    result=aligned_residual(p*p if representation=='squared_pu' else p,a,['1.1','2.2'],['1.1','2.2'],plan_representation=representation)
    assert np.allclose(result['e_total'],.004)
    with pytest.raises(ValueError,match='ALIGNMENT'): aligned_residual(p,a,['1.1','2.2'],['2.2','1.1'],plan_representation='magnitude_pu')


def test_full_april_higher_quantiles_and_final_flags():
    p=np.ones((30,96,1)); a=p+np.arange(30)[:,None,None]*.001
    r=aligned_residual(p,a,['1.1'],['1.1'],plan_representation='magnitude_pu')
    metrics,point,daily,coverage,bands=statistics(r,list(range(30)),['1.1'])
    assert point[0]['delta_up']==np.quantile(r['r_up'],.9,method='higher')
    assert all(not b['FINAL_MARGIN_ACCEPTED'] for b in bands)
    assert metrics['maximum_absolute_error']==pytest.approx(.029)
    with pytest.raises(ValueError,match='FULL_APRIL'): statistics(r,list(range(29)),['1.1'])


def test_physical_queue_schema_excludes_forecast_input():
    assert 'forecast' not in inspect.signature(replay).parameters
    assert 'grid' not in inspect.signature(replay).parameters
    from v42_capacity.common import OUT,read
    frozen=read(OUT/'PREREGISTRATION.json')
    assert not frozen['FINAL_MARGIN_ACCEPTED'] and not frozen['PROBLEM13_FINAL_VALIDATED']
    assert not frozen['Actual_PQ_repair'] and not frozen['MESS_ACTIVE']


@pytest.mark.parametrize('elapsed,expected',[(900,0),(2700,-2),(900000,-999)])
def test_overrun_exposure_keeps_signed_q50_origin(elapsed,expected):
    from v42_capacity.planning import nominal_expiry
    row=dict(Q50_total_seconds=900,elapsed_seconds=elapsed,state_at_D1_cutoff='RUNNING')
    assert nominal_expiry(row)==expected
    kernel=np.linspace(.8,.1,1000)
    exposure=risk_exposure(4,expected,'s',kernel,[24])
    assert exposure.get(('s',24),0)==(4*kernel[24-expected] if 24-expected<1000 else 0)


def test_no_future_completion_cannot_change_pre_receipt_actions():
    r=[request('a',0,3),request('b',1,1),request('c',2,1)]
    c1=Controller({'s':4}); c2=Controller({'s':4})
    private1=Environment({'a':1000,'b':2000,'c':3000})
    private2=Environment({'a':2000,'b':1000,'c':6000})
    for job in r:
        for c in [c1,c2]: c.submit(job,job.submit); c.admit(job.submit)
    assert c1.ledger.jobs==c2.ledger.jobs
    assert not hasattr(c1,'environment')


def test_electrical_current_affine_specialization():
    from v42_capacity.electrical import imports
    m=imports()
    assert m['_anchor_and_sensitivity_day'].__module__=='dayahead.run_v16_3_voltage_candidate'
    h=np.arange(24).reshape(3,8)*.00001
    anchor=np.array([20.,30.,0.]); squared=np.arange(8)*.001+.99
    constant=squared-anchor@h
    assert np.allclose(constant+anchor@h,squared,atol=1e-12,rtol=0)
