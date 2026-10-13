"""One heavyweight model, exact readback, optional single bounded Optimize."""
import argparse,gc,time,traceback
from tools.adaptive_compact_joint.adapter import *
from tools.adaptive_compact_joint.compact import construct
from tools.global_local_multistart1800.joint import build_spec
from tools.u4_primal_alns.pilot import finite_attr

def execute(args):
    guard();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);began=time.perf_counter()
    assert read(DOCS/'PHASE0_SAFE_STOP.json')['PASS']
    spec=read(args.spec);point=v.load_point(ROOT/RAW_REL);case=v.load_native_case();case.point=None
    proof=read(args.proof);assert proof['PASS']
    original_spec,lo,hi,A,rhs=build_spec(case,point,spec['center_replay']['path'],spec['pools'],spec['candidate_id'],args.seconds)
    assert original_spec['mathematical_model_signature']==spec['mathematical_model_signature']
    mode=args.mode;compact=not args.old
    if mode=='pilot':
        assert compact and read(DOCS/'NATIVE0_GATE.json')['PASS']
        assert args.seconds<=read(DOCS/'PILOT_POLICY.json')['maximum_single_call_seconds']
        assert v.file_sha(args.spec)==read(DOCS/'EXECUTED_SOURCE_HASHES.json')[args.spec.relative_to(ROOT).as_posix()]
    pre=r.audit('COMPACT_PRE_BUILD');write(out/'PRE_BUILD_GATE.json',pre);assert pre['PASS']
    before=r.memory();model=None;entered=False
    ledger=dict(entered_native=False,Native_Runtime=None,Optimize_calls=0,compact=compact,requested_seconds=args.seconds,Threads=1,Heavy_Worker=1,
        captures=[],callback_errors=[],resource_samples=[],source_seal=record(DOCS/'EXECUTED_SOURCE_HASHES.json') if (DOCS/'EXECUTED_SOURCE_HASHES.json').exists() else None,
        source_spec=record(args.spec),proof=record(args.proof),Global_LB_admissible=False,ACTUAL='ACTUAL_NOT_RUN')
    try:
        model,x,lam,data=construct(case,point,spec,out,args.seconds,compact)
        gate=r.admit(before,r.memory());write(out/'POST_BUILD_ADMISSION.json',gate);assert gate['PASS'];guard()
        ledger['readback']=record(out/'COMPACT_NATIVE_READBACK.json');ledger['model_build_wall_seconds']=data['build_wall_seconds']
        if mode=='native0':
            # presolve is a model transformation; never model.optimize or an LP solve.
            t=time.perf_counter();presolved=model.presolve();presolved.update()
            transform=dict(Optimize_calls=0,operation='Gurobi Model.presolve model transformation',wall_seconds=time.perf_counter()-t,
                NumVars=presolved.NumVars,NumConstrs=presolved.NumConstrs,NumBinVars=presolved.NumBinVars,NumNZs=presolved.NumNZs,
                memory=r.memory(),solver_optimization_not_entered=True)
            presolved.dispose();write(out/'PRESOLVE_NATIVE0_TRANSFORMATION.json',transform)
            ledger.update(status='NATIVE0_PASS',Native_Runtime=0.,Presolve_transform_wall=transform['wall_seconds'])
        else:
            import gurobipy as gp
            next_gate=0.;best=INITIAL_UB
            def capture(m,where):
                nonlocal next_gate,best
                if where==gp.GRB.Callback.POLLING:return
                try:
                    runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME))
                    if runtime>=next_gate:
                        next_gate=runtime+10;guard();safety=r.callbackcheck()
                        ledger['resource_samples'].append(dict(Native_elapsed=runtime,safety=safety,memory=r.memory()))
                        if not safety['PASS']:ledger['stop_reason']='RESOURCE_OR_SOURCE';m.terminate();return
                    if where==gp.GRB.Callback.MIPSOL:
                        obj=float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                        if obj<best-1e-8:
                            raw=np.asarray(m.cbGetSolution(x));selection=np.asarray(m.cbGetSolution(lam));path=out/f'RAW_{len(ledger["captures"]):03d}.npz'
                            np.savez_compressed(path,point=raw);ledger['captures'].append(dict(raw=record(path),lambda_values=selection.tolist(),Solver_ObjVal=obj,Native_discovery=runtime))
                            best=obj
                            if obj<INITIAL_UB-DELTA:ledger['stop_reason']='STRICT_IMPROVEMENT_EXIT_FOR_FULL';m.terminate()
                except Exception as exc:ledger['callback_errors'].append(repr(exc));m.terminate()
            entered=True;ledger.update(entered_native=True,Optimize_calls=1,status='INFLIGHT');write(out/'NATIVE_CALL.json',ledger)
            t=time.perf_counter();model.optimize(capture);ledger['Optimize_wall_seconds']=time.perf_counter()-t
            ledger['Native_Runtime']=finite_attr(model,'Runtime')
            for key in ('Status','SolCount','ObjVal','ObjBound','MIPGap','NodeCount','IterCount','BarIterCount','MemUsed','MaxMemUsed'):ledger[key]=finite_attr(model,key)
            if model.SolCount:
                path=out/'FINAL_RAW.npz';np.savez_compressed(path,point=np.asarray(x.X))
                ledger['captures'].append(dict(raw=record(path),lambda_values=np.asarray(lam.X).tolist(),Solver_ObjVal=ledger['ObjVal'],Native_discovery=ledger['Native_Runtime']))
            ledger['status']='FINISHED'
        ledger['memory_after']=r.memory()
    except Exception as exc:
        ledger.update(status='FAILED' if entered else 'NATIVE0_REJECTED',error=repr(exc),traceback=traceback.format_exc())
        if entered:ledger['Native_Runtime']=finite_attr(model,'Runtime')
    finally:
        if model is not None:model.dispose()
        ledger.update(model_disposed=True,worker_wall_seconds=time.perf_counter()-began);write(out/'NATIVE_CALL.json',ledger)
    print(json.dumps(dict(status=ledger['status'],Native_Runtime=ledger['Native_Runtime'],error=ledger.get('error'))))
    return 0 if ledger['status'] in ('FINISHED','NATIVE0_PASS') else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['native0','pilot','validate'],required=True)
    p.add_argument('--spec',type=Path);p.add_argument('--proof',type=Path);p.add_argument('--seconds',type=float,default=30)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--old',action='store_true');p.add_argument('--raw',type=Path);p.add_argument('--objective',type=float)
    args=p.parse_args()
    if args.mode=='validate':raise SystemExit(0 if replay(args.raw,args.output,args.objective)['PASS'] else 2)
    raise SystemExit(execute(args))
