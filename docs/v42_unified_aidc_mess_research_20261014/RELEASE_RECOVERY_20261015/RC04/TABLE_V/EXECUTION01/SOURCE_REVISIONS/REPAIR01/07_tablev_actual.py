"""Table V Actual adapters. Original event service and settled AC remain intact.

Reference arms do not receive an electrical scheduling veto. All four arms use
the same observed-completion release ledger; private service stays in the
original Environment. This module never calls a mathematical optimizer.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from time import perf_counter
import json
import math
import numpy as np

from .actual import JobEventController, run_actual, _require_public_metadata
from .aidc_sensitivity_runtime import CurrentEventExecutionLedger
from .actual_validation import read, checked, load_stats, _power_model
from .coordinator import verify_sources
from .current_ac_admission import CausalObservations
from .m_engine import file_record, _write
from .policy import digest
from .qos import QoSWindowProvider
from .release_ac_contract import CONTRACT, validate_settled_fresh
from .release_private_actual_inputs import (ARCHIVE, STRICT_STATS, STRICT_STATS_SHA,
    _public_source_join, _load_private_truth, _driver_bank, _decoded_initial_copy)
from .table_v_flex_planning import compile_public_reference

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='TABLE_V_ACTUAL_EXECUTION_V1'


class TableVReferenceController(JobEventController):
    """B0/B2's literal original grid-blind FIFO plus common release accounting."""
    def __init__(self,*args,**kwargs):
        if kwargs.get('arm') not in ('B0','B2') or kwargs.get('frozen_policy') is not None:
            raise ValueError('TABLE_V_GRID_BLIND_REFERENCE_ARM_REQUIRED')
        super().__init__(*args,**kwargs)
        self.ledger=CurrentEventExecutionLedger(self.ledger.capacities)
        self.control_tick_times=[]

    def admit(self,now):
        began=perf_counter()
        result=super().admit(now)
        if now%900==0:
            self.control_tick_times.append(dict(time_seconds=now,wall_seconds=perf_counter()-began,
                scope='ENTIRE_ORIGINAL_GRID_BLIND_FIFO_TICK',starts=len(result)))
        return result

    def snapshot(self,now):
        result=super().snapshot(now)
        result['tablev_state']=dict(control_tick_timings=deepcopy(self.control_tick_times),
            scheduling='ORIGINAL_GRID_BLIND_REFERENCE_FIFO',sensitivity_reads=0,
            electrical_admission_veto_added=False,observed_completion_releases_GPU_immediately=True)
        return result


def project_public_initial(arguments,state,*,reference,provider,known_observed=None):
    """Exact source projection; the private Environment is passed by identity."""
    from .d0_actual_inputs import SOURCE_FIELDS
    running={r['uid']:r for r in state['running']};pending={r['uid']:r for r in state['pending']}
    initial={**running,**pending};seen=set();known_observed=known_observed or {}
    actual_running={r.uid:(s,t) for r,s,t in arguments['running']}
    if actual_running!={u:(r['site'],r['observed_start_seconds']) for u,r in running.items()}:
        raise ValueError('TABLE_V_APPROVED_RUNNING_SITE_START_ROSTER_REQUIRED')
    def project(request):
        if request.uid in seen:raise ValueError('TABLE_V_DUPLICATE_REQUEST')
        seen.add(request.uid);raw=initial.get(request.uid)
        if raw is None:
            if request.submit<arguments['begin'] or request.metadata.get('origin_unknown') is not True:
                raise ValueError('TABLE_V_FUTURE_REQUEST_MUST_STAY_UNKNOWN')
            return request
        if (request.submit!=raw['submit_seconds'] or request.gpu!=raw['gpu'] or request.q50!=raw['q50']
                or tuple(request.compatible)!=tuple(raw['compatible_sites'])):
            raise ValueError('TABLE_V_INITIAL_PUBLIC_REQUEST_DRIFT')
        metadata=deepcopy(request.metadata)
        for name in SOURCE_FIELDS:
            if metadata.get(name)!=raw['metadata'].get(name):raise ValueError('TABLE_V_SOURCE_CONTRACT_DRIFT:'+name)
        for name in ('reused_planning_qos_authority','reference_sha','reference_start_seconds','provider_sha'):
            metadata.pop(name,None)
        is_running=request.uid in running
        metadata.update(origin_unknown=False,D0_original_D1_origin_unknown=raw['origin_unknown'],cc4_eligible=False,
            common_initial_state_sha=state['common_initial_state_sha'],dday_initialization_seconds=arguments['begin'],
            initial_observed_state='RUNNING' if is_running else 'PENDING',state='RUNNING' if is_running else 'PENDING',
            episode_id=raw['episode_id'],elapsed_compute_seconds=raw['elapsed_compute_seconds'],
            reference_sha=reference.reference_sha,provider_sha=provider.provider_sha,
            reference_start_seconds=arguments['begin'] if is_running else reference.assigned[request.uid]['reference_start_seconds'],
            nominal_service_seconds=max(0.,raw['q50']-raw['elapsed_compute_seconds']) if is_running else raw['q50'])
        if request.uid in known_observed:
            observed=known_observed[request.uid]
            for name,value in observed.items():
                if name not in ('uid','event_seconds','is_observed'):
                    metadata[name]=deepcopy(value)
        _require_public_metadata(metadata)
        return replace(request,metadata=metadata)
    result=dict(arguments,running=[(project(r),s,t) for r,s,t in arguments['running']],
        requests=[project(r) for r in arguments['requests']],qos_window_provider=provider,reference=reference)
    if not set(initial)<=seen or {r.uid for r in result['requests'] if r.uid in initial}!=set(pending):
        raise ValueError('TABLE_V_INITIAL_KNOWN_POPULATION_MUST_BE_PRESERVED')
    if result['environment'] is not arguments['environment']:raise ValueError('TABLE_V_PRIVATE_ENVIRONMENT_REPLACED')
    return result


def _require_reference(context,result,acceptance):
    from .table_v_reference import require_reference_acceptance
    require_reference_acceptance(acceptance,identity=context['manifest']['identity'],result=result)
    scheduler,_=compile_public_reference(context['state'])
    if result.get('reference_sha')!=scheduler.reference_sha:
        raise ValueError('TABLE_V_PUBLIC_REFERENCE_CLOCK_OR_SOURCE_DRIFT')
    expected=result.get('public_reference_records')
    if expected is not None and digest(expected)!=digest(scheduler.assigned):
        raise ValueError('TABLE_V_PUBLIC_REFERENCE_RECORDS_DRIFT')
    return scheduler


def prepare_reference_inputs(context,*,reference_result,reference_acceptance,output,slots=96):
    """Only the approved Reference receipt can open retrospective service IO."""
    if 'tablev_flex' in context:
        from .table_v_flex_planning import require_flex_context
        require_flex_context(context)
    else:
        from .release_date_case import _require_context
        _require_context(context)
    if type(slots) is not int or slots not in (16,96):raise ValueError('TABLE_V_EXPLICIT_16_OR_96_SCOPE_REQUIRED')
    reference=_require_reference(context,reference_result,reference_acceptance)
    state=context['state'];day=state['day'];begin=state['begin_epoch_seconds']
    if day!='2025-05-01':raise ValueError('TABLE_V_MAY01_ONLY')
    output=Path(output)
    if output.exists():raise FileExistsError('TABLE_V_PRIVATE_PREPARATION_MUST_NOT_OVERWRITE')
    raw=ARCHIVE/'raw'/day
    names=('PLANNING_INPUT_BUNDLE.json','ACTUAL_INPUT_BUNDLE.json','SOURCE_PROVENANCE.json','POWER_AUTHORITY.json')
    sources=[file_record(raw/n) for n in names]
    verify_sources(context['manifest']['source_freeze'],sources)
    plan,actual,provenance,power=[read(raw/n) for n in names]
    population,_,_=_public_source_join(state,plan,actual)
    stats_record=file_record(STRICT_STATS)
    if stats_record['sha256']!=STRICT_STATS_SHA:raise ValueError('TABLE_V_ORIGINAL_STRICT_STATS_DRIFT')
    provider=QoSWindowProvider(load_stats(STRICT_STATS),case_sha=context['manifest']['identity']['case_sha'],
        provider_sha=state['provider_identifiers']['runtime_provider_sha'])
    checked(provenance['archive'])
    truth,archive_receipt=_load_private_truth(population,provenance['archive'])
    bank,bank_receipt=_driver_bank(state,plan,actual,truth);del truth
    model,power_receipts=_power_model(power,plan['capacities'])
    observations=CausalObservations.load(raw,begin=begin,end=begin+86400)
    from v42_final.workload import ForecastBook
    arguments=dict(bank,capacities=state['capacities'],begin=begin,end=begin+slots*900,
        qos_window_provider=provider,forecast=ForecastBook(tuple(context['forecast']['Q50_GPUh']),
            tuple(context['forecast']['Q90_GPUh']),begin),power_model=model,
        weather=[observations.at(begin+t*900,observed_now=begin+t*900)['weather']['values'] for t in range(slots)])
    arguments=project_public_initial(arguments,state,reference=reference,provider=provider)
    if len(arguments['running'])!=324 or sum(r.gpu for r,_,_ in arguments['running'])!=472:
        raise ValueError('TABLE_V_APPROVED_324_RUNNING_472_GPU_REQUIRED')
    if sum(r.metadata.get('origin_unknown') is False for r in arguments['requests'])!=1300:
        raise ValueError('TABLE_V_APPROVED_1300_PENDING_KNOWN_REQUIRED')
    sources += [stats_record,archive_receipt,*power_receipts,*observations.sources]
    sources += [file_record(ROOT/p) for p in ('v42_integration/tablev_actual.py','v42_integration/actual.py',
        'v42_integration/release_private_actual_inputs.py','v42_integration/table_v_reference.py',
        'v42_integration/table_v_flex_planning.py','v42_integration/qos.py','v42_capacity/actual.py')]
    sources=list({r['path']:r for r in sources}.values());verify_sources(context['manifest']['source_freeze'],sources)
    output.mkdir(parents=True);decoded=_decoded_initial_copy(context,output)
    receipt=dict(status='PASS_PRIVATE_INPUT_PREPARATION_ONLY',reference_acceptance=reference_acceptance,
        initial_source=context['manifest']['initial_record'],private_bank=bank_receipt,
        approved_initial_Known=1624,initial_GPU=472,initial_CC4_depletion=0,
        strict_original_QoS=True,Basic_85500_research_window_used=False,
        original_truth_extractor_and_Environment_reused=True,private_Controller_fields_read=0,
        source_records=sources,decoded_initial=decoded,Native_calls=0)
    _write(output/'TABLE_V_PRIVATE_INPUT_PREPARATION.json',receipt)
    return dict(arguments=arguments,sources=sources,raw_folder=raw,observations=observations,
        projection_receipt=receipt)


def _source_freeze(context,private,output):
    files=list({r['path']:r for r in context['manifest']['source_freeze']['files']+private['sources']}.values())
    # Keep each additive execution's literal source. Later Table V arm wiring
    # must not invalidate this completed Reference run's immutable receipt.
    snapshots=Path(output)/'EXECUTED_SOURCE';snapshots.mkdir()
    own=file_record(__file__);target=snapshots/Path(__file__).name
    target.write_bytes(Path(__file__).read_bytes());copy=file_record(target)
    if (own['sha256'],own['bytes'])!=(copy['sha256'],copy['bytes']):
        raise ValueError('TABLE_V_EXECUTED_SOURCE_LOSSLESS_SNAPSHOT_FAILED')
    files=[copy if r['path']==own['path'] else r for r in files]
    _write(snapshots/'SOURCE_SNAPSHOT.json',dict(executed_module=own,immutable_snapshot=copy,
        exact_executed_bytes=True,source_replacement_is_not_an_algorithm_change=True))
    freeze=dict(files=files,source_sha=digest(files),science_version='TABLE_V_ACTUAL_ORIGINAL_EVENT_V1')
    verify_sources(freeze);_write(Path(output)/'TABLE_V_ACTUAL_SOURCE_FREEZE.json',freeze)
    return freeze


def _require_mess(context,arm,m_result,m_acceptance):
    from .production_case import initial_mess
    if arm in ('B0','B1'):
        if m_result is not None or m_acceptance is not None:raise ValueError('TABLE_V_MESS_OFF_REJECTS_ON_PLAN')
        return initial_mess(context['data'][0])
    from .table_v_mess import require_m_acceptance
    require_m_acceptance(m_acceptance,arm=arm,stage='M1' if arm=='B2' else 'M2',
        identity=context['manifest']['identity'],result=m_result)
    return m_result['mess']


def run_tablev_actual(*,context,arm,reference_result,reference_acceptance,output,
        m_result=None,m_acceptance=None,a_result=None,a_acceptance=None,gate,slots=96):
    """Execute an admitted arm; model/optimizer calls are always forbidden."""
    if arm in ('B1','B3'):
        from .tablev_fullflex_actual import run_fullflex_actual
        return run_fullflex_actual(context=context,arm=arm,a_result=a_result,a_acceptance=a_acceptance,
            m_result=m_result,m_acceptance=m_acceptance,reference_result=reference_result,
            reference_acceptance=reference_acceptance,output=output,gate=gate,slots=slots)
    if arm not in ('B0','B2'):raise ValueError('TABLE_V_FULL_FLEX_FACTORY_NOT_YET_ADMITTED')
    if gate.get('Gate_contract')!=CONTRACT or gate.get('official_contract_authorized') is not True:
        raise ValueError('TABLE_V_ORIGINAL_SETTLED_AC_CONTRACT_REQUIRED')
    mess=_require_mess(context,arm,m_result,m_acceptance)
    output=Path(output)
    if output.exists():raise FileExistsError('TABLE_V_ACTUAL_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True)
    private=prepare_reference_inputs(context,reference_result=reference_result,
        reference_acceptance=reference_acceptance,output=output/'PRIVATE_INPUTS',slots=slots)
    freeze=_source_freeze(context,private,output);args=dict(private['arguments']);args.update(arm=arm)
    payload=dict(schema='TABLE_V_ACTUAL_EVALUATION_CASE_V1',arm=arm,
        source_identity=context['manifest']['identity'],source_sha=context['manifest']['source_sha'],
        initial_state_sha=context['state']['common_initial_state_sha'],reference_result_sha=digest(reference_result),
        reference_acceptance_sha=digest(reference_acceptance),MESS_plan_sha=mess['plan_sha'],slots=slots,
        policy='ORIGINAL_REFERENCE_FIFO_GRID_BLIND_NO_ADDED_FLEX',clock_contract=CONTRACT)
    from .isolated_unknown import no_native
    from .rc02_prefix_cache import memory_gate
    memory_gate();began=perf_counter()
    with no_native() as attempts:result=run_actual(**args,controller_class=TableVReferenceController)
    trace=output/'ACTUAL_OCCUPANCY_POWER_TRACE.npz'
    np.savez_compressed(trace,sites=result['sites'],timestamps_start_epoch_seconds=np.arange(args['begin'],args['end'],900),
        GPU=result['occupancy_GPU'],compute_GPU=result['compute_occupancy_GPU'],**result['physical'])
    for name,value in dict(PUBLIC_EPISODE_STATE=result['carryout']['controller'],QOS_LEDGER=result['qos_ledger'],
            QUEUE_LEDGER=result['queue_ledger'],JOB_EVENT_LEDGER=result['job_event_ledger']).items():
        _write(output/(name+'.json'),value)
    bad=[k for k in ('capacity_violations','dropped_jobs','future_duration_controller_reads',
        'future_completion_controller_reads','optimizer_calls','actual_global_reoptimization') if result['receipt'][k]!=0]
    verify_sources(freeze)
    receipt=dict(schema=SCHEMA,fixture=False,arm=arm,day='2025-05-01',status='FULL_PASS' if not bad else 'NOT_CERTIFIED',
        Actual_stage_PASS=not bad,Actual_stage_failures=bad,source_identity=context['manifest']['identity'],
        source_sha=context['manifest']['source_sha'],evaluation_case_payload=payload,evaluation_case_sha=digest(payload),
        initial_state_sha=context['state']['common_initial_state_sha'],MESS_plan_sha=mess['plan_sha'],
        executed_actual_slots=slots,actual_trace=file_record(trace),actual_source_freeze=file_record(output/'TABLE_V_ACTUAL_SOURCE_FREEZE.json'),
        Original_event_driver_reused=True,private_Environment_identity_preserved=True,Actual_global_MILP_calls=0,
        blocked_native_attempts=attempts,actual_wall_seconds=perf_counter()-began,receipt=result['receipt'],
        raw_folder=str(private['raw_folder']),Gate_contract=CONTRACT,
        control_tick_timings=result['carryout']['controller']['tablev_state']['control_tick_timings'],
        added_TimeShift_PreSite_Migration=False,Fresh_status='NOT_RUN')
    _write(output/'TABLE_V_ACTUAL_EXECUTION.json',receipt)
    return dict(status=receipt['status'],result=receipt,raw_records=[file_record(output/'TABLE_V_ACTUAL_EXECUTION.json'),file_record(trace)])


def run_tablev_fresh(*,context,actual_result,output,m_result=None,m_acceptance=None,slots=96):
    from .actual_validation import fresh_ac_minimum
    from .mess_actual import consume_frozen_mess
    actual=actual_result.get('result',actual_result)
    if (actual.get('schema')!=SCHEMA or actual.get('fixture') is not False or actual.get('Actual_stage_PASS') is not True
            or actual.get('source_identity')!=context['manifest']['identity'] or actual.get('executed_actual_slots')!=slots
            or actual.get('evaluation_case_sha')!=digest(actual['evaluation_case_payload'])):
        raise ValueError('TABLE_V_FRESH_EXACT_CURRENT_ACTUAL_REQUIRED')
    mess=_require_mess(context,actual['arm'],m_result,m_acceptance)
    if mess['plan_sha']!=actual['MESS_plan_sha']:raise ValueError('TABLE_V_FRESH_MESS_ANCHOR_DRIFT')
    for descriptor in (actual['actual_trace'],actual['actual_source_freeze']):checked(descriptor)
    freeze=read(actual['actual_source_freeze']['path']);verify_sources(freeze)
    output=Path(output)
    if output.exists():raise FileExistsError('TABLE_V_FRESH_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True)
    execution=consume_frozen_mess(mess,day_begin_seconds=context['state']['begin_epoch_seconds'],
        original_full_validated=actual['arm'] in ('B2','B3'))
    _write(output/'MESS_ACTUAL_EXECUTION_RECEIPT.json',execution)
    from .isolated_unknown import no_native
    from .rc02_prefix_cache import memory_gate
    memory_gate()
    with no_native() as attempts:
        result=fresh_ac_minimum(actual['raw_folder'],Path(actual['actual_trace']['path']).parent,output/'ORIGINAL_FRESH',
            source_freeze=freeze,campaign_manifest=ARCHIVE/'CAMPAIGN_MANIFEST.json',slots=slots,mess_plan=mess,
            mess_execution_receipt=execution,trace_path=actual['actual_trace']['path'],arm=actual['arm'],
            case_scope=dict(partial_actual_trace_authorized=slots==16,evaluation_case_sha=actual['evaluation_case_sha'],
                common_initial_state_sha=actual['initial_state_sha']))
    rows=read(output/'ORIGINAL_FRESH/FRESH_PHYSICAL_SLOTS.json')
    certificate=validate_settled_fresh(result,rows,day=actual['day'],case_sha=actual['evaluation_case_sha'],
        initial_state_sha=actual['initial_state_sha'],mess_plan_sha=mess['plan_sha'],trace_record=actual['actual_trace'],slots=slots)
    receipt=dict(status='FULL_PASS' if certificate['status']=='PASS' else 'PHYSICAL_FAIL',arm=actual['arm'],
        official_contract=CONTRACT,official_certificate=certificate,executed_slots=slots,
        actual_record=file_record(Path(actual['actual_trace']['path']).parent/'TABLE_V_ACTUAL_EXECUTION.json'),
        raw_receipt=file_record(output/'ORIGINAL_FRESH/FRESH_PHYSICAL_RESULT.json'),
        raw_slot_rows=file_record(output/'ORIGINAL_FRESH/FRESH_PHYSICAL_SLOTS.json'),Native_attempts=attempts)
    _write(output/'TABLE_V_SETTLED_FRESH.json',receipt)
    return dict(status=receipt['status'],result=receipt,raw_records=[file_record(output/'TABLE_V_SETTLED_FRESH.json')])
