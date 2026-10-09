"""Native=0 Worker receipts with fake A/M and Fresh AC adapters only."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import uuid
from unittest.mock import patch

import pytest

from v42_may_campaign import coordinator as co, execution, worker
from v42_may_campaign.budget import BudgetStop
from v42_may_campaign.common import ROOT, atomic, read, sha, LockBusy, exclusive_lock
from v42_may_campaign.preflight import native_zero


@pytest.fixture
def campaign():
    base = ROOT / 'tmp/v42_may_campaign_worker_tests'
    base.mkdir(parents=True, exist_ok=True)
    root = base / uuid.uuid4().hex
    root.mkdir()
    manifest = dict(run_id='FAKE_NATIVE_ZERO_' + root.name, Python=sys.executable,
                    input_folders={}, axis=[dict(arm=a, day=d) for a, d in co.AXIS])
    for arm in ('B1', 'B2'):
        for day in co.DAYS[:4]:
            folder = root / 'inputs' / arm / day
            folder.mkdir(parents=True)
            atomic(folder / 'INPUT_IDENTITY.json', dict(arm=arm, day=day, fixture_only=True))
            atomic(folder / 'NATIVE_INPUT.json', dict(arm=arm, day=day, fixture_only=True))
            manifest['input_folders'][arm + '/' + day] = str(folder)
    atomic(root / 'CAMPAIGN_MANIFEST.json', manifest)
    prior_environment = {name: os.environ.get(name) for name in ('TEMP', 'TMP', 'PYTHONDONTWRITEBYTECODE', 'PYTHONUTF8')}
    prior_temp = tempfile.tempdir
    try:
        yield root, manifest
    finally:
        tempfile.tempdir = prior_temp
        for name, value in prior_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        assert root.resolve().is_relative_to(base.resolve())
        shutil.rmtree(root)


def fake_stage(request, budget, progress):
    output = Path(request['output'])
    output.mkdir()
    (output / 'incumbent.npz').write_bytes(b'NATIVE_ZERO_FAKE_POINT')
    atomic(output / 'CERTIFICATE.json', dict(PASS=True, fixture_only=True))
    progress(dict(phase='FAKE_P1_NATIVE_ZERO', UB=1., Certified_Global_LB=.998,
                  Certified_Gap=.002, **budget.snapshot()))
    return dict(PASS=True, classification='PASS', UB=1., LB=.998, certified_gap=.002,
                planning_rho_max=1.1, case_sha='FAKE_CASE_SHA', P2_calls=0,
                incumbent=dict(path=str(output / 'incumbent.npz')))


def fake_operations(request, scientific, progress):
    progress(dict(phase='FAKE_FRESH_AC_NATIVE_ZERO'))
    atomic(Path(request['output']) / 'FRESH_AC.json', dict(PASS=True, fixture_only=True))
    return dict(PASS=True, summary=dict(rho_max_AC=1.2,
                voltage_violation_count=0, line_current_violation_count=0))


@contextmanager
def fake_adapters(campaign, stage=fake_stage, operations=fake_operations):
    root, manifest = campaign
    modules = {}
    for name, run in (('a_stage', stage), ('m_stage', stage), ('operations', operations)):
        module = ModuleType('v42_may_campaign.' + name)
        module.run = run
        modules[module.__name__] = module
    package = sys.modules['v42_may_campaign']
    with patch.dict(sys.modules, modules), \
            patch.object(package, 'a_stage', modules['v42_may_campaign.a_stage'], create=True), \
            patch.object(package, 'm_stage', modules['v42_may_campaign.m_stage'], create=True), \
            patch.object(package, 'operations', modules['v42_may_campaign.operations'], create=True), \
            patch.object(co, 'load_manifest', return_value=manifest), \
            patch.object(execution, 'verify_manifest', return_value=manifest), \
            patch.object(worker, 'RUNTIME', root / 'locks'), \
            patch.object(worker, 'assert_no_other_native_worker', return_value=[]), native_zero() as denied:
        yield denied


@pytest.mark.parametrize('arm', ['B1', 'B2'])
def test_pass_receipt_is_immutable_with_ledger_inclusive_wall_and_terminal_heartbeat(campaign, arm):
    root, manifest = campaign
    request_path, request = co.new_request(root, manifest, arm, co.DAYS[0])
    request['started_UTC'] = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    atomic(request_path, request)
    inclusive_wall = {}
    def delayed_stage(request, budget, progress):
        inclusive_wall['worker_T0'] = budget.started
        time.sleep(.015)
        return fake_stage(request, budget, progress)
    before = time.perf_counter()
    with fake_adapters(campaign, stage=delayed_stage) as denied:
        assert worker.run(request_path) == 0
    receipt = read(request['result'])
    assert denied == []
    assert receipt['PASS'] is True and receipt['status'] == 'PASS'
    assert receipt['Native_calls'] == receipt['Native_Runtime'] == receipt['P2_calls'] == 0
    assert inclusive_wall['worker_T0'] <= before - 19
    assert receipt['optimization_wall_seconds'] >= 20
    assert receipt['total_date_wall_seconds'] >= receipt['optimization_wall_seconds']
    assert receipt['dispatch_wall_seconds'] >= 20
    assert receipt['fields']['UB'] == 1 and receipt['fields']['independent_Global_LB'] == .998
    assert receipt['fields']['certified_gap'] == .002
    assert receipt['fields']['case_sha'] == 'FAKE_CASE_SHA'
    assert receipt['input_SHA'] == sha(Path(request['input_folder']) / 'NATIVE_INPUT.json')
    assert receipt['own_tmp'] == str(request_path.parent / 'tmp')
    assert receipt['worker_slot'] == request['worker_slot']
    admission = read(receipt['admission']['path'])
    assert sha(receipt['admission']['path']) == receipt['admission']['sha256']
    assert admission['Threads'] == 1 and admission['P2_calls'] == 0
    assert admission['B1_parallel_workers'] == 1 and admission['B2_parallel_workers'] == 3
    records = {Path(row['path']).name: row for row in receipt['files']}
    assert {'incumbent.npz', 'CERTIFICATE.json', 'FRESH_AC.json', 'NATIVE_RUNTIME_LEDGER.json'} <= set(records)
    assert all(sha(row['path']) == row['sha256'] for row in records.values())
    ledger = read(request_path.parent / 'NATIVE_RUNTIME_LEDGER.json')
    assert ledger['calls'] == [] and ledger['P2_calls'] == 0
    assert ledger['inclusive_T0'] == inclusive_wall['worker_T0']
    assert ledger['wall_ceiling_seconds'] == ledger['Native_ceiling_seconds'] == 5400
    heartbeat = read(request_path.parent / 'HEARTBEAT.json')
    assert heartbeat['phase'] == 'TERMINAL' and heartbeat['status'] == 'PASS'
    assert heartbeat['identity'] == receipt['identity']
    assert read(request['progress'])['phase'] == 'TERMINAL'
    assert co.receipt_valid(root, manifest, request, receipt)
    if arm == 'B2':
        assert receipt['B2_AIDC_optimization_calls'] == 0
    with pytest.raises(PermissionError, match='NEVER_REEXECUTED'):
        worker.run(request_path)
    (Path(request['output']) / 'incumbent.npz').write_bytes(b'TAMPERED_POINT')
    assert not co.receipt_valid(root, manifest, request, receipt)


def test_failed_stage_preserves_error_ledger_and_partial_artifact_receipts_and_advances_once(campaign):
    root, manifest = campaign
    request_path, request = co.new_request(root, manifest, 'B1', co.DAYS[0])
    def failing_stage(request, budget, progress):
        fake_stage(request, budget, progress)
        raise ValueError('INPUT_FIXTURE_FAILURE')
    with fake_adapters(campaign, stage=failing_stage) as denied:
        assert worker.run(request_path) == 1
    receipt = read(request['result'])
    assert denied == [] and receipt['status'] == 'INPUT_FAILURE' and receipt['PASS'] is False
    assert read(request['error'])['error'] == receipt['error']
    assert read(Path(request['output']) / 'WORKER_FAILURE.json')['error'] == receipt['error']
    names = {Path(row['path']).name for row in receipt['files']}
    assert {'WORKER_FAILURE.json', 'incumbent.npz', 'NATIVE_RUNTIME_LEDGER.json'} <= names
    checkpoint = co.load_checkpoint(root, manifest)
    row = checkpoint['dates']['B1/' + co.DAYS[0]]
    row.update(status='RUNNING', attempts=1, request=str(request_path))
    co.finish_attempt(root, manifest, checkpoint, row, request, 1)
    assert row['status'] == 'INPUT_FAILURE' and row['attempts'] == 1
    assert checkpoint['dates']['B1/' + co.DAYS[1]]['status'] == 'PENDING'


def test_budget_stop_preserves_feasible_incumbent_and_scientific_summary(campaign):
    root, manifest = campaign
    request_path, request = co.new_request(root, manifest, 'B1', co.DAYS[0])
    with fake_adapters(campaign) as denied, \
            patch.object(worker.DateBudget, 'check', side_effect=BudgetStop('DATE_BUDGET_FIXTURE')):
        assert worker.run(request_path) == 1
    receipt = read(request['result'])
    assert denied == [] and receipt['status'] == 'TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
    assert receipt['PASS'] is False
    assert receipt['fields']['UB'] == 1 and receipt['fields']['independent_Global_LB'] == .998
    assert 'incumbent.npz' in {Path(row['path']).name for row in receipt['files']}
    assert 'NATIVE_RUNTIME_LEDGER.json' in {Path(row['path']).name for row in receipt['files']}
    assert read(request_path.parent / 'HEARTBEAT.json')['status'] == receipt['status']


def test_p2_and_b2_aidc_optimization_fail_closed_before_any_native_call(campaign):
    root, manifest = campaign
    request_path, request = co.new_request(root, manifest, 'B2', co.DAYS[0])
    def denied_stage(request, budget, progress):
        with pytest.raises(PermissionError, match='P1_ONLY'):
            execution.authorize(request['day'], 'P2')
        execution.authorize(request['day'], 'A1')
    with fake_adapters(campaign, stage=denied_stage) as denied:
        assert worker.run(request_path) == 1
    receipt = read(request['result'])
    assert denied == [] and receipt['PASS'] is False
    assert 'B2_AIDC_OPTIMIZATION_FORBIDDEN' in receipt['error']
    assert receipt['P2_calls'] == receipt['Native_calls'] == 0


def test_process_guard_requires_python_module_not_text_in_read_only_shell_command():
    own = worker.psutil.Process().pid
    harmless = SimpleNamespace(pid=own + 1, info=dict(name='pwsh.exe', cmdline=[
        'pwsh.exe', '-Command', 'Get-Content v42_may_campaign.worker']))
    current = SimpleNamespace(pid=own, info=dict(name='python.exe', cmdline=['python.exe', '-m', 'v42_may_campaign.worker']))
    with patch.object(worker.psutil, 'process_iter', return_value=[harmless, current]):
        worker.assert_no_other_native_worker()
    other = SimpleNamespace(pid=own + 2, info=dict(name='pythonw.exe', cmdline=['pythonw.exe', '-B', '-m', 'v42_may_campaign.worker', 'request.json']))
    with patch.object(worker.psutil, 'process_iter', return_value=[other]):
        with pytest.raises(LockBusy, match='OTHER_CAMPAIGN_WORKER_PID'):
            worker.assert_no_other_native_worker()


def dispatched_request(campaign, arm, day, slot=1):
    root, manifest = campaign
    path, request = co.new_request(root, manifest, arm, day)
    request['worker_slot'] = slot
    request['worker_command'] = co.default_worker_command(manifest, path)
    atomic(path, request)
    return path, request


def process_fixture(request_path, pid):
    request = read(request_path)
    return SimpleNamespace(pid=pid, info=dict(name='python.exe', cmdline=request['worker_command']))


def test_three_same_run_b2_workers_admitted_during_popen_to_actives_window(campaign):
    root, _ = campaign
    own = worker.psutil.Process().pid
    paths = [dispatched_request(campaign, 'B2', day, i + 1)[0]
             for i, day in enumerate(co.DAYS[:3])]
    request = read(paths[0])
    assert not (root / 'ACTIVES.json').exists()
    peers = [process_fixture(paths[i], own + i + 100) for i in (1, 2)]
    with patch.object(worker.psutil, 'process_iter', return_value=peers):
        actual = worker.assert_no_other_native_worker(request)
    assert [(r['worker_slot'], r['day']) for r in actual] == [(2, co.DAYS[1]), (3, co.DAYS[2])]


@pytest.mark.parametrize('other', ['duplicate_date', 'duplicate_slot', 'fourth_worker',
                                    'B1_overlap', 'other_run', 'manifest_drift',
                                    'bad_command', 'cross_date_output', 'P2', 'Threads'])
def test_parallel_b2_admission_rejects_unscoped_or_duplicate_peers(campaign, other):
    root, _ = campaign
    own = worker.psutil.Process().pid
    first_path, first = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    second_path, second = dispatched_request(campaign, 'B2', co.DAYS[1], 2)
    peers = [process_fixture(second_path, own + 100)]
    if other == 'duplicate_date':
        # A second PID using the exact same date's persisted dispatch.
        peers = [process_fixture(first_path, own + 100)]
    elif other == 'duplicate_slot':
        second['worker_slot'] = 1
    elif other == 'fourth_worker':
        third, _ = dispatched_request(campaign, 'B2', co.DAYS[2], 3)
        fourth, _ = dispatched_request(campaign, 'B2', co.DAYS[3], 2)
        peers += [process_fixture(third, own + 101), process_fixture(fourth, own + 102)]
    elif other == 'B1_overlap':
        b1, _ = dispatched_request(campaign, 'B1', co.DAYS[0], 1)
        peers = [process_fixture(b1, own + 100)]
    elif other == 'other_run':
        second['run_id'] = 'UNAPPROVED_OTHER_RUN'
    elif other == 'manifest_drift':
        second['manifest_SHA'] = '0' * 64
    elif other == 'bad_command':
        second['worker_command'] += ['--unapproved-option']
    elif other == 'cross_date_output':
        second['output'] = first['output']
    elif other == 'P2':
        second['P2_calls'] = 1
    elif other == 'Threads':
        second['Threads'] = 3
    atomic(second_path, second)
    with patch.object(worker.psutil, 'process_iter', return_value=peers):
        with pytest.raises(LockBusy):
            worker.assert_no_other_native_worker(first)


@pytest.mark.parametrize('module', ['v42_a_stage_canary.runner', 'v42_m1_anytime.runner',
                                   'v42_pr134_b1.worker', 'v42_may12_rescue.sweep'])
def test_external_historical_scientific_workers_rejected_in_parallel_scope(campaign, module):
    own = worker.psutil.Process().pid
    _, request = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    external = SimpleNamespace(pid=own + 100, info=dict(name='python.exe',
        cmdline=['python.exe', '-B', '-m', module, 'external-request.json']))
    with patch.object(worker.psutil, 'process_iter', return_value=[external]):
        with pytest.raises(LockBusy, match='OTHER_SCIENTIFIC_WORKER_PID'):
            worker.assert_no_other_native_worker(request)


def test_direct_script_historical_worker_is_rejected(campaign):
    own = worker.psutil.Process().pid
    _, request = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    external = SimpleNamespace(pid=own + 100, info=dict(name='python.exe',
        cmdline=['python.exe', str(ROOT / 'v42_m1_anytime/runner.py')]))
    with patch.object(worker.psutil, 'process_iter', return_value=[external]):
        with pytest.raises(LockBusy, match='OTHER_SCIENTIFIC_WORKER_PID'):
            worker.assert_no_other_native_worker(request)


def test_b1_remains_single_with_b1_or_b2_peer(campaign):
    own = worker.psutil.Process().pid
    _, request = dispatched_request(campaign, 'B1', co.DAYS[0], 1)
    paths = [dispatched_request(campaign, arm, co.DAYS[1], slot)[0]
             for arm, slot in [('B1', 1), ('B2', 2)]]
    for path in paths:
        with patch.object(worker.psutil, 'process_iter', return_value=[process_fixture(path, own + 100)]):
            with pytest.raises(LockBusy):
                worker.assert_no_other_native_worker(request)


def test_global_admission_mutex_is_released_while_independent_b2_slots_are_owned(campaign):
    root, _ = campaign
    _, first = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    _, second = dispatched_request(campaign, 'B2', co.DAYS[1], 2)
    _, third = dispatched_request(campaign, 'B2', co.DAYS[2], 3)
    _, fourth = dispatched_request(campaign, 'B2', co.DAYS[3], 1)
    with patch.object(worker, 'RUNTIME', root / 'locks'), \
            patch.object(worker, 'assert_no_other_native_worker', return_value=[]):
        with worker.native_worker_admission(first):
            # A brief mutex, rather than a lifetime global serialization gate.
            with exclusive_lock(root / 'locks/NATIVE_WORKER.lock'):
                pass
            with worker.native_worker_admission(second), worker.native_worker_admission(third):
                with pytest.raises(LockBusy, match='LIVE_OS_LOCK'), worker.native_worker_admission(fourth):
                    pytest.fail('A fourth global scientific slot cannot be acquired')
            with worker.native_worker_admission(second):
                pass  # OS slot ownership is released when that worker exits.
        with worker.native_worker_admission(fourth):
            pass


def test_date_lock_rejects_duplicate_even_if_claimed_slot_differs(campaign):
    root, _ = campaign
    _, request = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    duplicate = dict(request, worker_slot=2)
    with patch.object(worker, 'RUNTIME', root / 'locks'), \
            patch.object(worker, 'assert_no_other_native_worker', return_value=[]):
        with worker.native_worker_admission(request):
            with pytest.raises(LockBusy, match='WORKER.lock'), worker.native_worker_admission(duplicate):
                pytest.fail('A duplicated arm/date cannot enter another slot')


def test_b1_holds_all_global_slots_even_if_process_inventory_is_temporarily_empty(campaign):
    root, _ = campaign
    _, b1 = dispatched_request(campaign, 'B1', co.DAYS[0], 1)
    _, b2 = dispatched_request(campaign, 'B2', co.DAYS[0], 3)
    with patch.object(worker, 'RUNTIME', root / 'locks'), \
            patch.object(worker, 'assert_no_other_native_worker', return_value=[]):
        with worker.native_worker_admission(b1):
            with pytest.raises(LockBusy, match='SLOT_3.lock'), worker.native_worker_admission(b2):
                pytest.fail('B1 and B2 cannot overlap')


def test_worker_temp_ledger_and_artifact_paths_remain_separate_for_b2_dates(campaign):
    _, manifest = campaign
    requests = [dispatched_request(campaign, 'B2', day, i + 1)
                for i, day in enumerate(co.DAYS[:3])]
    observed = []
    def check_temp(request, budget, progress):
        expected = str(Path(request['result']).parent / 'tmp')
        observed.append((os.environ['TEMP'], os.environ['TMP'], tempfile.gettempdir(),
                         str(budget.path)))
        assert observed[-1][:3] == (expected,) * 3
        return fake_stage(request, budget, progress)
    with fake_adapters(campaign, stage=check_temp) as denied:
        for path, request in requests:
            assert worker.run(path) == 0
    assert denied == []
    assert len({row[0] for row in observed}) == 3
    assert len({row[3] for row in observed}) == 3
    for path, request in requests:
        receipt = read(request['result'])
        assert receipt['Native_calls'] == receipt['Native_Runtime'] == 0
        assert all(Path(row['path']).resolve().is_relative_to(path.parent.resolve())
                   for row in receipt['files'])


def test_duplicate_worker_cannot_write_heartbeat_error_or_result_of_live_attempt(campaign):
    path, request = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    atomic(request['progress'], dict(fixture_only=True, phase='LIVE_ORIGINAL_WORKER'))
    before = sha(request['progress'])
    with exclusive_lock(path.parent / 'WORKER.lock'):
        with pytest.raises(LockBusy, match='WORKER.lock'):
            worker.run(path)
    assert sha(request['progress']) == before
    assert not Path(request['error']).exists()
    assert not Path(request['result']).exists()
    assert not (path.parent / 'HEARTBEAT.json').exists()


@pytest.mark.parametrize('name', ['progress', 'error', 'output', 'result'])
def test_worker_rejects_cross_date_write_path_before_artifact_mutation(campaign, name):
    first, request = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    second, other = dispatched_request(campaign, 'B2', co.DAYS[1], 2)
    request[name] = other[name]
    atomic(first, request)
    with pytest.raises(PermissionError, match='OUTPUT_ISOLATION'):
        worker.run(first)
    assert not Path(request['result']).exists()
    assert not Path(other['result']).exists()
    assert not Path(request['error']).exists()
    assert not Path(other['error']).exists()


def test_native_entry_rechecks_external_workers_after_initial_admission(campaign):
    _, request = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    own = worker.psutil.Process().pid
    external = SimpleNamespace(pid=own + 100, info=dict(name='python.exe',
        cmdline=['python.exe', '-m', 'v42_pr134_b1.worker', 'historical-request.json']))
    model = SimpleNamespace(Params=SimpleNamespace(Threads=1))
    token = execution._active.set(dict(request=request, worker_slot=1, fixture_only=True))
    try:
        with patch.object(worker.psutil, 'process_iter', return_value=[]):
            with execution.native_scope(model, 'P1', 'M'):
                execution.guard(model)
        with patch.object(worker.psutil, 'process_iter', return_value=[external]):
            with execution.native_scope(model, 'P1', 'M'):
                with pytest.raises(LockBusy, match='OTHER_SCIENTIFIC_WORKER_PID'):
                    execution.guard(model)
    finally:
        execution._active.reset(token)


def test_admission_mutex_wait_includes_dispatch_wall_and_stops_before_stage(campaign):
    root, _ = campaign
    path, request = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    with patch.object(worker, 'RUNTIME', root / 'locks'), \
            patch.object(worker, 'assert_no_other_native_worker', return_value=[]), \
            exclusive_lock(root / 'locks/NATIVE_WORKER.lock'):
        with pytest.raises(BudgetStop, match='ADMISSION'), worker.native_worker_admission(
                request, started=time.perf_counter() - 5401):
            pytest.fail('Admission synchronization cannot extend a date wall ceiling')
    assert not (path.parent / 'NATIVE_WORKER_ADMISSION.json').exists()
    assert not (path.parent / 'NATIVE_RUNTIME_LEDGER.json').exists()


def test_admission_mutex_wait_rechecks_external_worker_and_releases_own_handles(campaign):
    root, _ = campaign
    path, request = dispatched_request(campaign, 'B2', co.DAYS[0], 1)
    checks = [[], [], LockBusy('OTHER_SCIENTIFIC_WORKER_PID:FAKE_NATIVE_ZERO')]
    with patch.object(worker, 'RUNTIME', root / 'locks'), \
            patch.object(worker, 'assert_no_other_native_worker', side_effect=checks), \
            exclusive_lock(root / 'locks/NATIVE_WORKER.lock'):
        with pytest.raises(LockBusy, match='OTHER_SCIENTIFIC_WORKER_PID'), \
                worker.native_worker_admission(request):
            pytest.fail('An external worker appearing while waiting must deny admission')
    assert not (path.parent / 'NATIVE_WORKER_ADMISSION.json').exists()
    with exclusive_lock(root / 'locks/NATIVE_WORKER.lock'):
        pass
    with exclusive_lock(path.parent / 'WORKER.lock'):
        pass
