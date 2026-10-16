from copy import deepcopy
from datetime import datetime,timezone
import json
from types import SimpleNamespace
import numpy as np
import pytest
from v42_integration.table_v_interruption import restart_bounds,archived_runtime_summary
from v42_integration.m_engine import file_record


def events():
    return [dict(Id=i,TimeCreated=datetime.fromtimestamp(t,timezone.utc).isoformat())
        for i,t in [(1074,110),(6006,120),(6005,130)]]


def call():return dict(pid=999999999,started_epoch_seconds=100.,cap=60.,label='RELEASE_P1:A1:TEST',stage_context={})


def test_restart_interval_does_not_count_later_session_downtime_or_fabricate_runtime():
    a=restart_bounds(call(),events(),boot_epoch=140,pid_alive=False,log_text='  3  8.0  19s\n')
    b=restart_bounds(call(),events(),boot_epoch=100000,pid_alive=False,log_text='  3  8.0  19s\n')
    assert a==b and a['exact'] is None and a['lower']==18. and a['upper']==31.
    assert not a['offline_downtime_charged_as_native']


@pytest.mark.parametrize('change', ['live','no_boot','before_boot','bad_interval'])
def test_restart_proof_rejects_live_owner_missing_boot_or_inconsistent_log(change):
    args=dict(boot_epoch=140,pid_alive=False,log_text='  3  8.0  19s\n');rows=events()
    if change=='live':args['pid_alive']=True
    if change=='no_boot':rows=rows[:2]
    if change=='before_boot':args['boot_epoch']=100
    if change=='bad_interval':args['log_text']='  3  8.0  100s\n'
    with pytest.raises(ValueError):restart_bounds(call(),rows,**args)


def receipt(tmp_path,document):
    from v42_integration.table_v_native_journal import atomic_json
    old=tmp_path/'OLD.json';atomic_json(old,document)
    ev=tmp_path/'EVENTS.json';atomic_json(ev,events())
    log=tmp_path/'NATIVE.log';log.write_text('  3  8.0  19s\n')
    bounds=restart_bounds(document['inflight'],events(),boot_epoch=140,pid_alive=False,log_text=log.read_text())
    p=tmp_path/'RECEIPT.json';atomic_json(p,dict(original_ledger=file_record(old),events=file_record(ev),
        native_log=file_record(log),observed_new_boot_epoch_seconds=140,native_runtime_interval_seconds=bounds))
    return file_record(p),bounds


def test_official_reconciliation_keeps_exact_subtotal_null_lost_runtime_and_raw_backup(tmp_path):
    from v42_integration.release_production_budget import reconcile_interrupted_ledger
    from v42_integration.table_v_native_journal import atomic_json
    d=dict(inflight=call(),active_stage_context={},calls=[dict(solver='GUROBI',Native_Runtime=2.)],
        Gurobi_Native_seconds=2.,conservative_solve_seconds=2.)
    proof,bounds=receipt(tmp_path,d);p=tmp_path/'CURRENT.json';atomic_json(p,d)
    old=(tmp_path/'OLD.json').read_bytes()
    out=reconcile_interrupted_ledger(p,evidence=proof,charge_seconds=31.,host_restart_receipt=proof)
    assert out['Gurobi_Native_seconds']==2. and out['calls'][-1]['Native_Runtime'] is None
    assert out['conservative_solve_seconds']==33. and out['inflight'] is None
    assert out['sealed_interrupted_attempt'] and (tmp_path/'OLD.json').read_bytes()==old
    summary=archived_runtime_summary(out)
    assert summary['known_native_seconds']==2. and summary['native_lower_bound_seconds']==20.
    assert summary['native_upper_bound_seconds']==33. and not summary['native_runtime_fully_known']
    changed=deepcopy(out);changed['calls'][-1]['Native_Runtime']=0.
    with pytest.raises(ValueError,match='REMAIN_NULL'):archived_runtime_summary(changed)
    changed=deepcopy(out);changed['calls'][-1]['charged_seconds']=30.
    with pytest.raises(ValueError,match='CHARGE_DRIFT'):archived_runtime_summary(changed)
    (tmp_path/'NATIVE.log').write_text('changed')
    with pytest.raises(ValueError,match='BYTE_DRIFT'):archived_runtime_summary(out)


def test_fresh_attempt_preserves_uncertain_archive_and_cannot_reopen_old_attempt(tmp_path,monkeypatch):
    from tests.test_v42_table_v_budget import setup,context
    from v42_integration import table_v_budget as mod
    from v42_integration.release_production_budget import reconcile_interrupted_ledger
    from v42_integration.table_v_native_journal import atomic_json
    b,auth,hist,Model=setup(tmp_path,monkeypatch)
    with b.arm_context('B1'),context(b,'B1','A1'),b.capture_native_methods():
        b.solve(Model(),label='RELEASE_P1:A1:FIXTURE',cap=60.)
    b._refresh();b.document['inflight']=call();atomic_json(b.path,b.document)
    proof,_=receipt(tmp_path,b.document)
    reconcile_interrupted_ledger(b.path,evidence=proof,charge_seconds=31.,host_restart_receipt=proof)
    with pytest.raises(RuntimeError,match='SEALED_INTERRUPTED'):
        mod.TableVStageBudget(b.path,authorization=auth,historical_ledgers=hist,worker_lock=b.worker_lock)
    old=b.path.read_bytes();fresh=dict(schema='TABLE_V_EXPLICIT_FRESH_NATIVE_CYCLE_V1',approved=True,
        start_native_seconds=0,cycle_id='NAMED_RESTART_FIXTURE',human_approval_reference='NAMED_USER',
        archived_native_ledgers=[file_record(b.path)],reuse_previous_solution_or_bound=False)
    a=dict(auth,authorization_id='NAMED_RESTART_NEW_ATTEMPT',authorized_ledger_path=str(tmp_path/'FRESH.json'),fresh_native_cycle=fresh)
    new=mod.TableVStageBudget(tmp_path/'FRESH.json',authorization=a,historical_ledgers=hist,worker_lock=b.worker_lock)
    assert new.used()==0. and new.document['archived_native_seconds_excluded_from_current_cycle']==2.
    assert new.document['archived_native_lower_bound_seconds']==20. and new.document['archived_native_upper_bound_seconds']==33.
    assert not new.document['archived_native_runtime_fully_known'] and b.path.read_bytes()==old


def test_native_journal_keeps_callback_runtime_and_partial_barx_separate_from_ub(tmp_path,monkeypatch):
    import sys
    from v42_integration.table_v_native_journal import NativeJournal
    callback=SimpleNamespace(POLLING=0,RUNTIME=6002)
    monkeypatch.setitem(sys.modules,'gurobipy',SimpleNamespace(GRB=SimpleNamespace(Callback=callback)))
    budget=SimpleNamespace(path=tmp_path/'LEDGER.json',document=dict(inflight=dict(pid=__import__('os').getpid(),label='test')))
    journal=NativeJournal(budget,'test')
    class Model:
        def cbGet(self,code):return 12.25
        def getAttr(self,key):
            if key=='BarX':return [1e15,-3.]
            raise AttributeError(key)
    journal.callback(Model(),1);journal.finish(Model(),dict(native_execution_entered=True,Native_Runtime=13.))
    live=json.loads((journal.folder/'LIVE.json').read_text())
    assert live['Native_Runtime_observed']==12.25 and live['final_Runtime_available'] is False
    terminal=json.loads((journal.folder/'TERMINAL.json').read_text())
    assert terminal['partial_BarX_is_not_original_FULL_UB'] and terminal['available_attributes']==['BarX']
    with np.load(terminal['arrays']['path']) as raw:assert np.array_equal(raw['BarX'],[1e15,-3.])
