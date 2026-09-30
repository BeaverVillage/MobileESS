"""Valid lower bounds; independent slot minima alone never certify a PASS."""
import numpy as np
import gurobipy as gp
from time import perf_counter
from .common import *
from .service import bind_service,slot_minima
from v42_may01.projection import write_solver_file

def known_bounds(jobs,ts,*,begin=24,end=120,max_active=1):
    rows=[]
    for t in range(begin,end):
        live=[j for j in jobs if j['reference_start_if_authorized']<=t<j['reference_end']]
        # Intersection over all authorized delayed starts. Omitting jobs that
        # can avoid this slot is a lower bound, not deleted service in a plan.
        mandatory=[j for j in live if j['reference_start_if_authorized']+ts[j['job_uid']]['TS_slots']<=t]
        count=max_active*(end-t-1)
        removal=sum(sorted((j['GPU_gang'] for j in mandatory),reverse=True)[:count])
        original=sum(j['GPU_gang'] for j in live);forced=sum(j['GPU_gang'] for j in mandatory)
        rows.append(dict(issue_slot=t,Dday_slot=t-begin,known_reference_GPU=original,TS_relief_available_GPU=original-forced,
                         maximum_suspended_jobs=count,generous_suspension_GPU=removal,known_GPU_lower_bound=forced-removal))
    return rows

def main():
    require(not (OUT/'MAY01_TS_CC4_RESOURCE_FEASIBILITY.json').exists(),'RESOURCE_ALREADY_SEALED')
    b=read(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json');jobs=[j for j in b['known_population'] if j['planning_eligible']]
    ts=pd.read_csv(OUT/'TS_HIERARCHICAL_BACKOFF_LEDGER.csv',dtype={'job_id':str}).set_index('job_id').to_dict('index')
    require(sum(b['capacities'].values())==780 and b['runtime_reserve_gamma']==2.423057443558147,'FROZEN_CAPACITY_GAMMA')
    e=pd.read_csv(OUT/'CC4_SERVICE_TIMING_ENVELOPE.csv');k=pd.read_csv(OLD/'CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy()
    q=b['C0_Q50'];arrivals=np.zeros(93);arrivals[::4]=q
    minimal=np.convolve(arrivals,slot_minima(e.Q10,e.Q90))*4
    rows=known_bounds(jobs,ts,max_active=b['WAN']['maximum_active_transfers'])
    for r in rows:
        r.update(minimum_anonymous_CC4_GPU=float(minimal[r['Dday_slot']]),capacity_GPU=780)
        r['necessary_GPU_lower_bound']=r['known_GPU_lower_bound']+r['minimum_anonymous_CC4_GPU']
        r['capacity_excess_GPU']=max(0.,r['necessary_GPU_lower_bound']-780)
    worst=max(rows,key=lambda r:r['necessary_GPU_lower_bound']);point_fail=worst['capacity_excess_GPU']>1e-8
    LOCAL.mkdir(exist_ok=True);start=perf_counter();m=gp.Model('V42_TS_CC4_NECESSARY');m.Params.OutputFlag=0
    try:
        service=bind_service(m,q,k,e.Q10,e.Q90)
        for r in rows:m.addConstr(r['known_GPU_lower_bound']+service['gpu'][r['Dday_slot']]<=780,name=f'capacity[{r["Dday_slot"]}]')
        m.setObjective(0.);m.Params.TimeLimit=600;m.Params.MIPGap=.001;m.Params.Threads=1;m.Params.DualReductions=0
        m.update();write_solver_file(m,LOCAL/'NECESSARY.lp');build=perf_counter()-start;m.optimize()
        passed=not point_fail and m.Status==gp.GRB.OPTIMAL
        if passed:
            csv('NECESSARY_ANONYMOUS_WITNESS.csv',[dict(hour=h,slot=t,GPUh=v.X) for (h,t),v in service['x'].items()])
            dump('NECESSARY_CARRYOUT_WITNESS.json',{h:v.X for h,v in service['carryout'].items()})
        result=dict(PASS=passed,status='NECESSARY_CONDITION_PASS_NOT_FULL_FEASIBILITY' if passed else 'INFEASIBLE_PROVEN_BEFORE_A1' if m.Status==gp.GRB.INFEASIBLE or point_fail else 'UNRESOLVED_STOP',
            worst_slot=worst,pointwise_bound_violated=point_fail,joint_capacity_solver_status=m.Status,
            full_A1_authorized_after_this_PASS=passed,accepted_native_plan=False,
            reserve_achieved_relaxed_to_zero=True,reserve_scope='DIAGNOSTIC_LOWER_BOUND_ONLY; full A1 must bind frozen real Planning reserve',
            known_bound='All TS starts; mandatory interval minus PR96 last-transfer injection top-gang bound retaining resumed service',
            anonymous_minimum='Exact individual-slot minimum with full cumulative envelope; simultaneous feasibility separately checked by LP',
            relaxation='Known per-slot bounds need not be jointly attainable; PASS only authorizes A1, never an operating schedule',
            binding_authority='TRAIN_Q10_Q90_CDF_AND_LAST_TRANSFER_INJECTION',capacity_GPU=780,gamma90=b['runtime_reserve_gamma'],
            build_seconds=build,solve_seconds=m.Runtime,wall_seconds=perf_counter()-start,binary_count=m.NumBinVars,
            continuous_count=m.NumVars-m.NumIntVars,constraints=m.NumConstrs,source=rec(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),
            legacy_certificate_status='SUPERSEDED_BY_TS_AND_CC4_TEMPORAL_FLEXIBILITY_INTERFACE',
            legacy_certificate=rec(OLD/'MAY01_RESUMED_SERVICE_CERTIFICATE.json'))
        csv('MAY01_TS_CC4_RESOURCE_BOUND.csv',rows);dump('MAY01_TS_CC4_RESOURCE_FEASIBILITY.json',result);print(result)
    finally:m.dispose()

if __name__=='__main__':main()
