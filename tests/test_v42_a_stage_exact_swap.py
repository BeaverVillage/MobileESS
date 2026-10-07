from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_primal.swap import enumerate_swaps,exact_null

def test_same_GPU_swap_closes_shift_and_detects_coupling_drift():
    units=[dict(uid='a',class_key='a',stay_count=True,optional=False,v={'y':{('s',0):('v',2),('s',1):('v',3)}}),
        dict(uid='b',class_key='b',stay_count=True,optional=False,v={'y':{('s',0):('v',4),('s',1):('v',5)}})]
    state=dict(data=(None,{u:SimpleNamespace(gpu=2,service_slots=1) for u in ('a','b')}),reference_descriptor={'units':units})
    A=sp.csr_matrix([[0,0,1,1,0,0],[0,0,0,0,1,1],[1,0,-2,0,-2,0],[0,1,0,-2,0,-2]])
    s=LinearSnapshot(A,np.zeros(6),np.array([4,4,1,1,1,1]),np.full(4,'='),np.array([1,1,0,0]),
        np.array(['C','C','I','I','I','I']),(Objective('shift_magnitude',((3,Fraction(1)),(4,Fraction(1))),Fraction(948)),)).require()
    x=np.array([2.,2.,0.,1.,1.,0.]);p=enumerate_swaps(state,s,x,948)
    assert len(p)==1 and exact_null(A,p[0]['changes'])
    y=x.copy()
    for j,v in p[0]['changes'].items():y[j]+=v
    assert np.array_equal(A@y,s.rhs) and np.all((y>=s.lower)&(y<=s.upper))
    assert y[3]+y[4]+948==948
    drift=A.copy().tolil();drift[3,5]=-3
    assert not exact_null(drift.tocsr(),p[0]['changes'])
