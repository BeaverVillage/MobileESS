PR137 exact head `94f8a38b7ef7b60cf5d7ffd91c86b109589fcaef`에서, 기존 stay binary의 location 선택을 grid P1 epigraph에 연결하는 conditional-LP disjunctive-cut 진단 경로를 추가합니다. Production M1과 May/B3 구현은 그대로 보존합니다.

Baseline optimal simplex basis를 한 번 확보하고, 저장된 PR137 primal에서 377개 split MESS/slot의 6,903개 후보를 grid matrix 민감도로 순위화했습니다. 하나의 continuous model에서 `MESS01 / slot 67 / STA12`만 LB=UB=1로 변경하고 baseline basis를 재사용했습니다. 이 warm dual-simplex 실행은 전체 separation wall 1,740.354초에 TIME_LIMIT으로 끝나 **UNRESOLVED**입니다. 6,902개 후보는 미계산이며, 인증된 conditional 하한/추가 cut/fixing은 모두 0입니다.

Fresh root LP objective는 `0.5687116107773678`, 지정 L0 대비 delta는 `4.275e-10`입니다. **Material gate FAIL, strengthening 미선정, 600초 canary NOT_RUN**입니다. 이 결과로 single-state cut 전체의 효과가 없다고 단정하지 않습니다. 다음 방향은 `route-transition / multi-time disjunction`으로만 기록했고 추가 실험은 하지 않았습니다.

- Identity: 886,017 rows / 316,743 columns / 208,312 binaries / 8,447,855 nnz. 원래 5,155개 tracked 파일, A1 freeze, NormalAmps, zero margin, P1/P2와 source SHA 보존.
- Exact validity: original DAG unit-flow의 stay/transit partition, computed/uncomputed/transit 세 경우의 partial-cut proof, bounded exhaustive route + continuous grid-box projection equivalence. Exact rational weak-duality checker는 residual을 포함하고 원래 binding 등식에서 finite coordinate enclosures를 증명합니다. 이번 실제 조건 LP에는 usable certificate가 없습니다.
- Numerical coefficients: raw objective 금지, 사전 고정 safety 1e-8, 증명되지 않은 fixing 금지, violated cut >1e-6만 추가. 점수는 순위화에만 사용.
- Execution: heavy worker 1, Gurobi Threads 1, BLAS/OMP 환경 1; conditional cold barrier 및 parameter retry/sweep 0. Basis와 bounds 복원 및 원래 matrix 재감사 PASS.
- Validation: semantic **258 PASS**; full pytest **1,655 PASS**, 기존 warning 1개. 기존 native OpenDSS import exception traces는 두 log에 각각 8개 보존. Cold model 및 원래 tracked bytes 재감사, compile, git diff --check PASS.
- Campaign: 1,458-stage dry plan, Actual feedback firewall, previous Planning only, B3 L1–L4와 early-stop 금지 보존. Production optimizer / Actual / Fresh AC **0/0/0**. May main/L2/L3/L4 및 1800초 production MIP NOT_RUN; Problem13 FINAL_VALIDATED=false.

상세 결과와 한계: [27항목 한국어 보고서](https://github.com/BeaverVillage/MobileESS/blob/codex/v42-m1-location-grid-disjunctive-cuts-v1/docs/v42_m1_location_grid_disjunctive_cuts/FINAL_REVIEW_KO.md), [verification](https://github.com/BeaverVillage/MobileESS/blob/codex/v42-m1-location-grid-disjunctive-cuts-v1/docs/v42_m1_location_grid_disjunctive_cuts/VERIFICATION.json), [final flags](https://github.com/BeaverVillage/MobileESS/blob/codex/v42-m1-location-grid-disjunctive-cuts-v1/docs/v42_m1_location_grid_disjunctive_cuts/FINAL_FLAGS.json), [SHA manifest](https://github.com/BeaverVillage/MobileESS/blob/codex/v42-m1-location-grid-disjunctive-cuts-v1/docs/v42_m1_location_grid_disjunctive_cuts/SHA256_MANIFEST.json).
