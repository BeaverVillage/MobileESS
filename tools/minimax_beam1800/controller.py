"""Frozen cold-start minimax matheuristic, one worker, cumulative Native budget."""
from collections import Counter
from pathlib import Path
import gc,math,shutil,subprocess,sys,time,traceback,argparse
import numpy as np
from tools.minimax_beam1800.adapter import *
from tools.minimax_beam1800 import native0
from tools.minimax_beam1800.grid import refresh
from tools.minimax_beam1800.routes import generate,choose

def invoke(args,log,module='tools.minimax_beam1800.worker'):
    start=time.perf_counter()
    with Path(log).open('w',encoding='utf-8') as stream:
        child=subprocess.run([sys.executable,'-X','utf8','-m',module,*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    return child.returncode,time.perf_counter()-start

def prepare():
    DOCS.mkdir(parents=True,exist_ok=True);assert not (DOCS/'RUN_STARTED.json').exists()
    assert read(DOCS/'PR218_READONLY_FAILURE_ANALYSIS.json')['PASS']
    r.create_baseline();source=r.audit('MINIMAX_PREPARE',True);write(DOCS/'PRE_RUN_RESOURCE_SOURCE_AUDIT.json',source);assert source['PASS']
    external=Path('D:/v42_b2_k32_routefixed1800_canary_20261012');prior_final=read(external/'docs/v42_b2_k32_routefixed1800_canary/FINAL_STATE.json')
    assert prior_final['stopped_reason']=='NATIVE_BUDGET_END' and read(external/'docs/v42_b2_k32_routefixed1800_canary/FINAL_INDEPENDENT_REVIEW.json')['PASS']
    baseline=read(r.BASELINE);known={x['path'] for x in baseline['protected_files']}
    index=read(external/'docs/v42_b2_k32_routefixed1800_canary/DELIVERY_ARTIFACT_INDEX.json')
    for item in index['files']:
        path=external/item['path'];assert v.file_sha(path)==item['sha256']
        if str(path) not in known:baseline['protected_files'].append(r.digest(path));known.add(str(path))
    write(r.BASELINE,baseline);r.baseline.cache_clear()
    write(DOCS/'PR218_COMPLETED_READONLY_RECEIPT.json',dict(PASS=True,exact_HEAD=BASE,completed_state=record(external/'docs/v42_b2_k32_routefixed1800_canary/FINAL_STATE.json'),
        all_published_artifacts_rehashed=len(index['files']),no_concurrent_heavy_native=source['checks'],old_Native_not_new_performance=True))
    for filename in ('SIGNED_SELECTION_CONTEXT.json','SIGNED_SELECTION_SOURCE_RAW.json','SIGNED_SELECTION_INDEPENDENT_NATIVE0.json','U4_K32_SIGNED_DIAGNOSTICS.json'):
        if not (DOCS/filename).exists():shutil.copyfile(OLD/filename,DOCS/filename)
    case=v.load_case();case.A=case.A.tocsr();identity=case.identity
    assert identity['original_matrix_sha']==v.FULL_MATRIX_SHA and identity['original_domain_sha']==v.FULL_DOMAIN_SHA
    spec=cold_spec(case);low,high,*_=restriction(case,None,spec);assert audit(case,None,spec,low,high)['PASS']
    independent=native0.template(case)
    if not (DOCS/'grid/epoch99').exists():
        context,path=refresh(case,case.point,99)
        context['independent_source_projection']=native0.grid(case,context);write(path,context)
    else:context=read(DOCS/'grid/epoch99/CRITICAL_MINIMAX_CONTEXT.json')
    # Read-only algebra/regression test uses the Source authority reference,
    # never an N1 point and never a solver start or a new performance point.
    queue,search=generate(case,case.point,context,99)
    assert len(queue)>8 and all(c['moves']>=1 for c in queue)
    counts=Counter();seen=set();chosen=[]
    for i in range(4):
        c=choose(queue,seen,counts,i);seen.add(c['signature']);counts.update(c['units']);chosen.append(c)
        s=route_spec(case,c);lo,hi,*_=restriction(case,None,s);assert audit(case,None,s,lo,hi)['PASS']
    assert set(counts)==set(case.graph[1])
    from tools.minimax_beam1800.conditional_lp import build_arrays
    A,d,proof=build_arrays(route_spec(case,chosen[0]),context)
    assert proof['PASS'] and A.shape[1]==27599
    bad=dict(s);bad['route_fixed_values']=list(s['route_fixed_values']);bad['route_fixed_values'][0]=1-bad['route_fixed_values'][0]
    rejected=False
    try:audit(case,None,bad,lo,hi)
    except AssertionError:rejected=True
    assert rejected
    write(DOCS/'PRE_NATIVE0_REGRESSION.json',dict(PASS=True,independent_LP_template=independent,
        grid_projection=context['independent_source_projection'],moving_routes=len(queue),first_four_vehicle_counts=dict(counts),
        corrupt_route_rejected=True,LP_rows=A.shape[0],LP_columns=A.shape[1],heuristic_readonly_Source_reference=True,
        reference_registered_as_new_UB=False,reference_used_as_solver_start=False,Native_optimize_calls=0))
    certs={}
    for key,i,value in [('K32',1,.46497617639758426),('K48',2,GLOBAL_LB)]:
        folder=ROOT/f'docs/v42_critical_grid_cg/iteration{i:02d}';packet=read(folder/'INDEPENDENT_CERTIFICATE.json')
        assert packet['PASS'] and packet['Global_LB']==value and packet['source18r']==v.SOURCE_SHA and packet['case_sha']==v.CASE_SHA
        assert packet['FULL_projection_subset_native_Joint'] and packet['native_source_attribute']=='ObjBound'
        for name,digest in read(folder/'INDEPENDENT_NATIVE0.json')['file_sha256'].items():assert v.file_sha(folder/name)==digest
        certs[key]=dict(LB=value,certificate=record(folder/'INDEPENDENT_CERTIFICATE.json'),proof=packet,model_and_coefficient_files_rehashed=True)
    write(DOCS/'K32_K48_LB_CERTIFICATES.json',dict(PASS=True,certificates=certs,Global_LB=GLOBAL_LB,new_Optimize_calls=0,
        FULL_matrix_SHA=v.FULL_MATRIX_SHA,FULL_domain_SHA=v.FULL_DOMAIN_SHA))
    write(DOCS/'SOURCE_AND_CASE_AUTHORITY.json',dict(PASS=True,base_PR218=BASE,source_PR207=v.SOURCE_SHA,case_SHA=v.CASE_SHA,
        FULL_matrix_SHA=v.FULL_MATRIX_SHA,FULL_domain_SHA=v.FULL_DOMAIN_SHA,identity=identity,authority=source['originals'],source_equivalence_proofs=case.source_evidence))
    policy=dict(Native_limit=1800,Threads=1,Heavy_workers=1,GPU=False,RAM_reserve_GiB=4,Commit_reserve_GiB=6,
        initial_plan=dict(cold=120,LP=240,MILP=1260,reserve=180),per_call_caps=dict(INITIALIZE=120,CONDITIONAL_LP=30,ROUTE_FIXED=75),
        improvement_delta=1e-5,strict_baseline_delta=1e-5,material_baseline_delta=.005,UB_tolerance=1e-8,global_gap_target=.03,
        cold_U4_only_if_initialization_fails=True,no_N1_upfront=True,no_historical_solver_start=True,no_new_Global_LB_optimize=True,
        stationary_control_maximum=1,stationary_control_after_Native=300,stationary_control_only_before_moving_baseline_match=True,
        LP_pilot_candidates=8,LP_budget_cap=240,LP_gate=dict(median_Native_max=5,median_build_wall_max=15,
            minimum_certified_ratio=.75,minimum_prune_ratio=.125,weak_gap_threshold=.02),
        LP_gate_logic='Disable after8 if slow, less75% certified, or no prunes and median matched unrestricted MILP-minus-LP gap>.02; release unused LP budget',
        mode_objective_and_FULL_constraints_unchanged=True,goal_policy='Pilot unrestricted, thereafter3of4 moving models rho<=currentUB-1e-5; every4th unrestricted',
        search_beam_width=64,max_MOVE_per_vehicle=3,ranking_frozen_before_Native=True,no_budget_reset=True,
        ACTUAL='ACTUAL_NOT_RUN',May01_only=True,algorithm='Certified Matheuristic / Bound-Guided Anytime MILP')
    write(DOCS/'PREREGISTERED_POLICY.json',policy)
    files=[]
    for directory in ('tools/minimax_beam1800','tools/k32_routefixed1800','tools/integrated_primal1800','tools/u4_primal_alns',
        'v42_common_mess','tools/b2_root_lp_tightening','tools/critical_grid_cg','tools/time_decomposed_lb'):
        files.extend((ROOT/directory).glob('*.py'))
    files.append(DOCS/'PREREGISTERED_POLICY.json')
    write(DOCS/'EXECUTED_SOURCE_HASHES.json',{str(p.relative_to(ROOT)):v.file_sha(p) for p in files})
    print(json.dumps(dict(PASS=True,Native_calls=0,moving_routes=len(queue))),flush=True)

def run():
    assert not (DOCS/'RUN_STARTED.json').exists(),'NO_IMPLICIT_RESTART_OR_RESET';guard();start=time.perf_counter()
    write(DOCS/'RUN_STARTED.json',dict(UTC=r.timestamp(),Native_limit=1800))
    state=dict(Native_used=0.,calls=[],iterations=[],events=[],trajectory=[],moving_trajectory=[],search_epochs=[],LP_pilot=[],
        LP_screening_enabled=True,LP_native=0.,LP_wall=0.,LP_exact_pruned=0,counts={},BEST_GLOBAL_UB=None,
        BEST_MOVING_FEASIBLE_UB=None,Global_LB=GLOBAL_LB,Global_gap=None,stopped_reason=None,ACTUAL='ACTUAL_NOT_RUN',
        unrestricted_FULL_Optimize_calls=0,new_Global_LB_Optimize_calls=0,historical_solver_starts=0,N1_upfront_calls=0,
        source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA)
    seen=set();counts=Counter();epoch=0;last_center=None;queue=[];grid_path=None;control_done=False;index=0
    def persist():
        state['controller_wall_seconds']=time.perf_counter()-start;state['counts']=dict(counts)
        best=state['BEST_GLOBAL_UB'];state['Global_gap']=None if best is None else (best['UB']-GLOBAL_LB)/best['UB']
        write(DOCS/'LIVE_STATE.json',state);write(DOCS/'NATIVE_RUNTIME_LEDGER.json',dict(Native_limit=1800,Native_used=state['Native_used'],calls=state['calls'],
            all_Optimize_calls_included=True,budget_reset_count=0))
    def register_call(path,rc,wall):
        assert path.exists(),'MISSING_NATIVE_RECEIPT_STOP';call=read(path)
        assert call['entered_native'],'PRE_NATIVE_GATE_STOP'
        runtime=call['Native_Runtime'];assert runtime is not None and math.isfinite(runtime) and runtime>=0
        before=state['Native_used'];state['Native_used']+=runtime
        call.update(receipt=record(path),worker_exit_code=rc,worker_wall_seconds=wall,cumulative_Native_before=before,cumulative_Native_after=state['Native_used'])
        state['calls'].append(call);persist();assert state['Native_used']<=1800,'NATIVE_BUDGET_CEILING'
        assert not call.get('callback_errors') and not call.get('callback_stop_reason'),'CALLBACK_STOP'
        assert not call.get('error'),'WORKER_ERROR_STOP'
        return call
    def full(method,candidate=None):
        nonlocal index
        guard();remaining=1800-state['Native_used']-5.;assert remaining>2
        index+=1;folder=DOCS/f'calls/{index:03d}_{method}';folder.mkdir(parents=True,exist_ok=False)
        case=v.load_native_case();goal=None
        if method=='INITIALIZE':spec=cold_spec(case)
        else:
            is_control=candidate.get('stationary_control',False)
            assert is_control or (candidate['moves']>=1 and candidate['paths']!=stationary_paths(case))
            moving_count=sum(i['method']=='ROUTE_FIXED' and not (i['candidate'] or {}).get('stationary_control') for i in state['iterations'])
            if not is_control and moving_count>=8 and moving_count%4!=3:goal=state['BEST_GLOBAL_UB']['UB']-1e-5
            spec=route_spec(case,candidate,goal)
        lo,hi,*_=restriction(case,None,spec);assert audit(case,None,spec,lo,hi,folder/'PRE_NATIVE0.json')['PASS']
        write(folder/'SPEC.json',spec);del case,lo,hi;gc.collect()
        seconds=min(120 if method=='INITIALIZE' else 75,remaining)
        rc,wall=invoke(['--mode','native','--method',method,'--spec',folder/'SPEC.json','--output',folder/'native','--seconds',seconds],folder/'WORKER.log')
        call=register_call(folder/'native/NATIVE_CALL.json',rc,wall);iteration=dict(method=method,candidate=candidate,
            specification=record(folder/'SPEC.json'),call=call['receipt'],validated=[],result_states=[],goal=goal,verified_UB=None)
        state['iterations'].append(iteration);persist()
        # Keep every raw capture. Duplicate vectors share a single independent
        # original FULL replay receipt, without changing solver-native bytes.
        replayed={}
        for k,capture in enumerate(call['captures']):
            raw=Path(capture['file']['path']);key=capture['vector_sha256'];vwall=0.
            if key not in replayed:
                replay=folder/f'REPLAY_{k:03d}.json'
                vrc,vwall=invoke(['--mode','validate','--point',raw,'--output',replay,'--solver-objective',capture['Solver_ObjVal']],folder/f'VERIFY_{k:03d}.log')
                cert=read(replay) if replay.exists() else dict(PASS=False)
                replayed[key]=(replay,cert,vrc)
            replay,cert,vrc=replayed[key]
            item=dict(raw=record(raw),replay=record(replay),PASS=vrc==0 and cert.get('PASS',False),validation_wall_seconds=vwall,
                Native_capture_seconds=call['cumulative_Native_before']+capture['discovered_Native_seconds'],
                cumulative_Native_at_FULL_validation=state['Native_used'],controller_wall_at_FULL_validation=time.perf_counter()-start)
            iteration['validated'].append(item)
            if not item['PASS']:iteration['result_states'].append('FULL_REPLAY_FAIL');continue
            ub=cert['Global_UB'];moves=0 if candidate is None else candidate['moves'];assert ub>=GLOBAL_LB-1e-8
            result=dict(UB=ub,point=record(raw),replay=record(replay),method=method,moves=moves,candidate_id=spec['candidate_id'],
                Native_capture_seconds=item['Native_capture_seconds'],cumulative_Native_at_FULL_validation=state['Native_used'],
                controller_wall_at_FULL_validation=item['controller_wall_at_FULL_validation'],stationary_control=spec.get('stationary_control',False))
            state['events'].append(result)
            iteration['verified_UB']=ub if iteration['verified_UB'] is None else min(ub,iteration['verified_UB'])
            if moves>0 and (state['BEST_MOVING_FEASIBLE_UB'] is None or ub<state['BEST_MOVING_FEASIBLE_UB']['UB']-1e-8):
                state['BEST_MOVING_FEASIBLE_UB']=result;state['moving_trajectory'].append(result)
            if state['BEST_GLOBAL_UB'] is None or ub<state['BEST_GLOBAL_UB']['UB']-1e-8:
                state['BEST_GLOBAL_UB']=result;state['trajectory'].append(result)
                print(json.dumps(dict(verified_UB=ub,moves=moves,Native_capture=item['Native_capture_seconds'],Native_validation=state['Native_used'])),flush=True)
            persist()
        if iteration['verified_UB'] is not None:iteration['result_states'].append('FULL_FEASIBLE_MOVING' if candidate and candidate['moves'] else 'FULL_FEASIBLE_STATIONARY')
        else:iteration['result_states'].append('IMPROVEMENT_GOAL_INFEASIBLE_NOT_PHYSICAL_INFEASIBLE' if call.get('Status')==3 and goal is not None else
            'ROUTE_MILP_INFEASIBLE' if call.get('Status')==3 else 'TIME_LIMIT_NO_FULL_FEASIBLE' if call.get('Status')==9 else 'UNRESOLVED')
        persist();return iteration,call
    def lp(candidate,spec,folder):
        cap=min(30.,240-state['LP_native'],1800-state['Native_used']-5.)
        rc,wall=invoke(['--spec',spec,'--grid',grid_path,'--output',folder,'--seconds',cap],folder.parent/'LP_WORKER.log','tools.minimax_beam1800.conditional_lp')
        call=register_call(folder/'NATIVE_CALL.json',rc,wall);state['LP_native']+=call['Native_Runtime'];state['LP_wall']+=wall
        cert=native0.certificate(folder);prune=cert.get('certified') and cert['Certified_LP_LB']>=state['BEST_GLOBAL_UB']['UB']-1e-8
        metric=dict(candidate_id=candidate['candidate_id'],certified=bool(cert.get('certified')),bound=cert.get('Certified_LP_LB'),
            pruned=bool(prune),Native=call['Native_Runtime'],build_wall=call['build_wall_seconds'],worker_wall=wall,
            memory=call['after_native_memory'],status=call.get('Status'),MILP_UB=None,MILP_minus_LP=None,folder=str(folder))
        state['LP_pilot'].append(metric);state['LP_exact_pruned']+=int(prune);persist();return metric
    try:
        full('INITIALIZE');assert state['BEST_GLOBAL_UB'] is not None,'NO_COLD_FULL_FEASIBLE_SAFE_STOP'
        # No U4 is needed for an already feasible cold point. No N1 upfront.
        while 1800-state['Native_used']>7:
            persist();guard()
            if state['Global_gap']<=.03:state['stopped_reason']='GLOBAL_GAP_3PCT_CERTIFIED';break
            center=state['BEST_GLOBAL_UB']['point']['sha256']
            if center!=last_center:
                began=time.perf_counter();case=v.load_case();point=v.load_point(state['BEST_GLOBAL_UB']['point']['path'])
                context,grid_path=refresh(case,point,epoch)
                context['independent_source_projection']=native0.grid(case,context);write(grid_path,context)
                queue,search=generate(case,point,context,epoch)
                search['generation_wall_seconds']=time.perf_counter()-began;state['search_epochs'].append(search)
                write(DOCS/f'ROUTE_CANDIDATES_EPOCH_{epoch:02d}.json',dict(candidates=queue,search=search,center=state['BEST_GLOBAL_UB']))
                last_center=center;epoch+=1;del case,point;gc.collect();persist()
                print(json.dumps(dict(generated_candidates=len(queue),Native=state['Native_used'])),flush=True)
            moving=state['BEST_MOVING_FEASIBLE_UB'];matched=moving is not None and moving['UB']<=HISTORICAL+1e-8
            if not control_done and state['Native_used']>=300 and not matched:
                case=v.load_native_case();paths=stationary_paths(case);del case;gc.collect()
                control=dict(candidate_id='STAY_ONLY_CONTROL_ONCE_AFTER300',paths=paths,moves=0,travel_energy_kWh=0.,score=0.,units=[],
                    stationary_control=True,mathematically_original_N1_equivalent=True)
                control_done=True;full('ROUTE_FIXED',control);continue
            c=choose(queue,seen,counts,len(seen))
            if c is None:state['stopped_reason']='CANDIDATES_EXHAUSTED';break
            seen.add(c['signature']);counts.update(c['units']);print(json.dumps(dict(evaluating=c['candidate_id'],units=c['units'],moves=c['moves'],score=c['score'],Native=state['Native_used'])),flush=True)
            metric=None
            if state['LP_screening_enabled'] and state['LP_native']<235 and 1800-state['Native_used']>40:
                folder=DOCS/f'lp_calls/{len(state["LP_pilot"])+1:03d}';folder.mkdir(parents=True,exist_ok=False)
                case=v.load_native_case();spec=route_spec(case,c);del case;gc.collect();write(folder/'SPEC.json',spec)
                metric=lp(c,folder/'SPEC.json',folder/'native')
            if metric is None or not metric['pruned']:
                if 1800-state['Native_used']<=7:break
                it,call=full('ROUTE_FIXED',c)
                if metric is not None:
                    metric['MILP_UB']=it['verified_UB'];metric['MILP_minus_LP']=None if it['verified_UB'] is None or metric['bound'] is None else it['verified_UB']-metric['bound']
            if len(state['LP_pilot'])>=8 and 'LP_PRACTICAL_GATE' not in state:
                metrics=state['LP_pilot'][:8];gap=[m['MILP_minus_LP'] for m in metrics if m['MILP_minus_LP'] is not None]
                observed=dict(median_Native=float(np.median([m['Native'] for m in metrics])),median_build_wall=float(np.median([m['build_wall'] for m in metrics])),
                    certified_ratio=sum(m['certified'] for m in metrics)/8,prune_ratio=sum(m['pruned'] for m in metrics)/8,
                    median_MILP_minus_LP=None if not gap else float(np.median(gap)))
                disabled=observed['median_Native']>5 or observed['median_build_wall']>15 or observed['certified_ratio']<.75 or (
                    observed['prune_ratio']<.125 and (observed['median_MILP_minus_LP'] is None or observed['median_MILP_minus_LP']>.02))
                state['LP_screening_enabled']=not disabled;state['LP_PRACTICAL_GATE']=dict(PASS=True,observed=observed,disabled=disabled,preregistered=True,
                    released_budget=max(0.,240-state['LP_native']))
                write(DOCS/'LP_PRACTICAL_GATE.json',state['LP_PRACTICAL_GATE']);persist()
        if not state['stopped_reason']:state['stopped_reason']='NATIVE_BUDGET_END'
    except Exception as exc:
        state.update(stopped_reason='SOURCE_RESOURCE_OR_VALIDITY_SAFE_STOP',error=repr(exc),traceback=traceback.format_exc());print(state['traceback'],flush=True)
    finally:
        persist();write(DOCS/'FINAL_STATE.json',state);print(json.dumps(dict(stopped_reason=state['stopped_reason'],Native=state['Native_used'],UB=state['BEST_GLOBAL_UB'],Moving=state['BEST_MOVING_FEASIBLE_UB'],gap=state['Global_gap'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run']);a=p.parse_args();prepare() if a.mode=='prepare' else run()
