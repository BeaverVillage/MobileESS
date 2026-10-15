"""Small monitor JSON fixtures; no old monitor process or solver touched."""
import json

from tools.serve_v42_table_v_monitor import digest, state


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf8')


def current_physical_fixture(source, *, folder=None):
    identity = dict(case_sha='current-E1', science_sha='science')
    write(source/'MAY01_TABLE_V_FOUR_ARM_CONTRACT.json',dict(source_identity=identity,source_sha='source',common_initial_state_sha='initial'))
    folder = source/'B0' if folder is None else folder
    payload = dict(arm='B0',source_identity=identity,source_sha='source',policy='현재')
    actual = dict(arm='B0',status='FULL_PASS',source_identity=identity,source_sha='source',
        evaluation_case_payload=payload,evaluation_case_sha=digest(payload),executed_actual_slots=96,
        MESS_plan_sha='off',actual_trace=dict(path='source-current-trace',sha256='sha',bytes=1))
    write(folder/'ACTUAL_RESULT.json',dict(status='FULL_PASS',result=actual))
    cert = dict(case_sha=actual['evaluation_case_sha'],initial_state_sha='initial',MESS_plan_sha='off',
        actual_trace=actual['actual_trace'],slots=96,official_Full96=True,maximum_phase_line_loading=.734,
        voltage_min_pu=.96,voltage_max_pu=1.04,status='PASS')
    cert['certificate_sha'] = digest(cert)
    fresh = dict(status='FULL_PASS',executed_slots=96,official_certificate=cert)
    write(folder/'FRESH_AC_RESULT.json',dict(status='FULL_PASS',result=fresh))
    return actual, fresh


def test_actual_physical_ratio_converted_to_percent_only_for_current96(tmp_path):
    current_physical_fixture(tmp_path)
    result = state(tmp_path)
    assert result['order'] == ['B0','B1','B2','B3']
    assert result['arms'][0]['maximum_actual_phase_line_loading_percent'] == 73.4
    assert result['arms'][1]['maximum_actual_phase_line_loading_percent'] is None
    assert result['Planning_rho_displayed_as_Actual_loading'] is False


def test_old_case_fresh_metric_not_transferred_by_a_full_pass_header(tmp_path):
    _, fresh = current_physical_fixture(tmp_path)
    fresh['official_certificate']['case_sha'] = 'old-RC03'
    write(tmp_path/'B0/FRESH_AC_RESULT.json',dict(status='FULL_PASS',result=fresh))
    result = state(tmp_path)
    assert result['arms'][0]['maximum_actual_phase_line_loading_percent'] is None
    assert result['arms'][0]['physical_status'] == 'NOT_RUN'


def test_latest_append_attempt_selected_without_resetting_shared_native(tmp_path):
    folder = tmp_path/'B0/ATTEMPT02'
    current_physical_fixture(tmp_path,folder=folder)
    write(tmp_path/'B0/ARM_OUTCOME.json',dict(status='NOT_CERTIFIED',failed_stage='SOURCE_VERIFY'))
    write(tmp_path/'B0/LATEST_ATTEMPT.json',dict(path=str(folder.resolve()),name='ATTEMPT02',
        prior_attempts_preserved=True,Native_budget_reset=False))
    write(tmp_path/'PLANNING_NATIVE_LEDGER.json',dict(calls=[dict(solver='GUROBI',Native_Runtime=12.,
        stage_context=dict(arm='B2',stage='M1'))]))
    result = state(tmp_path)
    assert result['arms'][0]['current_attempt'] == 'ATTEMPT02'
    assert result['arms'][0]['prior_original_status'] == 'NOT_CERTIFIED'
    assert result['arms'][0]['maximum_actual_phase_line_loading_percent'] == 73.4
    assert result['arms'][2]['Native_seconds'] == 12.


def test_inflight_native_overrides_stale_bindings_phase_and_separates_wall(tmp_path, monkeypatch):
    monkeypatch.setattr('tools.serve_v42_table_v_monitor.time.time', lambda: 1000.)
    context = dict(arm='B1',stage='A1')
    write(tmp_path/'B1/LIVE_PROGRESS.json',dict(stage='A1',elapsed_wall_seconds=100.,
        progress=dict(phase='NATIVE_BINDINGS')))
    write(tmp_path/'PLANNING_NATIVE_LEDGER.json',dict(calls=[
        dict(solver='BUILD',measured_seconds=93.914,stage_context=context)],
        active_stage_context=context,inflight=dict(stage_context=context,started_epoch_seconds=400.)))
    row = state(tmp_path)['arms'][1]
    assert row['current_stage'] == 'A1' and row['current_phase'] == 'NATIVE_OPTIMIZE_RUNNING'
    assert row['last_progress_phase'] == 'NATIVE_BINDINGS'
    assert row['completed_model_preprocessing_wall_seconds'] == 93.914
    assert row['completed_Native_Runtime_seconds'] == 0.
    assert row['Native_calls_completed'] == 0 and row['Native_calls_inflight'] == 1
    assert row['Native_calls_started'] == 1 and row['current_Native_call_wall_seconds'] == 600.
    assert row['current_Native_Runtime_pending'] and row['current_call_wall_is_not_final_Native_Runtime']


def test_ended_infeasible_arm_does_not_remain_in_bindings_or_running_phase(tmp_path):
    context = dict(arm='B1',stage='A1')
    write(tmp_path/'B1/LIVE_PROGRESS.json',dict(stage='A1',progress=dict(phase='NATIVE_BINDINGS')))
    write(tmp_path/'B1/ARM_OUTCOME.json',dict(status='NOT_CERTIFIED',failed_stage='A1',wall_seconds=888.227))
    write(tmp_path/'PLANNING_NATIVE_LEDGER.json',dict(calls=[
        dict(solver='BUILD',measured_seconds=93.914,stage_context=context),
        dict(solver='GUROBI',Native_Runtime=776.269,status=3,stage_context=context)],inflight=None))
    row = state(tmp_path)['arms'][1]
    assert row['current_phase'] == 'ARM_FAILED' and row['failed_phase'] == 'A1'
    assert row['last_progress_phase'] == 'NATIVE_BINDINGS'
    assert row['last_completed_Native_status'] == 3 and row['last_completed_Native_status_name'] == 'INFEASIBLE'
    assert row['Native_calls_completed'] == 1 and row['Native_calls_inflight'] == 0
    assert row['completed_Native_Runtime_seconds'] == 776.269
    assert row['completed_model_preprocessing_wall_seconds'] == 93.914


def test_completed_arm_shows_terminal_phase(tmp_path):
    current_physical_fixture(tmp_path)
    write(tmp_path/'B0/LIVE_PROGRESS.json',dict(stage='FRESH_AC96',progress='STARTED'))
    write(tmp_path/'B0/ARM_OUTCOME.json',dict(status='FULL_PASS',wall_seconds=48.5))
    row = state(tmp_path)['arms'][0]
    assert row['current_stage'] == 'COMPLETED' and row['current_phase'] == 'ARM_COMPLETED'
    assert row['completed_phase'] == 'FRESH_AC96' and row['failed_phase'] is None
