from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import runpy

import pytest

from v42_integration import release_date_execution as api
from v42_integration.d0_a_planning import classify_d0_backlog
from v42_integration.unified_contract import digest


def named_fixture(monkeypatch):
    # Reuse the existing explicit private-field poison and original provider
    # fixture; this is a contract fixture, never a numerical FULL certificate.
    source = runpy.run_path(str(Path(__file__).with_name('test_v42_d0_actual_inputs.py')))
    state, provider, args, _ = source['fixture']()
    state['capacities']=dict(args['capacities'])
    begin = state['begin_epoch_seconds']
    state['historical_completed'] = [dict(job_uid='COMPLETED',original_native_site='A',
        observed_start_seconds=begin-8000,observed_completion_seconds=begin-4000,
        observed_control_release_seconds=begin-3600,GPU_gang=1)]
    identity = provider.identity
    rows, audit = classify_d0_backlog(state,source_identity=identity)
    for row in rows:
        row['legal_D0_start_seconds'] = [begin,begin+900] if row['D0_status']=='PENDING' else [begin]
    manifest = dict(schema='NAMED_NUMERIC_CONTRACT_FIXTURE_ONLY',identity=identity,source_sha='1'*64,
        time_axis_sha='2'*64,time_axis=dict(planning_issue_epoch_seconds=begin,evaluation_begin_seconds=begin),
        initial_record=dict(path='NAMED_SOURCE_NOT_REAL_AUTHORITY'))
    context = dict(manifest=manifest,state=state,input_audit=dict(a_input_sha='3'*64),classification=rows,
        backlog=provider.contract,data=(None,None,None,None,{r['uid']:dict(GPU_gang=r['gpu']) for r in rows}))
    selected = dict(P=dict(start=24,initial_site='B',segments=[['B',24,26]],checkpoint=-1))
    result = dict(stage='A1',source_identity=identity,D0_input_sha='3'*64,D0_issue_seconds=begin,
        input_MESS_anchor='5'*64,FULL_feasible=True,FULL_max_residual=0.,FULL_point_replay=dict(PASS=True),
        selected_jobs=selected,initial_Q50_expired_physical_holds=dict(R=dict(site='A',gpu=1,
            elapsed_seconds=2700,physical_release_rule='OBSERVED_COMPLETION_ONLY')),
        AIDC_P_by_site={},AIDC_Q_by_site={},CC4_service={},CC4_carryout={},anonymous_resource_envelope=[],
        resource_sites=['A','B'],known_site_GPU=dict(A=[1.]*96,B=[1.]*96))
    result['case_sha'] = digest(dict(parent=identity['case_sha'],stage='A1',input_MESS_anchor='5'*64,
        backlog_contract=provider.contract['contract_sha']))
    result['aidc_anchor'] = digest({k:result[k] for k in ('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site',
        'CC4_service','CC4_carryout','anonymous_resource_envelope')})
    monkeypatch.setattr(api,'_state',lambda c: state)
    monkeypatch.setattr(api,'_initial_mess_sha',lambda c:'5'*64)
    return state,provider,args,context,result


def test_may01_helpers_delegate_directly_without_rewriting_inputs(monkeypatch):
    context = dict(manifest=dict(time_axis=dict(planning_issue_epoch_seconds=1746021600.)))
    sentinel = object()
    for name, owner in [('compile_d0_commands',api.original_execution),('project_d0_driver_arguments',api.original_inputs),
        ('require_d0_actual_handoff',api.original_execution)]:
        monkeypatch.setattr(owner,name,lambda *a,**kw:sentinel)
    assert api.compile_date_commands({},context) is sentinel
    assert api.project_date_driver_arguments({},state={},provider=None,context=context) is sentinel
    assert api.require_date_actual_handoff({},context,{},identity={}) is sentinel


def test_projection_keeps_private_environment_opaque_future_request_identical_and_source_unchanged(monkeypatch):
    state,p,args,c,_ = named_fixture(monkeypatch)
    future = args['requests'][1]
    projected = api.project_date_driver_arguments(args,state=state,provider=p,context=c,evidence_scope='NAMED_NUMERIC_FIXTURE')
    assert projected.arguments['environment'] is args['environment']
    assert projected.arguments['requests'][1] is future
    assert projected.arguments['requests'][0].metadata['origin_unknown'] is False
    assert projected.arguments['requests'][0].metadata['cc4_eligible'] is False
    assert args['requests'][0].metadata['origin_unknown'] is True
    assert 'reused_planning_qos_authority' not in projected.arguments['requests'][0].metadata
    assert projected.receipt['Actual_engine_calls']==0 and not projected.receipt['private_environment_fields_read']


def test_source_protection_and_preplace_flags_are_not_silently_repaired(monkeypatch):
    state,p,args,c,_=named_fixture(monkeypatch)
    args['requests'][0]=replace(args['requests'][0],metadata=dict(args['requests'][0].metadata,protected=False))
    with pytest.raises(ValueError,match='SOURCE_METADATA_DRIFT'):
        api.project_date_driver_arguments(args,state=state,provider=p,context=c)


def test_provider_of_another_case_is_rejected(monkeypatch):
    state,p,args,c,_=named_fixture(monkeypatch)
    p.identity=dict(p.identity,case_sha='f'*64)
    with pytest.raises(ValueError,match='PROVIDER_SOURCE_CASE'):
        api.project_date_driver_arguments(args,state=state,provider=p,context=c)


def test_missing_pending_or_changed_running_history_fail_closed(monkeypatch):
    state,p,args,c,_=named_fixture(monkeypatch)
    args['requests']=args['requests'][1:]
    with pytest.raises(ValueError,match='PENDING_ROSTER'):
        api.project_date_driver_arguments(args,state=state,provider=p,context=c)
    state,p,args,c,_=named_fixture(monkeypatch)
    r,s,t=args['running'][0];args['running']=[(r,s,t+900)]
    with pytest.raises(ValueError,match='RUNNING_SITE_HISTORY'):
        api.project_date_driver_arguments(args,state=state,provider=p,context=c)


def test_native_command_mapping_keeps_expired_running_hold_and_full_pending_start(monkeypatch):
    state,_,_,c,a=named_fixture(monkeypatch)
    result=api.compile_date_commands(a,c)
    assert set(result)=={'P'} and result['P']['start_seconds']==state['begin_epoch_seconds']
    assert result['P']['command_type']=='D0_PENDING_NEW_OPTIMIZED_START'
    assert a['initial_Q50_expired_physical_holds']['R']['physical_release_rule']=='OBSERVED_COMPLETION_ONLY'


@pytest.mark.parametrize('change,error',[
    (dict(FULL_feasible=False),'BOOLEAN_FULL'),
    (dict(FULL_max_residual=1.),'ORIGINAL_FULL_POINT'),
    (dict(case_sha='f'*64),'STAGE_CASE'),
    (dict(D0_issue_seconds=0.),'SOURCE_INPUT_BINDING'),
])
def test_foreign_or_nonfull_planning_result_is_rejected_before_driver(monkeypatch,change,error):
    _,_,_,c,a=named_fixture(monkeypatch);a.update(change)
    with pytest.raises(ValueError,match=error):api.compile_date_commands(a,c)


def actual_packet(monkeypatch):
    state,p,args,c,a=named_fixture(monkeypatch)
    projection=api.project_date_driver_arguments(args,state=state,provider=p,context=c,evidence_scope='NAMED_NUMERIC_FIXTURE')
    arguments=dict(projection.arguments,known_schedule=api.compile_date_commands(a,c))
    identity=dict(source_sha='1'*64,stage_case_sha=a['case_sha'],science_sha=p.identity['science_sha'],
        initial_state_sha=state['common_initial_state_sha'],time_axis_sha='2'*64,
        cc4_sha=p.identity['cc4_sha'],runtime_sha=p.identity['runtime_sha'])
    return state,arguments,c,a,identity


def test_public_handoff_joins_exact_dynamic_population_without_reading_environment(monkeypatch):
    state,args,c,a,identity=actual_packet(monkeypatch)
    receipt=api.require_date_actual_handoff(a,c,args,identity=identity)
    assert receipt['status']=='PASS' and receipt['D0_known_population']==2
    assert receipt['actual_initial_state_join']['Running_UIDs']==1
    assert receipt['actual_initial_state_join']['Pending_UIDs']==1
    assert receipt['Actual_engine_calls']==0 and not receipt['private_environment_fields_read']


def test_foreign_initial_identity_and_retimed_command_rejected(monkeypatch):
    _,args,c,a,identity=actual_packet(monkeypatch)
    with pytest.raises(ValueError,match='EXACT_IDENTITY'):
        api.require_date_actual_handoff(a,c,args,identity=dict(identity,initial_state_sha='f'*64))
    args['known_schedule']['P']['start_seconds']+=900
    with pytest.raises(ValueError,match='COMMAND_DRIFT'):
        api.require_date_actual_handoff(a,c,args,identity=identity)


def test_first_interval_gpu_coupling_revalidated(monkeypatch):
    _,args,c,a,identity=actual_packet(monkeypatch)
    a['known_site_GPU']['B'][0]=2.
    with pytest.raises(ValueError,match='GPU_COUPLING'):
        api.require_date_actual_handoff(a,c,args,identity=identity)


def test_saved_real_may01_command_compilation_is_exact_original_and_native_zero(monkeypatch):
    from v42_integration import release_date_case as cases
    from v42_integration.release_p1_acceptance import saved_a1
    folder=cases.BASE/'RC02/DATE_CASES/COMPILE01/2025-05-01/CASE'
    if not folder.exists():pytest.skip('Authoritative local saved May01 case is unavailable')
    import gurobipy as gp
    def forbidden(*a,**k):raise AssertionError('Command handoff must not create or solve a model')
    for name in ('__init__','optimize','presolve','computeIIS'):monkeypatch.setattr(gp.Model,name,forbidden)
    context=cases.load_date_case('2025-05-01',folder)
    result=saved_a1()['result']
    assert api.compile_date_commands(result,context)==api.original_execution.compile_d0_commands(result,context)
