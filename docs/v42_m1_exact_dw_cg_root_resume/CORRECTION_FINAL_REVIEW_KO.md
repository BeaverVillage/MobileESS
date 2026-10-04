1. PR: https://github.com/BeaverVillage/MobileESS/pull/140; 결과 commit 게시 전. 최종 SHA/원격 일치/clean은 최종 응답에서 확인. semantic 271 / full 1718 PASS.
2. 원본 INCONCLUSIVE 이력 보존: PASS; 기존 8959개 파일의 바이트 일치.
3. 정정: 기존 V42 contract에 맞춰 affine postsolve audit 1e-8 → 1e-6.
4. Solver FeasibilityTol / IntFeasTol / OptimalityTol = 1e-8 유지.
5. Floating-point affine postsolve audit만 1e-6으로 변경. 원본 physical bounds, route equality, exact integer, reduced-cost 및 BestBd 기준 유지.
6. Checkpoint integrity PASS: SHA/축/원본 local rows/route/mode/PQ/SOC/초기·종료 SOC/travel-energy/PCS를 optimize 없이 검증.
7. 복원 column: initial 4 + generated 836 = 840.
8. Iteration 210: 기록된 residual 6.371490002266e-08에 대한 old gate FAIL / new scalar gate PASS. 저장 primal이 없어 point 재평가를 주장하지 않으며 원본 STOP 이력 유지.
9. Failed iteration 210 dual reused=false. 원본 209 dual 이력은 보존하고 resume pricing에는 새 dual만 사용.
10. Cold RMP 재구축 37.758826초; old basis 미사용.
11. 첫 resumed RMP 목적값 0.5984747449853429; 미인증 master 진단값.
12. Resumed 전체 원본 행 postsolve 최대 residual 5.748676841221823e-07; 첫 master 6.371490002266e-08. Terminal RMP에는 validated residual 없음. 전체 원본 행 point 감사 결과 별도 보존.
13. 추가 RMP 53회: complete CG 52회 + terminal TIME_LIMIT RMP 1회.
14. 추가 full-domain pricing 208회.
15. 추가 validated columns 208개.
16. 누적 RMP 263회.
17. 누적 pricing 1044회.
18. 누적 retained columns 1048개.
19. 누적 heavy wall: 2141.402753 + 1444.948114 = 3586.350867/3600초. 예산 리셋 없음.
20. 누적 pricing median/p95/max 0.102837/1.222292/7.589435초. Original/resumed 분포와 columns/min은 speed audit에 보존.
21. 누적 RMP median/p95/max 6.903536/17.030265/19.907917초. 각 CG iteration timing 별도 보존.
22. 최종 MESS01–04 same-dual pricing certificates: {'MESS01': False, 'MESS02': False, 'MESS03': False, 'MESS04': False}.
23. Exact CG convergence=False; status=INCONCLUSIVE; stop=RMP_NOT_OPTIMAL.
24. Certified D-W root LB=NULL. 마지막 validated iteration 262의 incomplete RMP 0.59303720565463는 전역 LB가 아님. Terminal RMP는 미인증.
25. Arc root 0.5687116103498322 대비 certified delta=NULL.
26. Diagnostic gap: 이전 15.043608904%, 이후 NULL. Uref=0.6694159238756876는 진단 reference이며 UB 자동 승격 없음.
27. Material gate=INCONCLUSIVE.
28. End-to-end speed improvement 주장=False. Arc reference 146.990초; per-pricing throughput과 root 인증 시간을 구분.
29. Branch-and-Price NOT_RUN. Production M1/P2/A2/M2/Actual/Fresh AC NOT_RUN.
30. May production optimizer/Actual/Fresh AC = 0/0/0. 기존 1,458-stage dry plan, B0→B1→B2→B3(L1) 이후 L2/L3/L4, 이전 Planning만 사용 및 Actual→Planning feedback 금지 보존.

기존 pilot의 1e-8 raw-row postsolve gate 실패는 기록에서 삭제하거나 PASS로 소급 변경하지 않았다.

정정은 기존 V42 numerical contract에 맞춰 solver/reduced-cost certificate 1e-8은 유지하고, floating-point postsolve audit만 1e-6으로 통일한 것이다.

기존 840개 validated trajectory column을 checkpoint로 복원했으며 836회의 과거 pricing을 재실행하지 않았다.

failed iteration 210의 dual은 재사용하지 않고 840-column RMP를 다시 풀어 새 validated dual에서 CG를 재개했다.

Pricing timeout을 no-negative-column certificate로 해석하지 않았다.
