"""Independent rational certificate verifier over captured restricted matrix."""
from fractions import Fraction
from collections import defaultdict,Counter
import sys
import numpy as np
import scipy.sparse as sp
from .common import *
def verify(folder):
    a=sp.load_npz(folder/'EXPANDED_MATRIX.npz');z=dict(np.load(folder/'EXPANDED_ATTRIBUTES.npz'))
    ray=dict(np.load(folder/'RAW_FARKAS.npz'))['ray'];names=dict(np.load(folder/'NATIVE_NAMES.npz'))
    weights=[Fraction(float(x)) for x in ray];totals=defaultdict(Fraction);rhs=Fraction(0);rows=[];bad=[];signs=True
    for i in np.flatnonzero(ray):
        w=weights[i];s=str(z['sense'][i]);signs &= not(s=='<' and w<0 or s=='>' and w>0)
        rhs+=w*Fraction(float(z['rhs'][i]));start,end=a.indptr[i:i+2]
        for j,c in zip(a.indices[start:end],a.data[start:end]):totals[int(j)]+=w*Fraction(float(c))
        rows.append(dict(row=int(i),name=str(names['rows'][i]),multiplier=str(w),sense=s))
    minimum=Fraction(0)
    for j,c in totals.items():
        if not c:continue
        b=float(z['lb'][j] if c>0 else z['ub'][j])
        if not np.isfinite(b) or abs(b)>=1e100:bad.append(dict(variable=j,name=str(names['vars'][j]),coefficient=str(c)))
        else:minimum+=c*Fraction(b)
    allowance=Fraction(1e-5)*(sum(abs(w) for w in weights)+sum(abs(c) for c in totals.values()))
    result=dict(PASS=bool(signs and not bad and minimum-rhs>allowance),minimum=str(minimum),rhs=str(rhs),margin=str(minimum-rhs),
        residual_allowance=str(allowance),row_signs_valid=bool(signs),unbounded_nonzero_terms=bad,weighted_rows=rows,
        row_family_counts=dict(Counter(x['name'].split('[')[0] for x in rows)),matrix=record(folder/'EXPANDED_MATRIX.npz'),raw=record(folder/'RAW_FARKAS.npz'),optimizer_calls=0,
        tolerance_ignored_terms=0)
    atomic(folder/'INDEPENDENT_EXACT_CERTIFICATE.json',result)
    print('EXACT_NEW_CERT',result['PASS'],'margin',float(minimum-rhs),'families',result['row_family_counts'],'bad',bad[:4],flush=True)
    return result
if __name__=='__main__':verify(Path(sys.argv[1]))
