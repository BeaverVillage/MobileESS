## 결과

Source18r B2 May01의 동일 FULL 검증 U4 point에서 N1/N2/N3를 독립 비교했다. 최선 FULL 검증 UB는0.5461621302242249(N1), 기존0.6760534504652341 대비0.129891320241 개선이다. 기존 K48 Global LB0.46498486997548166를 유지해 Global Gap은14.86321657%다.

N1은 **UB_GAIN_STRONG**으로 UB를19.213173% 개선했고 실제 Native는39.555초였다. N2/N3는 **NO_VALID_IMPROVEMENT**이며 각각579.006초/599.200초를 사용했다. N2는 서로 다른7개 모델의 유한 정책을 소진했고 N3는6개 쌍 중5개 실행 후 예산을 소진했다.

4대·96슬롯 원본 물리/계통을 보존하는 제한 Primal 모델만 실행했으며, 각600초/총1,800초 actual 누적 예산에서 총1217.761001초를 사용했다. Restricted ObjBound는 Global LB로 사용하지 않았다.

## 검증과 범위

- 모든 채택 후보 원본 FULL Replay 및 독립 예산·Source·자원 감사 PASS.
- 원본 U4/PR207과 과거 연구 결과 보존. N1 버전 사건은 정확한 epoch01 증거와 실제 정식화 동등성으로 공개하고 재실행 없이 보존했으며, N2/N3는 새epoch02 검증 후 원래 U4에서 시작했다.
- 실제 중심점마다 원본814,560Security 행 재선정, exact signed helper projection, 실제DAG/ETA 및 유한 후보 정책 적용.
- 1 Worker × Threads1. B1/task/예약 비활성, 5월campaign/B3/IEEE8500 실행0. Actual=ACTUAL_NOT_RUN.

정확한 base는PR215 `6ca7624d7eafd45d5b061ff33e262b0de32bfe8d`. 상세 비교·모든 호출·운전계획·실패/버전 증거는 `docs/v42_b2_u4_primal_alns_600x3/B2_U4_PRIMAL_ALNS_600X3_FINAL_KO.md`에 있다.
