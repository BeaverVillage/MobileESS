"""Route-conditional LP: original physics, relaxed modes, valid Grid projection.

Conditional bounds never enter the Original FULL Global LB registry.
"""
from pathlib import Path
from fractions import Fraction as F
from scipy import sparse
import gc,math,time,argparse,traceback,numpy as np
from tools.minimax_beam1800.adapter import *
from tools.b2_root_lp_tightening.verify import exact_box_dual,downward

PHYS={'connected_Pch','connected_Pdis','connected_Qmax','connected_Qmin',
    'no_simultaneous_charge','no_simultaneous_discharge','PCS16','energy_balance','initial_SOC','terminal_SOC'}
POWER={'Pch','Pdis','Q','SOC','charge_mode','rho_max'}
TEMPLATE=DOCS/'lp_template'

def npz(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}

def prepare_template():
    TEMPLATE.mkdir(parents=True,exist_ok=False)
    case=v.load_case();d=case.original_d
    A=case.original_A.tocsr();assert v.matrix_sha(A)==v.FULL_MATRIX_SHA
    rows=np.asarray([i for i,n in enumerate(d['row_names']) if str(n).split('[',1)[0] in PHYS],dtype=np.int64)
    cols=np.asarray([j for j,n in enumerate(d['names']) if str(n).split('[',1)[0] in POWER],dtype=np.int64)
    arcs=np.asarray([j for j,n in enumerate(d['names']) if str(n).startswith('arc[')],dtype=np.int64)
    assert len(cols)==27599 and np.count_nonzero(np.char.startswith(d['names'][cols],'charge_mode['))==384
    chosen=set(map(int,np.r_[cols,arcs]))
    physical=A[rows].tocsr();assert set(map(int,physical.indices))<=chosen
    P=physical[:,cols].tocsr();R=physical[:,arcs].tocsr()
    sparse.save_npz(TEMPLATE/'PHYS_POWER_A.npz',P);sparse.save_npz(TEMPLATE/'PHYS_ARC_A.npz',R)
    np.savez_compressed(TEMPLATE/'DATA.npz',names=d['names'][cols],lb=d['lower'][cols],ub=d['upper'][cols],
        c=d['objective'][cols],constant=d['constant'],senses=d['sense'][rows],rhs=d['rhs'][rows],
        row_names=d['row_names'][rows],columns=cols,original_rows=rows,arc_columns=arcs,arc_names=d['names'][arcs])
    proof=dict(PASS=True,source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,FULL_matrix_SHA=v.FULL_MATRIX_SHA,
        FULL_domain_SHA=v.FULL_DOMAIN_SHA,all_original_physical_row_families_preserved=sorted(PHYS),
        original_rows=len(rows),columns=len(cols),all384_modes_relaxed=True,
        all97_SOC_per_unit=True,initial_terminal_SOC_energy_eta_PCS_connected_PQ_preserved=True,
        fixed_routes_are_source_Arc_literals=True,omitted_grid_rows_form_a_relaxation=True,
        source_source_bytes_unchanged=True,Native_optimize_calls=0,
        file_sha256={p.name:v.file_sha(p) for p in TEMPLATE.glob('*.npz')})
    write(TEMPLATE/'INDEPENDENT_NATIVE0.json',proof)
    return proof

def build_arrays(spec,grid):
    frozen=read(TEMPLATE/'INDEPENDENT_NATIVE0.json');assert frozen['PASS']
    independent=read(TEMPLATE/'INDEPENDENT_SOURCE_REEXTRACTION.json');assert independent['PASS']
    assert grid['independent_source_projection']['PASS']
    for name,digest in frozen['file_sha256'].items():assert v.file_sha(TEMPLATE/name)==digest
    d=npz(TEMPLATE/'DATA.npz');P=sparse.load_npz(TEMPLATE/'PHYS_POWER_A.npz').tocsr();R=sparse.load_npz(TEMPLATE/'PHYS_ARC_A.npz').tocsr()
    chosen={u:set(p) for u,p in spec['paths'].items()}
    literals=np.asarray([float(int(str(n).split(',')[-1][:-1]) in chosen[str(n).split('[',1)[1].split(',')[0]]) for n in d['arc_names']])
    # Every original physical row couples at most one selected outgoing Arc.
    # Thus binary64 multiply by literal one and addition of zeros are exact.
    occupancy=R.copy();occupancy.data=np.ones_like(occupancy.data)
    selected_counts=occupancy@literals
    assert np.all(selected_counts<=1),'MULTIPLE_FIXED_ARCS_IN_ONE_PHYSICAL_ROW'
    shift=R@literals;rhs=d['rhs']-shift
    assert all(F(float(a))-F(float(b))==F(float(c)) for a,b,c in zip(d['rhs'],shift,rhs)), 'PHYSICAL_RHS_NOT_EXACT_BINARY64'
    lookup={str(n):j for j,n in enumerate(d['names'])};rr=[];cc=[];vv=[];grhs=[];gnames=[];audit_rows=[]
    for i,packet in enumerate(grid['rows']):
        error=F(0);terms={};exact_rhs=F(packet['rhs'])
        for name,value in packet['coeff'].items():
            j=lookup[name];exact=F(value);native=float(exact)
            assert native!=0 and math.isfinite(native)
            terms[j]=native;diff=F(native)-exact
            error+=max(diff*F(float(d['lb'][j])),diff*F(float(d['ub'][j])))
        target=exact_rhs+error;native_rhs=float(target)
        if F(native_rhs)<target:native_rhs=float(np.nextafter(native_rhs,np.inf))
        assert F(native_rhs)>=target
        for j,value in sorted(terms.items()):rr.append(i);cc.append(j);vv.append(value)
        grhs.append(native_rhs);gnames.append(packet['name'])
        audit_rows.append(dict(original_row=packet['original_row'],name=packet['name'],exact_rhs=str(exact_rhs),
            coefficient_error_support=str(error),outward_native_rhs=native_rhs,helper_rows=packet['helper_rows'],
            source_row_sha256=packet['source_row_sha256']))
    G=sparse.csr_matrix((vv,(rr,cc)),shape=(len(grhs),P.shape[1]));A=sparse.vstack((P,G),format='csr')
    data=dict(names=d['names'],lb=d['lb'],ub=d['ub'],c=d['c'],constant=d['constant'],
        senses=np.r_[d['senses'],np.full(len(grhs),'<')],rhs=np.r_[rhs,grhs],row_names=np.r_[d['row_names'],gnames])
    proof=dict(PASS=True,original_route_fixed_MILP_projection_subset_LP=True,
        all_original_physics_rows_and_bounds_preserved=True,only_Mode_B_to_C_and_grid_omission=True,
        original_FIXED_AIDC_forecast_correction_in_projected_RHS=True,grid_outward_rows=audit_rows,
        physical_row_rhs_binary64_exact=True,route_signature=spec['mathematical_model_signature'],
        route_bound_is_original_Global_LB=False,Native_optimize_calls=0)
    return A,data,proof

def main(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);began=time.perf_counter();guard()
    spec=read(args.spec);grid=read(args.grid);assert spec['moves']>=1
    pre=r.audit('CONDITIONAL_LP_PRE_BUILD');write(out/'PRE_BUILD_GATE.json',pre);assert pre['PASS']
    before=r.memory();A,d,proof=build_arrays(spec,grid)
    sparse.save_npz(out/'LP_A.npz',A);np.savez_compressed(out/'LP_DATA.npz',**d)
    write(out/'INDEPENDENT_RELAXATION_NATIVE0.json',proof)
    import gurobipy as gp
    from tools.u4_primal_alns.pilot import PARAMS,finite_attr
    model=gp.Model('Source18r_Route_Conditional_Screening_LP')
    ledger=dict(method='CONDITIONAL_LP',entered_native=False,Native_Runtime=None,Threads=1,Native_worker=1,
        requested_seconds=args.seconds,captures=[],resource_samples=[],callback_errors=[],
        route_bound_is_Global_LB=False,initial_point=None,ACTUAL='ACTUAL_NOT_RUN')
    cert=dict(PASS=False,Certified_LP_LB=None)
    try:
        params=dict(PARAMS,Method=1,TimeLimit=args.seconds,LogFile=str(out/'NATIVE_GUROBI.log'))
        for name,value in params.items():setattr(model.Params,name,value)
        x=model.addMVar(A.shape[1],lb=d['lb'],ub=d['ub'],obj=d['c'],vtype='C')
        x.VarName=d['names'].tolist();model.ObjCon=float(d['constant'])
        cons=model.addMConstr(A,x,d['senses'],d['rhs']);cons.ConstrName=d['row_names'].tolist();model.update()
        actual=model.getA().tocsr()
        checks=dict(matrix=v.matrix_sha(actual)==v.matrix_sha(A),rhs=np.array_equal(model.getAttr('RHS'),d['rhs']),
            senses=np.array_equal(model.getAttr('Sense'),d['senses']),lb=np.array_equal(x.LB,d['lb']),ub=np.array_equal(x.UB,d['ub']),
            objective=np.array_equal(x.Obj,d['c']),constant=model.ObjCon==float(d['constant']),continuous=model.NumBinVars==0 and not model.IsMIP,
            original_rho_minimize=model.ModelSense==1,threads=model.Params.Threads==1,no_historical_start=model.NumStart==0)
        assert all(checks.values());del actual
        write(out/'NATIVE_READBACK.json',dict(PASS=True,checks=checks,matrix_SHA=v.matrix_sha(A),parameters={k:getattr(model.Params,k) for k in PARAMS}))
        gate=r.admit(before,r.memory());write(out/'POST_BUILD_NATIVE_ADMISSION.json',gate);assert gate['PASS'];guard()
        ledger.update(build_memory_before=before,build_memory_after=r.memory(),build_wall_seconds=time.perf_counter()-began,
            parameter_readback={k:getattr(model.Params,k) for k in dict(PARAMS,Method=1,TimeLimit=args.seconds)})
        next_gate=0.
        def callback(m,where):
            nonlocal next_gate
            if where==gp.GRB.Callback.POLLING:return
            try:
                elapsed=float(m.cbGet(gp.GRB.Callback.RUNTIME))
                if elapsed>=next_gate:
                    next_gate=elapsed+10.;guard();safety=r.callbackcheck()
                    ledger['resource_samples'].append(dict(Native_elapsed=elapsed,sample=r.memory(),safety=safety))
                    if not safety['PASS']:ledger['callback_stop_reason']='SOURCE_OR_RESOURCE';m.terminate()
            except Exception as exc:ledger['callback_errors'].append(repr(exc));m.terminate()
        ledger['entered_native']=True;write(out/'NATIVE_CALL.json',ledger);model.optimize(callback)
        for name in ('Status','SolCount','ObjVal','IterCount'):ledger[name]=finite_attr(model,name)
        ledger['Native_Runtime']=finite_attr(model,'Runtime');ledger['after_native_memory']=r.memory()
        # No incumbent value is used as a bound. Any available sign-valid dual
        # gives an exact dyadic weak-duality finite-box certificate, including
        # TIME_LIMIT only if this independent certificate actually succeeds.
        try:
            pi=np.asarray(model.getAttr('Pi'));bound,detail=exact_box_dual(A,d,pi)
            detail.pop('reduced_cost_vector_exact',None)
            lower=downward(bound)
            np.savez_compressed(out/'LP_DUAL_RAW.npz',pi=pi)
            if model.SolCount:np.savez_compressed(out/'LP_POINT_RAW.npz',x=np.asarray(x.X))
            cert=dict(PASS=True,Certified_LP_LB=lower,exact_conditional_bound=str(bound),proof=detail,
                route_bound_is_Global_LB=False,LP_point_is_FULL_UB=False,
                original_route_fixed_projection_subset_LP=True,Native_Status=ledger['Status'],Native_Runtime=ledger['Native_Runtime'])
        except Exception as exc:cert.update(error=repr(exc),TIME_LIMIT_not_an_exclusion=True)
    except Exception as exc:
        ledger.update(error=repr(exc),traceback=traceback.format_exc())
        if ledger['entered_native']:ledger['Native_Runtime']=finite_attr(model,'Runtime')
    finally:
        model.dispose();write(out/'NATIVE_CALL.json',ledger);write(out/'CONDITIONAL_BOUND_CERTIFICATE.json',cert)
    print(json.dumps(dict(Runtime=ledger['Native_Runtime'],Status=ledger.get('Status'),bound=cert.get('Certified_LP_LB'),certified=cert['PASS'])))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True);p.add_argument('--grid',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=float,required=True);main(p.parse_args())
