"""Certificate-only implied global boxes; the native model is NEVER changed.

Use only original scientific rows with no local/candidate coefficient. For
nonnegative global variables, a positive coefficient gives an upper bound once
all negative-coefficient variables have finite upper bounds. Sparse-dot and
division errors round outward. Store the source rows and dependency steps.
"""
from dataclasses import replace
import numpy as np
import scipy.sparse as sp

def implied_upper(snapshot,global_rows,n,resource_rows):
    if np.any(snapshot.lower[:n]!=0):raise ValueError('IMPLIED_BOX_NONNEGATIVE_ZERO_LOWER_REQUIRED')
    excluded=set(resource_rows)
    rows=np.asarray([i for i in global_rows if i not in excluded],dtype=int)
    if snapshot.matrix[rows,n:].nnz:raise ValueError('CANDIDATE_COEFFICIENT_IN_GLOBAL_ONLY_CERTIFICATE_ROW')
    original=snapshot.matrix[rows,:n].tocsr();sense=snapshot.senses[rows];rhs=snapshot.rhs[rows]
    forward=np.flatnonzero(sense!='>');reverse=np.flatnonzero(sense!='<')
    A=sp.vstack((original[forward],-original[reverse]),format='csr');b=np.r_[rhs[forward],-rhs[reverse]]
    source=np.r_[rows[forward],rows[reverse]];orientation=np.r_[np.ones(len(forward)),np.full(len(reverse),-1)]
    A.sum_duplicates();negative=A.copy();negative.data=np.minimum(0,negative.data);negative.eliminate_zeros()
    P=A.tocoo();positive=P.data>0;pr=P.row[positive];pc=P.col[positive];pv=P.data[positive]
    upper=snapshot.upper[:n].copy();upper[upper>=1e100]=np.inf
    counts=np.diff(negative.indptr);eps=np.finfo(float).eps;steps=[];origins={}
    for iteration in range(n+1):
        missing=np.isinf(upper)
        infinite=(abs(negative)>0)@missing.astype(np.int64)
        finite=np.where(missing,0.,upper);products=negative@finite;magnitude=abs(negative)@abs(finite)
        k=2*counts+8;error=np.nextafter(k*eps/(1-k*eps)*np.nextafter(magnitude/(1-k*eps),np.inf)+k*np.nextafter(0.,1.),np.inf)
        lower_dot=np.nextafter(products-error,-np.inf)
        numerator=np.nextafter(b-lower_dot,np.inf)
        eligible=infinite[pr]==0;rr=pr[eligible];cc=pc[eligible];aa=pv[eligible]
        proposed=np.nextafter(numerator[rr]/aa,np.inf)
        if np.any(proposed<0):raise ValueError('ORIGINAL_GLOBAL_ROWS_PROVE_NEGATIVE_BOUND_OR_INVALID_NONNEGATIVE_BOX')
        updated=upper.copy();np.minimum.at(updated,cc,proposed)
        changed=np.flatnonzero(updated<upper)
        if not len(changed):break
        # Persist a deterministic original row attaining each new bound.
        for j in changed:
            choices=np.flatnonzero((cc==j)&(proposed==updated[j]));q=int(choices[0]);row=int(rr[q])
            origins[int(j)]=dict(iteration=iteration,original_row=int(source[row]),orientation=int(orientation[row]),
                upper=float(updated[j]),positive_coefficient=float(aa[q]),lower_dot=float(lower_dot[row]),
                sparse_dot_error_envelope=float(error[row]),native_bounds_changed=False)
        steps.append(dict(iteration=iteration,updated_columns=len(changed),remaining_infinite=int(np.isinf(updated).sum())))
        if np.array_equal(updated,upper):break
        upper=updated
        if not np.any(np.isinf(upper)):break
    return upper,dict(PASS=True,derived_finite=int(np.count_nonzero(np.isfinite(upper)&~np.isfinite(snapshot.upper[:n]))),
        remaining_infinite=int(np.isinf(upper).sum()),steps=steps,origins=origins,
        source_rows_original=True,candidate_rows_excluded=True,box_used_only_in_independent_lower_bound=True,
        native_model_bounds_modified=False,scientific_domain_restricted=False)
