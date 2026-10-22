"""Exact unit-pivot view for original Fraction-based Geometry, not Native IO.

Native rows keep their original positive-power2 scale to retain tiny nonzero
coefficients in Gurobi. The original helper oracle expects unit pivots. A
read-only exact dyadic rescaling provides that representation without changing
the oracle algorithm or adding any grid row. Both byte authorities are needed
before a future whole-case interface can be certified.
"""
import numpy as np
import scipy.sparse as sp

def helper_view(A,d,nbase,t,naux=34329):
    B=A.copy().tocsr();v=dict(d,names=np.asarray(d['names'],dtype=object).copy(),
        row_names=np.asarray(d['row_names'],dtype=object).copy(),rhs=np.asarray(d['rhs']).copy())
    eq=np.flatnonzero(d['sense']=='=');assert len(eq)==naux
    diagonal=[]
    for ordinal,i in enumerate(eq):
        a,b=A.indptr[i:i+2]
        # Source injection equations are interleaved P(site),Q(site), while
        # their variables are stored P(all sites),Q(all sites).
        if ordinal<48:
            own=A.indices[a:b];own=own[(own>=nbase)&(own<nbase+48)]
            assert len(own)==1;j=int(own[0])
        else:j=nbase+ordinal
        k=j-nbase;found=np.flatnonzero(A.indices[a:b]==j)
        assert len(found)==1;pivot=float(A.data[a+found[0]])
        assert pivot>0 and np.frexp(pivot)[0]==.5
        reciprocal=1/pivot;old=B.data[a:b].copy();B.data[a:b]*=reciprocal
        assert np.array_equal(B.data[a:b]*pivot,old)
        before=v['rhs'][i];v['rhs'][i]*=reciprocal;assert v['rhs'][i]*pivot==before
        family='injection_grid' if k<48 else 'response_'+str(d['names'][j]).split('[',1)[0].rsplit('_',1)[0]
        v['names'][j]=f'{family}[{t},{k}]';v['row_names'][i]=f'{family}_binding[{t},{k}]'
        diagonal.append(pivot)
    return B,v,dict(equality_rows=len(eq),positive_binary_power_scales=True,
        every_coefficient_and_RHS_exact_roundtrip=True,original_Native_rows_changed=False,
        minimum_pivot=float(min(diagonal)),maximum_pivot=float(max(diagonal)))
