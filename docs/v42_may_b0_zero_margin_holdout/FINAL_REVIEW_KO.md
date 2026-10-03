# May B0 zero-margin holdout 결과

PR128 exact head 3872dea8130baa25fd3deaabeddeabee5fbd730f에서 시작해 April의 parameter/margin과 모든 기존 evidence를 보존했다. 기존 frozen May raw authority의 2025-05-01–31 전체를 사용했다. B0만 실행했으며 Planning margin은 0, band는 0.95–1.05 pu다. Planning과 Actual 모두 source-backed autonomous RegControl 7개, fixed-ON capacitor 4개, CapControl 0개다. Actual은 매일 fresh source context에서 시작하고 하루 안에서 sequential carryover한다. Planning tap/cap replay, Actual P/Q repair, reoptimization, MESS, AIDC grid-aware flexibility와 parameter/margin tuning은 모두 0이다.

Planning 31일 전체를 먼저 freeze하고 private Actual realized service와 observed weather를 열었다. Source-backed realized duration 49,414개에 누락은 0개다. Controller는 causal submission/completion event만 받는다. 동일 frozen Runtime Q50, Runtime reserve gamma/kernel, CC4, physical modelability, capacity, strict FCFS queue, C1/PF와 affine Planning authority를 유지했다. Original raw files는 read-only이며 Git에 복사하지 않았다. Source issue vintage와 forecast/grid/weather 시간축은 31일 모두 통과했다.

| 측정 | May 결과 |
|---|---:|
| 대상 | 31 days / 2,976 slots |
| Planning voltage violations | 0 cells / 0 days |
| Actual Fresh OpenDSS convergence | 2976/2,976 slots |
| Actual voltage violations | 0 cells / 0 days |
| Actual min/max | 0.970952249438 / 1.049950018757 pu |
| Line current violations | 0 |
| Transformer current violations | **12 cells** |
| Transformer kVA violations | 0 |
| Residual mean signed | 0.000166410804 pu |
| MAE | 0.002993572761 pu |
| RMSE | 0.003689210607 pu |
| Max absolute error | 0.014292720819 pu |

Residual은 V_ACTUAL_AC−V_PLAN magnitude pu이며 31×96×386 = 1,148,736 points의 exact day/node/phase/slot 축이다. Worst는 2025-05-21, slot 30, 160r.2다. Lossless full precision CSV.gz와 NPZ를 보존한다.

±0.005 coverage는 참고지표다. Upper 91.3721%, lower 93.2914%, joint point 84.6635%, joint day 0/31이며 이를 margin 조정에 사용하지 않았다. April/May 비교는 APRIL_MAY_COMPARISON.csv에 있다.

판정: **margin=0 holdout PASS candidate — 전압 기준, May B0 한정**. Planning과 Actual 전압 위반이 모두 0이다. Transformer current 위반 12 cells는 May 19/20/21/22일에 있으며 peak current ratio는 1.0532829242이다. CURRENT_VIOLATION_LEDGER.csv와 raw measurements에 보존했다. 이 결과를 전체 전력망 제약 PASS로 해석하지 않는다. 결과를 보고 P/Q, Runtime/CC4, queue, control parameter 또는 voltage margin을 변경하지 않았다.

FINAL_MARGIN_ACCEPTED=false, PROBLEM13_FINAL_VALIDATED=false를 유지한다. B1/B2/B3/M1/A2/M2는 NOT_RUN이다. 이 B0 voltage holdout을 다른 비교군이나 V42 전체의 최종 margin으로 일반화하지 않는다.

Exact PR128 BASE 3,809개 파일의 bytes, current source hashes, May pre-Actual workload/P/Q/V_PLAN freeze와 engine P/Q readback을 검증한다. May 수치가 April 수치와 같다는 주장이 아니라 같은 frozen scientific authority로 독립적인 May 입력을 평가했다는 증명이다. Full pytest는 inherited 8-file EOL compatibility variant를 사용한 뒤 exact BASE bytes를 복원한다. TEST_RECEIPT.json, VERIFICATION.json, SHA256_MANIFEST.json에 최종 검증 결과를 보존한다.

Kestrel immutable request-version history와 CC4 역사적 ingestion receipt에 대한 기존 한계는 유지한다. 또한 저장소에는 이전 May01 development canary가 존재한다. 이 holdout은 April calibration이나 이번 parameter freeze에 May outcomes를 사용하지 않은 평가이며, 모든 과거 개발에서 May가 전혀 열리지 않았다는 주장을 하지 않는다.
