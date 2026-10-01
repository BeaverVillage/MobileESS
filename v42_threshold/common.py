from pathlib import Path
from functools import lru_cache
from decimal import Decimal
import csv,gzip,hashlib,json,subprocess,time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_b3_threshold_certificate'
PR113=ROOT/'docs/v42_m1_late_window_certificate_mipstart'
PR112=ROOT/'docs/v42_m1_integrality_gap_root_cause'
RELAX=ROOT/'docs/v42_m1_relaxation_strengthening'
LOCAL=ROOT.parent/'THRESHOLD_LOCAL'
BASE='c554832083498179ddb936379772ed7715cd3192'
S2=.5722125039436496
ORIGINAL_UB=.5912812634331275
T=float(Decimal('0.5722125039436496')+Decimal('0.001'))
MATRIX_TOL=1e-6
INTEGER_TOL=1e-7
RHO_TOL=1e-7
THRESHOLD_MARGIN=1e-6
WINDOW=[58,95]
SOURCES=['BASE','S3']
COMMON_SETTINGS=dict(Method=1,NodeMethod=1,Seed=20260929,MIPFocus=1,Heuristics=.2,
    DegenMoves=0,CutPasses=1,FeasibilityTol=1e-7,IntFeasTol=1e-7,OptimalityTol=1e-7,
    NumericFocus=1,DualReductions=0,InfUnbdInfo=1,SoftMemLimit=12.,SolutionLimit=1)

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def dump(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name;tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8');tmp.replace(p)
def table(name,rows,fields=None):
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def prose(name,text):(OUT/name).write_text(text.strip()+'\n',encoding='utf8')
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT).decode().strip()
@lru_cache(None)
def axis():
    with np.load(PR112/'F3_MODEL_AXIS.npz',allow_pickle=False) as z:return {k:z[k] for k in z.files}
@lru_cache(None)
def domains():
    with np.load(PR113/'NESTING_DOMAIN_AXIS.npz',allow_pickle=False) as z:return z['B3']
@lru_cache(None)
def inputs():
    from v42_forensic.common import inputs as inherited
    return inherited()
@lru_cache(None)
def arcs():
    from v42_epigraph.common import arcs_for
    _,_,_,sites,_,routes,_=inputs();return arcs_for(sites,routes)
def root(source):
    p=RELAX/(source+'_ROOT_LP_SOLUTION.npz')
    with np.load(p,allow_pickle=False) as z:v=dict(zip(map(str,z['names']),map(float,z['values'])))
    return v,p
def full_start():
    with np.load(PR113/'MIP_START_EXACT.npz',allow_pickle=False) as z:return z['values']
def settings(kind):
    p=read(OUT/'PREREGISTRATION.json')
    return dict(COMMON_SETTINGS,Threads=p['threads'],TimeLimit=p['direct_seconds'] if kind=='DIRECT' else p['candidate_seconds'])
def classify(point,status,exact_model=True):
    if point is not None and point.get('threshold_certificate_PASS',False):return 'B3_NEGATIVE_CERTIFIED'
    if status==3 and exact_model:return 'B3_POSITIVE_CERTIFIED'
    return 'B3_INCONCLUSIVE'
def threshold_guard(rho,recomputed,matrix,integer,physics,grid):
    return bool(all(np.isfinite(v) for v in [rho,recomputed,matrix,integer]) and
        matrix<=MATRIX_TOL and integer<=INTEGER_TOL and physics and grid and
        recomputed-rho<=RHO_TOL and max(rho,recomputed)<=T-THRESHOLD_MARGIN)
def original_UB_eligible(partial_validation,all_binary_fractionality):
    return bool(partial_validation.get('B3_feasible_PASS') and all_binary_fractionality<=INTEGER_TOL)

def resource_snapshot():
    import psutil
    procs=[]
    for p in psutil.process_iter(['pid','name','memory_info']):
        try:
            if p.pid!=psutil.Process().pid and any(s in p.name().lower() for s in ['python','gurobi']):
                p.cpu_percent(None);procs.append(p)
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    time.sleep(1)
    rows=[]
    for p in procs:
        try:
            cpu=p.cpu_percent(None);rss=p.memory_info().rss
            rows.append(dict(pid=p.pid,name=p.name(),CPU_percent=cpu,RSS_bytes=rss,heavy=cpu>10 and rss>200*1024**2))
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    return dict(created_UTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),other_solver_processes=rows,
        other_heavy_solve=any(r['heavy'] for r in rows),physical_CPUs=psutil.cpu_count(logical=False),
        logical_CPUs=psutil.cpu_count(),available_memory_bytes=psutil.virtual_memory().available,
        observation_seconds=1,process_command_lines_not_collected=True)

def threshold_model(env):
    import gurobipy as gp
    m=gp.read(str(LOCAL/'F3.mps'),env=env)
    m.setAttr('VType',['B' if x else 'C' for x in domains()]);m.update()
    m.setObjective(gp.LinExpr(0.),gp.GRB.MINIMIZE)
    m.addConstr(m.getVarByName('rho_max')<=T,name='B3_THRESHOLD_RHO');m.update()
    assert (m.NumVars,m.NumConstrs,m.NumNZs,m.NumBinVars)==(316743,954561,8282351,85744)
    return m

def matrix_validation(m,values,include_threshold=True):
    values=np.asarray(values);A=m.getA();rhs=np.asarray(m.getAttr('RHS'));sense=np.asarray(m.getAttr('Sense'))
    if not include_threshold:A=A[:-1];rhs=rhs[:-1];sense=sense[:-1]
    residual=A@values-rhs;viol=np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual))
    maximum=max(0.,float(viol.max()),float((np.asarray(m.getAttr('LB'))-values).max()),float((values-np.asarray(m.getAttr('UB'))).max()))
    return dict(PASS=bool(np.isfinite(values).all() and maximum<=MATRIX_TOL),max_residual=maximum,
        equality_max_residual=float(abs(residual[sense=='=']).max()),rows=A.shape[0],threshold_row_included=include_threshold)
