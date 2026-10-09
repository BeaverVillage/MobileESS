import numpy as np
from scipy import sparse
from types import SimpleNamespace as NS
from v42_b2_seed_recovery_v19.diagnostic_benchmark import substitute_fixed


def test_fixed_substitution_records_original_singleton_rows_and_never_admits_point():
    d=dict(names=np.array(['binary','Pch','Q']),lower=np.array([0.,0.,-1.]),upper=np.array([1.,2.,1.]),types=np.array(['B','C','C']),objective=np.array([0.,1.,0.]),constant=np.array(0.),rhs=np.array([0.,0.,2.]),sense=np.array(['=','<','>']),row_names=np.array(['FIXED_binary','connected_Pch','voltage_lower']))
    case=NS(A=sparse.csr_matrix([[1.,0.,0.],[-2.,1.,0.],[0.,1.,1.]]),d=d,case_sha='case')
    before=case.A.copy();reduced,authority=substitute_fixed(case)
    assert (case.A!=before).nnz==0 and list(case.d['lower'])==[0.,0.,-1.]
    assert authority['diagnostic_only'] and len(authority['singleton_original_row_derivations'])==2
    assert authority['fixed_indices']==[0,1]
    assert reduced.A.shape==(3,1) and reduced.d['rhs'][2]==2
    assert list(reduced.d['row_names'])==list(d['row_names'])
