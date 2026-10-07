"""Read-only exact RC diagnostics for the still-unbounded certificate boxes."""
from fractions import Fraction
from time import time
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_lexcases.policy import OUT
from v42_a_stage_compact_rowgen.budget import Budget

def run():
    folder=OUT/'M19/P2/SHIFT_MAGNITUDE/TREE/N2';identity=read(folder/'MODEL_IDENTITY.json');rec=read(folder/'NATIVE_RESULT.json')
    recovery=read(OUT/'CERTIFICATE_RECOVERY/RESULT.json');u=np.load(recovery['upper']['path'])['upper']
    for r in (identity['matrix'],identity['attributes'],rec['raw_attributes'],recovery['upper']):
        if record(r['path'])!=r:raise ValueError('QUALIFIED_BYTE_DRIFT')
    A=sp.load_npz(identity['matrix']['path']).tocsc();attrs=dict(np.load(identity['attributes']['path']));raw=dict(np.load(rec['raw_attributes']['path']))
    pi=raw['Pi'].copy();pi[(attrs['senses']=='<')&(pi>0)]=0;pi[(attrs['senses']=='>')&(pi<0)]=0
    bad=[];budget=Budget();start=time();infinite=np.flatnonzero((~np.isfinite(u))|(u>=1e100))
    for num,j in enumerate(infinite):
        if num%128==0:
            budget.remaining()
            if time()-start>180:raise TimeoutError('READ_ONLY_RC_DIAGNOSTIC_ALLOCATION')
        lo,hi=A.indptr[j:j+2];exact=Fraction(float(attrs['objective'][j]))-sum((Fraction(float(a))*Fraction(float(pi[i])) for i,a in zip(A.indices[lo:hi],A.data[lo:hi])),Fraction(0))
        if exact<0:
            terms=[dict(row=int(i),coefficient=float(a),Pi=float(pi[i]),rhs=float(attrs['rhs'][i]),sense=str(attrs['senses'][i])) for i,a in zip(A.indices[lo:hi],A.data[lo:hi]) if pi[i]]
            bad.append(dict(column=int(j),exact_RC=str(exact),RC_float=float(exact),nonzero_dual_terms=terms))
    result=dict(PASS=True,diagnostic_only=True,bad_infinite_columns=bad,count=len(bad),infinite_columns=len(infinite),
        source_identity=record(folder/'MODEL_IDENTITY.json'),native_raw=rec['raw_attributes'],wall_seconds=time()-start,
        native_solve_calls=0,raw_dual_unchanged=True,no_pruning=True,source=record(__file__))
    atomic(OUT/'CERTIFICATE_RECOVERY/EXACT_INFINITE_RC_DIAGNOSTIC.json',result)
    print('EXACT_INFINITE_RC_DIAGNOSTIC',len(bad),[(r['column'],r['RC_float'],len(r['nonzero_dual_terms'])) for r in bad[:20]],flush=True)
if __name__=='__main__':run()
