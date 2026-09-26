"""Registered day-grouped metrics, paired uncertainty and strict verdict."""
from common import *


def scored(frame, variant):
    g=frame.copy()
    if variant=='raw':
        g['Q50']=g.raw_Q50;g['Q90']=g.raw_Q90
    return g


def row_metrics(group):
    return dict(N_days=group.target_day.nunique(),**metrics(group.actual_GPUh,group.Q50,group.Q90))


def aggregate(frame, keys, variant, extra=None):
    rows=[]
    for key,g in frame.groupby(keys,sort=True):
        key=(key,) if not isinstance(key,tuple) else key
        row=dict(zip(keys,key));row['variant']=variant
        if extra:row.update(extra)
        rows.append(dict(**row,**row_metrics(g)))
    return rows


def block_indices(days, rng, draws=2000):
    """Resample paired day blocks; never bridge a missing calendar day."""
    d=pd.to_datetime(days)
    boundaries=np.r_[0,np.flatnonzero(np.diff(d.values).astype('timedelta64[D]').astype(int)!=1)+1,len(days)]
    result=[]
    for _ in range(draws):
        sample=[]
        for start,end in zip(boundaries[:-1],boundaries[1:]):
            n=end-start
            starts=rng.integers(0,n,size=int(np.ceil(n/7)))
            sample.extend((start+((starts[:,None]+np.arange(7))%n)).ravel()[:n])
        result.append(sample)
    return np.array(result)


def bootstrap(day):
    rows=[]
    keys=['Q90_coverage','Q90_pinball','Q90_sum_GPUh','actual_GPUh']
    avg=day.groupby(['split','variant','model','target_day'])[keys].mean().reset_index()
    for (split,variant),frame in avg.groupby(['split','variant']):
        reference=frame[frame.model.eq('LGBM')].set_index('target_day').sort_index()
        ix=block_indices(reference.index,np.random.default_rng(20260926))
        for family in ['SEASONAL','TFT','DEEPAR']:
            candidate=frame[frame.model.eq(family)].set_index('target_day').sort_index()
            if candidate.empty:continue
            require(candidate.index.equals(reference.index),'paired dates differ')
            c=candidate[keys].to_numpy();b=reference[keys].to_numpy()
            values={
                'Q90_pinball':(c[ix,1].mean(1)-b[ix,1].mean(1),c[:,1].mean()-b[:,1].mean()),
                'calibration_error':(abs(c[ix,0].mean(1)-.9)-abs(b[ix,0].mean(1)-.9),abs(c[:,0].mean()-.9)-abs(b[:,0].mean()-.9)),
                'requirement_ratio':(c[ix,2].sum(1)/c[ix,3].sum(1)-b[ix,2].sum(1)/b[ix,3].sum(1),
                                     c[:,2].sum()/c[:,3].sum()-b[:,2].sum()/b[:,3].sum())}
            for metric,(distribution,point) in values.items():
                low,high=np.quantile(distribution,[.025,.975])
                rows.append(dict(split=split,variant=variant,candidate=family,reference='LGBM',metric=metric,
                    delta=point,CI95_low=low,CI95_high=high,N_days=len(c),bootstrap_draws=len(ix),block_days=7,
                    improvement_supported=bool(high<0),seeds='averaged within day; not independent replicates'))
    return pd.DataFrame(rows)


def main():
    require((ROOT/'MAY_HISTORICAL_COMPLETE.json').exists(),'all registered evaluation must complete')
    require(not (ROOT/'FINAL_SELECTION_FREEZE.json').exists(),'final report immutable')
    f=pd.concat([pd.read_parquet(ROOT/f'{role}_PREDICTIONS.parquet') for role in ROLES[-2:]],ignore_index=True)
    f.to_parquet(ROOT/'PREDICTIONS.parquet',index=False)
    audit=json.loads((ROOT/'TARGET_RECONSTRUCTION_AUDIT.json').read_text(encoding='utf-8'))
    threshold=audit['TRAIN_positive_Q95_burst_threshold_GPUh']
    f['lead_band']=pd.cut(f.lead_hours,[5,11,17,23,29],labels=['6-11','12-17','18-23','24-29']).astype(str)
    model=[];daily=[];hourly=[];lead=[];regime=[]
    base=['split','model','seed']
    for variant in ['raw','calibrated']:
        g=scored(f,variant)
        model+=aggregate(g,base,variant)
        daily+=aggregate(g,base+['target_day'],variant)
        hourly+=aggregate(g,base+['target_hour'],variant)
        lead+=aggregate(g,base+['lead_band'],variant)
        for name,mask in [('zero',g.actual_GPUh.eq(0)),('positive',g.actual_GPUh.gt(0)),('burst',g.actual_GPUh.gt(threshold))]:
            regime+=aggregate(g[mask],base,variant,dict(regime=name,TRAIN_burst_threshold_GPUh=threshold))
    tables={'MODEL_METRICS.csv':model,'DAY_METRICS.csv':daily,'HOUR_OF_DAY_METRICS.csv':hourly,
            'LEAD_TIME_METRICS.csv':lead,'BURST_METRICS.csv':regime}
    for name,rows in tables.items():pd.DataFrame(rows).to_csv(ROOT/name,index=False)
    uncertainty=bootstrap(pd.DataFrame(daily))
    uncertainty.to_csv(ROOT/'PAIRED_DAY_BLOCK_UNCERTAINTY.csv',index=False)
    m=pd.DataFrame(model);r=pd.DataFrame(regime)
    numeric=[col for col in m.columns if col not in base+['variant']]
    summary=m.groupby(['split','model','variant'])[numeric].mean().reset_index()
    summary.to_csv(ROOT/'SEED_MEAN_METRICS.csv',index=False)
    selected=json.loads((ROOT/'MODEL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))['selected_family']
    s=summary[summary.model.eq(selected)&summary.variant.eq('calibrated')].set_index('split')
    baseline=summary[summary.model.eq('SEASONAL')&summary.variant.eq('calibrated')].set_index('split')
    seeds=m[m.model.eq(selected)&m.variant.eq('calibrated')]
    rg=r[r.model.eq(selected)&r.variant.eq('calibrated')].groupby(['split','regime'])[['Q90_coverage','Q90_pinball']].mean()
    calibration=bool(s.Q90_coverage.between(.88,.92).all())
    seed_pass=bool(seeds.Q90_coverage.between(.85,.95).all())
    sharpness=bool((s.Q90_pinball<=baseline.Q90_pinball).all() and (s.requirement_ratio<=baseline.requirement_ratio).all())
    regimes=bool(all(rg.loc[(split,'positive'),'Q90_coverage']>=.80 and rg.loc[(split,'burst'),'Q90_coverage']>=.50 for split in s.index))
    integrity=all(json.loads((ROOT/f'{name}.json').read_text(encoding='utf-8'))['status']=='PASS' for name in
                  ['TARGET_RECONSTRUCTION_AUDIT','POPULATION_COMPARISON','LEAKAGE_AUDIT','DATA_SPLITS_AND_MATURITY','BASELINE_VALIDATION'])
    failure_count=len(json.loads((ROOT/'FAILURES.json').read_text(encoding='utf-8')))
    all_runs=json.loads((ROOT/'MODEL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))['runs']
    complete=all(sum(run['family']==family for run in all_runs)==3 for family in ['LGBM','TFT','DEEPAR'])
    supported=integrity and complete and calibration and seed_pass and sharpness and regimes
    comparison=uncertainty[uncertainty.candidate.eq(selected)&uncertainty.variant.eq('calibrated')&uncertainty.metric.eq('Q90_pinball')]
    replacement=bool(supported and selected!='LGBM' and len(comparison)==2 and comparison.improvement_supported.all())
    decision=dict(time=now(),selected_family_frozen_on_DEVELOPMENT=selected,evaluation_reselection=False,
        CC4_V2_FORECAST_TARGET_VALID=integrity,Q90_90PCT_CALIBRATION_SUPPORTED=bool(supported),
        MODEL_REPLACEMENT_SUPPORTED=replacement,OPTIMIZER_INTEGRATION_READY=bool(supported),
        PRODUCTION_MODEL_PROMOTED=False,OPTIMIZER_CHANGED=False,GRID_CAMPAIGN_EXECUTIONS=0,NO_UNTOUCHED_CONFIRMATION=True,
        gates=dict(integrity=integrity,all_registered_seed_runs_complete=complete,calibration_band_both_periods=calibration,
                   all_seed_band=seed_pass,sharpness_vs_seasonal=sharpness,positive_burst_robustness=regimes),
        failure_count=failure_count,model_selection_sha256=sha(ROOT/'MODEL_SELECTION_FREEZE.json'),
        calibration_freeze_sha256=sha(ROOT/'CALIBRATION_FREEZE.json'),prediction_sha256=sha(ROOT/'PREDICTIONS.parquet'))
    dump('FINAL_SELECTION_FREEZE.json',decision,exclusive=True)
    no_cap=dict(status='PASS',prediction_upper_cap=None,target_upper_cap=None,
        physical_capacity_in_model_inputs=False,headroom_in_model_inputs=False,
        raw_prediction_max_GPUh=float(f.raw_Q90.max()),calibrated_prediction_max_GPUh=float(f.Q90.max()),
        calibrated_predictions_above_780_GPUh=int(f.Q90.gt(780).sum()),
        calibrated_predictions_above_3120_GPUh=int(f.Q90.gt(3120).sum()),
        repair='nonnegative support and monotone quantiles only; never an upper capacity limit')
    dump('NO_CAP_AUDIT.json',no_cap)
    write_review(summary,rg,uncertainty,decision,threshold)
    print(json.dumps(decision,indent=2),flush=True)


def write_review(summary,rg,uncertainty,decision,threshold):
    counts=json.loads((ROOT/'DATA_SPLITS_AND_MATURITY.json').read_text(encoding='utf-8'))['memberships']
    selected=decision['selected_family_frozen_on_DEVELOPMENT']
    lines=['# CC4-v2 시간별 미래 도착 GPU-work 예측: 최종 검토', '',
        '독립 offline experiment v1. 과거 평가를 본 뒤 재학습·보정·대상 변경을 하지 않았다. 모든 수치는 GPU·h 원단위이며 seed별 점수를 동일 가중 평균했다.', '',
        '## 1–3. 기존 H4의 의미와 90% 한계', '',
        '기존 H4는 4시간 안에 원래 submit 시각이 들어오는 Job의 **전체 lifetime GPU-work** 합이다. 실행이 그 4시간 안에 끝난다는 뜻이 아니다. 따라서 장시간 Job들의 도착량은 그 창에서 처리 가능한 780 GPU × 4 h = 3120 GPU·h보다 클 수 있다.',
        'PR #57의 2,511개 May 창 중 353개가 physical cap을 넘는다. 기존 actionable coverage는 2045/2511 = 81.4416567%, physical-cap oracle ceiling은 2158/2511 = 85.9418558%다. 기존 target과 cap을 함께 유지하면 어떤 예측기로도 90% actionable coverage를 달성할 수 없다. PR #59의 교체 근거 부족 판정은 변경하지 않는다.', '',
        '## 4–5. 새 target과 인과 경계', '',
        '고정 UTC+10 modeled local time의 D−1 18:00에 다음날 D 00:00–24:00의 24개 정시 bin을 예측한다. Lead는 6–29시간이다. 각 bin은 submit이 그 시간에 들어가는 frozen-eligible Job의 GPU 수 × 실제 runtime 전체 합이다. 모든 대상 Job은 발행 시점 이후 submit된다. 14:20 도착, 4 GPU, 2.5 h Job은 14시 bin에 10 GPU·h를 더하며 15시 이후에도 처리될 수 있다.',
        '원시 Job archive의 전체 partition을 다시 읽어 frozen IDs와 GPU·h를 대조했다. 미래 runtime은 label에만 사용한다. 과거 workload는 완료되어 성숙한 경우만 feature에 들어가고 미성숙은 mask와 0으로 표시한다. 71개 lineage 중 불필요한 child15_position만 target_hour로 바꿨다. 실제 telemetry ingestion latency와 request 수정 이력은 원 authority에서 인증되지 않았으므로 event-time 기준의 인과 검증이다.', '',
        '모델 파라미터·정규화·burst threshold는 TRAIN에서만 추정한다. DEVELOPMENT에서 설정과 모델을 고정하고, CALIBRATION의 시간별 잔차를 유한표본 순위로 보정했다. 26개 일별 residual이면 ceil(0.9×27)=25번째 값을 쓴다. 시간별 보정은 24시간 동시 보장이나 시계열 분포 무관 보장을 뜻하지 않는다. 보정은 signed additive이며 Q50 이하를 막는 순서 제약만 적용한다. 용량 상한이나 임의 배율은 없다.', '',
        '## 정확한 분할', '', '```text']
    lines += [f'{role}_DAYS = {counts[role]["N_days"]}' for role in ROLES]
    lines += ['NO_UNTOUCHED_CONFIRMATION = TRUE','```', '',
        'PR #59와 day membership은 정확히 대조하며 모든 24시간은 같은 split에 속한다. PURGE와 기존 제외일을 보존했다. 전체 날짜와 성숙 시각은 각 MEMBERSHIP.csv, 변경 여부는 SPLIT_MEMBERSHIP_DIFF.csv에 있다. May는 untouched holdout이 아니다.', '',
        '## 6. Q50/Q90와 sharpness', '',
        '| 기간 | 모델 | Q50 coverage | Q90 coverage | 보정오차 | Q90 pinball | Q50 pinball | Q50 MAE | Q50 RMSE | 요구량 비율 | 초과량 비율 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in summary[summary.variant.eq('calibrated')].itertuples():
        lines.append(f'| {row.split} | {row.model} | {row.Q50_coverage:.4%} | {row.Q90_coverage:.4%} | {row.calibration_error:.5f} | {row.Q90_pinball:.3f} | {row.Q50_pinball:.3f} | {row.Q50_MAE:.3f} | {row.Q50_RMSE:.3f} | {row.requirement_ratio:.3f} | {row.excess_reserve_proxy:.3f} |')
    lines += ['', 'Q50는 별도 보정을 하지 않았다. raw/calibrated와 모든 seed의 결과를 MODEL_METRICS.csv에 함께 보존한다. Coverage는 정확한 actual ≤ prediction이며 zero를 제외하지 않는다.', '',
        '## 7–8. 모델 선택과 day-block uncertainty', '',
        f'DEVELOPMENT에서 사전 고정한 모델은 **{selected}**다. 평가에서 다른 모델의 일부 지표가 더 좋아도 모델을 다시 선택하지 않았다. TFT는 PR #59의 소형 gated variable selection/LSTM/causal attention 구현이고 DeepAR는 hurdle-lognormal recurrent 구현이다. 원 논문의 완전한 대형 benchmark 구현이라는 주장은 하지 않는다.',
        '3개 seed를 독립 day sample처럼 취급하지 않았다. 동일 날짜에서 seed 점수를 평균하고, 두 모델에 동일한 7일 block을 적용한 2,000회 paired bootstrap으로 불확실성을 계산했다. 음수 delta가 개선이며 CI가 0을 포함하면 우위를 주장하지 않는다.', '',
        '| 기간 | 후보 vs LightGBM | 지표 | Δ | 95% CI |', '|---|---|---|---:|---|']
    for row in uncertainty[uncertainty.variant.eq('calibrated')&uncertainty.candidate.isin(['TFT','DEEPAR'])].itertuples():
        lines.append(f'| {row.split} | {row.candidate} | {row.metric} | {row.delta:.5f} | [{row.CI95_low:.5f}, {row.CI95_high:.5f}] |')
    lines += ['', '## 9–11. 과대예측, positive/burst, 기간 일관성', '',
        f'Burst는 TRAIN의 positive hourly GPU-work Q95={threshold:.6f}보다 큰 시간으로 미리 정의했다. 선택 모델 {selected}의 다음 수치는 모든 seed 평균이다.', '',
        '| 기간 | regime | Q90 coverage | Q90 pinball |', '|---|---|---:|---:|']
    for (split,regime),row in rg.iterrows():
        lines.append(f'| {split} | {regime} | {row.Q90_coverage:.4%} | {row.Q90_pinball:.3f} |')
    lines += ['', f'사전 등록한 품질 gate의 실제 결과: `{json.dumps(decision["gates"],ensure_ascii=False)}`.',
        '88–92% coverage, seed 안정성, seasonal 대비 pinball·요구량, positive/burst 강건성을 **두 평가기간 모두** 확인한다. 98–100% coverage나 큰 요구량은 성공으로 간주하지 않는다. 상세 시간대·lead별 편차는 HOUR_OF_DAY_METRICS.csv와 LEAD_TIME_METRICS.csv에 모두 보존했다. 이 gate가 실패하면 약 90%의 전반적인 성공을 주장하지 않는다.', '',
        '## 12. Production 교체 근거', '',
        f'Q90 보정·sharpness·강건성 지지: **{decision["Q90_90PCT_CALIBRATION_SUPPORTED"]}**. 교체 지지: **{decision["MODEL_REPLACEMENT_SUPPORTED"]}**. Target의 과학적 단위 정합성과 ML의 예측 성능은 별개다. 상한 제거는 기존 인위적 ceiling을 제거하지만 좋은 보정과 정확도를 보장하지 않는다. 이 연구만으로 운영 reserve adequacy 90%를 주장할 수 없다. Production 승격은 수행하지 않았다.', '',
        '## 13. 다음 optimizer/P2 연결 — 문서만', '',
        '**ML predicts future workload. Optimizer determines headroom.**',
        '차후 optimizer가 H_h(x)=C_h−L_h_known(x)를 정하고, 0≤S_h_future≤H_h(x)Δt로 미래 service를 배분해야 한다. Arrival workload를 같은 시간의 service 의무로 놓지 않아야 한다. 시간 간 누적 도착·service·carry-out과 실제 deadline authority를 정의한 뒤 누적/마감 기반 reserve 제약을 설계해야 한다. 시간별 marginal Q90의 단순 합은 하루 profile의 joint Q90가 아니므로 dependence/scenario 또는 별도 joint calibration 검증이 필요하다. 그 이후 P2 trade-off와 실제 미래 Job replay를 검증해야 한다. 이번 작업에서 optimizer, P2, scheduler, MESS, Fresh/Actual, OpenDSS, Gurobi를 변경하거나 실행하지 않았다.', '', '```text']
    for key in ['CC4_V2_FORECAST_TARGET_VALID','Q90_90PCT_CALIBRATION_SUPPORTED','MODEL_REPLACEMENT_SUPPORTED','OPTIMIZER_INTEGRATION_READY','PRODUCTION_MODEL_PROMOTED','OPTIMIZER_CHANGED','GRID_CAMPAIGN_EXECUTIONS','NO_UNTOUCHED_CONFIRMATION']:
        val=decision[key]
        lines.append(f'{key} = {str(val).upper()}')
    lines += ['```','']
    (ROOT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':main()
