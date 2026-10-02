"""Optional fixture-only exact power-of-two row scaling; production uses identity."""
from dataclasses import replace
import numpy as np
from scipy import sparse
from .exact import q
from v42_benders.canonical import digest_arrays

def scaled(n,exponents):
    e=np.asarray(exponents,dtype=int);assert e.shape==n.b.shape and np.max(abs(e),initial=0)<=20
    factors=np.exp2(e);A=(sparse.diags(factors)@n.A).tocsr();B=(sparse.diags(factors)@n.B).tocsr();b=n.b*factors
    A.sort_indices();B.sort_indices()
    for original,new in [(n.A,A),(n.B,B)]:
        assert np.array_equal(original.indptr,new.indptr) and np.array_equal(original.indices,new.indices)
        for i in range(len(e)):
            for k in range(original.indptr[i],original.indptr[i+1]):assert q(new.data[k])==q(original.data[k])*q(factors[i])
    assert all(q(v)==q(o)*q(f) for v,o,f in zip(b,n.b,factors))
    return replace(n,A=A,B=B,b=b,source_hash=digest_arrays(A.data,B.data,b,n.sense))
