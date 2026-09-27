"""Generate Korean delivery report only after frozen evaluation and audits."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def read(n):return json.loads((ROOT/n).read_text(encoding='utf-8'))
for n in ['VALIDATION.json','RESULT_REVIEW.json','REUSE_AUDIT.json','TEST_RESULTS.json']:assert read(n)['PASS']
f=read('FINAL_SELECTION_FREEZE.json');v=read('FINAL_VERDICT.json');d=read('DISTRIBUTION_PARAMETERS.json')
m=pd.read_csv(ROOT/'MODEL_METRICS.csv');ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv')
cost=pd.concat([pd.read_csv(ROOT/'HISTORICAL_COMPUTATIONAL_COST.csv'),pd.read_csv(ROOT/'NEW_COMPUTATIONAL_COST.csv')],ignore_index=True)
cost.to_csv(ROOT/'COMPUTATIONAL_COST.csv',index=False,lineterminator='\n')
aggregate=cost.groupby(['arm','phase']).agg(fits=('day','size'),sum_fit_forecast_seconds=('total_fit_forecast_seconds','sum'),mean_fit_forecast_seconds=('total_fit_forecast_seconds','mean')).reset_index()
aggregate.to_csv(ROOT/'COMPUTATIONAL_COST_SUMMARY.csv',index=False,lineterminator='\n')
lines=['# CC4-v2.6 최종 검토 — Distributional / Hybrid Forecast Comparison','',
f"DEV/CAL에서 동결한 primary는 **{f['primary']}**이다. Historical evaluation 후 재선택하지 않았다. May는 이미 노출된 historical diagnostic이며 tuning 또는 untouched confirmation에 사용하지 않았다.",'',
'이번 고정 비교에서는 B0보다 더 sharp하면서 reserve 제약을 지키는 대체 모델을 뒷받침하지 못했다. B1/B2는 tail coverage를 올리는 대가로 pinball과 reserve가 모두 악화됐다. B3/B4/B5의 Dec–Feb pinball 개선 CI는 모두0을 포함하고, May에서는 모든 challenger의 requirement ratio가2를 초과했다. B0 유지가 B0 자체의 목표 coverage 달성을 의미하지는 않는다.','',
'## 고정 authority와 비교 범위','',
'PR #64의 raw expanding/30-day recency/daily-refit LightGBM을 B0로 유지했다. PR #67/#69/#70/#73의 negative-result evidence를 보존하고, 새 distributional 비교만 추가했다. Target은 D−1 18:00의 next-day hourly future-arrival GPU·h이며 population, split, 71개 causal feature 및 neural past authority를 변경하지 않았다. 모델 clock은 기존 UTC+10이다.','',
'모든 refit은 full-day label_matured_at < issue_time 및 과거 issue, non-PURGE membership을 사용한다. 기존 정책대로 이미 성숙한 Mar–Apr와 이전 evaluation/May label은 이후 issue의 고정 refit에만 들어갈 수 있다. 이러한 label을 dispersion, gate, ensemble weight, feature 또는 hyperparameter 선택에 사용하지 않는다.','',
'B0·B4·B5는 기존 예측과 1,911개 forecast receipt를 검증하여 재사용했다. PR64의 weight receipt에는 축약된 pandas Index 문자열이 저장되어 있어 그 문자열과 고정 수식을 검증하고 전체 numeric membership/weights를 새로 저장했다. 이를 과거 numeric receipt byte 검증으로 주장하지 않는다. 원 frozen artifact를 수정하지 않았다.','',
'## 분포의 수학적 의미','',
'B1은 **zero-atom lognormal distribution**이다. Tweedie 구현이나 Tweedie quantile 근사로 부르지 않는다. Binary LightGBM으로 p=P(Y>0|X), positive log(Y)의 L2 LightGBM으로 location μ를 추정한다. 분포는 0에 질량 1−p, 양의 구간에 lognormal(μ,σ²)를 둔다.','',
'- τ≤1−p이면 Qτ=0.','- 나머지는 Qτ=exp[μ+σ Φ⁻¹((τ−1+p)/p)].','- Burst risk는 p·[1−Φ((log(TRAIN burst threshold)−μ)/σ)]다.','',
f"Sigma={d['sigma']:.12g}는 TRAIN 내부 daily OOS positive log residual {d['residual_rows']:,}개, {len(d['days'])}일에서 recency-weighted mean squared residual의 제곱근으로 추정했다. 각 residual의 source model은 그 issue 이전에 성숙한 최소60일만 학습했고, residual label 자체도 첫 DEV issue 전에 성숙했다. 이는 고정 location의 Gaussian likelihood 분산 추정이며 coverage를 맞추는 multiplier가 아니다. Sigma를 DEV 전에 동결하고 후속 update·scale·cap을 적용하지 않았다.",'',
'계산은 analytic inverse-CDF에 기반하며 scipy lognormal PPF로 별도 재검산했다. 수학적으로 유효한 분포라는 사실은 lognormal 가정의 데이터 적합성이나 empirical coverage를 보장하지 않는다. Unsupported 수치를 clipping으로 숨기지 않고 nonfinite이면 중단한다. 수식 구현 근거: [SciPy lognorm](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.lognorm.html), [LightGBM objectives](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html).','',
f"B2는 B1의 burst 확률≥**{f['gate']}**인 시간에만 B1 Q50/Q90을 사용한다. Gate 밖은 B0와 bit-exact하며 global uplift나 max envelope가 없다. Gate 후보 .1/.2/.3 중 DEV에서만 선택했다.",'',
f"B3는 **(1−{f['weight']})×B0 + {f['weight']}×B5**의 quantile 평균이다. Q50/Q90에 같은 weight를 사용하므로 ordering이 유지된다. Weight 후보 .25/.5/.75는 DEV에서만 비교했다. 이는 mixture-CDF의 quantile이라는 주장이 아니다.",'',
'B4/B5는 기존 compact SmallTFT/SmallDeepAR를 그대로 사용한다. 3개 고정 seed의 **prediction 평균**을 주 지표로 비교하며, 과거 PR64의 seed별 metric 평균과 구분한다. SEED_METRICS.csv에 개별 seed도 저장했다. TFT hidden16/8epochs, DeepAR hidden16/18epochs/lr.001 및128 trajectory sampling을 변경하지 않았다. DeepAR quantile에는 원래 Monte Carlo 오차가 있으며 full-size TFT/DeepAR 전체 계열을 대표하는 비교가 아니다.','',
'## 선택과 동결','',
'B2/B3 parameter는 DEV에서 ratio<2인 후보 중 Q90 pinball 최소값으로 선택했다. 그런 후보가 없으면 가장 낮은 손실의 연구 설정만 동결한다. CAL에서 parameter를 바꾸지 않았다. Family eligibility는 DEV와 CAL 각각 coverage88–92%, ratio<2, pinball≤B0, burst coverage>B0다. 5% pinball 개선과 ratio<1.8은 선호 기준이다. Eligible 후보가 없으면 B0를 유지한다.','',
f"Freeze eligibility: `{f['eligibility']}`. Code freeze `{read('CODE_FREEZE.json')['time']}`, dispersion freeze `{d['time']}`, selection freeze `{f['time']}`, evaluation 완료 `{read('EVALUATION_COMPLETE.json')['time']}`.",'',
'## 모델 지표','',
'| period | arm | coverage | Q90 pinball GPUh | ratio | positive coverage | burst coverage | Q50 MAE GPUh | Q50 WAPE |',
'|---|---|---:|---:|---:|---:|---:|---:|---:|']
for r in m.itertuples():lines.append(f'| {r.role} | {r.arm} | {r.Q90_coverage:.2%} | {r.Q90_pinball:.4f} | {r.requirement_ratio:.4f} | {r.positive_coverage:.2%} | {r.burst_coverage:.2%} | {r.Q50_MAE:.4f} | {r.Q50_WAPE:.4f} |')
lines+=['','## Paired statistical uncertainty','',
'같은 target-day의24시간을 함께 재표집했다. 1일/7개 관측일 circular block 각2,000회이며 draw마다 coverage·reserve 비율을 다시 계산했다. Zero denominator 또는 nonfinite draw가 하나라도 있으면 그 CI 전체를 unavailable로 표시하고 해당 draw를 삭제·재추출하지 않는다. 7-day CI를 지원 판정에 사용하며 day CI는 sensitivity다.','',
'아래는 B0 대비 차이다. Pinball은 GPUh, coverage는 percentage point, ratio는 무차원이다. 전체 CI와 positive/burst/MAE 대비는 PAIRED_UNCERTAINTY.csv에 있다.','',
'| period | arm | Δpinball [95% CI] | Δcoverage pp [95% CI] | Δratio [95% CI] |',
'|---|---|---|---|---|']
for role in ['EXPOSED_EVALUATION','MAY_HISTORICAL']:
    for arm in ['B1','B2','B3','B4','B5']:
        vals=[]
        for name in ['Q90_pinball','Q90_coverage','requirement_ratio']:
            r=ci[(ci.role==role)&(ci.arm==arm)&(ci.metric==name)&(ci.block_days==7)].iloc[0];scale=100 if name=='Q90_coverage' else 1
            vals.append(f'{r.delta*scale:+.4f} [{r.low*scale:+.4f}, {r.high*scale:+.4f}]' if r.invalid_draws==0 else 'unavailable (invalid denominator)')
        lines.append('| '+role+' | '+arm+' | '+' | '.join(vals)+' |')
lines+=['','CI는 frozen forecast에 조건부인 exploratory per-contrast95% 구간이다. Refit/selection uncertainty나 multiple-comparison adjustment를 포함하지 않으며 untouched 또는 familywise confirmation으로 주장하지 않는다.','',
'지원 판정은 DEV/CAL-eligible 설정에만 가능하다. Dec–Feb와 May 모두 같은 point gate를 통과하고 7-day CI의 Δpinball upper<0, Δburst coverage lower>0이어야 한다. Evaluation 결과로 eligibility·primary·gate·weight를 바꾸지 않았다.','',
'## 계산 비용','',
'| arm | phase | daily fits/seed fits | summed fit+forecast seconds | mean seconds per fit |','|---|---|---:|---:|---:|']
for r in aggregate.itertuples():lines.append(f'| {r.arm} | {r.phase} | {r.fits} | {r.sum_fit_forecast_seconds:.3f} | {r.mean_fit_forecast_seconds:.3f} |')
lines+=['','B0/B4/B5 비용은 원 fit receipt의 historical measured elapsed time이다. 이번 task에서는 재학습0회로 재사용했다. Neural 비용은3개 seed 모두 포함한다. B1은4개 CPU process로 새 학습했고 표의 합은 각 fit의 elapsed time 합으로, 전체 task wall time과 다르다. B0는 fit/forecast 통합 receipt, neural과 B1은 train/inference 분리 receipt를 사용하므로 서로 동일 hardware benchmark로 해석하지 않는다.','',
'B2는 공유 B0+B1, B3는 공유 B0+3-seed DeepAR가 필요하며 별도 model fitting은 없다. Hybrid/convex-average의 작은 array 연산 시간을 측정한 것처럼0으로 기록하지 않는다. Shared fit cost를 중복 합산하지 않았다. 모든 day별 측정치는 COMPUTATIONAL_COST.csv, aggregate는 COMPUTATIONAL_COST_SUMMARY.csv에 있다.','',
'## 검증 및 최종 판정','',
f"14개 contract test PASS. 재사용 forecast/membership1,911개, 새 exact membership{read('VALIDATION.json')['exact_memberships']}개, checkpoint{read('VALIDATION.json')['checkpoint_replays']}개, prediction row{read('VALIDATION.json')['prediction_rows']:,}개를 감사했다. 전체 metric/strata/horizon row{read('RESULT_REVIEW.json')['metric_rows']}개와 paired CI{read('VALIDATION.json')['paired_CI_rows']}개를 별도 수식으로 재현했다.",'']
for key in ['DISTRIBUTIONAL_MODEL_SUPPORTED','HYBRID_SUPERIOR_TO_LGBM','ENSEMBLE_SUPERIOR_TO_LGBM','PRODUCTION_REPLACEMENT_SUPPORTED','OPTIMIZER_INTEGRATION_READY','PRODUCTION_PROMOTED','NO_UNTOUCHED_CONFIRMATION']:
    lines.append(f"- {key} = **{str(v[key]).upper()}**")
lines+=['','DISTRIBUTIONAL_IMPLEMENTATION_VALID=TRUE는 수학적 구현 검증이다. DISTRIBUTIONAL_MODEL_SUPPORTED는 실증적 채택 근거를 뜻한다. Tweedie는 평가하지 않았으며 unsupported Tweedie approximation을 만든 것이 아니다.','',
'기존 V40S4 D1_SCHEDULER_REQUEST_STATE_PROXY_V1의 request/ingestion provenance는 UNVERIFIED / UNOBSERVED다. 당시 archive 값과 실제 issue-time 상태의 정확한 동일성·request immutability·변경빈도0을 주장하지 않는다. 이 한계와 untouched confirmation 부재로 production replacement와 integration readiness는 fail-closed로 유지한다.','',
'기존 frozen evidence 및 production은 보존했다. Optimizer/MESS/IEEE123/8500/Actual/OpenDSS는 수정·실행하지 않았고 optimizer coupling과 production promotion도 하지 않았다.']
with (ROOT/'FINAL_REVIEW_KO.md').open('x',encoding='utf-8',newline='\n') as stream:stream.write('\n'.join(lines)+'\n')
print('REPORT COMPLETE')
