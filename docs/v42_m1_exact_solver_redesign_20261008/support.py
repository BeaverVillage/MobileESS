"""Read-only scientific authority; isolated artifact I/O. No optimize on import."""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import csv, hashlib, importlib.util, json, math, subprocess, sys, time
from fractions import Fraction as F
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); sys.modules[name]=m; s.loader.exec_module(m); return m
hc=module('redesign_readers',ROOT/'docs/v42_m1_gap_rootcause_20261007/common.py')
BASE='b86486a6f58d6c39a1ea4ff2c7e984372b6087a5'
SCIENTIFIC='1d922c91eb27056a5ccc79c92ef18146707099ab'
PREVIOUS=ROOT/'docs/v42_m1_hamming48_600s_20261007'
PR177=ROOT/'docs/v42_m1_p1_objective_t1_1800s_20261008'
LB=.5687116003498334; UB=.6306505800203936
SETTINGS=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,DegenMoves=0,Heuristics=0,CutPasses=0,TimeLimit=600)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def clean(v):
    if isinstance(v,F):return str(v)
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(tuple,list,np.ndarray)):return [clean(x) for x in v]
    if isinstance(v,np.generic):return clean(v.item())
    if isinstance(v,float) and not math.isfinite(v):return None
    return v
def write(n,v):
    p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(clean(v),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');os.replace(tmp,p)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def table(n,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r)); p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(clean(rows))
def stamp():return datetime.now(timezone.utc).isoformat()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').strip()
def protected():
    folders=[PR177,PREVIOUS,ROOT/'docs/v42_m1_hamming48_20261007',ROOT/'docs/v42_m1_target_rho_t1_20261007',ROOT/'docs/v42_m1_target_rho_t1_1800s_20261007',hc.OUT,hc.HISTORY,hc.PARENT]
    return {p.relative_to(ROOT).as_posix():sha(p) for folder in folders for p in folder.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.suffix!='.pyc'}
def finite(v):return float(v) if math.isfinite(float(v)) and abs(float(v))<1e90 else None
def parameters(m):
    out={}
    for n in dir(m.Params):
        if n.startswith('_'):continue
        try:
            info=m.getParamInfo(n)
            if info is not None:out[n]=info[2]
        except (AttributeError,RuntimeError):pass
    return out
def full_replay(A,d,x,reader=None):
    raw=hc.replay(A,d,x,True); physical=None
    if raw['PASS']:
        reader=reader or hc.physical_reader();physical=reader.check(x,A,d)
    return dict(PASS=bool(raw['PASS'] and physical and physical['PASS']),original_C3A=raw,full_physical=physical,no_repairs=True,raw_vector_unchanged=True)
