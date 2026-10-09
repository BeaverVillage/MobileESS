"""Recovery cannot invent budget, weaken validation, or duplicate a live day."""
import json
from pathlib import Path

import pytest

from v42_autonomous import recovery as r


def packet(tmp_path, monkeypatch, *, runtime=10.):
    source = tmp_path / 'repair.py'
    source.write_text('original_domain_preserved = True\n')
    validation = dict(PASS=True, repair_source_SHA='b' * 64,
                      repair_commit_SHA='c' * 40, source_files=[r.record(source)],
                      **{name: True for name in r.REQUIRED_VALIDATION})
    proof = tmp_path / 'validation.json'
    r.atomic(proof, validation)
    failure = dict(date='2025-05-08', arm='B2', failed_stage='M',
                   failure_class='IMPLEMENTATION_FAILURE',
                   original_attempt_id='old', original_source_SHA='a' * 64,
                   original_native_runtime=runtime)
    original = tmp_path / 'original'
    if isinstance(runtime, (int, float)) and not isinstance(runtime, bool) and runtime == runtime:
        r.atomic(original / 'RESULT.json', dict(PASS=False, Native_Runtime=runtime))
        r.atomic(original / 'ledger.json', dict(measured_Native_Runtime=runtime, inflight=None, calls=[]))
        failure.update(original_result_receipt=r.record(original / 'RESULT.json'),
                       original_ledger_receipt=r.record(original / 'ledger.json'))
    folder = tmp_path / 'dates/B2/2025-05-08/attempts/new'
    request = dict(arm='B2', day='2025-05-08', attempt_id='new', worker_slot=1,
                   result=str(folder / 'RESULT.json'), implementation_SHA='b' * 64)
    r.atomic(folder / 'request.json', request)
    repair = dict(repair_commit_SHA='c' * 40, repair_source_SHA='b' * 64,
                  repair_reason='Preserve runtime before optional diagnostics',
                  retry_priority=100, validation_receipt=r.record(proof),
                  repair_code_root=str(tmp_path),
                  retry_request_receipt=r.record(folder / 'request.json'))
    # The scientific checkout admission belongs to B2/B3 regression suites;
    # these focused tests exercise queue contracts without a Native optimize.
    monkeypatch.setattr(r, '_verify_dispatch', lambda row, request: None)
    return failure, repair


def test_exclusive_lease_blocks_second_owner_and_retains_release(tmp_path):
    with r.repair_lease(tmp_path, token='one'):
        assert r.assert_lease(tmp_path, 'one')['automatic_time_expiry'] is False
        with pytest.raises(r.LeaseBusy):
            with r.repair_lease(tmp_path, token='two'):
                pass
        with pytest.raises(PermissionError, match='LIVE_REPAIR_LEASE_REQUIRED'):
            r.assert_lease(tmp_path, 'wrong')
    assert r.read(tmp_path / 'repair_leases/one.json')['state'] == 'RELEASED'
    with pytest.raises(PermissionError):
        r.assert_lease(tmp_path, 'one')


def test_stale_receipt_without_actual_lock_is_rejected(tmp_path):
    r.atomic(tmp_path / 'REPAIR_LEASE.json',
             dict(token='fake', state='ACTIVE', guardian=r.identity()))
    with pytest.raises(PermissionError, match='WITHOUT_OS_LOCK'):
        r.assert_lease(tmp_path, 'fake')


@pytest.mark.parametrize('runtime', [None, 'UNKNOWN', float('nan'), -1., True])
def test_unmeasured_runtime_never_creates_retry(tmp_path, monkeypatch, runtime):
    failure, repair = packet(tmp_path, monkeypatch, runtime=runtime)
    with r.repair_lease(tmp_path, token='test'):
        with pytest.raises(PermissionError, match='UNKNOWN_NATIVE_RUNTIME'):
            r.enqueue(tmp_path, failure, repair, lease_token='test')
    assert not (tmp_path / 'RECOVERY_QUEUE.json').exists()


def test_exhaustion_and_conservative_unknown_are_terminal(tmp_path, monkeypatch):
    failure, repair = packet(tmp_path, monkeypatch, runtime=5400.)
    with r.repair_lease(tmp_path, token='test'):
        with pytest.raises(PermissionError, match='EXHAUSTED_NATIVE_BUDGET'):
            r.enqueue(tmp_path, failure, repair, lease_token='test')
        failure.update(original_native_runtime=3900., budget_basis='CONSERVATIVE_LOST_CALL_WINDOW')
        with pytest.raises(PermissionError, match='UNKNOWN_NATIVE_RUNTIME'):
            r.enqueue(tmp_path, failure, repair, lease_token='test')


def test_new_source_and_original_validation_required(tmp_path, monkeypatch):
    failure, repair = packet(tmp_path, monkeypatch)
    with r.repair_lease(tmp_path, token='test'):
        repair['repair_source_SHA'] = failure['original_source_SHA']
        with pytest.raises(PermissionError, match='NEW_REPAIR_SOURCE'):
            r.enqueue(tmp_path, failure, repair, lease_token='test')
        repair['repair_source_SHA'] = 'b' * 64
        proof = Path(repair['validation_receipt']['path'])
        validation = r.read(proof)
        validation['original_physical_integer_PASS'] = False
        r.atomic(proof, validation)
        repair['validation_receipt'] = r.record(proof)
        with pytest.raises(PermissionError, match='SCIENTIFIC_VALIDATION'):
            r.enqueue(tmp_path, failure, repair, lease_token='test')


def test_queue_is_idempotent_and_defers_active_date(tmp_path, monkeypatch):
    failure, repair = packet(tmp_path, monkeypatch)
    with r.repair_lease(tmp_path, token='test'):
        first = r.enqueue(tmp_path, failure, repair, lease_token='test')
        second = r.enqueue(tmp_path, failure, repair, lease_token='test')
    assert first['queue_id'] == second['queue_id']
    assert first['remaining_native_seconds'] == 5390.
    assert len(r.queue(tmp_path)['entries']) == 1
    assert r.ready(tmp_path, 'B2', ['2025-05-08']) == []
    assert r.ready(tmp_path, 'B2')[0]['date'] == '2025-05-08'
    r.atomic(tmp_path / 'SUPERVISOR_STATE.json',
             dict(workers={'B2/2025-05-08': dict(arm='B2', day='2025-05-08', worker_slot=2)}))
    monkeypatch.setattr(r.subprocess, 'Popen', lambda *a, **k: pytest.fail('DUPLICATE_DAY_LAUNCH'))
    assert r.dispatch_ready(tmp_path, 'B2', 1, {}) is None


def test_launch_intent_is_never_reexecuted_after_unknown_exit(tmp_path, monkeypatch):
    failure, repair = packet(tmp_path, monkeypatch)
    with r.repair_lease(tmp_path, token='test'):
        r.enqueue(tmp_path, failure, repair, lease_token='test')
    doc = r.queue(tmp_path)
    doc['entries'][0]['verification_status'] = 'DISPATCH_INTENT'
    r.atomic(tmp_path / 'RECOVERY_QUEUE.json', doc)
    monkeypatch.setattr(r, '_request_workers', lambda path: [])
    monkeypatch.setattr(r.subprocess, 'Popen', lambda *a, **k: pytest.fail('UNKNOWN_RELAUNCH'))
    assert r.dispatch_ready(tmp_path, 'B2', 1, {}) is None
    row = r.queue(tmp_path)['entries'][0]
    assert row['verification_status'] == 'QUARANTINE_DISPATCH_INTERRUPTED'
    assert row['Native_Runtime'] == 'UNKNOWN'


def test_recovery_progress_requires_actual_admission_and_receipts(tmp_path, monkeypatch):
    failure, repair = packet(tmp_path, monkeypatch)
    with r.repair_lease(tmp_path, token='test'):
        row = r.enqueue(tmp_path, failure, repair, lease_token='test')
    with pytest.raises(PermissionError, match='NATIVE_PROGRESS_EVIDENCE'):
        r.mark_verified(tmp_path, row['queue_id'], {'START_REQUESTED': True})
    entered = r.mark_dispatched(tmp_path, row['queue_id'], 'new', r.identity(), source_SHA='b' * 64)
    assert entered['verification_status'] == 'WORKER_ENTERED'
    ledger = tmp_path / 'measured_ledger.json'
    r.atomic(ledger, dict(Native_Runtime=1., entered_native=True))
    proof = dict(source_admission_PASS=True, model_generation_PASS=True,
                 Native_entered=True, heartbeat_progress_PASS=True,
                 ledger_progress_PASS=True, receipts=[r.record(ledger)])
    verified = r.mark_verified(tmp_path, row['queue_id'], proof)
    assert verified['verification_status'] == 'NATIVE_PROGRESS_VERIFIED'


def test_repair_source_files_are_checked_again_before_dispatch(tmp_path, monkeypatch):
    failure, repair = packet(tmp_path, monkeypatch)
    with r.repair_lease(tmp_path, token='test'):
        row = r.enqueue(tmp_path, failure, repair, lease_token='test')
    Path(row['source_files'][0]['path']).write_text('changed after validation\n')
    # Undo only this helper mock so real seal verification runs before any Popen.
    monkeypatch.undo()
    request = r.read(row['retry_request_receipt']['path'])
    with pytest.raises(PermissionError, match='SEALED_EVIDENCE_DRIFT'):
        r._verify_dispatch(row, request)
