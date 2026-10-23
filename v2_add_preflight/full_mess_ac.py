"""Revalidate the preserved finite eight-car pilot on current24-port hardware."""
import csv,types
import numpy as np
from .full_common import *

def run():
    init();resources();import psutil;psutil.Process().cpu_affinity([13])
    name='PRESTART_SPLIT_50_50_Q50'
    path=DOC/'prestart/TWO_PEAK_UNIT_TRAJECTORIES.csv'
    rows=[r for r in csv.DictReader(path.open(encoding='utf-8')) if r['schedule']==name];assert len(rows)==8*96
    by={(r['vehicle'],int(r['slot'])):r for r in rows}
    from .prestart_native import inputs
    from v42_native.mess import validate
    sites,initial,routes,battery,receipt=inputs(read(day_input('2025-05-01')['files']['native']['path']),INITIAL)
    values={};chosen={}
    for u,origin in initial.items():
        chosen[u]=[sites.index(origin)*96+t for t in range(96)]
        for t in range(97):values[f'SOC[{u},{t}]']=float(by[u,min(t,95)]['SOC_start' if t<96 else 'SOC_end'])
        for s in sites:
            for t in range(96):
                p=float(by[u,t]['P_demand_kw']) if s==origin else 0.;q=float(by[u,t]['Q_demand_kvar']) if s==origin else 0.
                values[f'Pch[{u},{s},{t}]']=max(p,0);values[f'Pdis[{u},{s},{t}]']=max(-p,0);values[f'Q[{u},{s},{t}]']=-q
    vehicle=validate(dict(values=values,chosen_arcs=chosen,initial_sites=INITIAL,mode='MILP'),sites,routes,battery,96)
    assert vehicle['PASS'] and all(abs(float(r['Q_demand_kvar']))<=250 for r in rows)
    from .full_physical import engine
    def current(tag,role):
        e=engine('MESS_CURRENT24_'+tag,role);apply=e.apply
        def scheduled(role,t,beta,mess=None,aidc_delta=None):
            load={s:(float(by[u,t-24]['P_demand_kw']),float(by[u,t-24]['Q_demand_kvar'])) for u,s in INITIAL.items()} if t>=24 else {}
            return apply(role,t,beta,load,aidc_delta)
        e.apply=scheduled;return e
    from . import full_days
    folder=RUN/'MESS_CURRENT24';folder.mkdir(exist_ok=True)
    fn=types.FunctionType(full_days.run.__code__,dict(full_days.run.__globals__,DAYROOT=folder,engine=current,
        table=lambda n,r:table('MESS_CURRENT24_'+n,r)),argdefs=full_days.run.__defaults__);fn.__kwdefaults__=full_days.run.__kwdefaults__
    a=np.load(RUN/'daily_r0/2025-05-01/INPUTS.npz');a={k:a[k] for k in a.files};day=day_input('2025-05-01')
    actual=fn(day,'ACTUAL',a);fresh=fn(day,'ACTUAL',a,fresh=True)
    aa=np.load(folder/'2025-05-01_ACTUAL/AC.npz');ff=np.load(folder/'2025-05-01_ACTUAL_FRESH/AC.npz')
    error=max(float(np.max(abs(aa[k]-ff[k]))) for k in aa.files)
    b0=read(RUN/'daily_r0/2025-05-01_ACTUAL/RECEIPT.json')
    put('MESS8_CURRENT24_FINITE_AC.json',dict(status='PRESERVED_FINITE_STAY_PILOT_NOT_M1_OR_B3_OPTIMIZATION',
        original_trajectory=record(path),schedule=name,independent_original_vehicle_validator=vehicle,Q250_PASS=True,
        simultaneous8_ports_PASS=actual['evaluated_TIME_PASS'],actual=actual,fresh=fresh,Fresh_array_error=error,
        global_rho_reduction_percentage_points=(b0['rho_global']-actual['rho_global'])*100,
        same_B0_jobs_GPU_PV_BG_and_ports=True,nominal24MW_or24MWh_assumed=False,STAY_MOVE_model_domain_restricted=False,
        full120_PASS=actual['full_TIME_PASS'] and fresh['full_TIME_PASS'],Native_calls=0))
    print('CURRENT24 MESS GAIN',100*(b0['rho_global']-actual['rho_global']),flush=True)

if __name__=='__main__':run()
