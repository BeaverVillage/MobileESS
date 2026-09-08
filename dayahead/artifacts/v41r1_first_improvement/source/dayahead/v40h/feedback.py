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
    from dayahead.v41r1.migration import fixed_pending
    if fixed_pending(row) or row.get('migration_selected'):return [deepcopy(row)]
    # Existing A1 authorization fixes every RUNNING choice, including all
    # accepted migration segments/events. It also fixes exact post-H tails.
    if row['state_at_issue']=='RUNNING' or row['end_slot']>H:
        return [deepcopy(row)]
    result=[]
    for site,start in authorized_options(row,capacity):
        value=deepcopy(row);end=start+row['safe_duration_slots']
        value.update(AIDC_site=site,start_slot=start,end_slot=end,
                     compute_segments=[{'site':site,'start':start,'end':end}])
        if site!='UNASSIGNED':
            value['Rack_label']=sorted(p.rack_pool_id for p in capacity.eligible_racks(site,row['requested_GPU']))[0]
        validate(value);result.append(value)
    return result

def solve_feedback(a0, m1, context, *, tolerance=1e-6, work_limit=60.0):
    from dayahead.v41r1.migration_admission import physical_parts
    started=time.perf_counter(); frozen_route=route_sha(m1.slots); frozen_m1=digest(m1)
    p0,_=pcc_from_jobs(a0,context)
    fixed=controls_from_trajectory(context.coefficients,p0,m1.slots)
    initial=evaluate_grid(context.coefficients,fixed,context.nodes)
    if initial['status']!='PASS':raise ValueError('A1_REQUIRES_FEASIBLE_M1')
    model=gp.Model('V40G_SEGMENT_AIDC_FEEDBACK');model.Params.OutputFlag=0
    model.Params.Threads=4;model.Params.Seed=20260905;model.Params.MIPGap=0;model.Params.MIPGapAbs=0
    model.Params.FeasibilityTol=1e-8;model.Params.IntFeasTol=1e-9;model.Params.OptimalityTol=1e-8
    model.Params.WorkLimit=work_limit;model.Params.SoftMemLimit=GRB.INFINITY;model.Params.MemLimit=GRB.INFINITY;model.Params.NodefileStart=.5
    sites=tuple(context.capacity.aidc_ids);load=defaultdict(gp.LinExpr)
    variables={};options={};deviation=gp.LinExpr();tie=gp.LinExpr();engine=None
    bounded=bool(getattr(context,'v41_bounded_compute',None));gpu_variables={}
    def solution_value(expr):
        if engine is not None:return engine.value(expr)
        if isinstance(expr,(int,float)):return float(expr)
        return expr.X if isinstance(expr,gp.Var) else expr.getValue()
    try:
        for i,row in enumerate(a0):
            options[i]=candidates(row,context.capacity)
            require(any(x['compute_segments']==row['compute_segments'] for x in options[i]), 'A0_OUTSIDE_AUTHORIZED_DOMAIN')
            vs=[]
            for k,candidate in enumerate(options[i]):
                v=1 if bounded and len(options[i])==1 else model.addVar(vtype=GRB.BINARY,name=f'job[{i},{k}]')
                variables[i,k]=v
                if not isinstance(v,int):
                    vs.append(v);v.Start=float(candidate['compute_segments']==row['compute_segments'])
                for part in physical_parts(candidate,candidate['compute_segments']):
                    if bounded:
                        from dayahead.v41r1.migration_load import add_interval
                        add_interval(load,part['site'],int(part['start']),int(part['end']),int(row['requested_GPU'])*v,96,event_form=True)
                    else:
                        for t in range(max(BEGIN,int(part['start'])),min(H,int(part['end']))):
                            load[t-BEGIN,part['site']]+=int(row['requested_GPU'])*v
                deviation+=occupancy_deviation(row,candidate)*v
                tie+=(k+1)*(i+1)*v
            if vs:model.addConstr(gp.quicksum(vs)==1,name=f'gang_indivisible[{i}]')
        controls=[list(fixed[t]) for t in range(96)]
        for t in range(96):
            for i,s in enumerate(sites):
                cap=int(context.capacity.site_capacity[s]);values=context.tables[s][t]
                g=model.addVar(vtype=GRB.INTEGER,lb=0,ub=cap,name=f'GPU[{t},{s}]')
                p=model.addVar(lb=float(values.min()),ub=float(values.max()),name=f'PCC[{t},{s}]')
                gpu_variables[t,s]=g
                rhs=load[t,s]+(gpu_variables[t-1,s] if bounded and t else 0)
                model.addConstr(g==rhs);model.addGenConstrPWL(g,p,list(range(cap+1)),values.tolist())
                controls[t][i]=p
        rho,grid_rows=add_grid(model,context.coefficients,controls,min(1,initial['rho_max']+tolerance))
        reserve_mean = None
        if hasattr(context, 'v41_ml_snapshot'):
            from dayahead.v41.reserve import add_constraints
            reserve_mean, reserve_xi = add_constraints(model, context, gpu_variables if bounded else load)
        stages=[]
        if bounded:
            from pathlib import Path
            from dayahead.v41r1.feasible_seed import complete_start,job_audit
            from dayahead.v41r1.bounded_solver import BoundedLex
            from dayahead.paper_analysis.storage import write_json
            output=Path(context.v41_a1_output);output.mkdir(parents=True,exist_ok=True)
            fixed_migrations=gp.LinExpr(sum(bool(r.get('migration_selected')) for r in a0))
            expressions=[rho,reserve_mean if reserve_mean is not None else gp.LinExpr(),fixed_migrations,deviation,tie]
            seed,seed_audit=complete_start(model,a0,context,output,policy='B3',objective_expressions=expressions,mess=m1.slots)
            metadata={i:dict(members=[r['job_uid']],state=r['state_at_issue'],candidate_count=len(options[i]),
                can_relocate=len(options[i])>1,can_migrate=False,touched_sites=sorted({c['AIDC_site'] for c in options[i]}),
                earliest_effect=r['start_slot'],latest_effect=r['end_slot']) for i,r in enumerate(a0)}
            write_json(output/'V41R1_FULL_CANDIDATE_MANIFEST.json',dict(policy='B3',stage='A1',
                day=context.day,status='PASS',candidate_set_SHA=digest(options),jobs=metadata,candidates=options,
                final_authoritative_candidates=sum(len(v) for v in options.values()),
                PENDING_relocation_candidates=sum(sum(c['AIDC_site']!=a0[i]['AIDC_site'] for c in choices) for i,choices in options.items()),
                RUNNING_migration_candidates=0,total_destination_arcs=sum(max(0,len(v)-1) for v in options.values()),
                eligible_relocation_jobs=sum(len(v)>1 for v in options.values()),eligible_migration_jobs=0,
                reason_counts={},removal_scope='THIS_COMPUTE_REVISION; ORIGINAL_A1_POLICY_AUTHORITY_UNCHANGED',
                hard_infeasible_removals=0,top_K_pruning=0,sensitivity_pruning=0,
                frozen_RUNNING_migration='EXACT_ACCEPTED_B1_EVENTS_UNCHANGED',fixed_planned_starts=True))
            def validate_materialized():
                rows=[deepcopy(next(options[i][k] for k in range(len(options[i])) if solution_value(variables[i,k])>.5)) for i in options]
                physical,power=job_audit(rows,context)
                grid=evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,power['pcc'],m1.slots),context.nodes)
                term=terminal_audit(a0,rows)
                from dayahead.v41.reserve import diagnostics
                reserve_check=diagnostics(context.v41_ml_snapshot,context.capacity,power['gpu'])
                return dict(status='PASS' if physical['status']==grid['status']==term['status']=='PASS' else 'FAIL',
                    physical=physical,grid=grid,terminal=term,job_decision_SHA=digest(rows),
                    materialized_jobs=rows,materialized_power=power,
                    canonical_auxiliary_values={'rho_max':grid['rho_max'],
                        **{f'V41_H4_shortfall_GPUh[{k}]':v for k,v in enumerate(reserve_check['xi_GPUh'])}})
            context.v41_policy_budget.charge(time.perf_counter()-started,'A1_BUILD_VERIFY_SEED_AND_CANDIDATES')
            engine=BoundedLex(model,seed,output,context.v41_policy_budget,allocation=(900,480,390,30),
                metadata=metadata,context=context,fixed_mess=m1.slots,objective_expressions=expressions,validator=validate_materialized)
        def record(label, attempts):
            from dayahead.v41r1.migration_solver_policy import certificate
            entry={'objective':label,'status':int(model.Status),'incumbent':float(model.ObjVal) if model.SolCount else None,
                   'bound':float(model.ObjBound) if model.IsMIP and model.SolCount else None,
                   'solver_runtime_seconds':float(model.Runtime),'work':float(model.Work),
                   'global_optimality_certified':False,'surrogate_solver_optimal':model.Status==GRB.OPTIMAL,
                   'optimality_scope':'Frozen affine/polyhedral Planning surrogate only','attempts':attempts}
            entry.update(certificate(model));stages.append(entry)
        def optimize(label):
            if engine is not None:
                entry=engine.optimize(label);entry['objective']=label;stages.append(entry);return
            from dayahead.v41r1.migration_solver_policy import apply_gap
            apply_gap(model,label,revision=hasattr(context,'v41_ml_snapshot'),policy='B3')
            tier=0;attempts=[]
            while True:
                limit=work_limit*(3**tier);model.Params.WorkLimit=limit;model.optimize()
                attempts.append({'status':int(model.Status),'work_limit':limit,'work':float(model.Work),
                    'incumbent':float(model.ObjVal) if model.SolCount else None,
                    'bound':float(model.ObjBound) if model.IsMIP and model.SolCount else None})
                if model.Status==GRB.OPTIMAL or model.Status!=GRB.WORK_LIMIT or model.Params.MIPGap==0.:break
                tier+=1
            record(label,attempts)
            if model.Params.MIPGap>0. and model.Status!=GRB.OPTIMAL:
                raise RuntimeError(label+'_REGISTERED_GAP_NOT_CERTIFIED')
        model.setObjective(rho,GRB.MINIMIZE);optimize('rho_max')
        if engine is None and not model.SolCount:return {'status':'NO_INCUMBENT','jobs':deepcopy(a0),'solver':stages,'wallclock_seconds':time.perf_counter()-started}
        # Save incumbent before another solve; limit termination must never discard it.
        chosen={i:next(k for k in range(len(options[i])) if solution_value(variables[i,k])>.5) for i in options}
        accepted_primary=float(solution_value(rho))
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
            model.setObjective(reserve_mean, GRB.MINIMIZE);optimize('V41_mean_H4_shortfall_GPUh')
            if engine is None and not model.SolCount:
                raise RuntimeError('V41_A1_RESERVE_STAGE_NO_INCUMBENT')
            reserve_optimum = float(solution_value(reserve_mean))
            model.addConstr(reserve_mean <= reserve_optimum + model.Params.FeasibilityTol,
                            name='V41_MEAN_H4_SHORTFALL_LOCK')
            stages[-1]['freeze_for_subsequent_stage'] = dict(name='V41_MEAN_H4_SHORTFALL_LOCK', sense='<=',
                bound=reserve_optimum + model.Params.FeasibilityTol, feasibility_tolerance=model.Params.FeasibilityTol)
            chosen={i:next(k for k in range(len(options[i])) if solution_value(variables[i,k])>.5) for i in options}
            # Lower priorities must fall back to the accepted P1/P2 decision.
            reserve_jobs=[deepcopy(options[i][chosen[i]]) for i in range(len(a0))]
            reserve_materialized=float(recompute(reserve_jobs))
            if reserve_materialized > primary_materialized + 1e-10:
                raise RuntimeError('V41_A1_PRIMARY_SACRIFICED_IN_RESERVE_STAGE')
            primary_jobs=reserve_jobs
            primary_materialized=reserve_materialized
        model.setObjective(deviation,GRB.MINIMIZE);optimize('complete_segment_site_symmetric_GPU_slots')
        if engine is not None or model.SolCount:
            chosen={i:next(k for k in range(len(options[i])) if solution_value(variables[i,k])>.5) for i in options}
            if engine is not None or model.Status==GRB.OPTIMAL:
                model.addConstr(deviation<=round(solution_value(deviation)),name='SECONDARY_EXACT_CAP')
                if reserve_mean is not None:
                    stages[-1]['freeze_for_subsequent_stage'] = dict(name='SECONDARY_EXACT_CAP', sense='<=', bound=round(solution_value(deviation)))
                model.setObjective(tie,GRB.MINIMIZE);optimize('deterministic_tie')
                if engine is not None or model.SolCount:chosen={i:next(k for k in range(len(options[i])) if solution_value(variables[i,k])>.5) for i in options}
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
