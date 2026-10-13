"""Actual adaptive feedback canary to the same1800s cap, no stagnation stop."""
import subprocess,sys,time,gc,re,statistics
from tools.adaptive_compact_joint.resume_adapter import *
from tools.adaptive_compact_joint.resume_feedback import generate
from tools.adaptive_compact_joint.direct import save
from tools.adaptive_compact_joint.compact import integer_proof
from tools.global_local_multistart1800.joint import build_spec
from tools.global_local_multistart1800.dag import Graph

def invoke(args,log):
    started=time.perf_counter()
    with log.open('w',encoding='utf-8') as stream:rc=subprocess.run([sys.executable,'-X','utf8','-m','tools.adaptive_compact_joint.resume_worker',*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
    return rc,time.perf_counter()-started

def main():
    configure();guard();assert read(DOCS/'NATIVE0_GATE.json')['PASS'] and not (DOCS/'RUN_STARTED.json').exists(),'NO_RESTART_OR_BUDGET_RESET'
    began=time.perf_counter();policy=read(DOCS/'EXECUTION_POLICY.json');prior=read(PILOT_DOCS/'FINAL_STATE.json')
    state=dict(PASS=False,Native_used=prior['fresh_Native_used'],Native_limit=1800,prior_Native=prior['fresh_Native_used'],calls=list(prior['Native_calls']),
        new_calls=[],iterations=[],validations=[],events=[],comparisons=[],backend='JOINT',switches=[],
        BEST_GLOBAL_UB=prior['BEST_GLOBAL_UB'],BEST_MOVING_FEASIBLE_UB=prior['BEST_MOVING_FEASIBLE_UB'],Global_LB=GLOBAL_LB,
        trajectory=list(prior['trajectory']),pool_count=0,stopped_reason=None,ACTUAL='ACTUAL_NOT_RUN')
    accepted=[a for a in prior['validations'] if a['FULL_PASS']];last=accepted[-1]
    last_full=dict(UB=last['UB'],point=last['dense_lift'],replay=last['replay'],paths=last['paths'],moves=last['moves'])
    seen={'DIRECT|'+read(c['model']['path'])['pool_signature'] for c in prior['Native_calls']}
    for p in list(OLD_DOCS.glob('calls/*/SPEC.json'))+list((OLD_DOCS/'v2/calls').glob('*/SPEC.json')):
        s=read(p)
        if s['method']=='FOUR_MESS_JOINT_ROUTE_POOL':seen.add('JOINT|'+s['pool_signature'])
    write(DOCS/'RUN_STARTED.json',dict(timestamp=r.timestamp(),same_fresh_limit=1800,Native_offset=state['Native_used'],budget_reset=False,source=record(DOCS/'EXECUTED_SOURCE_HASHES.json')))
    index=0
    def persist():
        state['wall_seconds']=time.perf_counter()-began;state['Global_Gap_percent']=100*(state['BEST_GLOBAL_UB']['UB']-GLOBAL_LB)/state['BEST_GLOBAL_UB']['UB']
        write(DOCS/'LIVE_STATE.json',state);write(DOCS/'NATIVE_RUNTIME_LEDGER.json',dict(Native_used=state['Native_used'],Native_limit=1800,inherited_pilot=state['prior_Native'],calls=state['calls'],new_calls=state['new_calls'],budget_reset=False))
    def remaining():return 1800-state['Native_used']-10
    def perform(form,specpath,requested,epoch):
        nonlocal index,last_full
        if remaining()<5 or (DOCS/'CANCEL_REQUEST.json').exists():return None
        spec=read(specpath);sig=form+'|'+spec['pool_signature']
        if sig in seen:return None
        seen.add(sig);index+=1;out=DOCS/'calls'/f'{index:03d}_E{epoch:03d}_{form}';cap=min(requested,remaining(),175)
        print(json.dumps(dict(dispatch=form,epoch=epoch,cap=cap,Native_before=state['Native_used'],pool_signature=spec['pool_signature'])),flush=True)
        rc,wall=invoke(['--mode','native','--formulation',form,'--spec',specpath,'--output',out,'--seconds',cap],DOCS/f'WORKER_{index:03d}.log')
        q=read(out/'NATIVE_CALL.json');assert q['entered_native'] and q['Native_Runtime'] is not None,'UNKNOWN_RUNTIME_FAIL_CLOSED'
        before=state['Native_used'];state['Native_used']+=q['Native_Runtime']
        call=dict(receipt=record(out/'NATIVE_CALL.json'),model=record(specpath),formulation=form,epoch=epoch,Native_Runtime=q['Native_Runtime'],Native_before=before,Native_after=state['Native_used'],worker_wall=wall)
        state['calls'].append(call);state['new_calls'].append(call);persist()
        assert state['Native_used']<=1800 and rc==0 and not q['callback_errors']
        log=(out/'NATIVE_GUROBI.log').read_text(encoding='utf-8',errors='replace')
        ps=re.findall(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log);binaries=re.findall(r'Variable types: .*?\((\d+) binary\)',log)
        root=re.findall(r'Root relaxation:.*?, ([\d.]+) seconds',log);pt=re.findall(r'Presolve time: ([\d.]+)s',log)
        item=dict(formulation=form,epoch=epoch,pool_signature=spec['pool_signature'],Native_Runtime=q['Native_Runtime'],model_build_wall=q['model_build_wall_seconds'],
            Presolved=ps[-1] if ps else None,presolved_binary=int(binaries[-1]) if binaries else None,Presolve_seconds=float(pt[-1]) if pt else None,
            root_seconds=float(root[-1]) if root else None,root_completed=q.get('root_completed_Native_seconds'),
            NodeCount=q['NodeCount'],Status=q['Status'],ObjVal=q['ObjVal'],ObjBound=q['ObjBound'],restricted_gap=q['MIPGap'],FULL_PASS=0,
            MIP_Start_loaded='Loaded user MIP start' in log,UB_discovery=[])
        for j,capture in enumerate(q['captures']):
            rep=out/f'FULL_REPLAY_{j:03d}.json'
            vr,vwall=invoke(['--mode','validate','--point',capture['dense_lift']['path'],'--objective',repr(capture['Solver_ObjVal']),'--output',rep],out/f'REPLAY_{j:03d}.log')
            cert=read(rep);val=dict(raw=capture['dense_lift'],native_raw=capture['native_raw'],replay=record(rep),PASS=vr==0 and cert['PASS'] and capture['strict_literal_lambda'],formulation=form,epoch=epoch,validation_wall=vwall,Native_discovery=before+capture['Native_discovery'])
            if val['PASS']:
                case=v.load_native_case();point=v.load_point(capture['dense_lift']['path']);paths=paths_of(case,point);selection=np.asarray(capture['lambda_values'])
                assert np.isin(selection,(0.,1.)).all()
                for u in spec['pools']:
                    chosen=[a for a,lam in zip(spec['lambda_axis'],selection) if a['unit']==u and lam==1.]
                    assert len(chosen)==1 and chosen[0]['path']==paths[u]
                meta=Graph(case).metadata(paths);last_full=dict(UB=cert['Global_UB'],point=capture['dense_lift'],replay=record(rep),paths=paths,**meta,
                    Native_discovery=val['Native_discovery'],Native_at_validation=state['Native_used'],formulation=form,epoch=epoch)
                val.update(UB=last_full['UB'],paths=paths,**meta);item['FULL_PASS']+=1;item['UB_discovery'].append(dict(UB=last_full['UB'],Native=val['Native_discovery']))
                state['events'].append(last_full)
                if last_full['UB']<state['BEST_GLOBAL_UB']['UB']-1e-8:
                    state['BEST_GLOBAL_UB']=last_full;state['trajectory'].append(dict(Native=val['Native_discovery'],UB=last_full['UB']))
                    print(json.dumps(dict(FULL_IMPROVEMENT=last_full['UB'],Native=val['Native_discovery'],epoch=epoch,formulation=form)),flush=True)
                if meta['moves'] and last_full['UB']<state['BEST_MOVING_FEASIBLE_UB']['UB']-1e-8:state['BEST_MOVING_FEASIBLE_UB']=last_full
                del case,point;gc.collect()
            state['validations'].append(val);persist()
        state['iterations'].append(item);persist();return item
    try:
        for epoch in range(policy['max_pool_epochs_safety']):
            if remaining()<5:state['stopped_reason']='NATIVE_BUDGET_WITH_RETURN_RESERVE';break
            if (DOCS/'CANCEL_REQUEST.json').exists():state['stopped_reason']='USER_CANCEL';break
            if epoch==0:folder=DOCS/'packages/COMPARE_POOL_001';signature=read(folder/'SPEC.json')['pool_signature']
            else:
                case=v.load_native_case();point=v.load_point(last_full['point']['path'])
                pools,signature=generate(case,point,last_full['replay']['path'],epoch,seen)
                if pools is None:del case,point;gc.collect();state['stopped_reason']='VALID_ADAPTIVE_CANDIDATE_SIGNATURES_EXHAUSTED';break
                folder=DOCS/'packages'/f'POOL_{epoch:03d}';folder.mkdir(parents=True,exist_ok=False)
                spec,lo,hi,A,rhs=build_spec(case,point,last_full['replay']['path'],pools,f'POOL_{epoch:03d}',0)
                proof=integer_proof(case,point,spec,lo,hi,A,rhs);spec['center_raw']=last_full['point']
                write(folder/'JOINT_SPEC.json',spec);write(folder/'JOINT_PROOF.json',proof)
                pair=epoch<policy['comparison_pools_minimum'] or epoch%policy['periodic_other_formulation_every']==0
                direct_needed=pair or state['backend']=='DIRECT'
                if direct_needed:
                    sub=folder/'direct';save(case,point,last_full['replay']['path'],pools,f'POOL_{epoch:03d}',sub)
                del case,point,A,lo,hi;gc.collect()
            state['pool_count']+=1
            pair=epoch<policy['comparison_pools_minimum'] or epoch%policy['periodic_other_formulation_every']==0
            forms=['JOINT','DIRECT'] if pair else [state['backend']]
            results={}
            for form in forms:
                specpath=folder/'JOINT_SPEC.json' if form=='JOINT' else folder/'SPEC.json' if epoch==0 else folder/'direct/SPEC.json'
                requested=policy['initial_comparison_cap'] if epoch<3 else policy['normal_native_cap']
                results[form]=perform(form,specpath,requested,epoch)
                if remaining()<5:break
            if results.get('JOINT') and results.get('DIRECT'):
                state['comparisons'].append(dict(epoch=epoch,pool_signature=signature,JOINT=results['JOINT'],DIRECT=results['DIRECT']))
            if len(state['comparisons'])>=policy['comparison_pools_minimum']:
                medians={form:statistics.median(pair[form]['Native_Runtime'] for pair in state['comparisons'][-5:]) for form in ('JOINT','DIRECT')}
                chosen=min(medians,key=medians.get)
                if chosen!=state['backend']:state['switches'].append(dict(Native=state['Native_used'],old=state['backend'],new=chosen,medians=medians))
                state['backend']=chosen
            persist()
        else:state['stopped_reason']='CONFIGURED_POOL_EPOCH_SAFETY_LIMIT'
        state['PASS']=True
    except Exception as exc:
        import traceback
        state.update(PASS=False,stopped_reason='RESOURCE_NUMERIC_OR_SOURCE_FAIL_CLOSED',error=repr(exc),traceback=traceback.format_exc())
    finally:
        persist();write(DOCS/'FINAL_STATE.json',state)
    print(json.dumps(dict(PASS=state['PASS'],Native_used=state['Native_used'],UB=state['BEST_GLOBAL_UB']['UB'],pools=state['pool_count'],stop=state['stopped_reason'])))
    return 0 if state['PASS'] else 2

if __name__=='__main__':raise SystemExit(main())
