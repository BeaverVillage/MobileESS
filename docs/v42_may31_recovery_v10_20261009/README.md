# May31 정수 제어 수치 오류 복구 V10

31일 V9는 Native 194.442초에 끝났다. 원인은 예산 소진이 아니라 정수 모델의 고정밀도 설정 누락이다. LP의 독립 인증 LB 0.6612200946112171보다 기존 정수 목적값 0.661219815926337이 작아 `A_CERTIFIED_LB_UB_CONFLICT`가 발생했고, 콜백 중단 status 11이 TIME_LIMIT로 잘못 분류됐다.

V10은 V9 실행 경로를 별도 버전으로 보존하여 사용한다. A의 INTEGER_CONTROL에도 기존 FeasibilityTol/OptimalityTol=1e-9, NumericFocus=3, ScaleFlag=2를 전달한다. 원본 Method=2, Heuristics=0.05, IntFeasTol, 물리 제약, 정수 타입, raw point, 원본 행 허용오차 1e-6 및 strict UB >= exact LB 판정을 유지한다. 콜백 오류는 예산 소진으로 분류하지 않는다. 이전 V9/V6 소스는 수정하지 않았다.

실패 모델의 CSR, RHS, 목적함수, bound 및 타입을 그대로 사용한 독립 Native 진단은 PASS다. Native 13.699초, UB 0.6612200947908031, 최대 원본 행 잔차 9.85664883046411e-11이다. 진단 해와 LB는 운영 실행에 전달하지 않는다. 이 진단은 전체 날짜 물리 인증을 대신하지 않는다.

V10은 사용자가 요청한 B1 May31만 새 attempt recovery_v10_01로 재실행한다. 기존 May01~30 결과, May31 실패 결과와 Native ledger를 보존한다. 이전 194.44199967384338초는 새 날짜 누적 Native 시간에 이월하며 남은 예산은 5205.558000326157초다. 기존 점이나 bound는 새 실행에 전달하지 않는다. 다른 날짜/arm의 시간은 공유하지 않는다.

B1 1워커, B2 3워커, Threads=1, P2=0, 5400초 Native 누적 예산을 유지한다. B2는 31일 종료 후 새 버전의 Native=0 FULL 비교 게이트를 통과해야 시작한다. V9 Coordinator는 HOLD에서 자연 종료했고 진행 중인 Native Worker를 중단하지 않았다.

경량 회귀 228개 PASS, UI DOM PASS. 운영 실행의 실제 상태는 PRODUCTION_MAY31_RESTART.json과 localhost:8793 모니터에서 확인한다.
