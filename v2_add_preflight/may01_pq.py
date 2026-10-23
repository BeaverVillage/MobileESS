"""Finite May01 schedules on frozen candidates, with independent TIME/Fresh."""
import copy,csv,types
import numpy as np
from .may01_common import *
from .may01_voltage import engine

def validator(rows):
    from .prestart_native import inputs
    from v42_native.mess import validate
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    sites,initial,routes,battery,receipt=inputs(read(day['files']['native']['path']),INITIAL)
    by={(r['vehicle'],int(r['slot'])):r for r in rows};values={};arcs={}
    for u,s0 in initial.items():
        arcs[u]=[sites.index(s0)*96+t for t in range(96)]
        for t in range(97):values[f'SOC[{u},{t}]']=float(by[u,min(t,95)]['SOC_start' if t<96 else 'SOC_end'])
        for s in sites:
            for t in range(96):
                r=by[u,t];p=float(r['P_demand_kw']) if s==s0 else 0.;q=float(r['Q_demand_kvar']) if s==s0 else 0.
                values[f'Pch[{u},{s},{t}]']=max(p,0);values[f'Pdis[{u},{s},{t}]']=max(-p,0);values[f'Q[{u},{s},{t}]']=-q
    r=validate(dict(values=values,chosen_arcs=arcs,initial_sites=initial,mode='MILP'),sites,routes,battery,96)
    assert r['PASS'];return r

def run():
    init();import psutil;psutil.Process().cpu_affinity([13])
    assert (OUT/'MAY01_HARDWARE_SELECTION.json').exists()
    from . import full_days
    from .may01_witness import pilots
    q50=pilots();ponly=[dict(r,Q_demand_kvar=0.) for r in q50]
    move=list(csv.DictReader((OUT/'FINITE_TWO_MOVE_UNIT_TRAJECTORY.csv').open(encoding='utf-8')))
    # H4 is the most extensive preregistered diagnostic, never a selected
    # Primary. It is tested despite a failed B0 gate to expose PQ interaction.
    configurations=['H0','H4']
    put('MESS_PQ_TIME_PREREGISTRATION.json',dict(day='2025-05-01',hardware=configurations,
        schedules=['ZERO','TWO_PEAK_P_ONLY','TWO_PEAK_Q50','TWO_MOVE_REBOUND_Q_BIDIRECTIONAL'],
        no_manual_slot_voltage_repairs=True,hardware_policy_arm_independent=True,
        source_Q_only_safety_policy_added=False,scientific_primary_selected=False))
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    with np.load(PRIOR/'daily_r0/2025-05-01/INPUTS.npz') as z:a={k:z[k] for k in z.files}
    reports=[]
    for h in configurations:
        for name,rows in [('ZERO',[]),('TWO_PEAK_P_ONLY',ponly),('TWO_PEAK_Q50',q50),('TWO_MOVE_REBOUND_Q_BIDIRECTIONAL',move)]:
            if name=='TWO_MOVE_REBOUND_Q_BIDIRECTIONAL':v=read(OUT/'FINITE_TWO_MOVE_SOURCE_VALIDATOR.json')['validator']
            elif rows:v=validator(rows)
            else:v=dict(PASS=True,initial_terminal_SOC=760,all_power_zero=True)
            loads={}
            for r in rows:
                t=int(r['slot']);u=r['vehicle'];s=r.get('site',INITIAL[u])
                if s=='TRANSIT':continue
                key=t,s;p,q=loads.get(key,(0.,0.));loads[key]=(p+float(r['P_demand_kw']),q+float(r['Q_demand_kvar']))
            folder=RUN/'pq'/h/name;folder.mkdir(parents=True,exist_ok=True)
            def selected(tag,role):
                e=engine('PQ_'+h+'_'+name+'_'+tag,role,h);apply=e.apply
                def scheduled(role,t,beta,mess=None,aidc_delta=None):
                    load={s:pq for (k,s),pq in loads.items() if k==t-24} if t>=24 else {}
                    return apply(role,t,beta,load,aidc_delta)
                e.apply=scheduled;return e
            fn=types.FunctionType(full_days.run.__code__,dict(full_days.run.__globals__,DAYROOT=folder,
                engine=selected,table=lambda n,r:table(h+'_'+name+'_'+n,r)),argdefs=full_days.run.__defaults__)
            fn.__kwdefaults__=full_days.run.__kwdefaults__
            if h=='H0' and name=='ZERO':
                actual=read(PRIOR/'daily_r0/2025-05-01_ACTUAL/RECEIPT.json')
                fresh=read(PRIOR/'daily_r0/2025-05-01_ACTUAL_FRESH/RECEIPT.json')
            elif h=='H0' and name=='TWO_PEAK_Q50':
                actual=read(PRIOR/'MESS_CURRENT24/2025-05-01_ACTUAL/RECEIPT.json')
                fresh=read(PRIOR/'MESS_CURRENT24/2025-05-01_ACTUAL_FRESH/RECEIPT.json')
            elif name=='ZERO':
                actual=read(RUN/'hardware'/h/'2025-05-01_ACTUAL/RECEIPT.json')
                fresh=fn(day,'ACTUAL',a,fresh=True)
            else:actual=fn(day,'ACTUAL',a);fresh=fn(day,'ACTUAL',a,fresh=True)
            with np.load(actual['files']['AC.npz']['path']) as aa,np.load(fresh['files']['AC.npz']['path']) as ff:
                errors={k:float(np.max(abs(aa[k]-ff[k]))) if aa[k].shape==ff[k].shape else None for k in aa.files}
                eq=all(e is not None and e<=1e-9 for e in errors.values())
            reports.append(dict(hardware=h,schedule=name,source_vehicle_validator=v,actual=actual,fresh=fresh,
                independent_Fresh_PASS=eq,Fresh_array_errors=errors,full_TIME_PASS=actual['full_TIME_PASS'] and fresh['full_TIME_PASS'] and eq,
                accepted_as_M1_M2_or_B3_optimizer_result=False))
            put('MAY01_MESS_PQ_TIME_SECURITY.json',dict(PASS=all(x['full_TIME_PASS'] for x in reports),cases=reports,
                all_requested_daily_diagnostics_complete=len(reports)==8,primary_selected=False,
                instantaneous_PQ_results=record(OUT/'ALL24_PORT_INSTANTANEOUS_PQ_SECURITY.csv'),Native_calls=0))
    print('MAY01 PQ COMPLETE',len(reports),flush=True)

if __name__=='__main__':run()
