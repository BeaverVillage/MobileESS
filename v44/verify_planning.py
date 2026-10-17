"""Required real Native0 comparison against the V43 May01 matrices."""
from pathlib import Path
import traceback
import numpy as np
from scipy import sparse
from .common import ROOT,DOC,RUNTIME,read,record,verify,atomic,digest,now
from .locks import coordinator,process_identity

OUT=RUNTIME/'v43_planning_svr12_actual_v1/PLANNING_NATIVE0_001'
OLD=Path('D:/MobileESS_V43/runtime/may01_B2_M1_attempt002')

def run():
    from .planning import scope
    from .daily import day_inputs
    from .runtime import build
    from v42_may_campaign_native90.preflight import native_zero
    from v42_may_campaign_native90.m_model import _domain_sha
    from v42_m1_hybrid.blocks import matrix_sha
    from v43_arms.reference import load
    if OUT.exists():raise FileExistsError('NEW_NATIVE0_COMPARISON_ROOT_REQUIRED')
    OUT.mkdir(parents=True)
    identity=read(OLD/'SCIENTIFIC_CASE_IDENTITY.json')['input_identity']
    payload=load(Path(identity['physical']['path']).parent)
    row=day_inputs('2025-05-01')
    if row['files']['native']['sha256']!=identity['input']['sha256']:raise ValueError('EXACT_V43_NATIVE_INPUT_REQUIRED')
    files=[record(ROOT/n) for n in ('v44/planning.py','v44/runtime.py','v44/frozen/v43_mess/case.py',
        'v44/frozen/v43_mess/performance.py','v44/frozen/v43_mess/library.py','v42_may_campaign_native90/m_model.py')]
    request=dict(day='2025-05-01',arm='B2',stage='M1',output=str(OUT/'MODEL'),
        input_folder=row['native_folder'],source_sha=digest(files),sources=files)
    atomic(OUT/'START.json',dict(process_identity(),UTC=now(),sources=files,Native_calls=0))
    def progress(value):atomic(OUT/'PROGRESS.json',dict(value,UTC=now()))
    with coordinator(OUT/'LEASE'),native_zero() as denied,scope('2025-05-01'):
        case=build(payload,request,progress)
        results=[]
        for label,A,d,an,dn in [('FULL',case.original_A,case.original_d,'FULL_A.npz','FULL_DATA.npz'),
                ('C3A',case.A,case.d,'C3A_A.npz','C3A_DATA.npz')]:
            oldA=sparse.load_npz(OLD/an)
            with np.load(OLD/dn,allow_pickle=False) as z:oldD={k:z[k].copy() for k in z.files}
            math_equal=matrix_sha(A)==matrix_sha(oldA) and _domain_sha(d)==_domain_sha(oldD)
            results.append(dict(representation=label,PASS=math_equal,rows=A.shape[0],columns=A.shape[1],nnz=A.nnz,
                original_matrix=record(OLD/an),original_metadata=record(OLD/dn),
                all_coefficients_objective_bounds_types_row_column_identity_equal=math_equal))
    verify(files)
    result=dict(PASS=not denied and all(r['PASS'] for r in results),UTC=now(),comparisons=results,
        exact_scientific_input=identity['input'],sources=files,Native_calls=0,added_SVR=0,RegControl_count=7,
        V43_case=record(OLD/'SCIENTIFIC_CASE_IDENTITY.json'),validation_in_campaign=False)
    atomic(OUT/'RESULT.json',result)
    atomic(DOC/'v43_planning_svr12_actual_v1/PLANNING_MATRIX_EQUIVALENCE.json',result)
    print(result,flush=True)
    return result

if __name__=='__main__':
    try:run()
    except BaseException as error:
        atomic(OUT/'FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc(),UTC=now()));raise
