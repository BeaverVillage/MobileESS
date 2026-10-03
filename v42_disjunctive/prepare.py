from .common import *
import numpy as np
from v42_degen.identity import inputs, model, signature, digest
from v42_integrated.matrix import audit

def run():
    from .resources import gate
    gate('disjunctive_prepare')
    import v42_strengthening.preservation as preserve
    preserve.OUT=OUT; preserve.BASE=BASE; preserve.write=write
    preserve.freeze()
    # The inherited snapshot label is retained only locally in this new output directory.
    A,d,B,e,identity,freeze=inputs()
    previous=read(ROOT/'docs/v42_m1_exact_formulation_strengthening/M1_STRENGTHENING_BASE_IDENTITY.json')
    assert signature(B,e)==previous['scientific_signature']
    m,receipt=model(B,e,identity)
    receipt.update(base_exact_head=BASE,source_SHA=previous['source_asset_SHAs'],
                   native_row_names_SHA=digest(np.array(m.getAttr('ConstrName'))),
                   original_family_row_names_SHA=digest(e['row_names']),
                   A1_freeze_SHA=identity['A1_freeze_sha256'],NormalAmps_SHA=identity['NormalAmps_authority'],
                   voltage=[.95,1.05],voltage_margin=0.,P1_P2_objective_SHA=previous['P1_P2_objective_SHA'],
                   no_site_route_time_domain_change=True,no_new_binary=True)
    for path,expected in previous['source_asset_SHAs'].items(): assert sha(path)==expected
    assert receipt['native_row_names_SHA']==previous['native_row_names_SHA']
    write('M1_DISJUNCTIVE_BASE_IDENTITY.json',receipt)
    with np.load(ROOT/'docs/v42_m1_exact_formulation_strengthening/BASELINE_ROOT_LP_SOLUTION.npz') as z:
        point=z['values'].copy(); assert np.array_equal(z['names'],d['names']) and np.array_equal(z['integer_types'],d['types'])
    check=audit(A,d,point,tolerance=1e-8)
    assert check['PASS'] and abs(check['objective']-BASE_LB)<=1e-8
    write('BASELINE_PRIMAL_REUSE.json',dict(PASS=True,audit=check,source_SHA=sha(ROOT/'docs/v42_m1_exact_formulation_strengthening/BASELINE_ROOT_LP_SOLUTION.npz'),new_baseline_primal_calls=0))
    write('NUMERICAL_POLICY.json',dict(preregistered_before_baseline_and_conditionals=True,
          certification='Exact rational weak duality with sign-projected dyadic Pi and outward proven finite coordinate enclosures; residuals are included, not ignored.',
          L0_authority='Inherited PR137 globally valid BASE lower bound; never replace with diagnostic feasible reference.',
          fixed_extra_safety_epsilon=1e-8,primal_tolerance=1e-8,dual_and_basis_residual_tolerance=1e-8,
          maximum_primal_minus_rational_bound=1e-6,maximum_basis_condition=1e12,
          unresolved_on_missing_basis_or_numeric_failure=True,conditional_wall_budget_seconds=1800,
          wall_budget_reserve_seconds=5,basis_acquisition_TimeLimit=1800,
          conditional_Method=1,conditional_Threads=1,conditional_LPWarmStart=1,
          baseline_Method=2,baseline_Crossover=2,root_Method=2,root_Crossover=0,root_TimeLimit=300,
          FeasibilityTol=1e-8,OptimalityTol=1e-8,BarConvTol=1e-11,PreDual=0,Seed=20260929,
          separation_threshold=1e-6,environment=ENV,MAX_HEAVY_WORKERS=1))
    for v in m.getVars(): v.VType='C'
    m.update()
    for key,value in dict(Threads=1,Method=2,Crossover=2,TimeLimit=1800,FeasibilityTol=1e-8,OptimalityTol=1e-8,BarConvTol=1e-11,PreDual=0,Seed=20260929).items(): setattr(m.Params,key,value)
    m.Params.LogFile='docs/v42_m1_location_grid_disjunctive_cuts/DISJ_BASELINE_BASIS.log'
    once('BASELINE_BASIS')
    m.optimize()
    result=dict(status=m.Status,runtime=m.Runtime,barrier_iterations=m.BarIterCount,simplex_iterations=m.IterCount,
                settings=dict(Threads=1,Method=2,Crossover=2,TimeLimit=1800),optimization_calls=1,
                basis_reused=False,objective=m.ObjVal if m.SolCount else None)
    if m.Status==2:
        x=np.array(m.getAttr('X')); pi=np.array(m.getAttr('Pi')); rc=np.array(m.getAttr('RC'))
        vb=np.array(m.getAttr('VBasis')); cb=np.array(m.getAttr('CBasis'))
        full=audit(A,d,x,tolerance=1e-8)
        result.update(PASS=bool(full['PASS'] and abs(m.ObjVal-BASE_LB)<=1e-8),full_original_audit=full,
                      objective_delta=m.ObjVal-BASE_LB,usable_simplex_basis=True,
                      basis_status_counts={str(k):int((vb==k).sum()) for k in (-3,-2,-1,0)},
                      ConstrVio=m.ConstrVio,BoundVio=m.BoundVio,DualVio=m.DualVio,Kappa=m.Kappa)
        np.savez_compressed(OUT/'BASELINE_BASIS.npz',VBasis=vb,CBasis=cb,X=x,Pi=pi,RC=rc)
        result['basis_SHA']=sha(OUT/'BASELINE_BASIS.npz')
    else: result.update(PASS=False,usable_simplex_basis=False,stop_reason='BASELINE_BASIS_NOT_OPTIMAL_NO_RETRY')
    write('DISJ_BASELINE_BASIS_RECEIPT.json',result)
    m.dispose()
    print('BASELINE_BASIS',result,flush=True)

if __name__=='__main__': run()
