"""Spawn-only independent Env/Model; exactly one optimize per registered child."""
from .common import *
from .domain import child_data
from .repair import repair_multiplier
from v42_physics_redesign.exact_cut import certify,construct
from v42_b2_root_validation.certificate import verify_certificate
import gurobipy as gp
import traceback
import psutil

def run_worker(candidate,value,start_event,cancel_event,messages):
    label=candidate['candidate'];folder=WORK/'children'/label/f'z{value}'
    folder.mkdir(parents=True,exist_ok=True);begin=time.perf_counter();model=None;env=None;calls=0
    result=dict(candidate=label,value=value,column=candidate['column'],variable=candidate['variable_name'],
        native_calls=0,executed=False,certificate_PASS=False,PID=os.getpid(),creation_epoch=psutil.Process().create_time())
    try:
        gate=read(REPORTS/'REVISED_EXECUTION_GATE.json');assert gate['execution_allowed']
        assert gate['loss_threshold_is_diagnostic_only'] and gate['independent_exact_certificate_PASS']
        assert read(REPORTS/'BRANCH_DOMAIN_AUDIT.json')['PASS']
        assert (REPORTS/'PARALLEL_EXECUTION_PREREGISTRATION_KO.md').exists()
        assert not (folder/'NATIVE_CALL_STARTED.json').exists(),'NO_CHILD_RERUN'
        for key in ('TEMP','TMP','TMPDIR'):os.environ[key]=str(folder/'tmp')
        (folder/'tmp').mkdir(exist_ok=True)
        load_start=time.perf_counter();A,d,T,AA,full=model_inputs();child=child_data(full,candidate['column'],value)
        result['data_loading_seconds']=time.perf_counter()-load_start
        build_start=time.perf_counter();env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
        from v42_redundancy.model import build
        model=build(AA,child,env=env)
        for k,v in CHILD_SETTINGS.items():model.setParam(k,v)
        model.Params.LogFile=str(folder/'NATIVE_SOLVER.log');model.Params.NodefileDir=str(folder/'tmp')
        model.Params.LogToConsole=0;model.Params.OutputFlag=1;model.update()
        actual=model.getA().tocsr()
        assert actual.data.tobytes()==AA.data.tobytes() and np.array_equal(actual.indices,AA.indices) and np.array_equal(actual.indptr,AA.indptr)
        for n,attribute in [('objective','Obj'),('lower','LB'),('upper','UB'),('rhs','RHS')]:assert np.asarray(model.getAttr(attribute)).tobytes()==child[n].tobytes(),n
        assert np.float64(model.ObjCon).tobytes()==child['constant'].tobytes() and model.ModelSense==1
        assert np.array_equal(model.getAttr('Sense'),child['sense']) and np.array_equal(model.getAttr('VarName'),child['names'])
        assert np.array_equal(model.getAttr('ConstrName'),child['row_names']) and all(v=='C' for v in model.getAttr('VType'))
        parameters={k:model.getParamInfo(k)[2] for k in CHILD_SETTINGS};assert parameters==CHILD_SETTINGS
        assert model.getParamInfo('MemLimit')[2]==model.getParamInfo('MemLimit')[5]
        assert model.getParamInfo('SoftMemLimit')[2]==model.getParamInfo('SoftMemLimit')[5]
        identity=dict(PASS=True,parameters=parameters,objective_identity=prior.objective_identity(A,d),
            rows=model.NumConstrs,columns=model.NumVars,nnz=model.NumNZs,original_CSR_bit_identity=True,
            original_RHS_senses_axis_bit_identity=True,one_binary_bound_fix=True,selected_column=candidate['column'],selected_value=value,
            all_other_bounds_bit_identity=True,all_native_types_C=True,source_MILP_types_unchanged=True,
            own_Env_Model=True,MemLimit='default infinity',SoftMemLimit='default infinity')
        write(folder/'MODEL_IDENTITY.json',identity);result['model_build_and_guard_seconds']=time.perf_counter()-build_start
        ready=time.perf_counter();messages.put(dict(kind='ready',candidate=label,value=value,PID=os.getpid(),license_environment_acquired=True))
        while not start_event.wait(.1):
            if cancel_event.is_set():result.update(reason='CONTROLLER_ADMISSION_CANCELLED',worker_wait_seconds=time.perf_counter()-ready);return
        result['worker_wait_seconds']=time.perf_counter()-ready
        assert not cancel_event.is_set()
        with (folder/'NATIVE_CALL_STARTED.json').open('x',encoding='utf-8') as f:json.dump(dict(maximum_calls=1,TimeLimit=480,source_HEAD=BASE187),f)
        calls=1;result.update(native_calls=1,executed=True,native_start_epoch=time.time())
        messages.put(dict(kind='native_started',candidate=label,value=value,PID=os.getpid(),epoch=result['native_start_epoch']))
        trajectory=[];errors=[];native_start=time.perf_counter();raw_optimize=gp.Model.optimize
        def once(m,*args,**kwargs):
            assert m is model and not getattr(once,'used',False);once.used=True;return raw_optimize(m,*args,**kwargs)
        gp.Model.optimize=once
        def callback(m,where):
            try:
                if where==gp.GRB.Callback.BARRIER:trajectory.append(dict(wall=time.perf_counter()-native_start,
                    iteration=m.cbGet(gp.GRB.Callback.BARRIER_ITRCNT),primal=m.cbGet(gp.GRB.Callback.BARRIER_PRIMOBJ),
                    dual=m.cbGet(gp.GRB.Callback.BARRIER_DUALOBJ),primal_inf=m.cbGet(gp.GRB.Callback.BARRIER_PRIMINF),dual_inf=m.cbGet(gp.GRB.Callback.BARRIER_DUALINF)))
            except Exception as e:errors.append(repr(e))
        # Callback constants were verified in the solver-free preflight.
        model.optimize(callback)
        result.update(native_end_epoch=time.time(),native_controller_wall_seconds=time.perf_counter()-native_start)
        raw={};missing={}
        for attr,key in [('X','x'),('Pi','pi'),('RC','rc'),('Slack','slack'),('FarkasDual','farkas')]:
            try:raw[key]=np.asarray(model.getAttr(attr))
            except (gp.GurobiError,AttributeError) as e:missing[attr]=str(e)
        save(folder/'RAW.npz',**raw)
        for attr in ('Status','Runtime','Work','IterCount','BarIterCount','ObjVal','ObjBound','ConstrVio','BoundVio','DualVio','ComplVio','Kappa','KappaExact'):
            try:result[attr]=getattr(model,attr)
            except (gp.GurobiError,AttributeError) as e:missing[attr]=str(e)
        result.update(raw_saved_before_certificate=True,missing_attributes=missing,callback_errors=errors)
        write(folder/'NATIVE_RESULT.json',result);table(folder/'BARRIER_TRAJECTORY.csv',trajectory,fields=['wall','iteration','primal','dual','primal_inf','dual_inf'])
        gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(AssertionError('POST_CHILD_OPTIMIZE_FORBIDDEN'))
        model.dispose();model=None;env.dispose();env=None
        messages.put(dict(kind='native_finished',candidate=label,value=value,PID=os.getpid(),Runtime=result['Runtime'],Work=result['Work']))
        cert_start=time.perf_counter()
        if result['Status']==2 and 'pi' in raw:
            base=certify(AA,child,np.array([],dtype=int),raw['pi'],folder/'EXACT_BASE','optimality')
            accepted=base['accepted'];assert accepted and accepted['PASS']
            independent_base=verify_certificate(AA,child,accepted)
            with np.load(accepted['npz_path']) as f:pi=f['pi'].copy();residual=f['stationarity'].copy()
            repaired,rows,target=repair_multiplier(AA,child,pi,residual)
            save(folder/'EQUALITY_REPAIRED_MULTIPLIER.npz',pi=repaired,raw_pi=raw['pi'],sign_cone_pi=pi)
            table(folder/'EQUALITY_REPAIR_ROWS.csv',rows)
            fixed=construct(AA,child,np.array([],dtype=int),repaired,folder/'EXACT_EQUALITY_REPAIRED')
            independent_fixed=verify_certificate(AA,child,fixed)
            candidates=[(accepted,independent_base),(fixed,independent_fixed)]
            selected=max(candidates,key=lambda v:__import__('fractions').Fraction(v[0]['exact_alpha']))
            proof=dict(PASS=True,base=base,base_independent=independent_base,equality_repaired=fixed,
                equality_repaired_independent=independent_fixed,accepted=selected[0],independent=selected[1],
                selected_proof='BASE' if selected[0] is accepted else 'EQUALITY_REPAIRED',valid_for_child_full_domain=True,
                selected_binary_bound_only=[candidate['column'],value],native_calls_in_certificate=0)
            result.update(certificate_PASS=True,exact_LB=selected[1]['certified_LB'],certificate_loss=result['ObjVal']-selected[1]['certified_LB'],
                certificate_quality_within_1e4=abs(result['ObjVal']-selected[1]['certified_LB'])<=1e-4,
                strict_primal_replay=hc.replay(AA,child,raw['x'],False),original_C3A_primal_replay=hc.replay(A,d,raw['x'],False))
            write(folder/'EXACT_CERTIFICATE.json',proof)
        elif result['Status']==3 and 'farkas' in raw:
            proof=certify(AA,child,np.array([],dtype=int),-raw['farkas'],folder/'EXACT_FARKAS','feasibility')
            mathematical=dict(child,objective=np.zeros(AA.shape[1]),constant=np.array(0.))
            accepted=proof.get('accepted')
            if accepted:
                independent=verify_certificate(AA,mathematical,accepted)
                result['infeasibility_certificate_PASS']=independent['certified_LB']>0
                result['certificate_PASS']=result['infeasibility_certificate_PASS']
                write(folder/'EXACT_CERTIFICATE.json',dict(producer=proof,independent=independent,PASS=result['certificate_PASS']))
        else:result['certificate_reason']='NO_COMPLETED_OPTIMAL_POINT_OR_INDEPENDENT_INFEASIBILITY_PROOF'
        result['exact_certificate_seconds']=time.perf_counter()-cert_start
    except Exception as e:
        result.update(error=repr(e),traceback=traceback.format_exc(),certificate_PASS=False)
        messages.put(dict(kind='worker_error',candidate=label,value=value,PID=os.getpid(),error=repr(e)))
    finally:
        if model is not None:model.dispose()
        if env is not None:env.dispose()
        result.update(worker_total_wall_seconds=time.perf_counter()-begin,native_calls=calls)
        write(folder/'RESULT.json',result);messages.put(dict(kind='done',candidate=label,value=value,PID=os.getpid(),result=str(folder/'RESULT.json')))
