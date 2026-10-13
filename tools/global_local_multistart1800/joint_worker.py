"""Single Native four-unit joint route-pool MILP; raw FULL replay occurs after exit."""
import argparse,gc,math,time,traceback
from scipy import sparse
from tools.global_local_multistart1800.adapter import *
from tools.global_local_multistart1800.joint import build_spec,independent
from tools.u4_primal_alns.pilot import PARAMS,finite_attr

def native(args):
    guard();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);began=time.perf_counter()
    spec=read(args.spec);center=v.load_point(args.center)
    assert v.file_sha(args.center)==spec['center_raw']['sha256'] and 0<args.seconds<=175
    assert read(DOCS/'PR220_WARM_START_CERTIFICATE.json')['PASS']
    pre=r.audit('JOINT_PRE_BUILD');write(out/'PRE_BUILD_GATE.json',pre);assert pre['PASS']
    case=v.load_native_case();case.point=None
    rebuilt,lower,upper,A,rhs=build_spec(case,center,spec['center_replay']['path'],spec['pools'],spec['candidate_id'],args.seconds)
    assert rebuilt['mathematical_model_signature']==spec['mathematical_model_signature']
    proof=independent(case,center,spec,lower,upper,A,rhs);write(out/'INDEPENDENT_JOINT_NATIVE0.json',proof);assert proof['PASS']
    before=r.memory();model=None;entered=False
    params=dict(PARAMS,Method=2,TimeLimit=args.seconds)
    ledger=dict(method='FOUR_MESS_JOINT_ROUTE_POOL',stage='JOINT',family='FOUR_MESS_JOINT',entered_native=False,Native_Runtime=None,
        requested_seconds=args.seconds,Threads=1,Native_worker=1,captures=[],callback_errors=[],resource_samples=[],initial_point=record(args.center),
        center_vector_SHA=v.vector_sha(center),execution_source_seal=record(DOCS/'EXECUTED_SOURCE_HASHES.json'),specification_input=record(args.spec),
        restricted_ObjBound_is_Global_LB=False,Global_LB_admissible=False,ACTUAL='ACTUAL_NOT_RUN')
    write(out/'NATIVE_CALL.json',ledger)
    try:
        from v42_common_mess.model import build
        import gurobipy as gp
        model,x,identity=build(case,out,lower=lower,upper=upper,start=center,spec=None,numeric_parameters=params)
        assert not identity['unrestricted_original_C3A_MILP'] and all(identity['checks'].values())
        lam=model.addMVar(spec['lambda_count'],lb=0.,ub=1.,vtype='B',obj=0.)
        lam.VarName=[a['name'] for a in spec['lambda_axis']];lam.Start=np.asarray(spec['lambda_Start']);model.update()
        combined=gp.MVar.fromlist(list(x.tolist())+list(lam.tolist()))
        rows=model.addMConstr(A,combined,'=',rhs)
        rows.ConstrName=['route_pool_one['+u+']' for u in sorted(spec['pools'])]+['route_pool_link['+str(case.d['names'][j])+']' for j in spec['varying_route_columns']]
        model.update();actual=model.getA().tocsr();oldrows=case.A.shape[0];oldcols=case.A.shape[1]
        prefix=actual[:oldrows,:oldcols].tocsr();suffix=actual[oldrows:].tocsr()
        source_binaries=np.count_nonzero(case.d['types']!='C');modes=np.flatnonzero(np.char.startswith(case.d['names'],'charge_mode['))
        checks=dict(source_rows_exact=v.matrix_sha(prefix)==v.matrix_sha(case.A) and actual[:oldrows,oldcols:].nnz==0,
            source_RHS_sense_exact=np.array_equal(model.getAttr('RHS')[:oldrows],case.d['rhs']) and np.array_equal(model.getAttr('Sense')[:oldrows],case.d['sense']),
            route_pool_matrix_exact=v.matrix_sha(suffix)==v.matrix_sha(A),route_pool_RHS_sense=np.array_equal(model.getAttr('RHS')[oldrows:],rhs) and set(model.getAttr('Sense')[oldrows:])=={'='},
            original_types_objective=np.array_equal(x.VType,case.d['types']) and np.array_equal(x.Obj,case.d['objective']) and model.ObjCon==float(case.d['constant']),
            original_restricted_bounds=np.array_equal(x.LB,lower) and np.array_equal(x.UB,upper),lambda_binary_bounds=np.all(np.asarray(lam.VType)=='B') and np.all(np.asarray(lam.LB)==0) and np.all(np.asarray(lam.UB)==1),
            binary_count=model.NumBinVars==source_binaries+spec['lambda_count'],lambda_objective_zero=np.all(np.asarray(lam.Obj)==0),
            all384_Mode_free=len(modes)==384 and np.array_equal(np.asarray(x.LB)[modes],case.d['lower'][modes]) and np.array_equal(np.asarray(x.UB)[modes],case.d['upper'][modes]),
            unchanged_raw_Start=np.array_equal(np.asarray(x.Start),center) and np.array_equal(np.asarray(lam.Start),spec['lambda_Start']),
            actual_source_Start_SHA=v.vector_sha(np.asarray(x.Start))==v.vector_sha(center),center_joint_link_feasible=np.array_equal(A@np.r_[np.asarray(x.Start),np.asarray(lam.Start)],rhs),
            four_MESS_exactly_one_route=set(a['unit'] for a in spec['lambda_axis'])==set(case.graph[1]),minimize=model.ModelSense==1,
            no_Hamming_or_Global_Best_cutoff=model.NumConstrs==oldrows+len(rhs),all_four_can_select_MOVE=proof['all_four_MOVE_joint_combination_topology'])
        authority_point=v.load_point(ROOT/RAW_REL);authority_paths=paths_of(case,authority_point);authority_lambda=np.zeros(spec['lambda_count'])
        for u in authority_paths:
            chosen=next(i for i,a in enumerate(spec['lambda_axis']) if a['unit']==u and a['path']==authority_paths[u]);authority_lambda[chosen]=1
        checks['unchanged_PR220_authority_joint_Start_valid']=v.file_sha(ROOT/RAW_REL)==RAW_SHA and np.array_equal(A@np.r_[authority_point,authority_lambda],rhs)
        del actual,prefix,suffix;gc.collect();assert all(checks.values()),checks
        readback=dict(PASS=True,checks=checks,source_binary=int(source_binaries),new_lambda_binary=spec['lambda_count'],total_binary=model.NumBinVars,
            source_Start_vector_SHA=v.vector_sha(np.asarray(x.Start)),lambda_Start=spec['lambda_Start'],parameters={k:getattr(model.Params,k) for k in params},proof=record(out/'INDEPENDENT_JOINT_NATIVE0.json'))
        write(out/'JOINT_NATIVE_READBACK.json',readback)
        assert all(getattr(model.Params,k)==val for k,val in params.items())
        after=r.memory();gate=r.admit(before,after);write(out/'POST_BUILD_NATIVE_ADMISSION.json',gate);assert gate['PASS'];guard()
        ledger.update(parameter_readback=readback['parameters'],actual_NumStart=model.NumStart,build_memory_before=before,build_memory_after=after,model_build_wall_seconds=time.perf_counter()-began)
        next_gate=0.;best_seen=float(case.d['objective']@center+float(case.d['constant']));center_UB=best_seen;root_complete=None
        def capture(m,where):
            nonlocal next_gate,best_seen,root_complete
            if where==gp.GRB.Callback.POLLING:return
            try:
                runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME))
                if runtime>=next_gate:
                    next_gate=runtime+10;guard();safety=r.callbackcheck();sample=r.memory()
                    ledger['resource_samples'].append(dict(Native_elapsed=runtime,sample=sample,safety=safety))
                    write(out/'LIVE_NATIVE.json',dict(Native_elapsed=runtime,observed_unverified_UB=best_seen,memory=sample))
                    if not safety['PASS']:ledger['callback_stop_reason']='RESOURCE_OR_SOURCE_CALLBACK_GATE';m.terminate();return
                if where==gp.GRB.Callback.MESSAGE:
                    text=m.cbGet(gp.GRB.Callback.MSG_STRING)
                    if text.lstrip().startswith('Root relaxation: objective') and not any(t in text.lower() for t in ('interrupted','infeasible','time limit','unbounded')):root_complete=runtime
                if where==gp.GRB.Callback.MIPSOL:
                    value=float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                    if value<best_seen-1e-8:
                        point=np.asarray(m.cbGetSolution(x),dtype=float);selection=np.asarray(m.cbGetSolution(lam),dtype=float)
                        path=out/f'RAW_{len(ledger["captures"]):03d}.npz';np.savez_compressed(path,point=point,route_selection=selection)
                        ledger['captures'].append(dict(file=record(path),Solver_ObjVal=value,discovered_Native_seconds=runtime,vector_sha256=v.vector_sha(point),lambda_values=selection.tolist()))
                        best_seen=value;write(out/'NATIVE_CALL.json',ledger)
                        if value<=center_UB-DELTA:ledger['callback_stop_reason']='FIRST_STRICT_IMPROVEMENT_RAW_EXIT_FOR_FULL_REPLAY';m.terminate()
            except Exception as e:ledger['callback_errors'].append(repr(e));ledger['callback_stop_reason']='CALLBACK_ERROR';m.terminate()
        entered=True;ledger['entered_native']=True;write(out/'NATIVE_CALL.json',ledger);begin=time.perf_counter();model.optimize(capture)
        ledger['Optimize_return_wall_seconds']=time.perf_counter()-begin
        ledger['Native_Runtime']=finite_attr(model,'Runtime');ledger['root_completed_Native_seconds']=root_complete
        for k in ('Status','SolCount','ObjVal','ObjBound','MIPGap','NodeCount','IterCount','BarIterCount','MemUsed','MaxMemUsed'):ledger[k]=finite_attr(model,k)
        if model.SolCount:
            point=np.asarray(x.X,dtype=float);selection=np.asarray(lam.X,dtype=float);path=out/'FINAL_RAW.npz';np.savez_compressed(path,point=point,route_selection=selection)
            ledger['captures'].append(dict(file=record(path),Solver_ObjVal=ledger['ObjVal'],discovered_Native_seconds=ledger['Native_Runtime'],vector_sha256=v.vector_sha(point),lambda_values=selection.tolist()))
        ledger['after_native_memory']=r.memory();ledger['status']='FINISHED'
    except Exception as e:
        ledger.update(error=repr(e),traceback=traceback.format_exc(),status='FAILED' if entered else 'PRE_NATIVE_REJECTED')
        if entered:ledger['Native_Runtime']=finite_attr(model,'Runtime')
    finally:
        if model is not None:model.dispose()
        ledger.update(Native_Model_disposed_before_FULL_replay=True,worker_wall_seconds=time.perf_counter()-began);write(out/'NATIVE_CALL.json',ledger)
    print(json.dumps(dict(Native=ledger['Native_Runtime'],UB=ledger.get('ObjVal'),status=ledger.get('status'))))
    return 0 if ledger.get('status')=='FINISHED' else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True);p.add_argument('--center',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=float,required=True)
    raise SystemExit(native(p.parse_args()))
