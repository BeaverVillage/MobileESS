"""Independent rational replay of all earlier-rank outer LP certificates."""
import sys
from fractions import Fraction as Q
import numpy as np,scipy.sparse as sp
from .common import *

def main(day):
    base=CASE/day/'ALL_PHYSICAL_RANK_MINIMUM_PROBES';results=[]
    for folder in sorted(base.glob('RANK_*')):
        a=sp.load_npz(folder/'MATRIX.npz');z=dict(np.load(folder/'ATTRIBUTES.npz'));ray=np.load(folder/'RAW_RAY.npz')['ray']
        terms={};rhs=Q(0);norm=Q(0)
        for i in np.flatnonzero(ray):
            w=Q(float(ray[i]));s=str(z['sense'][i])
            if s=='<' and w<0 or s=='>' and w>0:raise ValueError('INDEPENDENT_PREFIX_SIGN')
            norm+=abs(w);rhs+=w*Q(float(z['rhs'][i]));lo,hi=a.indptr[i:i+2]
            for j,c in zip(a.indices[lo:hi],a.data[lo:hi]):terms[int(j)]=terms.get(int(j),Q(0))+w*Q(float(c))
        minimum=Q(0)
        for j,c in terms.items():
            if not c:continue
            bound=float(z['lb'][j] if c>0 else z['ub'][j])
            if not np.isfinite(bound) or abs(bound)>=1e100:raise ValueError('INDEPENDENT_PREFIX_FREE_BOUND')
            minimum+=c*Q(bound)
        allowance=Q(1e-5)*(norm+sum(abs(c) for c in terms.values()));margin=minimum-rhs
        claimed=read(folder/'EXACT_RAY.json')
        if margin<=allowance or margin!=Q(claimed['margin']):raise ValueError('INDEPENDENT_PREFIX_CONTRADICTION')
        results.append(dict(rank=int(folder.name.split('_')[1]),PASS=True,exact_margin=str(margin),allowance=str(allowance),matrix=record(folder/'MATRIX.npz'),raw=record(folder/'RAW_RAY.npz')))
    audit=dict(PASS=len(results)>0 and all(x['PASS'] for x in results),ranks=results,optimizer_calls=0,master_builder_imported=False,
        scope='independent exact algebra over necessary outer prefix model; never full-science feasible or global-minimum assertion',
        integer_minimum_completed=False)
    atomic(base/'INDEPENDENT_EARLIER_RANK_CERTIFICATES.json',audit);print('INDEPENDENT_EARLIER_RANKS_PASS',len(results),flush=True)
if __name__=='__main__':main(sys.argv[1])
