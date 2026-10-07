import numpy as np
import scipy.sparse as sp
from v42_a_stage_certificates.dual import repair
from v42_a_stage_phase1.core import interval_box_bound

def test_tiny_wrong_infinite_RC_is_never_accepted_and_raw_pi_is_preserved():
    A=sp.eye(2,format='csr');c=np.array([0.,1.]);pi=np.array([2.**-50,1.]);lower=np.zeros(2);upper=np.array([np.inf,2.]);rhs=np.array([-.5,1.]);senses=np.array(['>','>'])
    assert interval_box_bound(A,c,pi,lower,upper,rhs) is None
    certificate,proof=repair(A,c,pi,senses,lower,upper)
    assert proof['PASS'] and proof['removed_rows']==[0] and pi[0]==2.**-50
    L=interval_box_bound(A,c,certificate,lower,upper,rhs)
    assert L is not None and .999999999<L<=1
