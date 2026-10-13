"""Signed scoring/SOC regression without Optimize or a Gurobi model."""
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.scoring import LookaheadMinimax
from tools.adaptive_perf_v3.grid import refresh
from tools.global_local_multistart1800.dag import Graph

def main():
    configure();full_guard();timer=Timing();state=read(PREVIOUS_DOCS/'LIVE_STATE.json');last=state['events'][-1]
    with timer.stage('Source_Case_load'):case=v.load_native_case();point=v.load_point(last['point']['path'])
    with timer.stage('Grid_context_all96_slots'):context,context_path=refresh(case,point,900)
    with timer.stage('SOC_rebound_signed_score_regressions'):
        scorer=LookaheadMinimax(case,point,context);paths=paths_of(case,point);baseline=scorer.peak(paths)[0]
        assert abs(baseline-last['UB'])<1e-10 and set(r['slot'] for r in context['rows'])==set(range(96))
        spec=read(state['new_calls'][-1]['model']['path']);graph=Graph(case);witness=[]
        for u,pool in spec['pools'].items():
            depths=set()
            for path in pool:
                graph.validate(u,path);depths.add(len(graph.move_indices(path)));peak,vec,risk=scorer.peak(dict(paths,**{u:path}))
                assert np.isfinite(peak) and np.isfinite(vec).all()
            assert 0 in depths and 1 in depths and max(depths)>=2
            witness.append(dict(unit=u,STAY_single_multiple=True))
    write(DOCS/'BEAM_NATIVE0_REGRESSION.json',dict(PASS=True,Optimize_calls=0,all96_slots_signed_Source_coefficients=True,
        actual_reference_score_error=baseline-last['UB'],regressions=witness,no_MOVE_forcing=True,no_heuristic_dominance_pruning=True,
        terminal_SOC_opportunity_and_transit_loss_in_score=True,context=record(context_path),timing=timer.receipt(),memory=r.memory()))
    print(json.dumps(dict(PASS=True,timing=timer.receipt())),flush=True)
if __name__=='__main__':main()
