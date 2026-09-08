"""Clean-engine scenario replay. This entry point never optimizes."""
from pathlib import Path
import sys, os, json
from types import SimpleNamespace
import numpy as np
import pandas as pd
import calibrate as c
import support
sys.path.insert(0,str(c.ROOT))
DAY=support.DAY
RUN=support.RUN

def binding(bg,pcc):
    from dayahead.v28r2.opendss_mapping import FeederAssets
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
    assets=FeederAssets.from_repo(SOURCE_DATA_REPOSITORY);assets.validate()
    src=assets.master.parent.parent;previous=Path.cwd()
    try:
        result=build_full_grid_binding(assets=src/'opendss_assets',contract=src/'power_v70_p4f_contract',
            demand_mw_96=[0.]*96,rooftop_pv_mw_96=[0.]*96,aidc_plan_kw_96x12=pcc,
            pcc_asset=assets.pcc,background_binding=bg)
    finally:os.chdir(previous)
    return result,assets

def nominal_voltage():
    cert=c.read(c.ROOT/'frozen_artifacts/v41r3_scale/e/20250504/V41_ELECTRICAL_CERTIFICATE.json')
    p=support.verify(cert['outputs']['voltage'])
    with np.load(p) as z:return {k:z[k].copy() for k in ('node_names','regulator_taps','capacitor_states')}

def replay(label,policy,power,power_source,voltage,folder,native=False):
    import screen
    bg=support.background(label);grid,_=binding(bg,power[0])
    # Inputs have already been scaled exactly once by the materializer.
    original=screen.scale
    screen.scale=lambda bg,alpha:bg
    try:summary,result=screen.replay(1.6,'DAYAHEAD',bg,power,power_source,voltage,grid,folder,native=native)
    finally:screen.scale=original
    with np.load(folder/'physics/OPENDSS_PHASE_ARRAYS.npz') as z:
        line=np.asarray(z['branch_kinds'])=='line';rho=z['phase_current_loading_pu'][:,line]
    return dict(scenario=label,policy=policy,summary=summary,p95_line_loading=float(np.quantile(rho,.95)),
        p99_line_loading=float(np.quantile(rho,.99)),source=c.record(folder/'SUMMARY.json'),
        new_OpenDSS_trajectory_calls=1,new_OpenDSS_slots=96,decision_source=power_source),result

def main():
    audit=c.read(c.OUT/'V41R4_SCENARIO_PHYSICAL_SUPPORT_AUDIT.json');assert audit['status']=='PASS'
    for ref in audit['outputs'].values():support.verify(ref)
    support.verify(audit['authority'])
    b0=c.read(c.OLD/'V41R3_B0_ACCEPTANCE.json')
    provenance=c.read(c.SCALE/'V41R3_BACKGROUND_INPUT_PROVENANCE.json')['AIDC_power_sources']['DAYAHEAD']
    with np.load(support.verify(provenance)) as z:power=(z['pcc'].copy(),z['qcc'].copy())
    voltage=nominal_voltage();rows={}
    for label in ('S0','S1','S2'):
        row,result=replay(label,'B0',power,provenance,voltage,RUN/'B0'/label,native=True)
        rows[label]=row
        if label=='S0':
            assert max(abs(row['summary'][k]-b0['Fresh_summary'][k]) for k in ('Vmin_pu','Vmax_pu','rho_max_AC'))<1e-8
        print('SCENARIO_B0',label,row['summary']['rho_max_AC'],row['summary']['Vmin_pu'],row['summary']['Vmax_pu'],flush=True)
    result=dict(status='PASS' if all(r['summary']['eligible'] for r in rows.values()) else 'PHYSICAL_VIOLATION',
        day=DAY,scenarios=rows,MESS='OFF',same_B0_reference_schedule=True,source=c.record(__file__),
        physical_support_audit=c.record(c.OUT/'V41R4_SCENARIO_PHYSICAL_SUPPORT_AUDIT.json'),
        B0_AIDC_reference=support.verify(b0['decision_source']).as_posix(),
        historical_optimization_calls=0,historical_OpenDSS_calls=0,May04_optimization_calls=0,May04_OpenDSS_slots=288,
        MAY04_ROLE='DEVELOPMENT_PILOT',FULL_MAY='HOLD')
    c.save('V41R4_MAY04_SCENARIO_PREFLIGHT.json',result)

if __name__=='__main__':main()
