"""Certificate-only equality multiplier adjustment, no model or solver edits."""
import numpy as np

def repair_binding_duals(A,d,pi,exact_residual_display):
    families={'injection_P','injection_Q'}
    target=np.array([str(n).split('[')[0] in families for n in d['names']])
    CSC=A.tocsc();CSR=A.tocsr();candidate=np.asarray(pi).copy();changes=[]
    for j in np.flatnonzero(target):
        family=str(d['names'][j]).split('[')[0]
        rows=CSC.indices[CSC.indptr[j]:CSC.indptr[j+1]]
        eligible=[int(i) for i in rows if d['sense'][i]=='=' and str(d['row_names'][i])==family+'_binding']
        if len(eligible)!=1:continue
        i=eligible[0];cols=CSR.indices[CSR.indptr[i]:CSR.indptr[i+1]];coeff=CSR.data[CSR.indptr[i]:CSR.indptr[i+1]]
        if np.count_nonzero(target[cols])!=1:continue
        a=float(coeff[np.flatnonzero(cols==j)[0]])
        if a==0:continue
        delta=float(exact_residual_display[j])/a
        candidate[i]+=delta
        changes.append(dict(row=i,column=int(j),coefficient=a,delta=delta))
    assert len({r['row'] for r in changes})==len(changes)
    assert np.isfinite(candidate).all()
    assert all(d['sense'][r['row']]=='=' for r in changes)
    return candidate,changes
