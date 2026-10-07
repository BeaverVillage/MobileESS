import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_lexrefine.partition import split

def test_partition_covers_every_integer_assignment_and_has_safe_right_bound():
    s=LinearSnapshot(sp.csr_matrix((0,2)),np.zeros(2),np.ones(2),np.array([],dtype='U1'),np.array([]),np.full(2,'B'),(Objective('shift_magnitude',((0,2),(1,3))),)).require()
    left,p=split(s,'shift_magnitude',3)
    assert p['both_children_preserved'] and p['right']['valid_LB']==3
    for x in (np.array([a,b]) for a in (0,1) for b in (0,1)):
        obj=2*x[0]+3*x[1]
        assert (obj<=2)!=(obj>=3)
        assert (left.matrix@x<=left.rhs)[0]==(obj<=2)
