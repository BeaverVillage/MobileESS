"""Adversarial Supervisor D0 gates; named Native0 records are not May results.

The case tests use exact saved source metadata. The handoff/resource tests use
small named records and never call a planning model, Actual or native solver.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from v42_integration import d0_execution, d0_resource
from v42_integration.d0_case import compile_contracts, require_case, seal
from v42_integration.unified_contract import digest


@pytest.fixture(scope='module')
def source_case(tmp_path_factory):
    manifest,*_=compile_contracts(output=tmp_path_factory.mktemp('D0_SOURCE_METADATA_ONLY'))
    return manifest


def reseal_case(manifest):
    """An attacker can recompute hashes; frozen numeric/semantic checks remain."""
    result=deepcopy(manifest)
    result['source_sha']=result['source_freeze']['source_sha']
    result['time_axis_sha']=digest(result['time_axis'])
    result['physical_sha']=digest(result['physical'])
    science=result['science_payload']
    science.update(source=result['source_sha'],time_axis=result['time_axis_sha'],
        physical=result['physical_sha'],backlog=result['backlog_contract']['contract_sha'],
        CC4=result['forecast_receipt']['forecast_receipt_sha'])
    result['identity']['science_sha']=digest(science)
    result['case_payload'].update(science_sha=result['identity']['science_sha'],
        forecast=result['forecast_receipt']['forecast_receipt_sha'])
    result['identity']['case_sha']=digest(result['case_payload'])
    result.pop('manifest_sha',None)
    return seal(result,'manifest_sha')


def test_exact_case_metadata_is_verified_without_issuing_solver_or_old_prefix_gate(source_case):
    validated=require_case(source_case,stage='A1')
    assert validated['identity']['initial_state_sha']=='5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573'
    assert validated['time_axis']['historical_six_hour_prefix_is_new_gate'] is False


@pytest.mark.parametrize('field,error',[('science_sha','SCIENCE_DERIVATION'),('case_sha','CASE_PUBLIC_INPUT_DERIVATION')])
def test_resealed_wrong_science_or_case_hash_is_not_authority(source_case,field,error):
    forged=deepcopy(source_case);forged['identity'][field]='f'*64
    forged.pop('manifest_sha');forged=seal(forged,'manifest_sha')
    with pytest.raises(ValueError,match=error):require_case(forged)


def test_resealed_wrong_source_digest_cannot_bypass_frozen_files(source_case):
    forged=deepcopy(source_case);forged['source_freeze']['source_sha']='f'*64
    forged=reseal_case(forged)
    with pytest.raises(ValueError,match='SOURCE_TIME_PHYSICAL_DERIVATION'):require_case(forged)


def test_fully_resealed_extra_slot_and_different_svr_inventory_are_rejected(source_case):
    forged=deepcopy(source_case);forged['time_axis']['evaluation_end_seconds']+=900
    with pytest.raises(ValueError,match='ORIGINAL_APPROVED_TIME_PROJECTION'):
        require_case(reseal_case(forged))
    forged=deepcopy(source_case);forged['physical']['installed_SVR']=7
    with pytest.raises(ValueError,match='ORIGINAL_PHYSICAL_AUTHORITY'):
        require_case(reseal_case(forged))


def test_fully_resealed_scaled_forecast_cannot_claim_original_prediction(source_case):
    forged=deepcopy(source_case);forecast=forged['forecast_receipt']
    forecast['Q50_GPUh'][0]*=.5
    forecast.pop('forecast_receipt_sha');forged['forecast_receipt']=seal(forecast,'forecast_receipt_sha')
    forged['forecast_receipt_sha']=forged['forecast_receipt']['forecast_receipt_sha']
    with pytest.raises(ValueError,match='LITERAL_UNCHANGED_CC4_FORECAST'):
        require_case(reseal_case(forged))


def named_handoff(monkeypatch):
    """A tiny contract record with no numerical FULL/performance certification."""
    begin=90000.
    identity=dict(science_sha='a'*64,case_sha='b'*64,initial_state_sha='c'*64,
        cc4_sha='d'*64,runtime_sha='e'*64)
    manifest=dict(identity=identity,source_sha='1'*64,time_axis_sha='2'*64,
        time_axis=dict(planning_issue_epoch_seconds=begin,evaluation_begin_seconds=begin),
        initial_record=dict(path='NAMED_NATIVE0_SOURCE_NOT_READ'))
    rows=[dict(uid='R',D0_status='RUNNING',Q50_expired_running=False,
        fixed_running_site='A',gpu=2,elapsed_compute_seconds=900.,episode_id='R_EP',compatible_sites=['A']),
        dict(uid='H',D0_status='RUNNING',Q50_expired_running=True,
        fixed_running_site='B',gpu=1,elapsed_compute_seconds=7200.,episode_id='H_EP',compatible_sites=['B']),
        dict(uid='P',D0_status='PENDING',Q50_expired_running=False,
        fixed_running_site=None,gpu=1,elapsed_compute_seconds=0.,episode_id='P_EP',
        compatible_sites=['A','B'],legal_D0_start_seconds=[begin,begin+900])]
    context=dict(manifest=manifest,input_audit=dict(a_input_sha='3'*64),classification=rows,
        backlog=dict(contract_sha='4'*64),initial_mess=dict(plan_sha='5'*64),
        data=(None,None,None,None,{r['uid']:dict(GPU_gang=r['gpu']) for r in rows}))
    selected=dict(R=dict(start=24,initial_site='A',checkpoint=-1,segments=[['A',24,26]]),
        P=dict(start=24,initial_site='B',checkpoint=-1,segments=[['B',24,25]]))
    result=dict(stage='A1',source_identity=deepcopy(identity),D0_input_sha='3'*64,D0_issue_seconds=begin,
        input_MESS_anchor='5'*64,FULL_feasible=True,FULL_max_residual=0.,FULL_point_replay=dict(PASS=True),
        selected_jobs=selected,initial_Q50_expired_physical_holds=dict(H=dict(site='B',gpu=1,
            elapsed_seconds=7200.,physical_release_rule='OBSERVED_COMPLETION_ONLY')),
        AIDC_P_by_site={},AIDC_Q_by_site={},CC4_service={},CC4_carryout={},anonymous_resource_envelope=[],
        resource_sites=['A','B'],known_site_GPU=dict(A=[2.]*96,B=[2.]*96))
    result['case_sha']=digest(dict(parent=identity['case_sha'],stage='A1',
        input_MESS_anchor=result['input_MESS_anchor'],backlog_contract=context['backlog']['contract_sha']))
    fields=('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout','anonymous_resource_envelope')
    result['aidc_anchor']=digest({k:result[k] for k in fields})
    monkeypatch.setattr(d0_execution,'require_case',lambda m,**kw:m)
    monkeypatch.setattr(d0_execution,'build_approved_dday_observed_state',lambda *a,**kw:dict(named_fixture=True))
    monkeypatch.setattr(d0_execution,'require_initial_state_alignment',lambda *a,**kw:
        dict(status='PASS',scope='NAMED_CONTRACT_FIXTURE_ONLY'))
    return begin,context,result


def test_historical_a_and_wrong_new_stage_case_are_rejected_before_driver(monkeypatch):
    _,context,result=named_handoff(monkeypatch)
    historical=dict(case_sha='f'*64,stage='A1',FULL_feasible=True)
    with pytest.raises(ValueError,match='CURRENT_A_SOURCE_INPUT_BINDING'):
        d0_execution.compile_d0_commands(historical,context)
    changed=deepcopy(result);changed['case_sha']='f'*64
    with pytest.raises(ValueError,match='CURRENT_A_STAGE_CASE_DRIFT'):
        d0_execution.compile_d0_commands(changed,context)


def test_embedded_absolute_command_cannot_mask_an_old_native_prefix_start(monkeypatch):
    begin,context,result=named_handoff(monkeypatch)
    result['selected_jobs']['P'].update(start=23,start_seconds=begin,site='B')
    fields=('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout','anonymous_resource_envelope')
    result['aidc_anchor']=digest({k:result[k] for k in fields})
    with pytest.raises(ValueError,match='NATIVE_OPTION'):
        d0_execution.compile_d0_commands(result,context)


def test_truthy_text_does_not_claim_a_full_feasible_primal(monkeypatch):
    _,context,result=named_handoff(monkeypatch)
    result['FULL_feasible']='False'
    with pytest.raises(ValueError,match='FULL'):
        d0_execution.compile_d0_commands(result,context)


def test_pending_d0_start_and_historical_running_episode_are_distinct_native_coordinates(monkeypatch):
    begin,context,result=named_handoff(monkeypatch)
    before=digest(result['selected_jobs']);commands=d0_execution.compile_d0_commands(result,context)
    assert commands['R']['start_seconds']==begin
    assert commands['R']['historical_episode_start_seconds']==begin-900
    assert commands['R']['physical_job_restarted'] is False
    assert commands['P']['start_seconds']==begin
    assert commands['P']['command_type']=='D0_PENDING_NEW_OPTIMIZED_START'
    assert 'H' not in commands and digest(result['selected_jobs'])==before


def test_planned_first_interval_can_include_pending_d0_start_and_detects_gpu_drift(monkeypatch):
    begin,context,result=named_handoff(monkeypatch)
    commands=d0_execution.compile_d0_commands(result,context)
    request=lambda uid:SimpleNamespace(uid=uid,metadata=dict(origin_unknown=False))
    arguments=dict(begin=begin,end=begin+900,known_schedule=commands,
        running=[(request('R'),'A',begin-900),(request('H'),'B',begin-7200)],requests=[request('P')])
    identity=dict(source_sha=context['manifest']['source_sha'],stage_case_sha=result['case_sha'],
        science_sha=context['manifest']['identity']['science_sha'],initial_state_sha=d0_execution.SEMANTIC,
        time_axis_sha=context['manifest']['time_axis_sha'],cc4_sha='d'*64,runtime_sha='e'*64)
    handoff=d0_execution.require_d0_actual_handoff(result,context,arguments,identity=identity)
    assert handoff['status']=='PASS' and handoff['historical_prefix_gate_used'] is False
    changed=deepcopy(result);changed['known_site_GPU']['B'][0]=1.
    with pytest.raises(ValueError,match='PLANNED_FIRST_INTERVAL_KNOWN_GPU_COUPLING'):
        d0_execution.require_d0_actual_handoff(changed,context,arguments,identity=identity)


def named_budget(monkeypatch):
    budget=object.__new__(d0_resource.D0PilotBudget)
    budget.d0_manifest=dict(identity=dict(case_sha='a'*64,science_sha='b'*64),manifest_sha='c'*64)
    budget.d0_stage_case_sha='d'*64;budget.d0_source_input_sha='e'*64
    budget.stage_context=dict(D0_case_sha='a'*64,D0_science_sha='b'*64,
        stage_case_sha='d'*64,source_input_sha='e'*64)
    budget.pilot_started_used=292.443;budget.pilot_limit=25.;budget.return_reserve=30.
    budget.used=lambda:292.443;budget.remaining=lambda reserve=0:67.557-reserve
    monkeypatch.setattr(d0_resource,'require_case',lambda *a,**kw:budget.d0_manifest)
    return budget


@pytest.mark.parametrize('field,value',[('D0_case_sha','f'*64),('stage_case_sha','f'*64),('source_input_sha','f'*64)])
def test_pilot_cannot_solve_other_source_or_stage(monkeypatch,field,value):
    budget=named_budget(monkeypatch);budget.stage_context[field]=value
    with pytest.raises(ValueError,match='EXACT_USER_AUTHORIZED_A1_ONLY'):
        budget.solve(None,label='D0_A1_ORIGINAL_P1',cap=25.)


@pytest.mark.parametrize('threads,sense',[(2,1),(1,-1)])
def test_pilot_one_thread_and_original_minimization_are_mandatory_before_solver(monkeypatch,threads,sense):
    budget=named_budget(monkeypatch)
    monkeypatch.setattr(d0_resource,'native_binding',lambda _:dict(Threads=threads,objective_sense=sense))
    with pytest.raises(ValueError,match='MINIMIZATION_ONE_THREAD'):
        budget.solve(None,label='D0_A1_ORIGINAL_P1',cap=25.)


def test_pilot_total_cap_return_reserve_and_a2_labels_fail_before_solver(monkeypatch):
    budget=named_budget(monkeypatch)
    with pytest.raises(RuntimeError,match='LIMIT_OR_CANONICAL_RETURN_RESERVE'):
        budget.solve(None,label='D0_A1_ORIGINAL_P1',cap=26.)
    budget.remaining=lambda reserve=0:40.-reserve
    with pytest.raises(RuntimeError,match='LIMIT_OR_CANONICAL_RETURN_RESERVE'):
        budget.solve(None,label='D0_A1_ORIGINAL_P1',cap=25.)
    with pytest.raises(ValueError,match='EXACT_USER_AUTHORIZED_A1_ONLY'):
        budget.solve(None,label='D0_A2_ORIGINAL_P1',cap=1.)


def test_nonfinite_return_reserve_cannot_open_canonical_budget_admission(monkeypatch):
    monkeypatch.setattr(d0_resource.UnifiedResearchBudget,'__init__',lambda self:None)
    monkeypatch.setattr(d0_resource.D0PilotBudget,'used',lambda self:292.443)
    monkeypatch.setattr(d0_resource.D0PilotBudget,'remaining',lambda self,reserve=0:67.557-reserve)
    monkeypatch.setattr(d0_resource,'require_case',lambda manifest,**kw:manifest)
    with pytest.raises(ValueError,match='RETURN_RESERVE'):
        d0_resource.D0PilotBudget({},stage_case_sha='a'*64,source_input_sha='b'*64,
            return_reserve=float('nan'))


@pytest.fixture
def named_factory(monkeypatch,tmp_path):
    """Original factory call path with a mocked M producer, never a model."""
    from v42_integration import d0_case,d0_a_planning,production_case
    from v42_may_campaign_native90 import m_model
    import v42_native.grid
    import pandas as pd
    begin=90000.
    identity=dict(science_sha='a'*64,case_sha='b'*64,initial_state_sha='c'*64,
        cc4_sha='d'*64,runtime_sha='e'*64)
    manifest=dict(identity=identity,source_sha='1'*64,physical_sha='2'*64,time_axis_sha='3'*64,
        source_freeze={},manifest_sha='4'*64,initial_record={},
        time_axis=dict(planning_issue_epoch_seconds=begin))
    bundle=dict(capacities=dict(A=4,B=4),battery={})
    backlog=dict(contract_sha='5'*64)
    initial_plan=dict(P_by_site=dict(A=[0.]*96,B=[0.]*96),Q_by_site=dict(A=[0.]*96,B=[0.]*96),
        routes={},SOC={},Mode={},scope='NAMED_NATIVE0_CONTRACT_FIXTURE_ONLY')
    initial_plan['plan_sha']=digest(initial_plan)
    audit=dict(status='PASS',identity=identity,a_input_sha='6'*64,issue_seconds=begin)
    data=(bundle,{}, {},None,{}, {}, {},{})
    monkeypatch.setattr(d0_case,'compile_contracts',lambda **kw:
        (deepcopy(manifest),{},bundle,backlog,{},dict(kernel=[])))
    monkeypatch.setattr(d0_case,'require_case',lambda value,**kw:value)
    monkeypatch.setattr(d0_case,'read',lambda path:{})
    monkeypatch.setattr(d0_case,'_write',lambda *args,**kw:None)
    monkeypatch.setattr(d0_a_planning,'compile_d0_known_data',lambda *args,**kw:
        (data,[],audit,{},{}))
    physical=SimpleNamespace(certificate=dict(input_identity=dict(identity=dict(inputs=dict(
        OpenDSS_master=dict(sha256='7'*64))))),thermal=dict(transformer_current_authority_sha256='8'*64),
        coefficients=())
    monkeypatch.setattr(production_case,'ProductionPhysicalContext',lambda *args:physical)
    monkeypatch.setattr(production_case,'planning_power',lambda *args:({},1.,1.,[]))
    monkeypatch.setattr(production_case,'initial_mess',lambda *args:deepcopy(initial_plan))
    monkeypatch.setattr(v42_native.grid,'GridAuthority',lambda *args,**kw:None)
    monkeypatch.setattr(pd,'read_csv',lambda *args,**kw:SimpleNamespace(Q10=[],Q90=[]))
    calls=[]
    def mocked_m_build(payload,settings,**kwargs):
        calls.append(deepcopy(payload))
        standalone=dict(arm='B2',standalone_original_M_producer=True,payload=deepcopy(payload))
        return SimpleNamespace(identity=standalone,case_sha=digest(standalone))
    monkeypatch.setattr(m_model,'build_case',mocked_m_build)
    context=d0_case.build_planning_inputs(output=tmp_path)
    def a_result(case,value=0.):
        result=dict(stage=case.stage,case_sha=case.case_sha,source_identity=identity,D0_input_sha=audit['a_input_sha'],
            D0_issue_seconds=begin,input_MESS_anchor=case.grid.fixed_mess['plan_sha'],FULL_feasible=True,
            FULL_point_replay=dict(PASS=True,scope='NAMED_INTERFACE_FIXTURE_ONLY'),FULL_max_residual=0.,
            selected_jobs={},AIDC_P_by_site=dict(A=[value]*96,B=[value]*96),
            AIDC_Q_by_site=dict(A=[0.]*96,B=[0.]*96),CC4_service={},CC4_carryout={},anonymous_resource_envelope=[])
        result['aidc_anchor']=digest({k:result[k] for k in (
            'selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout','anonymous_resource_envelope')})
        return result
    def m_result(case):
        plan=deepcopy(initial_plan);plan.pop('plan_sha');plan['case_sha']=case.case_sha;plan['plan_sha']=digest(plan)
        return dict(stage=case.identity['stage'],case_sha=case.case_sha,FULL_validated=True,
            binding=dict(aidc_anchor=case.identity['aidc_anchor']),mess=plan)
    a1=a_result(context['make_a_case']('A1'))
    return context,a1,a_result,m_result,calls,tmp_path


def test_factory_a1_m1_a2_m2_binds_original_flat_m_identity_and_each_anchor(named_factory):
    context,a1,a_result,m_result,calls,folder=named_factory
    m1=context['make_m_case']('M1',a1,folder/'M1')
    assert m1.identity['arm']=='B3' and m1.identity['stage']=='M1'
    assert m1.identity['aidc_anchor']==a1['aidc_anchor']
    assert m1.identity['qos_sha']==context['backlog']['contract_sha']
    assert m1.case_sha==digest(m1.identity)
    assert calls[-1]['planning']['complete_AIDC_anchor']==a1['aidc_anchor']
    bound_m1=context['bind_m_result'](m_result(m1))
    assert bound_m1['D0_source_identity']==context['manifest']['identity']
    a2_case=context['make_a_case']('A2',fixed_mess=bound_m1['mess'],upstream_m_result=bound_m1)
    a2=a_result(a2_case,value=1.)
    m2=context['make_m_case']('M2',a2,folder/'M2')
    assert m2.identity['stage']=='M2' and m2.identity['aidc_anchor']==a2['aidc_anchor']
    assert m2.case_sha!=m1.case_sha and a2['input_MESS_anchor']==bound_m1['mess']['plan_sha']
    assert context['bind_m_result'](m_result(m2))['D0_fixed_AIDC_anchor']==a2['aidc_anchor']


@pytest.mark.parametrize('field,value',[
    ('source_identity',{}),('D0_input_sha','f'*64),('case_sha','f'*64),('FULL_feasible','False')])
def test_m_factory_rejects_old_or_changed_a_before_original_m_producer(named_factory,field,value):
    context,a1,_,_,calls,folder=named_factory
    changed=deepcopy(a1);changed[field]=value
    with pytest.raises(ValueError,match='D0_M'):
        context['make_m_case']('M1',changed,folder/'BAD_M1')
    assert calls==[]


@pytest.mark.parametrize('change',['stage','FULL_validated','aidc_anchor','plan_case'])
def test_m_binding_requires_exact_stage_boolean_fixed_a_and_plan_case(named_factory,change):
    context,a1,_,m_result,_,folder=named_factory
    m1=context['make_m_case']('M1',a1,folder/'M1');result=m_result(m1)
    if change=='stage':result['stage']='M2'
    elif change=='FULL_validated':result['FULL_validated']='False'
    elif change=='aidc_anchor':result['binding']['aidc_anchor']='f'*64
    else:
        result['mess']['case_sha']='f'*64;result['mess'].pop('plan_sha')
        result['mess']['plan_sha']=digest(result['mess'])
    with pytest.raises(ValueError,match='D0_M_RESULT'):
        context['bind_m_result'](result)


def test_a2_requires_successfully_bound_m1_and_failed_plan_does_not_register_anchor(named_factory):
    context,a1,a_result,m_result,_,folder=named_factory
    m1=context['make_m_case']('M1',a1,folder/'M1');unbound=m_result(m1)
    unbound['D0_source_identity']=context['manifest']['identity']
    with pytest.raises(ValueError,match='D0_A2'):
        context['make_a_case']('A2',fixed_mess=unbound['mess'],upstream_m_result=unbound)
    invalid=deepcopy(unbound);invalid['mess']['case_sha']='f'*64;invalid['mess'].pop('plan_sha')
    invalid['mess']['plan_sha']=digest(invalid['mess'])
    with pytest.raises(ValueError,match='D0_M_RESULT_PLAN_STAGE_CASE'):
        context['bind_m_result'](invalid)
    staged_a2=a_result(SimpleNamespace(stage='A2',case_sha=digest(dict(parent=context['manifest']['identity']['case_sha'],
        stage='A2',input_MESS_anchor=invalid['mess']['plan_sha'],backlog_contract=context['backlog']['contract_sha'])),
        grid=SimpleNamespace(fixed_mess=invalid['mess'])))
    with pytest.raises(ValueError,match='D0_M2_CURRENT_A2_M1_ANCHOR'):
        context['make_m_case']('M2',staged_a2,folder/'BAD_M2')
