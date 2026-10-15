from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import pytest

from v42_integration.actual import JobRequest
from v42_integration.d0_a_planning import BACKLOG_SCHEMA,digest
from v42_integration.d0_actual_inputs import (D0BacklogProvider,build_actual_source_authority,
    d0_actual_factory_gate,project_d0_driver_arguments,require_actual_source_authority)
from v42_integration.qos import ObservedJob,QoSWindowProvider,TrainingStatistics


class PrivateEnvironment:
    def __getattribute__(self,name):raise AssertionError('PRIVATE_ENVIRONMENT_MUST_NOT_BE_READ')


def fixture():
    begin=90000
    identity=dict(science_sha='a'*64,case_sha='b'*64,initial_state_sha='c'*64,cc4_sha='d'*64,runtime_sha='e'*64)
    metadata=dict(qos='normal',protected=None,batch_eligible=None,partition='',requested_walltime_seconds=None,
        can_prestart_place=False,migration_capability=None,request_version_authority='UNVERIFIED_SOURCE_PROXY',
        release_seconds=None,hard_earliest_start_seconds=None,hard_latest_start_seconds=None,completion_deadline_seconds=None,
        representation_starts_seconds=tuple(begin+t*900 for t in range(96)))
    def raw(uid,site=None):return dict(uid=uid,site=site,observed_start_seconds=begin-2700 if site else None,
        submit_seconds=begin-7200,gpu=1,q50=1800,elapsed_compute_seconds=2700 if site else 0,
        compatible_sites=['A','B'],episode_id=uid+'_EPISODE',origin_unknown=True,metadata=deepcopy(metadata))
    state=dict(begin_epoch_seconds=begin,common_initial_state_sha='c'*64,running=[raw('R','A')],
        pending=[raw('P')],historical_completed=[dict(job_uid='COMPLETED')])
    contract=dict(schema=BACKLOG_SCHEMA,policy_id='D0_EXPLICIT_BASE_QUEUE_STUDY',issue_seconds=begin,end_seconds=begin+86400,
        initial_state_sha='c'*64,initial_backlog_optimization_authorized=True,pending_source_compatible_placement_research_authorized=True,
        site_scope='SOURCE_COMPATIBLE_ONLY',automatic_hard_deadline_extension=False,source_protection_confirmed_by_research=False,
        customer_SLA_claimed=False,additional_intentional_delay_budget_seconds=0)
    contract['contract_sha']=digest(contract)
    strict=QoSWindowProvider(TrainingStatistics.from_records([],source_sha='f'*64),case_sha='1'*64,provider_sha='2'*64)
    provider=D0BacklogProvider(strict,state=state,contract=contract,identity=identity,reference_sha='3'*64)
    def request(row):return JobRequest(row['uid'],row['submit_seconds'],row['gpu'],tuple(row['compatible_sites']),
        row['q50'],row['site'],dict(row['metadata'],origin_unknown=True,episode_id=row['episode_id'],
            elapsed_compute_seconds=row['elapsed_compute_seconds'],reused_planning_qos_authority=dict(case_sha='1'*64)))
    running=request(state['running'][0]);pending=request(state['pending'][0])
    future=JobRequest('FUTURE',begin+900,1,('A','B'),1800,None,dict(metadata,origin_unknown=True,cc4_eligible=True))
    env=PrivateEnvironment()
    args=dict(begin=begin,end=begin+3600,capacities=dict(A=4,B=4),running=[(running,'A',begin-2700)],
        requests=[pending,future],environment=env,qos_window_provider=strict)
    return state,provider,args,strict


def observed(provider,state,uid='P'):
    raw=next(row for field in ('running','pending') for row in state[field] if row['uid']==uid)
    metadata=raw['metadata']
    return ObservedJob(uid,raw['submit_seconds'],state['begin_epoch_seconds'],state['begin_epoch_seconds'],raw['q50'],
        qos=metadata['qos'],protected=metadata['protected'],batch_eligible=metadata['batch_eligible'],partition=metadata['partition'],
        requested_walltime_seconds=metadata['requested_walltime_seconds'],gpu=raw['gpu'],origin_unknown=False,
        state='RUNNING' if raw['site'] else 'PENDING',release_seconds=metadata['release_seconds'],
        hard_earliest_start_seconds=metadata['hard_earliest_start_seconds'],hard_latest_start_seconds=metadata['hard_latest_start_seconds'],
        completion_deadline_seconds=metadata['completion_deadline_seconds'],representation_starts_seconds=metadata['representation_starts_seconds'],
        nominal_service_seconds=max(0,raw['q50']-raw['elapsed_compute_seconds']),provider_sha=provider.provider_sha,reference_sha=provider.reference_sha)


def test_projection_reclassifies_public_initial_jobs_without_reading_private_environment():
    state,provider,args,strict=fixture();old_future=args['requests'][1]
    projection=project_d0_driver_arguments(args,state=state,provider=provider)
    assert projection.arguments['environment'] is args['environment']
    assert projection.arguments['requests'][1] is old_future
    assert projection.arguments['running'][0][1:]==args['running'][0][1:]
    for request in [projection.arguments['running'][0][0],projection.arguments['requests'][0]]:
        assert request.metadata['origin_unknown'] is False and request.metadata['cc4_eligible'] is False
        assert request.metadata['D0_original_D1_origin_unknown'] is True
        assert request.metadata['protected'] is None and request.metadata['batch_eligible'] is None
        assert request.metadata['can_prestart_place'] is False
        assert 'reused_planning_qos_authority' not in request.metadata
    assert projection.arguments['running'][0][0].metadata['elapsed_compute_seconds']==2700
    assert args['requests'][0].metadata['origin_unknown'] is True
    assert projection.receipt['Actual_engine_calls']==0 and not projection.receipt['private_environment_fields_read']


def test_known_base_queue_window_has_no_source_SLA_or_optional_delay_claim():
    state,provider,args,strict=fixture();receipt=provider.issue(observed(provider,state))
    assert receipt.budget_seconds==85500 and len(receipt.allowed_starts_seconds)==96
    assert receipt.source_empirical_budget_seconds==0 and receipt.additional_intentional_delay_budget_seconds==0
    assert receipt.source_observed_metadata['protected'] is None
    assert not receipt.contract_is_observed_SLA and not receipt.research_base_window_is_source_QoS_extension
    assert provider.strict.receipts=={} and strict.receipts=={}
    assert provider.stats.source_empirical_stats_sha==strict.stats.sha


def test_running_expired_q50_receipt_preserves_current_episode():
    state,provider,args,_=fixture();receipt=provider.issue(observed(provider,state,'R'))
    assert receipt.allowed_starts_seconds==(state['begin_epoch_seconds'],) and receipt.budget_seconds==0
    projection=project_d0_driver_arguments(args,state=state,provider=provider)
    request,site,start=projection.arguments['running'][0]
    assert (site,start)==('A',state['begin_epoch_seconds']-2700)
    assert request.q50==1800 and request.metadata['elapsed_compute_seconds']==2700


def test_original_hard_deadline_never_gets_extended():
    state,provider,args,_=fixture()
    state['pending'][0]['metadata']['completion_deadline_seconds']=state['begin_epoch_seconds']+900
    provider.known['P']=deepcopy(state['pending'][0])
    receipt=provider.issue(observed(provider,state))
    assert receipt.allowed_starts_seconds==() and receipt.status=='EMPTY_SOURCE_HARD_WINDOW'
    assert receipt.hard_contract['completion_deadline_seconds']==state['begin_epoch_seconds']+900


def test_protected_job_does_not_receive_research_authority_automatically():
    state,provider,args,_=fixture();state['pending'][0]['metadata']['protected']=True
    provider.known['P']=deepcopy(state['pending'][0]);receipt=provider.issue(observed(provider,state))
    assert receipt.allowed_starts_seconds==() and receipt.hard_contract['protected'] is True


def test_future_observed_unknown_delegates_to_original_stats_without_copying_D1_receipts():
    state,provider,args,strict=fixture();begin=state['begin_epoch_seconds']
    job=ObservedJob('FUTURE',begin+900,begin+900,begin+900,1800,protected=None,batch_eligible=None,
        requested_walltime_seconds=None,origin_unknown=True,representation_starts_seconds=(begin+900,),
        provider_sha=provider.provider_sha,reference_sha=provider.reference_sha)
    receipt=provider.issue(job)
    assert receipt.source_empirical_budget_seconds==0 and receipt.base_backlog_scheduling_window_seconds==0
    assert receipt.allowed_starts_seconds==(begin+900,) and provider.strict.stats is strict.stats
    assert strict.receipts=={} and set(provider.strict.receipts)=={'FUTURE'}


def test_changed_original_metadata_or_request_identity_is_rejected():
    state,provider,args,_=fixture();args['requests'][0]=replace(args['requests'][0],metadata=dict(args['requests'][0].metadata,protected=False))
    with pytest.raises(ValueError,match='SOURCE_METADATA_DRIFT'):project_d0_driver_arguments(args,state=state,provider=provider)
    state,provider,args,_=fixture();job=replace(observed(provider,state),gpu=2)
    with pytest.raises(ValueError,match='PUBLIC_SOURCE_AUTHORITY_DRIFT'):provider.issue(job)


def test_completed_initial_drop_and_running_elapsed_change_fail_closed():
    state,provider,args,_=fixture();args['requests']=args['requests'][1:]
    with pytest.raises(ValueError,match='PENDING_ROSTER_DRIFT'):project_d0_driver_arguments(args,state=state,provider=provider)
    state,provider,args,_=fixture();request,site,start=args['running'][0]
    args['running']=[(request,site,start+900)]
    with pytest.raises(ValueError,match='RUNNING_SITE_HISTORY_DRIFT'):project_d0_driver_arguments(args,state=state,provider=provider)


def test_final_factory_stops_before_private_projection_without_current_primal_or_A2_M2():
    assert d0_actual_factory_gate(context={},a_result={'FULL_feasible':False})==dict(status='NOT_RUN',
        reason='CURRENT_D0_A_HAS_NO_ORIGINAL_FULL_PRIMAL',private_Actual_bank_read=False)
    result=d0_actual_factory_gate(context={},a_result={'FULL_feasible':True,'stage':'A1'})
    assert result['status']=='NOT_RUN' and result['reason']=='CURRENT_D0_FINAL_A2_M2_NOT_AVAILABLE'


def test_immutable_receipt_rejects_changed_authority():
    state,provider,args,_=fixture();job=observed(provider,state);provider.issue(job)
    with pytest.raises(ValueError,match='IMMUTABLE_OBSERVED_RECEIPT_DRIFT'):provider.issue(replace(job,t50_seconds=1900))


def test_projection_does_not_silently_repair_episode_elapsed_or_future_role():
    state,provider,args,_=fixture();request,site,start=args['running'][0]
    args['running']=[(replace(request,metadata=dict(request.metadata,elapsed_compute_seconds=0)),site,start)]
    with pytest.raises(ValueError,match='EPISODE_OR_ELAPSED_DRIFT'):project_d0_driver_arguments(args,state=state,provider=provider)
    state,provider,args,_=fixture();request=args['requests'][1]
    args['requests'][1]=replace(request,metadata=dict(request.metadata,origin_unknown=False))
    with pytest.raises(ValueError,match='FUTURE_REQUEST_MUST_REMAIN_UNKNOWN'):project_d0_driver_arguments(args,state=state,provider=provider)


def test_actual_source_authority_is_separate_from_planning_and_final_handoff(tmp_path):
    from v42_integration.d0_case import compile_contracts,INITIAL,SOURCE
    if not INITIAL.exists() or not SOURCE.exists():pytest.skip('Original source-bound D0 inputs unavailable.')
    # Build a fresh Native0 source receipt; do not validate a half-updated
    # application report while the Supervisor assembles a new source revision.
    manifest,*_=compile_contracts(output=tmp_path/'FRESH_NATIVE0_SOURCE')
    authority=build_actual_source_authority(manifest,output=tmp_path/'ACTUAL_SOURCE.json')
    verified=require_actual_source_authority(authority,manifest)
    assert verified['status']=='PASS' and not verified['final_A2_M2_admitted']
    assert authority['planning_identity']==manifest['identity'] and not authority['planning_math_source_modified']
    changed=deepcopy(authority);changed['planning_identity']['case_sha']='f'*64
    changed['authority_sha']=digest({k:v for k,v in changed.items() if k!='authority_sha'})
    with pytest.raises(ValueError,match='PLANNING_SOURCE_BINDING_DRIFT'):require_actual_source_authority(changed,manifest)
    changed=deepcopy(authority);changed['material_actual_code'][0]['sha256']='f'*64
    changed['authority_sha']=digest({k:v for k,v in changed.items() if k!='authority_sha'})
    with pytest.raises(ValueError,match='MATERIAL_CODE_BYTES_DRIFT'):require_actual_source_authority(changed,manifest)
