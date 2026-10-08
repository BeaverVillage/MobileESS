from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_phase1.core import elastic_master,primal_replay,phase_objective,verify_zero
from v42_a_stage_canary.phase import artificial_point

def master():
    s=LinearSnapshot(sp.csr_matrix([[1.]]),np.array([0.]),np.array([3.]),np.array(['<']),np.array([1.]),
        np.array(['C']),(Objective('rho',((0,Fraction(1)),)),)).require()
    return elastic_master(s,(0,))
def test_actual_producer_tuple_is_unpacked_and_infeasible_original_is_preserved():
    m=master();point=artificial_point(m,np.array([2.]))
    assert isinstance(point,np.ndarray) and point[0]==2
    assert primal_replay(m.snapshot,point)['PASS']
    assert phase_objective(m,point)>0 and not verify_zero(m,point)['PASS']
def test_zero_checkpoint_replay_uses_actual_array():
    m=master();point=artificial_point(m,np.array([.5]))
    assert verify_zero(m,point)['PASS'] and phase_objective(m,point)==0
