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
    doc['entries'][0]['worker_slot'] = 1
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
    with pytest.raises(PermissionError, match='SOURCE_FILES_DRIFT'):
        r._verify_dispatch(row, request)


def test_retry_intent_is_persisted_before_launch_and_live_intent_adopted(tmp_path, monkeypatch):
    failure, repair = packet(tmp_path, monkeypatch)
    repair['worker_module'] = 'v42_autonomous_b2.worker'
    with r.repair_lease(tmp_path, token='test'):
        row = r.enqueue(tmp_path, failure, repair, lease_token='test')
    worker = r.identity()
    launched = []
    def popen(command, **kwargs):
        current = r.queue(tmp_path)['entries'][0]
        assert current['verification_status'] == 'DISPATCH_INTENT'
        launched.append(command)
        return type('Child', (), {'pid': worker['PID']})()
    monkeypatch.setattr(r, '_request_workers', lambda path: [])
    monkeypatch.setattr(r.subprocess, 'Popen', popen)
    retry = r.dispatch_ready(tmp_path, 'B2', 1, {})
    assert launched[0][-2] == 'v42_autonomous_b2.worker'
    assert retry['day'] == '2025-05-08' and retry['recovery_queue_id'] == row['queue_id']
    assert r.dispatch_ready(tmp_path, 'B2', 1, {}) is None
    doc = r.queue(tmp_path)
    doc['entries'][0]['verification_status'] = 'DISPATCH_INTENT'
    r.atomic(tmp_path / 'RECOVERY_QUEUE.json', doc)
    monkeypatch.setattr(r, '_request_workers', lambda path: [worker])
    adopted = r.dispatch_ready(tmp_path, 'B2', 1, {})
    assert adopted['PID'] == worker['PID'] and len(launched) == 1


def test_presealed_slot_alternatives_use_next_available_worker(tmp_path, monkeypatch):
    failure, repair = packet(tmp_path, monkeypatch)
    alternative = tmp_path / 'dates/B2/2025-05-08/attempts/new_slot2/request.json'
    request = r.read(repair['retry_request_receipt']['path'])
    request.update(attempt_id='new_slot2', worker_slot=2, result=str(alternative.parent / 'RESULT.json'))
    r.atomic(alternative, request)
    repair['retry_request_receipts_by_slot'] = {'2': r.record(alternative)}
    with r.repair_lease(tmp_path, token='test'):
        r.enqueue(tmp_path, failure, repair, lease_token='test')
    monkeypatch.setattr(r, '_request_workers', lambda path: [])
    monkeypatch.setattr(r.subprocess, 'Popen', lambda *a, **k: type('Child', (), {'pid': r.identity()['PID']})())
    retry = r.dispatch_ready(tmp_path, 'B2', 2, {})
    assert retry['worker_slot'] == 2 and retry['request'] == str(alternative)
    assert r.queue(tmp_path)['entries'][0]['retry_attempt_id'] == 'new_slot2'


def terminal_packet(tmp_path, row, *, unknown=False):
    request=r.read(row['retry_request_receipt']['path'])
    result=Path(request['result'])
    ledger=result.parent/'NATIVE_RUNTIME_LEDGER.json'
    r.atomic(ledger,dict(measured_Native_Runtime=11.,prior_attempt={'Native_Runtime':10.},
        inflight={'status':'IN_FLIGHT'} if unknown else None,
        calls=[dict(entered_native=True,Native_Runtime=1.,runtime_unavailable=False)]))
    r.atomic(result,dict(identity={'day':row['date'],'arm':row['arm'],'attempt_id':request['attempt_id']},
        source_SHA=row['repair_source_SHA'],PASS=True,status='PASS',scientific_PASS=True,Native_Runtime=11.))
    return result,ledger


def next_repair(tmp_path,repair):
    newer=dict(repair,repair_source_SHA='d'*64,repair_commit_SHA='e'*40)
    proof=r.read(repair['validation_receipt']['path'])
    proof.update(repair_source_SHA=newer['repair_source_SHA'],repair_commit_SHA=newer['repair_commit_SHA'])
    path=tmp_path/'new_validation.json';r.atomic(path,proof)
    newer['validation_receipt']=r.record(path)
    request=r.read(repair['retry_request_receipt']['path'])
    folder=tmp_path/'dates/B2/2025-05-08/attempts/newer'
    request.update(attempt_id='newer',implementation_SHA='d'*64,result=str(folder/'RESULT.json'))
    r.atomic(folder/'request.json',request)
    newer['retry_request_receipt']=r.record(folder/'request.json')
    return newer


def current_pass_with_ready(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        original=r.enqueue(tmp_path,failure,repair,lease_token='test')
        result,ledger=terminal_packet(tmp_path,original)
        r.mark_finished(tmp_path,original['queue_id'],result)
        ready=r.enqueue(tmp_path,failure,next_repair(tmp_path,repair),lease_token='test')
    key='B2/2025-05-08'
    cp=dict(workers={},dates={key:dict(status='PASS',current_attempt='new',
        request=original['retry_request_receipt']['path'],result=str(result),
        result_SHA=r.record(result)['sha256'],Native_Runtime=11.,source_SHA='b'*64,
        first_attempt_terminal={'status':'FAIL'},attempt_history=[{'status':'FAIL'}])})
    return cp,ready,result,ledger


def test_current_verified_pass_retires_only_unstarted_prepared_repair(tmp_path,monkeypatch):
    from copy import deepcopy
    from v42_autonomous import supervisor
    cp,ready,_,_=current_pass_with_ready(tmp_path,monkeypatch);before=deepcopy(cp)
    supervisor.refresh_retries(tmp_path,cp)
    assert cp==before
    retired=r.queue(tmp_path)['entries'][-1]
    assert retired['verification_status']=='RETIRED_CURRENT_VERIFIED_PASS'
    assert retired['retry_request_receipt']==ready['retry_request_receipt']
    assert retired['current_PASS_evidence']['attempt_id']=='new'
    assert r.queue(tmp_path)['entries'][0]['verification_status']=='RECOVERY_PASS'


@pytest.mark.parametrize('tamper',['result','ledger','request','source','identity'])
def test_unverified_or_tampered_pass_never_cancels_prepared_repair(tmp_path,monkeypatch,tamper):
    cp,ready,result,ledger=current_pass_with_ready(tmp_path,monkeypatch)
    row=cp['dates']['B2/2025-05-08']
    if tamper=='result':row['result_SHA']='0'*64
    elif tamper=='ledger':r.atomic(ledger,dict(measured_Native_Runtime=11.,inflight={'status':'IN_FLIGHT'}))
    elif tamper=='request':r.atomic(row['request'],dict(arm='B2',day='2025-05-08',attempt_id='wrong'))
    elif tamper=='source':row['source_SHA']='0'*64
    else:row['current_attempt']='wrong'
    r.retire_satisfied_ready(tmp_path,cp)
    assert r.queue(tmp_path)['entries'][-1]['verification_status']=='READY_VERIFIED_REPAIR'


@pytest.mark.parametrize('kind',['active','intent','untracked_worker'])
def test_active_or_intended_repair_is_never_retired(tmp_path,monkeypatch,kind):
    cp,ready,_,_=current_pass_with_ready(tmp_path,monkeypatch)
    if kind=='active':cp['workers']['B2/2025-05-08']={'arm':'B2','day':'2025-05-08'}
    elif kind=='untracked_worker':monkeypatch.setattr(r,'_request_workers',lambda path:[{'PID':123}])
    else:
        doc=r.queue(tmp_path);doc['entries'][-1]['verification_status']='DISPATCH_INTENT'
        r.atomic(tmp_path/'RECOVERY_QUEUE.json',doc)
    r.retire_satisfied_ready(tmp_path,cp)
    assert r.queue(tmp_path)['entries'][-1]['verification_status']==('DISPATCH_INTENT' if kind=='intent' else 'READY_VERIFIED_REPAIR')


def test_real_failure_still_dispatches_next_priority_repair(tmp_path,monkeypatch):
    from types import SimpleNamespace
    cp,ready,_,_=current_pass_with_ready(tmp_path,monkeypatch)
    cp['dates']['B2/2025-05-08']['status']='FAIL'
    r.atomic(tmp_path/'SUPERVISOR_STATE.json',cp)
    monkeypatch.setattr(r.subprocess,'Popen',lambda *args,**kwargs:SimpleNamespace(pid=123))
    monkeypatch.setattr(r,'identity',lambda pid=None:dict(PID=pid,created=1.,command=[]))
    worker=r.dispatch_ready(tmp_path,'B2',1,{})
    assert worker['recovery_queue_id']==ready['queue_id']
    assert r.queue(tmp_path)['entries'][-1]['verification_status']=='WORKER_ENTERED'


def test_ready_supersession_is_verified_atomic_idempotent_and_preserves_history(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        newer=next_repair(tmp_path,repair)
        new=r.enqueue(tmp_path,failure,newer,lease_token='test',supersede_queue_id=old['queue_id'])
        assert r.enqueue(tmp_path,failure,newer,lease_token='test',supersede_queue_id=old['queue_id'])==new
    rows=r.queue(tmp_path)['entries']
    assert rows[0]['verification_status']=='SUPERSEDED_UNSTARTED_READY'
    assert rows[0]['retry_request_receipt']==old['retry_request_receipt']
    assert rows[0]['superseded_by_queue_id']==new['queue_id']
    assert rows[1]['supersedes_queue_id']==old['queue_id']
    assert rows[1]['verification_status']=='READY_VERIFIED_REPAIR'


@pytest.mark.parametrize('blocker',['active','intent','invalid_new_validation'])
def test_supersession_never_changes_active_intended_or_unverified_queue(tmp_path,monkeypatch,blocker):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        newer=next_repair(tmp_path,repair)
        if blocker=='active':r.atomic(tmp_path/'SUPERVISOR_STATE.json',dict(workers={'x':dict(arm='B2',day='2025-05-08')}))
        elif blocker=='intent':
            doc=r.queue(tmp_path);doc['entries'][0]['verification_status']='DISPATCH_INTENT'
            r.atomic(tmp_path/'RECOVERY_QUEUE.json',doc)
        else:
            proof=r.read(newer['validation_receipt']['path']);proof['PASS']=False
            r.atomic(newer['validation_receipt']['path'],proof)
            newer['validation_receipt']=r.record(newer['validation_receipt']['path'])
        before=r.queue(tmp_path)
        with pytest.raises(PermissionError):
            r.enqueue(tmp_path,failure,newer,lease_token='test',supersede_queue_id=old['queue_id'])
        assert r.queue(tmp_path)==before


def other_running_attempt(tmp_path,target,monkeypatch,*,day='2025-05-08',source='a'*64,attempt='running_other'):
    """Declared live OS stand-in; no worker process or Native model launched."""
    folder=tmp_path/'dates/B2'/day/'attempts'/attempt
    request=dict(arm='B2',day=day,attempt_id=attempt,worker_slot=1,
        result=str(folder/'RESULT.json'),implementation_SHA=source)
    r.atomic(folder/'request.json',request)
    worker=dict(r.identity(),arm='B2',day=day,worker_slot=1,request=str(folder/'request.json'),
        source_SHA=source,recovery_queue_id='different_active_queue')
    worker['command']=['python','-m',target['worker_module'],worker['request']]
    cp=dict(workers={'B2/'+day:worker},dates={'B2/'+day:dict(status='RUNNING',
        current_attempt=attempt,request=worker['request'],source_SHA=source,
        active_recovery_queue_id='different_active_queue',retry_queue_ids=['different_active_queue'])})
    r.atomic(tmp_path/'SUPERVISOR_STATE.json',cp)
    # Match only this explicit OS stand-in. Real lease guardian checks remain.
    original_alive=r.alive
    monkeypatch.setattr(r,'alive',lambda owner:True if owner==worker else original_alive(owner))
    return cp,worker,folder


@pytest.mark.parametrize('source',['a'*64,'b'*64])
def test_unstarted_ready_supersession_preserves_proved_other_same_day_attempt(tmp_path,monkeypatch,source):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        cp,worker,folder=other_running_attempt(tmp_path,old,monkeypatch,source=source)
        r.atomic(folder/'NATIVE_RUNTIME_LEDGER.json',dict(inflight={'status':'IN_FLIGHT'},calls=[]))
        cp_path=tmp_path/'SUPERVISOR_STATE.json';before=(cp_path.read_bytes(),r.record(folder/'request.json'),r.record(folder/'NATIVE_RUNTIME_LEDGER.json'))
        newer=next_repair(tmp_path,repair);authorize_zero(tmp_path,newer)
        new=r.enqueue(tmp_path,failure,newer,lease_token='test',supersede_queue_id=old['queue_id'])
        assert r.enqueue(tmp_path,failure,newer,lease_token='test',supersede_queue_id=old['queue_id'])==new
        assert r.assert_lease(tmp_path,'test')['state']=='ACTIVE'
        assert (cp_path.read_bytes(),r.record(folder/'request.json'),r.record(folder/'NATIVE_RUNTIME_LEDGER.json'))==before
    assert new['initial_native_runtime']==0 and new['remaining_native_seconds']==5400
    assert r.queue(tmp_path)['entries'][0]['verification_status']=='SUPERSEDED_UNSTARTED_READY'
    assert r.queue(tmp_path)['entries'][1]['verification_status']=='READY_VERIFIED_REPAIR'


def test_other_day_same_attempt_name_and_source_does_not_block_target_supersession(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        other_running_attempt(tmp_path,old,monkeypatch,day='2025-05-09',source='b'*64,attempt='new')
        cp_path=tmp_path/'SUPERVISOR_STATE.json';before=cp_path.read_bytes()
        new=r.enqueue(tmp_path,failure,next_repair(tmp_path,repair),lease_token='test',supersede_queue_id=old['queue_id'])
        assert cp_path.read_bytes()==before and new['supersedes_queue_id']==old['queue_id']


@pytest.mark.parametrize('reference',['queue_id','recovery_queue_id','active_recovery_queue_id','request'])
def test_other_day_explicit_target_cp_ownership_blocks_supersession(tmp_path,monkeypatch,reference):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        other=dict(status='RETRY_PENDING',current_attempt='new',retry_queue_ids=[old['queue_id']])
        other[reference]=old['retry_request_receipt']['path'] if reference=='request' else old['queue_id']
        r.atomic(tmp_path/'SUPERVISOR_STATE.json',dict(workers={},dates={'B2/2025-05-09':other}))
        before=((tmp_path/'SUPERVISOR_STATE.json').read_bytes(),(tmp_path/'RECOVERY_QUEUE.json').read_bytes())
        with pytest.raises(PermissionError,match='ONLY_UNSTARTED_READY'):
            r.enqueue(tmp_path,failure,next_repair(tmp_path,repair),lease_token='test',supersede_queue_id=old['queue_id'])
        assert ((tmp_path/'SUPERVISOR_STATE.json').read_bytes(),(tmp_path/'RECOVERY_QUEUE.json').read_bytes())==before


def test_other_day_inactive_pending_metadata_and_generic_attempt_name_are_not_target_ownership(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        cp=dict(workers={},dates={'B2/2025-05-09':dict(status='RETRY_PENDING',
            current_attempt='new',retry_queue_ids=[old['queue_id']])})
        r.atomic(tmp_path/'SUPERVISOR_STATE.json',cp);before=(tmp_path/'SUPERVISOR_STATE.json').read_bytes()
        new=r.enqueue(tmp_path,failure,next_repair(tmp_path,repair),lease_token='test',supersede_queue_id=old['queue_id'])
        assert new['supersedes_queue_id']==old['queue_id'] and (tmp_path/'SUPERVISOR_STATE.json').read_bytes()==before


@pytest.mark.parametrize('blocker',['target_queue','target_request','target_attempt','missing_identity',
    'dead_identity','command_mismatch','source_mismatch','current_attempt_mismatch','launch_intent','missing_current_date'])
def test_target_or_ambiguous_supervisor_ownership_blocks_supersession_without_cp_or_queue_edit(tmp_path,monkeypatch,blocker):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        cp,worker,_=other_running_attempt(tmp_path,old,monkeypatch)
        key='B2/2025-05-08'
        if blocker=='target_queue':cp['dates'][key]['active_recovery_queue_id']=old['queue_id']
        elif blocker=='target_request':cp['dates'][key]['request']=old['retry_request_receipt']['path']
        elif blocker=='target_attempt':cp['dates'][key]['current_attempt']='new'
        elif blocker=='missing_identity':cp['workers'][key].pop('PID')
        elif blocker=='dead_identity':monkeypatch.setattr(r,'alive',lambda owner:False if owner==worker else True)
        elif blocker=='command_mismatch':cp['workers'][key]['command'][-1]='D:/other_request.json'
        elif blocker=='source_mismatch':cp['workers'][key]['source_SHA']='f'*64
        elif blocker=='current_attempt_mismatch':cp['dates'][key]['current_attempt']='unproved_other'
        elif blocker=='launch_intent':cp['workers'][key]['launch_intent']=True
        else:cp['dates'].clear()
        r.atomic(tmp_path/'SUPERVISOR_STATE.json',cp)
        cp_path=tmp_path/'SUPERVISOR_STATE.json';before=(cp_path.read_bytes(),(tmp_path/'RECOVERY_QUEUE.json').read_bytes())
        with pytest.raises(PermissionError,match='ONLY_UNSTARTED_READY'):
            r.enqueue(tmp_path,failure,next_repair(tmp_path,repair),lease_token='test',supersede_queue_id=old['queue_id'])
        assert (cp_path.read_bytes(),(tmp_path/'RECOVERY_QUEUE.json').read_bytes())==before


@pytest.mark.parametrize('marker',['worker','worker_slot','launch_intent','popen_returned','dispatch_intent_UTC'])
def test_hidden_target_launch_metadata_is_not_discarded_by_supersession(tmp_path,monkeypatch,marker):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        doc=r.queue(tmp_path);doc['entries'][0][marker]={'PID':123} if marker=='worker' else 1
        r.atomic(tmp_path/'RECOVERY_QUEUE.json',doc);before=(tmp_path/'RECOVERY_QUEUE.json').read_bytes()
        with pytest.raises(PermissionError,match='ONLY_UNSTARTED_READY'):
            r.enqueue(tmp_path,failure,next_repair(tmp_path,repair),lease_token='test',supersede_queue_id=old['queue_id'])
        assert (tmp_path/'RECOVERY_QUEUE.json').read_bytes()==before


@pytest.mark.parametrize('marker',['NATIVE_RUNTIME_LEDGER.json','progress.json','error.json','output'])
def test_target_execution_artifact_without_final_result_is_not_superseded(tmp_path,monkeypatch,marker):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        path=Path(old['retry_request_receipt']['path']).parent/marker
        if marker=='output':path.mkdir()
        else:r.atomic(path,dict(inflight={'status':'IN_FLIGHT'}))
        before=(tmp_path/'RECOVERY_QUEUE.json').read_bytes()
        with pytest.raises(PermissionError,match='ONLY_UNSTARTED_READY'):
            r.enqueue(tmp_path,failure,next_repair(tmp_path,repair),lease_token='test',supersede_queue_id=old['queue_id'])
        assert (tmp_path/'RECOVERY_QUEUE.json').read_bytes()==before


def test_alternate_request_os_worker_detection_blocks_target_supersession(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    alternate=tmp_path/'dates/B2/2025-05-08/attempts/target_slot2/request.json'
    request=r.read(repair['retry_request_receipt']['path'])
    request.update(attempt_id='target_slot2',worker_slot=2,result=str(alternate.parent/'RESULT.json'))
    r.atomic(alternate,request);repair['retry_request_receipts_by_slot']={'2':r.record(alternate)}
    # Exercise the actual _request_workers implementation with a declared
    # process-table stand-in; it has the real test process PID/create time.
    class Process:
        pid=r.identity()['PID'];info={'name':'python.exe'}
        def cmdline(self):return ['python','-m','v42_autonomous_b2.worker',str(alternate)]
    monkeypatch.setattr(r.psutil,'process_iter',lambda fields:[Process()])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test');before=(tmp_path/'RECOVERY_QUEUE.json').read_bytes()
        with pytest.raises(PermissionError,match='ONLY_UNSTARTED_READY'):
            r.enqueue(tmp_path,failure,next_repair(tmp_path,repair),lease_token='test',supersede_queue_id=old['queue_id'])
        assert (tmp_path/'RECOVERY_QUEUE.json').read_bytes()==before


def test_supersession_still_requires_exclusive_queue_lock_and_live_lease(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        other_running_attempt(tmp_path,old,monkeypatch)
        before=(tmp_path/'RECOVERY_QUEUE.json').read_bytes();newer=next_repair(tmp_path,repair)
        with r.os_lock(tmp_path/'RECOVERY_QUEUE.lock'):
            with pytest.raises(r.LeaseBusy):
                r.enqueue(tmp_path,failure,newer,lease_token='test',supersede_queue_id=old['queue_id'])
        assert (tmp_path/'RECOVERY_QUEUE.json').read_bytes()==before
        with pytest.raises(PermissionError,match='LIVE_REPAIR_LEASE'):
            r.enqueue(tmp_path,failure,newer,lease_token='wrong',supersede_queue_id=old['queue_id'])


def test_inactive_retry_pending_list_is_not_target_dispatch_ownership(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    with r.repair_lease(tmp_path,token='test'):
        old=r.enqueue(tmp_path,failure,repair,lease_token='test')
        cp=dict(workers={},dates={'B2/2025-05-08':dict(status='RETRY_PENDING',
            current_attempt='historical_failed',request=str(tmp_path/'original/request.json'),
            active_recovery_queue_id='historical_failed_queue',retry_queue_ids=[old['queue_id']])})
        r.atomic(tmp_path/'SUPERVISOR_STATE.json',cp)
        before=(tmp_path/'SUPERVISOR_STATE.json').read_bytes()
        new=r.enqueue(tmp_path,failure,next_repair(tmp_path,repair),lease_token='test',supersede_queue_id=old['queue_id'])
        assert new['supersedes_queue_id']==old['queue_id']
        assert (tmp_path/'SUPERVISOR_STATE.json').read_bytes()==before


def test_nine_pending_targets_with_three_running_other_attempts_can_be_superseded_without_cp_edits(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    rows=[];repairs=[];failures=[]
    with r.repair_lease(tmp_path,token='test'):
        for n in range(1,10):
            day=f'2025-05-{n:02d}';f=dict(failure,date=day)
            folder=tmp_path/'dates/B2'/day/'attempts/target28'
            request=dict(r.read(repair['retry_request_receipt']['path']),day=day,attempt_id='target28',result=str(folder/'RESULT.json'))
            r.atomic(folder/'request.json',request)
            item=dict(repair,retry_request_receipt=r.record(folder/'request.json'))
            rows.append(r.enqueue(tmp_path,f,item,lease_token='test'));repairs.append(item);failures.append(f)
        cp=dict(workers={},dates={});live=[]
        for n,row in enumerate(rows,1):
            key='B2/'+row['date']
            if n<=3:
                one,worker,_=other_running_attempt(tmp_path,row,monkeypatch,day=row['date'],attempt=f'active27_slot{n}')
                cp['workers'].update(one['workers']);cp['dates'].update(one['dates']);live.append(worker)
            else:
                cp['dates'][key]=dict(status='RETRY_PENDING',current_attempt='historical25',
                    request=str(tmp_path/'historical25/request.json'),active_recovery_queue_id='historical25_queue',
                    retry_queue_ids=[row['queue_id']])
        original_alive=r.alive
        monkeypatch.setattr(r,'alive',lambda owner:True if owner in live else original_alive(owner))
        r.atomic(tmp_path/'SUPERVISOR_STATE.json',cp);before=(tmp_path/'SUPERVISOR_STATE.json').read_bytes()
        for n,(old,f,item) in enumerate(zip(rows,failures,repairs),1):
            newer=dict(next_repair(tmp_path,item));path=tmp_path/'dates/B2'/f['date']/'attempts/target30/request.json'
            request=dict(r.read(newer['retry_request_receipt']['path']),day=f['date'],attempt_id='target30',result=str(path.parent/'RESULT.json'))
            r.atomic(path,request);newer['retry_request_receipt']=r.record(path)
            new=r.enqueue(tmp_path,f,newer,lease_token='test',supersede_queue_id=old['queue_id'])
            assert new['verification_status']=='READY_VERIFIED_REPAIR'
        assert (tmp_path/'SUPERVISOR_STATE.json').read_bytes()==before
    assert sum(row['verification_status']=='SUPERSEDED_UNSTARTED_READY' for row in r.queue(tmp_path)['entries'])==9


def test_terminal_recovery_is_measured_and_never_overwritten(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    result,_=terminal_packet(tmp_path,row)
    finished=r.mark_finished(tmp_path,row['queue_id'],result)
    assert finished['verification_status']=='RECOVERY_PASS'
    assert finished['final_remaining_native_seconds']==5389.
    assert r.mark_finished(tmp_path,row['queue_id'],result)==finished
    doc=r.read(result);doc['Native_Runtime']=0.;r.atomic(result,doc)
    with pytest.raises(PermissionError,match='NEVER_OVERWRITTEN'):
        r.mark_finished(tmp_path,row['queue_id'],result)


def test_terminal_inflight_accounting_stays_quarantined(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    result,_=terminal_packet(tmp_path,row,unknown=True)
    finished=r.mark_finished(tmp_path,row['queue_id'],result)
    assert finished['verification_status']=='QUARANTINE_TERMINAL_ACCOUNTING'
    assert finished['final_PASS'] is False


def test_completed_launch_intent_uses_exact_result_instead_of_unknown(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    terminal_packet(tmp_path,row)
    doc=r.queue(tmp_path);doc['entries'][0].update(verification_status='DISPATCH_INTENT',worker_slot=1)
    r.atomic(tmp_path/'RECOVERY_QUEUE.json',doc)
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    monkeypatch.setattr(r.subprocess,'Popen',lambda *a,**k:pytest.fail('DUPLICATE_COMPLETED_RETRY'))
    assert r.dispatch_ready(tmp_path,'B2',1,{}) is None
    assert r.queue(tmp_path)['entries'][0]['verification_status']=='RECOVERY_PASS'


def test_orphaned_live_recovery_is_adopted_without_relaunch(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    r.mark_dispatched(tmp_path,row['queue_id'],'new',r.identity(),source_SHA='b'*64)
    monkeypatch.setattr(r,'_request_workers',lambda path:[r.identity()])
    monkeypatch.setattr(r.subprocess,'Popen',lambda *a,**k:pytest.fail('ORPHAN_RELAUNCH'))
    workers=r.reconcile_workers(tmp_path)
    assert len(workers)==1 and workers[0]['recovery_queue_id']==row['queue_id']


def test_native_progress_gets_immutable_snapshot_receipts(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    r.mark_dispatched(tmp_path,row['queue_id'],'new',r.identity(),source_SHA='b'*64)
    request=r.read(row['retry_request_receipt']['path']);attempt=Path(request['result']).parent
    request.update(output=str(attempt/'output'),progress=str(attempt/'progress.json'))
    r.atomic(row['retry_request_receipt']['path'],request)
    r.atomic(attempt/'output/V19_MODEL_IDENTITY_VERIFICATION.json',{'PASS':True})
    r.atomic(attempt/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=10.,inflight={'status':'IN_FLIGHT'},calls=[]))
    r.atomic(attempt/'progress.json',dict(attempt_id='new',Native_Runtime=11.))
    r.atomic(attempt/'HEARTBEAT.json',dict(timestamp_UTC='2099-01-01T00:00:00+00:00'))
    worker=dict(r.identity(),request=row['retry_request_receipt']['path'],recovery_queue_id=row['queue_id'])
    synced=r.sync_worker(tmp_path,worker)
    assert synced['verification_status']=='NATIVE_PROGRESS_VERIFIED'
    receipts=synced['verification']['receipts']
    r.atomic(attempt/'progress.json',dict(attempt_id='new',Native_Runtime=12.))
    assert all(r.record(receipt['path'])==receipt for receipt in receipts)


def test_repair_manifest_cannot_drop_original_native_carry(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    request=r.read(row['retry_request_receipt']['path'])
    manifest=tmp_path/'repair_manifest.json';r.atomic(manifest,dict(prior_attempts={}))
    request['manifest']=str(manifest);r.atomic(row['retry_request_receipt']['path'],request)
    row['retry_request_receipt']=r.record(row['retry_request_receipt']['path'])
    monkeypatch.undo()
    monkeypatch.setattr(r.subprocess,'run',lambda *a,**k:type('Result',(),{'stdout':'c'*40 if 'rev-parse' in a[0] else ''})())
    with pytest.raises(PermissionError,match='CUMULATIVE_BUDGET_CARRY_REQUIRED'):
        r._verify_dispatch(row,request)


def b3_result(folder, runtimes, *, source='a'*64, prior=None, entered=True):
    """Real persisted stage evidence; no optimization is needed for accounting."""
    ledgers, identities, counts, states = {}, {}, {}, {}
    for stage, value in runtimes.items():
        if not entered:
            counts[stage], states[stage] = 0, 'NOT_ENTERED'
            continue
        path=folder/'PIPELINE'/stage/'NATIVE_RUNTIME_LEDGER.json'
        rows=[] if value==0 else [dict(entered_native=True,Native_Runtime=value,runtime_unavailable=False)]
        if prior is not None:
            rows=json.loads(json.dumps(prior['calls'][stage]))
            extra=value-prior['runtime'][stage]
            if extra:
                rows.append(dict(entered_native=True,Native_Runtime=extra,runtime_unavailable=False))
        r.atomic(path,dict(measured_Native_Runtime=value,inflight=None,calls=rows,
            Native_ceiling_seconds=5400,wall_ceiling_seconds=None,P2_calls=0,budget_basis='MEASURED_NATIVE_RUNTIME_ONLY'))
        identity=path.with_name('NATIVE_RUNTIME_LEDGER_IDENTITY.json')
        r.atomic(identity,dict(stage=stage,day='2025-05-08',source_sha=source,input_sha='d'*64,native_limit_seconds=5400))
        ledgers[stage],identities[stage]=r.record(path),r.record(identity)
        counts[stage],states[stage]=len(rows),'MEASURED'
    return dict(PASS=False,status='FAIL',Native_Runtime=sum(runtimes.values()),failed_stage='M2',
        stage_native_runtime=runtimes,stage_native_calls=counts,stage_native_accounting=states,
        stage_native_ledger_receipts=ledgers,stage_native_ledger_identity_receipts=identities,native_runtime_state='KNOWN')


def b3_packet(tmp_path,monkeypatch,*,runtimes=None,entered=True):
    failure,repair=packet(tmp_path,monkeypatch)
    costs=dict(A1=0.,M1=3500.,A2=2600.,M2=20.) if runtimes is None else runtimes
    folder=tmp_path/'b3_original'
    result=b3_result(folder,costs,entered=entered)
    result['failed_stage']='M2' if entered else 'ADMISSION'
    r.atomic(folder/'RESULT.json',result)
    failure.update(arm='B3',failed_stage=result['failed_stage'],original_native_runtime=sum(costs.values()),
        original_result_receipt=r.record(folder/'RESULT.json'))
    if entered:
        failure['original_ledger_receipt']=result['stage_native_ledger_receipts']['M2']
    else:
        failure.pop('original_ledger_receipt',None)
    path=tmp_path/'dates/B3/2025-05-08/attempts/new/request.json'
    request=dict(arm='B3',day='2025-05-08',attempt_id='new',worker_slot=1,
        result=str(path.parent/'RESULT.json'),repair_source_SHA='b'*64,implementation_SHA='b'*64,source_SHA='b'*64,
        source_seal=str(tmp_path/'source_seal.json'),
        previous_attempts=[str(folder)])
    r.atomic(path,request)
    repair.update(worker_module='v42_autonomous_b3.worker',retry_request_receipt=r.record(path))
    return failure,repair


def test_b3_aggregate_above_one_stage_cap_preserves_four_independent_budgets(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    assert row['original_native_runtime']==6120.
    assert row['remaining_native_seconds']==5380.
    assert row['remaining_native_seconds_by_stage']==dict(A1=5400.,M1=1900.,A2=2800.,M2=5380.)
    assert row['native_budget_scope']=='B3_STAGE_ISOLATED'
    assert set(row['original_stage_ledger_receipts'])==set(r.B3_STAGES)


@pytest.mark.parametrize('stage',['M1','M2'])
def test_b3_any_exhausted_rerun_stage_blocks_retry(tmp_path,monkeypatch,stage):
    costs=dict(A1=0.,M1=3500.,A2=2600.,M2=20.);costs[stage]=5400.
    failure,repair=b3_packet(tmp_path,monkeypatch,runtimes=costs)
    with r.repair_lease(tmp_path,token='test'):
        with pytest.raises(PermissionError,match='EXHAUSTED_NATIVE_BUDGET'):
            r.enqueue(tmp_path,failure,repair,lease_token='test')


def test_b3_stage_unknown_blocks_even_when_aggregate_is_numeric(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch)
    path=Path(failure['original_result_receipt']['path']);doc=r.read(path)
    doc['stage_native_accounting']['M2']='UNKNOWN';doc['stage_native_runtime']['M2']=None
    r.atomic(path,doc);failure['original_result_receipt']=r.record(path)
    with r.repair_lease(tmp_path,token='test'):
        with pytest.raises(PermissionError,match='UNKNOWN_NATIVE_RUNTIME'):
            r.enqueue(tmp_path,failure,repair,lease_token='test')


def test_b3_result_total_must_equal_sum_of_measured_stages(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch)
    path=Path(failure['original_result_receipt']['path']);doc=r.read(path);doc['Native_Runtime']+=1
    r.atomic(path,doc);failure.update(original_native_runtime=doc['Native_Runtime'],original_result_receipt=r.record(path))
    with r.repair_lease(tmp_path,token='test'):
        with pytest.raises(PermissionError,match='AGGREGATE_STAGE_NATIVE_ACCOUNTING'):
            r.enqueue(tmp_path,failure,repair,lease_token='test')


def test_b3_result_stage_cost_must_equal_its_ledger(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch)
    path=Path(failure['original_result_receipt']['path']);doc=r.read(path)
    doc['stage_native_runtime']['A2']+=1;doc['Native_Runtime']+=1
    r.atomic(path,doc);failure.update(original_native_runtime=doc['Native_Runtime'],original_result_receipt=r.record(path))
    with r.repair_lease(tmp_path,token='test'):
        with pytest.raises(PermissionError,match='STAGE_MEASURED_NATIVE_ACCOUNTING'):
            r.enqueue(tmp_path,failure,repair,lease_token='test')


def test_b3_inflight_ledger_is_unknown_even_with_finite_recorded_cost(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch)
    result_path=Path(failure['original_result_receipt']['path']);result=r.read(result_path)
    ledger_path=Path(result['stage_native_ledger_receipts']['A2']['path']);ledger=r.read(ledger_path)
    ledger['inflight']={'status':'IN_FLIGHT'};r.atomic(ledger_path,ledger)
    result['stage_native_ledger_receipts']['A2']=r.record(ledger_path);r.atomic(result_path,result)
    failure['original_result_receipt']=r.record(result_path)
    with r.repair_lease(tmp_path,token='test'):
        with pytest.raises(PermissionError,match='UNKNOWN_NATIVE_RUNTIME'):
            r.enqueue(tmp_path,failure,repair,lease_token='test')


def test_b3_stage_identity_from_another_day_is_rejected(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch)
    result_path=Path(failure['original_result_receipt']['path']);result=r.read(result_path)
    identity_path=Path(result['stage_native_ledger_identity_receipts']['A2']['path']);identity=r.read(identity_path)
    identity['day']='2025-05-09';r.atomic(identity_path,identity)
    result['stage_native_ledger_identity_receipts']['A2']=r.record(identity_path);r.atomic(result_path,result)
    failure['original_result_receipt']=r.record(result_path)
    with r.repair_lease(tmp_path,token='test'):
        with pytest.raises(PermissionError,match='STAGE_LEDGER_SCIENTIFIC_IDENTITY'):
            r.enqueue(tmp_path,failure,repair,lease_token='test')


def test_b3_explicit_not_entered_failure_does_not_require_invented_ledger(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch,runtimes={stage:0. for stage in r.B3_STAGES},entered=False)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    assert row['original_stage_ledger_receipts']=={}
    assert row['remaining_native_seconds'] is None
    assert all(value==5400 for value in row['remaining_native_seconds_by_stage'].values())


def b3_terminal(tmp_path,row,*,break_prefix=False):
    original=r.read(row['original_result_receipt']['path'])
    prior=r.b3_stage_accounting(original,day=row['date'],source=row['original_source_SHA'])
    request=r.read(row['retry_request_receipt']['path']);path=Path(request['result'])
    final=b3_result(path.parent,dict(A1=0.,M1=3501.,A2=2602.,M2=23.),source='b'*64,prior=prior)
    if break_prefix:
        ledger_path=Path(final['stage_native_ledger_receipts']['M1']['path'])
        ledger=r.read(ledger_path);ledger['calls'][0]['changed_prior_call']=True;r.atomic(ledger_path,ledger)
        final['stage_native_ledger_receipts']['M1']=r.record(ledger_path)
    final.update(identity=dict(day=row['date'],arm='B3',attempt_id='new'),source_sha='b'*64,
        PASS=True,status='PASS',stages={stage:dict(native_seconds=value,
            original_integer_physical_verified=True,independent_global_verified=True)
            for stage,value in final['stage_native_runtime'].items()})
    r.atomic(path,final)
    return path


def test_b3_terminal_above_aggregate_cap_is_valid_with_preserved_stage_prefixes(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    result=b3_terminal(tmp_path,row)
    final=r.mark_finished(tmp_path,row['queue_id'],result)
    assert final['verification_status']=='RECOVERY_PASS'
    assert final['final_Native_Runtime']==6126.
    assert final['final_remaining_native_seconds_by_stage']['M1']==1899.


def test_b3_terminal_cannot_replace_prior_calls_with_equal_cost_calls(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    result=b3_terminal(tmp_path,row,break_prefix=True)
    final=r.mark_finished(tmp_path,row['queue_id'],result)
    assert final['verification_status']=='QUARANTINE_TERMINAL_ACCOUNTING'
    assert final['final_PASS'] is False


def authorize_zero(tmp_path,repair):
    auth=tmp_path/'USER_ZERO_START_RETRY_AUTHORIZATION.json'
    r.atomic(auth,dict(schema='V42_USER_AUTHORIZED_ZERO_START_RETRY_V1',campaign_root=str(tmp_path),UTC=r.now(),
        user_instruction='해결하고 재실행할 때는 0초부터 처음부터 다시 돌려야돼. 알지?',
        scope='VERIFIED_SOURCE_REPAIR_FRESH_DATE_RETRY',restart_from_zero=True,native_budget_seconds=5400,
        B3_native_budget_per_stage_seconds=5400,previous_checkpoint_reuse=False,previous_native_budget_carry=False,
        old_attempts_and_accounting_preserved=True,normal_workers_must_continue=True,applies_to_hourly_verified_repairs=True))
    receipt=r.record(auth);repair.update(restart_from_zero=True,reset_authorization=receipt)
    path=Path(repair['retry_request_receipt']['path']);request=r.read(path)
    request.update(root=str(tmp_path),restart_from_zero=True,reset_authorization=receipt,previous_attempts=[])
    if request['arm']=='B2':
        manifest=tmp_path/'ZERO_START_MANIFEST.json';r.atomic(manifest,dict(prior_attempts={}))
        request['manifest']=str(manifest)
    r.atomic(path,request);repair['retry_request_receipt']=r.record(path)
    return receipt


def test_zero_start_retry_without_explicit_user_receipt_is_rejected(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    repair['restart_from_zero']=True
    with r.repair_lease(tmp_path,token='test'):
        with pytest.raises(PermissionError,match='ZERO_START_USER_AUTHORIZATION'):
            r.enqueue(tmp_path,failure,repair,lease_token='test')


@pytest.mark.parametrize('runtime',[10.,5400.,None,'UNKNOWN'])
def test_authorized_zero_retry_preserves_known_exhausted_and_unknown_history(tmp_path,monkeypatch,runtime):
    failure,repair=packet(tmp_path,monkeypatch,runtime=10.)
    result=Path(failure['original_result_receipt']['path']);ledger=Path(failure['original_ledger_receipt']['path'])
    original=r.read(result);original['Native_Runtime']=runtime;r.atomic(result,original)
    doc=r.read(ledger);doc.update(measured_Native_Runtime=runtime,inflight={'status':'IN_FLIGHT'} if runtime is None or runtime=='UNKNOWN' else None)
    r.atomic(ledger,doc)
    failure.update(original_native_runtime=runtime,original_result_receipt=r.record(result),original_ledger_receipt=r.record(ledger),
        runtime_unknown=runtime is None or runtime=='UNKNOWN',quarantined=runtime is None or runtime=='UNKNOWN')
    before=(result.read_bytes(),ledger.read_bytes());authorize_zero(tmp_path,repair)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    assert row['initial_native_runtime']==0. and row['remaining_native_seconds']==5400.
    assert row['historical_native_runtime']==runtime
    assert (result.read_bytes(),ledger.read_bytes())==before
    request=r.read(row['retry_request_receipt']['path']);final=Path(request['result'])
    r.atomic(final.parent/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=1.,inflight=None,prior_attempt=None,
        calls=[dict(entered_native=True,Native_Runtime=1.,runtime_unavailable=False)]))
    r.atomic(final,dict(identity=dict(arm='B2',day=row['date'],attempt_id=request['attempt_id']),
        source_SHA=row['repair_source_SHA'],PASS=True,status='PASS',scientific_PASS=True,Native_Runtime=1.))
    outcome=r.mark_finished(tmp_path,row['queue_id'],final)
    assert outcome['verification_status']=='RECOVERY_PASS' and outcome['final_remaining_native_seconds']==5399.
    assert (result.read_bytes(),ledger.read_bytes())==before


def test_authorized_b3_zero_retry_uses_new_stage_budgets_without_old_prefix(tmp_path,monkeypatch):
    failure,repair=b3_packet(tmp_path,monkeypatch,runtimes=dict(A1=0.,M1=5400.,A2=3000.,M2=100.))
    old_result=Path(failure['original_result_receipt']['path']);old_bytes=old_result.read_bytes()
    authorize_zero(tmp_path,repair)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    assert row['initial_stage_native_runtime']=={stage:0. for stage in r.B3_STAGES}
    assert row['remaining_native_seconds_by_stage']=={stage:5400. for stage in r.B3_STAGES}
    request=r.read(row['retry_request_receipt']['path']);path=Path(request['result'])
    result=b3_result(path.parent,dict(A1=0.,M1=1.,A2=2.,M2=3.),source='b'*64)
    result.update(identity=dict(arm='B3',day=row['date'],attempt_id=request['attempt_id']),source_sha='b'*64,
        PASS=True,status='PASS',stages={stage:dict(native_seconds=value,original_integer_physical_verified=True,
            independent_global_verified=True) for stage,value in result['stage_native_runtime'].items()})
    r.atomic(path,result)
    assert r.mark_finished(tmp_path,row['queue_id'],path)['verification_status']=='RECOVERY_PASS'
    assert old_result.read_bytes()==old_bytes


def test_daily_retry_admission_failure_preserves_budget_and_other_retry_can_launch(tmp_path,monkeypatch):
    failure,repair=packet(tmp_path,monkeypatch)
    with r.repair_lease(tmp_path,token='test'):
        row=r.enqueue(tmp_path,failure,repair,lease_token='test')
    monkeypatch.setattr(r,'_request_workers',lambda path:[])
    monkeypatch.setattr(r,'_verify_dispatch',lambda row,request:(_ for _ in ()).throw(PermissionError('EXHAUSTED_NATIVE_BUDGET_NO_AUTOMATIC_RETRY')))
    monkeypatch.setattr(r.subprocess,'Popen',lambda *a,**k:pytest.fail('EXHAUSTED_RETRY_LAUNCHED'))
    assert r.dispatch_ready(tmp_path,'B2',1,{}) is None
    denied=r.queue(tmp_path)['entries'][0]
    assert denied['verification_status']=='QUARANTINE_REPAIR_ADMISSION'
    assert denied['original_native_runtime']==10. and denied['new_attempt_native_runtime']==0.
    assert r.read(denied['admission_failure_receipt']['path'])['Native_Runtime']==10.
