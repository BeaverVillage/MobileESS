# Runtime-vNext8 최종 검토

**결과는 부정적이다. 작업별 연구 예측기와 호출 패키지는 만들었지만 통과 모델은 없다. 기존 strict authority FALSE를 유지하고 V42 연구 통합도 승인하지 않는다.**

|모델|Q50 MAE(s)|Q90 coverage|>4h coverage|Q90 pinball|예약/실제 GPUh|W0 대비 예약|
|---|---:|---:|---:|---:|---:|---:|
|W0|40,397.1|94.53%|79.83%|4,057.5|4.3042|100.00%|
|B0|9,330.6|81.71%|73.34%|3,350.4|2.7739|64.45%|
|Bconst|11,318.2|95.67%|77.66%|7,615.6|4.1889|97.32%|
|V8|10,381.2|69.46%|37.62%|4,584.6|2.4227|56.29%|

## 1. 어떤 Kestrel raw/archive feature를 사용했는가?

GPU/nodes/cores/memory/walltime 요청 수치, QoS·partition·account 익명 토큰, array index/존재 descriptor를 사용했다. 파생 log·비율·곱·결측 indicator를 포함해 최종 진단 후보는29개 입력 열이다. 원본9종 입력 개념에서 만든 수이며9개 모두 strict하다는 뜻은 아니다. 모델 이름은 M3_F2다.

## 2. 어떤 feature를 제외했고 왜 제외했는가?

actual start/end/runtime, 상태, queue wait, 사용량, 미래 상태·checkpoint는 금지했다. submit hour/dow도 제외했다. user/name/submitline/script/workdir는 빈도·cardinality·chronological unseen screen에 탈락했다. job_type/python/reframe은 생성시점 불명확으로 제외했다. ID는 lookup에 쓰지 않는다.

## 3. strict causal feature=0과 research trace feature 사용은 어떻게 다른가?

PR78의 원본 제출 버전 authority와 strict 집합0은 그대로다. 사용자 지시에 따라 archive의 요청 descriptor를 연구용 proxy로 사용할 수 있지만, 원본 제출값 인증이나 production 승격으로 해석하지 않는다. provider는 Kestrel_trace_proxy와 strict FALSE를 반환하고 연구 opt-in을 요구한다.

## 4. Runtime target은 정확히 무엇인가?

초 단위 end_time-start_time이다. 큐 대기와 요청 walltime은 라벨에 포함하지 않았다. pre-April 원자료 시간차와 기존 normalized runtime_seconds의 유효 행 오차는0초다. suspension 등을 제외한 CPU busy time이나 여러 requeue attempt의 누적 실행시간이라고 주장하지 않는다. 잘못된 시간 순서는 제외, 관측된0초 실행은 유지했다.

## 5. 가장 좋은 feature family는 무엇인가?

고정된 다기준 선택 순위에서는 account·array를 추가한 F2의 M3가 진단 후보로 남았다. 단, 모든 predictive gate를 통과한 최상위 모델은 없다. F2를 일반적으로 우수하다고 선언하지 않는다. F3와 제거 ablation도 pre-April에서만 수행했다.

## 6. requested walltime은 얼마나 유용했는가?

선택 후보의 walltime 관련 입력/정규화를 제거한 M2 대조군은 DEV pinball4504.2→5734.7, CAL_VALID1290.7→1647.0으로 악화됐다. walltime 정규화까지 함께 바뀌므로 순수 단일 변수 효과가 아니다. 요청시간이 실제시간이라는 뜻도 아니다.

## 7. GPU/nodes/cores/memory shape는 얼마나 기여했는가?

M3_F2에서 파생 shape를 제거하면 DEV pinball4504.2→4531.1, CAL_VALID1290.7→1359.4다. 기여는 작고 구간에 따라 다르며 인과 효과나 통계적으로 확실한 개선으로 단정하지 않는다. 기본 자원 수치는 유지하는 제거 실험이다.

## 8. QoS/partition/account/user는 도움이 되었는가?

scheduler와 account를 제거한 결과는 SELECTED_FAMILY_ABLATION.csv 및 FEATURE_SET_ABLATION.csv에 분리했다. DEV에서 scheduler 제거 시 coverage84.91%→54.98%로 악화됐다. account가 F2의 유일한 통과 identity다. user는 CAL_VALID unknown86.42%로 배제돼 기여를 주장할 수 없다.

## 9. workflow/script identity는 unseen 문제 때문에 쓸 수 있었는가?

최종 후보에는 넣지 않았다. 빈도20 이상 TRAIN mapping 기준 CAL_VALID unknown은 script99.86%, workdir99.61%, name96.44%, submitline96.18%다. 기존 공개 토큰 반복만으로 안정적인 새 작업 workflow identity를 보장하지 않는다. 역식별은 하지 않았다.

## 10. raw vs log-runtime target 중 무엇이 나았는가?

F2에서 M1 raw DEV pinball4834.1, M2 log5125.1로 raw가 낫지만 CAL_VALID는2574.8/2355.7로 log가 낫다. 어느 한 변환이 일관되게 우월하지 않았다. Q50과 장기 coverage도 별도로 비교했다.

## 11. walltime-relative target은 효과가 있었는가?

M3는 log((T+1)/(walltime+1))를 학습하고 exp(pred)×(walltime+1)-1로 복원한다. DEV/CAL_VALID pinball4504.2/1290.7과 예약 감소가 선택 순위에 도움이 됐지만, 최종 April undercoverage가 커서 유효성 검증에는 실패했다.

## 12. long-tail mixture는 효과가 있었는가?

M4는 P(T>4h) classifier와 short/long 각각6개 조건부 log-quantile로 CDF mixture를 구성했다. 구간이 분리되어 있어 일반 이분법 대신 동일한 mixture inverse를 직접 계산했다. F2 DEV pinball5248.9, 장기 coverage79.30%로 목표를 충족하지 못했다. M5는 상위 두 가족 오차 상관0.961이 사전 조건0.95 미만을 만족하지 않아 제외했다.

## 13. 최종 Q50/Q90 성능은?

April mature49,712행에서 Q50 MAE 10,381.2초, Q90 pinball 4,584.6다. B0의 MAE 9,330.6초와 pinball 3,350.4보다 악화됐다. 이는 frozen 진단 후보의 결과이며 통과 모델 성능이라고 쓰지 않는다.

## 14. 전체 Q90 coverage는?

69.46%로 사전88–92% 기준을 실패했다. DEV84.91%, CAL_VALID99.24%에서도 구간 간 안정성이 부족했다.

## 15. >4h Q90 coverage는?

April9,628행에서37.62%로 사전85% 최소 기준에 크게 못 미친다. B0는73.34%, Bconst는77.66%다.

## 16. GPU-weighted long-job 성능은?

장기 작업의 GPU 가중 coverage는43.30%, underprediction은56.70%다. 자원 가중치를 적용해도 장기 보호 실패다.

## 17. reservation/actual GPUh ratio는?

900초 올림을 적용한 V8=2.4227, W0=4.3042, B0=2.7739다. 연속시간 비율과 별도 저장했으며 vNext6의 unrounded 수치를 그대로 비교하지 않았다.

## 18. W0보다 얼마나 reservation을 줄였는가?

43.71% 감소했다. Q90/장기/queue gate를 실패했으므로 안전하거나 실용적인 개선으로 인정하지 않는다.

## 19. B0보다 실제로 개선됐는가?

종합적으로 아니다. pre-April pinball/예약에서 일부 개선이 있었지만 DEV Q50은 악화되고 장기 underprediction도 나빠졌다. 잠금 April에서도 MAE·pinball·coverage가 악화됐다. 예약 감소 하나로 승격하지 않았다.

## 20. 개선 차이 uncertainty는?

제출 UTC일 단위 paired1000회 bootstrap을 사용했다. DEV pinball 차이(V8−B0)−268.6초의95% CI는[−1811.3,1475.6]으로0을 포함한다. DEV MAE 차이+3365.0초 CI[930.6,6065.1]은 악화다. CAL_VALID는3일뿐이므로 interval을 강한 일반화 증거로 볼 수 없다. 4개 요구 지표의 전체 CI는 PAIRED_UNCERTAINTY.csv에 있다.

## 21. April2 start<H는 W0/B0/V8 각각 몇 개인가?

동일 v6 기준의 예약 ledger에서150/47/111건이다. 세 arm 모두2340건 admitted. W0의 site/start를 원래 reference와 정확히 재현했다.

## 22. vNext6의150→0 악화는 해소됐는가?

0건 collapse 자체는111건으로 완화됐지만 W0의150건보다39건 적다. 따라서 운영 개선 gate는 FALSE다. 별도 현재-slot dispatch stress는 모든 arm841건으로, 예약 ledger와 다른 정책이며 그 수치로 실패를 감추지 않는다.

## 23. checkpoint total-minus-elapsed는 충분한가?

아니다. mature 작업의 모든30분 checkpoint299,805개에서 remaining MAE31,067.7초, overrun checkpoint32.76%다. 15분/30분/1h/2h/4h 분류와 장기 실행집단도 보고했고 vNext6 Bconst와 비교했다.

## 24. 별도 remaining/survival model이 필요한가?

INCONCLUSIVE다. 먼저 total-runtime 모델이 충분히 좋아져야 한다는 조건을 통과하지 못했다. subtraction 실패만으로 survival 필요를 TRUE로 선언하거나 이번 작업에서 추가 학습하지 않았다.

## 25. overrun semantics는 안전한가?

계약 unit 검증은 PASS다. RUNNING이고 elapsed≥plan이면 GPU를 유지하고900초씩 연장, 강제 종료하지 않으며 STAY를 반환한다. 별도 causal stress에서 capacity violation0, extension은 W0/B0/V8=209/1014/1995다. 이는 배경332개 예약을 고정한 제한된 재생이며 전체 V42 운영 안전 인증은 아니다.

## 26. CPU/GPU 어느 backend가 적합한가?

이 workload에서는 CPU4 threads가4.43초로 CPU single11.78초, OpenCL GPU6.67초보다 빨랐다. 비교 예측 오차0이었다. CPU 단일 추론 P99=10.78ms. OpenCL 기본 장치로 실행했으며 장치명 runtime 로그를 남기지 않아 RTX4060 귀속은 아래 장치 감사 한계에 따라 정적 추정으로 표시한다.

## 27. 새 job inference가 재학습 없이 가능한가?

가능하다. CPU provider의 predict_total(job_record,event_time=None)가 Q50/Q90·버전·Kestrel_trace_proxy를 반환한다. 새 job ID 치환 불변성, unknown category0, 금지된 outcome key 거부, 직렬화 예측 오차0을 확인했다. callable이라는 사실은 성능 승격을 뜻하지 않는다.

## 28. April/May tuning은 있었는가?

없다. target·membership·피처/맵·모델·보정·gates·provider bytes를3개 freeze로 고정한 뒤 April raw 파티션을1회 열었다. 후속 코드는 평가·문서·무학습 장치 감사뿐이다. May 파티션은 열지 않았고 April 행의 cutoff 이후 end는 라벨 산술 전에 가렸다.

## 29. V42 research provider로 사용할 수 있는가?

검증된 V42 research provider로 채택할 수 없다. TRACE_DESCRIPTOR_RUNTIME_MODEL_VALIDATED=FALSE 및 V42_RESEARCH_RUNTIME_PROVIDER_READY=FALSE다. 재현 가능한 진단 패키지만 보존했고 V42 코드/논문/기존 모델을 수정하지 않았다.

## 30. 논문 provenance limitation은 무엇인가?

익명 요청 descriptor를 이용한 trace 연구라고 밝혀야 한다. 공개 trace가 모든 값의 immutable initial submission version임을 확인할 request-version 이력을 제공하지 않는다는 제한이 필수다. 검증되지 않은 연구 후보의 결과를 production-certified scheduler 입력 모델이라고 쓰면 안 된다.

## 범위와 해석

TRAIN222,182, DEV11,486, CAL_FIT5,438, CAL_VALID14,623행은 vNext6 mature membership와 해시까지 일치한다. DEV/CAL_FIT/CAL_VALID unresolved495/498/13건은 라벨로 쓰지 않았다. April51,499행 중1,787건은 unresolved로 제외했다. 성공 COMPLETED 작업만의 모델이 아니며 종료된 실패·취소 작업도 실행시간 라벨에 포함될 수 있다. 종료 cutoff에 의한 maturity selection과 archive request-version 불확실성을 유지한다.

MODEL_SELECTION_FREEZE의 selected_qualified_model은 FALSE다. 필수 잠금 평가를 마치기 위해 사전 순위의 한 **진단 후보**만 직렬화했다. FAILED 후보를 성능 통과로 선택했다는 뜻이 아니다. TOTAL_RUNTIME_MODEL_SELECTED도 qualified 의미로 FALSE다.

장기 gate는 actual>4h를 **평가 층화**에만 쓴다. inference에는 실행/종료/라벨이 들어가지 않는다. M4 TRAIN의 장기 label은 classifier의 정상 학습 타깃이며 새 job의 actual 장기 여부를 입력으로 주지 않는다. CAL_FIT residual로 DEV에 보정값을 적용한 행은 소급적 진단이고 사전 DEV gate는 raw prediction이다.

F3 pruning은 pre-April DEV 두 시간구간에서 양의 group permutation 중요도를 요구했다. 추가 selected-family ablation은 후속 진단이며 재선택에 쓰지 않았다. M5는 고정된 complementarity 조건에 탈락했다. 대규모 search, 별도 remaining·survival·neural 모델은 없다.

## 최종 flags

```json
{
  "STRICT_CAUSAL_FEATURE_COUNT": 0,
  "REQUEST_VERSION_AUTHORITY_FOUND": false,
  "RESEARCH_TRACE_FEATURE_COUNT": 29,
  "OUTCOME_LEAKAGE_FOUND": false,
  "TARGET_RUNTIME_AUTHORITY_PASS": true,
  "TOTAL_RUNTIME_MODEL_SELECTED": false,
  "FROZEN_DIAGNOSTIC_CANDIDATE_SELECTED": true,
  "Q50_MODEL_VALIDATED": false,
  "Q90_MODEL_VALIDATED": false,
  "OVERALL_Q90_CALIBRATION_PASS": false,
  "LONG_JOB_Q90_GATE_PASS": false,
  "HIGH_GPU_GATE": "INSUFFICIENT_SUPPORT",
  "RESERVATION_SHARPNESS_PASS": false,
  "RESERVATION_REDUCTION_PASS": true,
  "APRIL_QUEUE_REPLAY_COMPLETED": true,
  "APRIL_QUEUE_REPLAY_IMPROVED": false,
  "CHECKPOINT_SUBTRACTION_VALIDATED": false,
  "REMAINING_RUNTIME_MODEL_RESEARCH_NEEDED": "INCONCLUSIVE",
  "TRACE_DESCRIPTOR_RUNTIME_MODEL_VALIDATED": false,
  "V42_RESEARCH_RUNTIME_PROVIDER_READY": false,
  "STRICT_CAUSAL_RUNTIME_PROVIDER_READY": false,
  "APRIL_USED_FOR_SELECTION": false,
  "MAY_USED_FOR_SELECTION": false,
  "ONLINE_REFIT_REQUIRED": false,
  "NEW_JOB_CALLABLE": true,
  "CAPACITY_SAFETY_PASS": true,
  "OVERRUN_CONTRACT_PASS": true,
  "selected_diagnostic_candidate": "M3_F2",
  "calibration": "NONE",
  "reason": "No pre-April eligible challenger; locked April fails calibration, long-job safety, B0 accuracy/pinball and W0 queue utility. Keep diagnostic package, reject research integration.",
  "production_certified": false,
  "prior_vNext7_rewritten": false,
  "created_at": "2026-09-28T12:39:31.322730+00:00"
}
```

세부 근거는 MODEL_COMPARISON.csv, SELECTED_FAMILY_ABLATION.csv, CALIBRATION_COMPARISON.csv, PAIRED_UNCERTAINTY.csv, APRIL_LOCKED_RUNTIME_METRICS.csv, APRIL_WALLTIME_VS_RUNTIME_QUEUE_REPLAY.csv와 SOURCE_MANIFEST.json에 보존했다. 원본 gate·provider bytes의 사후 불변성은 VERIFICATION.json으로 검증한다.
