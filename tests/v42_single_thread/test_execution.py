"""Negative execution gates and a P2 counterexample to P1 degradation."""
import json
from types import SimpleNamespace
import numpy as np
import pytest

def test_external_python_candidate_blocks_start(monkeypatch):
    from v42_single_thread import resources as r
    from v42_single_thread.common import ENV
    for key in ENV:monkeypatch.setenv(key,'1')
    monkeypatch.setattr(r.psutil,'cpu_percent',lambda interval=None:0.)
    monkeypatch.setattr(r,'snapshot',lambda:dict(heavy_processes=[dict(pid=123,self=False)]))
    records=[];monkeypatch.setattr(r,'write',lambda name,value:records.append(value))
    with pytest.raises(RuntimeError,match='SINGLE_WORKER_GATE_BLOCKED'):r.exclusive_gate('test')
    assert records[0]['external_python_or_solver_candidates']==[dict(pid=123,self=False)]

def test_oversubscribed_environment_blocks_start(monkeypatch):
    from v42_single_thread import resources as r
    from v42_single_thread.common import ENV
    for key in ENV:monkeypatch.setenv(key,'1')
    monkeypatch.setenv('OMP_NUM_THREADS','4')
    monkeypatch.setattr(r.psutil,'cpu_percent',lambda interval=None:0.)
    monkeypatch.setattr(r,'snapshot',lambda:dict(heavy_processes=[dict(pid=123,self=True)]))
    monkeypatch.setattr(r,'write',lambda *args:None)
    with pytest.raises(RuntimeError,match='SINGLE_WORKER_GATE_BLOCKED'):r.exclusive_gate('test')

@pytest.mark.parametrize('mode',[None,'UNAPPROVED_NATIVE_MULTIOBJECTIVE'])
def test_A1_requires_authorized_lexicographic_mode_before_build(monkeypatch,tmp_path,mode):
    from v42_single_thread import a1
    monkeypatch.setattr(a1,'configure',lambda:None);monkeypatch.setattr(a1,'OUT',tmp_path)
    if mode:(tmp_path/'A1_LEXICOGRAPHIC_EXECUTION_AUTHORITY.json').write_text(json.dumps(dict(mode=mode)),encoding='utf8')
    with pytest.raises(ValueError,match='A1_OPTIMIZE_CALL_INTERPRETATION_PENDING|UNSUPPORTED_A1_EXECUTION_MODE'):a1.run()

def test_P2_cannot_trade_away_accepted_P1(monkeypatch,tmp_path):
    import gurobipy as gp
    from v42_single_thread import m1
    from v42_integrated.matrix import arrays
    monkeypatch.setattr(m1,'OUT',tmp_path);monkeypatch.setattr(m1,'LOCAL',tmp_path)
    monkeypatch.setattr(m1,'exclusive_gate',lambda *args:None)
    monkeypatch.setattr(m1,'write',lambda *args:None)
    (tmp_path/'M1_OBJECTIVE_CONTRACT.json').write_text(json.dumps(dict(movement_energy_coefficients={'move':1.},movement_count_variables=['move'])),encoding='utf8')
    np.savez(tmp_path/'M1_FINAL_POINT.npz',values=np.array([.5,1.]))
    model=gp.Model();model.Params.OutputFlag=0;model.Params.LogToConsole=0
    rho=model.addVar(lb=.4,ub=1.,name='rho_max');move=model.addVar(vtype='B',name='move')
    model.addConstr(rho+.1*move>=.55);model.update();A,d=arrays(model)
    class Callback:
        errors=[]
        def __init__(self,**kwargs):pass
        def __call__(self,*args):pass
    def physical(point,columns):
        values=dict(zip(columns['names'],point))
        return dict(PASS=values['rho_max']<=.5+1e-8,movement_energy=float(values['move']),movement_count=int(round(values['move'])))
    solve=SimpleNamespace(model=lambda kind:model,Monitor=Callback,full_arrays=lambda:(A,d),physical=physical,finite=float,MIP_POLICY=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,TimeLimit=1800))
    telemetry=SimpleNamespace(active_model=None,policy_violations=[],sample=lambda *args:None)
    p1=dict(UB=.5,LB=.5,gap=0.)
    result=m1.p2(solve,telemetry,p1)
    assert result['accepted'] and result['movement_energy']==1 and result['movement_count']==1
    assert all(r['P1_no_degradation'] for r in result['passes'])
    assert p1==dict(UB=.5,LB=.5,gap=0.)
