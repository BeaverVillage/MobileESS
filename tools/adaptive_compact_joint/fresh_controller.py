"""New run from zero, bounded pilot, then measured adaptive feedback epochs."""
import subprocess,sys,time,gc
from tools.adaptive_compact_joint.fresh_adapter import *
from tools.adaptive_compact_joint.direct import save
from tools.adaptive_compact_joint.fresh_feedback import generate
from tools.global_local_multistart1800.dag import Graph

def invoke(args,log):
    began=time.perf_counter()
    with log.open('w',encoding='utf-8') as stream:rc=subprocess.run([sys.executable,'-X','utf8','-m','tools.adaptive_compact_joint.fresh_worker',*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
    return rc,time.perf_counter()-began

def main():
    guard();assert read(DOCS/'NATIVE0_GATE.json')['PASS'];assert not (DOCS/'RUN_STARTED.json').exists(),'NEW_RUN_ALREADY_STARTED'
    policy=read(DOCS/'EXECUTION_POLICY.json');began=time.perf_counter()
    initial=dict(UB=INITIAL_UB,point=record(ROOT/RAW_REL),replay=record(DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json'),moves=3)
    state=dict(PASS=False,fresh_Native_used=0.,fresh_Native_limit=1800,Native_calls=[],validations=[],iterations=[],
        BEST_GLOBAL_UB=initial,BEST_MOVING_FEASIBLE_UB=initial,Global_LB=GLOBAL_LB,trajectory=[dict(Native=0.,UB=INITIAL_UB)],
        stop_reason=None,ACTUAL='ACTUAL_NOT_RUN',historical_Native=read(DOCS/'FRESH_EXECUTION_AUTHORIZATION.json')['historical_total_Native'])
    write(DOCS/'RUN_STARTED.json',dict(Native_limit=1800,Native_initial=0.,new_execution=True,authorization=record(DOCS/'FRESH_EXECUTION_AUTHORIZATION.json'),timestamp=r.timestamp()))
    seen=set();index=0;last_full=initial
    def persist():
        state['wall_seconds']=time.perf_counter()-began
        state['Global_Gap_percent']=100*(state['BEST_GLOBAL_UB']['UB']-GLOBAL_LB)/state['BEST_GLOBAL_UB']['UB']
        write(DOCS/'LIVE_STATE.json',state);write(DOCS/'NATIVE_RUNTIME_LEDGER.json',dict(fresh_Native_used=state['fresh_Native_used'],fresh_limit=1800,
            historical_separate_Native=state['historical_Native'],all_sessions_actual_Native=state['historical_Native']+state['fresh_Native_used'],calls=state['Native_calls'],prior_ledger_resets=0))
    def perform(spec_path,requested,pilot=False):
        nonlocal index,last_full
        guard()
        if (DOCS/'CANCEL_REQUEST.json').exists():state['stop_reason']='USER_CANCEL';return None
        cap=min(requested,1800-state['fresh_Native_used']-10,240-state['fresh_Native_used']-5 if pilot else 175)
        if cap<5:return None
        spec=read(spec_path)
        if spec['pool_signature'] in seen:return None
        seen.add(spec['pool_signature']);index+=1;out=DOCS/'calls'/f'{index:03d}_{spec["candidate_id"]}'
        print(json.dumps(dict(dispatch=spec['candidate_id'],seconds=cap,fresh_Native_before=state['fresh_Native_used'],binary=spec['compact_binary'],columns=spec['compact_columns'])),flush=True)
        rc,wall=invoke(['--mode','native','--spec',spec_path,'--seconds',cap,'--output',out],DOCS/f'WORKER_{index:03d}.log')
        q=read(out/'NATIVE_CALL.json');assert q['entered_native'] and q['Native_Runtime'] is not None,'UNKNOWN_RUNTIME_FAIL_CLOSED'
        before=state['fresh_Native_used'];state['fresh_Native_used']+=q['Native_Runtime']
        state['Native_calls'].append(dict(receipt=record(out/'NATIVE_CALL.json'),Native_Runtime=q['Native_Runtime'],Native_before=before,Native_after=state['fresh_Native_used'],model=record(spec_path),worker_wall=wall))
        persist();assert state['fresh_Native_used']<=1800 and rc==0 and not q['callback_errors']
        iteration=dict(label=spec['candidate_id'],spec=record(spec_path),Native_Runtime=q['Native_Runtime'],NodeCount=q['NodeCount'],Status=q['Status'],ObjVal=q['ObjVal'],ObjBound=q['ObjBound'],restricted_gap=q['MIPGap'],accepted=0)
        for i,capture in enumerate(q['captures']):
            replay=out/f'FULL_REPLAY_{i:03d}.json'
            vr,vwall=invoke(['--mode','validate','--point',capture['dense_lift']['path'],'--objective',repr(capture['Solver_ObjVal']),'--output',replay],out/f'REPLAY_{i:03d}.log')
            cert=read(replay);item=dict(dense_lift=capture['dense_lift'],native_raw=capture['native_raw'],replay=record(replay),FULL_PASS=vr==0 and cert['PASS'] and capture['strict_literal_lambda'],lambda_values=capture['lambda_values'],validation_wall=vwall)
            if item['FULL_PASS']:
                selection=np.asarray(capture['lambda_values']);case=v.load_native_case();point=v.load_point(capture['dense_lift']['path']);paths=paths_of(case,point)
                for u in spec['pools']:
                    selected=[a for a,value in zip(spec['lambda_axis'],selection) if a['unit']==u and value==1.]
                    assert len(selected)==1 and selected[0]['path']==paths[u]
                meta=Graph(case).metadata(paths);last_full=dict(UB=cert['Global_UB'],point=capture['dense_lift'],replay=record(replay),paths=paths,**meta)
                item.update(UB=last_full['UB'],paths=paths,**meta);iteration['accepted']+=1
                if last_full['UB']<state['BEST_GLOBAL_UB']['UB']-1e-8:
                    state['BEST_GLOBAL_UB']=last_full;state['trajectory'].append(dict(Native=before+capture['Native_discovery'],UB=last_full['UB']))
                if meta['moves'] and last_full['UB']<state['BEST_MOVING_FEASIBLE_UB']['UB']-1e-8:state['BEST_MOVING_FEASIBLE_UB']=last_full
                del case,point;gc.collect()
            state['validations'].append(item);persist()
        state['iterations'].append(iteration);persist();return iteration
    baseline=None
    for descriptor in policy['initial_pilot']:
        result=perform(DOCS/'packages'/descriptor['label']/'SPEC.json',descriptor['seconds'],True)
        if descriptor['label']=='SAME_POOL':baseline=result
    old=read(OLD_DOCS/'v2/calls/001_JOINT_POOL_101/native/NATIVE_CALL.json')
    compute_gain=baseline is not None and baseline['accepted']>0 and baseline['Status']==2 and baseline['Native_Runtime']<=old['Native_Runtime']*policy['compute_gain_ratio']
    ub_gain=state['BEST_GLOBAL_UB']['UB']<INITIAL_UB-DELTA
    decision=dict(PASS=True,verified_UB_gain=ub_gain,observed_compute_gain=compute_gain,new_runtime=None if baseline is None else baseline['Native_Runtime'],old_same_pool_Runtime=old['Native_Runtime'],
        one_case_observation_not_general_speedup=True,allow_feedback_search=compute_gain or ub_gain,pilot_fresh_Native=state['fresh_Native_used'])
    write(DOCS/'PILOT_CONTINUATION_DECISION.json',decision)
    if compute_gain or ub_gain:
        no_gain=0
        for epoch in range(1,policy['max_feedback_rounds_without_UB_gain']+1):
            if state['fresh_Native_used']>=1790 or (DOCS/'CANCEL_REQUEST.json').exists():break
            case=v.load_native_case();point=v.load_point(last_full['point']['path'])
            pools,signature=generate(case,point,last_full['replay']['path'],epoch,seen)
            if signature in seen:
                del case,point;gc.collect();continue
            folder=DOCS/'packages'/f'FEEDBACK_{epoch:02d}';save(case,point,last_full['replay']['path'],pools,f'FEEDBACK_{epoch:02d}',folder)
            del case,point;gc.collect();old_best=state['BEST_GLOBAL_UB']['UB']
            perform(folder/'SPEC.json',policy['feedback_default_Native_cap'])
            no_gain=0 if state['BEST_GLOBAL_UB']['UB']<old_best-DELTA else no_gain+1
            if no_gain>=policy['max_feedback_rounds_without_UB_gain']:state['stop_reason']='NO_UB_PROGRESS_AFTER_BOUNDED_FEEDBACK_ROUNDS';break
    else:state['stop_reason']='PILOT_NO_VERIFIED_UB_OR_COMPUTE_GAIN_NO_BUDGET_AUTOCONSUMPTION'
    state['PASS']=True;state['stop_reason']=state['stop_reason'] or 'BOUNDED_FRESH_FEEDBACK_EXECUTION_COMPLETE';persist();write(DOCS/'FINAL_STATE.json',state)
    print(json.dumps(dict(PASS=True,fresh_Native_used=state['fresh_Native_used'],BEST_GLOBAL_UB=state['BEST_GLOBAL_UB']['UB'],stop=state['stop_reason'])))

if __name__=='__main__':main()
