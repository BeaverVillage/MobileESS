from types import SimpleNamespace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_acceptance.global_box import certify

def snapshot(matrix,senses,rhs,lower,upper):
    return SimpleNamespace(matrix=sp.csr_matrix(matrix,dtype=float),senses=np.asarray(senses),rhs=np.asarray(rhs,dtype=float),
        lower=np.asarray(lower,dtype=float),upper=np.asarray(upper,dtype=float),fingerprint=lambda:'TEST_ORIGINAL')

@pytest.mark.parametrize('sense,row,rhs',[('<',1,40),('>',-1,-40),('=',1,40)])
def test_exact_original_row_upper_bound_prices_tiny_negative_residual(sense,row,rhs):
    s=snapshot([[row]],[sense],[rhs],[0],[np.inf]);c=np.array([-1e-20])
    L,p=certify(s,(0,),1,np.zeros(1),c,())
    assert p['PASS'] and p['proofs'][0]['exact_bound']=='40'
    assert Fraction(L)<=Fraction(float(c[0]))*40
    assert np.isinf(s.upper[0]) and p['derived_box_not_installed_in_solver']

def test_candidate_coupling_row_cannot_supply_full_domain_bound():
    s=snapshot([[1]],['<'],[40],[0],[np.inf])
    L,p=certify(s,(0,),1,np.zeros(1),np.array([-1e-20]),(0,))
    assert L is None and not p['PASS']

def test_unbounded_other_variable_cannot_be_silently_assigned_a_finite_bound():
    s=snapshot([[1,-1]],['<'],[40],[0,0],[np.inf,np.inf])
    L,p=certify(s,(0,),2,np.zeros(1),np.array([-1e-20,0]),())
    assert L is None and not p['PASS']

def test_lower_bound_from_original_row_keeps_outward_direction():
    s=snapshot([[1]],['>'],[-3],[-np.inf],[0])
    L,p=certify(s,(0,),1,np.zeros(1),np.array([1e-20]),())
    assert p['PASS'] and p['proofs'][0]['direction']=='lower'
    assert Fraction(L)<=Fraction(1e-20)*-3
