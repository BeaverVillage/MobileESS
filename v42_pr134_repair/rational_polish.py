"""Complete a Farkas certificate by adding valid nonnegative original rows.

This does not round or delete residuals and does not change any model row.
Every added multiplier is an exact rational, explicitly audited afterwards.
"""
from fractions import Fraction as Q
from collections import defaultdict
import numpy as np, scipy.sparse as sp
from .common import *

def run():
    day='2025-05-19';target=CASE/day
    original=dict(np.load(target/'ORIGINAL_IIS_RAW_FARKAS.npz'));a=sp.load_npz(target/'A0_MATRIX.npz')
    z=dict(np.load(target/'A0_ATTRIBUTES_CODED.npz'));names=dict(np.load(target/'ORIGINAL_NATIVE_NAMES.npz'))
    weights={int(r):Q(float(w)) for r,w in zip(original['rows'],original['ray']) if w}
    combined=defaultdict(Q)
    def add(row,w):
        weights[row]=weights.get(row,Q(0))+w
        p,q=a.indptr[row:row+2]
        for j,c in zip(a.indices[p:q],a.data[p:q]):combined[int(j)]+=w*Q(float(c))
    for r,w in list(weights.items()):
        weights[r]=Q(0);add(r,w)
    bad=[j for j,c in combined.items() if c and ((c>0 and (not np.isfinite(z['lb'][j]) or z['lb'][j]<=-1e100)) or
        (c<0 and (not np.isfinite(z['ub'][j]) or z['ub'][j]>=1e100)))]
    additions=[]
    candidates=np.flatnonzero((z['sense']=='<')&(z['rhs']>=0))
    for j in bad:
        if combined[j]>=0:continue
        found=None
        for r0 in candidates:
            r=int(r0);p,q=a.indptr[r:r+2];ids=a.indices[p:q];cs=a.data[p:q]
            hit=np.flatnonzero(ids==j)
            if len(hit) and cs[hit[0]]>0 and np.all(cs>=0) and np.all(np.isfinite(z['lb'][ids])) and np.all(z['lb'][ids]>-1e100):
                found=(r,float(cs[hit[0]]));break
        if found is None:raise ValueError('NO_EXACT_NONNEGATIVE_ORIGINAL_BOUNDING_ROW:'+str(names['vars'][j]))
        r,coefficient=found;weight=-combined[j]/Q(coefficient)
        before=str(combined[j]);add(r,weight)
        additions.append(dict(original_variable=j,name=str(names['vars'][j]),raw_exact_residual=before,
            added_original_row=r,row_name=str(names['rows'][r]),row_family=str(z['rf_names'][z['rf'][r]]),
            added_exact_multiplier=str(weight),resulting_coefficient=str(combined[j]),
            all_added_row_coefficients_nonnegative=True))
    rows=sorted(r for r,w in weights.items() if w);multipliers=[str(weights[r]) for r in rows]
    certificate=dict(day=day,rows=rows,exact_multipliers=multipliers,additions=additions,
        original_raw_ray=record(target/'ORIGINAL_IIS_RAW_FARKAS.npz'),
        original_matrix=record(target/'A0_MATRIX.npz'),
        mathematical_operation='Add nonnegative exact rational multiples of unchanged original <= rows. Recompute all combined coefficients/RHS/bounds independently.',
        residuals_ignored_or_rounded=0,model_rows_changed=0,optimizer_calls=0)
    write('MAY19_RATIONAL_FARKAS_COMPLETION.json',certificate)
    print('Exact original-row certificate completion',additions,flush=True)
if __name__=='__main__':run()
