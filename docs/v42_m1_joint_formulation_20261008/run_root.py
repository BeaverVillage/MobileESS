"""One guarded 600s original-objective LP per registered formulation."""
from common import *
import threading,traceback,psutil

def arrays_for(label):
    A,d,_=load();n=A.shape[1]
    if label=='ORIGINAL':return A,d,n
    B=sparse.load_npz(OUT/f'{label}_ADDED_MATRIX.npz').tocsr()
    with np.load(OUT/f'{label}_DATA.npz') as z:e={k:z[k] for k in z.files}
    full=sparse.vstack([sparse.hstack([A,sparse.csr_matrix((A.shape[0],B.shape[1]-n))]),B],format='csr');return full,e,n

def run(label):
    assert label in ['ORIGINAL','A','B'];assert read(OUT/'BOUNDED_EXACTNESS_TESTS.json')['PASS'];assert read(OUT/'CENTER_FULL_REPLAY.json')['PASS']
    if label!='ORIGINAL':
        proof=read(OUT/f'{label}_EXACTNESS_VERIFICATION.json');assert proof['PASS']
        assert proof['matrix_SHA256']==sha(OUT/f'{label}_ADDED_MATRIX.npz') and proof['data_SHA256']==sha(OUT/f'{label}_DATA.npz') and proof['spec_SHA256']==sha(OUT/f'{label}_SPEC.json')
    if label=='B':assert read(OUT/'A_MATERIALITY_GATE.json')['PASS'] is False
    folder=OUT/'runs'/label;folder.mkdir(parents=True,exist_ok=True);assert not (folder/'OPTIMIZE_ONCE.json').exists()
    runner_source=Path(__file__).read_bytes();(folder/'RUNNER_SOURCE.py').write_bytes(runner_source)
    A,d,n=arrays_for(label);original,od,_=load();identity=objective_identity(original,od)
    assert d['objective'][:n].tobytes()==od['objective'].tobytes() and d['constant'].tobytes()==od['constant'].tobytes() and np.array_equal(d['names'][:n],od['names'])
    assert not np.any(d['objective'][n:].view(np.uint64));e=dict(d,types=np.full(A.shape[1],'C'))
    import gurobipy as gp
    from v42_redundancy.model import build
    from v42_integrated.matrix import arrays
    begin=time.perf_counter();process=psutil.Process();memory_before=psutil.virtual_memory()._asdict();m=build(A,e)
    for key,value in SETTINGS.items():m.setParam(key,value)
    m.Params.LogToConsole=0;m.Params.OutputFlag=1;m.Params.LogFile=str(folder/'NATIVE_SOLVER.log');m.update()
    actual,transport=arrays(m);assert actual.shape==A.shape and (actual!=A).nnz==0
    for key in e:assert np.array_equal(e[key],transport[key]),('NATIVE_TRANSPORT_CHANGED',key)
    # NumPy widens the unified string dtype when longer auxiliary names are
    # appended. Verify actual native original strings before canonicalizing
    # ONLY their storage dtype to the original axis dtype; no truncation.
    assert np.array_equal(transport['names'][:n],od['names'])
    original_native_names=np.asarray(transport['names'][:n],dtype=od['names'].dtype)
    assert np.array_equal(original_native_names,transport['names'][:n])
    assert m.ModelSense==1;native_identity=verifier.verify(ROOT,dict(names=original_native_names,objective=transport['objective'][:n],constant=transport['constant']),int(m.ModelSense));assert native_identity['PASS']
    atomic(folder/'MODEL_IDENTITY.json',dict(PASS=True,objective=native_identity,original_A_SHA256=sha(hc.PARENT/'C3A_A.npz'),original_DATA_SHA256=sha(hc.PARENT/'C3A_DATA.npz'),new_variable_objective_exact_positive_zero=True,original_variable_axis_prefix_identical=True,only_root_B_relaxation=True,rows=A.shape[0],columns=A.shape[1],nnz=A.nnz))
    atomic(folder/'SOLVER_PARAMETERS.json',prior.parameters(m));setup=time.perf_counter()-begin;rss=[];stop=threading.Event();events=[];errors=[];last=-30.
    def monitor():
        while not stop.is_set():rss.append(process.memory_info().rss);stop.wait(.5)
    t=threading.Thread(target=monitor,daemon=True);t.start();original_optimize=gp.Model.optimize;calls=0
    def guarded(model,*args,**kwargs):
        nonlocal calls
        assert model is m and calls==0;assert read(OUT/'BOUNDED_EXACTNESS_TESTS.json')['PASS'];assert native_identity['PASS']
        with (folder/'OPTIMIZE_ONCE.json').open('x',encoding='utf-8') as f:json.dump(dict(label=label,optimize_calls=1,UTC=stamp(),source_commit=git('rev-parse','HEAD'),runner_source_SHA256=hashlib.sha256(runner_source).hexdigest(),TimeLimit=600,Threads=1,original_scientific_objective=True),f,indent=2)
        calls+=1;return original_optimize(model,*args,**kwargs)
    gp.Model.optimize=guarded
    def callback(model,where):
        nonlocal last
        if where==gp.GRB.Callback.POLLING:return
        try:
            runtime=float(model.cbGet(gp.GRB.Callback.RUNTIME))
            if where==gp.GRB.Callback.BARRIER:
                event=dict(Runtime=runtime,iterations=int(model.cbGet(gp.GRB.Callback.BARRIER_ITRCNT)),primal_objective=float(model.cbGet(gp.GRB.Callback.BARRIER_PRIMOBJ)),dual_objective=float(model.cbGet(gp.GRB.Callback.BARRIER_DUALOBJ)),primal_infeasibility=float(model.cbGet(gp.GRB.Callback.BARRIER_PRIMINF)),dual_infeasibility=float(model.cbGet(gp.GRB.Callback.BARRIER_DUALINF)))
                events.append(event)
            if runtime-last>=30:last=runtime;print('ROOT_PROGRESS',label,round(runtime,3),flush=True)
        except BaseException:errors.append(traceback.format_exc());model.terminate()
    exception=None
    try:m.optimize(callback)
    except BaseException:exception=traceback.format_exc()
    finally:gp.Model.optimize=original_optimize;stop.set();t.join(timeout=2);rss.append(process.memory_info().rss)
    status=int(m.Status);result=dict(label=label,UTC=stamp(),native_status=status,status_name={2:'OPTIMAL',9:'TIME_LIMIT',11:'INTERRUPTED',13:'SUBOPTIMAL'}.get(status,str(status)),Runtime=float(m.Runtime),Work=float(m.Work),IterCount=float(m.IterCount),BarIterCount=int(m.BarIterCount),setup_wall_seconds=setup,total_wall_seconds=time.perf_counter()-begin,rows=A.shape[0],columns=A.shape[1],nnz=A.nnz,native_LP_objective=None,raw_native_ObjBound=None,valid_LB=None,certificate_loss=None,optimal_certificate_PASS=False,objective_identity_PASS=True,original_integer_projection_unchanged=True,optimize_calls=calls,peak_sampled_RSS=max(rss),Windows_lifetime_peak_wset=getattr(process.memory_info(),'peak_wset',None),memory_before=memory_before,callback_errors=errors,exception=exception)
    try:result['raw_native_ObjBound']=float(m.ObjBound)
    except (gp.GurobiError,AttributeError):pass
    if status==2 and not errors and exception is None:
        x=np.asarray(m.getAttr('X'));pi=np.asarray(m.getAttr('Pi'));rc=np.asarray(m.getAttr('RC'));save_vector(folder/'LP_POINT_DUAL.npz',x=x,Pi=pi,RC=rc)
        certificate,_,_,_=hc.exact_bounded_lagrangian(A,d,pi);certificate.update(PASS=True,OPTIMAL_native_status=2,vector_SHA256=sha(folder/'LP_POINT_DUAL.npz'),original_objective_hash=identity['source_objective_SHA256'],integer_projection_equivalence=label=='ORIGINAL' or read(OUT/f'{label}_EXACTNESS_VERIFICATION.json')['PASS'])
        atomic(folder/'EXACT_LB_CERTIFICATE.json',certificate)
        # Read saved vectors and immutable compiled matrix independently.
        independent_A,independent_d,_=arrays_for(label)
        with np.load(folder/'LP_POINT_DUAL.npz') as z:independent_pi=z['Pi'].copy()
        independent,_,_,_=hc.exact_bounded_lagrangian(independent_A,independent_d,independent_pi)
        assert independent['exact_rational']==certificate['exact_rational'];assert F(certificate['exact_rational'])<=F.from_float(UB)
        check=hc.replay(A,dict(d,types=np.full(A.shape[1],'C')),x,False);mask=od['types']=='B';values=x[:n][mask]
        result.update(native_LP_objective=float(m.ObjVal),valid_LB=certificate['lower_bound'],valid_LB_exact=certificate['exact_rational'],certificate_loss=float(m.ObjVal)-float(F(certificate['exact_rational'])),optimal_certificate_PASS=True,independent_exact_certificate_PASS=True,raw_strengthened_LP_replay=check,original_rows_relaxed_replay=hc.replay(original,dict(od,types=np.full(n,'C')),x[:n],False),fractional_original_binary_count=int(np.count_nonzero(np.minimum(abs(values),abs(1-values))>1e-8)),original_binaries=mask.sum())
    else:
        try:save_vector(folder/'UNRESOLVED_POINT.npz',x=np.asarray(m.getAttr('X')))
        except (gp.GurobiError,AttributeError):pass
    table(folder/'BARRIER_TRACE.csv',events)
    m.dispose();log=(folder/'NATIVE_SOLVER.log').read_text(encoding='utf-8');result['numerical_warnings']=[line for line in log.splitlines() if re.search(r'warning|numerical trouble|unscaled.*violation|quad precision',line,re.I)];result['factor_memory_log']=[line for line in log.splitlines() if 'Factor NZ' in line or 'AA\' NZ' in line or 'Factor Ops' in line]
    result['NATIVE_LOG_SHA256']=sha(folder/'NATIVE_SOLVER.log');result['total_wall_seconds']=time.perf_counter()-begin;atomic(folder/'RESULT.json',result);print('ROOT_COMPLETE',label,json.dumps(clean(result)),flush=True)
    return result
if __name__=='__main__':run(sys.argv[1])
