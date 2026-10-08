from fractions import Fraction as F
from itertools import product
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_may10_prestart_rescue.cuts import shift_cover_cuts,append_cuts


def test_all_integer_schedules_and_continuous_lane_satisfy_shift_covers():
    s=LinearSnapshot(sp.csr_matrix([[38.,25.,2.,.5]]),np.zeros(4),np.full(4,148.),
        np.array(['=']),np.array([74.]),np.array(['I','I','I','C']),
        (Objective('prestart_relocation',((0,F(1)),)),
         Objective('shift_magnitude',((0,F(38)),(1,F(25)),(2,F(2)),(3,F(1,2)))))).require()
    cuts=shift_cover_cuts(s,0,np.arange(4))
    strengthened=append_cuts(s,cuts,np.arange(4));count=0
    for integers in product(range(3),range(4),range(38)):
        residual=74-sum(a*x for a,x in zip((38,25,2),integers))
        if residual<0:continue
        point=np.array((*integers,2*residual),dtype=float);count+=1
        assert np.all(strengthened.matrix[1:]@point<=strengthened.rhs[1:])
        assert all(3 not in c['columns'] for c in cuts)
    assert count>40
    # This fractional original LP point is deliberately cut, while no original
    # feasible integer point is removed.
    point=np.array([74/38,0,0,0])
    assert s.matrix@point==74
    assert any(strengthened.matrix[1:]@point>strengthened.rhs[1:])


def test_shift_cover_requires_actual_nonnegative_original_lock():
    s=LinearSnapshot(sp.csr_matrix([[38.,-1.]]),np.zeros(2),np.full(2,80.),
        np.array(['=']),np.array([74.]),np.full(2,'I'),
        (Objective('prestart_relocation',((0,F(1)),)),
         Objective('shift_magnitude',((0,F(38)),(1,F(-1)))))).require()
    with pytest.raises(ValueError,match='NONNEGATIVE_FULL_SHIFT'):
        shift_cover_cuts(s,0,np.arange(2))
