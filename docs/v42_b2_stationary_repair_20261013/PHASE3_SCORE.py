"""Read-only score counterexample using the saved case; no Optimize."""
import runpy,sys
sys.argv=['PHASE1_2_REPLAY_TRACE.py','2025-05-01']
ns=runpy.run_path('D:/v42_b2_stationary_diagnosis_20261013/PHASE1_2_REPLAY_TRACE.py')
globals().update({k:ns[k] for k in ('case','point','wp','paths','folder','ROOT','read','atomic')})
from tools.minimax_beam1800 import grid
from tools.adaptive_perf_v3.scoring import LookaheadMinimax
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.joint import path_signature
grid.DOCS=ROOT/'binding_regression/2025-05-01'
context=read(folder/'PR221/OPTIMIZATION_FEEDBACK_00.json')['original_grid_context']
scorer=LookaheadMinimax(case,point,context)
base=scorer.baseline_paths
trial=dict(base,MESS03=paths['MESS03'])
baseline=scorer.peak(base)[0];predicted=scorer.peak(trial)[0]
reservoir=read(folder/'PR221/BEAM_RESERVOIR.json')['units']['MESS03']
ranked=[]
for sig,p in reservoir.items():
    ranked.append((scorer.peak(dict(base,MESS03=p))[0],sig))
ranked.append((predicted,path_signature(paths['MESS03'])))
ranked.sort()
rank=next(i+1 for i,r in enumerate(ranked) if r[1]==path_signature(paths['MESS03']))
key=('MESS03',tuple(paths['MESS03']))
q=dict(PASS=True,Native_optimize_calls=0,baseline_score=baseline,
    known_moving_heuristic_score=predicted,known_moving_current_FULL_UB=.5398310226338695,
    predicted_minus_actual=predicted-.5398310226338695,rank_when_inserted=rank,
    ranked_count=len(ranked),score_prefers_STAY=predicted>baseline,
    baseline_same_optimized_PQ=True,unchanged_vehicles_PQ_fixed_in_score=True,
    full_joint_reoptimization_in_score=False,
    lookahead=scorer.lookahead_diagnostics[key],
    original_moves=Graph(case).metadata(paths))
atomic(ROOT/'PHASE3_SCORING_COUNTEREXAMPLE.json',q)
print({k:q[k] for k in ('baseline_score','known_moving_heuristic_score','predicted_minus_actual','rank_when_inserted','ranked_count','score_prefers_STAY')})
