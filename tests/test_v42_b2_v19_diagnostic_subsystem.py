from types import SimpleNamespace as NS
import numpy as np
from scipy import sparse
from v42_b2_seed_recovery_v19.diagnostic_benchmark import diagnostic_subsystem
from v42_b2_seed_recovery_v19.common import atomic

def test_subsystem_is_diagnostic_only_preserves_original_rows_and_case(tmp_path):
    A=sparse.csr_matrix(np.array([[1.,0.,0.],[0.,1.,0.],[1.,-1.,0.],[0.,1.,0.],[1.,0.,0.]]))
    d=dict(names=np.array(['Pch[M1,S0,0]','Pch[M1,STA2,0]','arc[M1,0]']),
        row_names=np.array(['voltage_upper[0,1]','line_thermal_face[0,1]','energy_balance[M1,0]','PCS16[0]','PCS16[1]']),
        rhs=np.zeros(5),sense=np.array(['<']*5))
    case=NS(A=A,d=d,graph=(None,None,[('S0',0,'S0',1,None)],None,None),case_sha='case')
    atomic(tmp_path/'INITIALIZATION_FAILURE_CONSTRAINT_ANALYSIS.json',dict(original_stationary_background_failures=[]))
    candidate,rows=diagnostic_subsystem(case,dict(paths={'M1':[0]}),np.array([2]),np.array([1.]),tmp_path)
    assert rows.tolist()==[0,2,4]
    assert np.array_equal(candidate.A[:3].toarray(),A[rows].toarray())
    assert candidate.d['row_names'][-1]=='FIXED_arc[M1,0]'
    assert candidate.A.shape==(4,3) and case.A.shape==(5,3)
    assert np.array_equal(d['rhs'],np.zeros(5)) and np.array_equal(case.A.toarray(),A.toarray())
