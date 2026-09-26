"""Frozen evaluation reports and paired issue-day uncertainty; never selects models."""
from experiment import *

def paired(a,b,block):
 cols=['job_issue_id','issue_time','actual_seconds','runtime_seconds','num_gpus_req','Q90']
 m=a[cols].merge(b[['job_issue_id','Q90']],on='job_issue_id',suffixes=('_candidate','_reference'),validate='one_to_one')
 require(len(m)>0 and m.actual_seconds.notna().all(),'PAIRED_POPULATION');days=sorted(m.issue_time.unique());values=[]
 for t,g in m.groupby('issue_time',sort=True):
  y=g.actual_seconds.to_numpy();gpu=g.num_gpus_req.to_numpy();v=[len(g),gpu.sum()]
  for c in ['Q90_candidate','Q90_reference']:
   q=g[c].to_numpy();e=y-q;v += [np.maximum(.9*e,-.1*e).sum(),(y<=q).sum(),((y<=q)*gpu).sum(),
    (gpu*np.maximum(np.minimum(np.ceil(y/900),96)-np.minimum(np.ceil(q/900),96),0)).sum(),(np.maximum(q-y,0)*gpu).sum()/3600]
  values.append(v)
 # Seven observed issue-days, preserving their order across the Apr15 gap.
 # Splitting a five-day segment then drawing seven-day circular blocks would
 # hold that segment's contribution fixed and understate its uncertainty.
 values=np.array(values);n=len(values);segments=[np.arange(n)]
 def summary(v):
  s=v.sum(0);a=s[2:7];b=s[7:12];return np.array([(a[0]-b[0])/s[0],(a[1]-b[1])/s[0],(a[2]-b[2])/s[1],a[3]-b[3],a[4]-b[4]])
 rng=np.random.default_rng(20260926);samples=[]
 for _ in range(2000):
  ix=[]
  for s in segments:
   starts=rng.integers(len(s),size=int(np.ceil(len(s)/block)));ix.extend(s[((starts[:,None]+np.arange(block))%len(s)).ravel()[:len(s)]])
  samples.append(summary(values[ix]))
 point=summary(values);rows=[]
 for k,name in enumerate(['Q90_pinball','coverage','GPU_coverage','missed_GPU_slots','overreserved_GPUh']):
  lo,hi=np.quantile(np.asarray(samples)[:,k],[.025,.975]);rows.append(dict(metric=name,delta=float(point[k]),CI95_low=float(lo),CI95_high=float(hi),block_days=block,draws=2000,N_days=n,N_pairs=len(m),candidate_unmatched=len(a)-len(m),reference_unmatched=len(b)-len(m)))
 return rows

def major(f):
 keys=groupkeys(f);rows=[]
 for c in keys:
  for value,ix in keys.groupby(c).groups.items():
   g=f.loc[ix];m=stats(g);rows.append(dict(stratum=c,value=str(value),major=bool(len(g)>=100 and g.num_gpus_req.sum()>=.01*f.num_gpus_req.sum()),**m))
 return rows

def main():
 f=pd.read_parquet(ROOT/'PREDICTIONS.parquet');freeze=read('FINAL_SELECTION_FREEZE.json');chosen=freeze['model'];rows=[];strata=[]
 for (role,model),g in f.groupby(['role','model']):
  rows.append(dict(role=role,model=model,state='ALL',**stats(g)))
  strata += [dict(role=role,model=model,**r) for r in major(g)]
  for state,d in g.groupby('state'):rows.append(dict(role=role,model=model,state=state,**stats(d)))
  running=g[g.state.eq('RUNNING')];elapsed=running.elapsed_seconds/3600;regime=pd.Series(np.select([elapsed<1,elapsed<2,elapsed<4,elapsed<=8],['<1h','1-2h','2-4h','4-8h'],default='>8h'),index=running.index)
  for value in ['<1h','1-2h','2-4h','4-8h','>8h']:
   d=running[regime==value]
   if len(d):strata.append(dict(role=role,model=model,stratum='elapsed',value=str(value),major=len(d)>=100,**stats(d)))
 metrics=pd.DataFrame(rows);metrics.to_csv(ROOT/'MODEL_METRICS.csv',index=False);strata=pd.DataFrame(strata);strata.to_csv(ROOT/'STRATIFIED_METRICS.csv',index=False)
 comparisons=[];ci=[];pairedmetrics=[]
 for role,d in f.groupby('role'):
  reference='PR31_FROZEN_MOE' if role=='EXPOSED_EVALUATION' else 'PR42_FROZEN_LGBM_NAIVE_REMAINING'
  comparisons += [(role,model,reference,'vs_frozen_production') for model in ['MOE_POOLED','MULTI_QUANTILE','MULTI_QUANTILE_HIERARCHICAL']]
  comparisons += [(role,'MOE_POOLED','MOE_CURRENT_TEMPORAL_GPU_COHORT','temporal_same_GPU_cohort'),
   (role,'MULTI_QUANTILE','MOE_POOLED','architecture_same_policy'),
   (role,'MULTI_QUANTILE_HIERARCHICAL','MULTI_QUANTILE','hierarchical_calibration')]
 for role,model,ref,effect in comparisons:
  a=f[f.role.eq(role)&f.model.eq(model)];b=f[f.role.eq(role)&f.model.eq(ref)];ids_common=set(a.job_issue_id)&set(b.job_issue_id)
  aa=a[a.job_issue_id.isin(ids_common)];bb=b[b.job_issue_id.isin(ids_common)]
  for state in ['ALL','PENDING','RUNNING']:
   sa=aa if state=='ALL' else aa[aa.state.eq(state)];sb=bb if state=='ALL' else bb[bb.state.eq(state)]
   if not len(sa):continue
   ma,mb=stats(sa),stats(sb);reduction=1-ma['missed_GPU_slots']/mb['missed_GPU_slots'] if mb['missed_GPU_slots'] else None
   pairedmetrics.append(dict(role=role,model=model,reference=ref,effect=effect,state=state,missed_slots_reduction=reduction,**ma,
    reference_missed_GPU_slots=mb['missed_GPU_slots'],reference_pinball=mb['pinball']))
   for block in [1,7]:
    for r in paired(sa,sb,block):ci.append(dict(role=role,model=model,reference=ref,effect=effect,state=state,**r))
 cif=pd.DataFrame(ci);cif.to_csv(ROOT/'PAIRED_UNCERTAINTY.csv',index=False);pm=pd.DataFrame(pairedmetrics);pm.to_csv(ROOT/'MATCHED_REFERENCE_METRICS.csv',index=False)
 selected=metrics[metrics.model.eq(chosen)&metrics.state.eq('ALL')];gates=[]
 for _,r in selected.iterrows():
  sub=strata[strata.role.eq(r.role)&strata.model.eq(chosen)&strata.major&strata.stratum.ne('elapsed')]
  match=pm[pm.role.eq(r.role)&pm.model.eq(chosen)&pm.effect.eq('vs_frozen_production')&pm.state.eq('ALL')].iloc[0]
  interval=cif[cif.role.eq(r.role)&cif.model.eq(chosen)&cif.effect.eq('vs_frozen_production')&cif.state.eq('ALL')&cif.block_days.eq(7)&cif.metric.eq('Q90_pinball')].iloc[0]
  gates.append(dict(role=r.role,coverage=bool(.90<=r.Q90_coverage<=.95),GPU_coverage=bool(.90<=r.GPU_coverage<=.95),
   major_groups=bool((sub.Q90_coverage>=.88).all()),long_job=bool(r.long_under<=.15),long_target=bool(r.long_under<=.10),
   missed_slots=bool(pd.notna(match.missed_slots_reduction) and match.missed_slots_reduction>=.5),
   overreserve=bool(r.overreserved_GPUh<r.requested_overreserved_GPUh),robust_pinball=bool(interval.CI95_high<0)))
 temporal=cif[cif.effect.eq('temporal_same_GPU_cohort')&cif.state.eq('ALL')&cif.block_days.eq(7)&cif.metric.eq('Q90_pinball')]
 quality=all(all(r[k] for k in ['coverage','GPU_coverage','major_groups','long_job','missed_slots','overreserve']) for r in gates)
 robust=all(r['robust_pinball'] for r in gates)
 verdict=dict(target_interface_valid=True,target_interface_scope='offline event-time proxy; request-version and ingestion authority UNVERIFIED',
  temporal_refit_improvement_supported=bool((temporal.CI95_high<0).all()),temporal_scope='common positive-GPU cohort only; all-job PR27 production temporal superiority NOT established',
  new_model_superior_to_baseline=quality and robust,improvement_statistically_robust=robust,production_replacement_supported=False,
  optimizer_integration_ready=False,quality_gates_pass=quality,gates=gates,selected=chosen,production_reason='cohort bridge and request provenance unresolved; offline exposed history only')
 dump('VERDICT.json',verdict)
 table=selected[['role','Q90_coverage','GPU_coverage','long_under','missed_GPU_slots','overreserved_GPUh','requested_overreserved_GPUh']].to_string(index=False,float_format=lambda x:f'{x:.4f}')
 text=f'''# Runtime-vNext 최종 검토\n\n선택은 평가 전 {chosen}으로 고정했다. 평가 후 target·feature·hyperparameter·calibration·제외 규칙을 바꾸지 않았다.\n\n```text\n{table}\n```\n\n## 판정\n\n'''
 for k in ['target_interface_valid','temporal_refit_improvement_supported','new_model_superior_to_baseline','improvement_statistically_robust','production_replacement_supported','optimizer_integration_ready']:text+=f'- {k}: **{verdict[k]}**\n'
 text+='''\n## 기준선과 모집단\n\nPR27 MoE는 당시 전체 Job training과 고정 recipe로 245개 예측을 정확히 재현한다. PR42 `ROLLING_Q90_TRACK_P_L2`는 frozen May 31일분을 저장된 예측과 비교한다. 두 기준선은 모델뿐 아니라 학습 모집단도 다르다. 새 temporal/architecture 연구는 raw positive-GPU completed history를 모든 arm에 공통으로 적용한다. 따라서 새 MoE arm을 과거 전체 Job production과 동일하다고 부르지 않으며, 전체 Job production temporal refit 효과는 이 연구로 확정할 수 없다. PR31의 고정 reference는 사전에 정해진 동일 Job-issue 교집합에서만 paired 비교한다. unmatched 수를 숨기지 않는다. May는 최신 production 모델로 동일 feature를 재계산하며 Running에는 total-minus-elapsed라는 명시적인 naive remaining baseline을 사용한다.\n\n## Causality와 Pending/Running\n\n학습은 `job_end_time < issue_time`을 지킨다. 요청 feature는 submit 이후 관측 가능하다는 event-time proxy이며 실제 request 수정 이력 및 historical scheduler snapshot provenance는 미확인이다. 이를 운영 인과성 인증으로 해석할 수 없다. Pending은 total runtime, Running은 elapsed를 입력으로 하는 remaining runtime이다. Running training의 landmark는 Job ID의 고정 hash로만 선택하고, 해당 elapsed까지 살아 있던 완료 Job만 사용한다. 완료 Job만 학습하는 조건에 따른 completion selection bias가 있을 수 있으며 censored-aware survival 성능을 주장하지 않는다.\n\nHierarchical calibration은 충분한 과거 support가 있을 때 hardware → standby/state → requested-walltime bucket → GPU bucket 순으로 세분한다. support가 부족하면 causal parent로 돌아간다. residual은 당시 issue에서 나온 out-of-sample 예측만 사용하고 current issue 전에 완료된 Job만 남긴다. 동일 Job/state는 최신 한 관측만 남겨 support를 부풀리지 않는다. Q50/Q90/Q95/Q99는 모두 추정하되 승격 판단은 Q90 gate로 하며 Q99/UARP로 coverage만 끌어올리지 않는다. 임의 cap/scaling은 없다.\n\n## 통계와 해석\n\n학습기간·architecture·calibration 효과를 PAIRED_UNCERTAINTY.csv의 effect로 분리했다. paired issue-day bootstrap과 관측된 issue-day 순서의 circular 7-issue block bootstrap을 각 2,000회 시행했다. block_days는 관측 issue-day 개수이며 Apr15 누락을 사이에 둔 관측도 순서를 유지한다. 5일짜리 짧은 구간을 따로 circular 7일 resampling하여 그 구간의 기여가 고정되는 문제를 피한다. 오래 남는 Job의 dependence가 7개 issue를 넘을 수 있으므로 CI는 모든 종속성에 대한 보장이 아니다. GPU-weighted coverage는 requested GPU 개수로 가중한다. GPU-slots는 runtime-origin에서 24시간 동안의 predicted-finished/actually-active occupancy proxy이다. optimizer schedule, 실제 dispatch 또는 OpenDSS 결과가 아니다. overreserved GPU·h는 동일 target에 대한 requested-walltime reference와 비교한다.\n\n기존 frozen evidence는 보존했다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS를 수정하거나 실행하지 않았으며 production promotion과 integration을 수행하지 않았다.\n'''
 (ROOT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8');print(json.dumps(verdict,indent=2),flush=True)

if __name__=='__main__':main()
