"""Unmodified original-row transport, retaining every original variable."""
import gurobipy as gp
import numpy as np
from .core import row_digest

def build(A,d,axis,env=None):
    m=gp.Model('M1_EXACT_ORIGINAL_ROW_SUBSET',env=env)
    m.Params.OutputFlag=0
    v=m.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'],obj=d['objective'],name='original')
    m.ObjCon=float(d['constant'])
    add(m,v,A,d,axis)
    m.update()
    return m,v

def add(m,v,A,d,axis):
    axis=np.asarray(axis,dtype=np.int64)
    if len(axis):m.addMConstr(A[axis],v,d['sense'][axis],d['rhs'][axis],name='original_row')
    m.update()

def transport_audit(m,A,d,axis):
    native=m.getA().tocsr();original=A[np.asarray(axis,dtype=np.int64)].tocsr()
    if not (np.array_equal(native.indptr,original.indptr) and np.array_equal(native.indices,original.indices)
            and np.array_equal(native.data,original.data)):raise ValueError('NATIVE_ORIGINAL_ROW_TRANSPORT_DRIFT')
    for attr,key in [('RHS','rhs'),('Sense','sense')]:
        if not np.array_equal(np.asarray(m.getAttr(attr)),d[key][axis]):raise ValueError('NATIVE_ROW_ATTRIBUTE_DRIFT')
    for attr,key in [('LB','lower'),('UB','upper'),('VType','types'),('Obj','objective')]:
        if not np.array_equal(np.asarray(m.getAttr(attr)),d[key]):raise ValueError('NATIVE_VARIABLE_ATTRIBUTE_DRIFT')
    assert m.ObjCon==float(d['constant'])
    return dict(PASS=True,rows=len(axis),columns=A.shape[1],nnz=native.nnz,coefficient_sign_transform='none',
                original_variables_types_bounds_objective_retained=True)
