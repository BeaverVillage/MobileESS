"""Current-case reference seed, completed and checked against every A row.

Only this disposable feasibility projection fixes the observed frozen reference
choice. The final complete-domain model remains unchanged and free.
"""
from dataclasses import asdict
from pathlib import Path
import numpy as np

from .m_engine import _write,vector_sha


def reference_assignments(model,units,data,choices=None):
    import gurobipy as gp
    from v42_compact.graph import old_to_compact
    from v42_job_capability import Option,validate
    result={};plans={}
    choices={} if choices is None else choices
    if set(choices)-set(data[1]):raise ValueError('SEED_CHOICE_UID_NOT_IN_CURRENT_DOMAIN')
    for uid,job in data[1].items():
        if uid in choices:
            row=dict(choices[uid]);row['segments']=tuple(tuple(r) for r in row['segments'])
            row['wan']=tuple(tuple(r) for r in row.get('wan',()))
            option=Option(**row)
        else:
            option=Option(job.reference_start,job.reference_site,
                ((job.reference_site,job.reference_start,job.reference_start+job.service_slots),))
        if option.migrated:raise ValueError('ALL_STAY_SEED_CANNOT_ASSIGN_MIGRATION_LANES')
        validate(job,option,data[2][uid],data[3])
        plans[uid]=asdict(option)
    for unit in units:
        uid=unit['uid'];job=data[1][uid]
        expected={}
        if not unit['optional']:
            members=unit['members'] if unit['stay_count'] else [uid]
            # Nonmigration native mapping is exactly old_to_compact; all WAN
            # families are zero. Accumulate each member's actual choice.
            for member in members:
                mapped=old_to_compact(Option(**plans[member]))
                for family,items in mapped.items():
                    target=expected.setdefault(family,{})
                    for key,value in items.items():target[key]=target.get(key,0.)+value
        for family,items in unit['v'].items():
            for key,value in items.items():
                if not isinstance(value,gp.Var):continue
                wanted=0. if unit['optional'] else float(expected.get(family,{}).get(key,0))
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


def project_reference_seed(model,units,data,budget,output,*,stage,seconds=30.,choices=None,iis_cap=None):
    import gurobipy as gp
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    receipt=dict(scope='DISPOSABLE_REFERENCE_ASSIGNMENT_FEASIBILITY_PROJECTION',
        final_domain_restricted=False,old_point_or_UB_reused=False,global_bound_certified=False)
    if choices:
        from .a_engine import digest
        receipt.update(seed_rule='SAME_FROZEN_REFERENCE_AUTHORIZED_PARTICIPANT_CHOICES',
            explicit_choice_UIDs=sorted(choices),choices_sha=digest(choices),
            shared_class_histograms='SUM_EXACT_MEMBER_MAPPINGS',reference_or_receipts_reissued=False)
        _write(output/'EXPLICIT_KNOWN_CHOICES.json',choices)
    try:fixed,plans=reference_assignments(model,units,data,choices)
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
        prior_context=getattr(budget,'stage_context',None)
        had_context=hasattr(budget,'stage_context')
        budget.stage_context=dict(prior_context or {},
            bound_scope='FIXED_KNOWN_FEASIBILITY_SEED_NOT_GLOBAL',
            seed_choice_sha=receipt.get('choices_sha'),reference_or_receipts_reissued=False)
        try:
            call=budget.solve(seed,label=stage+('_AUTHORIZED_CHOICES_FEASIBILITY_SEED'
                if choices else '_REFERENCE_FEASIBILITY_SEED'),cap=seconds)
        finally:
            if had_context:budget.stage_context=prior_context
            else:delattr(budget,'stage_context')
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
        else:
            receipt.update(status='REFERENCE_SEED_NOT_FOUND',global_infeasibility_claimed=False)
            if seed.Status==gp.GRB.INFEASIBLE and iis_cap:
                prior=getattr(budget,'stage_context',None);had=hasattr(budget,'stage_context')
                budget.stage_context=dict(prior or {},bound_scope='FIXED_KNOWN_IIS_NOT_FREE_A1_INFEASIBILITY',
                    seed_choice_sha=receipt.get('choices_sha'))
                diagnostic=None;rows=[];bounds=[];minimal=None;failure=None
                try:
                    diagnostic=budget.diagnose_iis(seed,label=stage+'_FIXED_CHOICES_IIS',cap=iis_cap)
                    rows=[dict(index=row.index,name=row.ConstrName,sense=row.Sense,RHS=row.RHS)
                        for row in seed.getConstrs() if row.IISConstr]
                    bounds=[dict(index=v.index,name=v.VarName,LB=v.LB,UB=v.UB,
                        IISLB=bool(v.IISLB),IISUB=bool(v.IISUB)) for v in seed.getVars() if v.IISLB or v.IISUB]
                    minimal=bool(seed.IISMinimal)
                except Exception as exc:failure=repr(exc)
                finally:
                    if had:budget.stage_context=prior
                    else:delattr(budget,'stage_context')
                doc=dict(scope='CURRENT_FIXED_KNOWN_CHOICES_SUBPROBLEM_ONLY',
                    original_free_A1_domain_infeasibility_proven=False,
                    diagnostic_cost=diagnostic,IIS_minimal=minimal,diagnostic_failure=failure,
                    status='IIS_CAPTURED' if rows or bounds else 'DIAGNOSTIC_NOT_CERTIFIED',
                    rows=rows,bounds=bounds,source_choices_sha=receipt.get('choices_sha'))
                _write(output/'INFEASIBLE_CHOICES_IIS.json',doc)
                receipt['infeasible_choices_IIS']=dict(path=str(output/'INFEASIBLE_CHOICES_IIS.json'),
                    rows=len(rows),bounds=len(bounds),IIS_minimal=doc['IIS_minimal'],diagnostic_cost=diagnostic)
        _write(output/'SEED_RECEIPT.json',receipt)
        return point,plans,receipt
    finally:seed.dispose()


def value_at(value,point):
    import gurobipy as gp
    if isinstance(value,gp.Var):return float(point[value.index])
    if isinstance(value,gp.LinExpr):
        return float(value.getConstant()+sum(value.getCoeff(i)*point[value.getVar(i).index] for i in range(value.size())))
    return float(value)
