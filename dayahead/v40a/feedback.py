"""One AIDC feedback MILP with M1 controls fixed in every Planning row."""
from __future__ import annotations
from copy import deepcopy
from collections import defaultdict
import time
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from .grid import add_grid, controls_from_trajectory, evaluate_grid
from .invariants import H, BEGIN, occupancy_deviation, terminal_audit, route_sha, digest


def authorized_options(row, capacity):
    """Inherited standby RW-completion domain, intersected with exact A0 terminal equality.

    RUNNING decisions and checkpoint/WAN state are fixed. The user confirmed
    that feasible A0/M1 does not authorize new performance-driven migrations.
    """
    if row['state_at_issue']=='RUNNING' or row['end_slot']>H:
        return [(row['AIDC_site'],int(row['start_slot']))]
    gpu=int(row['requested_GPU']);duration=int(row['safe_duration_slots'])
    if row['eligible_standby']:
        lo=int(row['RSP_start_slot']);hi=min(int(row['RW_completion_slot'])-duration,H-duration)
    else:lo=hi=int(row['start_slot'])
    if lo>hi:raise ValueError('EMPTY_AUTHORIZED_TEMPORAL_DOMAIN:'+row['job_uid'])
    sites=tuple(s for s in capacity.aidc_ids if capacity.site_capacity[s]>=gpu and capacity.eligible_racks(s,gpu))
    result=[]
    for start in range(lo,hi+1):
        if start+duration<=BEGIN:
            result.append((row['AIDC_site'],start))
        else:result.extend((s,start) for s in sites)
    return sorted(set(result))


def pcc_from_jobs(jobs, context):
    sites=tuple(context.capacity.aidc_ids);occ=np.zeros((96,len(sites)),dtype=int)
    for row in jobs:
        start=max(BEGIN,int(row['start_slot']));end=min(H,int(row['end_slot']))
        if start<end:
            occ[start-BEGIN:end-BEGIN,sites.index(row['AIDC_site'])]+=int(row['requested_GPU'])
    if any(np.any(occ[:,i]>context.capacity.site_capacity[s]) for i,s in enumerate(sites)):
        raise ValueError('SITE_CAPACITY_VIOLATION')
    pcc=np.column_stack([context.tables[s][np.arange(96),occ[:,i]] for i,s in enumerate(sites)])
    return pcc,occ


def solve_feedback(a0, m1, context, *, tolerance=1e-6, work_limit=60.0):
    started=time.perf_counter(); frozen_route=route_sha(m1.slots)
    p0,_=pcc_from_jobs(a0,context)
    fixed=controls_from_trajectory(context.coefficients,p0,m1.slots)
    initial=evaluate_grid(context.coefficients,fixed,context.nodes)
    if initial['status']!='PASS':raise ValueError('A1_REQUIRES_FEASIBLE_M1')
    model=gp.Model('V40A_AIDC_FEEDBACK');model.Params.OutputFlag=0
    model.Params.Threads=4;model.Params.Seed=20260905;model.Params.MIPGap=0;model.Params.MIPGapAbs=0
    model.Params.FeasibilityTol=1e-8;model.Params.IntFeasTol=1e-9;model.Params.OptimalityTol=1e-8
    model.Params.WorkLimit=work_limit;model.Params.SoftMemLimit=8;model.Params.NodefileStart=1
    sites=tuple(context.capacity.aidc_ids);load=defaultdict(gp.LinExpr)
    variables={};options={};deviation=gp.LinExpr();tie=gp.LinExpr()
    try:
        for i,row in enumerate(a0):
            options[i]=authorized_options(row,context.capacity)
            if (row['AIDC_site'],int(row['start_slot'])) not in options[i]:raise ValueError('A0_OUTSIDE_AUTHORIZED_DOMAIN:'+row['job_uid'])
            vs=[]
            for k,(site,start) in enumerate(options[i]):
                v=model.addVar(vtype=GRB.BINARY,name=f'job[{i},{k}]');variables[i,k]=v;vs.append(v)
                v.Start=float((site,start)==(row['AIDC_site'],row['start_slot']))
                end=start+int(row['safe_duration_slots'])
                for t in range(max(BEGIN,start),min(H,end)):
                    load[t-BEGIN,site]+=int(row['requested_GPU'])*v
                candidate={**row,'AIDC_site':site,'start_slot':start,'end_slot':end}
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
        model.setObjective(rho,GRB.MINIMIZE);model.optimize();stages=[]
        def record(label):
            stages.append({'objective':label,'status':int(model.Status),'incumbent':float(model.ObjVal) if model.SolCount else None,
                           'bound':float(model.ObjBound) if model.IsMIP and model.SolCount else None,
                           'solver_runtime_seconds':float(model.Runtime),'work':float(model.Work),'global_optimality_certified':model.Status==GRB.OPTIMAL})
        record('rho_max')
        if not model.SolCount:return {'status':'NO_INCUMBENT','jobs':deepcopy(a0),'solver':stages,'wallclock_seconds':time.perf_counter()-started}
        # Save incumbent before another solve; limit termination must never discard it.
        chosen={i:next(k for k in range(len(options[i])) if variables[i,k].X>.5) for i in options}
        accepted_primary=float(rho.X)
        model.addConstr(rho<=min(initial['rho_max']+tolerance,accepted_primary+tolerance),name='PRIMARY_NONDEGRADATION')
        model.setObjective(deviation,GRB.MINIMIZE);model.optimize();record('complete_interval_site_symmetric_GPU_slots')
        if model.SolCount:
            chosen={i:next(k for k in range(len(options[i])) if variables[i,k].X>.5) for i in options}
            if model.Status==GRB.OPTIMAL:
                model.addConstr(deviation<=round(deviation.getValue()),name='SECONDARY_EXACT_CAP')
                model.setObjective(tie,GRB.MINIMIZE);model.optimize();record('deterministic_tie')
                if model.SolCount:chosen={i:next(k for k in range(len(options[i])) if variables[i,k].X>.5) for i in options}
        jobs=deepcopy(a0)
        for i,row in enumerate(jobs):
            site,start=options[i][chosen[i]];row.update(AIDC_site=site,start_slot=start,end_slot=start+row['safe_duration_slots'])
            if site!='UNASSIGNED' and row['state_at_issue']!='RUNNING':
                row['Rack_label']=sorted(p.rack_pool_id for p in context.capacity.eligible_racks(site,row['requested_GPU']))[0]
        audit=terminal_audit(a0,jobs);pcc,_=pcc_from_jobs(jobs,context)
        result=evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,pcc,m1.slots),context.nodes)
        if route_sha(m1.slots)!=frozen_route:raise ValueError('A1_MUTATED_MESS')
        return {'status':'PASS' if audit['status']=='PASS' and result['status']=='PASS' else 'FAIL','jobs':jobs,'grid':result,
                'terminal_audit':audit,'solver':stages,'Gurobi_optimize_calls':len(stages),'grid_rows':grid_rows,
                'M1_fixed_controls_SHA':digest(fixed[:,12:]),'M1_route_SHA':frozen_route,
                'running_migrations_added':0,'wallclock_seconds':time.perf_counter()-started}
    finally:model.dispose()
