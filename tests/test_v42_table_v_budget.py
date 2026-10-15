"""Accounting fixtures only: no real Gurobi optimization."""
from copy import deepcopy
import sys
from types import SimpleNamespace

import pytest

from v42_integration import table_v_budget as mod
from v42_integration import release_production_budget as native


def setup(tmp_path, monkeypatch):
    history=[]
    for name in ('canonical','consumed'):
        p=tmp_path/(name+'.json');p.write_text(name);history.append(p)
    auth=dict(schema=mod.SCHEMA,approved=True,budget_kind='PLANNING_NATIVE',
        stage_caps_seconds=deepcopy(mod.MAIN_CAPS),total_limit_seconds=None,total_limit_enabled=False,
        timeout_basis='CUMULATIVE_GUROBI_NATIVE_OPTIMIZE_PER_ARM_STAGE',P2_calls=0,Worker=1,Threads=1,
        authorization_id='NAMED_TABLE_V_FIXTURE',authorized_ledger_path=str(tmp_path/'NEW.json'),
        human_approval_reference='NAMED_FIXTURE',source_cases=[{'fixture':True}])
    b=mod.TableVStageBudget(tmp_path/'NEW.json',authorization=auth,historical_ledgers=history,
                           worker_lock=tmp_path/'WORKER.lock')
    monkeypatch.setattr(native,'resource_snapshot',lambda:dict(memory=dict(AvailableMBytes=20000,PercentCommittedBytesInUse=20)))
    monkeypatch.setattr(native,'native_binding',lambda m:dict(Threads=m.Params.Threads,objective_sense=1,matrix_sha='fixture'))
    class Model:
        NumObj=1
        def __init__(self):
            self.Params=SimpleNamespace(Threads=1,TimeLimit=None)
            self.Runtime=0.;self.Status=1;self.seconds=2.
        def optimize(self,*args):
            self.Runtime=self.seconds;self.Status=2
        def presolve(self):pass
        def computeIIS(self):pass
    monkeypatch.setitem(sys.modules,'gurobipy',SimpleNamespace(Model=Model))
    return b,auth,history,Model


def context(b,arm,stage):
    c=dict(day='2025-05-01',arm=arm,stage=stage,stage_case_sha='fixture-case',
           source_sha='fixture-source',parent_result_sha='fixture-parent')
    b.derived_bindings.append(c)
    return b.phase(stage,c['stage_case_sha'],c['source_sha'],c['parent_result_sha'])


def test_native_cumulative_per_arm_stage_no_global_cap(tmp_path,monkeypatch):
    b,auth,hist,Model=setup(tmp_path,monkeypatch)
    before=[p.read_bytes() for p in hist]
    with b.arm_context('B1'),context(b,'B1','A1'),b.capture_native_methods():
        first=Model();first.seconds=5399.
        b.solve(first,label='RELEASE_P1:A1:FIXTURE',cap=5400.)
        second=Model();second.seconds=1.
        b.solve(second,label='RELEASE_P1:A1:FIXTURE',cap=5400.)
        assert second.Params.TimeLimit==1.
        with pytest.raises(RuntimeError,match='EXHAUSTED'):
            b.solve(Model(),label='RELEASE_P1:A1:FIXTURE',cap=1.)
        b.record_external('RELEASE_P1:A1:AC',10000.,solver='AC')
    with b.arm_context('B3'),context(b,'B3','A1'),b.capture_native_methods():
        assert b.remaining()==5400.
        other=Model();other.seconds=5400.
        b.solve(other,label='RELEASE_P1:A1:FIXTURE',cap=5400.)
    assert b.used()==10800.
    assert b.document['limit_seconds'] is None
    assert b.document['total_limit_enabled'] is False
    assert [p.read_bytes() for p in hist]==before
    reopened=mod.TableVStageBudget(b.path,authorization=auth,historical_ledgers=hist,worker_lock=b.worker_lock)
    with reopened.arm_context('B1'),context(reopened,'B1','A1'):
        assert reopened.remaining()==0.


def test_highs_build_ac_do_not_consume_native_timeout(tmp_path,monkeypatch):
    b,_,_,Model=setup(tmp_path,monkeypatch)
    with b.arm_context('B2'),context(b,'B2','M1'),b.capture_native_methods():
        for solver in ('HIGHS','BUILD','FORECAST','AC'):
            b.record_external('RELEASE_P1:M1:'+solver,8000.,solver=solver)
        assert b.remaining()==1800. and b.used()==0.
        b.solve(Model(),label='RELEASE_P1:M1:JOINT',cap=1800.)
        assert b.remaining()==1798.
    assert not any('OVERSHOOT' in str(r.get('status')) for r in b.calls)


def test_p2_unbudgeted_and_wrong_arm_binding_blocked(tmp_path,monkeypatch):
    b,_,_,Model=setup(tmp_path,monkeypatch)
    with b.arm_context('B2'),context(b,'B2','M1'),b.capture_native_methods():
        with pytest.raises(PermissionError,match='UNBUDGETED'):
            Model().optimize()
        with pytest.raises(ValueError,match='P1_ONLY'):
            b.solve(Model(),label='RELEASE_P1:M1:P2',cap=1.)
        with pytest.raises(ValueError,match='P2_ABSOLUTELY'):
            b.native_optimize(Model(),component='P2',requested_seconds=1.)
    with b.arm_context('B3'):
        with pytest.raises(PermissionError,match='EXACT_APPROVED'):
            with b.phase('M1','fixture-case','fixture-source','fixture-parent'):pass
    assert b.used()==0.


def test_unknown_native_runtime_blocks_stage_without_fabrication(tmp_path,monkeypatch):
    b,_,_,Model=setup(tmp_path,monkeypatch)
    with b.arm_context('B2'),context(b,'B2','M1'),b.capture_native_methods():
        m=Model();m.seconds=float('nan')
        b.solve(m,label='RELEASE_P1:M1:FIXTURE',cap=1.)
        assert b.calls[0]['Native_Runtime'] is None
        with pytest.raises(RuntimeError,match='UNKNOWN_NATIVE'):
            b.remaining()
    assert b.used()==0.


def test_new_total_cap_or_cap_change_rejected(tmp_path,monkeypatch):
    _,auth,hist,_=setup(tmp_path,monkeypatch)
    for change in (dict(total_limit_seconds=8400.),dict(total_limit_enabled=True),
                   dict(stage_caps_seconds={'B1:A1':600.})):
        invalid=dict(auth,**change)
        with pytest.raises(PermissionError,match='STAGE_ONLY'):
            mod.TableVStageBudget(tmp_path/'OTHER.json',authorization=invalid,historical_ledgers=hist)


def test_owned_worker_lock_and_no_reset(tmp_path,monkeypatch):
    b,auth,hist,Model=setup(tmp_path,monkeypatch)
    b.worker_lock.write_text('unrelated-worker')
    with b.arm_context('B2'),context(b,'B2','M1'),b.capture_native_methods():
        with pytest.raises(FileExistsError):
            b.solve(Model(),label='RELEASE_P1:M1:FIXTURE',cap=1.)
    assert b.worker_lock.read_text()=='unrelated-worker'
    b.path.unlink()
    with pytest.raises(RuntimeError,match='RESET_FORBIDDEN'):
        mod.TableVStageBudget(b.path,authorization=auth,historical_ledgers=hist,worker_lock=b.worker_lock)


def test_case_repair_carries_prior_native_stage_cost_without_reset(tmp_path,monkeypatch):
    b,auth,hist,Model=setup(tmp_path,monkeypatch)
    with b.arm_context('B1'),context(b,'B1','A1'),b.capture_native_methods():
        m=Model();m.seconds=776.269
        b.solve(m,label='RELEASE_P1:A1:FIXTURE',cap=5400.)
    prior=b.path.read_bytes()
    new=dict(auth,authorization_id='NAMED_REPAIRED_CASE',authorized_ledger_path=str(tmp_path/'REPAIRED.json'),
             carry_forward_ledgers=[mod.file_record(b.path)])
    repaired=mod.TableVStageBudget(tmp_path/'REPAIRED.json',authorization=new,historical_ledgers=hist,worker_lock=b.worker_lock)
    assert repaired.used()==pytest.approx(776.269)
    with repaired.arm_context('B1'),context(repaired,'B1','A1'):
        assert repaired.remaining()==pytest.approx(4623.731)
    with repaired.arm_context('B3'),context(repaired,'B3','A1'):
        assert repaired.remaining()==5400.
    assert b.path.read_bytes()==prior and repaired.document['prior_arm_stage_costs_reset'] is False
    reopened=mod.TableVStageBudget(repaired.path,authorization=new,historical_ledgers=hist,worker_lock=b.worker_lock)
    assert reopened.used()==pytest.approx(776.269)


def test_case_repair_refuses_inflight_or_unknown_native_parent(tmp_path,monkeypatch):
    b,auth,hist,_=setup(tmp_path,monkeypatch)
    document=deepcopy(b.document);document['inflight']={'pid':123}
    b.path.write_text(__import__('json').dumps(document),encoding='utf8')
    new=dict(auth,authorization_id='BAD_PARENT',authorized_ledger_path=str(tmp_path/'BAD.json'),
             carry_forward_ledgers=[mod.file_record(b.path)])
    with pytest.raises(ValueError,match='COMPLETED_SAME'):
        mod.TableVStageBudget(tmp_path/'BAD.json',authorization=new,historical_ledgers=hist,worker_lock=b.worker_lock)
