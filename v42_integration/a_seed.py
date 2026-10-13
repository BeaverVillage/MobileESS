"""Current-case reference seed, completed and checked against every A row.

Only this disposable feasibility projection fixes the observed frozen reference
choice. The final complete-domain model remains unchanged and free.
"""
from dataclasses import asdict
from pathlib import Path
import numpy as np

from .m_engine import _write,vector_sha


def reference_assignments(model,units,data):
    import gurobipy as gp
    from v42_root.factor import mapping
    from v42_job_capability import Option,validate
    result={};plans={}
    for uid,job in data[1].items():
        option=Option(job.reference_start,job.reference_site,
            ((job.reference_site,job.reference_start,job.reference_start+job.service_slots),))
        validate(job,option,data[2][uid],data[3])
        plans[uid]=asdict(option)
    for unit in units:
        uid=unit['uid'];job=data[1][uid]
        expected={} if unit['optional'] else mapping(job,data[5][uid],data[3],Option(**plans[uid]))
        count=len(unit['members']) if unit['stay_count'] else 1
        for family,items in unit['v'].items():
            for key,value in items.items():
                if not isinstance(value,gp.Var):continue
                wanted=0. if unit['optional'] else float(expected.get(family,{}).get(key,0))*count
                if value.index in result and result[value.index]!=wanted:
                    raise ValueError('REFERENCE_SEED_SHARED_VARIABLE_CONFLICT')
                if not value.LB-1e-9<=wanted<=value.UB+1e-9:
                    raise ValueError('REFERENCE_SEED_OUTSIDE_CURRENT_DOMAIN')
                result[value.index]=wanted
    return result,plans


def full_replay(model,point):
    point=np.asarray(point,float)
    if point.shape!=(model.NumVars,) or not np.isfinite(point).all():
        raise ValueError('A_CURRENT_POINT_AXIS')
    A=model.getA();lhs=A@point
    rhs=np.asarray(model.getAttr('RHS'),float);sense=np.asarray(model.getAttr('Sense'))
    rows=np.maximum.reduce([np.where(sense=='<',lhs-rhs,0),np.where(sense=='>',rhs-lhs,0),
                            np.where(sense=='=',abs(lhs-rhs),0)])
    lb=np.asarray(model.getAttr('LB'));ub=np.asarray(model.getAttr('UB'))
    kinds=np.asarray(model.getAttr('VType'));integral=kinds!='C'
    residual=max(float(np.max(rows,initial=0)),float(np.max(lb-point,initial=0)),
        float(np.max(point-ub,initial=0)),float(np.max(abs(point[integral]-np.rint(point[integral])),initial=0)))
    return dict(PASS=residual<=1e-5,FULL_max_residual=residual,rows=model.NumConstrs,
                columns=model.NumVars,point_sha256=vector_sha(point))


def project_reference_seed(model,units,data,budget,output,*,stage,seconds=30.):
    import gurobipy as gp
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    receipt=dict(scope='DISPOSABLE_REFERENCE_ASSIGNMENT_FEASIBILITY_PROJECTION',
        final_domain_restricted=False,old_point_or_UB_reused=False,global_bound_certified=False)
    try:fixed,plans=reference_assignments(model,units,data)
    except ValueError as exc:
        receipt.update(status='NO_REFERENCE_SEED',reason=str(exc),Native_optimize_calls=0)
        _write(output/'SEED_RECEIPT.json',receipt)
        return None,None,receipt
    seed=model.copy()
    try:
        variables=seed.getVars()
        for index,value in fixed.items():variables[index].LB=variables[index].UB=value
        seed.Params.LogFile=str(output/'NATIVE_SEED.log')
        seed.Params.OutputFlag=1
        call=budget.solve(seed,label=stage+'_REFERENCE_FEASIBILITY_SEED',cap=seconds)
        receipt.update(Native_call=call,Native_optimize_calls=1,status=int(seed.Status),
            local_fixed_variables=len(fixed),full_rows_retained=seed.NumConstrs==model.NumConstrs)
        point=None
        if seed.SolCount:
            point=np.asarray(seed.getAttr('X'),float)
            replay=full_replay(model,point)
            receipt['FULL_replay']=replay
            if not replay['PASS']:raise ValueError('A_REFERENCE_SEED_FULL_REPLAY_FAIL')
            np.savez_compressed(output/'CURRENT_CASE_SEED.npz',point=point)
            model.setAttr('Start',model.getVars(),point.tolist())
            model.update()
            if not np.array_equal(np.asarray(model.getAttr('Start')),point):
                raise ValueError('CURRENT_CASE_A_START_TRANSPORT_DRIFT')
            receipt.update(status='CURRENT_CASE_FULL_FEASIBLE_SEED',objective=float(seed.ObjVal),
                complete_Start_readback=np.array_equal(np.asarray(model.getAttr('Start')),point))
        else:receipt.update(status='REFERENCE_SEED_NOT_FOUND',global_infeasibility_claimed=False)
        _write(output/'SEED_RECEIPT.json',receipt)
        return point,plans,receipt
    finally:seed.dispose()


def value_at(value,point):
    import gurobipy as gp
    if isinstance(value,gp.Var):return float(point[value.index])
    if isinstance(value,gp.LinExpr):
        return float(value.getConstant()+sum(value.getCoeff(i)*point[value.getVar(i).index] for i in range(value.size())))
    return float(value)
