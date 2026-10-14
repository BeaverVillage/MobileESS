"""Supervisor contracts for the resumed current-event research.

Historical PR230 diagnostic contracts remain immutable. These gates admit a
saved Planning result only with its own source, CC4 and observed D-day state.
They never manufacture a replacement Known schedule or optimization result.
"""
from copy import deepcopy
from pathlib import Path
import math
import json

from .unified_contract import digest, file_sha, load_contracts

REPORT = Path(__file__).resolve().parents[1] / 'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP'
IDENTITY_FIELDS = ('source_sha', 'stage_case_sha', 'science_sha', 'initial_state_sha',
                   'time_axis_sha', 'cc4_sha', 'runtime_sha')
COMPARISON_FIELDS = ('planning_commands_sha', 'initial_state_sha', 'arrivals_sha',
                     'private_simulator_runtime_sha', 'control_authority_sha',
                     'source_sha', 'stage_case_sha', 'science_sha', 'time_axis_sha')


def load_followup_contracts():
    manifest=load_contracts(REPORT)
    interface=json.loads((REPORT/'UNIFIED_INTERFACE_CONTRACT.json').read_text(encoding='utf8'))
    if (interface.get('policy')!='CURRENT_EVENT_UNKNOWN_PENDING_KNOWN_CORRECTIVE' or
            interface.get('Unknown_future_Known_speculative_veto') is not False or
            interface.get('Known_execution_fairness')!='SAME_INITIAL_PLAN_INPUTS_AND_RIGHTS_OUTCOMES_MAY_DIFFER'):
        raise ValueError('FOLLOWUP_CURRENT_EVENT_INTERFACE_REQUIRED')
    return manifest


def require_sha(value, field):
    if (not isinstance(value, str) or len(value) != 64 or
            any(c not in '0123456789abcdef' for c in value)):
        raise ValueError('FOLLOWUP_COMPLETE_SHA_REQUIRED:' + field)
    return value


def same_case(planning, actual):
    for key in IDENTITY_FIELDS:
        require_sha(planning.get(key), key)
        require_sha(actual.get(key), key)
        if planning[key] != actual[key]:
            raise ValueError('FOLLOWUP_SAME_CASE_AUTHORITY_DRIFT:' + key)
    return {key: planning[key] for key in IDENTITY_FIELDS}


def validate_known_boundary(commands, observed_state, *, begin_seconds):
    """A past command requires observed execution/completion, never retiming."""
    if not math.isfinite(begin_seconds) or begin_seconds % 900:
        raise ValueError('FOLLOWUP_ORIGINAL_CONTROL_TIME_AXIS_REQUIRED')
    running, completed = {}, {}
    for field, target in (('running', running), ('historical_completed', completed)):
        for row in observed_state.get(field, []):
            uid = row['uid']
            if uid in running or uid in completed:
                raise ValueError('FOLLOWUP_DUPLICATE_BOUNDARY_UID')
            seen = row.get('observed_at_seconds')
            if seen is None or not math.isfinite(float(seen)) or seen > begin_seconds:
                raise ValueError('FOLLOWUP_OBSERVED_BOUNDARY_RECEIPT_REQUIRED')
            target[uid] = row
    missing, mismatched = [], []
    for uid, command in commands.items():
        start = float(command['start_seconds'])
        if not math.isfinite(start):
            raise ValueError('FOLLOWUP_FINITE_KNOWN_START_REQUIRED')
        if command.get('execution_rule', '').startswith('DETERMINISTIC_KNOWN'):
            raise ValueError('FOLLOWUP_DIAGNOSTIC_FCFS_IS_NOT_PLANNING_AUTHORITY')
        row = running.get(uid)
        if row is not None:
            if (start >= begin_seconds or row.get('site') != command['site'] or
                    row.get('start_seconds') != start):
                mismatched.append(uid)
            continue
        row = completed.get(uid)
        if row is not None:
            completion = row.get('observed_completion_seconds')
            if (completion is None or not math.isfinite(float(completion)) or
                    not start <= completion <= begin_seconds or row.get('site') != command['site'] or
                    row.get('start_seconds') != start):
                mismatched.append(uid)
            continue
        if start >= begin_seconds:
            continue
        missing.append(uid)
    return dict(status='PASS' if not missing and not mismatched else 'NOT_CERTIFIED',
                past_commands_without_observed_execution_UIDs=missing,
                observed_execution_command_mismatch_UIDs=mismatched,
                planning_commands_sha=digest(commands), commands_retimed=False,
                begin_seconds=begin_seconds)


def require_planning_actual_handoff(a_result, planning_identity, actual_identity,
                                   commands, observed_state, *, begin_seconds, planning_slot_zero_seconds):
    identity = same_case(planning_identity, actual_identity)
    if a_result.get('FULL_feasible') is not True:
        raise ValueError('SAME_CASE_A1_NOT_CERTIFIED')
    replay = a_result.get('FULL_point_replay', {})
    residual = a_result.get('FULL_max_residual')
    if (replay.get('PASS') is not True or residual is None or
            not math.isfinite(float(residual)) or not 0. <= residual <= 1e-5):
        raise ValueError('FOLLOWUP_ORIGINAL_FULL_POINT_REPLAY_REQUIRED')
    from .coordinator import _full_a
    _full_a(a_result)
    if a_result.get('case_sha') != identity['stage_case_sha']:
        raise ValueError('FOLLOWUP_A_RESULT_STAGE_CASE_DRIFT')
    if not math.isfinite(planning_slot_zero_seconds) or planning_slot_zero_seconds % 900:
        raise ValueError('FOLLOWUP_PLANNING_SLOT_ORIGIN_REQUIRED')
    from .known_commands import compile_known_commands
    selected = a_result.get('selected_jobs')
    if not isinstance(selected, dict):
        raise ValueError('FOLLOWUP_CERTIFIED_SELECTED_JOBS_REQUIRED')
    expected = compile_known_commands(selected, slot_zero_seconds=planning_slot_zero_seconds)
    if set(expected) != set(commands):
        raise ValueError('FOLLOWUP_PLANNING_COMMAND_UID_DRIFT')
    for uid, original in expected.items():
        if any(digest(commands[uid].get(key)) != digest(value) for key, value in original.items()):
            raise ValueError('FOLLOWUP_PLANNING_COMMAND_DERIVATION_DRIFT:' + uid)
    boundary = validate_known_boundary(commands, observed_state, begin_seconds=begin_seconds)
    if boundary['status'] != 'PASS':
        raise ValueError('FOLLOWUP_DDAY_PLANNING_BOUNDARY_NOT_CERTIFIED')
    return dict(status='PASS', identity=identity, boundary=boundary,
                original_commands=deepcopy(commands), planning_commands_sha=digest(commands),
                Known_command_authority='ORIGINAL_FULL_PLANNING',
                actual_command_ledger='ACTUAL_CORRECTIVE_COMMAND',
                Actual_global_MILP_calls=0)


def comparison_inputs(rows):
    """Equal plans/exogenous inputs/rights; corrected Known outcomes may differ."""
    if set(rows) not in ({'C0', 'C1'}, {'C0', 'C1', 'C2'}):
        raise ValueError('FOLLOWUP_C0_C1_OPTIONAL_C2_REQUIRED')
    first = rows['C0']
    for label, row in rows.items():
        for key in COMPARISON_FIELDS:
            require_sha(row.get(key), key)
            if row[key] != first.get(key):
                raise ValueError('FOLLOWUP_COMPARISON_INPUT_DRIFT:' + label + ':' + key)
    return dict(status='PASS', same_initial_planning_and_exogenous_inputs=True,
                same_corrective_authority=True, Actual_Known_execution_SHA_equality_required=False,
                actual_outcomes_are_comparison_results=True)


def require_initial_state_alignment(observed_state, arguments, actual_identity, *, evidence_scope):
    """Join the validated boundary to what the private simulator will execute."""
    begin=arguments['begin']
    expected_running={r['uid']:(r.get('site'),r.get('start_seconds'))
                      for r in observed_state.get('running',[])}
    running=arguments.get('running',())
    actual_running={request.uid:(site,start) for request,site,start in running}
    if len(actual_running)!=len(running) or actual_running!=expected_running:
        raise ValueError('FOLLOWUP_ACTUAL_DRIVER_INITIAL_RUNNING_DRIFT')
    for request,site,start in running:
        row=next(r for r in observed_state['running'] if r['uid']==request.uid)
        if row.get('gpu',request.gpu)!=request.gpu:
            raise ValueError('FOLLOWUP_ACTUAL_DRIVER_INITIAL_GPU_DRIFT')
        elapsed=getattr(request,'metadata',{}).get('elapsed_compute_seconds',begin-start)
        if row.get('elapsed_compute_seconds',elapsed)!=elapsed:
            raise ValueError('FOLLOWUP_ACTUAL_DRIVER_INITIAL_ELAPSED_DRIFT')
    expected_pending={r['uid'] for r in observed_state.get('pending',[])}
    requests=arguments.get('requests',())
    actual_pending={r.uid for r in requests if r.uid not in actual_running and
        (r.submit<begin or r.uid in expected_pending or
         getattr(r,'metadata',{}).get('dday_initialization_seconds')==begin)}
    if actual_pending!=expected_pending:
        raise ValueError('FOLLOWUP_ACTUAL_DRIVER_INITIAL_PENDING_DRIFT')
    completed={r['uid'] for r in observed_state.get('historical_completed',[])}
    if completed & (set(actual_running)|{r.uid for r in requests}):
        raise ValueError('FOLLOWUP_COMPLETED_BOUNDARY_UID_RESUBMITTED')
    record=observed_state.get('source_record')
    if record is None and evidence_scope.startswith('REAL'):
        raise ValueError('FOLLOWUP_REAL_BOUNDARY_SOURCE_RECEIPT_REQUIRED')
    if record is not None:
        path=Path(record['path'])
        if (file_sha(path)!=record.get('sha256') or path.stat().st_size!=record.get('bytes') or
                record['sha256']!=actual_identity['initial_state_sha']):
            raise ValueError('FOLLOWUP_BOUNDARY_SOURCE_BYTE_SHA_DRIFT')
        source=json.loads(path.read_text(encoding='utf8'))
        # A normalized observed-state receipt has a literal frozen row roster.
        # Source-specific normalization must be certified before this gate.
        for field in ('running','pending','historical_completed'):
            if digest(source.get(field,[]))!=digest(observed_state.get(field,[])):
                raise ValueError('FOLLOWUP_BOUNDARY_SOURCE_ROW_DRIFT:'+field)
    return dict(status='PASS',Running_UIDs=len(actual_running),Pending_UIDs=len(actual_pending),
                completed_UIDs_not_resubmitted=True,driver_state_matches_validated_boundary=True,
                source_receipt_verified=record is not None)


def full96_fresh_gate(actual, fresh, *, evidence_kind):
    """A fixture or another trace's historical AC certificate cannot pass May."""
    if evidence_kind != 'REAL_DATA':
        return dict(status='DIAGNOSTIC_ONLY', full96_performance_certified=False)
    for trace in (actual, fresh):
        try:
            require_sha(trace.get('trace_sha'), 'trace_sha')
        except ValueError:
            return dict(status='NOT_CERTIFIED', full96_performance_certified=False,
                        reason='CURRENT_TRACE_SHA_REQUIRED')
    ok = (actual.get('slots') == 96 and actual.get('Actual_global_MILP_calls') == 0 and
          fresh.get('status') == 'PASS' and fresh.get('slots') == 96 and
          fresh.get('installed_SVR') == 11 and fresh.get('trace_sha') == actual.get('trace_sha') and
          fresh.get('original_voltage_limits_preserved') is True and
          fresh.get('original_current_transformer_limits_preserved') is True)
    return dict(status='PASS' if ok else 'NOT_CERTIFIED', full96_performance_certified=ok)
