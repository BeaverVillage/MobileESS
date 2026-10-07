from itertools import product
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_cg.cuts import weighted_rounding,strengthen
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective

def test_every_original_integer_histogram_is_retained_but_fractional_tail_is_cut():
    for gpu in ((4,6,8),(2,5,7),(1,2,4),(3,3,3)):
        for R in range(1,16):
            for d in set(gpu):
                weights,U=weighted_rounding(gpu,R,d)
                for y in product(range(5),repeat=3):
                    if sum(g*v for g,v in zip(gpu,y))<=R:assert sum(w*v for w,v in zip(weights,y))<=U
    weights,U=weighted_rounding((4,6,8),9,4)
    assert weights==(1,1,2) and U==2
    assert 8*1.125==9 and weights[2]*1.125>U

def fixture():
    s=LinearSnapshot(sp.csr_matrix([[1.,-4.,-6.,-8.]]),np.zeros(4),np.array([9.,3.,3.,3.]),np.array(['=']),np.zeros(1),np.array(['C','I','I','I']),
        (Objective('shift_magnitude',((1,Fraction(1)),),0),)).require()
    receipt=dict(PASS=True,original_snapshot_sha256=s.fingerprint(),cuts=[dict(original_binding_row=0,known_column=0,
        unchanged_capacity=9,actual_fixed_occupancy_RHS=0,original_columns=[1,2,3],GPU_per_column=[4,6,8],minimum_gpu=4)])
    return s,receipt

def test_actual_native_binding_is_checked_before_strengthening():
    s,r=fixture();a,p=strengthen(s,s,r);assert p['cuts_added']==1 and p['same_integer_feasible_schedules']
    assert np.array_equal(a.matrix.toarray(),[[1.,-4.,-6.,-8.],[0.,1.,1.,2.]])
    assert a.rhs[-1]==2 and a.objectives==s.objectives
    r['cuts'][0]['GPU_per_column'][1]=5
    with pytest.raises(ValueError,match='COEFFICIENT_DRIFT'):strengthen(s,s,r)
