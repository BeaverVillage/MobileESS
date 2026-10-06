"""Exactly one cold canonical-CSR revalidation, with unchanged native settings.

The retained-column incremental insertion path is replaced by one verified
final-matrix transport. This does not claim to repair Gurobi's arithmetic:
only a new terminal certificate passing the unchanged gate can do so.
"""
import json,time,csv,traceback,os
from pathlib import Path
import numpy as np
from scipy import sparse
from v42_dw_root.models import build
from v42_m_stage_root.dual_authority import ARRAY_FIELDS,array_sha,capture,validate
from reproduce_rmp43 import OUT,ROOT,OLD,PARAMS,read,sha,write,corrected_audit

def canonical_rebuild(path):
    meta=read(path.with_suffix('.json'))
    assert sha(path)==meta['snapshot_SHA']
    with np.load(path) as z:v={k:z[k] for k in ARRAY_FIELDS}
    assert {k:array_sha(v[k]) for k in ARRAY_FIELDS}==meta['identity']
    A=sparse.csr_matrix((v['data'],v['indices'],v['indptr']),shape=tuple(v['shape']))
    d={k:v[k] for k in ('names','rhs','sense','lower','upper','objective','constant','row_names')}
    d['types']=np.full(len(v['point']),'C')
    m=build(A,d,'DW_ROOT_RMP')
    assert (m.NumConstrs,m.NumVars,m.NumNZs,m.Fingerprint&0xffffffff)==(679959,83058,7514086,0xf6cbcc5d)
    return m,v,meta
def run():
    assert read(OUT/'RESULT.json')['EXACT_DUAL_AUTHORITY_PASS'] is False
    marker=OUT/'REPAIRED_REVALIDATION_REGISTERED.json'
    with marker.open('x',encoding='utf8') as f:
        json.dump(dict(pid=os.getpid(),maximum_native_calls=1,settings_changes={},
            repair='Verified canonical final CSR rebuild, instead of incremental column insertions; no row transform, bound, objective or gate change',
            raw_native_numerical_failure_not_declared_fixed=True,source_snapshot_SHA=sha(OUT/'RMP43_TERMINAL_BEFORE_GATE.npz')),f,indent=2)
    start=time.perf_counter();m,v,meta=canonical_rebuild(OUT/'RMP43_TERMINAL_BEFORE_GATE.npz')
    m.reset(1)
    for k,value in PARAMS.items():m.setParam(k,value)
    m.Params.LogFile=str(OUT/'RMP43_CANONICAL_REVALIDATION.log')
    write('REVALIDATION_PRE_SOLVE_IDENTITY.json',dict(PASS=True,fingerprint=hex(m.Fingerprint&0xffffffff),
        same_original_matrix_axes_bounds_objective=True,original_snapshot_identity=meta['identity'],
        parameters=PARAMS,settings_changes={},primal_dual_basis_warm_start_imported=False,build_wall_seconds=time.perf_counter()-start))
    write('REVALIDATION_NATIVE_CALL_STARTED.json',dict(call_number=1,start=time.time(),parameters=PARAMS))
    print('ONE_CANONICAL_REVALIDATION_OPTIMIZE_STARTED',flush=True);m.optimize()
    write('REVALIDATION_NATIVE_CALL_ENDED.json',dict(call_number=1,status=m.Status,native_runtime=m.Runtime,
        iterations=m.IterCount,barrier_iterations=m.BarIterCount,objective=m.ObjVal if m.SolCount else None))
    if m.Status!=2:
        write('FINAL_RESULT.json',dict(EXACT_DUAL_AUTHORITY_PASS=False,reason='REVALIDATION_NONOPTIMAL',native_status=m.Status,initial_fullscale_RMP_calls=1,repaired_revalidation_calls=1,BAP_calls=0))
        return
    p=OUT/'RMP43_REVALIDATION_BEFORE_GATE.npz';capture(m,p);print('REVALIDATION_SNAPSHOT_SAVED_BEFORE_GATE',flush=True)
    audit=validate(p)
    cp=read(OLD/'DW_CHECKPOINT_LATEST.json');cost=np.asarray(m.getAttr('Obj'));pi=np.asarray(m.getAttr('Pi'));rc=np.asarray(m.getAttr('RC'))
    manual=cost-m.getA().T@pi;offset=m.NumVars-1841
    with (OUT/'REVALIDATION_1841_RC_IDENTITY.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.writer(f);w.writerow(['column','MESS','column_SHA','manual_RC','native_RC','absolute_error','PASS'])
        for j,h in enumerate(cp['pool']):
            i=offset+j;err=abs(manual[i]-rc[i]);w.writerow([j,h['MESS'],h['column_SHA'],manual[i],rc[i],err,err<=1e-8])
    corrected=read(OUT/'CORRECTED_BOUND_RECONSTRUCTION.json')
    result=dict(EXACT_DUAL_AUTHORITY_PASS=bool(audit['PASS'] and corrected['PASS']),audit=audit,
        corrected_bound_reconstruction_PASS=corrected['PASS'],initial_fullscale_RMP_calls=1,repaired_revalidation_calls=1,
        BAP_calls=0,pricing_calls=0,revalidation_native_runtime=m.Runtime,revalidation_wall_seconds=time.perf_counter()-start,
        solver_settings_unchanged=True,canonical_rebuild_is_not_a_sign_projection=True,
        root_CG_continuation=False,BAP7200=False,P2=False)
    write('FINAL_RESULT.json',result);print(json.dumps(result),flush=True);m.dispose()
if __name__=='__main__':
    try:run()
    except Exception:
        write('REVALIDATION_DRIVER_ERROR.json',dict(traceback=traceback.format_exc()));raise
