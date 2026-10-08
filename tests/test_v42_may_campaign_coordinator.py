"""Native=0 infrastructure and phase-boundary tests with disposable fake workers."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid
from unittest.mock import patch

import pytest

from v42_pr134_b1.common import atomic, read, process, sha, ROOT
from v42_may_campaign import coordinator as co
from v42_may_campaign import monitor, watchdog


@pytest.fixture
def campaign():
    base = ROOT / 'tmp' / 'v42_may_campaign_coordinator_tests'
    base.mkdir(parents=True, exist_ok=True)
    root = base / uuid.uuid4().hex
    root.mkdir()
    manifest = dict(run_id='FAKE_NATIVE_ZERO_' + root.name, Python=sys.executable,
                    monitor_port=8793, axis=[dict(arm=a, day=d) for a, d in co.AXIS])
    atomic(root / 'CAMPAIGN_MANIFEST.json', manifest)
    try:
        yield root, manifest
    finally:
        assert root.resolve().is_relative_to(base.resolve())
        shutil.rmtree(root)


def complete_b1(checkpoint, through=31):
    for index, day in enumerate(co.DAYS[:through]):
        checkpoint['dates'][co.key('B1', day)].update(
            status='PASS' if index % 3 == 0 else 'TIME_LIMIT_NO_VALID_INCUMBENT' if index % 3 == 1
            else 'PHYSICAL_FAILURE', attempts=1)


def request(campaign, arm, day):
    root, manifest = campaign
    folder = root / 'inputs' / arm / day
    folder.mkdir(parents=True)
    atomic(folder / 'INPUT_IDENTITY.json', dict(arm=arm, day=day, Native_calls=0))
    path, req = co.new_request(root, manifest, arm, day)
    return path, req


def test_b1_30_terminal_one_pending_cannot_start_b2(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    complete_b1(checkpoint, 30)
    assert co.counts(checkpoint, 'B1')['completed'] == 30
    with pytest.raises(PermissionError, match='BEFORE_ALL_B1_TERMINAL'):
        co.ensure_phase(checkpoint, 'B2')
    assert all(r['attempts'] == 0 for r in checkpoint['dates'].values() if r['arm'] == 'B2')


def test_b1_31_terminal_failures_permit_b2(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    complete_b1(checkpoint)
    co.ensure_phase(checkpoint, 'B2')
    assert co.counts(checkpoint, 'B1')['PASS'] < 31
    assert co.counts(checkpoint, 'B1')['TIMEOUT'] > 0
    assert co.counts(checkpoint, 'B1')['FAIL'] > 0


FAKE_WORKER = r'''
import datetime, hashlib, json, os, pathlib, sys
request_path = pathlib.Path(sys.argv[1]); r = json.loads(request_path.read_text())
root = pathlib.Path(r['root']); marker = root / 'FAKE_WORKER_ACTIVE'
if marker.exists(): raise RuntimeError('MULTIPLE_FAKE_WORKERS')
marker.write_text(str(os.getpid()))
try:
    with (root / 'FAKE_EXECUTION_ORDER.jsonl').open('a') as order:
        order.write(json.dumps(dict(arm=r['arm'],day=r['day'],pid=os.getpid(),Native_calls=0))+'\n')
    output = pathlib.Path(r['output']); output.mkdir()
    payload = output / 'fake_payload.json'; payload.write_text(json.dumps(dict(arm=r['arm'],day=r['day'],fake=True,Native_calls=0)))
    status = 'TIME_LIMIT_NO_VALID_INCUMBENT' if r['arm']=='B1' and r['day']=='2025-05-05' else 'PASS'
    receipt = dict(run_id=r['run_id'],arm=r['arm'],day=r['day'],status=status,PASS=status=='PASS',Native_calls=0,
                   wall_seconds=0.0,Native_Runtime_seconds=0.0,files=[dict(path=str(payload),sha256=hashlib.sha256(payload.read_bytes()).hexdigest())],
                   finished_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat())
    temporary=pathlib.Path(r['result']+'.tmp'); temporary.write_text(json.dumps(receipt)); os.replace(temporary,r['result'])
finally:
    marker.unlink()
'''


def fake_factory(root):
    path = root / 'fake_worker.py'
    path.write_text(FAKE_WORKER, encoding='utf-8')
    return lambda manifest, request_path: [sys.executable, '-B', str(path), str(request_path)]


def test_62_serial_arm_dates_failure_continues_and_completed_are_not_rerun(campaign):
    root, manifest = campaign
    for arm, day in co.AXIS:
        folder = root / 'inputs' / arm / day
        folder.mkdir(parents=True)
        atomic(folder / 'INPUT_IDENTITY.json', dict(arm=arm, day=day, Native_calls=0))
    assert co.run(root, worker_command=fake_factory(root), verify=False, poll_seconds=0.01) == 0
    rows = [json.loads(line) for line in (root / 'FAKE_EXECUTION_ORDER.jsonl').read_text().splitlines()]
    assert [(r['arm'], r['day']) for r in rows] == list(co.AXIS)
    assert all(r['Native_calls'] == 0 for r in rows)
    checkpoint = read(root / 'CHECKPOINT.json')
    assert checkpoint['state'] == 'COMPLETE'
    assert co.counts(checkpoint) == dict(total=62, completed=62, PASS=61, TIMEOUT=1, FAIL=0, pending=0)
    assert all(r['attempts'] == 1 for r in checkpoint['dates'].values())
    with patch.object(co.subprocess, 'Popen', side_effect=AssertionError('TERMINAL_DATE_RERUN')):
        co.run(root, verify=False)
    assert len((root / 'FAKE_EXECUTION_ORDER.jsonl').read_text().splitlines()) == 62
    result = Path(checkpoint['dates']['B1/2025-05-01']['result'])
    payload = Path(read(result)['files'][0]['path'])
    original_payload = payload.read_bytes()
    payload.write_bytes(b'tampered scientific payload')
    with patch.object(co.subprocess, 'Popen', side_effect=AssertionError('PAYLOAD_TAMPER_RERUN')):
        with pytest.raises(PermissionError, match='COMPLETED_RESULT_SHA_DRIFT'):
            co.run(root, verify=False)
    payload.write_bytes(original_payload)
    result.write_text('{}')
    with patch.object(co.subprocess, 'Popen', side_effect=AssertionError('TAMPER_RERUN')):
        with pytest.raises(PermissionError, match='COMPLETED_RESULT_SHA_DRIFT'):
            co.run(root, verify=False)


def test_transition_automatically_starts_b2_after_last_b1_terminal(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    complete_b1(checkpoint, 30)
    co.save_checkpoint(root, checkpoint)
    assert co.run(root, worker_command=fake_factory(root), verify=False, poll_seconds=0.01) == 0
    rows = [json.loads(line) for line in (root / 'FAKE_EXECUTION_ORDER.jsonl').read_text().splitlines()]
    assert [(r['arm'], r['day']) for r in rows[:2]] == [('B1', co.DAYS[-1]), ('B2', co.DAYS[0])]
    assert len(rows) == 32
    assert co.counts(read(root / 'CHECKPOINT.json'), 'B1')['completed'] == 31


def test_restart_at_b2_transition_adopts_exact_live_worker_without_duplicate(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    complete_b1(checkpoint)
    path, req = request(campaign, 'B2', co.DAYS[0])
    worker = process()
    req['worker_command'] = worker['command']
    atomic(path, req)
    atomic(root / 'ACTIVE.json', dict(arm='B2', day=co.DAYS[0], request=str(path), worker=worker))
    with patch.object(co.subprocess, 'Popen', side_effect=AssertionError('LIVE_ORPHAN_DUPLICATED')):
        active = co.recover_active(root, manifest, checkpoint)
    assert active['adopted'] is True
    assert active['worker'] == worker
    assert checkpoint['dates']['B2/2025-05-01']['attempts'] == 1
    atomic(root / 'B1_TO_B2_TRANSITION_VERIFICATION.json', dict(
        native_zero_tests=dict(PASS=True, Native_optimize_calls=0, fixture_only=True),
        actual_transition=dict(status='NOT_YET_OBSERVED')))
    evidence = co.transition_evidence(root, checkpoint, active,
                                     dict(worker=worker, timestamp_UTC=req['started_UTC'], phase='FAKE_NATIVE_ZERO'))
    assert evidence['native_zero_tests']['PASS'] is True
    actual = evidence['actual_transition']
    assert actual['status'] == 'OBSERVED'
    assert actual['B2_worker'] == worker
    assert actual['input_SHA']
    assert actual['first_heartbeat']['worker'] == worker


def test_restart_with_dead_attempt_finishes_once_and_never_retries(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    path, req = request(campaign, 'B1', co.DAYS[0])
    checkpoint['dates']['B1/2025-05-01'].update(status='RUNNING', attempts=1, request=str(path))
    co.save_checkpoint(root, checkpoint)
    with patch.object(co, 'matching_live_worker', return_value=None):
        co.recover_active(root, manifest, checkpoint)
    row = checkpoint['dates']['B1/2025-05-01']
    assert row['status'] == 'INTERRUPTED_NO_VALID_RESULT'
    assert row['attempts'] == 1
    assert checkpoint['dates']['B1/2025-05-02']['status'] == 'PENDING'


def test_restart_request_precedes_checkpoint_no_second_attempt(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    request(campaign, 'B1', co.DAYS[0])
    with patch.object(co, 'matching_live_worker', return_value=None):
        co.recover_active(root, manifest, checkpoint)
    assert checkpoint['dates']['B1/2025-05-01']['status'] == 'INTERRUPTED_NO_VALID_RESULT'
    assert checkpoint['dates']['B1/2025-05-01']['attempts'] == 1


def test_arm_mixing_in_result_input_ledger_or_checkpoint_is_rejected(campaign):
    root, manifest = campaign
    path, req = request(campaign, 'B2', co.DAYS[0])
    fake_b1_result = dict(run_id=manifest['run_id'], arm='B1', day=co.DAYS[0], status='PASS', PASS=True, files=[])
    assert co.receipt_valid(root, manifest, req, fake_b1_result) is False
    mixed_req = dict(req, input_folder=str(root / 'inputs' / 'B1' / co.DAYS[0]))
    with pytest.raises(PermissionError, match='INPUT_FOLDER_MIXING'):
        co.validate_request(root, manifest, mixed_req)
    atomic(Path(req['input_folder']) / 'INPUT_IDENTITY.json', dict(arm='B1', day=co.DAYS[0]))
    with pytest.raises(PermissionError, match='INPUT_LEDGER_MIXING'):
        co.validate_request(root, manifest, req)
    checkpoint = co.load_checkpoint(root, manifest)
    checkpoint['dates']['B2/2025-05-01']['arm'] = 'B1'
    co.save_checkpoint(root, checkpoint)
    with pytest.raises(PermissionError, match='ARM_DATE_OR_NO_RETRY_DRIFT'):
        co.load_checkpoint(root, manifest)


def test_verified_checkpoint_backup_and_pid_reuse_rejection(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    co.save_checkpoint(root, checkpoint)
    co.save_checkpoint(root, checkpoint)
    (root / 'CHECKPOINT.json').write_text('{corrupt')
    restored = co.load_checkpoint(root, manifest)
    assert restored['run_id'] == manifest['run_id']
    assert list(root.glob('CHECKPOINT_CORRUPT_*'))
    from v42_pr134_b1.common import same_process
    worker = process()
    assert not same_process(dict(worker, created=worker['created'] + 1))


def test_coordinator_lock_prevents_second_coordinator(campaign):
    root, manifest = campaign
    with co.os_lock(root / 'COORDINATOR.lock') as first:
        assert first
        with co.os_lock(root / 'COORDINATOR.lock') as second:
            assert not second


def test_monitor_is_read_only_and_shows_separate_31_date_tables(campaign):
    root, manifest = campaign
    before = sorted(p.name for p in root.iterdir())
    value = monitor.view(root)
    assert before == sorted(p.name for p in root.iterdir())
    assert value['read_only'] is True
    assert len(value['date_tables']['B1']) == len(value['date_tables']['B2']) == 31
    assert value['B2_ready'] is False
    assert value['UB'] is value['Native_BestBd'] is value['independent_Global_LB'] is None
    (root / 'CHECKPOINT.json').write_text('{bad')
    value = monitor.view(root)
    assert (root / 'CHECKPOINT.json').read_text() == '{bad'
    assert value['state'] == 'STATUS_UNAVAILABLE'


def test_watchdog_does_not_restart_or_kill_healthy_processes(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    co.save_checkpoint(root, checkpoint)
    atomic(root / 'COORDINATOR_HEARTBEAT.json', dict(process=process(), timestamp_UTC='2000-01-01T00:00:00+00:00'))
    atomic(root / 'MONITOR_PROCESS.json', process())
    with patch.object(watchdog, 'load_manifest', return_value=manifest), patch.object(watchdog.subprocess, 'run') as launch:
        value = watchdog.run(root)
    launch.assert_not_called()
    assert value['actions'] == []
    assert value['healthy_solver_kill'] is False


def test_monitor_native_bound_gap_do_not_masquerade_as_independent_certificate(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    co.save_checkpoint(root, checkpoint)
    atomic(root / 'CAMPAIGN_STATUS.json', dict(progress=dict(BestBd=0.9, gap=0.01), resource={}))
    view = monitor.view(root)
    assert view['Native_BestBd'] == 0.9
    assert view['independent_Global_LB'] is None
    assert view['Certified_Gap'] is None


def test_transition_first_worker_heartbeat_is_durable_and_separate_from_native_zero_tests(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    complete_b1(checkpoint)
    path, req = request(campaign, 'B2', co.DAYS[0])
    worker = process()
    active = dict(arm='B2', day=co.DAYS[0], request=str(path), worker=worker)
    native_tests = dict(PASS=True, Native_optimize_calls=0, fixture_only=True)
    atomic(root / 'B1_TO_B2_TRANSITION_VERIFICATION.json', dict(
        native_zero_tests=native_tests, actual_transition=dict(status='NOT_YET_OBSERVED')))
    before = co.transition_evidence(root, checkpoint, {})
    assert before['actual_transition']['status'] == 'NOT_YET_OBSERVED'
    Path(req['output']).mkdir()
    heartbeat_path = Path(req['output']) / 'HEARTBEAT.json'
    atomic(heartbeat_path, dict(timestamp_UTC=req['started_UTC'], process=worker))
    first = co.transition_evidence(root, checkpoint, active)
    assert first['native_zero_tests'] == native_tests
    assert first['actual_transition']['first_heartbeat']['timestamp_UTC'] == req['started_UTC']
    atomic(heartbeat_path, dict(timestamp_UTC='2099-01-01T00:00:00+00:00', process=worker))
    second = co.transition_evidence(root, checkpoint, active)
    assert second['actual_transition']['first_heartbeat'] == first['actual_transition']['first_heartbeat']


def test_worker_nested_fields_are_exported_with_distinct_bound_and_fresh_ac_time(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    path, req = request(campaign, 'B1', co.DAYS[0])
    atomic(path.parent / 'NATIVE_RUNTIME_LEDGER.json', dict(calls=[dict(Native_BestBd=1.5)], fixture_only=True))
    row = checkpoint['dates']['B1/2025-05-01']
    row.update(status='PASS', request=str(path), summary=dict(
        PASS=True, scientific_PASS=True, Native_Runtime=90, Native_calls=2,
        optimization_wall_seconds=123, evaluation_wall_seconds=20,
        fields=dict(UB=2.0, LB=1.995, certified_gap=.0025, planning_rho_max=2.0, case_sha='fake-case'),
        evaluation=dict(PASS=True, summary=dict(rho_max_AC=2.1, voltage_violation_count=0,
                                                line_current_violation_count=0))))
    co.export(root, manifest, checkpoint)
    import csv
    gap = next(csv.DictReader((root / 'DATE_ARM_GAP.csv').open(encoding='utf-8')))
    runtime = next(csv.DictReader((root / 'DATE_ARM_RUNTIME.csv').open(encoding='utf-8')))
    ac = next(csv.DictReader((root / 'DATE_ARM_DDAY_AC.csv').open(encoding='utf-8')))
    assert gap['UB'] == '2.0' and gap['independent_Global_LB'] == '1.995'
    assert gap['Native_BestBd'] == '1.5' and gap['Certified_Gap_percent'] == '0.25'
    assert runtime['wall_seconds'] == '123' and runtime['Native_Runtime_seconds'] == '90'
    assert runtime['Fresh_AC_seconds'] == '20'
    assert ac['Fresh_AC_status'] == 'PASS' and ac['Fresh_AC_max_line_loading'] == '2.1'
