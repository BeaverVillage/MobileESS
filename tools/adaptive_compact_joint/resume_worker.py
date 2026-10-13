"""One worker comparing original joint and exact direct compact formulations."""
import argparse,gc,time,traceback
from tools.adaptive_compact_joint.resume_adapter import *
from tools.adaptive_compact_joint.compact import construct
from tools.global_local_multistart1800.joint import build_spec
from tools.u4_primal_alns.pilot import PARAMS,finite_attr

def joint(args):
    guard();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);began=time.perf_counter();spec=read(args.spec)
    point=v.load_point(spec['center_raw']['path']);case=v.load_native_case();case.point=None
    assert v.file_sha(spec['center_raw']['path'])==spec['center_raw']['sha256']
    assert read(args.spec.parent/'JOINT_PROOF.json')['PASS']
    rebuilt,*_=build_spec(case,point,spec['center_replay']['path'],spec['pools'],spec['candidate_id'],args.seconds)
    assert rebuilt['mathematical_model_signature']==spec['mathematical_model_signature']
    pre=r.audit('CONTINUATION_JOINT_PRE_BUILD');write(out/'PRE_BUILD_GATE.json',pre);assert pre['PASS'];before=r.memory()
    q=dict(entered_native=False,Native_Runtime=None,Optimize_calls=0,formulation='ORIGINAL_JOINT',Threads=1,Heavy_Worker=1,
        captures=[],resource_samples=[],callback_errors=[],spec=record(args.spec),source_seal=record(DOCS/'EXECUTED_SOURCE_HASHES.json') if (DOCS/'EXECUTED_SOURCE_HASHES.json').exists() else None,
        Global_LB_admissible=False,requested_seconds=args.seconds,ACTUAL='ACTUAL_NOT_RUN')
    model=None;entered=False
    try:
        model,x,lam,rb=construct(case,point,spec,out,args.seconds,compact=False)
        q['readback']=record(out/'COMPACT_NATIVE_READBACK.json');q['model_build_wall_seconds']=rb['build_wall_seconds']
        admission=r.admit(before,r.memory());write(out/'POST_BUILD_ADMISSION.json',admission);assert admission['PASS'];guard()
        if args.mode=='native0':
            t=time.perf_counter();ps=model.presolve();ps.update();write(out/'PRESOLVE_TRANSFORMATION.json',dict(Optimize_calls=0,wall_seconds=time.perf_counter()-t,NumVars=ps.NumVars,NumBinVars=ps.NumBinVars,NumConstrs=ps.NumConstrs,NumNZs=ps.NumNZs,memory=r.memory()));ps.dispose()
            q.update(status='NATIVE0_PASS',Native_Runtime=0.)
        else:
            import gurobipy as gp
            assert read(DOCS/'NATIVE0_GATE.json')['PASS'] and not (DOCS/'CANCEL_REQUEST.json').exists()
            best=float(case.d['objective']@point+float(case.d['constant']));initial=best;next_gate=0.;root=None
            def save_raw(values,selection,obj,runtime):
                raw=out/f'RAW_{len(q["captures"]):03d}.npz';np.savez_compressed(raw,point=values)
                q['captures'].append(dict(dense_lift=record(raw),native_raw=record(raw),lambda_values=selection.tolist(),strict_literal_lambda=bool(np.isin(selection,(0.,1.)).all()),Solver_ObjVal=obj,Native_discovery=runtime,lift_is_exact_model_inverse=True))
            def callback(m,where):
                nonlocal best,next_gate,root
                if where==gp.GRB.Callback.POLLING:return
                try:
                    runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME))
                    if runtime>=next_gate:
                        next_gate=runtime+10;guard();safety=r.callbackcheck();q['resource_samples'].append(dict(Native_elapsed=runtime,memory=r.memory(),safety=safety))
                        if not safety['PASS'] or (DOCS/'CANCEL_REQUEST.json').exists():q['stop_reason']='RESOURCE_SOURCE_OR_USER_CANCEL';m.terminate();return
                    if where==gp.GRB.Callback.MESSAGE:
                        msg=m.cbGet(gp.GRB.Callback.MSG_STRING)
                        if msg.lstrip().startswith('Root relaxation: objective'):root=runtime
                    if where==gp.GRB.Callback.MIPSOL:
                        obj=float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                        if obj<best-1e-8:
                            save_raw(np.asarray(m.cbGetSolution(x)),np.asarray(m.cbGetSolution(lam)),obj,runtime);best=obj
                            if obj<initial-DELTA:q['stop_reason']='STRICT_IMPROVEMENT_EXIT_FOR_FULL';m.terminate()
                except Exception as exc:q['callback_errors'].append(repr(exc));m.terminate()
            entered=True;q.update(entered_native=True,Optimize_calls=1,status='INFLIGHT');write(out/'NATIVE_CALL.json',q)
            t=time.perf_counter();model.optimize(callback);q['Optimize_wall_seconds']=time.perf_counter()-t;q['Native_Runtime']=finite_attr(model,'Runtime')
            for key in ('Status','SolCount','ObjVal','ObjBound','MIPGap','NodeCount','IterCount','BarIterCount','MemUsed','MaxMemUsed'):q[key]=finite_attr(model,key)
            q['root_completed_Native_seconds']=root
            if model.SolCount:save_raw(np.asarray(x.X),np.asarray(lam.X),q['ObjVal'],q['Native_Runtime'])
            q['status']='FINISHED'
        q['memory_after']=r.memory()
    except Exception as exc:
        q.update(status='FAILED' if entered else 'NATIVE0_REJECTED',error=repr(exc),traceback=traceback.format_exc())
        if entered:q['Native_Runtime']=finite_attr(model,'Runtime')
    finally:
        if model is not None:model.dispose()
        q.update(model_disposed=True,worker_wall_seconds=time.perf_counter()-began);write(out/'NATIVE_CALL.json',q)
    print(json.dumps(dict(status=q['status'],Native=q['Native_Runtime'],error=q.get('error'))))
    return 0 if q['status'] in ('NATIVE0_PASS','FINISHED') else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['native0','native','validate'],required=True);p.add_argument('--formulation',choices=['JOINT','DIRECT'])
    p.add_argument('--spec',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=float,default=120)
    p.add_argument('--point',type=Path);p.add_argument('--objective',type=float);args=p.parse_args();configure()
    if args.mode=='validate':raise SystemExit(0 if validate(args.point,args.output,args.objective)['PASS'] else 2)
    if args.formulation=='DIRECT':
        from tools.adaptive_compact_joint.fresh_worker import execute
        raise SystemExit(execute(args))
    raise SystemExit(joint(args))
