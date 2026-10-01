from pathlib import Path
from functools import lru_cache
import csv,gzip,hashlib,json,pickle,shutil,subprocess
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_integrality_gap_root_cause'
RELAX=ROOT/'docs/v42_m1_relaxation_strengthening'
PRIOR=ROOT/'docs/v42_m1_spatial_epigraph_strengthening'
LOCAL=Path('C:/Users/kjw39/Documents/Codex/2026-10-01/files-pasted-by-the-user-repository/work/V42_FORENSIC_LOCAL')
INPUT=LOCAL.parent/'V42_SPATIAL_LOCAL'
HEAD='90efccb2dbcc1ab4557cedcf04ef479a225d4e47'
F3=.5718494602017812
S2=.5722125039436496
UB=.6696147314213984
TOL=1e-5
OBJ_TOL=1e-7
EPS=1e-6

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def dump(n,v):
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/n;tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');tmp.replace(p)
def table(n,rows,fields=None):
    with (OUT/n).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def csvread(n):
    with (OUT/n).open(encoding='utf8') as f:return list(csv.DictReader(f))
@lru_cache(None)
def inputs():
    assert sha(LOCAL/'DATA.pkl')==read(RELAX/'PR108_A1_ANCHOR_REUSE.json')['data_sha256']
    assert sha(LOCAL/'PR107_M1_PLAN.json')==read(RELAX/'PR108_MIP_START_RECEIPT.json')['plan_sha256']
    with (LOCAL/'DATA.pkl').open('rb') as f:d=pickle.load(f)
    assert len(d[1])==1499
    from v42_bootstrap.m1 import native_inputs
    sites,initial,routes,b,_=native_inputs(d[0])
    return d[0],read(RELAX/'A1_AIDC_GRID_CONTROL_ANCHOR.json'),read(LOCAL/'PR107_M1_PLAN.json'),sites,initial,tuple(dict.fromkeys(routes)),b
def base():
    import v42_relaxation.base as b
    b.LOCAL=LOCAL
    return b
def arcs_for(sites,routes,H=96):
    from v42_epigraph.common import arcs_for as f
    return f(sites,routes,H)
def selected_arc(a,start,end):
    """Occupancy intersects W or departs from a W node; never prune arcs."""
    return (a[1]<=end and a[3]>start) or start<=a[1]<=end
def root_values():
    chosen=read(OUT/'ROOT_SOURCE_RECEIPT.json')['selected']
    with np.load(RELAX/(chosen+'_ROOT_LP_SOLUTION.npz'),allow_pickle=False) as z:v=dict(zip(map(str,z['names']),map(float,z['values'])))
    _,_,_,sites,initial,routes,_=inputs();arcs=arcs_for(sites,routes)
    for u in initial:
        for k in range(len(arcs)):v.setdefault(f'arc[{u},{k}]',0.)
        for s in sites:
            for t in range(96):
                for f in ['Pch','Pdis','Q']:v.setdefault(f'{f}[{u},{s},{t}]',0.)
    return v
def setup():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==HEAD
    assert not (OUT/'PREREGISTRATION.json').exists()
    OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(exist_ok=True)
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,base_head=HEAD,files=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked]))
    dump('PR110_BASE_RECEIPT.json',dict(PR=110,exact_head=HEAD,inherited_evidence=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for folder in [RELAX,PRIOR] for p in sorted(folder.rglob('*')) if p.is_file()]))
    for n in ['DATA.pkl','PR107_M1_PLAN.json']:shutil.copyfile(INPUT/n,LOCAL/n)
    from v42_bootstrap.handoff import validate_handoff
    validate_handoff(read(RELAX/'A1_TO_M1_HANDOFF.json'),inputs()[1])
    dump('A1_ANCHOR_REUSE.json',dict(PASS=True,A1_RERUN=False,jobs=1499,A1_OPTIMIZE_CALLS=0,data_sha256=sha(LOCAL/'DATA.pkl'),anchor_sha256=sha(RELAX/'A1_AIDC_GRID_CONTROL_ANCHOR.json')))
    dump('PREREGISTRATION.json',dict(BASE_PR=110,BASE_HEAD=HEAD,F3_LB=F3,S2_LB=S2,retained_UB=UB,model='Original sparse M1-F3, no S2 extensions in diagnostic models',
        active_rule='rho_star-rho[t]<=1e-7 AND P1 abs dual mass[t]>=1e-6',face_tolerance=1e-7,positive_mass=EPS,physical_tolerance=TOL,
        BUFFER=8,partial_arms=['R_ROUTE_ONLY','R_ACTIVE','R_BUFFER'],partial_seconds=600,unit_gate='R_ACTIVE LB_gain>=0.001',unit_seconds=300,
        UB_arms=['P_FIXED_ALL','P_FIXED_ROUTE','P_LATE_ROUTE_NEIGHBORHOOD'],fixed_route_seconds=300,late_seconds=600,
        LP=dict(Method=2,Threads=1),MIP=dict(Method=2,Threads=1,Heuristics=0,MIPFocus=3,MIPGap=.005,Seed=20260929,GPU=False),
        LB_thresholds=[.001,.01,.03,.05],UB_thresholds=[.001,.005,.01],negative_certificate='OPTIMAL to solver tolerance with bounded interval OR matrix-validated partial feasible upper-F3<=0.001; no motion of BestBd alone is inconclusive',
        classification=dict(A='partial gain>=.01 and UB_gain<.005',B='certified partial nonmaterial and UB_gain>=.005',C='partial gain>=.001 and UB_gain>=.005',D='R_ACTIVE/R_BUFFER certified nonmaterial and UB_gain<.005',E='required negative evidence absent'),
        A1_OPTIMIZE_CALLS=0,S1_OPTIMIZE_CALLS=0,S2_OPTIMIZE_CALLS=0,S3_OPTIMIZE_CALLS=0,production=False,new_cuts=False,STOP_before_A2=True))
if __name__=='__main__':setup()
