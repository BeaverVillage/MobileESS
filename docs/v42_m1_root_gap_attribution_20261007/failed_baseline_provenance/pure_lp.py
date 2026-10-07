"""One authorized pure C3A LP; no MIP search or production modification."""
import os
os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
import csv,hashlib,json,math,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=Path(__file__).resolve().parent;PARENT=ROOT/'docs/v42_m1_ultracompact_exact_20261006'
BASE='1d922c91eb27056a5ccc79c92ef18146707099ab'
EXPECTED={'C3A_A.npz':'45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8','C3A_DATA.npz':'20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467','C3A_VALID_START.npz':'be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5'}
import numpy as np
from scipy import sparse

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(n,x):
    def fix(v):
        if isinstance(v,dict):return {str(k):fix(x) for k,x in v.items()}
        if isinstance(v,(tuple,list)):return [fix(x) for x in v]
        if isinstance(v,np.generic):return fix(v.item())
        if isinstance(v,float) and not math.isfinite(v):return None
        return v
    (OUT/n).write_bytes((json.dumps(fix(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))
def load():
    for name,h in EXPECTED.items():assert sha(PARENT/name)==h,name
    A=sparse.load_npz(PARENT/'C3A_A.npz')
    with np.load(PARENT/'C3A_DATA.npz') as z:d={k:z[k] for k in z.files}
    with np.load(PARENT/'C3A_VALID_START.npz') as z:start=z['point'].copy()
    assert (A.shape[0],A.shape[1],int((d['types']=='B').sum()),A.nnz)==(582808,306040,9322,5351612)
    return A,d,start
def replay(A,d,x):
    r=np.asarray(A@x-d['rhs']);v=np.where(d['sense']=='=',abs(r),np.where(d['sense']=='<',r,-r))
    maximum=float(v.max(initial=0));bound=float(max((d['lower']-x).max(initial=0),(x-d['upper']).max(initial=0)))
    return dict(PASS=bool(np.isfinite(x).all() and maximum<=1e-8 and bound<=1e-8),max_row_violation=maximum,max_bound_violation=bound,objective=float(d['objective']@x+float(d['constant'])))
def rows(n,items):
    keys=list(dict.fromkeys(k for item in items for k in item))
    with (OUT/n).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(items)
def main():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    assert not (OUT/'PURE_LP_ONCE.json').exists(),'PURE_LP_RETRY_FORBIDDEN'
    A,d,start=load();authority=json.loads((PARENT/'ULTRACOMPACT_CURRENT_AUTHORITY_M1.json').read_text())
    assert authority['selected']=='C3A' and authority['N']==4 and authority['H']==96
    parent_hashes={str(p.relative_to(ROOT)):sha(p) for p in PARENT.iterdir() if p.is_file()}
    write('BASE_AUTHORITY.json',dict(PASS=True,exact_base=BASE,selected_authority=authority,selected_hashes=EXPECTED,parent_namespace_hashes=parent_hashes,aborted_run_is_not_completed_benchmark=True))
    import gurobipy as gp
    from v42_redundancy.model import build
    from v42_rowgen.native import transport_audit
    original=build(A,d);original.update();lp=original.copy();variables=lp.getVars()
    lp.setAttr('VType',variables,['C']*len(variables));lp.update()
    settings=dict(Method=2,Threads=1,Crossover=0,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,TimeLimit=gp.GRB.INFINITY)
    for k,v in settings.items():lp.setParam(k,v)
    lp.Params.OutputFlag=1;lp.Params.LogToConsole=0;lp.Params.LogFile=str(OUT/'PURE_LP.log')
    relaxed=dict(d,types=np.full(A.shape[1],'C'));transport=transport_audit(lp,A,relaxed,np.arange(A.shape[0]))
    assert original.NumBinVars==9322 and lp.NumBinVars==0 and lp.NumIntVars==0 and lp.ModelSense==gp.GRB.MINIMIZE
    write('C3A_IDENTITY_AUDIT.json',dict(PASS=True,base=BASE,selected_hashes=EXPECTED,rows=A.shape[0],columns=A.shape[1],binaries=9322,continuous=296718,nnz=A.nnz,independent_native_copy=True,pure_LP_transport=transport,all_integer_variables_relaxed_same_bounds=True,physical_formulation_changed=False,solver_settings=settings))
    with (OUT/'PURE_LP_ONCE.json').open('x',encoding='utf-8') as f:json.dump(dict(stage='PURE_LP',optimize_calls=1),f)
    t=time.perf_counter();print('PURE_C3A_LP_START',flush=True);lp.optimize();wall=time.perf_counter()-t
    assert lp.Status==gp.GRB.OPTIMAL,lp.Status
    x=np.asarray(lp.getAttr('X'));pi=np.asarray(lp.getAttr('Pi'));rc=np.asarray(lp.getAttr('RC'));slack=np.asarray(lp.getAttr('Slack'))
    check=replay(A,d,x);assert check['PASS'],check
    active=np.abs(slack)<=1e-8
    np.savez_compressed(OUT/'PURE_LP_POINT.npz',x=x,dual=pi,reduced_cost=rc,slack=slack,active=active,original_types=d['types'])
    families={}
    for i,n in enumerate(d['row_names']):
        if active[i]:families[str(n).split('[')[0]]=families.get(str(n).split('[')[0],0)+1
    report=dict(PASS=True,objective=float(lp.ObjVal),native_global_LP_LB=float(lp.ObjBound),Runtime=float(lp.Runtime),Work=float(lp.Work),wall_seconds=wall,
        Status=int(lp.Status),LP_iterations=float(lp.IterCount),barrier_iterations=int(lp.BarIterCount),settings=settings,optimize_calls=1,
        all_values_duals_RC_slacks_saved=True,active_row_count=int(active.sum()),active_rows_by_family=families,independent_relaxed_matrix_replay=check,
        no_native_MILP_gap_reported=True,reference_incumbent=0.6694159238756877,gap_ref=(0.6694159238756877-float(lp.ObjVal))/0.6694159238756877,
        root_gap_is_LP_to_known_incumbent_gap_not_proven_integrality_gap=True,integer_optimum_unknown=True)
    write('PURE_LP_RESULT.json',report);lp.dispose();original.dispose();print('PURE_C3A_LP_DONE',report['objective'],report['Runtime'],flush=True)

if __name__=='__main__':main()
