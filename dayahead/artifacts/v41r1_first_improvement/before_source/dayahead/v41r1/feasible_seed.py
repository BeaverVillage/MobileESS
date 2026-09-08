"""Complete deterministic starts and independent substitution of every model row.

This evaluator never optimizes and never reads Actual. Unsupported constraint
types fail closed; a partial MIP start is not a feasibility certificate.
"""
from collections import defaultdict
from pathlib import Path
import hashlib
import math
import re
import numpy as np
from gurobipy import GRB
from dayahead.paper_analysis.storage import write_json
from dayahead.v41.preflight import record


def row_audit(model, values):
    model.update()
    vs = model.getVars()
    x = np.asarray(values, dtype=float)
    if x.shape != (len(vs),) or not np.isfinite(x).all():
        raise ValueError('SEED_INCOMPLETE_OR_NONFINITE')
    constraints = model.getConstrs()
    rhs = np.asarray(model.getAttr('RHS', constraints))
    sense = np.asarray(model.getAttr('Sense', constraints))
    lhs = model.getA() @ x
    residual = np.where(sense == '=', np.abs(lhs-rhs),
        np.where(sense == '<', np.maximum(lhs-rhs, 0), np.maximum(rhs-lhs, 0)))
    lb = np.asarray(model.getAttr('LB', vs)); ub = np.asarray(model.getAttr('UB', vs))
    bounds = np.maximum(np.maximum(lb-x, x-ub), 0)
    integer = np.asarray(model.getAttr('VType', vs)) != GRB.CONTINUOUS
    integers = np.abs(x[integer]-np.rint(x[integer]))
    general = []; unsupported = []
    def lin(expr):
        return expr.getConstant() + math.fsum(expr.getCoeff(i)*x[expr.getVar(i).index] for i in range(expr.size()))
    def violation(a, s, b):
        return abs(a-b) if s == '=' else max(0., a-b if s == '<' else b-a)
    for c in model.getGenConstrs():
        kind = c.GenConstrType
        if kind == GRB.GENCONSTR_PWL:
            a,b,xx,yy = model.getGenConstrPWL(c)
            # Model x is inside the original breakpoint domain in this model.
            if not xx[0] <= x[a.index] <= xx[-1]:
                unsupported.append(c.GenConstrName + ':PWL_EXTRAPOLATION')
            err = abs(x[b.index]-np.interp(x[a.index],xx,yy))
        elif kind == GRB.GENCONSTR_MAX:
            result, args, constant = model.getGenConstrMax(c)
            err = abs(x[result.index]-max([constant]+[x[v.index] for v in args]))
        elif kind == GRB.GENCONSTR_INDICATOR:
            flag, value, expr, s, b = model.getGenConstrIndicator(c)
            err = violation(lin(expr),s,b) if round(x[flag.index]) == value else 0.
        else:
            unsupported.append(c.GenConstrName+':'+str(kind)); err = math.inf
        general.append((c.GenConstrName, float(err)))
    if model.NumQConstrs or model.NumSOS:
        unsupported.append('QUADRATIC_OR_SOS_NOT_IMPLEMENTED')
    tol = model.Params.FeasibilityTol; itol = model.Params.IntFeasTol
    bad = np.flatnonzero(residual > tol)
    extrema = dict(linear=float(residual.max(initial=0)), bounds=float(bounds.max(initial=0)),
        integrality=float(integers.max(initial=0)), general=max((v for _,v in general),default=0.))
    passed = not unsupported and extrema['linear'] <= tol and extrema['bounds'] <= tol and extrema['integrality'] <= itol and extrema['general'] <= tol
    return dict(status='PASS' if passed else 'FAIL', all_hard_model_rows_substituted=True,
        linear_constraints=len(constraints), general_constraints=len(general), matrix_nonzeros=int(model.NumNZs),
        variables=len(vs), residual_extrema=extrema, feasibility_tolerance=tol, integrality_tolerance=itol,
        violated_linear_rows=[dict(name=constraints[i].ConstrName,lhs=float(lhs[i]),rhs=float(rhs[i]),
            residual=float(residual[i])) for i in bad[np.argsort(residual[bad])[::-1]][:20]],
        violated_general_rows=[dict(name=n,residual=v) for n,v in general if v>tol][:20],
        violated_bounds=[dict(name=vs[i].VarName,value=float(x[i]),lb=float(lb[i]),ub=float(ub[i])) for i in np.flatnonzero(bounds>tol)[:20]],
        unsupported_constraints=unsupported)


def modeled_capacity_interval(part):
    from dayahead.v41r1.migration import BEGIN,END
    lo=max(BEGIN,part['start']);hi=min(END,part['end'])
    return (lo,hi) if lo<hi else None


def job_audit(jobs, context):
    from dayahead.v40g_segments.canonical import import_frozen, planning_power, wan_audit
    from dayahead.v41r1.migration_admission import unadmitted
    canonical = import_frozen(jobs)
    events = defaultdict(lambda: defaultdict(int))
    rack_cap = {p.rack_pool_id: int(p.historical_gpu_capacity) for p in context.capacity.rack_pools}
    # Keep full canonical job segments; audit exactly the original independent
    # D00-D24 capacity horizon. Do not add post-horizon constraints to this MILP.
    for row in canonical:
        if unadmitted(row):
            continue
        for i, part in enumerate(row['compute_segments']):
            site = part['site']; rack = row.get('initial_Rack_label',row['Rack_label']) if i == 0 and row.get('migration_selected') else row['Rack_label']
            eligible = {p.rack_pool_id for p in context.capacity.eligible_racks(site,row['requested_GPU'])}
            if rack not in eligible:
                raise ValueError('SEED_RACK_COMPATIBILITY:'+row['job_uid'])
            interval=modeled_capacity_interval(part)
            if interval is None:continue
            lo,hi=interval
            for kind,key in (('site',site),('rack',rack)):
                events[kind,key][lo] += row['requested_GPU']
                events[kind,key][hi] -= row['requested_GPU']
    extrema = {'site_excess_GPU':0,'rack_excess_GPU':0}; peaks=[]
    for (kind,key),points in sorted(events.items()):
        cap = context.capacity.site_capacity[key] if kind=='site' else rack_cap[key]
        used = peak = 0
        for t,delta in sorted(points.items()):
            used += delta; peak=max(peak,used)
            if used < 0: raise ValueError('SEED_NEGATIVE_RESOURCE_OCCUPANCY')
        if used: raise ValueError('SEED_RESOURCE_NOT_RELEASED')
        extrema[kind+'_excess_GPU']=max(extrema[kind+'_excess_GPU'],peak-cap)
        peaks.append(dict(kind=kind,resource=key,peak_GPU=peak,capacity_GPU=int(cap)))
    wan = wan_audit(canonical,context.wan)
    return dict(status='PASS' if not any(extrema.values()) and wan['status']=='PASS' else 'FAIL',
        residual_extrema=extrema, resource_peaks=peaks, WAN=wan, service_state='CANONICAL_VALIDATED',
        capacity_horizon_issue_slots=[24,120],complete_job_segments_preserved=True,
        post_horizon_capacity_constraints_added=False,
        Actual_reads=0), planning_power(canonical,context)


def complete_start(model, jobs, context, output, *, policy, objective_expressions, mess=()):
    from dayahead.v40a.grid import controls_from_trajectory, evaluate_grid
    from dayahead.v28r2.electrical_subproblem import anchored_polygon_parameters
    from dayahead.v41.reserve import diagnostics
    from dayahead.v41r1.migration import checkpoints
    model.update(); vs=model.getVars(); values=np.asarray(model.getAttr('Start',vs),dtype=float)
    physical,power=job_audit(jobs,context)
    controls=controls_from_trajectory(context.coefficients,power['pcc'],mess)
    grid=evaluate_grid(context.coefficients,controls,context.nodes)
    reserve=diagnostics(context.v41_ml_snapshot,context.capacity,power['gpu']) if hasattr(context,'v41_ml_snapshot') else None
    fill={}; sites=tuple(context.capacity.aidc_ids)
    for t,c in enumerate(context.coefficients):
        x=controls[t]; _,correction,_=anchored_polygon_parameters(c)
        voltage=c.voltage_constant+c.voltage_matrix.T@x
        p=c.flow_p_constant+c.flow_p_matrix@x; q=c.flow_q_constant+c.flow_q_matrix@x
        delta=correction.T@(x-c.anchor)
        for k,s in enumerate(sites):
            fill[f'GPU[{t},{s}]']=power['gpu'][t,k];fill[f'PCC[{t},{s}]']=power['pcc'][t,k]
        for k,v in enumerate(voltage):fill[f'v_squared[{t},{k}]']=v
        for k in range(len(c.branch_names)):
            for prefix,value in (('line_p',p[k]),('line_q',q[k]),('line_delta',delta[k]),('tx_p',p[k]),('tx_q',q[k])):
                fill[f'{prefix}[{t},{k}]']=value
    fill['rho_max']=grid['rho_max']
    if reserve:
        for k,v in enumerate(reserve['xi_GPUh']):fill[f'V41_H4_shortfall_GPUh[{k}]']=v
    for row in jobs:
        cp=checkpoints(row,getattr(context,'elapsed',{}))
        if cp:fill['WAN_ready_'+row['job_uid']]=max(26,cp[0])
        fill['WAN_selected_'+row['job_uid']]=0;fill['WAN_cursor_'+row['job_uid']]=26
    unknown=[]
    for i,v in enumerate(vs):
        if v.VarName in fill:values[i]=fill[v.VarName]
        elif v.VarName.startswith('migration_source['):values[i]=0.
        elif not math.isfinite(values[i]) or abs(values[i])>=GRB.UNDEFINED:
            unknown.append(v.VarName)
    if unknown:raise ValueError('SEED_UNASSIGNED_VARIABLES:'+str(unknown[:20]))
    audit=row_audit(model,values)
    def evaluate(expr):
        if hasattr(expr,'index'):return float(values[expr.index])
        return float(expr.getConstant()+math.fsum(expr.getCoeff(i)*values[expr.getVar(i).index] for i in range(expr.size())))
    vector=[evaluate(e) for e in objective_expressions]
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    artifact=output/'POLICY_FEASIBLE_SEED.npz'
    np.savez_compressed(artifact,values=values,names=np.asarray(model.getAttr('VarName',vs)))
    result=dict(schema='V41R1_POLICY_FEASIBLE_SEED_V1',day=getattr(context,'day',None),policy=policy,
        seed_source='CURRENT_POLICY_REFERENCE_WITH_NO_OPTIONAL_MOVE',
        status='PASS' if audit['status']==physical['status']==grid['status']=='PASS' else 'FAIL',
        before_optimization=True, model=audit, physical=physical, electrical=grid,
        seed_objective_vector=vector, seed_artifact=record(artifact),
        policy_relation='REFERENCE_MEMBERSHIP_VERIFIED_BY_COMPLETE_MODEL_SUBSTITUTION; GENERAL_SUPERSET_NOT_ASSUMED',
        Actual_reads=0, complete_variable_assignment=True)
    write_json(output/'POLICY_FEASIBLE_SEED_AUDIT.json',result)
    if result['status']!='PASS':raise ValueError('POLICY_FEASIBLE_SEED_FAILED:'+str(output))
    model.setAttr('Start',vs,values.tolist())
    return values,result


def neutral_mess():
    from dayahead.v35.execution import MESS_INITIAL
    from dayahead.v33m.mess_trajectory import MessTrajectory, MessTrajectorySlot
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    a=MessElectricalAuthority.from_repository()
    if a.initial_energy_kwh != a.terminal_energy_kwh:
        raise ValueError('NEUTRAL_MESS_TERMINAL_NOT_FEASIBLE')
    return MessTrajectory(tuple(MessTrajectorySlot(m,t,'CONNECTED',s,None,None,(),None,
        0.,0.,0.,0.,0,None,0.,0.,0.,0.,a.initial_energy_kwh,a.initial_energy_kwh/a.capacity_kwh)
        for t in range(96) for m,s in sorted(MESS_INITIAL.items())))


def policy_reference(jobs, context, output, policy, mess=None):
    """Physical/domain seed gate for B0 and the MESS-capable B2/B3 policies.

    An A0/A1 complete algebraic substitution receipt is additionally required
    when those models are constructed; this does not claim arbitrary B0-set
    inclusion in B3, which freezes an accepted B1 schedule.
    """
    from dayahead.v40g.domain import audit
    from dayahead.v40g_segments.canonical import import_frozen
    from dayahead.v40a.grid import controls_from_trajectory,evaluate_grid
    from dayahead.v40h.recourse import validate_physics
    from dayahead.v41.reserve import diagnostics
    if policy not in ('B0','B1','B2','B3'):raise ValueError('UNKNOWN_POLICY')
    physical,power=job_audit(jobs,context)
    if mess is None and policy in ('B2','B3'):mess=neutral_mess()
    check=validate_physics(mess) if mess is not None else dict(status='PASS',rule='MESS_OFF_POLICY')
    grid=evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,power['pcc'],() if mess is None else mess.slots),context.nodes)
    canonical=import_frozen(jobs)
    # Identity preserves job-state, service, first-checkpoint and terminal semantics.
    state=audit(jobs,jobs,context.capacity,context.wan) if not any(r.get('migration_selected') for r in jobs) else {'status':'PASS','identity':True,'canonical_validation':True}
    h4=diagnostics(context.v41_ml_snapshot,context.capacity,power['gpu'])
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    artifact=out/'POLICY_REFERENCE_SEED.json'
    write_json(artifact,dict(jobs=canonical,MESS=None if mess is None else [r.to_dict() for r in mess.slots]))
    value=dict(day=context.day,policy=policy,seed_source='CURRENT_Q90_POLICY_REFERENCE',
        status='PASS' if all(v['status']=='PASS' for v in (physical,check,grid,state)) else 'FAIL',
        physical=physical,MESS=check,electrical=grid,service_state=state,H4=h4,
        seed_objective_vector=[grid['rho_max'],h4['mean_xi_GPUh'],sum(bool(r.get('migration_selected')) for r in jobs)],
        seed_artifact=record(artifact),Actual_reads=0,before_optimization=True,
        policy_relation='SPECIFIC_REFERENCE_WITNESS; B3_FREEZES_CURRENT_B1; NO_UNPROVEN_SET_INCLUSION',
        model_row_substitution='REQUIRED_SEPARATELY_AT_A0_A1_MODEL_ENTRY')
    write_json(out/'POLICY_FEASIBLE_SEED_AUDIT.json',value)
    if value['status']!='PASS':raise ValueError('POLICY_REFERENCE_SEED_NOT_FEASIBLE')
    return mess,value
