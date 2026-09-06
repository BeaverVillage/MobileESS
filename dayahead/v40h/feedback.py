"""One AIDC feedback MILP with M1 controls fixed in every Planning row."""
from __future__ import annotations
from copy import deepcopy
from collections import defaultdict
import time
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from dayahead.v40a.grid import add_grid, controls_from_trajectory, evaluate_grid
from dayahead.v40a.invariants import H, BEGIN, route_sha, digest
from dayahead.v40a.feedback import authorized_options
from dayahead.v40g_segments.canonical import pcc_from_jobs, deviation as occupancy_deviation, terminal_audit, validate, require
from .primary import preserve



def candidates(row, capacity):
    validate(row)
    # Existing A1 authorization fixes every RUNNING choice, including all
    # accepted migration segments/events. R1 PENDING uses its common per-job
    # terminal-residual cap; only legacy callers retain exact post-H tails.
    from dayahead.v41r1.terminal import active
    if row['state_at_issue']=='RUNNING' or (row['end_slot']>H and not active(row)):
        return [deepcopy(row)]
    result=[]
    for site,start in authorized_options(row,capacity):
        value=deepcopy(row);end=start+row['safe_duration_slots']
        value.update(AIDC_site=site,start_slot=start,end_slot=end,
                     compute_segments=[{'site':site,'start':start,'end':end}])
        if active(row): value['post_H_site'] = site if end > H else None
        if site!='UNASSIGNED':
            value['Rack_label']=sorted(p.rack_pool_id for p in capacity.eligible_racks(site,row['requested_GPU']))[0]
        validate(value);result.append(value)
    return result

def solve_feedback(a0, m1, context, *, tolerance=1e-6, work_limit=60.0):
    from dayahead.v41r1.terminal import active
    if any(active(r) for r in a0):
        require(len(context.coefficients)==96,'SCIENTIFIC_DAY_MUST_HAVE_96_SLOTS')
    started=time.perf_counter(); frozen_route=route_sha(m1.slots); frozen_m1=digest(m1)
    p0,_=pcc_from_jobs(a0,context)
    fixed=controls_from_trajectory(context.coefficients,p0,m1.slots)
    initial=evaluate_grid(context.coefficients,fixed,context.nodes)
    if initial['status']!='PASS':raise ValueError('A1_REQUIRES_FEASIBLE_M1')
    model=gp.Model('V40G_SEGMENT_AIDC_FEEDBACK');model.Params.OutputFlag=0
    model.Params.Threads=4;model.Params.Seed=20260905;model.Params.MIPGap=0;model.Params.MIPGapAbs=0
    model.Params.FeasibilityTol=1e-8;model.Params.IntFeasTol=1e-9;model.Params.OptimalityTol=1e-8
    model.Params.WorkLimit=work_limit;model.Params.SoftMemLimit=8;model.Params.NodefileStart=1
    sites=tuple(context.capacity.aidc_ids);load=defaultdict(gp.LinExpr)
    variables={};options={};deviation=gp.LinExpr();tie=gp.LinExpr()
    try:
        for i,row in enumerate(a0):
            options[i]=candidates(row,context.capacity)
            require(any(x['compute_segments']==row['compute_segments'] for x in options[i]), 'A0_OUTSIDE_AUTHORIZED_DOMAIN')
            vs=[]
            for k,candidate in enumerate(options[i]):
                from dayahead.v41r1.terminal import active
                fixed_r1 = active(row) and len(options[i]) == 1
                v=1 if fixed_r1 else model.addVar(vtype=GRB.BINARY,name=f'job[{i},{k}]')
                variables[i,k]=v;vs.append(v)
                if not fixed_r1: v.Start=float(candidate['compute_segments']==row['compute_segments'])
                for part in candidate['compute_segments']:
                    for t in range(max(BEGIN,int(part['start'])),min(H,int(part['end']))):
                        load[t-BEGIN,part['site']]+=int(row['requested_GPU'])*v
                deviation+=occupancy_deviation(row,candidate)*v
                tie+=(k+1)*(i+1)*v
            model.addConstr(gp.quicksum(vs)==1,name=f'gang_indivisible[{i}]')
        controls=[list(fixed[t]) for t in range(96)]
        for t in range(96):
            for i,s in enumerate(sites):
                cap=int(context.capacity.site_capacity[s]);values=context.tables[s][t]
                g=model.addVar(vtype=GRB.INTEGER,lb=0,ub=cap,name=f'GPU[{t},{s}]')
                p=model.addVar(lb=float(values.min()),ub=float(values.max()),name=f'PCC[{t},{s}]')
                model.addConstr(g==load[t,s]);model.addGenConstrPWL(g,p,list(range(cap+1)),values.tolist())
                controls[t][i]=p
        rho,grid_rows=add_grid(model,context.coefficients,controls,min(1,initial['rho_max']+tolerance))
        reserve_mean = None
        if hasattr(context, 'v41_ml_snapshot'):
            from dayahead.v41.reserve import add_constraints
            reserve_mean, reserve_xi = add_constraints(model, context, load)
        model.setObjective(rho,GRB.MINIMIZE);model.optimize();stages=[]
        def record(label):
            stages.append({'objective':label,'status':int(model.Status),'incumbent':float(model.ObjVal) if model.SolCount else None,
                           'bound':float(model.ObjBound) if model.IsMIP and model.SolCount else None,
                           'solver_runtime_seconds':float(model.Runtime),'work':float(model.Work),
                           'global_optimality_certified':False,'surrogate_solver_optimal':model.Status==GRB.OPTIMAL,
                           'optimality_scope':'Frozen affine/polyhedral Planning surrogate only'})
        record('rho_max')
        if not model.SolCount:return {'status':'NO_INCUMBENT','jobs':deepcopy(a0),'solver':stages,'wallclock_seconds':time.perf_counter()-started}
        # Save incumbent before another solve; limit termination must never discard it.
        value=lambda v: v if isinstance(v,int) else v.X
        chosen={i:next(k for k in range(len(options[i])) if value(variables[i,k])>.5) for i in options}
        accepted_primary=float(rho.X)
        primary_jobs=[deepcopy(options[i][chosen[i]]) for i in range(len(a0))]
        def recompute(current):
            pp,_=pcc_from_jobs(current,context)
            return evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,pp,m1.slots),context.nodes)['rho_max']
        primary_materialized=float(recompute(primary_jobs))
        model.addConstr(1000*rho<=1000*accepted_primary,name='PRIMARY_EXACT_VALUE_LOCK')
        if reserve_mean is not None:
            stages[-1]['freeze_for_subsequent_stage'] = dict(name='PRIMARY_EXACT_VALUE_LOCK', sense='<=',
                scale=1000, bound=accepted_primary, intentional_degradation=0., feasibility_tolerance=model.Params.FeasibilityTol)
        reserve_optimum = None
        if reserve_mean is not None:
            model.setObjective(reserve_mean, GRB.MINIMIZE); model.optimize(); record('V41_mean_H4_shortfall_GPUh')
            if not model.SolCount:
                raise RuntimeError('V41_A1_RESERVE_STAGE_NO_INCUMBENT')
            reserve_optimum = float(reserve_mean.getValue())
            model.addConstr(reserve_mean <= reserve_optimum + model.Params.FeasibilityTol,
                            name='V41_MEAN_H4_SHORTFALL_LOCK')
            stages[-1]['freeze_for_subsequent_stage'] = dict(name='V41_MEAN_H4_SHORTFALL_LOCK', sense='<=',
                bound=reserve_optimum + model.Params.FeasibilityTol, feasibility_tolerance=model.Params.FeasibilityTol)
            chosen={i:next(k for k in range(len(options[i])) if value(variables[i,k])>.5) for i in options}
            # Lower priorities must fall back to the accepted P1/P2 decision.
            reserve_jobs=[deepcopy(options[i][chosen[i]]) for i in range(len(a0))]
            reserve_materialized=float(recompute(reserve_jobs))
            if reserve_materialized > primary_materialized + 1e-10:
                raise RuntimeError('V41_A1_PRIMARY_SACRIFICED_IN_RESERVE_STAGE')
            primary_jobs=reserve_jobs
            primary_materialized=reserve_materialized
        model.setObjective(deviation,GRB.MINIMIZE);model.optimize();record('complete_segment_site_symmetric_GPU_slots')
        if model.SolCount:
            chosen={i:next(k for k in range(len(options[i])) if value(variables[i,k])>.5) for i in options}
            if model.Status==GRB.OPTIMAL:
                model.addConstr(deviation<=round(deviation.getValue()),name='SECONDARY_EXACT_CAP')
                if reserve_mean is not None:
                    stages[-1]['freeze_for_subsequent_stage'] = dict(name='SECONDARY_EXACT_CAP', sense='<=', bound=round(deviation.getValue()))
                model.setObjective(tie,GRB.MINIMIZE);model.optimize();record('deterministic_tie')
                if model.SolCount:chosen={i:next(k for k in range(len(options[i])) if value(variables[i,k])>.5) for i in options}
        jobs=[deepcopy(options[i][chosen[i]]) for i in range(len(a0))]
        jobs,primary_guard=preserve(primary_jobs,primary_materialized,jobs,recompute)
        audit=terminal_audit(a0,jobs);pcc,_=pcc_from_jobs(jobs,context)
        result=evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,pcc,m1.slots),context.nodes)
        if route_sha(m1.slots)!=frozen_route or digest(m1)!=frozen_m1:raise ValueError('A1_MUTATED_MESS')
        v41 = {}
        if reserve_mean is not None:
            from dayahead.v41.reserve import diagnostics, OBJECTIVE_HIERARCHY
            _, gpu = pcc_from_jobs(jobs, context)
            reserve_report = diagnostics(context.v41_ml_snapshot, context.capacity, gpu)
            if reserve_report['mean_xi_GPUh'] > reserve_optimum + 2 * model.Params.FeasibilityTol:
                raise RuntimeError('V41_A1_RESERVE_PRIORITY_SACRIFICED')
            v41 = dict(ML_snapshot_sha256=context.v41_ml_snapshot_sha256, reserve_interface_version='V41',
                       reserve_diagnostics=reserve_report, reserve_optimum=reserve_optimum,
                       objective_hierarchy=list(OBJECTIVE_HIERARCHY),
                       OBJECTIVE_VECTOR=[result['rho_max'], reserve_report['mean_xi_GPUh'],
                           sum(bool(r.get('migration_selected')) for r in jobs),
                           sum(occupancy_deviation(old, new) for old, new in zip(a0, jobs)),
                           sum((i+1)*(next(k for k, opt in enumerate(options[i]) if opt == job)+1)
                               for i, job in enumerate(jobs))],
                       P3_fixed_by_existing_RUNNING_decision=True)
        return {'status':'PASS' if audit['status']=='PASS' and result['status']=='PASS' else 'FAIL','jobs':jobs,'grid':result,
                'terminal_audit':audit,'solver':stages,'Gurobi_optimize_calls':len(stages),'grid_rows':grid_rows,
                'A1_primary_incumbent':stages[0]['incumbent'],'A1_primary_bound':stages[0]['bound'],
                'A1_final_recomputed_rho':result['rho_max'],'A1_primary_degradation_due_to_lower_priorities':primary_guard['primary_degradation_due_to_lower_priorities'],
                'strict_primary_guard':primary_guard,'M1_fixed_controls_SHA':digest(fixed[:,12:]),'M1_route_SHA':frozen_route,
                'running_migrations_added':0,'wallclock_seconds':time.perf_counter()-started, **v41}
    finally:model.dispose()
