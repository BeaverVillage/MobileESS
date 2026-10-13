"""Existing May01 matrix + winner + diverse Joint Pool, no Optimize/Presolve."""
import runpy,sys,time
sys.argv=['PHASE1_2_REPLAY_TRACE.py','2025-05-01']
ns=runpy.run_path('D:/v42_b2_stationary_diagnosis_20261013/PHASE1_2_REPLAY_TRACE.py')
globals().update({k:ns[k] for k in ('case','point','wp','paths','folder','ROOT','read','atomic','verified','warm','np')})
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import v42_m1_hybrid.final_verify as fv
from v42_may_final.incumbent import binding,admit,Bank
from v42_may_final.dispatch_score import DispatchScore,refine
from v42_may_final.pr221 import rebound,current_axes
from v42_pr134_b1.common import record
from tools.minimax_beam1800 import grid
from tools.adaptive_perf_v3 import cache,bootstrap
from tools.adaptive_compact_joint import direct,beam
from tools.global_local_multistart1800 import joint
from tools.u4_primal_alns import verify as v
import psutil,gurobipy as gp
begin=time.perf_counter();out=ROOT/'repair_native0';out.mkdir(exist_ok=False)
case.bundle=read(Path('D:/v42_may_joint_repair_campaign_20261013/inputs/B2/2025-05-01/NATIVE_INPUT.json'))
entry=dict(origin='PR220_CURRENT_FULL_REPLAY',binding=binding(case,'B2'),raw=record(warm))
atomic(ROOT/'VALIDATED_CASE_INCUMBENTS.json',[entry])
with patch.object(fv,'ROOT',ROOT):accepted=admit(case,[entry],out,fv._strict_ub,'B2')
assert len(accepted)==1
bank=Bank(case);bank.offer(*accepted[0]);bank.offer(point,read(folder/'PR221/INITIAL_POINT.REPLAY.json'))
assert bank.fields()==dict(BEST_GLOBAL_UB=.5398310226338695,BEST_MOVING_FEASIBLE_UB=.5398310226338695)
wrong=dict(entry,binding=dict(entry['binding'],day='2025-05-02'))
with patch.object(fv,'ROOT',ROOT):assert admit(case,[wrong],out/'negative',fv._strict_ub,'B2')==[]
grid.DOCS=ROOT/'binding_regression/2025-05-01'
context=read(folder/'PR221/OPTIMIZATION_FEEDBACK_00.json')['original_grid_context']
scorer=DispatchScore(case,point,context)
cold_score=scorer.score(scorer.base.baseline_paths);warm_score=scorer.score(paths)
atomic(out/'REDISPATCH_COUNTEREXAMPLE.json',dict(STAY=cold_score,PR220=warm_score,
    Native_optimize_calls=0,selected_rows=len(context['rows']),slots=len(set(r['slot'] for r in context['rows']))))
print('REDISPATCH',cold_score['score'],warm_score['score'],flush=True)
assert warm_score['score']<cold_score['score']
pools=read(folder/'PR221/ADAPTIVE_POOL_001.json')['pools']
for u in paths:
    if paths[u] not in pools[u]:pools[u][-1]=paths[u]
assert all(paths[u] in pools[u] for u in paths)
v.DOCS=out;cache.DOCS=out;v.CASE_SHA=case.case_sha
v.MATRIX_SHA=v.matrix_sha(case.A);v.DOMAIN_SHA=v.domain_sha(case.d)
v.FULL_MATRIX_SHA=v.matrix_sha(case.original_A);v.FULL_DOMAIN_SHA=v.domain_sha(case.original_d)
replay=ROOT/'PR220_CURRENT_MAY01_FULL_REPLAY.json'
axes=current_axes(case);timer=bootstrap.Timing();static=cache.get(case,timer)
spec_builder=rebound(joint.build_spec,axes={9322:axes['source_binary']})
transform=rebound(direct.transform,namespace=dict(build_spec=spec_builder,integer_proof=lambda *a,**k:direct.integer_proof(*a,**k)),
    axes={216674:axes['route_columns'],137603:axes['keep_columns'],8938:axes['route_binary'],207736:axes['route_continuous']})
with patch.object(direct,'transform',transform):
    spec,proof=cache.fast_save(case,wp,replay,pools,'REGRESSION',out/'model',static,timer)
from scipy import sparse
A=sparse.load_npz(out/'model/A.npz');T=sparse.load_npz(out/'model/LIFT.npz')
with np.load(out/'model/DATA.npz') as z:d={k:z[k].copy() for k in z.files}
with np.load(out/'model/START.npz') as z:start=z['point'].copy()
model=gp.Model('V42_STATIONARY_REPAIR_NATIVE0');model.Params.OutputFlag=0;model.Params.Threads=1
x=model.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'],obj=d['objective'])
x.VarName=d['names'].tolist();x.Start=start;model.ObjCon=float(d['constant'])
rows=model.addMConstr(A,x,d['sense'],d['rhs']);rows.ConstrName=d['row_names'].tolist();model.update()
checks=dict(CSR_exact=v.matrix_sha(model.getA().tocsr())==v.matrix_sha(A),
    RHS_exact=np.array_equal(model.getAttr('RHS'),d['rhs']),sense_exact=np.array_equal(model.getAttr('Sense'),d['sense']),
    Bounds_exact=np.array_equal(x.LB,d['lower']) and np.array_equal(x.UB,d['upper']),
    Types_exact=np.array_equal(x.VType,d['types']),Objective_exact=np.array_equal(x.Obj,d['objective']) and model.ObjCon==float(d['constant']),
    Raw_Start_unchanged=np.array_equal(T@x.Start,wp),Start_exact=np.array_equal(x.Start,start),
    all384_modes_free=sum(str(n).startswith('charge_mode[') for n in d['names'])==384,
    binary_count=model.NumBinVars==384+spec['lambda_count'],
    same_original_rhs=np.array_equal(d['rhs'][:-4],case.d['rhs']),
    four_one_hot=np.array_equal((A@start)[-4:],np.ones(4)),
    all_original_rows_retained=A.shape[0]==case.A.shape[0]+4,
    Original_FULL_contains_joint=proof['restricted_to_FULL_inclusion'])
assert all(checks.values()),checks
activity=A@start;sign=d['sense'];residual=np.where(sign=='<',activity-d['rhs'],np.where(sign=='>',d['rhs']-activity,abs(activity-d['rhs'])))
assert residual.max()<1e-8
certificate=dict(PASS=True,checks=checks,Native_optimize_calls=0,Native_Runtime=0,
    presolve_called=False,solver_Start_readback_accepted=True,solver_Start_processing_not_run=True,
    case_sha=case.case_sha,known_FULL_UB=verified['Global_UB'],**bank.fields(),
    pool_counts={u:len(p) for u,p in pools.items()},lambda_values=start[-spec['lambda_count']:].tolist(),
    lambda_axis=spec['lambda_axis'],maximum_Start_row_violation=float(residual.max()),
    NumVars=model.NumVars,NumConstrs=model.NumConstrs,NumBinVars=model.NumBinVars,NumNZs=model.NumNZs,
    process_RSS=psutil.Process().memory_info().rss,system_memory=psutil.virtual_memory()._asdict(),
    wall_seconds=time.perf_counter()-begin)
atomic(out/'NATIVE_READBACK_AND_INCUMBENT_REGRESSION.json',certificate)
model.dispose();print('NATIVE0_PASS',certificate['NumBinVars'],certificate['maximum_Start_row_violation'],flush=True)
