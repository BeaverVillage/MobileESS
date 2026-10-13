"""Native readback and exact inverse lift for the new direct formulation."""
import argparse,gc,time,traceback
from scipy import sparse
from tools.adaptive_compact_joint.fresh_adapter import *
from tools.u4_primal_alns.pilot import PARAMS,finite_attr

def execute(args):
    guard();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);began=time.perf_counter()
    spec=read(args.spec);proof=read(args.spec.parent/'EXACT_INTEGER_AND_ROW_EQUIVALENCE.json');assert proof['PASS']
    for rec in spec['packets'].values():assert v.file_sha(rec['path'])==rec['sha256']
    A=sparse.load_npz(spec['packets']['A']['path']).tocsr();T=sparse.load_npz(spec['packets']['LIFT']['path']).tocsr()
    with np.load(spec['packets']['DATA']['path'],allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    with np.load(spec['packets']['START']['path'],allow_pickle=False) as z:start=z['point'].copy()
    assert v.matrix_sha(A)==spec['compact_matrix_SHA'] and v.domain_sha(d)==spec['compact_domain_SHA'] and v.matrix_sha(T)==spec['lift_SHA']
    center=v.load_point(spec['center_raw']['path']);assert v.file_sha(spec['center_raw']['path'])==spec['center_raw']['sha256']
    assert np.array_equal(T@start,center) and v.vector_sha(T@start)==spec['center_vector_SHA']
    pre=r.audit('FRESH_DIRECT_PRE_BUILD');write(out/'PRE_BUILD_GATE.json',pre);assert pre['PASS'];before=r.memory()
    mode=args.mode;model=None;entered=False
    q=dict(entered_native=False,Optimize_calls=0,Native_Runtime=None,Threads=1,Heavy_Worker=1,captures=[],callback_errors=[],resource_samples=[],
        spec=record(args.spec),direct=True,Global_LB_admissible=False,requested_seconds=args.seconds,
        source_seal=record(DOCS/'EXECUTED_SOURCE_HASHES.json') if (DOCS/'EXECUTED_SOURCE_HASHES.json').exists() else None,ACTUAL='ACTUAL_NOT_RUN')
    try:
        import gurobipy as gp
        model=gp.Model('V42_EXACT_DIRECT_4MESS_JOINT');params=dict(PARAMS,Method=2,TimeLimit=args.seconds)
        for k,value in params.items():setattr(model.Params,k,value)
        model.Params.LogFile=str(out/'NATIVE_GUROBI.log')
        x=model.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'],obj=d['objective']);x.VarName=d['names'].tolist()
        model.ObjCon=float(d['constant']);x.Start=start
        rows=model.addMConstr(A,x,d['sense'],d['rhs']);rows.ConstrName=d['row_names'].tolist();model.update()
        actual=model.getA().tocsr();keep=np.asarray(spec['keep_columns'],dtype=int);K=len(keep)
        checks=dict(CSR_exact=v.matrix_sha(actual)==v.matrix_sha(A),RHS_Sense_exact=np.array_equal(model.getAttr('RHS'),d['rhs']) and np.array_equal(model.getAttr('Sense'),d['sense']),
            Bounds_Type_Objective_exact=np.array_equal(x.LB,d['lower']) and np.array_equal(x.UB,d['upper']) and np.array_equal(x.VType,d['types']) and np.array_equal(x.Obj,d['objective']) and model.ObjCon==float(d['constant']),
            Start_exact=np.array_equal(x.Start,start) and v.vector_sha(T@x.Start)==v.vector_sha(center),
            binary_count=model.NumBinVars==384+spec['lambda_count'],all_384_original_mode_free=sum(str(n).startswith('charge_mode[') for n in d['names'])==384,
            all_four_one_hot=spec['compact_rows']==715600 and set(a['unit'] for a in spec['lambda_axis'])=={'MESS01','MESS02','MESS03','MESS04'},
            source_rows_semantically_preserved=proof['original_source_rows_semantically_preserved']==715596,
            exact_product_coefficients_independently_proven=proof['exact_dyadic_lambda_row_coefficients_checked']>0,
            no_physical_columns_removed=proof['source_columns_removed']==216674,
            parameters_exact=all(getattr(model.Params,k)==value for k,value in params.items()))
        assert all(checks.values()),checks;del actual;gc.collect()
        readback=dict(PASS=True,checks=checks,NumVars=model.NumVars,NumConstrs=model.NumConstrs,NumBinVars=model.NumBinVars,NumNZs=model.NumNZs,
            continuous=model.NumVars-model.NumBinVars,build_wall_seconds=time.perf_counter()-began,source_matrix_SHA=spec['compact_matrix_SHA'],source_domain_SHA=spec['compact_domain_SHA'],parameters=params)
        write(out/'NATIVE_READBACK.json',readback);q['readback']=record(out/'NATIVE_READBACK.json')
        gate=r.admit(before,r.memory());write(out/'POST_BUILD_ADMISSION.json',gate);assert gate['PASS'];guard()
        q['model_build_wall_seconds']=readback['build_wall_seconds'];q['build_memory']=r.memory()
        if mode=='native0':
            t=time.perf_counter();ps=model.presolve();ps.update()
            write(out/'PRESOLVE_TRANSFORMATION.json',dict(Optimize_calls=0,wall_seconds=time.perf_counter()-t,NumVars=ps.NumVars,NumConstrs=ps.NumConstrs,NumBinVars=ps.NumBinVars,NumNZs=ps.NumNZs,memory=r.memory()))
            ps.dispose();q.update(status='NATIVE0_PASS',Native_Runtime=0.)
        else:
            assert read(DOCS/'NATIVE0_GATE.json')['PASS'];assert not (DOCS/'CANCEL_REQUEST.json').exists()
            policy=read(DOCS/'EXECUTION_POLICY.json');assert 0<args.seconds<=policy['maximum_single_call_seconds']
            best=float(d['objective']@start+float(d['constant']));initial=best;next_gate=0.;root=None
            def save_raw(z,obj,runtime):
                selection=z[K:];native=out/f'NATIVE_RAW_{len(q["captures"]):03d}.npz';np.savez_compressed(native,point=z)
                dense=T@z;lifted=out/f'DENSE_LIFT_{len(q["captures"]):03d}.npz';np.savez_compressed(lifted,point=dense)
                # This is the model's defined inverse map, never a repair.
                assert np.array_equal(dense[keep],z[:K])
                q['captures'].append(dict(native_raw=record(native),dense_lift=record(lifted),lambda_values=selection.tolist(),Solver_ObjVal=obj,
                    Native_discovery=runtime,strict_literal_lambda=bool(np.isin(selection,(0.,1.)).all()),lift_is_exact_model_inverse=True))
            def callback(m,where):
                nonlocal best,next_gate,root
                if where==gp.GRB.Callback.POLLING:return
                try:
                    runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME))
                    if runtime>=next_gate:
                        next_gate=runtime+10;guard();safety=r.callbackcheck();q['resource_samples'].append(dict(Native_elapsed=runtime,memory=r.memory(),safety=safety))
                        if not safety['PASS'] or (DOCS/'CANCEL_REQUEST.json').exists():q['stop_reason']='RESOURCE_SOURCE_OR_USER_CANCEL';m.terminate();return
                    if where==gp.GRB.Callback.MESSAGE:
                        message=m.cbGet(gp.GRB.Callback.MSG_STRING)
                        if message.lstrip().startswith('Root relaxation: objective'):root=runtime
                    if where==gp.GRB.Callback.MIPSOL:
                        obj=float(m.cbGet(gp.GRB.Callback.MIPSOL_OBJ))
                        if obj<best-1e-8:
                            z=np.asarray(m.cbGetSolution(x));save_raw(z,obj,runtime);best=obj
                            if obj<initial-DELTA:q['stop_reason']='STRICT_IMPROVEMENT_EXIT_FOR_FULL';m.terminate()
                except Exception as exc:q['callback_errors'].append(repr(exc));m.terminate()
            entered=True;q.update(entered_native=True,Optimize_calls=1,status='INFLIGHT');write(out/'NATIVE_CALL.json',q)
            t=time.perf_counter();model.optimize(callback);q['Optimize_wall_seconds']=time.perf_counter()-t;q['Native_Runtime']=finite_attr(model,'Runtime')
            for key in ('Status','SolCount','ObjVal','ObjBound','MIPGap','NodeCount','IterCount','BarIterCount','MemUsed','MaxMemUsed'):q[key]=finite_attr(model,key)
            q['root_completed_Native_seconds']=root
            if model.SolCount:save_raw(np.asarray(x.X),q['ObjVal'],q['Native_Runtime'])
            q['status']='FINISHED'
        q['memory_after']=r.memory()
    except Exception as exc:
        q.update(status='FAILED' if entered else 'NATIVE0_REJECTED',error=repr(exc),traceback=traceback.format_exc())
        if entered:q['Native_Runtime']=finite_attr(model,'Runtime')
    finally:
        if model is not None:model.dispose()
        q.update(model_disposed=True,worker_wall_seconds=time.perf_counter()-began);write(out/'NATIVE_CALL.json',q)
    print(json.dumps(dict(status=q['status'],Native=q['Native_Runtime'],error=q.get('error'))))
    return 0 if q['status'] in ('FINISHED','NATIVE0_PASS') else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['native0','native','validate'],required=True);p.add_argument('--spec',type=Path)
    p.add_argument('--seconds',type=float,default=60);p.add_argument('--output',type=Path,required=True);p.add_argument('--point',type=Path);p.add_argument('--objective',type=float)
    args=p.parse_args()
    if args.mode=='validate':raise SystemExit(0 if validate(args.point,args.output,args.objective)['PASS'] else 2)
    raise SystemExit(execute(args))
