"""Date-bound public D0 handoff, preserving the original execution contracts.

No driver, private Environment field, solver or AC engine is entered here.
May01 delegates to the exact original helpers. Other days replace only the
May01 source/count/file-format constants with the approved date snapshot.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import math

import numpy as np

from .actual import _require_public_metadata
from .coordinator import _full_a
from .d0_actual_inputs import D0BacklogProvider, D0DriverProjection, SOURCE_FIELDS
from . import d0_actual_inputs as original_inputs
from . import d0_execution as original_execution
from .followup_contract import require_initial_state_alignment
from .known_commands import compile_known_commands
from .release_date_case import require_date_case, _require_context, load_state
from .unified_contract import digest


def _day(context):
    begin = context['manifest']['time_axis']['planning_issue_epoch_seconds']
    return datetime.fromtimestamp(begin, timezone(timedelta(hours=10))).date().isoformat()


def _state(context):
    _require_context(context)
    day = _day(context)
    state, _ = load_state(day, context['manifest']['initial_record'])
    if digest(state) != digest(context['state']):
        raise ValueError('DATE_ACTUAL_CONTEXT_PUBLIC_INITIAL_STATE_DRIFT')
    return state


def _initial_mess_sha(context):
    if 'initial_mess' in context:
        plan = context['initial_mess']
    else:
        from .production_case import initial_mess
        plan = initial_mess(context['data'][0])
    if plan.get('plan_sha') != digest({k:v for k,v in plan.items() if k != 'plan_sha'}):
        raise ValueError('DATE_ACTUAL_INITIAL_MESS_ANCHOR_SEAL_DRIFT')
    return plan['plan_sha']


def compile_date_commands(a_result, context):
    """Unchanged native24→D0 conversion and pinned RUNNING continuation."""
    if _day(context) == '2025-05-01':
        return original_execution.compile_d0_commands(a_result, context)
    state = _state(context)
    manifest = context['manifest']
    begin = state['begin_epoch_seconds']
    if (a_result.get('source_identity') != manifest['identity']
        or a_result.get('D0_input_sha') != context['input_audit']['a_input_sha']
        or a_result.get('D0_issue_seconds') != begin or a_result.get('stage') not in ('A1','A2')):
        raise ValueError('DATE_CURRENT_A_SOURCE_INPUT_BINDING_REQUIRED')
    expected_stage = digest(dict(parent=manifest['identity']['case_sha'], stage=a_result['stage'],
        input_MESS_anchor=a_result.get('input_MESS_anchor'), backlog_contract=context['backlog']['contract_sha']))
    if a_result.get('case_sha') != expected_stage:
        raise ValueError('DATE_CURRENT_A_STAGE_CASE_DRIFT')
    anchor = a_result.get('input_MESS_anchor')
    if not isinstance(anchor,str) or len(anchor) != 64:
        raise ValueError('DATE_CURRENT_A_FIXED_MESS_ANCHOR_REQUIRED')
    if a_result['stage'] == 'A1' and anchor != _initial_mess_sha(context):
        raise ValueError('DATE_CURRENT_A1_INITIAL_MESS_ANCHOR_DRIFT')
    if a_result.get('FULL_feasible') is not True:
        raise ValueError('DATE_EXACT_BOOLEAN_FULL_FEASIBLE_REQUIRED')
    _full_a(a_result)
    residual = a_result.get('FULL_max_residual', math.inf)
    if (a_result.get('FULL_point_replay',{}).get('PASS') is not True
        or type(residual) not in (int,float) or not math.isfinite(residual) or not 0 <= residual <= 1e-5):
        raise ValueError('DATE_CURRENT_ORIGINAL_FULL_POINT_REPLAY_REQUIRED')
    selected = a_result['selected_jobs']
    holds = a_result.get('initial_Q50_expired_physical_holds',{})
    if any('start_seconds' in option or 'site' in option or not all(k in option for k in
        ('start','initial_site','segments','checkpoint')) for option in selected.values()):
        raise ValueError('DATE_ORIGINAL_NATIVE_OPTION_REQUIRED_NOT_ABSOLUTE_COMMAND')
    rows = {r['uid']:r for r in context['classification']}
    initial_uids = {r['uid'] for field in ('running','pending') for r in state[field]}
    if set(rows) != initial_uids or set(selected)&set(holds) or set(selected)|set(holds) != initial_uids:
        raise ValueError('DATE_ALL_PUBLIC_KNOWN_SERVICE_OR_HOLD_REQUIRED')
    expected_hold = {uid for uid,r in rows.items() if r['Q50_expired_running']}
    if set(holds) != expected_hold:
        raise ValueError('DATE_EXPIRED_RUNNING_PHYSICAL_HOLD_ROSTER_DRIFT')
    for uid, hold in holds.items():
        row = rows[uid]
        if (hold.get('site') != row['fixed_running_site'] or hold.get('gpu') != row['gpu']
            or hold.get('elapsed_seconds') != row['elapsed_compute_seconds']
            or hold.get('physical_release_rule') != 'OBSERVED_COMPLETION_ONLY'):
            raise ValueError('DATE_EXPIRED_RUNNING_PHYSICAL_HOLD_DRIFT')
    commands = compile_known_commands(selected, slot_zero_seconds=begin-21600)
    for uid, command in commands.items():
        row = rows[uid]
        if command['start_seconds'] < begin or command['site'] not in row['compatible_sites']:
            raise ValueError('DATE_SOURCE_LEGAL_POST_ISSUE_COMMAND_REQUIRED')
        if row['D0_status'] == 'RUNNING':
            if command['start_seconds'] != begin or command['site'] != row['fixed_running_site']:
                raise ValueError('DATE_RUNNING_SITE_PINNED_CONTINUATION_REQUIRED')
            command.update(command_type='D0_RUNNING_CONTINUATION', episode_id=row['episode_id'],
                historical_episode_start_seconds=begin-row['elapsed_compute_seconds'],
                elapsed_compute_seconds=row['elapsed_compute_seconds'], physical_job_restarted=False)
        else:
            if command['start_seconds'] not in row['legal_D0_start_seconds']:
                raise ValueError('DATE_PENDING_ORIGINAL_HARD_RESEARCH_WINDOW_REQUIRED')
            command.update(command_type='D0_PENDING_NEW_OPTIMIZED_START', episode_id=row['episode_id'])
    return commands


def project_date_driver_arguments(arguments, *, state, provider, context, evidence_scope='REAL_DATA'):
    """Public typed metadata projection; Environment and future requests stay opaque."""
    if _day(context) == '2025-05-01':
        return original_inputs.project_d0_driver_arguments(arguments, state=state, provider=provider,
            evidence_scope=evidence_scope)
    bound = _state(context)
    if digest(state) != digest(bound):
        raise ValueError('DATE_ACTUAL_PASSED_INITIAL_STATE_DRIFT')
    if not isinstance(provider,D0BacklogProvider):
        raise ValueError('DATE_ORIGINAL_D0_BACKLOG_PROVIDER_REQUIRED')
    if (provider.identity != context['manifest']['identity'] or provider.contract != context['backlog']
        or digest(provider.known) != digest({r['uid']:r for key in ('running','pending') for r in state[key]})):
        raise ValueError('DATE_ACTUAL_PROVIDER_SOURCE_CASE_OR_PUBLIC_BACKLOG_DRIFT')
    begin = state['begin_epoch_seconds']
    if arguments['begin'] != begin or provider.begin != begin:
        raise ValueError('DATE_PRIVATE_DRIVER_PUBLIC_CLOCK_DRIFT')
    running = {r['uid']:r for r in state['running']}
    pending = {r['uid']:r for r in state['pending']}
    initial = {**running,**pending}
    completed = {r.get('uid',r.get('job_uid')) for r in state.get('historical_completed',[])}
    actual_running = {r.uid:(site,start) for r,site,start in arguments.get('running',[])}
    if (len(actual_running) != len(arguments.get('running',[]))
        or actual_running != {u:(r['site'],r['observed_start_seconds']) for u,r in running.items()}):
        raise ValueError('DATE_DRIVER_INITIAL_RUNNING_SITE_HISTORY_DRIFT')
    seen = set()
    reclassified = []
    def projected(request):
        if request.uid in seen or request.uid in completed:
            raise ValueError('DATE_DUPLICATE_OR_COMPLETED_DRIVER_UID')
        seen.add(request.uid)
        raw = initial.get(request.uid)
        if raw is None:
            if request.submit < begin:
                raise ValueError('DATE_UNACCOUNTED_PREISSUE_DRIVER_UID')
            if request.metadata.get('origin_unknown') is not True:
                raise ValueError('DATE_FUTURE_REQUEST_MUST_REMAIN_UNKNOWN')
            return request
        metadata = deepcopy(request.metadata)
        _require_public_metadata(metadata)
        if (request.submit != raw['submit_seconds'] or request.gpu != raw['gpu'] or request.q50 != raw['q50']
            or tuple(request.compatible) != tuple(raw['compatible_sites'])):
            raise ValueError('DATE_DRIVER_PUBLIC_REQUEST_CONTRACT_DRIFT')
        if (metadata.get('episode_id') != raw['episode_id']
            or metadata.get('elapsed_compute_seconds') != raw['elapsed_compute_seconds']):
            raise ValueError('DATE_DRIVER_EPISODE_OR_ELAPSED_DRIFT')
        for name in SOURCE_FIELDS:
            if metadata.get(name) != raw['metadata'].get(name):
                raise ValueError('DATE_DRIVER_SOURCE_METADATA_DRIFT:'+name)
        for name in ('reused_planning_qos_authority','reference_sha','reference_start_seconds','provider_sha'):
            metadata.pop(name,None)
        is_running = request.uid in running
        metadata.update(origin_unknown=False, D0_original_D1_origin_unknown=raw['origin_unknown'], cc4_eligible=False,
            D0_classification_authority=provider.contract['contract_sha'], common_initial_state_sha=state['common_initial_state_sha'],
            dday_initialization_seconds=begin, initial_observed_state='RUNNING' if is_running else 'PENDING',
            state='RUNNING' if is_running else 'PENDING', episode_id=raw['episode_id'],
            elapsed_compute_seconds=raw['elapsed_compute_seconds'], reference_sha=provider.reference_sha,
            reference_start_seconds=begin, provider_sha=provider.provider_sha,
            nominal_service_seconds=max(0.,raw['q50']-raw['elapsed_compute_seconds']) if is_running else raw['q50'],
            representation_starts_seconds=tuple(raw['metadata']['representation_starts_seconds']),
            D0_base_queue_window_is_additional_intentional_delay=False)
        if raw['origin_unknown']:
            reclassified.append(request.uid)
        _require_public_metadata(metadata)
        return replace(request,metadata=metadata)
    projected_running = [(projected(request),site,start) for request,site,start in arguments.get('running',[])]
    requests = [projected(request) for request in arguments['requests']]
    if {r.uid for r in requests if r.uid in initial} != set(pending) or not set(initial) <= seen:
        raise ValueError('DATE_DRIVER_INITIAL_PENDING_ROSTER_DRIFT')
    result = dict(arguments,running=projected_running,requests=requests,qos_window_provider=provider)
    if result.get('environment') is not arguments.get('environment'):
        raise ValueError('DATE_PRIVATE_ENVIRONMENT_REPLACED')
    return D0DriverProjection(result,dict(status='PASS',scope=evidence_scope,day=_day(context),
        projected_initial_known_UIDs=len(initial),initial_running_UIDs=len(running),initial_pending_UIDs=len(pending),
        initial_running_GPU=sum(r.gpu for r,_,_ in projected_running), reclassified_D1_Unknown_to_D0_Known=len(reclassified),
        source_metadata_and_hard_contracts_changed=False,source_submit_q50_GPU_site_elapsed_changed=False,
        old_D1_planning_receipt_reuse=False,initial_CC4_depletion_eligible_UIDs=0,
        private_Environment_preserved_by_identity=True,private_environment_fields_read=False,
        future_requests_preserved_until_submit=True,Actual_engine_calls=0,Native_calls=0,
        date_performance_certified=False))


def _observed_boundary(state):
    begin = state['begin_epoch_seconds']
    running = [dict(uid=r['uid'],episode_id=r['episode_id'],site=r['site'],start_seconds=r['observed_start_seconds'],
        gpu=r['gpu'],submit_seconds=r['submit_seconds'],q50_total_seconds=r['q50'],compatible_sites=deepcopy(r['compatible_sites']),
        elapsed_compute_seconds=r['elapsed_compute_seconds'],observed_at_seconds=begin,source_row_sha=digest(r)) for r in state['running']]
    pending = [dict(uid=r['uid'],episode_id=r['episode_id'],site=r['site'],gpu=r['gpu'],q50_total_seconds=r['q50'],
        compatible_sites=deepcopy(r['compatible_sites']),submit_seconds=r['submit_seconds'],observed_at_seconds=begin,
        source_row_sha=digest(r)) for r in state['pending']]
    completed = [dict(uid=r['job_uid'],site=r['original_native_site'],start_seconds=r['observed_start_seconds'],gpu=r['GPU_gang'],
        observed_completion_seconds=r['observed_completion_seconds'],observed_control_release_seconds=r['observed_control_release_seconds'],
        observed_at_seconds=begin,source_row_sha=digest(r)) for r in state['historical_completed']]
    return dict(running=running,pending=pending,historical_completed=completed)


def require_date_actual_handoff(a_result, context, arguments, *, identity):
    """Public handoff only; final M2/Fresh/dispatch gates remain independently required."""
    if _day(context) == '2025-05-01':
        return original_execution.require_d0_actual_handoff(a_result,context,arguments,identity=identity)
    state = _state(context)
    manifest = context['manifest']
    commands = compile_date_commands(a_result,context)
    expected = dict(source_sha=manifest['source_sha'],stage_case_sha=a_result['case_sha'],
        science_sha=manifest['identity']['science_sha'],initial_state_sha=state['common_initial_state_sha'],
        time_axis_sha=manifest['time_axis_sha'],cc4_sha=manifest['identity']['cc4_sha'],runtime_sha=manifest['identity']['runtime_sha'])
    if identity != expected:
        raise ValueError('DATE_PLANNING_ACTUAL_EXACT_IDENTITY_REQUIRED')
    begin = state['begin_epoch_seconds']
    if arguments['begin'] != begin or not begin < arguments['end'] <= begin+86400:
        raise ValueError('DATE_ACTUAL_EXACT_APPROVED_DAY_OR_PREFIX_REQUIRED')
    if digest(arguments.get('known_schedule')) != digest(commands):
        raise ValueError('DATE_ACTUAL_ORIGINAL_NEW_PLANNING_COMMAND_DRIFT')
    # Reuse the unchanged numeric join after independently validating the
    # date-specific byte/semantic source above. The original source-file tail
    # only reads plain May01 JSON; compressed date snapshots use this adapter.
    join = require_initial_state_alignment(_observed_boundary(state),arguments,identity,
        evidence_scope='SOURCE_BOUND_DATE_PUBLIC_JOIN_ONLY')
    join.update(source_receipt_verified=True,source_receipt=deepcopy(manifest['initial_record']),
        source_semantic_sha=state['common_initial_state_sha'],date_source_authority_verified=True)
    known_uids = set(context['data'][4])
    for request,_,_ in arguments['running']:
        if request.uid not in known_uids or request.metadata.get('origin_unknown') is not False:
            raise ValueError('DATE_ALL_OBSERVED_INITIAL_RUNNING_ARE_NEW_KNOWN')
    for request in arguments['requests']:
        if request.uid in known_uids and request.metadata.get('origin_unknown') is not False:
            raise ValueError('DATE_ALL_OBSERVED_BACKLOG_ARE_NEW_KNOWN')
    expected_gpu = {site:0. for site in a_result['resource_sites']}
    for hold in a_result['initial_Q50_expired_physical_holds'].values():
        expected_gpu[hold['site']] += hold['gpu']
    for uid, option in a_result['selected_jobs'].items():
        for site,left,right in option['segments']:
            if left <= 24 < right:
                expected_gpu[site] += context['data'][4][uid]['GPU_gang']
    if not np.allclose([a_result['known_site_GPU'][s][0] for s in expected_gpu],list(expected_gpu.values()),rtol=0,atol=1e-5):
        raise ValueError('DATE_PLANNED_FIRST_INTERVAL_KNOWN_GPU_COUPLING_DRIFT')
    return dict(status='PASS',identity=expected,planning_commands_sha=digest(commands),original_commands=deepcopy(commands),
        actual_initial_state_join=join,D0_known_population=len(known_uids),D0_new_planning=True,day=_day(context),
        historical_prefix_gate_used=False,historical_prefix_certification_transferred=False,
        Known_command_authority='ORIGINAL_FULL_D0_PLANNING',actual_command_ledger='ACTUAL_CORRECTIVE_COMMAND',
        Actual_global_MILP_calls=0,Actual_engine_calls=0,private_environment_fields_read=False,
        final_A2_M2_chain_and_current_Fresh96_admission='REQUIRED_AT_PRODUCTION_DISPATCH_NOT_GRANTED_BY_PUBLIC_HANDOFF')
