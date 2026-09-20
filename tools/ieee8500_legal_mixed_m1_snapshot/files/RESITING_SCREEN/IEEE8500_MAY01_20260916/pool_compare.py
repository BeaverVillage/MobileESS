from optimize import *
import shutil
def main():
 start=time.perf_counter();names=['legal_mixed_M1','stress_pair_M1','remote_receivers_M1'];ref=H/'placements/legal_mixed_M1'
 jobs=[('B0_reference',BASE_P,None),('audited_original_21',np.load(ROOT/'independent_screening/IEEE8500_FAST_SCALE_20260916/B_DC_1/POWER.npz')['pcc'],ROOT/'independent_screening/IEEE8500_FAST_SCALE_20260916/B_DC_1'),('resited_17',np.load(ref/'B1_R2/B_DC_1/POWER.npz')['pcc'],ref/'B1_R2/B_DC_1')]
 ms=[]
 for name in ['B2_EXACT_PROXY','B3_EXACT_PROXY']:
  f=ref/name;mm={(r['slot'],r['station']):(r['P'],r['Q']) for r in read(f/'MESS.json')};assert physics(mm)['status']=='PASS';ms.append((name,mm,f))
 results=[];trials=[];slots=list(range(34,54))+list(range(68,86))
 for name in names:
  layout=read(H/'placements'/name/'LAYOUT.json');out=H/'final_proxy'/name;out.mkdir(parents=True,exist_ok=True);options={p:[] for p in ['B0','B1','B2','B3']}
  for jname,p,jpath in jobs:
   ac=replay(layout,p,out/f'{jname}_idle',slots=slots);r=dict(placement=name,job_schedule=jname,mess_schedule='idle',**ac);trials.append(r)
   if ac['physical_pass']:
    entry=(ac,p,None,jpath,jname,'idle');options['B1'].append(entry)
    if jname=='B0_reference':options['B0'].append(entry)
   for mname,mm,mpath in ms:
    ac=replay(layout,p,out/f'{jname}_{mname}',mess=mm,slots=slots);r=dict(placement=name,job_schedule=jname,mess_schedule=mname,**ac);trials.append(r)
    if ac['physical_pass']:
     entry=(ac,p,mm,jpath,jname,mname);options['B3'].append(entry)
     if jname=='B0_reference':options['B2'].append(entry)
  chosen={}
  for policy,opts in options.items():
   assert opts,f'{name} {policy} no feasible point';ac,p,mm,jpath,jname,mname=min(opts,key=lambda v:v[0]['max_phase_line_loading_pu'])
   target=out/policy;target.mkdir(exist_ok=True);np.savez_compressed(target/'POWER.npz',pcc=p);save(target/'MESS.json',[dict(slot=t,station=sid,P=pq[0],Q=pq[1]) for (t,sid),pq in (mm or {}).items()]);save(target/'PHYSICS.json',physics(mm or {}))
   if jpath:shutil.copyfile(jpath/'JOBS.json',target/'JOBS.json')
   else:shutil.copyfile(AUTH/'REFERENCE_JOBS.json',target/'JOBS.json')
   record=dict(policy=policy,job_schedule=jname,mess_schedule=mname,**ac);save(target/'RESULT.json',record);chosen[policy]=record
  rho=[chosen[f'B{i}']['max_phase_line_loading_pu'] for i in range(4)];adj=np.array(rho[:-1])-rho[1:]
  row=dict(placement=name,**{f'rho_B{i}':rho[i] for i in range(4)},Vmin=min(r['Vmin_pu'] for r in chosen.values()),Vmax=max(r['Vmax_pu'] for r in chosen.values()),AC_PASS=True,strict_ordering=bool((adj>1e-6).all()),total_reduction=rho[0]-rho[3],min_adjacent_separation=float(adj.min()),max_transformer_current_pu=max(r['max_transformer_phase_current_pu'] for r in chosen.values()),max_transformer_kVA_pu=max(r['max_transformer_winding_kva_pu'] for r in chosen.values()))
  results.append(row);print(json.dumps(row),flush=True)
 results.sort(key=lambda r:(r['rho_B3'],-r['total_reduction']));save(H/'FINAL_PROXY_RESULTS.json',results);table(H/'FINAL_PROXY_RESULTS.csv',results);save(H/'FINAL_PROXY_TRIALS.json',trials)
 save(H/'PROXY_METHOD.json',dict(status='finite-pool restricted screening, not production and not a global optimum',source='Original 24-cohort P1-P5 MILP restricted search with complete original options, original resource/WAN/PWL/job constraints, followed by exact-AC-accepted sequential P/Q refinement. Reuse the same audited 3-job-schedule x 2-MESS-schedule pool across all shortlisted infrastructures; B1 is best AIDC-only, B2 best fixed-workload MESS, B3 best joint feasible combination. No policy-ordering constraints. Exact maximum rho is primary when comparing returned incumbents.',critical_slots=list(range(68,86)),energy_recovery_slots=list(range(34,54)),energy_scope='96-slot recursion and exact initial/terminal energy; stationary routes at remapped initial station IDs; no travel',policy_comparison_runtime_seconds=time.perf_counter()-start,scale_up=False,full_96_slot_AC=False,production=False,Fresh_pipeline=False,Actual=False,global_optimum_proven=False))
 save(H/'PROVISIONAL_SELECTION.json',dict(placement=results[0]['placement'],selected_for_future_full_validation_only=True,infrastructure_frozen_for_Actual=False,metrics=results[0],layout=read(H/'placements'/results[0]['placement']/'LAYOUT.json')))
if __name__=='__main__':main()
