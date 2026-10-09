"""Native=0 infrastructure and phase-boundary tests with disposable fake workers."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import uuid
from contextlib import ExitStack
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
    for arm, day in co.AXIS:
        folder = root / 'inputs' / arm / day
        folder.mkdir(parents=True)
        atomic(folder / 'INPUT_IDENTITY.json', dict(arm=arm, day=day, Native_calls=0))
        atomic(folder / 'NATIVE_INPUT.json', dict(arm=arm, day=day, fixture_only=True))
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
    folder.mkdir(parents=True, exist_ok=True)
    atomic(folder / 'INPUT_IDENTITY.json', dict(arm=arm, day=day, Native_calls=0))
    atomic(folder / 'NATIVE_INPUT.json', dict(arm=arm, day=day, fixture_only=True))
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
import datetime, hashlib, json, os, pathlib, sys, time
request_path = pathlib.Path(sys.argv[1]); r = json.loads(request_path.read_text())
root = pathlib.Path(r['root']); marker = root / ('FAKE_WORKER_ACTIVE_'+r['arm']+'_'+str(r['worker_slot']))
if marker.exists(): raise RuntimeError('MULTIPLE_FAKE_WORKERS_IN_SAME_SLOT')
marker.write_text(str(os.getpid()))
try:
    order_lock=root/'FAKE_ORDER_LOCK'
    while True:
        try:
            fd=os.open(order_lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd);break
        except FileExistsError: time.sleep(.005)
    try:
        with (root / 'FAKE_EXECUTION_ORDER.jsonl').open('a') as order:
            order.write(json.dumps(dict(arm=r['arm'],day=r['day'],slot=r['worker_slot'],pid=os.getpid(),Native_calls=0))+'\n')
    finally: order_lock.unlink()
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


def test_62_b1_single_b2_three_failure_continues_and_completed_are_not_rerun(campaign):
    root, manifest = campaign
    for arm, day in co.AXIS:
        folder = root / 'inputs' / arm / day
        folder.mkdir(parents=True, exist_ok=True)
        atomic(folder / 'INPUT_IDENTITY.json', dict(arm=arm, day=day, Native_calls=0))
        atomic(folder / 'NATIVE_INPUT.json', dict(arm=arm, day=day, fixture_only=True))
    assert co.run(root, worker_command=fake_factory(root), verify=False, poll_seconds=0.01) == 0
    rows = [json.loads(line) for line in (root / 'FAKE_EXECUTION_ORDER.jsonl').read_text().splitlines()]
    assert [(r['arm'], r['day']) for r in rows[:31]] == list(co.AXIS[:31])
    assert sorted((r['arm'], r['day']) for r in rows[31:]) == list(co.AXIS[31:])
    assert all(r['slot'] == 1 for r in rows[:31]) and all(1 <= r['slot'] <= 3 for r in rows[31:])
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
    assert (rows[0]['arm'], rows[0]['day']) == ('B1', co.DAYS[-1])
    assert sorted((r['arm'], r['day']) for r in rows[1:4]) == [('B2', day) for day in co.DAYS[:3]]
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


PARALLEL_FAKE_WORKER = r'''
import hashlib,json,os,pathlib,sys,time,datetime,psutil
path=pathlib.Path(sys.argv[1]);r=json.loads(path.read_text());root=pathlib.Path(r['root'])
p=psutil.Process();identity=dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),parent=p.ppid(),priority=int(p.nice()))
def atomic(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp');tmp.write_text(json.dumps(value))
    for retry in range(200):
        try: os.replace(tmp,path);break
        except PermissionError: time.sleep(.005)
    else: raise RuntimeError('FAKE_ATOMIC_REPLACE_FAILED')
start=root/'FAKE_STARTS'/(r['arm']+'_'+r['day']+'.json')
atomic(start,dict(worker=identity,worker_slot=r['worker_slot'],Native_calls=0))
release=root/'FAKE_RELEASES'/(r['arm']+'_'+r['day']+'.json');begin=time.monotonic()
while not release.exists() and time.monotonic()-begin<20:
    stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    atomic(path.parent/'HEARTBEAT.json',dict(worker=identity,timestamp_UTC=stamp,phase='FAKE_P1',Native_calls=0))
    atomic(r['progress'],dict(worker=identity,timestamp_UTC=stamp,phase='FAKE_P1',UB=1.,independent_Global_LB=.99,certified_gap=.01,Native_Runtime=0.,Wall_Time=time.monotonic()-begin))
    time.sleep(.025)
status=json.loads(release.read_text())['status'] if release.exists() else 'IMPLEMENTATION_FAILURE'
output=pathlib.Path(r['output']);output.mkdir()
payload=output/'FAKE_PAYLOAD.json';atomic(payload,dict(arm=r['arm'],day=r['day'],Native_calls=0))
atomic(r['result'],dict(identity={k:r[k] for k in ('run_id','arm','day')},status=status,PASS=status=='PASS',Native_calls=0,files=[dict(path=str(payload),sha256=hashlib.sha256(payload.read_bytes()).hexdigest())],finished_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat()))
'''


def parallel_factory(root):
    path = root / 'parallel_fake_worker.py'
    path.write_text(PARALLEL_FAKE_WORKER, encoding='utf-8')
    return lambda manifest, request_path: [sys.executable, '-B', str(path), str(request_path)]


def wait_until(check, seconds=5):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if check():
            return
        time.sleep(.025)
    raise AssertionError('FAKE_WORKER_OBSERVATION_TIMEOUT')


def release_fake(root, active, status='PASS'):
    atomic(root / 'FAKE_RELEASES' / (active['arm'] + '_' + active['day'] + '.json'), dict(status=status))


def cleanup_fake(root, actives, children):
    for active in actives.values():
        release_fake(root, active)
    for child in children.values():
        code = child.wait(timeout=10)
        assert code == 0, (Path(child.args[-1]).parent / 'stderr.log').read_text()


def started_three(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest)
    complete_b1(checkpoint)
    co.save_checkpoint(root, checkpoint)
    actives, children = {}, {}
    factory = parallel_factory(root)
    names = co.dispatch_available(root, manifest, checkpoint, actives, children, factory)
    assert names == [co.key('B2', day) for day in co.DAYS[:3]]
    wait_until(lambda: all((root / 'FAKE_STARTS' / ('B2_' + day + '.json')).exists() for day in co.DAYS[:3]))
    return checkpoint, actives, children, factory


def test_b1_thirty_terminal_starts_zero_b2_then_thirtyone_starts_three(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest); complete_b1(checkpoint, 30)
    actives, children = {}, {}; factory = parallel_factory(root)
    try:
        co.dispatch_available(root, manifest, checkpoint, actives, children, factory)
        assert len(actives) == 1 and all(a['arm'] == 'B1' for a in actives.values())
        assert not list((root / 'dates' / 'B2').glob('*')) if (root / 'dates' / 'B2').exists() else True
        active = next(iter(actives.values())); release_fake(root, active)
        wait_until(lambda: bool(co.reap_finished(root, manifest, checkpoint, actives, children)))
        assert co.counts(checkpoint, 'B1')['completed'] == 31
        co.dispatch_available(root, manifest, checkpoint, actives, children, factory)
        assert len(actives) == 3 and {a['worker_slot'] for a in actives.values()} == {1, 2, 3}
        wait_until(lambda: all((Path(a['request']).parent / 'HEARTBEAT.json').exists() for a in actives.values()))
        value = co.snapshot(root, manifest, checkpoint)
        transition = read(root / 'B1_TO_B2_TRANSITION_VERIFICATION.json')
        assert transition['actual_transition'].get('B2_first_day') == co.DAYS[0], [
            (a['worker'], co.process(a['worker']['PID'])) for a in actives.values()]
        assert transition['actual_transition']['input_SHA'] == sha(root / 'inputs/B2/2025-05-01/NATIVE_INPUT.json')
        assert transition['actual_transition']['first_heartbeat']
        assert len(value['worker_slots']) == 3
    finally:
        cleanup_fake(root, actives, children)


def test_three_b2_workers_completion_fills_vacant_slot_and_monitor_exposes_each(campaign):
    root, manifest = campaign
    checkpoint, actives, children, factory = started_three(campaign)
    try:
        untouched = {name: a['worker'] for name, a in actives.items() if a['worker_slot'] != 1}
        release_fake(root, actives[co.key('B2', co.DAYS[0])])
        wait_until(lambda: bool(co.reap_finished(root, manifest, checkpoint, actives, children)))
        assert co.dispatch_available(root, manifest, checkpoint, actives, children, factory) == [co.key('B2', co.DAYS[3])]
        assert actives[co.key('B2', co.DAYS[3])]['worker_slot'] == 1
        assert all(actives[name]['worker'] == identity for name, identity in untouched.items())
        wait_until(lambda: (Path(actives[co.key('B2', co.DAYS[3])]['request']).parent / 'HEARTBEAT.json').exists())
        co.snapshot(root, manifest, checkpoint)
        view = monitor.view(root)
        assert {r['worker_slot'] for r in view['worker_slots']} == {1, 2, 3}
        assert {r['day'] for r in view['worker_slots']} == set(co.DAYS[1:4])
        assert len(set(view['Worker_PIDs'])) == 3
        assert all(r['worker_alive'] and r['heartbeat_timestamp_UTC'] and r['resource']['RSS'] for r in view['worker_slots']), [
            (r['worker'], co.process(r['PID']), r['worker_alive'], r.get('heartbeat_timestamp_UTC')) for r in view['worker_slots']]
        assert all(r['UB'] == 1 and r['independent_Global_LB'] == .99 and r['Certified_Gap'] == .01 for r in view['worker_slots'])
    finally:
        cleanup_fake(root, actives, children)


def test_one_b2_failure_is_terminal_other_two_keep_running_and_next_date_starts(campaign):
    root, manifest = campaign
    checkpoint, actives, children, factory = started_three(campaign)
    try:
        identities = {name: a['worker'] for name, a in actives.items() if a['worker_slot'] != 1}
        first = co.key('B2', co.DAYS[0]); release_fake(root, actives[first], 'INPUT_FAILURE')
        wait_until(lambda: bool(co.reap_finished(root, manifest, checkpoint, actives, children)))
        assert checkpoint['dates'][first]['status'] == 'INPUT_FAILURE'
        assert checkpoint['dates'][first]['attempts'] == 1
        assert all(co.same_process(identity) and actives[name]['worker'] == identity for name, identity in identities.items())
        co.dispatch_available(root, manifest, checkpoint, actives, children, factory)
        assert co.key('B2', co.DAYS[3]) in actives and first not in actives
        assert all(checkpoint['dates'][name]['attempts'] == 1 for name in actives)
    finally:
        cleanup_fake(root, actives, children)


def test_restart_adopts_all_three_even_when_actives_persistence_is_missing(campaign):
    root, manifest = campaign
    checkpoint, actives, children, factory = started_three(campaign)
    try:
        identities = {name: a['worker'] for name, a in actives.items()}
        (root / 'ACTIVES.json').unlink(); atomic(root / 'ACTIVE.json', {})
        checkpoint['dates'][co.key('B2', co.DAYS[1])].update(status='PENDING', attempts=0)
        with patch.object(co.subprocess, 'Popen', side_effect=AssertionError('RESTART_DUPLICATE')):
            recovered = co.recover_actives(root, manifest, checkpoint)
            assert co.dispatch_available(root, manifest, checkpoint, recovered, {}, factory) == []
        assert set(recovered) == set(identities)
        assert all(a['adopted'] and a['worker'] == identities[name] for name, a in recovered.items())
        assert all(checkpoint['dates'][name]['attempts'] == 1 for name in recovered)
        assert len(read(root / 'ACTIVES.json')['workers']) == 3
    finally:
        cleanup_fake(root, actives, children)


def test_duplicate_slot_and_cross_arm_overlap_are_denied(campaign):
    root, manifest = campaign
    checkpoint = co.load_checkpoint(root, manifest); complete_b1(checkpoint)
    duplicated = {co.key('B2', day): dict(arm='B2', day=day, worker_slot=1) for day in co.DAYS[:2]}
    with pytest.raises(PermissionError, match='WORKER_SLOT_LIMIT_OR_DUPLICATE'):
        co.validate_slots(checkpoint, duplicated)
    with pytest.raises(PermissionError, match='B1_B2_WORKER_OVERLAP'):
        co.validate_slots(checkpoint, dict(duplicated, **{'B1/2025-05-31': dict(arm='B1', day=co.DAYS[-1], worker_slot=1)}))


@pytest.mark.parametrize('corruption,expected', [
    ('checkpoint_pointer', 'CHECKPOINT_REQUEST_PATH_NOT_CANONICAL'),
    ('request_arm', 'CHECKPOINT_REQUEST_ARM_DATE_DRIFT'),
    ('request_day', 'CHECKPOINT_REQUEST_ARM_DATE_DRIFT'),
    ('request_output', 'ARM_DATE_OUTPUT_PATH_MIXING'),
    ('request_progress', 'ARM_DATE_OUTPUT_PATH_MIXING'),
    ('request_result', 'ARM_DATE_OUTPUT_PATH_MIXING'),
    ('request_error', 'ARM_DATE_OUTPUT_PATH_MIXING'),
    ('request_manifest', 'WORKER_REQUEST_MANIFEST_PATH_DRIFT'),
    ('request_root', 'WORKER_REQUEST_ROOT_DRIFT'),
    ('request_run_id', 'WORKER_REQUEST_RUN_ARM_DATE_DRIFT'),
    ('request_missing_slot', 'WORKER_REQUEST_SLOT_OUTSIDE_ARM_LIMIT'),
    ('checkpoint_missing_request', 'CHECKPOINT_RUNNING_REQUEST_MISSING'),
    ('checkpoint_slot', 'CHECKPOINT_REQUEST_WORKER_SLOT_DRIFT'),
    ('active_request_pointer', 'ACTIVES_REQUEST_PATH_NOT_CANONICAL'),
    ('active_slot', 'CHECKPOINT_REQUEST_WORKER_SLOT_DRIFT'),
])
def test_restart_rejects_cross_date_or_request_identity_before_any_peer_mutation(campaign, corruption, expected):
    root, manifest = campaign
    checkpoint, actives, children, factory = started_three(campaign)
    names = [co.key('B2', day) for day in co.DAYS[:3]]
    victim, peer = names[1], names[2]
    paths = {name: Path(active['request']) for name, active in actives.items()}
    original = {name: path.read_bytes() for name, path in paths.items()}
    identities = {name: active['worker'] for name, active in actives.items()}
    try:
        # The later row is corrupted while an earlier, correctly live peer is
        # eligible for adoption. The entire recovery must fail before writes.
        if corruption == 'checkpoint_pointer':
            checkpoint['dates'][victim]['request'] = str(paths[peer])
        elif corruption == 'checkpoint_missing_request':
            del checkpoint['dates'][victim]['request']
        elif corruption == 'checkpoint_slot':
            checkpoint['dates'][victim]['worker_slot'] = actives[peer]['worker_slot']
        elif corruption.startswith('active_'):
            tampered = json.loads(json.dumps(actives))
            if corruption == 'active_request_pointer':
                tampered[victim]['request'] = str(paths[peer])
            else:
                tampered[victim]['worker_slot'] = actives[peer]['worker_slot']
            co.persist_actives(root, manifest, tampered)
        else:
            value = read(paths[victim])
            field = corruption.removeprefix('request_')
            if field == 'arm':
                value[field] = 'B1'
            elif field == 'day':
                value[field] = co.DAYS[2]
            elif field == 'manifest':
                alternate = root / 'alternate_manifest.json'
                alternate.write_bytes((root / 'CAMPAIGN_MANIFEST.json').read_bytes())
                value[field] = str(alternate)
            elif field == 'root':
                value[field] = str(root.parent)
            elif field == 'run_id':
                value[field] = 'DIFFERENT_CAMPAIGN_RUN'
            elif field == 'missing_slot':
                del value['worker_slot']
            else:
                value[field] = read(paths[peer])[field]
            atomic(paths[victim], value)
        co.save_checkpoint(root, checkpoint)
        before = {name: (root / name).read_bytes() for name in ('CHECKPOINT.json', 'ACTIVE.json', 'ACTIVES.json')}
        with ExitStack() as forbid:
            for function in ('matching_live_worker', 'finish_attempt', 'persist_actives', 'save_checkpoint'):
                forbid.enter_context(patch.object(co, function, side_effect=AssertionError('MUTATION_OR_ADOPTION_BEFORE_COMPLETE_IDENTITY_CHECK')))
            forbid.enter_context(patch.object(co.subprocess, 'Popen', side_effect=AssertionError('WRONG_DATE_DUPLICATE_LAUNCH')))
            with pytest.raises(PermissionError, match=expected):
                co.recover_actives(root, manifest, checkpoint)
        assert all((root / name).read_bytes() == contents for name, contents in before.items())
        assert all(co.same_process(identity) for identity in identities.values())
        assert all(actives[name]['worker'] == identity for name, identity in identities.items())
        assert paths[names[0]].read_bytes() == original[names[0]]
        assert paths[peer].read_bytes() == original[peer]
        assert all(checkpoint['dates'][name]['attempts'] == 1 for name in names)
    finally:
        for name, path in paths.items():
            path.write_bytes(original[name])
        cleanup_fake(root, actives, children)
