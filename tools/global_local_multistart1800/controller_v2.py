"""One cumulative canary: alternate distinct global routes and their local seeds."""
import gc,math,subprocess,sys,time,traceback
from collections import Counter
from tools.global_local_multistart1800.adapter_v2 import *
from tools.global_local_multistart1800.neighborhoods import priorities,make
from tools.global_local_multistart1800.routes import choose,generate
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.joint import select_pools,build_spec,independent,pool_signature

def invoke(args,log,module='tools.global_local_multistart1800.worker_v2'):
    began=time.perf_counter()
    with Path(log).open('w',encoding='utf-8') as stream:
        p=subprocess.run([sys.executable,'-X','utf8','-m',module,*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    return p.returncode,time.perf_counter()-began

def run():
    assert not (DOCS/'RUN_STARTED.json').exists(),'NO_BUDGET_RESET';guard();began=time.perf_counter()
    policy=read(DOCS/'SEARCH_SWITCHING_POLICY.json');write(DOCS/'RUN_STARTED.json',dict(UTC=r.timestamp(),Native_limit=1800,Warm=True))
    initial=dict(UB=INITIAL_UB,point=record(ROOT/RAW_REL),replay=record(DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json'),moves=3,
        method='INHERITED_PR220',stage='INHERITED_PR220',Native_capture_seconds=0.,inherited_not_new_discovery=True)
    prior=read(DOCS/'INHERITED_V1_NATIVE_CALLS.json')
    state=dict(Native_used=prior['actual_Native_used'],calls=list(prior['calls']),iterations=[],events=[],seeds=[],switches=[],trajectory=[initial],moving_trajectory=[initial],
        BEST_GLOBAL_UB=initial,BEST_MOVING_FEASIBLE_UB=initial,BEST_JOINT_FEASIBLE_UB=initial,Global_LB=GLOBAL_LB,Global_gap=(INITIAL_UB-GLOBAL_LB)/INITIAL_UB,
        family_best={},improvements=[],joint_results=[],ablation_results=[],skips=[],stopped_reason=None,ACTUAL='ACTUAL_NOT_RUN',new_LB_Optimize_calls=0,all_four_joint_calls=0,V1_Native_offset=prior['actual_Native_used'],V1_preserved_calls=len(prior['calls']),
        unrestricted_FULL_calls=0,conditional_LP_screen_calls=0,Cold_N1_U4_calls=0,source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,
        old_PR219_Native_separate=1795.0249993801117,old_PR220_Native_separate=724.820999622345)
    seen_models=set();seen_routes=set();used_keys=set();
    for call in prior['calls']:
        folder=Path(call['receipt']['path']).parent.parent
        oldspec=read(folder/'SPEC.json');seen_models.add(oldspec['executed_mathematical_model_signature'])
    index=0;pool=read(DOCS/'GLOBAL_CANDIDATE_POOL.json')['candidates'];epoch=0
    def persist():
        state['controller_wall_seconds']=time.perf_counter()-began
        state['Global_gap']=(state['BEST_GLOBAL_UB']['UB']-state['Global_LB'])/state['BEST_GLOBAL_UB']['UB']
        write(DOCS/'LIVE_STATE.json',state);write(DOCS/'NATIVE_RUNTIME_LEDGER.json',dict(Native_used=state['Native_used'],Native_limit=1800,calls=state['calls'],budget_reset_count=0,only_new_Optimize_calls_included=True))
    def remaining():return 1800-state['Native_used']-8-(180 if state['new_LB_Optimize_calls']==0 else 0)
    def perform(spec,cap,center=None):
        nonlocal index
        if remaining()<5:return None
        guard();case=v.load_native_case();x=None if center is None else v.load_point(center['point']['path'])
        joint=spec['method']=='FOUR_MESS_JOINT_ROUTE_POOL'
        if joint:
            rebuilt,lo,hi,links,rhs=build_spec(case,x,spec['center_replay']['path'],spec['pools'],spec['candidate_id'],cap)
            sig=rebuilt['mathematical_model_signature'];proof=independent(case,x,spec,lo,hi,links,rhs)
        else:
            lo,hi,ham,coeff,rhs,_=restriction(case,x,spec);sig=signature(lo,hi,ham,coeff,rhs);proof=audit(case,x,spec,lo,hi)
        if sig in seen_models:state['skips'].append(dict(label=spec['candidate_id'],reason='DUPLICATE_MATHEMATICAL_MODEL'));persist();return None
        seen_models.add(sig);spec['executed_mathematical_model_signature']=sig;assert proof['PASS']
        index+=1;folder=DOCS/f'calls/{index:03d}_{spec["candidate_id"]}';folder.mkdir(parents=True)
        write(folder/'SPEC.json',spec);write(folder/'PRE_NATIVE0.json',proof)
        del case,x,lo,hi;gc.collect();seconds=min(cap,remaining(),175)
        args=['--spec',folder/'SPEC.json','--output',folder/'native','--seconds',seconds] if joint else ['--mode','native','--method',spec['method'],'--spec',folder/'SPEC.json','--output',folder/'native','--seconds',seconds]
        if center is not None:args+=['--center',center['point']['path']]
        state['switches'].append(dict(ordinal=index,stage=spec['stage'],family=spec['family'],Native_before=state['Native_used'],center_UB=None if center is None else center['UB']))
        print(json.dumps(dict(evaluating=spec['candidate_id'],family=spec['family'],method=spec['method'],seconds=seconds,Native=state['Native_used'],center=None if center is None else center['UB'])),flush=True)
        rc,wall=invoke(args,folder/'WORKER.log','tools.global_local_multistart1800.joint_worker_v2' if joint else 'tools.global_local_multistart1800.worker_v2');path=folder/'native/NATIVE_CALL.json';assert path.exists()
        call=read(path);assert call['entered_native'],'PRE_NATIVE_GATE_REJECTED';runtime=call['Native_Runtime'];assert runtime is not None and math.isfinite(runtime)
        before=state['Native_used'];state['Native_used']+=runtime
        call.update(receipt=record(path),worker_exit=rc,worker_wall_seconds=wall,cumulative_Native_before=before,cumulative_Native_after=state['Native_used'],family=spec['family'])
        state['calls'].append(call);state['all_four_joint_calls']+=int(joint);persist();assert state['Native_used']<=1800
        it=dict(candidate_id=spec['candidate_id'],family=spec['family'],stage=spec['stage'],method=spec['method'],specification=record(folder/'SPEC.json'),call=record(path),center=center,validated=[],best=None)
        state['iterations'].append(it);persist()
        if call.get('error') or call['callback_errors'] or call.get('callback_stop_reason') in ('RESOURCE_OR_SOURCE_CALLBACK_GATE','CALLBACK_ERROR'):raise ValueError('NATIVE_ERROR_FAIL_CLOSED')
        for k,capture in enumerate(call['captures']):
            raw=Path(capture['file']['path']);replay=folder/f'REPLAY_{k:03d}.json'
            vr,vwall=invoke(['--mode','validate','--point',raw,'--solver-objective',capture['Solver_ObjVal'],'--output',replay],folder/f'VERIFY_{k:03d}.log')
            cert=read(replay) if replay.exists() else dict(PASS=False)
            item=dict(raw=record(raw),replay=record(replay) if replay.exists() else None,PASS=vr==0 and cert.get('PASS',False),validation_wall_seconds=vwall,
                Native_capture_seconds=before+capture['discovered_Native_seconds'],cumulative_Native_at_FULL_validation=state['Native_used'],controller_wall_at_FULL_validation=time.perf_counter()-began)
            it['validated'].append(item)
            if not item['PASS']:continue
            case=v.load_native_case();x=v.load_point(raw);paths=paths_of(case,x);meta=Graph(case).metadata(paths);del case,x;gc.collect()
            ub=cert['Global_UB'];assert ub>=state['Global_LB']-1e-8
            if joint:
                if not np.isin(np.asarray(capture['lambda_values']),(0.,1.)).all():
                    item.update(PASS=False,joint_lambda_gate='STRICT_LITERAL_LAMBDA_FAILED');persist();continue
                selection={}
                for u in spec['pools']:
                    selected=[a for a,value in zip(spec['lambda_axis'],capture['lambda_values']) if a['unit']==u and value==1.]
                    assert len(selected)==1 and selected[0]['path']==paths[u],'ACTUAL_LAMBDA_ROUTE_MISMATCH'
                    selection[u]=selected[0]['path_signature']
            result=dict(UB=ub,point=record(raw),replay=record(replay),stage=spec['stage'],method=spec['method'],family=spec['family'],candidate_id=spec['candidate_id'],
                Native_capture_seconds=item['Native_capture_seconds'],cumulative_Native_at_FULL_validation=state['Native_used'],controller_wall_at_FULL_validation=item['controller_wall_at_FULL_validation'],
                actual_route=paths,**meta)
            if joint:result['selected_lambda_path_signatures']=selection
            state['events'].append(result)
            if joint and ub<state['BEST_JOINT_FEASIBLE_UB']['UB']-1e-8:state['BEST_JOINT_FEASIBLE_UB']=result
            if it['best'] is None or ub<it['best']['UB']-1e-8:it['best']=result
            old=state['family_best'].get(spec['family'])
            if old is None or ub<old['UB']-1e-8:state['family_best'][spec['family']]=result
            if result['moves']>0 and ub<state['BEST_MOVING_FEASIBLE_UB']['UB']-1e-8:state['BEST_MOVING_FEASIBLE_UB']=result;state['moving_trajectory'].append(result)
            if ub<state['BEST_GLOBAL_UB']['UB']-1e-8:
                state['BEST_GLOBAL_UB']=result;state['trajectory'].append(result);state['improvements'].append(result)
                print(json.dumps(dict(FULL_verified_global_improvement=ub,family=spec['family'],Native=result['Native_capture_seconds'])),flush=True)
            persist()
        it.update(Status=call.get('Status'),NodeCount=call.get('NodeCount'),restricted_MIPGap=call.get('MIPGap'),root_completed=call.get('root_completed_Native_seconds') is not None)
        (state['joint_results'] if joint else state['ablation_results']).append(it)
        persist();return it['best']
    pools=None;pool_size=policy['initial_pool_size'];joint_ordinal=100
    def joint_call():
        nonlocal pools,pool_size,joint_ordinal
        if remaining()<8:return False
        center=state['BEST_GLOBAL_UB'];case=v.load_native_case();x=v.load_point(center['point']['path'])
        root_incomplete=bool(state['joint_results']) and state['joint_results'][-1]['Status']==9 and not state['joint_results'][-1]['root_completed']
        if pools is None:cap=policy['initial_Joint_cap'];new=select_pools(case,pool,x,pool_size,variant=6)
        elif root_incomplete:
            cap=policy['initial_Joint_cap'];new=select_pools(case,pool,x,pool_size,variant=joint_ordinal)
        else:
            pool_size=min(policy['max_pool_size'],pool_size+policy['expand_each_vehicle_by'])
            cap=policy['joint_cap'];new=select_pools(case,pool,x,pool_size,previous=pools)
        joint_ordinal+=1;label=f'JOINT_POOL_{joint_ordinal:03d}'
        if pools is not None and pool_signature(new)==pool_signature(pools):
            new=select_pools(case,pool,x,pool_size,variant=joint_ordinal+1)
        spec,lo,hi,A,rhs=build_spec(case,x,center['replay']['path'],new,label,cap);spec['center_raw']=center['point']
        spec['pool_adaptation']=dict(root_incomplete=root_incomplete,variant=joint_ordinal,size=pool_size,
            all_four_pools_changed_or_current_winner_preserved=True,previous_pool_signature=None if pools is None else pool_signature(pools))
        del case,x,lo,hi,A;gc.collect();pools=new
        oldUB=state['BEST_GLOBAL_UB']['UB'];result=perform(spec,cap,center)
        state['switches'].append(dict(action='JOINT_DONE_CONTINUE_GLOBAL_POOL_SEARCH',joint_ordinal=joint_ordinal,
            global_gain=oldUB-state['BEST_GLOBAL_UB']['UB'],next_policy='all_four_pool_diversification',remaining=remaining()))
        persist();return True
    def ablation(family):
        candidate=choose(pool,family,seen_routes,used_keys)
        if candidate is None:return False
        used=sum(c['Native_Runtime'] for c in state['calls'] if c.get('stage')=='ABLATION')
        if used>=policy['ablation_stage_cap']-3 or remaining()<35:return False
        seen_routes.add(candidate['signature']);used_keys.add(str(candidate['diversity_key']))
        candidate=dict(candidate,stage='ABLATION');case=v.load_native_case();spec=route_spec(case,candidate);del case;gc.collect()
        perform(spec,min(policy['ablation_call_cap'],policy['ablation_stage_cap']-used-3));return True
    def dual():
        assert state['new_LB_Optimize_calls']==0;seconds=min(175.,1800-state['Native_used']-8.)
        assert seconds>0;rc,wall=invoke(['--seconds',seconds],DOCS/'DUAL_WORKER.log','tools.global_local_multistart1800.lb_v2')
        path=DOCS/'dual/NATIVE_CALL.json';assert path.exists();call=read(path);assert call['entered_native'] and call['Native_Runtime'] is not None
        before=state['Native_used'];state['Native_used']+=call['Native_Runtime'];state['new_LB_Optimize_calls']=1
        call.update(receipt=record(path),family='DUAL',worker_exit=rc,worker_wall_seconds=wall,cumulative_Native_before=before,cumulative_Native_after=state['Native_used']);state['calls'].append(call)
        cert=read(DOCS/'FAST_LB_INDEPENDENT_CERTIFICATE.json')
        if cert['PASS']:state['Global_LB']=max(GLOBAL_LB,cert['Global_LB'])
        persist();assert state['Native_used']<=1800
        if call.get('error') or call['callback_errors'] or call.get('callback_stop_reason'):raise ValueError('DUAL_RESOURCE_NUMERIC_FAIL_CLOSED')
    try:
        # The main result is4-MESS joint. Solo/pairs only initialize/compare.
        joint_call()
        assert state['all_four_joint_calls']>=1,'JOINT_INTEGRITY_BEFORE_DUAL_REQUIRED'
        for family in policy['ablation_families']:
            if remaining()<8:break
            ablation(family);joint_call()
        dual()
        empty=0
        while remaining()>10:
            previous_calls=state['all_four_joint_calls'];joint_call()
            empty=empty+1 if state['all_four_joint_calls']==previous_calls else 0
            if empty>=2:
                if epoch>=3:state['stopped_reason']='ADAPTIVE_GENERATOR_NO_UNSEEN_JOINT_POOL';break
                epoch+=1;case=v.load_native_case();x=v.load_point(state['BEST_GLOBAL_UB']['point']['path'])
                import tools.minimax_beam1800.grid as mm
                mm.DOCS=DOCS;context,receipt=mm.refresh(case,x,epoch);newpool,diversity=generate(case,x,context,epoch)
                pool=pool+newpool;write(DOCS/f'adaptive/EPOCH_{epoch}.json',dict(diversity=diversity,scoring_center=state['BEST_GLOBAL_UB'],new_Optimize_calls=0))
                del case,x;gc.collect();empty=0
        if state['stopped_reason'] is None:state['stopped_reason']='NATIVE_BUDGET_END_WITH_RETURN_RESERVE'
    except Exception as e:state.update(stopped_reason='SOURCE_RESOURCE_OR_VALIDITY_FAIL_CLOSED',error=repr(e),traceback=traceback.format_exc());print(state['traceback'],flush=True)
    finally:
        persist();write(DOCS/'FINAL_STATE.json',state);print(json.dumps(dict(Native=state['Native_used'],UB=state['BEST_GLOBAL_UB']['UB'],LB=state['Global_LB'],gap=state['Global_gap'],stop=state['stopped_reason'])),flush=True)

if __name__=='__main__':run()
