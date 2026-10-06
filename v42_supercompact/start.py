"""Current validated original point transport; no physical repair."""
from .common import *
from .formulation import Compact,residual
from .build import load
from .verify import inverse_map
import numpy as np
from scipy import sparse
from v42_degen.identity import inputs
from v42_strengthening.analysis import graph_inputs
from v42_one_tree_bc.audit import Validator

def run():
    full,fd,A,d,_,_=inputs();original=Validator(full,fd)
    path=ROOT/'docs/v42_m1_exact_grid_rowgen_20261006/A_BASELINE_FINAL_VALID_POINT.npz'
    with np.load(path) as z:x=z['point'].copy()
    check=original(x);assert check['PASS'],'CURRENT_ORIGINAL_START_INVALID'
    sites,initial,arcs,battery,receipt=graph_inputs();c=Compact(A,d,arcs,initial,96);y=c.forward(x)
    B,e,C,f,T,offset,rows,cols,steps=inverse_map();z=y[cols]
    inverse=np.asarray(T@z).ravel()+offset
    # No original physical/route/mode/SOC value is modified. Differences may
    # only be algebraically defined auxiliary reconstruction residuals.
    physical=np.asarray([str(n).startswith(('arc[','SOC[','Pch[','Pdis[','Q[','charge_mode[')) for n in d['names']])
    error=float(np.max(abs(inverse[:len(x)][physical]-x[physical]),initial=0.));assert error==0,'PHYSICAL_START_REPAIR_FORBIDDEN'
    allchecks={}
    for label,point in [('C0',y),('C1',y),('C2',z)]:
        AA,dd=load(label);rr=residual(AA,dd,point);rr['PASS']=rr['max_row_violation']<=1e-8 and rr['max_bound_violation']<=1e-8 and rr['max_integrality_violation']==0
        allchecks[label]=rr;np.savez_compressed(OUT/(label+'_VALID_START.npz'),point=point)
    inversecheck=original(inverse[:len(x)])
    valid=all(v['PASS'] for v in allchecks.values()) and inversecheck['PASS']
    mapping=dict(PASS=valid,current_original_start_file=str(path.relative_to(ROOT)),source_SHA256=sha(path),original_forward='Copy physical decisions/route/mode/SOC/grid auxiliaries; node activity exact sum of original binary flow',C2_retained_columns=len(cols),inverse_steps=len(steps),physical_decisions_exactly_unchanged=error==0,physical_repairs=0,auxiliary_reconstruction_max_difference=float(np.max(abs(inverse[:len(x)]-x),initial=0.)),rational_reconstruction_required=False)
    write('COMPACT_START_MAPPING.json',mapping)
    result=dict(PASS=valid,COMPACT_START_VALID=valid,original_full_validation=check,arms=allchecks,maximum_row_residual=max(r['max_row_violation'] for r in allchecks.values()),inverse_original_validation=inversecheck,physical_mapping_max_difference=error,FeasibilityTol=1e-8,loosened_tolerances=False,physical_repairs=0)
    write('COMPACT_START_VALIDATION.json',result);print('START_RESULT',result,flush=True)
    return result
if __name__=='__main__':run()
