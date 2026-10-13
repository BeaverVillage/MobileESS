# V42 B2 — Adaptive Beam·4-MESS Joint 정식화 재설계 최종 보고서

IEEE123 B2 May01(2025-05-01), 원본96슬롯 Source18r Exact C3A+Dense. UB 개선은 없었다. 직접 대체 정식화는 수학적·물리적 무결성 검증에 통과했지만 실제 계산시간이 악화되어 채택하지 않았다. 독립 감사 PASS 후 제출하는 제한 실험의 부정적 결과다.

## 1. 안전 종료와 예산 정정

기존 Controller125764는 소유권·부모PID·생성시각·명령줄·Worktree를 확인한 후 Stop-Process로 신규 Dispatch를 차단했다. 마지막 Worker142760은 원본120초 TimeLimit으로 정상 반환하고 Raw를 저장한 뒤 모델을 해제했다. 마지막 호출 Runtime120.74799990653992초, Status9, NodeCount1, Root LP 미완료, Restricted Bound0.3380383194213583이다. 이 Bound는 Global LB가 아니다.

기존 실제34개 호출 누적 **1696.113000154495초**와 기존 잔여103.88699984550476초를 먼저 확정했다. 잔여 예산 Pilot 두 호출의 실제 **42.836000204086초**도 보존했다. 사용자의 “잔여로 하면 안되고 처음부터 돌려야지” 정정으로 별도 신규 실행의 Native 한도를 **1,800초**, 초기 사용량을 **0초**로 설정했다. 기존 원장·Source Seal·Policy·Raw는 초기화하거나 덮어쓰지 않았다.

신규 실행 실제 사용량 **63.641999959946초**, 미사용 한도 **1736.358000040054초**. 이 작업의 세 실행 단계 실제 합계 **1802.591000318527초**. 과거 PR2191795.0249993801117초·PR220724.820999622345초는 더 오래된 별도 연구 비용이다. UNKNOWN Runtime은0개다.

원본 실행 Worktree는 D:/v42_b2_global_local_multistart_dual1800_20261013이고 실제 실행 코드는 로컬 미Push 버전이었다. PR220 HEAD를 실행 코드라고 간주하지 않았다. 이전 코드·정책·Raw717개 파일의 SHA를 보존하고, 새 개발은 별도 D:/v42_b2_adaptive_compact_joint_20261013에서 수행했다. Source/Policy SHA는 PHASE0_SAFE_STOP.json과 각 EXECUTED_SOURCE_HASHES.json에 기록했다. B1·다른 Codex·시스템 프로세스는 중단하지 않았다.

## 2. 기존 Joint 정체 원인

6~24개 후보와 교체 모델을 포함한 Joint26개 및 서로 다른 저장 운전벡터33개를 읽기 전용으로 분석했다. 현재 생성기는 원래 PR219의 부분 경로 Beam을 실행한 것이 아니라 정적 한MOVE 열거와 일부 두MOVE 확장으로 후보를 생성했다. 두 번째 출발은40/64/80슬롯, 일부6개 목적지, 첫8개 대표 경로에 편향됐다. 평가 후보 합집합에서 MESS02·04 단일MOVE는 각각5개, MESS03의 세MOVE는 PR220 경로 하나였다. 차량별 원본 Arc 대표 비율은 약1.29~2.36%이며, Arc 비율은 전체 경로 가능영역의 대표율이 아니다.

원본 DAG의 위상적 최대 MOVE 수는 차량별57~59다. 이것은 Grid·SOC·PCS를 모두 만족하는 물리적 이동 최대 횟수가 아니다. PR219의 깊이3, 개발 Beam의 깊이4는 휴리스틱 한도다. STAY·한MOVE·복수MOVE를 허용했고 이동 횟수를 원본 목적문제에 강제하지 않았다.

초기 모델들은 작은 Restricted Pool에서 Warm UB로 Presolve 종료했고, 후기24개 모델 두 개는 Root LP 제한시간에 걸렸다. 후보 품질 부족과 Root 지연을 분리했다. 이 두 현상으로 FULL 물리적 개선 한계를 증명할 수 없다. OPTIMAL은 해당 제한 후보집합과 Solver 허용오차의 결과이며 원본 전역 최적성 증명이 아니다.

## 3. 정수 중복과 정확한 정식화

실제 Source Binary9,322개는 node_activity8,938개와 Charge Mode384개다. 연속 Route Flow207,736개는 Binary와 별도로 감사했다. 정확한 한경로 선택식 `sum_r lambda[u,r]=1`과 원본 경로 incidence 때문에 모든 Route/Node 좌표는 literal0/1로 결정된다.

첫 Exact Extended Formulation은 원본 좌표와 모든 원본 CSR 행을 유지하며8,938개 Node의 중복 정수 지정을 제거했다. 실제 Native0·Raw FULL 검증을 통과했다. 두 번째 Direct Formulation은 Route/Node216,674개 좌표를 삭제하고 `x_dense=T z`, `A_compact=A_source T`로 모든 원본715,596개 행을 의미적으로 유지했다. RHS·Sense는 바꾸지 않았고,4개 한경로 선택 행만 추가했다. 모든 lambda 열의 계수 합을 원본 계수의 정확한 dyadic 분수 합으로 독립 검증하여 상수 이동이나 부동소수 RHS 반올림을 피했다.

Mode384개, Pch/Pdis/Q/SOC와 나머지137,603개 Source 좌표의 Bound·Type·Objective는 그대로 유지했다. 원본 Arc/Node/Flow/Alias·DAG·ETA·이동에너지·종단 SOC·PCS16·AIDC·전체 Grid의 의미는 기존 독립 alias 증명과 Original FULL Replay로 검증했다. 경로 제한 모델은 FULL 가능영역의 부분집합이며 FULL과 전체 가능영역이 같다고 주장하지 않는다.

24개/차량이면 이론적으로384+96=480 Binary지만 이번 실제 작은 모델은8개/차량으로384+32=416 Binary다. Direct 모델의 변수137,635개, 행715,600개, nonzero약7.01M이다. Sparse Fill-in은 증가하지 않았다. Native137,635차원 Raw와354,277차원 Dense 역변환 Raw를 따로 저장했다. `T z`는 모델의 정의된 역변환이며 숫자 반올림·클리핑·수리가 아니다. 원본 PR220 Warm 점은 bit 단위로 복원됐다.

## 4. 실제 계산 비교와 채택 결정

| 정식화 | 입력 변수 | 입력 Binary | 실제 Native초 | Presolve초 | 탐색 Node |
|---|---:|---:|---:|---:|---:|
| OLD_JOINT | 354,309 | 9,354 | 18.729000 | 17.95 | 0 |
| EXACT_EXTENDED_FORM | 354,309 | 416 | 18.747000 | 18.00 | 0 |
| EXACT_DIRECT | 137,635 | 416 | 29.366000 | 28.12 | 0 |
| ADAPTIVE_DIRECT | 137,635 | 416 | 34.276000 | 32.99 | 0 |

OLD_JOINT·EXACT_EXTENDED_FORM·EXACT_DIRECT의 경로 Pool은 동일하다. Source 비용은 과거·잔여 Pilot·신규 실행으로 나눴다. Direct는 입력 변수 약61%를 제거했지만 동일 Pool에서18.728999853134155→29.365999937057495초로 악화됐다. 단순 정수 지정 제거 EF는18.746999979019165초로 이전과 사실상 같았고 속도 개선을 입증하지 못했다. Presolve가 이미 중복 정수를 정리하므로 입력 Binary 감소만으로 실제 난도가 줄었다고 말할 수 없다. 단일 사례 관측이며 일반적인 속도 배율을 주장하지 않는다.

**직접 대체 정식화는 채택하지 않는다.** Source Exact Joint Extended Formulation을 기준 Backend로 보존한다. 첫 Pilot 최대240초에서 FULL UB 이득과 계산 이득을 모두 확인하지 못해 잔여1,736.358초를 자동 소비하지 않았다. 원본 코드·Policy를 수정하지 않고 FINAL_BACKEND_DECISION.json에 거부 결정을 별도로 기록했다.

## 5. Adaptive Minimax Beam와 최적화 피드백

기존 Minimax는 알려진 PR220 해 자체를 약0.1114799241 높게 예측했다. 실제 검증된 incumbent의 차량별 Signed P/Q 기여를 기준으로 보정하고 변경 차량의 서비스·이동 중 출력 중단·PCS·SOC·충전 Rebound 전망을 덧붙였다. 현재 해 기준 점수 일치는 구성상 기준 보정이며 성능 이득이나 인증 Bound가 아니다.

개발 Beam은 PR219 Label·Minimax와 PR220 원본 DAG closure·retiming을 재사용했다. 신규 Joint 결과를 FULL 검증한 뒤 실제64개 다중 병목·SOC/P/Q·충전 Rebound·예측 오차를 반환했다. 후속 Native0 피드백에서는 검증된 PR219 Beam 본체(폭64, 휴리스틱 깊이3)에 실제 incumbent 기준 scorer를 주입하고 개발 깊이4 후보도 reservoir에 유지했다. 부분경로에 위치·시간·에너지·MOVE·SOC 도달 가능 상한·서비스시간·종단 회복 전망을 사용했다.

안전 제외는 원본 Arc Domain과 낙관적 SOC/종단 SOC 도달 상한 필요조건이다. Beam 폭·깊이·점수·8개 입장은 휴리스틱 가지치기이며 전역 불가능성 증명이 아니다. 후보 수를24→30→40으로 늘리지 않았다. 매 차량 STAY·한MOVE·복수MOVE와 PR220/검증된 우승 경로를 유지했다.4차량 provisional 경로의 공동 최대 부하와 위치·출발·재접속 다양성으로 후보를 선택하며 이동을 강제하지 않았다.

피드백 후 차량별 reservoir는 약760~803개,8,729개 고유 단독 경로를 생성한 원래 Beam 결과를 활용했다. 최종 입력은8개/차량이다. 새 Pool Signature는 `a28fd2042132db9f8276a1ae10645c6ffffec899d0ce27549349107cc0c91f68`이고 기존 두 평가 Pool과 다르다. 이 후속 Pool의 정합성과 FULL 부분집합 증명은 Native0 PASS이며, 새 Pool의 운전 성능은 Native를 실행하지 않아 미검증이다. MIP의 LP dual 가격을 만들지 않았고 정확한 Reduced-Cost Pricing·Column Generation이라고 부르지 않았다.

## 6. 실제4대 선택·P/Q/SOC·Grid

신규 두 MILP 모두4대 lambda와384 Mode·Pch/Pdis/Q/SOC를 한 모델에서 자유롭게 결정했다. 결과는 MESS01=0MOVE, MESS02=0MOVE, MESS03=3MOVE, MESS04=0MOVE다. 이 선택은 Solver 결과이며 세 차량을 강제로 STAY시킨 모델이 아니다. 모든 차량 MOVE 조합도 위상적으로 선택 가능하지만 모든 조합의 SOC/Grid 가능성을 가정하지 않았다.

- MESS03: Arc 4954, STA08 출발 4 → IDC06 도착 6, 재접속 7, 21.904604877305 kWh
- MESS03: Arc 37751, IDC06 출발 64 → IDC05 도착 66, 재접속 66, 23.328662383891 kWh
- MESS03: Arc 44900, IDC05 출발 77 → IDC01 도착 79, 재접속 79, 21.431159059228 kWh

총 이동에너지는 66.664426320424kWh. SOC는 각 차량97개 경계, 초기·종단760kWh, 원본440~1080kWh·PCS16·300kW·400kVA·효율0.95 조건으로 검사했다. 실제384행 P/Q/Mode와 SOC를 BEST_ACTUAL_JOINT_96_SLOT_MESS_PLAN.csv에 별도 저장했다. Global Best 원본 PR220 계획도 별도 CSV로 보존했다.

Original FULL1,130,336개 행·Dense715,596개 행의 검증과96슬롯 전체403,968개 열적 얼굴 계산을 유지했다. 이전 저장벡터33개마다 모든 원본 행 활동을 계산하고 매96슬롯 최악 행·상위100개·준활성 수·SOC/PCS/P 포화를 기록했다. line.sw2/A/42 또는 line.l10/A/19 두 행만 분석하지 않았다. line.sw1/A 및 line.sw2/A의 여러 슬롯에서도 준활성·활성 얼굴이 관찰됐다. 실제Signed Pch/Pdis/Q 기여와 양의 충전 Rebound를 OPTIMIZATION_FEEDBACK_01.json에 기록했다. 후보는 공급 상실과 이동 후 기회를 고려하지만 FULL 가능 운전과 같은 의미의 heuristic 기여는 아니다.

## 7. 인증 결과

- BEST_GLOBAL_UB = **0.5398310226338695**
- BEST_MOVING_FEASIBLE_UB = **0.5398310226338695**
- 신규 실제4-MESS Joint FULL UB = **0.5398310226338695**
- PR220 대비 UB 개선량 = **0**
- 인증 Global LB(K48) = **0.46498486997548166**
- Global Gap = **13.864737208545%**

3% Global Gap을 달성하지 못했다. 신규 Restricted Bound는 Global LB로 채택하지 않았다. 기존244 Binary K32 선택 실험의 인증 개선은0이었으므로 재실행하지 않았다. Conditional LP는 과거 median 생성15.740초·인증 제외0개의 실용성 실패 증거를 근거로 자동 Screening하지 않았다. 신규 LB Native와 Conditional LP Native는0회다.

## 8. Native·Wall·메모리

전체실행 비용은 ALL_SESSION_NATIVE_RUNTIME_LEDGER.json, 생성·Native·Worker Wall·Root·Presolve는 SAME_POOL_FORMULATION_COMPARISON.json과 MEMORY_NUMERIC_WALL_AUDIT.json에 구분했다. 신규 Controller Wall은 129.140초, 신규 Native0 Gate Wall은 156.456초다. 준비·Beam·독립 검증·모델 변환 비용은 Native Optimize Runtime과 별도로 기록했다.

이 작업 호출 표본의 최대 실제 Private Commit 3.396GiB, 최대 RSS 1.891GiB, 최소 가용 RAM 12.405GiB·가용 Commit 30.473GiB. Heavy Worker1·Threads1과 RAM4/Commit6GiB 및 실제 모델 성장 예비 공간 Gate를 통과했다. 원본1e-13~4e2 계수 범위 경고는 보존됐고 수치 허용오차·물리식을 변경하지 않았다. 신규 Raw FULL Replay2/2 PASS, Numerical/Resource 중단0, UNKNOWN Runtime0이다.

## 9. 실패와 미검증

이동성 탐색에서 새 좋은 FULL 해를 찾지 못했다. 정적 후보의 깊이·시간·목적지 편향, 기존 점수의 incumbent 기준 오차, 큰 물리적 연속 모형의 Presolve 비용이 관찰된 원인이다. 입력 크기를 줄여도 계산이 개선되지 않았으므로 직접 대체를 채택하지 않았다. 새로운 피드백 Pool은 폭·종류·다양성이 개선됐지만 실제 UB 효과는 미검증이다. 제한 후보집합의 실패는 물리적 개선 불가능성 증명이 아니다. 단독·2/3대 탐색은 Ablation/초기화 증거이며 본 실험의 결과는 실제4대 Joint 두 모델에서 얻었다.

기존 V1 Raw의 추가lambda 배열 때문에 생긴 packet 형식 실패는 lossless point-only 분리 후 Original FULL 검증된 기존 증거로 보존했다. Phase0 CLI에서 PowerShell이 숫자 인자를 줄인 비교 실패도 실패 증거를 보존하고 문자열 인자로 다시 검사했다. 원본 Raw 숫자를 수리하거나 원래 실패를 덮어쓰지 않았다. 개발 초기 Grid 슬롯 표시 오류는 원본 행 이름의 첫 axis로 수정했으며 수정 전 분석을 development_v0에 보존했다. 이러한 전송·분석 오류와 물리적 불가능성을 구분했다.

## 10. 감사와 제출

독립 이름 기반 incidence·Source 계수 분수 합·전체物리 변수 Bound/Type·CSR/RHS/Sense·Native Readback·Raw inverse·Original FULL·예산·Source 보호 감사 PASS. Source18r `497609b46faa14ea7e32a9483a333ab32fd264ef`, PR220 `b9684fa0999b88092d0cd38229f3453ef3f901b4`와 모든 원본 물리 Case를 보존했다. 이후 Commit/Push 및 새 Draft PR으로 이 부정적 결과와 재사용 가능한 검증 코드를 제출한다. B1/B3/IEEE8500/다른 날짜/May 전체 캠페인/Actual Fresh AC는 실행하지 않았다.
