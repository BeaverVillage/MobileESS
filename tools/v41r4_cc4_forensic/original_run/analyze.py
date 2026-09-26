"""Read-only descriptive audit. No project imports, simulation, solver or model calls."""
import json,hashlib,math
from pathlib import Path
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent
R=OUT/'evidence/V41R4_May2025_raw'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rel(p):return p.relative_to(R).as_posix() if p is not None else 'NOT_AVAILABLE'
def resolve(s):return R/'frozen_artifacts'/s.replace('\\','/').split('/frozen_artifacts/',1)[1]
def save(name,value):
 (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def csv(name,rows):
 df=rows if isinstance(rows,pd.DataFrame) else pd.DataFrame(rows)
 df.to_csv(OUT/name,index=False,encoding='utf-8-sig',na_rep='NOT_AVAILABLE')
def span(segments,lo=120,hi=float('inf')):
 return math.fsum(max(0,min(float(s['end']),hi)-max(float(s['start']),lo)) for s in segments)
def stats(df):
 if len(df)==0:return {'jobs':0,'delayed_jobs':0,'delayed_fraction':None,'total_delay_seconds':None,'mean_delay_seconds':None,'P95_delay_seconds':None,'max_delay_seconds':None,'GPU_weighted_delay_GPU_seconds':None,'GPU_weighted_mean_delay_seconds':None,'remaining_GPUh':None}
 d=df.start_delay_seconds.to_numpy(float);g=df.requested_GPU.to_numpy(float)
 return dict(jobs=len(df),delayed_jobs=int((d>0).sum()),delayed_fraction=float((d>0).mean()),total_delay_seconds=float(d.sum()),mean_delay_seconds=float(d.mean()),P95_delay_seconds=float(np.quantile(d,.95)),max_delay_seconds=float(d.max()),GPU_weighted_delay_GPU_seconds=float((d*g).sum()),GPU_weighted_mean_delay_seconds=float((d*g).sum()/g.sum()),remaining_GPUh=float(df.remaining_GPU_hours_at_H.sum()))
def main():
 idx=read(R/'FINAL_RESULT_INDEX.json');assert len(idx)==124
 windows={};policywindows=[];daily=[];joblinks=[];incominglinks=[];migrationrows=[];sources=[];checks=[]
 refs={};seen_contrib={}; allstats={};delayexamples=[]
 for entry in idx:
  day,policy=entry['day'],entry['policy'];joint=resolve(entry['accepted_joint_original_path']);da=joint.parent
  assert hashlib.sha256(joint.read_bytes()).hexdigest()==entry['accepted_joint_sha256']
  frozen=read(joint);decision=frozen['decision'];jobs=decision['AIDC_decision']
  common=R/entry['final_actual'].replace('/replays/','/common_inputs/')
  ready=read(common/'READY.json');assert ready['decision_SHA']==frozen['decision_SHA']
  replay=read(common/'ACTUAL_JOB_REPLAY.json');ledger=replay['job_ledger'];kpi=read(common/'ACTUAL_EXECUTION_DELAY_KPIS.json')
  assert {j['job_uid'] for j in jobs}=={j['job_uid'] for j in ledger}
  assert replay['counters']['Actual_optimizer_calls']==ready['scheduling_optimizer_calls']==0
  original_da=R/f'frozen_artifacts/v41r4_may/loop_wall_v4/{day}/{policy}/dayahead'
  prediction=original_da/'ml/H4_WINDOW_PREDICTIONS.parquet';pred=pd.read_parquet(prediction)
  snapshot=read(original_da/'ml/ML_SNAPSHOT.json')
  scorepath=common/'H4_SCORE.json';score=read(scorepath);assert score['future_scheduling_calls']==0
  h=np.array(score['realized_H4_GPUh']);reserve=pred.ACTIONABLE_H4_GPUh.to_numpy();error=h-reserve
  # Final selected schedule headroom; score headroom can be historical/reporting-only.
  plan=read(da/'PLANNING_RESULT.json');a=np.array(plan['reserve']['H_available_GPUh']);xi=np.array(plan['reserve']['xi_GPUh'])
  assert np.allclose(xi,np.maximum(reserve-a,0),atol=1e-8,rtol=0)
  opt=da/'H4_OPTIMIZER_WINDOWS.parquet'
  if opt.exists():
   o=pd.read_parquet(opt);assert np.allclose(o.available_headroom_GPUh,a,atol=1e-8,rtol=0)
  begin=pd.Timestamp(pred.window_start.iloc[0]);end=pd.Timestamp(pred.window_end.iloc[-1]);issue=begin-pd.Timedelta(hours=6)
  assert len(pred)==len(h)==81 and end-begin==pd.Timedelta(days=1)
  contributors=common.parent/'workload/REALIZED_WORKLOAD_CONTRIBUTORS.parquet'
  if not contributors.exists():
   candidates=list((R/f'frozen_artifacts/v41r4_may/loop_wall_v4/{day}').glob('*/actual/authority/ACTUAL_WORKLOAD_CONTRIBUTORS.parquet'))
   contributors=sorted(candidates)[0] if candidates else None
  cf=pd.read_parquet(contributors) if contributors else pd.DataFrame(columns=['id','submit_time','start_time','end_time','gpus_requested','GPU_service_GPUh'])
  cf['id']=cf.id.astype(str);cf['submit_time']=pd.to_datetime(cf.submit_time,utc=True)
  assert cf.id.is_unique and cf.submit_time.ge(begin).all() and cf.submit_time.lt(end).all()
  derived=cf.gpus_requested.astype(float)*(pd.to_datetime(cf.end_time,utc=True)-pd.to_datetime(cf.start_time,utc=True)).dt.total_seconds()/3600
  assert np.allclose(cf.GPU_service_GPUh.astype(float),derived,atol=1e-9,rtol=0)
  slots=((cf.submit_time-begin).dt.total_seconds()//900).astype(int)
  atomic=np.bincount(slots,weights=derived,minlength=96);rebuilt=np.lib.stride_tricks.sliding_window_view(atomic,16).sum(axis=1)
  if contributors:assert np.allclose(h,rebuilt,atol=1e-8,rtol=0)
  incoming_ids=set(cf.id);execution_ids={x['job_uid'] for x in ledger}
  overlap=incoming_ids&execution_ids;assert not overlap,(day,policy,overlap)
  assert all(pd.Timestamp(j['submit_time'])<=issue for j in ledger)
  if day not in windows:
   windows[day]=[dict(day=day,window_index=k,window_start=pd.Timestamp(pred.window_start.iloc[k]).isoformat(),window_end=pd.Timestamp(pred.window_end.iloc[k]).isoformat(),R_k_GPUh=float(reserve[k]),H_actual_GPUh=float(h[k]),forecast_miss_GPUh=float(error[k]),positive_miss_GPUh=float(max(error[k],0)),miss_flag=bool(error[k]>0),physical_cap_bound=bool(pred.phys_cap_binding.iloc[k]),historical_cap_bound=bool(pred.hist_cap_binding.iloc[k]),raw_forecast_GPUh=float(pred.RAW_R85_B2_GPUh.iloc[k]),physical_cap_GPUh=float(pred.PHYS_CAP_GPUh.iloc[k]),historical_cap_GPUh=float(pred.HIST_CAP_GPUh.iloc[k]),incoming_jobs=int(((slots>=k)&(slots<k+16)).sum()),H_source=rel(scorepath),R_source=rel(prediction),contributors_source=rel(contributors)) for k in range(81)]
   seen_contrib[day]=len(cf)
   if contributors is None:
    for w in windows[day]:w['incoming_jobs']=None
  else:
   assert np.array_equal(h,np.array([w['H_actual_GPUh'] for w in windows[day]]))
   assert np.array_equal(reserve,np.array([w['R_k_GPUh'] for w in windows[day]]))
  if policy=='B0':refs[day]={j['job_uid']:j for j in jobs}
  selected=[j for j in ledger if j['frozen_policy_admitted']]
  rows=[]
  for j in ledger:
   uid=j['job_uid'];sel=bool(j['frozen_policy_admitted']);g=float(j['requested_GPU'])
   # Existing fields are service remaining, not elapsed wall-clock until completion.
   row=dict(day=day,policy=policy,population='FROZEN_ISSUE_KNOWN_JOB',job_uid=uid,submit_time=j['submit_time'],canonical_window=None,window_miss_flag=None,window_miss_GPUh=None,planned_start=j['DA_PLANNED_START'],actual_start=j['ACTUAL_EXECUTION_START'],actual_end=j['ACTUAL_EXECUTION_END'],start_delay_seconds=float(j['START_DELAY_SECONDS']),requested_GPU=g,realized_runtime_seconds=j['REALIZED_RUNTIME_SECONDS'],delay_reason=j['DELAY_REASON'],blocking_job_ids=json.dumps(j['BLOCKING_JOB_IDS']),unfinished_at_H=j.get('unfinished_at_H'),remaining_GPU_hours_at_H=j.get('remaining_GPU_hours_at_H'),frozen_policy_admitted=sel,explicitly_replayed=sel,mapping_status='SUBMITTED_BEFORE_ISSUE_OUTSIDE_ALL_H4_WINDOWS',state_at_issue=j['state_at_issue'],migration_selected=bool(j.get('migration_selected')),contention_added_completion_lateness_seconds=j['contention_added_completion_lateness_seconds'],runtime_prediction_seconds=j['safe_duration_seconds'],observed_full_runtime_seconds=j['actual_runtime_seconds'],source=rel(common/'ACTUAL_JOB_REPLAY.json'))
   row['wait_overlaps_any_miss_window']=False
   if sel and j['START_DELAY_SECONDS']>0:
    b=pd.Timestamp(j['DA_PLANNED_START']);e=pd.Timestamp(j['ACTUAL_EXECUTION_START'])
    row['wait_overlaps_any_miss_window']=any(error[k]>0 and b<pd.Timestamp(pred.window_end.iloc[k]) and e>pd.Timestamp(pred.window_start.iloc[k]) for k in range(81))
    assert j['DELAY_REASON']=='RESOURCE_CONTENTION_FROM_RUNTIME_OVERRUN'
    if len(delayexamples)<12 and policy in ('B1','B3'):
     byid={x['job_uid']:x for x in ledger}
     delayexamples.append(dict(day=day,policy=policy,job_uid=uid,delay_seconds=j['START_DELAY_SECONDS'],source=row['source'],blockers=[dict(job_uid=u,state=byid[u]['state_at_issue'],predicted_seconds=byid[u]['safe_duration_seconds'],observed_runtime_seconds=byid[u]['actual_runtime_seconds'],actual_service_seconds=byid[u]['actual_service_seconds']) for u in j['BLOCKING_JOB_IDS']]))
   rows.append(row)
   if policy in ('B1','B3'):joblinks.append(row)
   if j.get('migration_selected'):
    ev=j.get('actual_migration_execution',{});parts=j['actual_compute_segments']
    gap=0 if len(parts)<2 else (parts[1]['start']-parts[0]['end'])*900
    migrationrows.append(dict(day=day,policy=policy,job_uid=uid,requested_GPU=g,migration_executed=bool(j.get('migration_executed')),interruption_seconds=gap,interruption_GPUh=gap*g/3600,WAN_queue_seconds=ev.get('WAN_QUEUE_DELAY_SECONDS'),restart_GPU_queue_seconds=ev.get('RESTART_GPU_QUEUE_DELAY_SECONDS'),migration_clock_shift_seconds=ev.get('TOTAL_MIGRATION_DELAY_SECONDS'),remaining_GPU_hours_at_H=j.get('remaining_GPU_hours_at_H'),source=row['source']))
  frame=pd.DataFrame(rows);sf=frame[frame.frozen_policy_admitted]
  st=stats(sf);assert st['delayed_jobs']==kpi['delayed_jobs'] and abs(st['total_delay_seconds']-kpi['total_start_delay_seconds'])<1e-6
  assert abs(st['mean_delay_seconds']-kpi['mean_start_delay_seconds'])<1e-6
  planned_extra=0.;affected=0
  for job in jobs:
   ref=refs[day][job['job_uid']];delta=(span(job['compute_segments'])-span(ref['compute_segments']))*job['requested_GPU']/4
   if delta>1e-9:
    assert job.get('migration_selected'),(day,policy,job['job_uid'])
    planned_extra+=delta;affected+=1
  dayrow=dict(day=day,policy=policy,cc4_miss_windows=int((error>0).sum()),cc4_mean_positive_part_GPUh=float(np.maximum(error,0).mean()),cc4_max_miss_GPUh=float(np.maximum(error,0).max()),planned_xi_positive_windows=int((xi>1e-8).sum()),mean_planned_xi_GPUh=float(xi.mean()),max_planned_xi_GPUh=float(xi.max()),realized_H_exceeds_A_windows=int((h>a).sum()),incoming_jobs=len(cf),incoming_replay_ID_overlap=len(overlap),**st,unfinished_selected_jobs=int(sf.unfinished_at_H.sum()),delayed_jobs_waiting_during_any_miss_window=int(sf.wait_overlaps_any_miss_window.sum()),contention_added_completion_lateness_seconds=float(sf.contention_added_completion_lateness_seconds.sum()),planned_migration_extra_postH_GPUh=planned_extra,planned_migration_extra_postH_jobs=affected,unselected_jobs=len(ledger)-len(selected),unselected_backlog_GPUh=float(frame.loc[~frame.frozen_policy_admitted,'remaining_GPU_hours_at_H'].sum()),score_headroom_max_difference_from_final_DA=float(np.max(np.abs(np.array(score['frozen_headroom_GPUh'])-a))),joint_source=rel(joint),replay_source=rel(common/'ACTUAL_JOB_REPLAY.json'),h4_score_source=rel(scorepath),planning_source=rel(da/'PLANNING_RESULT.json'),contributors_source=rel(contributors))
  if contributors is None:
   dayrow['incoming_jobs']=None;dayrow['incoming_replay_ID_overlap']=None
  daily.append(dayrow);allstats[day,policy]=sf
  if policy in ('B1','B3'):
   for k,w in enumerate(windows[day]):
    w[f'A_k_{policy}_GPUh']=float(a[k]);w[f'xi_k_{policy}_GPUh']=float(xi[k]);w[f'{policy}_planning_source']=rel(da/'PLANNING_RESULT.json')
    w[f'{policy}_replayed_incoming_jobs']=0
    waiting=sf[(sf.start_delay_seconds>0)&(pd.to_datetime(sf.planned_start,utc=True)<pd.Timestamp(w['window_end']))&(pd.to_datetime(sf.actual_start,utc=True)>pd.Timestamp(w['window_start']))]
    policywindows.append(dict(day=day,policy=policy,window_index=k,miss_flag=bool(error[k]>0),A_k_GPUh=float(a[k]),xi_k_GPUh=float(xi[k]),realized_headroom_excess_GPUh=float(max(h[k]-a[k],0)),incoming_jobs=w['incoming_jobs'],incoming_jobs_explicitly_replayed=0,incoming_delayed_jobs=None,incoming_mean_delay_seconds=None,incoming_P95_delay_seconds=None,incoming_GPU_weighted_delay=None,incoming_unfinished_GPUh=None,known_jobs_wait_interval_overlap_count=len(waiting),known_jobs_overlap_total_full_start_delay_seconds=float(waiting.start_delay_seconds.sum()),known_jobs_overlap_mean_full_start_delay_seconds=float(waiting.start_delay_seconds.mean()) if len(waiting) else None,known_jobs_overlap_max_full_start_delay_seconds=float(waiting.start_delay_seconds.max()) if len(waiting) else None,known_jobs_overlap_GPU_weighted_full_delay_GPU_seconds=float((waiting.start_delay_seconds*waiting.requested_GPU).sum()),interpretation='Incoming outcome NOT_IDENTIFIABLE; known-job wait overlap is descriptive only and overlaps windows',replay_source=rel(common/'ACTUAL_JOB_REPLAY.json')))
   for (_,j),slot in zip(cf.iterrows(),slots):
    k=min(int(slot),80);w=windows[day][k]
    covering=[q for q in range(max(0,int(slot)-15),min(int(slot),80)+1)]
    incominglinks.append(dict(day=day,policy=policy,population='FUTURE_ARRIVAL_LABEL_ONLY',job_uid=j.id,submit_time=j.submit_time.isoformat(),canonical_window=k,window_miss_flag=w['miss_flag'],window_miss_GPUh=w['forecast_miss_GPUh'],planned_start=None,actual_start=None,actual_end=None,start_delay_seconds=None,requested_GPU=j.gpus_requested,realized_runtime_seconds=(pd.Timestamp(j.end_time)-pd.Timestamp(j.start_time)).total_seconds(),delay_reason=None,blocking_job_ids=None,unfinished_at_H=None,remaining_GPU_hours_at_H=None,frozen_policy_admitted=None,explicitly_replayed=False,mapping_status='NO_JOB_ID_IN_SAME_DAY_REPLAY',any_covering_window_miss=any(error[q]>0 for q in covering),observed_trace_start=pd.Timestamp(j.start_time).isoformat(),observed_trace_end=pd.Timestamp(j.end_time).isoformat(),observed_trace_submit_to_start_seconds=(pd.Timestamp(j.start_time)-j.submit_time).total_seconds(),source=rel(contributors)))
  sources.append(dict(day=day,policy=policy,final_actual=entry['final_actual'],common_inputs=rel(common),joint=rel(joint),joint_sha256=entry['accepted_joint_sha256'],decision_SHA=frozen['decision_SHA'],incoming_ID_overlap=0 if contributors else None,future_scheduling_calls=score['future_scheduling_calls'],Actual_optimizer_calls=replay['counters']['Actual_optimizer_calls']))
  print(day,policy,'miss',int((error>0).sum()),'delayed',st['delayed_jobs'],flush=True)
 wf=pd.DataFrame([w for day in sorted(windows) for w in windows[day]]);df=pd.DataFrame(daily);inc=pd.DataFrame(incominglinks)
 assert len(wf)==2511 and len(df)==124
 positive=wf.loc[wf.miss_flag,'positive_miss_GPUh']
 policy_stats={}
 for policy in ('B0','B1','B2','B3'):
  f=pd.concat([v for (d,p),v in allstats.items() if p==policy],ignore_index=True);d=df[df.policy==policy];ms=pd.DataFrame([x for x in migrationrows if x['policy']==policy])
  ps=dict(**stats(f),unique_job_ids=int(f.job_uid.nunique()),days_with_delay=int((d.delayed_jobs>0).sum()),days_with_miss_and_any_delay=int(((d.delayed_jobs>0)&(d.cc4_miss_windows>0)).sum()),mean_xi_GPUh=float(d.mean_planned_xi_GPUh.mean()),positive_xi_windows=int(d.planned_xi_positive_windows.sum()),max_xi_GPUh=float(d.max_planned_xi_GPUh.max()),H_exceeds_A_windows=int(d.realized_H_exceeds_A_windows.sum()),unfinished_selected_job_days=int(d.unfinished_selected_jobs.sum()),planned_migration_extra_postH_GPUh=float(d.planned_migration_extra_postH_GPUh.sum()),planned_migration_extra_postH_jobs=int(d.planned_migration_extra_postH_jobs.sum()),contention_added_completion_lateness_seconds=float(d.contention_added_completion_lateness_seconds.sum()),wait_overlapping_any_miss_job_days=int(f.wait_overlaps_any_miss_window.sum()),score_headroom_mismatch_days=int((d.score_headroom_max_difference_from_final_DA>1e-8).sum()),daily_miss_severity_vs_total_delay_pearson=float(d.cc4_mean_positive_part_GPUh.corr(d.total_delay_seconds)),daily_miss_severity_vs_total_delay_spearman=float(d.cc4_mean_positive_part_GPUh.corr(d.total_delay_seconds,method='spearman')))
  if len(ms):ps['migration']=dict(selected_job_days=len(ms),executed_job_days=int(ms.migration_executed.sum()),total_interruption_GPUh=float(ms.interruption_GPUh.sum()),WAN_queue_job_seconds=float(ms.WAN_queue_seconds.sum()),restart_GPU_queue_job_seconds=float(ms.restart_GPU_queue_seconds.sum()),migration_clock_shift_job_seconds=float(ms.migration_clock_shift_seconds.sum()))
  policy_stats[policy]=ps
 group={}
 for policy in ('B1','B3'):
  group[policy]={}
  for label,flag in [('M',True),('C',False)]:
   f=inc[(inc.policy==policy)&(inc.window_miss_flag==flag)]
   group[policy][label]=dict(incoming_jobs=len(f),replayed_incoming_jobs=0,delayed_jobs=None,delayed_fraction=None,mean_start_delay_seconds=None,P95_start_delay_seconds=None,GPU_weighted_delay=None,unfinished_post_horizon_GPUh=None,status='NOT_IDENTIFIABLE_NO_FUTURE_ARRIVALS_IN_REPLAY')
 summary=dict(cc4_miss_windows=int(wf.miss_flag.sum()),cc4_total_windows=len(wf),cc4_miss_rate=float(wf.miss_flag.mean()),actionable_coverage_recomputed=float((~wf.miss_flag).mean()),actionable_coverage_percent=float((~wf.miss_flag).mean()*100),matches_81_44_percent_after_rounding=round(float((~wf.miss_flag).mean()*100),2)==81.44,positive_miss_GPUh=dict(mean=float(positive.mean()),median=float(positive.median()),P90=float(positive.quantile(.9)),max=float(positive.max())),physical_cap_bound_windows=int(wf.physical_cap_bound.sum()),historical_cap_bound_windows=int(wf.historical_cap_bound.sum()),miss_windows_with_physical_cap=int((wf.miss_flag&wf.physical_cap_bound).sum()),raw_forecast_miss_windows=int((wf.H_actual_GPUh>wf.raw_forecast_GPUh).sum()),jobs_mapped_to_miss_windows=int(len(inc[(inc.policy=='B1')&inc.window_miss_flag])),jobs_mapped_to_miss_windows_unit='unique day-job arrivals, canonical latest covering window; counted once across policies',incoming_jobs=sum(seen_contrib.values()),incoming_jobs_explicitly_replayed=0,delayed_jobs_in_miss_windows=None,delayed_jobs_in_nonmiss_windows=None,mean_delay_miss_seconds=None,mean_delay_nonmiss_seconds=None,cc4_miss_caused_delay='NOT_IDENTIFIABLE',online_cc4_recourse_exists='NO',actual_delay_mechanism='RESOURCE_CONTENTION_FROM_RUNTIME_OVERRUN; migration/WAN/restart interruption separately recorded',future_arrival_jobs_explicitly_replayed='NO',question_A='NOT_IDENTIFIABLE',question_B='NOT_IDENTIFIABLE',question_C='NO',question_D='RESOURCE_CONTENTION_FROM_RUNTIME_OVERRUN',question_E='Future arrivals are label-only; frozen issue-known jobs are explicitly replayed',policy_statistics=policy_stats,canonical_incoming_groups=group,overlap_note='No window independence assumption or causal test. Day-policy aggregation; jobs may repeat across independent days. GPUh sums over windows are not distinct workload mass.',null_meaning='NOT_IDENTIFIABLE, not zero delay',source_map='CC4_EVIDENCE_SOURCE_MAP.json',final_interpretation='CC4 undercoverage exists, but incoming jobs underlying H4 are absent from same-day execution. Existing frozen jobs have deterministic capacity-contention delays; neither zero incoming delay nor a causal CC4 effect can be inferred. Migration service deferral is separately quantified.')
 summary['incoming_jobs_with_archived_contributor_rows']=summary['incoming_jobs'];summary['incoming_jobs']=None
 summary['missing_contributor_days']=['2025-05-21'];summary['job_mapping_population']='30 days with contributor rows; May 21 missing, never treated as zero incoming jobs'
 csv('CC4_HEADROOM_MISS_WINDOWS.csv',wf);csv('CC4_MISS_JOB_DELAY_LINK.csv',pd.DataFrame(joblinks+incominglinks))
 csv('CC4_DAY_POLICY_AGGREGATION.csv',df);csv('CC4_WINDOW_POLICY_DELAY_DIAGNOSTICS.csv',policywindows);csv('CC4_MIGRATION_DELAY_SEPARATION.csv',migrationrows)
 csv('CC4_TOP10_MISS_WINDOWS.csv',wf.sort_values(['positive_miss_GPUh','day','window_index'],ascending=[False,True,True]).head(10))
 save('CC4_HEADROOM_MISS_DELAY_SUMMARY.json',summary);save('CC4_EVIDENCE_SOURCE_MAP.json',sources);save('CC4_DELAY_BLOCKER_EXAMPLES.json',delayexamples)
 save('ANALYSIS_VALIDATION.json',dict(status='PASS_WITH_MISSING_2025_05_21_CONTRIBUTOR_TABLE',windows=2511,policy_days=124,all_joint_hashes_match=True,all_ready_decision_SHA_match=True,H_reconstructed_from_contributors_days=30,H_score_only_days=['2025-05-21'],all_policy_H_and_R_equal=True,all_replay_ID_sets_equal_frozen_job_ID_sets=True,all_replay_submit_times_at_or_before_issue=True,all_available_incoming_ID_intersections_empty=True,all_delay_KPI_counts_totals_means_reconciled=True,all_xi_equals_positive_R_minus_A=True,no_project_imports_or_replay_execution=True))
 print(json.dumps(summary,ensure_ascii=True,indent=2))
if __name__=='__main__':main()
