"""One sequential warm canary, adaptive center, nonrepeating route neighborhoods."""
from collections import Counter
from pathlib import Path
import gc,math,subprocess,sys,time,traceback,argparse,numpy as np
from tools.route_centered_lb1800.adapter import *
from tools.route_centered_lb1800.dag import Graph
from tools.route_centered_lb1800.neighborhoods import priorities,make

def invoke(args,log,module='tools.route_centered_lb1800.worker'):
    begin=time.perf_counter()
    with Path(log).open('w',encoding='utf-8') as stream:
        process=subprocess.run([sys.executable,'-X','utf8','-m',module,*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    return process.returncode,time.perf_counter()-begin

def run():
    assert not (DOCS/'RUN_STARTED.json').exists(),'NO_NATIVE_BUDGET_RESET_OR_IMPLICIT_RESTART';guard()
    began=time.perf_counter();write(DOCS/'RUN_STARTED.json',dict(UTC=r.timestamp(),Native_limit=1800,Warm_start=True))
    policy=read(DOCS/'PREREGISTERED_POLICY.json');warm=read(DOCS/'PR219_WARM_START_CERTIFICATE.json')
    initial=dict(UB=INITIAL_UB,point=record(ROOT/RAW_REL),replay=record(DOCS/'PR219_FRESH_ORIGINAL_FULL_REPLAY.json'),
        moves=3,method='INHERITED_PR219',stage='INHERITED_PR219',Native_capture_seconds=0.,inherited_not_new_discovery=True)
    state=dict(Native_used=0.,calls=[],iterations=[],events=[],trajectory=[initial],BEST_GLOBAL_UB=initial,BEST_MOVING_FEASIBLE_UB=initial,
        Global_LB=GLOBAL_LB,Global_gap=(INITIAL_UB-GLOBAL_LB)/INITIAL_UB,stage_best={},improvements=[],center_epochs=[],skips=[],
        stopped_reason=None,ACTUAL='ACTUAL_NOT_RUN',old_PR219_Native=1795.0249993801117,new_LB_Optimize_calls=0,
        unrestricted_FULL_calls=0,Cold_N1_U4_calls=0,source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA)
    seen=set();index=0;current_priority=read(DOCS/'INITIAL_CRITICAL_PRIORITY.json');last_center=initial['point']['sha256'];epoch=0
    def persist():
        state['controller_wall_seconds']=time.perf_counter()-began
        state['Global_gap']=(state['BEST_GLOBAL_UB']['UB']-GLOBAL_LB)/state['BEST_GLOBAL_UB']['UB']
        write(DOCS/'LIVE_STATE.json',state);write(DOCS/'NATIVE_RUNTIME_LEDGER.json',dict(Native_used=state['Native_used'],Native_limit=1800,
            calls=state['calls'],budget_reset_count=0,only_new_Optimize_calls_included=True,old_PR219_Native_separate=1795.0249993801117))
    def stage_used(stage):return sum(c['Native_Runtime'] for c in state['calls'] if c['stage']==stage)
    def refresh_center():
        nonlocal last_center,current_priority,epoch
        best=state['BEST_GLOBAL_UB']
        if best['point']['sha256']==last_center:return
        guard();case=v.load_native_case();x=v.load_point(best['point']['path']);context,receipt=g.refresh(case,x)
        sites,partners,ranks=priorities(case,x,context)
        current_priority=dict(context=context,receipt=receipt,sites=sites,partners=partners,signed_ranking=ranks)
        write(DOCS/f'centers/epoch{epoch:02d}/CRITICAL_PRIORITY.json',current_priority)
        state['center_epochs'].append(dict(epoch=epoch,center=best,critical_grid=receipt));epoch+=1;last_center=best['point']['sha256']
        del case,x;gc.collect();persist()
    def perform(spec,cap,center=None):
        nonlocal index
        guard();remaining=1800-state['Native_used']-8.
        if remaining<=2:return False
        case=v.load_native_case();x=None if center is None else v.load_point(center['point']['path'])
        lo,hi,hh,cc,rhs,_=restriction(case,x,spec);sig=signature(lo,hi,hh,cc,rhs)
        if sig in seen:
            state['skips'].append(dict(label=spec['candidate_id'],reason='EXACT_MODEL_SIGNATURE_ALREADY_EXECUTED',signature=sig));persist();return False
        assert spec['method']=='ROUTE_FIXED' or spec['mathematical_model_signature']==sig
        seen.add(sig);spec['executed_mathematical_model_signature']=sig
        proof=audit(case,x,spec,lo,hi);assert proof['PASS']
        index+=1;folder=DOCS/f'calls/{index:03d}_{spec["candidate_id"]}';folder.mkdir(parents=True,exist_ok=False)
        write(folder/'SPEC.json',spec);write(folder/'PRE_NATIVE0.json',proof)
        del case,x,lo,hi,hh,cc;gc.collect()
        seconds=min(float(cap),remaining,300.)
        command=['--mode','native','--method',spec['method'],'--spec',folder/'SPEC.json','--output',folder/'native','--seconds',seconds]
        if center is not None:command+=['--center',center['point']['path']]
        print(json.dumps(dict(evaluating=spec['candidate_id'],stage=spec['stage'],seconds=seconds,Native=state['Native_used'],
            radius=spec.get('hamming_radius'),free_binary=spec.get('actual_free_binary'))),flush=True)
        rc,wall=invoke(command,folder/'WORKER.log');path=folder/'native/NATIVE_CALL.json';assert path.exists(),'NATIVE_RUNTIME_RECEIPT_MISSING'
        call=read(path);assert call['entered_native'],'PRE_NATIVE_GATE_REJECTION'
        runtime=call['Native_Runtime'];assert runtime is not None and math.isfinite(runtime) and runtime>=0
        before=state['Native_used'];state['Native_used']+=runtime
        call.update(receipt=record(path),worker_exit=rc,worker_wall_seconds=wall,cumulative_Native_before=before,cumulative_Native_after=state['Native_used'])
        state['calls'].append(call);persist();assert state['Native_used']<=1800,'NATIVE_BUDGET_CEILING'
        it=dict(stage=spec['stage'],method=spec['method'],candidate_id=spec['candidate_id'],specification=record(folder/'SPEC.json'),
            signature=sig,call=record(path),validated=[],verified_UB=None,verified_moves=None,result_states=[],center=center)
        state['iterations'].append(it);persist()
        if call.get('error') or call['callback_errors'] or call.get('callback_stop_reason') in ('RESOURCE_OR_SOURCE_CALLBACK_GATE','CALLBACK_ERROR'):
            raise ValueError('NATIVE_SOURCE_RESOURCE_NUMERICAL_ERROR_STOP')
        for k,capdata in enumerate(call['captures']):
            raw=Path(capdata['file']['path']);replay=folder/f'REPLAY_{k:03d}.json'
            code,vwall=invoke(['--mode','validate','--point',raw,'--solver-objective',capdata['Solver_ObjVal'],'--output',replay],folder/f'VERIFY_{k:03d}.log')
            cert=read(replay) if replay.exists() else dict(PASS=False)
            item=dict(raw=record(raw),replay=record(replay) if replay.exists() else None,PASS=code==0 and cert.get('PASS',False),
                validation_wall_seconds=vwall,Native_capture_seconds=before+capdata['discovered_Native_seconds'],
                cumulative_Native_at_FULL_validation=state['Native_used'],controller_wall_at_FULL_validation=time.perf_counter()-began)
            it['validated'].append(item)
            if not item['PASS']:it['result_states'].append('ORIGINAL_FULL_REPLAY_FAIL');continue
            ub=cert['Global_UB'];assert ub>=GLOBAL_LB-1e-8
            # Count the actual selected Original arcs. Local MILP chooses the
            # new path itself, so never copy a witness's MOVE count as result.
            case=v.load_case();rawx=v.load_point(raw);paths=paths_of(case,rawx);graph=Graph(case);metadata=graph.metadata(paths)
            del case,rawx;gc.collect()
            result=dict(UB=ub,point=record(raw),replay=record(replay),moves=metadata['moves'],actual_route=paths,
                travel_energy_kWh=metadata['travel_energy_kWh'],actual_moves=metadata['actual_moves'],stage=spec['stage'],method=spec['method'],
                candidate_id=spec['candidate_id'],Native_capture_seconds=item['Native_capture_seconds'],
                cumulative_Native_at_FULL_validation=state['Native_used'],controller_wall_at_FULL_validation=item['controller_wall_at_FULL_validation'],
                inherited_seed_vector=capdata['vector_sha256']==VECTOR_SHA)
            state['events'].append(result);it['verified_UB']=ub if it['verified_UB'] is None else min(ub,it['verified_UB'])
            it['verified_moves']=metadata['moves'] if ub==it['verified_UB'] else it['verified_moves']
            previous=state['stage_best'].get(spec['stage'])
            if previous is None or ub<previous['UB']-1e-8:state['stage_best'][spec['stage']]=result
            if result['moves']>0 and ub<state['BEST_MOVING_FEASIBLE_UB']['UB']-1e-8:state['BEST_MOVING_FEASIBLE_UB']=result
            if ub<state['BEST_GLOBAL_UB']['UB']-1e-8:
                state['BEST_GLOBAL_UB']=result;state['trajectory'].append(result);state['improvements'].append(result)
                print(json.dumps(dict(verified_improvement=ub,moves=result['moves'],Native_capture=result['Native_capture_seconds'],Native_validation=state['Native_used'])),flush=True)
            persist()
        status=call.get('Status')
        label={2:'RESTRICTED_OPTIMAL',3:'RESTRICTED_INFEASIBLE',9:'TIME_LIMIT',12:'NUMERIC',11:'USER_STOP',17:'MEMORY_LIMIT'}.get(status,'STATUS_'+str(status))
        it['result_states'].append(label)
        if it['verified_UB'] is not None:it['result_states'].append('ORIGINAL_FULL_PASS')
        else:it['result_states'].append('NO_ORIGINAL_FULL_FEASIBLE')
        persist();return True
    try:
        # A0 is authority only. These six routes reconstruct complete DAG paths
        # and never pass the incompatible original center as a MIP Start.
        for candidate in read(DOCS/'ABLATION_CANDIDATES.json')['candidates']:
            remaining=250-stage_used('ABLATION')-3.
            if remaining<=2:break
            case=v.load_native_case();spec=route_spec(case,candidate);del case;gc.collect()
            perform(spec,min(40,remaining));refresh_center()
        primary=policy['primary_descriptors']
        for descriptor in primary:
            if 1800-state['Native_used']<=10:break
            if state['Global_gap']<=.03:state['stopped_reason']='CERTIFIED_GLOBAL_GAP_3PCT';break
            refresh_center();best=state['BEST_GLOBAL_UB'];case=v.load_native_case();x=v.load_point(best['point']['path'])
            spec=make(case,x,best['replay']['path'],descriptor,current_priority['sites']);del case,x;gc.collect()
            perform(spec,descriptor['cap'],best)
        # Beam assistance is permitted only after all R1..R4 were attempted
        # with no new improvement across the primary Local Branching stages.
        primary_gain=any(e['stage'] in ('R1','R2','R3','R4') for e in state['improvements'])
        for descriptor in policy['reserve_descriptors']:
            if state['stopped_reason'] or 1800-state['Native_used']<=10:break
            refresh_center();best=state['BEST_GLOBAL_UB'];case=v.load_native_case();x=v.load_point(best['point']['path'])
            extras=[]
            if not primary_gain:
                from tools.minimax_beam1800.grid import refresh as beam_grid
                from tools.minimax_beam1800.routes import generate
                # Relocation is already confined to this new process. Old
                # source modules and existing PR219 candidate evidence stay intact.
                context,gpath=beam_grid(case,x,100+descriptor['beam_ordinal'])
                queue,search=generate(case,x,context,100+descriptor['beam_ordinal'])
                selected=[c for c in queue if set(c['units'])<=set(descriptor['units'])][:12]
                extras=[c['paths'] for c in selected]
                write(DOCS/f'R5_BEAM_ASSIST_{descriptor["beam_ordinal"]:02d}.json',dict(search=search,selected=selected,
                    route_fixed_restarts=False,center=best,new_Native_calls=0))
            else:
                descriptor=dict(descriptor,label=descriptor['label'].replace('R5_BEAM','ADAPTIVE_POST_GAIN'),stage='ADAPTIVE',beam_used=False)
            spec=make(case,x,best['replay']['path'],descriptor,current_priority['sites'],extras);del case,x;gc.collect()
            perform(spec,descriptor['cap'],best)
        if not state['stopped_reason']:state['stopped_reason']='NATIVE_BUDGET_END' if 1800-state['Native_used']<=10 else 'NONREPEATING_NEIGHBORHOODS_EXHAUSTED'
    except Exception as exc:
        state.update(stopped_reason='SOURCE_RESOURCE_OR_VALIDITY_FAIL_CLOSED',error=repr(exc),traceback=traceback.format_exc());print(state['traceback'],flush=True)
    finally:
        persist();write(DOCS/'FINAL_STATE.json',state);print(json.dumps(dict(Native=state['Native_used'],stopped_reason=state['stopped_reason'],
            UB=state['BEST_GLOBAL_UB']['UB'],Moving=state['BEST_MOVING_FEASIBLE_UB']['UB'],gap=state['Global_gap'])),flush=True)

if __name__=='__main__':run()
