"""Exact extended formulation: redundant route integrality is implied by lambda."""
import gc,time
from collections import Counter
from tools.adaptive_compact_joint.adapter import *
from tools.global_local_multistart1800.joint import build_spec,independent
from tools.u4_primal_alns.pilot import PARAMS

def removable(case):
    route=np.flatnonzero((case.d['types']=='B') & np.char.startswith(case.d['names'],'node_activity['))
    mode=np.flatnonzero(np.char.startswith(case.d['names'],'charge_mode['))
    assert len(route)==8938 and len(mode)==384
    assert set(np.flatnonzero(case.d['types']!='C'))==set(route)|set(mode)
    return route,mode

def integer_proof(case,point,spec,lo,hi,A,rhs):
    prior=independent(case,point,spec,lo,hi,A,rhs)
    route,mode=removable(case);ids,_=route_values(case,paths_of(case,point))
    linked=set(spec['varying_route_columns']);fixed={int(j) for j in ids if lo[j]==hi[j] and lo[j] in (0.,1.)}
    assert set(ids)==linked|fixed
    assert set(route)<=linked|fixed and not set(mode)&set(ids)
    assert all(case.d['objective'][j]==0 for j in route)
    return dict(PASS=True,Optimize_calls=0,predecessor_independent_proof=prior,
        source_binary_families=dict(Counter(str(case.d['names'][j]).split('[')[0] for j in np.flatnonzero(case.d['types']!='C'))),
        eliminated_integer_designations=len(route),eliminated_columns=0,retained_route_flow_continuous=sum(str(case.d['names'][j]).startswith('route_flow[') for j in ids),
        all_route_coordinates_exactly_linked_or_fixed=True,removed_integer_columns=route.tolist(),
        retained_384_charge_modes_free=True,source_rows_deleted=0,original_source_CSR_RHS_Sense_Bounds_Objective_preserved=True,
        sparse_fill_in_increase_relative_to_old_joint=0,
        theorem='One-hot binary lambda makes every linked route coordinate a selected literal0/1 incidence value. Common route coordinates are fixed literal0/1. All8938 node_activity binaries are in these sets, so their integrality is redundant. Keeping them continuous with exact links preserves both directions of integer feasibility for the same restricted pools. Original FULL lift is inherited from independently checked source inverse aliases. No physics row is removed.',
        restricted_to_FULL_inclusion=True,restricted_equals_FULL_not_claimed=True,
        continuous_helpers_not_unconditionally_eliminated=True)

def construct(case,point,spec,out,seconds,compact=True):
    from v42_common_mess.model import build
    import gurobipy as gp
    began=time.perf_counter()
    _,lo,hi,A,rhs=build_spec(case,point,spec['center_replay']['path'],spec['pools'],spec['candidate_id'],seconds)
    params=dict(PARAMS,Method=2,TimeLimit=seconds)
    model,x,identity=build(case,out,lower=lo,upper=hi,start=point,numeric_parameters=params)
    route,mode=removable(case)
    if compact:x[route].VType='C'
    lam=model.addMVar(spec['lambda_count'],lb=0.,ub=1.,vtype='B',obj=0.)
    lam.VarName=[a['name'] for a in spec['lambda_axis']];lam.Start=np.asarray(spec['lambda_Start'])
    joined=gp.MVar.fromlist(list(x.tolist())+list(lam.tolist()))
    model.addMConstr(A,joined,'=',rhs);model.update()
    actual=model.getA().tocsr();m,n=case.A.shape
    expected_types=case.d['types'].copy()
    if compact:expected_types[route]='C'
    checks=dict(source_CSR_exact=v.matrix_sha(actual[:m,:n].tocsr())==v.matrix_sha(case.A) and actual[:m,n:].nnz==0,
        source_RHS_Sense_exact=np.array_equal(model.getAttr('RHS')[:m],case.d['rhs']) and np.array_equal(model.getAttr('Sense')[:m],case.d['sense']),
        links_CSR_exact=v.matrix_sha(actual[m:].tocsr())==v.matrix_sha(A),links_RHS_Sense_exact=np.array_equal(model.getAttr('RHS')[m:],rhs) and set(model.getAttr('Sense')[m:])=={'='},
        audited_types_exact=np.array_equal(x.VType,expected_types),source_bounds_exact=np.array_equal(x.LB,lo) and np.array_equal(x.UB,hi),
        original_objective_exact=np.array_equal(x.Obj,case.d['objective']) and model.ObjCon==float(case.d['constant']) and np.all(lam.Obj==0),
        lambda_types_bounds_exact=np.all(lam.VType=='B') and np.all(lam.LB==0) and np.all(lam.UB==1),
        mode384_original_free=len(mode)==384 and np.array_equal(x.LB[mode],case.d['lower'][mode]) and np.array_equal(x.UB[mode],case.d['upper'][mode]) and np.all(x.VType[mode]=='B'),
        raw_start_bit_equal=np.array_equal(x.Start,point) and v.vector_sha(x.Start)==v.vector_sha(point),
        lambda_start_exact=np.array_equal(lam.Start,spec['lambda_Start']) and np.array_equal(A@np.r_[x.Start,lam.Start],rhs),
        binary_count=model.NumBinVars==(384 if compact else 9322)+spec['lambda_count'],
        rows_count=model.NumConstrs==m+len(rhs),columns_count=model.NumVars==n+spec['lambda_count'],
        parameters_exact=all(getattr(model.Params,k)==vv for k,vv in params.items()))
    assert all(checks.values()),checks
    data=dict(PASS=True,Optimize_calls=0,checks=checks,compact=compact,NumBinVars=model.NumBinVars,NumVars=model.NumVars,
        NumConstrs=model.NumConstrs,NumNZs=model.NumNZs,continuous=model.NumVars-model.NumBinVars,
        build_wall_seconds=time.perf_counter()-began,source_matrix_SHA=v.matrix_sha(case.A),new_joint_matrix_SHA=v.matrix_sha(actual),
        source_domain_SHA=v.domain_sha(case.d),parameters=params)
    write(out/'COMPACT_NATIVE_READBACK.json',data);del actual;gc.collect()
    return model,x,lam,data
