# V42 B2 V18: FULL 검증 Dispatch LP 직접 채택

V17(PR194)은 May01 dispatch LP로18.673초에 UB=.6426752324712284를 얻은 뒤 seed MILP를900.696초 더 풀었다. seed의 incumbent는1개, NodeCount는1이고 같은 UB/BestBd=.3143088163056946/Native Gap51.094%로 종료했다. 이 시간 내 개선 해를 찾지 못했다는 사실은 확인되지만 상세 root 원인은 기록되지 않아 단정하지 않는다. 최종3%는 Native Gap이 아닌 기존 exact UB/LB bracket으로 판정한다.

V18은 별도 codex/v42-b2-direct-lp-seed 브랜치이며 PR194 위에 쌓인 Draft PR195다.

## 직접 채택 계약

원본 prepare()의 case.point가 없으면 같은 날짜 stationary_dispatch.validated_start()를 호출한다. 원본 FULL/C3A 정수축 및96슬롯 route/SOC/PCS/charge-mode 물리 검증을 통과한 point만 case.point에 저장한다. point vector SHA와 파일 SHA, case SHA 및 strict FULL 검증 필드를 확인한다. SEED_BYPASS_CERTIFIED_DISPATCH.json을 기록하며 M_SEED 호출은0회다. 원본 m_stage.run()은 기존 case.point 계약에 따라 seed를 건너뛰고 원래 _fresh_lp_dual()과 Adaptive로 진행한다.

FULL 검증 실패, 다른 case/date, 변경된 point/파일은 채택하지 않는다. 이전 날짜 해를 사용하지 않는다. FULL/Compact/C3A 수학적 의미, 전체 경로/정수축, Pch/Pdis/Q/SOC/PCS16, 목적함수, 검증 허용오차를 변경하지 않는다.

## 실패 시 초기화 후보

Stationary LP 실패 시 기존 무dispatch 후보의 원본 실패 행과 rhs/max residual을 기록한다. feasible LP point가 없으면 실제 LP row residual은 UNKNOWN으로 남기며 배경 후보 residual과 혼동하지 않는다. 같은 날짜 원본 voltage_matrix의 P/Q 감도로 후보만 순위를 정한다.

최대4개 후보(peak 전/후 충전 모드2개와 합법 왕복 경로 최대2개)를 검토한다. 경로는 원본 graph의 출발/도착/connect ETA, 이동에너지, source authority, 초기/종단 SOC 및 충전 가능 시간을 사용한다.96슬롯 전체 경로의 시간·위치 흐름을 검사한다. 후보별60초 연속 LP에는 원본 C3A 행/목적함수를 유지하고 정수 패턴만 고정한다. 모든 결과는 원본 FULL 독립 검증 후 채택한다. 후보 탐색은 잔여 예산에서 seed900초와 초기LB300초를 남길 수 있을 때만 수행한다.

모든 실제 후보가 실패했을 때만 원본 unrestricted seed MILP를 호출한다. 요청900초, 실제min(요청,잔여예산), MIPGap=.03, MIPFocus=1, SolutionLimit=1은 초기화 전용이다. 첫 feasible MILP point도 FULL 검증을 통과해야 한다. 후보 실패는 원본 FULL MILP infeasibility를 뜻하지 않는다. 후보의 경로·모드 제한은 Adaptive 또는 fallback MILP에 전달하지 않는다.

## 기존 인증기·Adaptive byte/SHA 동결

FROZEN_SCIENTIFIC_SOURCES.json에 기존 builder/Adaptive/RMP/Pricing/UB/LB 인증기 source SHA를 기록했다. 기존 파일은 변경하지 않는다.

May01 V17은 하한 LP 반환 후 기존 finite-box 인증기의 가정 오류로 자연 종료했다. 자유 helper48547개에 무한 경계가 있어 EXACT_BOX_CERTIFICATE_REQUIRES_FINITE_COEFFICIENTS_AND_BOUNDS가 발생했다. 독립 LB/Gap은 UNKNOWN이며 Adaptive에 진입하지 않았다. 누적4538.197999954224초, 잔여861.8020000457764초와 모든 원본 결과를 보존했다.

V18 certificate_box는 원본 등식과 기존 변수 경계에서 helper의 유한 envelope를 exact rational interval로 유도하고, 별도 verifier가 각 등식·pivot·의존성·endpoint·outward rounding을 재검사한다. 이 증명된 범위를 기존 인증기의 기존 lower/upper 인수로 전달한다. Solver 모델/case.d 경계, 행, 목적함수 또는 인증기의 유리수 평가 코드는 변경하지 않는다. 진짜 자유 변수의 유한 범위를 증명할 수 없으면 거부한다. Native objective/BestBd는 인증에 쓰지 않는다.

실제 May01 C3A에서48547개 envelope를 약11.24초의 비Native 시간에 유도하고 독립 검사했다. 기존 인증기는 zero-dual exact LB=0을 인증했다. LB=0은 약한 유효 하한이며3% 달성 증거가 아니다. 증명 파일은 새 시도의 CERTIFICATE_DOMAIN_PROOFS에 source matrix/domain SHA와 함께 보존한다.

## 예산·실제 검증

May01 V17을 중단하거나 재실행하지 않았다. 자연 종료 뒤 V18의 May02/03을 새 seed_policy_v18_01 attempt로 실행했다. 시작 전 RAM 여유17.97GB를 확인해2워커/Threads1을 선택했다. 예산은 날짜별 기존5400초 중 누적 사용분을 차감한다.

- May01 보호: 누적4538.198초 보존, 새 호출0회.
- May02 이월:3285.426초, 시작 잔여2114.574초.
- May03 이월:3316.044초, 시작 잔여2083.956초.
- 실행 source commit82d3ac0b, execution SHA9818db5ddae1a1329467d3f037a90cc8140208c07a416672cd61b59d55f62c2b.

각 시도에서 기존/새 원본 matrix/domain/bundle/anchor/binary count7개 필드를 비교한다. case SHA에는 새 증거 경로가 포함되지만 물리 모델 SHA는 동일해야 한다. 실제 Runtime이 TimeLimit을 조금 넘겨도 전부 차감한다. 예산 초과 시 유효 incumbent/최종 인증서가 없어졌다고 잘못 표시하지 않고 TIME_LIMIT_FEASIBLE_NOT_CERTIFIED와 초과 시간을 남기며 최종 PASS는 허용하지 않는다.

두 날짜에서 LP 직접 채택/초기strictUB/exactLB/기존Adaptive/최종독립 인증의 정상 절차가 확인돼야 나머지 날짜를 해제한다. 시간 제한으로3%에 못 도달한 결과도 명확히 구분한다. Runtime 미확정 시 QUARANTINE하고0으로 초기화하지 않는다.

## 테스트와 측정 구분

기존 회귀를 포함186개 경량 테스트 PASS, 실제 Native optimize0회. case.point 우회, exact3% 경계, FULL 실패/다른case/point 변조 거부, 합법 ETA/SOC 경로, fallback 설정, finite envelope 변조/임의cap 거부를 검사했다. 소형 fixture의 물리 verdict를 대체한 테스트와 실제 FULL 물리 검증을 구분한다.

May01 V17의 실제 불필요 seed 시간은900.696초다. May02/03에서 seed 호출이0이면 생략 사실은 실측할 수 있지만, 같은 날짜 V17 MILP의 반사실적 Runtime을900초로 꾸며 비교하지 않는다. 같은 날짜 V13의 중단된 seed는 각각3285.426/3316.044초 동안 incumbent0개였다. 새 LP 시간·FULL 통과 시점·UB/point SHA·LB/Adaptive/최종Gap·누적 예산 및 원본 모델 동일성을 PERFORMANCE.json에 기록한다.


## V18 종료 진단 오류 수정 및 별도 초기해 성능시험

V18의 완료 진단 dict.update에서 SolCount 중복 키 예외가 Runtime 저장보다 먼저 발생했다. May02/03의 해당 호출 Runtime은 UNKNOWN이며 QUARANTINE 기록과 실패 source/결과를 보존한다. V18R2는 Runtime을 먼저 ledger에 영속화하고 선택적 진단 실패와 분리한다.

최신 사용자 지시에 따라 캠페인 예산 이월 재시작에 앞서 별도 initialization_benchmark_v18r2_01에서 May02/03 초기해 성능을 Native 0초부터 실측한다. 원본 캠페인의 예산을 초기화하지 않는다. 첫 원본 FULL 정수·96슬롯 물리 검증 통과까지만 실행하고 LB/Adaptive는 호출하지 않는다. 기존 Adaptive/RMP/Pricing/인증기 파일 SHA는 보존한다. 실패 시 LP 후보 불가능을 FULL MILP 불가능으로 선언하지 않는다. Fallback MILP는 최대900초, MIPFocus1, 최초 feasible exit 후 독립 FULL 검증을 유지한다.
