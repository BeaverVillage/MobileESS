"""Bounded-memory source Native CSR readback and immutable ASCII-name IO.

No model equation, parameter, objective or optimization algorithm is changed.
Actual Gurobi rows are read independently and hashed in the identical CSR
byte order without allocating a second 51M-nonzero matrix beside the model.
"""
from array import array
from contextlib import contextmanager
import hashlib
import numpy as np
from .stage_common import *

def streaming_sha(A):
    if isinstance(A,NativeRows):return A.fingerprint()
    A=A.tocsr();h=hashlib.sha256(np.asarray(A.shape,dtype='<i8').tobytes())
    for v in (A.indptr,A.indices,A.data):
        h.update(v.dtype.str.encode('ascii'))
        view=memoryview(np.ascontiguousarray(v)).cast('B')
        for offset in range(0,len(view),1024*1024):h.update(view[offset:offset+1024*1024])
    return h.hexdigest()

class AsciiNames:
    def __init__(self,names):
        self.value=np.asarray(names).astype('S');self.shape=self.value.shape
    def tolist(self):return [v.decode('ascii') for v in self.value.tolist()]

class TextNames(np.ndarray):
    """Original ASCII storage with scalar/iteration Unicode text semantics.

    Native's file bytes and source domain hash stay unchanged. Python source
    parsers receive the same strings without a 4x Unicode resident copy.
    """
    def __new__(cls,value):return np.asarray(value,dtype='S').view(cls)
    def __getitem__(self,item):
        value=super().__getitem__(item)
        return value.decode('ascii') if isinstance(value,(bytes,np.bytes_)) else value
    def __iter__(self):
        for i in range(len(self)):yield self[i]
    def __eq__(self,other):return super().__eq__(other.encode('ascii') if isinstance(other,str) else other)
    def __ne__(self,other):return super().__ne__(other.encode('ascii') if isinstance(other,str) else other)
    def tolist(self):return [self[i] for i in range(len(self))]

class NativeRows:
    def __init__(self,model,rows,folder):self.model=model;self.rows=rows;self.folder=folder
    def tocsr(self):return self
    def fingerprint(self):
        start=time.perf_counter();m=self.model;m.update();n=int(m.NumConstrs);p=int(m.NumVars)
        self.folder.mkdir(parents=True,exist_ok=True);indptr=np.zeros(n+1,dtype=np.int32)
        from .stage_native_batch import blocks
        with (self.folder/'ACTUAL_INDICES.bin').open('wb') as ix,(self.folder/'ACTUAL_VALUES.bin').open('wb') as values:
            for first,A in blocks(m,0,n):
                indptr[first+1:first+A.shape[0]+1]=A.indptr[1:]+indptr[first]
                ix.write(memoryview(A.indices));values.write(memoryview(A.data));guard(start)
        assert int(indptr[-1])==int(m.DNumNZs)
        h=hashlib.sha256(np.asarray((n,p),dtype='<i8').tobytes())
        h.update(indptr.dtype.str.encode('ascii'));h.update(memoryview(indptr))
        for key,dtype in (('ACTUAL_INDICES.bin',np.dtype('int32')),('ACTUAL_VALUES.bin',np.dtype('float64'))):
            h.update(dtype.str.encode('ascii'))
            with (self.folder/key).open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        value=h.hexdigest()
        (self.folder/'ACTUAL_CSR_READBACK.json').write_text(json.dumps(dict(PASS=True,mode='EVERY_ACTUAL_NATIVE_ROW_BATCHED_C_API',
            rows=n,columns=p,nonzeros=int(indptr[-1]),canonical_CSR_sha256=value,
            Source_hash_byte_schema_unchanged=True,bounded_query_rows=1024,every_coefficient_read_from_actual_Native_model=True,
            API='GRBgetconstrs',wall_seconds=time.perf_counter()-start)),encoding='utf-8')
        return value

@contextmanager
def readback_scope(engine,folder):
    import gurobipy as gp
    from unittest.mock import patch
    original=gp.Model
    class Model(original):
        def addMConstr(self,*a,**kw):
            result=super().addMConstr(*a,**kw);self._stage_actual_rows=result;return result
        def getA(self):return NativeRows(self,self._stage_actual_rows,folder)
    with patch.object(gp,'Model',Model),patch.object(engine,'matrix_sha',streaming_sha):yield


def certify():
    """Check streamed actual rows against Gurobi's independent getA()."""
    import scipy.sparse as sp
    from .prestart_native import native_zero
    from v44.frozen.v43_mess.library import load
    with measured('NATIVE_STREAMED_READBACK_VERIFICATION.json') as (report,start),native_zero() as denied:
        import gurobipy as gp
        engine=load()['m_engine'];real_model=gp.Model;original_hash=engine.matrix_sha
        A=sp.csr_matrix(np.array([[0.,3.,-2.,0.,1.],[-4.,0.,0.,5.,0.],[0.,0.,0.,0.,0.],[1.,0.,0.,0.,-1.]]))
        folder=WORK/'READBACK_FIXTURE'
        with readback_scope(engine,folder):
            model=gp.Model('V2_ADD_STREAMED_NATIVE_READBACK');model.Params.OutputFlag=0
            try:
                x=model.addMVar(5,lb=-7.,ub=9.,vtype=['C','B','C','C','C'],name=AsciiNames(['a','b','c','d','e']).tolist())
                model.addMConstr(A,x,np.array(['<','=','>','<']),np.array([4.,2.,0.,3.]));model.update()
                actual=real_model.getA(model).tocsr()
                expected=original_hash(actual);observed=engine.matrix_sha(model.getA())
                assert observed==expected==streaming_sha(actual)
                assert model.NumConstrs==4 and model.NumVars==5 and model.SolCount==0
                report.update(PASS=True,all_actual_rows_independently_equal=True,
                    original_source_hash_schema_equal=True,CSR_sha256=observed,
                    rows=model.NumConstrs,columns=model.NumVars,nonzeros=model.NumNZs,
                    no_solver_called=True,denied_attempts=denied)
            finally:model.dispose()


if __name__=='__main__':certify()
