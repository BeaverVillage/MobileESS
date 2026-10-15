from types import SimpleNamespace
import json
import numpy as np
import pytest
from v42_integration import table_v_dw as dw
from v42_integration.m_engine import file_record
from tests.test_v42_table_v_phase_policy import snapshot

class Model:
    def __init__(self):self.Params=SimpleNamespace();self.disposed=False
    def setParam(self,k,v):setattr(self.Params,k,v)
    def setObjective(self,*args):pass
    def reset(self):pass
    def getAttr(self,name):return self.raw[name]
    def dispose(self):self.disposed=True

class Budget:
    def __init__(self):self.native=0.;self.calls=[]
    def remaining(self):return 4100.-self.native
    def solve(self,model,**kw):
        self.native+=1.;model.Status=2;model.SolCount=1;model.Runtime=1.;model.Work=1.;model.ObjVal=0.
        model.raw=dict(X=np.array([-7.63e-6 if not self.calls else 0.]),Pi=np.array([1.]),RC=np.array([0.]))
        self.calls.append(kw);return dict(Native_Runtime=1.,label=kw['label'])

def setup(tmp_path,monkeypatch):
    from v42_a_stage_domain_v2 import stress_backend
    from v42_integration import table_v_resources
    model=Model();monkeypatch.setattr(stress_backend,'materialize',lambda *a:(model,[('Phi',0.)]))
    monkeypatch.setattr(table_v_resources,'admit_resources',lambda *a,**k:dict(PASS=True))
    source=tmp_path/'frozen.py';source.write_text('unchanged')
    (tmp_path/'DW_SOURCE_FREEZE.json').write_text(json.dumps(dict(sources=[file_record(source)])))
    case=SimpleNamespace(table_v_day='2025-05-01',data=[dict(day='2025-05-01')],stage='A1',case_sha='case')
    budget=Budget();return dw.CurrentNative(budget,case,tmp_path),model,budget,source

def test_real_production_native_adapter_falls_back_without_changing_raw(tmp_path,monkeypatch):
    native,model,budget,source=setup(tmp_path,monkeypatch)
    rec,raw=native.solve(snapshot(),tmp_path/'S0','PHASE_I')
    assert rec['adaptive_policy']=='ACCURATE_C' and len(budget.calls)==2 and native.native_seconds==2.
    with np.load(tmp_path/'S0/FAST_B/RAW_ATTRIBUTES.npz') as a:assert a['X'][0]==-7.63e-6
    with np.load(tmp_path/'S0/ACCURATE_C/RAW_ATTRIBUTES.npz') as a:assert a['X'][0]==0.
    assert raw['X'][0]==0. and model.disposed
    assert [c['cap'] for c in budget.calls]==[900.,300.]

def test_source_drift_blocks_before_model_and_native(tmp_path,monkeypatch):
    native,model,budget,source=setup(tmp_path,monkeypatch);source.write_text('changed')
    with pytest.raises(PermissionError,match='FROZEN_SOURCE'):native.solve(snapshot(),tmp_path/'S0','PHASE_I')
    assert not budget.calls

def test_reserved_integer_allowance_blocks_phase_only(tmp_path,monkeypatch):
    native,model,budget,source=setup(tmp_path,monkeypatch);budget.native=2400.
    with pytest.raises(RuntimeError,match='RESERVED_ORIGINAL_INTEGER'):native.solve(snapshot(),tmp_path/'S0','PHASE_I')
    assert not budget.calls and model.disposed


def test_time_limit_does_not_cold_restart_other_numeric_policy(tmp_path,monkeypatch):
    native,model,budget,source=setup(tmp_path,monkeypatch)
    def timeout(current,**kwargs):
        budget.calls.append(kwargs);budget.native+=900.
        current.Status=9;current.SolCount=0;current.Runtime=900.;current.Work=125.
        return dict(Native_Runtime=900.,status=9)
    budget.solve=timeout
    rec,raw=native.solve(snapshot(),tmp_path/'S0','PHASE_I')
    assert len(budget.calls)==1 and rec['status']==9 and raw=={}
    assert native.native_seconds==900. and model.disposed


def test_s1_receives_only_unused_s0_phase_allowance(tmp_path,monkeypatch):
    native,model,budget,source=setup(tmp_path,monkeypatch)
    native.calls=[dict(component='PHASE_I',native_seconds=111.)]
    native.native_seconds=111.;budget.native=111.
    def timeout(current,**kwargs):
        budget.calls.append(kwargs);current.Status=9;current.SolCount=0
        current.Runtime=kwargs['cap'];current.Work=1.
        return dict(Native_Runtime=current.Runtime,status=9)
    budget.solve=timeout
    native.solve(snapshot(),tmp_path/'S1','PHASE_I')
    assert len(budget.calls)==1 and budget.calls[0]['cap']==789.
    assert native.native_seconds==900.


def test_resumed_adapter_cannot_reopen_existing_stage_phase_clock(tmp_path,monkeypatch):
    native,model,budget,source=setup(tmp_path,monkeypatch);native.case.arm='B1'
    budget.document=dict(calls=[dict(solver='GUROBI',label='RELEASE_P1:A1:DW:PHASE_I:FAST_B',
        Native_Runtime=816.,stage_context=dict(day='2025-05-01',arm='B1',stage='A1'))])
    resumed=dw.CurrentNative(budget,native.case,tmp_path)
    def timeout(current,**kwargs):
        budget.calls.append(kwargs);current.Status=9;current.SolCount=0
        current.Runtime=kwargs['cap'];current.Work=1.
        return dict(Native_Runtime=current.Runtime,status=9)
    budget.solve=timeout
    resumed.solve(snapshot(),tmp_path/'RESUMED','PHASE_I')
    assert resumed.prior_phase_seconds==816. and budget.calls[0]['cap']==84.
