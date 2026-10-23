"""Exhaustive bounded-memory reads from the actual Gurobi constraint matrix.

GRBgetconstrs is the documented read-only C API, queried twice per range:
https://docs.gurobi.com/projects/optimizer/en/current/reference/c/queries.html
No optimization, presolve, coefficient generation or sampling occurs here.
"""
import ctypes
from functools import lru_cache
from pathlib import Path
import numpy as np
import scipy.sparse as sp
from types import SimpleNamespace

@lru_cache(maxsize=1)
def api():
    import gurobipy as gp
    version=gp.gurobi.version()
    if version[:2]!=(13,0):raise RuntimeError('UNCERTIFIED_GUROBI_CAPSULE_ABI')
    dll=ctypes.WinDLL(str(Path(gp.__file__).parent/'gurobi130.dll'))
    query=dll.GRBgetconstrs
    query.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_double),ctypes.c_int,ctypes.c_int]
    query.restype=ctypes.c_int
    name=ctypes.pythonapi.PyCapsule_GetName;name.argtypes=[ctypes.py_object];name.restype=ctypes.c_char_p
    pointer=ctypes.pythonapi.PyCapsule_GetPointer;pointer.argtypes=[ctypes.py_object,ctypes.c_char_p];pointer.restype=ctypes.c_void_p
    return dll,query,name,pointer

def blocks(model,first,count,chunk_rows=1024):
    model.update();n=int(model.NumConstrs);columns=int(model.NumVars)
    if not (0<=first<=first+count<=n and chunk_rows>0):raise ValueError('ACTUAL_NATIVE_ROW_RANGE')
    dll,query,name,pointer=api();capsule=model._cmodel
    if type(capsule).__name__!='PyCapsule':raise RuntimeError('GUROBI_MODEL_CAPSULE_REQUIRED')
    address=pointer(capsule,name(capsule))
    if not address:raise RuntimeError('EMPTY_GUROBI_MODEL_POINTER')
    for offset in range(0,count,chunk_rows):
        length=min(chunk_rows,count-offset);nnz=ctypes.c_int()
        error=query(address,ctypes.byref(nnz),None,None,None,first+offset,length)
        if error:raise RuntimeError('GRBgetconstrs_COUNT_ERROR:'+str(error))
        if nnz.value<0:raise OverflowError('NATIVE_ROW_QUERY_NNZ_OVERFLOW')
        indptr=np.empty(length+1,dtype=np.int32);indices=np.empty(nnz.value,dtype=np.int32);values=np.empty(nnz.value,dtype=np.float64)
        error=query(address,ctypes.byref(nnz),indptr.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
            indices.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),values.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),first+offset,length)
        if error:raise RuntimeError('GRBgetconstrs_DATA_ERROR:'+str(error))
        indptr[-1]=nnz.value
        if not np.isfinite(values).all() or np.any(values==0.):raise ValueError('NONCANONICAL_ACTUAL_NATIVE_COEFFICIENT')
        matrix=sp.csr_matrix((values,indices,indptr),shape=(length,columns));matrix.sort_indices()
        yield offset,matrix

def exact(model,handle,expected,rhs,sense,start):
    from .stage_common import guard
    count=expected.shape[0]
    if not count:return
    first=handle[0].item().index
    if handle[count-1].item().index!=first+count-1:raise ValueError('NONCONTIGUOUS_NATIVE_ROW_HANDLE')
    if not np.array_equal(handle.getAttr('RHS'),rhs) or not np.array_equal(handle.getAttr('Sense'),sense):raise ValueError('ACTUAL_NATIVE_RHS_OR_SENSE_MISMATCH')
    expected=expected.tocsr();expected.sort_indices()
    if expected.shape[1]!=int(model.NumVars):raise ValueError('ACTUAL_NATIVE_COLUMN_AXIS_MISMATCH')
    for offset,actual in blocks(model,first,count):
        target=expected[offset:offset+actual.shape[0]]
        if not (np.array_equal(actual.indptr,target.indptr) and np.array_equal(actual.indices,target.indices) and np.array_equal(actual.data,target.data)):
            raise ValueError('ACTUAL_NATIVE_COEFFICIENT_MISMATCH')
        guard(start)

def difference(model,expected):
    """The original full CSR subtraction, evaluated in bounded row ranges."""
    if expected.shape!=(int(model.NumConstrs),int(model.NumVars)):raise ValueError('ACTUAL_NATIVE_MATRIX_AXIS_MISMATCH')
    differing=0
    for first,actual in blocks(model,0,expected.shape[0]):
        delta=actual-expected[first:first+actual.shape[0]];delta.eliminate_zeros();differing+=delta.nnz
    return SimpleNamespace(nnz=int(differing))
