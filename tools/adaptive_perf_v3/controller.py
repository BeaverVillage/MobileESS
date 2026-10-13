"""Same-budget continuation after a verified idle-worker version handoff."""
import subprocess,statistics,re
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.cache import get,fast_save
from tools.adaptive_perf_v3.hybrid import save as ef_save,structure
from tools.adaptive_perf_v3.feedback import generate

def invoke(args,log):
    began=time.perf_counter()
    with log.open('w',encoding='utf-8') as stream:
        rc=subprocess.run([sys.executable,'-X','utf8','-m','tools.adaptive_perf_v3.worker',*map(str,args)],cwd=DEVELOPMENT_ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
    return rc,time.perf_counter()-began

def main():
    configure();full_guard();assert read(DOCS/'NATIVE0_GATE.json')['PASS'] and not (DOCS/'RUN_STARTED.json').exists()
    previous_state=read(DOCS/'MIGRATION_STATE.json');state=dict(previous_state);state.update(PASS=False,version='V3_PERFORMANCE_AND_LOOKAHEAD',
        previous_version_calls=previous_state['new_calls'],new_calls=[],v3_comparisons=[],v3_iterations=[],v3_timings=[],stopped_reason=None,backend='DIRECT')
    began=time.perf_counter();latest=state['events'][-1];seen=set();native_seen=set()
    for call in state['calls']:
        s=read(call['model']['path']);signature=s['pool_signature']
        for form in ('JOINT','DIRECT'):seen.add(form+'|'+signature)
        native_seen.add(call.get('formulation','DIRECT')+'|'+signature)
    write(DOCS/'RUN_STARTED.json',dict(timestamp=r.timestamp(),Native_offset=state['Native_used'],same_limit=1800,budget_reset=False,source=record(DOCS/'EXECUTED_SOURCE_HASHES.json')))
    index=0
    def persist():
        state['v3_wall_seconds']=time.perf_counter()-began;state['Global_Gap_percent']=100*(state['BEST_GLOBAL_UB']['UB']-GLOBAL_LB)/state['BEST_GLOBAL_UB']['UB']
        write(DOCS/'LIVE_STATE.json',state);write(DOCS/'NATIVE_RUNTIME_LEDGER.json',dict(Native_used=state['Native_used'],Native_limit=1800,
            inherited_offset=previous_state['Native_used'],budget_reset=False,calls=state['calls'],new_calls=state['new_calls']))
    try:
        for epoch in range(1001,1101):
            if 1800-state['Native_used']<15:state['stopped_reason']='NATIVE_BUDGET_WITH_RETURN_RESERVE';break
            if (DOCS/'CANCEL_REQUEST.json').exists():state['stopped_reason']='USER_CANCEL';break
            timer=Timing()
            if epoch==1001:
                folder=DOCS/'packages/INITIAL_1001';signature=read(folder/'DIRECT/SPEC.json')['pool_signature']
                assert 'DIRECT|'+signature not in native_seen,'INITIAL_POOL_ALREADY_SOLVED_DURING_DEVELOPMENT'
            else:
                with timer.stage('Source_Case_load'):case=v.load_native_case();point=v.load_point(latest['point']['path'])
                cache=get(case,timer);pools,signature=generate(case,point,latest['replay']['path'],epoch,seen,timer)
                if pools is None:state['stopped_reason']='VALID_ADAPTIVE_CANDIDATE_SIGNATURES_EXHAUSTED';break
                folder=DOCS/'packages'/f'POOL_{epoch}'
                fast_save(case,point,latest['replay']['path'],pools,f'POOL_{epoch}',folder/'DIRECT',cache,timer)
                if epoch<=1002 or epoch%5==0:ef_save(case,point,latest['replay']['path'],pools,f'POOL_{epoch}',folder/'EF',cache,timer)
                if state['backend']=='EF' and not (folder/'EF/SPEC.json').exists():ef_save(case,point,latest['replay']['path'],pools,f'POOL_{epoch}',folder/'EF',cache,timer)
                del case,point,cache;gc.collect()
            state['pool_count']+=1;forms=['DIRECT','EF'] if (folder/'EF/SPEC.json').exists() else [state['backend']]
            # Matched caps for each new-pool comparison; never reset Native.
            requested=min(140.,(1800-state['Native_used']-10)/len(forms));results={}
            for form in forms:
                if 1800-state['Native_used']<15:break
                specpath=folder/form/'SPEC.json';spec=read(specpath);identity=form+'|'+signature
                assert identity not in native_seen;native_seen.add(identity);index+=1
                out=DOCS/'calls'/f'{index:03d}_E{epoch}_{form}';cap=min(requested,1800-state['Native_used']-10)
                print(json.dumps(dict(dispatch=form,epoch=epoch,cap=cap,Native_before=state['Native_used'],pool_signature=signature)),flush=True)
                rc,wall=invoke(['--mode','native','--spec',specpath,'--output',out,'--seconds',cap],DOCS/f'WORKER_{index:03d}.log')
                q=read(out/'NATIVE_CALL.json');assert q['entered_native'] and q['Native_Runtime'] is not None
                before=state['Native_used'];state['Native_used']+=q['Native_Runtime']
                call=dict(receipt=record(out/'NATIVE_CALL.json'),model=record(specpath),formulation=form,epoch=epoch,Native_Runtime=q['Native_Runtime'],
                    Native_before=before,Native_after=state['Native_used'],worker_wall=wall)
                state['calls'].append(call);state['new_calls'].append(call);persist()
                assert state['Native_used']<=1800 and rc==0 and not q['callback_errors'] and q['Status'] not in (3,4,5,12)
                log=(out/'NATIVE_GUROBI.log').read_text(encoding='utf-8',errors='replace');ps=re.findall(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
                pt=re.findall(r'Presolve time: ([\d.]+)s',log);binv=re.findall(r'Variable types: .*?\((\d+) binary\)',log)
                item=dict(formulation=form,epoch=epoch,Native_Runtime=q['Native_Runtime'],presolve_seconds=float(pt[-1]) if pt else None,
                    Presolved=ps[-1] if ps else None,presolved_binary=int(binv[-1]) if binv else None,root_completed_Native=q.get('root_completed_Native_seconds'),
                    NodeCount=q['NodeCount'],Status=q['Status'],ObjVal=q['ObjVal'],restricted_ObjBound=q['ObjBound'],FULL_PASS=0)
                for j,capture in enumerate(q['captures']):
                    replay=out/f'FULL_REPLAY_{j:03d}.json'
                    with timer.stage('Original_FULL_Replay'):
                        vr,vwall=invoke(['--mode','validate','--point',capture['dense_lift']['path'],'--objective',repr(capture['Solver_ObjVal']),'--output',replay],out/f'REPLAY_{j:03d}.log')
                    cert=read(replay);passed=vr==0 and cert['PASS'] and capture['strict_literal_lambda']
                    val=dict(raw=capture['dense_lift'],native_raw=capture['native_raw'],replay=record(replay),PASS=passed,formulation=form,epoch=epoch,
                        validation_wall=vwall,Native_discovery=before+capture['Native_discovery'])
                    state['validations'].append(val);assert passed,'ORIGINAL_FULL_OR_LITERAL_ROUTE_REJECTION'
                    with timer.stage('selected_original_DAG_and_lambda_restore'):
                        from tools.global_local_multistart1800.dag import Graph
                        case=v.load_case(native=False);point=v.load_point(capture['dense_lift']['path']);paths=paths_of(case,point);lam=np.asarray(capture['lambda_values'])
                        for u in spec['pools']:assert [a['path'] for a,value in zip(spec['lambda_axis'],lam) if a['unit']==u and value==1.]==[paths[u]]
                        meta=Graph(case).metadata(paths);latest=dict(UB=cert['Global_UB'],point=capture['dense_lift'],replay=record(replay),paths=paths,**meta,
                            Native_discovery=val['Native_discovery'],Native_at_validation=state['Native_used'],formulation=form,epoch=epoch)
                        del case,point;gc.collect()
                    val.update(UB=latest['UB'],paths=paths,**meta);state['events'].append(latest);item['FULL_PASS']+=1
                    if latest['UB']<state['BEST_GLOBAL_UB']['UB']-1e-8:
                        state['BEST_GLOBAL_UB']=latest;state['trajectory'].append(dict(Native=val['Native_discovery'],UB=latest['UB'],wall=state['v3_wall_seconds']))
                        print(json.dumps(dict(FULL_IMPROVEMENT=latest['UB'],Native=val['Native_discovery'])),flush=True)
                    if meta['moves'] and latest['UB']<state['BEST_MOVING_FEASIBLE_UB']['UB']-1e-8:state['BEST_MOVING_FEASIBLE_UB']=latest
                state['iterations'].append(item);state['v3_iterations'].append(item);results[form]=item
                timer.parts['Worker_model_Readback_Optimize_and_IO']=timer.parts.get('Worker_model_Readback_Optimize_and_IO',0.)+wall;persist()
            for f in ('JOINT','DIRECT'):seen.add(f+'|'+signature)
            if len(results)==2:state['v3_comparisons'].append(dict(epoch=epoch,pool_signature=signature,**results))
            if len(state['v3_comparisons'])>=2:
                medians={f:statistics.median(a[f]['Native_Runtime'] for a in state['v3_comparisons'][-4:]) for f in ('DIRECT','EF')}
                state['backend']=min(medians,key=medians.get)
            state['v3_timings'].append(dict(epoch=epoch,**timer.receipt()));persist()
        else:state['stopped_reason']='CONFIGURED_POOL_EPOCH_SAFETY_LIMIT'
        state['PASS']=True
    except Exception as exc:
        import traceback
        state.update(PASS=False,stopped_reason='RESOURCE_NUMERIC_OR_SOURCE_FAIL_CLOSED',error=repr(exc),traceback=traceback.format_exc())
    finally:persist();write(DOCS/'FINAL_STATE.json',state)
    print(json.dumps(dict(PASS=state['PASS'],Native_used=state['Native_used'],UB=state['BEST_GLOBAL_UB']['UB'],stop=state['stopped_reason'])),flush=True)
    return 0 if state['PASS'] else 2
if __name__=='__main__':raise SystemExit(main())
