"""Build actual May02 tight M1, prove only authorized FULL RHS changes."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import v44_recovery_r030
import numpy as np
from scipy import sparse
from v44.common import read, record, atomic, digest, now
from v44.daily import load_aidc
from v44 import runtime, q250_m4_v2 as q
from v42_may_campaign_native90.preflight import native_zero
from v44_recovery_r030 import m1_voltage

root=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004')
parent=root/'2025-05-02/B3/attempt001/M1'
output=Path(sys.argv[1])
output.mkdir(parents=True,exist_ok=False)
request=read(parent/'request.json')
request.update(root=str(output/'M1'),output=str(output/'M1'),case_root=str(output/'case'),
    sources=request['sources']+[record(p) for p in sorted(Path(m1_voltage.__file__).parent.glob('*.py'))])
request['source_sha']=digest(request['sources'])
payload,_=load_aidc(Path(read(parent/'RESULT.json')['fixed_AIDC']['physical']['path']).parent,'2025-05-02')
def progress(value):atomic(output/'progress.json',dict(value,UTC=now()))
with native_zero() as attempts,m1_voltage.scope(request),q.q_domain():
    case=runtime.build(payload,request,progress)
    rows=m1_voltage.check_rows(case)
    A=sparse.load_npz(parent/'FULL_A.npz')
    with np.load(parent/'FULL_DATA.npz',allow_pickle=False) as z:old={k:z[k].copy() for k in z.files}
    assert A.shape==case.original_A.shape and (A!=case.original_A).nnz==0,'UNAUTHORIZED_MATRIX_CHANGE'
    for key in old:
        if key!='rhs':assert np.array_equal(old[key],case.original_d[key]),'NON_RHS_ATTRIBUTE_CHANGE:'+key
    names=np.asarray(old['row_names']).astype(str)
    lower=np.array([x.startswith('voltage_lower[') for x in names]);upper=np.array([x.startswith('voltage_upper[') for x in names])
    difference=case.original_d['rhs']-old['rhs']
    assert np.all(difference[~(lower|upper)]==0),'NONVOLTAGE_RHS_CHANGE'
    assert np.max(np.abs(difference[lower]-(.912025-.9025)))<1e-12
    assert np.max(np.abs(difference[upper]-(1.092025-1.1025)))<1e-12
    assert not attempts
    from v44.frozen.v43_mess.library import load
    from v44.frozen.v43_mess.prepared import run_prepared_k48
    modules=load();k48=modules['table_v_k48']
    packet,proof=k48.prepare_k16(case,None,output/'NATIVE0_K16')
    assert proof['PASS'] and not attempts
    value=dict(UTC=now(),PASS=True,revision='r030',new_Native_optimization_calls=0,
        actual_case_sha=case.case_sha,full_matrix_identical=True,only_voltage_rhs_changed=True,
        non_voltage_rows_bounds_types_objective_identical=True,rows=case.original_A.shape[0],
        columns=case.original_A.shape[1],lower_voltage_rows=int(lower.sum()),upper_voltage_rows=int(upper.sum()),
        full_voltage_row_check=rows,K48_native0_decomposition_PASS=True,
        original_parent=record(parent/'RESULT.json'),new_case_identity=record(case.output/'SCIENTIFIC_CASE_IDENTITY.json'),
        source_records=[record(p) for p in sorted(Path(m1_voltage.__file__).parent.glob('*.py'))])
    atomic(output/'VALIDATION.json',value)
    print(dict(PASS=True,rows=value['rows'],columns=value['columns'],voltage_rows=value['lower_voltage_rows']+value['upper_voltage_rows'],Native=0,K48_native0_PASS=True))
