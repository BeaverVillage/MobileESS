# Lane D May campaign 구현 검토

1. Base SHA: `ce5d30fb9bcb91ab8395d1313e868d24f5fde517` (Draft PR #143 exact head).
2. Branch: `codex/v42-may-campaign-orchestrator-prep`. [Draft PR #146](https://github.com/BeaverVillage/MobileESS/pull/146), 구현 commit `2552359614dc0c0c9c571e7837d55dc159dca3a8`. 생성 시 local/remote/PR head 일치를 `PR_PUBLICATION.json`에 기록했다. 이후 publication 문서 commit을 포함한 최종 remote head는 GitHub PR metadata와 최종 응답에서 확인한다. Force push/merge/rebase 없이 push하며 마지막 clean tree를 별도로 검증한다.
3. 날짜 authority: 기존 frozen `MAY_CAMPAIGN_DRY_RUN_PLAN.json`의 명시적 목록. 2025-05-01~2025-05-31, 31개 unique, 순서·월·연도 검증. 전체 목록은 `MAY_DATE_AUTHORITY_AUDIT.json`.
4. DAG: B0 31일 → B1 31일 → B2 31일 → B3 L1 31일 → main-complete → B3 L2 31일 → L3 31일 → L4 31일. 각 day는 기존 arm별 Planning 뒤 Freeze→Actual→Fresh AC→Validation.
5. 총 stage: `3×31×5 + 4×31×8 + 1 = 1,458`. 마지막 1은 main-complete coordinator gate. 역사적 1,458과 차이 0, science 변경 없음.
6. B0: 고정 D1 workload와 MESS OFF. 독립 day 최대 4개 dynamic queue.
7. B1: A1, MESS OFF. 한 day pipeline만 진행.
8. B2: M1, D1 AIDC fixed. day 최대 4개, day마다 inner pricing 1개.
9. B3: 한 day pipeline만 진행. 매 loop A1→M1→A2→M2. M2 route/movement/P/Q/SOC free 보존.
10. Inner pricing: B2=1, B3=최대 4. 모든 향후 Gurobi Threads=1. 현재 실행은 sleep/mock뿐이다.
11. Global semaphore: campaign 전체 4 single-thread slot, 각 heavy mock solve가 1개 요청. outer day는 별도 solver token을 점유하지 않는다. 명시적 config로 capacity 변경 가능, nested 16-way 확장 없음.
12. Memory: available RAM≥1 GiB, OOM, commit≥95%, sustained catastrophic paging, solver/license failure 및 잘못된 telemetry 차단. Mock telemetry만 사용하며 실제 RAM stress 0. 실행 중 guard도 global stop·token release 검증.
13. State machine: NOT_RUN/READY/RUNNING/PASS/FAIL/INTERRUPTED/BLOCKED. 명시적 transition 검증. 각 transition마다 atomic checkpoint; worker/time/SHA/reason/retry 저장.
14. Idempotency: scientific SHA/input SHA/stage version/day/arm/loop와 receipt·output hash 일치 시 authoritative PASS 재사용, replay mock 실행 0. stale identity는 descendants invalidate, corrupt receipt는 quarantine, 새 generation은 격리 path.
15. Crash/restart: coordinator subprocess 강제 종료, worker crash, interrupted stage, machine restart에 해당하는 fresh-process 복구, receipt publish와 checkpoint 사이 crash 검증. PASS 유지, orphan RUNNING→INTERRUPTED→READY, 유효한 receipt가 이미 있으면 PASS 복원. B0 1~8일 완료 fixture에서 9~31일만 unfinished queue.
16. Arm barriers: 모든 required day Validation PASS 전 다음 arm 진입 불가. B0 모두 PASS fixture에서 B1 unlock 확인. Scientific hard failure는 downstream BLOCKED, transient retry는 최대 2회.
17. Planning/Actual firewall: control gate와 data dependency 분리. Actual 값/SHA는 다음 Planning context/input hash에 들어가지 않는다. Actual 주입 및 provenance 위조 거부. 다음 loop에는 같은 day 이전 Planning만 전달. Mock broker 범위이며 미래 native I/O는 별도 audited integration 필요.
18. Convergence: main 완료 후에만 L2, 다음 L3, 다음 L4. 실제 analytical detector를 합성 hash에 적용하여 2-cycle/fixed-point를 관측해도 L4 완료. B0/B1/B2 재실행 없음.
19. Main selection: B0/B1/B2/B3 L1만 사용, incomplete set 거부. L2~L4 별도 convergence selector.
20. Mock concurrency: 4일 bounded fixture에서 day peak B0/B1/B2/B3=4/1/4/1. 상세 measured evidence는 `MAY_MOCK_CONCURRENCY_TEST.json`.
21. Oversubscription: B2 4 day가 각 1 slot, B3 1 day의 M-stage inner4가 전역 최대 4 slot. 계측 결과는 `MAY_NO_OVERSUBSCRIPTION_TEST.json`.
22. Production guard: ENABLE_PRODUCTION 기본 false. 임의 adapter 거부, production command는 true config에서도 future reviewed adapter 없으면 거부.
23. Production call: optimizer/Actual/Fresh OpenDSS = 0/0/0. A1/M1/A2/M2/full pricing/Branch-and-Price/Gurobi calls 모두 0. Synthetic PASS는 과학 acceptance나 논문 결과가 아니다.
24. FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=true. scheduler unit/mock integration/static 검증만 수행. 테스트 수·로그·source/artifact SHA는 `VERIFICATION.json`과 `SCHEDULER_TEST.log`에 기록.
25. 향후 통합: M1 authority 확정 후 새 production identity/version/root, per-day frozen source SHA, certificate/physical/numerical audit adapter, concurrency-safe Planning read audit, native semaphore/Threads=1 및 live memory/cancellation을 별도 구현한다. 자세한 integration point는 `MAY_ORCHESTRATOR_ARCHITECTURE.md`. 이번 lane에서 A/B/C merge/rebase 없음.

"이번 Lane D는 May campaign의 scheduler와 dry-run orchestration만 구현했으며 optimizer, Actual, Fresh OpenDSS production call은 모두 0회였다."

"B0/B1/B2/B3 day-worker 정책 4/1/4/1 및 B2 inner1/B3 inner4를 보존했고, main comparison과 B3 convergence campaign 사이의 scientific barrier를 유지했다."

"Lane A의 heavy optimization과 자원 경합을 피하기 위해 실제 Gurobi/OpenDSS campaign을 실행하지 않았다."
