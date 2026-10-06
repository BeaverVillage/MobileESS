"""One registered RMP43-equivalent solve; never continues column generation."""
from pathlib import Path
import json,hashlib,csv,time,traceback,os
from fractions import Fraction as F
import numpy as np
import psutil
from v42_degen.identity import inputs,digest
from v42_dw_root.partition import axes
from v42_dw_root.models import hash_column
from v42_dw_resume.audit import Master
from v42_m_stage_root.dual_authority import capture,validate,array_sha
from v42_disjunctive.certificate import down

ROOT=Path(__file__).resolve().parent
OLD=ROOT/'docs/v42_m_stage_exact_completion'
OUT=ROOT/'docs/v42_m1_rmp43_reproduction_20261006'
PARAMS=dict(Threads=1,Method=2,Crossover=1,LPWarmStart=0,PreDual=0,BarConvTol=1e-11,
            Seed=20260929,FeasibilityTol=1e-8,IntFeasTol=1e-8,OptimalityTol=1e-8,TimeLimit=300.,LogToConsole=0)
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,v):
    p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
def corrected_audit():
    cert=read(OLD/'DW_CONTINUATION_FINAL_CERTIFICATION.json')['certificate']
    proof=read(OLD/'ROOT_INDEPENDENT_BOUND_CHECK.json')
    global_value=F(int(proof['exact_global_numerator']),int(proof['exact_global_denominator']))
    with np.load(OLD/'RMP_POINT_0036.npz') as z:pi,alpha=z['pi'],z['alpha']
    key=hashlib.sha256(pi.tobytes()+alpha.tobytes()).hexdigest()
    beta=[F(down(F(float(b))-F(1e-8))) for b in cert['beta_raw']]
    delta=[min(F(0),b) for b in beta]
    exact=global_value+sum((F(float(a))+b for a,b in zip(alpha,delta)),F(0))
    ok=key==cert['dual_SHA'] and down(exact)==cert['L_corr'] and exact==F(int(cert['exact_numerator']),int(cert['exact_denominator']))
    r=dict(PASS=ok,dual_SHA=key,source='Existing approved same-RMP36 full-domain certificate; no bounds mixed into reproduced dual',
           source_SHA=sha(OLD/'ROOT_INDEPENDENT_BOUND_CHECK.json'),L_corr=down(exact),
           aggregate_inherited_valid_LB=.5687115725336208,fresh_RMP43_full_domain_bound_certified=False,
           restricted_LP_is_not_integer_UB=True,pricing_calls=0,materiality_not_recomputed=True)
    write('CORRECTED_BOUND_RECONSTRUCTION.json',r);return r
def run():
    OUT.mkdir(exist_ok=True)
    marker=OUT/'ONE_SHOT_REGISTRATION.json'
    if marker.exists():
        assert not (OUT/'INITIAL_NATIVE_CALL_STARTED.json').exists(),'ONE_INITIAL_SOLVE_ONLY'
        assert "'-0x93433a3'" in read(OUT/'DRIVER_ERROR.json')['traceback'],'ONLY_UNSIGNED_IDENTITY_WRAPPER_REBUILD_ALLOWED'
        p=OUT/'UNSIGNED_IDENTITY_WRAPPER_REBUILD.json'
        with p.open('x',encoding='utf8') as f:json.dump(dict(reason='Signed int32 fingerprint equals expected uint32; zero native calls before wrapper correction',pid=os.getpid()),f)
    else:
        with marker.open('x',encoding='utf8') as f:
            json.dump(dict(pid=os.getpid(),process_creation=psutil.Process().create_time(),start=time.time(),
                           maximum_initial_RMP_calls=1,maximum_repaired_revalidation_calls=1,
                           fullscale_BAP_seconds_only_after_PASS=600,root_CG_continuation=False,P2=False,BAP7200=False),f,indent=2)
    start=time.perf_counter();cp=read(OLD/'DW_CHECKPOINT_LATEST.json');r42=read(OLD/'RMP_RECEIPT_0042.json')
    assert cp['RMP']['round']==42 and len(cp['pool'])==1841
    pointpath=OLD/r42['point_file'];assert sha(pointpath)==r42['point_SHA']
    with np.load(pointpath) as z:oldpi,oldalpha=z['pi'],z['alpha']
    assert hashlib.sha256(oldpi.tobytes()+oldalpha.tobytes()).hexdigest()==r42['dual_SHA']
    A,d,B,e,identity,freeze=inputs();owner,row_owner=axes();del A,d
    rows=np.flatnonzero(row_owner<0)
    assert digest(rows)==cp['dual_axis_SHA'] and digest(e['row_names'][rows])==cp['row_axis_SHA']
    with np.load(ROOT/'docs/v42_m1_exact_dw_cg_root_pilot/DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    master=Master(B,e,owner,row_owner,native)
    for j,h in enumerate(cp['pool']):
        p=ROOT/h['file'];assert sha(p)==h['file_SHA']
        unit=int(h['MESS'][-2:])-1
        with np.load(p) as z:
            modern='x' in z
            x=z['x'] if modern else z['local_values'];a=z['a'] if modern else z['master_coefficients']
            c=float(z['c'] if modern else z['objective']);axis=z['axis'] if modern else z['original_columns']
        assert np.array_equal(axis,np.flatnonzero(owner==unit))
        assert hash_column(x,a,c)==h['column_SHA']
        master.add(unit,x,a,c,h['column_SHA'])
        # Dense coupling vectors need not be retained to reproduce the native matrix.
        master.column_data[-1]['a']=None
        if j%100==0:print(json.dumps(dict(build_columns=j+1,total=1841)),flush=True)
    m=master.model
    assert (m.NumConstrs,m.NumVars,m.NumNZs,m.Fingerprint&0xffffffff)==(679959,83058,7514086,0xf6cbcc5d),('MODEL_IDENTITY_MISMATCH',m.NumConstrs,m.NumVars,m.NumNZs,hex(m.Fingerprint))
    m.reset(1)
    for k,v in PARAMS.items():m.setParam(k,v)
    m.Params.LogFile=str(OUT/'RMP43_EQUIVALENT.log')
    write('PRE_SOLVE_IDENTITY.json',dict(PASS=True,checkpoint_SHA=sha(OLD/'DW_CHECKPOINT_LATEST.json'),
        last_valid_point_SHA=r42['point_SHA'],last_valid_dual_SHA=r42['dual_SHA'],retained_columns=1841,
        model=dict(rows=m.NumConstrs,columns=m.NumVars,nnz=m.NumNZs,fingerprint=hex(m.Fingerprint&0xffffffff)),
        objective_constant=m.ObjCon,parameters=PARAMS,source_model_identity=identity,row_axis_SHA=cp['row_axis_SHA'],
        same_objective_rows_solver_settings=True,warm_start_imported=False,memory_guards=False,build_wall_seconds=time.perf_counter()-start))
    write('INITIAL_NATIVE_CALL_STARTED.json',dict(call_number=1,pid=os.getpid(),start=time.time(),parameters=PARAMS))
    print('INITIAL_RMP43_OPTIMIZE_STARTED',flush=True);m.optimize()
    write('INITIAL_NATIVE_CALL_ENDED.json',dict(call_number=1,status=m.Status,native_runtime=m.Runtime,wall=time.time(),
        objective=m.ObjVal if m.SolCount else None,iterations=m.IterCount,barrier_iterations=m.BarIterCount))
    if m.Status!=2:
        write('RESULT.json',dict(EXACT_DUAL_AUTHORITY_PASS=False,status='NONOPTIMAL_TERMINAL_RMP',native_status=m.Status,initial_calls=1,BAP_calls=0))
        raise RuntimeError('NONOPTIMAL_TERMINAL_RMP_NO_BLIND_RETRY')
    snapshot=OUT/'RMP43_TERMINAL_BEFORE_GATE.npz';capture(m,snapshot)
    print('SNAPSHOT_SAVED_BEFORE_SIGN_GATE',flush=True)
    audit=validate(snapshot)
    with np.load(snapshot) as z:
        pi=z['pi'];rc=z['rc'];sense=z['sense'];names=z['row_names'];matrix=m.getA().tocsr()
        manual=z['objective']-matrix.T@pi
        with (OUT/'RETAINED_1841_RC_IDENTITY.csv').open('w',encoding='utf8',newline='') as f:
            w=csv.writer(f);w.writerow(['column','MESS','column_SHA','manual_RC','native_RC','absolute_error','PASS'])
            for j,h in enumerate(cp['pool']):
                k=len(master.z)+j;err=abs(manual[k]-rc[k]);w.writerow([j,h['MESS'],h['column_SHA'],manual[k],rc[k],err,err<=1e-8])
        family={}
        for s in ('<','>','='):
            mask=sense==s;bad=mask&(((sense=='<')&(pi>0))|((sense=='>')&(pi<0)))
            family[s]=dict(rows=int(mask.sum()),wrong_sign_rows=int(bad.sum()),Pi_min=float(pi[mask].min()) if mask.any() else None,Pi_max=float(pi[mask].max()) if mask.any() else None)
        bad=np.flatnonzero(((sense=='<')&(pi>0))|((sense=='>')&(pi<0)))
        first=None if not len(bad) else dict(index=int(bad[0]),name=str(names[bad[0]]),family=str(names[bad[0]]).split('[',1)[0],sense=str(sense[bad[0]]),raw_Pi=float(pi[bad[0]]),scaling_multiplier=1.,expected_sign='nonpositive' if sense[bad[0]]=='<' else 'nonnegative',RMP42_Pi=float(oldpi[bad[0]]) if bad[0]<len(oldpi) else None)
        write('SIGN_CONVENTION_AUDIT.json',dict(PASS=audit['strict_sense_sign_PASS'],conventions=family,first_failure=first,
            transform='identity +1; original CSR, RHS and senses transported verbatim; no normalization/negation',
            sign_transform_bug=False if first else None,raw_Pi_not_clipped=True,snapshot_saved_before_gate=True))
    corrected=corrected_audit()
    result=dict(EXACT_DUAL_AUTHORITY_PASS=bool(audit['PASS'] and corrected['PASS']),audit=audit,
        corrected_bound_reconstruction_PASS=corrected['PASS'],first_failed_row=first,
        initial_fullscale_RMP_calls=1,repaired_revalidation_calls=0,BAP_calls=0,pricing_calls=0,
        initial_native_runtime=m.Runtime,total_wall_seconds=time.perf_counter()-start,
        root_CG_continuation=False,BAP7200=False,P2=False,memory_guards=False)
    write('RESULT.json',result);print(json.dumps(result),flush=True)
    m.dispose()
if __name__=='__main__':
    try:run()
    except Exception:
        if OUT.exists():write('DRIVER_ERROR.json',dict(traceback=traceback.format_exc()))
        raise
