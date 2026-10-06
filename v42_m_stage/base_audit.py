"""Bind the PR152 pool and dual without replaying any native call."""
from .common import *
from v42_degen.identity import inputs,signature,digest
from v42_dw_root.partition import axes
from v42_dw_root.models import hash_column
import numpy as np
import shutil

def run():
    cp=read(SCI/'DW_CHECKPOINT_LATEST.json');prior=read(SCI/'DW_CONTINUATION_BASE_AUDIT.json')
    assert cp['type']=='TERMINAL' and cp['RMP']['status']==2
    assert cp['total_retained_columns']==len(cp['pool'])==1604
    pool=hashlib.sha256(json.dumps([(h['MESS'],h['column_SHA']) for h in cp['pool']],separators=(',',':')).encode()).hexdigest()
    assert pool==cp['pool_SHA']
    A,d,B,e,identity,a1=inputs();owner,rows=axes()
    assert signature(A,d)==prior['full_matrix_signature']
    assert cp['dual_axis_SHA']==digest(np.flatnonzero(rows<0))
    assert cp['row_axis_SHA']==digest(e['row_names'][rows<0])
    for h in cp['pool']:
        p=ROOT/h['file'];assert sha(p)==h['file_SHA']
        with np.load(p) as z:
            modern='x' in z;x=z['x'] if modern else z['local_values'];a=z['a'] if modern else z['master_coefficients']
            c=float(z['c'] if modern else z['objective']);axis=z['axis'] if modern else z['original_columns']
            assert hash_column(x,a,c)==h['column_SHA']
            assert np.array_equal(axis,np.flatnonzero(owner==int(h['MESS'][-2:])-1))
    point=SCI/cp['RMP']['point_file'];assert sha(point)==cp['RMP']['point_SHA']
    with np.load(point) as z:
        key=hashlib.sha256(z['pi'].tobytes()+z['alpha'].tobytes()).hexdigest()
    assert key==cp['RMP']['dual_SHA']
    assert read(SCI/'DW_CONTINUATION_FULL_POOL_AUDIT.json')['PASS']
    with np.load(SCI/cp['smooth_file']) as z:
        assert hashlib.sha256(z['pi'].tobytes()+z['alpha'].tobytes()).hexdigest()==cp['smooth_key']
    write('DW_CONTINUATION_BASE_AUDIT.json',dict(PASS=True,exact_head=PR152,pool_columns=1604,
        pool_SHA=pool,true_dual_SHA=key,full_matrix_signature=signature(A,d),
        dual_axis_SHA=cp['dual_axis_SHA'],row_axis_SHA=cp['row_axis_SHA'],
        inherited_lower=cp['best_interval'][0],inherited_RMP_upper=cp['best_interval'][1],
        historical_total_native=cp['cumulative_optimize'],native_optimize_calls=0,
        A1_development_identity=identity,current_A1_canary_authority_assessed=False,
        old_authoritative_completed_calls_replayed=False))
    # Physical cache is source/matrix/axis keyed; Integration only reuses a
    # receipt on exact matching authority and always recomputes current RC.
    shutil.copyfile(SCI/'PHYSICAL_AUDIT_CACHE.json',OUT/'PHYSICAL_AUDIT_CACHE.json')
    print('ROOT1604_BASE_AUDIT_PASS',pool,key,flush=True)

if __name__=='__main__':run()
