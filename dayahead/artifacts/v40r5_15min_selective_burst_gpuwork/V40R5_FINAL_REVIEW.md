FINAL CLASSIFICATION: **V40R5_BODY_FORECAST_INSUFFICIENT**

SELECTED MODEL: **NONE**

BODY MODEL: **PB1 / BC0** (선택 실패 시 거부된 진단 모델)

BURST CLASSIFIER: **C3**

BURST THRESHOLD: **240.441055556 GPUh**

ETA: **0.0163896139711**

ROBUST ENVELOPE: **R0**

TRUE CONFIRMATORY: **NO**

OPTIMIZER INTEGRATION: **NO**

PRODUCTION READY: **NO**


R5는 원래 job 제출 시각으로 15분 × 96 타깃을 재구성하고 BODY 예측·burst 감지·robust abstention을 시험했다. 모든 수치는 이미 노출된 과거 구간의 진단이다. 실패한 pipeline의 adapter 행은 proposal_only=True, scientifically_selected=False, optimizer_use_allowed=False로 보존한다.

**1. 계보.** R5 base/R4 receipt=ff1fec3a7d8f80b3c2af496758747fafc04bad7b; R4 research=a925a34848458b07b2a07a43b1150c89c21425b9; R4 prereg=f10187e0b0cbaadde5b28186e70822f5ff258f76; R4 development baseline=1a178ceba65a4bf830c6e0955effb4838d922f3f. R3 receipt=43710c96c36f7e66257885a56ef6df697b3c53bb, R3 scientific=6e2f0791952a9001d2fdd4a6564e0f699ec3fc90. R5 prereg=9e77df9e3d607c2b1ef3ee9a6f18fe21b653634e; CAL-selection commit=2917efa8a3b56b2bc0b897574009eb96df3cd526. PR27 HEAD snapshot=a2a21c904535125c66668a294f91d73a66f5d4a7 (metadata/source-contract read only).

**2. 보호 범위.** R3 234파일 + R4 201파일의 시작/종료 byte hash가 동일하다. 보호 경로 diff=0. R2 SUPERSEDED_BY_V40R3, R3/R4 FAIL 분류 유지. PR27 merge 없음.

**3. 타깃 모집단.** raw recovered 4,728,595(부모 provenance; 재스캔 없음), GPU candidates790,173, authorized550,123, service-validity 제외1,784, eligible548,339, missing-GPU 제외240,050, target contributors545,553, target days349. 미래 미제출 작업의 외생 arriving GPU-service demand이며 실제 execution occupancy나 FLOPs가 아니다. F30·GPU결측 대입 없음.

**4. 총 GPUh.** 1,904,541.778333333554. 각 작업 g×(end−start)/3600 전량을 submit 구간에 배정했다.

**5. 구간 수.** 33,504=349×96. D−1 18:00 fixed AEST=D−1 08:00 UTC 발행, 다음 D일00:00–24:00 fixed AEST, [start,end) 경계다.

**6. 15→30 재구성.** 모든16,752쌍 최대 차이=2.91038304567e-11 GPUh, 허용오차1e-7. 30분 label 반분이나 오차를 맞추는 사후 보정 없음. Event table의 datetime64[us,UTC]를 ns UTC로 정규화하고 정확한 경계를 검증했다.

**7. AEMO.** 현재 PR의 mean-power 중복 규칙 P15a=P15b=P30을 source-only로 확인했고 합성 power의 energy 보존 오차0. R4 승인 feature에 AEMO가 실제로 없어 새 AEMO feature/payload를 추가하지 않았다. 에너지 quantity에 power 중복 규칙을 적용하지 않는다.

**8. Feature authority.** 61개: 기존30분 causal history의36개 요약+4개 마지막 값, 순수15분/calendar9개, 직접 재구성한15분 seasonal GPUh/count/maturity12개. Classifier는 여기에 예측 count mean/log 및 large-count probability2개를 사용한다. 새 외부 source 없음.

**9. 성숙도·인과성.** Parent184,272 proof rows와 새134,016 seasonal proof rows, feature별 ns availability matrix를 검사했다. Historical15분 child는 부모30분 구간의 모든 raw END가 성숙한 경우만 허용하는 보수적 규칙이다. 미래 count/resource/start/end/runtime feature 없음. Origin+5/+15분 leakage 없음. 실제 telemetry ingestion delay/version-history 인증은 범위 밖이다.

**10. 15분 분포.** Mature TRAIN N=16,032, zero=50.9481%, positive=49.0519%, mean=37.168208, median=0.000000, P90=38.743111, P95=97.385000, P99=661.907572, max=8753.507778 GPUh.

**11. Count 과분산.** TRAIN mean=21.035117, variance=3583.102191, variance/mean=170.339064, zero=50.9481%. NB는 Poisson보다 낮은 BIC이며 ZINB 추가 zero는 경계에 가깝다.

**12. Severity.** TRAIN jobs=337,235, mean=1.766960, median=0.057778, P95=2.506750, P99=36.212556, max=6145.208889 GPUh. N15–mean severity Spearman=-0.364994. 새 EVT fit 없음.

**13. 새 burst 기준.** Strict DeltaW15>240.441055556 GPUh. TRAIN 양수Q95로 고정했고 R4의441.777542를 재사용하지 않았다.

**14. Burst prevalence.** TRAIN 전체15분 구간의 2.4576%; EXPOSED_EVALUATION은 418/8448=4.9479%.

**15. Baselines.** 모두15분 재학습. 표는 개발 단계에서 고정한 raw pipeline이다.

| 모델 | Primary | 전체 coverage | 양수 coverage | burst coverage | 안전 |
|---|---:|---:|---:|---:|---|
| B0 | 0.900000 | 45.64% | 0.00% | 0.00% | FAIL |
| B1 | 0.873658 | 79.29% | 61.89% | 10.05% | FAIL |
| B2 | 0.748991 | 87.55% | 77.09% | 1.44% | FAIL |
| B3 | 0.738999 | 87.14% | 76.35% | 2.87% | FAIL |

**16. BODY 모델.** PB1 Hurdle LightGBM / BC0. 모델 trial은 DEV oracle BODY에서, BC0/BC1과 최종 조합은 CAL에서 결정했다. BODY/BURST oracle label은 학습·진단에만 사용한다.

**17. BODY Q90 coverage.** 86.799502%.

**18. Positive BODY coverage.** 74.604696%. 요청 게이트는 두 값 모두90–95%다.

**19. BODY loss/WAPE.** Positive normalized pinball=0.505446565; Q50 WAPE=100.0036%; Q50 MAE=16.527540 GPUh.

BODY 게이트의 수학적 가능성도 별도로 검사했다. 비음수 Q90은 모든 실제0을 덮으므로 overall=z+(1−z)×positive다. BODY zero 비율 z>50%이면 positive coverage≥90%와 overall≤95%는 동시에 불가능하다. 아래는 모델 성능과 별개의 구성비 제약이며 게이트를 완화하지 않았다.

| 역할 | BODY zero fraction | positive90%일 때 최소 overall | 동시 가능 |
|---|---:|---:|---|
| TRAIN | 52.2317% | 95.2232% | False |
| DEVELOPMENT | 59.3944% | 95.9394% | False |
| CALIBRATION | 50.9595% | 95.0959% | False |
| EXPOSED_EVALUATION | 48.0199% | 94.8020% | True |

PRIMARY RESULT: **NO REGISTERED COMBINATION PASSED THE FROZEN SAFETY GATES**

IMPORTANT METHODOLOGICAL FINDING: **BODY_GATE_STRUCTURAL_INCOMPATIBILITY_DUE_TO_ZERO_INFLATION**

BODY_GATE_STRUCTURAL_INCOMPATIBILITY=YES. 전체 TRAIN의 zero 비율과 BODY-only zero 비율은 서로 다른 분모다. 실제 CAL BODY는 1,195/2,345가 zero이므로 양수 coverage≥90%이면 전체 coverage≥95.095949%다. 이 때문에 필수 CAL BODY 게이트는 모델과 무관하게 동시 통과가 불가능하다. 정수 표본에서도 양수 구간을 최소1,035개 덮어야 하지만 전체 상한이 허용하는 최대는1,032개다.

The 15-min target increased zero inflation sufficiently that the preregistered simultaneous overall and positive BODY Q90 coverage bounds became structurally incompatible. Therefore, failure of the registered BODY gate cannot be interpreted solely as evidence of poor forecast quality.

The comparison is retrospective and diagnostic. The frozen failure taxonomy is retained; it does not mean that all models are poor.

| 역할 / BODY 후보 | 전체 coverage | zero coverage | 양수 BODY coverage | 양수 Q90 normalized pinball | 양수 Q50 WAPE | 양수 Q50 MAE GPUh | under GPUh | over GPUh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CALIBRATION / PB1_TRIAL_0_BC0 | 86.652452% | 100.00% | 72.782609% | 0.592989760 | 97.155226% | 28.109647 | 18782.184 | 51946.216 |
| CALIBRATION / PB1_TRIAL_1_BC0 | 85.628998% | 100.00% | 70.695652% | 0.621460547 | 96.978707% | 28.058575 | 20234.465 | 45463.525 |
| CALIBRATION / PB1_TRIAL_0_BC1 | 95.138593% | 100.00% | 90.086957% | 0.538887212 | 101.301343% | 29.309231 | 5014.055 | 229082.596 |
| EXPOSED_EVALUATION / PB1_TRIAL_0_BC0 | 86.799502% | 100.00% | 74.604696% | 0.505446565 | 96.689123% | 30.742098 | 61227.443 | 213142.709 |
| EXPOSED_EVALUATION / PB1_TRIAL_1_BC0 | 86.052304% | 100.00% | 73.167226% | 0.512909240 | 96.435423% | 30.661434 | 62372.817 | 214262.198 |
| EXPOSED_EVALUATION / PB1_TRIAL_0_BC1 | 96.948941% | 100.00% | 94.130331% | 0.512829162 | 100.408081% | 31.924533 | 11832.123 | 946228.651 |

A: PB1 trial0/BC1은 CAL·EXPOSED 모두 양수 BODY coverage90–95%를 충족한다. B: BODY 게이트 내에서는 두 split 모두 전체 upper95%만으로 탈락한다. CAL은 구조적 충돌이고, EXPOSED는 zero 비율이50%미만이라 원리적으로 가능한 게이트에서 해당 예측의 전체 상한 초과다. 이 결과는 전체 pipeline의 통과를 뜻하지 않는다. C: raw PB1 trial0/BC0와 trial1/BC0는 양수 BODY coverage 자체도90%미만이다.

모든 기존 BODY 옵션과 두 raw tuning trial을 보고했다. Trial1은 사후 진단뿐이며 새 BC1 calibration을 만들지 않았다. BC1은 기존 저장 배열만 읽었다. Pinball 평균·합, Q90 기준 양수 WAPE/MAE와 월별 실패 사유는 [정식 감사 JSON](<C:/codex_mobileess_workspace/MobileESS_v40r5_15min_selective_burst_gpuwork/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_ZERO_INFLATION_GATE_AUDIT.json>) 및 [수학적 증명](<C:/codex_mobileess_workspace/MobileESS_v40r5_15min_selective_burst_gpuwork/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_BODY_GATE_FEASIBILITY_PROOF.md>)에 있다.

Burst detector/eta/envelope/overreservation 게이트는 모두 그대로이며 자동 PASS는 없다. 모델 재학습·새 calibration·새 threshold·재선택·winner promotion=0.

V40R5 remains failed under its frozen preregistration; the evaluation contract will be corrected only in a separate prospective revision.


**20. Auxiliary count.** N0 causal seasonal 대비 N1 LightGBM Poisson mean+TRAIN conditional NB dispersion. Classifier TRAIN count feature는5개 chronological expanding folds와 N0 warm-up으로 만들었다. 완료 label이 destination의 첫 origin까지 성숙해야 fold fit에 들어간다.

**21. Large-count recall.** N_high=180.850000; N1 recall(P90>N_high)=4.000000%, count MAE=22.695902, RMSE=93.959047.

**22. Classifier 비교.** C0 TRAIN base rate, C1 logistic, C2 LightGBM, C3 XGBoost. Trial은 DEV PR-AUC/Brier, eta는 CAL에서만 고정했다.

| 모델 | PR-AUC | ROC-AUC | recall | GPUh recall | ECE | FPR | detector safety |
|---|---:|---:|---:|---:|---:|---:|---|
| C0 | 0.049479 | 0.500000 | 100.00% | 100.00% | 0.024903 | 100.00% | True |
| C1 | 0.080225 | 0.658589 | 84.45% | 87.62% | 0.021934 | 60.15% | False |
| C2 | 0.080605 | 0.654657 | 81.58% | 89.20% | 0.020811 | 61.10% | False |
| C3 | 0.087499 | 0.658430 | 77.27% | 82.97% | 0.022277 | 54.79% | False |

**23. 고정 classifier AUC.** PR-AUC=0.087499, ROC-AUC=0.658430.

**24. Recall.** 77.272727%; TP=323, FN=95.

**25. GPUh-weighted recall.** 82.969317%.

**26. Detector captured burst.** 447,685.465278 GPUh, fraction=82.969317%. 감지 성공과 envelope가 실제 크기를 덮는지는 별개다.

**27. Eta.** 0.0163896139711. CAL recall와 GPUh recall≥90%를 만족하는 가장 큰 threshold. 95%-recall 민감도도 사전 규칙으로 보존했으나 선택을 바꾸지 않았다.

**28. Robust envelope 비교.** R0/R1은 CAL burst empiricalQ90/Q95. R2는 고정6시간대×TRAIN 예측count-riskQ75 class부터 시작해 지원N30미만이면 count class→time→global로 fallback한다. 전체 CAL 조합의 loss·coverage·과예약을 보존했다.

| Envelope | CAL primary | CAL burst coverage | CAL overreservation GPUh |
|---|---:|---:|---:|
| R0 | 1.113141 | 83.4437% | 2,522,710.962 |
| R1 | 1.807742 | 86.7550% | 5,496,337.819 |
| R2 | 1.118066 | 82.1192% | 2,563,619.511 |

R0=1609.317222222 GPUh; R1=3442.890416667 GPUh. 비교는 동일한 고정 BODY/classifier에서 CAL만 사용했다. R2의 각 group 지원 수·quantile·fallback은 별도 JSON에 있다.

**29. 고정 envelope.** R0; 전체 조합 CAL 통과 수=0. 선택 실패 시 이 policy는 거부된 진단 예제다. Robust envelope를 body Q90이라고 부르지 않는다.

**30. Hybrid 전체 coverage.** 94.353693%.

**31. Hybrid 양수 coverage.** 89.612369%.

**32. Hybrid burst coverage.** 64.114833%.

**33. 월별 burst.** 작은 표본은 INSUFFICIENT_SUPPORT이며 pooling으로 실패를 숨기지 않았다. Catastrophic gate는 safe reserve WAPE>200%다.

| 월 | burst N | burst coverage | gate | safe WAPE | catastrophic |
|---|---:|---:|---|---:|---|
| 2024-12 | 112 | 38.3929% | FAIL | 840.50% | True |
| 2025-01 | 183 | 74.3169% | FAIL | 1132.29% | True |
| 2025-02 | 123 | 72.3577% | FAIL | 1469.45% | True |

**34. Positive normalized pinball.** 1.165619434; ZERO 최소 유용성 기준은0.9미만이다. Hybrid에서는 Q90-style 의사결정 손실이며 true unconditional Q90 주장과 구분한다.

**35. WAPE.** Safe envelope 전체=1138.9714%, 양수=784.5011%; body Q50 전체=99.7934%. Cumulative reserve WAPE=1009.0610%; daily total reserve MAE/bias=80332.165097/79734.609883 GPUh; horizon crossing=0.

**36. Overprediction.** 7,336,923.703991 GPUh.

**37. Underprediction.** 320,278.034266 GPUh.

**38. Missed burst.** 304,778.411863 GPUh.

**39. Envelope captured fraction.** 43.515574%.

**40. 30MIN 보조 진단.** Sum-of-15min safe reserve coverage=93.229167%, WAPE=1119.1458%, positive pinball score=1.215134133. 15분 출력의 합이며 해당 시간척도의 true Q90이라고 부르지 않는다.

**41. 60MIN 보조 진단.** Sum-of-15min safe reserve coverage=92.376894%, WAPE=1097.7692%, positive pinball score=1.203538284. 15분 출력의 합이며 해당 시간척도의 true Q90이라고 부르지 않는다.

**42. Bootstrap.** NOT_EXECUTED_SAFETY_FAIL; 95%CI=None. Safety 실패 시 사전 규칙에 따라 실행하지 않는다. 비교 baseline=B3.

**43. Confirmation.** TRUE_CONFIRMATORY_AVAILABLE=NO. 모든 과거 split은 노출된 TRAIN/DEVELOPMENT/CAL/STRESS 역할이며 새 untouched로 이름을 바꾸지 않았다.

**44. May.** 2025년5월 scientific reads=0. 경로/index/source/provenance metadata는 NONZERO로 공개한다. Raw archive 및 May scientific payload를 새로 열지 않았다.

**45. 호출.** Optimizer=0, Gurobi=0, OpenDSS=0. Interface는 proposal뿐이다.

**46. 수정 금지.** Optimizer modified=NO; migration=NO; WAN=NO; terminal=NO; event trigger=NO; local repair=NO. A0/A1/M1/MF/Fresh/rollingMPC/second route search/V40S2 변경 없음. Production q=UNCHANGED; PF=.95; Q control=NO; electrical=HOLD; electricalB0–B3=NO; FULL_MAY=NO.

**47. Tests.** 73/75 PASS, 실패0, 아직 미실행2. Required-artifact/clean-state 검사는 receipt commit 이후 단계다. 테스트 성공은 과학적 safety 성공을 뜻하지 않는다. 최초 post-fit 검사에서 float64 극소확률과 등록된 float32 feature를 상대오차로 비교한 오류1건을 발견했다. 등록된 dtype 변환 후 정확한 배열 일치 검사로 수정했으며 모델·입력·예측·게이트는 변경하지 않았다. 최초 검사와 정정 기록을 보존했다.

**48. 재현.** 독립 same-seed rebuild1회. Safe prediction max/mean 차이=0/0 GPUh, CAL primary 원본/재현=1.113141187/1.113141187. 더 좋은 재현을 선택하지 않았다. Count crossfit, BODY, classifier를 다시 학습했다. [장치·버전·시드·학습/예측시간](<C:/codex_mobileess_workspace/MobileESS_v40r5_15min_selective_burst_gpuwork/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_COMPUTE_LEDGER.json>).

**49. 연구 커밋.** [Final research commit receipt](<C:/codex_mobileess_workspace/MobileESS_v40r5_15min_selective_burst_gpuwork/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_FINAL_COMMIT_RECEIPT.json>)에 exact SHA를 저장한다. Scientific result commit과 후속 closure verification commit을 구분한다.

**50. Receipt 커밋.** 자기참조 SHA 대신 receipt JSON에 git log로 해석하는 명령을 저장한다. 최종 응답에 실제 closure/receipt HEAD를 보고한다.

NEXT_RECOMMENDED_REVISION=**V40R5R1_ZERO_INFLATION_AWARE_GATE_CORRECTION**. 제안만 기록하며 R5R1 생성·실행은 하지 않았다. 향후 수정 범위는 평가계약뿐이다: occurrence와 양수 magnitude 분리, positive BODY Q90 gate, overall coverage의 diagnostic 전환, burst 및 hybrid 과예약·안전 게이트 유지. 15분×96 target/cohort/splits/causal features/burst threshold/model registry/hyperparameters/optimizer firewall/May firewall은 유지한다. 현재 R5에 이 변경을 선반영하지 않았다.

[사전등록](<C:/codex_mobileess_workspace/MobileESS_v40r5_15min_selective_burst_gpuwork/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_PREREGISTRATION.json>) · [선택 결과](<C:/codex_mobileess_workspace/MobileESS_v40r5_15min_selective_burst_gpuwork/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_MODEL_SELECTION.json>) · [BODY gate 가능성](<C:/codex_mobileess_workspace/MobileESS_v40r5_15min_selective_burst_gpuwork/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_BODY_GATE_FEASIBILITY_AUDIT.json>) · [연결 제안 계약](<C:/codex_mobileess_workspace/MobileESS_v40r5_15min_selective_burst_gpuwork/dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_OPTIMIZER_INTERFACE_CONTRACT.json>)
