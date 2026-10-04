1. Draft PR / SHA / tests / clean: https://github.com/BeaverVillage/MobileESS/pull/140; scientific commit `c67723f004fa1c11fd4a9ebe6ca688e4366f70ad`; exact base `c8e518f97cbe1748f3e8773128ff8152bd394ee8`. Semantic 253 PASS / full pytest 1700 PASS; diff checks PASS. 최종 metadata commit 뒤 remote SHA와 clean tree는 최종 응답에서 확인한다.
2. PR139 model identity PASS: 886,017 rows / 316,743 columns / 208,312 binaries / 8,447,855 nnz. Matrix/attributes/native names, A1 freeze/NormalAmps/source/P1 SHA 보존; 기존 5,313개 파일 byte 보존 및 cold 재감사 PASS.
3. D-W matrix partition exactness PASS: native free/shared 및 objective anchors를 제외한 실제 sparse dependency graph components로 local ownership을 결정했다. Continuous ownership을 이름만으로 추측하지 않았고 ambiguous/unanchored dependencies는 global에 남겼다. 원본 CSR 재조합 coefficient/RHS/sense/bound/type/objective 차이 0.
4. Local rows / global coupling rows: 206,062 / 679,955; original shared columns 81,217. 모든 원래 global 행/변수 bounds/objective는 그대로 유지했다.
5. Initial polished columns: 4개. 각 full 0–96 trajectory의 native local rows, exact binary pattern, route/PQ/SOC/PCS/initial/terminal/travel audit PASS. Clipping/repair=0.
6. Initial RMP objective: 0.6694159238756876; polished reference 0.6694159238756876 재현 PASS, lambda[p0_m]=1. 제한된 RMP objective를 global LB로 취급하지 않았다.
7. Pricing model MESS별 rows/cols/binaries/nnz: MESS01 51,458/58,814/52,018/314,503; MESS02 51,527/58,895/52,090/314,932; MESS03 51,596/58,976/52,162/315,361; MESS04 51,481/58,841/52,042/314,646. All original local rows/columns, 96 slots, legal route domain 그대로 사용했다.
8. CG iteration 수: 210.
9. 총 pricing call 수: 836; 모두 sequential, Threads=1, MIPGap/MIPGapAbs=0, 각 TimeLimit≤600. Pilot wall 2141.403/3600s; optimize wall 합 1440.013s.
10. Pricing OPTIMAL / negative-column / certified-no-column / inconclusive: 5 / 836 / 0 / 0. OPTIMAL은 native solver status 별도 집계이며 다른 세 분류와 중복 가능하다. Negative point만 찾은 call을 most-negative/global optimal로 승격하지 않았다.
11. MESS별 final pricing certificate: MESS01=False; MESS02=False; MESS03=False; MESS04=False. 같은 마지막 RMP dual에서만 유효하며 과거 dual certificate를 이전하지 않았다.
12. Initial / 추가 column 수: 4 / 836. Bit-exact local vector + master coefficient vector + objective SHA만으로 duplicate 처리; tolerance merging 및 aging/deletion 없음.
13. Final retained trajectory columns: 840; global variables 포함 master columns 82057. 마지막 solve의 RMP trajectory columns 840. 추가 후 budget 종료 시 미재최적화 column과 마지막 solved objective를 구분한다.
14. Arc-root certified LB: 0.5687116103498322.
15. Certified D-W root LB: NULL. Last solved restricted RMP objective 0.5984747449853429는 별도 진단이며 incomplete master의 LB가 아니다. Certified인 경우 원본 global dual exact arithmetic + full-domain pricing BestBd로 보수적 LB를 검증했다.
16. Delta LB: NULL.
17. Diagnostic gap before/after: 15.043608904% → NULL; Uref=0.6694159238756876 diagnosticonly, 상대 closure NULL.
18. Material gate: **INCONCLUSIVE**. Certification/equivalence + delta≥0.005 또는 diagnostic gap relative closure≥5%.
19. Exact root CG termination: False; status **INCONCLUSIVE**, reason `RMP_NUMERICAL_AUDIT_FAIL`. 마지막 RMP raw-row residual 6.371490002266e-08 (기준 1e-8); 수치 gate 실패 dual은 pricing에 사용하지 않았다. Certificate 부족 시 DW 효과를 0이라고 주장하지 않았다.
20. Heuristic route restriction 0: Top-K, route pool, Hamming, site/time pruning, greedy/beam/approximate-path pricing 모두 없음. Native full MILP에서 찾은 validated negative point는 증명 완료 전에도 유효 column으로 추가 가능하다는 요청 규칙만 사용했다.
21. Timeout/incomplete search를 no-column으로 사용하지 않았다. No-negative는 해당 full-domain native global BestBd≥-1e-8일 때만 기록했고, threshold ambiguity는 INCONCLUSIVE다.
22. Bounded fixture integer equivalence PASS: 모든 2 legal paths × 4 mode patterns의 physical polytope vertices를 exact rational enumeration; feasible/infeasible, P1/integer optimum, route/PQ/SOC 동일. Lambda는 continuous이며 original binary reconstruction으로 한 pattern만 허용해 연속 trajectory 내부점도 정확히 표현했다. DW LP≥arc LP PASS.
23. Branch-and-Price 실행 여부=false; node-level/DW master branching, production integer DW, P2/A2/M2/Actual/Fresh AC 모두 NOT_RUN. Full-domain local MILP pricing과 승인된 bounded equivalence fixture 외 production solve 없음.
24. 다음 단계 하나: **Exact full-domain D-W/CG root certification stability: resolve the original RMP numerical audit before convergence claims**. 이번 task에서는 추가 설계 구현/실험하지 않았다.
25. May/B3 orchestrator preserved PASS: 1,458-stage plan, B0→B1→B2→B3(L1) 완료 후 B3 L2/L3/L4, 각 A1→M1→A2→M2. Previous Planning only, Actual completion sequence gate만 허용, B0/B1/B2 반복 및 Loop4 전 early stop 없음.
26. Production optimizer/Actual/Fresh AC = 0/0/0. Main/L2/L3/L4 NOT_RUN, PROBLEM13_FINAL_VALIDATED=false. Heavy pilot 종료 후 semantic/full tests를 순차 실행했다.

이번 Dantzig–Wolfe/Column Generation pilot은 Top-K, route pool, Hamming restriction, site pruning, heuristic pricing을 사용하지 않았다.

모든 MESS pricing에서 negative reduced-cost trajectory가 존재하지 않는다는 global pricing certificate가 같은 RMP dual에서 확보된 경우에만 D-W root optimum을 certified로 판정했다.

Pricing time limit 또는 incomplete search를 '개선 column 없음'으로 해석하지 않았다.

이번 task는 root-only exact D-W/CG pilot이며 Branch-and-Price와 production M1은 실행하지 않았다.

May 31-day production campaign은 실행하지 않았고, B0->B1->B2->B3(L1), 이후 B3 L2/L3/L4 실행 순서와 Actual feedback firewall을 그대로 보존했다.
