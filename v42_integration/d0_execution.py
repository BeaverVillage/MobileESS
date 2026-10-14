"""D0-only source handoff into the preserved CurrentEvent Actual controller."""
from copy import deepcopy
import math

import numpy as np

from .d0_case import require_case,SEMANTIC
from .unified_contract import digest
from .coordinator import _full_a
from .known_commands import compile_known_commands
from .followup_contract import build_approved_dday_observed_state,require_initial_state_alignment


def compile_d0_commands(a_result,context):
    """Native24 is D0 continuation/start; no old command is shifted or reused."""
    manifest=context['manifest'];require_case(manifest)
    audit=context['input_audit'];begin=manifest['time_axis']['planning_issue_epoch_seconds']
    if (a_result.get('source_identity')!=manifest['identity'] or a_result.get('D0_input_sha')!=audit['a_input_sha'] or
        a_result.get('D0_issue_seconds')!=begin or a_result.get('stage') not in ('A1','A2')):
        raise ValueError('D0_CURRENT_A_SOURCE_INPUT_BINDING_REQUIRED')
    expected_stage=digest(dict(parent=manifest['identity']['case_sha'],stage=a_result['stage'],
        input_MESS_anchor=a_result.get('input_MESS_anchor'),backlog_contract=context['backlog']['contract_sha']))
    if a_result.get('case_sha')!=expected_stage:
        raise ValueError('D0_CURRENT_A_STAGE_CASE_DRIFT')
    if a_result['stage']=='A1' and a_result.get('input_MESS_anchor')!=context['initial_mess']['plan_sha']:
        raise ValueError('D0_CURRENT_A1_INITIAL_MESS_ANCHOR_DRIFT')
    if a_result.get('FULL_feasible') is not True:
        raise ValueError('D0_EXACT_BOOLEAN_FULL_FEASIBLE_REQUIRED')
    _full_a(a_result)
    if (a_result.get('FULL_point_replay',{}).get('PASS') is not True or
        not math.isfinite(float(a_result.get('FULL_max_residual',math.inf))) or
        not 0<=a_result['FULL_max_residual']<=1e-5):
        raise ValueError('D0_CURRENT_ORIGINAL_FULL_POINT_REPLAY_REQUIRED')
    selected=a_result['selected_jobs'];holds=a_result.get('initial_Q50_expired_physical_holds',{})
    if any('start_seconds' in option or 'site' in option or not all(
            key in option for key in ('start','initial_site','segments','checkpoint'))
            for option in selected.values()):
        raise ValueError('D0_ORIGINAL_NATIVE_OPTION_REQUIRED_NOT_ABSOLUTE_COMMAND')
    rows={r['uid']:r for r in context['classification']}
    if set(selected)&set(holds) or set(selected)|set(holds)!=set(rows):
        raise ValueError('D0_ALL1624_KNOWN_SERVICE_OR_HOLD_REQUIRED')
    expected_hold={uid:r for uid,r in rows.items() if r['Q50_expired_running']}
    if set(holds)!=set(expected_hold):
        raise ValueError('D0_EXPIRED_RUNNING_PHYSICAL_HOLD_ROSTER_DRIFT')
    for uid,hold in holds.items():
        row=rows[uid]
        if (hold.get('site')!=row['fixed_running_site'] or hold.get('gpu')!=row['gpu'] or
            hold.get('elapsed_seconds')!=row['elapsed_compute_seconds'] or
            hold.get('physical_release_rule')!='OBSERVED_COMPLETION_ONLY'):
            raise ValueError('D0_EXPIRED_RUNNING_PHYSICAL_HOLD_DRIFT')
    commands=compile_known_commands(selected,slot_zero_seconds=begin-21600)
    for uid,command in commands.items():
        row=rows[uid];start=command['start_seconds']
        if start<begin or command['site'] not in row['compatible_sites']:
            raise ValueError('D0_SOURCE_LEGAL_POST_ISSUE_COMMAND_REQUIRED')
        if row['D0_status']=='RUNNING':
            if start!=begin or command['site']!=row['fixed_running_site']:
                raise ValueError('D0_RUNNING_SITE_PINNED_CONTINUATION_REQUIRED')
            command.update(command_type='D0_RUNNING_CONTINUATION',episode_id=row['episode_id'],
                historical_episode_start_seconds=begin-row['elapsed_compute_seconds'],
                elapsed_compute_seconds=row['elapsed_compute_seconds'],physical_job_restarted=False)
        else:
            if start not in row['legal_D0_start_seconds']:
                raise ValueError('D0_PENDING_ORIGINAL_HARD_RESEARCH_WINDOW_REQUIRED')
            command.update(command_type='D0_PENDING_NEW_OPTIMIZED_START',episode_id=row['episode_id'])
    return commands


def require_d0_actual_handoff(a_result,context,arguments,*,identity):
    manifest=context['manifest'];require_case(manifest)
    commands=compile_d0_commands(a_result,context)
    expected=dict(source_sha=manifest['source_sha'],stage_case_sha=a_result['case_sha'],
        science_sha=manifest['identity']['science_sha'],initial_state_sha=SEMANTIC,
        time_axis_sha=manifest['time_axis_sha'],cc4_sha=manifest['identity']['cc4_sha'],runtime_sha=manifest['identity']['runtime_sha'])
    if identity!=expected:
        raise ValueError('D0_PLANNING_ACTUAL_EXACT_IDENTITY_REQUIRED')
    begin=manifest['time_axis']['evaluation_begin_seconds']
    if arguments['begin']!=begin or not begin<arguments['end']<=begin+86400:
        raise ValueError('D0_ACTUAL_EXACT_APPROVED_DAY_OR_PREFIX_REQUIRED')
    if digest(arguments.get('known_schedule'))!=digest(commands):
        raise ValueError('D0_ACTUAL_ORIGINAL_NEW_PLANNING_COMMAND_DRIFT')
    state=build_approved_dday_observed_state(manifest['initial_record'],initial_state_sha=SEMANTIC,begin_seconds=begin)
    initial_join=require_initial_state_alignment(state,arguments,identity,evidence_scope='REAL_DATA')
    known_uids=set(context['data'][4])
    for request,_,_ in arguments['running']:
        if request.uid not in known_uids or request.metadata.get('origin_unknown') is not False:
            raise ValueError('D0_ALL_OBSERVED_INITIAL_RUNNING_ARE_NEW_KNOWN')
    for request in arguments['requests']:
        if request.uid in known_uids and request.metadata.get('origin_unknown') is not False:
            raise ValueError('D0_ALL_OBSERVED_BACKLOG_ARE_NEW_KNOWN')
    # The pre-event Running occupancy is 472; planned interval zero may also
    # contain legal Pending starts at D0. Reconstruct that interval separately.
    expected_gpu={site:0. for site in a_result['resource_sites']}
    raw=context['data'][4]
    for uid,hold in a_result['initial_Q50_expired_physical_holds'].items():
        expected_gpu[hold['site']]+=hold['gpu']
    for uid,option in a_result['selected_jobs'].items():
        for site,start,end in option['segments']:
            if start<=24<end:expected_gpu[site]+=raw[uid]['GPU_gang']
    if not np.allclose([a_result['known_site_GPU'][s][0] for s in expected_gpu],
                       list(expected_gpu.values()),rtol=0,atol=1e-5):
        raise ValueError('D0_PLANNED_FIRST_INTERVAL_KNOWN_GPU_COUPLING_DRIFT')
    return dict(status='PASS',identity=expected,planning_commands_sha=digest(commands),
        original_commands=deepcopy(commands),actual_initial_state_join=initial_join,
        D0_known_population=1624,D0_new_planning=True,historical_prefix_gate_used=False,
        historical_prefix_certification_transferred=False,Known_command_authority='ORIGINAL_FULL_D0_PLANNING',
        actual_command_ledger='ACTUAL_CORRECTIVE_COMMAND',Actual_global_MILP_calls=0)


def run_d0_current_actual(arguments,*,context,a_result,identity,frozen_policy,resource_bridge,expected_bindings):
    """All source gates run before the unchanged private driver is called."""
    from .aidc_sensitivity_runtime import run_current_event_actual
    handoff=require_d0_actual_handoff(a_result,context,arguments,identity=identity)
    if resource_bridge.identity!=identity or resource_bridge.source_sha!=digest(a_result):
        raise ValueError('D0_ACTUAL_CC4_RESOURCE_BRIDGE_SOURCE_DRIFT')
    if digest(frozen_policy.reference.commands)!=handoff['planning_commands_sha']:
        raise ValueError('D0_ACTUAL_FROZEN_POLICY_NEW_KNOWN_COMMAND_DRIFT')
    result=run_current_event_actual(arguments,frozen_policy=frozen_policy,resource_bridge=resource_bridge,
        expected_bindings=expected_bindings,handoff_gate=handoff)
    result['receipt'].update(D0_case_sha=context['manifest']['identity']['case_sha'],
        historical_prefix_gate_used=False,D0_state_conditioned_planning=True)
    return result
