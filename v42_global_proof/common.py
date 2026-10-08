"""Immutable scientific inputs and namespace-local output helpers. No solve on import."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_m1_global_physical_proof_20261008'
OUT.mkdir(parents=True, exist_ok=True)
for key in ('TEMP', 'TMP', 'TMPDIR', 'GIT_TMPDIR'):
    os.environ[key] = str(OUT / 'tmp')
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
(OUT / 'tmp').mkdir(exist_ok=True)
os.environ['PYTHONPYCACHEPREFIX'] = str(OUT / 'tmp/pycache')
os.environ['V42_SOURCE_AUTHORITY_DIR'] = str(ROOT / 'docs/v42_m1_gap_rootcause_20261007/source_authority')
import csv, hashlib, importlib.util, json, math, subprocess, sys, time
import numpy as np
from scipy import sparse
BASE = '4b19e85089171729a3225529a40cb00bf31f43d5'
LB = .5687116104049206
UB = .6284141956452488
CUTOFF = .60
PARENT = ROOT / 'docs/v42_m1_ultracompact_exact_20261006'
B2 = ROOT / 'docs/v42_m1_b2_root_validation_20261008'
ROUTE = ROOT / 'docs/v42_m1_group_branching_20261008/artifacts/source_authority/ROUTE_TABLE.json.gz'
EXPECTED = {'C3A_A.npz':'45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8',
    'C3A_DATA.npz':'20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467',
    'C3A_VALID_START.npz':'be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5'}
def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def clean(v):
    if isinstance(v, dict): return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v, (list,tuple,np.ndarray)): return [clean(x) for x in v]
    if isinstance(v, np.generic): return clean(v.item())
    if isinstance(v, float) and not math.isfinite(v): return None
    return v
def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    assert path.resolve().is_relative_to(OUT), 'WRITE_OUTSIDE_NEW_NAMESPACE'
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    os.replace(tmp,path)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
def load():
    for n,h in EXPECTED.items(): assert sha(PARENT/n)==h,n
    A=sparse.load_npz(PARENT/'C3A_A.npz').tocsr()
    with np.load(PARENT/'C3A_DATA.npz') as z:d={k:z[k].copy() for k in z.files}
    T=sparse.load_npz(B2/'artifacts/TEMPORAL_VALID_ROWS.npz').tocsr()
    with np.load(B2/'artifacts/TEMPORAL_VALID_ROW_DATA.npz') as z:r=z['rhs'].copy()
    AA=sparse.vstack([A,T],format='csr')
    dd=dict(d,rhs=np.r_[d['rhs'],r],sense=np.r_[d['sense'],np.full(len(r),'<')],
        row_names=np.r_[d['row_names'],np.array([f'temporal_reachability[{i}]' for i in range(len(r))])])
    assert A.shape==(582808,306040) and A.nnz==5351612
    assert T.shape==(651,306040) and T.nnz==1302
    assert AA.shape==(583459,306040) and AA.nnz==5352914
    assert int((d['types']=='B').sum())==9322
    return A,d,T,AA,dd
def physical_reader():
    hc=module('global_readonly_frozen_authority',ROOT/'docs/v42_m1_gap_rootcause_20261007/common.py')
    import v42_bootstrap.m1 as native
    original=native.native_inputs
    def relocated(bundle):
        assert sha(ROUTE)==bundle['route_table']['sha256']=='3a08a7485ccfa153a3cd944132a251e8360002ce479546e943d91a4de2f3fca9'
        copy=dict(bundle);copy['route_table']=dict(bundle['route_table'],path=str(ROUTE))
        return original(copy)
    native.native_inputs=relocated
    return hc.physical_reader()
def row_replay(A,d,x,integral=True):
    from v42_integrated.matrix import audit
    return audit(A,d,x,integral=integral,tolerance=1e-8)
def save(path,**arrays):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    assert path.resolve().is_relative_to(OUT)
    with path.open('wb') as f:np.savez_compressed(f,**arrays)
def forbid_optimize():
    import gurobipy as gp
    def forbidden(*a,**kw):raise AssertionError('OPTIMIZE_FORBIDDEN_DURING_ANALYSIS_OR_CHECKING')
    gp.Model.optimize=forbidden
