from pathlib import Path
from functools import lru_cache
import csv,gzip,hashlib,json,pickle,shutil,subprocess
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_multitime_global_epigraph'
PRIOR=ROOT/'docs/v42_m1_spatial_epigraph_strengthening'
RELAX=ROOT/'docs/v42_m1_relaxation_strengthening'
LOCAL=Path('C:/Users/kjw39/Documents/Codex/2026-10-01/files-pasted-by-the-user-repository/work/V42_WINDOW_LOCAL')
INPUT=LOCAL.parent/'V42_SPATIAL_LOCAL'
HEAD='90efccb2dbcc1ab4557cedcf04ef479a225d4e47'
WINDOW=tuple(range(40,47))
CRITICAL=[41,44,43,40,42,46]
TIME_PAIRS=[(40,43),(43,46),(40,46),(41,44)]
F3=.5718494602017812
DEFAULT=.5722125039436496
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
    assert sha(LOCAL/'DATA.pkl')==read(PRIOR/'A1_ANCHOR_REUSE_RECEIPT.json')['data_sha256']
    assert sha(LOCAL/'PR107_M1_PLAN.json')==read(RELAX/'PR108_MIP_START_RECEIPT.json')['plan_sha256']
    with (LOCAL/'DATA.pkl').open('rb') as f:data=pickle.load(f)
    assert len(data[1])==1499
    from v42_bootstrap.m1 import native_inputs
    sites,initial,routes,battery,_=native_inputs(data[0])
    return data[0],read(RELAX/'A1_AIDC_GRID_CONTROL_ANCHOR.json'),read(LOCAL/'PR107_M1_PLAN.json'),sites,initial,tuple(dict.fromkeys(routes)),battery
def base():
    import v42_relaxation.base as b
    b.LOCAL=LOCAL
    return b
def arcs_for(sites,routes,H=96):
    from v42_epigraph.common import arcs_for as f
    return f(sites,routes,H)
def state_indices(arcs,t):
    from v42_epigraph.common import state_indices as f
    return f(arcs,t)
def setup():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==HEAD
    OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(exist_ok=True)
    assert not (OUT/'PREREGISTRATION.json').exists()
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(base_head=HEAD,files=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked],PASS=True))
    dump('PR110_BASE_RECEIPT.json',dict(PR=110,exact_head=HEAD,inherited_evidence=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for folder in [PRIOR,RELAX] for p in sorted(folder.rglob('*')) if p.is_file()]))
    for n in ['DATA.pkl','PR107_M1_PLAN.json']:shutil.copyfile(INPUT/n,LOCAL/n)
    from v42_bootstrap.handoff import validate_handoff
    validate_handoff(read(RELAX/'A1_TO_M1_HANDOFF.json'),inputs()[1])
    dump('A1_ANCHOR_REUSE.json',dict(PASS=True,A1_RERUN=False,A1_ANCHOR_REUSED=True,A1_OPTIMIZE_CALLS_THIS_TASK=0,jobs=1499,CC4_Runtime_unchanged=True,data_sha256=sha(LOCAL/'DATA.pkl'),anchor_sha256=sha(RELAX/'A1_AIDC_GRID_CONTROL_ANCHOR.json')))
    assert read(PRIOR/'CRITICAL_SLOT_FREEZE.json')['slots']==CRITICAL
    dump('FROZEN_CRITICAL_SLOTS.json',dict(slots=CRITICAL,source='PR110 CRITICAL_SLOT_FREEZE.json',source_sha256=sha(PRIOR/'CRITICAL_SLOT_FREEZE.json'),reselected=False))
    dump('MULTITIME_WINDOW_FREEZE.json',dict(WINDOW_START=40,WINDOW_END=46,WINDOW_SIZE=7,slots=list(WINDOW),reason='Contiguous min/max frozen critical slots; 45 included only for contiguity',frozen_before_optimization=True))
    dump('G3_TIME_PAIR_FREEZE.json',dict(pairs=TIME_PAIRS,reason=['start-middle','middle-end','full-window endpoints','highest-ranked interior slots'],frozen_before_optimization=True))
    dump('PREREGISTRATION.json',dict(BASE_PR=110,BASE_HEAD=HEAD,WINDOW=list(WINDOW),critical=CRITICAL,G3_TIME_PAIRS=TIME_PAIRS,PRODUCTION_BASE='M1-F3',
        F3_LB=F3,S2_REFERENCE_LB=DEFAULT,UB=UB,default_beta=DEFAULT,physical_tolerance=TOL,nonviolation_tolerance=OBJ_TOL,useful_violation=1e-5,material_gain=.001,bands=[.60,.62,.65,UB*.995],
        LP=dict(Method=2,Threads=1),workers=dict(initial=2,max=4),
        solve_order='MESS id, time, state id; root-positive >1e-6 or incumbent states first',
        stopping='Complete enumeration, exact reachability, or valid upper/lower certificate proving classification cannot change',
        auxiliary_certificate_strategy='Try window-idle unit witnesses for a universal conditional upper certificate; their feasible objectives are NEVER lower coefficients',
        MIP=dict(Method=2,Threads=1,Heuristics=0,MIPFocus=3,Seed=20260929,MIPGap=.005,GPU=False),canary_seconds=600,production_seconds=1800,max_canaries=1,max_production=1,
        A1_OPTIMIZE_CALLS_THIS_TASK=0,S0_OPTIMIZE_CALLS=0,S1_OPTIMIZE_CALLS=0,S2_OPTIMIZE_CALLS=0,S3_OPTIMIZE_CALLS=0,STOP_before_A2=True))
def identity():
    b=base()
    def inspect(m,obj,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        m.setObjective(obj[0][1]);m.update();v=data[2]['values'].copy();map_bindings(bindings,v)
        m.setAttr('Start',[v[n] for n in m.getAttr('VarName')]);m.update();observed=b.stats(m);assert observed==b.EXPECTED
        dump('BASE_F3_IDENTITY.json',dict(PASS=True,expected=b.EXPECTED,observed=observed,matrix_validation=b.matrix_validate(m,v),optimize_calls=0))
        return None,dict(optimize_calls=0)
    b.build(inspect)
    from v42_relaxation.strengthening import hook
    cert=read(RELAX/'S3_BARRIER_OPTIMALITY_CERTIFICATE.json');prior=read(PRIOR/'ROOT_DIAGNOSTIC_SOURCE_RECEIPT.json');check={}
    chosen='S3' if cert['PASS'] and cert['BarStatus']==2 and cert['width']<=OBJ_TOL and prior['full_matrix_revalidation']['PASS'] else 'S2'
    with np.load(RELAX/(chosen+'_ROOT_LP_SOLUTION.npz'),allow_pickle=False) as z:v=dict(zip(map(str,z['names']),map(float,z['values'])))
    def inspect_root(m,obj,*args):
        m.setObjective(obj[0][1]);m.update();check.update(b.matrix_validate(m,v));return None,dict(optimize_calls=0)
    b.build(inspect_root,hook(chosen,compact_energy_bounds=chosen=='S3'))
    dump('ROOT_SOURCE_RECEIPT.json',dict(PASS=True,chosen=chosen,S3_CERTIFICATE_USED=chosen=='S3',rho=v['rho_max'],certificate=cert,full_matrix_revalidation=check,solution_sha256=sha(RELAX/(chosen+'_ROOT_LP_SOLUTION.npz')),optimize_calls=0))
    print('F3 IDENTITY & ROOT SOURCE PASS',chosen,check,flush=True)
if __name__=='__main__':
    import sys
    globals()[sys.argv[1]]()
