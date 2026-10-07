"""Exact weighted Chvatal rounding of verified nonnegative integer histograms.

For integer nonnegative y, sum(g*y)<=R implies
sum(floor(g/d)*y)<=floor(R/d). No scientific row, variable or objective
is replaced. Every source binding and box is checked independently.
"""
from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp

def weighted_rounding(gpu,residual,divisor):
    if type(residual) is not int or residual<0 or type(divisor) is not int or divisor<=0:raise ValueError('EXACT_NONNEGATIVE_INTEGER_CAPACITY_REQUIRED')
    if any(type(g) is not int or g<=0 for g in gpu):raise ValueError('EXACT_POSITIVE_INTEGER_GPU_REQUIRED')
    return tuple(g//divisor for g in gpu),residual//divisor

def strengthen(original,current,verified_histogram_receipt):
    r=verified_histogram_receipt
    if not r.get('PASS') or r['original_snapshot_sha256']!=original.fingerprint():raise ValueError('QUALIFIED_ORIGINAL_HISTOGRAM_PROOF_REQUIRED')
    n=original.matrix.shape[1];m=original.matrix.shape[0]
    if current.matrix.shape[1]!=n or not np.array_equal(original.lower,current.lower) or not np.array_equal(original.upper,current.upper) or not np.array_equal(original.vtypes,current.vtypes):raise ValueError('UNCHANGED_ORIGINAL_COLUMN_AXES_AND_BOXES_REQUIRED')
    delta=current.matrix[:m]-original.matrix;delta.eliminate_zeros()
    if delta.nnz or not np.array_equal(original.senses,current.senses[:m]) or not np.array_equal(original.rhs,current.rhs[:m]):raise ValueError('ALL_ORIGINAL_ROWS_MUST_REMAIN_UNCHANGED')
    cuts={}
    for source in r['cuts']:
        row=source['original_binding_row'];known=source['known_column'];lo,hi=original.matrix.indptr[row:row+2]
        co=dict(zip(map(int,original.matrix.indices[lo:hi]),map(Fraction,original.matrix.data[lo:hi])))
        capacity=Fraction(float(original.upper[known]));fixed=Fraction(float(original.rhs[row]))
        if original.senses[row]!='=' or co.get(known)!=1 or capacity.denominator!=1 or fixed.denominator!=1 or not 0<=fixed<=capacity:raise ValueError('UNCHANGED_INTEGER_KNOWN_GPU_BINDING_REQUIRED')
        if int(capacity)!=source['unchanged_capacity'] or int(fixed)!=source['actual_fixed_occupancy_RHS']:raise ValueError('QUALIFIED_CAPACITY_DRIFT')
        if any(v>0 or original.lower[j]<0 for j,v in co.items() if j!=known):raise ValueError('DROPPED_OCCUPANCY_MUST_BE_NONNEGATIVE')
        columns=source['original_columns'];gpu=source['GPU_per_column'];D=source['minimum_gpu'];R=int(capacity-fixed)
        for j,g in zip(columns,gpu):
            if original.vtypes[j] not in ('B','I') or original.lower[j]<0 or co.get(j)!=-g:raise ValueError('ACTUAL_INTEGER_HISTOGRAM_COEFFICIENT_DRIFT')
        weights,U=weighted_rounding(gpu,R,D)
        if all(w==1 for w in weights):continue # Existing count row already proves this case.
        terms=tuple((j,w) for j,w in zip(columns,weights) if w)
        if not terms or sum(w*float(original.upper[j]) for j,w in terms)<=U:continue
        key=terms
        proof=dict(source_binding_row=row,known_column=known,capacity=int(capacity),fixed=int(fixed),residual=R,
            divisor=D,integer_nonnegative_columns=list(columns),GPU_per_column=list(gpu),terms=list(terms),upper=U)
        if key not in cuts or U<cuts[key]['upper']:cuts[key]=proof
    ordered=sorted(cuts.values(),key=lambda c:(c['terms'],c['upper']))
    rows=[];cols=[];values=[]
    for i,c in enumerate(ordered):
        for j,w in c['terms']:rows.append(i);cols.append(j);values.append(float(w))
    A=sp.csr_matrix((values,(rows,cols)),shape=(len(ordered),n))
    augmented=replace(current,matrix=sp.vstack((current.matrix,A),format='csr'),senses=np.r_[current.senses,np.full(len(ordered),'<')],rhs=np.r_[current.rhs,[c['upper'] for c in ordered]]).require()
    return augmented,dict(PASS=True,family='EXACT_WEIGHTED_INTEGER_HISTOGRAM_CG_CAPACITY',cuts=ordered,cuts_added=len(ordered),cut_nnz=A.nnz,
        original_snapshot_sha256=original.fingerprint(),input_snapshot_sha256=current.fingerprint(),output_snapshot_sha256=augmented.fingerprint(),
        original_rows_boxes_types_objectives_unchanged=True,same_integer_feasible_schedules=True,same_integer_objective_values=True,
        same_LP_projection_asserted=False,LP_relaxation_strengthened=bool(ordered),native_solve_calls=0,
        proof='floor(g/d)<=g/d, y>=0 integer; integer weighted sum <=R/d implies <=floor(R/d)')
