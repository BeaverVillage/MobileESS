1. PR / SHA / tests / clean: Draft PR 게시 대기; scientific commit 결과 commit 이후 기록. Semantic 258 PASS, full pytest 1655 PASS; git diff --check PASS. 최종 metadata commit 뒤 remote HEAD와 clean tree는 최종 응답에서 확인한다.
2. PR137 model identity PASS: exact head `94f8a38b7ef7b60cf5d7ffd91c86b109589fcaef`, original tracked 5,155개 파일 byte 보존. Matrix/indices/RHS/senses/bounds/types/objective/names 및 A1 freeze/NormalAmps/source SHA cold 재감사 PASS.
3. Baseline LB: 0.5687116103498322. Basis acquisition 1회 objective 0.5687116103498316; 모든 원래 full rows 감사 PASS. 저장된 PR137 primal은 sensitivity와 separation에 그대로 사용했다.
4. Split MESS/slot 수: 377; 최대 24 sites 동시 fractional occupancy.
5. Conditional-LP candidate states: 6,903. 실제 positive fractional stay만 순위화; zero sensitivity도 삭제하지 않았다. Score는 scientific 계수로 사용하지 않았다.
6. 실제 conditional LP 실행: 1. One model, baseline basis 복원, selected stay LB=UB=1만 변경, Method=1/Threads=1. Sequential wall 1740.354/1800s; 6,902개 미계산. 재시도 0.
7. OPTIMAL / INFEASIBLE / UNRESOLVED: 0 / 0 / 1. OPTIMAL은 solver status와 사전 수치 인증 모두 통과한 state다. Solver OPTIMAL status만 받은 수는 0; 미계산 state는 UNRESOLVED count에 포함하지 않았다.
8. 인증된 conditional LB 최대: NULL. Raw solver objective 최대 NULL는 별도 진단이며 cut 계수로 사용하지 않았다.
9. L_safe 최대: NULL. Exact rational weak-duality + original affine equalities로 증명한 finite box + 고정 1e-8 safety를 사용했다. Dual residual을 0으로 무시하지 않았다.
10. Exact infeasible-state fixing: 0; unproven fixing 0. Farkas contradiction의 정확한 유리수 재구성만 허용했다.
11. Generated disjunctive cuts: 0. Computed-site 조건하한을 original stay binary로 연결; 새 변수 0.
12. Baseline root violated cuts: 0; 추가 0. Violation >1e-6만 추가하며 physical tolerance 변경은 없다.
13. Max separation violation: 0.0; sum positive 0.
14. Strengthened rows/cols/binaries/nnz: 886,017/316,743/208,312/8,447,855. Infeasible fix 0; 원래 row 및 objective 보존.
15. Fresh strengthened root LB: 0.5687116107773678; status 2, runtime 144.965s, barrier 60 iterations. 미완료 objective 또는 diagnostic reference를 LB로 승격하지 않았다.
16. Delta LB: 4.275355625082966e-10. Old LB를 새 root 결과로 복사하지 않았다.
17. Diagnostic root gap 전/후: 15.318438725% → 15.318438661%. U_ref=0.6715884801665905는 진단 기준이며 incumbent/UB certificate가 아니다.
18. Location fractional mass 전/후: 278.49392145342824 → 278.49392145342824; all-binary mass 498.8221507384342 → 498.82215073843406.
19. Location split count 전/후: 377 → 377; 최대 동시 sites 24 → 24.
20. Material gate: FAIL. Exact validity + LB nondecrease(1e-8) + delta≥0.005 또는 diagnostic gap 상대 closure≥5%; closure 4.155798706451824e-09.
21. 600s MIP canary: NOT_RUN; optimize calls 0. Material FAIL이면 금지. 1800s production MIP=0.
22. First nonroot / first branch: NULL / NULL. 실행하지 않은 canary에 과거 timing을 복사하지 않았다.
23. Canary LB/UB/gap: NULL / NULL / NULL.
24. Final strengthening 판정: **FAILED**; selected=False. 부분 계산 범위에서의 material 판정이며 미계산 state나 수치 미확정 state의 효과를 0이라고 단정하지 않는다.
25. 다음 병목 하나: **route-transition / multi-time disjunction**. 보고만 했고 이번 task에서 구현·실험하지 않았다.
26. May/B3 orchestrator preserved PASS: 1,458-stage byte/semantic plan, B0→B1→B2→B3(L1) 이후 B3 L2/L3/L4, previous Planning only, Actual firewall, Loop4 전 early-stop 금지 모두 보존했다.
27. Production May optimizer/Actual/Fresh AC calls=0/0/0. Main/Loop2/Loop3/Loop4 NOT_RUN; Problem13 FINAL_VALIDATED=false. Test의 bounded synthetic optimization은 production과 구분한다.

이번 작업은 MESS location 선택과 grid P1 epigraph를 conditional LP lower bound로 직접 연결했으며, integer feasible set과 physical authority를 변경하지 않았다.

계산하지 않은 location state와 transit state에는 기존 global lower bound L0를 사용했으므로 partial separation도 integer-valid하게 유지했다.

May 31-day production campaign은 실행하지 않았고, B0->B1->B2->B3(L1), 이후 B3 L2/L3/L4 실행 구조와 Actual feedback firewall을 그대로 보존했다.
