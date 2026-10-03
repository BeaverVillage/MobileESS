# Source-backed autonomous RegControl April B0 calibration

PR127 exact head f535cc2671b285068f6b5ffbec55b951ffb7ea6d의 실제 IEEE-123
authority를 채택했다. 7개 RegControl은 autonomous, 4개 capacitor는 fixed ON,
CapControl은 0개다. 기존 source targets/bands/delays/tap limits와 engine version을
변경하지 않았다. 새 Actual 경로는 Planning tap/cap을 입력받지 않고, 매일 fresh
source compile에서 시작해 하루 96 slot 동안 같은 engine의 상태를 이어간다.
Planning producer 및 저장된 V_PLAN은 보존했다.

먼저 April 15/16/30 diagnostic의 제어·P/Q identity·capacitor·수렴 gate가 PASS한
뒤 별도의 30일 full rerun을 수행했다. Diagnostic과 full run의 해당 3일은 exact
numeric repeat identity가 성립한다. Voltage violation을 gate failure로 삼거나
결과를 보고 control parameter를 조정하지 않았다.

| 날짜 | Old frozen 위반 cells | New autonomous 위반 cells | 관측 settled tap steps | Planning과 다른 slots | 최대 차이 steps |
|---|---:|---:|---:|---:|---:|
| April 15 | 3 | 0 | 49 | 92 | 2 |
| April 16 | 17 | 0 | 44 | 89 | 1 |
| April 30 | 2 | 0 | 44 | 61 | 1 |

Archival verifier는 동일 source·realized inputs·physical P/Q를 사용해 기존
PR125 frozen 조건을 3일 재현했고, 저장된 old voltage/tap/cap arrays와 exact
numeric identity를 확인했다. 이것은 새 production의 fallback이 아니라 별도
historical paired-input 검증이다. 22개 old violation cell 모두 해당 slot에서
tap이 Planning과 달라졌고, new voltage가 physical band에 들어왔다.
FROZEN_TAP_VIOLATION_CAUSAL_AUDIT.csv는 각 cell의 old/new voltage, band excess,
regulator별 signed step 차이 및 residual을 보존한다. 이 결과의 causal 해석은
동일 physical inputs에서 tap-control law만 바꾼 paired simulation 범위다.

Full April은 **30/30일, 2880/2880 slots 수렴**했다. Voltage 위반은 **0 cells /
0 days**이며 line current / transformer current / transformer kVA 위반도 모두
0이다. Actual magnitude 범위는 **0.9784057383–1.0498964147 pu**다.
Regulator settled tap-step operations는 총 **1238**, Planning과 다른 slot은
**2595/2880**, 차이가 있는 날은 **30/30**, 최대 차이는 **2 steps**다.
모든 capacitor state는 [1]이며 controller 추가/스위칭/보정은 없다.

Operation count는 source initial→slot0 및 slot 간 **net settled tap steps**를
합한 값이다. Within-solve reversals/event 수는 관측하지 못하므로 실제 내부
operation 총수로 과장하지 않는다. Raw logs는 control iterations, convergence
iterations, control-actions-done와 previous/final tap을 보존한다.

Primary residual은 unchanged V_PLAN magnitude에 대한 V_ACTUAL_AC−V_PLAN이다.
30×96×386 = **1,111,680 points**를 동일 day/node/phase/slot로 비교했다.

| 지표 | pu |
|---|---:|
| Mean signed error | -0.00000568536735445 |
| MAE | 0.00302957779359 |
| RMSE | 0.00368192136837 |
| Median absolute error | 0.00276723498921 |
| Maximum absolute error | 0.0151772711242 |

Worst는 April 12, slot 25, idc_idc10_pcc phase A다. Planning 1.0449663262 pu,
Actual 1.0297890550 pu다. Physical voltage safety와 forecast-conditioned Planning
residual coverage는 다른 측정이다. 안전해진 결과만으로 margin을 승인하지 않는다.
Old 조건보다 MAE/RMSE/max 및 joint ±0.005 coverage가 개선되었다고 주장하지
않는다. 독립적인 forecast/Actual tap trajectories는 다른 operating points를 만든다.

±0.005 upper/lower/joint point coverage는 **91.5535% / 93.6364% / 85.1899%**다.
Joint day coverage는 **0/30**, exceedance는 **30/30일**이며 최대 excess는
**0.0101772711 pu**다.

Empirical `higher` candidate bands는 다음과 같다. Q90/Q97.5 및 방향별 delta도
별도 CSV/JSON에 전부 보존했다.

| Population | Quantile | lower pu | upper pu |
|---|---:|---:|---:|
| Pointwise | Q95 | 0.9554406099 | 1.0443005829 |
| Pointwise | Q99 | 0.9594516010 | 1.0414860392 |
| Day-worst | Q95 | 0.9644181303 | 1.0374186321 |
| Day-worst | Q99 | 0.9651772711 | 1.0366032101 |

PR125 workload/capacity/C1/PF/Runtime/CC4/queue/physical P/Q/V_PLAN은 CURRENT /
PRESERVED이다. Old voltage evidence는 historical condition으로 보존하고 voltage
calibration만 SUPERSEDED_BY_AUTONOMOUS_REGCONTROL로 명시했다. Exact PR127
BASE 3590 files의 raw bytes와 old arrays의 identity를 검증한다.

Common authority/session은 B0/B1/B2/B3와 April/May에 같은 source SHA를 제공한다.
Arm별 parameter SHA override는 fail-fast다. B1/B2/B3/May/M1/A2/M2 scientific
execution은 NOT_RUN이다. May Actual voltage/holdout outcomes는 tuning에 사용하지
않았고, April runner는 May 날짜를 거부한다. Source-defined 연간 normalization
reference는 기존 frozen authority대로 hash만 확인하고 May rows를 load하지 않는다.

Actual P/Q/local repair·AIDC/MESS/global reoptimization·MESS P/Q·parameter tuning은
모두 0이다. FINAL_MARGIN_ACCEPTED=false, PROBLEM13_FINAL_VALIDATED=false다.
Scientific blocker는 없으며 May holdout과 다른 arms의 검증은 이번 scope 밖이다.
Regression 결과는 TEST_RECEIPT.json/PYTEST_FULL.log, 최종 independent CSV/BASE
audit는 VERIFICATION.json을 참조한다. Historical CRLF hash 호환을 위한 pytest
임시 EOL 변환은 finally에서 exact BASE bytes로 복원하고 다시 검증한다.

PR125의 Actual voltage violation **22개 cell 전부가 frozen Planning tap replay
조건에서 발생했고**, source-backed autonomous RegControl 재실행에서 **0개로
제거됨을 동일 inputs의 paired simulation으로 정량 확인하였다.**
