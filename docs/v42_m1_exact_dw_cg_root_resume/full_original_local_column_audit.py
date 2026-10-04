import sys
sys.path.insert(0,sys.argv[1])
from v42_dw_resume.common import *
import numpy as np
from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
from v42_dw_root.partition import axes
from v42_degen.identity import inputs
gate('postterminal_full_local_column_audit')
assert (OUT/'DW_CORRECTED_ROOT_RESULT.json').exists()
A,d,B,e,*_=inputs();owner,row_owner=axes()
full_owner=np.full(A.shape[0],-1,dtype=np.int8)
for i in range(A.shape[0]):
    deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
    if len(deps)==1 and -1 not in deps:full_owner[i]=next(iter(deps))
local={}
for m in range(4):
    rr=np.flatnonzero(full_owner==m);cc=np.flatnonzero(owner==m)
    data=dict(d,rhs=d['rhs'][rr],sense=d['sense'][rr],lower=d['lower'][cc],upper=d['upper'][cc],types=d['types'][cc],objective=d['objective'][cc],constant=np.array(0.))
    mat=A[rr][:,cc];local[m]=(mat,data,pure_binary_equalities(mat,data),cc)
checks=[]
for record in ledger('DW_RESUME_COLUMN_HASH_LEDGER.csv',OUT):
    if record['added']!='True':continue
    mat,data,mask,cc=local[UNITS.index(record['MESS'])]
    with np.load(OUT/record['file']) as z:
        assert np.array_equal(z['original_columns'],cc)
        result=corrected_rows(mat,data,z['local_values'],True,mask)
    assert result['PASS'],record['file']
    checks.append(dict(file=record['file'],file_SHA=sha(OUT/record['file']),MESS=record['MESS'],full_original_local_rows=mat.shape[0],PASS=True,raw_max=result['max_constraint_violation']))
assert len(checks)==read(OUT/'DW_CORRECTED_ROOT_RESULT.json')['new_validated_columns']
write('DW_RESUME_FULL_ORIGINAL_LOCAL_COLUMN_AUDIT.json',dict(PASS=True,optimization_calls=0,repair_calls=0,checks=checks,all_affine_rows_audited_at=1e-6,original_bounds_and_route_equalities=1e-8,raw_binary_exact=True))
print('FULL_ORIGINAL_LOCAL_COLUMNS_PASS',len(checks))
