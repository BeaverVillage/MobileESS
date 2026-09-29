from common import *

def main():
    c=pd.read_csv(ROOT/'FINAL_Q50_COMPARISON.csv',float_precision='round_trip').set_index('Model')
    f=pd.read_csv(ROOT/'Q50_FOLD_METRICS.csv');f=f[f.Model==PRIMARY]
    b=pd.read_csv(ROOT/'Q50_RUNTIME_BUCKET_METRICS.csv');b=b[(b.Model==PRIMARY)&(b.fold=='POOLED')].set_index('bucket')
    r=pd.read_csv(ROOT/'Q50_RATIO_DISTRIBUTION.csv');r=r[(r.Model==PRIMARY)&(r.fold=='POOLED')].iloc[0]
    p=c.loc[PRIMARY]
    # Qualitative comparative judgment, not a hidden threshold or automatic Pareto gate.
    decision='NONE'
    rationale='D2 extreme is a useful comparative research reference and is non-dominated on the preregistered core axes, but its 1.347x pooled total is not sufficient evidence for a stable nominal provider. Median coverage changes direction across folds, short-job overprediction is large, and >12h actual jobs nearly always overrun Q50. The separate reserve needed to make that acceptable has not been evaluated. No numerical PASS cutoff is introduced.'
    flags=dict(NO_NEW_RUNTIME_TRAINING=True,COMMON_POPULATION_REUSED=True,COMMON_POPULATION_N=230237,RUNTIME_TARGET_UNIT='seconds',GPU_WEIGHTING_USED=False,PINBALL_USED_FOR_PRIMARY_DECISION=False,
        Q50_COVERAGE_COMPUTED=True,Q50_COVERAGE_TARGET=.50,Q50_USED_AS_NOMINAL_NOT_ROBUST_BOUND=True,
        PLANNING_RESERVE_IMPLEMENTED=False,ACTUAL_RUNTIME_RESERVE_IMPLEMENTED=False,CC4_CHANGED=False,V42_CHANGED=False,MAY_OPENED=False,OPENDSS_RUN=False,
        PRIMARY_NOMINAL_RUNTIME_CANDIDATE=decision,PRIMARY_Q50_MAE_HOURS=None,PRIMARY_Q50_COVERAGE=None,PRIMARY_Q50_TIME_RATIO=None,PRIMARY_GT12H_Q50_COVERAGE=None,
        APRIL_USED_FOR_SELECTION=False,PR94_RESULT_CHANGED=False,PR94_SELECTED_RUNTIME_MODEL='NONE',PR94_SELECTED_ALPHA=None,V9_FULL_DISTRIBUTION_PROMOTED=False,CONDITIONAL_REMAINING_MODEL_CHANGED=False)
    write('FINAL_FLAGS.json',flags)
    write('FINAL_VERDICT.json',dict(time=now(),status='COMPLETED_DESCRIPTIVE_AUDIT',PRIMARY_NOMINAL_RUNTIME_CANDIDATE=decision,decision_type='Qualitative comparative judgment, no invented numerical PASS threshold',rationale=rationale,
        audited_primary_candidate=PRIMARY,audited_primary_metrics=p.to_dict(),core_pareto=c[c.pareto_core].index.tolist(),stability_pareto=c[c.pareto_with_stability].index.tolist(),
        interpretation='Q50 targets about 50% coverage, not 90%. Pooled >50% is conservative in aggregate; it does not establish conditional calibration. Outcome-stratified coverage describes error burden and need not itself equal50%.',
        next_step='Evidence is available for a separately preregistered Planning-overrun-reserve design study with comparative frozen nominal baselines. This audit does not approve provider deployment, capacity headroom, or a remaining-runtime model.',
        prior_result='PR94 NONE and alpha null remain unchanged under its distinct Q50-Q90 scalar-duration criterion.',
        architecture=dict(Planning='Q50 total nominal duration plus a separately designed overrun reserve; unimplemented here',Actual='Observed RUNNING job retains its full physical GPU gang until completion; current capacity checked before PENDING start; no duplicate runtime reserve',D_day='After submission and metadata availability, same Runtime provider concept as known jobs; no per-job Runtime ML before an unknown job submits',Running='Elapsed time is observed; current physical occupancy cannot be reduced by a predicted remaining duration. Remaining inference unchanged.'),
        evidence=[rec(ROOT/n) for n in ['PREREGISTRATION.json','FINAL_Q50_COMPARISON.csv','Q50_FOLD_METRICS.csv','Q50_RUNTIME_BUCKET_METRICS.csv','Q50_LONG_RUNTIME_METRICS.csv','Q50_RATIO_DISTRIBUTION.csv']]))
    def pct(x):return f'{100*x:.2f}%'
    def vals(col):return '; '.join(f'fold {int(x.fold)}: {x[col]:.6f}' for _,x in f.iterrows())
    def compare(arm):
        z=c.loc[arm]
        return f'{arm}: MAE {z.Q50_MAE_hours:.3f}h, C50 {pct(z.Q50_coverage)}, 시간 비율 {z.Q50_time_ratio:.3f}, fold 표준편차 {100*z.fold_coverage_std:.2f}pp, >12h C50 {pct(z.GT12H_Q50_coverage)}. D2 extreme은 MAE {p.Q50_MAE_hours:.3f}h / C50 {pct(p.Q50_coverage)} / {p.Q50_time_ratio:.3f}배 / std {100*p.fold_coverage_std:.2f}pp / >12h {pct(p.GT12H_Q50_coverage)}이므로 어느 한 지표만으로 우위를 판정하지 않는다.'
    def bucket(name):
        z=b.loc[name];return f'N={int(z.N):,}, C50 {pct(z.Q50_coverage)}, MAE {z.Q50_MAE_hours:.3f}h, bucket 시간 비율 {z.Q50_time_ratio:.3f}배다.'
    table='| Model | Q50 MAE [h] | Q50 coverage [%] | Q50 time ratio [x] | Raw Q90 [%] | >12h Raw Q90 [%] |\n|---|---:|---:|---:|---:|---:|\n'
    for arm,z in c.iterrows():table+=f'| {arm} | {z.Q50_MAE_hours:.3f} | {100*z.Q50_coverage:.2f} | {z.Q50_time_ratio:.3f} | {100*z.Raw_Q90_coverage:.2f} | {100*z.GT12H_Raw_Q90_coverage:.2f} |\n'
    foldtable='| Fold | N | Q50 MAE [h] | C50 [%] | Calibration error [pp] | Time ratio [x] | >12h C50 [%] |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for _,z in f.iterrows():foldtable+=f'| {int(z.fold)} | {int(z.N):,} | {z.Q50_MAE_hours:.3f} | {100*z.Q50_coverage:.2f} | {100*z.Q50_calibration_error:.2f} | {z.Q50_time_ratio:.3f} | {100*z.GT12H_Q50_coverage:.3f} |\n'
    closestcal=c.Q50_calibration_error.idxmin();closesttime=(c.Q50_time_ratio-1).abs().idxmin();bestmae=c.Q50_MAE_hours.idxmin()
    qa=[
      ('Q50 coverage 정의는?', 'C50 = (1/N) sum I(T_actual≤Q50)다. 동일값은 covered로 포함한다. Underprediction은 엄격히 T_actual>Q50이며 두 비율의 합은1이다.'),
      ('왜 목표가90%가 아니라 약50%인가?', 'Q50은 중앙값 예측이기 때문이다. 연속적인 이상적 median의 coverage는 약50%다. 유한 표본·동일값·0-runtime 질량 때문에 정확히50%일 필요는 없고, pooled50%만으로 조건부 calibration이 입증되지도 않는다. 90% 견고성은 Q50에 강요하지 않는다.'),
      ('동일한230,237 jobs인가?', '그렇다. PR94의30개 VALID parquet byte SHA, 5개 fold membership hash, submit-time proxy, 실제 runtime, Q50/Q90를 그대로 재사용했다. 새 population이나 CAL 데이터는 열지 않았다.'),
      ('zero-runtime1,290건은?', '전체·fold MAE, coverage, aggregate 시간 합에는 포함했다. Q50/T 개별 비율에서만 제외해 양의 runtime228,947건을 사용했다. 양수 runtime bucket과 별도로 EXACT_ZERO_DIAGNOSTIC행을 제공하며, 이 행의 시간 비율은 분모0이므로 null이다.'),
      ('D2 extreme Q50 MAE는?', f'{p.Q50_MAE_seconds:.10f}초 = {p.Q50_MAE_hours:.8f}시간이다. PR94와 저장 float값을 정확히 재현했다.'),
      ('pooled C50는?', pct(p.Q50_coverage)+'다. pooled 수준에서는 중앙값 예측이 높은 방향이지만, 모든 fold에 같은 방향은 아니다.'),
      ('calibration error는?', f'|C50−0.5|={p.Q50_calibration_error:.8f}, 즉 {100*p.Q50_calibration_error:.4f}pp다. 설명 지표이며 새 PASS cutoff는 만들지 않았다.'),
      ('실제 runtime이 Q50을 넘는 비율은?', pct(p.Q50_underprediction_fraction)+'다. 작업 발생빈도이지 필요한 GPU reserve 양이나 동시 overrun 확률은 아니다.'),
      ('aggregate Q50 time ratio는?', f'{p.Q50_time_ratio:.10f}배다. GPU 가중치나15분 rounding 없이 sum(Q50 seconds)/sum(T seconds)다.'),
      ('1.347x와 median per-job4.001x는 왜 다른가?', f'개별 Q50/T 중앙값은 {r["median"]:.8f}배다. Aggregate는 긴 실제 runtime이 큰 분모를 차지하지만 median은 양의-runtime 작업마다 동등한 순위를 부여한다. 양의T에 한하면 aggregate는 runtime 가중 평균과 연결되며, 여기에는 별도로 T=0행의 Q50 합도 포함된다. 짧은 작업 다수와 긴 꼬리의 이질성이 차이를 만든다. Q10={r.Q10:.4f}, Q25={r.Q25:.4f}, Q75={r.Q75:.2f}, Q90={r.Q90:.2f}, Q95={r.Q95:.2f}; 평균은 진단용으로만 보존했다.'),
      ('fold별 C50는?', vals('Q50_coverage')+'. 위 fold 표에서는 백분율로 표시했다.'),
      ('fold별 시간 비율은?', vals('Q50_time_ratio')+'. 이5개 fold에서 비율<1인1/2/4는 C50<50%, 비율>1인3/5는 C50>50%였다. 보편 법칙이나 원인 증명은 아니다.'),
      ('worst Q50 coverage fold는?', f'50%에서 가장 먼 median-calibration 기준은 fold{int(p.worst_calibration_fold)}: C50 77.83%, error27.83pp다. 최소 coverage인 fold1(40.64%, error9.36pp)을 자동으로 최악이라 부르면 median 평가를 잘못 해석한다.'),
      ('fold coverage std는?',f'ddof=0, {p.fold_coverage_std:.8f} = {100*p.fold_coverage_std:.4f}pp. Min {pct(p.min_fold_Q50_coverage)}, max {pct(p.max_fold_Q50_coverage)}다.'),
      ('>4h C50는?',pct(p.GT4H_Q50_coverage)),
      ('>12h C50는?',pct(p.GT12H_Q50_coverage)+f'; 따라서 해당 실제 tail 작업의 {pct(1-p.GT12H_Q50_coverage)}가 Q50을 넘는다.'),
      ('>24h C50는?',pct(p.GT24H_Q50_coverage)),
      ('0<T≤15min에서는?',bucket('GT0_LE15MIN')),
      ('15min<T≤1h에서는?',bucket('GT15MIN_LE1H')),
      ('1h<T≤4h에서는?',bucket('GT1H_LE4H')),
      ('4h<T≤12h에서는?',bucket('GT4H_LE12H')),
      ('12h<T≤24h에서는?',bucket('GT12H_LE24H')),
      ('T>24h에서는?',bucket('GT24H')),
      ('short jobs를 심하게 overpredict하는가?', '실제0–15분 작업160,951건에서는 총 예측 시간이 실제의113.463배이고 MAE3.385h로 큰 과대예측 부담이 보인다. 이 bucket은 실제 결과로 정의했으므로 이를 predictor에 사용하거나 각 bucket이50%여야 한다고 주장하지 않는다.'),
      ('long jobs를 심하게 underpredict하는가?', '실제12–24h에서 시간 비율0.523, C50 3.08%; >24h에서는0.299, C50 0.44%, MAE26.124h다. 실제 긴 작업에서 명목 종료 이후 실행이 지속되는 부담이 크다. 결과 조건부 분석 자체를 조건부 median calibration 실패의 독립 증명으로 혼동하지 않는다.'),
      ('aggregate ratio가 이를 숨기는가?', '단독 보고하면 그렇다. 짧은 작업의 예측 시간 과잉과 긴 작업의 예측 시간 부족이 합계에서 상쇄된다. 1.347배를 모든 작업의 예측이34.7% 길다는 뜻으로 읽을 수 없다.'),
      ('D2 normal1.5와 비교하면?',compare('V9_D2_NORMAL_1P5_NONE')),
      ('D1 rolling14와 비교하면?',compare('V9_D1_ROLLING14')),
      ('D3 rolling14와 비교하면?',compare('V9_D3_ROLLING14')),
      ('V13과 비교하면?',compare('V13_EXPANDING_S4')),
      ('normal1.0 진단과 비교하면?',compare('V9_D2_NORMAL_1P0_NONE')+' 낮은 Q90 신뢰도 때문에 과거 진단 대조군이었던 상태도 바꾸지 않는다.'),
      ('MAE 최선은?',f'{bestmae}, {c.loc[bestmae,"Q50_MAE_hours"]:.4f}h.'),
      ('C50가50%에 가장 가까운 후보는?',f'{closestcal}, {pct(c.loc[closestcal,"Q50_coverage"])}. 가장 가까워도 calibrated median이라고 승인한 것은 아니다.'),
      ('time ratio가1에 가장 가까운 후보는?',f'{closesttime}, {c.loc[closesttime,"Q50_time_ratio"]:.6f}배. Normal1.0의0.651251배도 |ratio−1|=0.348749로 D2 extreme의0.347265와 거의 같다. 이 작은 차이로 모델을 선택하지 않는다.'),
      ('세 최선 모델이 동일한가?', '아니다. MAE normal1.5, pooled calibration normal1.0, 시간 합의1근접성 extreme1.0이다.'),
      ('D2 extreme은 Pareto 관점에서 합리적인가?', '추가 연구의 비교 후보로는 합리적이다. 사전 고정 core3축에서는 normal1.5/normal1.0/extreme1.0이 frontier이며, temporal2축을 추가하면6개 모두 남는다. 하지만 Pareto membership만으로 provider를 선택하지 않는다. 방향이 바뀌는 fold calibration과 큰 short/long 오차, 미평가 reserve 부담을 함께 고려해 최종 primary nominal 채택은 NONE이다. 수치 PASS 기준을 추가한 판단이 아니다.'),
      ('Q90를 optimizer nominal duration으로 쓰는가?', '아니다. 의도된 nominal duration은 total Q50다. 이번에는 optimizer나 provider 통합도 하지 않았다.'),
      ('Q90는 어떤 보조 정보인가?', f'동결 upper-quantile 신뢰도와 tail 위험의 보조 정보다. D2 extreme raw Q90 {pct(p.Raw_Q90_coverage)}, >12h raw Q90 {pct(p.GT12H_Raw_Q90_coverage)}를 재현했다. 이를 Q50의 안전성이나 향후 pooled reserve의 충분성으로 바꾸어 해석하지 않는다. Full-distribution 결함도 수리하지 않았다.'),
      ('Planning reserve를 구현했는가?', '아니다. headroom도 계산하지 않았다. 의도된 구조는 total-Q50 nominal + 별도 overrun reserve이며 다음 연구 범위다.'),
      ('Actual에 duplicate reserve를 두는가?', '아니다. 관측된 RUNNING gang의 실제 점유를 유지한다. 같은 overrun을 별도 Actual reserve로 또 더하지 않는 구조를 문서화했다.'),
      ('Actual RUNNING job 처리는?', '실제 완료가 관측될 때까지 full GPU gang 점유가 유지된다. PENDING 시작 전 현재 physical capacity를 검사한다. 예측 nominal end나 remaining 값이 현재 점유를 해제할 수 없다. 이번에 실행한 로직은 아니다.'),
      ('known과D-day submitted job이 같은 provider인가?', '의도된 설계에서는 제출 후 metadata가 존재하면 동일 provider를 사용한다. 원래 알려진 작업인지 D-1에는 몰랐던 D-day 작업인지는 개별 Runtime 예측 규칙을 바꾸지 않는다. 이번 감사에서는 아직 provider를 선택하지 않았다.'),
      ('D-day submission 전 unknown에 개별ML을 쓰는가?', '아니다. 개별 작업이 제출되기 전에는 그 작업 metadata에 근거한 individual Runtime ML을 적용하지 않는다.'),
      ('GPUh를 선택에 사용했는가?', '아니다. 입력은 fold/job_id/submit_time/runtime_seconds/q50/q90 여섯 열뿐이고, GPU weighting은 없다.'),
      ('Pinball을 main table에 쓰는가?', '아니다. MAE/C50/time ratio의3열은 오차·median calibration·시간 합을 구분하는 좋은 주 표이지만, 이3개만으로 채택을 판단하기에는 부족하다. 반드시 fold 안정성과 실제 tail burden 표를 함께 제공해야 한다. Q90 및 >12h Q90는 보조 열이다.'),
      ('May를 사용했는가?', '아니다. April 선택, May payload, CC4/V42 optimizer outcome도 사용하지 않았다.'),
      ('새 ML을 학습했는가?', '아니다. 추론조차 새로 하지 않았고 PR94 저장 VALID 예측의 산술만 계산했다. Conditional remaining도 바꾸지 않았다.'),
      ('PR94 NONE 판정을 바꿨는가?', '아니다. Q50+α(Q90−Q50) 규칙의 SELECTED_RUNTIME_MODEL=NONE, SELECTED_ALPHA=null과 원본 파일 모두 보존했다. 이번 nominal 인터페이스의 질문은 별개다.'),
      ('PRIMARY_NOMINAL_RUNTIME_CANDIDATE는?', 'NONE. D2 extreme의 후보성은 연구 비교에 한정한다. PRIMARY_* 선택 지표는 null이며, 평가한 D2 extreme의 실제값은 comparison/FINAL_VERDICT의 audited_primary_metrics에 그대로 남긴다.'),
      ('다음 Planning reserve 설계로 넘어갈 수 있는가?', '별도 사전등록 설계 연구를 위한 입력과 위험 특성은 확보했다. D2 extreme을 포함한 동결 baseline으로 overrun과 Actual 점유를 검증하는 연구는 가능하지만, 이 감사가 기본 provider 채택·V42 통합·reserve 충분성을 승인하지 않는다. 다음 연구 전까지 기존 provider/PR94 판정을 유지한다.')]
    report='# 동결 Q50 보정 감사\n\n**PRIMARY_NOMINAL_RUNTIME_CANDIDATE=NONE**. Q50을90% 상한으로 요구하지 않았고, 신규 수치 PASS cutoff도 만들지 않았다. D2 extreme의 비교 장점과 시간/fold/꼬리 부담을 함께 검토한 정성적 결론이다. PR94의 별도 scalar-duration NONE 판정은 그대로다.\n\n'+table+'\n## D2 extreme의 temporal fold\n\n'+foldtable+'\n'
    report+='\n\n'.join(f'## {i}. {q}\n\n{a}' for i,(q,a) in enumerate(qa,1))+'\n'
    (ROOT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf-8')
    (ROOT/'README.md').write_text('# Frozen Q50 audit for nominal V42 scheduling\n\n6개 동결 모델의 동일230,237개 VALID 작업만 재평가했습니다. 모델 학습·추론·CAL 보정·reserve/headroom 계산·V42 실행은 없습니다. PR94의 scalar-duration NONE 결과를 대체하지 않습니다.\n\n'+table+'\nD2 extreme: C50 65.24%, 초과34.76%, fold40.64–77.83%, >12h C50 2.49%. 총시간1.347배만으로 안정적인 nominal provider라고 채택하지 않았습니다. **PRIMARY_NOMINAL_RUNTIME_CANDIDATE=NONE**이며 Pareto 연구 후보 지위는 남습니다.\n\n[한국어50항목 검토](FINAL_REVIEW_KO.md), [사전등록](PREREGISTRATION.json), [공통 population 재검증](COMMON_POPULATION_RECHECK.json), [검증](VERIFICATION.json)을 참조하세요. Coverage는[0,1] 단위 CSV이며 표에서는%입니다. Calibration error/std의 pp 표시와 fraction을 구분합니다. Actual-runtime bucket은 결과 진단이며 각 bucket에서50%를 요구하는 calibration test가 아닙니다.\n\n의도된 향후 구조: Planning=total Q50+별도 overrun reserve; Actual=관측 RUNNING gang의 실제 점유 유지, PENDING 시작 전 현재 capacity 확인, duplicate reserve 없음. 제출된 D-day 작업도 같은 provider 개념이며 제출 전 unknown 개별 작업 예측은 하지 않습니다. 이번에는 구현하지 않았습니다.\n\n재현 순서: exact NumPy/pandas 환경과 PR94 SHA-bound 로컬 VALID 파일에서 `preregister.py` → `audit.py` → `finalize.py` → `test_audit.py` → `verify.py`. 기존 사전등록을 덮어쓰지 않습니다. Public Git 파일은 DELIVERY_MANIFEST, 로컬 로그는 LOCAL_EVIDENCE_MANIFEST로 묶었습니다.\n',encoding='utf-8')
if __name__=='__main__':main()
