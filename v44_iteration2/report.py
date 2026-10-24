"""Per-date comparison; mixed hardware and combined treatment remain explicit."""
from pathlib import Path
import csv,gc,math
from . import config as c
from .io import read,record,atomic,verify
from .archives import Store
from .audit import trajectory

def physical_summary(store,case):
 rawpath=Path(case)/'ACTUAL/C1/FRESH_SVR12_TIME_AC.json'
 raw=store.read(rawpath);summary=trajectory(raw)
 summary['all120_Fresh_PASS']=all(r['PASS'] and r['converged'] and r['time_control']['PASS'] and r['SVR_devices']['hardware_PASS'] for r in raw['physical_steps'])
 summary['raw']=store.record(rawpath);del raw;gc.collect();return summary

def mess(plan):
 units={};site_count=len(plan['P_by_site'])
 for unit in c.FLEET:
  p=plan['P_kW'][unit];q=plan['Q_kvar'][unit];soc=plan['SOC_kWh'][unit]
  units[unit]=dict(moves=sum(int(k)>=site_count*96 for k in plan['route_paths'][unit]),
   P_min_kW=min(p),P_max_kW=max(p),Q_min_kvar=min(q),Q_max_kvar=max(q),SOC_min_kWh=min(soc),SOC_max_kWh=max(soc),SOC_terminal_kWh=soc[-1])
 return dict(units=units,total_moves=sum(x['moves'] for x in units.values()),plan_sha=plan['plan_sha'],full_route_P_Q_SOC_in_core_result=True)

def aidc(store,case):
 path=Path(case)/'ACTUAL/C1/ACTUAL_EVENT_LEDGERS.json'
 if not store.exists(path):return dict(available=False,reason='Fixed trajectory baseline uses preserved original event case; see original_case')
 events=store.read(path);qos=events['qos_ledger'];submitted={r['uid']:r for r in events['job_event_ledger'] if r.get('event')=='SUBMISSION_OBSERVED'}
 result=dict(available=True,Known_jobs=sum(r.get('origin_unknown') is False for r in submitted.values()),Unknown_jobs=sum(r.get('origin_unknown') is True for r in submitted.values()),
  Time_shifted_jobs=sum(r['intentional_start_delay_seconds']>1e-6 for r in qos),intentional_start_delay_seconds=sum(r['intentional_start_delay_seconds'] for r in qos),
  Migration_receipts=len(events['migration_receipts']),QoS_budget_violation_jobs=sum(r['total_intentional_burden_seconds']>r['budget_seconds']+1e-6 for r in qos),
  receipt=events['receipt'],events=store.record(path))
 v=store.read(Path(case)/'ACTUAL/C1/RESULT.json');result['Source_presite_executed']=v.get('Source_presite_executed');return result

def report(state):
 store=Store();rows=[];details=[];catalogue={x['day']:x for x in read(c.DOC/'BASELINE_CATALOG.json')['days']}
 try:
  for job in state['jobs']:
   day=job['day'];base=catalogue[day];old=physical_summary(store,base['comparison_case']);actual=job.get('actual',{});new={};audit={}
   if actual.get('result'):
    value=read(actual['result']['path'])
    if value.get('independent_audit'):
     verify([value['independent_audit']]);audit=read(value['independent_audit']['path']);new=audit.get('evaluation96',{})
   stage_values={s:read(x['result']['path']) for s,x in job['stages'].items() if x.get('result')}
   native=sum(v.get('Native_seconds') or 0. for v in stage_values.values())
   def improve(key):return 100*(old[key]-new[key])/old[key] if key in old and key in new and old[key]>0 else None
   f=audit.get('independent_Fresh120',{})
   rows.append(dict(day=day,status=actual.get('status',job['status']),old_equipment=base['comparison_equipment'],new_equipment=c.EQUIPMENT,equipment_equal=base['equipment_equal'],
    baseline_peak_line_percent=100*old['maximum_line_loading_pu'],new_peak_line_percent=100*new['maximum_line_loading_pu'] if new else None,
    peak_improvement_percent=improve('maximum_line_loading_pu'),baseline_mean_slot_peak_line_percent=100*old['mean_slot_maximum_line_loading_pu'],
    new_mean_slot_peak_line_percent=100*new['mean_slot_maximum_line_loading_pu'] if new else None,mean_improvement_percent=improve('mean_slot_maximum_line_loading_pu'),
    Vmin_pu=f.get('voltage_min_pu'),Vmax_pu=f.get('voltage_max_pu'),maximum_transformer_percent=100*f['maximum_transformer_kVA_loading_pu'] if f else None,
    Fresh120_PASS=f.get('PASS'),overall_PASS=audit.get('PASS',False),new_optimization_Native_seconds=native,commit_sha=state['commit_sha']))
   item=dict(day=day,comparison_scope='Descriptive comparison only; strengthened M2 + added iteration + disclosed equipment difference cannot isolate iteration causality',
    baseline=old,new=new,stages=stage_values,original_reused_stages=job.get('reused_original_stages'),new_optimization_Native_seconds=native,
    baseline_AIDC=aidc(store,base['original_case']),new_AIDC=aidc(store,actual['root']) if actual.get('result') and (Path(actual['root'])/'ACTUAL/C1/ACTUAL_EVENT_LEDGERS.json').exists() else None)
   if job.get('M4_freeze'):
    freeze=read(job['M4_freeze']['path']);item['new_MESS']=mess(read(freeze['M4_core']['path'])['MESS_plan'])
   # The original Actual may use the preserved M2 from a different attempt.
   original=store.read(Path(base['original_case'])/'ACTUAL/CASE/CASE_BINDINGS.json');item['baseline_actual_binding']=original
   item['original_reused_native_cost_not_newly_spent']={s:store.read(Path(base[s])/'RESULT.json').get('Native_seconds') for s in ('A1','M1','A2')}
   details.append(item);gc.collect()
 finally:store.close()
 out=c.ROOT/'REPORTS';out.mkdir(exist_ok=True)
 with (out/'DAILY_COMPARISON.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 atomic(out/'DAILY_COMPARISON.json',dict(days=details,summary=rows,exact_dates=31,MESS_units=list(c.FLEET),new_stages=list(c.STAGES),pure_iteration_effect_claimed=False,
  mixed_hardware_dates=[r['day'] for r in rows if not r['equipment_equal']],final_commit_sha=state['commit_sha']))
