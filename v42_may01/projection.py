"""Exact-safe infeasibility certificate before complete-option expansion.

For TS=0, aggregate STAY occupancy B[t] is invariant to pre-start placement.
Only a migrated job can be absent from that interval. Relax its whole original
service to zero, even before its checkpoint, omit the replacement/tail service,
and allow fractional migration choices. This is a SUPERSET of every legal
complete-option schedule, never an operating schedule or service relaxation
accepted for execution. If even this superset is infeasible, the full A1 is.

Each migration consumes >=1 integral transfer slot before H=120, at most one
transfer active per slot. Hence sum(migrated)<=120 is valid (deliberately loose).
"""
from time import perf_counter
from pathlib import Path
import json,math
import tempfile,shutil
import gurobipy as gp
from gurobipy import GRB
from v42_native.contracts import require,digest
from v42_native.solver import size,assert_milp
from v42_native.supervision import atomic


def write_solver_file(model, path):
    """Gurobi's Windows file API cannot open a resolved Korean OneDrive path.

    Python copies the unchanged diagnostic bytes to the evidence directory.
    This adapter does not touch the model or solver settings.
    """
    path=Path(path)
    with tempfile.TemporaryDirectory(prefix='v42_gurobi_') as directory:
        temporary=Path(directory)/path.name
        require(str(temporary).isascii(),'GUROBI_DIAGNOSTIC_TEMP_PATH_MUST_BE_ASCII')
        model.write(str(temporary))
        shutil.copyfile(temporary,path)


def known_planning_gate(bundle):
    require(bundle['day']=='2025-05-01' and bundle['network']=='IEEE123','PREREGISTERED_DAY_NETWORK')
    require(not bundle['unknown_arrival_actions'],'UNKNOWN_ACTIONS_DISABLED')
    require(not bundle['unresolved_transitive_physical_inputs'],'PHYSICAL_SOURCE_BUNDLE')
    # Unknown-runtime promotion and Actual response-kernel freeze are NOT
    # requirements of this known-population native computational experiment.
    require(all(r['exact_service_seconds']>0 for r in bundle['known_population'] if r['planning_eligible']),'KNOWN_SERVICE_AUTHORITY')
    return True


def capacity_lower_bounds(jobs,q50,total_capacity,transfer_slots=120,max_active=1,begin=24):
    require(all(r['can_timeshift'] is False for r in jobs),'PROJECTION_REQUIRES_ZERO_TEMPORAL_DOMAIN')
    require(transfer_slots>0 and type(max_active) is int and max_active>=1,'WAN_TRANSFER_BOUND')
    bound=transfer_slots*max_active;rows=[]
    for t in range(begin,begin+len(q50)*4):
        active=[r for r in jobs if r['reference_start_if_authorized']<=t<r['reference_end']]
        total=sum(r['GPU_gang'] for r in active)
        removable=sum(sorted((r['GPU_gang'] for r in active),reverse=True)[:bound])
        low=total-removable;nominal=float(q50[(t-begin)//4])
        rows.append(dict(slot_issue_origin=t,slot_Dday=t-begin,active_known_jobs=len(active),known_reference_GPU=total,
            deliberately_overgenerous_migration_removal_GPU=removable,known_GPU_lower_bound=low,
            C0_Q50_equivalent_GPU=nominal,nominal_support_hours=1,capacity_GPU=total_capacity,
            necessary_total_GPU_lower_bound=low+nominal,excess_GPU=max(0.,low+nominal-total_capacity),
            max_total_migrations_loose_upper_bound=bound,physical_schedule=False))
    return rows


def solve(jobs,q50,capacity,output,seconds=600.,progress=None):
    require(0<seconds<=600,'CANARY_WALL_CAP');start=perf_counter();output=Path(output)
    rows=capacity_lower_bounds(jobs,q50,capacity)
    m=gp.Model('MAY01_A1_NATIVE_RESOURCE_SUPERSET');m.Params.OutputFlag=0
    events=dict(first_incumbent_seconds=None,root_relaxation_seconds=None,presolve_removed_rows=None,presolve_removed_columns=None)
    trace=[]
    try:
        # Fractional variables and omission of all transfer/site/grid/terminal
        # restrictions enlarge the full model. Their feasibility is NOT a pass.
        z={r['job_uid']:m.addVar(lb=0,ub=1,name='relaxed_migration['+r['job_uid']+']') for r in jobs}
        m.addConstr(gp.quicksum(z.values())<=120,name='NECESSARY_ONE_ACTIVE_TRANSFER_PER_SLOT')
        for row in rows:
            t=row['slot_issue_origin'];active=[r for r in jobs if r['reference_start_if_authorized']<=t<r['reference_end']]
            m.addConstr(gp.quicksum(r['GPU_gang']*(1-z[r['job_uid']]) for r in active)+row['C0_Q50_equivalent_GPU']<=capacity,
                name=f'KNOWN_PLUS_C0_NOMINAL_CAPACITY[{t}]')
        m.setObjective(0.);m.Params.TimeLimit=max(.001,seconds-(perf_counter()-start));m.Params.MIPGap=.001
        m.Params.Threads=1;m.Params.Seed=20260929;m.Params.InfUnbdInfo=1;m.Params.DualReductions=0
        m.update();model_size=assert_milp(m);write_solver_file(m,output/'NATIVE_RESOURCE_PROJECTION.lp')
        atomic(output/'model_build.json',dict(scope='NECESSARY_RELAXATION_NOT_FULL_A1_MODEL',model_size=model_size,
            build_seconds=perf_counter()-start,known_jobs=len(jobs),MIPGap=.001,TimeLimit=m.Params.TimeLimit))
        def callback(model,where):
            if where==GRB.Callback.PRESOLVE:
                events['presolve_removed_rows']=int(model.cbGet(GRB.Callback.PRE_ROWDEL))
                events['presolve_removed_columns']=int(model.cbGet(GRB.Callback.PRE_COLDEL))
            if perf_counter()-start>=seconds:model.terminate()
        m.optimize(callback)
        result=dict(status='INFEASIBLE' if m.Status==GRB.INFEASIBLE else 'RELAXATION_FEASIBLE_REQUIRES_FULL_MODEL' if m.SolCount else 'ERROR',
            solver_status=m.Status,scope='NATIVE_A1_NECESSARY_RESOURCE_PROJECTION_NOT_FULL_MILP_TIMING',
            full_A1_infeasible_proven=m.Status==GRB.INFEASIBLE and any(r['excess_GPU']>1e-8 for r in rows),
            certificate_method='CONTINUOUS_SUPERSET_PLUS_INDEPENDENT_TOP_120_GANG_LOWER_BOUND',
            solver_runtime_seconds=m.Runtime,total_worker_seconds=perf_counter()-start,model_size=model_size,
            full_A1_model_size=None,full_A1_MIP_gap=None,objective=None,best_bound=None,nodes=m.NodeCount,
            MIPGap_parameter=m.Params.MIPGap,TimeLimit_parameter=m.Params.TimeLimit,incumbent_available=False,
            scientific_schedule_accepted=False,service_was_shortened_in_accepted_schedule=False,
            number_violated_necessary_rows=sum(r['excess_GPU']>1e-8 for r in rows),worst_row=max(rows,key=lambda r:r['excess_GPU']),
            gap_at_60s=None,gap_at_180s=None,gap_at_300s=None,**events)
        # IIS is diagnostic only, within the same budget. Analytic certificate
        # needs no IIS and remains independently verifiable if time expires.
        if result['full_A1_infeasible_proven'] and seconds-(perf_counter()-start)>1:
            m.Params.TimeLimit=seconds-(perf_counter()-start);m.computeIIS()
            result['IIS_constraints']=[c.ConstrName for c in m.getConstrs() if c.IISConstr]
            write_solver_file(m,output/'NATIVE_RESOURCE_PROJECTION.ilp')
        atomic(output/'projection_result.json',result)
        atomic(output/'capacity_lower_bounds.json',rows)
        return result
    finally:m.dispose()
