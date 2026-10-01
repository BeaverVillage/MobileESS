from pathlib import Path
from functools import lru_cache
import csv, hashlib, json, pickle, subprocess
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/v42_m1_spatial_epigraph_strengthening'
PRIOR = ROOT/'docs/v42_m1_relaxation_strengthening'
LOCAL = Path('C:/Users/kjw39/Documents/Codex/2026-10-01/files-pasted-by-the-user-repository/work/V42_SPATIAL_LOCAL')
INPUT = Path('C:/Users/kjw39/Documents/Codex/2026-10-01/files-pasted-by-the-user-repository/work/V42_RELAXATION_LOCAL')
HEAD = '6dabb39e3ae6bb36c4ac47725c0e11d5bbc1b812'
F3 = .5718494602017812
DEFAULT = .5722125039436496
UB = .6696147314213984
TOL = 1e-5
OBJ_TOL = 1e-7
EPS = 1e-6

def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf8'))
def dump(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name;tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');tmp.replace(p)
def table(name,rows,fields=None):
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def csvread(name):
    with (OUT/name).open(encoding='utf8') as f:return list(csv.DictReader(f))

@lru_cache(None)
def inputs():
    assert sha(LOCAL/'DATA.pkl')==read(PRIOR/'PR108_A1_ANCHOR_REUSE.json')['data_sha256']
    assert sha(LOCAL/'PR107_M1_PLAN.json')==read(PRIOR/'PR108_MIP_START_RECEIPT.json')['plan_sha256']
    with (LOCAL/'DATA.pkl').open('rb') as f:data=pickle.load(f)
    assert len(data[1])==1499
    from v42_bootstrap.m1 import native_inputs
    sites,initial,routes,battery,_=native_inputs(data[0])
    # Native constructor deduplicates route authority, preserving its exact order.
    routes=tuple(dict.fromkeys(routes))
    return data[0],read(PRIOR/'A1_AIDC_GRID_CONTROL_ANCHOR.json'),read(LOCAL/'PR107_M1_PLAN.json'),sites,initial,routes,battery

def configure_inherited():
    import v42_relaxation.base as base
    base.LOCAL=LOCAL
    return base

def arcs_for(sites,routes,H=96):
    return [(s,t,s,t+1,None) for s in sites for t in range(H)]+[(r.source,r.depart,r.destination,r.connect,r) for r in routes]

def state_indices(arcs,t):
    # A stay arc covers [t,t+1); travel occupies departure <= t < connection.
    return {s:[k for k,a in enumerate(arcs) if a[-1] is None and a[:2]==(s,t)] for s in sorted({a[0] for a in arcs})}|{'TRANSIT':[k for k,a in enumerate(arcs) if a[-1] is not None and a[1]<=t<a[3]]}

def reachable_arcs(sites,initial,routes,H=96):
    from collections import defaultdict
    arcs=arcs_for(sites,routes,H);by_time=defaultdict(list)
    for k,a in enumerate(arcs):by_time[a[1]].append(k)
    result={}
    for u,origin in initial.items():
        reachable={(origin,0)};ks=set()
        for t in range(H):
            for k in by_time[t]:
                a=arcs[k]
                if a[:2] in reachable:reachable.add((a[2],a[3]));ks.add(k)
        result[u]=ks
    return result

def root_values():
    source=read(OUT/'ROOT_DIAGNOSTIC_SOURCE_RECEIPT.json')['solution']
    with np.load(ROOT/source,allow_pickle=False) as z:v=dict(zip(map(str,z['names']),map(float,z['values'])))
    _,_,_,sites,initial,routes,_=inputs();arcs=arcs_for(sites,routes)
    for u in initial:
        for k in range(len(arcs)):v.setdefault(f'arc[{u},{k}]',0.)
        for s in sites:
            for t in range(96):
                for family in ['Pch','Pdis','Q']:v.setdefault(f'{family}[{u},{s},{t}]',0.)
    return v

def setup():
    import shutil
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==HEAD
    assert not (OUT/'PREREGISTRATION.json').exists(),'ALREADY_PREREGISTERED'
    OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(exist_ok=True)
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(base_head=HEAD,files=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked],PASS=True))
    dump('PR109_BASE_RECEIPT.json',dict(PR=109,exact_head=HEAD,inherited_evidence=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(PRIOR.rglob('*')) if p.is_file()]))
    for n in ['DATA.pkl','PR107_M1_PLAN.json']:shutil.copyfile(INPUT/n,LOCAL/n)
    bundle,anchor,prior,*_=inputs()
    from v42_bootstrap.handoff import validate_handoff
    validate_handoff(read(PRIOR/'A1_TO_M1_HANDOFF.json'),anchor)
    dump('A1_ANCHOR_REUSE_RECEIPT.json',dict(PASS=True,A1_OPTIMIZE_CALLS=0,A1_RERUN=False,A1_ANCHOR_REUSED=True,jobs=1499,CC4_Runtime_unchanged=True,
        data_sha256=sha(LOCAL/'DATA.pkl'),anchor_sha256=sha(PRIOR/'A1_AIDC_GRID_CONTROL_ANCHOR.json'),handoff_sha256=sha(PRIOR/'A1_TO_M1_HANDOFF.json')))
    dump('PREREGISTRATION.json',dict(BASE_PR=109,BASE_HEAD=HEAD,PRODUCTION_BASE='M1-F3',F3_LB=F3,S2_LB=DEFAULT,existing_UB=UB,
        physical_tolerance=TOL,objective_tolerance=OBJ_TOL,state_priority_mass=EPS,K=6,selection='descending incumbent rho[t] minus diagnostic root rho[t]; lower index first',
        E2_slots='first three frozen slots',E2_pairs='all six unordered pairs',oracle=dict(Method=2,Threads=1,initial_workers=2,max_workers=4,grid='only original P1 line faces at selected time; all voltage and transformer grid rows dropped; full horizon native MESS physics retained'),
        E1_install_violation=1e-5,E2_install_violation=1e-5,noncut_tolerance=OBJ_TOL,beta_default=DEFAULT,
        material_gain=.001,bands=[.60,.62,.65,UB*.995],MIP=dict(Method=2,Threads=1,Heuristics=0,MIPFocus=3,Seed=20260929,MIPGap=.005,GPU=False),
        canary=dict(seconds=600,max_runs=1),production=dict(seconds=1800,max_runs=1,cumulative_budget=True),A1_optimize_calls=0,STOP_before_A2=True))

if __name__=='__main__':setup()
