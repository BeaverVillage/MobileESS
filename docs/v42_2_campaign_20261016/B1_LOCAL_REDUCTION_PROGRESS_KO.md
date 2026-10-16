# Local 추가 축소 — 진행 중

사용자 지시에 따라 ATTEMPT005는 공식 중지·정산한 상태다. 실제 Arm 최적화는 재개하지 않았다. 원래 Integer FULL은 변경하지 않았다.

| 범위 | 최초 | 1차 zero/alias | Bounds 흡수 | 역방향·평행 행 정리 |
|---|---:|---:|---:|---:|
| 전체 229 Class Local Hard 행 | 261,414 | 210,067 | 199,617 | 197,359 |
| Local 변수 | 174,685 | 134,630 | 134,630 | 134,630 |
| Local NNZ | 930,913 | 789,632 | 777,078 | 770,085 |

누적 64,055행(24.50%), 40,055변수(22.93%), 160,828 NNZ(17.28%) 감소했다. 이는 Local 범위이며 전체 모델 비율과 혼동하지 않는다.

추가 10,450행은 정확히 표현 가능한 단일 변수 제약을 Bounds에 흡수하고, 그 Bounds만으로 보장되는 행을 삭제했다. 모든 계산은 원래 binary64를 정확한 유리수로 해석한다. 반올림해야 하는 Bounds는 채택하지 않는다. 새로 고정된 0이 아닌 변수 45개는 좌표를 유지해 Global 우변·상수·목적함수·UID 인터페이스를 바꾸지 않는다.

독립 검증기는 원래 단일 변수 행에서 새 Bounds를 재도출하고 삭제한 모든 행의 정확한 구간 부등식을 검사한다. 따라서 원래 Local의 모든 점이 새 Boxes를 만족하며, 새 Local의 모든 점은 삭제된 원래 행도 만족한다. zero/alias의 역방향 lift와 합성한 전체 연속 Local Polytope 동치성이다. 정수성이나 유한 Column Pool은 사용하지 않는다.

`LOCAL_REDUCTION_NATIVE0_02/RESULT.json`: 실제 229개 Class 전체 PASS, 1,555 UID 유지. Gurobi optimize/presolve 차단 상태에서 A/RHS/Sense/LB/UB/VType/목적함수 재읽기까지 통과했다. Native 호출 0, Wall 43.2163366초. 속도 개선을 뜻하는 수치는 아니다.

1차 축소의 전체 Hybrid 통합은 `B1_NATIVE0_08/REDUCED_HYBRID_NATIVE0.json`에서 PASS했다. 1,026,045×190,778→974,698×150,723, NNZ 11,155,684→11,014,403. 모든 Global 행·우변·sense·Global boxes와 Local 결합 계수를 검증했다. 이 증거의 Source에는 추가 Bounds 축소가 아직 포함되지 않는다.

Bounds 추가 축소까지의 `B1_NATIVE0_09` 전체 Hybrid 검증은 PASS했다: 964,248행·150,723변수·11,001,849 NNZ. 역방향·평행 행까지 포함한 현재 Source의 전체 Hybrid 통합·Original FULL 유지·full local pricing 경로는 새 `B1_NATIVE0_10`에서 PASS했다. 현재 Source의 M Native0와 Regression도 별도로 필요하다. 과거 Source 결과는 현재 Gate로 전용하지 않는다.

남은 Local은 2~3변수 행이 대부분이다. 단순하게 독립 link-bytes 좌표를 합치면 분수 LP 자유도를 없앨 수 있으므로 동일한 경로 incidence만으로 병합하지 않는다. WAN 누적 전송식의 affine 소거는 fill 증가까지 함께 평가해야 한다. 추가 정리로 부족하면 Local 행을 Master에서 Pricing으로 분리하는 정확한 Local Polytope DW 파일럿을 검증한다. 유한 초기 Pool만으로 full-domain pricing·Global LB는 인증하지 않는다.

실제 Phase I 완료시간, exact Phi=0, Global LB, FULL/Actual96/Fresh96는 아직 미인증이다. 다음 실제 성능 측정은 현재 Source의 모든 Gate를 통과한 새로운 Attempt에서 수행한다.

## 역방향·평행 행 추가 정리

동일한 정확한 선형식 L에 대해 L≤b와 L≥b를 동시에 가진 2,206쌍을 L=b 하나로 바꾸고, 이미 있는 등식으로 증명되는 평행 부등식 52개를 제거했다. 추가 2,258행·6,993 NNZ 감소이며 변수는 유지했다. 서로 다른 경계의 양방향 구간이나 근사적으로만 같은 계수는 병합하지 않는다.

독립 검증기는 새 등식마다 두 원래 부등식의 정확한 계수 배율·우변·반대 방향을 검사한다. 모든 삭제 행에 대해 Boxes 또는 남은 평행 행으로부터 정확한 함의를 재검사한다. 원래 제약→새 제약, 새 제약→원래 제약의 양방향 동치성이다.

`LOCAL_REDUCTION_NATIVE0_03/RESULT.json`: 전체 229 Class PASS, Native 0, Wall 55.923068초. 현재 회귀 `REGRESSION16/RESULTS.json`: 1,319 PASS, 기존 682 IDs 및 과거 원장 보존. 전체 Master 현재 Source 검증도 B1_NATIVE0_10에서 PASS했다. 실제 속도 검증과는 구분한다.

## 현재 Source 전체 Hybrid Native0 결과

`B1_NATIVE0_10/RESULT.json` 및 `REDUCED_HYBRID_NATIVE0.json`: PASS, Native 0. 전체 Hybrid 1,026,045행·190,778열·11,155,684 NNZ에서 961,990행·150,723열·10,994,856 NNZ로 축소했다. 전체 행은 6.24%, 열은 21.00% 감소했다. Local 행 감소율 24.50%와 범위를 구분한다.

독립 전체 Master 증명은 모든 Global 행의 Local 결합 계수를 유리수로 검사하고, Global prefix의 계수·Boxes 및 모든 Global RHS/Sense를 보존한다. 12×96 PCC 하드 정의식 1,152개를 유지했다. 모든 229개 원래 Local의 완전한 연속 도메인과 결합·목적함수·UID 표현이 보존되며, Gurobi 전체 재읽기 및 analytical zero-dual full-block coverage 경로도 통과했다. 이는 최적화 pricing closure 또는 Global LB가 아니다.

현재 Source 원본 Integer FULL은 2,108,858행·946,756열·21,126,591 NNZ로 그대로 재구성됐다. Source 변경 전후의 정확한 행·열 대응은 별도 `ORIGINAL_FULL_CROSS_SOURCE_PERMUTATION_02`에서 검사한다. 축소 후 Native 최적화는 아직 실행하지 않았다.

축소 후 sparse support 분류에서 WAN 전송·링크 관련 193,380행, Local service 2,092행, checkpoint/migration 1,887행이다. 혼합 행은 WAN 우선으로 분류하므로, 이는 의미적 행 이름의 유일한 계보나 Barrier fill의 인과 증거는 아니다. 상세는 `B1_REDUCED_LOCAL_SUPPORT_CENSUS.json`에 보존했다.

Original FULL의 Source 간 대응 검사도 ORIGINAL_FULL_CROSS_SOURCE_PERMUTATION_02/RESULT.json에서 PASS했다. 모든 원본 행·변수·Bounds·목적함수·UID 표현 및 실제 4,800 tail lift를 확인했다. 따라서 이전 실제 실행과 같은 물리 Case의 성능 비교를 위한 동치 근거가 확보됐다. 실제 속도 개선은 아직 측정 전이다.
