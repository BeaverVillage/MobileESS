"""Read only frozen evaluations; no model selection is performed here."""
from experiment import *

def frame_metrics(f):
 y=f.actual_GPUh.to_numpy();q=f.Q90.to_numpy();m=metrics(y,f.Q50,q)
 m.update(positive_coverage=float(np.mean(y[y>0]<=q[y>0])) if (y>0).any() else None,
  burst_coverage=float(np.mean(y[y>BURST]<=q[y>BURST])) if (y>BURST).any() else None)
 return m

def paired(left,right,block):
 keys=['target_day','target_hour'];agg={'actual_GPUh':'first','Q50':'mean','Q90':'mean'}
 require(left.groupby(keys).actual_GPUh.nunique().eq(1).all() and right.groupby(keys).actual_GPUh.nunique().eq(1).all(),'SEED_TARGET_DRIFT')
 a=left.groupby(keys).agg(agg).sort_index();b=right.groupby(keys).agg(agg).sort_index()
 require(a.index.equals(b.index),'BOOTSTRAP_POPULATION_MISMATCH');require(np.array_equal(a.actual_GPUh,b.actual_GPUh),'BOOTSTRAP_LABEL_MISMATCH')
 y=a.actual_GPUh.to_numpy().reshape(-1,24);qa=a.Q90.to_numpy().reshape(-1,24);qb=b.Q90.to_numpy().reshape(-1,24)
 # Average each seed's loss first, avoiding evaluation of an unregistered ensemble.
 def losses(f):
  g=f.copy();err=g.actual_GPUh-g.Q90;g['loss']=np.maximum(.9*err,-.1*err);g['covered']=g.actual_GPUh<=g.Q90
  return g.groupby('target_day')[['loss','covered']].mean().sort_index().to_numpy()
 la,lb=losses(left),losses(right);n=len(y);days=pd.to_datetime(a.index.get_level_values(0).unique())
 segments=np.split(np.arange(n),np.flatnonzero(np.diff(days.values).astype('timedelta64[D]').astype(int)!=1)+1)
 rng=np.random.default_rng(20260926);samples=[]
 for _ in range(2000):
  idx=[]
  for s in segments:
   starts=rng.integers(len(s),size=int(np.ceil(len(s)/block)))
   idx.extend(s[((starts[:,None]+np.arange(block))%len(s)).ravel()[:len(s)]])
  ix=np.array(idx);delta=la[ix].mean(0)-lb[ix].mean(0)
  ratio=(qa[ix].sum()-qb[ix].sum())/y[ix].sum();samples.append([*delta,ratio])
 point=[*(la.mean(0)-lb.mean(0)),(qa.sum()-qb.sum())/y.sum()]
 out=[]
 for k,name in enumerate(['Q90_pinball','Q90_coverage','requirement_ratio']):
  lo,hi=np.quantile(np.asarray(samples)[:,k],[.025,.975]);out.append(dict(metric=name,delta=point[k],CI95_low=lo,CI95_high=hi,block_days=block,draws=2000,N_days=n))
 return out

def main():
 freeze=read('FINAL_SELECTION_FREEZE.json');f=pd.read_parquet(ROOT/'PREDICTIONS.parquet')
 groups=['split','model','policy','cadence','variant','seed'];rows=[];strata=[]
 for key,g in f.groupby(groups):
  ident=dict(zip(groups,key));rows.append(dict(**ident,**frame_metrics(g)))
  for name,v in [('hour',g.target_hour),('lead_band',pd.cut(g.lead_hours,[5,11,17,23,29],labels=['6-11','12-17','18-23','24-29'])),
   ('target_regime',pd.Series(np.select([g.actual_GPUh.eq(0),g.actual_GPUh.gt(BURST)],['zero','burst'],default='positive_body'),index=g.index))]:
   for label in pd.unique(v):strata.append(dict(**ident,stratum=name,value=str(label),**frame_metrics(g.loc[v==label])))
 metricsf=pd.DataFrame(rows);metricsf.to_csv(ROOT/'MODEL_METRICS.csv',index=False);pd.DataFrame(strata).to_csv(ROOT/'STRATIFIED_METRICS.csv',index=False)
 means=metricsf.groupby(groups[:-1]).mean(numeric_only=True).reset_index();means.to_csv(ROOT/'SEED_MEAN_METRICS.csv',index=False)
 ci=[];win=freeze['temporal'];family=freeze['model']
 for split,p in f.groupby('split'):
  current=p[p.model.eq('CURRENT_LGBM')];mono=p[p.model.eq('LGBM')&p.policy.eq(win['policy'])&p.variant.eq('raw')]
  fixed=p[p.model.eq('LGBM')&p.policy.eq('fixed')&p.variant.eq('raw')]
  for (model,policy,cadence,variant),candidate in p[~p.model.eq('CURRENT_LGBM')].groupby(['model','policy','cadence','variant']):
   comparisons=[('vs_PR63_current',current)]
   if model=='LGBM' and variant=='raw':comparisons.append(('temporal_vs_fixed_raw',fixed))
   if policy==win['policy'] and variant=='raw':comparisons.append(('architecture_vs_mono_raw',mono))
   if variant=='causal_calibrated':comparisons.append(('calibration_vs_same_raw',p[p.model.eq(model)&p.policy.eq(policy)&p.cadence.eq(cadence)&p.variant.eq('raw')]))
   for effect,reference in comparisons:
    for block in [1,7]:
     for r in paired(candidate,reference,block):ci.append(dict(split=split,model=model,policy=policy,cadence=cadence,variant=variant,effect=effect,**r))
 cif=pd.DataFrame(ci);cif.to_csv(ROOT/'PAIRED_UNCERTAINTY.csv',index=False)
 selected=means[means.model.eq(family)&means.policy.eq(win['policy'])&means.variant.eq('causal_calibrated')]
 gates=[]
 for _,r in selected.iterrows():
  base=means[means.split.eq(r['split'])&means.model.eq('CURRENT_LGBM')].iloc[0]
  interval=cif[cif.split.eq(r['split'])&cif.model.eq(family)&cif.policy.eq(win['policy'])&cif.variant.eq('causal_calibrated')&cif.effect.eq('vs_PR63_current')&cif.block_days.eq(7)&cif.metric.eq('Q90_pinball')].iloc[0]
  gates.append(dict(split=r['split'],overall=bool(.88<=r.Q90_coverage<=.92),positive=bool(r.positive_coverage>=.85),burst=bool(r.burst_coverage>=.70),
   requirement=bool(r.requirement_ratio<2),target_1_8=bool(r.requirement_ratio<=1.8),preferred_5pct=bool(r.Q90_pinball<=.95*base.Q90_pinball),robust=bool(interval.CI95_high<0)))
 temporal=cif[cif.model.eq('LGBM')&cif.policy.eq(win['policy'])&cif.variant.eq('raw')&cif.effect.eq('temporal_vs_fixed_raw')&cif.block_days.eq(7)&cif.metric.eq('Q90_pinball')]
 robust=all(r['robust'] for r in gates);quality=all(all(r[k] for k in ['overall','positive','burst','requirement']) for r in gates)
 verdict=dict(target_interface_valid=True,temporal_refit_improvement_supported=bool((temporal.CI95_high<0).all()),
  new_model_superior_to_baseline=quality and robust,improvement_statistically_robust=robust,production_replacement_supported=False,optimizer_integration_ready=False,
  quality_gates_pass=quality,gates=gates,selection=freeze['model'],policy=win['policy'],cadence=win['cadence'],calibration=freeze['calibration_window'],
  production_reason='offline exposed historical evidence, ingestion latency unverified, no promotion/integration authorized')
 dump('VERDICT.json',verdict)
 table=selected[['split','Q90_coverage','positive_coverage','burst_coverage','requirement_ratio','Q90_pinball']].to_string(index=False,float_format=lambda v:f'{v:.4f}')
 text=f'''# CC4-v2.1 최종 검토\n\n고정 선택: {family}, {win['policy']}, {win['cadence']}일 refit, {freeze['calibration_window']} residual calibration. 모든 선택은 DEVELOPMENT/CALIBRATION에서 종료했고 evaluation 결과로 재선택하지 않았다.\n\n```text\n{table}\n```\n\n## 판정\n\n'''
 for k in ['target_interface_valid','temporal_refit_improvement_supported','new_model_superior_to_baseline','improvement_statistically_robust','production_replacement_supported','optimizer_integration_ready']:text+=f'- {k}: **{verdict[k]}**\n'
 text+='''\n## 해석과 한계\n\nPR63 target과 population, D−1 18:00 issue, UTC+10 고정 시계 및 기존 평가 날짜를 유지했다. May 예측의 refit에는 해당 시점에 성숙한 Mar–Apr와 이전 May label이 들어갈 수 있지만 May를 선택·튜닝에 쓰지 않았다. feature_available_time <= issue, 전체 하루 target의 label maturity < refit issue를 검사했다. 데이터 ingestion latency는 실제 운영 로그로 인증되지 않았다.\n\nStage A는 동일 LightGBM의 raw 예측, Stage B는 고정 temporal policy의 architecture, Stage C는 동일 예측의 calibration 효과다. 이 효과를 PAIRED_UNCERTAINTY.csv의 effect 열로 분리했다. 1일 paired bootstrap과 연속 날짜 구간을 넘지 않는 circular 7일 block bootstrap을 각각 2,000회 시행했다. neural seed는 독립적인 날짜처럼 부풀리지 않고 날짜별 seed 평균 loss로 계산했다. 다중 비교 후 evaluation winner를 고르지 않았다.\n\nHurdle은 P(W=0)을 포함한 무조건부 quantile 역산을 사용했다. burst expert의 혼합 CDF와 positive quantile 모델에는 알려진 TRAIN threshold만 사용했다. 임의 scaling/capping은 없으며 support와 quantile ordering만 보정했다. Calibration의 시계열 exchangeability 또는 distribution-free coverage는 주장하지 않는다.\n\n모든 history·membership·model artifact는 새 namespace에 저장했다. 기존 frozen evidence, production, optimizer, MESS, IEEE123/8500, Actual/OpenDSS는 변경하거나 실행하지 않았다. 새 모델을 production으로 승격하거나 optimizer에 통합하지 않았다.\n'''
 (ROOT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8');print(json.dumps(verdict,indent=2),flush=True)

if __name__=='__main__':main()
