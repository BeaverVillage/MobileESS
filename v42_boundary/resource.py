import numpy as np
import gurobipy as gp
from time import perf_counter
from .common import *
from v42_temporal.resource import known_bounds
from v42_temporal.service import bind_service,slot_minima
from v42_may01.projection import write_solver_file

def main():
    require(not (OUT/'MAY01_RESOURCE_RECHECK.json').exists(),'RESOURCE_RECHECK_ALREADY_SEALED')
    b=read(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json');jobs=[j for j in b['known_population'] if j['planning_eligible']]
    windows=read(OUT/'KNOWN_TS_SERVICE_BOUNDARY_AUDIT.json')['windows']
    ts={j['job_id']:dict(TS_slots=j['latest_start']-j['reference_start']) for j in windows}
    rows=known_bounds(jobs,ts,max_active=b['WAN']['maximum_active_transfers'])
    e=pd.read_csv(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv');k=pd.read_csv(OLD/'CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy()
    arrivals=np.zeros(93);arrivals[::4]=b['C0_Q50'];low=np.convolve(arrivals,slot_minima(e.Q10,e.Q90))*4
    for r in rows:
        r.update(minimum_anonymous_CC4_GPU=float(low[r['Dday_slot']]),capacity_GPU=780)
        r['necessary_GPU_lower_bound']=r['known_GPU_lower_bound']+r['minimum_anonymous_CC4_GPU']
        r['capacity_excess_GPU']=max(0.,r['necessary_GPU_lower_bound']-780)
    started=perf_counter();m=gp.Model('BOUNDARY_NECESSARY_RESOURCE');m.Params.OutputFlag=0
    try:
        service=bind_service(m,b['C0_Q50'],k,e.Q10,e.Q90)
        for r in rows:m.addConstr(r['known_GPU_lower_bound']+service['gpu'][r['Dday_slot']]<=780,name='capacity')
        m.setObjective(0.);m.Params.TimeLimit=600;m.Params.MIPGap=.001;m.Params.Threads=1;m.update()
        LOCAL.mkdir(exist_ok=True);write_solver_file(m,LOCAL/'RESOURCE_RECHECK.lp');m.optimize()
        passed=m.Status==gp.GRB.OPTIMAL
        result=dict(PASS=passed,full_A1_authorized_after_this_PASS=passed,solver_status=m.Status,solve_seconds=m.Runtime,
            total_seconds=perf_counter()-started,worst=max(rows,key=lambda r:r['necessary_GPU_lower_bound']),
            reserve_achieved_relaxed_to_zero=True,diagnostic_only=True,accepted_plan=False,
            CC4_envelope=rec(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv'),capacity_GPU=780,gamma90=b['runtime_reserve_gamma'],
            PR97_PASS_preserved=rec(PR97/'MAY01_TS_CC4_RESOURCE_FEASIBILITY.json'))
        dump('MAY01_RESOURCE_RECHECK.json',result);csv('MAY01_RESOURCE_BOUND.csv',rows);print(result)
    finally:m.dispose()

if __name__=='__main__':main()
