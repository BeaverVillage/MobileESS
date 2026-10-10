# B3 5월 수치 정책 적용

버전 `B3_MAY_PRECISION_ORIGINAL_ROWS_V1`. 원본 V9 May25 진단은 2.9715e10 규모 등식의 presolve/postsolve 복원 잔차 3.814697265625e-6이 원본 acceptance 1e-6을 넘었음을 기록합니다. 고정밀도만 또는 Method=1은 실패했고 기존 Method=2+고정밀도+Phase I Presolve=0 진단은 최대 잔차 7.105427357601002e-15로 원본 primal/dual replay를 통과했습니다. 외부 B1 진단을 B3 인증으로 사용하지 않습니다.

B3 A1/A2의 PHASE_I와 ORIGINAL_P1은 5월 31일 모두 FeasibilityTol/OptimalityTol=1e-9, NumericFocus=3, ScaleFlag=2를 적용합니다. Phase I는 Presolve=0과 기존 Method=2를 요구합니다. 다른 A component는 원본 설정을 유지합니다. M1/M2는 모든 수용된 P1 Native 진입에 같은 네 고정밀도 값을 적용하고 기존 Presolve/Method/IntFeasTol은 유지합니다.

원본 행렬·목적·부호·물리/정수 제약·exact LB/UB·replay 허용오차를 변경하지 않습니다. Heuristics=0.05도 변경하지 않으며 **내장 휴리스틱 활성**입니다. 새 휴리스틱을 추가하거나 기존 휴리스틱을 비활성화했다고 주장하지 않습니다.

A 원본 policy 적용 callback과 ModelIdentity/SolverParameters의 May11 예외 메타데이터를 B3 전용 어댑터로 교체했습니다. 최종 Native 설정은 원본 DateBudget이 Threads/TimeLimit을 부여한 뒤 readback하여 ledger `calls[].b3_numerical_policy`에 봉인합니다. 원본 M 생성기 메타데이터의 1e-8은 pre-admission 값이고 최종 Solver 진입 설정의 근거로 사용하지 않습니다. 실제 backstop도 설정 receipt·scope·model을 검증합니다. 이전 ledger 버전은 identity mismatch로 거부하며 예산을 초기화하지 않습니다.

경량 173개와 Schema 4개 PASS. 실제 원본 DateBudget의 복제 AST 함수 경로에 Fake Solver를 넣어 **31일×4단계=124 진입**의 설정·메타데이터·예산 전달을 검증했습니다. 추가 fixture는 component별 정책, 원본 Method/Heuristics/integrality, 변조 거부, 재시작 예산, source policy preflight와 최종 backstop을 확인합니다.

이 작업의 실제 Native/FULL/OpenDSS 호출은 0회입니다. 실제 B3 전체 모델·Native·Global Gap·물리 인증은 **NOT_TESTED**이고 **PRODUCTION_NOT_AUTHORIZED**입니다. 현재 B1/B2 Worker·manifest·원본 A/M 소스·HOLD 상태는 수정하지 않았습니다. 완료 commit은 이 브랜치 Git HEAD와 PR191에서 확인합니다.
