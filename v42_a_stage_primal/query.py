"""Temporary primal repair query; it never supplies a domain lower bound."""
from dataclasses import replace
import numpy as np

def fixed_query(locked,point,proposal):
    mask=locked.vtypes!='C'
    if len(point)!=locked.matrix.shape[1] or np.max(abs(point[mask]-np.rint(point[mask])))>1e-5:
        raise ValueError('PRESERVED_ORIGINAL_INTEGER_ASSIGNMENT_REQUIRED')
    integers=np.rint(point).copy();src=proposal['source'];dst=proposal['destination']
    if not mask[src] or not mask[dst]:raise ValueError('ONLY_ORIGINAL_INTEGER_HISTOGRAM_TRANSFER')
    integers[src]-=1;integers[dst]+=1
    lo=locked.lower.copy();hi=locked.upper.copy()
    if np.any(integers[mask]<lo[mask]) or np.any(integers[mask]>hi[mask]):raise ValueError('UNCHANGED_SCIENTIFIC_INTEGER_BOXES_REQUIRED')
    lo[mask]=integers[mask];hi[mask]=integers[mask]
    q=replace(locked,lower=lo,upper=hi,vtypes=np.full(len(lo),'C')).require()
    return q,dict(PASS=True,temporary_query=True,original_rows_objectives_unchanged=True,
        original_integer_assignments_fixed_exactly=True,fixed_integer_columns=int(np.count_nonzero(mask)),
        continuous_scientific_bounds_unchanged=True,global_lower_bound_claimed=False,
        candidate_deletion=False,source=locked.fingerprint(),query=q.fingerprint(),proposal=proposal)
