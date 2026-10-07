"""Finite certificate boxes from ALL closed-domain original scientific rows.

Original local boxes participate in interval propagation but are never
changed. Only global upper bounds are derived. Every origin stores the
original row and outward rounding envelope. The native model stays intact.
"""
import numpy as np
import scipy.sparse as sp

def upper_boxes(snapshot,n,check=lambda:None,progress=lambda proof:None):
    if np.any(snapshot.lower<0):raise ValueError('NONNEGATIVE_DOMAIN_REQUIRED')
    senses=snapshot.senses;forward=np.flatnonzero(senses!='>');reverse=np.flatnonzero(senses!='<')
    A=sp.vstack((snapshot.matrix[forward],-snapshot.matrix[reverse]),format='csr')
    b=np.r_[snapshot.rhs[forward],-snapshot.rhs[reverse]]
    source=np.r_[forward,reverse];orientation=np.r_[np.ones(len(forward)),np.full(len(reverse),-1)]
    neg=A.copy();neg.data=np.minimum(0,neg.data);neg.eliminate_zeros()
    coo=A[:,:n].tocoo();positive=coo.data>0;pr=coo.row[positive];pc=coo.col[positive];pv=coo.data[positive]
    u=snapshot.upper.copy();u[u>=1e100]=np.inf;eps=np.finfo(float).eps;counts=np.diff(neg.indptr);origins={};steps=[]
    for iteration in range(n+1):
        check()
        missing=np.isinf(u);infinite=(abs(neg)>0)@missing.astype(np.int64)
        finite=np.where(missing,0.,u);products=neg@finite;magnitude=abs(neg)@abs(finite)
        k=2*counts+8
        if np.any(k*eps>=.5):raise ValueError('PROPAGATION_ERROR_ENVELOPE_INVALID')
        error=np.nextafter(k*eps/(1-k*eps)*np.nextafter(magnitude/(1-k*eps),np.inf)+k*np.nextafter(0.,1.),np.inf)
        lower_dot=np.nextafter(products-error,-np.inf);numerator=np.nextafter(b-lower_dot,np.inf)
        eligible=infinite[pr]==0;rr=pr[eligible];cc=pc[eligible];aa=pv[eligible]
        proposed=np.nextafter(numerator[rr]/aa,np.inf)
        if np.any(proposed<0):raise ValueError('NEGATIVE_IMPLIED_UPPER_BOUND')
        updated=u.copy();np.minimum.at(updated,cc,proposed);changed=np.flatnonzero(updated[:n]<u[:n])
        if not len(changed):break
        for j in changed:
            choices=np.flatnonzero((cc==j)&(proposed==updated[j]));q=int(choices[0]);row=int(rr[q])
            origins[int(j)]=dict(iteration=iteration,original_row=int(source[row]),orientation=int(orientation[row]),
                upper=float(updated[j]),positive_coefficient=float(aa[q]),lower_dot=float(lower_dot[row]),
                sparse_dot_error_envelope=float(error[row]),native_bounds_changed=False)
        steps.append(dict(iteration=iteration,updated_columns=len(changed),remaining_global_infinite=int(np.isinf(updated[:n]).sum())))
        progress(dict(iteration=iteration,steps=steps,origins=origins))
        u=updated
        if not np.any(np.isinf(u[:n])):break
    return u,dict(PASS=True,remaining_global_infinite=int(np.isinf(u[:n]).sum()),remaining_local_infinite=int(np.isinf(u[n:]).sum()),
        origins=origins,steps=steps,source_original_rows=True,closed_full_relevant_domain=True,
        fixed_local_boxes_included=True,boxes_used_only_in_independent_bound=True,native_bounds_modified=False)
