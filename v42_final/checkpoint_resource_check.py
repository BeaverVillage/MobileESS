"""Stronger necessary resource screen: immutable prefix and WAN release dates.

Still a superset: discard all post-first-checkpoint original service, permit
fractional migration, no destination/restart service, and just one WAN slot/job.
"""
from .common import *
from v42_job_capability import Job,checkpoint_records
from v42_may01.projection import write_solver_file
from time import perf_counter
import gurobipy as gp
from gurobipy import GRB


def main():
    prior=read(OUT/'MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json')
    require(prior['status']=='NECESSARY_CONDITION_PASS_NOT_FULL_FEASIBILITY','INITIAL_RELAXATION_REQUIRED')
    require(not (OUT/'MAY01_CHECKPOINT_RESOURCE_CERTIFICATE.json').exists(),'NO_SILENT_RECHECK')
    # Preserve the earlier, looser test verbatim as a stage-specific receipt.
    (OUT/'MAY01_RESOURCE_LOOSE_RELAXATION.json').write_bytes((OUT/'MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json').read_bytes())
    b=read(OUT/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json');jobs=[j for j in b['known_population'] if j['planning_eligible'] and j['service_slots']>0]
    require(all(j['can_timeshift'] is False for j in jobs),'ZERO_TS_DOMAIN')
    first={};trace=[]
    for r in jobs:
        j=Job(r['job_uid'],r['state'],0,0,r['reference_start_if_authorized'],r['planning_site'],r['service_slots'],r['GPU_gang'],
            elapsed_seconds=r['elapsed_seconds'],duration_authority=MODEL)
        points=checkpoint_records(j,j.reference_start,min(j.reference_start+j.service_slots,120))
        cp=points[0][0] if points else 120
        # One slot WAN transfer plus one restart slot must finish before 120.
        # cp<=117 is necessary. All site/rack/path restrictions are relaxed.
        first[j.uid]=cp
        trace.append(dict(job_id=j.uid,first_checkpoint_slot=cp if points else None,relaxed_migration_candidate=cp<=117,
            nominal_start=j.reference_start,nominal_end=j.reference_start+j.service_slots,GPU=j.gpu))
    start=perf_counter();m=gp.Model('V42_FINAL_CHECKPOINT_WAN_RESOURCE_SUPERSET');m.Params.OutputFlag=0
    try:
        z={j['job_uid']:m.addVar(lb=0,ub=1,name='relaxed_migration['+j['job_uid']+']') for j in jobs if first[j['job_uid']]<=117}
        # Hall suffix inequalities for unit-length transfers on one network-wide
        # machine, each released at first checkpoint and due by transfer_end118.
        for u in sorted(set(first[j] for j in z)):
            m.addConstr(gp.quicksum(v for j,v in z.items() if first[j]>=u)<=118-u,name=f'WAN_RELEASE_SUFFIX[{u}]')
        for t in range(24,120):
            live=[j for j in jobs if j['reference_start_if_authorized']<=t<j['reference_end']]
            original=sum(j['GPU_gang'] for j in live)
            removable=gp.quicksum(j['GPU_gang']*z[j['job_uid']] for j in live if j['job_uid'] in z and first[j['job_uid']]<=t)
            m.addConstr(original-removable+b['unknown_nominal_GPU'][t-24]<=780,name=f'FINAL_NOMINAL_CAPACITY[{t}]')
        m.setObjective(gp.quicksum(z.values()));m.Params.TimeLimit=600;m.Params.MIPGap=.001;m.Params.Threads=1;m.Params.DualReductions=0
        m.update();write_solver_file(m,LOCAL/'CHECKPOINT_WAN_NECESSARY.lp');m.optimize()
        result=dict(status='INFEASIBLE' if m.Status==GRB.INFEASIBLE else 'NECESSARY_CONDITION_PASS_NOT_FULL_FEASIBILITY' if m.Status==GRB.OPTIMAL else 'FAIL_CLOSED_UNRESOLVED',
            PASS=m.Status==GRB.OPTIMAL,solver_status=m.Status,solver_seconds=m.Runtime,wall_seconds=perf_counter()-start,
            variables=m.NumVars,constraints=m.NumConstrs,relaxed_minimum_migrations=float(m.ObjVal) if m.SolCount else None,
            MIPGap_parameter=.001,TimeLimit_parameter=600,first_checkpoint_source='Execution-start anchored 1800-second phase with inherited ceil-to-900 control adapter',
            WAN='At most one transfer network-wide; each transfer consumes >=1 slot; one restart slot and restart_end<120',
            suffix_bound='sum z[j] with first_cp[j]>=u <=118-u',
            service_preserved_in_accepted_plan=True,accepted_plan_exists=False,full_A1_run=False,
            mathematical_scope='Fractional superset: no pre-checkpoint deletion, no destination compute, no full transfer duration, no rack/site/electrical constraints',
            source=rec(OUT/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),loose_precheck=rec(OUT/'MAY01_RESOURCE_LOOSE_RELAXATION.json'))
        if m.Status==GRB.INFEASIBLE:
            m.computeIIS();result['IIS_constraints']=[c.ConstrName for c in m.getConstrs() if c.IISConstr]
            write_solver_file(m,LOCAL/'CHECKPOINT_WAN_NECESSARY.ilp')
        result['evidence']=[rec(p) for p in LOCAL.glob('CHECKPOINT_WAN_NECESSARY.*')]
        dump('MAY01_CHECKPOINT_RESOURCE_CERTIFICATE.json',result);csv('MAY01_CHECKPOINT_RELEASE_AUDIT.csv',trace)
        dump('MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json',dict(result,
            old_PR93_certificate='SUPERSEDED_FOR_V42_FINAL_INTERFACE',CC4_direct_GPUh_error_removed=True,
            runtime_Q50_and_lag_profiles_bound=True,runtime_reserve_gamma=b['runtime_reserve_gamma'],
            reserve_targets_soft_in_P2=True,full_A1_authorized_after_this_PASS=result['PASS']))
        print(json.dumps(result,indent=2))
    finally:m.dispose()


if __name__=='__main__':main()
