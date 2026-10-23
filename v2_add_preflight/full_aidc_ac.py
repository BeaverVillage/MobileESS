"""Finite strict same-policy Job replay AC; never a B1/B3 optimizer outcome."""
import types
import numpy as np
from .full_common import *

def run():
    init();resources();import psutil;psutil.Process().cpu_affinity([13])
    from . import full_days
    from .full_physical import engine
    day=day_input('2025-05-01');base=np.load(RUN/'daily_r0/2025-05-01/INPUTS.npz')
    power=np.load(RUN/'jobs/SAME_POLICY_POWER.npz');results={}
    for variant in ('BASE','PRESITE'):
        a={k:base[k].copy() for k in base.files}
        a['ACTUAL_AIDC_P_kw']=power['base_P' if variant=='BASE' else 'P']
        a['ACTUAL_AIDC_Q_kvar']=power['base_Q' if variant=='BASE' else 'Q']
        folder=RUN/'aidc_ac'/variant;folder.mkdir(parents=True,exist_ok=True)
        fn=types.FunctionType(full_days.run.__code__,dict(full_days.run.__globals__,DAYROOT=folder,
            engine=lambda tag,role:engine('AIDC_'+variant+'_'+tag,role),table=lambda name,rows:table('AIDC_'+variant+'_'+name,rows)),argdefs=full_days.run.__defaults__)
        fn.__kwdefaults__=full_days.run.__kwdefaults__
        actual=fn(day,'ACTUAL',a);fresh=fn(day,'ACTUAL',a,fresh=True)
        aa=np.load(folder/'2025-05-01_ACTUAL/AC.npz');ff=np.load(folder/'2025-05-01_ACTUAL_FRESH/AC.npz')
        err=max(float(np.max(abs(aa[k]-ff[k]))) for k in aa.files)
        results[variant]=dict(actual=actual,fresh=fresh,Fresh_array_max_error=err,Fresh_PASS=err<1e-9)
    gain=(results['BASE']['actual']['rho_global']-results['PRESITE']['actual']['rho_global'])*100
    put('AIDC_STRICT_SAME_POLICY_AC.json',dict(status='FINITE_CONTROL_DIAGNOSTIC_NOT_B1_OPTIMIZATION',results=results,
        global_rho_reduction_percentage_points=gain,reference='Same original strict B1-controller baseline, not FCFS B0',
        Source_QoS_relaxed=False,original_FULL_planning_reference_and_forced_option_PASS=True,
        dispatch_whole_work_certification=record(OUT/'AIDC_SAME_POLICY_STUDY.json'),
        full120_operationally_certified=all(r['actual']['full_TIME_PASS'] and r['fresh']['full_TIME_PASS'] for r in results.values()),
        campaign_FULL_Job_grid_and_policy_connected=False,GPU_scaling_run=False,Native_calls=0))
    print('AIDC FINITE AC GAIN pp',gain,flush=True)

if __name__=='__main__':run()
