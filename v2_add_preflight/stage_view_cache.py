"""Commit exact immutable normalized views; never reuse a different RHS."""
from pathlib import Path
import os,uuid
import numpy as np
import scipy.sparse as sp
from .stage_common import read,record
from .prestart_execution import atomic
from v42_native.contracts import digest

def same_bytes(a,b):return a['sha256']==b['sha256'] and a['bytes']==b['bytes']

def preserve_write(path,write):
    """Keep old sealed bytes and timestamps if this is an identical replay."""
    path=Path(path);temp=path.with_name(path.stem+'.'+uuid.uuid4().hex+'.candidate.npz')
    try:
        write(temp)
        if path.exists():
            if not same_bytes(record(path),record(temp)):raise ValueError('CHANGED_VIEW_REQUIRES_NEW_CASE_OUTPUT_ROOT:'+str(path))
        else:os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

def load_or_build(path,authority,context,build,legacy=None):
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    receipt=path/('V2_EXACT_VIEW_'+digest(context)+'.json');producer=record(__file__)
    if receipt.exists():
        saved=read(receipt)
        if (saved.get('PASS') is True and saved.get('schema')=='V2_EXACT_CURRENT_SLOT_VIEW_V1'
                and saved.get('producer')==producer and saved.get('authority')==authority and saved.get('context')==context):
            proof=saved['proof']
            if same_bytes(record(path/'A.npz'),proof['view_matrix']) and same_bytes(record(path/'D.npz'),proof['view_domain']):
                return sp.load_npz(path/'A.npz'),proof,True
    # A legacy whole96 independent constructor certificate is admitted only
    # after its exact current raw matrix/RHS/domain/coefficient inputs and its
    # complete output bytes have been checked by the caller.
    if legacy is not None:
        A=sp.load_npz(path/'A.npz');proof=legacy
    else:
        A,local,proof=build()
        preserve_write(path/'A.npz',lambda target:sp.save_npz(target,A))
        preserve_write(path/'D.npz',lambda target:np.savez_compressed(target,**local))
        proof=dict(proof,view_matrix=record(path/'A.npz'),view_domain=record(path/'D.npz'))
    atomic(receipt,dict(PASS=True,schema='V2_EXACT_CURRENT_SLOT_VIEW_V1',producer=producer,authority=authority,context=context,proof=proof,
        all_raw_matrix_RHS_domain_and_coefficient_bytes_bound=True,solver_results_or_clocks_cached=False))
    return A,proof,False
