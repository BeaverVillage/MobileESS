"""Isolated root-gap diagnosis; imports historical readers, never their mains."""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import csv, hashlib, importlib.util, json, math, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import sparse
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
HISTORY = ROOT/'docs/v42_m1_root_gap_attribution_20261007'
PARENT = ROOT/'docs/v42_m1_ultracompact_exact_20261006'
BASE = '0d423626790a1102d42e6ba84beeb5f7d4ab1d4b'
UB = .6694159238756877
LB = .5687116003498334
REQUIRED = UB*.995-LB
sys.path.insert(0, str(ROOT))

def module(name, path):
    spec=importlib.util.spec_from_file_location(name, path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
history_authority=module('gap_history_authority', HISTORY/'independent_hull.py')
exact_bound_module=module('gap_history_bound', HISTORY/'numerical_bound_audit.py')
ORIGINAL_SOURCE_LOCATION=history_authority.SOURCE
bundled_source=OUT/'source_authority'
selected_source=Path(os.environ.get('V42_SOURCE_AUTHORITY_DIR',str(bundled_source)))
if all((selected_source/name).is_file() for name in ('FULL_A.npz','FULL_DATA.npz','DATA.pkl')):
    # Read-only relocation of the same frozen bytes; historical files untouched.
    import v42_degen.common as degen_authority
    import v42_strengthening.common as strengthening_authority
    import v42_strengthening.analysis as graph_authority
    history_authority.SOURCE=selected_source
    degen_authority.SOURCE=selected_source
    strengthening_authority.SOURCE=selected_source
    graph_authority.SOURCE=selected_source
Authority=history_authority.Authority
exact_bounded_lagrangian=exact_bound_module.exact_bounded_lagrangian

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not math.isfinite(x):return None
    return x
def write(name,x):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def table(name,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def stamp():return datetime.now(timezone.utc).isoformat()
def load():
    expected={'C3A_A.npz':'45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8','C3A_DATA.npz':'20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467','C3A_VALID_START.npz':'be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5'}
    for n,h in expected.items():assert sha(PARENT/n)==h,n
    A=sparse.load_npz(PARENT/'C3A_A.npz').tocsr()
    with np.load(PARENT/'C3A_DATA.npz') as z:d={k:z[k] for k in z.files}
    with np.load(PARENT/'C3A_VALID_START.npz') as z:x=z['point'].copy()
    return A,d,x
def replay(A,d,x,integral=False):
    from v42_integrated.matrix import audit
    if 'types' not in d:
        assert not integral,'INTEGRAL_REPLAY_REQUIRES_TYPES'
        d=dict(d,types=np.full(A.shape[1],'C'))
    return audit(A,d,x,integral=integral,tolerance=1e-8)
def physical_reader():
    # Only instantiate the saved inverse + frozen validator; no historical write/main.
    m=module('gap_physical_replay', HISTORY/'aborted_1h_provenance/run_one.py')
    m.ROOT=ROOT
    m.PARENT=PARENT
    return m.PhysicalReplay()
def once(stage,settings,scope):
    assert (OUT/'PREREGISTRATION.md').is_file()
    assert read(OUT/'UB_VALIDATION.json')['PASS'] and read(OUT/'LB_VALIDATION.json')['PASS']
    p=OUT/(stage+'_ONCE.json')
    with p.open('x',encoding='utf-8') as f:json.dump(dict(stage=stage,UTC=stamp(),settings=settings,scope=scope,optimize_calls=1),f,ensure_ascii=False,indent=2)
def snapshot(name):
    import psutil
    processes=[]
    for p in psutil.process_iter(['pid','name','cmdline','create_time']):
        try:
            if p.info['name'] and ('python' in p.info['name'].lower() or 'gurobi' in p.info['name'].lower()):processes.append(p.info)
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    write(name,dict(UTC=stamp(),processes=processes,memory=dict(psutil.virtual_memory()._asdict()),other_workers_untouched=True,overlap_is_not_controlled_performance_benchmark=True))
