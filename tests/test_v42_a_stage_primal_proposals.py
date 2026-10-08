from fractions import Fraction
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_primal.prepare import proposals
from v42_a_stage_primal.query import fixed_query

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

def test_primal_repair_fixes_integer_assignment_without_changing_physics():
    s=LinearSnapshot(sp.csr_matrix([[0.,1.,1.],[1.,-2.,-3.]]),np.zeros(3),
        np.array([10.,2.,2.]),np.array(['=','=']),np.array([2.,0.]),np.array(['C','I','I']),
        (Objective('rho',((0,Fraction(1)),)),)).require()
    q,p=fixed_query(s,np.array([4.,2.,0.]),dict(source=1,destination=2))
    assert q.matrix is s.matrix and q.objectives==s.objectives
    assert np.array_equal(q.lower,[0.,1.,1.]) and np.array_equal(q.upper,[10.,1.,1.])
    assert np.array_equal(s.lower,[0.,0.,0.]) and np.array_equal(s.upper,[10.,2.,2.])
    assert np.all(q.vtypes=='C') and p['global_lower_bound_claimed'] is False
    # The fixed exact integer schedule lifts uniquely; only its global
    # continuous physical variable is repaired from 4 to 5.
    assert np.array_equal(q.matrix@np.array([5.,1.,1.]),q.rhs)
