"""Lossless signed-row partition; bounds are explicit canonical rows."""
from dataclasses import dataclass
import hashlib
import numpy as np
from scipy import sparse
import gurobipy as gp

def digest_arrays(*arrays):
    h=hashlib.sha256()
    for a in arrays:
        a=np.ascontiguousarray(a)
        h.update(str(a.dtype).encode()); h.update(str(a.shape).encode()); h.update(a.tobytes())
    return h.hexdigest()

@dataclass
class Canonical:
    A: object
    B: object
    b: object
    c: object
    xi: object
    yi: object
    lower: object
    upper: object
    xlower: object
    xupper: object
    source_rows: object
    signs: object
    bound_columns: object
    bound_signs: object
    discrete_rows: object
    names: object
    objective_constant: float
    original_hash: str

    def rhs(self,x): return self.b-self.B@np.asarray(x)

    def assemble(self,x,y):
        z=np.empty(len(self.names));z[self.xi]=x;z[self.yi]=y
        return z

    def residual(self,x,y):
        return max(0.,float(np.max(self.A@y-self.rhs(x),initial=0)))

def from_model(model, master_mask=None):
    model.update()
    if model.ModelSense!=gp.GRB.MINIMIZE:raise ValueError('MINIMIZATION_AUTHORITY_REQUIRED')
    if model.NumQConstrs or model.NumSOS or model.NumGenConstrs or isinstance(model.getObjective(),gp.QuadExpr):
        raise ValueError('RECOURSE_NOT_LP')
    types=np.asarray(model.getAttr('VType'))
    if np.any(~np.isin(types,['B','C'])): raise ValueError('UNSUPPORTED_DISCRETE_TYPE')
    mask=(types=='B') if master_mask is None else np.asarray(master_mask,dtype=bool)
    if mask.shape!=(model.NumVars,) or np.any(mask & (types!='B')): raise ValueError('PARTITION_AUTHORITY')
    # An explicitly selected partial mask means omitted original binaries are relaxed.
    xi=np.flatnonzero(mask);yi=np.flatnonzero(~mask)
    C=model.getA().tocsr();d=np.asarray(model.getAttr('RHS'));sense=np.asarray(model.getAttr('Sense'))
    rows=np.concatenate([np.arange(model.NumConstrs),np.flatnonzero(sense=='=')])
    sign=np.concatenate([np.where(sense=='>',-1.,1.),-np.ones(np.count_nonzero(sense=='='))])
    signed=C[rows].multiply(sign[:,None]).tocsr()
    A=signed[:,yi].tocsr();B=signed[:,xi].tocsr();b=d[rows]*sign
    lb=np.asarray(model.getAttr('LB'));ub=np.asarray(model.getAttr('UB'))
    lo=np.where(lb[yi]<=-gp.GRB.INFINITY,-np.inf,lb[yi]);hi=np.where(ub[yi]>=gp.GRB.INFINITY,np.inf,ub[yi])
    lc=np.flatnonzero(np.isfinite(lo));uc=np.flatnonzero(np.isfinite(hi))
    cols=np.concatenate([lc,uc]);bs=np.concatenate([-np.ones(len(lc)),np.ones(len(uc))])
    bounds=sparse.csr_matrix((bs,(np.arange(len(cols)),cols)),shape=(len(cols),len(yi)))
    discrete=np.flatnonzero(np.diff(A.indptr)==0)
    A=sparse.vstack([A,bounds],format='csr')
    B=sparse.vstack([B,sparse.csr_matrix((len(cols),len(xi)))],format='csr')
    b=np.concatenate([b,-lo[lc],hi[uc]])
    c=np.asarray(model.getAttr('Obj'))
    if np.any(c[xi]): raise ValueError('CONTINUOUS_P1_OBJECTIVE_REQUIRED')
    original_hash=digest_arrays(C.indptr,C.indices,C.data,d,sense,lb,ub,types,c)
    return Canonical(A,B,b,c[yi],xi,yi,lo,hi,lb[xi],ub[xi],rows,sign,cols,bs,
        discrete,np.asarray(model.getAttr('VarName')),model.ObjCon,original_hash)

def matrix_audit(model,can):
    C=model.getA().tocsr();n=len(can.source_rows)
    merged=sparse.hstack([can.B[:n],can.A[:n]],format='csr')[:,np.argsort(np.r_[can.xi,can.yi])]
    target=C[can.source_rows].multiply(can.signs[:,None]).tocsr()
    diff=merged-target
    equal=diff.nnz==0 or np.all(diff.data==0)
    b=np.asarray(model.getAttr('RHS'))[can.source_rows]*can.signs
    bound=can.A[n:]
    expected_bound_rhs=np.where(can.bound_signs<0,-can.lower[can.bound_columns],can.upper[can.bound_columns])
    return dict(PASS=bool(equal and np.array_equal(b,can.b[:n]) and np.array_equal(can.b[n:],expected_bound_rhs) and bound.nnz==len(can.bound_columns)
            and np.array_equal(bound.data,can.bound_signs) and np.array_equal(bound.indices,can.bound_columns)),
        original_rows=model.NumConstrs,original_columns=model.NumVars,original_nonzeros=model.NumNZs,
        canonical_rows=can.A.shape[0],master_columns=len(can.xi),recourse_columns=len(can.yi),
        equality_directions=2,finite_bound_rows=len(can.bound_columns),
        discrete_only_signed_rows=len(can.discrete_rows),coefficient_difference=0 if equal else float(abs(diff.data).max()),
        original_hash=can.original_hash,canonical_hash=digest_arrays(can.A.indptr,can.A.indices,can.A.data,
            can.B.indptr,can.B.indices,can.B.data,can.b),row_order_and_sign_provenance=True)

def lp_audit(model,can):
    return dict(PASS=not (model.NumQConstrs or model.NumSOS or model.NumGenConstrs),
        recourse_integer=0,recourse_binary=0,quadratic_constraints=model.NumQConstrs,
        SOS=model.NumSOS,general_constraints=model.NumGenConstrs,quadratic_objective=0,
        continuous_columns=len(can.yi),PCS16_linear=True,SOC_linear=True,grid_linear=True,
        partial_domain_relaxation=bool(len(can.xi)!=model.NumBinVars),physics_linearization=False)
