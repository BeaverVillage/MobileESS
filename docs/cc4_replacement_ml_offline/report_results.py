import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import json,hashlib,math
import numpy as np,pandas as pd
from prepare_data import OUT,BASE,R5,R6,sha,dump
KEYS=['model','seed','training_mode','horizon_hours','role']
def mdtable(df):
 def fmt(x):
  if isinstance(x,(float,np.floating)):return f'{x:.5g}'
  return str(x).replace('|','/')
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(fmt(x) for x in row)+' |' for row in df.itertuples(index=False,name=None))
def pb(y,q,t=.9):
 e=y-q;return np.maximum(t*e,(t-1)*e)
def safe_mean(v):return float(np.mean(v)) if len(v) else None
def metrics(g):
 y=g.target_GPUh.to_numpy();q50=g.q50.to_numpy();raw=g.raw_q90.to_numpy();q=g.calibrated_q90.to_numpy();p=y>0;b=y>=g.burst_threshold.iloc[0];under=np.maximum(y-q,0);over=np.maximum(q-y,0)
 return {'N_days':g.day.nunique(),'N_windows':len(g),'N_positive':int(p.sum()),'N_zero':int((y==0).sum()),'Q50_MAE':float(abs(y-q50).mean()),'Q50_WAPE':float(abs(y-q50).sum()/y.sum()) if y.sum()>0 else None,
 'unrepaired_raw_Q90_pinball':float(pb(y,g.raw_q90_unrepaired.to_numpy()).mean()) if 'raw_q90_unrepaired' in g else None,'unrepaired_raw_coverage':float((y<=g.raw_q90_unrepaired).mean()) if 'raw_q90_unrepaired' in g else None,'raw_crossing_fraction':float((g.raw_q50_unclipped>g.raw_q90_unrepaired).mean()) if 'raw_q90_unrepaired' in g else None,
 'raw_Q90_pinball':float(pb(y,raw).mean()),'calibrated_Q90_pinball':float(pb(y,q).mean()),'raw_coverage':float((y<=raw).mean()),'calibrated_coverage':float((y<=q).mean()),'positive_coverage':safe_mean((y<=q)[p]),'zero_coverage':safe_mean((y<=q)[~p]),'burst_threshold':g.burst_threshold.iloc[0],'N_burst':int(b.sum()),'burst_coverage':safe_mean((y<=q)[b]),'burst_mean_miss_GPUh':safe_mean(under[b]),'burst_P90_miss_GPUh':float(np.quantile(under[b],.9)) if b.any() else None,'mean_underprediction_GPUh':under.mean(),'P90_underprediction_GPUh':float(np.quantile(under,.9)),'mean_overprediction_GPUh':over.mean(),'P90_overprediction_GPUh':float(np.quantile(over,.9)),'mean_forecast_requirement':q.mean(),'mean_raw_requirement':raw.mean(),'actionable_coverage':float((y<=g.actionable).mean()),'cap_activation':float((q>g.actionable).mean()),'physical_cap_activation':float((q>g.physical_cap).mean()),'historical_cap_activation':float((q>g.historical_cap).mean()),'physical_oracle_coverage':float((y<=g.physical_cap).mean()),'log_space_Q90_pinball':float(pb(np.log1p(y),np.log1p(q)).mean()),'actual_secured_reserve':'NOT_RUN','calibration_days_min':int(g.calibration_N_days.min())}
def old_reports():
 old=OUT/'history/D/dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml';rows=[];summary=[]
 for name in ['TFT','DEEPAR','NHITS','CMABF']:
  r=json.loads((old/f'fits/{name}/result.json').read_text(encoding='utf-8'));s=r['selected_trial'];h=s['history']
  summary.append({'model':name,'lr':s['learning_rate'],'selected_epoch':s['selected_epoch'],'epochs_run':s['epochs_run'],'first_train_loss':h[0]['train_loss'],'last_train_loss':h[-1]['train_loss'],'first_development_primary':h[0]['development_primary'],'last_development_primary':h[-1]['development_primary']})
  for trial in r['trials']:
   rows.extend([dict(model=name,trial=trial['trial_id'],lr=trial['learning_rate'],**v) for v in trial['history']])
 pd.DataFrame(rows).to_csv(OUT/'PREVIOUS_TRAINING_CURVES.csv',index=False);dump('PREVIOUS_TRAINING_DIAGNOSIS.json',summary)
 table=mdtable(pd.DataFrame(summary))
 text=f'''# 이전 신경망 실패 진단

과거 판정은 수정하지 않았다. R6는 `V40R6_MULTI_HORIZON_GPUWORK_SAFETY_FAIL`, R6R1은 `V40R6R1_JOINT_GPUWORK_RESERVE_FAIL`, 선택 NONE 및 NO_MODEL_PROMOTED를 그대로 보존한다. 원본 보고서는 history/B, history/C, history/D에 고정 commit별로 저장했다.

{table}

근거: R3 `train.py:fit_neural_once`, `neural.py:neural_loss`, `library_batch`, 각 fits/*/result.json의 전체 history. 두 learning-rate trial의 곡선은 PREVIOUS_TRAINING_CURVES.csv에 저장했다.

TFT/DeepAR/CMABF의 epoch 1 선택은 실제 기록이다. 학습 손실 하락과 development 양수-target Q90 점수 악화가 함께 나타난다. 이는 일반화 악화와 일치하지만, 이것만으로 실제 과적합과 시간적 분포변화를 분리할 수는 없다. 과거에는 TRAIN 양수 Q95로 선형 스케일링했다. TFT/NHiTS는 전체 표본의 Q50/Q90 pinball 평균을 학습하면서 양수 표본의 Q90 점수만으로 조기종료했다. DeepAR는 Gaussian NLL, CMABF는 발생 BCE·분위수·양수분위수·burst 혼합 손실을 사용했다. 따라서 학습 목적과 조기종료 목적이 다르며, zero-heavy 자료에서 epoch 1의 높은 예측이 양수 지표에 유리할 가능성이 있다. 이는 코드와 곡선에 근거한 원인 후보이며 단일 원인 확정은 아니다.

과거 maturity mask는 history_values에서 관측 END/구간 종료 경계를 적용하고, library_batch에서 미성숙 GPUh를 다시 0 placeholder로 가렸다. 이 0은 mask와 함께 전달되며 GPU 결측값 대체가 아니다. DeepAR 학습의 teacher forcing은 생성 likelihood 계산용 shifted target이며, 추론에서는 y 없이 autoregressive 경로를 생성한다. 코드 검토에서 미래 target을 추론 입력으로 넣는 경로는 발견하지 못했다. 6시간 lead는 미래 calendar/lead covariate로 표시되지만 별도 bridge decoder를 학습하지 않은 구조적 한계는 있다.

과거 학습은 비유한 loss를 검사하고 gradient norm 1로 clip했다. gradient의 전후 norm 및 비유한 gradient 통계는 기록되어 있지 않으므로 비정상 gradient가 없었다고 소급 확정할 수 없다. best epoch 1만으로 epoch 수를 늘릴 근거도 없다.

이번 TFT는 16 hidden의 소형 TFT 기반 구현(변수선택, gated residual, LSTM, causal attention)이며 원본 라이브러리 TFT의 재현이라고 부르지 않는다. 전체 window 원단위 pinball(0.2 Q50 + 0.8 Q90), log1p 출력, TRAIN 분위수 초기화를 사용한다. 이번 DeepAR 기반 구현은 전체 H4 합계 target을 직접 autoregressive 예측하고, 0 질량을 분리한 hurdle lognormal likelihood를 사용한다. 양수 log-target 정규화는 TRAIN으로만 추정한다. DeepAR의 NLL와 Q90 조기종료 목적 차이는 여전히 남아 있고 명시한다. 두 모델 모두 raw 336×8 과거 sequence와 동일 71개 window 특징을 사용하므로 LightGBM의 요약 특징보다 표현 형태가 풍부하다. 정보원과 성숙 경계는 같지만 순수 파라미터화만 바꾼 ablation은 아니다.

이번의 실제 gradient norm, 학습/검증 곡선, checkpoint SHA, seed, 시간, GPU peak는 fits/*/receipt.json에 저장했다. 과거 30분 target 실험과 이번 H4 직접 합계 예측 실험의 수치를 동일 표본의 개선율로 비교하지 않는다.
'''
 (OUT/'PREVIOUS_FAILURE_DIAGNOSIS_KO.md').write_text(text,encoding='utf-8')
def original_report():
 r=json.loads((OUT/'FROZEN_REPRODUCTION.json').read_text(encoding='utf-8'));line=json.loads((OUT/'SOURCE_AND_MODEL_LINEAGE.json').read_text(encoding='utf-8'));periods=pd.read_csv(OUT/'ORIGINAL_TRAINING_PERIODS.csv');a=np.load(OUT/'DATA.npz');f=pd.read_csv(BASE/'CC4_PHYSICAL_CAP_ORACLE_20260923/CC4_ALL_MAY_WINDOWS.csv');ids=[list(a['days']).index(d) for d in f.date.unique()];err=float(abs(a['y4'][ids].ravel()-f.Y_k_GPUh.to_numpy()).max());assert err<1e-7
 # Reconstruct original exact row identifiers, not merely dates/counts.
 target=pd.read_parquet(R6/'V40R6_CUMULATIVE_TARGET.parquet');ledger=pd.read_parquet(OUT/'DAY_LEDGER.parquet');av=np.maximum(pd.to_datetime(ledger.target_end,utc=True).astype('int64'),pd.to_datetime(ledger.target_label_available_at,utc=True).astype('int64')).to_numpy();memberships=[]
 orig_ids=[]
 for fn in ['development_baselines.npz','calibration_predictions.npz','exposed_predictions.npz']:orig_ids.extend(np.load(R6/fn)['row_ids'].tolist())
 t=target.iloc[orig_ids];t=t[t.horizon=='H4'];lut={str(d):i for i,d in enumerate(a['days'])}
 for row in line['May_snapshots']:
  s=json.loads(Path(row['path']).read_text(encoding='utf-8'));issue=pd.Timestamp(s['issue_time']).value
  keys=[f'R6:{v.row_id}' for v in t.itertuples() if av[lut[v.day]]<issue]
  for i,d in enumerate(a['days']):
   if str(d)>='2025-02-27' and av[i]<issue:keys.extend(f'V41:{d}:{k}' for k in range(81))
  digest=hashlib.sha256(('\n'.join(sorted(keys))+'\n').encode()).hexdigest();assert digest==s['H4_calibration_support']['membership_sha256'];memberships.append({'day':row['day'],'membership_sha256':digest,'match':True,'N':len(keys)})
 dump('FROZEN_MEMBERSHIP_REPRODUCTION.json',memberships)
 text=f'''# 기존 CC4 재현 결과

검증 PASS. 지정 GitHub PR #42/#33/#34 및 네 고정 commit을 GitHub API로 확인했다. PR은 배경 참조이며 수정하지 않았다. 고정 commit의 파일은 로컬 Git object에서 독립 경로로 추출했다. GitHub source와 로컬 production source 7개 파일의 SHA 비교는 SOURCE_AND_MODEL_LINEAGE.json에 저장했다.

원본 CC4는 R6 L0 H4 LightGBM Q50/Q90이다. log1p(target_GPUh), num_leaves=15, learning_rate=0.03, n_estimators=400, min_child_samples=50, seed=20260907, CPU threads=1. H4 81 window/day × 167일 = 13,527 학습 row이며 random window split이 없다. 원본 feature ordering 71개는 history/B/.../V40R6_FEATURE_CONTRACT.json에서 읽어 byte hash를 연결했다. 과거 제출 수, 성숙한 GPUh/mask/age의 6시간·24시간·7일 요약, 마지막 상태, deterministic calendar/lead, 7/14/21/28일 15분 계절 특징과 H4 누적 계절합이다. GPU 요청·runtime의 미래 실현값은 predictor에 들어가지 않는다.

{mdtable(periods)}

범위 표기와 실제 적격 membership가 다르다. 예를 들어 TRAIN 8월 29/30일은 미성숙으로 제외되므로 마지막 적격일은 8월 28일이다. 개발/보정도 날짜 문자열로 생성하지 않고 원본 maturity ledger와 R6 fit receipt를 사용했다. R6의 CAL_FIT/CAL_SELECT는 calendar 순서 반분 후 기존 적격 마스크를 유지하는 offline 분할이고, R6R1/V41의 expanding rolling calibration과 별개다. 원본 계약은 history/B/.../V40R6_CAL_SUBSPLIT_CONTRACT.json 및 history/C에 보존했다.

target은 submit window에 들어온 양수 GPU 수량 authority와 유효 관측 start/end가 있는 작업의 전체 lifetime GPU·h 합계다. 전력, 동시 GPU 점유, 확보된 여유용량, 해당 window 내 완료 의무량이 아니다. raw archive 모든 partition을 검사해 349일 원본 15분 target을 재생성했고 원본 H1/H4/H8 feature matrix는 정확히 일치했다. May 원본 평가 target와의 최대 오차는 {err:.3g} GPU·h다. 12 synthetic AIDC를 독립 학습시계열로 복제하지 않았다.

모델 SHA256:
- Q50: {line['models'][0]['sha256']}
- Q90: {line['models'][1]['sha256']}

두 모델은 GitHub B의 model bytes, 로컬 frozen model 및 May 31개 snapshot의 H4_model_authority에 모두 연결된다. 원본 H4_AUTHORITY 파일의 추가 탐색 결과는 AUTHORITY_SEARCH.json에 별도로 기록한다. snapshot 내 authority와 실제 model bytes를 우선 실행 증거로 사용했다.

고정 base trees로 chronological OOS 예측을 재생성한 뒤 max(target_day_end,target_label_available_at) < issue인 잔차만 모아 log1p one-sided 85% finite-sample order statistic을 재계산했다. 31일의 membership hash도 원본과 모두 일치했다. 기존 exposed Q50/Q90 최대 오차 {r['exposed_q_max_error']:.3g}; May base Q90 최대 오차 {max(v['base_Q90_max_error'] for v in r['May']):.3g}; May uncapped 최대 오차 {max(v['uncapped_max_error'] for v in r['May']):.3g} GPU·h. 상세 수치는 FROZEN_REPRODUCTION.json.

F0의 Dec–Feb 85% 수치는 이번에 동일 frozen model로 원인과적 재계산한 역사 reference이며 과거 R6의 offline 90% CAL_FIT 판정 수치를 대체하지 않는다. May F0는 실제 frozen 85% snapshot을 재현한다. historical 99% cap과 physical cap을 구분하며 May physical oracle coverage 85.9418558343%를 확인했다.

기존 NONE/FAIL/NO_MODEL_PROMOTED는 그대로 유지한다. 새 모델을 production에 연결하지 않았다.
'''
 (OUT/'OLD_MODEL_REPRODUCTION_REPORT_KO.md').write_text(text,encoding='utf-8')
def evaluate():
 p=pd.read_parquet(OUT/'PREDICTIONS.parquet');assert p.groupby(KEYS+['day']).window_start_slot.nunique().eq(p.groupby(KEYS+['day']).size()).all()
 m=[]
 for key,g in p.groupby(KEYS,sort=False):m.append(dict(zip(KEYS,key))|metrics(g))
 m=pd.DataFrame(m);m.to_csv(OUT/'MODEL_METRICS.csv',index=False)
 diag=[];dayrows=[]
 for key,g in p.groupby(KEYS+['day'],sort=False):
  met=metrics(g);dayrows.append(dict(zip(KEYS+['day'],key))|met)
 pd.DataFrame(dayrows).to_csv(OUT/'DAY_METRICS.csv',index=False)
 p['time_band']=(p.window_start_slot//24).map({0:'00-06',1:'06-12',2:'12-18',3:'18-24'})
 for axis in ['lead_hours','time_band']:
  for key,g in p.groupby(KEYS+[axis],sort=False):diag.append(dict(zip(KEYS,key[:-1]))|{'axis':axis,'value':key[-1]}|metrics(g))
 pd.DataFrame(diag).to_csv(OUT/'CALIBRATION_BY_LEAD_AND_TIME_BAND.csv',index=False)
 mean=m.groupby(['model','training_mode','horizon_hours','role']).mean(numeric_only=True).reset_index();mean.to_csv(OUT/'SEED_MEAN_METRICS.csv',index=False)
 comparisons=[]
 for row in mean.itertuples():
  ref=mean[(mean.model=='F1_LGBM')&(mean.training_mode==row.training_mode)&(mean.horizon_hours==row.horizon_hours)&(mean.role==row.role)]
  if len(ref):
   r=ref.iloc[0];comparisons.append({'model':row.model,'mode':row.training_mode,'horizon_hours':row.horizon_hours,'role':row.role,'Q90_pinball_ratio_to_same_H_LGBM':row.calibrated_Q90_pinball/r.calibrated_Q90_pinball,'raw_Q90_pinball_ratio_to_same_H_LGBM':row.raw_Q90_pinball/r.raw_Q90_pinball,'requirement_ratio_to_same_H_LGBM':row.mean_forecast_requirement/r.mean_forecast_requirement,'coverage':row.calibrated_coverage,'positive_coverage':row.positive_coverage,'burst_coverage':row.burst_coverage,'N_zero':row.N_zero,'N_windows':row.N_windows})
 pd.DataFrame(comparisons).to_csv(OUT/'HORIZON_COMPARISON.csv',index=False)
 refs=[]
 for key,g in mean.groupby(['model','horizon_hours','role']):
  if set(g.training_mode)=={'fixed','expanding'}:
   a=g[g.training_mode=='fixed'].iloc[0];b=g[g.training_mode=='expanding'].iloc[0];refs.append(dict(zip(['model','horizon_hours','role'],key))|{'fixed_pinball':a.calibrated_Q90_pinball,'expanding_pinball':b.calibrated_Q90_pinball,'pinball_change':b.calibrated_Q90_pinball-a.calibrated_Q90_pinball,'fixed_coverage':a.calibrated_coverage,'expanding_coverage':b.calibrated_coverage,'fixed_requirement':a.mean_forecast_requirement,'expanding_requirement':b.mean_forecast_requirement,'fixed_burst_coverage':a.burst_coverage,'expanding_burst_coverage':b.burst_coverage})
 pd.DataFrame(refs).to_csv(OUT/'REFIT_COMPARISON.csv',index=False)
 d=pd.DataFrame(dayrows).groupby(['model','training_mode','horizon_hours','role','day']).mean(numeric_only=True).reset_index();unc=[];rng=np.random.default_rng(20260924)
 for (model,mode,h,role),g in d.groupby(['model','training_mode','horizon_hours','role']):
  if role=='DEVELOPMENT':continue
  ref=d[(d.model=='F1_LGBM')&(d.training_mode==mode)&(d.horizon_hours==h)&(d.role==role)]
  if not len(ref):continue
  z=g.merge(ref,on='day',suffixes=('','_ref')).sort_values('day');n=len(z);nb=math.ceil(n/7);starts=rng.integers(0,n,size=(1000,nb));indices=((starts[:,:,None]+np.arange(7))%n).reshape(1000,-1)[:,:n]
  for field in ['calibrated_Q90_pinball','raw_Q90_pinball','mean_forecast_requirement','burst_mean_miss_GPUh','calibrated_coverage']:
   dif=(z[field]-z[field+'_ref']).to_numpy();boot=np.nanmean(dif[indices],1);unc.append({'model':model,'mode':mode,'horizon_hours':h,'role':role,'metric':field,'difference_to_LGBM':float(np.nanmean(dif)),'CI95_low':float(np.nanquantile(boot,.025)),'CI95_high':float(np.nanquantile(boot,.975)),'N_paired_days':n,'block_length_days':7,'bootstrap_draws':1000,'seed_aggregation':'mean per-seed daily metric before resampling'})
 pd.DataFrame(unc).to_csv(OUT/'PAIRED_DAY_BLOCK_UNCERTAINTY.csv',index=False)
 return m,mean,pd.DataFrame(comparisons),pd.DataFrame(refs),pd.DataFrame(unc)
if __name__=='__main__':
 old_reports();original_report()
 if (OUT/'EXECUTION_COMPLETE.json').exists():evaluate()

