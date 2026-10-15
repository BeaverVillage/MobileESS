"""Exact cache reuse must never merge RHS, senses, axes or small coefficients."""
import numpy as np
from scipy import sparse
from v42_supercompact import presolve

def data(A,rhs,senses):
    return dict(names=np.array(['x'+str(i) for i in range(A.shape[1])]),
        lower=np.full(A.shape[1],-np.inf),upper=np.full(A.shape[1],np.inf),types=np.array(['C']*A.shape[1]),
        objective=np.zeros(A.shape[1]),constant=np.asarray(0.),rhs=np.array(rhs),sense=np.array(senses),
        row_names=np.array(['r'+str(i) for i in range(A.shape[0])]))

def test_dyadic_memo_preserves_rhs_senses_and_column_axes():
    A=sparse.csr_matrix([[2.,4.,0.],[2.,4.,0.],[2.,4.,0.],[-2.,-4.,0.],[0.,2.,4.]])
    p=presolve.Presolve(A,data(A,[6.,8.,6.,-6.,6.],['<','<','=','>','<']))
    count,categories=p.row_scan()
    assert count==2 and list(p.row_ids)==[0,2,4]
    assert categories['PROPORTIONAL']==2

def test_smallest_nonzero_coefficient_is_preserved():
    tiny=np.nextafter(0.,1.);A=sparse.csr_matrix([[tiny,1.],[tiny,1.],[0.,1.]])
    p=presolve.Presolve(A,data(A,[1.,1.,1.],['<']*3));p.row_scan()
    assert list(p.row_ids)==[0,2] and p.A.data[0]==tiny
