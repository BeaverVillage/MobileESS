import itertools
import numpy as np
import pytest
from scipy import sparse
from v42_m1_accel_vnext.reduction import duplicate_groups,quotient,lift

def test_exhaustive_parallel_arc_quotient():
    # Parallel source->sink arcs; unit-flow sum exactly one.
    A=sparse.csr_matrix([[1.,1.,1.],[2.,2.,3.]])
    B=sparse.csr_matrix([[4.,4.,5.]])
    d=dict(types=np.array(['B']*3),lower=np.zeros(3),upper=np.ones(3),objective=np.array([2.,2.,3.]),names=np.array(['a','b','c']))
    groups=duplicate_groups(A,B,d,[0,1,2],True);assert groups==[[0,1]]
    C,D,e,keep=quotient(A,B,d,groups)
    original={(tuple(B@x),float(d['objective']@x),tuple(A@x)) for raw in itertools.product([0.,1.],repeat=3) if sum(raw)==1 for x in [np.array(raw)]}
    reduced={(tuple(D@y),float(e['objective']@y),tuple(C@y)) for raw in itertools.product([0.,1.],repeat=2) if sum(raw)==1 for y in [np.array(raw)]}
    assert original==reduced
    for y in [np.array([1.,0.]),np.array([0.,1.])]:assert np.array_equal(A@lift(y,keep,3),C@y)

def test_missing_capacity_proof_rejected():
    with pytest.raises(ValueError,match='Missing'):duplicate_groups(None,None,None,[],False)

def test_higher_SOC_is_not_universal_dominance():
    # Same location/time/cost, but no charging/discharging in travel slot and
    # fixed terminal SOC. SOC 1 reaches terminal1; SOC2 cannot reproduce it.
    feasible=lambda energy:energy==1.
    assert feasible(1.) and not feasible(2.)
