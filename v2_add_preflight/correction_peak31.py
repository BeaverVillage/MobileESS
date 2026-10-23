"""Post-B0 finite MESS diagnostic at the newly observed high-BG peak31.

Not backdated into the original preregistration; no scenario-selection or
optimization authority. Only original stationary8 SOC-feasible trajectories.
"""
import json
from pathlib import Path
import numpy as np
from . import correction as c
from .audit import read,sha,DOC
from .correction_time100 import install
from .correction_projection import project,CAN

def main(register_only=False):
    c.priority();install();c.RUN=c.RUNTIME/'correction_peak31_time100';c.RUN.mkdir(exist_ok=True)
    schedules=[dict(name='PEAK31_27_34',discharge_begin=[27]*8,duration=8,Q_support=0),dict(name='PEAK31_24_39',discharge_begin=[24]*8,duration=16,Q_support=0)]
    prereg=dict(status='POST_B0_PREREGISTERED_BEFORE_THIS_DISPATCH_AC',beta=[2.,2.1],schedules=schedules,
        reason='Canonical high-BG B0 peak is31; existing68..75 pilots do not overlap it',
        B0_observed_before_registration=True,B0_selection_authority=False,posthoc_beta_tuning=False,
        same_source_PCS_SOC_Route_and_initial_sites=True,hardware='S0; physical FAIL candidates retained as diagnostic only',Native_calls=0)
    p=c.OUT/'PEAK31_DIAGNOSTIC_PREREGISTRATION.json'
    if p.exists():assert read(p)==prereg
    else:c.put(p.name,prereg)
    if register_only:return
    base_fingerprint=c.fingerprint
    def fingerprint():
        v=base_fingerprint();v['peak31_diagnostic_code']=sha(Path(__file__).read_bytes());v['peak31_preregistration']=sha(p.read_bytes());return v
    c.fingerprint=fingerprint
    output=[];units=[];checks=[]
    for beta in prereg['beta']:
        b,_,_,_=project(c.RUNTIME/'correction_time100'/f'TIME_{beta:.2f}_ACTUAL_B0/RECEIPT.json')
        for schedule in schedules:
            rhos,receipt=c.run_case(beta,'ACTUAL',schedule=schedule)
            _,fresh=c.run_case(beta,'ACTUAL',schedule=schedule,fresh=True)
            check=c.fresh_check(receipt,fresh);assert check['PASS'];checks.append(check)
            result,slots,_,_=project(Path(receipt['archive_path']).parent/'RECEIPT.json')
            pp,qq,soc=c.trajectory(schedule)
            result.update(schedule=schedule['name'],baseline_rho=b['rho_objective'],delta_global_pp=100*(b['rho_objective']-result['rho_objective']),
                base_peak_slot=b['peak_slot'],at_original_peak_reduction_pp=100*(b['rho_objective']-slots[b['peak_slot']+24]['rho_objective']),
                charge_kwh=float(np.maximum(pp,0).sum()*.25),discharge_kwh=float(np.maximum(-pp,0).sum()*.25),SOC_min=float(soc.min()),SOC_max=float(soc.max()))
            output.append(result)
            initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
            for u,(unit,site) in enumerate(initial.items()):
                for t in range(96):units.append(dict(beta_BG=beta,schedule=schedule['name'],vehicle=unit,STA=site,slot=t,
                    P_demand_kw=float(pp[t,u]),Q_demand_kvar=float(qq[t,u]),SOC_start=float(soc[t,u]),SOC_end=float(soc[t+1,u]),travel_energy_kwh=0,ETA_slots=0,route='SOURCE_STAY'))
            c.csvout('PEAK31_DIAGNOSTIC_CANONICAL_RESULTS.csv',output);c.csvout('PEAK31_DIAGNOSTIC_UNIT_TRAJECTORIES.csv',units);c.put('PEAK31_DIAGNOSTIC_FRESH_CHECKS.json',checks)
    print('POST_B0 PEAK31 DIAGNOSTIC COMPLETE',flush=True)

if __name__=='__main__':
    import sys
    main('--register-only' in sys.argv)
