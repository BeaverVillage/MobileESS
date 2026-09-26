from pathlib import Path
import json,csv,sys,hashlib
import numpy as np
ROOT=Path(__file__).parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
def grid(p):
 paths=[Path(p)/'OPENDSS_PHASE_ARRAYS.npz'] if (Path(p)/'OPENDSS_PHASE_ARRAYS.npz').exists() else list(Path(p).rglob('OPENDSS_PHASE_ARRAYS.npz'));assert len(paths)==1,(p,paths)
 with np.load(paths[0]) as z:return float(z['phase_current_loading_pu'][:,z['branch_kinds']=='line'].max())
def metrics(da,ac):
 import pandas as pd
 d=read(da/'FROZEN_JOINT_DECISION.json')['decision'];jobs=d['AIDC_decision'];mess=d['MESS_trajectory']
 planning=read(da/'PLANNING_RESULT.json');fresh=read(da/'FRESH_RESULT.json')['summary'];actual=read(ac/'COMPLETE.json')['ETA95_QSAFE_ACTUAL']
 h=planning['reserve'];p=np.array([r['p_kw'] for r in mess]);q=np.array([r['q_kvar'] for r in mess])
 migrations=[r for r in jobs if r.get('migration_selected')]
 moves={(r['mess_id'],r['departure_slot'],r['origin_service_id'],r['destination_service_id']) for r in mess if r['departure_slot'] is not None and r['mode']=='TRANSIT'}
 carry=sum(r['requested_GPU']*.25*sum(max(0,s['end']-max(120,s['start'])) for s in r['compute_segments']) for r in jobs)
 migrated=sum(r['requested_GPU']*.25*sum(max(0,min(120,s['end'])-max(24,s['start'])) for s in r['compute_segments'] if s['site']!=r['initial_AIDC']) for r in migrations)
 v=read(da/'optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
 # DA exact replay and Fresh share the same frozen joint under original authority.
 rho=grid(da/'fresh')
 result=dict(P1_planning_rho=planning['grid']['rho_max'],DA_exact_AC_max_rho=rho,Fresh_exact_AC_max_rho=rho,Actual_max_rho=grid(ac/'ETA95_QSAFE_ACTUAL'),mean_reserve_shortfall_GPUh=h['mean_xi_GPUh'],total_reserve_shortfall_GPUh=h['sum_xi_GPUh'],migration_count=len(migrations),migrated_GPUh=migrated,post_horizon_service_GPUh=carry,carry_out_jobs=sum(any(s['end']>120 for s in r['compute_segments']) for r in jobs),MESS_relocation_count=len(moves),MESS_charge_kWh=float(.25*np.maximum(-p,0).sum()),MESS_discharge_kWh=float(.25*np.maximum(p,0).sum()),MESS_max_abs_P_kW=float(abs(p).max()),MESS_max_abs_Q_kvar=float(abs(q).max()),selected_job_option_changes_vs_reference=None,start_time_changes_vs_reference=None,site_placement_changes_vs_reference=None,AC_PASS=bool(not fresh['physical_violation'] and not actual['physical_violation'] and fresh['convergence_count']==actual['convergence_count']==96))
 # Reference is the original admitted job schedule used by P4/P5.
 reference_path=da/'authority/COMMON_B0_REFERENCE_JOBS.json'
 candidates=list((da/'authority').rglob('*REFERENCE*JOBS*.json'))
 if candidates:
  refs={r['job_uid']:r for r in read(candidates[0])}
 else:
  import runtime_environment as env
  domain=read(env.read_path(env.ORIGINAL/'frozen_artifacts/v41r4_may/audit'/d['day']/'domain/DAILY_DOMAIN_AUTHORITY.json'))
  refs={r['job_uid']:r for r in read(env.read_path(domain['reference']['path']))}
 fields=['AIDC_site','start_slot','end_slot','migration_selected']
 result.update(selected_job_option_changes_vs_reference=sum(any(r.get(k)!=refs[r['job_uid']].get(k) for k in fields) for r in jobs),start_time_changes_vs_reference=sum(r['start_slot']!=refs[r['job_uid']]['start_slot'] for r in jobs),site_placement_changes_vs_reference=sum(r['AIDC_site']!=refs[r['job_uid']]['AIDC_site'] for r in jobs))
 return result,d
def day_report(day,case):
 import runtime_environment as env
 env.ACTIVE='AUDIT'
 a=next(r for r in read(ROOT/'AUTHORITY_VERIFIED.json')['days'] if r['day']==day)
 oldda=Path(a['final_joint']['input_joint']).parent;newda=Path(read(case/'closure'/day/'ACCEPTANCE.json')['final_dayahead'])
 before,old=metrics(oldda,Path(a['Actual_root']));after,new=metrics(newda,case/'actual/replays'/day/'B3')
 for key in ['ML_snapshot','common_service_SHA','electrical']:assert old[key]==new[key],('PAIRED_INPUT_AUTHORITY_CHANGED',key)
 oldjobs={r['job_uid']:r for r in old['AIDC_decision']};newjobs={r['job_uid']:r for r in new['AIDC_decision']};assert oldjobs.keys()==newjobs.keys()
 fields=['AIDC_site','start_slot','end_slot','Rack_label','migration_selected','compute_segments','migration_events']
 changes=[dict(job_uid=k,fields=[f for f in fields if oldjobs[k].get(f)!=newjobs[k].get(f)],WITH=oldjobs[k],WITHOUT=newjobs[k]) for k in oldjobs if any(oldjobs[k].get(f)!=newjobs[k].get(f) for f in fields)]
 from dayahead.v40a.invariants import MOBILITY_FIELDS
 oldm={(r['mess_id'],r['slot']):r for r in old['MESS_trajectory']};newm={(r['mess_id'],r['slot']):r for r in new['MESS_trajectory']};assert oldm.keys()==newm.keys()
 routes=[dict(mess_id=k[0],slot=k[1],WITH=oldm[k],WITHOUT=newm[k]) for k in oldm if any(oldm[k].get(f)!=newm[k].get(f) for f in MOBILITY_FIELDS)]
 pq=[dict(mess_id=k[0],slot=k[1],WITH_P=oldm[k]['p_kw'],WITHOUT_P=newm[k]['p_kw'],WITH_Q=oldm[k]['q_kvar'],WITHOUT_Q=newm[k]['q_kvar']) for k in oldm if oldm[k]['p_kw']!=newm[k]['p_kw'] or oldm[k]['q_kvar']!=newm[k]['q_kvar']]
 counts=dict(changed_jobs_count=len(changes),changed_start_times_count=sum(oldjobs[k]['start_slot']!=newjobs[k]['start_slot'] for k in oldjobs),changed_site_placements_count=sum(oldjobs[k]['AIDC_site']!=newjobs[k]['AIDC_site'] for k in oldjobs),changed_migrations_count=sum(oldjobs[k].get('migration_events')!=newjobs[k].get('migration_events') for k in oldjobs),changed_MESS_route_count=len({r['mess_id'] for r in routes}),changed_MESS_route_intervals=len(routes),changed_PQ_intervals=len(pq))
 after['runtime_seconds']=sum(read(p).get('wall_seconds',0) for p in (case/'status').glob('*.json') if p.stem in ['A1','B3','CLOSURE','ACTUAL'])
 oldreceipt=read(oldda/'DAYAHEAD_RECEIPT.json')
 from datetime import datetime
 olda1=read(oldda.parents[1]/'B1/dayahead/DAYAHEAD_RECEIPT.json')
 before['runtime_seconds']=(datetime.fromisoformat(oldreceipt['completed_at'])-datetime.fromisoformat(oldreceipt['started_at'])).total_seconds()+(datetime.fromisoformat(olda1['completed_at'])-datetime.fromisoformat(olda1['started_at'])).total_seconds()
 before['runtime_seconds']+=read(Path(a['Actual_root'])/'COMPLETE.json')['ETA95_QSAFE_ACTUAL'].get('elapsed_seconds',0.)
 row={'date':day,**counts}
 for k in before:
  row['WITH_'+k]=before[k];row['WITHOUT_'+k]=after[k]
  if type(before[k]) in (float,int):row['DELTA_'+k]=before[k]-after[k]
 save(case/'paired.json',dict(status='PASS',row=row,WITH=before,WITHOUT=after,job_changes=changes,route_changes=routes,PQ_changes=pq,definitions={'delta':'WITH minus WITHOUT','DA_exact_AC':'Original production stores the clean frozen DA replay as Fresh; these columns intentionally alias the same exact AC trajectory. No affine/exact substitution.','migrated_GPUh':'Within issue horizon [24,120), compute GPUh on noninitial site for migration-selected jobs','total_shortfall':'Sum across 81 overlapping four-hour windows; not disjoint daily work','changed_MESS_route_count':'Number of vehicles with any changed mobility interval','runtime':'WITHOUT full A1/M1/A2/M2/closure/Actual wall; WITH sum of original A1+B3 receipt wall plus sealed Actual electrical replay elapsed; reporting overhead and historical closure overhead are not reconstructed'}))
 with (case/'paired.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=row);w.writeheader();w.writerow(row)
def aggregate():
 rows=[read(p)['row'] for p in sorted((ROOT/'days').glob('*/paired.json'))];out=ROOT/'reports';out.mkdir(exist_ok=True)
 if rows:
  with (out/'PAIRED_DAILY.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
 summary=dict(completed_pairs=len(rows),expected_pairs=31,status='COMPLETE' if len(rows)==31 else 'PARTIAL',TOTAL_AIDC_BUDGET_MATCHED=False,P1_BUDGET_UNCHANGED=True,REMAINING_PRIORITY_BUDGETS_UNCHANGED=True,P2_BUDGET_REDISTRIBUTED=False,NO_CC4_AIDC_BUDGET_SECONDS=1320)
 if rows:
  summary['means']={k:float(np.mean([r[k] for r in rows])) for k in rows[0] if type(rows[0][k]) in (float,int)}
  summary['maximum_Actual_rho']={p:max(r[p+'_Actual_max_rho'] for r in rows) for p in ['WITH','WITHOUT']}
  summary['reserve_shortfall_reduction_due_to_CC4_GPUh']=summary['means']['WITHOUT_mean_reserve_shortfall_GPUh']-summary['means']['WITH_mean_reserve_shortfall_GPUh']
  denominator=summary['means']['WITHOUT_mean_reserve_shortfall_GPUh']
  summary['reserve_shortfall_reduction_due_to_CC4_percent']=100*summary['reserve_shortfall_reduction_due_to_CC4_GPUh']/denominator if denominator else None
 save(out/'PAIRED_SUMMARY.json',summary)
 (out/'INTERPRETATION.md').write_text('CC4/P2 ablation: WITH reuses frozen IEEE123 May 2025 1-Round results.\n\nDifferences are WITH minus WITHOUT. A positive WITHOUT-minus-WITH reserve shortfall is a direct decision-facing benefit. Feeder differences are paired ablation differences only. Post-issue future jobs are not enqueued in realized replay; no job SLA/delay causal effect is evaluated. No claim that CC4 misses imply electrical infeasibility.\n\nP1 900 seconds unchanged; P3/P4/P5 180/120/120 seconds unchanged from original. P2 480 seconds omitted, not redistributed. NO_CC4 total 1320 seconds; WITH_CC4 frozen total 1800 seconds.\n',encoding='utf-8')
 return summary
if __name__=='__main__':print(json.dumps(aggregate(),indent=2))
