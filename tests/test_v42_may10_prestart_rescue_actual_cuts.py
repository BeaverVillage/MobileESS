from fractions import Fraction as F
from types import SimpleNamespace as NS
from itertools import product
import numpy as np
import scipy.sparse as sp
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_may10_prestart_rescue.cuts import window_cuts,append_cuts


def test_actual_row_and_complete_domain_cut_is_valid_for_all_integer_schedules():
    A=sp.csr_matrix([[1.5,0,0],[1,1,1],[0,3,0]],dtype=float)
    s=LinearSnapshot(A,np.zeros(3),np.full(3,3.),np.array(['<','=','=']),np.array([1.5,3,3]),np.full(3,'I'),
        (Objective('prestart_relocation',((2,F(1)),)),Objective('shift_magnitude',((1,F(3)),)))).require()
    job=NS(reference_site='A',reference_start=0)
    state=dict(grows=[0],axes={('GPU','A',0):0},
        data=({},dict(a=job,b=job,c=job),None,None,None,None,None,dict(classes={'K':['a','b','c']})),
        domains={'a':NS(stays=[(0,'A'),(3,'A'),(0,'B')])},
        reference_descriptor=dict(units=[dict(uid='a',stay_count=True,optional=False,v={'y':{('A',0):('v',0),('A',3):('v',1),('B',0):('v',2)}})]))
    cuts,info=window_cuts(state,s,3)
    assert info['histograms_independently_matched']==1
    assert cuts[0]['lower']==1
    strengthened=append_cuts(s,cuts,np.arange(3))
    original=[]
    for x in product(range(4),repeat=3):
        if x[0]*F(3,2)<=F(3,2) and sum(x)==3 and 3*x[1]==3:
            original.append(x)
            assert strengthened.matrix[-1]@np.array(x)>=strengthened.rhs[-1]
    assert original
