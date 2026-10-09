# B2 초기 Native 호출 진단과 향후 seed 정책

현재 세 B2 Solver는 변경·중단·재시작하지 않았다. 수정은 별도 worktree와
codex/v42-b2-seed-policy 브랜치에만 있다. 활성 체크아웃 D:/MobileESS_V42의
V13 코드, 요청, manifest, ledger, Scheduler 작업에는 쓰지 않았다.

## 현재 병목 판정

INITIAL_NATIVE_READ_ONLY.json에 시각별 실제 callback Runtime과 PID를 기록했다.
세 호출은 첫 CURRENT_DAY_UNRESTRICTED_P1_SEED에 머물러 있다. 현재 콜백은
Runtime만 보고하며 OutputFlag=0인 로그에는 시작 헤더만 있다.
SolCount, incumbent, BestBd, 실제 Native Gap, root/node는 UNKNOWN이다.
따라서 첫 정수해 부재와 0.5% 증명 지연을 구분할 수 없다.
독립 초기해 인증 파일이 없다는 것은 Solver 내부 incumbent 부재의 증거가 아니다.
CPU 누적 증가와 Runtime 보고는 활동의 증거이며 presolve/root/tree 단계는 증명하지 않는다.
progress와 ledger는 서로 다른 시점의 비트랜잭션 읽기이며 콜백 Runtime을
완료된 누적 ledger Runtime과 혼동하지 않는다.

재현 가능한 읽기 전용 도구:

    python -B -X utf8 -m v42_b2_start_recovery_v13.seed_audit ACTIVE_ROOT REPORT_OUTSIDE_ACTIVE_CHECKOUT

이 도구는 Solver에 연결하거나 신호를 보내지 않는다. 출력 파일은 활성 체크아웃 밖으로 제한한다.

## 0.5% 설정의 근거 조사

v42_m1_research/lb.py의 공용 build_model이 MIPGap=.005를 설정하고,
기존 B2 _seed_integer가 이를 그대로 상속한다. B2 최종 목표는 m_stage.TARGET=3/100이다.
초기 seed의 역할은 원본 제약을 만족하는 현재 날짜 정수 witness를 얻는 것이다.
초기 _strict_ub는 C3A 및 FULL의 literal 정수/이진 패턴, 원본 행/경계,
96슬롯 route/SOC/PCS/charge-mode 물리 검증, exact 목적함수 transport를 검사한다.
이 검사는 Native MIPGap을 사용하지 않는다. 최종 승인도 기존 rational dual 검사와
엄밀한 UB/LB bracket의 exact gap으로 판정한다.
다른 M1 연구용 최종 납품 검증에는 .005 파라미터 감사가 있지만 B2 seed 승인 경로에는 없다.
따라서 이 경로에서 seed에 0.5%를 요구할 과학적 필요는 찾지 못했다.
검색 정지 조건을 3%로 바꾼다고 첫 정수해를 더 빨리 찾는다는 보장은 없다.

Gurobi 문서에서도 MIPGap은 incumbent와 best bound 사이의 검색 종료 조건이다.
[MIPGap 정의](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-MIPGap).

## 준비된 구현

1. V13 B2 adapter의 seed 호출에만 MIPGap=.03을 적용한다.
   공용 A/M builder, B1 정책, 이후 adaptive U/L 알고리즘과 FULL/Compact/C3A 생성은 유지한다.
   seed identity에 실제 정책과 MIPGap을 기록한다.
2. B2 Native 호출의 TimeLimit=min(requested_seconds, 날짜 잔여 Native 예산)으로 설정한다.
   요청이 None일 때만 잔여 예산을 사용한다. 0/음수/NaN/무한대/bool 요청은 Native 진입 전에 거부한다.
   요청 900초의 초기 seed는 잔여 예산이 충분하면 TimeLimit=900이다.
   기존 seed 배분 공식 min(900, remaining/3)은 유지한다.
3. Native 콜백에 탐색 단계, best incumbent, BestBd, 계산한 Native Gap, node/iteration 및
   관측 시각을 기록한다. 실제 Model.SolCount는 optimize 종료 후에 읽는다.
   콜백의 SOLCNT는 별도 필드로 기록한다. 특히 MIPSOL_SOLCNT는 이전 콜백 해 개수라
   0이어도 incumbent 부재로 해석하지 않는다. 미관측 값은 UNKNOWN이다.
   [콜백 값과 의미](https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/callbacks.html).
4. Native 값은 진단 필드에만 기록한다. UB/LB/certified_gap으로 승격하지 않는다.
   초기해는 기존 _strict_ub를 그대로 통과해야 한다. 최종 3%는 기존 exact 인증기로만 판정한다.

TimeLimit 종료에는 속성 계산 등의 추가 시간이 필요할 수 있다.
900초를 넘긴 실제 Runtime도 전부 누적 차감하며 5400초 초과는 승인하지 않는다.
[TimeLimit 종료와 Runtime](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-TimeLimit).

## 900초 종료 후 실패·복구 계약

- SolCount=0이면 기존 TIME_LIMIT_NO_VALID_INCUMBENT 분류와 명시적인 seed 실패 사유를 남긴다.
  INFEASIBLE 상태는 INCONCLUSIVE로 남겨 입력·수치 진단 대상으로 둔다.
  incumbent가 있어도 literal 정수/FULL 물리 검증 실패면 PHYSICAL_FAILURE이며 UB를 만들지 않는다.
- B2_SEED_FAILURE_AND_RECOVERY.json에 case SHA, 실패 이유, 종료 ledger SHA,
  실제 누적 Runtime, 잔여 Native 예산, 인증 bound 없음, 자동 재시도 없음 등을 저장한다.
  M_STAGE_RESULT와 상위 Worker RESULT도 기존 실패 분류로 종료한다.
- 숨은 5400초 재호출, 자동 파라미터 변경, 무한 seed 재시도는 하지 않는다.
  이미 사용한 시간은 모두 보존한다. 예: 실제 901.2초 사용 시 같은 날짜의 잔여 예산은 4498.8초다.
- 복구는 기존 시도의 자연 종료 후 동일 arm/date의 별도 attempt로만 한다.
  정식 신규 source-version 전환 계약에서 이전 RESULT/request/case/ledger와 원본 입력 SHA를
  봉인하고 종료 ledger를 연결한다. 모든 이전 시도의 actual Runtime을 중복 없이 이월하고
  새 예산은 5400 - 이전 누적 Runtime이다. 과거 bound/point는 새 인증에 자동 이식하지 않는다.
  현재 날짜 원본 모델을 다시 생성하고 새로운 초기해를 동일 독립 검사로 검증한다.
- Runtime unavailable, inflight ledger, 누락·SHA 불일치 ledger는 복구를 거부한다.
  콜백의 마지막 샘플로 총 Runtime을 추정하거나 0으로 초기화하지 않는다.
  OS 강제 중단으로 정확한 Runtime을 잃으면 해당 날짜 예산을 격리하고 후속 Native 호출을 막는다.

## 활성 캠페인 적용 경계와 보존

현재 V13 manifest는 소스 SHA를 봉인했고 시작한 날짜 재dispatch를 거부한다.
따라서 이 브랜치를 활성 폴더에 병합하거나 기존 manifest를 재봉인하지 않는다.
향후 적용은 활성 3워커의 자연 종료와 Coordinator의 안전한 경계 이후,
새 source-version/attempt의 정식 전환 및 검증으로 수행해야 한다.
900초 실패 복구를 위한 신규 Coordinator 전환 구현은 이 준비 브랜치에서 활성화하지 않았다.
실패 기록과 복구 계약은 준비했으며 현재 캠페인으로의 dispatch는 미수행이다.

현재 워커를 중단할 필요는 없다. 추후 중단이 필요하다면 먼저 각 PID/생성시각,
누적 완료 Runtime 및 inflight 상태, request/manifest/case SHA, 완료 인증서와 RESULT를 보고한다.
원본 시도 디렉터리는 읽기 전용 보존하고 새 시도 경로를 분리한다.
Solver가 자연 반환하기 전 내부 incumbent/tree를 외부 파일에서 복구 가능하다고 약속하지 않는다.
정확한 종료 Runtime이 확보되지 않은 강제 중단은 자동 재실행하지 않는다.

## 검증 범위

Mock Solver 및 소형 CSR fixture로 시간 배분, 실제 Runtime 초과 차감, UNKNOWN 처리,
초기 seed 실패, FULL 행/정수/물리 거부 경로, exact 3% 승인 경계를 검증했다.
물리 판정과 분해/운전계획은 일부 소형 테스트에서 fixture로 대체했다.
새 실제 날짜의 대형 FULL 물리 검증이나 900초 incumbent 발견 성능을 증명한 결과는 아니다.
대형 Native optimize 및 동시 FULL build는 실행하지 않았다. 실행 내역은 VALIDATION.json에 있다.
