"""Post-gate typed Actual input IO; no solver, power flow or event execution.

Only the private Environment receives retrospective service. D0 public state,
source request contracts and existing strict QoS/reference/power implementations
are preserved. No D-minus-1 Planning receipt is produced or imported.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import gzip
import inspect
import json
import math
from pathlib import Path

from .actual import JobRequest, _require_public_metadata
from .actual_validation import checked, load_stats, read, _power_model
from .coordinator import _full_a, _full_m, verify_sources
from .current_ac_admission import CausalObservations, epoch
from .d0_actual_inputs import D0BacklogProvider
from .m_engine import file_record, _write
from .policy import digest
from .qos import CausalReferenceScheduler, QoSWindowProvider
from .release_ac_contract import CONTRACT, actual_evaluation_case_payload
from .release_date_execution import _state, compile_date_commands, project_date_driver_arguments
from .release_p1_production import require_production_acceptance

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=Path('D:/v42_may_joint_repair_campaign_20261013')
STRICT_STATS=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/QOS_EMPIRICAL_STATS_STRICT.json')
STRICT_STATS_SHA='2a9bb692b0e538f38e8d0fab8cba9398bef2de91b568efb8311063204a8c067b'
GATE_SCHEMA='RELEASE_PRIVATE_ACTUAL_PREPARATION_GATE_V1'


def _require_gate(context, slots):
    """Recheck final real FULL parents before opening any Actual descriptor."""
    manifest=context['manifest'];identity=manifest['identity']
    gate=context.get('private_actual_preparation_gate',{})
    if (type(slots) is not int or slots not in (16,96)
            or gate.get('schema')!=GATE_SCHEMA or gate.get('status')!='PASS'
            or gate.get('source_identity')!=identity or gate.get('source_sha')!=manifest['source_sha']
            or gate.get('clock_contract')!=CONTRACT or gate.get('slots')!=slots
            or gate.get('preparation_gate_sha')!=digest({k:v for k,v in gate.items() if k!='preparation_gate_sha'})):
        raise ValueError('PRIVATE_ACTUAL_EXACT_POST_GATE_AUTHORITY_REQUIRED')
    ancestors=gate['ancestors'];a=ancestors['A2_result'];aa=ancestors['A2_acceptance']
    m=ancestors['M2_result'];ma=ancestors['M2_acceptance']
    require_production_acceptance(aa,stage='A2',identity=identity,result=a)
    require_production_acceptance(ma,stage='M2',identity=identity,result=m)
    _full_a(a);plan=_full_m(m)
    full_a=aa.get('Original_FULL',{});full_m=ma.get('Original_FULL',{})
    residual=full_a.get('FULL_max_residual',math.inf)
    physical=full_m.get('original_matrix_and_96_slot_physical_replay',{})
    if (aa.get('source_sha')!=manifest['source_sha'] or ma.get('source_sha')!=manifest['source_sha']
            or aa.get('stage_case_sha')!=a.get('case_sha') or ma.get('stage_case_sha')!=m.get('case_sha')
            or ma.get('parent_acceptance_sha')!=aa.get('acceptance_sha')
            or aa.get('AIDC_anchor')!=a.get('aidc_anchor') or ma.get('AIDC_anchor')!=a.get('aidc_anchor')
            or ma.get('MESS_anchor')!=plan['plan_sha'] or plan.get('case_sha')!=m.get('case_sha')
            or m.get('stage')!='M2' or m.get('D0_source_identity')!=identity
            or m.get('D0_fixed_AIDC_anchor')!=a.get('aidc_anchor')
            or m.get('binding',{}).get('aidc_anchor')!=a.get('aidc_anchor')
            or full_a.get('PASS') is not True or type(residual) not in (int,float)
            or not math.isfinite(residual) or not 0<=residual<=1e-5
            or full_a.get('point_sha256')!=a.get('FULL_point_replay',{}).get('point_sha256')
            or full_m.get('PASS') is not True or physical.get('PASS') is not True
            or physical.get('case_sha')!=m.get('case_sha')
            or full_m.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True):
        raise ValueError('PRIVATE_ACTUAL_ORIGINAL_FULL_FINAL_A2_M2_SOURCE_CHAIN_REQUIRED')
    compile_date_commands(a,context)
    begin=manifest['time_axis']['planning_issue_epoch_seconds']
    day=datetime.fromtimestamp(begin,timezone(timedelta(hours=10))).date().isoformat()
    source_case=dict(day=day,source_identity=identity,source_sha=manifest['source_sha'])
    payload=actual_evaluation_case_payload(source_case,ancestors,gate['actual_policy'],slots)
    if (gate.get('evaluation_case_payload')!=payload or gate.get('evaluation_case_sha')!=digest(payload)):
        raise ValueError('PRIVATE_ACTUAL_CANONICAL_EVALUATION_CASE_REQUIRED')
    return gate,day


def _public_source_join(state,plan,actual):
    begin=state['begin_epoch_seconds']
    if (plan['day']!=state['day'] or actual['day']!=state['day']
            or plan['capacities']!=state['capacities'] or actual['capacities']!=state['capacities']
            or epoch(plan['issue_time'])!=begin-21600 or plan['slot_seconds']!=900
            or actual['slot_seconds']!=900):
        raise ValueError('PRIVATE_ACTUAL_SAME_DATE_SOURCE_AXIS_CAPACITY_REQUIRED')
    population=plan['known_population']+actual['post_issue_arrivals']
    source={str(r['job_uid']):r for r in population}
    if len(source)!=len(population):
        raise ValueError('PRIVATE_ACTUAL_SOURCE_UID_DUPLICATE')
    original_known={r['job_uid'] for r in plan['known_population']}
    initial={r['uid']:r for name in ('running','pending') for r in state[name]}
    if len(initial)!=len(state['running'])+len(state['pending']) or not set(initial)<=set(source):
        raise ValueError('PRIVATE_ACTUAL_INITIAL_SOURCE_UID_UNAVAILABLE')
    if (state['provider_identifiers']['CC4_provider_sha']!=digest(plan['forecast_inputs']['current_CC4'])
            or state['provider_identifiers']['frozen_Q50_values_sha']!=digest({u:r['Q50_total_seconds'] for u,r in source.items()})):
        raise ValueError('PRIVATE_ACTUAL_ORIGINAL_CC4_FROZEN_Q50_PROVIDER_DRIFT')
    for uid,row in initial.items():
        raw=source[uid]
        if (row['submit_seconds']!=epoch(raw['submit_time']) or row['gpu']!=raw['GPU_gang']
                or row['q50']!=raw['Q50_total_seconds'] or tuple(row['compatible_sites'])!=tuple(raw['compatible_sites'])
                or row.get('source_member')!=raw['source_member'] or row.get('source_row')!=raw['source_row']
                or row['origin_unknown']!=(uid not in original_known)):
            raise ValueError('PRIVATE_ACTUAL_IMMUTABLE_PUBLIC_REQUEST_SOURCE_DRIFT:'+uid)
        _require_public_metadata(row['metadata'])
    return population,source,initial


def _load_private_truth(population,archive):
    # Literal original source-row extraction, exclusively after _require_gate.
    from v42_voltage_control.b0_new import _truth
    return _truth(population,archive)


def _driver_bank(state,plan,actual,truth):
    """IO conversion only; private event truth never enters JobRequest metadata."""
    from v42_capacity.actual import Environment
    population,source,initial=_public_source_join(state,plan,actual)
    if set(truth)!=set(source):
        raise ValueError('PRIVATE_ACTUAL_COMPLETE_SOURCE_TRUTH_JOIN_REQUIRED')
    begin=state['begin_epoch_seconds'];end=begin+86400
    running_uids={r['uid'] for r in state['running']}
    pending_uids={r['uid'] for r in state['pending']}
    original_known={r['job_uid'] for r in plan['known_population']}
    future=[];completed=[]
    for uid,native in source.items():
        submit=epoch(native['submit_time']);service=truth[uid]
        start=epoch(service['start_time']);completion=epoch(service['end_time'])
        seconds=service['realized_seconds']
        if (service.get('job_uid')!=uid or service.get('source_member')!=native['source_member']
                or service.get('source_row')!=native['source_row']
                or type(seconds) not in (int,float) or not math.isfinite(seconds)
                or seconds<0 or not math.isclose(completion-start,seconds,rel_tol=1e-12,abs_tol=1e-6)
                or not submit<=start<=completion):
            raise ValueError('PRIVATE_ACTUAL_SOURCE_REALIZATION_EVENT_ORDER_OR_JOIN_DRIFT:'+uid)
        if uid in initial:
            raw=initial[uid]
            if uid in running_uids:
                if (raw['observed_start_seconds']!=start or raw['elapsed_compute_seconds']!=begin-start
                        or not start<=begin<completion):
                    raise ValueError('PRIVATE_ACTUAL_RUNNING_SOURCE_HISTORY_DRIFT:'+uid)
            elif not submit<=begin<start:
                raise ValueError('PRIVATE_ACTUAL_PENDING_SOURCE_OBSERVED_STATE_DRIFT:'+uid)
        elif submit>=begin:
            future.append(uid)
        elif completion<=begin:
            completed.append(uid)
        else:
            raise ValueError('PRIVATE_ACTUAL_SOURCE_ACTIVE_INITIAL_UID_MISSING:'+uid)
    representation=tuple(begin+t*900 for t in range(98))
    durations={};completions={};requests=[];running=[]
    def make(uid):
        native=source[uid];raw=initial.get(uid);is_running=uid in running_uids
        if raw is not None:
            metadata=deepcopy(raw['metadata'])
            metadata.update(episode_id=raw['episode_id'],elapsed_compute_seconds=raw['elapsed_compute_seconds'],
                initial_site_authority=raw['initial_site_authority'],KESTREL_OBSERVED_SITE=False)
        else:
            metadata=dict(qos=native.get('qos','UNCONFIRMED'),protected=native.get('protected'),
                batch_eligible=native.get('batch_eligible'),partition=native.get('partition',''),
                requested_walltime_seconds=native.get('requested_walltime_seconds'),
                can_prestart_place=native.get('can_prestart_place',False),
                migration_capability=native.get('migration_capability'),
                request_version_authority=native.get('request_version_history','UNVERIFIED_SOURCE_PROXY'),
                representation_starts_seconds=representation)
            for name in ('release_seconds','hard_earliest_start_seconds','hard_latest_start_seconds','completion_deadline_seconds'):
                if name in native:
                    metadata[name]=deepcopy(native[name])
        metadata.update(state='RUNNING' if is_running else 'PENDING',origin_unknown=uid not in original_known,
            cc4_eligible=uid in future,common_initial_state_sha=state['common_initial_state_sha'],
            dday_initialization_seconds=begin,initial_observed_state=('RUNNING' if is_running else 'PENDING') if raw else None,
            source_request_provenance=native.get('request_version_history'),
            source_representation='EXPLICIT_DDAY_MIDNIGHT_96_SLOT_CONTROL_AXIS')
        _require_public_metadata(metadata)
        request=JobRequest(uid,epoch(native['submit_time']),native['GPU_gang'],tuple(native['compatible_sites']),
            native['Q50_total_seconds'],raw['site'] if is_running else native.get('source_site'),metadata)
        durations[uid]=truth[uid]['realized_seconds']
        if is_running:
            running.append((request,raw['site'],raw['observed_start_seconds']))
            completions[uid]=epoch(truth[uid]['end_time'])
        else:
            requests.append(request)
    for row in sorted(state['running'],key=lambda r:(r['submit_seconds'],r['uid'])):
        make(row['uid'])
    for row in sorted(state['pending'],key=lambda r:(r['submit_seconds'],r['uid'])):
        make(row['uid'])
    for uid in sorted(future,key=lambda u:(epoch(source[u]['submit_time']),u)):
        make(uid)
    return dict(requests=requests,running=running,environment=Environment(durations,completions)),dict(
        initial_running_UIDs=len(running_uids),initial_pending_UIDs=len(pending_uids),
        private_future_submission_count=len(future),historical_completed_excluded=len(completed),
        exact_private_source_join_count=len(truth),realized_service_destination='ORIGINAL_PR125_PRIVATE_ENVIRONMENT_ONLY',
        private_completion_or_duration_in_request_metadata=False,private_Environment_fields_read=False,
        preday_queue_replay_executed=False,Actual_calls=0,Native_calls=0,AC_calls=0)


def _decoded_initial_copy(context,output):
    record=context['manifest']['initial_record'];path=checked(record)
    encoded=path.read_bytes();decoded=gzip.decompress(encoded) if path.suffix=='.gz' else encoded
    if digest(json.loads(decoded.decode('utf-8-sig')))!=digest(context['state']):
        raise ValueError('PRIVATE_ACTUAL_LOSSLESS_INITIAL_DECODE_DRIFT')
    target=output/'INITIAL_STATE_LOSSLESS.json'
    target.write_bytes(decoded)
    return dict(source_record=deepcopy(record),decoded_record=file_record(target),
        decoded_semantic_sha=context['state']['common_initial_state_sha'],
        compressed_source_preserved=True,decoded_bytes_are_original_uncompressed_bytes=True)


def prepare_private_actual_inputs(context,*,output,slots=96):
    """Prepare typed inputs after exact real gates; never run Actual or Fresh."""
    gate,day=_require_gate(context,slots)
    state=_state(context)
    output=Path(output)
    if output.exists():
        raise FileExistsError('PRIVATE_ACTUAL_INPUT_OUTPUT_MUST_NOT_OVERWRITE')
    raw_folder=ARCHIVE/'raw'/day
    names=('PLANNING_INPUT_BUNDLE.json','ACTUAL_INPUT_BUNDLE.json','SOURCE_PROVENANCE.json','POWER_AUTHORITY.json')
    sources=[file_record(raw_folder/name) for name in names]
    verify_sources(context['manifest']['source_freeze'],sources)
    plan,actual,provenance,power=[read(raw_folder/name) for name in names]
    population,_,_=_public_source_join(state,plan,actual)
    stats_record=file_record(STRICT_STATS)
    if stats_record['sha256']!=STRICT_STATS_SHA:
        raise ValueError('PRIVATE_ACTUAL_ORIGINAL_STRICT_STATISTICS_BYTES_DRIFT')
    stats=load_stats(STRICT_STATS)
    identity=context['manifest']['identity'];begin=state['begin_epoch_seconds']
    strict=QoSWindowProvider(stats,case_sha=identity['case_sha'],provider_sha=identity['runtime_sha'])
    reference_sha=digest(dict(rule='DDAY_CAUSAL_GRID_BLIND_REFERENCE_V1',
        common_initial_state_sha=state['common_initial_state_sha'],capacities=state['capacities'],
        nominal_provider=state['provider_identifiers']))
    provider=D0BacklogProvider(strict,state=state,contract=context['backlog'],identity=identity,reference_sha=reference_sha)
    checked(provenance['archive'])
    truth,archive_receipt=_load_private_truth(population,provenance['archive'])
    bank,bank_receipt=_driver_bank(state,plan,actual,truth)
    del truth
    power_model,power_receipts=_power_model(power,plan['capacities'])
    observations=CausalObservations.load(raw_folder,begin=begin,end=begin+86400)
    weather=[observations.at(begin+t*900,observed_now=begin+t*900)['weather']['values'] for t in range(slots)]
    from v42_final.workload import ForecastBook
    forecast=ForecastBook(tuple(context['forecast']['Q50_GPUh']),tuple(context['forecast']['Q90_GPUh']),begin)
    arguments=dict(bank,capacities=state['capacities'],begin=begin,end=begin+slots*900,
        qos_window_provider=provider,forecast=forecast,power_model=power_model,weather=weather[:slots],
        reference=CausalReferenceScheduler(state['capacities'],reference_sha=reference_sha))
    projection=project_date_driver_arguments(arguments,state=state,provider=provider,context=context,evidence_scope='REAL_DATA')
    arguments=projection.arguments
    reference=arguments['reference']
    for request,site,start in arguments['running']:
        reference.observe_running(request,site=site,start_seconds=start,event_seconds=begin,
            elapsed_compute_seconds=begin-start)
    pending={r['uid'] for r in state['pending']}
    for request in arguments['requests']:
        if request.uid in pending:
            reference.submit(request,event_seconds=begin)
    if set(reference.assigned)!={r['uid'] for key in ('running','pending') for r in state[key]} or provider.receipts:
        raise ValueError('PRIVATE_ACTUAL_FUTURE_REFERENCE_OR_PREISSUED_QOS_LEAK')
    from v42_voltage_control.b0_new import _truth
    sources += [stats_record,archive_receipt,*power_receipts,*observations.sources,
        *[file_record(inspect.getsourcefile(f)) for f in (_truth,_power_model,project_date_driver_arguments)],
        file_record(ROOT/'v42_capacity/actual.py'),file_record(ROOT/'v42_integration/actual.py'),file_record(__file__)]
    sources=list({(r['path'],r['sha256'],r['bytes']):r for r in sources}.values())
    verify_sources(context['manifest']['source_freeze'],sources)
    output.mkdir(parents=True)
    decoded=_decoded_initial_copy(context,output)
    receipt=dict(status='PASS_PRIVATE_INPUT_PREPARATION_ONLY',day=day,slots=slots,
        source_identity=identity,source_sha=context['manifest']['source_sha'],
        evaluation_case_sha=gate['evaluation_case_sha'],preparation_gate_sha=gate['preparation_gate_sha'],
        private_bank=bank_receipt,projection=projection.receipt,source_records=sources,
        initial_state_decode=decoded,Original_private_truth_extractor_reused=True,
        Original_power_model_reused=True,Original_environment_reused=True,
        Original_strict_empirical_statistics_sha=stats.sha,old_D1_receipts_reused=False,
        QoS_receipts_preissued=0,future_UIDs_in_reference=0,weather='ORIGINAL_CAUSAL_ASOF_OBSERVATION_HOLD',
        physical_voltage_gate_certified=False,Actual_calls=0,Native_calls=0,AC_calls=0)
    _write(output/'PRIVATE_ACTUAL_INPUT_PREPARATION.json',receipt)
    from .research_presite_actual import ObservedSourceAuthority
    return dict(arguments=arguments,projection_receipt=receipt,sources=sources,raw_folder=raw_folder,
        power_receipts=power_receipts,observations=observations,
        source_authority_lookup=ObservedSourceAuthority(raw_folder/'ACTUAL_INPUT_BUNDLE.json'),
        raw_bundle_path=raw_folder/'ACTUAL_INPUT_BUNDLE.json')
