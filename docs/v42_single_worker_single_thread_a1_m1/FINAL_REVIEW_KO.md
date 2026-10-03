1. PR / SHA / pytest / clean: [Draft PR #134](https://github.com/BeaverVillage/MobileESS/pull/134) / 코드·실험 검증 SHA 45cd67096de8c402199aeb5fefd5cc342d53aa9f / full 1,532 PASS, 1 warning / semantic 34 PASS / clean 확인. 최종 metadata commit의 HEAD는 PR head SHA와 최종 전달에서 확인한다.
2. 1 worker / 1 thread: 준수. A1 → M1 build → full LP → reduced LP → M1 P1 → semantic → full pytest 순차. OS 지원 thread는 solver worker가 아니다.
3. A1 rows/cols/binaries/nnz: 9,133,426 / 7,449,002 / 2,223,230 / 53,767,578; 96 steps, 1,499 jobs.
4. A1 Method / Threads: 1 / 1. 한 실행, 4개 승인된 기존 P1/P2 순차 optimize; 재시도·sweep 0.
5. A1 peak RSS / minimum free RAM: 관측 21.32 GiB / 0.58 GiB; 5초 표본+수집 overhead, exact peak 주장 없음.
6. A1 status / runtime: ACCEPTED; 4개 모두 OPTIMAL(MIPGap=0.005 기준); 누적 solver 1,588.424 s. Build 415.667 s는 별도.
7. A1 objective 및 P1/P2: P1 UB=LB=0.6715877825912354; migration 0 (LB 0, gap 0); shift 727 (LB 725, gap 0.275103%); prestart 231 (LB 230, gap 0.432900%). 최종 rho=0.6715878825912354는 기존 1e-7 P1 lock을 유지한 값이다. P2 정수 목적의 exact global minimum은 주장하지 않는다. 최종 물리 감사 PASS, max V=1.050000014633 pu는 기존 1e-5 감사 tolerance 이내이다.
8. A1_ACCEPTED: true. Freeze SHA d16ab0194a44a52c0e2d5277ad438bf4229e5c125967b8a995125da61f0fa0e0.
9. M1 생성 여부: true. 새 A1 고정, fresh original model; MESS route/movement/P/Q/SOC 결정 유지.
10. M1 rows/cols/binaries/nnz: full 961,472 / 316,743 / 208,312 / 8,587,630; reduced 886,017 / 316,743 / 208,312 / 8,447,855.
11. duplicate 제거 수: 독립 exact scan 75,455. 계수·sense·RHS 동일 행만 제거, proportional/approximate 제거 0.
12. root LP full/reduced objective: 0.5687116103448068 / 0.5687116107773678; 차이 4.32561e-10, both OPTIMAL, full 행 및 원래 단위 물리 감사 PASS. Runtime 152.440 / 144.576 s.
13. MIP Start 사용 여부: false. 새 A1 fixed AIDC가 달라 기존 Start REJECTED; 제약 변경으로 복구하지 않았다.
14. root relaxation 완료 시간: optimize callback 246.793 s. Root 작업 로그 시간 203.82 s는 별도.
15. crossover 완료 시간: optimize callback 244.268 s. Crossover 작업 로그 시간 56.24 s는 별도.
16. first branch 시간: NULL(노출·관측되지 않음). First nonroot/root-processing completion도 NULL; explored 1 root node.
17. M1 UB: NULL, incumbent 0개.
18. M1 LB: 0.5687116103498322, 새 모델에 결합한 유효 terminal global LB. 정확한 600초 checkpoint BestBd는 NULL로 보존한다.
19. M1 gap: NULL. M1_ROOT_PATH_GATE=FAIL; 600.226 s terminate 요청, 600.288 s terminal INTERRUPTED. 하나의 optimize만 수행.
20. M1 P2 movement energy / movement count: NOT_RUN / NOT_RUN, P1 acceptance 불충족.
21. M1_ACCEPTED: false. 통합/코드 검증 PASS와 과학적 M1 acceptance를 구분한다.
22. OOM 재발 여부: 없음. M1 관측 peak RSS 2.34 GiB / minimum free RAM 18.54 GiB; PR133 OOM 증거 보존.
23. 다음 병목 하나: crossover 이후 첫 nonroot 전 root DegenMoves. 동일 새 모델의 기록된 root 퇴화 처리를 검토하는 후속 방향 하나만 제시하며 이번 작업에서 추가 시험은 실행하지 않았다. Log상 callback 66.91 s도 runtime에 포함되므로 causal speedup은 주장하지 않는다.

모든 heavy optimization은 1 worker / Gurobi Threads=1로 순차 실행했으며 heavy solve 중 병렬 pytest/solver 작업을 실행하지 않았다.
기존 PR126/PR131의 UB/LB/gap은 새 M1 certificate에 재사용하지 않았다.
A2/M2/Actual/Fresh AC는 실행하지 않았다.
