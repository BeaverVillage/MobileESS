"""Re-evaluate all original finite pilot definitions under certified TIME loop."""
from pathlib import Path
import numpy as np
from . import correction as c
from .correction_time100 import install
from .audit import DOC,read,sha

def scaled_trajectory(schedule):
    p=np.zeros((96,8));q=p.copy();soc=np.full((97,8),760.)
    if schedule.get('amplitude',0):
        a=schedule['amplitude'];p[8:16]=a*320/.95/2;p[68:76]=-a*320*.95/2
    for t in range(96):soc[t+1]=soc[t]+.25*(.95*np.maximum(p[t],0)-np.maximum(-p[t],0)/.95)
    assert np.max(abs(soc[-1]-760))<1e-8 and soc.min()>=440-1e-8 and soc.max()<=1080+1e-8
    for angle in np.arange(16)*np.pi/8:assert np.max(np.cos(angle)*p+np.sin(angle)*q)<=400*np.cos(np.pi/16)+1e-8
    return p,q,soc

def main():
    install();c.priority();c.RUN=c.RUNTIME/'correction_old_pilot_time100';c.RUN.mkdir(exist_ok=True)
    c.trajectory=scaled_trajectory
    z=np.load(DOC/'source/aidc_pilot/AIDC_FEASIBLE_CANDIDATE.npz');frozen=np.load(DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz')
    output=[];checks=[]
    for role in ('PLANNING','ACTUAL'):
        bpath=c.RUNTIME/'correction_time100'/f'TIME_1.50_{role}_B0'
        base=c.summary(read(bpath/'ROWS.json'),read(bpath/'RECEIPT.json'),1.5,role)
        for kind in ('AIDC_ONLY','MESS_ONLY','JOINT'):
            for amplitude in ([0.] if kind=='AIDC_ONLY' else [.25,.5,1.]):
                delta=None
                if kind in ('AIDC_ONLY','JOINT'):
                    delta=np.stack([z[role+'_P']-frozen[role+'_AIDC_P_kw'],z[role+'_Q']-frozen[role+'_AIDC_Q_kvar']],axis=-1)
                schedule=dict(name=f'LEGACY_{kind}_{amplitude:.2f}',amplitude=amplitude)
                rows,r=c.run_case(1.5,role,schedule=schedule,aidc=delta);s=c.summary(rows,r,1.5,role)
                fr,rr=c.run_case(1.5,role,schedule=schedule,aidc=delta,fresh=True);checks.append(c.fresh_check(r,rr));assert checks[-1]['PASS']
                s.update(kind=kind,amplitude=amplitude,delta_global_pp=100*(base['rho_objective']-s['rho_objective']),
                    nonzero_actual_AIDC_witness=False if role=='ACTUAL' and kind!='MESS_ONLY' else None,
                    status='TIME_PHYSICS_PASS_LIMITED_WITNESS' if r['physics_PASS'] else 'TIME_PHYSICAL_FAIL',
                    no_B1_B2_B3_optimization_claim=True)
                output.append(s);c.csvout('LEGACY_PILOT_TIME_REVALIDATION.csv',output);c.put('LEGACY_PILOT_TIME_FRESH_CHECKS.json',checks)
    print('ALL LEGACY PILOT DEFINITIONS REPLAYED',flush=True)

if __name__=='__main__':main()
