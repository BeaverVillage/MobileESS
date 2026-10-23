"""Finite SOC-feasible pilot on S1_03 beta2 evaluation96-operational candidate."""
from pathlib import Path
import numpy as np
from . import correction as c
from .audit import read,sha,DOC
from .correction_projection import project
from .correction_svr import SV,save
from . import correction_svr_run as runner
from .correction_svr_implicit import source_svr

def main(register_only=False):
    schedules=[dict(name='S1_03_PEAK31_27_34',discharge_begin=[27]*8,duration=8,Q_support=0),dict(name='S1_03_PEAK31_24_39',discharge_begin=[24]*8,duration=16,Q_support=0)]
    reg=dict(status='POST_B0_REGISTERED_BEFORE_PILOT_AC',configuration='S1_03',beta=2.,schedules=schedules,
        reason='S1_03 beta2 B0 passes evaluation96 settled/event physical gates; cold Prefix unsafe remains separate',
        original_initial_states_and_P5_preserved=True,Primary_selection=False,no_optimization=True,no_further_hardware_or_beta_tuning=True)
    path=SV/'SVR_PEAK31_DIAGNOSTIC_PREREGISTRATION.json'
    if path.exists():assert read(path)==reg
    else:save(path.name,reg)
    if register_only:return
    c.priority();runner.seal_s0();runner.source_svr=source_svr
    runner.RUN=c.RUNTIME/'correction_svr_peak31';runner.RUN.mkdir(exist_ok=True);runner.install('S1_03')
    original=c.fingerprint
    def fingerprint():
        v=original()
        for p in (Path(__file__),path,Path(source_svr.__code__.co_filename)):v[str(p)]=sha(p.read_bytes())
        return v
    c.fingerprint=fingerprint
    base,_,_,_=project(c.RUNTIME/'correction_svr/TIME_2.00_ACTUAL_S1_03/RECEIPT.json')
    results=[];checks=[];units=[]
    for schedule in schedules:
        _,r=c.run_case(2.,'ACTUAL',schedule=schedule);_,fr=c.run_case(2.,'ACTUAL',schedule=schedule,fresh=True)
        check=c.fresh_check(r,fr);assert check['PASS'];checks.append(check)
        result,slots,_,_=project(Path(r['archive_path']).parent/'RECEIPT.json');p,q,soc=c.trajectory(schedule)
        result.update(configuration='S1_03',schedule=schedule['name'],baseline_rho=base['rho_objective'],
            delta_global_pp=100*(base['rho_objective']-result['rho_objective']),base_peak_slot=base['peak_slot'],
            at_original_peak_reduction_pp=100*(base['rho_objective']-slots[base['peak_slot']+24]['rho_objective']),
            charge_kwh=float(np.maximum(p,0).sum()*.25),discharge_kwh=float(np.maximum(-p,0).sum()*.25),SOC_min=float(soc.min()),SOC_max=float(soc.max()))
        results.append(result)
        initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
        for u,(unit,site) in enumerate(initial.items()):
            for t in range(96):units.append(dict(beta_BG=2.,schedule=schedule['name'],vehicle=unit,STA=site,slot=t,P_demand_kw=float(p[t,u]),Q_demand_kvar=float(q[t,u]),SOC_start=float(soc[t,u]),SOC_end=float(soc[t+1,u]),travel_energy_kwh=0,ETA_slots=0,route='SOURCE_STAY'))
        c.csvout('SVR_PEAK31_DIAGNOSTIC_CANONICAL_RESULTS.csv',results);c.csvout('SVR_PEAK31_DIAGNOSTIC_UNIT_TRAJECTORIES.csv',units)
        save('SVR_PEAK31_DIAGNOSTIC_FRESH_CHECKS.json',checks)
    print('S1 FINITE PEAK31 PILOT COMPLETE',flush=True)

if __name__=='__main__':
    import sys
    main('--register-only' in sys.argv)
