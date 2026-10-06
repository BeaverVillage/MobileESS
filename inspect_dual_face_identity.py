"""Read-only two-coordinate face census; zero optimizer calls."""
import json
import numpy as np
from scipy import sparse
from audit_numerical_dual import OUT
p=OUT/'polish/POLISHED_TERMINAL_BEFORE_GATE.npz'
with np.load(p) as z:
    A=sparse.csr_matrix((z['data'],z['indices'],z['indptr']),shape=tuple(z['shape']));C=A.tocsc()
    i=248399;a,b=A.indptr[i:i+2];target=A.indices[a:b];possible=set()
    for j in target:possible.update(map(int,C.indices[C.indptr[j]:C.indptr[j+1]]))
    rows=[]
    for k in sorted(possible):
        a,b=A.indptr[k:k+2]
        if not set(map(int,A.indices[a:b]))<=set(map(int,target)):continue
        activity=float((A[k]@z['point']).item());res=activity-float(z['rhs'][k])
        rows.append(dict(row=k,name=str(z['row_names'][k]),sense=str(z['sense'][k]),Pi=float(z['pi'][k]),
                         rhs=float(z['rhs'][k]),residual=res,coefficients={str(j):float(v) for j,v in zip(A.indices[a:b],A.data[a:b])}))
    result=dict(failed_row=i,target_columns=target.tolist(),rows=rows)
(OUT/'polish/FACE_ROW_CENSUS.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result),flush=True)
