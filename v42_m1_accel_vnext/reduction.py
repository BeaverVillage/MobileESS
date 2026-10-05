"""Exact parallel-arc quotient; requires a independently proved unit DAG flow."""
import hashlib
import numpy as np

def duplicate_groups(A,B,d,eligible,unit_DAG_flow_proven):
    if not unit_DAG_flow_proven:raise ValueError('Missing at-most-one unit DAG flow proof')
    local=A.tocsc();coupling=B.tocsc();buckets={};groups=[]
    for j in eligible:
        if d['types'][j]!='B' or d['lower'][j]!=0 or d['upper'][j]!=1:continue
        h=hashlib.sha256()
        for matrix in (local,coupling):
            lo,hi=matrix.indptr[j:j+2]
            h.update(matrix.indices[lo:hi].tobytes());h.update(matrix.data[lo:hi].tobytes())
        h.update(np.array([d['objective'][j]],dtype=np.float64).tobytes())
        key=h.hexdigest();buckets.setdefault(key,[]).append(int(j))
    for bucket in buckets.values():
        if len(bucket)<2:continue
        j=bucket[0]
        # Hashes propose equivalence only; exact arrays/objective prove it.
        members=[j]
        for k in bucket[1:]:
            same=d['objective'][j]==d['objective'][k]
            for matrix in (local,coupling):
                a,b=matrix.indptr[j:j+2];c,e=matrix.indptr[k:k+2]
                same=same and np.array_equal(matrix.indices[a:b],matrix.indices[c:e]) and np.array_equal(matrix.data[a:b],matrix.data[c:e])
            if same:members.append(k)
        if len(members)>1:groups.append(members)
    return groups

def quotient(A,B,d,groups):
    deleted={j for g in groups for j in g[1:]}
    keep=np.array([j for j in range(A.shape[1]) if j not in deleted],dtype=int)
    data=dict(d)
    for key in ['names','lower','upper','types','objective']:data[key]=d[key][keep].copy()
    return A[:,keep],B[:,keep],data,keep

def lift(values,keep,size):
    x=np.zeros(size);x[keep]=values;return x
