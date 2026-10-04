from .common import *
import numpy as np
import gurobipy as gp
from v42_degen.identity import inputs,model,digest
from v42_integrated.matrix import audit
def run():
    gate('polish')
    assert read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json')['PASS']
    A,d,B,e,i,_=inputs();m,_=model(B,e,i)
    source=ROOT/'docs/v42_m1_degenmoves_zero_start_v1/RAW_POINTS/ZERO_ACTION_CANDIDATE.npz'
    validation=read(ROOT/'docs/v42_m1_degenmoves_zero_start_v1/ZERO_ACTION_START_TOLERANCE_REAUDIT.json')
    assert validation['M1_ZERO_ACTION_START_VALID'] and sha(source)==validation['candidate_sha256']
    with np.load(source) as z:
        assert np.array_equal(z['names'],d['names']);pattern=z['values']
    mask=d['types']!='C';fixed=pattern[mask]
    assert np.array_equal(fixed,np.rint(fixed))
    from v42_strengthening.analysis import graph_inputs
    sites,initial,arcs,*_=graph_inputs();stay=len(sites)*96
    movement=[j for j,n in enumerate(d['names']) if str(n).startswith('arc[') and int(str(n).rsplit(',',1)[1][:-1])>=stay]
    assert np.all(pattern[movement]==0)
    vs=m.getVars()
    for j in np.flatnonzero(mask):vs[j].LB=float(pattern[j]);vs[j].UB=float(pattern[j])
    m.setAttr('VType',vs,['C']*len(vs));m.update()
    policy=dict(Threads=1,Method=2,Crossover=1,TimeLimit=300,FeasibilityTol=1e-8,OptimalityTol=1e-8,BarConvTol=1e-11,PreDual=0,Seed=20260929)
    for k,v in policy.items():m.setParam(k,v)
    m.Params.LogFile='docs/v42_m1_movement_grid_epigraph_strengthening/M1_FIXED_DISCRETE_POLISH.log'
    write('POLISH_DISCRETE_PATTERN_BINDING.json',dict(PASS=True,source_SHA=sha(source),source_validation_SHA=sha(ROOT/'docs/v42_m1_degenmoves_zero_start_v1/ZERO_ACTION_START_TOLERANCE_REAUDIT.json'),integer_count=int(mask.sum()),pattern_SHA=digest(fixed),movement_count=0,continuous_old_values_used=False,global_model_bounds_changed=False,diagnostic_subproblem_only=True))
    once('POLISH');m.optimize()
    result=dict(status=m.Status,status_name='OPTIMAL' if m.Status==2 else str(m.Status),runtime=m.Runtime,objective=m.ObjVal if m.SolCount else None,settings=policy,optimization_calls=1,global_UB_certificate=None,barrier_iterations=m.BarIterCount,simplex_iterations=m.IterCount)
    checked=dict(PASS=False,POLISHED_START_AVAILABLE=False,reason='NO_OPTIMAL_RAW_POINT',physical_audit=None)
    if m.SolCount:
        x=np.asarray(m.getAttr('X'));np.savez_compressed(OUT/'M1_FIXED_DISCRETE_POLISH_POINT.npz',names=d['names'],values=x)
        raw=audit(A,d,x,integral=True,tolerance=1e-8);exact=np.array_equal(x[mask],fixed)
        checked.update(original_full_row_audit=raw,exact_fixed_integers=exact,finite_full_row_residual=bool(np.isfinite(raw['max_constraint_violation'])),solver_LP_feasible=m.Status==2 and m.ConstrVio<=1e-8 and m.BoundVio<=1e-8,point_SHA=sha(OUT/'M1_FIXED_DISCRETE_POLISH_POINT.npz'))
        import v42_integrated.solve as solve
        from v42_integrated.contract import physical_authority
        solve.OUT=OUT;solve.LOCAL=SOURCE;solve.write=write
        (OUT/'INTEGRATED_A1_FREEZE.json').write_bytes((SCIENCE/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json').read_bytes())
        with physical_authority():p=solve.physical(x,d);units=solve.grid_point(x,d)
        checked.update(physical_audit=p,original_units=units,scientific_physical_PASS=bool(p['PASS'] and units['PASS']))
        available=bool(raw['PASS'] and exact and checked['solver_LP_feasible'] and checked['scientific_physical_PASS'])
        checked.update(PASS=available,POLISHED_START_AVAILABLE=available,reason='RAW_OPTIMAL_STRICT_POINT' if available else 'RAW_AUDIT_FAILED')
    else:
        np.savez_compressed(OUT/'M1_FIXED_DISCRETE_POLISH_POINT.npz',names=d['names'],values=np.asarray([],float),available=np.asarray(False))
    result.update(POLISHED_START_AVAILABLE=checked['POLISHED_START_AVAILABLE'],point_repaired=False,Start_solver_acceptance='NOT_ATTEMPTED',source_pattern_SHA=digest(fixed))
    write('M1_FIXED_DISCRETE_POLISH_RESULT.json',result);write('M1_FIXED_DISCRETE_POLISH_AUDIT.json',checked)
    m.dispose();print('POLISH_DONE',result,flush=True)
if __name__=='__main__':run()
