from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_practical.global_bounds import implied_upper

def test_global_implied_boxes_are_outward_original_constraints_not_native_bound_edits():
    # x <= 2; y - 3*x <= 1; z/3-y <= 1. Nonbinary exact division is
    # handled by outward bounds, not by compiling rounded scientific boxes.
    s=LinearSnapshot(sp.csr_matrix([[1.,0.,0.],[-3.,1.,0.],[0.,-1.,float(Fraction(1,3))]]),np.zeros(3),np.full(3,np.inf),
        np.full(3,'<'),np.array([2.,1.,1.]),np.full(3,'C'),(Objective('rho',(),0),)).require()
    u,r=implied_upper(s,(0,1,2),3,())
    assert r['PASS'] and r['remaining_infinite']==0 and np.all(np.isinf(s.upper))
    assert Fraction(float(u[0]))>=2 and Fraction(float(u[1]))>=7
    assert Fraction(float(u[2]))>=(Fraction(8)/Fraction(float(Fraction(1,3))))
    assert u[0]<2.00000001 and u[1]<7.00000001 and u[2]<24.00000001

def test_candidate_row_bounds_cannot_be_used_as_full_domain_global_certificate():
    s=LinearSnapshot(sp.csr_matrix([[1.,-1.]]),np.zeros(2),np.full(2,np.inf),np.array(['<']),np.array([0.]),np.full(2,'C'),(Objective('rho',(),0),)).require()
    with pytest.raises(ValueError,match='CANDIDATE_COEFFICIENT'):implied_upper(s,(0,),1,())
    u,r=implied_upper(s,(0,),1,(0,))
    assert np.isinf(u[0]) and r['remaining_infinite']==1
