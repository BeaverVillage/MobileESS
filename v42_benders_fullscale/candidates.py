"""Atomic candidate receipts are the prerequisite for every recourse call."""
import os,time
import numpy as np
from v42_benders.canonical import digest_arrays
from .common import *

def persist(directory,index,n,x,master,active_cuts,resource,stage):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    prefix=f'MASTER_X_{index:03d}';values=np.asarray(x,dtype=np.float64)
    if values.shape!=n.xlower.shape or not np.isfinite(values).all() or np.any(values!=np.rint(values)) or np.any(values<n.xlower) or np.any(values>n.xupper):raise ValueError('CANDIDATE_BINARY_OR_AXIS')
    names=n.names[n.xi];bits=values.astype(np.uint8);p=directory/(prefix+'.npz');tmp=p.with_suffix('.npz.tmp')
    with tmp.open('wb') as f:
        np.savez_compressed(f,names=names,values=values,bits=bits,original_column_indices=n.xi)
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
    axis=dict(names=names.tolist(),axis_hash=digest_arrays(names,n.xi),original_column_indices=n.xi.tolist(),
        length=len(names),dtype=str(names.dtype),source_model_hash=n.source_hash)
    dump(prefix+'_AXIS.json',axis,directory)
    receipt=dict(stage=stage,index=index,label='NEW_V2_EXPERIMENT_X0' if stage=='PILOT' and index==0 else stage+'_NEW_CANDIDATE',
        historical_PR115_x=False,vector_length=len(values),dtype=str(values.dtype),vector_sha256=digest_arrays(values),
        bits_sha256=digest_arrays(bits),axis_hash=axis['axis_hash'],npz_sha256=sha(p),axis_json_sha256=sha(directory/(prefix+'_AXIS.json')),
        source_commit=git('rev-parse','HEAD'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),
        execution_freeze_sha256=sha(OUT/'EXECUTION_FREEZE.json'),master_status=master.Status,
        master_settings={k:getattr(master.Params,k) for k in ['Threads','Seed','Method','FeasibilityTol','IntFeasTol','MIPGap']},
        master_wall_seconds=master.Runtime,master_objective=master.ObjVal,active_cut_IDs=list(active_cuts),
        created_UTC=stamp(),resource_snapshot=resource,persisted_before_recourse=True,
        native_master_output_sha256=digest_arrays(values),candidate_values_changed_after_persistence=False)
    dump(prefix+'_RECEIPT.json',receipt,directory)
    load(directory,index,n)
    return receipt

def load(directory,index,n):
    directory=Path(directory);prefix=f'MASTER_X_{index:03d}';r=read(prefix+'_RECEIPT.json',directory)
    p=directory/(prefix+'.npz');a=directory/(prefix+'_AXIS.json')
    if not r['persisted_before_recourse'] or sha(p)!=r['npz_sha256'] or sha(a)!=r['axis_json_sha256']:raise ValueError('CANDIDATE_FILE_HASH')
    with np.load(p,allow_pickle=False) as z:
        values=z['values'];names=z['names'];bits=z['bits'];indices=z['original_column_indices']
    if not np.array_equal(names,n.names[n.xi]) or not np.array_equal(indices,n.xi):raise ValueError('CANDIDATE_SOURCE_AXIS')
    if digest_arrays(names,indices)!=r['axis_hash'] or digest_arrays(values)!=r['vector_sha256'] or digest_arrays(bits)!=r['bits_sha256']:raise ValueError('CANDIDATE_ARRAY_HASH')
    if values.dtype!=np.float64 or values.shape!=n.xlower.shape or np.any(values!=np.rint(values)) or np.any(values<n.xlower) or np.any(values>n.xupper) or not np.array_equal(bits,values.astype(np.uint8)):raise ValueError('CANDIDATE_FIDELITY')
    if r['preregistration_sha256']!=sha(OUT/'PREREGISTRATION.json'):raise ValueError('CANDIDATE_PREREGISTRATION')
    return values,r
