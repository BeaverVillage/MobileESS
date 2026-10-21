"""Finite, preregistered TIME stress and temporal diagnostics; Native0."""
import sys
from pathlib import Path
import numpy as np
from .audit import DOC,ROOT,read,sha
from .correction import OUT,RUN,EXT,put,csvout,priority,run_case,summary,fresh_check,trajectory,fingerprint

def register():
    OUT.mkdir(exist_ok=True)
    prereg=dict(experiment='V2_add',authority='2026-10-21 user correction directive; NEW extension, not historical registration',
        beta_BG=EXT,background_only=True,original_alpha1_15_already_in_arrays=True,application_count=1,
        unchanged=['PV','AIDC','Jobs','C1','PCC','P5','line/transformer ratings','Route','MESS8/P300/Q250/PCS400/SOC'],
        order=EXT,roles=['PLANNING96','ACTUAL_PREFIX24_EVAL96'],fresh='independent full replay every beta/role',
        objective='V44_CANONICAL_OBJECTIVE; both-terminal safety separate',
        target_primary=[.75,.85],target_fallback=[.70,.85],minimum_daily_MV_LV_headroom=.05,
        ranking='all gates incl physical/QoS pass first; primary interval before fallback; closest to0.80, then lower beta; never use B1/B2/B3 results',
        one_pp_control_gain='preferred, not guaranteed',
        failing_candidates='preserved as diagnostic failures; never certified as V44 operational B0',
        native_calls=0,scientific_inputs=fingerprint())
    p=OUT/'EXTENDED_BETA_PREREGISTRATION.json'
    if p.exists():assert read(p)==prereg
    else:put(p.name,prereg)
    schedules=[dict(name='ORIGINAL_68_75',discharge_begin=[68]*8,duration=8,Q_support=0)]
    for shift in (1,2,3,4):schedules.append(dict(name=f'LATE_{shift}',discharge_begin=[68+shift]*8,duration=8,Q_support=0))
    schedules.extend([dict(name='LONG_68_83',discharge_begin=[68]*8,duration=16,Q_support=0),
        dict(name='STAGGERED_68_82',discharge_begin=list(range(68,76)),duration=8,Q_support=0),
        dict(name='LONG_Q100',discharge_begin=[68]*8,duration=16,Q_support=100)])
    for s in schedules:trajectory(s)
    pilotreg=dict(schedules=schedules,beta=[1.5,2.0],
        beta_choice='1.50 old comparison and2.00 user extension nominal80%-region diagnostic anchor fixed before stress results; no scenario-selection authority',
        battery='SOC760->1080->760 each vehicle; 320kWh cycle .95/.95; same initial8 sites; original STAY route entries reused, no forced future STAY',
        finite_diagnostic_only=True,no_optimization=True,all_initial_transients_and_event_security_count=True)
    if (OUT/'MESS8_TEMPORAL_PREREGISTRATION.json').exists():assert read(OUT/'MESS8_TEMPORAL_PREREGISTRATION.json')==pilotreg
    else:put('MESS8_TEMPORAL_PREREGISTRATION.json',pilotreg)
    print('REGISTERED extension and',len(schedules),'temporal schedules',flush=True)

def extension():
    priority();assert read(OUT/'TIME_CONTROL_FRESH_CERTIFICATION.json')['status']=='TIME_CONTROL_CERTIFIED'
    register();results=[];checks=[];headroom=[];top=[];receipts=[]
    for beta in EXT:
        for role in ('PLANNING','ACTUAL'):
            rows,r=run_case(beta,role);fr,rr=run_case(beta,role,fresh=True);checks.append(fresh_check(r,rr));assert checks[-1]['PASS']
            result=summary(rows,r,beta,role);result.update(certification='B0_PHYSICAL_CERTIFIED' if r['physics_PASS'] else 'DIAGNOSTIC_TIME_PHYSICAL_FAIL')
            results.append(result);receipts.extend([r,rr])
            off=24 if role=='ACTUAL' else 0
            for row in rows:headroom.append(dict(beta_BG=beta,role=role,slot=row['slot'],evaluation_slot=row['evaluation_slot'],
                rho_MV_objective=row['rho_MV'],rho_LV_objective=row['rho_LV'],MV_LV_pp=100*(row['rho_MV']-row['rho_LV']),
                rho_objective=row['rho_global'],rho_all_terminals=row['rho_all_terminals'],line=row['binding_line'],phase=row['binding_physical_phase'],
                terminal=row['binding_terminal'],physics_PASS=row['physics_PASS']))
            path=Path(r['archive_path']).parent;axes=read(path/'AXES.json')['line'];a=np.load(path/'AC_FULL.npz')
            rh=a['line_rho'][a['event_slot']>=off];maxima={}
            for j,v in enumerate(axes):
                if not v['objective_included']:continue
                rho=float(rh[:,j].max())
                if rho>maxima.get(v['element'],{}).get('rho',-1):maxima[v['element']]=dict(line=v['element'],rho=rho,phase=v['physical_phase'],terminal=v['terminal'])
            for rank,v in enumerate(sorted(maxima.values(),key=lambda r:(-r['rho'],r['line']))[:20]):top.append(dict(beta_BG=beta,role=role,rank=rank+1,**v))
            csvout('EXTENDED_BETA_B0_RESULTS.csv',results);csvout('EXTENDED_BETA_MV_LV_HEADROOM.csv',headroom)
            csvout('EXTENDED_BETA_TOP20.csv',top);put('EXTENDED_BETA_FRESH_CHECKS.json',checks);put('EXTENDED_BETA_RECEIPTS.json',receipts)
    print('EXTENSION COMPLETE',flush=True)

def temporal():
    priority();assert read(OUT/'TIME_CONTROL_FRESH_CERTIFICATION.json')['status']=='TIME_CONTROL_CERTIFIED'
    register();reg=read(OUT/'MESS8_TEMPORAL_PREREGISTRATION.json');output=[];peaks=[];units=[];checks=[]
    for beta in reg['beta']:
        baserows,base=run_case(beta,'ACTUAL');b=summary(baserows,base,beta,'ACTUAL')
        for schedule in reg['schedules']:
            rows,r=run_case(beta,'ACTUAL',schedule=schedule);s=summary(rows,r,beta,'ACTUAL')
            p,q,soc=trajectory(schedule)
            s.update(schedule=schedule['name'],baseline_rho=b['rho_objective'],delta_global_pp=100*(b['rho_objective']-s['rho_objective']),
                base_peak_slot=b['peak_slot'],at_original_peak_reduction_pp=100*(baserows[b['peak_slot']+24]['rho_global']-rows[b['peak_slot']+24]['rho_global']),
                charge_kwh=float(np.maximum(p,0).sum()*.25),discharge_kwh=float(np.maximum(-p,0).sum()*.25),SOC_min=float(soc.min()),SOC_max=float(soc.max()),
                status='FEASIBLE_CONTROL_PILOT_CERTIFIED' if r['physics_PASS'] else 'DIAGNOSTIC_PHYSICAL_FAIL_NOT_FEASIBLE_PILOT')
            output.append(s);peaks.append(dict(beta_BG=beta,schedule=schedule['name'],old_peak=b['peak_slot'],new_peak=s['peak_slot'],
                new_peak_time=f'{int(s["peak_slot"])//4:02d}:{int(s["peak_slot"])%4*15:02d}',line=s['line'],phase=s['phase'],
                fleet_P_at_peak=float(p[int(s['peak_slot'])].sum()),delta_global_pp=s['delta_global_pp'],physics_PASS=s['physics_PASS']))
            initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
            for u,(unit,site) in enumerate(initial.items()):
                for t in range(96):units.append(dict(beta_BG=beta,schedule=schedule['name'],vehicle=unit,STA=site,slot=t,
                    P_demand_kw=float(p[t,u]),Q_demand_kvar=float(q[t,u]),SOC_start=float(soc[t,u]),SOC_end=float(soc[t+1,u]),
                    travel_energy_kwh=0,ETA_slots=0,route='SOURCE_STAY',PCS16_PASS=True))
            # Every finite candidate has an independent Fresh, including failures.
            fr,rr=run_case(beta,'ACTUAL',schedule=schedule,fresh=True);checks.append(fresh_check(r,rr));assert checks[-1]['PASS']
            csvout('MESS8_TEMPORAL_PILOT_COMPARISON.csv',output);csvout('MESS8_PEAK_SHIFT_ANALYSIS.csv',peaks)
            csvout('MESS8_TEMPORAL_UNIT_TRAJECTORIES.csv',units);put('MESS8_TEMPORAL_FRESH_CHECKS.json',checks)
    print('TEMPORAL COMPLETE',flush=True)

def legacy_remaining():
    priority();assert read(OUT/'TIME_CONTROL_FRESH_CERTIFICATION.json')['status']=='TIME_CONTROL_CERTIFIED'
    output=[];checks=[]
    for beta in (1.05,1.10,1.15,1.20,1.25,1.30,1.40):
        for role in ('PLANNING','ACTUAL'):
            rows,r=run_case(beta,role);fr,rr=run_case(beta,role,fresh=True)
            checks.append(fresh_check(r,rr));assert checks[-1]['PASS'];output.append(summary(rows,r,beta,role))
            csvout('LEGACY_BETA_TIME_REVALIDATION.csv',output);put('LEGACY_BETA_TIME_FRESH_CHECKS.json',checks)

if __name__=='__main__':globals()[sys.argv[1]]()
