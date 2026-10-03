"""Direct binary row equality; no tolerance or proportional equivalence."""
import hashlib, struct
import numpy as np

def payload(A, rhs, sense, i):
    a,b=A.indptr[i:i+2]
    return A.indices[a:b].astype('<i8').tobytes()+A.data[a:b].astype('<f8').tobytes()+struct.pack('<d',float(rhs[i]))+str(sense[i]).encode('ascii')

def duplicates(A, rhs, sense):
    A=A.tocsr(copy=True);A.sum_duplicates();A.sort_indices()
    seen={};pairs=[]
    for i in range(A.shape[0]):
        if A.indptr[i]==A.indptr[i+1]:continue
        p=payload(A,rhs,sense,i);h=hashlib.sha256(p).digest()
        if h not in seen:seen[h]=i
        else:
            rep=seen[h]
            if p!=payload(A,rhs,sense,rep):raise ValueError('HASH_COLLISION')
            pairs.append((i,rep,h.hex()))
    return pairs

def audit(A, d, point, integral=False, tolerance=1e-5):
    residual=A@point-d['rhs'];sense=d['sense']
    vio=np.maximum(0,np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual)))
    bound=max(0.,float(np.max(d['lower']-point)),float(np.max(point-d['upper'])))
    mask=d['types']!='C'
    integer=float(np.max(abs(point[mask]-np.rint(point[mask])),initial=0.)) if integral else None
    finite=bool(np.isfinite(point).all())
    return dict(PASS=finite and float(vio.max(initial=0.))<=tolerance and bound<=tolerance and (not integral or integer<=tolerance),finite=finite,max_constraint_violation=float(vio.max(initial=0.)),max_bound_violation=bound,max_integrality_violation=integer,objective=float(d['objective']@point+float(d['constant'])))

def column_identity(d):
    h=hashlib.sha256()
    for k in ('names','lower','upper','types','objective','constant'):
        value=np.asarray(d[k])
        # IEEE signed zero has identical bounds/objective semantics. No nonzero
        # value is rounded, scaled, or compared with a tolerance.
        if value.dtype.kind=='f':value=np.where(value==0.,0.,value)
        h.update(k.encode());h.update(np.ascontiguousarray(value).tobytes())
    return h.hexdigest()

def arrays(m):
    return m.getA().tocsr(),dict(names=np.array(m.getAttr('VarName')),rhs=np.array(m.getAttr('RHS')),sense=np.array(m.getAttr('Sense')),lower=np.array(m.getAttr('LB')),upper=np.array(m.getAttr('UB')),types=np.array(m.getAttr('VType')),objective=np.array(m.getAttr('Obj')),constant=np.array(m.ObjCon),row_names=np.array(m.getAttr('ConstrName')))
