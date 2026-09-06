# V40I final forensic closure

May-01 B1의 Actual 악화는 frozen PENDING runtime 과소예측과 spatial placement의 결합으로 재현됐다. Pre-May COMPLETED H100에서 체계적 point 과소예측과 pooled q의 conditional coverage 부족이 확인된다. May cohort의12h 요청 조합은 동일한 나머지 입력의48h 학습 regime과 달랐다. 이 support mismatch의 존재는 확정되지만 개별 예측에 대한 직접 인과 기여는 미입증이다. Actual occupancy의 sw2 하류+2GPU와 constant-PF coupled P-Q directional sensitivity가 저장된 전류 증가를 가깝게 재현했다. 작은 절대 grid 효과는 제어 가능한 부하가 slot73 feeder의 약0.895%라는 규모와도 일치한다.

필수 수치: COMPLETED N=2,562, point underprediction64.1296%, mean error+7064.205s, median+332.336s. q=5576.44921875s, COMPLETED diagnostic q90=29813.46171875s, ratio=5.346316. DUAL_PREDICTOR_AND_CALIBRATION_FAILURE.

12h COMPLETED training274개는4user/3account에 속하며271개가 한 account다. 전체 COMPLETED 중0.965%이고 calibration12h는0개다. 12H_SUPPORT_SPARSE. May29개 모두 exact9-match0, 같은 other8-match1501(모두48h)로 REGIME_MISMATCH다. Runtime 값의 범위 support와 feature-conditional support는 같은 판정이 아니다.

| 당시 exact feature support | N | MAE s | mean signed error s | point under | post-q under |
|---|---:|---:|---:|---:|---:|
| NO_EXACT_SUPPORT_REGIME_MISMATCH_CANDIDATE | 553 | 9284.251 | 7812.358 | 58.7703% | 55.6962% |
| SPARSE_OBSERVED_EXACT_SUPPORT | 5 | 33776.528 | -1428.297 | 80.0000% | 40.0000% |
| STRONG_OBSERVED_EXACT_SUPPORT | 2004 | 11425.133 | 6878.943 | 65.5689% | 26.6966% |

Support는 각 prediction split 이전120일 end_time-known 학습 자료에서 계산했다. 자기 UID와 미래 종료는 제외했다.100개 기준은 기존 min_expert_rows를 투명한 descriptive bin으로 사용한 것이며 실제 fitted leaf support를 증명하지 않는다. 그룹 간 association으로 fitted causal effect를 주장하지 않는다.

동일 input support가100개 이상인군도 point underprediction65.57%다. 따라서 support 부족만으로 point misfit를 설명할 수 없다. q 적용 후에는 exact support0군55.70%,100개 이상군26.70%로 차이가 있지만 이는 association이며 sparse군N5는 비교 근거가 약하다.

TRAIN_DEPLOYMENT_STATUS_MIX_MISMATCH=CONFIRMED(학습 대 pre-May 검증). FAILED_SHORT_SAMPLE_DIRECT_CAUSAL_EFFECT_ON_PREDICTION=PLAUSIBLE_NOT_PROVEN. Final COMPLETED/FAILED는 retrospective label이고 D-1 feature가 아니다.

Runtime distribution=MULTI_REGIME; positive residual은 경험적 heavy right tail. Formal asymptotic heavy-tail law는 미입증. ALL H10028.38%/28.17%와 COMPLETED32.98%/32.67%를 구분한다.15-min ceil은 주원인이 아니다.

UID reconciliation PASS: under+29, over−3, admission−3. Frozen effects−2+9−4−1=+2GPU. Migration은 주원인이 아니다.

전기: constant-PF coupled P-Q directional sensitivity ΔI=0.148915853403A, 저장Actual=0.146241726480A, 절대차이=0.002674126923A, 상대오차=1.828566%. 순수 P 미분으로 부르지 않는다. FIXED_PF_ASSUMPTION_PRIMARY_CAUSE_OF_REVERSAL=NO(현재 frozen replay에서 별도 primary mechanism 불필요), 물리 fidelity=INSUFFICIENT_AUTHORITY/OPEN_LIMITATION.

AIDC Q는 fixed PF0.95 파생값이며 P와 함께 시간에 따라 변한다. 독립 AIDC Q authority=NO(검색 범위 내 미확인), Q control authorization=NO. 별도 MESS PCC Q gradient는 진단 proxy이고 AIDC Q partial/capability가 아니다.

slot73: feeder2693.449615kW, AIDC334.562009kW, controllable24.099852kW, fixed310.462157kW; controllable/feeder0.8948%, controllable/AIDC7.2034%. 작은 효과가 optimizer failure임을 뜻하지 않는다. Primary Planning 최적성 근거는 유지되어 있다.

최종 연구 방향: RUNTIME_NEXT_REVISION=HYBRID_PREDICTOR_CALIBRATION_ROBUST; REACTIVE_NEXT_REVISION=RETAIN_FIXED_PF. Conditional calibration만으로 충분하다고 판단할 근거는 없다. Causal point model, condition-aware upper tail, optimization-side reserve/envelope를 별도 pre-May 프로토콜에서 비교한다. Exogenous PF는 독립 자료, controllable Q는 장비 authority가 필요하다.

새 fit/재학습/q적용/parameter tuning/optimization/PF/Qcontrol 변경 없음. May-01은 이미 진단에 사용됐으므로 새 방법의 blind confirmatory test라고 주장하지 않는다. May fitting/calibration은 금지한다. Conditional source까지 포함한 최종 회귀 결과와 commit SHA는 최종 checkpoint receipt에 기록한다. Commit 이후에도31일 재생성HOLD, B2/B3 NO, full-May NO.
