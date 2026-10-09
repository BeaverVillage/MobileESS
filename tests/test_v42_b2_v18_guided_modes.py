from types import SimpleNamespace as NS
from contextlib import nullcontext
import numpy as np
import pytest
from v42_b2_seed_recovery_v18r3 import initialization as init

def test_modes_come_from_same_day_dispatch_and_do_not_change_the_point():
    names=np.array(['Pch[M1,S1,0]','Pdis[M1,S1,0]','charge_mode[M1,0]',
        'Pch[M1,S1,1]','Pdis[M1,S1,1]','charge_mode[M1,1]','charge_mode[M1,2]'])
    point=np.array([20.,0.,.17,0.,30.,.83,.5]);before=point.copy()
    patterns=init.mode_patterns(NS(d=dict(names=names)),point)
    assert patterns[0][1]=={('M1',0):1.,('M1',1):0.,('M1',2):0.}
    assert patterns[1][1]=={('M1',0):0.,('M1',1):1.,('M1',2):1.}
    assert np.array_equal(before,point)

def test_relaxed_guide_is_never_admitted_without_full_candidate_validation(tmp_path,monkeypatch):
    guide=np.array([.2,.8]);discrete_point=np.array([1.,0.])
    case=NS(graph=(['S'],{'M1':'S'},[('S',t,'S',t+1,None) for t in range(96)],None,None),
        d=dict(names=np.array(['charge_mode[M1,0]','node_activity[M1,S,0]'])),A=NS(shape=(1,2)),output=tmp_path)
    class Model:
        Params=NS();SolCount=1;Status=2
        def addMConstr(self,*a,**kw):pass
        def getVars(self):return [0,1]
        def getAttr(self,*a):return guide
        def update(self):pass
        def dispose(self):pass
    monkeypatch.setattr(init.original,'_model',lambda *a,**kw:(Model(),{}))
    monkeypatch.setattr(init,'values_for',lambda *a:(np.array([0,1]),np.array([0.,1.])))
    monkeypatch.setattr(init,'mode_patterns',lambda *a:[('test',{('M1',0):True})])
    checked=[]
    def candidate(*a):checked.append('FULL');return discrete_point,{'PASS':True},tmp_path/'FULL.json'
    monkeypatch.setattr(init,'candidate_lp',candidate)
    def admit(c,p,*a):
        assert checked==['FULL'] and p is discrete_point and p is not guide
        init.atomic(tmp_path/'SEED_BYPASS_CERTIFIED_DISPATCH.json',{})
        return p
    monkeypatch.setattr(init,'admit',admit)
    budget=NS(calls=[dict(track='M_MODE_GUIDE',Native_Runtime=1.)],native_optimize=lambda *a,**k:None)
    assert init.initialize(case,budget,None) is discrete_point

def test_failed_candidate_does_not_admit_relaxation_or_declare_full_infeasible(tmp_path,monkeypatch):
    case=NS(graph=(['S'],{'M1':'S'},[('S',t,'S',t+1,None) for t in range(96)],None,None),
        d=dict(names=np.array(['charge_mode[M1,0]'])),A=NS(shape=(1,1)),output=tmp_path)
    class Model:
        Params=NS();SolCount=0;Status=11
        def addMConstr(self,*a,**kw):pass
        def getVars(self):return [0]
        def update(self):pass
        def dispose(self):pass
    monkeypatch.setattr(init.original,'_model',lambda *a,**k:(Model(),{}))
    monkeypatch.setattr(init,'values_for',lambda *a:(np.array([0]),np.array([0.])))
    monkeypatch.setattr(init,'admit',lambda *a:pytest.fail('relaxation never admitted'))
    monkeypatch.setattr(init,'fallback',lambda *a:'UNCHANGED_BOUNDED_FALLBACK')
    budget=NS(native_optimize=lambda *a,**k:None)
    assert init.initialize(case,budget,None)=='UNCHANGED_BOUNDED_FALLBACK'
