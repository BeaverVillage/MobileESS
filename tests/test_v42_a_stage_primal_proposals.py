from fractions import Fraction
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_primal.prepare import proposals

def test_integer_transfer_is_only_a_proposal_and_rejects_GPU_overload():
    # One whole-gang histogram changes by one count, preserving cardinality.
    job=SimpleNamespace(gpu=2,service_slots=2)
    unit=dict(uid='u',class_key='c',stay_count=True,optional=False,
        v={'y':{('s',0):('v',6),('s',2):('v',7),('s',4):('v',8)}})
    state=dict(scientific_descriptor={'known':{('s',t):('v',t) for t in range(6)}},
        data=(None,{'u':job}),reference_descriptor={'units':[unit]})
    s=LinearSnapshot(sp.csr_matrix((0,9)),np.zeros(9),np.r_[np.full(6,4.),np.ones(3)],
        np.asarray([],dtype='U1'),np.zeros(0),np.r_[np.full(6,'C'),np.full(3,'I')],
        (Objective('shift_magnitude',((7,Fraction(2)),(8,Fraction(4))),Fraction(946)),)).require()
    x=np.array([0.,0.,0.,0.,2.,2.,0.,0.,1.])
    p=proposals(state,s,x,948)
    assert len(p)==1 and (p[0]['source'],p[0]['destination'])==(8,7)
    assert p[0]['scientific_feasibility_claimed'] is False
    assert p[0]['native_solve_required'] is True
    overloaded=x.copy();overloaded[2]=4.
    assert proposals(state,s,overloaded,948)==[]
    assert proposals(state,s,x,950)==[]
