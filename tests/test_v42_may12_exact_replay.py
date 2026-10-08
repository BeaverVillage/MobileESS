from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_may12_rescue.exact import replay

def test_dyadic_replay_catches_cancellation_hidden_by_float_dot():
    s=LinearSnapshot(sp.csr_matrix([[1e16,1.,-1e16]]),np.zeros(3),np.ones(3),np.array(['=']),np.array([0.]),
        np.array(['C']*3),(Objective('rho',(),0),))
    r=replay(s,np.ones(3))
    assert not r['PASS'] and r['exact_max_row_violation']=='1'

def test_exact_dyadic_zero_and_original_tolerance():
    s=LinearSnapshot(sp.csr_matrix([[.25,-.5]]),np.zeros(2),np.ones(2),np.array(['=']),np.array([0.]),
        np.array(['C']*2),(Objective('rho',(),0),))
    assert replay(s,np.array([1.,.5]))['PASS']
    assert not replay(s,np.array([1.,.6]))['PASS']
