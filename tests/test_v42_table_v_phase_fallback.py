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
    assert rec['adaptive_policy']=='FAST_B' and len(budget.calls)==2 and native.native_seconds==2.
    with np.load(tmp_path/'S0/FAST_A/RAW_ATTRIBUTES.npz') as a:assert a['X'][0]==-7.63e-6
    with np.load(tmp_path/'S0/FAST_B/RAW_ATTRIBUTES.npz') as a:assert a['X'][0]==0.
    assert raw['X'][0]==0. and model.disposed
    assert [c['cap'] for c in budget.calls]==[30.,180.]

def test_source_drift_blocks_before_model_and_native(tmp_path,monkeypatch):
    native,model,budget,source=setup(tmp_path,monkeypatch);source.write_text('changed')
    with pytest.raises(PermissionError,match='FROZEN_SOURCE'):native.solve(snapshot(),tmp_path/'S0','PHASE_I')
    assert not budget.calls

def test_reserved_integer_allowance_blocks_phase_only(tmp_path,monkeypatch):
    native,model,budget,source=setup(tmp_path,monkeypatch);budget.native=2400.
    with pytest.raises(RuntimeError,match='RESERVED_ORIGINAL_INTEGER'):native.solve(snapshot(),tmp_path/'S0','PHASE_I')
    assert not budget.calls and model.disposed
