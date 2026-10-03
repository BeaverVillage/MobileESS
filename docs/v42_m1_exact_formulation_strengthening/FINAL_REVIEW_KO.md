1. PR / SHA / tests / clean: Draft PR 게시 대기; scientific commit 첫 결과 commit 이후 기록. Semantic 108 PASS, full pytest 1628 PASS. git diff --check PASS. 최종 metadata commit 뒤 remote HEAD와 clean tree는 최종 응답에서 확인한다.
2. Baseline M1 identity PASS: PR136 exact `37ffd404e7d0d598ddb84fec084e3ac332ed99c0`. Matrix/RHS/senses/bounds/types/objective/column names/native row names와 A1 freeze/NormalAmps/source SHA를 동결하고 최종 cold import로 재검사했다.
3. Baseline root LB: 0.5687116103498322. 재사용 continuous primal objective는 0.5687116107773678로 reference와 4.28e-10 차이이며 모델/전수 row audit를 통과했다. Fresh baseline optimize=0.
4. Total fractional binaries: 138,644/208,312. Fractionality mass 498.822150738; 모든 binary에 sum min(x,1-x)를 적용했다.
5. Fractional family top 5: movement_travel_arcs 131,350/198,986 (mass 39.108217); stay_arcs 6,910/8,942 (mass 278.493921); charge_mode 384/384 (mass 181.220012); location_connection_binary 0/0 (mass 0.000000); other_MESS_discrete_helper 0/0 (mass 0.000000). 독립 location/helper binary는 존재하지 않아 0이다.
6. 가장 큰 fractional pathology: 377개 MESS/slot이 여러 site에 분리되고 최대 24 site를 동시에 점유한다. Location split 최대 0.789717. Charge-mode 384/384가 fractional, 347개가 0.5±0.05다. 이 census는 인과적인 family별 objective-gap 분해 증명이 아니다.
7. CUT-A violation: 254개, max 13.368822969 kW. A1=0, A2=0, A3=254; total positive violation 2478.858642433 kW. Capacity 반복보다 simultaneous C+D의 connected-mass 초과가 관측됐다.
8. CUT-A exact validity PASS: DAG unit-flow의 단일 integer path, 단일 connected stay, binary mode에서 세 inequality가 도출된다. 1,024 binary flow assignments와 mode/continuous-box vertices를 exact rational로 검증했다. 선형 cut의 vertex validity로 전체 연속 domain의 projected equality를 증명했다.
9. CUT-A root LB 0.5687116104305803; delta 8.075e-11. Material gate FAIL; rows +1,152, nnz +45,478, new binary=0. Runtime 154.443s, barrier 56 iterations.
10. CUT-A fractional mass 498.822150738 → 484.543506344; fractional count 138,550. 감소만으로 production 채택하지 않았다.
11. SOC envelope stage 실행: formal proof + exact interval-union forward/backward DP + 명시적 transit partition. Initial/terminal SOC, battery bounds, power/efficiency/dt, source travel cost/timing을 모두 사용했다. Actual 사용=0. Baseline violation 18개, max 5.124231575 kWh.
12. SOC envelope root LB 0.5687116102532198; delta -9.661e-11. 수치 오차 수준의 차이이며 material gate FAIL. Runtime 177.309s, barrier 71 iterations. nnz +1,232,264. Fractional mass 484.057412455. CUT-A가 미선정이므로 B에는 A를 포함하지 않았다.
13. SOC-flow stage 실행: bounded symbolic projection + 실제 4-slot native prototype 뒤 full LP 1회. 16,384 binary assignments, 80 route/mode cases, 1,040 exact affine equalities와 실제 native row substitution regression PASS. 모든 real-valued power와 unchanged Q/PCS/grid domain을 포함한다.
14. SOC-flow matrix growth: continuous +207,928; rows +443,344; nnz +2,559,730 (+30.30%); binaries +0. 사전 hard gate는 total nnz ≤2x, added columns ≤1x original, 보수적 memory estimate의 2배 가용 RAM이었다. 실제 nnz는 사전 upper bound 2,559,826 이내다. Factorization fill은 사전 보장하지 않았다.
15. SOC-flow root LB / delta: NULL / NULL. 기존 동일 LP policy의 300초 TimeLimit, status=9, 57 barrier iterations, 반환 primal vector 없음. 마지막 rounded barrier primal=0.569311936, dual=0.569313184는 진단 로그이며 유효한 새 LB/UB 또는 material improvement certificate가 아니다. 재시도·추가 시간·parameter 변경=0.
16. 최종 selected strengthening: **BASE**. A/B는 무의미한 bound 개선, C는 미완료 LP certificate로 미선정. 어떤 후보도 production source에 자동 적용하지 않았다.
17. Selected matrix rows/cols/binaries/nnz: 886,017/316,743/208,312/8,447,855. C diagnostic matrix는 1,329,361/524,671/208,312/11,007,585다.
18. Selected root LB 0.5687116103498322; baseline 감소 없음.
19. Zero-action diagnostic root gap: 15.318438725% → 15.318438725%. UB_ref=0.6715884801665905; 강화 후보의 UB certificate로 사용하지 않았다.
20. 600s MIP canary **NOT_RUN**: selected material root improvement가 없어 진입 gate 미충족. 1800s production MIP=0.
21. First nonroot / first branch: NULL / NULL (새 MIP를 실행하지 않았음). 과거 PR136 timing을 이 시험의 관측으로 복사하지 않았다.
22. Canary LB / UB / gap: NULL / NULL / NULL. Diagnostic reference를 incumbent로 승격하지 않았다.
23. Formulation strengthening 판정: **material gate FAIL**. A/B exact cuts는 현재 x*를 잘랐으나 objective bound를 개선하지 못했다. C는 exact projection 검증을 통과했지만 300초 LP certificate를 얻지 못했으므로 효과는 미확정이다. C를 무효한 formulation 또는 효과 0이라고 단정하지 않는다.
24. 다음 병목 가설 하나: fractional connection-state의 P/Q spatial pooling과 grid epigraph 결합. 다음 방향은 route/location-conditioned PCS–grid exact valid inequality의 proof/violation 진단이다. 인과 확정이 아니며 이 task의 추가 실험은 0이다.
25. May campaign orchestrator preserved PASS: PR136 source/artifact byte SHA, 1,458-stage plan semantic equality, B0→B1→B2→B3 L1 뒤 B3 L2/L3/L4, 각 loop A1→M1→A2→M2, previous Planning only, Actual firewall, 4-loop/early-stop 금지 모두 보존했다.
26. Production May calls=0: campaign optimizer / Actual / Fresh AC = 0/0/0; Main/Loop2/Loop3/Loop4 모두 NOT_RUN. Test의 bounded synthetic adapter calls는 production 호출과 구분한다. Problem13 FINAL_VALIDATED=false.

이번 작업은 M1 integer feasible set과 physical authority를 변경하지 않고 LP relaxation만 exact하게 강화했다.

효과가 없는 candidate strengthening은 production formulation에 채택하지 않았다.

May 31-day production campaign은 실행하지 않았으며, PR136의 B0->B1->B2->B3(L1), 이후 B3 L2/L3/L4 실행 순서와 Actual feedback firewall을 그대로 보존했다.
