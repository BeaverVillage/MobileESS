"""Instrument the unchanged PR185 root entry point for exactly one native call."""
from v42_physics_redesign.common import *
import runpy
import gurobipy as gp

def main():
    identity=read(REPORTS/'B2_ROOT_SOURCE_IDENTITY.json');assert identity['PASS']
    assert (REPORTS/'B2_ROOT_EXECUTION_PREREGISTRATION.md').exists()
    assert not (WORK/'checkpoints/B2_EXECUTION_ATTEMPT.json').exists(),'NO_REPEAT_ENTRY_POINT'
    write(WORK/'checkpoints/B2_EXECUTION_ATTEMPT.json',dict(maximum_native_calls=1,TimeLimit=900,source_HEAD=identity['base_HEAD']))
    calls=0;native=gp.Model.optimize;messages=[];presolve=[];errors=[]
    def once(model,callback=None):
        nonlocal calls
        assert calls==0
        actual={k:model.getParamInfo(k)[2] for k in SETTINGS}
        assert actual==SETTINGS
        assert model.ModelSense==1 and model.NumConstrs==583459 and model.NumVars==306040 and model.NumNZs==5352914
        assert all(t=='C' for t in model.getAttr('VType'))
        assert model.getParamInfo('MemLimit')[2]==model.getParamInfo('MemLimit')[5]
        assert model.getParamInfo('SoftMemLimit')[2]==model.getParamInfo('SoftMemLimit')[5]
        A,d,_=hc.load();T=sparse.load_npz(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz').tocsr();actual_A=model.getA().tocsr()
        for expected,observed in ((A,actual_A[:A.shape[0]]),(T,actual_A[A.shape[0]:])):
            assert np.array_equal(expected.indptr,observed.indptr) and np.array_equal(expected.indices,observed.indices)
            assert expected.data.tobytes()==observed.data.tobytes()
        assert np.asarray(model.getAttr('Obj')).tobytes()==d['objective'].tobytes()
        assert np.float64(model.ObjCon).tobytes()==d['constant'].tobytes()
        assert np.asarray(model.getAttr('LB')).tobytes()==d['lower'].tobytes()
        assert np.asarray(model.getAttr('UB')).tobytes()==d['upper'].tobytes()
        assert np.array_equal(model.getAttr('VarName'),d['names'])
        write(REPORTS/'B2_ACTUAL_SOLVER_SETTINGS.json',dict(PASS=True,parameters=actual,
            MemLimit='default infinity',SoftMemLimit='default infinity',original_CSR_native_bit_transport_PASS=True,
            source_MILP_types_preserved=True,relaxed_native_types='all C',objective_native_bit_identity_PASS=True))
        calls+=1;begin=time.perf_counter()
        write(WORK/'checkpoints/B2_NATIVE_CALL_LEDGER.json',dict(native_calls=calls,started=True,completed=False,maximum_calls=1))
        def joined(m,where):
            try:
                if where==gp.GRB.Callback.MESSAGE:messages.append(m.cbGet(gp.GRB.Callback.MSG_STRING))
                if where==gp.GRB.Callback.PRESOLVE:
                    presolve.append(dict(wall=time.perf_counter()-begin,rows_removed=m.cbGet(gp.GRB.Callback.PRE_ROWDEL),columns_removed=m.cbGet(gp.GRB.Callback.PRE_COLDEL)))
            except Exception as e:errors.append(repr(e))
            if callback is not None:callback(m,where)
        native(model,joined)
        # Save the raw arrays and attributes before any certificate/replay.
        raw={};missing={}
        for attribute,key in [('X','x'),('Pi','pi'),('RC','rc'),('Slack','slack')]:
            try:raw[key]=np.asarray(model.getAttr(attribute))
            except gp.GurobiError as e:missing[attribute]=str(e)
        save(WORK/'artifacts/B2_ROOT_RAW.npz',**raw)
        values={}
        for attribute in ['Status','Runtime','Work','IterCount','BarIterCount','SolCount','ObjVal','ObjBound','ConstrVio','BoundVio','DualVio','ComplVio','Kappa','KappaExact']:
            try:values[attribute]=getattr(model,attribute)
            except (gp.GurobiError,AttributeError) as e:missing[attribute]=str(e)
        (WORK/'logs/B2_CALLBACK_MESSAGES.log').write_text(''.join(messages),encoding='utf-8')
        table(WORK/'logs/B2_PRESOLVE_TRAJECTORY.csv',presolve,fields=['wall','rows_removed','columns_removed'])
        write(REPORTS/'B2_ROOT_NATIVE_RESULT.json',dict(executed=True,native_optimize_calls=calls,
            **values,parameters=actual,rows=model.NumConstrs,columns=model.NumVars,nnz=model.NumNZs,
            controller_native_wall_seconds=time.perf_counter()-begin,raw_saved_before_certificate=True,
            missing_attributes=missing,callback_errors=errors))
        write(WORK/'checkpoints/B2_NATIVE_CALL_LEDGER.json',dict(native_calls=calls,started=True,completed=True,Status=model.Status,maximum_calls=1))
    gp.Model.optimize=once
    try:runpy.run_module('v42_physics_redesign.root',run_name='__main__')
    finally:
        gp.Model.optimize=lambda *a,**k:(_ for _ in ()).throw(AssertionError('ADDITIONAL_OPTIMIZE_FORBIDDEN'))
        write(WORK/'checkpoints/B2_FINAL_NATIVE_CALL_COUNT.json',dict(native_calls=calls,maximum_calls=1))
    result=read(REPORTS/'ROOT_RESULT.json')
    if not calls:
        assert not result['executed']
        write(REPORTS/'B2_ROOT_NATIVE_RESULT.json',dict(executed=False,native_optimize_calls=0,
            Status=None,Runtime=None,Work=None,ObjVal=None,charged_native_Runtime=0,
            reason=result['reason'],model_size_source='PR185 original plus verified temporal CSR',
            rows=583459,columns=306040,nnz=5352914))
        save(WORK/'artifacts/B2_ROOT_RAW.npz',native_execution_present=np.array(False))
    print('B2_EXECUTION_FINISHED',calls,flush=True)

if __name__=='__main__':main()
