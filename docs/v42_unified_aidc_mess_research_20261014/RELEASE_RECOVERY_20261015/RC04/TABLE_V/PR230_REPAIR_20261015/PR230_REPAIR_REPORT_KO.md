# PR230 결함 수정 및 May01 재실행 준비

이 보고서는 Native0 검증과 실제 Solver/Actual 결과를 분리한다. 과거 B0 FULL_PASS는 보존된 원래 Source/Case의 결과이며 현재 Release 재인증으로 바꾸지 않는다. May02–31 Heavy 실행은 승인되지 않았다.

## 추가 결함 4건

| 결함 | 수정 및 검증 |
|---|---|
| 재시작의 JSON 일괄 읽기 | JSON 구조를 검사하고 NPZ·로그는 원본 SHA256/크기로 검사한다. 실제 NPZ 정상 재시작, JSON/NPZ/로그 변조·누락 및 JSON scalar 거부를 검증했다. Raw와 이전 Native 원장을 쓰지 않는다. |
| Launch Gate 우회 | CLI, 직접 Arm, 캠페인 API, 직렬 실행기 모두 같은 Gate를 통과한다. 현재 Git/Release/Source/Science/Case/Policy 및 날짜별 명시 승인 예산을 검사한다. 승인된 Arm·Actual 슬롯과 다른 CLI 인자를 거부한다. May01 Scope로 다른 날짜를 실행할 수 없다. |
| 과거 PASS 오인 | 현재 원본 Reference, A/M 최종 부모·Anchor·점·Case, Actual Policy/Trace, Fresh 원본 측정과 SHA를 재검증한다. 96슬롯 정착 전압·선로·변압기 검증을 기존 물리 검증기로 독립 계산한다. 다른 Case/Source, Header 변경 및 16슬롯의 Full96 승격을 거부한다. 대표 날짜 승인에도 실제 16슬롯 정착 Raw가 필요하다. |
| M/K48 고정 자원 PASS | 모델 생성 전과 Native 진입 직전에 실제 Available RAM, Commit, RSS 및 다른 Heavy PID를 검사한다. Native 진입에는 살아 있는 현재 PID의 Lock·Nonce·Ledger·Authorization 일치가 필요하다. 부족·충돌 시 Native 진입을 막고 거부 원본을 추가 저장한다. 진입 전 차단은 이전 model.Runtime을 다시 차감하지 않는다. |

독립 감사는 `FOUR_DEFECT_AUDIT01/INDEPENDENT_AUDIT_RESULT.json` 및 덮어쓰지 않은 AUDIT02–05 보충 감사에 보존했다. 최종 Source와 최신 사용자 fresh Native 승인을 반영한 `REGRESSION06/RESULTS.json`은 **965 PASS**다. 원본 682개 ID를 보존했으며 실패·Skip·실제 Native 호출은 0이다.

## 원래 요청 12항목

| 항목 | 검증 시점 상태 |
|---|---|
| 1. E1 도메인 누락 | 원본 typed issuer를 1,624 UID 전부 재발행해 정확히 비교했다. 누락 복구 부분집합 992 UID/+3,667 시작 슬롯, 양의 잔여 서비스 전체 1,555 UID/5,976 시작 슬롯을 구분한다. 만료 RUNNING 69 UID/187 GPU 물리 점유와 서비스·Carry를 보존한다. `DOMAIN_AUDIT01` 참조. |
| 2. DW Phase I/P1 연결 | 원본 `phase.run`, 전체 Pricing, 원본 Compact assembly와 기존 Integer MILP/FULL Replay를 연결했다. `DW_NATIVE0_04`에서 **실제 FULL→DW 독립 수학 동등성 및 전체 1,555개 Pricing 클래스 연결 PASS**, Native 0. 원본 2,108,858행/946,756열의 Runtime equality 69,542개를 exact 소거하고 상수 aux 180개를 원본 그대로 유지했다. 목적·계수·변수 범위·행 전부 보존하고 정수성만 완화했다. 실제 Phase I/P1의 Phi/LB 인증은 아직 미실행이다. |
| 3. 현재 DW Global LB | **NULL**. 실제 Phase I/P1 인증 전이며 과거 May12 LB나 MILP 내부 Bound를 이전하지 않는다. |
| 4. 현재 FULL 정수 UB | **NULL**. 중단된 EXECUTION02 B1에서 유효 정수해가 없었다. |
| 5. AIDC Global Gap | **NULL/NOT_CERTIFIED**. 검증된 같은 문제의 LB·UB가 없으면 0%로 만들지 않는다. |
| 6. 기존 B1 상태/Native | 과거 실행은 Status 11/SolCount 0으로 종료했으며 1,189.1240000724792초 + 이전 776.2689998149872초 = **1,965.3929998874664초**를 원장 그대로 보존했다. 내부 ObjBound 0.6131179484539293은 DW 인증이 아니다. **최신 사용자 명시 승인에 따라 새 B1 예산 주기는 0초 시작/A1 5,400초이며 과거 주기 사용량을 새 주기에 합산하지 않는다.** 같은 새 주기를 재시작할 때는 누적을 이어간다. |
| 7. B1→B3 재사용 | 정식 경로와 ATTEMPT별 검증 완료 원장을 탐색한다. Science/Case/Matrix/Domain/Objective 및 정수점이 정확히 같을 때만 B3 FULL Replay와 Arm별 Acceptance를 새로 만든다. 잘못된 최신 Pointer나 실패 Attempt를 채택하지 않는다. |
| 8. Gap 기준 | AIDC 0.5%, MESS Global 3%. Restricted Joint 진단과 K48 도달/실제풀이/유효성 인증을 분리한다. Gap 미달은 FULL-feasible 물리 평가를 막지 않는다. |
| 9. 원장/Worker/Raw | 이전 원장과 중단 호출을 읽기 전용으로 보존했다. 최신 사용자 승인인 fresh cycle은 별도 Authorization/새 Ledger에서 0초 시작하며 이전 원장 SHA를 역사적 보존 증거로 핀한다. Source별 실행 증거를 분리하고 기존 결과를 덮어쓰지 않는다. Worker 1/Threads 1, P2 0, R2 HOLD. |
| 10. 네 Arm 상태 | B0: 원래 Source의 Actual96/Fresh96 FULL_PASS 보존. B1: 과거 실행 INTERRUPTED_NO_FEASIBLE, Actual/Fresh 미실행. B2/B3: 실제 실행 전. 최신 승인에 따라 검증 후 B1을 새 예산 주기 0초부터, 이전 점·Bound·DW 인증을 재사용하지 않고 계산하고 B2→B3를 직렬 실행한다. 승인 Arm 목록에서 B0를 제외한다. |
| 11. 미완료 | 확인된 네 추가 결함과 Native0 구조 차단 사유는 해소했다. `DW_NATIVE0_03`의 접근 위반은 역사적 실패 Raw로 보존한다. 비동기 진단 스레드 없는 04 재검증은 통과했으며 원인 인과관계를 단정하지 않는다. 기존 V6 캐시로 같은 실행 내 중복 Reference 조립 258.53초를 제거했다. May01 B1/B2/B3 실제 계산과 그에 따른 Phi/LB/정수 UB/Gap·Actual96/Fresh96는 실측 미완료다. |
| 12. May31 장애 | May01 현재 Source 네 Arm의 실제 정착 Full96 증거, 대표 May02/10/12의 실제 Canary Raw와 별도 승인, 최종 Release/Git SHA 및 날짜별 실행·예산 승인이 필요하다. 31일 입력 연결 PASS는 실행 승인이나 물리 PASS가 아니다. |

## 31일 Production 연결

`MONTH_NATIVE0_02`에서 31일 × 네 Arm **124개 입력·Stage·Policy·실제 Executor 연결을 모두 검사**했다. 날짜별 독립 D0, Known/Unknown 분리, Runtime/CC4, Demand/PV·전력망 계수, Source/Case 및 96슬롯 축을 확인했다. May02/10/12도 서로 다른 입력과 초기 상태를 사용했다. 이전 날 결과·상태를 가져오지 않았고 미래 Actual 자료를 Planning에 파싱하지 않았다.

`EXECUTOR_REBIND_FINAL02/FINAL_EXECUTOR_REBIND.json`에서 **최종 Source 실제 Executor 124/124 재바인딩 PASS**다. 31개 최종 Source, 공개입력 342개, 원본 과학 Source 42개의 bytes를 재검증했다. 원본 compiler fallback은 없었다. 기존 원본 감사의 `NOT_CERTIFIED_NATIVE0_MONTH`와 변경 중 중간 재바인딩 Raw는 조작하지 않고 그대로 남겼다. 원래 11 SVR/7 RegControl/AUTO 및 MESS P/Q/SOC/경로 제약은 보존했다. 이는 31일 Heavy 실행이나 전기적 실행 완료가 아니다.

향후 대표 Canary16은 별도 `REPRESENTATIVE_CANARY16_APPROVED` 승인이 있어야 한다. 현재 Release/Case/예산과 May01 네 Arm 실제 Full96를 먼저 검사하고 May02/10/12의 16슬롯만 허용하므로, Canary 생성과 월간 승인 사이의 순환 의존을 없앴다. 이번 작업에서 대표 날짜 실행 권한은 발행하지 않았다. May31 Full96 실행에는 대표 날짜의 실제 정착 Raw 및 별도 승인이 계속 필요하다.

## 증거 보존

- `STOP_AUDIT01`: 종료 상태, Native 및 B0 원본 결과의 당시 스냅샷과 실행 Source.
- `DOMAIN_AUDIT01`: 원본 E1 재발행, UID별 도메인 및 보존 재검사.
- `DW_NATIVE0_EVIDENCE_01`: 최종 DW Native0 PASS, exact 동등성·Runtime 투영·1,555개 클래스·Source·기존 V6 캐시·역사적 실패 원문 및 41개 scoped 회귀.
- `MONTH_NATIVE0_02`: 124개 날짜별 원본 입력 감사.
- `FOUR_DEFECT_AUDIT01`–`05`, `REGRESSION06`: 독립 결함 감사 및 최종 전체 회귀.
- `MONTH_EVIDENCE_02`, `FINAL_EXECUTOR_EVIDENCE_01`: 464개 원본 공개입력과 최종 124개 Source 재바인딩의 lossless ZIP. 합계 38,784,999 bytes, 전 entry SHA/크기 readback PASS.
- `PRESERVED_BASELINE_EVIDENCE_01`: 기존 B0 Actual/Fresh 원본 및 Native 원장 lossless ZIP, 49 entry/6,480,781 bytes, readback SHA/크기 PASS. 현재 Release의 B0 재인증으로 바꾸지 않는다.

실제 재실행 대상은 **EXECUTION05**다. 준비만 하고 사용하지 않은 EXECUTION03/04는 중단 표식으로 봉인했다. EXECUTION05의 최초 원장은 **Native 0초, A1 5,400초**, 과거 1,965.3929998874664초는 별도 읽기 전용 archive다. B1에는 이전 점·Bound·DW 인증을 입력하지 않는다. B0를 제외한 B1→B2→B3를 기존 Production 캠페인 API의 실제 Executor와 날짜별 체크포인트로 직렬 실행한다.

대용량 원본 FULL sparse/배열과 실패 Raw도 로컬에 그대로 보존한다. 압축 제출물은 원본 파일별 SHA와 압축 해제 후 SHA 검증 목록으로 연결한다.
