import os,sys,json,time,hashlib,threading
from pathlib import Path
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
os.environ.pop('V41_FO_RECOVERY_PLAN',None)
sys.dont_write_bytecode=True
P=Path(__file__).absolute().parent;PREF=P
sys.path.insert(0,str(PREF))
from electrical_engine import Engine,BIND,STRESS,sha,record,read,NAMES,PF_TAN
from numerical_coefficients import Coefficients,AX,NL,NT,NW,build
from full_electrical_rows import evaluate_grid,matrix_for_slot
from frozen_binding import context,ROOT,EXPECTED
import numpy as np
LOCK=threading.RLock()
def install_output_paths():
    original=Path.resolve
    def resolve(p,strict=False):
        absolute=p.absolute()
        if absolute.is_relative_to(P):return absolute
        return original(p,strict=strict)
    Path.resolve=resolve
def save(p,v):
    p=Path(p);assert p.absolute().is_relative_to(P)
    with LOCK:
        p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.tmp')
        body=json.dumps(v,indent=2,ensure_ascii=False,default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x.item() if isinstance(x,np.generic) else str(x))
        for attempt in range(100):
            try:
                tmp.write_text(body,encoding='utf-8');os.replace(tmp,p);break
            except PermissionError:
                if attempt==99:raise
                time.sleep(.05)
def state(**kw):
    with LOCK:
        f=P/'STATUS.json';v=read(f) if f.exists() else {};v.update(kw,updated_unix=time.time(),pid=os.getpid());save(f,v)
def verify():
    assert read(PREF/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json')['status']=='IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS'
    assert sha(PREF/'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json')=='86d91887379cbb7b21e7e30933ff0532cc50a21416c1984c7c449aec21a535cf'
    for r in read(PREF/'ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json')['files']:assert sha(r['path'])==r['sha256'],r['path']
    for r in read(BIND/'RECONSTRUCTION_FREEZE_MANIFEST.json')['files']:assert sha(r['path'])==r['sha256'],r['path']
def new_context():
    ctx=context();ctx.coefficients=Coefficients();ctx.nodes=AX['nodes'];ctx.new_production_root=P
    ctx.input_shas={r['path']:r['sha256'] for r in ctx.input_sources};return ctx
def exact(pcc,mess,folder):
    from dayahead.v40a.grid import controls_from_trajectory
    folder=Path(folder);start=time.perf_counter();x=controls_from_trajectory(Coefficients(),pcc,mess)
    e=Engine(folder/'runtime');rows=[];states=[]
    try:
        for t in range(96):
            e.inputs(t,x[t]);e.solve();settled=bool(e.d.Solution.ControlActionsDone());a=e.arrays()
            vals=[np.sqrt(a[0]),np.abs(a[1]),np.abs(a[2]),np.abs(a[3])/np.array(AX['winding_rating_kVA'])]
            row=dict(slot=t,Vmin_pu=float(vals[0].min()),Vmax_pu=float(vals[0].max()),max_phase_line_loading_pu=float(vals[1].max()),max_transformer_phase_current_pu=float(vals[2].max()),max_transformer_winding_kva_pu=float(vals[3].max()),converged=True,controls_settled=settled,line_witness=AX['line'][int(vals[1].argmax())])
            row['feasible']=settled and row['Vmin_pu']>=.95-1e-9 and row['Vmax_pu']<=1.05+1e-9 and max(row[k] for k in ('max_phase_line_loading_pu','max_transformer_phase_current_pu','max_transformer_winding_kva_pu'))<=1+1e-9
            rows.append(row);states.append(e.state(t))
    finally:e.close()
    keys=['Vmin_pu','Vmax_pu','max_phase_line_loading_pu','max_transformer_phase_current_pu','max_transformer_winding_kva_pu']
    metrics={k:(min if k=='Vmin_pu' else max)(r[k] for r in rows) for k in keys}
    report=dict(status='PASS' if all(r['feasible'] for r in rows) else 'FAIL',metrics=metrics,slots=rows,wall_seconds=time.perf_counter()-start,source_pu=1.04,Vreg_V=123.5,alpha8500=.552,CAPBank3='OFF')
    save(folder/'AC_VALIDATION.json',report);save(folder/'CONTROL_STATES.json',states);np.savez_compressed(folder/'CONTROLS.npz',x=x,control_names=NAMES)
    return report
