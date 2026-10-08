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
from v42_may_campaign.common import ROOT, atomic, read, sha, LockBusy
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
        folder = root / 'inputs' / arm / co.DAYS[0]
        folder.mkdir(parents=True)
        atomic(folder / 'INPUT_IDENTITY.json', dict(arm=arm, day=co.DAYS[0], fixture_only=True))
        atomic(folder / 'NATIVE_INPUT.json', dict(arm=arm, day=co.DAYS[0], fixture_only=True))
        manifest['input_folders'][arm + '/' + co.DAYS[0]] = str(folder)
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
            patch.object(worker, 'assert_no_other_native_worker'), native_zero() as denied:
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
