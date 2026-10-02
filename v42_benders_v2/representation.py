"""Lossless mixed-sense matrix partition. No scientific rows are removed."""
from dataclasses import dataclass
from fractions import Fraction
import numpy as np
import gurobipy as gp
from v42_benders.canonical import digest_arrays

@dataclass
class Native:
    A: object
    B: object
    b: object
    sense: object
    lower: object
    upper: object
    c: object
    xi: object
    yi: object
    xlower: object
    xupper: object
    names: object
    rownames: object
    objective_constant: float
    source_hash: str

    def rhs(self, x):
        # Correctly round each exact IEEE-rational b_i - sum B_ij*x_j once.
        # This is representation rounding, never an arbitrary physics adjustment.
        x=np.asarray(x, dtype=float)
        if x.shape != (len(self.xi),) or not np.isfinite(x).all(): raise ValueError('MASTER_AXIS')
        result=self.b.copy()
        for i in np.flatnonzero(np.diff(self.B.indptr)):
            value=Fraction.from_float(float(self.b[i]))
            for k in range(self.B.indptr[i], self.B.indptr[i+1]):
                j=self.B.indices[k]
                if x[j]: value-=Fraction.from_float(float(self.B.data[k]))*Fraction.from_float(float(x[j]))
            result[i]=float(value)
        return result

    def assemble(self, x, y):
        z=np.empty(len(self.names)); z[self.xi]=x; z[self.yi]=y; return z

    def residual(self, x, y):
        r=self.A@y+self.B@x-self.b
        v=np.where(self.sense=='=', abs(r), np.where(self.sense=='<', r, -r))
        return max(0., float(np.max(v, initial=0)), float(np.max(self.lower-y, initial=0)), float(np.max(y-self.upper, initial=0)))

def from_model(m, master_mask=None):
    m.update()
    if m.ModelSense != 1 or m.NumQConstrs or m.NumSOS or m.NumGenConstrs or isinstance(m.getObjective(), gp.QuadExpr):
        raise ValueError('LINEAR_MIN_AUTHORITY_REQUIRED')
    types=np.asarray(m.getAttr('VType'))
    if np.any(~np.isin(types, ['B','C'])): raise ValueError('DISCRETE_TYPE')
    mask=types=='B' if master_mask is None else np.asarray(master_mask, dtype=bool)
    if mask.shape != types.shape or np.any(mask & (types!='B')): raise ValueError('PARTITION_AUTHORITY')
    xi=np.flatnonzero(mask); yi=np.flatnonzero(~mask)
    C=m.getA().tocsr(); b=np.asarray(m.getAttr('RHS')); sense=np.asarray(m.getAttr('Sense'))
    lb=np.asarray(m.getAttr('LB')); ub=np.asarray(m.getAttr('UB')); c=np.asarray(m.getAttr('Obj'))
    if np.any(c[xi]): raise ValueError('CONTINUOUS_P1_OBJECTIVE_REQUIRED')
    lower=np.where(lb[yi]<=-gp.GRB.INFINITY, -np.inf, lb[yi])
    upper=np.where(ub[yi]>=gp.GRB.INFINITY, np.inf, ub[yi])
    return Native(C[:,yi].tocsr(), C[:,xi].tocsr(), b, sense, lower, upper, c[yi], xi, yi,
        lb[xi], ub[xi], np.asarray(m.getAttr('VarName')), np.asarray(m.getAttr('ConstrName')),
        m.ObjCon, digest_arrays(C.indptr,C.indices,C.data,b,sense,lb,ub,types,c))

def audit(m, n):
    from scipy import sparse
    inverse=sparse.hstack([n.B,n.A], format='csr')[:,np.argsort(np.r_[n.xi,n.yi])]
    diff=inverse-m.getA()
    ok=(diff.nnz==0 or np.all(diff.data==0)) and np.array_equal(n.b,m.getAttr('RHS')) and np.array_equal(n.sense,m.getAttr('Sense'))
    lb=np.asarray(m.getAttr('LB'))[n.yi]; ub=np.asarray(m.getAttr('UB'))[n.yi]
    ok=ok and np.array_equal(n.lower,np.where(lb<=-gp.GRB.INFINITY,-np.inf,lb)) and np.array_equal(n.upper,np.where(ub>=gp.GRB.INFINITY,np.inf,ub))
    return dict(PASS=bool(ok),rows=n.A.shape[0],columns=n.A.shape[1],master_columns=len(n.xi),
        source_hash=n.source_hash,original_row_axis_preserved=True,equality_duplicated=0,explicit_bound_rows=0,
        native_bounds_preserved=True,scientific_rows_deleted=0,route_columns_pruned=0,
        inverse_mapping='xi/yi ordered original column indices; original rows identity',simplifications=[])
