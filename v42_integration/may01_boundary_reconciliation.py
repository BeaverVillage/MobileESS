"""Read-only PR223 issue/D-day joins and source-verified continuation types.

The approved D-day model is reused through its original semantic validator.
An issue-RUNNING native start=0 denotes remaining-service continuation, not
the historical episode's start. Pending commands are never retimed here.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from .dday_initialization import load_dday_state,_episode
from .known_commands import compile_known_commands
from .policy import digest


CONTINUATION_SCHEMA='SOURCE_VERIFIED_ISSUE_RUNNING_CONTINUATION_V1'
APPROVED_COUNTS=dict(running=324,running_GPU=472,pending=1300,fixed=151,fixed_GPU=296,
    unresolved=173,unresolved_GPU=176,excluded=44)


def file_record(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),sha256=sha,bytes=path.stat().st_size)


def checked_json(record):
    actual=file_record(record['path'])
    if any(actual[k]!=record[k] for k in ('sha256','bytes')):
        raise ValueError('BOUNDARY_ORIGINAL_SOURCE_FILE_BYTES_DRIFT')
    return json.loads(Path(record['path']).read_text(encoding='utf-8-sig'))


def approved_initialization_audit(record,*,expected_semantic_sha,arm='B1',expected_counts=APPROVED_COUNTS):
    checked_json(record)
    state=load_dday_state(record['path'],arm=arm)
    if state['common_initial_state_sha']!=expected_semantic_sha:
        raise ValueError('APPROVED_DDAY_SEMANTIC_SHA_DRIFT')
    if expected_counts and any(state['counts'].get(k)!=v for k,v in expected_counts.items()):
        raise ValueError('APPROVED_324_1300_472_POPULATION_DRIFT')
    return state,dict(status='PASS',schema='APPROVED_DDAY_INITIALIZATION_REUSE_AUDIT_V1',
        initial_file_record=deepcopy(record),semantic_sha=state['common_initial_state_sha'],
        raw_file_sha=record['sha256'],semantic_and_file_SHA_have_distinct_meanings=True,
        reader='v42_integration.dday_initialization.load_dday_state',
        semantic_validation='digest(initial_state_payload_keys)',
        freeze_envelope_validation='digest(all fields except freeze_sha)',
        source_and_original_PR125_policy_bytes_verified=True,counts=deepcopy(state['counts']),
        PR129_reused_UIDs=state['PR129_reused_jobs'],PR125_fallback_UIDs=state['PR125_fallback_jobs'],
        PR125_fallback_GPU=state['PR125_fallback_GPU'],Arm_initial_state_SHA=deepcopy(state['Arm_initial_state_SHA']),
        model_assumption=state['MODEL_ASSUMPTION'],Kestrel_observed_site=state['KESTREL_OBSERVED_SITE'],
        Kestrel_observed_queue=state['KESTREL_OBSERVED_QUEUE'],site_mapping_changed=False,
        excluded44_reactivated=False,initial_queue_rule=state['queue_policy_id'],
        Apr30_queue_replay=state['Apr30_queue_replay'],Native_calls=0,Actual_calls=0,Fresh_AC_calls=0)


def _epoch(value):
    if isinstance(value,(float,int)):return float(value)
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('SOURCE_EXPLICIT_TIMEZONE_REQUIRED')
    return parsed.timestamp()


def _source_roster(native):
    rows={r['job_uid']:r for r in native['known_population']}
    if len(rows)!=len(native['known_population']):raise ValueError('BOUNDARY_ISSUE_KNOWN_UID_DUPLICATE')
    return rows


def _boundary_roster(state):
    rows={}
    for status,key in (('RUNNING','running'),('PENDING','pending'),('COMPLETED','historical_completed')):
        for raw in state.get(key,[]):
            uid=raw.get('uid',raw.get('job_uid'))
            if uid in rows:raise ValueError('BOUNDARY_UID_IN_MULTIPLE_STATES')
            rows[uid]=(status,raw)
    return rows


def _remaining(row):
    q50=float(row['V10_Q50_total_seconds']);elapsed=float(row.get('elapsed_seconds') or 0.)
    return max(0.,q50-elapsed) if row['state']=='RUNNING' else q50


def _command_derivation(a_result,native,commands,issue):
    if a_result.get('FULL_feasible') is not True:raise ValueError('ORIGINAL_A_FULL_AUTHORITY_REQUIRED')
    residual=a_result.get('FULL_max_residual',math.inf)
    if not math.isfinite(float(residual)) or residual<0 or residual>1e-5:
        raise ValueError('ORIGINAL_A_FULL_RESIDUAL_NOT_CERTIFIED')
    replay=a_result.get('FULL_point_replay',{})
    if (replay.get('PASS') is not True or not isinstance(replay.get('FULL_max_residual'),(int,float))
            or not math.isfinite(replay['FULL_max_residual']) or not 0<=replay['FULL_max_residual']<=1e-5
            or not all(type(replay.get(k)) is int and replay[k]>0 for k in ('rows','columns'))
            or not isinstance(replay.get('point_sha256'),str) or len(replay['point_sha256'])!=64
            or any(c not in '0123456789abcdef' for c in replay['point_sha256'])):
        raise ValueError('ORIGINAL_A_FULL_POINT_REPLAY_REQUIRED')
    known=_source_roster(native)
    expected=compile_known_commands(a_result['selected_jobs'],slot_zero_seconds=issue)
    if set(expected)!=set(commands):raise ValueError('BOUNDARY_PLANNING_COMMAND_UID_DRIFT')
    for uid,original in expected.items():
        if uid not in known:raise ValueError('BOUNDARY_SELECTED_UID_ABSENT_FROM_ISSUE')
        if any(digest(commands[uid].get(k))!=digest(v) for k,v in original.items()):
            raise ValueError('BOUNDARY_ORIGINAL_COMMAND_RETIMED_OR_CHANGED:'+uid)
    return known


def _continuation_row(uid,source,option,boundary,issue,begin):
    """Return a proof only for the same already-running physical episode."""
    status,raw=boundary
    if source['state']!='RUNNING' or status!='RUNNING' or option['start']!=0 or option.get('checkpoint',-1)>=0:
        return None
    submit=_epoch(source['submit_time']);source_issue=_epoch(source['issue_time'])
    elapsed=float(source.get('elapsed_seconds') or 0.);actual_elapsed=float(raw['elapsed_compute_seconds'])
    start=float(raw['observed_start_seconds']);gpu=source['GPU_gang'];q50=float(source['V10_Q50_total_seconds'])
    site=option['initial_site'];remaining=_remaining(source);slots=int(source['service_slots'])
    expected_episode=_episode(uid,submit)
    if (not source.get('known_at_issue') or source_issue!=issue or submit>issue or start>issue
            or not all(math.isfinite(v) and v>=0 for v in (elapsed,actual_elapsed,q50,remaining))
            or issue-elapsed!=start or actual_elapsed!=elapsed+(begin-issue)
            or raw['gpu']!=gpu or raw['q50']!=q50 or raw['site']!=site
            or raw.get('episode_id')!=expected_episode
            or source.get('current_site_if_running')!=site
            or source.get('nominal_remaining_seconds')!=remaining or slots!=math.ceil(remaining/900)
            or option['segments']!=[[site,0,slots]]):
        return None
    return dict(uid=uid,episode_id=expected_episode,status='PASS',command_type='ISSUE_RUNNING_CONTINUATION',
        native_start_slot=0,native_start_epoch_seconds=issue,historical_episode_start_seconds=start,
        current_site=site,gpu=gpu,q50_total_seconds=q50,issue_elapsed_seconds=elapsed,
        Dday_elapsed_seconds=actual_elapsed,observed_prefix_compute_seconds=begin-issue,
        observed_prefix_compute_GPUh=gpu*(begin-issue)/3600,
        issue_nominal_remaining_seconds=remaining,Dday_nominal_remaining_seconds=max(0.,q50-actual_elapsed),
        nominal_service_slots=slots,nominal_Q50_expiry_is_actual_completion=False,
        running_GPU_retained=True,physical_job_restarted=False,planning_command_retimed=False,
        issue_source_row_sha=digest(source),approved_boundary_row_sha=digest(raw),
        actual_future_completion_or_remaining_runtime_read=False)


def build_running_continuation_certificate(a_result_record,native_record,initial_record,*,
        issue_seconds,commands,expected_semantic_sha,evidence_scope='ORIGINAL_PR223_SOURCE'):
    a_result=checked_json(a_result_record);native=checked_json(native_record)
    state=load_dday_state(initial_record['path'],arm='B1');checked_json(initial_record)
    if not any(all(record.get(k)==native_record.get(k) for k in ('path','sha256','bytes'))
            for record in state.get('source_receipts',[])):
        raise ValueError('CONTINUATION_NATIVE_NOT_IN_APPROVED_INITIAL_SOURCE_RECEIPTS')
    if state['common_initial_state_sha']!=expected_semantic_sha:
        raise ValueError('CONTINUATION_APPROVED_INITIAL_SEMANTIC_DRIFT')
    issue=float(issue_seconds);begin=float(state['begin_epoch_seconds'])
    if not math.isfinite(issue) or issue%900 or not issue<=begin:raise ValueError('CONTINUATION_ISSUE_DDAY_AXIS_REQUIRED')
    if _epoch(native['issue_time'])!=issue:raise ValueError('CONTINUATION_NATIVE_SOURCE_ISSUE_AXIS_DRIFT')
    known=_command_derivation(a_result,native,commands,issue);boundary=_boundary_roster(state)
    rows=[]
    for uid,option in sorted(a_result['selected_jobs'].items()):
        if uid not in boundary:continue
        row=_continuation_row(uid,known[uid],option,boundary[uid],issue,begin)
        if row:rows.append(row)
    proof=dict(schema=CONTINUATION_SCHEMA,status='PASS',scope='ALREADY_RUNNING_CONTINUATION_UIDS_ONLY',
        stage_case_sha=a_result['case_sha'],stage=a_result.get('stage'),arm=a_result.get('arm'),
        planning_commands_sha=digest(commands),original_selected_jobs_sha=digest(a_result['selected_jobs']),
        initial_semantic_sha=expected_semantic_sha,initial_raw_file_sha=initial_record['sha256'],
        issue_seconds=issue,begin_seconds=begin,a_result_record=deepcopy(a_result_record),
        native_record=deepcopy(native_record),initial_record=deepcopy(initial_record),evidence_scope=evidence_scope,
        rows=rows,eligible_UIDs=[r['uid'] for r in rows],eligible_GPU=sum(r['gpu'] for r in rows),
        observed_continuation_prefix_GPUh=sum(r['observed_prefix_compute_GPUh'] for r in rows),
        Pending_execution_certified=False,full_issue_to_Dday_schedule_prefix_certified=False,
        original_commands_changed=False,initial_state_changed=False,Native_calls=0)
    proof['certificate_sha']=digest(proof)
    return proof


def validate_running_continuation_certificate(proof,*,commands,stage_case_sha,initial_semantic_sha,begin_seconds):
    if (proof.get('schema')!=CONTINUATION_SCHEMA
            or proof.get('certificate_sha')!=digest({k:v for k,v in proof.items() if k!='certificate_sha'})
            or proof.get('planning_commands_sha')!=digest(commands)
            or proof.get('stage_case_sha')!=stage_case_sha or proof.get('initial_semantic_sha')!=initial_semantic_sha
            or proof.get('begin_seconds')!=begin_seconds):
        raise ValueError('SOURCE_RUNNING_CONTINUATION_CERTIFICATE_BINDING_DRIFT')
    rebuilt=build_running_continuation_certificate(proof['a_result_record'],proof['native_record'],proof['initial_record'],
        issue_seconds=proof['issue_seconds'],commands=commands,expected_semantic_sha=initial_semantic_sha,
        evidence_scope=proof['evidence_scope'])
    if rebuilt!=proof:raise ValueError('SOURCE_RUNNING_CONTINUATION_REVALIDATION_DRIFT')
    return {r['uid']:deepcopy(r) for r in rebuilt['rows']}


def compare_known_boundary(native,a_result,state,*,issue_seconds,stage='A1',qos_receipts=None,
        reference_rebindings=None,original_actual_queue=None,original_actual_metadata=None,original_actual_decisions=None):
    """UID/episode taxonomy. Historical outcomes are audit-only extra fields."""
    known=_source_roster(native);boundary=_boundary_roster(state);selected=a_result['selected_jobs']
    issue=float(issue_seconds);begin=float(state['begin_epoch_seconds']);qos_receipts=qos_receipts or {}
    prefix_slots=(begin-issue)/900
    if not all(math.isfinite(v) for v in (issue,begin,prefix_slots)) or prefix_slots<0 or prefix_slots%1:
        raise ValueError('BOUNDARY_ISSUE_DDAY_LEGAL_SLOT_AXIS_REQUIRED')
    reference_rebindings=reference_rebindings or {};actual={r['job_uid']:r for r in (original_actual_queue or [])}
    actual_metadata=original_actual_metadata or {};actual_decisions=original_actual_decisions or {}
    rows=[]
    for uid,source in sorted(known.items()):
        status,initial=boundary.get(uid,('ABSENT',{}));option=selected.get(uid);receipt=qos_receipts.get(uid,{})
        submit=_epoch(source['submit_time']);gpu=source['GPU_gang'];remaining=_remaining(source)
        optimized_start=None if option is None else issue+option['start']*900
        optimized_site=None if option is None else option['initial_site'];observed_start=initial.get('observed_start_seconds')
        observed_site=initial.get('site',initial.get('original_native_site'))
        elapsed=initial.get('elapsed_compute_seconds')
        q50=float(source['V10_Q50_total_seconds']);nominal_prefix=0.;reservation_prefix=0.
        if option is not None:
            nominal_prefix=gpu*min(remaining,max(0.,begin-max(issue,optimized_start)))/3600
            reservation_prefix=gpu*sum(max(0.,min(prefix_slots,b)-max(0,a))/4 for site,a,b in option['segments'])
        observed_prefix=0.
        if status=='RUNNING':observed_prefix=gpu*max(0.,begin-max(issue,observed_start))/3600
        if status=='COMPLETED':observed_prefix=gpu*max(0.,min(begin,initial['observed_completion_seconds'])-max(issue,observed_start))/3600
        continuation=None if option is None or uid not in boundary else _continuation_row(uid,source,option,boundary[uid],issue,begin)
        categories=[]
        if option is None:
            categories.append('ZERO_NOMINAL_RUNNING_PHYSICAL_HOLD' if status=='RUNNING' else
                'ZERO_NOMINAL_PRIOR_COMPLETED' if status=='COMPLETED' else 'NO_NATIVE_DOMAIN_COMMAND')
        elif status=='RUNNING' and source['state']=='RUNNING':
            categories.append('VERIFIED_ISSUE_RUNNING_CONTINUATION' if continuation else 'ISSUE_RUNNING_CONTINUATION_INVALID')
        elif status=='RUNNING' and source['state']=='PENDING':
            categories.append('ISSUE_PENDING_SOURCE_STARTED_BEFORE_OPTIMIZED' if observed_start<optimized_start else
                'ISSUE_PENDING_SOURCE_STARTED_AFTER_OPTIMIZED' if observed_start>optimized_start else 'ISSUE_PENDING_SOURCE_START_MATCH')
            if observed_site!=optimized_site:categories.append('DISTINCT_APPROVED_DDAY_SITE_MODEL')
        elif status=='PENDING' and optimized_start<begin:
            categories.append('PENDING_PRE_DDAY_COMMAND_NOMINAL_FINISHED' if max(b for site,a,b in option['segments'])<=prefix_slots
                else 'PENDING_PRE_DDAY_COMMAND_NOMINAL_ACTIVE')
        elif status=='PENDING':categories.append('FUTURE_PENDING_COMMAND')
        elif status=='COMPLETED':categories.append('ISSUE_RUNNING_OBSERVED_PRIOR_COMPLETION' if source['state']=='RUNNING' else 'PENDING_OBSERVED_PRIOR_COMPLETION')
        else:categories.append('NATIVE_UID_NOT_PRESENT_IN_APPROVED_BOUNDARY')
        if status=='RUNNING' and elapsed>=q50:categories.append('Q50_EXPIRED_RUNNING_PHYSICAL_HOLD')
        episode=initial.get('episode_id',_episode(uid,submit) if status=='COMPLETED' else None)
        if episode is not None and episode!=_episode(uid,submit):categories.append('UID_EPISODE_MAPPING_ERROR')
        public_remaining=max(0.,q50-(elapsed or 0.)) if status=='RUNNING' else 0. if status=='COMPLETED' else q50
        event=None if option is None or continuation is not None or (status=='PENDING' and optimized_start>=begin) else max(
            issue,min(optimized_start,observed_start) if observed_start is not None else optimized_start)
        original=actual.get(uid,{})
        rows.append(dict(uid=uid,episode_id=episode,stage=stage,stage_case_sha=a_result['case_sha'],
            issue_status=source['state'],submit_seconds=submit,planning_issue_seconds=issue,
            reference_start_seconds=receipt.get('reference_start_seconds'),
            reference_site=reference_rebindings.get(uid,{}).get('rebound_reference_site',source.get('planning_site')),
            optimized_start_seconds=optimized_start,native_start_slot=None if option is None else option['start'],
            optimized_site=optimized_site,command_semantics='REMAINING_SERVICE_CONTINUATION_AT_ISSUE' if option is not None and source['state']=='RUNNING' else
                'PENDING_START_COMMAND' if option is not None else 'NO_NONZERO_NOMINAL_NATIVE_COMMAND',
            Dday_status=status,Dday_site=observed_site,Dday_observed_episode_start_seconds=observed_start,
            Issue_elapsed_seconds=source.get('elapsed_seconds'),Dday_elapsed_seconds=elapsed,
            Q50_total_seconds=q50,Issue_remaining_nominal_seconds=remaining,Dday_remaining_nominal_seconds=public_remaining,
            actual_remaining_runtime_seconds=None,actual_remaining_runtime_status='PRIVATE_FUTURE_NOT_READ',
            gpu=gpu,allowed_starts_seconds=receipt.get('allowed_starts_seconds',[]),
            original_QoS_status=receipt.get('status'),original_QoS_reasons=receipt.get('reasons',[]),
            original_QoS_budget_seconds=receipt.get('budget_seconds'),original_QoS_latest_start_seconds=receipt.get('latest_start_seconds'),
            original_QoS_receipt_sha=receipt.get('receipt_sha'),original_hard_contract=receipt.get('hard_contract'),
            prior_completion=status=='COMPLETED',prior_completion_seconds=initial.get('observed_completion_seconds'),
            planned_migration=False if option is None else option.get('checkpoint',-1)>=0,
            initial_site_authority=initial.get('initial_site_authority'),initial_state_semantic_sha=state['common_initial_state_sha'],
            source_issue_row_sha=digest(source),source_boundary_row_sha=None if not initial else digest(initial),
            source_episode_identity_verified=episode==_episode(uid,submit) if episode is not None else False,
            mismatch_types=categories,primary_classification=categories[0],continuation_certified=continuation is not None,
            first_possible_divergence_seconds=event,first_Dday_observed_comparison_seconds=begin,
            planned_prefix_nominal_compute_GPUh=nominal_prefix,planned_prefix_reserved_GPUh=reservation_prefix,
            observed_public_past_prefix_compute_GPUh=observed_prefix,
            observed_minus_planned_prefix_compute_GPUh=observed_prefix-nominal_prefix,
            original_saved_Actual_admitted_seconds=original.get('admitted_time'),original_saved_Actual_site=original.get('site'),
            original_saved_Actual_rule=actual_decisions.get(uid,{}).get('status','INITIAL_RUNNING_SOURCE_INJECTION' if status=='RUNNING' else None),
            original_saved_Actual_episode_id=actual_metadata.get(uid,{}).get('episode_id'),
            original_saved_Actual_plan_start_audit_seconds=original.get('plan_start_seconds'),
            original_saved_Actual_retro_outcomes_are_not_controller_inputs=True,
            planning_commands_retimed=False,approved_initial_state_changed=False,diagnostic_FCFS_replacement=False))
    groups={}
    for classification in sorted({r['primary_classification'] for r in rows}):
        group=[r for r in rows if r['primary_classification']==classification]
        groups[classification]=dict(UIDs=len(group),GPU=sum(r['gpu'] for r in group),
            issue_remaining_nominal_GPUh=sum(r['gpu']*r['Issue_remaining_nominal_seconds']/3600 for r in group),
            planned_prefix_nominal_compute_GPUh=sum(r['planned_prefix_nominal_compute_GPUh'] for r in group),
            planned_prefix_reserved_GPUh=sum(r['planned_prefix_reserved_GPUh'] for r in group),
            observed_past_prefix_compute_GPUh=sum(r['observed_public_past_prefix_compute_GPUh'] for r in group),
            first_possible_divergence_seconds=min((r['first_possible_divergence_seconds'] for r in group
                if r['first_possible_divergence_seconds'] is not None),default=None),
            first_observed_comparison_seconds=begin)
    counts=Counter(category for row in rows for category in row['mismatch_types'])
    return rows,dict(status='PASS',scope='UID_ROOT_CAUSE_CLASSIFICATION_ONLY_NOT_FULL_BOUNDARY_CERTIFICATION',
        native_Known_UIDs=len(known),optimized_commands=len(selected),issue_seconds=issue,begin_seconds=begin,
        stage=stage,stage_case_sha=a_result['case_sha'],primary_groups=groups,overlapping_type_counts=dict(counts),
        Running_with_native_commands=sum(r['Dday_status']=='RUNNING' and r['optimized_start_seconds'] is not None for r in rows),
        Pending_with_pre_Dday_native_commands=sum(r['Dday_status']=='PENDING' and r['optimized_start_seconds'] is not None
            and r['optimized_start_seconds']<begin for r in rows),
        all_UIDs_explained=all(r['primary_classification']!='NATIVE_UID_NOT_PRESENT_IN_APPROVED_BOUNDARY' for r in rows),
        optimized_schedule_full_prefix_replayed=False,initialization_redesigned=False,Native_calls=0)
