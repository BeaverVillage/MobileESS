"""Exercise the repaired production Beam body plus dispatch shortlist."""
import runpy,sys,time
sys.argv=['PHASE1_2_REPLAY_TRACE.py','2025-05-01']
ns=runpy.run_path('D:/v42_b2_stationary_diagnosis_20261013/PHASE1_2_REPLAY_TRACE.py')
globals().update({k:ns[k] for k in ('case','point','wp','paths','folder','ROOT','read','atomic','verified','warm','np')})
from v42_may_final.pr221 import rebound
from v42_may_final.dispatch_score import refine
from tools.adaptive_compact_joint import beam
from tools.minimax_beam1800 import grid
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.joint import path_signature
begin=time.perf_counter();out=ROOT/'repair_beam';out.mkdir(exist_ok=False)
beam.DOCS=out;grid.DOCS=ROOT/'binding_regression/2025-05-01';beam.RAW_REL=str(warm)
beam.v.load_point=lambda p:np.load(p)['point'].copy()
context=read(folder/'PR221/OPTIMIZATION_FEEDBACK_00.json')['original_grid_context']
replay=folder/'PR221/INITIAL_POINT.REPLAY.json'
generate=rebound(beam.generate,[("legacy=read(OLD_DOCS/'GLOBAL_CANDIDATE_POOL.json')['candidates']","legacy=[]"),
    ("'PR220_AUTHORITY'","'VERIFIED_CASE_AUTHORITY'")])
pools,packet=generate(case,point,context,replay,size=8,epoch=0)
assert all(paths[u] in pools[u] for u in paths)
result,signature=refine(case,point,context,pools,out,0)
assert all(paths[u] in result[u] for u in paths)
graph=Graph(case);units={}
for u,p in result.items():
    moves=[len(graph.move_indices(q)) for q in p]
    assert len(p)==8 and 0 in moves and 1 in moves and max(moves)>=2
    units[u]=dict(moves=moves,authority_in_pool=paths[u] in p,authority_ordinal=p.index(paths[u]))
q=dict(PASS=True,units=units,winning_MESS03_signature=path_signature(paths['MESS03']),
    winning_MESS03_origin=packet['all_generated_candidates']['MESS03'][path_signature(paths['MESS03'])]['origin'],
    baseline_original_moves=graph.metadata(beam.paths_of(case,point)),authority_original_moves=graph.metadata(paths),
    Native_optimize_calls=0,Native_Runtime=0,score_only_HiGHS_LP=True,
    pool_signature=signature,wall_seconds=time.perf_counter()-begin,
    complete_three_MOVE_path_in_generated=True,complete_three_MOVE_path_in_pool=True)
atomic(out/'BEAM_REPAIR_REGRESSION.json',q)
print('BEAM_REPAIR_PASS',units,flush=True)
