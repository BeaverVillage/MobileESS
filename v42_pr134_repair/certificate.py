"""Certificate-only continuation for a saved original IIS, never a day rerun."""
import argparse
import gurobipy as gp,numpy as np
from .common import *
from .static_gate import arrays
from .original_diagnosis import exact_ray

def run(day):
    from v42_a_stage_domain_v2.execution import require_action_authorized,tag_model_for_day
    require_action_authorized(day,'FEASIBILITY_LP')
    target=CASE/day;out=OUT/(label(day)+'_ORIGINAL_BOUND_COMPLETE_CERTIFICATE.json')
    if out.exists():raise PermissionError('CERTIFICATE_ATTEMPT_ALREADY_RECORDED')
    diagnostic=read(OUT/(label(day)+'_ORIGINAL_NATIVE_DIAGNOSIS.json'))
    if diagnostic['status']!=gp.GRB.INFEASIBLE:raise PermissionError('ORIGINAL_INFEASIBLE_DIAGNOSTIC_REQUIRED')
    rows=np.array(diagnostic['IIS_rows']);a,z=arrays(target,'A0');columns=np.unique(a[rows].indices);small=a[rows][:,columns]
    iz=dict(lb=z['lb'][columns],ub=z['ub'][columns],rhs=z['rhs'][rows],sense=z['sense'][rows])
    m=gp.Model('SAVED_ORIGINAL_IIS_ALL_ORIGINAL_BOUNDS');m.Params.OutputFlag=0
    tag_model_for_day(m,day)
    x=m.addMVar(len(columns),lb=iz['lb'],ub=iz['ub']);m.addMConstr(small,x,iz['sense'],iz['rhs']);m.update()
    m.Params.Threads=1;m.Params.Method=1;m.Params.InfUnbdInfo=1;m.Params.DualReductions=0
    m.Params.TimeLimit=max(0,BUDGET-diagnostic['diagnostic_budget_used']);m.Params.LogFile=str(target/'BOUND_COMPLETE_CERTIFICATE.log')
    m.optimize()
    result=dict(day=day,status=m.Status,native_runtime=m.Runtime,original_IIS_rows=len(rows),columns=len(columns),
        all_original_bounds_retained=True,integrality_relaxed_only=True,scientific_model_changed=False,
        continuation_reason='Initial certificate relaxation omitted implicit binary bounds through IISLB/IISUB; original IIS itself retained them. No production implementation defect.',
        diagnostic_budget_used=diagnostic['diagnostic_budget_used']+m.Runtime)
    if m.Status==gp.GRB.INFEASIBLE:
        ray=np.array(m.getAttr('FarkasDual'));cert=exact_ray(small,iz,ray)
        np.savez_compressed(target/'BOUND_COMPLETE_RAW_FARKAS.npz',ray=ray,rows=rows,columns=columns)
        atomic(target/'BOUND_COMPLETE_EXACT_FARKAS.json',cert)
        result.update(raw_FarkasProof=m.FarkasProof,exact_certificate_PASS=cert['PASS'],
            exact_summary={k:v for k,v in cert.items() if k not in ('rows','bound_terms')},
            raw_ray=record(target/'BOUND_COMPLETE_RAW_FARKAS.npz'),certificate=record(target/'BOUND_COMPLETE_EXACT_FARKAS.json'))
    elif m.Status==gp.GRB.OPTIMAL:
        np.savez_compressed(target/'BOUND_COMPLETE_IIS_LP_FEASIBLE_POINT.npz',values=np.array(m.getAttr('X')),rows=rows,columns=columns)
    m.dispose();atomic(out,result);print(day,result,flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('day',choices=DAYS);run(parser.parse_args().day)
