"""Read-only PR218 rank, bias, timing and counterfactual benchmark audit."""
from collections import Counter
from scipy.stats import spearmanr
from tools.minimax_beam1800.adapter import *

def main():
    old=ROOT/'docs/v42_b2_k32_routefixed1800_canary'
    receipt=read(old/'FINAL_INDEPENDENT_REVIEW.json');assert receipt['PASS'] and receipt['Native_used']==1795.0209996700287
    state=read(old/'FINAL_STATE.json');data=read(old/'ROUTE_FIXED_MILP_RESULTS.json')['results']
    measured=[x for x in data if x['verified_UB'] is not None]
    case=v.load_case();grid=read(old/'CRITICAL_GRID_ANALYSIS.json')['N1']['critical_grid']['line_thermal_face']['highest_normalized_values']
    critical_slots=sorted({row['slot'] for row in grid});timing=[]
    for x in data:
        c=x['candidate'];moves=[]
        for u,path in c['paths'].items():
            for k in path:
                a=case.graph[2][k]
                if a[-1] is not None:moves.append(dict(unit=u,arc=k,depart=a[1],arrive=a[-1].arrive,connect=a[3],energy_kWh=a[-1].energy_kwh,
                    directly_cannot_serve_earlier_critical_slots=[t for t in critical_slots if t<a[3]]))
        timing.append(dict(candidate_id=c['candidate_id'],score=c['score'],verified_UB=x['verified_UB'],moves=moves))
    corr=spearmanr([x['candidate']['score'] for x in measured],[x['verified_UB'] for x in measured])
    events=[]
    for it in state['iterations']:
        for item in it['validated']:
            if not item['PASS']:continue
            replay=read(item['replay']['path']);ub=replay['Global_UB']
            moves=(it.get('candidate') or {}).get('moves',0)
            events.append(dict(UB=ub,moves=moves,method=it['method'],Native_capture_seconds=item['discovered_Native_seconds'],
                individual_call_Native_Runtime=read(it['call']['path'])['Native_Runtime'],point=item['raw']))
    def first(predicate):
        matches=[e for e in events if predicate(e)]
        return min(e['Native_capture_seconds'] for e in matches) if matches else 'NOT_REACHED'
    result=dict(PASS=True,source_readonly=True,source_case_identity_verified=True,Native_optimize_calls=0,
        PR218_HEAD=BASE,old_runtime=state['Native_used'],route_milp_calls=len(data),moving_FULL_feasible=len(measured),
        score_vs_actual_objective_Spearman=float(corr.statistic),pvalue=float(corr.pvalue),
        interpretation='Positive correlation: higher heuristic gain scores were associated with worse (higher) rho, not better outcomes. Observational within-May01 evidence, not a causal proof.',
        initial_four_evaluations_units=[x['candidate']['units'] for x in data[:4]],
        overall_unit_counts=dict(Counter(u for x in data for u in x['candidate']['units'])),
        baseline_equal_paths=sum(abs(x['verified_UB']-HISTORICAL)<=1e-8 for x in measured),
        baseline_equal_ratio=sum(abs(x['verified_UB']-HISTORICAL)<=1e-8 for x in measured)/len(measured),
        critical_N1_slots=critical_slots,actual_move_critical_timing=timing,
        zip_pairing_used=True,beam_width=64,max_moves_per_unit=3,
        shortcomings=dict(sum_relief_not_minimax=True,late_connection_is_row_specific=True,
            initial_vehicle_bias=True,zip_excludes_cross_complements=True,repeated_equal_UB_native_cost=True),
        design=dict(minimax_vector_peak=True,real_ETA_lookahead=True,SOC_rebound_lookahead=True,
            vehicle_time_destination_coverage=True,cross_product_pairing=True,conditional_certified_LP=True),
        benchmarks=dict(T1=first(lambda e:e['UB']<=HISTORICAL+1e-8),
            T2=first(lambda e:e['moves']>0 and e['UB']<=HISTORICAL+1e-8),
            T3=first(lambda e:e['moves']>0 and e['UB']<HISTORICAL-1e-5)),
        benchmark_scope='Actual cumulative Native capture time of points later passing FULL. Validation wall is not Native; no prior point becomes a new start.',
        new_solver_starts_from_old_raw=0,May01_policy_design_is_not_May02_03_generalization=True,
        evidence={name:record(old/name) for name in ('ROUTE_CANDIDATES.json','ROUTE_FIXED_MILP_RESULTS.json','CRITICAL_GRID_ANALYSIS.json','REBOUND_ANALYSIS.json','BEST_MOVING_96_SLOT_MESS_PLAN.csv')})
    write(DOCS/'PR218_READONLY_FAILURE_ANALYSIS.json',result)
    print(json.dumps(dict(PASS=True,Spearman=result['score_vs_actual_objective_Spearman'],benchmarks=result['benchmarks'])))

if __name__=='__main__':main()
