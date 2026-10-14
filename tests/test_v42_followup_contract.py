from copy import deepcopy
import pytest
from v42_integration.followup_contract import (
    IDENTITY_FIELDS, COMPARISON_FIELDS, same_case, validate_known_boundary,
    require_planning_actual_handoff, comparison_inputs, full96_fresh_gate)
from v42_integration.followup_contract import require_initial_state_alignment
from types import SimpleNamespace


def identity():
    return {k: ('abcdef0123456789' * 4) for k in IDENTITY_FIELDS}


def planning_result(commands):
    from v42_integration.a_engine import digest
    core = dict(selected_jobs=commands, AIDC_P_by_site={}, AIDC_Q_by_site={},
                CC4_service={}, CC4_carryout={}, anonymous_resource_envelope=[])
    return dict(core, aidc_anchor=digest(core), FULL_feasible=True, FULL_max_residual=0.,
                FULL_point_replay=dict(PASS=True), case_sha=identity()['stage_case_sha'])


@pytest.mark.parametrize('key', IDENTITY_FIELDS)
def test_every_case_authority_is_required_and_exact(key):
    a = identity(); b = dict(a, **{key: '0' * 64})
    with pytest.raises(ValueError, match='SAME_CASE_AUTHORITY_DRIFT'):
        same_case(a, b)
    b.pop(key)
    with pytest.raises(ValueError, match='COMPLETE_SHA_REQUIRED'):
        same_case(a, b)


def test_past_pending_command_cannot_be_retimed_or_certified():
    c = {'k': dict(site='A', start_seconds=-900.)}
    result = validate_known_boundary(c, {'pending': [{'uid': 'k'}]}, begin_seconds=0.)
    assert result['status'] == 'NOT_CERTIFIED' and c['k']['start_seconds'] == -900.
    assert not result['commands_retimed']
    with pytest.raises(ValueError, match='BOUNDARY_NOT_CERTIFIED'):
        require_planning_actual_handoff(planning_result(c),
            identity(), identity(), c, {}, begin_seconds=0., planning_slot_zero_seconds=0.)


def test_observed_running_must_match_original_site_and_start():
    c = {'k': dict(site='A', start_seconds=-900.)}
    good = dict(running=[dict(uid='k', site='A', start_seconds=-900., observed_at_seconds=0.)])
    assert validate_known_boundary(c, good, begin_seconds=0.)['status'] == 'PASS'
    bad = deepcopy(good); bad['running'][0]['site'] = 'B'
    assert validate_known_boundary(c, bad, begin_seconds=0.)['status'] == 'NOT_CERTIFIED'


def test_completed_boundary_receipt_cannot_use_future_completion():
    c = {'k': dict(site='A', start_seconds=-900.)}
    future = dict(historical_completed=[dict(uid='k', observed_completion_seconds=1., observed_at_seconds=0.)])
    assert validate_known_boundary(c, future, begin_seconds=0.)['status'] == 'NOT_CERTIFIED'


def test_diagnostic_fcfs_and_uncertified_a1_fail_closed():
    c = {'k': dict(site='A', start_seconds=0., execution_rule='DETERMINISTIC_KNOWN_FCFS')}
    with pytest.raises(ValueError, match='FCFS_IS_NOT_PLANNING'):
        validate_known_boundary(c, {}, begin_seconds=0.)
    with pytest.raises(ValueError, match='SAME_CASE_A1_NOT_CERTIFIED'):
        require_planning_actual_handoff({}, identity(), identity(), {}, {}, begin_seconds=0., planning_slot_zero_seconds=0.)


def test_unrelated_future_commands_cannot_inherit_certified_a1():
    a = planning_result({'k': dict(site='A', start_seconds=900.)})
    c = {'k': dict(site='B', start_seconds=900.)}
    with pytest.raises(ValueError, match='COMMAND_DERIVATION_DRIFT'):
        require_planning_actual_handoff(a, identity(), identity(), c, {},
            begin_seconds=0., planning_slot_zero_seconds=0.)


def test_full_flag_cannot_replace_original_raw_replay_or_anchor():
    a = planning_result({}); a['FULL_max_residual'] = float('nan')
    with pytest.raises(ValueError, match='FULL_POINT_REPLAY_REQUIRED'):
        require_planning_actual_handoff(a, identity(), identity(), {}, {},
            begin_seconds=0., planning_slot_zero_seconds=0.)
    a = planning_result({}); a['aidc_anchor'] = '0'*64
    with pytest.raises(ValueError, match='FIXED_ANCHOR_DRIFT'):
        require_planning_actual_handoff(a, identity(), identity(), {}, {},
            begin_seconds=0., planning_slot_zero_seconds=0.)


def test_boundary_cannot_use_future_observation_or_premature_running():
    c = {'k': dict(site='A', start_seconds=900.)}
    r = dict(running=[dict(uid='k', site='A', start_seconds=900., observed_at_seconds=0.)])
    assert validate_known_boundary(c, r, begin_seconds=0.)['status'] == 'NOT_CERTIFIED'
    r['running'][0]['observed_at_seconds'] = 1.
    with pytest.raises(ValueError, match='OBSERVED_BOUNDARY_RECEIPT_REQUIRED'):
        validate_known_boundary(c, r, begin_seconds=0.)


def test_fair_comparison_allows_different_corrective_known_outcomes():
    inputs = {k: 'a' * 64 for k in COMPARISON_FIELDS}
    rows = dict(C0=dict(inputs, Actual_Known_SHA='b'*64), C1=dict(inputs, Actual_Known_SHA='c'*64))
    assert comparison_inputs(rows)['Actual_Known_execution_SHA_equality_required'] is False
    rows['C1']['arrivals_sha'] = '0'*64
    with pytest.raises(ValueError, match='COMPARISON_INPUT_DRIFT'):
        comparison_inputs(rows)


def test_fresh_gate_requires_current_real_full96_original_11svr_trace():
    a = dict(slots=96, Actual_global_MILP_calls=0, trace_sha='a'*64)
    f = dict(status='PASS', slots=96, installed_SVR=11, trace_sha='a'*64,
             original_voltage_limits_preserved=True, original_current_transformer_limits_preserved=True)
    assert full96_fresh_gate(a, f, evidence_kind='REAL_DATA')['status'] == 'PASS'
    assert full96_fresh_gate(a, f, evidence_kind='NAMED_FIXTURE')['status'] == 'DIAGNOSTIC_ONLY'
    f['trace_sha'] = 'b'*64
    assert full96_fresh_gate(a, f, evidence_kind='REAL_DATA')['status'] == 'NOT_CERTIFIED'
    del a['trace_sha']; del f['trace_sha']
    assert full96_fresh_gate(a, f, evidence_kind='REAL_DATA')['status'] == 'NOT_CERTIFIED'


def test_validated_boundary_must_match_actual_driver_running_and_pending():
    r=SimpleNamespace(uid='k',gpu=4,submit=-900.,metadata={})
    args=dict(begin=0.,running=[(r,'B',-900.)],requests=[])
    state=dict(running=[dict(uid='k',site='A',start_seconds=-900.)])
    with pytest.raises(ValueError,match='INITIAL_RUNNING_DRIFT'):
        require_initial_state_alignment(state,args,identity(),evidence_scope='NAMED_FIXTURE')
    args['running']=[];args['requests']=[r];state={}
    with pytest.raises(ValueError,match='INITIAL_PENDING_DRIFT'):
        require_initial_state_alignment(state,args,identity(),evidence_scope='NAMED_FIXTURE')


def test_completed_boundary_cannot_reappear_in_future_arrival_bank():
    r=SimpleNamespace(uid='done',submit=900.,metadata={})
    with pytest.raises(ValueError,match='COMPLETED_BOUNDARY_UID_RESUBMITTED'):
        require_initial_state_alignment(dict(historical_completed=[dict(uid='done')]),
            dict(begin=0.,running=[],requests=[r]),identity(),evidence_scope='NAMED_FIXTURE')


def test_real_initial_boundary_requires_frozen_source_bytes(tmp_path):
    import json
    from v42_integration.unified_contract import file_sha
    args=dict(begin=0.,running=[],requests=[])
    with pytest.raises(ValueError,match='SOURCE_RECEIPT_REQUIRED'):
        require_initial_state_alignment({},args,identity(),evidence_scope='REAL_DATA')
    p=tmp_path/'STATE.json';p.write_text(json.dumps(dict(running=[],pending=[],historical_completed=[])))
    state=dict(source_record=dict(path=str(p),sha256=file_sha(p),bytes=p.stat().st_size))
    ident=dict(identity(),initial_state_sha=file_sha(p))
    assert require_initial_state_alignment(state,args,ident,evidence_scope='REAL_DATA')['status']=='PASS'
    p.write_text('{}')
    with pytest.raises(ValueError,match='SOURCE_BYTE_SHA_DRIFT'):
        require_initial_state_alignment(state,args,ident,evidence_scope='REAL_DATA')
