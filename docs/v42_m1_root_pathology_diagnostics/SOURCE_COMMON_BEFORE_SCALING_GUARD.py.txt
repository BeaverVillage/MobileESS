"""Read-only scientific sources; all diagnostic writers use the new namespace."""
from pathlib import Path
import csv,json,os,hashlib,subprocess,time
import numpy as np
import gurobipy as gp
from scipy import sparse
from v42_monolithic.common import ROOT,UB,LB,original
from v42_monolithic.experiment import load_compact,attr

BASE='573517629a0445472da2f755460032ee9322e968'
OUT=ROOT/'docs/v42_m1_root_pathology_diagnostics'
LOCAL=ROOT.parent/'ROOT_DIAGNOSTICS_LOCAL'
OLD=ROOT/'docs/v42_m1_compact_exact_start'
CACHE=ROOT.parent/'COMPACT_MONOLITHIC_LOCAL'
LP_POLICY=dict(Threads=4,Seed=20260929,NumericFocus=1,FeasibilityTol=1e-8,OptimalityTol=1e-8)
MIP_POLICY=dict(LP_POLICY,Method=2,NodeMethod=1,IntFeasTol=1e-8,Heuristics=0,MIPGap=.005,MIPFocus=0)
TARGET={'original':.5718494620559795,'compact':.5718494622717606}
EXPECTED={'original':(954560,316743,8282350,0x14204d6e),'compact':(972540,316839,12678118,0x81269e47)}
SCIENTIFIC_SIGNATURES={'original':'a2d08eae6b9194f576e134c89da1d62a003e1304f751e480f5cd235f069ae821',
    'compact':'a4eab472d9c0831a0b9cc71f51cee7f4ecfa4126b4c57fedc3afd4ef62a9fe1f'}
GRID=lambda f:f.startswith(('injection_','response_','voltage_','line_','transformer_'))

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def stamp():return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def read(name):return json.loads((OUT/name).read_text(encoding='utf8'))
def dump(name,obj):
    p=OUT/name;tmp=p.with_suffix(p.suffix+'.tmp')
    with tmp.open('w',encoding='utf8',newline='\n') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    os.replace(tmp,p)
def table(name,rows,fields=None):
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def family(n):return str(n).split('[')[0]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def preserve():
    r=read('PR126_BASE_RECEIPT.json');assert all(sha(ROOT/x['path'])==x['sha256'] for x in r['files']),'BASE_PHYSICAL_BYTES_CHANGED'
    return len(r['files'])
def make(kind,env):
    m=original(env) if kind=='original' else load_compact(env)
    assert (m.NumConstrs,m.NumVars,m.NumNZs,int(m.Fingerprint)&0xffffffff)==EXPECTED[kind],'SOURCE_FINGERPRINT_MISMATCH'
    assert signature(m)==SCIENTIFIC_SIGNATURES[kind],'CANONICAL_SCIENTIFIC_MATRIX_MISMATCH'
    return m
def row_families(kind):
    with np.load(ROOT/'docs/v42_m1_integrality_gap_root_cause/F3_MODEL_AXIS.npz') as z:rows=z['rownames']
    if kind=='original':return rows
    extra=np.array(['compact_connected_lower','compact_connected_upper']*8942+['compact_terminal_node_definition']*96)
    assert len(rows)+len(extra)==972540
    return np.concatenate([rows,extra])
def signature(m,include_types=True):
    A=m.getA().tocsr();A.sort_indices();h=hashlib.sha256()
    arrays=[A.indptr,A.indices,A.data,np.array(m.getAttr('RHS')),np.array(m.getAttr('Sense')),np.array(m.getAttr('LB')),np.array(m.getAttr('UB')),np.array(m.getAttr('Obj'))]
    if include_types:arrays.append(np.array(m.getAttr('VType')))
    for a in arrays:h.update(a.dtype.str.encode());h.update(a.tobytes())
    h.update(float(m.ObjCon).hex().encode());h.update(str(m.ModelSense).encode())
    return h.hexdigest()
def lp_audit(m,x):
    A=m.getA();r=A@x-np.array(m.getAttr('RHS'));s=np.array(m.getAttr('Sense'))
    v=np.where(s=='=',abs(r),np.where(s=='<',r,-r))
    bounds=max(0.,float(np.max(np.array(m.getAttr('LB'))-x)),float(np.max(x-np.array(m.getAttr('UB')))))
    return dict(max_row_violation=max(0.,float(v.max())),rows_exceeding_1e8=int((v>1e-8).sum()),max_bound_violation=bounds,
                finite=bool(np.isfinite(x).all()),objective=float(np.array(m.getAttr('Obj'))@x+m.ObjCon),LP_only=True,certificate_update=False)
def freeze_check():
    f=read('SOURCE_FREEZE_AMENDED_PREFLIGHT.json' if (OUT/'SOURCE_FREEZE_AMENDED_PREFLIGHT.json').exists() else 'SOURCE_FREEZE.json')
    assert all(sha(ROOT/n)==s for n,s in f['sources'].items()),'DIAGNOSTIC_SOURCE_CHANGED'
    assert sha(OUT/'PREREGISTRATION.json')==f['preregistration_sha256']
    assert all(sha(Path(n))==s for n,s in f['inputs'].items()),'SOURCE_CACHE_CHANGED'
    preserve()
def snapshot(label):
    import psutil,platform
    from threadpoolctl import threadpool_info
    vm=psutil.virtual_memory();sw=psutil.swap_memory();procs=[]
    for p in psutil.process_iter(['pid','name','cmdline','memory_info']):
        try:
            d=p.info
            if any(v in (d['name'] or '').lower() for v in ['python','gurobi']):
                procs.append(dict(pid=d['pid'],name=d['name'],command_line=d['cmdline'],RSS=d['memory_info'].rss))
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    r=dict(utc=stamp(),worker_pid=os.getpid(),hardware=platform.platform(),CPU_percent=psutil.cpu_percent(interval=1),
        logical_cores=psutil.cpu_count(),available_logical_cores=len(psutil.Process().cpu_affinity()),RAM=vm._asdict(),swap_pagefile=sw._asdict(),
        active_Python_solver_processes=procs,threadpools=threadpool_info(),independent_jobs_allowed=True,RESOURCE_CONTENTION_ABSENCE_REQUIRED=False,
        Gurobi_Threads=4,environment={k:os.environ.get(k) for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']})
    dump('RESOURCE_'+label+'.json',r)
    assert vm.available>=4*1024**3,'ACTUAL_RAM_EXHAUSTION_RISK'
    return r
