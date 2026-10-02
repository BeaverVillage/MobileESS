"""Read-only audit of the frozen MIP start, without repair or optimization."""
import numpy as np
import gurobipy as gp
from .common import *
from .build import LOCAL
from .experiment import load_compact,check_freeze
from .prepare import SETTINGS

def main():
    check_freeze();rows=[]
    with np.load(LOCAL/'AXIS_START.npz') as z:
        points={k:z[k+'_values'] for k in ['original','compact']}
        names={k:z[k+'_names'] for k in ['original','compact']}
    with gp.Env(params={'OutputFlag':0}) as env:
        for kind in ['original','compact']:
            m=original(env) if kind=='original' else load_compact(env)
            assert np.array_equal(m.getAttr('VarName'),names[kind])
            point=points[kind];rhs=np.array(m.getAttr('RHS'));sense=np.array(m.getAttr('Sense'))
            residual=m.getA()@point-rhs
            violation=np.maximum(0.,np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual)))
            top=np.argsort(violation)[-12:][::-1]
            tolerance=SETTINGS['FeasibilityTol']
            integral=np.array(m.getAttr('VType'))!='C'
            rows.append(dict(model=kind,maximum_row_violation=float(np.max(violation)),
                registered_FeasibilityTol=tolerance,rows_exceeding_registered_tolerance=int(np.sum(violation>tolerance)),
                start_within_unscaled_registered_row_tolerance=bool(np.max(violation)<=tolerance),
                integer_fractionality=float(np.max(abs(point[integral]-np.rint(point[integral])))),
                maximum_bound_violation=float(max(0.,np.max(np.array(m.getAttr('LB'))-point),np.max(point-np.array(m.getAttr('UB'))))),
                worst_rows=[dict(index=int(i),name=m.getConstrs()[int(i)].ConstrName,sense=str(sense[i]),
                    RHS=float(rhs[i]),residual=float(residual[i]),violation=float(violation[i])) for i in top]))
            m.dispose()
    dump('MIP_START_TOLERANCE_AUDIT.json',dict(utc=stamp(),no_optimization=True,no_start_repair=True,
        sealed_Start_sha256=sha(LOCAL/'AXIS_START.npz'),models=rows,
        independent_physical_validation_PASS=read('MIP_START_PHYSICAL_VALIDATION.json')['PASS'],
        interpretation='The independently validated physical point is preserved. Unscaled native row residuals exceed the registered solver tolerance. This is a plausible Start rejection cause, not a solver-reported causal diagnosis; no tolerance, Start, bounds or physical variables are changed.'))
    print(rows,flush=True)

if __name__=='__main__':main()
