"""Profile one unchanged B2 route problem before opening the full search."""
from bootstrap import *
import hashlib
import traceback
from types import SimpleNamespace


def profile():
    from dayahead.v35.execution import MESS_INITIAL
    from dayahead.v35r3 import algorithm as r3
    from dayahead.v35r3e import algorithm as r3e
    from dayahead.v35r3e.algorithm import build_planning_screen_context, screen_dynamic_candidates
    from dayahead.v39e.runtime import four_thread_fixed_candidate
    import gurobipy as gp
    import mess_runtime
    import mess_grid8500
    from electrical_engine import Engine

    assert read(H/'COEFFICIENT_GENERATION_FINAL.json')['status']=='PASS'
    assert read(H/'Actual/B0_GATE.json')['status']=='PASS'
    assert read(H/'FINAL_CANDIDATE_FREEZE.json')['MESS_SCALE']==2.
    seed=read(H/'COMPACT_B0_ACTIVE_SEED.json')
    with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:aidc=z['pcc'].copy()
    t0=time.perf_counter();cc=mess_runtime.coefficients();coefficient_seconds=time.perf_counter()-t0
    assert len(cc)==96 and len(cc[0].control_names)==60
    coeff_hashes=[c.coefficient_sha256 for c in cc]

    # Same anchored polygon arithmetic, with and without shared immutable cache.
    critical=cc[seed['critical_slot']]
    t0=time.perf_counter();plain=mess_grid8500.anchored_polygon_parameters(critical);uncached=time.perf_counter()-t0
    t0=time.perf_counter();cached_first=mess_grid8500.polygon_parameters(critical);first=time.perf_counter()-t0
    t0=time.perf_counter();cached_second=mess_grid8500.polygon_parameters(critical);hit=time.perf_counter()-t0
    equal=all(np.array_equal(a,b) for a,b in zip(plain[:2],cached_first[:2])) and all(
        np.array_equal(a,b) for a,b in zip(plain[:2],cached_second[:2]))
    assert equal and hit < uncached, (uncached,hit)

    t0=time.perf_counter();traffic=mess_runtime.traffic();traffic_seconds=time.perf_counter()-t0
    save(H/'B2_preflight/PROGRESS.json',dict(stage='TRAFFIC_READY',coefficient_seconds=coefficient_seconds,
        traffic_seconds=traffic_seconds,polygon_uncached_seconds=uncached,polygon_hit_seconds=hit))
    route_table=traffic[2]
    services=tuple(name[10:-1] for name in map(str,NAMES) if name.startswith('mess_p_kw['))
    assert len(services)==24
    t0=time.perf_counter();context=build_planning_screen_context(
        aidc_pcc_kw_96x12=aidc,coefficients=cc,services=services,
        fixed_mess_p_by_service={},fixed_mess_q_by_service={},sequential_previous_mess_count=0)
    context_seconds=time.perf_counter()-t0
    candidate_id='MESS01'
    r3.assert_apr01_only=lambda day: (_ for _ in ()).throw(AssertionError(day)) if day!='2025-05-01' else None
    r3e.assert_apr01_only=lambda day: (_ for _ in ()).throw(AssertionError(day)) if day!='2025-05-01' else None
    enum=r3.enumerate_initial_relocations(day='2025-05-01',mess_id=candidate_id,
        initial_service=MESS_INITIAL[candidate_id],route_table=route_table)
    stay=next(x for x in enum.candidates if x.is_stay)
    t0=time.perf_counter();screen,screen_seconds=screen_dynamic_candidates(
        day='2025-05-01',case='B2',mess_id=candidate_id,route_table=route_table,
        context=context,variant='S4');route_seconds=time.perf_counter()-t0
    line_seed={tuple(x) for x in seed['line_states']}
    save(H/'B2_preflight/PROGRESS.json',dict(stage='ROUTE_SCREEN_READY',route_seconds=route_seconds,
        route_count=len(enum.candidates),polygon_uncached_seconds=uncached,polygon_hit_seconds=hit))
    t0=time.perf_counter();item=four_thread_fixed_candidate(
        candidate=stay,aidc_pcc_kw_96x12=aidc,coefficients=cc,services=services,
        fixed_mess_p_by_service={},fixed_mess_q_by_service={},line_states=line_seed,
        voltage_states=(),transformer_current_states=(),transformer_kva_states=())
    model_build_seconds=time.perf_counter()-t0
    assert item.model.Params.Threads==4
    optimize_original=gp.Model.optimize
    evaluate_original=r3.evaluate_opportunity_dispatch
    counters=dict(optimize_calls=0,solver_seconds=0.,evaluation_calls=0,evaluation_seconds=0.)
    def timed_optimize(model,*args,**kwargs):
        start=time.perf_counter();result=optimize_original(model,*args,**kwargs)
        counters['optimize_calls']+=1;counters['solver_seconds']+=time.perf_counter()-start
        return result
    def timed_evaluate(*args,**kwargs):
        start=time.perf_counter();result=evaluate_original(*args,**kwargs)
        counters['evaluation_calls']+=1;counters['evaluation_seconds']+=time.perf_counter()-start
        return result
    gp.Model.optimize=timed_optimize;r3.evaluate_opportunity_dispatch=timed_evaluate
    try:
        start=time.perf_counter();dispatch,evaluation=r3.solve_fixed_candidate_certified(item)
        restricted_seconds=time.perf_counter()-start
    finally:
        gp.Model.optimize=optimize_original;r3.evaluate_opportunity_dispatch=evaluate_original
        active=dict(line=len(item.added_line_states),voltage=len(item.added_voltage_states),
                    transformer_current=len(item.added_transformer_current_states),
                    transformer_kva=len(item.added_transformer_kva_states))
        item.model.dispose()
    assert evaluation['exact_optimality_certificate']
    save(H/'B2_preflight/STAY_RESTRICTED_DISPATCH.json',dict(candidate_id=stay.candidate_id,
        route_type='STAY',planning_rho=dispatch['rho'],p_kw=dispatch['p_kw'],
        q_kvar=dispatch['q_kvar'],certificate=evaluation['exact_optimality_certificate'],
        active_states=active,model_build_seconds=model_build_seconds,
        restricted_solve_seconds=restricted_seconds,solver_seconds=counters['solver_seconds']))
    separation_seconds=max(0.,restricted_seconds-counters['solver_seconds']-counters['evaluation_seconds'])

    # Exact AC observation for this single unchanged STAY route; diagnostic only.
    engine=Engine(H/'B2_preflight/stay_exact/runtime');rows=[]
    start=time.perf_counter()
    try:
        for slot in range(96):
            x=np.r_[aidc[slot],np.zeros(48)]
            service=r3._candidate_service(stay,slot)
            if service is not None:
                index=services.index(service)
                x[12+index]=dispatch['p_kw'][slot]
                x[36+index]=dispatch['q_kvar'][slot]
            engine.inputs(slot,x);engine.solve();v2,line,tx,winding=engine.arrays()
            rows.append(dict(slot=slot,rho=float(np.abs(line).max()),
                Vmin=float(np.sqrt(v2).min()),Vmax=float(np.sqrt(v2).max()),
                tx_current=float(np.abs(tx).max()),
                tx_kva=float((np.abs(winding)/np.asarray(AX['winding_rating_kVA'])).max()),
                settled=bool(engine.d.Solution.ControlActionsDone())))
    finally:engine.close()
    exact_seconds=time.perf_counter()-start
    exact_pass=all(row['settled'] and row['Vmin']>=.95-1e-9 and row['Vmax']<=1.05+1e-9
                   and max(row['rho'],row['tx_current'],row['tx_kva'])<=1+1e-9 for row in rows)
    save(H/'B2_preflight/STAY_EXACT_SLOTS.json',rows)
    worst=max(rows,key=lambda row:max(row['rho'],row['tx_current'],row['tx_kva'],
        max(0.,.95-row['Vmin'])*20,max(0.,row['Vmax']-1.05)*20))
    save(H/'B2_preflight/STAY_EXACT_DIAGNOSTIC.json',dict(status='PASS' if exact_pass else 'FAIL',
        worst=worst,metrics=dict(rho=max(r['rho'] for r in rows),Vmin=min(r['Vmin'] for r in rows),
            Vmax=max(r['Vmax'] for r in rows),transformer_current=max(r['tx_current'] for r in rows),
            transformer_kva=max(r['tx_kva'] for r in rows)),
        interpretation='Fixed STAY-route diagnostic only; not the full B2 search acceptance'))
    report=dict(status='PASS',summary=('Fixed STAY-route profile; exact AC PASS' if exact_pass else
        'Fixed STAY-route profile; exact AC FAIL diagnostic, full B2 acceptance remains gated'),
        date='2025-05-01',BG=.552,AIDC=2.4,MESS=2.,workers=1,threads=4,
        coefficient_build_seconds=coefficient_seconds,coefficient_count=len(cc),
        coefficient_SHAs=coeff_hashes,traffic_load_seconds=traffic_seconds,
        context_build_seconds=context_seconds,route_candidate_evaluation_seconds=route_seconds,
        route_candidate_count=len(enum.candidates),screened_route_count=len(screen),
        model_build_seconds=model_build_seconds,restricted_solve_seconds=restricted_seconds,
        solver_seconds=counters['solver_seconds'],separation_and_cut_seconds=separation_seconds,
        separation_iterations=counters['optimize_calls'],evaluation_seconds=counters['evaluation_seconds'],
        final_active_state_count=active,initial_seed_state_count=seed['counts'],
        exact_AC_validation_seconds=exact_seconds,diagnostic_STAY_exact_AC_PASS=exact_pass,
        diagnostic_exact_rho=max(r['rho'] for r in rows),planning_rho=dispatch['rho'],
        objective_consistency=evaluation['exact_optimality_certificate'],
        polygon_precompute=dict(uncached_seconds=uncached,first_seconds=first,
            cache_hit_seconds=hit,exact_array_equality=equal,
            hit_rate=mess_grid8500._POLYGON_CACHE_HITS/max(1,mess_grid8500._POLYGON_CACHE_HITS+mess_grid8500._POLYGON_CACHE_MISSES)),
        stage_C_feasible_same_scale_incumbent='UNAVAILABLE',
        B2_SEARCH_DOMAIN_CHANGED=False,active_set_hard_cap=False,
        full_separation_required=True,diagnostic_not_production=True)
    save(H/'B2_PERFORMANCE_PREFLIGHT.json',report)
    print('B2_PREFLIGHT_PASS',json.dumps({k:report[k] for k in ('model_build_seconds',
        'route_candidate_evaluation_seconds','restricted_solve_seconds','separation_iterations',
        'exact_AC_validation_seconds','diagnostic_exact_rho')}),flush=True)


if __name__=='__main__':
    try:profile()
    except BaseException as error:
        save(H/'B2_PERFORMANCE_PREFLIGHT.json',dict(status='FAIL',error=repr(error),
            traceback=traceback.format_exc()))
        raise
