from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_lexcases.definition import define,fix_case

def test_unique_lift_preserves_fractional_LP_and_integer_objective_exactly():
    s=LinearSnapshot(sp.csr_matrix([[1.,1.]]),np.zeros(2),np.ones(2),np.array(['=']),np.array([1.]),np.full(2,'I'),
        (Objective('shift_magnitude',((0,Fraction(2)),(1,Fraction(3))),Fraction(4)),)).require()
    e,p=define(s,'shift_magnitude');assert p['PASS'] and p['same_LP_projection'] and not p['artificial_variable']
    for a in (0.,.25,.5,1.):
        x=np.array([a,1-a]);Z=4+2*x[0]+3*x[1];lift=np.r_[x,Z]
        assert np.array_equal(e.matrix@lift,e.rhs)
        assert e.objective('shift_magnitude').coefficients()=={2:Fraction(1)}
    case=fix_case(e,2,6);assert case.lower[2]==case.upper[2]==6
