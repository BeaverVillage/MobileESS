"""One user-authorized certificate-only original-matrix dual-simplex polish."""
import json,time,os,subprocess,traceback
import numpy as np
from audit_numerical_dual import ROOT,OUT,RAW,read,sha
from revalidate_rmp43 import canonical_rebuild
from reproduce_rmp43 import PARAMS
from v42_m_stage_root.dual_authority import capture,validate
POLISH=OUT/'polish'
SETTINGS=dict(PARAMS,Method=1,LPWarmStart=1,Presolve=0,NumericFocus=3,Quad=1,MarkowitzTol=.5,OptimalityTol=1e-9)
def write(name,value):
    POLISH.mkdir(parents=True,exist_ok=True)
    (POLISH/name).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf8')
def run():
    previous=read(OUT/'OFFLINE_CERTIFICATE_RESULT.json')
    assert previous['PASS'] is False and previous['native_solve_calls']==0
    POLISH.mkdir(exist_ok=True)
    with (POLISH/'ONE_NATIVE_POLISH_REGISTERED.json').open('x',encoding='utf8') as f:
        json.dump(dict(maximum_native_calls=1,source_snapshot_SHA=sha(RAW),pid=os.getpid(),
            source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            settings=SETTINGS,existing_acceptance_EPS=1e-8,
            reason='Offline rational primal-dual gap 1.74154325092717e-8 exceeds unchanged 1e-8 authority',
            exact_model_unchanged=True,retained_columns=1841,root_CG=False,early_BAP=False,BAP7200=False,P2=False),f,indent=2)
    m,v,meta=canonical_rebuild(RAW);m.reset(1)
    for key,value in SETTINGS.items():m.setParam(key,value)
    m.setAttr('VBasis',m.getVars(),v['raw_VBasis'].tolist());m.setAttr('CBasis',m.getConstrs(),v['raw_CBasis'].tolist());m.update()
    m.Params.LogFile=str(POLISH/'CERTIFICATE_ONLY_DUAL_SIMPLEX.log')
    write('PRE_SOLVE_IDENTITY.json',dict(fingerprint=hex(m.Fingerprint&0xffffffff),
        rows=m.NumConstrs,columns=m.NumVars,nnz=m.NumNZs,settings=SETTINGS,
        source_raw_snapshot_SHA=sha(RAW),same_exact_CSR_RHS_bounds_objective_and_axes=True,
        raw_basis_reused_only_at_identical_full_RMP_axes=True,primal_incumbent_warm_start=False,
        solver_tolerances_tightened_not_relaxed=True,acceptance_authority_unchanged=True,memory_guards=False))
    write('NATIVE_POLISH_CALL_STARTED.json',dict(native_calls=1,start=time.time(),settings=SETTINGS))
    print('ONE_CERTIFICATE_ONLY_DUAL_SIMPLEX_POLISH_STARTED',flush=True)
    m.optimize()
    write('NATIVE_POLISH_CALL_ENDED.json',dict(native_calls=1,status=m.Status,runtime=m.Runtime,iterations=m.IterCount,
        objective=m.ObjVal if m.SolCount else None))
    if m.Status!=2:
        write('FINAL_RESULT.json',dict(EXACT_DUAL_AUTHORITY_PASS=False,native_status=m.Status,native_solve_calls=1,
            reason='ONE_POLISH_NOT_OPTIMAL_NO_RETRY',root_CG=False,early_BAP=False,BAP7200=False,P2=False));m.dispose();return
    p=POLISH/'POLISHED_TERMINAL_BEFORE_GATE.npz';capture(m,p)
    print('POLISHED_RAW_SNAPSHOT_AND_NATIVE_QUALITY_SAVED_BEFORE_GATE',flush=True)
    raw_audit=validate(p)
    write('RAW_STRICT_GATE.json',raw_audit);m.dispose()
    result=subprocess.run([r'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe','-X','utf8',
        str(ROOT/'audit_numerical_dual.py'),'--certificate','--raw',str(p),'--out',str(POLISH)],cwd=ROOT)
    if result.returncode:raise RuntimeError('POLISH_AUDIT_FAILED_WITHOUT_RETRY')
    final=read(POLISH/'OFFLINE_CERTIFICATE_RESULT.json');final['native_solve_calls']=1;final['additional_native_calls']=0
    final['certificate_only_polish']=True;final['raw_native_strict_gate_PASS']=raw_audit['PASS']
    write('FINAL_RESULT.json',final);print(json.dumps(final),flush=True)
if __name__=='__main__':
    try:run()
    except Exception:
        write('DRIVER_ERROR.json',dict(traceback=traceback.format_exc()));raise
