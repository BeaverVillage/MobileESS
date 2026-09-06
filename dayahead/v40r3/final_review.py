"""Render the final Korean research record from frozen experimental artifacts."""
from .common import *
from .train import ALL_NAMES,DEEP_NAMES,load
from .evaluate import REPORT_NAMES

def link(name,label=None):
    return f'[{label or name}](<{(OUT/name).as_posix()}>)'

def main():
    reg,commit,a,info,m=load()
    selection=read('V40R3_METHOD_SELECTION.json');tests=read('V40R3_TEST_REPORT.json')
    assert tests['passed']==60 and tests['failed']==tests['errors']==tests['not_run']==0
    reports={n:read(f'V40R3_{REPORT_NAMES[n]}_REPORT.json') for n in ALL_NAMES}
    c=reports['CMABF']['evaluation'];raw=reports['CMABF']['raw_evaluation']
    bootstrap=read('V40R3_PAIRED_BOOTSTRAP_SUPERIORITY.json')
    monthly=read('V40R3_MONTHLY_METRICS.json')['models'];det=read('V40R3_DETERMINISM_REPORT.json')
    runs=read('V40R3_TRAINING_RUN_LEDGER.json');cover=read('V40R3_TARGET_POPULATION_COVERAGE_AUDIT.json')
    jobs=pd.read_parquet(OUT/'GPU_related_candidates_preMay.parquet',columns=['model_cohort','submit_time','work_GPUh'])
    inside=jobs.model_cohort & jobs.submit_time.ge(info.target_start.min()) & jobs.submit_time.lt(info.target_end.max())
    targetjobcount=int(inside.sum());targetwork=float(jobs.loc[inside,'work_GPUh'].sum())
    assert abs(targetwork-np.load(OUT/'causal_dataset.npz')['target'].sum())<1e-6
    dump('V40R3_TARGET_WINDOW_POPULATION.json',{'decoded_cohort_jobs':cover['modeled_jobs'],
        'jobs_in_349_operating_day_targets':targetjobcount,'GPUh_in_349_operating_day_targets':targetwork,
        'target_start_UTC':str(info.target_start.min()),'target_end_UTC':str(info.target_end.max()),
        'distinction':'548339 is contract-eligible cohort in decoded raw coverage, including history outside forecast target days; this artifact gives exact jobs contributing to the 349 target days'})
    lines=[
      '- 최종 분류: **V40R3_FUTURE_GPUWORK_SAFETY_FAIL**',
      '- 선택 모델: **없음**',
      '- CMABF: **FAIL**',
      '- CMABF 종합 우위: **NO**. 사전 고정 DeepAR와의 한 쌍 비교에서는 CI가 양수이나, 안전성과 모든 기준모델 대비 우위를 충족하지 못했다.',
      '- 최강 기준모델: **DEEPAR**(개발 기간에 고정한 bootstrap 비교 대상). 평가의 비영 기준모델 중 primary 최소는 HURDLE_LIGHTGBM이지만 역시 안전 FAIL이다.',
      '- untouched confirmation: **NO**',
      '',
      'V40R2는 사용자 중단 실험으로 **SUPERSEDED_BY_V40R3** 상태를 유지한다. V40R3에서 R2 실행 재개·model fitting·코드 merge/reuse·파일 수정·삭제를 하지 않았다. R2의 direct future-active-GPU estimand를 사용하지 않았다. 새 타깃·코호트·특징·모델을 R3 계약에서 독립 생성했다.',
      '',
      '**1. Forecast origin.** 운영일 D의 전날 18:00 고정 AEST(UTC+10), 즉 D−1 08:00 UTC. D 00:00부터 다음 날 00:00까지 예측하며 첫 도착 구간은 발행 시각보다 6시간 뒤 시작한다.',
      '',
      '**2. Slow-layer interval.** 권위 계약의 slow scheduling grid는 30분, 사건 관측은 5분, 최대 refresh는 30분이다. 원래 보존식은 B[k+1]=B[k]+ΔW[k]−S[k]이며 도착 이전 수요를 처리할 수 없다. 기존 H100-equivalent GPUh와 R3의 원시 GPUh는 변환 없이 동일시하지 않는다. '+link('V40R3_DOWNSTREAM_WORKLOAD_CONTRACT_AUDIT.json','계약 근거'),
      '',
      '**3. Target population.** GPU_QUANTITY_AUTHORIZED_WORKLOAD_COHORT: 명시된 gpus_requested>0, 유효 submit/start/end, start≥submit, 양의 관측 서비스 시간. H100·non-standby·COMPLETED 상태를 강제하지 않았다. 원시 복원 4,728,595 jobs 중 GPU 관련 후보 790,173, 수량 권위 확인 550,123, 서비스 유효성 제외 1,784, 계약 적격 548,339 jobs이다.',
      '',
      '**4. GPU missing.** 240,050 jobs를 제외했다. NULL→0, nodes×4, partition 기반 GPU 수량 추정을 하지 않았다. 알 수 없는 GPUh 분모 때문에 전체 시설 GPUh 커버리지는 식별 불가(null)이다.',
      '',
      f'**5. Coverage.** 복원 범위 적격 jobs는 후보의 {cover["modeled_fraction_of_candidates"]:.2%}, 전체 원시 jobs의 {cover["modeled_fraction_of_raw_jobs"]:.2%}이다. 실제 349개 타깃 운영일에는 {targetjobcount:,} jobs, {targetwork:,.3f} GPUh가 기여한다. 333일에는 양의 도착 수요가 있다. 자원 필드 결측 및 관측 서비스 유효성이 선택 편향을 만들므로 all Kestrel workload로 일반화하지 않는다. '+link('V40R3_TARGET_POPULATION_COVERAGE_AUDIT.json','월별·partition·QoS·runtime·자원 분포'),
      '',
      '**6. Target formula.** w_j=g_j×(end_j−start_j)/3600 [GPUh]; ΔW_k=Σ_j w_j I(submit_j∈k). 전체 작업량을 submission 구간에 배정한다. 이는 요청 GPU 수량과 관측 wall-clock service duration의 곱인 서비스 수요 proxy이며 실제 활용률·FLOPs·고유 계산 복잡도·하드웨어 독립 작업량을 뜻하지 않는다. ML은 외생 도착 수요, optimizer는 나중에 내생 처리 시점을 담당한다.',
      '',
      '**7. Horizons/statistics.** 30분 비음수 증분 48개, 누적은 C_k=Σ_{i≤k}ΔW_i. 별도 누적 head는 없다. 30/60/120/240분 및 1,440분 누적 진단을 저장했다. 전체 16,752 intervals, zero 38.3238%, positive 61.6762%; 평균 113.6904, 중앙값 2.1089, P90/P95/P99=177.8390/397.4974/1,906.1280, 최대 53,461.3128 GPUh. TRAIN의 양수 Q95=441.777542 GPUh가 고정 burst threshold다. 전체 burst 734개(4.3816%), 평균 연속 지속 35.46분, lag-1/48/336 상관 0.04637/0.03843/0.00790. 일일 총량·시간대·요일·기간 이동은 사전 통계에 있다.',
      '',
      '**8. Causal features.** 23개 특징 유형(과거 8 + 미래 달력/성숙 계절문맥 15), 과거 7일×336 positions, tree 입력 2,703개 열. 모든 모델에 동일 정보와 성숙 마스크를 제공했다. 제출 수, 성숙 GPUh, 성숙 여부·나이, 달력, 7/14/21/28일 동일 시간대 성숙 이력만 사용했다.',
      '',
      '**9. Removed leakage and F30.** 기존 177-feature matrix를 상속하지 않았다. V40P에서 보고된 70 FUTURE_LEAKAGE 및 20 ambiguous features는 역사적 진단이며, R3는 새 ledger에서 23유형을 허용하고 16유형을 거부했다. request-resource/QoS/partition은 submit-time 버전 권위가 없어 predictor에서 제외했다. 미래 submit/start/end, 미완료 작업의 최종 runtime, 최종 queue/status, target actual, R2 결과도 거부했다. **LEGACY F30: actual runtime≥30m AND actual queue wait≥15m는 소급 정의여서 제거했다.** 짧은 작업과 즉시 시작한 작업도 R3 cohort에 들어간다. 양의 runtime 및 완료 관측은 label 구성 유효성 조건이며 flexibility 분류기가 아니다. 이 코호트만으로 실제 작업의 지연·중단 가능성까지 인증하지 않는다.',
      '',
      '**10. Label maturity.** target_label_available_at=max(타깃 일/구간 종료, 기여 jobs의 최종 end). 빈 구간을 미리 아는 문제를 막기 위해 구간 종료 하한을 추가했다. 각 단계 cutoff 이전 성숙 label만 사용: train 2일, development 2일, calibration 3일 제외. 과거 특징은 해당 bin의 모든 원시 제출 작업 종료를 확인하는 더 보수적인 마스크를 사용하고, 미성숙 GPUh=0 placeholder와 mask=0을 함께 전달한다. 성숙 전 실제 GPUh를 바꿔도 입력이 불변임을 검증했다. 아카이브의 논리적 event-time 재구성이며 운영 telemetry 수집 지연까지 인증한 것은 아니다.',
      '',
      '**11. Frozen split.**',
      '',
      '| 역할 | 운영일 | 전체 / 성숙 적격 일수 |',
      '|---|---|---:|',
      '| TRAIN | 2024-03-15–2024-08-30 | 169 / 167 |',
      '| DEVELOPMENT | 2024-09-01–2024-10-30 | 60 / 58 |',
      '| CALIBRATION | 2024-11-01–2024-11-29 | 29 / 26 |',
      '| EXPOSED_EVALUATION | 2024-12-01–2025-02-26 | 88 / 88 |',
      '',
      'Purge는 2024-08-31, 10-31, 11-30이다. Training/selection/calibration cutoffs는 각각 08-31/10-31/11-30 08:00 UTC. Random split은 없다. K5/V40P/R/R2 이력에 노출된 기간을 untouched holdout으로 재명명하지 않았다. 최대 긍정 표현은 PREVALIDATED이나 이번 결과는 SAFETY_FAIL이다.',
      '',
      '**12. All benchmark results.** 아래는 공통 등록 calibration 이후, 동일 노출 평가 88일·4,224구간·양수 2,839구간·burst 240구간이다. Primary=양수 구간 Q90 pinball 합/실제 GPUh 합(낮을수록 좋음). WAPE와 coverage는 %. ZERO는 등록대로 보정하지 않았다.',
      '',
      '| 모델 | Primary | 양수 WAPE | Q90 전체 coverage | 양수 coverage | burst coverage | 1월 burst coverage | 안전 |',
      '|---|---:|---:|---:|---:|---:|---:|---|',
    ]
    for name,r in reports.items():
        e=r['evaluation'];p=e['probabilistic'];j=monthly[name]['2025-01']['probabilistic']['burst']
        lines.append(f'| {name} | {p["primary_positive_Q90_normalized_pinball"]:.6f} | {100*e["point"]["positive"]["WAPE"]:.2f} | {100*p["overall"]["Q90_coverage"]:.2f} | {100*p["positive"]["Q90_coverage"]:.2f} | {100*p["burst"]["Q90_coverage"]:.2f} | {100*j["Q90_coverage"]:.2f} | FAIL |')
    lines += ['',
      '모든 비영 후보는 pooled coverage 기준을 통과했지만 1월 burst coverage에서 실패했다. ZERO는 전체·양수·burst gate 모두 실패한다. 어떠한 후보도 월별 WAPE>200% catastrophic gate에 걸리지는 않았다. 12월 burst N=61, 1월 N=114, 2월 N=65로 등록 규칙상 월별 burst gate는 1월에 적용된다.',
      '',
      '| 모델 | 전체 MAE | 전체 RMSE | 전체 WAPE % | 전체 bias | 양수 MAE | 양수 bias | Q90 pinball 전체 / 양수 / burst |',
      '|---|---:|---:|---:|---:|---:|---:|---|']
    for name,r in reports.items():
        e=r['evaluation'];p=e['point'];q=e['probabilistic']
        lines.append(f'| {name} | {p["overall"]["MAE"]:.3f} | {p["overall"]["RMSE"]:.3f} | {100*p["overall"]["WAPE"]:.2f} | {p["overall"]["bias"]:.3f} | {p["positive"]["MAE"]:.3f} | {p["positive"]["bias"]:.3f} | {q["overall"]["Q90_pinball"]:.3f} / {q["positive"]["Q90_pinball"]:.3f} / {q["burst"]["Q90_pinball"]:.3f} |')
    lines += ['',
      '**13. CMABF result/architecture.** 독립 dual-stream TCN(32 hidden, causal dilation 1/2/4/8, kernel 3), gated fusion, shared multi-horizon decoder, 발생 확률과 양수 quantile grid를 사용했다. Q90은 mixture inverse CDF로 계산하며 p×positive_Q90이 아니다. Loss는 BCE 1 + 평균 Q50/Q90 pinball 1 + positive-grid pinball 0.2 + burst-weighted Q90 0.25; burst weight=1+min(y/Q95_train,3). 안전 FAIL이며 논문 proposed-model 우위를 입증하지 못했다.',
      '',
      f'**14. Positive WAPE.** CMABF {c["point"]["positive"]["WAPE"]:.4%}; 전체 WAPE {c["point"]["overall"]["WAPE"]:.4%}. 기존 K5B2 약 100% WAPE와 burst 실패는 다른 타깃의 역사적 진단이며 동일 조건 baseline 수치로 재사용하지 않았다.',
      '',
      f'**15. Q90 pinball.** CMABF 전체 {c["probabilistic"]["overall"]["Q90_pinball"]:.6f}, 양수 {c["probabilistic"]["positive"]["Q90_pinball"]:.6f}, burst {c["probabilistic"]["burst"]["Q90_pinball"]:.6f} GPUh; primary {c["probabilistic"]["primary_positive_Q90_normalized_pinball"]:.9f}. 보정 전 primary {raw["probabilistic"]["primary_positive_Q90_normalized_pinball"]:.9f}, burst coverage 0%였다. 등록한 max(overall/positive/burst 잔차 Q90,0) 보정이 Q90에 {reports["CMABF"]["calibration"]["additive_Q90_delta_GPUh"]:.6f} GPUh를 더했다. 그 결과 pooled coverage는 높아졌으나 과대 예측 손실이 커졌다. 모든 비영 모델의 보정 후 primary는 ZERO 0.9보다 나쁘다. 높은 coverage를 정확한 명목 Q90 보정이나 우수한 sharpness로 해석하지 않는다.',
      '',
      f'**16. Overall Q90 coverage.** CMABF {c["probabilistic"]["overall"]["Q90_coverage"]:.4%}; 절대 calibration error {100*c["probabilistic"]["overall"]["calibration_error"]:.4f} percentage points.',
      '',
      f'**17. Positive Q90 coverage.** CMABF {c["probabilistic"]["positive"]["Q90_coverage"]:.4%}; 절대 calibration error {100*c["probabilistic"]["positive"]["calibration_error"]:.4f} percentage points.',
      '',
      '**18. Burst Q90 coverage.** CMABF pooled 219/240=91.25%는 통과했지만 2025-01은 102/114=89.4737%로 90% gate 실패다. 월별 실패를 pooled 성적으로 덮지 않았다.',
      '',
      f'**19. Missed burst GPUh.** CMABF {c["burst"]["missed_burst_GPUh"]:,.6f} GPUh; captured fraction {c["burst"]["captured_burst_GPUh_fraction"]:.4%}, burst당 평균 부족 {c["burst"]["underprediction_GPUh"]:.6f} GPUh. 최악은 2024-12-30 slot 7: actual 22,570.465, Q90 5,020.475, miss 17,549.990 GPUh다. 큰 폭발 수요가 남았다.',
      '',
      f'**20. Cumulative WAPE.** CMABF Q50 증분합의 누적 WAPE {c["cumulative"]["WAPE"]:.4%}, 누적 MAE {c["cumulative"]["MAE_GPUh"]:,.6f} GPUh. Q90 증분합의 최대 누적 underforecast는 보정 후 0이지만, 각 구간에 큰 보정량을 더한 결과이며 실제 누적량의 90% quantile 보장을 의미하지 않는다.',
      '',
      f'**21. Daily total error.** CMABF 일일 총량 MAE {c["cumulative"]["daily_total_MAE_GPUh"]:,.6f} GPUh, bias {c["cumulative"]["daily_total_bias_GPUh"]:,.6f} GPUh, 일일 총량 WAPE {c["cumulative"]["compatibility_horizons"]["1440"]["WAPE"]:.4%}.',
      '',
      '**22. Horizon crossing.** 모든 후보의 최종 Q50/Q90 증분은 비음수, 누적 horizon crossing=0, 최종 quantile crossing=0. 등록된 Q90=max(Q90,Q50) projection 이전 crossing은 각 fit report에 보존했다. 두 marginal quantile만으로 CRPS를 식별할 수 없어 계산하지 않았다.',
      '',
      '| 모델 | Missed burst GPUh | 누적 WAPE % | 일일 MAE GPUh | 일일 bias GPUh |',
      '|---|---:|---:|---:|---:|']
    for name,r in reports.items():
        e=r['evaluation'];cu=e['cumulative']
        lines.append(f'| {name} | {e["burst"]["missed_burst_GPUh"]:.3f} | {100*cu["WAPE"]:.2f} | {cu["daily_total_MAE_GPUh"]:.3f} | {cu["daily_total_bias_GPUh"]:.3f} |')
    lines += ['',
      '**23. Strongest baseline.** DEVELOPMENT 안전 통과 기준모델이 없어서 등록된 fallback ranking으로 DEEPAR를 고정했다. 평가/보정 결과를 보고 HURDLE_LIGHTGBM 등으로 bootstrap 상대를 바꾸지 않았다. 최종 수치상 ZERO·HURDLE_LIGHTGBM·TFT·NHiTS가 CMABF보다 primary가 낮으며, CMABF의 every-benchmark numeric superiority는 NO다.',
      '',
      f'**24. Paired bootstrap.** 같은 88일을 묶은 circular 7-day block, 5,000회, seed {SEED}. Δ=DeepAR−CMABF={bootstrap["delta"]:.9f}, 95% percentile CI=[{bootstrap["CI95"][0]:.9f}, {bootstrap["CI95"][1]:.9f}], 상대 개선 {bootstrap["practical_improvement_percent"]:.6f}%. 특정 고정 비교대상에 대한 통계적 우위는 YES다. 비교대상 freeze SHA256={bootstrap["baseline_freeze_SHA256"]}. 두 모델 모두 안전 FAIL이고 CMABF가 전체 baseline을 이기지 못했으므로 종합 우위/논문 채택은 NO다. 노출 이력의 비교이며 untouched confirmatory 유의성으로 주장하지 않는다.',
      '',
      '**25. Ablation.** 등록한 세 가지 제거 실험만 실행했다. A0는 hard sanitation을 유지하고 maturity modeling mechanism만 제거하여 미래값을 의도적으로 누설시키지 않는다. 각 1설정+독립 재현, full CMABF의 선택 LR 사용, 주 모델 선택에는 사용할 수 없다.',
      '',
      '| 변형 | Primary | 양수 WAPE % | burst coverage % | 안전 |',
      '|---|---:|---:|---:|---|']
    for name,r in read('V40R3_CMABF_ABLATION_REPORT.json')['ablations'].items():
        e=r['metrics'];lines.append(f'| {name} | {e["probabilistic"]["primary_positive_Q90_normalized_pinball"]:.9f} | {100*e["point"]["positive"]["WAPE"]:.3f} | {100*e["probabilistic"]["burst"]["Q90_coverage"]:.2f} | FAIL |')
    lines += ['',
      'A0(no maturity mechanism)=2.198417은 full보다 primary가 낮았다. A1(no hurdle)은 point WAPE가 악화했고, A2(no burst weight)는 full과 거의 같았다. 이 노출 이력 결과는 full 설계의 모든 구성요소가 필요하거나 우수하다는 주장을 지지하지 않는다. 결과에 맞춰 구조·loss를 바꾸지 않았다.',
      '',
      '**26. Selection and interpretation.** 선택 모델 없음. safety-first 규칙상 어떤 모델도 적격이 아니다. causal target/feature/maturity/누적 단조성 계약을 구현했지만, 이번 등록 예산에서 안전한 예측 모델을 확보하지 못했다. calibration의 과대 보정과 월별 burst 실패를 성공으로 포장하지 않는다. 새로운 후보/보정 방법을 연구하려면 별도 preregistration이 필요하며 이 실험에는 반영하지 않았다.',
      '',
      '**27. May firewall.** V40R3의 2025년 May scientific target/runtime/status/Actual/train/calibration/selection/B0-B3 outcome reads=0. ZIP 이름·parquet footer·허용 code/config·git HEAD/status·V40P 해시의 metadata 접근은 NONZERO다. 2024년 5월은 금지된 2025년 5월과 구분했다. mixed row group은 decode 전 제외했고 완전 제출 범위는 2025-02-26 23:29:23 UTC 이전이다. V40P의 과거 broad-search 노출과 earlier R2 checkout incident를 지우지 않았다. clean-room/zero-metadata 주장은 하지 않는다. '+link('V40R3_MAY_FIREWALL.json','상세 firewall'),
      '',
      '**28. Production integration.** NO. Optimizer 연결, job scheduling, active-GPU trajectory 생성, 전기계수 재생성, B0-B3, Full May, V40S2 merge를 실행하지 않았다. background/fixed workload도 F30 complement로 재구성하지 않았다.',
      '',
      f'**29. Tests and compute.** Final {tests["passed"]}/{tests["tests"]} PASS, failures=0, errors=0, skipped=0. Prefit는 57 PASS와 학습 이후 검증 3개 대기였다. synthetic gradient 테스트는 optimizer/parameter update 없이 수행했다. 이 테스트 PASS는 과학적 안전성 PASS와 구별된다. '+link('V40R3_TEST_REPORT.json','테스트 목록'),
      '',
      'RTX 4060 Laptop GPU(cuda:0), PyTorch 2.8.0+cu128, CUDA runtime 12.8(드라이버 지원 최대 13.0과 구분), pytorch-forecasting 1.5.0을 사용했다. LightGBM 4.6.0/XGBoost 3.0.5는 CPU 4threads. 모든 주 ML 계열 2개 LR trials, deep 동일 batch 16/max40 epochs/patience8/min_delta1e-6/seed20260906/AMP off. deterministic_algorithms=True(warn_only), cuDNN deterministic=True, benchmark=False, TF32=False, CUBLAS :4096:8. 실제 epochs·선택 epoch·시간은 아래와 개별 logs에 있다. 총 27 configuration training runs(기본 탐색14+선택 설정 재현7+제거 실험3+재현3), ZERO/SEASONAL fits=0.',
      '',
      '| Deep model | 탐색 epochs (trial0 / trial1) | 선택 LR / epoch | 독립 재현 epochs | 탐색 합산 시간 s | 재현 시간 s |',
      '|---|---|---|---:|---:|---:|']
    for name in DEEP_NAMES:
        r=reports[name]['fit'];s=r['selected_trial'];rr=det['models'][name]['repeat_training']
        lines.append(f'| {name} | {r["trials"][0]["epochs_run"]} / {r["trials"][1]["epochs_run"]} | {s["learning_rate"]} / {s["selected_epoch"]} | {rr["epochs_run"]} | {sum(t["training_walltime_seconds"] for t in r["trials"]):.3f} | {rr["training_walltime_seconds"]:.3f} |')
    nh=det['models']['NHITS']
    lines += ['',
      f'모든 주 ML 모델과 제거 실험은 선택 설정으로 같은 고정 seed의 독립 학습을 총 2회(원본+재현) 수행했다. NHiTS에서 max/mean 차이 {nh["max_prediction_difference_GPUh"]:.6f}/{nh["mean_prediction_difference_GPUh"]:.6f} GPUh, 보정 평가 primary {nh["original_evaluation_calibrated_primary"]:.9f}→{nh["repeat_evaluation_calibrated_primary"]:.9f}(Δ={nh["evaluation_calibrated_primary_difference"]:.9f})를 관측했다. 양쪽 모두 safety FAIL이다. CUDA upsample backward의 비결정성 경고를 보존했다. 다른 후보는 값 차이가 0이지만 XGBoost/deep 원본 float64와 반복 float32 저장 dtype이 달라 바이트 동일성을 주장하지 않는다. LightGBM/hurdle만 이 두 실행에서 dtype/bytes까지 동일했다. 반복 중 좋은 결과를 고르지 않았다.',
      '',
      f'개별 timer 합 {runs["training_walltime_sum_seconds"]:.3f}초는 학습+개발 scoring+최종 inference+저장 시간이며, 병렬 CPU/GPU 실행 때문에 전체 경과시간과 동일하지 않다. '+link('V40R3_TRAINING_RUN_LEDGER.json','전체 실행·예산·시간 ledger')+' / '+link('V40R3_DETERMINISM_REPORT.json','재현 오차와 metric variation'),
      '',
      '**30. Protected scope and lineage.** 변경은 dayahead/v40r3/와 해당 R3 artifacts/ 두 namespace에 한정한다. V40P 고정 reference 188개와 모델 38개 해시가 일치했다. V40P/R/R2/S는 시작·종료 HEAD/status가 일치한다. V40S2는 별도 작업 중 HEAD/status가 바뀌었으며 R3의 수정이나 merge가 아니다. R2는 원래 untracked 자료를 포함해 보존했고 byte inventory를 처음부터 갖고 있지 않아 그 파일들의 bitwise 보존을 과장하지 않는다. R2 쓰기·삭제 0, 재학습 0, 소스 의존 0이다. '+link('V40R3_PROTECTED_SCOPE_DIFF.json','보호 범위 감사'),
      '',
      f'Start {START}; V40P scientific reference 3a6ab4fa369a9f8e16203af62b1b00bf56666716; branch codex/v40r3-causal-gpuwork-arrival-ml. 최종 사전등록 commit **{commit}**는 어떤 fitting보다 먼저 확정했다. 첫 등록 뒤 Windows CRLF/LF 해시 불일치를 학습 0회 상태에서 바로잡았고 그 기록을 보존했다. 이후 frozen source/data hashes는 모두 일치했다. 결과를 본 뒤의 수정은 np.array_equal 값/바이트 구분, pairwise/global superiority 구분 및 보고서/테스트의 표시 의미에 한정했다. 모델·예측·loss·split·threshold·예산·선택 결과는 바뀌지 않았다. '+link('V40R3_REPORTING_CORRECTIONS.json','표시 의미 정정 이력'),
      '',
      '**31. Holds.** production q=UNCHANGED; PF=0.95; Q control=NO; 31-day electrical regeneration=HOLD; B0/B1/B2/B3=NO; FULL_MAY=NO; optimizer=NO.',
      '',
      '사전 문헌 검토와 각 논문/공식 구현의 출처는 '+link('V40R3_SCI_BENCHMARK_REVIEW.md','문헌·benchmark 검토')+'에 있다. CMABF는 연구용 명칭이며 새로움이나 논문 모델 적격을 선언하지 않는다. 결과 및 최종 receipt commit은 '+link('V40R3_FINAL_COMMIT_RECEIPT.json','최종 commit receipt')+'로 연결한다.',
    ]
    (OUT/'V40R3_FINAL_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    (ROOT/'dayahead/v40r3/README.md').write_text('''V40R3 independently forecasts next-operating-day incremental arriving GPU-service demand.

Final classification: V40R3_FUTURE_GPUWORK_SAFETY_FAIL. No model selected. No production/optimizer integration.
V40R2 is SUPERSEDED_BY_V40R3; never resume, fit, import, merge, modify or delete it.

Authoritative preregistration commit: fbde550fee28065ad1b9946b430c1b3e69cefe42.
Frozen target/model/split/loss/metric code must not be edited to improve this completed experiment.
Detailed Korean results and provenance are in ../artifacts/v40r3_causal_gpuwork_arrival_ml/V40R3_FINAL_REVIEW.md.

Existing-run read-only-science verification (from this worktree, using the recorded isolated runtime):

    python -m dayahead.v40r3.final_audit
    python -m dayahead.v40r3.test_contracts --final
    python -m dayahead.v40r3.final_review

These commands write reporting/audit artifacts only and do not fit models. final_audit must follow evaluate
because it disambiguates intermediate array-value equality from byte identity and pairwise from overall
proposed-model superiority. The original frozen train/evaluate code and the original fit predictions remain
unchanged. Synthetic gradient tests never call optimizer.step.

Do not rerun initialize/preregister in this completed checkout. A separate explicitly scoped reproduction
must retain the original frozen contracts and preserve these results; use the exact environment and run
ledger, not the superseded V40R2 implementation. The confirmatory block is unavailable; exposed-history
evaluation and test passes are not production validation.
''',encoding='utf-8',newline='\n')
    print(json.dumps({'report':'V40R3_FINAL_REVIEW.md','target_jobs':targetjobcount,'target_GPUh':targetwork,
        'training_walltime_sum_seconds':runs['training_walltime_sum_seconds'],'tests_passed':tests['passed']}))

if __name__=='__main__':main()
