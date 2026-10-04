from .common import *
import numpy as np
from v42_degen.identity import inputs,model,signature,digest
from v42_integrated.matrix import audit
from .partition import extract
def run():
    gate('prepare')
    import v42_strengthening.preservation as p
    p.BASE=BASE;p.OUT=OUT;p.write=write;p.freeze()
    (OUT/'PR136_WORKSPACE_BYTE_SNAPSHOT.json').rename(OUT/'PR139_WORKSPACE_BYTE_SNAPSHOT.json')
    A,d,B,e,i,_=inputs();previous=read(ROOT/'docs/v42_m1_movement_grid_epigraph_strengthening/M1_MOVEMENT_GRID_BASE_IDENTITY.json')
    assert signature(B,e)==previous['reference'];m,r=model(B,e,i)
    native_names=np.asarray(m.getAttr('ConstrName'));assert digest(native_names)==previous['native_row_names_SHA']
    r.update(base_exact_head=BASE,native_row_names_SHA=digest(native_names),family_row_names_SHA=digest(e['row_names']),
             A1_freeze_SHA=previous['A1_freeze_SHA'],NormalAmps_SHA=previous['NormalAmps_SHA'],source_data_SHA=sha(SOURCE/'DATA.pkl'),
             source_asset_SHAs=previous['source_asset_SHAs'],P1_P2_objective_SHA=previous['P1_P2_objective_SHA'],voltage=[.95,1.05],margin=0.)
    for path,h in r['source_asset_SHAs'].items():assert sha(path)==h
    write('DW_BASE_MODEL_IDENTITY.json',r);m.dispose()
    np.savez_compressed(OUT/'DW_NATIVE_ROW_NAMES.npz',names=native_names)
    owner,rows,partition=extract(B,e)
    source=ROOT/'docs/v42_m1_movement_grid_epigraph_strengthening/M1_FIXED_DISCRETE_POLISH_POINT.npz'
    prior=read(ROOT/'docs/v42_m1_movement_grid_epigraph_strengthening/M1_FIXED_DISCRETE_POLISH_AUDIT.json')
    assert prior['POLISHED_START_AVAILABLE'] and sha(source)==prior['point_SHA']
    with np.load(source) as z:assert np.array_equal(z['names'],e['names']);x=z['values']
    full=audit(A,d,x,integral=True,tolerance=1e-8);assert full['PASS'] and full['objective']==U_REF
    np.savez_compressed(OUT/'DW_INITIAL_COLUMNS.npz',source_names=e['names'],source_values=x,column_owner=owner)
    audits=[]
    for k,u in enumerate(UNITS):
        rr=np.flatnonzero(rows==k);cc=np.flatnonzero(owner==k)
        local=dict(e,rhs=e['rhs'][rr],sense=e['sense'][rr],lower=e['lower'][cc],upper=e['upper'][cc],types=e['types'][cc],objective=e['objective'][cc],constant=np.array(0.))
        checked=audit(B[rr][:,cc],local,x[cc],integral=True,tolerance=1e-8);assert checked['PASS']
        assert np.array_equal(x[cc][local['types']!='C'],np.rint(x[cc][local['types']!='C']))
        audits.append(dict(MESS=u,PASS=True,local_audit=checked,integer_pattern_exact=True,columns=len(cc),rows=len(rr)))
    write('DW_INITIAL_COLUMN_AUDIT.json',dict(PASS=True,source_SHA=sha(source),source_full_audit=full,local_columns=audits,initial_columns=4,repairs=0,clipping=0))
    write('DW_EXACTNESS_CONTRACT.json',dict(top_k_routes=False,route_pool_restriction=False,hamming_restriction=False,site_pruning=False,time_pruning=False,heuristic_pricing=False,pricing_timeout_means_no_column=False,global_pricing_certificate_required_for_termination=True,branch_and_price_run=False,column_aging=False,column_deletion=False,incomplete_RMP_objective_is_global_LB=False,original_local_X_full_domain=True,continuous_local_polyhedra_bounded=True))
    write('DW_EXECUTION_PREREGISTRATION.json',dict(MAX_HEAVY_WORKERS=1,environment=ENV,overall_pilot_wall_seconds=3600,per_pricing_TimeLimit=600,MIPGap=0.,MIPGapAbs=0.,solver_tolerances=1e-8,
          negative_threshold=-1e-7,no_negative_global_bound_threshold=-1e-8,early_negative_stop_allowed=True,
          RMP_policy=dict(Threads=1,Method=2,Crossover=1,TimeLimit=300),pricing_policy=dict(Threads=1,Method=2,NodeMethod=1,Crossover=2,DegenMoves=0,CutPasses=1,MIPFocus=3),
          incomplete_pricing='INCONCLUSIVE, never no-column',pricing_resume='Same full-domain model and identical dual may resume within per-call and overall budget, no domain change or parameter sweep.',
          master_integer_production_calls=0,Branch_and_Price_calls=0,P2_calls=0,A2_calls=0,M2_calls=0,Actual_calls=0,Fresh_AC_calls=0))
    print('DW_PREPARE_PASS',partition['blocks'],partition['global_rows'],flush=True)
if __name__=='__main__':run()
