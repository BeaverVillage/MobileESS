# V40J 최종 연구 검토

판정: **V40J_CALIBRATION_IMPROVED_POINT_MODEL_INSUFFICIENT**. Winner는 없으며 production integration recommendation은 **NO**다.

시작 HEAD `3f6317efeffac7e3fbc37d9c3c2ddca57357c70f`, 사전등록 커밋 `570c653`. 최종 커밋은 별도 git receipt에서 확인한다.

May runtime/status row, Actual outcome artifact, model-building, training, calibration, model-selection 읽기 횟수는 각각 0이다. 초기 path/code 탐색과 metadata 읽기는 별도 NONZERO 카운터로 공개했다. 정확한 전체 횟수는 주장하지 않는다. V40I 문서는 요청된 motivation/claim-boundary로만 읽었다. Amendment 커밋 69d8425 이후에만 winner selection을 수행했다.

원자료 footer census는 21개 pre-May native-time 월 파티션과 7,325,307행을 확인했다. 실제 후보 개발 입력은 기존 pre-issue normalized cache의 GPU 233,999행이다. CPU 전용 작업이나 unobserved/censored jobs에 대한 성능을 주장하지 않는다. April partition은 UTC 기준 May-01 일부 시간까지 걸치므로 metadata와 row payload를 구분했다.

실제 GPU cache의 submit 범위는 2024-10-27–2025-03-31, end-known 범위는 2024-10-31–2025-03-31이다. 최대 120일 lookback을 적용했지만 cache 시작일 때문에 초기 fold의 실제 historical support는 120일보다 짧다. 더 오래된 raw 자료 전체를 학습한 실험으로 주장하지 않는다.

검증: F1 2025-02-15–21, F2 02-22–28, F3 03-01–07. 학습마다 end_time-known을 적용했다. Calibration에는 별도 앞선 블록만 사용했다. 최종 03-08–31 calibration과 04-24–30 shadow는 winner가 없으므로 실행하지 않았다.

현재 baseline은 고정된 3월 22일 예측과 byte-identical, 최대 차이 0초로 재현했다. 새 후보는 L1, log1p, Huber, Q50, causal early-termination mixture, 직접 Q50/Q90/Q95다. C4는 candidate 환경에 필요한 survival dependency가 없어 사전등록대로 제외했다.

| Point candidate | COMPLETED H100-standby underprediction | Mean actual-point (s) | MAE (s) |
|---|---:|---:|---:|
| C0 | 73.6425% | 4612.127 | 12517.794 |
| C1_HUBER | 73.9819% | 20244.582 | 25374.212 |
| C1_L1 | 10.4072% | -28986.442 | 38230.863 |
| C1_LOG | 84.2195% | 31001.581 | 31840.417 |
| C1_Q50 | 15.4412% | -36574.165 | 45296.877 |
| C2_MIXTURE | 16.4593% | -5764.396 | 14547.639 |
| C3_QUANTILE | 15.4412% | -36574.165 | 45296.877 |

조건부 native Q90 coverage는 point·reserve와 분리해 판정했다. 아래는 후보별 N=100, R3 진단이며 winner를 의미하지 않는다. 전체 N=100/200/500 및 R0–R3 결과는 JSON에 있다.

| Candidate | Native Q90 coverage | H100-standby | Active-miss GPU-slots | Overreserved GPU-h | Gates |
|---|---:|---:|---:|---:|---|
| C1_L1 | 94.2724% | 98.0925% | 125,937 | 867,508.05 | {'GPU': True, 'conservatism': False, 'coverage': True, 'point': False} |
| C1_LOG | 96.1078% | 94.8021% | 103,962 | 1,125,847.50 | {'GPU': True, 'conservatism': False, 'coverage': False, 'point': False} |
| C1_HUBER | 90.2762% | 94.7544% | 106,044 | 1,079,223.10 | {'GPU': True, 'conservatism': False, 'coverage': False, 'point': False} |
| C1_Q50 | 94.4306% | 98.1879% | 125,221 | 852,143.24 | {'GPU': True, 'conservatism': False, 'coverage': True, 'point': False} |
| C2_MIXTURE | 89.7247% | 94.2299% | 126,821 | 761,531.63 | {'GPU': True, 'conservatism': False, 'coverage': False, 'point': False} |
| C3_QUANTILE | 92.6902% | 94.0391% | 59,537 | 396,079.63 | {'GPU': True, 'conservatism': True, 'coverage': False, 'point': False} |

R0는 nominal 점유, R1은 Q90 hard 점유, R2는 nominal 점유에 Q90까지의 capacity/grid reserve, R3는 Q90 hard 점유에 Q95까지 reserve다. Offline duration-aligned workload replay만 수행했다. 실제 grid-critical line metric은 독립 pre-May authority가 연결되지 않아 NOT_EVALUATED로 남겼다. 다른 site를 actual site로 대체하지 않았다.

12h 전용 규칙은 없다. exact9/other8, hardware, walltime, regime support를 반환하며 sparse/regime mismatch는 leaf를 건너뛰고 보수적인 parent calibration으로 fallback한다. OUT_OF_SUPPORT는 requested-walltime 이상으로 확장하고 요청값이 잘못되면 abstain한다. 이러한 fallback의 reservation 비용도 gate에 포함했다.

외부 P/Q 판정: **PLAUSIBLE_APPROXIMATION**. 총 PF P5/P50/P95 = 0.943389/0.950123/0.958954. SHA 일치·원본 불변. 극성 반전 때문에 leading/lagging은 조건부 해석이다. 상세 출처와 계산은 별도 외부 감사 문서에 있다.

Protected scope, current q/model, PF=0.95를 보존한다. 72 authority blockers 유지, 31-day electrical regeneration HOLD, B2/B3 NO, FULL_MAY NO, Q control NO. Optional B0/B1 shadow도 gate 미통과로 실행하지 않았다.

테스트 실행 수와 로그·hash는 V40J_TEST_REPORT.json에 기록한다. 기존 V40H 106/V40I 80 PASS는 frozen receipt와 소스 보존으로 유지하며 May outcome/row fixtures를 다시 열어 재실행하지 않았다. 새 V40J 회귀는 실제 실행했다. Shadow를 열거나 cutoff·후보·support threshold를 바꿔 실패를 보정하지 않았다.
