from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,csv,subprocess,uuid,threading,time
import numpy as np
import psutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_may_b1_supercompact_production_20261007'
SC_OUT=ROOT/'docs/v42_a1_pr134_supercompact_exact_20261007'
BASE='52ef855a59144a7c561df44b81dc2ad265babdbd'
CHECKER='0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51'
CODE=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
DAYS=tuple(f'2025-05-{i:02d}' for i in range(1,32))
STAGES=('A1','PLANNING_FREEZE','ACTUAL','FRESH_AC','VALIDATION')
SETTINGS=dict(Threads=1,Method=1,Seed=20260929,MIPGap=.005,Presolve=-1,Cuts=-1,Heuristics=.05,NumericFocus=0,FeasibilityTol=1e-6,OptimalityTol=1e-6,IntFeasTol=1e-5)
BUDGET=3600.
_write_locks={}
_write_locks_mutex=threading.Lock()
def write_lock(path):
    key=str(path.resolve()).casefold()
    with _write_locks_mutex:return _write_locks.setdefault(key,threading.RLock())
def replace_file(temp,path):
    # Windows may briefly deny replacement while another process opens the
    # status file. Retry only that file-sharing race, never a resource gate.
    for attempt in range(100):
        try:os.replace(temp,path);return
        except PermissionError as e:
            if getattr(e,'winerror',None) not in (5,32) or attempt==99:raise
            time.sleep(.001)
def now():return datetime.now(timezone.utc).isoformat()
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(tuple,list,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,Path):return str(x)
    if isinstance(x,float) and not np.isfinite(x):return str(x)
    return x
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(x):return hashlib.sha256(json.dumps(clean(x),sort_keys=True,separators=(',',':')).encode()).hexdigest()
def record(p):return dict(path=str(Path(p).resolve()),sha256=sha(p),bytes=Path(p).stat().st_size)
def atomic(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    with write_lock(p):
        try:
            t.write_text(json.dumps(clean(v),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n');replace_file(t,p)
        finally:
            t.unlink(missing_ok=True)
def table(p,rows,fields):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    with write_lock(p):
        try:
            with t.open('w',encoding='utf8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n',extrasaction='ignore');w.writeheader();w.writerows(clean(r) for r in rows)
            replace_file(t,p)
        finally:t.unlink(missing_ok=True)
def process(pid=None):
    p=psutil.Process(pid or os.getpid());return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),parent=p.ppid(),priority=int(p.nice()))
def same_process(row):
    try:
        p=psutil.Process(row['PID']);return p.create_time()==row['created'] and p.cmdline()==row['command']
    except (KeyError,psutil.Error):return False
def identity(freeze,day,stage):
    return dict(run_id=freeze['run_id'],Git_SHA=freeze['Git_SHA'],scientific_SHA=freeze['scientific_SHA'],
                input_SHA=freeze['day_input_SHA'][day],checker_SHA=CHECKER,day=day,stage=stage,stage_version=1)
def verify_freeze(freeze):
    if freeze['scientific_base']!=BASE or freeze['solver']!=SETTINGS or freeze['native_budget']!=BUDGET:raise PermissionError('SCIENTIFIC_AUTHORITY_DRIFT')
    if any(freeze[k] for k in ('memory_guards','artificial_slowdown','parameter_sweep','Actual_reoptimization','PQ_repair')):raise PermissionError('PROHIBITED_POLICY')
    for r in freeze['source_files']+freeze['immutable_artifacts']:
        if sha(r['path'])!=r['sha256']:raise PermissionError('FROZEN_SOURCE_OR_CERTIFICATE_DRIFT:'+r['path'])
def valid_receipt(receipt,expected,root):
    try:return receipt['PASS'] is True and receipt['identity']==expected and bool(receipt['files']) and all(Path(r['path']).resolve().is_relative_to(root.resolve()) and sha(r['path'])==r['sha256'] for r in receipt['files'])
    except (KeyError,OSError):return False
def classify(error):
    text=str(error)
    if 'DATE_TIMEOUT' in text:return 'TIMEOUT'
    if any(k in text for k in ('NUMERICAL','NATIVE_POINT','DETERMINISTIC_WAN','CERTIFICATE_FAIL')):return 'NUMERICAL_FAILURE'
    if 'FRESH_' in text or 'CONTROL_ACTIONS' in text:return 'FRESH_AC_FAILURE'
    if 'VALIDATION_FAIL' in text:return 'VALIDATION_FAILURE'
    # A native INFEASIBLE status alone is not a proof of scientific infeasibility.
    if 'INFEASIBLE' in text:return 'INCONCLUSIVE'
    return 'IMPLEMENTATION_FAILURE'
