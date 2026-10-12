Source18r IEEE123 B2 May01에서 저장된 N1을 Solver Start로 사용하지 않고 새 초기화→U4→N1→N2+/N3+ 통합 Canary를 실행했다. 새 N1 FULL UB 0.5461621302242249을 재현했고 U4 대비 19.2132% 개선했다. 25개 Route/Mode Neighborhood에서 추가 이득은 없었다. 기존 K48 LB 대비 Global Gap 14.86321657%로 3% 목표는 미달이다.

실제 Native 1592.383000s/1800s, 28회 Optimize 후 비중복 후보 소진으로 종료했다. N2+/N3+는 384 Mode 전체를 개방하고 Node에만 Hamming을 적용했다. 135개 중복은 Native 없이 제외했으며 실제 동일 수학적 모델을 재실행하지 않았다. 동등 목적값 중심 재선정 및 Guard 정지/재개 증거를 공개했다.

원본 모든 물리/Grid·FULL validator·Source18r 및 기존 PR/B1/HOLD를 보존했다. 각 Raw FULL Replay와 독립 SHA/영역/예산 검산 PASS. 새 LB Optimize 0회. Actual 동결 계약 미충족으로 ACTUAL_NOT_RUN.

Base PR216 `38d98b99d1ea5ce9021fe0d727ab80309910b63d`. 전체 Native 로그, 96슬롯 CSV/97SOC, peak RAM/Commit, 실패 epoch, 그래프와 한국어 최종 보고서는 `docs/v42_b2_integrated_primal1800_canary/`에 있다.
