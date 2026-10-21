"""Separately preregistered slow-charge diagnostics: same energy/hardware/SOC."""
from pathlib import Path
import sys
import numpy as np
from . import correction as c
from .audit import DOC,read,sha
from .correction_time100 import install

SCHEDULES=[dict(name='CHARGE24_LATE4',begin=[72]*8,duration=8,Q=0),
    dict(name='CHARGE24_LONG',begin=[68]*8,duration=16,Q=0),
    dict(name='CHARGE24_STAGGERED',begin=list(range(68,76)),duration=8,Q=0),
    dict(name='CHARGE24_LONG_Q100',begin=[68]*8,duration=16,Q=100)]

def slow_charge(schedule):
    p=np.zeros((96,8));q=p.copy();soc=np.full((97,8),760.)
    p[0:24]=320/.95/6
    for u,start in enumerate(schedule['begin']):
        p[start:start+schedule['duration'],u]=-320*.95/(.25*schedule['duration'])
        q[start:start+schedule['duration'],u]=-schedule['Q']
    for t in range(96):soc[t+1]=soc[t]+.25*(.95*np.maximum(p[t],0)-np.maximum(-p[t],0)/.95)
    assert np.max(abs(soc[-1]-760))<1e-8 and soc.min()>=440-1e-8 and soc.max()<=1080+1e-8
    assert abs(p).max()<=300 and abs(q).max()<=250
    for a in np.arange(16)*np.pi/8:assert np.max(np.cos(a)*p+np.sin(a)*q)<=400*np.cos(np.pi/16)+1e-8
    return p,q,soc

def register():
    value=dict(experiment='V2_add',authority='Finite temporal diagnostic scope within user Part E',
        reason='TIME transition voltage safety and charging rebound must be tested; extend charge from2h to6h at identical320kWh SOC cycle before any temporal-pilot result is used',
        original_temporal_preregistration_unchanged=True,beta=[1.5,2.0],charge_slots=[0,23],schedules=SCHEDULES,
        source_vehicle_P_Q_PCS_SOC_eta_unchanged=True,physical_settings_unchanged=True,
        Native_calls=0,selection='report all; never retune P5 or beta',code_sha256=sha(Path(__file__).read_bytes()))
    path=c.OUT/'CHARGE_SPREAD_PREREGISTRATION.json'
    if path.exists():assert read(path)==value
    else:c.put(path.name,value)
    for s in SCHEDULES:slow_charge(s)

def main():
    register();install();c.priority();c.RUN=c.RUNTIME/'correction_charge_spread_time100';c.RUN.mkdir(exist_ok=True);c.trajectory=slow_charge
    output=[];peaks=[];units=[];checks=[]
    for beta in (1.5,2.0):
        folder=c.RUNTIME/'correction_time100'/f'TIME_{beta:.2f}_ACTUAL_B0';br=read(folder/'ROWS.json');base=c.summary(br,read(folder/'RECEIPT.json'),beta,'ACTUAL')
        for schedule in SCHEDULES:
            rows,r=c.run_case(beta,'ACTUAL',schedule=schedule);s=c.summary(rows,r,beta,'ACTUAL');p,q,soc=slow_charge(schedule)
            fr,rr=c.run_case(beta,'ACTUAL',schedule=schedule,fresh=True);checks.append(c.fresh_check(r,rr));assert checks[-1]['PASS']
            s.update(schedule=schedule['name'],delta_global_pp=100*(base['rho_objective']-s['rho_objective']),
                charge_kwh=float(np.maximum(p,0).sum()*.25),discharge_kwh=float(np.maximum(-p,0).sum()*.25),
                at_original_peak_reduction_pp=100*(br[24+base['peak_slot']]['rho_global']-rows[24+base['peak_slot']]['rho_global']),
                status='FEASIBLE_CONTROL_PILOT_CERTIFIED' if r['physics_PASS'] else 'DIAGNOSTIC_PHYSICAL_FAIL_NOT_FEASIBLE_PILOT')
            output.append(s)
            peaks.append(dict(beta_BG=beta,schedule=schedule['name'],old_peak=base['peak_slot'],new_peak=s['peak_slot'],
                line=s['line'],phase=s['phase'],fleet_P_at_peak=float(p[s['peak_slot']].sum()),delta_global_pp=s['delta_global_pp'],physics_PASS=s['physics_PASS']))
            initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
            for u,(unit,site) in enumerate(initial.items()):
                for t in range(96):units.append(dict(beta_BG=beta,schedule=schedule['name'],vehicle=unit,STA=site,slot=t,
                    P_demand_kw=float(p[t,u]),Q_demand_kvar=float(q[t,u]),SOC_start=float(soc[t,u]),SOC_end=float(soc[t+1,u]),travel_energy_kwh=0,ETA_slots=0,route='SOURCE_STAY',PCS16_PASS=True))
            c.csvout('MESS8_CHARGE_SPREAD_COMPARISON.csv',output);c.csvout('MESS8_CHARGE_SPREAD_PEAKS.csv',peaks)
            c.csvout('MESS8_CHARGE_SPREAD_UNIT_TRAJECTORIES.csv',units);c.put('MESS8_CHARGE_SPREAD_FRESH_CHECKS.json',checks)

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='register':register()
    else:main()
