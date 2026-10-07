"""Read-only scientific readers and new-namespace I/O; no model/solve."""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import csv, hashlib, importlib.util, json, math, subprocess, sys
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
hc=module('target_readers',ROOT/'docs/v42_m1_gap_rootcause_20261007/common.py')
PREVIOUS=ROOT/'docs/v42_m1_hamming48_600s_20261007'
BASE='5d5718f5cfdc173eb2dd0a4c9f1ee3da8a833667'
SCIENTIFIC='1d922c91eb27056a5ccc79c92ef18146707099ab'
LB=.5687116003498334;UB=.6306505800203936;T1=.5996810901851135
SETTINGS=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,DegenMoves=0,TimeLimit=600)
def exact(v):return v if isinstance(v,F) else F.from_float(float(v))
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
    p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(clean(v),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def table(n,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/n).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(clean(rows))
def stamp():return datetime.now(timezone.utc).isoformat()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').strip()
def protected():
    folders=[PREVIOUS,ROOT/'docs/v42_m1_hamming48_20261007',hc.OUT,hc.HISTORY,hc.PARENT]
    return {p.relative_to(ROOT).as_posix():sha(p) for folder in folders for p in folder.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.suffix!='.pyc'}
def down(v):
    f=float(v)
    return float(np.nextafter(f,-np.inf)) if exact(f)>v else f
def up(v):
    f=float(v)
    return float(np.nextafter(f,np.inf)) if exact(f)<v else f
def rowdict(A,i):
    return {int(j):exact(w) for j,w in zip(A.indices[A.indptr[i]:A.indptr[i+1]],A.data[A.indptr[i]:A.indptr[i+1]])}
def axes():
    with np.load(PREVIOUS/'GRID_SOURCE_REDUCTION_AXES.npz') as z:keep=z['keep']
    with np.load(hc.PARENT/'C3_RETAINED_AXES.npz') as z:c3=z['rows']
    with np.load(ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz') as z:c2=z['rows'];c1=z['C1_original_rows']
    original=c1[c2[c3]];out=np.full(len(original),-1,int)
    valid=(original>=0)&(original<len(keep));out[valid]=keep[original[valid]]
    return out
def state(a,u,s,t):
    terms,c=a.expression(f'arc[{u},{a.sites.index(s)*96+t}]')
    return terms,c
def native_cut(terms,rhs,d):
    # All involved selected columns are nonnegative. Downward coefficients
    # and upward RHS relax the exact <= row for the entire original domain.
    assert all(d['lower'][j]>=0 for j in terms)
    return {j:down(v) for j,v in terms.items() if v},up(rhs)
def encode_cut(id,family,terms,rhs,d,**meta):
    terms={j:v for j,v in terms.items() if v};n,r=native_cut(terms,rhs,d)
    return dict(id=id,family=family,terms={str(j):str(v) for j,v in terms.items()},rhs=str(rhs),native_terms=n,native_rhs=r,nnz=len(terms),**meta)
