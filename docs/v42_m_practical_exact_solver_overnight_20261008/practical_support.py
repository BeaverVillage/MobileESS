"""Read-only original scientific authority and crash-safe overnight storage."""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import csv,hashlib,importlib.util,json,math,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
OLD=ROOT/'docs/v42_m1_exact_solver_redesign_20261008'
sys.path.insert(0,str(ROOT))
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
authority=module('overnight_authority',OLD/'support.py')
verifier=module('overnight_objective',OLD/'objective_identity.py')
hc=authority.hc;BASE=authority.BASE;INITIAL_LB=authority.LB;INITIAL_UB=authority.UB
SETTINGS=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,DegenMoves=0)
sha=authority.sha;clean=authority.clean;finite=authority.finite;parameters=authority.parameters;full_replay=authority.full_replay
def stamp():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def atomic(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.tmp')
    with tmp.open('w',encoding='utf-8',newline='\n') as f:
        json.dump(clean(value),f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
def point_save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.tmp')
    with tmp.open('wb') as f:np.savez_compressed(f,x=x);f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
def table(p,rows):
    p=Path(p);fields=list(dict.fromkeys(k for r in rows for k in r));tmp=p.with_name(p.name+'.tmp')
    with tmp.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(clean(rows));f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').strip()
def deadline():return datetime.fromisoformat(read(OUT/'IMMUTABLE_DEADLINE.json')['deadline_UTC'])
def remaining(reserve=0,now=None):return (deadline()-(now or datetime.now(timezone.utc))).total_seconds()-reserve
def bounded_limit(request,reserve=900):
    result=min(float(request),remaining(reserve));assert result>0,'IMMUTABLE_DEADLINE_EXHAUSTED';return result
def severe_warnings(log):
    import re
    return [l for l in log.splitlines() if re.search(r'numerical trouble|numeric error|numerical difficulties|unscaled.*violation|infeasible or unbounded|unreliable|unstable',l,re.I)]
def native_bound_valid(receipt,identity_pass,restricted,validated_UB,log):
    bound=receipt.get('ObjBound');reasons=[]
    if restricted:reasons.append('RESTRICTED_PRIMAL_BOUND_NOT_GLOBAL')
    if not identity_pass:reasons.append('OBJECTIVE_OR_DOMAIN_IDENTITY_FAILED')
    if receipt['Status'] not in (2,9,11):reasons.append('STATUS_OUTSIDE_INHERITED_NATIVE_CONTRACT')
    if receipt.get('callback_errors') or receipt.get('exception'):reasons.append('EXECUTION_ERROR')
    if severe_warnings(log):reasons.append('SEVERE_NUMERICAL_WARNING')
    if bound is None or not math.isfinite(bound):reasons.append('BOUND_UNAVAILABLE')
    elif bound>validated_UB:reasons.append('BOUND_CONTRADICTS_VALIDATED_UB')
    return dict(PASS=not reasons,reasons=reasons,global_LB_candidate=bound if not reasons else None,authority='Inherited full original native MILP certificate contract; not an exact rational external LP certificate')
