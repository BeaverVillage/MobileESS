# B2 초기 호출 제한 수정과 V17 재실행

최신 사용자 지시에 따라 May01/02/03을 정상 중단하고 별도 source/attempt로 재실행했다.
목표는 seed가 날짜 전체 90분 예산을 소진하는 문제를 해소하고 초기해 → 독립 UB/LB 인증 → 기존 Adaptive 절차를 실제 수행하는 것이다. 최종 3% 도달을 보장하지 않는다.

## 중단과 보존

먼저 HOLD_V13.json으로 Coordinator 신규 작업 투입을 차단하고 해당 run의 기존 Coordinator/Watchdog Scheduler를 비활성화했다. 각 worker의 PID/생성 시각 및 전용 콘솔 구성원을 확인한 뒤 CTRL_C_EVENT를 전달했다. 세 Gurobi 호출 모두 INTERRUPTED(11)로 정상 반환했다. Solver 강제 종료는 없었다.

| 날짜 | 최종 Native Runtime(s) | 잔여 예산(s) | SolCount |
|---|---:|---:|---:|
| May01 | 3318.513000011444 | 2081.486999988556 | 0 |
| May02 | 3285.425999879837 | 2114.574000120163 | 0 |
| May03 | 3316.044000148773 | 2083.955999851227 | 0 |

병목은 **첫 정수해 부재**로 확정됐다. 실제 Native Gap은 UNKNOWN_NO_INCUMBENT, 미관측 root/node는 UNKNOWN이다. Runtime이 모두 확정돼 QUARANTINE은 필요하지 않았다. 미종료 inflight, Runtime unavailable, 증거 SHA 불일치 시 후속 Native 진입을 막고 예산을 격리한다.

기존 V13 시도·Solver 로그·checkpoint·manifest·결과는 원래 경로에 보존했다. stop_preservation/에 중단 전후 근거를 복사했다. B0/B1 모델과 완료 결과는 수정하지 않았고 B1 31개 RESULT SHA를 새 manifest에 봉인했다. 새 CHECKPOINT_V17.json은 별도 journal이다.

## 수정 정책

- B2 seed MILP만 MIPGap=.03이다. 최종 TARGET=3/100과 기존 exact UB/LB 인증기는 유지한다.
- B2 실제 TimeLimit=min(requested_seconds, remaining_native_budget)이다. seed 요청은 이월 후에도 900초다. May01 ledger에서 요청/실제 모두900, MIPGap=.03을 확인했다.
- 이전 DateBudget이 requested_seconds를 무시하고 날짜 잔여 예산 전체를 설정한 것이 불일치 원인이다. 중단한 세 호출의 요청900/실제5400도 보존했다.
- 목적함수, FULL/C3A 행, 물리·정수 제약, 전체 route/SOC/P/Q 결정 공간은 변경하지 않는다. May01의 원본/선택 matrix·domain, bundle, anchor, binary_count 7개 식별 필드가 이전 시도와 일치한다. 새 case SHA에는 새 transport 증거 경로도 반영된다.
- 실제 Runtime은 요청 초과분까지 누적 차감한다. 이전 날짜별 예산을 0으로 초기화하거나 새5400초를 주지 않는다.

공용 v42_m1_research/lb.py의 .005를 B2 seed가 상속한 것이 기존 Gap 설정의 원인이다. 초기 seed 승인과 최종 exact 인증은 Native MIPGap을 사용하지 않는다. 이 경로에 0.5%가 필요한 과학적 이유는 찾지 못했다. MIPGap 변경만으로 첫 incumbent 발견이 빨라진다고 보장하지 않는다. [Gurobi MIPGap](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-MIPGap).
[TimeLimit 이후 실제 Runtime 처리](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-TimeLimit).

## 초기해 개선과 검증

기존 stationary 무이동/P=Q=0 후보의 원본 FULL 최대 row violation은 .00945962634612374다. STATIONARY_RESIDUAL_ANALYSIS.json에 기존 인증기가 보고한 최초20개 실패 원본 행의 lhs/rhs/residual과 행렬 SHA를 기록했다. 240개 원본 injection_binding 등식에서 Pch/Pdis/Q=0이면 injection=0임을 확인했다. 실패 행은 voltage_upper이며 rhs<0라 lhs=0이 위반한다. rho_max 변경으로 전압 위반을 해결할 수 없다.

새 보조 LP는 같은 날짜 원본 C3A 행/목적함수를 유지하고 초기 위치의 stationary 정수 패턴만 고정한 채 P/Q/SOC dispatch를 찾는다. 요청120초를 같은 날짜 Native 예산에 차감한다. 고정은 보조 후보 생성 모델에만 적용하고 뒤의 unrestricted seed MILP에는 적용하지 않는다. FULL 독립 검증을 통과한 후보만 MIP Start로 전달한다. 기존 실패 해나 이전 날짜 해는 재사용하지 않는다.

May01 보조 LP는 실제 Native18.67300009727478초에 OPTIMAL로 반환했다. 원본 FULL961472개 행/316743개 열, 208312개 정수·이진 열과 C3A9326개 정수·이진 열 및 96슬롯 route/SOC/PCS/charge-mode 검증 PASS다. rounding/clipping/repair는0이다. 검증된 초기 UB=.6426752324712284, exact UB=2894351937477671/4503599627370496이다.

seed MILP 첫 feasible incumbent 콜백 관측은 해당 호출 Runtime12.121999979019165초였다. 그때 Native incumbent=.6426752324712284, BestBd=.3143088163056946, Native Gap=.5109367835802421이다. 이는 탐색 진단이고 독립 Global Gap 인증이 아니다.

콜백에서 Runtime, incumbent/BestBd/Gap, node/root/phase/iteration, first-incumbent Runtime/UTC를 관측 가능한 범위에서 기록한다. 실제 Model.SolCount는 종료 후 읽고 callback SOLCNT는 별도 필드다. MIPSOL_SOLCNT는 이전 callback 수이므로0을 incumbent 부재로 해석하지 않는다. 미관측 값은 UNKNOWN이다. [Gurobi callback 의미](https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/callbacks.html).

900초 종료 후 독립 검증 가능한 초기해가 없으면 B2_SEED_FAILURE_AND_RECOVERY.json 및 M_STAGE_RESULT/Worker RESULT에 명시적 실패를 저장한다. Adaptive를 통과시키거나 자동 재호출하지 않는다. 복구는 새 같은 날짜 attempt에서 봉인된 종료 ledger/RESULT와 누적 Runtime을 연결해야 한다. UNKNOWN/미종료/누락·변조 증거는 후속 실행을 거부한다.

## 실제 실행과 모니터

실행 source commit=6a74fef5, execution SHA=2dd3bdf8db88a40f63e756e0e99e8f54f42fa4437711d5fb352689bdbae4dc60, attempt=seed_policy_v17_01이다. 기존 mess_build_v13_01 Runtime을 이월한다. 현재 May01 단독 실제 검증 실행이며 May02..31은 대기한다. May01 초기 strict UB/exact LB, 최종 독립 인증서와 정상 Adaptive 종료 근거를 확인해야 나머지를 자동 해제한다. 동시 워커 수는 RAM 여유와 May01 peak RSS로 계산한다(4GB 여유, 워커당 최소4.5GB, 최대3).

http://127.0.0.1:8793/ 모니터는 별도 V18 읽기 전용 코드로 V17 journal/새 attempt를 표시한다. Native Gap과 독립 인증 Global Gap을 구분하고 첫 정수해 시간/node, 이월 Runtime/잔여 시간/attempt/source SHA를 표시한다. B1/B2 날짜별 Actual 최대 선로 부하율 비교는 기존 SHA 검증된96슬롯 AC 배열을 사용한다. 모니터 전환에서 확인된 기존 모니터 PID만 종료했고 Solver/Coordinator는 변경하지 않았다.

## 검증

기존 회귀를 포함한 정책/시간 제한/예산 이월/인증/명시적 실패 테스트165개 PASS. 새 V18 표시 회귀3개와 기존 인증 표시9개 PASS. Node 오프라인 DOM 실행에서 워커 카드3개/Actual31행/May01 단독 검증 상태를 확인했다. 경량 테스트에는 대형 Native optimize가 없다. 실제 May01은 별도 원본 모델 실측이다. 최종 결과와 재개 여부는 MAY01_MEASURED_RESULT.json에 기록한다.
