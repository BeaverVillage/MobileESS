from copy import deepcopy
from pathlib import Path
import pytest

from v42_integration.d0_a_planning import (BACKLOG_SCHEMA,D0ACase,NATIVE_OFFSET,
    _compile_d0_known_data,build_d0_native_model,classify_d0_backlog,current_hard_runtime_overlap,digest,input_fingerprint,validate_backlog_contract)
from v42_integration.dday_initialization import load_dday_state


def fixture_packet():
    begin=90000
    identity=dict(science_sha='a'*64,case_sha='b'*64,initial_state_sha='c'*64,cc4_sha='d'*64,runtime_sha='e'*64)
    def row(uid,state,*,gpu=1,elapsed=0,q50=1800,origin=False,site=None):
        return dict(uid=uid,episode_id=uid+'_EPISODE',gpu=gpu,site=site,submit_seconds=begin-7200,
            observed_start_seconds=begin-elapsed if state=='RUNNING' else None,elapsed_compute_seconds=elapsed,
            q50=q50,compatible_sites=['A','B'],origin_unknown=origin,
            metadata=dict(qos='UNCONFIRMED',protected=None,batch_eligible=None,can_prestart_place=True,
                migration_capability=None,representation_starts_seconds=[begin+t*900 for t in range(96)]))
    state=dict(begin_epoch_seconds=begin,common_initial_state_sha='c'*64,capacities=dict(A=4,B=4),rack_compatibility=dict(A=[4],B=[4]),
        running=[row('R','RUNNING',gpu=2,elapsed=900,q50=2700,site='A'),
            row('OVER','RUNNING',elapsed=7200,q50=1800,origin=True,site='B')],
        pending=[row('P','PENDING',origin=True),row('LONG','PENDING',q50=90000)],
        historical_completed=[dict(job_uid='COMPLETED')])
    source_bundle=dict(capacities=deepcopy(state['capacities']),day='1970-01-02',
        racks=[dict(aidc_id=s,compatibility_GPU_limit=4) for s in ('A','B')],
        WAN=dict(link_capacity_bytes_15min={'AB':[100]*96},paths=[dict(source='A',destination='B',links=['AB'])],
            bytes_per_gpu=100,restart_slots=1,maximum_active_transfers=1),
        known_population=[dict(job_uid='OLD_JOB_SHOULD_NOT_REMAIN')],
        C0_Q50=[1.]*24,C0_Q90=[2.]*24,runtime_survival_kernel=[1,.5,.25],runtime_reserve_gamma=1)
    contract=dict(schema=BACKLOG_SCHEMA,policy_id='D0_EXPLICIT_BASE_BACKLOG_STUDY',issue_seconds=begin,end_seconds=begin+86400,
        initial_state_sha=identity['initial_state_sha'],initial_backlog_optimization_authorized=True,site_scope='SOURCE_COMPATIBLE_ONLY',
        pending_source_compatible_placement_research_authorized=True,
        automatic_hard_deadline_extension=False,source_protection_confirmed_by_research=False,customer_SLA_claimed=False,
        additional_intentional_delay_budget_seconds=0)
    contract['contract_sha']=digest(contract)
    cc4=dict(issue_seconds=begin,day_begin_seconds=begin,forecast_source_available_seconds=begin-21600,
        conditioned_on_initial_known=True,actual_future_UIDs_used=False,Q50_GPUh=[1.]*24,Q90_GPUh=[2.]*24,
        cc4_sha=identity['cc4_sha'],runtime_sha=identity['runtime_sha'])
    cc4['forecast_receipt_sha']=digest(cc4)
    return state,source_bundle,contract,identity,cc4


def compile_fixture(packet=None,hard=None):
    state,bundle,contract,identity,cc4=packet or fixture_packet()
    rows,audit=classify_d0_backlog(state,source_identity=identity)
    return _compile_d0_known_data(state,rows,audit,bundle,contract,identity,cc4,hard or {},
        dict(path='NAMED_NUMERIC_FIXTURE',sha256='f'*64,bytes=0),'NAMED_NUMERIC_FIXTURE')


def test_d0_public_backlog_reclassification_and_expired_physical_hold():
    state,_,_,identity,_=fixture_packet();rows,audit=classify_d0_backlog(state,source_identity=identity)
    assert audit['D0_known_UIDs']==4 and audit['newly_D0_known_UIDs']==2
    assert audit['initial_running_GPU']==3 and audit['Q50_expired_running_GPU']==1
    assert all(r['D0_known'] and not r['actual_future_completion_read'] for r in rows)
    assert 'COMPLETED' not in {r['uid'] for r in rows}
    assert audit['A1_FULL_feasible']=='NOT_RUN' and audit['Native_calls']==0


def test_new_d0_plan_has_no_old_command_and_keeps_original_service_tail():
    data,rows,audit,receipts,windows=compile_fixture()
    assert set(data[4])=={'R','OVER','P','LONG'} and 'OVER' not in data[1]
    assert data[3].fixed_gpu=={('B',NATIVE_OFFSET):1}
    assert data[1]['R'].initial_sites==('A',) and data[1]['R'].elapsed_seconds==900
    assert data[1]['R'].reference_start==NATIVE_OFFSET
    assert windows['P']==tuple(range(24,120))
    assert data[2]['LONG'].latest_completion>=219
    assert data[1]['LONG'].service_slots==100
    assert data[0]['reference']['policy_id']=='D0_OBJECTIVE_REFERENCE_ONLY_NOT_FCFS_EXECUTION'
    assert set(r['job_uid'] for r in data[0]['known_population'])==set(data[4])
    assert receipts['P']['base_backlog_scheduling_window_seconds']==85500
    assert receipts['P']['source_QoS_budget_seconds_preserved']==0 and receipts['P']['additional_intentional_delay_budget_seconds']==0
    assert not audit['old_six_hour_prefix_required'] and audit['native_model_build']=='NOT_RUN'
    assert audit['a_input_sha']==input_fingerprint(data)


def test_actual_hard_deadline_is_not_extended_or_silently_dropped():
    state,bundle,contract,identity,cc4=fixture_packet()
    state['pending'][0]['metadata']['completion_deadline_seconds']=state['begin_epoch_seconds']-1
    data,rows,audit,_,_=compile_fixture((state,bundle,contract,identity,cc4))
    assert audit['status']=='NOT_CERTIFIED' and audit['no_legal_D0_start_window_UIDs']==['P']
    assert 'P' in data[4] and 'P' not in data[1]
    assert next(r for r in rows if r['uid']=='P')['no_source_legal_D0_start_window']
    assert not audit['source_hard_deadlines_extended']


def test_source_release_and_window_are_intersected_with_research_horizon():
    state,bundle,contract,identity,cc4=fixture_packet();begin=state['begin_epoch_seconds']
    meta=state['pending'][0]['metadata'];meta['release_seconds']=begin+1800;meta['hard_latest_start_seconds']=begin+3600
    _,_,audit,receipts,windows=compile_fixture((state,bundle,contract,identity,cc4))
    assert windows['P']==(26,27,28) and receipts['P']['allowed_starts_seconds']==[begin+1800,begin+2700,begin+3600]
    assert audit['status']=='PASS'


def test_future_submit_and_cross_initial_case_are_rejected():
    state,_,_,identity,_=fixture_packet();state['pending'][0]['submit_seconds']=state['begin_epoch_seconds']+1
    with pytest.raises(ValueError,match='PUBLIC_JOB_INPUT_INVALID'):classify_d0_backlog(state,source_identity=identity)
    state,_,_,identity,_=fixture_packet();identity['initial_state_sha']='f'*64
    with pytest.raises(ValueError,match='INITIAL_SEMANTIC_DRIFT'):classify_d0_backlog(state,source_identity=identity)


@pytest.mark.parametrize('field,value', [('automatic_hard_deadline_extension',True),('customer_SLA_claimed',True),
    ('source_protection_confirmed_by_research',True),('additional_intentional_delay_budget_seconds',3600)])
def test_backlog_contract_does_not_grant_customer_or_optional_delay_rights(field,value):
    state,_,contract,identity,_=fixture_packet();contract[field]=value
    contract['contract_sha']=digest({k:v for k,v in contract.items() if k!='contract_sha'})
    with pytest.raises(ValueError,match='EXPLICIT_BACKLOG_RESEARCH_CONTRACT'):
        validate_backlog_contract(contract,begin=state['begin_epoch_seconds'],end=state['begin_epoch_seconds']+86400,identity=identity)


def test_cc4_causality_and_nonfinite_available_time_are_fail_closed():
    state,bundle,contract,identity,cc4=fixture_packet();cc4['forecast_source_available_seconds']=state['begin_epoch_seconds']+1
    cc4['forecast_receipt_sha']=digest({k:v for k,v in cc4.items() if k!='forecast_receipt_sha'})
    with pytest.raises(ValueError,match='CAUSAL_STATE_CONDITIONED_CC4'):compile_fixture((state,bundle,contract,identity,cc4))


def test_resealed_changed_forecast_mass_or_source_cannot_enter_planning():
    state,bundle,contract,identity,cc4=fixture_packet();cc4['Q50_GPUh'][0]=1.5
    cc4['forecast_receipt_sha']=digest({k:v for k,v in cc4.items() if k!='forecast_receipt_sha'})
    with pytest.raises(ValueError,match='FROZEN_SOURCE_MASS_DRIFT'):compile_fixture((state,bundle,contract,identity,cc4))
    state,bundle,contract,identity,cc4=fixture_packet();cc4['runtime_sha']='f'*64
    cc4['forecast_receipt_sha']=digest({k:v for k,v in cc4.items() if k!='forecast_receipt_sha'})
    with pytest.raises(ValueError,match='RUNTIME_SOURCE_IDENTITY_DRIFT'):compile_fixture((state,bundle,contract,identity,cc4))


def test_protected_source_requires_original_starts_and_sites():
    state,bundle,contract,identity,cc4=fixture_packet();state['pending'][0]['metadata']['protected']=True
    data,rows,audit,_,_=compile_fixture((state,bundle,contract,identity,cc4))
    assert audit['status']=='NOT_CERTIFIED' and audit['no_legal_D0_start_window_UIDs']==['P']
    assert 'P' in data[4] and 'P' not in data[1]
    state,bundle,contract,identity,cc4=fixture_packet();cc4['actual_future_UIDs_used']=True
    cc4['forecast_receipt_sha']=digest({k:v for k,v in cc4.items() if k!='forecast_receipt_sha'})
    with pytest.raises(ValueError,match='CAUSAL_STATE_CONDITIONED_CC4'):compile_fixture((state,bundle,contract,identity,cc4))


def test_no_unadmitted_model_build_or_input_mutation():
    data,rows,audit,receipts,windows=compile_fixture()
    case=D0ACase(data,None,Path('NAMED_FIXTURE_NOT_WRITTEN'),'a'*64,'A1','B1',windows,receipts,d0_input_audit=audit)
    with pytest.raises(ValueError,match='SUPERVISOR_NATIVE0_BUILD_ADMISSION'):build_d0_native_model(case,build_admission={})
    data[3].capacities['A']=100
    with pytest.raises(ValueError,match='INPUT_SOURCE_OR_CASE_DRIFT'):build_d0_native_model(case,build_admission={})


def test_exact_approved_public_d0_population_native0():
    path=Path(r'D:\v42_common_am_qos_integration_20261013\docs\v42_common_am_qos_integration\V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json')
    if not path.exists():pytest.skip('Exact approved source unavailable, no fixture certification.')
    state=load_dday_state(path,arm='B1')
    identity=dict(science_sha='a'*64,case_sha='b'*64,initial_state_sha=state['common_initial_state_sha'],cc4_sha='d'*64,runtime_sha='e'*64)
    rows,audit=classify_d0_backlog(state,source_identity=identity)
    assert (audit['D0_known_UIDs'],audit['running_UIDs'],audit['pending_UIDs'],audit['initial_running_GPU'])==(1624,324,1300,472)
    assert (audit['newly_D0_known_UIDs'],audit['newly_D0_known_running_UIDs'],audit['newly_D0_known_pending_UIDs'])==(78,23,55)
    assert (audit['Q50_expired_running_UIDs'],audit['Q50_expired_running_GPU'])==(69,187)
    assert all(r['submit_seconds']<=state['begin_epoch_seconds'] for r in rows)


def test_original_headroom_numeric_fixture_distinguishes_target_and_achieved_reserve():
    import gurobipy as gp
    from v42_final.reserve import bind_headroom
    from v42_integration.a_seed import full_replay
    import numpy as np
    model=gp.Model('D0_NAMED_HEADROOM_FIXTURE_NATIVE0');model.Params.OutputFlag=0
    try:
        headroom=bind_headroom(model,{('A',24):2},{('A',24):1},{('A',24):1.5},{('A',24):.5},{'A':4},[24])
        model.update();point=np.zeros(model.NumVars)
        point[headroom['CC4_achieved']['A',24].index]=.5
        point[headroom['runtime_achieved']['A',24].index]=.5
        shortfall=next(variable for variable in model.getVars() if variable.VarName.startswith('CC4_shortfall['))
        point[shortfall.index]=1
        assert full_replay(model,point)['PASS']
        point[headroom['CC4_achieved']['A',24].index]=1.5
        assert not full_replay(model,point)['PASS']
        assert headroom['reserve_is_electrical_load'] is False
        assert model.SolCount==0
    finally:model.dispose()


def test_observed_current_hard_gpu_is_not_a_second_runtime_target_native0():
    import json
    import math
    from v42_final.reserve import risk_exposure
    source=Path(r'D:\v42_may_joint_repair_campaign_20261013\raw\2025-05-01\NATIVE_INPUT_TEMPLATE_B1.json')
    initial=Path(r'D:\v42_common_am_qos_integration_20261013\docs\v42_common_am_qos_integration\V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json')
    if not source.exists() or not initial.exists():pytest.skip('Exact original source unavailable.')
    original=json.loads(source.read_text(encoding='utf-8-sig'));state=load_dday_state(initial,arm='B1')
    expired=[row for row in state['running'] if row['q50']<=row['elapsed_compute_seconds']]
    rows=[dict(state='RUNNING',service_slots=0,GPU_gang=row['gpu'],planning_site=row['site'],
        risk_nominal_completion_issue_slot=24+math.ceil((row['q50']-row['elapsed_compute_seconds'])/900)) for row in expired]
    bundle=dict(original,known_population=rows)
    overlap=current_hard_runtime_overlap(bundle)
    assert len(expired)==69 and sum(row['GPU_gang'] for row in rows)==187
    assert sum(overlap.values())==pytest.approx(38.061039555524204)
    future_original={};future_with_current_hard_excluded={}
    for row in rows:
        args=(row['GPU_gang'],row['risk_nominal_completion_issue_slot'],row['planning_site'],bundle['runtime_survival_kernel'],range(24,120))
        old=risk_exposure(*args);adjusted=risk_exposure(*args,current_hard_slot=24)
        assert all(key[1]!=24 for key in adjusted)
        assert {k:v for k,v in old.items() if k[1]>24}==adjusted
