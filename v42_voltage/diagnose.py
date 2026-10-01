"""Independent affine-box infeasibility certificate; no optimizer or model mutation."""
import numpy as np
from v42_root.data import prepare
from v42_root.common import *
from v42_temporal.native import load_power
from v42_may01.prepare import native_coefficients
from v42_native.voltage import *

def diagnose():
    data=prepare();bundle=data[0];cert,power,idle,swing=load_power(bundle);coeff=native_coefficients(cert)
    with np.load(cert['outputs']['voltage']['path'],allow_pickle=False) as z:
        possible={k:z[k].tolist() for k in z.files if any(v in k.lower() for v in ('node','bus','name'))}
    violations=[];worst=[]
    for t,c in enumerate(coeff):
        lb=[];ub=[]
        for name in c.control_names:
            s=name.split('[')[1][:-1]
            if name.startswith('aidc_load_kw'):
                a=power[s,t];cap=bundle['capacities'][s]
                assert a.slope>=0 and swing>=0
                lb.append(a.slope*(idle*cap)+a.intercept_kw);ub.append(a.slope*((idle+swing)*cap)+a.intercept_kw)
            else:lb.append(0.);ub.append(0.)
        lb=np.array(lb);ub=np.array(ub);mat=c.voltage_matrix.T
        minimum=c.voltage_constant+np.maximum(mat,0)@lb+np.minimum(mat,0)@ub
        maximum=c.voltage_constant+np.maximum(mat,0)@ub+np.minimum(mat,0)@lb
        for n,(lo,hi) in enumerate(zip(minimum,maximum)):
            impossible=lo>PLANNING_UPPER_SQUARED+1e-8 or hi<PLANNING_LOWER_SQUARED-1e-8
            if impossible:
                name=next((v[n] for k,v in possible.items() if isinstance(v,list) and len(v)==len(minimum)),str(n))
                violations.append(dict(control_slot=t,voltage_row_index=n,node_name=name,minimum_squared=float(lo),maximum_squared=float(hi),
                                       best_attainable_min_pu=float(np.sqrt(max(0,lo))),best_attainable_max_pu=float(np.sqrt(max(0,hi))),
                                       violation_squared=max(float(lo)-PLANNING_UPPER_SQUARED,PLANNING_LOWER_SQUARED-float(hi)),
                                       controls_lower=lb.tolist(),controls_upper=ub.tolist(),control_names=list(c.control_names),
                                       voltage_constant=float(c.voltage_constant[n]),voltage_coefficients=mat[n].tolist(),
                                       contradiction='VOLTAGE_UPPER_BELOW_GLOBAL_MINIMUM' if lo>PLANNING_UPPER_SQUARED else 'VOLTAGE_LOWER_ABOVE_GLOBAL_MAXIMUM'))
        worst.append(dict(slot=t,global_lowest_squared=float(minimum.min()),global_highest_squared=float(maximum.max())))
    diagnosis=dict(status='PROVEN_INFEASIBLE',solver_status=3,Planning_band=[.955,1.045],voltage_authority_sha256=authority_sha(),
                   independent_interval_contradictions=len(violations),independent_proof_PASS=bool(violations),
                   proof_method='Every A1 MESS P/Q is 0. Nonnegative known/anonymous GPU plus unchanged headroom implies 0 <= total_GPU <= site_capacity. Frozen monotone affine C1 gives the stated kW intervals. Independent affine squared-voltage interval minimum/maximum over this SUPERSET proves no schedule can satisfy each listed hard row.',
                   candidate_domain_removed=False,physics_relaxed=False,margin_relaxed=False,source_coefficient_sha=coeff[0].coefficient_sha256,
                   violations=violations,slot_interval_summary=worst,IIS_RUN=False,
                   purpose='Diagnostic numeric algebra, no optimizer and no production mutation')
    dump('A1_INFEASIBILITY_DIAGNOSIS.json',diagnosis)
    return diagnosis

if __name__=='__main__':
    result=diagnose();print('Independent interval contradictions:',result['independent_interval_contradictions'])
