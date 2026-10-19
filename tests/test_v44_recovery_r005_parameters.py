"""Read the real Joint constructor's applied parameters without any optimize."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest


@pytest.mark.parametrize('day,arm,stage',[('2025-05-02','B2','M1'),('2025-05-03','B2','M1'),('2025-05-05','B3','M1'),('2025-05-05','B3','M2')])
def test_joint_constructor_reads_effective_scoped_parameters(day,arm,stage,tmp_path):
    import gurobipy as gp
    from v44 import q250_m4_v2 as q
    from v44.frozen.v43_mess.library import load
    from v44_recovery_r005.finite_bound import install
    modules=load();engine=modules['m_engine'];captured={}
    class Params:
        def __setattr__(self,name,value):captured[name]=value
    class Model:
        def __init__(self,*args):self.Params=Params()
        def addMVar(self,*a,**kw):raise RuntimeError('NATIVE0_PARAMETER_CAPTURE_COMPLETE')
        def dispose(self):pass
    request=dict(day=day,arm=arm,stage=stage,Threads=4,worker_slot=1)
    original=dict(engine.APPROVED_JOINT_PARAMETERS)
    with q.install(),install(),q.m_threads(request) as effective,patch.object(gp,'Model',Model):
        with pytest.raises(RuntimeError,match='NATIVE0_PARAMETER_CAPTURE_COMPLETE'):
            engine._native_joint(SimpleNamespace(),SimpleNamespace(),(SimpleNamespace(shape=(1,1)),dict(lower=[0],upper=[1],types=['C'],objective=[1]),None,None,{}),tmp_path,1.)
        for name,value in effective['Joint'].items():assert captured[name]==value,name
        assert captured['MIPGap']==.03 and captured['Threads']==4 and captured['Method']==2
        if day=='2025-05-02':assert captured['BarHomogeneous']==1 and captured['CrossoverBasis']==1
    assert engine.APPROVED_JOINT_PARAMETERS==original
