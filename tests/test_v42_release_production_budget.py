"""Named fixtures exercise accounting and guards; no actual Native call."""
from copy import deepcopy
import json
import sys
from types import SimpleNamespace

import pytest

from v42_integration import release_production_budget as mod


def setup_budget(tmp_path, monkeypatch):
    old = []
    for name in ('canonical', 'consumed_rc01'):
        p = tmp_path / (name + '.json'); p.write_text(name); old.append(p)
    context = dict(day='2025-05-01', stage='M1', stage_case_sha='case', source_sha='source', parent_result_sha='A1')
    auth = dict(schema=mod.SCHEMA, approved=True, scope='NEW_RELEASE_P1_ONLY_HEAVY', P2_calls=0,
        Worker=1, Threads=1, human_approval_reference='NAMED_TEST_FIXTURE_ONLY', policy_sha='fixture-policy',
        authorization_id='NAMED_FIXTURE_ONLY',authorized_ledger_path=str(tmp_path/'NEW.json'),
        stage_caps_seconds={'M1': 4.}, return_reserve_seconds=30., limit_seconds=35.,
        stage_cap_scope='WHOLE_AUTHORIZATION_STAGE_TOTAL',
        allowed_stage_bindings=[context])
    b = mod.ReleaseProductionBudget(tmp_path / 'NEW.json', authorization=auth, historical_ledgers=old,
                                    worker_lock=tmp_path / 'SHARED.lock')
    monkeypatch.setattr(mod, 'resource_snapshot', lambda: dict(memory=dict(AvailableMBytes=20000, PercentCommittedBytesInUse=20)))
    monkeypatch.setattr(mod, 'native_binding', lambda m: dict(Threads=m.Params.Threads, objective_sense=1, matrix_sha='x', domain_sha='y'))
    class NamedFixtureModel:
        NumObj = 1
        def __init__(self):
            self.Params = SimpleNamespace(Threads=1, TimeLimit=None)
            self.Runtime = 0.; self.Status = 1; self.raise_error = False
        def optimize(self, *args):
            self.Runtime = 2.; self.Status = 2
            if self.raise_error:
                raise RuntimeError('NAMED_FIXTURE_SOLVER_ERROR')
        def presolve(self):
            raise AssertionError('UNEXPECTED_FIXTURE_PRESOLVE')
        def computeIIS(self):
            raise AssertionError('UNEXPECTED_FIXTURE_IIS')
    monkeypatch.setitem(sys.modules, 'gurobipy', SimpleNamespace(Model=NamedFixtureModel))
    return b, auth, old, context, NamedFixtureModel


def phase(b, c):
    return b.phase(c['stage'], c['stage_case_sha'], c['source_sha'], c['parent_result_sha'], day=c['day'])


def test_no_reuse_of_consumed_a1_or_unapproved_budget(tmp_path):
    for a in ({}, dict(scope='D0_A1_P1_EXACTLY_ONE_CALL', approved=True, limit_seconds=180.)):
        with pytest.raises(PermissionError, match='NEW_EXPLICIT'):
            mod.ReleaseProductionBudget(tmp_path / 'no.json', authorization=a, historical_ledgers=[])
    assert not (tmp_path / 'no.json').exists()


def test_native_stage_cap_shared_guards_and_historical_preservation(tmp_path, monkeypatch):
    b, auth, old, c, Model = setup_budget(tmp_path, monkeypatch)
    before = [p.read_bytes() for p in old]
    with phase(b, c), b.capture_native_methods():
        with pytest.raises(PermissionError, match='UNBUDGETED'):
            Model().optimize()
        with pytest.raises(PermissionError, match='UNBUDGETED'):
            Model().presolve()
        first = Model()
        b.solve(first, label='RELEASE_P1:M1:JOINT', cap=4.)
        second = Model()
        b.solve(second, label='RELEASE_P1:M1:JOINT', cap=4.)
        assert second.Params.TimeLimit == 2.
        with pytest.raises(RuntimeError, match='EXHAUSTED'):
            b.solve(Model(), label='RELEASE_P1:M1:JOINT', cap=1.)
    assert b.used() == 4.
    assert [p.read_bytes() for p in old] == before
    assert all(r['stage_context'] == c and r['P2_call'] is False for r in b.document['calls'])
    assert b.document['inflight'] is None and not b.worker_lock.exists()
    reopened = mod.ReleaseProductionBudget(b.path, authorization=auth, historical_ledgers=old, worker_lock=b.worker_lock)
    with phase(reopened, c):
        assert reopened.remaining() == 0.


def test_wrong_parent_binding_p2_and_unguarded_native_rejected(tmp_path, monkeypatch):
    b, _, _, c, Model = setup_budget(tmp_path, monkeypatch)
    with pytest.raises(PermissionError, match='EXACT_APPROVED'):
        with b.phase('M1', 'other-case', 'source', 'A1'):
            pass
    with phase(b, c):
        with pytest.raises(PermissionError, match='GUARDED'):
            b.solve(Model(), label='RELEASE_P1:M1:JOINT', cap=1.)
        with b.capture_native_methods():
            with pytest.raises(ValueError, match='P1_ONLY'):
                b.solve(Model(), label='RELEASE_P1:M1:P2', cap=1.)
            with pytest.raises(ValueError, match='EXACT_NATIVE'):
                b.solve(Model(), label='RELEASE_P1:M1:JOINT', cap=1., binding={'matrix_sha': 'wrong'})
    assert b.used() == 0.


def test_solver_error_charged_and_lock_released(tmp_path, monkeypatch):
    b, _, _, c, Model = setup_budget(tmp_path, monkeypatch)
    model = Model(); model.raise_error = True
    with phase(b, c), b.capture_native_methods():
        with pytest.raises(RuntimeError, match='NAMED_FIXTURE_SOLVER_ERROR'):
            b.solve(model, label='RELEASE_P1:M1:JOINT', cap=4.)
    assert b.used() == 2.
    assert 'NAMED_FIXTURE_SOLVER_ERROR' in b.document['calls'][-1]['error']
    assert b.document['inflight'] is None and not b.worker_lock.exists()


def test_external_wall_overshoot_is_charged_not_discarded(tmp_path, monkeypatch):
    b, _, _, c, _ = setup_budget(tmp_path, monkeypatch)
    with phase(b, c):
        b.record_external('RELEASE_P1:M1:HIGHS', 5., solver='HIGHS')
        b.record_external('RELEASE_P1:M1:AC', 7., solver='AC')
        assert b.remaining() == 0.
    assert b.used() == 5. and b.document['AC_wall_seconds'] == 7.
    assert 'OVERSHOOT' in b.document['calls'][0]['status']


def test_shared_worker_busy_cannot_run_native(tmp_path, monkeypatch):
    b, _, _, c, Model = setup_budget(tmp_path, monkeypatch)
    b.worker_lock.write_text('another-worker')
    with phase(b, c), b.capture_native_methods():
        with pytest.raises(FileExistsError):
            b.solve(Model(), label='RELEASE_P1:M1:JOINT', cap=2.)
    assert b.used() == 0. and b.worker_lock.read_text() == 'another-worker'


def test_interrupted_ledger_does_not_resume_or_reset(tmp_path, monkeypatch):
    b, auth, old, c, _ = setup_budget(tmp_path, monkeypatch)
    d = deepcopy(b.document)
    d.update(inflight=dict(pid=99999999, cap=4., label='RELEASE_P1:M1:JOINT'), active_stage_context=c)
    b.path.write_text(json.dumps(d), encoding='utf8')
    with pytest.raises(RuntimeError, match='UNRECONCILED'):
        mod.ReleaseProductionBudget(b.path, authorization=auth, historical_ledgers=old,worker_lock=b.worker_lock)
    with pytest.raises(ValueError, match='CONSERVATIVE'):
        mod.reconcile_interrupted_ledger(b.path, evidence='fixture-exit-receipt', charge_seconds=1.)
    monkeypatch.setattr('psutil.pid_exists', lambda pid: False)
    mod.reconcile_interrupted_ledger(b.path, evidence='fixture-exit-receipt', charge_seconds=4.)
    reopened = mod.ReleaseProductionBudget(b.path, authorization=auth, historical_ledgers=old,worker_lock=b.worker_lock)
    assert reopened.used() == 4. and len(reopened.document['calls']) == 1


def test_p2_component_direct_helper_cannot_be_relabelled_p1(tmp_path,monkeypatch):
    b,_,_,c,Model=setup_budget(tmp_path,monkeypatch)
    with phase(b,c),b.capture_native_methods():
        with pytest.raises(ValueError,match='P2_ABSOLUTELY'):
            b.native_optimize(Model(),component='P2',track='M',label='JOINT',requested_seconds=1.)
    assert b.used()==0.


def test_authorization_cannot_create_second_ledger_or_reset_deleted_one(tmp_path,monkeypatch):
    b,auth,old,_,_=setup_budget(tmp_path,monkeypatch)
    with pytest.raises(PermissionError,match='CANONICAL_LEDGER'):
        mod.ReleaseProductionBudget(tmp_path/'OTHER.json',authorization=auth,historical_ledgers=old,worker_lock=b.worker_lock)
    b.path.unlink()
    with pytest.raises(RuntimeError,match='RESET_FORBIDDEN'):
        mod.ReleaseProductionBudget(b.path,authorization=auth,historical_ledgers=old,worker_lock=b.worker_lock)


def test_phase_interrupt_without_inflight_conservatively_consumes_stage(tmp_path,monkeypatch):
    b,auth,old,c,_=setup_budget(tmp_path,monkeypatch)
    d=deepcopy(b.document)
    d.update(active_stage_context=c,active_stage_owner_pid=99999999)
    b.path.write_text(json.dumps(d),encoding='utf8')
    monkeypatch.setattr('psutil.pid_exists',lambda pid:False)
    with pytest.raises(ValueError,match='CONSERVATIVE'):
        mod.reconcile_interrupted_ledger(b.path,evidence='fixture-exit',charge_seconds=0.)
    mod.reconcile_interrupted_ledger(b.path,evidence='fixture-exit',charge_seconds=4.)
    reopened=mod.ReleaseProductionBudget(b.path,authorization=auth,historical_ledgers=old,worker_lock=b.worker_lock)
    with phase(reopened,c):
        assert reopened.remaining()==0.


def test_historical_drift_blocks_phase(tmp_path, monkeypatch):
    b, _, old, c, _ = setup_budget(tmp_path, monkeypatch)
    old[0].write_text('unexpected mutation')
    with pytest.raises(ValueError, match='HISTORICAL'):
        with phase(b, c):
            pass


@pytest.mark.parametrize('field,value',[('limit_seconds',float('inf')),
    ('limit_seconds',float('nan')),('return_reserve_seconds',float('nan')),
    ('return_reserve_seconds',True)])
def test_nonfinite_or_boolean_approval_amount_rejected(tmp_path,monkeypatch,field,value):
    _,auth,_,_,_=setup_budget(tmp_path,monkeypatch)
    auth[field]=value
    with pytest.raises(PermissionError,match='FINITE'):
        mod.require_authorization(auth)


def test_dead_owned_worker_and_mutation_locks_recovered_with_evidence(tmp_path,monkeypatch):
    b,_,_,_,_=setup_budget(tmp_path,monkeypatch)
    mutation=b.path.with_suffix(b.path.suffix+'.MUTATION.lock')
    for path,kind in ((mutation,'LEDGER_MUTATION'),(b.worker_lock,'HEAVY_WORKER')):
        owner=b._lock_owner(kind);owner['pid']=99999999
        path.write_text(json.dumps(owner),encoding='utf8')
    monkeypatch.setattr('psutil.pid_exists',lambda pid:False)
    records=mod.reclaim_stale_release_locks(b.path,evidence='NAMED_FIXTURE_PROCESS_EXIT')
    assert len(records)==2 and not mutation.exists() and not b.worker_lock.exists()
    assert b.used()==0. # recovery never claims or erases solver runtime
    assert all('debt_not_reconciled' in open(r['path'],encoding='utf8').read() for r in records)


def test_live_or_historical_worker_lock_cannot_be_recovered(tmp_path,monkeypatch):
    b,_,_,_,_=setup_budget(tmp_path,monkeypatch)
    owner=b._lock_owner('HEAVY_WORKER')
    b.worker_lock.write_text(json.dumps(owner),encoding='utf8')
    with pytest.raises(ValueError,match='DEAD_EXACT'):
        mod.reclaim_stale_release_locks(b.path,evidence='fixture')
    assert b.worker_lock.exists()
    b.worker_lock.write_text('35740',encoding='utf8')
    with pytest.raises(ValueError,match='HISTORICAL'):
        mod.reclaim_stale_release_locks(b.path,evidence='fixture')
    assert b.worker_lock.read_text()=='35740'


def test_per_date_stage_limits_do_not_reset_overall_approval(tmp_path,monkeypatch):
    b,auth,old,c,_=setup_budget(tmp_path,monkeypatch)
    other=deepcopy(c);other['day']='2025-05-02'
    auth.update(authorization_id='DISTINCT_TWO_DATE_FIXTURE',authorized_ledger_path=str(tmp_path/'TWO_DATES.json'),
        stage_cap_scope='PER_DATE_STAGE',allowed_stage_bindings=[c,other],limit_seconds=38.)
    b=mod.ReleaseProductionBudget(tmp_path/'TWO_DATES.json',authorization=auth,historical_ledgers=old,worker_lock=b.worker_lock)
    with phase(b,c):
        b.record_external('RELEASE_P1:M1:HIGHS',4.,solver='HIGHS')
        assert b.remaining()==0.
    with phase(b,other):
        assert b.remaining()==4.
        b.record_external('RELEASE_P1:M1:HIGHS',4.,solver='HIGHS')
        assert b.remaining()==0.
    assert b.used()==8. and b.document['limit_seconds']==38.
