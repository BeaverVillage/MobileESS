"""Original V41R4 K/beam MESS machinery, IEEE8500 electrical ports only."""
from common8500 import *
from types import SimpleNamespace
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import inspect,shutil
import mess_grid8500
from dayahead.v33m.mess_trajectory import MessTrajectory
PROFILE_CAPTURE={}
class FullModelCaptured(Exception):pass
def four_thread_paper_candidate(**kwargs):
    from dayahead.v39e.runtime import four_thread_fixed_candidate
    item=four_thread_fixed_candidate(**kwargs)
    assert item.model.Params.Threads==4
    return item
class Authority(dict):
    @property
    def files(self):return list(self)
    def close(self):pass
def coefficients():
    # Encode normalized phase-current norm bounds via the existing complex
    # thermal API, in addition to native winding-kVA bounds. Matrices unchanged.
    return tuple(replace(build(t),transformer_ratings=tuple([None]*NL+[1.]*NT+AX['winding_rating_kVA'])) for t in range(96))
def integrated_adapter(policy='AUDIT',profile_mode=False,grid_mode='full'):
    from dayahead.v34.integrated_mess import solve_integrated_mess
    from dayahead.v34 import integrated_mess as integrated_module
    import gurobipy as gp
    import math
    if grid_mode=='full':
        grid_builder=mess_grid8500.integrated_grid
        active_module=None
    elif grid_mode=='active_seed':
        import mess_grid8500_active
        grid_builder=mess_grid8500_active.integrated_grid
        active_module=mess_grid8500_active
        if not profile_mode:
            active_module.REPORT_ROOT=P/policy/'active_grid'
            active_module.ACTIVE_COUNT=max((int(path.name[5:]) for path in active_module.REPORT_ROOT.glob('call_*')
                                            if path.is_dir() and path.name[5:].isdigit()),default=0)
    else:
        raise ValueError(f'UNKNOWN_GRID_MODE:{grid_mode}')
    src=inspect.getsource(solve_integrated_mess)
    old='if len(controls) != 60 or len(node_names) != 386:'
    assert src.count(old)==1;src=src.replace(old,'if len(controls) != 60 or len(node_names) != 8639:')
    src=src.replace('"V34_FROZEN_C376_MAPPING"','"IEEE8500_FROZEN_24_MESS_PCC"')
    start=src.index('    for slot, coefficient in enumerate(coefficients):\n        for index, node in enumerate(node_names):')
    end=src.index('    cut_rows, trust_region_constraint_count = _add_restoration_cuts(',start)
    src=src[:start]+"    assert correction is None\n    grid_constraints += ieee8500_grid(model, coefficients, expressions_by_slot, eta, inputs)\n\n"+src[end:]
    build_marker='    model_build_seconds = time.perf_counter() - build_started\n'
    assert src.count(build_marker)==1
    src=src.replace(build_marker,build_marker+
        '    model_build_observed(model, model_build_seconds, build_started)\n')
    prepare_marker='    quality_bound = min(float(restricted["objective"]), preferred_objective)\n'
    assert src.count(prepare_marker)==1
    src=src.replace(prepare_marker,prepare_marker+
        '    full_solve_prepare(model, quality_bound, preferred_loaded, restricted, model_build_seconds, build_started)\n')
    preferred_marker='            preferred_objective = float(preferred["objective"])\n'
    assert src.count(preferred_marker)==1
    src=src.replace(preferred_marker,
        '            preferred = certify_preferred_for_full_grid(model, preferred)\n'+preferred_marker)
    solve_marker='        model.optimize()\n        if model.SolCount < 1:'
    assert src.count(solve_marker)==1
    if grid_mode=='active_seed' and not profile_mode:
        src=src.replace(solve_marker,
            '        full_solve_entry(model)\n        grid_constraints += full_active_optimize(model)\n        if model.SolCount < 1:')
    else:
        src=src.replace(solve_marker,
            '        full_solve_entry(model)\n        model.optimize(full_progress_callback)\n        if model.SolCount < 1:')
    trace=P/policy/'solver_trace';trace.mkdir(parents=True,exist_ok=True)
    active_trace=[trace]
    call_count=[max((int(path.name[5:]) for path in trace.glob('call_*')
                    if path.is_dir() and path.name[5:].isdigit()),default=0)]
    clock=[0.0];last=[0.0]
    def finite(value):
        value=float(value)
        return value if math.isfinite(value) and abs(value)<1e90 else None
    build_metrics={}
    def model_build_observed(model,model_build_seconds,build_started):
        if policy in ('B2','B3','B3_M1') and not profile_mode:
            call_count[0]+=1
            active_trace[0]=trace/f'call_{call_count[0]:05}'
            active_trace[0].mkdir(parents=True,exist_ok=True)
        build_metrics.update(build_started_perf=build_started,
            model_build_end_perf=time.perf_counter(),model_build_seconds=float(model_build_seconds),
            model_build_end_unix=time.time())
        save(active_trace[0]/'BUILD.json',dict(status='MODEL_BUILT',policy=policy,
            grid_mode=grid_mode,
            model_build_seconds=float(model_build_seconds),
            model_build_start_unix=build_metrics['model_build_end_unix']-float(model_build_seconds),
            model_build_end_unix=build_metrics['model_build_end_unix']))
    def full_solve_prepare(model,quality_bound,preferred_loaded,restricted,model_build_seconds,build_started):
        model.update()
        # Keep the original MIPFocus and all mathematical/closure parameters.
        model.Params.LogToConsole=0
        model.Params.OutputFlag=1
        model.Params.LogFile=str(active_trace[0]/f'full_mip_{time.time_ns()}.log')
        model.Params.DisplayInterval=30
        clock[0]=time.perf_counter();last[0]=0.0
        save(active_trace[0]/'ENTER.json',dict(status='RUNNING',policy=policy,
            source='unchanged full MESS model; timing and Gurobi logging instrumentation only',
            variables=int(model.NumVars),binary_variables=int(model.NumBinVars),
            constraints=int(model.NumConstrs),preferred_incumbent_loaded=bool(preferred_loaded),
            restricted_status=str(restricted['status']),quality_bound=finite(quality_bound),
            objective='UNCHANGED',feasible_route_domain='UNCHANGED',
            mip_gap=float(model.Params.MIPGap),mip_focus=int(model.Params.MIPFocus),
            threads=int(model.Params.Threads),time_limit=float(model.Params.TimeLimit),
            work_limit=float(model.Params.WorkLimit),work_limit_tiers=list(integrated_module.WORK_LIMIT_TIERS),
            termination_authority='PAPER_SOLVER_TERMINATION',
            soft_memory_limit=float(model.Params.SoftMemLimit),model_build_seconds=float(model_build_seconds),
            preparation_after_build_seconds=time.perf_counter()-build_metrics['model_build_end_perf'],
            total_before_full_optimize_seconds=time.perf_counter()-build_started,
            unix=time.time()))
        state(status='RUNNING',stage=policy+':FULL_MIP_SOLVE',
            full_mip_variables=int(model.NumVars),full_mip_constraints=int(model.NumConstrs),
            full_mip_incumbent_loaded=bool(preferred_loaded))
        if profile_mode:
            PROFILE_CAPTURE.clear()
            PROFILE_CAPTURE.update(model=model,preferred_loaded=bool(preferred_loaded),
                quality_bound=finite(quality_bound),build_metrics=dict(build_metrics),
                variables=int(model.NumVars),constraints=int(model.NumConstrs),
                binaries=int(model.NumBinVars),quadratic_constraints=int(model.NumQConstrs))
            raise FullModelCaptured()
    def certify_preferred_for_full_grid(model,preferred):
        """Only a full-grid-feasible sparse warm start can bound the full solve."""
        if not preferred['available'] or active_module is None:
            return preferred
        active=active_module.ACTIVE
        assert active is not None and active.model is model
        values=np.asarray(preferred['start'],dtype=float)
        assert len(values)==model.NumVars
        rho=float(values[active.eta.index])
        tolerance=float(model.Params.FeasibilityTol)
        maximum=-float('inf');violated=0;witness=None;checked=0
        for slot,coefficient in enumerate(active.coefficients):
            fixed,C,variables,_,_=active.parts[slot]
            numeric=fixed+C@values[[variable.index for variable in variables]]
            for group,(kind,w,constant,limit) in enumerate(mess_grid8500.rows(coefficient)):
                residual=constant+w@numeric-(rho if kind=='line' else limit)
                checked+=len(residual)
                peak=float(residual.max())
                if peak>maximum:
                    maximum=peak
                    witness=dict(slot=slot,group=group,kind=kind,
                                 row=int(np.argmax(residual)),violation=peak)
                violated+=int(np.count_nonzero(residual>tolerance))
        assert checked==active.logical_rows==31945536
        audit=dict(status='PASS' if violated==0 else 'NOT_FULL_GRID_FEASIBLE',
                   source='preferred incumbent solved against sparse seed before full separation',
                   preferred_objective=float(preferred['objective']),
                   max_original_row_violation=maximum,violated_rows=violated,
                   checked_rows=checked,tolerance=tolerance,witness=witness,
                   original_full_grid_acceptance_guard_unchanged=True)
        save(active_trace[0]/'PREFERRED_START_FULL_GRID_AUDIT.json',audit)
        if violated:
            for variable in model.getVars():
                variable.Start=gp.GRB.UNDEFINED
            model.update()
            return dict(preferred,available=False,objective=math.inf,start=())
        return preferred
    def full_solve_entry(model):
        save(active_trace[0]/'OPTIMIZE_ENTRY.json',dict(status='OPTIMIZE_ENTERED',policy=policy,
            unix=time.time(),elapsed_since_build_start_seconds=time.perf_counter()-build_metrics['build_started_perf'],
            variables=int(model.NumVars),constraints=int(model.NumConstrs),
            binary_variables=int(model.NumBinVars),quadratic_constraints=int(model.NumQConstrs)))
    def full_progress_callback(model,where):
        if where!=gp.GRB.Callback.MIP:return
        now=time.perf_counter()
        if now-last[0]<60.:return
        last[0]=now
        try:
            best=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBST))
            bound=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBND))
            payload=dict(status='RUNNING',policy=policy,elapsed_seconds=now-clock[0],
                incumbent=best,best_bound=bound,
                relative_gap=(abs(best-bound)/max(abs(best),1e-12) if best is not None and bound is not None else None),
                explored_nodes=finite(model.cbGet(gp.GRB.Callback.MIP_NODCNT)),
                open_nodes=finite(model.cbGet(gp.GRB.Callback.MIP_NODLFT)),
                solutions=finite(model.cbGet(gp.GRB.Callback.MIP_SOLCNT)),unix=time.time())
            save(active_trace[0]/'CURRENT.json',payload)
            save(active_trace[0]/f'progress_{int(payload["elapsed_seconds"]):07d}.json',payload)
            state(status='RUNNING',stage=policy+':FULL_MIP_SOLVE',solver_progress=payload)
        except Exception as error:
            print('B2_SOLVER_PROGRESS_CALLBACK_WARNING',repr(error),flush=True)
    def full_active_optimize(model):
        assert active_module is not None and active_module.ACTIVE is not None
        assert model.Params.MIPGap==.001 and model.Params.Threads==4
        assert model.Params.TimeLimit==600.
        assert model.Params.WorkLimit in integrated_module.WORK_LIMIT_TIERS
        assert model.Params.NodeLimit>=gp.GRB.INFINITY
        accepted_statuses={gp.GRB.OPTIMAL,gp.GRB.WORK_LIMIT,gp.GRB.TIME_LIMIT,gp.GRB.SUBOPTIMAL}
        added_total=0
        iteration=max((int(p.name.split('_')[1]) for p in active_trace[0].glob('ITERATION_*_START.json')),default=0)
        while True:
            iteration+=1
            model.Params.LogFile=str(active_trace[0]/f'active_iteration_{iteration:03}_{time.time_ns()}.log')
            model.update()
            before=dict(rows=int(model.NumConstrs),columns=int(model.NumVars),
                        binaries=int(model.NumBinVars),nonzeros=int(model.NumNZs),
                        quadratic_constraints=int(model.NumQConstrs))
            save(active_trace[0]/f'ITERATION_{iteration:03}_START.json',dict(
                status='RUNNING',iteration=iteration,unix=time.time(),model=before,
                time_limit=float(model.Params.TimeLimit),work_limit=float(model.Params.WorkLimit),
                termination_authority='PAPER_SOLVER_TERMINATION',no_active_set_cap=True,
                original_objective_and_route_domain=True))
            began=time.perf_counter()
            model.optimize(full_progress_callback)
            elapsed=time.perf_counter()-began
            if model.SolCount<1:
                # Preserve the original outer work-tier escalation on no incumbent.
                save(active_trace[0]/f'ITERATION_{iteration:03}_FAIL.json',dict(
                    status=int(model.Status),solution_count=int(model.SolCount),
                    elapsed_seconds=elapsed,rows=before['rows']))
                return added_total
            if model.Status not in accepted_statuses:
                raise RuntimeError(f'ACTIVE_GRID_PAPER_SOLVER_STATUS:{model.Status}')
            solver_status=int(model.Status)
            incumbent=float(model.ObjVal);bound=float(model.ObjBound);gap=float(model.MIPGap)
            separation=active_module.ACTIVE.separate()
            after=dict(rows=int(model.NumConstrs),columns=int(model.NumVars),
                       binaries=int(model.NumBinVars),nonzeros=int(model.NumNZs))
            report=dict(status='FULL_SEPARATION_CLOSED' if separation['new_rows']==0 else 'CONTINUE',
                iteration=iteration,solve_seconds=elapsed,before=before,after=after,
                incumbent=incumbent,best_bound=bound,mip_gap=gap,solver_status=solver_status,
                termination_authority='PAPER_SOLVER_TERMINATION',
                explored_nodes=float(model.NodeCount) if separation['new_rows']==0 else None,
                separation=separation,log_file=model.Params.LogFile)
            save(active_trace[0]/f'ITERATION_{iteration:03}_RESULT.json',report)
            added_total+=int(separation['new_rows'])
            if separation['new_rows']==0:
                save(active_trace[0]/'FULL_SEPARATION_CLOSURE.json',dict(
                    status='PASS',iterations=iteration,all_original_electrical_rows_checked=True,
                    checked_rows=separation['all_logical_rows_checked'],
                    maximum_violation=separation['maximum_violation'],
                    tolerance=separation['exact_original_row_tolerance'],
                    incumbent=incumbent,best_bound=bound,mip_gap=gap,solver_status=solver_status,
                    optimality_proven_to_target=solver_status==gp.GRB.OPTIMAL,
                    termination_authority='PAPER_SOLVER_TERMINATION',
                    no_active_row_cap=True,no_route_pruning=True,
                    total_new_rows=added_total))
                save(active_module.ACTIVE.report_root/'FULL_SEPARATION_CLOSURE.json',
                     read(active_trace[0]/'FULL_SEPARATION_CLOSURE.json'))
                return added_total
    ns=dict(solve_integrated_mess.__globals__,ieee8500_grid=grid_builder,
            _configured_model=integrated_module._configured_model,
            WORK_LIMIT_TIERS=integrated_module.WORK_LIMIT_TIERS,
            model_build_observed=model_build_observed,full_solve_prepare=full_solve_prepare,
            certify_preferred_for_full_grid=certify_preferred_for_full_grid,
            full_solve_entry=full_solve_entry,full_progress_callback=full_progress_callback,
            full_active_optimize=full_active_optimize)
    exec(compile(src,str(P/'mess_runtime.py')+'::electrical_adapter','exec'),ns)
    destination=trace/('ADAPTED_SOURCE_PROFILE.json' if profile_mode else 'ADAPTED_SOURCE_PRODUCTION.json')
    save(destination,dict(source=record(inspect.getsourcefile(solve_integrated_mess)),grid_mode=grid_mode,
        authorized_differences=['IEEE8500 node dimension','Original electrical rows seeded sparsely and fully separated to feasibility closure' if grid_mode=='active_seed' else 'Equivalent full electrical rows with certified redundant-row presolve','Paper TimeLimit/WorkLimit tiers/SoftMemLimit and feasible-incumbent acceptance restored by user request','Unchanged objective, route domain, tolerance, MIPFocus, and MIPGap target'],
        original_non_electrical_MESS_model_and_objective_unchanged=True,adapted_source=src))
    return ns['solve_integrated_mess']
def traffic():
    from dayahead.v36.contracts import FROZEN_MESS_WORKTREE
    from dayahead.v35.execution import daily_traffic_authority
    from dayahead.v35.contracts import PHASE_CALIBRATION
    from dayahead.v41.execution import SOURCE_REPO
    inventory=SOURCE_REPO/'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json'
    frozen=read(inventory)['traffic']['2025-05-01']
    authorities={'TRAFFIC_FORECAST.npz':frozen['forecast']['file'],'ROUTE_TABLE.json.gz':frozen['route_table']['file']}
    dest=P/'traffic/shared/traffic/2025-05-01';dest.mkdir(parents=True,exist_ok=True)
    for name in ('TRAFFIC_FORECAST.npz','ROUTE_TABLE.json.gz'):
        src=Path(authorities[name]['path']);assert src.is_file() and sha(src)==authorities[name]['sha256'],('MISSING_OR_DRIFTED_FROZEN_MAY01_TRAFFIC_AUTHORITY',src)
        out=dest/name
        if out.exists():assert sha(out)==sha(src)
        else:shutil.copyfile(src,out)
    result=daily_traffic_authority(FROZEN_MESS_WORKTREE,P/'traffic',PHASE_CALIBRATION,'2025-05-01',None)
    assert result[0].causality_pass and result[0].future_actual_read_count==0
    assert result[0].canonical_sha256==frozen['forecast']['canonical_SHA'] and result[2].canonical_sha256==frozen['route_table']['canonical_SHA']
    save(P/'MESS_TRAFFIC_AUTHORITY.json',dict(status='PASS',files=list(authorities.values()),inventory_source=record(inventory),date='2025-05-01',Actual_reads=0))
    return result
def search(ctx,pcc,policy):
    from dayahead.tools import run_v35r3e_r1_beam as beam
    from dayahead.v35r3 import algorithm as r3
    from dayahead.v35r3e import algorithm as r3e
    from dayahead.v37 import runner as old
    from dayahead.v35.execution import _planning_grid
    from dayahead.v36.runner import _prepare_seed_npz
    from dayahead.v34 import integrated_mess as integrated_module
    from dayahead.v40b.windows_paths import install_beam_paths
    from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive
    _install_windows_safe_k_archive();install_beam_paths()
    folder=P/policy;folder.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    cc=coefficients();voltage=Authority(control_names=np.array(NAMES),node_names=np.array(AX['nodes']))
    electrical=SimpleNamespace(legacy_context=None,voltage=voltage,current=Authority())
    tr=traffic();mapping={r['service']:r['PCC'] for r in read(PREF/'MESS_24_SERVICE_PCC_COLUMN_BINDING.json')['services']}
    arrays,_=_planning_grid(cc,voltage,pcc,MessTrajectory(()));_prepare_seed_npz(folder,ctx.day,'B0' if policy=='B2' else 'B1',arrays,cc)
    keys=('APR01','CACHE_ROOT','prepare_aidc_stages','daily_traffic_authority','slot_coefficients','EXECUTION_CACHE_CONTEXT','PROGRESS_CALLBACK','ProcessPoolExecutor','build_fixed_candidate_model','_local_search','_solve_worker','_solve_item','_service_mapping','solve_integrated_mess','_critical_states')
    original={k:getattr(beam,k) for k in keys};guards=(r3.assert_apr01_only,r3e.assert_apr01_only);cwd=Path.cwd()
    original_work_tiers=integrated_module.WORK_LIMIT_TIERS
    seed=read(P/'COMPACT_B0_ACTIVE_SEED.json')
    assert seed['status']=='PASS' and seed['seed_only'] and not seed['active_set_hard_cap']
    exact_seed={tuple(row) for row in seed['line_states']}
    def current_b0_seed(load,names):
        states,info=original['_critical_states'](load,names)
        assert load.shape[0]==96 and load.shape[1]>=NL
        assert all(0<=t<96 and 0<=i<NL for t,i in exact_seed)
        states |= exact_seed
        info=dict(info,exact_B0_seed_states=len(exact_seed),union_seed_states=len(states),
                  seed_authority=record(P/'COMPACT_B0_ACTIVE_SEED.json'),
                  full_separation_unchanged=True)
        return states,info
    def selected(day):assert day=='2025-05-01'
    def progress(e):state(status='RUNNING',stage=policy+':MESS_FULL_SEARCH',search_started=False,MESS_progress=dict(e))
    class Pool(ThreadPoolExecutor):
        def __init__(self,max_workers=None,initializer=None,initargs=(),**kw):super().__init__(max_workers=1,initializer=initializer,initargs=initargs)
    try:
        beam.APR01=ctx.day;beam.CACHE_ROOT=folder/'beam'
        beam._critical_states=current_b0_seed
        beam.prepare_aidc_stages=lambda *a,**k:(None,electrical,{'B0':{'planning_pcc_power_kw':pcc},'B1':{'planning_pcc_power_kw':pcc}})
        beam.daily_traffic_authority=lambda *a,**k:tr;beam.slot_coefficients=lambda *a:cc[int(a[-1])]
        cache_source=sha(P/'mess_runtime.py')
        if policy=='B2' and (P/'PAPER_PARENT_GUARD_REPAIR_AUTHORITY.json').exists():
            repair=read(P/'PAPER_PARENT_GUARD_REPAIR_AUTHORITY.json')
            assert repair['status']=='PASS' and repair['current_runtime_sha256']==cache_source
            assert repair['successful_candidate_math_unchanged'] and repair['same_fresh_paper_run_only']
            cache_source=repair['prior_runtime_sha256']
        if policy=='B2' and not (P/'PAPER_SOLVER_TERMINATION_AUTHORITY.json').exists() and (P/'B2_PERFORMANCE_RESUME_AUTHORITY.json').exists():
            resume=read(P/'B2_PERFORMANCE_RESUME_AUTHORITY.json')
            assert resume['status']=='PASS' and resume['restricted_candidate_problem_unchanged']
            if resume['current_mess_runtime_sha256']!=cache_source:
                repair=read(P/'B2_PREFERRED_BOUND_REPAIR_AUTHORITY.json')
                assert repair['status']=='PASS' and repair['current_mess_runtime_sha256']==cache_source
                assert repair['prior_mess_runtime_sha256']==resume['current_mess_runtime_sha256']
                assert repair['candidate_problem_unchanged']
            cache_source=resume['prior_restricted_solver_source_sha256']
        beam.EXECUTION_CACHE_CONTEXT=dict(stage=policy,workspace=str(P),coefficient_SHAs=[c.coefficient_sha256 for c in cc],candidate_cache_root=str(folder/'candidate_cache'),binding=sha(PREF/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json'),source=cache_source)
        beam.PROGRESS_CALLBACK=progress;beam.ProcessPoolExecutor=Pool;beam.build_fixed_candidate_model=four_thread_paper_candidate
        beam._local_search=lambda **kw:old._run_local_with_frozen_k_fallback(beam,original['_local_search'],**kw)
        from paper_parent_candidate_guard import bind as bind_parent_guard
        beam._solve_item=bind_parent_guard(old,original['_solve_item'])
        beam._solve_worker=old._v37_safe_restricted_worker;beam._service_mapping=lambda:mapping
        assert tuple(integrated_module.WORK_LIMIT_TIERS)==(60.,180.,300.)
        beam.solve_integrated_mess=integrated_adapter(policy,grid_mode='active_seed')
        assert integrated_module.WORK_LIMIT_TIERS==beam.solve_integrated_mess.__globals__['WORK_LIMIT_TIERS']
        r3.assert_apr01_only=r3e.assert_apr01_only=selected
        os.chdir(folder);result=None
        for width in (2,4):
            try:result=beam._run_case('B2' if policy=='B2' else 'B3',width,1);break
            except Exception as error:
                if width==2 and old._beam_fallback_allowed(error):continue
                raise
        save(folder/'ORIGINAL_SELECTED_BEFORE_EXACT.json',result)
        trajectory=MessTrajectory(tuple(beam._restore_slots(result['trajectory_slots'])))
        exact_report=exact(pcc,trajectory.slots,folder/'final_exact');assert exact_report['status']=='PASS'
        save(folder/'FINAL_AUTHORITY.json',dict(status='PASS',P1=result['planning']['rho'],AC=exact_report['metrics'],wall_seconds=time.perf_counter()-started,trajectory_slots=result['trajectory_slots'],original_K_sequence=[200,400,800,'FULL'],original_beams=[2,4],worker_count=1))
        return trajectory,result
    finally:
        os.chdir(cwd)
        for k,v in original.items():setattr(beam,k,v)
        integrated_module.WORK_LIMIT_TIERS=original_work_tiers
        r3.assert_apr01_only,r3e.assert_apr01_only=guards
def recourse(ctx,pcc,m1):
    from dayahead.v40a import recourse as old
    prior_functions=(old.add_grid,old.evaluate_grid)
    old.add_grid=mess_grid8500.add;old.evaluate_grid=evaluate_grid
    try:
        result=old.solve_fixed_route(pcc,m1,ctx)
        from dayahead.v40a.grid import controls_from_trajectory
        before=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,pcc,m1.slots),ctx.nodes)
        accepted=result['status']=='PASS' and result['grid']['rho_max']<=before['rho_max']+1e-6
        selected=result['trajectory'] if accepted else m1
        ac=exact(pcc,selected.slots,P/'B3_MF/final_exact')
        if ac['status']!='PASS':
            fallback=exact(pcc,m1.slots,P/'B3_MF/fallback_exact');assert fallback['status']=='PASS';selected=m1
        save(P/'B3_MF/RESULT.json',result)
        return selected
    finally:old.add_grid,old.evaluate_grid=prior_functions
