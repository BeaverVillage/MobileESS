"""One distinct B2 ROOT pilot after exactness AND resource admission."""
from .common import *
from .resource import inspect,Monitor
from .exact_cut import certify

def main():
    gate=read(WORK/'checkpoints/ROOT_EQUIVALENCE_GATE.json');assert gate['PASS']
    assert (REPORTS/'ROOT_PREREGISTRATION.md').exists()
    assert gate['temporal_rows_sha256']==sha(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz') and gate['temporal_data_sha256']==sha(WORK/'artifacts/TEMPORAL_VALID_ROW_DATA.npz')
    if gate['B2_distinct_rows']==0:
        write(REPORTS/'ROOT_RESULT.json',dict(executed=False,native_optimize_calls=0,reason='NO_DISTINCT_STRENGTHENING_CANDIDATE',new_certified_LB=LB,material_gate_PASS=False));return
    admission=inspect('ROOT_immediate_resource_admission');write(REPORTS/'PROCESS_ISOLATION_AUDIT.json',read(REPORTS/'RESOURCE_ISOLATION_AUDIT.json'))
    if not admission['admission_PASS']:
        write(REPORTS/'ROOT_RESULT.json',dict(executed=False,native_optimize_calls=0,reason='RESOURCE_ISOLATION_PENDING',model_size_source='Structural CSR measurement, not native presolve',Runtime=None,Work=None,charged_native_Runtime=0,charged_native_Work=0,controller_resource_sample_seconds=admission['wall_sample_seconds'],new_certified_LB=LB,material_gate_PASS=False,canary_calls=0,production_calls=0));print('ROOT_NOT_STARTED_RESOURCE_PENDING',flush=True);return
    import gurobipy as gp
    from v42_redundancy.model import build
    token=WORK/'checkpoints/B2_ROOT_ONCE.json';assert not token.exists(),'NO_DUPLICATE_ROOT_RUN'
    A,d,_=hc.load();identity=prior.objective_identity(A,d);T=sparse.load_npz(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz').tocsr()
    with np.load(WORK/'artifacts/TEMPORAL_VALID_ROW_DATA.npz') as f:rhs=f['rhs'].copy()
    augmented=sparse.vstack([A,T],format='csr');full=dict(d,rhs=np.r_[d['rhs'],rhs],sense=np.r_[d['sense'],np.full(len(rhs),'<')],row_names=np.r_[d['row_names'],np.array([f'temporal_reachability[{i}]' for i in range(len(rhs))])]);relaxed=dict(full,types=np.full(A.shape[1],'C'))
    build_start=time.perf_counter();m=build(augmented,relaxed)
    try:
        for k,v in SETTINGS.items():m.setParam(k,v)
        m.Params.LogFile=str(WORK/'logs/B2_ROOT_NATIVE.log');m.Params.LogToConsole=0;m.Params.OutputFlag=1;m.Params.NodefileDir=str(WORK/'tmp');m.update()
        assert (m.getA()[:A.shape[0]]!=A).nnz==0 and (m.getA()[A.shape[0]:]!=T).nnz==0
        assert m.ModelSense==1 and np.asarray(m.getAttr('Obj')).tobytes()==d['objective'].tobytes() and np.float64(m.ObjCon).tobytes()==d['constant'].tobytes()
        assert np.asarray(m.getAttr('RHS')).tobytes()==full['rhs'].tobytes() and np.array_equal(np.asarray(m.getAttr('Sense')),full['sense'])
        assert np.array_equal(np.asarray(m.getAttr('ConstrName')),full['row_names']) and all(v=='C' for v in m.getAttr('VType'))
        assert np.array_equal(np.asarray(m.getAttr('VarName')),d['names']) and np.array_equal(np.asarray(m.getAttr('LB')),d['lower']) and np.array_equal(np.asarray(m.getAttr('UB')),d['upper'])
        assert m.getParamInfo('MemLimit')[2]==m.getParamInfo('MemLimit')[5] and m.getParamInfo('SoftMemLimit')[2]==m.getParamInfo('SoftMemLimit')[5]
        paths_audit('B2_native_model_original_identity',m)
        admission=inspect('B2_after_build_final_resource_admission')
        write(REPORTS/'PROCESS_ISOLATION_AUDIT.json',read(REPORTS/'RESOURCE_ISOLATION_AUDIT.json'))
        if not admission['admission_PASS']:
            write(REPORTS/'ROOT_RESULT.json',dict(executed=False,native_optimize_calls=0,reason='RESOURCE_ISOLATION_PENDING',Runtime=None,Work=None,charged_native_Runtime=0,charged_native_Work=0,controller_resource_sample_seconds=admission['wall_sample_seconds'],native_model_build_wall_seconds=time.perf_counter()-build_start,new_certified_LB=LB,material_gate_PASS=False));return
        parameters={k:m.getParamInfo(k)[2] for k in SETTINGS};parameters.update(MemLimit='unchanged default infinity',SoftMemLimit='unchanged default infinity',LogFile=m.Params.LogFile,NodefileDir=m.Params.NodefileDir)
        write(REPORTS/'ROOT_SOLVER_PARAMETERS.json',dict(parameters=parameters,objective_identity=identity,source_modules={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'v42_physics_redesign').glob('*.py')},build_wall_seconds=time.perf_counter()-build_start,rows=m.NumConstrs,cols=m.NumVars,nnz=m.NumNZs,original_all_rows_retained=True))
        with token.open('x',encoding='utf-8') as f:json.dump(dict(maximum_optimize_calls=1,TimeLimit=900,Threads=1,source_BASE=BASE,preregistration_SHA256=sha(REPORTS/'ROOT_PREREGISTRATION.md')),f,indent=2)
        events=[];callback_errors=[];start=time.perf_counter()
        def callback(model,where):
            try:
                if where==gp.GRB.Callback.BARRIER:events.append(dict(wall=time.perf_counter()-start,iteration=model.cbGet(gp.GRB.Callback.BARRIER_ITRCNT),primal_objective=model.cbGet(gp.GRB.Callback.BARRIER_PRIMOBJ),dual_objective=model.cbGet(gp.GRB.Callback.BARRIER_DUALOBJ),primal_inf=model.cbGet(gp.GRB.Callback.BARRIER_PRIMINF),dual_inf=model.cbGet(gp.GRB.Callback.BARRIER_DUALINF)))
            except Exception as e:callback_errors.append(repr(e))
        calls=0;original_optimize=gp.Model.optimize
        def once(model,*args,**kwargs):
            nonlocal calls
            assert model is m and calls==0;calls+=1;return original_optimize(model,*args,**kwargs)
        gp.Model.optimize=once
        with Monitor() as monitor:m.optimize(callback)
        wall=time.perf_counter()-start;raw={};missing={}
        for attr,key in [('X','x'),('Pi','pi'),('RC','rc'),('Slack','slack')]:
            try:raw[key]=np.array(m.getAttr(attr))
            except gp.GurobiError as e:missing[attr]=str(e)
        save(WORK/'artifacts/B2_ROOT_RAW.npz',**raw)
        result=dict(executed=True,native_optimize_calls=calls,Status=m.Status,Runtime=m.Runtime,Work=m.Work,IterCount=m.IterCount,BarIterCount=m.BarIterCount,SolCount=m.SolCount,peak_RSS=monitor.peak,controller_optimize_wall_seconds=wall,TimeLimit_overshoot_seconds=max(0.,m.Runtime-900),rows=m.NumConstrs,cols=m.NumVars,nnz=m.NumNZs,raw_saved_before_validation=True,missing_attributes=missing,callback_errors=callback_errors,new_certified_LB=LB,material_gate_PASS=False,native_ObjBound_not_used=True)
        write(REPORTS/'ROOT_RESULT.json',result);table(WORK/'logs/B2_ROOT_TRAJECTORY.csv',events)
        # The same fresh worker cannot optimize again during proof recovery.
        gp.Model.optimize=lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('POST_ROOT_OPTIMIZE_FORBIDDEN'))
        if m.Status==2 and 'pi' in raw and not callback_errors:
            proof=certify(augmented,full,np.array([],dtype=int),raw['pi'],WORK/'artifacts/B2_EXACT_LB','optimality');accepted=proof.get('accepted')
            if accepted and accepted['PASS']:
                candidate=float(F(accepted['exact_alpha']))
                if F.from_float(candidate)>F(accepted['exact_alpha']):candidate=float(np.nextafter(candidate,-np.inf))
                assert candidate<=UB+1e-8
                result.update(new_certified_LB=max(LB,candidate),exact_candidate_LB=candidate,certified_improvement=max(0.,candidate-LB),material_gate_PASS=candidate-LB>=.001 and m.Runtime<=900,raw_relaxed_original_replay=hc.replay(A,d,raw['x'],False))
            write(REPORTS/'ROOT_LOWER_BOUND_CERTIFICATE.json',proof)
        result.update(canary_eligible=result['material_gate_PASS'],production_eligible=False,global_gap_percent=100*(UB-result['new_certified_LB'])/UB)
        write(REPORTS/'ROOT_RESULT.json',result);print('B2_ROOT_DONE',json.dumps(clean(result)),flush=True)
    finally:m.dispose()

if __name__=='__main__':
    from fractions import Fraction as F
    main()
