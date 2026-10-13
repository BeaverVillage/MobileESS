# V42 B2 Adaptive Beam–4-MESS Joint MILP 병목 개선 및 최종 결과

이번 실험은 Pilot 63.642초를 보존하고 동일 1,800초 예산에서 계속 실행했다. V2와 V3는 Source·Policy를 각각 동결한 별도 실행 버전이다. V3는 별도 Worktree에서 개발하고 Native0·독립 검사·Native Readback PASS 후 Worker가 없는 경계에서 전환했다. 기존 Pilot의 조기 기각 보고서와 원장은 역사 기록으로 보존하며 전체 알고리즘의 실패 판정으로 사용하지 않는다.

## 검증된 결과

| 항목 | 결과 |
|---|---:|
| BEST_GLOBAL_UB | 0.5398310226338695 |
| BEST_MOVING_FEASIBLE_UB | 0.5398310226338695 |
| PR220 대비 UB 개선량 | 0.0000000000000000 |
| 기존 K48 인증 Global LB | 0.4649848699754817 |
| Global Gap `(UB−LB)/UB` | 13.864737209% |
| 전체 평가한 경로 후보집합 | 25 |
| Pilot 포함 Native 호출 | 36 |
| V3 Native 호출 | 16 |
| Original FULL 독립 감사 | PASS |
| 종료 사유 | NATIVE_BUDGET_WITH_RETURN_RESERVE |

개선해 발견시간: 이번 실행의 신규 개선해는 없으므로 해당 없음. PR220 FULL 검증 해를 유지한다.

최선 실제 Joint 선택의 차량별 MOVE 수는 {"MESS01": 0, "MESS02": 0, "MESS03": 3, "MESS04": 0}다. 이 선택은 Solver 결과이며 차량 이동을 고정하거나 강제하지 않았다. 매 모델에서 MESS01~04 각 8개 후보의 STAY·단일 MOVE·복수 MOVE와 λ 하나 선택을 유지하고, 네 차량 경로·384개 Charge Mode·Pch/Pdis/Q/SOC를 하나의 MILP에서 공동 결정했다. 경로 조합을 별도 MILP로 열거하지 않았다.

## 준비시간·전체 반복시간

동일 Source/Case/Pool/Start의 Native0 비교에서 준비시간은 50.653초 → 27.203초로 23.450초, 46.30% 감소했다. 캐시 최초 생성비용 5.531초는 별도다. Source SHA·Case SHA·행렬/Domain/정적 Alias 및 정식화 버전에 묶인 읽기 전용 캐시를 사용하며 Source 변경·버전 변경·오염 재사용 거부 테스트는 PASS다.

새 DAG·λ 연결·Node/Flow/Arc/Alias·MIP Start·모델 CSR/Bounds/Types/Objective Readback·선택 Raw 복원·Original FULL Replay·Resource Gate를 생략하지 않았다. 불변 원본 Alias 전개만 정확한 정적 정수 연산자로 재사용하고 후보별 연결식은 독립적으로 다시 구성한다.

V3 전체 반복 Wall 평균 213.793초, 중앙값 204.436초다. 확장 없는 일반 반복 중앙값은 163.735초다. 정식화 두 종류를 비교하는 반복과 큰 Beam 확장을 별도로 식별한다. 첫 Pool은 개발 단계에서 미리 준비했으므로 그 133초 안팎의 준비 비용과 Native0/Readback 비용을 별도로 기록했다. 첫 반복의 낮은 Wall만으로 전체 속도 이득을 주장하지 않는다.

`V3_EXCLUSIVE_ITERATION_TIMINGS.csv`와 Worker CSV에는 Source 로딩, 정적 SHA/캐시, Grid/SOC/Rebound, Beam 생성, Score/Admission, CSR/패킷, Alias, 모델 생성, Native Readback, Optimize, FULL Replay를 분리했다. 배타적 단계 합계+기타 IO/제어 잔여는 전체 Wall과 일치한다. Presolve·Root·콜백은 Optimize의 부분 시간이므로 중복 합산하지 않는다. 초기 V2의 미계측 세부 시간을 사후에 지어내지 않았으며 Worker/Native/검증 실측과 미분리 잔여를 구분한다.

준비 캐시의 이득이 강화된 96슬롯 Grid·SOC 스코어 비용으로 일부 상쇄됐다. 전체 Wall 개선은 실제 반복 분포로 평가하며 준비시간 감소를 그대로 전체 속도 개선률로 환산하지 않는다. Beam 확장은 수 분이 걸릴 수 있으며 모든 반복마다 확장하지 않는다.

## Presolve·정식화 비교

기존 Joint 입력 Binary 9,354개 → Direct 416개를 확인했다. Sparse EF도 416개지만 원본 216,674개 Route/Node/Flow 좌표와 보조변수를 유지해 희소 연결을 보존한다. V3의 서로 다른 4개 Pool에서 동일 Source/Case/Raw Start/파라미터/TimeLimit로 Direct와 EF를 비교했으며 Runtime 중앙값은 Direct 37.269초, EF 42.547초다. 최종 Backend는 `DIRECT`다.

`ALL_NATIVE_SOLVER_METRICS.csv`에는 Presolve 전후 Rows/Columns/Binaries/NNZ, Presolve 초, Root 완료 여부, Barrier 반복, NodeCount, Status, ObjBound, MIPGap, 모델 생성 및 Native 시간이 있다. 각 초기 모델의 `MATRIX_STRUCTURE.json`에는 밀도, 행·열 NNZ 분포, 로컬 Fill-in, 전역 NNZ 비율과 원본 계수 범위를 기록했다. Root 기록 없음은 0초나 완료로 바꾸지 않았다. NodeCount=0·제한 Pool의 Optimal Status는 전역 최적성 증명이 아니다.

V2에서는 빠른 Presolve 종료와 140초 Root 시간 제한이 모두 나타났다. 후보 내용에 따라 풀이 시간이 달라지며 작은 Binary 수나 단일 Pool 속도만으로 정식화·전체 Beam을 기각하지 않았다. Restricted ObjBound는 Global LB로 사용하지 않았다. Source NumericFocus/Feasibility/Integrality/Scale/Method/Seed 정책은 유지했다.

## Adaptive Beam 품질과 피드백

96슬롯 모든 시간대의 실제 Near-Critical Line/Phase/Slot을 반영하고 원본 Signed P/Q 계수를 보존했다. 이동 구간의 기존 위치 서비스 상실, 도착 후 서비스, 이동에너지, 미래 충전 기회, 종단 SOC 복원 부담과 충전 Rebound를 스코어에 반영한다. PCS 스코어 배열 연산의 변경 전후 회귀는 4대 STAY·단일·복수 MOVE에서 최대 1e-12 이내 일치했다. 스코어와 SOC Reachability는 휴리스틱이며 인증 UB/LB 또는 미검증 Dominance로 사용하지 않는다.

FULL PASS Raw의 실제 P/Q/SOC, λ 조합, Grid와 예측 오차를 다음 Pool에 반영하고 차량·출발·목적지·재접속·MOVE 수를 다양화했다. 같은 수학적 모델 재실행을 Signature로 방지했다. 동일 Pool의 다른 정식화 비교는 별도 Benchmark로 기록했다. 후보별 점수·이동 메타데이터·λ 선택·Joint UB는 Candidate CSV/JSON에 보존했으며 공동 UB를 개별 경로의 독립 성능으로 귀속하지 않았다. 공동 UB가 일정하여 Spearman 순위상관계수는 정의되지 않는다.

차량별 실제 평가된 서로 다른 경로 수는 {"MESS01": 143, "MESS02": 138, "MESS03": 115, "MESS04": 158}다. 경로 수 자체를 성공으로 간주하지 않고 FULL UB 개선 여부를 함께 평가한다. 단독·2대·3대 탐색은 기존 Ablation이며 이번 주 결과는 4-MESS Joint다.

## 예산·무결성·안전

Pilot 63.641999960초 + V2 956.925999880초 + V3 769.629000425초 = 1790.197000265/1,800초다. 잔여 9.802999735초와 안전 반환 여유를 기록했고 예산 초기화는 0회다. 이전 별도 실행 및 중단 Pilot의 역사 Native 1738.949000359초는 분리 보존한다. 이 작업 전체 역사 합계 3529.146000624초를 한 실행의 승인 예산으로 해석하지 않는다.

Source18r의 원본 물리·Grid·PCS16·이동에너지·ETA·96슬롯·종단 SOC·고정 Forecast/AIDC·목적함수는 변경하지 않았다. Restricted MILP의 Original FULL 부분집합 포함성과 정확한 Source 계수·행·정의된 Raw Lift를 독립 감사했다. Heavy Worker 1, Threads 1, RAM/Commit Gate와 B1 보호를 유지했다. 최대 실측 Private Commit 2.885GiB, 최소 가용 RAM 10.916GiB, 최소 가용 Commit 26.794GiB다.

추가 K32/K48 Optimize, B1/B3/IEEE8500/다른 날짜/May 캠페인/Actual Fresh AC는 실행하지 않았다. 모든 채택 UB는 Original FULL Replay PASS다. Source·Policy·기존 Pilot·V2 원장/Raw SHA를 보존했으며 최종 독립 감사는 PASS다.

## 해석과 한계

UB 개선 여부는 위 수치 그대로다. 개선이 없다면 후보 입장 규칙, 제한된 Beam 폭/깊이와 여러 Grid 병목·SOC/이동/복원 비용을 포함한 탐색의 한계를 기록한다. 전체 원본 DAG의 물리적 개선 불가능성은 증명하지 않았다. 작은 표본의 준비·정식화 속도 결과를 다른 계통·날짜·후보집합으로 일반화하지 않는다. 최종 Guard/Readback/FULL/Runtime 증거는 이 폴더, 변경하지 않은 V2·Pilot·기존 Joint 증거 폴더에 보존했다.
