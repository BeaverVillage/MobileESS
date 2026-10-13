"""All historical pool route metadata and uncached legacy heuristic scores."""
import copy,csv
from fractions import Fraction as F
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_compact_joint.scoring import AdaptiveMinimax
from tools.global_local_multistart1800.dag import Graph

def main():
    configure();state=read(DOCS/'FINAL_STATE.json');case=v.load_case(native=False);graph=Graph(case);records=[];pool_records=[]
    for call in state['calls']:
        if call in state['new_calls']:continue
        spec=read(call['model']['path']);point=v.load_point(spec['center_raw']['path']);q=read(call['receipt']['path']);chosen=q['captures'][-1]['lambda_values']
        epoch=call.get('epoch');context_path=PREVIOUS_DOCS/f'OPTIMIZATION_FEEDBACK_{epoch:02d}.json' if epoch is not None else Path('NO_STORED_CONTEXT')
        if not context_path.exists():context_path=previous.PILOT_DOCS/'OPTIMIZATION_FEEDBACK_01.json'
        scorer=None
        if context_path.exists():
            context=copy.deepcopy(read(context_path)['original_grid_context']);original=case.lift(point);values=dict(zip(map(str,case.original_d['names']),map(float,original)))
            for row in context['rows']:
                coefficients={name:float(F(co)) for name,co in row['coeff'].items()};scale=-coefficients['rho_max']
                row['current_loading']=(sum(co*values[name] for name,co in coefficients.items() if name!='rho_max')-float(F(row['rhs'])))/scale
            context['center_vector_sha']=v.vector_sha(point);scorer=AdaptiveMinimax(case,point,context)
        base=paths_of(case,point);poolbest=INITIAL_UB
        for axis,entry in enumerate(spec['lambda_axis']):
            u=entry['unit'];path=entry['path'];meta=graph.metadata({u:path});score=None;risk=None;impacts=None
            if scorer:
                score,vector,rebound=scorer.peak(dict(base,**{u:path}));risk=float(np.sum(np.maximum(0.,rebound)));impacts=(np.asarray(vector)-scorer.loading).tolist()
            records.append(dict(epoch=epoch,formulation=call.get('formulation','DIRECT'),pool_signature=spec['pool_signature'],unit=u,ordinal=entry['ordinal'],
                path_signature=entry['path_signature'],MOVE_count=len(graph.move_indices(path)),travel_energy_kWh=meta['travel_energy_kWh'],moves=meta['actual_moves'],
                Minimax_score=score,Rebound_sum_heuristic=risk,signed_critical_impacts=impacts,selected_lambda=chosen[axis],joint_pool_FULL_UB=q['ObjVal'],
                individual_route_UB_not_assigned=True,score_recomputed_Native0=True,
                original_context_selection_available=epoch is not None and context_path==PREVIOUS_DOCS/f'OPTIMIZATION_FEEDBACK_{epoch:02d}.json' if epoch is not None else False,
                fallback_context_is_retrospective_diagnostic=True))
        pool_records.append(dict(spec=call['model'],FULL_UB=q['ObjVal'],actual_selected_lambda=chosen,original_context_or_retrospective_context=str(context_path)))
    write(DOCS/'LEGACY_ALL_POOL_CANDIDATE_DIAGNOSTICS.json',dict(PASS=True,Optimize_calls=0,records=records,pools=pool_records,
        original_missing_scores_not_claimed_as_logged_measurements=True,retrospective_scores_not_independent_route_performance=True,
        original_models_and_Raw_not_modified=True))
    print(json.dumps(dict(PASS=True,candidates=len(records),models=len(pool_records))),flush=True)
if __name__=='__main__':main()
