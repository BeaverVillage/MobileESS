PR211 K48의 행·RHS·Bounds·목적함수를 재사용하고 Binary 9,322개만 연속화해 실제 OPTIMAL BASE 분수점을 확보했습니다. 이 점으로 원본 Grid 행 16개와 SOC–Mode–Travel 에너지 가용성 행 32개를 독립 검증하고 각각 별도 LP로 시험했습니다.

결과는 `ROOT_LP_SOC_NONMATERIAL_GRID_UNCERTIFIED`입니다. BASE/SOC 목적값은 각각 0.4649848699754816 / 0.46498486997548155로 같고, 독립 exact weak-duality 하한 차이는 2.3995e-8로 0.001 채택 기준에 미달합니다. SOC를 기각했습니다. GRID는 34.988초에 보호 callback으로 중단돼 효과를 인증하지 못했으며 채택을 보류합니다. 누적 Global LB와 31.22069421% Gap은 PR211 그대로입니다.

검증:

- 원본 Security 814,560행의 분수점 Separation, 채택 16행의 Fraction·원본 SHA·고정항·상·반올림·실제 Native readback 검사 PASS.
- SOC 768행의 원본 정수 유효성 및 alias·원본 에너지 계수 독립 증명 PASS. 실제 위반 58개 중 B1 가용성 32행만 선택했습니다. B2 headroom은 위반이 없어 시험하지 않았습니다.
- BASE/SOC OPTIMAL 및 Primal/Pi/RC·Bounds·보완조건·정확한 finite-box Dual 보정 인증 PASS. Exact LP 최적값 equality 또는 exact B&B trace를 주장하지 않습니다.
- Native 3회 × TimeLimit 240초·Threads1, 요청 720초·실제 222.292초. GRID 중단 호출을 재시도하거나 예산을 초기화하지 않았습니다.
- 사용자 후속 B2 우선 지시를 반영했습니다. B1 실행·파일·결과·Native Ledger 변경 0회입니다. GRID의 불명확한 감시 중단을 실제 B1 Solver 충돌로 단정하지 않습니다.
- Full MILP/공식 캠페인/IEEE8500/결합 실험/Production 통합 0회. Source18r/U4와 PR207/209/210/211/212 보존 감사 PASS.

필수 보고서, 실제 분수 운전·계통 P/Q 기여, 역사적 강화 실험 비교, 원시 로그·SHA·Dual 인증·실행 원장은 `docs/v42_b2_root_lp_tightening/B2_ROOT_LP_TIGHTENING_FINAL_KO.md` 및 같은 디렉터리에 보존했습니다. 이 Draft PR의 base는 PR211입니다.
