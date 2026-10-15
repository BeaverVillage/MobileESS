"""Named Native0 fixtures; no May performance is inferred from these."""
from copy import deepcopy
import numpy as np
import pytest
from v42_capacity.actual import Environment
from v42_integration.actual import FrozenPowerModel,run_actual
from v42_integration.current_ac_admission import CausalSeries,CausalObservations,CurrentACAdmission
from v42_integration.release_actual import ReleasePolicy,ReleaseController,initial_authority,completed_prefix
from v42_integration.policy import digest
from test_v42_aidc_followup import current_fixture,ready_data
from test_v42_integration_actual import request


def observations():
    def series(name,values):return CausalSeries([dict(observed_seconds=0,available_seconds=0,values=values)],name=name)
    return CausalObservations(series('demand',{'demand_mw':1}),series('pv',{'pv_mw':0}),
        series('weather',{'t_wb_c':10,'rh_pct':50}))


class Probe:
    def __init__(self,limit=99):self.limit=limit;self.rows=[]
    def __call__(self,history,row):
        self.rows.append((history,row));ok=sum(row['GPU'])<=self.limit
        return dict(PASS=ok,status='PASS' if ok else 'PHYSICAL_FAIL',
            physical_steps=[dict(maximum_phase_line_loading=.5,PASS=ok)],future_native_Tap_actions_executed=0)
    def predicted_score(self,rows):
        # Current A looks better, but all-public-service-slot max makes B better.
        return dict(status='PASS',grid_peak=max((.2 if r['GPU'][0] else .3) if r['slot']==0
            else (.9 if r['GPU'][0] else .4) for r in rows))


def fixture(variant='C1',probe=None,commands=None):
    provider,old=current_fixture(commands=commands,basic=False)
    power=FrozenPowerModel(.1,1.,{'A':8,'B':8},.95,lambda it,w:np.asarray(it),'NAMED_ORIGINAL_C1')
    oracle=CurrentACAdmission(begin=0,sites=('A','B'),power_model=power,observations=observations(),probe=probe or Probe())
    identity={'study_case_sha':'fixture'}
    policy=ReleasePolicy(old.reference,old.packet,variant=variant,oracle=oracle,bindings=old.bindings,
        expected_bindings=old.bindings,evidence_scope='NAMED_RC01',source_identity=identity,
        site_authority=initial_authority(old.bindings,'fixture'))
    c=ReleaseController({'A':8,'B':8},arm='B3',qos_window_provider=provider,frozen_policy=policy,
        known_schedule=commands or {})
    return c,policy,oracle,power,provider


def choose(c,p,o,r):
    c.submit(r,0);p.observe(0,{'A':0,'B':0},c.metadata);o.observe(0,[])
    return p.select(c.metadata[r.uid],c.budgets[r.uid],0,c.reservations,reserve=False)


def test_initial_research_placement_needs_no_presite_permission_and_registers_no_gpu():
    c,p,o,_,_=fixture();r=request('U',source_site=None,can_prestart_place=False)
    c.submit(r,0)
    assert p.initial['U']['authority']=='RESEARCH_INITIAL_PLACEMENT'
    assert p.initial['U']['allowed'] and not p.initial['U']['sensitivity_used']
    assert c.ledger.physical(0)=={'A':0,'B':0}


@pytest.mark.parametrize('permission,data',[(False,None),(True,None),(True,ready_data(ready_at_seconds={'B':900}))])
def test_missing_or_not_ready_presite_stays_and_basic_start_succeeds(permission,data):
    c,p,o,_,_=fixture();d=choose(c,p,o,request('U',can_prestart_place=permission,preplacement_data=data))
    assert d['site']=='A' and d['action']=='START'
    assert not next(r for r in p.candidate_events[-1]['candidates'] if r['site']=='B')['feasible']


def test_c0_same_initial_stays_while_c1_public_multislot_strict_improvement_changes():
    choices=[]
    for label in ('C0','C1'):
        c,p,o,_,_=fixture(label)
        d=choose(c,p,o,request('U',q50=1800,can_prestart_place=True,preplacement_data=ready_data()))
        choices.append(d['site'])
        assert p.initial['U']['basic_site']=='A'
    assert choices==['A','B']
    row=p.candidate_events[-1]['candidates'][1]['sensitivity_score']
    assert row['checked_slots']==[0,1] and row['future_Actual_Tap_Completion_reads']==0


def test_unvalidated_prediction_fails_closed_to_stay_without_blocking_initial():
    c,p,o,_,_=fixture(probe=lambda h,r:dict(PASS=True,status='PASS',physical_steps=[]))
    d=choose(c,p,o,request('U',can_prestart_place=True,preplacement_data=ready_data()))
    assert d['site']=='A'


@pytest.mark.parametrize('failure_stage',['candidate','prediction'])
def test_optional_ac_failure_keeps_already_feasible_stay(failure_stage):
    class FailingProbe(Probe):
        def __call__(self,history,row):
            if failure_stage=='candidate' and row['GPU'][1]:raise ValueError('CANDIDATE_NONCONVERGENCE')
            return super().__call__(history,row)
        def predicted_score(self,rows):raise ValueError('PREDICTION_NOT_CERTIFIED')
    c,p,o,_,_=fixture(probe=FailingProbe())
    decision=choose(c,p,o,request('U',can_prestart_place=True,preplacement_data=ready_data()))
    assert decision['site']=='A' and decision['action']=='START'


def test_baseline_pass_cannot_authorize_candidate_and_atomic_start_rechecks():
    c,p,o,_,_=fixture(probe=Probe(limit=0));o.observe(0,[])
    assert o.evaluate(0,[0,0])['PASS']
    d=choose(c,p,o,request('U'))
    assert d['action']=='QUEUE' and not o.evaluate(0,[1,0])['PASS']
    assert p.current_guard(c.metadata['U'],[dict(resource='gpu:A',begin=0,end=900,quantity=1)],0,{'A':0,'B':0})


def test_running_cannot_presite_even_if_permission_and_data_exist():
    c,p,o,_,_=fixture();c.submit(request('U',can_prestart_place=True,preplacement_data=ready_data()),0)
    p.observe(0,{'A':1,'B':0},c.metadata);o.observe(0,[]);c.metadata['U']['state']='RUNNING'
    p.designate(c.metadata['U'],0)
    assert p._candidate(c.metadata['U'],'B',0,changing=True)['reason']=='PENDING_ONLY_RUNNING_MOVE_HOLD'


def test_asof_uses_lastchanged_and_never_interpolates_future():
    s=CausalSeries([dict(observed_seconds=0,available_seconds=0,values={'x':1}),
        dict(observed_seconds=900,available_seconds=1200,values={'x':9})],name='x')
    assert s.at(900,observed_now=900)['values']['x']==1
    assert s.at(1200,observed_now=1200)['values']['x']==9
    with pytest.raises(ValueError,match='FUTURE'):s.at(1200,observed_now=900)
    with pytest.raises(ValueError,match='FUTURE'):s.at(0,observed_now=float('nan'))


def test_nonfinite_and_conflicting_source_rows_fail_closed():
    with pytest.raises(ValueError,match='NONFINITE'):
        CausalSeries([dict(observed_seconds=0,available_seconds=float('nan'),values={'x':1})],name='x')
    with pytest.raises(ValueError,match='CONFLICTING'):
        CausalSeries([dict(observed_seconds=0,available_seconds=0,values={'x':x}) for x in (1,2)],name='x')


def test_past_prefix_integrates_observed_completion_not_previous_tick_hold():
    c,p,o,_,_=fixture();c.submit(request('U',gpu=4),0);c.ledger.start('U','A',0,'E')
    c.ledger.complete('U',450,450)
    rows=completed_prefix(c,900)
    np.testing.assert_allclose(rows[0]['GPU'],[2,0])
    assert rows[0]['end_seconds']==900 and rows[0]['authority'].startswith('OBSERVED_EPISODE')
    with pytest.raises(ValueError,match='COMPLETE_PAST'):o.observe(900,[])


def test_event_engine_actual_start_and_completion_preserve_integral_and_initial_site():
    c,p,o,power,provider=fixture('C0')
    result=run_actual({'A':8,'B':8},[request('U',gpu=4,q50=900,can_prestart_place=False)],
        Environment({'U':450}),begin=0,end=1800,arm='B3',qos_window_provider=provider,
        frozen_policy=p,controller_class=ReleaseController,expected_bindings=p.bindings,power_model=power,weather=[{}]*2)
    state=result['carryout']['controller']['release_state']
    assert state['initial_placements'][0]['basic_site']=='A'
    assert state['actual_starts'][0]['site']=='A' and state['actual_starts'][0]['time_seconds']==0
    np.testing.assert_allclose(result['occupancy_GPU'],[r['GPU'] for r in state['prefix']])
    assert result['queue_ledger'][0]['completion_observed_time']==450


def test_reused_physical_scope_still_checks_each_authority_byte(monkeypatch):
    import v42_integration.current_ac_admission as module
    import v42_svr11.authority as authority
    import v42_voltage_control.integration as physical
    _,_,oracle,_,_=fixture();oracle.freeze={'source_sha':'source'}
    oracle.manifest={k:{'path':k,'sha256':k} for k in ('hardware','scenario','thermal')}
    scope=dict(oracle.manifest,execution_SHA='source',integration_validation_only=True)
    checked=[]
    monkeypatch.setattr(authority,'active',lambda:scope)
    monkeypatch.setattr(module,'checked',lambda r:checked.append(r['path']) or r['path'])
    monkeypatch.setattr(module,'read',lambda p:{'scenario':'fixture'})
    monkeypatch.setattr(physical,'validate_scenario',lambda s:None)
    with oracle._hardware_context() as scenario:assert scenario=={'scenario':'fixture'}
    assert set(checked)=={'hardware','scenario','thermal'}
    def corrupt(r):raise ValueError('HARDWARE_BYTES_CHANGED')
    monkeypatch.setattr(module,'checked',corrupt)
    with pytest.raises(ValueError,match='BYTES_CHANGED'):
        with oracle._hardware_context():pass


@pytest.mark.parametrize('ready',[False,True])
def test_known_only_corrects_actual_conflict_with_source_readiness_and_keeps_plan(ready):
    commands={'K':dict(site='A',start_seconds=900,protected_segments=[
        dict(resource='gpu:A',begin=900,end=1800,quantity=8)])}
    _,p,_,power,provider=fixture('C1',commands=commands)
    u=request('U',gpu=8,q50=450,compatible=('A',),can_prestart_place=False)
    k=request('K',gpu=8,q50=900,origin_unknown=False,can_prestart_place=True,qos='normal',protected=False,
        reference_start_seconds=900,preplacement_data=ready_data() if ready else None)
    result=run_actual({'A':8,'B':8},[u,k],Environment({'U':2250,'K':900}),begin=0,end=4500,
        arm='B3',qos_window_provider=provider,frozen_policy=p,known_schedule=commands,
        controller_class=ReleaseController,expected_bindings=p.bindings,power_model=power,weather=[{}]*5)
    known=next(r for r in result['queue_ledger'] if r['job_uid']=='K')
    assert (known['site'],known['admitted_time'])==(('B',900) if ready else ('A',2700))
    state=result['carryout']['controller']
    assert state['isolated_reference_state']['historical_planning_commands_sha']==digest(commands)
    assert p.reference.commands==commands
    assert result['receipt']['future_completion_controller_reads']==0
