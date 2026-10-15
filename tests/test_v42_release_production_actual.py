"""Named Native0 public/controller fixtures, never production performance."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_v42_release_actual import fixture as release_fixture
from test_v42_integration_actual import request
from v42_integration.release_production_actual import (ProductionCurrentController,
    ProductionResearchPolicy, initial_pending_placement, require_actual_gates, run_production_actual)
from v42_integration.aidc_sensitivity_runtime import CurrentEventJobEventController
from v42_integration.release_actual import ReleaseController
from v42_integration.policy import digest


def controller(*,uid='K',source=None,permission=False,command_site='B',gpu=1):
    commands={uid:dict(site=command_site,start_seconds=0,command_type='D0_PENDING_NEW_OPTIMIZED_START')}
    _,policy,oracle,_,provider=release_fixture(commands=commands)
    raw=dict(uid=uid,site=source,gpu=gpu,q50=900)
    c=ProductionCurrentController({'A':8,'B':8},arm='B3',qos_window_provider=provider,
        frozen_policy=policy,known_schedule=commands,initial_pending={uid:raw},
        backlog_contract={'pending_source_compatible_placement_research_authorized':True})
    r=request(uid,gpu=gpu,q50=900,origin_unknown=False,source_site=source,can_prestart_place=permission)
    c.submit(r,0)
    return c,policy,oracle,r


def test_production_controller_does_not_inherit_pr223_reference_fallback():
    assert issubclass(ProductionCurrentController,CurrentEventJobEventController)
    assert not issubclass(ProductionCurrentController,ReleaseController)


def test_source_strict_presite_mode_preserves_approved_basic_initial_STAY():
    _,p,o,_,provider=release_fixture(variant='C0')
    p.spec['actual_policy']={'mode':'SOURCE_STRICT','variant':'C0','research_contract':None}
    p.sha=digest(p.spec)
    c=ProductionCurrentController({'A':8,'B':8},arm='B3',qos_window_provider=provider,
        frozen_policy=p,known_schedule={},initial_pending={},backlog_contract={})
    r=request('U',source_site=None,can_prestart_place=False)
    c.submit(r,0)
    assert p.initial['U']['allowed'] and not hasattr(p,'research')
    assert c.admit(0)==['U'] and c.metadata['U']['current_site']=='A'
    assert r.metadata['can_prestart_place'] is False


def test_resource_bridge_uses_importable_original_timing_authority(monkeypatch):
    from v42_integration import aidc_resource_bridge
    from v42_integration.release_production_actual import _resource_bridge
    monkeypatch.setattr(aidc_resource_bridge,'PlanningActualResourceBridge',lambda a,**kw:kw)
    identity={k:'a'*64 for k in ('science_sha','initial_state_sha','cc4_sha','runtime_sha')}
    cc4=dict(model_id='model',prediction_sha='a'*64,kernel_sha='b'*64,
        q50_hourly_GPUh=[0]*24,q90_hourly_GPUh=[0]*24)
    context=dict(manifest=dict(source_sha='c'*64,identity=identity,time_axis_sha='d'*64,
        time_axis={'evaluation_begin_seconds':0}),cc4=cc4)
    bridge,_=_resource_bridge(context,{'case_sha':'e'*64,'aidc_anchor':'f'*64},{'A':8})
    assert len(bridge['timing_lower'])>0 and bridge['cc4_source_authority']['timing_envelope_sha']


def test_approved_source_less_initial_pending_starts_at_full_A2_site_with_source_flags_unchanged():
    c,p,o,r=controller()
    before=deepcopy(r.metadata)
    assert c.admit(0)==['K']
    assert c.metadata['K']['current_site']=='B'
    assert r.metadata==before and c.metadata['K']['can_prestart_place'] is False
    assert not c.corrective_commands
    assert c.known_schedule==p.reference.commands
    assert c.actual_start_events[0]['atomic_AC_rechecked'] is True


@pytest.mark.parametrize('mutation',[ 'not_initial','source_present','already_started','no_contract','is_unknown','running','wrong_gpu','future_command'])
def test_initial_placement_exception_never_expands_other_rights(mutation):
    c,_,_,_=controller()
    if mutation=='not_initial':c.production_initial_pending={}
    elif mutation=='source_present':c.production_initial_pending['K']['site']='A'
    elif mutation=='already_started':c.ledger.jobs['K']['start_time']=-1
    elif mutation=='no_contract':c.production_backlog={}
    elif mutation=='is_unknown':c.metadata['K']['origin_unknown']=True
    elif mutation=='running':c.metadata['K']['state']='RUNNING'
    elif mutation=='wrong_gpu':c.production_initial_pending['K']['gpu']=2
    elif mutation=='future_command':c.planning_commands['K']['start_seconds']=900
    assert initial_pending_placement(c,'K',0) is None


def test_original_hard_deadline_is_not_extended_by_initial_contract():
    c,_,_,_=controller()
    c.metadata['K']['completion_deadline_seconds']=100
    assert c.admit(0)==[]
    assert c.metadata['K']['state']=='PENDING'


@pytest.mark.parametrize('preserve_observed_proof',[True,False])
def test_actual_atomic_AC_wait_retries_same_A2_site_only_with_prior_observed_attempt(preserve_observed_proof):
    c,p,o,r=controller()
    original=deepcopy(c.planning_commands)
    def probe(history,row):
        ok=row['slot']>0
        return dict(PASS=ok,status='PASS' if ok else 'PHYSICAL_FAIL',physical_steps=[])
    o.probe=probe
    assert c.admit(0)==[] and c.observed_known_waits['K']['actual_START_attempt_observed']
    if not preserve_observed_proof:c.observed_known_waits.clear()
    assert c.admit(900)==(['K'] if preserve_observed_proof else [])
    assert c.planning_commands==original and r.metadata['can_prestart_place'] is False
    if preserve_observed_proof:
        assert c.metadata['K']['current_site']=='B'
        assert c.decisions['K']['additional_start_delay_seconds']==0
        assert c.decisions['K']['unavoidable_resource_wait_seconds']==900


def test_actual_GPU_conflict_does_not_become_new_initial_or_corrective_permission():
    c,_,_,_=controller(gpu=1)
    c.submit(request('occupied',gpu=8,q50=900,origin_unknown=False),0)
    # Use an exact observed physical occupant; no speculative Known booking.
    c.ledger.start('occupied','B',0,'E')
    c.metadata['occupied'].update(state='RUNNING',current_site='B',origin_unknown=False)
    assert initial_pending_placement(c,'K',0) is None


def test_production_invalid_context_is_rejected_before_private_input_module_import(monkeypatch,tmp_path):
    import sys
    sys.modules.pop('v42_integration.release_private_actual_inputs',None)
    with pytest.raises((ValueError,KeyError)):
        run_production_actual(context={'manifest':{'schema':'UNTRUSTED'}},a_result={},a_acceptance={},
            m_result={},m_acceptance={},output=tmp_path/'not_created',slots=96,gate={})
    assert not (tmp_path/'not_created').exists()
    assert 'v42_integration.release_private_actual_inputs' not in sys.modules


def test_fresh_rejects_failed_actual_stage_before_opening_trace_or_creating_output(monkeypatch,tmp_path):
    from v42_integration import release_p1_production
    from v42_integration.release_production_actual import run_production_fresh
    monkeypatch.setattr(release_p1_production,'verify_context',lambda *a,**kw:None)
    monkeypatch.setattr(release_p1_production,'require_production_acceptance',lambda *a,**kw:None)
    context={'manifest':{'identity':{},'source_sha':'s',
        'time_axis':{'evaluation_begin_seconds':1746021600}}}
    actual={'schema':'RELEASE_PRODUCTION_ACTUAL_EXECUTION_V1','fixture':False,'Actual_stage_PASS':False}
    with pytest.raises(ValueError,match='CURRENT_ACTUAL_AND_M2'):
        run_production_fresh(context=context,actual_result=actual,m_result={},m_acceptance={},
            output=tmp_path/'must_not_exist',slots=96,gate={})
    assert not (tmp_path/'must_not_exist').exists()


def test_new_production_funnel_short_circuits_GPU_before_research_provider():
    class Forbidden:
        def propose(self,*a,**kw):raise AssertionError('DATA_QOS_MUST_NOT_BE_EVALUATED')
    policy=object.__new__(ProductionResearchPolicy)
    policy._current_resource_ledger=SimpleNamespace(current_gpu_use=lambda *a,**kw:{'A':8,'B':8})
    policy.packet=SimpleNamespace(rack_compatibility={'A':[8],'B':[8]},capacities={'A':8,'B':8})
    policy.initial={'U':{'basic_site':'A'}};policy.research=Forbidden()
    row=policy._candidate(dict(uid='U',gpu=1,compatible_sites=['A','B']),'B',0,changing=True)
    assert row['reason']=='CURRENT_GPU_CAPACITY' and row['data_QoS_AC']=='NOT_EVALUATED'
