import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_lexfull.full_bounds import upper_boxes

def test_candidate_box_proves_global_upper_without_changing_native_model():
    s=LinearSnapshot(sp.csr_matrix([[1.,-3.]]),np.zeros(2),np.array([np.inf,2.]),np.array(['=']),np.array([4.]),np.full(2,'C'),(Objective('rho',()),)).require()
    before=s.fingerprint();u,proof=upper_boxes(s,1)
    assert proof['PASS'] and proof['remaining_global_infinite']==0
    assert u[0]>=10 and u[0]<10.0000001 and u[1]==2
    assert s.fingerprint()==before and np.isinf(s.upper[0])
