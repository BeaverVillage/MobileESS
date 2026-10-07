"""Necessary aggregate resource check under the final workload interface."""
from .common import *
from v42_may01.projection import write_solver_file
import gurobipy as gp
from gurobipy import GRB
from time import perf_counter


def main():
    require(not (OUT/'MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json').exists(),'NO_SILENT_RESOURCE_RECHECK')
    bundle=read(OUT/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json')
    from v42_a_stage_domain_v2.execution import require_action_authorized,tag_model_for_day
    require_action_authorized(bundle,'FEASIBILITY_LP')
    jobs=[r for r in bundle['known_population'] if r['planning_eligible']]
    require(all(r['can_timeshift'] is False for r in jobs),'NECESSARY_CHECK_REQUIRES_ACTUAL_ZERO_TS_DOMAIN')
    require(bundle['C0_binding']=='LIFETIME_GPUH_EXECUTION_LAG_CONVOLUTION','NO_OLD_SAME_HOUR_GPU_BINDING')
    require(bundle['runtime_reserve_gamma']==read(OUT/'RUNTIME_RESERVE_CALIBRATION.json')['gamma_90'],'FROZEN_GAMMA')
    LOCAL.mkdir(exist_ok=True);start=perf_counter();m=gp.Model('V42_FINAL_NECESSARY_RESOURCE');m.Params.OutputFlag=0
    tag_model_for_day(m,bundle)
    try:
        z={j['job_uid']:m.addVar(lb=0,ub=1,name='relaxed_migration['+j['job_uid']+']') for j in jobs}
        m.addConstr(gp.quicksum(z.values())<=120,name='LOOSE_ONE_TRANSFER_PER_SLOT_COUNT')
        nominal=bundle['unknown_nominal_GPU'];rows=[]
        for t in range(24,120):
            active=[j for j in jobs if j['reference_start_if_authorized']<=t<j['reference_end']]
            known=sum(j['GPU_gang'] for j in active);removed=sum(sorted((j['GPU_gang'] for j in active),reverse=True)[:120])
            # Dropping both Planning reserve targets from a necessary check is
            # valid because their explicitly authorized P2 shortfall is soft.
            # It does not drop any nominal known or anonymous service.
            m.addConstr(gp.quicksum(j['GPU_gang']*(1-z[j['job_uid']]) for j in active)+nominal[t-24]<=780,name=f'FINAL_NOMINAL_CAPACITY[{t}]')
            rows.append(dict(slot_Dday=t-24,known_Q50_reference_GPU=known,CC4_lag_nominal_GPU=nominal[t-24],
                top120_removed_GPU=removed,necessary_lower_bound_GPU=known-removed+nominal[t-24],
                CC4_reserve_target_GPU=bundle['CC4_reserve_GPU'][t-24],reserve_shortfall_is_soft=True))
        m.setObjective(gp.quicksum(z.values()),GRB.MINIMIZE)
        m.Params.TimeLimit=600;m.Params.MIPGap=.001;m.Params.Threads=1;m.Params.DualReductions=0
        m.update();write_solver_file(m,LOCAL/'FINAL_NECESSARY_RESOURCE.lp');m.optimize()
        passed=m.Status==GRB.OPTIMAL
        result=dict(status='NECESSARY_CONDITION_PASS_NOT_FULL_FEASIBILITY' if passed else 'INFEASIBLE' if m.Status==GRB.INFEASIBLE else 'FAIL_CLOSED_UNRESOLVED',
            PASS=passed,solver_status=m.Status,solver_seconds=m.Runtime,wall_seconds=perf_counter()-start,
            relaxed_minimum_migrations=float(m.ObjVal) if m.SolCount else None,
            variables=m.NumVars,constraints=m.NumConstrs,MIPGap_parameter=.001,TimeLimit_parameter=600,
            old_certificate='SUPERSEDED_FOR_V42_FINAL_INTERFACE',new_CC4_binding='GPUh convolved through empirical execution lag then /0.25h',
            nominal_runtime=MODEL,Q50_only=True,source=rec(OUT/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),
            TS_jobs=0,Actual_RUNNING_hard=True,unresolved_pre_D00_external=44,
            planning_reserve_in_necessary_condition='Targets tracked separately; achieved reserve can be zero with authorized P2 shortfall. No nominal shortfall.',
            gamma_90=bundle['runtime_reserve_gamma'],physical_operating_schedule=False,
            relaxation='Same authorized migration-count superset as PR93, but NEW nominal durations and execution-lag arrivals; erase full service of each fractionally migrated job, no destinations',
            full_A1_required_after_PASS=True)
        if m.Status==GRB.INFEASIBLE:
            m.computeIIS();result['IIS_constraints']=[c.ConstrName for c in m.getConstrs() if c.IISConstr]
            write_solver_file(m,LOCAL/'FINAL_NECESSARY_RESOURCE.ilp')
        result['evidence']=[rec(p) for p in LOCAL.glob('FINAL_NECESSARY_RESOURCE.*')]
        dump('MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json',result);csv('MAY01_FINAL_RESOURCE_BOUND.csv',rows)
        print(json.dumps(result,indent=2))
    finally:m.dispose()


if __name__=='__main__':main()
