1. Draft PR / SHA / pytest / clean: Draft PR 생성 후 연결; full 1566 PASS / semantic 68 PASS. Final HEAD 및 clean은 최종 Git 전달에서 확인한다.
2. PR134 model identity 동일 여부: True. Matrix/objective/bounds/vtypes/RHS/names exact 동일, A1 freeze/NormalAmps/source SHA 동일. Reduced 886,017행 / 316,743열 / 208,312 binaries / 8,447,855 nnz.
3. 1 worker / Threads=1 준수: True. ENV thread pools=1. Solver FeasibilityTol/IntFeasTol/OptimalityTol=1e-8 유지; 전역 postsolve numerical tolerance=1e-6. 정정 후 optimize 0회.
4. Zero-action MESS Start: PASS (재분류). Original strict 1e-8 FAIL 보존; numerical 1e-6 및 기존 physical/primary semantics로 재검증. Full unreduced max row residual 3.07292584711e-08. Route/PQ/SOC repair/clipping 0.
5. Start 사용 여부: False. 새 후보만 검증, 과거 PR126/131 Start 사용 0.
6. Callback time PR134 vs 이번 run: native 66.91 s / 108.67 s; handler body wall 0.479781707923 s / thread CPU 0.359375 s; calls 62094. Callback filesystem I/O 0.
7. Presolve 완료 시간: 69.5479998589 s (solver runtime).
8. Barrier 완료 시간: 363.955999851 s.
9. Crossover 완료 시간: 451.838999987 s.
10. DegenMoves 구간 시간: start=NULL, end=NULL; 직접 관측 없으면 0으로 추정하지 않는다.
11. Root processing 완료 시간: NULL s. Root relaxation 완료는 452.694999933 s로 별도 기록.
12. First nonroot 시간: NULL s.
13. First branch 시간: NULL s; 추정하지 않는다.
14. First incumbent 시간: 474.884000063 s. 재검증 2개 numerical + physical PASS. 두 점 전체 max: bound residual=1.42291128213e-08, full-row=9.97802544427e-09, integrality=0; raw point repair 0.
15. 600초 시점 node count: NULL; watchdog 기록 600.2480064 s, 마지막 MIP node=0 @ 454.845999956 s는 과거 관측값. 정확한 600.000 s 값은 노출되지 않으면 NULL.
16. M1 UB: 0.72203218925; exact 값은 새 certificate에 보존.
17. M1 LB: 0.56871161035; 기존 reference bound와 혼합하지 않는다.
18. M1 gap: 21.2345905325%; (UB-LB)/abs(UB)를 동일 solve bound로 재계산. native status TIME_LIMIT, runtime 1800.27799988 s, node count 1.
19. P1_ACCEPTED: False.
20. P2 movement energy/count: NULL / NULL; optimization calls 0, P1 UB lock slack 0.
21. M1_ACCEPTED: False.
22. ROOT_PATH_FIX: PARTIAL; incumbent는 인정됐지만 nonroot/branch 미관측. 기존 strict gate 결과와 600초 checkpoint를 보존했고 root-path 재실행 0회. Wall-time causal proof는 주장하지 않는다.
23. 다음 병목 하나: post-crossover/root processing. 추가 시험 0.

이번 작업에서 scientific M1 model은 변경하지 않았고, solver-side 변경은 DegenMoves=0과 새 A1 기반 validated Start뿐이다. Start는 허용된 변경 범위이며 완료된 solve에서는 실제 미사용이다. 실제 적용한 solver parameter 변경은 DegenMoves=0 하나다.
기존 PR126/PR131/PR134의 UB/LB/gap을 새 certificate에 혼합하지 않았다.
A2/M2/Actual/Fresh AC는 실행하지 않았다.
이번 정정은 physical constraint 완화가 아니라 post-solve floating-point numerical audit contract의 전역 정상화이다.
Solver-side FeasibilityTol/IntFeasTol/OptimalityTol=1e-8은 변경하지 않았다.
현재 1800초 M1 solve를 재실행하지 않았으며, 저장된 incumbent와 bound만 동일한 새 validator로 재검증했다.
