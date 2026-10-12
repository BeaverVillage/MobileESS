"""Adaptive single-worker primal/dual controller with durable Native ledger."""
from __future__ import annotations
import argparse,gc,json,math,shutil,subprocess,sys,time,traceback
from collections import Counter
from pathlib import Path
import numpy as np
from tools.k32_routefixed1800.adapter import *
from tools.k32_routefixed1800.routes import generate,select
LB=.46498486997548166

def invoke(args,log,module='tools.k32_routefixed1800.worker'):
    began=time.perf_counter()
    with Path(log).open('w',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,'-X','utf8','-m',module,*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    return result.returncode,time.perf_counter()-began

def prepare():
    DOCS.mkdir(parents=True,exist_ok=True)
    assert not (DOCS/'RUN_STARTED.json').exists()
    baseline=r.create_baseline()
    source=r.audit('CANARY_PREPARE',True)
    write(DOCS/'PRE_RUN_RESOURCE_SOURCE_AUDIT.json',source)
    assert source['PASS'],source['checks']
    for filename in ('SIGNED_SELECTION_CONTEXT.json','SIGNED_SELECTION_SOURCE_RAW.json','SIGNED_SELECTION_INDEPENDENT_NATIVE0.json','U4_K32_SIGNED_DIAGNOSTICS.json'):
        shutil.copyfile(OLD/filename,DOCS/filename)
    case=v.load_native_case()
    identity=case.identity
    assert identity['original_matrix_sha']==v.FULL_MATRIX_SHA and identity['original_domain_sha']==v.FULL_DOMAIN_SHA
    cold=cold_spec(case);low,high,*_=restriction(case,None,cold);assert audit(case,None,cold,low,high)['PASS']
    # Deliberate moving DAG regression. It never uses a saved point as a start.
    paths=stationary_paths(case);u=sorted(paths)[0];origin=case.graph[1][u]
    stay={(a[0],a[1]):k for k,a in enumerate(case.graph[2]) if a[-1] is None}
    names={str(n):j for j,n in enumerate(case.original_d['names'])}
    moving=None
    for k,a in enumerate(case.graph[2]):
        if a[-1] is None or a[0]!=origin or not 12<=a[1]<=48:continue
        path=[stay[origin,t] for t in range(a[1])]+[k]+[stay[a[2],t] for t in range(a[3],96)]
        if not all(case.original_d['upper'][names[f'arc[{u},{q}]']]>=1 for q in path):continue
        trial=dict(paths);trial[u]=path
        try:
            moving=route_spec(case,dict(candidate_id='NATIVE0_REAL_MOVE',paths=trial,moves=1,travel_energy_kWh=float(a[-1].energy_kwh),score=0.))
            low,high,*_=restriction(case,None,moving);proof=audit(case,None,moving,low,high)
            break
        except (AssertionError,ValueError):continue
    assert moving is not None,'NO_VALID_MOVING_NATIVE0'
    corrupt=dict(moving);corrupt['route_fixed_values']=list(moving['route_fixed_values']);corrupt['route_fixed_values'][0]=1-corrupt['route_fixed_values'][0]
    rejected=False
    try:audit(case,None,corrupt,low,high)
    except AssertionError:rejected=True
    assert rejected
    write(DOCS/'PRE_NATIVE0_ROUTE_REGRESSION.json',dict(PASS=True,moving_route=proof,corrupt_route_rejected=True,
        historical_N1_start_used=False,Native_optimize_calls=0))
    lb_cert={}
    for key,i,value in [('K32',1,.46497617639758426),('K48',2,LB)]:
        folder=ROOT/f'docs/v42_critical_grid_cg/iteration{i:02d}'
        packet=read(folder/'INDEPENDENT_CERTIFICATE.json')
        assert packet['PASS'] and packet['Global_LB']==value and packet['source18r']==v.SOURCE_SHA and packet['case_sha']==v.CASE_SHA
        assert packet['FULL_projection_subset_native_Joint'] and packet['native_source_attribute']=='ObjBound'
        for name,digest in read(folder/'INDEPENDENT_NATIVE0.json')['file_sha256'].items():
            assert v.file_sha(folder/name)==digest,'LB_FILE_DRIFT:'+name
        lb_cert[key]=dict(LB=value,certificate=record(folder/'INDEPENDENT_CERTIFICATE.json'),proof=packet,
            independently_rehashed_model_and_coefficient_files=True)
    write(DOCS/'K32_K48_LB_CERTIFICATES.json',dict(PASS=True,certificates=lb_cert,Global_LB=LB,
        FULL_matrix_SHA=v.FULL_MATRIX_SHA,FULL_domain_SHA=v.FULL_DOMAIN_SHA,new_Optimize_calls=0))
    write(DOCS/'SOURCE_AND_CASE_AUTHORITY.json',dict(PASS=True,base_PR217=BASE,source_PR207=v.SOURCE_SHA,
        case_SHA=v.CASE_SHA,FULL_matrix_SHA=v.FULL_MATRIX_SHA,FULL_domain_SHA=v.FULL_DOMAIN_SHA,
        identity=identity,authority=source['originals'],source_equivalence_proofs=case.source_evidence))
    policy=dict(Native_limit=1800,Threads=1,Heavy_workers=1,initial_plan=dict(cold_U4_N1=210,route=1000,dual=300,reserve=290),
        per_call_caps=dict(INITIALIZE=120,U4=90,N1=150,ROUTE_FIXED=90,DUAL=300),
        global_gap_target=.03,UB_comparison_tolerance=1e-8,material_LB_gain=.001,
        all_route_candidates_must_move=True,N1_stationary_route_not_repeated=True,
        no_new_route_MIP_Start=True,actual='ACTUAL_NOT_RUN',no_unrestricted_FULL=True)
    write(DOCS/'PREREGISTERED_POLICY.json',policy)
    files=[]
    for directory in ('tools/k32_routefixed1800','tools/integrated_primal1800','tools/u4_primal_alns','v42_common_mess','tools/b2_root_lp_tightening','tools/critical_grid_cg'):
        files.extend((ROOT/directory).glob('*.py'))
    files.extend([ROOT/'tools/time_decomposed_lb/grid.py',DOCS/'PREREGISTERED_POLICY.json'])
    write(DOCS/'EXECUTED_SOURCE_HASHES.json',{str(p.relative_to(ROOT)):v.file_sha(p) for p in files})
    print(json.dumps(dict(PASS=True,Native_calls=0)))

def run(resume=False):
    assert resume or not (DOCS/'RUN_STARTED.json').exists(),'NO_BUDGET_RESET_OR_IMPLICIT_RESTART'
    guard();began=time.perf_counter()
    if not resume:write(DOCS/'RUN_STARTED.json',dict(UTC=r.timestamp(),Native_limit=1800))
    state=dict(Native_used=0.,calls=[],iterations=[],BEST_GLOBAL_UB=None,BEST_MOVING_FEASIBLE_UB=None,
        Global_LB=LB,Global_gap=None,stage_best={},trajectory=[],moving_trajectory=[],search_epochs=[],
        stopped_reason=None,source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,ACTUAL='ACTUAL_NOT_RUN',
        unrestricted_FULL_Optimize_calls=0,new_dual_calls=0)
    prior_wall=0.
    if resume:
        state=read(DOCS/'FINAL_STATE.json');prior_wall=state['controller_wall_seconds']
        assert state['stopped_reason']=='SOURCE_OR_RESOURCE_STOP' and len(state['calls'])==1 and state['calls'][0]['method']=='INITIALIZE'
        assert state['Native_used']==44.187999963760376
        state.update(stopped_reason=None,error=None,traceback=None,resume_preserves_Native_ledger=True)
        # Use the same solve's independently FULL-validated final raw as a
        # strict-box start representative. UB and route-search center stay put.
        final=next(x for x in state['iterations'][0]['validated'] if Path(x['raw']['path']).name=='FINAL_RAW.npz' and x['PASS'])
        state['START_REPRESENTATIVE']=dict(state['BEST_GLOBAL_UB'],point=final['raw'],replay=final['replay'])
        write(DOCS/'RUN_RESUMED.json',dict(UTC=r.timestamp(),Native_used_preserved=state['Native_used'],
            INITIALIZE_not_reexecuted=True,same_UB_final_strict_box_start_only=True))
    seen=set();counts=Counter();queue=[];dual_done=False;last_center=None;epoch=0
    def persist():
        best=state['BEST_GLOBAL_UB'];state['Global_gap']=None if best is None else (best['UB']-state['Global_LB'])/best['UB']
        state['controller_wall_seconds']=prior_wall+time.perf_counter()-began
        write(DOCS/'LIVE_STATE.json',state)
        write(DOCS/'NATIVE_RUNTIME_LEDGER.json',dict(Native_limit=1800,Native_used=state['Native_used'],
            calls=state['calls'],all_Optimize_calls_included=True,budget_reset_count=0))
    def perform(method,candidate=None,pattern=None):
        guard();remaining=1800-state['Native_used']-5.
        if remaining<2:return False
        index=max([0]+[int(p.name.split('_')[0]) for p in (DOCS/'calls').iterdir() if p.is_dir()])+1
        folder=DOCS/'calls'/f'{index:03d}_{method}';folder.mkdir(parents=True,exist_ok=False)
        current=state.get('START_REPRESENTATIVE') or state['BEST_GLOBAL_UB'];case=v.load_native_case();x=None
        if method=='INITIALIZE':spec=cold_spec(case,pattern or 'all_discharge')
        elif method=='ROUTE_FIXED':
            assert candidate['moves']>=1 and candidate['paths']!=stationary_paths(case),'STATIONARY_ROUTE_REPETITION_FORBIDDEN'
            spec=route_spec(case,candidate)
            assert signature(spec) not in seen;seen.add(signature(spec))
            for u in candidate['units']:counts[u]+=1
        elif method=='U4':
            code,_=invoke(['--mode','selector','--center',current['point']['path'],'--replay',current['replay']['path'],'--output',folder/'SPEC.json'],folder/'SELECTOR.log')
            assert code==0,'U4_SELECTOR_FAILURE'
            spec=read(folder/'SPEC.json');x=v.load_point(current['point']['path'])
        else:
            x=v.load_point(current['point']['path']);spec=make_spec(case,x,'N1',n.candidate_queue('N1')[0],current['replay']['path'])
        low,high,*_=restriction(case,x,spec);proof=audit(case,x,spec,low,high,folder/'PRE_NATIVE0.json');assert proof['PASS']
        write(folder/'SPEC.json',spec)
        del case,x,low,high;gc.collect()
        cap={'INITIALIZE':120,'U4':90,'N1':150,'ROUTE_FIXED':90}[method]
        if method=='ROUTE_FIXED' and candidate['moves']>1:cap=120
        seconds=min(cap,remaining)
        command=['--mode','native','--method',method,'--spec',folder/'SPEC.json','--output',folder/'native','--seconds',seconds]
        if method in ('U4','N1'):command+=['--center',current['point']['path']]
        rc,wall=invoke(command,folder/'WORKER.log')
        receipt=folder/'native/NATIVE_CALL.json';assert receipt.exists(),'NO_RUNTIME_RECEIPT_QUARANTINE'
        call=read(receipt);call.update(receipt=record(receipt),worker_exit_code=rc,worker_wall_seconds=wall)
        iteration=dict(method=method,candidate=candidate,call=record(receipt),validated=[],result_states=[])
        state['iterations'].append(iteration)
        if call['entered_native']:
            runtime=call['Native_Runtime'];assert runtime is not None and math.isfinite(runtime) and runtime>=0
            state['Native_used']+=runtime;state['calls'].append(call);persist()
            assert state['Native_used']<=1800,'NATIVE_BUDGET_CEILING'
        else:
            persist();raise ValueError('PRE_NATIVE_RESOURCE_OR_SOURCE_REJECTION')
        if method=='ROUTE_FIXED':
            iteration['result_states']+=['DAG_ROUTE_VALID','ROUTE_FIXED_MILP_OPTIMAL' if call.get('Status')==2 else 'ROUTE_FIXED_TIME_LIMIT' if call.get('Status')==9 else 'ROUTE_FIXED_STATUS_'+str(call.get('Status'))]
        for k,capture in enumerate(call['captures']):
            replay=folder/f'REPLAY_{k:03d}.json';raw=capture['file']['path']
            vrc,vwall=invoke(['--mode','validate','--point',raw,'--output',replay,'--solver-objective',capture['Solver_ObjVal']],folder/f'VERIFY_{k:03d}.log')
            cert=read(replay) if replay.exists() else dict(PASS=False,error='NO_REPLAY_RECEIPT')
            item=dict(raw=record(raw),replay=record(replay) if replay.exists() else None,PASS=vrc==0 and cert.get('PASS',False),
                validation_wall_seconds=vwall,discovered_Native_seconds=state['Native_used']-runtime+capture['discovered_Native_seconds'])
            iteration['validated'].append(item)
            if not item['PASS']:
                iteration['result_states'].append('FULL_REPLAY_FAIL');continue
            ub=cert['Global_UB'];assert ub>=state['Global_LB']-1e-8
            moves=int(cert['original_matrix_and_96_slot_physical_replay']['physical'].get('move_count',0))
            if method=='ROUTE_FIXED':moves=candidate['moves']
            result=dict(UB=ub,point=record(raw),replay=record(replay),method=method,moves=moves,
                candidate_id=spec['candidate_id'],Native_discovery_seconds=item['discovered_Native_seconds'])
            if moves>0 and (state['BEST_MOVING_FEASIBLE_UB'] is None or ub<state['BEST_MOVING_FEASIBLE_UB']['UB']-1e-8):
                state['BEST_MOVING_FEASIBLE_UB']=result;state['moving_trajectory'].append(result)
            prior=state['BEST_GLOBAL_UB']
            improvement=prior is None or ub<prior['UB']-1e-8
            if improvement:
                state['BEST_GLOBAL_UB']=result
                state['START_REPRESENTATIVE']=None
                state['trajectory'].append(dict(Native_seconds=item['discovered_Native_seconds'],UB=ub,LB=state['Global_LB'],
                    gap=(ub-state['Global_LB'])/ub,method=method,moves=moves,point=record(raw)))
                print(json.dumps(dict(verified_UB=ub,moves=moves,Native=state['Native_used'])),flush=True)
            if method=='ROUTE_FIXED':
                iteration['result_states'].append('FULL_FEASIBLE_MOVING')
                iteration['result_states'].append('MOVING_UB_IMPROVEMENT' if improvement else 'MOVING_FEASIBLE_BUT_WORSE')
            # Best in each stage is independent of global acceptance.
            prev=state['stage_best'].get(method)
            if prev is None or ub<prev['UB']-1e-8:state['stage_best'][method]=result
            if Path(raw).name=='FINAL_RAW.npz' and ub<=state['BEST_GLOBAL_UB']['UB']+1e-8:
                raw_x=v.load_point(raw);box_case=v.load_case()
                if np.all(raw_x>=box_case.d['lower']) and np.all(raw_x<=box_case.d['upper']):
                    state['START_REPRESENTATIVE']=result
                del box_case,raw_x;gc.collect()
            persist()
        if not any(i['PASS'] for i in iteration['validated']):
            iteration['result_states'].append('SOLVER_PROVED_INFEASIBLE' if call.get('Status')==3 else
                'TIME_LIMIT_NO_FEASIBLE' if call.get('Status')==9 and not call.get('SolCount') else 'UNRESOLVED_OR_FULL_REPLAY_FAIL')
        elif call.get('Status')==9:iteration['result_states'].append('TIME_LIMIT_WITH_FEASIBLE')
        persist();return True
    try:
        if not resume:perform('INITIALIZE')
        if state['BEST_GLOBAL_UB'] is None:perform('INITIALIZE',pattern='before_peak')
        assert state['BEST_GLOBAL_UB'] is not None,'NO_COLD_FULL_FEASIBLE'
        perform('U4');perform('N1')
        while 1800-state['Native_used']>7:
            persist()
            if state['Global_gap']<=.03:state['stopped_reason']='GLOBAL_GAP_3PCT_CERTIFIED';break
            center=state['BEST_GLOBAL_UB']['point']['sha256']
            if center!=last_center:
                case=v.load_case();point=v.load_point(state['BEST_GLOBAL_UB']['point']['path'])
                queue,search=generate(case,point,beam=64,epoch=epoch)
                state['search_epochs'].append(search);write(DOCS/'ROUTE_CANDIDATES.json',dict(candidates=queue,epochs=state['search_epochs']))
                del case,point;gc.collect();last_center=center;epoch+=1
                print(json.dumps(dict(generated_candidates=len(queue),Native=state['Native_used'])),flush=True)
            # One qualified strengthening opportunity; allocate when early route
            # exploration has established whether primal progress is material.
            if not dual_done and len([i for i in state['iterations'] if i['method']=='ROUTE_FIXED'])>=4 and 1800-state['Native_used']>307:
                guard()
                code,wall=invoke(['--seconds',min(300,1800-state['Native_used']-5)],DOCS/'DUAL_WORKER.log','tools.k32_routefixed1800.dual')
                dual_done=True
                path=DOCS/'dual/NATIVE_CALL.json'
                if path.exists():
                    call=read(path)
                    if call.get('entered_native'):
                        runtime=call['Native_Runtime'];assert runtime is not None and math.isfinite(runtime)
                        state['Native_used']+=runtime;state['calls'].append(dict(call,receipt=record(path)));state['new_dual_calls']+=1
                        assert state['Native_used']<=1800
                        cert=read(DOCS/'dual/INDEPENDENT_CERTIFICATE.json')
                        if cert['PASS']:
                            state['Global_LB']=max(state['Global_LB'],cert['Global_LB'])
                            state['trajectory'].append(dict(Native_seconds=state['Native_used'],UB=state['BEST_GLOBAL_UB']['UB'],LB=state['Global_LB'],
                                gap=(state['BEST_GLOBAL_UB']['UB']-state['Global_LB'])/state['BEST_GLOBAL_UB']['UB'],method='DUAL',moves=state['BEST_GLOBAL_UB']['moves']))
                elif code:raise ValueError('DUAL_PRE_NATIVE0_FAILED')
                persist();continue
            candidate=select(queue,seen,counts,advanced=len(seen)>=4)
            if candidate is None:
                state['stopped_reason']='CANDIDATE_EXHAUSTED';break
            print(json.dumps(dict(evaluating=candidate['candidate_id'],units=candidate['units'],moves=candidate['moves'],score=candidate['score'],Native=state['Native_used'])),flush=True)
            perform('ROUTE_FIXED',candidate)
            if state['calls'][-1].get('callback_stop_reason') in ('RESOURCE_OR_SOURCE_CALLBACK_GATE','CALLBACK_ERROR'):
                state['stopped_reason']='SOURCE_OR_RESOURCE_STOP';break
        if not state['stopped_reason']:state['stopped_reason']='NATIVE_BUDGET_END'
    except Exception as exc:
        state.update(stopped_reason='SOURCE_OR_RESOURCE_STOP',error=repr(exc),traceback=traceback.format_exc())
        print(state['traceback'],flush=True)
    finally:
        persist();write(DOCS/'FINAL_STATE.json',state)
        print(json.dumps(dict(stopped_reason=state['stopped_reason'],Native=state['Native_used'],UB=state['BEST_GLOBAL_UB'],LB=state['Global_LB'],gap=state['Global_gap'])),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','run','resume']);args=parser.parse_args()
    prepare() if args.mode=='prepare' else run(resume=args.mode=='resume')
