from fractions import Fraction as F
from types import SimpleNamespace
import numpy as np
from scipy import sparse
from v42_bap.fullscale import FileRegistry,FullScaleEarlyBAP
from v42_bap.state import BinaryProjection,BranchDecision
from v42_dw_bound.certificate import global_dual,corrected

def test_lazy_column_partition_applies_same_original_binary_to_both_children():
    r=FileRegistry([],None)
    r.columns={'a':SimpleNamespace(mess=0),'b':SimpleNamespace(mess=0),'c':SimpleNamespace(mess=1)}
    points={'a':np.array([0.,1.]),'b':np.array([1.,0.]),'c':np.array([.5,0.])}
    r.point=lambda k:points[k]
    v=BinaryProjection('original_binary',0,0,'arc',((0,1.),))
    a0,_=r.partition(tuple(points),(BranchDecision(v,0),));a1,_=r.partition(tuple(points),(BranchDecision(v,1),))
    assert set(a0)|set(a1)==set(points) and set(a0)&set(a1)=={'c'}
    # Unrelated MESS trajectory is valid in both children; full parent Cartesian
    # domain is partitioned by the MESS0 binary, not by arbitrary lambda ids.
    assert a0==('a','c') and a1==('b','c')

def test_native_negative_pricing_bound_is_paid_not_zeroed_and_rebuilt_exactly():
    A=sparse.csr_matrix([[1.]])
    d=dict(objective=np.array([1.]),constant=np.array(0.),rhs=np.array([.5]),sense=np.array(['>']))
    value,proof=global_dual(A,d,np.array([1.]),np.array([0.]),np.array([1.]))
    alpha=np.array([0.,0.,0.,0.]);bounds=[-.006,0.,0.,0.]
    lb,exact,beta,delta=corrected(value,alpha,bounds)
    assert exact==value+sum(delta,F(0)) and beta[0]<F(float(-.006)) and delta[0]<F(float(-.006))
    assert lb<.5-.006 and F(lb)<=exact

def test_rejected_native_primal_still_has_pre_gate_snapshot(monkeypatch):
    import v42_bap.fullscale as module
    events=[]
    attributes={'Obj':np.array([1.,0.]),'UB':np.array([np.inf,np.inf]),'LB':np.array([0.,0.]),
                'X':np.array([0.,1.+5e-7]),'RHS':np.array([0.,1.]),'Sense':np.array(['=','='])}
    model=SimpleNamespace(Status=2,ObjVal=1.,Params=SimpleNamespace(),getAttr=lambda k:attributes[k],getA=lambda:sparse.eye(2,format='csr'))
    solver=FullScaleEarlyBAP.__new__(FullScaleEarlyBAP);solver.root_pending=False;solver.model=model
    solver.update_columns=lambda n:events.append('columns');solver.optimize=lambda *a:events.append('optimize')
    solver.projection=lambda x:(((.5,),),(0.,))
    monkeypatch.setattr(module,'capture',lambda *a:events.append('durable_snapshot'))
    result=solver.node_solve(SimpleNamespace(node_id=777,column_ids=('k',)),None)
    assert result.status=='PRIMAL_AUDIT_INCONCLUSIVE' and events==['columns','optimize','durable_snapshot']
