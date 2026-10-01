"""User-revised goal: accelerate global-bound proof, not force root exit."""
BASE_LB=.5718494710510547
def degen_diagnostic_allowed(r):
    p=r['passes'][0];t=p['telemetry'];completion=t['events'].get('root_relaxation_completion_seconds')
    if p['quality_PASS'] or completion is None:return False
    first=t.get('first_non_root_node_seconds')
    delay=(first if first is not None else p['solve_wall_seconds'])-completion
    return delay>=120
def proof_gate(r):
    p=r['passes'][0]
    gain=p['bound']-BASE_LB if p['bound'] is not None else None
    return dict(PASS=p['quality_PASS'] or (gain is not None and gain>=1e-4),solver_certified_P1_quality=p['quality_PASS'],global_bound_gain=gain,bound_gain_threshold=1e-4,first_branch_not_authorization_basis=True,primal_heuristic_improvement_not_authorization_basis=True)
def rank(r):
    p=r['passes'][0]
    return (not p['quality_PASS'],-p['bound'] if p['bound'] is not None else float('inf'),p['relative_gap'] if p['relative_gap'] is not None else float('inf'),p['work'],p['solve_wall_seconds'])
def select(results):
    ordered=sorted(results,key=rank);chosen=ordered[0]
    return dict(selected=chosen['label'],DegenMoves=chosen['settings']['DegenMoves'],CutPasses=-1,Heuristics=0,MIPFocus=3,production_authorized=proof_gate(chosen)['PASS'],gates={r['label']:proof_gate(r) for r in results},ranking=[r['label'] for r in ordered],ranking_rule='solver-certified P1 quality, higher final BestBd, lower Gap, work/wall; first branch and node count are descriptive',frozen=True,interpretation='ROOT_LOOP_POLICY_EFFECT',pure_cut_ablation=False)
