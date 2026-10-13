"""All96-slot scoring and measured admission diagnostics, no individual UB attribution."""
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.scoring import LookaheadMinimax
from tools.adaptive_perf_v3 import grid as newgrid
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.joint import path_signature

def generate(case,point,replay,epoch,seen,timer):
    from tools.adaptive_compact_joint import resume_feedback as body,beam
    from tools.minimax_beam1800 import grid, routes
    configure();body.DOCS=DOCS;body.configure=configure;body.AdaptiveMinimax=LookaheadMinimax
    context_box=[];beam_wall=0.;grid_wall=0.;feedback_wall=0.
    oldrefresh=grid.refresh;oldbeam=routes.generate;oldfeedback=beam.feedback
    def refresh(*args):
        nonlocal grid_wall
        started=time.perf_counter();context,path=newgrid.refresh(*args);context_box.append(context);grid_wall+=time.perf_counter()-started;return context,path
    def labels(*args):
        nonlocal beam_wall
        started=time.perf_counter();answer=oldbeam(*args);beam_wall+=time.perf_counter()-started;return answer
    def incumbent(*args):
        nonlocal feedback_wall
        started=time.perf_counter();answer=oldfeedback(*args);feedback_wall+=time.perf_counter()-started;return answer
    grid.refresh=refresh;routes.generate=labels;beam.feedback=incumbent;body.feedback=incumbent
    started=time.perf_counter()
    try:pools,signature=body.generate(case,point,replay,epoch,seen)
    finally:grid.refresh=oldrefresh;routes.generate=oldbeam;beam.feedback=oldfeedback;body.feedback=oldfeedback
    total=time.perf_counter()-started
    timer.parts['Grid_SOC_rebound_context']=grid_wall;timer.parts['incumbent_feedback']=feedback_wall
    timer.parts['Beam_label_generation']=beam_wall;timer.parts['Score_admission_and_candidate_IO']=total-grid_wall-feedback_wall-beam_wall
    if pools is None:return None,None
    with timer.stage('candidate_diagnostics_score_and_SOC'):
        scorer=LookaheadMinimax(case,point,context_box[-1]);graph=Graph(case);base=paths_of(case,point);records=[]
        baseline=scorer.peak(base)[0];actual=read(replay)['Global_UB'];assert abs(baseline-actual)<1e-10
        for u,paths in pools.items():
            for ordinal,path in enumerate(paths):
                trial=dict(base);trial[u]=path;peak,vector,rebound=scorer.peak(trial);meta=graph.metadata({u:path})
                record_row=dict(unit=u,ordinal=ordinal,path_signature=path_signature(path),MOVE_count=len(graph.move_indices(path)),
                    original_moves=meta['actual_moves'],travel_energy_kWh=meta['travel_energy_kWh'],Minimax_heuristic_score=peak,
                    single_changed_route_reference_context_only=True,individual_route_FULL_UB_not_assigned=True,
                    signed_critical_impact=(np.asarray(vector)-scorer.loading).tolist(),charge_rebound_risk=rebound,
                    lookahead=scorer.lookahead_diagnostics.get((u,tuple(path)),{}))
                records.append(record_row)
        proposed=dict(base)
        for turn in range(2):
            for u in sorted(pools):
                proposed[u]=min(pools[u],key=lambda p:scorer.peak(dict(proposed,**{u:p}))[0])
        expected=scorer.peak(proposed)[0]
        write(DOCS/f'CANDIDATE_DIAGNOSTICS_{epoch:03d}.json',dict(PASS=True,Optimize_calls=0,pool_signature=signature,
            actual_reference_UB=actual,baseline_score=baseline,pool_predicted_score=expected,pool_predicted_paths=proposed,
            critical_rows=context_box[-1]['rows'],all96_slot_coverage=len(set(r['slot'] for r in context_box[-1]['rows']))==96,
            candidates=records,no_SCORE_used_as_certified_UB_or_LB=True,individual_route_joint_UB_attribution=False))
    return pools,signature
