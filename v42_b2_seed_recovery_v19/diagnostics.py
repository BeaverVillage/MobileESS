"""Candidate-only Farkas/Phase-I diagnostics; slack points are never admitted."""
from collections import Counter
import re
import numpy as np
from .common import atomic,now

def bounded_iis(case,model,out,seconds=15.):
    """IIS is analysis, not an optimize call; never invent its Native Runtime.

    Runtime is documented as the most recent optimization Runtime, so record
    separate measured wall time rather than charging a stale Runtime twice.
    """
    import time
    from collections import Counter
    old={k:getattr(model.Params,k) for k in ('TimeLimit','InfUnbdInfo','DualReductions')}
    started=time.perf_counter()
    try:
        model.Params.TimeLimit=seconds;model.Params.InfUnbdInfo=0;model.Params.DualReductions=1
        model.computeIIS()
        flags=model.getAttr('IISConstr');lb=model.getAttr('IISLB');ub=model.getAttr('IISUB')
        rows=[dict(index=i,name=str(case.d['row_names'][i]),category=category(case.d['row_names'][i]),
            sense=str(case.d['sense'][i]),rhs=float(case.d['rhs'][i])) for i,value in enumerate(flags) if value]
        bounds=[dict(index=j,name=str(case.d['names'][j]),category=category(case.d['names'][j]),
            lower_in_IIS=bool(lb[j]),upper_in_IIS=bool(ub[j]),lower=model.getVars()[j].LB,
            upper=model.getVars()[j].UB) for j in range(len(lb)) if lb[j] or ub[j]]
        result=dict(rows=rows,bounds=bounds,categories=dict(Counter(r['category'] for r in rows)),
            IISMinimal=bool(model.IISMinimal),scope='THIS_FIXED_CANDIDATE_ORIGINAL_ROW_SUBSYSTEM_ONLY',
            original_model_case_SHA=case.case_sha,Native_Runtime='UNKNOWN',
            diagnostic_wall_seconds=time.perf_counter()-started,TimeLimit=seconds,
            original_FULL_MILP_infeasibility_claimed=False,diagnostic_point_never_admitted=True)
        atomic(out/'IIS_DIAGNOSTIC.json',result);model.write(str(out/'CONFLICT.ilp'))
        return result
    except Exception as exc:
        atomic(out/'IIS_UNAVAILABLE.json',dict(error=repr(exc),Native_Runtime='UNKNOWN',
            diagnostic_wall_seconds=time.perf_counter()-started,TimeLimit=seconds));return None
    finally:
        for key,value in old.items():setattr(model.Params,key,value)

def category(name):
    family=str(name).removeprefix('FIXED_').split('[',1)[0]
    if family.startswith('voltage_'):return 'Voltage upper/lower'
    if family.startswith(('line_thermal','transformer','NormalAmps')):return 'Line/Transformer thermal'
    if family in ('initial_SOC','terminal_SOC'):return 'SOC initial/terminal'
    if family=='energy_balance':return 'SOC time coupling'
    if family in ('no_simultaneous_charge','no_simultaneous_discharge','charge_mode'):return 'Charging/discharging exclusivity'
    if family.startswith('PCS'):return 'PCS kVA'
    if family in ('flow','terminal_location','arc'):return 'Route flow'
    if family.startswith(('connected_','node_activity')):return 'ETA/connectivity'
    if family.startswith(('injection_P','injection_Q')):return 'Fixed AIDC PCC power'
    return 'Auxiliary reconstruction'

def farkas(case,model,out):
    dual=np.asarray(model.getAttr('FarkasDual'),dtype=float)
    names=list(map(str,case.d['row_names']))
    support=np.flatnonzero(dual!=0.)
    np.savez_compressed(out/'FARKAS_DUAL.npz',multipliers=dual)
    counts=Counter(category(names[i]) for i in support)
    rows=[dict(index=int(i),name=names[i],category=category(names[i]),multiplier=float(dual[i]),
        sense=str(case.d['sense'][i]),rhs=float(case.d['rhs'][i])) for i in support]
    aggregate=np.asarray(case.A.T@dual).reshape(-1)
    low=model.getAttr('LB');high=model.getAttr('UB')
    variables=[dict(index=int(j),name=str(case.d['names'][j]),category=category(case.d['names'][j]),
        weighted_coefficient=float(aggregate[j]),candidate_lower=low[j],candidate_upper=high[j])
        for j in np.flatnonzero(aggregate!=0.)]
    atomic(out/'FARKAS_DIAGNOSTIC.json',dict(UTC=now(),Native_FarkasProof=float(model.FarkasProof),
        categories=dict(counts),rows=rows,bound_contributions=variables,
        original_model_case_SHA=case.case_sha,scope='THIS_FIXED_CANDIDATE_ONLY',
        floating_Native_Farkas_diagnostic_not_independent_Global_certificate=True,
        original_FULL_MILP_infeasibility_claimed=False,diagnostic_support_not_constraint_deletion=True))
    return list(map(int,support))

def phase_one(case,model,budget,out,rows,seconds=15.):
    """Only a diagnostic model is softened; no point leaves this function."""
    import gurobipy as gp
    variables=model.getVars();constraints=model.getConstrs();slacks=[];metadata=[]
    original_obj=model.getAttr('Obj');objective=gp.LinExpr()
    try:
        for i in rows:
            sense=str(case.d['sense'][i]);weight=1./max(1.,abs(float(case.d['rhs'][i])))
            for sign in ((-1.,1.) if sense=='=' else (-1.,) if sense=='<' else (1.,)):
                slack=model.addVar(lb=0.,name=f'DIAGNOSTIC_ONLY_SLACK_{i}_{sign}')
                objective.addTerms(weight,slack);slacks.append(slack);metadata.append((i,sign,weight))
        model.update()
        for variable,(i,sign,weight) in zip(slacks,metadata):model.chgCoeff(constraints[i],variable,sign)
        model.setObjective(objective,gp.GRB.MINIMIZE);model.update();model.reset()
        budget.native_optimize(model,component='FEASIBILITY_LP',track='F4_PHASE_I',
            label='DIAGNOSTIC_ONLY_PHASE_I_SLACKS',requested_seconds=min(seconds,budget.remaining()))
        values=[]
        if model.SolCount:
            for variable,(i,sign,weight) in zip(slacks,metadata):
                if variable.X>0:
                    values.append(dict(row_index=i,name=str(case.d['row_names'][i]),category=category(case.d['row_names'][i]),
                        slack=float(variable.X),normalization_weight=weight,sign=sign))
        atomic(out/'PHASE_I_DIAGNOSTIC.json',dict(raw_status=int(model.Status),SolCount=int(model.SolCount),
            positive_slacks=values,diagnostic_point_never_admitted=True,
            no_original_FULL_feasibility_claim=True,normalization='1/MAX(1,ABS_ORIGINAL_ROW_RHS)'))
    finally:
        model.remove(slacks);model.update();model.setAttr('Obj',variables,original_obj);model.update()

def diagnose_model(case,model,budget,out,original_types,seconds=15.,run_phase_one=False):
    variables=model.getVars();old=dict(Method=model.Params.Method,DualReductions=model.Params.DualReductions,
        InfUnbdInfo=model.Params.InfUnbdInfo,SolutionLimit=model.Params.SolutionLimit)
    try:
        model.setAttr('VType',variables,['C']*len(variables));model.update();model.reset()
        model.Params.Method=1;model.Params.DualReductions=0;model.Params.InfUnbdInfo=1
        model.Params.SolutionLimit=2000000000
        budget.native_optimize(model,component='FEASIBILITY_LP',track='F4_FARKAS',
            label='F4_THIS_CANDIDATE_ORIGINAL_ROWS_LP',requested_seconds=min(seconds,budget.remaining()))
        status=int(model.Status)
        atomic(out/'DIAGNOSTIC_STATUS.json',dict(raw_status=status,SolCount=int(model.SolCount),
            DualReductions=0,InfUnbdInfo=1,scope='RESTRICTED_CANDIDATE_LP',FULL_infeasibility_claimed=False))
        if status==3:
            try:rows=farkas(case,model,out)
            except Exception as exc:
                atomic(out/'FARKAS_UNAVAILABLE.json',dict(raw_status=status,error=repr(exc),
                    FULL_MILP_infeasibility_claimed=False));rows=[]
            if run_phase_one and rows and budget.remaining()>0:
                phase_one(case,model,budget,out,rows[:128],seconds=min(15.,budget.remaining()))
        else:
            atomic(out/'FARKAS_UNAVAILABLE.json',dict(raw_status=status,
                reason='NO_INFEASIBLE_LP_CERTIFICATE',FULL_MILP_infeasibility_claimed=False))
    finally:
        model.setAttr('VType',variables,original_types);model.update()
        for name,value in old.items():setattr(model.Params,name,value)
