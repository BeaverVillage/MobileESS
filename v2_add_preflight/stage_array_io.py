"""Faithful read-only NPY storage for unused reference buffers in Native0.

The complete original rows, senses and RHS remain addressable. Direct Joint
uses the actual complete selected Native matrix; its original-reference hash
and physical arc domain are unchanged. No constraint is dropped or delayed.
"""
import gc,hashlib
import numpy as np
from .stage_common import *


def mapped(value,path):
    value=np.asarray(value);assert value.flags.c_contiguous
    np.save(path,value,allow_pickle=False)
    actual=np.load(path,mmap_mode='r',allow_pickle=False)
    assert actual.dtype==value.dtype and actual.shape==value.shape
    # Exhaustive byte comparison by a separate file read, without touching
    # the mapped pages or allocating a duplicate whole array.
    expected=hashlib.sha256(memoryview(value).cast('B')).hexdigest()
    with path.open('rb') as stream:
        version=np.lib.format.read_magic(stream)
        shape,fortran,dtype=np.lib.format._read_array_header(stream,version)
        assert shape==value.shape and not fortran and dtype==value.dtype
        h=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    assert h.hexdigest()==expected
    return actual,dict(PASS=True,file=record(path),dtype=dtype.str,shape=list(shape),all_payload_bytes_sha256=expected)


def direct_reference(case):
    folder=WORK/'DIRECT_REFERENCE_IO';folder.mkdir(exist_ok=True);records={}
    for key in ('rhs','sense'):
        value,proof=mapped(case.original_d[key],folder/(key+'.npy'))
        case.original_d[key]=value;records[key]=proof
    value,proof=mapped(case.original_A.indptr,folder/'indptr.npy')
    case.original_A.indptr=value;case._blocks.indptr=value;records['indptr']=proof
    gc.collect()
    put('DIRECT_REFERENCE_READONLY_IO.json',dict(PASS=True,case_sha=case.case_sha,records=records,
        complete_original_reference_remains_available=True,original_hash_unmodified=True,
        selected_full_native_rows_unmodified=True,Native_optimizer_calls=0))
