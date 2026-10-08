"""One preregistered full original integer-domain cutoff call; no repeated solve."""
from .common import *
import threading, traceback
import psutil
import gurobipy as gp

SETTINGS=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,MIPFocus=1,MIPGap=.005,
    FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,Seed=20260929,
    DegenMoves=0,BarConvTol=1e-8,TimeLimit=1180,Heuristics=.2,DualReductions=0,SolutionLimit=1)
def digest_csr(A):
    return hashlib.sha256(A.indptr.tobytes()+A.indices.tobytes()+A.data.tobytes()).hexdigest()
class Resource:
    def __init__(self):
        self.stop=threading.Event();self.start=time.perf_counter();self.phase='LOAD';self.peak=0
        self.cpu0=sum(psutil.Process().cpu_times()[:2]);self.errors=[]
    def run(self):
        proc=psutil.Process()
        with (OUT/'RESOURCE_TELEMETRY.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,['wall_seconds','phase','PID','RSS','peak_RSS','process_CPU_seconds','available_RAM']);w.writeheader()
            while True:
                try:
                    mem=proc.memory_info();self.peak=max(self.peak,mem.rss)
                    w.writerow(dict(wall_seconds=time.perf_counter()-self.start,phase=self.phase,PID=os.getpid(),
                        RSS=mem.rss,peak_RSS=self.peak,process_CPU_seconds=sum(proc.cpu_times()[:2])-self.cpu0,
                        available_RAM=psutil.virtual_memory().available));f.flush()
                except Exception as e:self.errors.append(repr(e))
                if self.stop.wait(5):break
    def begin(self):self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def close(self):self.stop.set();self.thread.join(10)

def main():
    begin=time.perf_counter();resource=Resource();resource.begin();env=None;model=None;calls=0
    result=dict(Status=None,SolCount=0,Runtime=0.,Work=0.,NodeCount=0.,incumbent_paths=[],callback_errors=[],
        classification='NOT_RUN',global_infeasibility_proven=False,independent_exact_infeasibility=False)
    token=OUT/'NATIVE_CUTOFF_ONCE.json'
    try:
        assert read(OUT/'SOURCE_IDENTITY.json')['PASS']
        assert read(OUT/'OPTIMIZE_ZERO_GATE.json')['PASS']
        registration=read(OUT/'EXPERIMENT_PREREGISTRATION.json')
        assert registration['cutoff_settings']==SETTINGS
        for rel,h in registration['native_producer_source_sha256'].items():assert sha(ROOT/rel)==h,rel
        assert not token.exists(), 'CONSUMED_EXPERIMENT_CANNOT_BE_REPEATED'
        A,d,T,AA,dd=load();load_wall=time.perf_counter()-begin;resource.phase='BUILD'
        env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
        model=gp.Model('DIAGNOSTIC_ORIGINAL_C3A_B2_RHO_LE_0p60',env=env)
        v=model.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'],obj=d['objective'])
        v.VarName=d['names'].tolist();model.ObjCon=float(d['constant']);model.ModelSense=1
        c=model.addMConstr(AA,v,dd['sense'],dd['rhs']);c.ConstrName=dd['row_names'].tolist()
        model.addConstr(v[239826]<=CUTOFF,name='rho_cutoff_0p60')
        for k,val in SETTINGS.items():model.setParam(k,val)
        model.Params.LogFile=str(OUT/'ORIGINAL_CUTOFF_NATIVE.log');model.Params.LogToConsole=0;model.Params.OutputFlag=1
        model.Params.NodefileDir=str(OUT/'tmp');model.update()
        actual=model.getA().tocsr()
        assert digest_csr(actual[:A.shape[0]])==digest_csr(A)
        assert digest_csr(actual[A.shape[0]:AA.shape[0]])==digest_csr(T)
        extra=actual.getrow(AA.shape[0]);assert extra.indices.tolist()==[239826] and extra.data.tolist()==[1.]
        native={k:np.asarray(model.getAttr(attr)) for k,attr in [('objective','Obj'),('lower','LB'),('upper','UB'),
            ('types','VType'),('names','VarName'),('rhs','RHS'),('sense','Sense'),('row_names','ConstrName')]}
        native['constant']=np.array(model.ObjCon)
        for k in ('objective','lower','upper','types','names','constant'):
            assert native[k].dtype==d[k].dtype and native[k].tobytes()==d[k].tobytes(),k
        for k in ('rhs','sense','row_names'):assert np.array_equal(native[k][:-1],dd[k]),k
        assert native['rhs'][-1]==CUTOFF and native['sense'][-1]=='<' and native['row_names'][-1]=='rho_cutoff_0p60'
        params={k:model.getParamInfo(k)[2] for k in SETTINGS};assert params==SETTINGS
        assert model.getParamInfo('MemLimit')[2]==model.getParamInfo('MemLimit')[5]
        assert model.getParamInfo('SoftMemLimit')[2]==model.getParamInfo('SoftMemLimit')[5]
        assert model.NumVars==306040 and model.NumConstrs==583460 and model.NumNZs==5352915
        save(OUT/'MODEL_IDENTITY.npz',**native)
        keys=('objective','constant','names','lower','upper','types')
        original_hashes={k:hashlib.sha256(d[k].tobytes()).hexdigest() for k in keys}
        native_hashes={k:hashlib.sha256(native[k].tobytes()).hexdigest() for k in keys}
        write(OUT/'MODEL_IDENTITY.json',dict(PASS=True,rows=model.NumConstrs,columns=model.NumVars,nnz=model.NumNZs,
            binaries=int((native['types']=='B').sum()),model_sense=model.ModelSense,
            source_CSR_SHA256=digest_csr(A),native_original_CSR_SHA256=digest_csr(actual[:A.shape[0]]),
            B2_CSR_SHA256=digest_csr(T),native_B2_CSR_SHA256=digest_csr(actual[A.shape[0]:AA.shape[0]]),
            original_array_hashes=original_hashes,native_array_hashes=native_hashes,
            native_rhs_original_SHA256=hashlib.sha256(native['rhs'][:A.shape[0]].tobytes()).hexdigest(),
            native_sense_original_SHA256=hashlib.sha256(native['sense'][:A.shape[0]].tobytes()).hexdigest(),
            native_B2_rhs_SHA256=hashlib.sha256(native['rhs'][A.shape[0]:AA.shape[0]].tobytes()).hexdigest(),
            cutoff=dict(name='rho_cutoff_0p60',sense='<',rhs=CUTOFF,column=239826,coefficient=1.,nnz=1),
            objective='unchanged min rho_max',original_bounds_and_integer_types_unchanged=True,
            parameters=params,MemLimit='default infinity',SoftMemLimit='default infinity',
            RAM_based_automatic_stop=False,source_HEAD=BASE,solver_version=list(gp.gurobi.version()),
            native_fingerprint=int(model.Fingerprint),only_added_constraint='rho_max <= 0.60'))
        build_wall=time.perf_counter()-begin-load_wall;resource.phase='NATIVE'
        with token.open('x',encoding='utf-8') as f:json.dump(dict(maximum_calls=1,settings=SETTINGS,
            reserve_seconds=20,maximum_native_runtime=1200,source_HEAD=BASE,PID=os.getpid(),start_epoch=time.time()),f)
        calls=1;trajectory=[];incumbents=[];branch_records=[];callback_errors=[];last=-60.;wall_native=time.perf_counter()
        native_initial_cpu=sum(psutil.Process().cpu_times()[:2])
        def callback(m,where):
            nonlocal last
            try:
                if where==gp.GRB.Callback.POLLING:return
                runtime=m.cbGet(gp.GRB.Callback.RUNTIME)
                # Budget stop is time-only; never derived from host RAM/RSS.
                if runtime>=1185:m.terminate()
                if where==gp.GRB.Callback.MIPSOL:
                    x=np.asarray(m.cbGetSolution(v));path=OUT/'incumbents'/f'{len(incumbents):03d}.npz'
                    save(path,x=x);incumbents.append(dict(path=path.relative_to(OUT).as_posix(),runtime=runtime,
                        rho=float(x[239826]),callback_objective=m.cbGet(gp.GRB.Callback.MIPSOL_OBJ)))
                if where==gp.GRB.Callback.MIP and runtime-last>=15:
                    trajectory.append(dict(runtime=runtime,Work=m.cbGet(gp.GRB.Callback.WORK),
                        nodes=m.cbGet(gp.GRB.Callback.MIP_NODCNT),unexplored_nodes=m.cbGet(gp.GRB.Callback.MIP_NODLFT),
                        best_bound=m.cbGet(gp.GRB.Callback.MIP_OBJBND),best_objective=m.cbGet(gp.GRB.Callback.MIP_OBJBST),
                        solutions=m.cbGet(gp.GRB.Callback.MIP_SOLCNT)));last=runtime
                    write(OUT/'LIVE_PROGRESS.json',trajectory[-1])
                if where==gp.GRB.Callback.MIPNODE:
                    count=int(m.cbGet(gp.GRB.Callback.MIPNODE_NODCNT))
                    if not branch_records or branch_records[-1]['processed_nodes']!=count:
                        branch_records.append(dict(runtime=runtime,processed_nodes=count,
                            status=int(m.cbGet(gp.GRB.Callback.MIPNODE_STATUS))))
            except Exception as e:callback_errors.append(repr(e))
        print('ONE_ORIGINAL_CUTOFF_NATIVE_CALL_STARTED',flush=True)
        model.optimize(callback)
        result.update(classification='INCONCLUSIVE',native_calls=1,
            native_controller_wall_seconds=time.perf_counter()-wall_native,
            native_CPU_seconds=sum(psutil.Process().cpu_times()[:2])-native_initial_cpu,
            load_seconds=load_wall,model_build_and_audit_seconds=build_wall,incumbent_paths=incumbents,
            callback_errors=callback_errors,Status=int(model.Status),SolCount=int(model.SolCount),
            Runtime=model.Runtime,Work=model.Work,NodeCount=model.NodeCount)
        for attr in ('ObjVal','ObjBound','IterCount','BarIterCount','ConstrVio','BoundVio','IntVio'):
            try:result[attr]=getattr(model,attr)
            except (gp.GurobiError,AttributeError):result[attr]=None
        if model.SolCount:
            save(OUT/'CUTOFF_RETURNED_POINT.npz',x=np.asarray(model.getAttr('X')))
            result['incumbent_paths'].append(dict(path='CUTOFF_RETURNED_POINT.npz',rho=float(model.ObjVal)))
        write(OUT/'CUTOFF_TRAJECTORY.json',dict(trajectory=trajectory,MIPNODE_events=branch_records,
            per_node_branch_variable='NOT_EXPOSED_BY_GUROBI_CALLBACK',
            complete_search_tree='NOT_EXPORTED; native status and log are numerical evidence only'))
        # Dispose before full-grid physical replay; never optimize during checking.
        model.dispose();model=None;env.dispose();env=None;resource.phase='REPLAY';forbid_optimize()
        checks=[];reader=None
        for candidate in result['incumbent_paths']:
            with np.load(OUT/candidate['path']) as z:x=z['x'].copy()
            raw=row_replay(A,d,x);b2=row_replay(AA,dd,x)
            if reader is None:reader=physical_reader()
            physical=reader.check(x,A,d)
            # Exact scalar cutoff: no tolerance or source point substitution.
            accepted=bool(raw['PASS'] and b2['PASS'] and physical['PASS'] and x[239826]<=CUTOFF)
            checks.append(dict(**candidate,PASS=accepted,original_C3A=raw,B2=b2,physical=physical,
                exact_scalar_cutoff_PASS=bool(x[239826]<=CUTOFF),repairs=0))
        result['independent_original_replay']=checks
        valid=[r for r in checks if r['PASS']]
        if valid:result.update(classification='FEASIBLE_COUNTEREXAMPLE',validated_UB=min(r['rho'] for r in valid))
        elif result['Status']==gp.GRB.INFEASIBLE:
            result.update(classification='NUMERICAL_INFEASIBLE_ONLY',
                solver_full_original_integer_domain_covered=True,
                exact_global_proof='NOT_PROVEN; MIP search status is not an independent rational certificate')
        else:result['exact_global_proof']='NOT_PROVEN'
        result['unresolved_region']='Entire cutoff domain remains undecided' if not valid and result['Status']!=3 else None
        result['actual_branch_variable_count']=None
        result['branch_variable_count_reason']='Callback exposes processed/open node counts, not all internal branch variables'
    except Exception as e:
        result.update(error=repr(e),traceback=traceback.format_exc(),native_calls=calls,
            classification='EXECUTION_FAILED' if calls else 'PREFLIGHT_FAILED')
        if calls and model is not None:
            for attr in ('Runtime','Work','Status','SolCount','NodeCount'):
                try:result[attr]=getattr(model,attr)
                except (gp.GurobiError,AttributeError):result[attr]=None
            result['native_attribute_recovery_after_error']=True
        print(result['traceback'],flush=True)
    finally:
        if model is not None:model.dispose()
        if env is not None:env.dispose()
        resource.close()
        result.update(native_calls=calls,controller_wall_seconds=time.perf_counter()-begin,
            observed_peak_RSS_bytes=resource.peak,controller_CPU_seconds=sum(psutil.Process().cpu_times()[:2])-resource.cpu0,
            resource_errors=resource.errors,no_resource_stop=True,production_calls=0,P2_calls=0,downstream_calls=0)
        known=result.get('Runtime') is not None
        result['actual_Runtime_known']=known
        result['charged_Runtime']=result['Runtime'] if known else 1200.
        result['native_runtime_budget_PASS']=known and result['Runtime']<=1200
        write(OUT/'ORIGINAL_CUTOFF_RESULT.json',result)
        write(OUT/'NATIVE_RUNTIME_LEDGER.json',dict(new_native_calls=calls,Runtime_sum=result['Runtime'],Work_sum=result['Work'],
            charged_Runtime=result['charged_Runtime'],unknown_native_charge=not known,
            original_cutoff_cap_seconds=1200,total_cap_seconds=3600,budget_PASS=result['native_runtime_budget_PASS'],
            cutoff_result='ORIGINAL_CUTOFF_RESULT.json',vehicle_calls=0,vehicle_runtime=0,
            controller_wall_seconds=result['controller_wall_seconds'],CPU_seconds=result['controller_CPU_seconds'],
            peak_RSS_bytes=resource.peak,threads_per_worker=1,RAM_based_stop=False,
            native_analytical_and_DP_calls=0,unspent_budget_seconds=3600-result['charged_Runtime'],
            registered_vehicle_calls_pending=True,vehicle_fields_are_not_final_until_aggregate_ledger=True))
        print('ORIGINAL_CUTOFF_COMPLETED',json.dumps(clean(result)),flush=True)
if __name__=='__main__':main()
