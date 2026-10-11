Joint16 정수해에서 생략된 원본 계통 제약 위반을 검사하고, 실제 위반하는 원본 행 16개씩을 추가한 K32/K48 하한 파일럿입니다. PR210의 모든 물리 행·K16·Bounds·Objective·9,322개 Binary를 그대로 유지했습니다.

결과는 `CG_LB_MATERIAL_IMPROVEMENT`입니다. 인증 Global LB는 0.4254777832 → 0.4649848700, 검증 U4 UB 대비 Global Gap은 37.06447576% → 31.22069421%입니다. 3% 목표에는 미달했습니다. 2차 증분은 0.0000086936이고 U4 시작해 외에 새 incumbent를 얻지 못해 같은 정책의 추가 확대를 기각하고 종료했습니다.

검증 및 실행:

- 원본 Security 814,560행을 각 단계에서 검사. 채택 32행은 독립 Fraction 소거·원본 SHA·상/시간·RHS·외향 반올림 검증 PASS.
- 두 단계 Native0, 여섯 종류 변조 거부, 실제 Gurobi readback, 최종 포함관계·수치 Solver Bound 인증 PASS. Exact rational B&B trace 인증은 아닙니다.
- 마지막 모델: 143,308행, 244,265열, Binary 9,322개, NNZ 1,257,052개.
- 순차 Native 2회 × TimeLimit 180초, Threads=1. 요청 360초, 실제 Runtime 360.083초. Peak RSS 1.1404 GiB, Peak Private Commit 3.1752 GiB.
- Full MILP/별도 Full LP/캠페인/가중치 최적화 0회. 축소 incumbent를 FULL UB 또는 Actual PASS로 사용하지 않았습니다.
- PR207/209/210 및 Source18r/U4 불변, 상속 증거 74개 SHA 대조 PASS. 기존 May HOLD·예약 Disabled·자동화 PAUSED 유지 감사 PASS.

상세 수학 증명, 원본 행 목록, 단계별 인증·원시 로그·실행 Ledger 및 제한은 `docs/v42_critical_grid_cg/CRITICAL_GRID_CG_FINAL_REPORT_KO.md`에 보존했습니다. 이 Draft PR의 base는 PR210 연구 브랜치입니다.
