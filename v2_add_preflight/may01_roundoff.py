"""Outward-error check against original dyadic matrix coefficients.

The support bound uses the projected expressions; this independent audit adds
a conservative floating-point projection/dot-product allowance computed from
absolute ORIGINAL components, including cancellation, before certifying a row.
"""
import numpy as np
import scipy.sparse as sp
from .may01_common import *

def run():
    init();start=__import__('time').perf_counter();results=[];total=0
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:nbase=len(z['names'])
    box=np.r_[np.full(24,300.),np.full(24,250.)]
    eps=np.finfo(float).eps;gamma=100*eps/(1-100*eps)
    for t in range(96):
        guard(start);p=RUN/'compact'/f'{t:02d}'
        A=sp.load_npz(PACK/f'{t:02d}'/'MATRIX.npz');C=sp.load_npz(p/'RECONSTRUCTION.npz')
        a=np.load(p/'RECONSTRUCTION_CONSTANT.npy')
        with np.load(PACK/f'{t:02d}'/'ROWS.npz') as z:r={k:z[k] for k in ('rhs','sense')}
        with np.load(PACK/f'{t:02d}'/'DOMAIN.npz') as z:d={k:z[k] for k in ('lower','upper')}
        with np.load(p/'ROWS.npz') as z:cr={k:z[k] for k in ('upper','rhs','safe','ids','margin')}
        lo=nbase+t*34329;non=np.flatnonzero(r['sense']!='=');E=abs(A[non,lo+48:lo+34329])
        # Each original face has <=3 eliminated auxiliaries. Gamma100 exceeds
        # the product/summation count in projection, support and RHS evaluation.
        assert np.diff(E.indptr).max(initial=0)<=3
        components=(abs(A[non,lo:lo+48])@box+E@(abs(C)@box)+E@abs(a)+abs(r['rhs'][non]))
        budgets=[gamma*(1+components)]
        for which,bound in [(np.flatnonzero(d['upper'][48:]<1e90),d['upper'][48:]),
                            (np.flatnonzero(d['lower'][48:]>-1e90),d['lower'][48:])]:
            budgets.append(gamma*(1+(abs(C[which])@box)+abs(a[which])+abs(bound[which])))
        error=np.nextafter(np.concatenate(budgets),np.inf);safe=cr['safe']
        conservative_upper=np.nextafter(cr['upper']+error,np.inf)
        gap=cr['rhs']-cr['margin']-conservative_upper
        assert np.all(gap[safe]>=0),'ORIGINAL_COMPONENT_ROUNDING_PROOF_FAILED'
        archive=p/'ROUNDING_AWARE_SAFE_ROW_PROOFS.npz'
        np.savez_compressed(archive,ids=cr['ids'][safe],conservative_original_upper=conservative_upper[safe],
            original_projected_RHS=cr['rhs'][safe],margin=cr['margin'][safe],projection_error_budget=error[safe])
        total+=int(safe.sum());results.append(dict(slot=t,rows=int(safe.sum()),
            minimum_proof_headroom=float(gap[safe].min()),maximum_projection_allowance=float(error[safe].max()),archive=record(archive)))
    put('ORIGINAL_COMPONENT_ROUNDING_BOUND_AUDIT.json',dict(PASS=True,rows=total,gamma100=gamma,
        uses_absolute_original_components_to_cover_cancellation=True,original_auxiliary_terms_per_row_max=3,
        no_source_coefficient_thresholding=True,proofs=results,wall_seconds=__import__('time').perf_counter()-start))
    p=OUT/'FULL_CONSTRAINT_SEPARATION_CERTIFICATION.json';x=read(p)
    x['roundoff_aware_safe_bound_proofs_PASS']=True;x['roundoff_proof']=record(OUT/'ORIGINAL_COMPONENT_ROUNDING_BOUND_AUDIT.json');put(p.name,x)
    print('ORIGINAL ROUNDING BOUND PASS',total,flush=True)

if __name__=='__main__':run()
