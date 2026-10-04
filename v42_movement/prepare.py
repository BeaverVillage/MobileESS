from .common import *
import numpy as np
from v42_degen.identity import inputs,model,signature,digest
from v42_integrated.matrix import audit
def run():
    gate('prepare')
    import v42_strengthening.preservation as p
    p.OUT=OUT;p.BASE=BASE;p.write=write;p.freeze()
    A,d,B,e,identity,freeze=inputs()
    previous=read(ROOT/'docs/v42_m1_location_grid_disjunctive_cuts/M1_DISJUNCTIVE_BASE_IDENTITY.json')
    assert signature(B,e)==previous['reference']
    m,r=model(B,e,identity)
    r.update(base_exact_head=BASE,native_row_names_SHA=digest(np.asarray(m.getAttr('ConstrName'))),
             original_family_row_names_SHA=digest(e['row_names']),source_data_SHA=sha(SOURCE/'DATA.pkl'),
             source_asset_SHAs=previous['source_SHA'],A1_freeze_SHA=previous['A1_freeze_SHA'],
             NormalAmps_SHA=previous['NormalAmps_SHA'],P1_P2_objective_SHA=previous['P1_P2_objective_SHA'],
             voltage=[.95,1.05],voltage_margin=0.,no_new_binary=True,no_route_site_time_pruning=True)
    assert r['native_row_names_SHA']==previous['native_row_names_SHA']
    for path,s in r['source_asset_SHAs'].items():assert sha(path)==s
    write('M1_MOVEMENT_GRID_BASE_IDENTITY.json',r);m.dispose()
    path=ROOT/'docs/v42_m1_exact_formulation_strengthening/BASELINE_ROOT_LP_SOLUTION.npz'
    with np.load(path) as z:
        assert np.array_equal(z['names'],d['names']);x=z['values']
    checked=audit(A,d,x,tolerance=1e-8);assert checked['PASS']
    write('BASELINE_PRIMAL_REUSE.json',dict(PASS=True,source_SHA=sha(path),audit=checked,new_optimize_calls=0))
    census(d,x,'BASELINE')
    write('EXECUTION_PREREGISTRATION.json',dict(base_exact_head=BASE,MAX_HEAVY_WORKERS=1,environment=ENV,
          fixed_discrete_polish=dict(Threads=1,Method=2,Crossover=1,TimeLimit=300),
          root=dict(Threads=1,Method=2,Crossover=0,TimeLimit=300),
          full_conditional_LP_calls=0,full_M1_optimizes_in_support_oracle=0,root_gate=dict(absolute=.005,relative=.05),
          no_clipping=True,no_rounding_repair=True,no_slack=True,no_parameter_sweep=True,
          canary_TimeLimit=600,canary_only_if_material=True,production_calls=0,
          numerical_policy='Solver Feasibility/Optimality/Integrality 1e-8. Polished availability additionally requires raw full rows <=1e-8 and exact fixed integers. Existing independent physical audit thresholds unchanged.',
          algebraic_policy='Exact dyadic factored row equations, outward interval expansion, exact rational polygon vertices and outward support bounds; never a full conditional solve.'))
    print('IDENTITY_PASS',flush=True)
if __name__=='__main__':run()
