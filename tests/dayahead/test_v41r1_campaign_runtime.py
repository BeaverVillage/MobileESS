from pathlib import Path
import threading
import pytest
from dayahead.paper_analysis.storage import write_json,read
from dayahead.v41r1 import campaign_run as run


def test_current_phase_keeps_original_recursive_verifier(tmp_path,monkeypatch):
    frozen=dict(scientific_commit='current',science={'manifest_SHA':'same'})
    path=tmp_path/'ACTUAL_RECEIPT.json';write_json(path,{**frozen,'status':'COMPLETE'})
    seen=[];monkeypatch.setattr(run,'original_verify',lambda p,f:seen.append((p,f)))
    run.verify_phase(path,frozen);assert seen==[(path,frozen)]


def test_old_actual_requires_narrow_retention_before_readback(tmp_path,monkeypatch):
    from dayahead.v41r1 import migration_retention
    frozen=dict(scientific_commit='new',science={'manifest_SHA':'new'})
    path=tmp_path/'ACTUAL_RECEIPT.json';receipt=dict(scientific_commit='old',science={'manifest_SHA':'old'})
    write_json(path,receipt);seen=[]
    monkeypatch.setattr(migration_retention,'validate',lambda r,s:seen.append(('retention',r,s)))
    monkeypatch.setattr(run,'original_verify',lambda p,f:seen.append(('recursive',p,f)))
    run.verify_phase(path,frozen)
    assert seen==[('retention',receipt,frozen['science']),('recursive',path,None)]


def test_unattested_old_phase_cannot_bypass_retention(tmp_path,monkeypatch):
    from dayahead.v41r1 import migration_retention
    path=tmp_path/'ACTUAL_RECEIPT.json';write_json(path,dict(scientific_commit='old',science={}))
    def reject(*args):raise ValueError('NOT_AUTHORIZED')
    monkeypatch.setattr(migration_retention,'validate',reject)
    monkeypatch.setattr(run,'original_verify',lambda *args:pytest.fail('readback must not bypass source gate'))
    with pytest.raises(ValueError,match='NOT_AUTHORIZED'):run.verify_phase(path,dict(scientific_commit='new',science={}))


def test_completed_B0_actual_adoption_never_runs_solver(tmp_path,monkeypatch):
    monkeypatch.setattr(run,'RUNTIME',tmp_path)
    path=tmp_path/'2025-05-01/B0/actual/ACTUAL_RECEIPT.json';write_json(path,dict(status='COMPLETE'))
    supervisor=run.Supervisor.__new__(run.Supervisor);supervisor.frozen={};supervisor.lock=threading.RLock()
    supervisor.save=lambda:None;seen=[]
    monkeypatch.setattr(run,'verify_phase',lambda p,f:seen.append(p))
    monkeypatch.setattr(run.native.Supervisor,'phase',lambda *args:pytest.fail('completed B0 was recomputed'))
    row=dict(day='2025-05-01',policy='B0');supervisor.phase(row,'actual')
    assert seen==[path] and row['retained_previously_complete']


def test_campaign_fixed_parallelism_and_unlimited_observed_solver(tmp_path):
    import gurobipy as gp
    from dayahead.v41.solver_observer import observe
    assert run.native.WORKERS==4
    m=gp.Model();m.Params.OutputFlag=0;m.Params.SoftMemLimit=.1;m.Params.MemLimit=.2
    m.addVar();m.setObjective(0)
    with observe(tmp_path,'TEST'):
        m.optimize()
        assert m.Params.Threads==4 and m.Params.MemLimit==m.Params.SoftMemLimit==float('inf')
        assert m.Params.NodefileStart==.5 and Path(m.Params.NodefileDir).is_relative_to(tmp_path)
    m.dispose()
