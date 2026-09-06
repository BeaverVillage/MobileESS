# V40K point swing audit

V40J를 변경하지 않은 pre-May 진단이다. 통계적 estimand와 cohort 차이를 구분한다.

| Model | Underprediction | Mean actual−point (s) | MAE (s) |
|---|---:|---:|---:|
| C1_L1 | 10.407240% | -28986.442 | 38230.863 |
| C0 | 73.642534% | 4612.127 | 12517.794 |
| C1_Q50 | 15.441176% | -36574.165 | 45296.877 |
| C2_MIXTURE | 16.459276% | -5764.396 | 14547.639 |

V40J mixture는 weighted mean이며 conditional median이 아니다. L1/Q50에는 log inverse나 walltime cap이 없으므로 이 두 변환을 원인으로 지목할 수 없다. 전체 historical-status 학습과 COMPLETED H100-standby 평가 cohort의 차이, 요청 walltime 분포와 finite-tree approximation을 함께 조사했다. 원인을 하나로 단정하지 않는다.

C1_L1 fold signed bias: F1=3996.1s, F2=-40541.8s, F3=-28575.4s
C0 fold signed bias: F1=-522.6s, F2=4639.1s, F3=12458.6s
C1_Q50 fold signed bias: F1=3021.3s, F2=-52127.5s, F3=-28575.4s
C2_MIXTURE fold signed bias: F1=-9516.8s, F2=-6707.0s, F3=4265.9s

정량 target 분포·early 비율·regime별 metric·feature gain은 동명 JSON에 있다. 새 estimand는 Q50이며 mean signed error는 diagnostic으로만 사용한다.
