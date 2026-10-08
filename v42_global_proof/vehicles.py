"""One full-physical support MILP per vehicle. Numerical bounds remain diagnostic.

The independent exact DAG/energy bounds remain the authority for A3. A numerical
MIP bound is never silently substituted for an exact analytical upper bound.
"""
from .common import *
from fractions import Fraction as F
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import multiprocessing, gzip, threading, traceback
import psutil

PHYSICAL={'flow','connected_Pch','connected_Pdis','no_simultaneous_charge',
    'no_simultaneous_discharge','PCS16','node_activity_link','energy_balance','temporal_reachability'}
def csr_sha(A):return hashlib.sha256(A.indptr.tobytes()+A.indices.tobytes()+A.data.tobytes()).hexdigest()
def outward(x):
    v=float(x);return float(np.nextafter(v,np.inf)) if F.from_float(v)<x else v
def worker(unit):
    import gurobipy as gp
    began=time.perf_counter();proc=psutil.Process();cpu0=sum(proc.cpu_times()[:2]);peak=0
    folder=OUT/'vehicles'/unit;folder.mkdir(parents=True,exist_ok=True);env=None;model=None;calls=0
    result=dict(MESS=unit,native_calls=0,Runtime=0.,Work=0.,Status=None,
        exact_bound_adopted=False,numerical_MIP_bound_used_as_global_proof=False)
    stop=threading.Event();phase=['LOAD'];telemetry=[]
    def monitor():
        nonlocal peak
        while True:
            try:
                peak=max(peak,proc.memory_info().rss)
                telemetry.append(dict(wall_seconds=time.perf_counter()-began,phase=phase[0],RSS=proc.memory_info().rss,
                    process_CPU_seconds=sum(proc.cpu_times()[:2])-cpu0))
            except psutil.Error:pass
            if stop.wait(5):return
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        registration=read(OUT/'EXPERIMENT_PREREGISTRATION.json');assert registration['vehicle_native_calls_registered']==4
        for rel,h in registration['native_producer_source_sha256'].items():assert sha(ROOT/rel)==h,rel
        assert read(OUT/'OPTIMIZE_ZERO_GATE.json')['PASS']
        selected=read(OUT/'GRID_DEMAND_CERTIFICATE.json')['selected'];p=Path(selected['exact_artifact']['path'])
        assert sha(p)==registration['selected_grid_exact_sha256']
        proof=json.loads(gzip.decompress(p.read_bytes()))
        exactweights={int(r['column']):F(r['coefficient']) for r in proof['weights']}
        A,d,T,AA,dd=load()
        units=np.array([str(n).split('[',1)[1].split(',',1)[0] if '[' in str(n) else '' for n in d['names']])
        cols=np.flatnonzero(units==unit);assert len(cols)>0
        belongs=np.zeros(A.shape[1],dtype=bool);belongs[cols]=True
        family=np.array([str(n).split('[',1)[0] for n in dd['row_names']])
        candidates=np.flatnonzero(np.isin(family,list(PHYSICAL)));keep=[]
        for i in candidates:
            js=AA.indices[AA.indptr[i]:AA.indptr[i+1]]
            if len(js) and belongs[js].all():keep.append(int(i))
            elif len(js) and belongs[js].any():raise AssertionError('PHYSICAL_ROW_CROSSES_UNIT_BOUNDARY')
        keep=np.array(keep,dtype=int);local=AA[keep][:,cols].tocsr()
        ld={k:d[k][cols].copy() for k in ('names','lower','upper','types')}
        ld.update(rhs=dd['rhs'][keep].copy(),sense=dd['sense'][keep].copy(),row_names=dd['row_names'][keep].copy())
        localobj=np.array([float(exactweights.get(int(j),F(0))) for j in cols])
        conversion=F(0)
        for k,j in enumerate(cols):
            delta=exactweights.get(int(j),F(0))-F.from_float(float(localobj[k]))
            conversion+=max(delta*F.from_float(float(ld['lower'][k])),delta*F.from_float(float(ld['upper'][k])))
        phase[0]='BUILD';env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
        model=gp.Model('ORIGINAL_VEHICLE_SUPPORT_'+unit,env=env)
        v=model.addMVar(len(cols),lb=ld['lower'],ub=ld['upper'],vtype=ld['types'],obj=localobj)
        v.VarName=ld['names'].tolist();model.ModelSense=-1;model.ObjCon=0.
        c=model.addMConstr(local,v,ld['sense'],ld['rhs']);c.ConstrName=ld['row_names'].tolist()
        params=registration['vehicle_settings']
        for k,val in params.items():model.setParam(k,val)
        model.Params.LogFile=str(folder/'NATIVE.log');model.Params.OutputFlag=1;model.Params.LogToConsole=0
        model.Params.NodefileDir=str(OUT/'tmp');model.update()
        assert csr_sha(model.getA().tocsr())==csr_sha(local)
        for key,attr in [('lower','LB'),('upper','UB'),('types','VType'),('names','VarName'),('rhs','RHS'),('sense','Sense')]:
            assert np.array_equal(np.asarray(model.getAttr(attr)),ld[key]),key
        assert np.array_equal(np.asarray(model.getAttr('Obj')),localobj) and model.ModelSense==-1
        assert model.getParamInfo('MemLimit')[2]==model.getParamInfo('MemLimit')[5]
        assert model.getParamInfo('SoftMemLimit')[2]==model.getParamInfo('SoftMemLimit')[5]
        save(folder/'LOCAL_PROJECTION.npz',columns=cols,rows=keep,objective=localobj,
            lower=ld['lower'],upper=ld['upper'],types=ld['types'],rhs=ld['rhs'],sense=ld['sense'])
        counts=dict(Counter(family[keep]));counts={k:int(v) for k,v in counts.items()}
        assert counts['energy_balance']==96 and counts['PCS16']>0 and counts['flow']>0
        write(folder/'MODEL_IDENTITY.json',dict(PASS=True,MESS=unit,source_columns=len(cols),source_rows=len(keep),
            binary_count=int((ld['types']=='B').sum()),native_CSR_bit_identity=True,all_original_bounds_types_preserved=True,
            row_families=counts,source_CSR_sha256=csr_sha(local),objective_binary64_conversion_error_upper_exact=str(conversion),
            max_objective_is_diagnostic_only=True,grid_coupling_removed=True,original_vehicle_physics_retained=True,
            F_subset_local_R='Projection of every original full model solution satisfies every retained vehicle-only row',
            terminal_SOC_preserved_through_original_energy_rows_and_bounds=True,settings=params))
        token=folder/'OPTIMIZE_ONCE.json'
        with token.open('x',encoding='utf-8') as f:json.dump(dict(max_calls=1,max_Runtime=600,settings=params,PID=os.getpid()),f)
        calls=1;phase[0]='NATIVE';native_began=time.perf_counter();errors=[]
        def callback(m,where):
            try:
                if where!=gp.GRB.Callback.POLLING and m.cbGet(gp.GRB.Callback.RUNTIME)>=585:m.terminate()
            except Exception as e:errors.append(repr(e))
        model.optimize(callback)
        result.update(native_calls=1,Status=int(model.Status),Runtime=model.Runtime,Work=model.Work,
            NodeCount=model.NodeCount,SolCount=model.SolCount,native_wall_seconds=time.perf_counter()-native_began,
            callback_errors=errors,objective_conversion_error_upper_exact=str(conversion))
        for attr in ('ObjVal','ObjBound','IterCount','BarIterCount','ConstrVio','BoundVio','IntVio'):
            try:result[attr]=getattr(model,attr)
            except (gp.GurobiError,AttributeError):result[attr]=None
        if result.get('ObjBound') is not None:
            result['numerical_support_upper_after_conversion']=outward(F.from_float(float(result['ObjBound']))+conversion)
            result['numerical_bound_authority']='Solver MIP bound subject to scientific tolerance; no independent exact search-tree certificate'
        if model.SolCount:
            x=np.asarray(model.getAttr('X'));save(folder/'INCUMBENT.npz',x=x)
            residual=local@x-ld['rhs'];viol=np.where(ld['sense']=='=',abs(residual),np.where(ld['sense']=='<',residual,-residual))
            bound=max(float((ld['lower']-x).max(initial=0)),float((x-ld['upper']).max(initial=0)))
            integ=float(abs(x[ld['types']=='B']-np.rint(x[ld['types']=='B'])).max(initial=0))
            feasible=bool(np.isfinite(x).all() and viol.max(initial=0)<=1e-8 and bound<=1e-8 and integ<=1e-8)
            support=sum(exactweights.get(int(j),F(0))*F.from_float(float(x[k])) for k,j in enumerate(cols))
            result.update(local_incumbent_replay=dict(PASS=feasible,max_original_row_violation=float(viol.max(initial=0)),
                max_original_bound_violation=bound,max_original_integrality_violation=integ,scientific_tolerance=1e-8),
                incumbent_support_exact_evaluation=str(support),incumbent_support_float=float(support),
                incumbent_is_not_capacity_upper_bound=True)
        model.dispose();model=None;env.dispose();env=None
    except Exception as e:
        result.update(error=repr(e),traceback=traceback.format_exc(),native_calls=calls)
        if calls and model is not None:
            for attr in ('Runtime','Work','Status','SolCount','NodeCount'):
                try:result[attr]=getattr(model,attr)
                except (gp.GurobiError,AttributeError):result[attr]=None
            result['native_attribute_recovery_after_error']=True
    finally:
        if model is not None:model.dispose()
        if env is not None:env.dispose()
        stop.set();thread.join(10)
        known=result.get('Runtime') is not None
        result.update(controller_wall_seconds=time.perf_counter()-began,CPU_seconds=sum(proc.cpu_times()[:2])-cpu0,
            peak_RSS_bytes=peak,actual_Runtime_known=known,charged_Runtime=result['Runtime'] if known else 600.,
            native_runtime_budget_PASS=known and result['Runtime']<=600)
        write(folder/'RESOURCE.json',dict(telemetry=telemetry,peak_RSS_bytes=peak,no_RAM_based_stop=True))
        write(folder/'RESULT.json',result)
    return result

def main():
    assert not (OUT/'VEHICLE_EXPERIMENT_ONCE.json').exists(),'NO_VEHICLE_SWEEP_OR_RERUN'
    with (OUT/'VEHICLE_EXPERIMENT_ONCE.json').open('x',encoding='utf-8') as f:json.dump(dict(calls=4,max_workers=2),f)
    began=time.perf_counter();results=[]
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
        for result in pool.map(worker,['MESS01','MESS02','MESS03','MESS04']):
            results.append(result);print('VEHICLE_SUPPORT_RESULT',json.dumps(clean(result)),flush=True)
    known=all(r['actual_Runtime_known'] for r in results)
    write(OUT/'VEHICLE_NATIVE_RESULTS.json',dict(vehicles=results,Runtime_sum=sum(r['Runtime'] for r in results) if known else None,
        charged_Runtime_sum=sum(r['charged_Runtime'] for r in results),actual_Runtime_known=known,
        Work_sum=sum(r['Work'] for r in results) if all(r.get('Work') is not None for r in results) else None,
        native_calls=sum(r['native_calls'] for r in results),
        budget_PASS=all(r['native_runtime_budget_PASS'] for r in results),controller_wall_seconds=time.perf_counter()-began,
        exact_analytical_bounds_remain_authoritative=True,native_numerical_bounds_never_promoted_to_exact_proof=True))
if __name__=='__main__':main()
