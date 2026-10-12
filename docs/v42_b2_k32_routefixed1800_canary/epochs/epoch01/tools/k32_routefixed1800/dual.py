"""One conditional K48 plus independently verified fractional Grid rows MILP."""
import argparse,gc,math,time,traceback
from fractions import Fraction
from scipy import sparse
import numpy as np
from tools.k32_routefixed1800.adapter import *
from tools.u4_primal_alns.pilot import finite_attr

def data(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}

def main(seconds):
    out=DOCS/'dual';out.mkdir(parents=True,exist_ok=False)
    previous=ROOT/'docs/v42_critical_grid_cg/iteration02'
    grid=ROOT/'docs/v42_b2_root_lp_tightening/grid'
    base_lp=ROOT/'docs/v42_b2_root_lp_tightening/base'
    guard()
    from tools.b2_root_lp_tightening.verify import cut_validity
    proof=cut_validity('GRID',base_lp,grid)
    write(out/'EXACT_CUT_VALIDITY_RECHECK.json',proof);assert proof['PASS']
    parent=read(previous/'INDEPENDENT_CERTIFICATE.json');assert parent['PASS'] and parent['FULL_projection_subset_native_Joint']
    for name,digest in read(previous/'INDEPENDENT_NATIVE0.json')['file_sha256'].items():assert v.file_sha(previous/name)==digest
    packet=read(grid/'CUTS_EXACT.json');rows=packet['rows']
    A=sparse.load_npz(previous/'JOINT_A.npz').tocsr();d=data(previous/'JOINT_DATA.npz');oldrows=A.shape[0]
    assert not set(r['name'] for r in rows)&set(map(str,d['row_names']))
    rr=[];cc=[];vv=[]
    for i,row in enumerate(rows):
        for col,value in sorted(row['terms'].items(),key=lambda z:int(z[0])):
            rr.append(i);cc.append(int(col));vv.append(float(Fraction(value)))
    cuts=sparse.csr_matrix((vv,(rr,cc)),shape=(len(rows),A.shape[1]))
    A=sparse.vstack([A,cuts],format='csr')
    d['rhs']=np.r_[d['rhs'],[r['native_rhs'] for r in rows]]
    d['senses']=np.r_[d['senses'],np.full(len(rows),'<')]
    d['row_names']=np.r_[d['row_names'],[r['name'] for r in rows]]
    assert A.shape==(143324,244265) and np.count_nonzero(d['vtypes']=='B')==9322
    lp=sparse.load_npz(grid/'LP_A.npz').tocsr()
    assert v.matrix_sha(A)==v.matrix_sha(lp),'EXACT_VERIFIED_GRID_ROWS_MISMATCH'
    del lp;gc.collect()
    sparse.save_npz(out/'JOINT_A.npz',A);np.savez_compressed(out/'JOINT_DATA.npz',**d)
    shutil=__import__('shutil');shutil.copyfile(grid/'CUTS_EXACT.json',out/'CUTS_EXACT.json')
    files={name:v.file_sha(out/name) for name in ('JOINT_A.npz','JOINT_DATA.npz','CUTS_EXACT.json')}
    inclusion=dict(PASS=True,FULL_projection_subset_strengthened_K48=True,strengthened_K48_subset_K48=True,
        relaxation_preserves_original_integer_projection=True,original_binary_count=9322,added_original_rows=[r['name'] for r in rows],
        no_duplicate_K48_rows=True,parent_certificate=record(previous/'INDEPENDENT_CERTIFICATE.json'),
        independent_original_row_reconstruction=record(out/'EXACT_CUT_VALIDITY_RECHECK.json'),
        binary64_outward_rounding=True,fixed_AIDC_forecast_correction_preserved=True,files=files,
        not_plain_K32_BB_extension=True,PR214_same_grid_LP_was_incomplete_not_ineffective=True,
        MILP_with_restored_source_binary_types_is_new_mathematical_model=True)
    write(out/'INDEPENDENT_NATIVE0.json',inclusion)
    write(DOCS/'VALID_GRID_STRENGTHENING_AUDIT.json',inclusion)
    pre=r.audit('DUAL_PRE_BUILD');assert pre['PASS']
    before=r.memory();guard()
    import gurobipy as gp
    from tools.u4_primal_alns.pilot import PARAMS
    model=gp.Model('Source18r_K48_ValidGrid_Strengthened_Global_LB')
    entered=False;ledger=dict(method='DUAL',entered_native=False,Native_Runtime=None,Threads=1,Native_worker=1,
        requested_seconds=seconds,restricted_ObjBound_is_Global_LB=False,Global_LB_admissible=True,
        captures=[],resource_samples=[],callback_errors=[],source_parameters=dict(PARAMS,MIPFocus=3),ACTUAL='ACTUAL_NOT_RUN')
    cert=dict(PASS=False,Global_LB=None)
    try:
        for key,val in dict(PARAMS,MIPFocus=3,TimeLimit=seconds,LogFile=str(out/'NATIVE_GUROBI.log')).items():setattr(model.Params,key,val)
        x=model.addMVar(A.shape[1],lb=d['lb'],ub=d['ub'],vtype=d['vtypes'],obj=d['c'])
        x.VarName=d['names'].tolist();model.ObjCon=float(d['constant'])
        cons=model.addMConstr(A,x,d['senses'],d['rhs']);cons.ConstrName=d['row_names'].tolist()
        model.update()
        native=model.getA().tocsr()
        checks=dict(matrix=v.matrix_sha(native)==v.matrix_sha(A),rhs=np.array_equal(model.getAttr('RHS'),d['rhs']),
            sense=np.array_equal(model.getAttr('Sense'),d['senses']),LB=np.array_equal(x.LB,d['lb']),UB=np.array_equal(x.UB,d['ub']),
            VType=np.array_equal(x.VType,d['vtypes']),objective=np.array_equal(x.Obj,d['c']),ObjCon=model.ObjCon==float(d['constant']),
            minimize=model.ModelSense==1,binaries=model.NumBinVars==9322)
        del native;assert all(checks.values())
        write(out/'NATIVE_READBACK.json',dict(PASS=True,checks=checks,matrix_SHA=v.matrix_sha(A),
            parameter_readback={k:getattr(model.Params,k) for k in dict(PARAMS,MIPFocus=3,TimeLimit=seconds)}))
        gate=r.admit(before,r.memory());write(out/'POST_BUILD_NATIVE_ADMISSION.json',gate);assert gate['PASS']
        # Saved U4 is used only after original lifted feasibility in this compact
        # strengthened model is independently checked; it is not a primal UB.
        start=data(previous/'JOINT_START.npz')['x']
        res=A@start-d['rhs'];err=np.where(d['senses']=='=',abs(res),np.where(d['senses']=='<',res,-res))
        assert err.max()<=1e-8 and np.all(start>=d['lb']) and np.all(start<=d['ub'])
        x.Start=start;model.update();guard()
        ledger.update(build_memory_before=before,build_memory_after=r.memory(),parameter_readback={k:getattr(model.Params,k) for k in dict(PARAMS,MIPFocus=3,TimeLimit=seconds)})
        next_gate=0.
        def callback(m,where):
            nonlocal next_gate
            if where==gp.GRB.Callback.POLLING:return
            try:
                runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME))
                if runtime>=next_gate:
                    next_gate=runtime+10;guard();safety=r.callbackcheck()
                    ledger['resource_samples'].append(dict(Native_elapsed=runtime,sample=r.memory(),safety=safety))
                    if not safety['PASS']:ledger['callback_stop_reason']='RESOURCE_OR_SOURCE_CALLBACK_GATE';m.terminate()
            except Exception as exc:ledger['callback_errors'].append(repr(exc));m.terminate()
        ledger['entered_native']=True;entered=True;write(out/'NATIVE_CALL.json',ledger)
        started=time.perf_counter();model.optimize(callback);ledger['Optimize_wall_seconds']=time.perf_counter()-started
        for key in ('Status','SolCount','ObjVal','ObjBound','MIPGap','NodeCount','IterCount','BarIterCount'):ledger[key]=finite_attr(model,key)
        ledger['Native_Runtime']=finite_attr(model,'Runtime');ledger['after_native_memory']=r.memory()
        if model.SolCount:np.savez_compressed(out/'COMPACT_RAW.npz',x=np.asarray(x.X))
        bound=ledger['ObjBound']
        admissible=(all(checks.values()) and ledger['Status'] in (2,9,11) and bound is not None and math.isfinite(bound)
            and not ledger['callback_errors'] and not ledger.get('callback_stop_reason')
            and all(v.file_sha(out/name)==digest for name,digest in files.items()))
        cert=dict(PASS=admissible,Global_LB=bound if admissible else None,native_source_attribute='ObjBound',
            compact_ObjVal_is_FULL_UB=False,FULL_projection_subset_strengthened_K48=True,
            strengthened_K48_subset_K48=True,original_rows_binary_bounds_objective_preserved=True,
            source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,original_matrix_SHA=v.FULL_MATRIX_SHA,original_domain_SHA=v.FULL_DOMAIN_SHA,
            Native_Runtime=ledger['Native_Runtime'],Status=ledger['Status'],
            LB_gain=None if not admissible else bound-.46498486997548166,material_gain=admissible and bound-.46498486997548166>=.001,
            proof=record(out/'INDEPENDENT_NATIVE0.json'),native_readback=record(out/'NATIVE_READBACK.json'),
            solver_global_bound_is_numerical_Gurobi_contract=True,exact_rational_optimality_claim=False)
    except Exception as exc:
        ledger.update(error=repr(exc),traceback=traceback.format_exc())
        if entered:ledger['Native_Runtime']=finite_attr(model,'Runtime')
    finally:
        model.dispose();write(out/'NATIVE_CALL.json',ledger);write(out/'INDEPENDENT_CERTIFICATE.json',cert)
    print(json.dumps(dict(Native=ledger['Native_Runtime'],certificate=cert)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,required=True);args=parser.parse_args();main(args.seconds)
