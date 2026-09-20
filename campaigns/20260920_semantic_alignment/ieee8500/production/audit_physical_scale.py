"""B0 physical-scale audit: independently derive profiles and read back DSS inputs."""
from bootstrap import *
import csv,inspect
import pandas as pd
from headroom_authority import OLD,NEW
from dayahead.v39a.contracts import IDLE_W_PER_GPU,CENTER_SWING_W_PER_GPU
from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
from dayahead.v41.data import SOURCE_REPO
from dayahead.v40d_actual.exogenous import load
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
AUDIT=P/'scale_audit';AUDIT.mkdir(exist_ok=True)
OLDROOT=P.parent.parent/'IEEE8500_FINAL_MAY01_PRODUCTION_20260918_STAGING/production'
SCALES=dict(BG=.45,AIDC=2.10,MESS=2.,PV=.50)

def main():
 protect()
 fc=read(P/'D1_AEMO_VIC1_FORECAST.json');exo=load(SOURCE_REPO,'2025-05-01')
 wf=pd.read_parquet(P.parent.parent/'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/may_2025/days/2025-05-01/gfs_d1_weather.parquet')
 params=load_c1(ROOT/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json')
 da=dict(np.load(P/'MAY01_B0_AIDC_POWER.npz'));old=dict(np.load(OLDROOT/'Actual/B0/ACTUAL_INPUTS.npz'))
 actualpower=dict(np.load(OLDROOT/'Actual/B0/ACTUAL_AIDC_POWER.npz'))
 profiles=dict(DA=(np.asarray(fc['demand_mw_96'])/max(fc['demand_mw_96']),np.asarray(fc['pv_mw_96'])/max(fc['pv_mw_96'])),Actual=(np.asarray(exo['demand_mw'])/max(fc['demand_mw_96']),np.asarray(exo['pv_mw'])/max(fc['pv_mw_96'])))
 profiles['Fresh']=profiles['DA']
 errors={};normalized={};base=[]
 for j in range(12):
  it=(OLD[j]*float(IDLE_W_PER_GPU)+NEW[j]*float(CENTER_SWING_W_PER_GPU))/1000
  base.append(2*float(exact_c1_pcc_kw(it,float(wf.iloc[0].t_wb_c),float(wf.iloc[0].rh_pct),params)))
 base=np.array(base)
 for phase,occ,it,power,weather in [('DA',da['gpu'],da['it'],da['pcc'],wf),('Actual',actualpower['occupancy'],actualpower['IT'],actualpower['PCC_P'],exo['weather'])]:
  gpu=occ/4.2;assert np.max(abs(gpu-np.round(gpu)))<1e-9
  calc_it=(np.array(OLD)*float(IDLE_W_PER_GPU)+gpu*float(CENTER_SWING_W_PER_GPU))/1000
  calc=4.2*np.array([[float(exact_c1_pcc_kw(calc_it[t,j],float(w.t_wb_c),float(w.rh_pct),params)) for j in range(12)] for t,w in enumerate(weather.itertuples())])
  errors[phase+'_IT']=float(np.max(abs(4.2*calc_it-it)))
  errors[phase+'_AIDC_P']=float(np.max(abs(calc-power)))
  normalized[phase]=calc/2.1/base
 normalized['Fresh']=normalized['DA']
 errors['Actual_demand_profile']=float(np.max(abs(old['md']-profiles['Actual'][0])))
 errors['Actual_PV_profile']=float(np.max(abs(old['mpv']-profiles['Actual'][1])))
 errors['Actual_AIDC_input_binding']=float(np.max(abs(old['PCC_P']-actualpower['PCC_P'])))
 errors['B0_MESS_P']=float(np.max(abs(old['P_EXEC'])))
 errors['B0_MESS_Q']=float(np.max(abs(old['Q_EXEC'])))
 authority=MessElectricalAuthority.from_repository();authority.validate()
 fields=dict(active_power_limit_kw=300,pcs_kva=400,capacity_kwh=1200,energy_min_kwh=440,energy_max_kwh=1080,initial_energy_kwh=760,terminal_energy_kwh=760)
 rating={k:dict(scale=2.,base=v,expected=2*v,actual=getattr(authority,k),PASS=abs(getattr(authority,k)-2*v)<1e-9) for k,v in fields.items()}
 errors['B0_MESS_initial_E']=float(np.max(abs(old['energy_after']-1520)))
 e=Engine(AUDIT/'native_inventory');native=e.loads;bp=e.P.copy();bq=e.Q.copy();ratio=e.ratio;e.close()
 save(AUDIT/'NATIVE_BASE_QUANTITIES.json',dict(loads=native,PV_ratio=ratio,AIDC_base_kw=base,AIDC_base_definition='2 * unchanged C1(full authorized normalized capacity, forecast slot-0 weather); profiles independently reconstructed from frozen/realized occupancy and weather',AIDC_internal_factor='original base 2 * physical scale 2.10 = 4.2'))
 slot_rows=[];readbacks=[]
 detail=AUDIT/'B0_SCALE_DECOMPOSITION_BY_ELEMENT.csv'
 with detail.open('w',newline='',encoding='utf-8-sig') as f:
  writer=csv.DictWriter(f,fieldnames=['phase','slot','component','element','scale','normalized_profile','native_base_quantity','expected','OpenDSS_readback','absolute_error','unit']);writer.writeheader()
  for phase in ('DA','Fresh','Actual'):
   e=Engine(AUDIT/phase/'runtime');md,mpv=profiles[phase];e.md=md;e.mpv=mpv;e.ap=da['pcc'] if phase!='Actual' else old['PCC_P'];e.aq=e.ap*PF_TAN
   try:
    for t in range(96):
     e.inputs(t);maxerror=0.
     def row(comp,element,scale,profile,quantity,got,unit):
      nonlocal maxerror
      expected=scale*profile*quantity;error=abs(expected-got);maxerror=max(maxerror,error)
      writer.writerow(dict(phase=phase,slot=t,component=comp,element=element,scale=scale,normalized_profile=profile,native_base_quantity=quantity,expected=expected,OpenDSS_readback=got,absolute_error=error,unit=unit))
     for j,r in enumerate(native):
      e.d.Loads.Name(r['load']);row('BG_P',r['load'],.45,md[t],bp[j],e.d.Loads.kW(),'kW');row('BG_Q',r['load'],.45,md[t],bq[j],e.d.Loads.kvar(),'kvar')
      e.d.Generators.Name(f'op8500_pv_{j:04d}');row('PV_P',f'op8500_pv_{j:04d}',.5,mpv[t],ratio*bp[j],e.d.Generators.kW() if e.d.CktElement.Enabled() else 0.,'kW')
     for j in range(12):
      name=f'op8500_aidc{j+1:02}';e.d.Loads.Name(name);row('AIDC_P',name,2.1,normalized[phase][t,j],base[j],e.d.Loads.kW(),'kW');row('AIDC_Q',name,2.1,normalized[phase][t,j],base[j]*PF_TAN,e.d.Loads.kvar(),'kvar')
     assert e.d.Solution.LoadMult()==1.
     e.solve();v,line,tx,kva=e.arrays()
     slot_rows.append(dict(phase=phase,slot=t,BG_scale=.45,BG_profile=float(md[t]),BG_native_base_kw=float(bp.sum()),BG_kw=float(.45*md[t]*bp.sum()),PV_scale=.5,PV_profile=float(mpv[t]),PV_native_base_kw=float(ratio*bp.sum()),PV_kw=float(.5*mpv[t]*ratio*bp.sum()),AIDC_scale=2.1,AIDC_kw=float(e.ap[t].sum()),MESS_scale=2.,max_input_error=maxerror,rho=float(abs(line).max()),Vmin=float(np.sqrt(v).min()),Vmax=float(np.sqrt(v).max()),controls_settled=bool(e.d.Solution.ControlActionsDone())))
     readbacks.append(maxerror)
   finally:e.close()
   print('SCALE_AUDIT_PHASE_COMPLETE',phase,flush=True)
 errors['OpenDSS_all_element_readback']=max(readbacks)
 passed=max(errors.values())<1e-8 and all(r['PASS'] for r in rating.values())
 with (AUDIT/'B0_SCALE_DECOMPOSITION_96_SLOTS.csv').open('w',newline='',encoding='utf-8-sig') as f:
  writer=csv.DictWriter(f,fieldnames=list(slot_rows[0]));writer.writeheader();writer.writerows(slot_rows)
 report=dict(status='PASS' if passed else 'SCALE_MISMATCH_INVALID',scales=SCALES,slots_per_phase=96,phases=['DA','Fresh','Actual'],max_errors=errors,MESS_rating=rating,unchanged_efficiency=dict(charge=authority.charge_efficiency,discharge=authority.discharge_efficiency),normalization='Both forecast and realized BG/PV divide by the same frozen forecast peak; AIDC follows the same idle/dynamic/C1 law using causal execution and weather',prior_Actual_B0=str(OLDROOT/'Actual/B0'),prior_Actual_disposition='PHYSICAL_SCALE_MATCHES; old controller result is superseded for new Q-first campaign' if passed else 'INVALID_SCALE_MISMATCH; all old Actual excluded; new execution required',details=str(detail),slot_summary=str(AUDIT/'B0_SCALE_DECOMPOSITION_96_SLOTS.csv'),per_phase_metrics={phase:dict(rho=max(r['rho'] for r in slot_rows if r['phase']==phase),Vmin=min(r['Vmin'] for r in slot_rows if r['phase']==phase),Vmax=max(r['Vmax'] for r in slot_rows if r['phase']==phase)) for phase in profiles},sources=[record(P/'electrical_engine.py'),record(P/'frozen_binding.py'),record(P/'actual_power_binding.py'),record(OLDROOT/'Actual/B0/ACTUAL_INPUTS.npz'),record(OLDROOT/'Actual/B0/ACTUAL_AIDC_POWER.npz'),record(P/'MAY01_B0_AIDC_POWER.npz')])
 save(AUDIT/'PHYSICAL_SCALE_AUDIT.json',report)
 save(P/'PRIOR_ACTUAL_DISPOSITION.json',dict(status=report['prior_Actual_disposition'],original_files_preserved=True,reuse_as_new_Actual=False,audit=record(AUDIT/'PHYSICAL_SCALE_AUDIT.json')))
 assert passed,errors
 print('B0_PHYSICAL_SCALE_PASS',json.dumps(errors),flush=True)
if __name__=='__main__':main()
