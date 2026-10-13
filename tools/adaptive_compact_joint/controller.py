"""Two small sequential pilot calls sharing the unrestarted 1800s budget."""
import subprocess,sys,time,gc
from tools.adaptive_compact_joint.adapter import *
from tools.global_local_multistart1800.dag import Graph

def invoke(args,log):
    began=time.perf_counter()
    with log.open('w',encoding='utf-8') as stream:
        rc=subprocess.run([sys.executable,'-X','utf8','-m','tools.adaptive_compact_joint.worker',*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
    return rc,time.perf_counter()-began

def main():
    guard();assert read(DOCS/'NATIVE0_GATE.json')['PASS'];assert not (DOCS/'PILOT_STARTED.json').exists(),'NO_BUDGET_RESET'
    policy=read(DOCS/'PILOT_POLICY.json');write(DOCS/'PILOT_STARTED.json',dict(timestamp=r.timestamp(),Native_used_before=policy['inherited_actual_Native']))
    began=time.perf_counter();used=0.;calls=[];valid=[];best=INITIAL_UB;moving=INITIAL_UB
    for descriptor in policy['calls']:
        cap=min(descriptor['seconds'],policy['first_pilot_new_Native_limit']-used,1800-policy['inherited_actual_Native']-used-10)
        if cap<5:break
        label=descriptor['label'];target=DOCS/'pilot'/label
        args=['--mode','pilot','--spec',DOCS/f'{label}_SPEC.json','--proof',DOCS/f'{label}_INTEGER_EQUIVALENCE.json','--output',target,'--seconds',cap]
        rc,wall=invoke(args,DOCS/f'PILOT_{label}.log');q=read(target/'NATIVE_CALL.json')
        assert q['entered_native'] and q['Native_Runtime'] is not None,'UNKNOWN_RUNTIME_FAIL_CLOSED'
        used+=q['Native_Runtime'];calls.append(dict(receipt=record(target/'NATIVE_CALL.json'),Native_Runtime=q['Native_Runtime'],label=label,worker_wall=wall))
        write(DOCS/'PILOT_NATIVE_RUNTIME_LEDGER.json',dict(calls=calls,new_Native_used=used,inherited_Native=policy['inherited_actual_Native'],combined_Native=policy['inherited_actual_Native']+used,budget_reset_count=0))
        assert rc==0 and not q.get('callback_errors') and policy['inherited_actual_Native']+used<=1800
        spec=read(DOCS/f'{label}_SPEC.json')
        for i,capture in enumerate(q['captures']):
            rep=target/f'FULL_REPLAY_{i:03d}.json'
            vr,vwall=invoke(['--mode','validate','--raw',capture['raw']['path'],'--objective',repr(capture['Solver_ObjVal']),'--output',rep],target/f'REPLAY_{i:03d}.log')
            cert=read(rep);item=dict(label=label,raw=capture['raw'],replay=record(rep),FULL_PASS=vr==0 and cert['PASS'],validation_wall=vwall)
            if item['FULL_PASS']:
                selection=np.asarray(capture['lambda_values']);case=v.load_native_case();point=v.load_point(capture['raw']['path']);paths=paths_of(case,point)
                chosen={u:[a for a,lam in zip(spec['lambda_axis'],selection) if a['unit']==u and lam==1.] for u in spec['pools']}
                assert np.isin(selection,(0.,1.)).all() and all(len(aa)==1 and aa[0]['path']==paths[u] for u,aa in chosen.items())
                meta=Graph(case).metadata(paths);item.update(UB=cert['Global_UB'],paths=paths,**meta)
                best=min(best,item['UB']);moving=min(moving,item['UB']) if meta['moves'] else moving
                del case,point;gc.collect()
            valid.append(item)
        if used>policy['first_pilot_new_Native_limit']:break
    result=dict(PASS=True,calls=calls,validations=valid,new_Native_used=used,inherited_Native=policy['inherited_actual_Native'],
        combined_Native=policy['inherited_actual_Native']+used,remaining_approved=1800-policy['inherited_actual_Native']-used,
        BEST_GLOBAL_UB=best,BEST_MOVING_FEASIBLE_UB=moving,Global_LB=GLOBAL_LB,Global_Gap_percent=100*(best-GLOBAL_LB)/best,
        UB_improvement=INITIAL_UB-best,wall_seconds=time.perf_counter()-began,stop_reason='INITIAL_LIMITED_PILOT_COMPLETE_NO_FULL_BUDGET_AUTOCONSUMPTION',
        additional_LB_Optimize=0,ACTUAL='ACTUAL_NOT_RUN')
    write(DOCS/'PILOT_RESULT.json',result);print(json.dumps({k:result[k] for k in ('PASS','combined_Native','new_Native_used','BEST_GLOBAL_UB','UB_improvement')}))

if __name__=='__main__':main()
