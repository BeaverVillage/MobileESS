"""Arithmetic route/PQ/SOC witnesses, never a Native optimization result."""
import csv, math
import numpy as np
from .may01_common import *

def route_witness():
    from .prestart_native import inputs
    from v42_native.mess import validate
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    sites,initial,routes,battery,receipt=inputs(read(day['files']['native']['path']),INITIAL)
    with np.load(PACK/'MOBILITY_DOMAIN.npz') as z:d={k:z[k] for k in z.files}
    names={str(n):i for i,n in enumerate(d['names'])};u='MESS01';origin=initial[u]
    chosen_route=None
    # Preserve all source arcs; choose one finite two-MOVE witness only.
    for k,r in enumerate(routes):
        if r.source!=origin or not r.destination.startswith('IDC') or not 8<=r.depart<=12 or r.connect>30:continue
        if f'arc[{u},{len(sites)*96+k}]' not in names:continue
        back=next(((j,s) for j,s in enumerate(routes) if s.source==r.destination and s.destination==origin and
            r.connect+3<=s.depart<=r.connect+8 and s.connect<60 and
            f'arc[{u},{len(sites)*96+j}]' in names),None)
        if back and r.energy_kwh+back[1].energy_kwh<200:
            chosen_route=(k,r,back[0],back[1]);break
    assert chosen_route
    k,a,j,b=chosen_route
    selected={x:[sites.index(s)*96+t for t in range(96)] for x,s in initial.items()}
    selected[u]=([sites.index(origin)*96+t for t in range(a.depart)]+[len(sites)*96+k]+
        [sites.index(a.destination)*96+t for t in range(a.connect,b.depart)]+[len(sites)*96+j]+
        [sites.index(origin)*96+t for t in range(b.connect,96)])
    arcdata=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[(r.source,r.depart,r.destination,r.connect,r) for r in routes]
    values={};trajectory=[];travel=a.energy_kwh+b.energy_kwh
    # A small discharge followed by exact recharge demonstrates rebound; Q of
    # both signs is zero energy in this source battery contract.
    discharge=10.;pulse=b.connect+2;charge_begin=b.connect+5;duration=8
    charge=(travel+battery.dt_hours*discharge/battery.eta_discharge)/(duration*battery.dt_hours*battery.eta_charge)
    assert charge<300 and charge_begin+duration<96
    for unit,s0 in initial.items():
        selected_set=set(selected[unit]);E=battery.initial;values[f'SOC[{unit},0]']=E
        for t in range(96):
            connected=next((s for s in sites if sites.index(s)*96+t in selected_set),None)
            p=charge if unit==u and charge_begin<=t<charge_begin+duration else (-discharge if unit==u and t==pulse else 0.)
            q=(-30. if t%2 else 30.) if unit==u and connected and a.connect<=t<b.depart else 0.
            for s in sites:
                values[f'Pch[{unit},{s},{t}]']=max(p,0) if s==connected else 0.
                values[f'Pdis[{unit},{s},{t}]']=max(-p,0) if s==connected else 0.
                values[f'Q[{unit},{s},{t}]']=-q if s==connected else 0.
            travel_t=sum(arcdata[h][4].energy_kwh for h in selected[unit] if arcdata[h][1]==t and arcdata[h][4] is not None)
            before=E;E+=battery.dt_hours*(battery.eta_charge*max(p,0)-max(-p,0)/battery.eta_discharge)-travel_t
            values[f'SOC[{unit},{t+1}]']=E
            trajectory.append(dict(vehicle=unit,slot=t,site=connected or 'TRANSIT',P_demand_kw=p,Q_demand_kvar=q,
                SOC_start=before,SOC_end=E,travel_kwh=travel_t))
    result=dict(values=values,chosen_arcs=selected,initial_sites=initial,mode='MILP')
    check=validate(result,sites,routes,battery,96);assert check['PASS']
    point=np.zeros(len(d['names']))
    for name,i in names.items():
        if name in values:point[i]=values[name]
        elif name.startswith('arc['):
            vehicle,index=name[4:-1].split(',');point[i]=int(int(index) in set(selected[vehicle]))
        elif name.startswith('charge_mode['):
            vehicle,t=name[len('charge_mode['):-1].split(',');t=int(t)
            point[i]=int(any(values[f'Pch[{vehicle},{s},{t}]']>0 for s in sites))
    point[names['rho_max']]=1.
    injection=np.zeros((96,48))
    for t in range(96):
        for h,s in enumerate(sites):
            injection[t,h]=sum(values[f'Pdis[{u},{s},{t}]']-values[f'Pch[{u},{s},{t}]'] for u in initial)
            injection[t,24+h]=sum(values[f'Q[{u},{s},{t}]'] for u in initial)
    table('FINITE_TWO_MOVE_UNIT_TRAJECTORY.csv',trajectory)
    np.save(RUN/'MOVE_COMPACT_POINT.npy',np.r_[point,injection.ravel()])
    put('FINITE_TWO_MOVE_SOURCE_VALIDATOR.json',dict(validator=check,vehicle=u,roundtrip=dict(outward=a.__dict__,returning=b.__dict__),
        travel_energy_kwh=travel,charging_kw=charge,terminal_SOC=battery.terminal,source_routes_changed=False,
        witness_not_optimizer_result=True,point=record(RUN/'MOVE_COMPACT_POINT.npy'),receipt=receipt))
    return np.r_[point,injection.ravel()]

def pilots():
    path=DOC/'prestart/TWO_PEAK_UNIT_TRAJECTORIES.csv'
    rows=[r for r in csv.DictReader(path.open(encoding='utf-8')) if r['schedule']=='PRESTART_SPLIT_50_50_Q50']
    assert len(rows)==8*96
    return rows

if __name__=='__main__':init();route_witness()
