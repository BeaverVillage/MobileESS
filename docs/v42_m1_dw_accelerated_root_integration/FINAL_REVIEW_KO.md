1. Draft PR [#149](https://github.com/BeaverVillage/MobileESS/pull/149), branch `codex/v42-m1-dw-accelerated-root-integration-v1`. 검증된 experiment payload/remote SHA `82480648b1a86030f361a11aab70e71da53f0ec5`; payload freeze 시 clean. 최종 publication metadata commit SHA/clean은 게시 후 별도 remote receipt로 검증한다.

2. PR147 scientific exact head `31858f4e35b44caadeee2a72ef2ae2d35b74899b`. 원본 tracked 파일 11,279개 byte-identical 및 full original matrix identity PASS.

3. PR144 runtime exact head `42204661b8a92e0b1153ade0dc11830d54ec8df5`. Runtime/test 11개 파일 exact import; PR145/146 미통합.

4. Arc-LP certified floor **0.5687115725336208**, material threshold **0.5737116104747505** 보존. Native arc optimum **0.5687116104747505**; 추가 full-scale Arc optimize 없음.

5. 시작 pool 1,244개. 재개는 authoritative 1,337-column checkpoint와 consumed 330.809초 / remaining 1,469.191초를 복원했다. 완료 pricing 24개와 accepted 신규 열 93개는 재실행하지 않았다.

6. Early-stop enabled. 기존 retained SHA와 중복되지 않는 distinct true-negative 4개가 full physical/integer audit 및 same-iteration true RC≤−1e−7을 통과한 경우에만 quota terminate를 요청했다.

7. Parallel validation enabled, Python workers 최대4. 모든 실제 batch의 sequential/parallel canonical 결과 완전 일치 PASS. 추가 Gurobi pricing process 없음.

8. Incremental audit enabled. 최초1,244개 authority 재발급 감사 후 재개 cache hit; 현재 dual의 RC는 항상 재계산했다. Certification과 final 모두1,433개 full-pool 감사 PASS.

9. Persistent RMP canary는 단 한 번 수행했다. System commit 95.117846% guard로 두 native 호출 모두 INTERRUPTED. Matrix identity PASS이나 objective/dual/postsolve 및 유효한 paired speed comparison은 없음; 초기화29.360초는 별도 기록했다.

10. Persistent selected=false, resource interruption으로 accuracy/performance gate 미통과. 재시험 없음. Warm basis selected=false.

11. 4-way pricing / Threads1 / RAM floor1GiB. Main CG sampled tree peak 13.316505GiB, min RAM 5.836300GiB, max commit 87.922075%. 누적 native optimize union755.427577/1800초, remaining1044.572423초; 두 번째 grant 없음. Canary 실패 telemetry와 분리했다.

12. Discovery 12회 완료; 고정된 최대 round 수에 도달해 추가 optimize 없이 종료했다.

13. Pricing 52회: Discovery48 + final Certification4.

14. Quota completion46회; 그중 native INTERRUPTED37회. Quota와 TIME_LIMIT의 경합으로 status9가 나온 호출도 Discovery certificate로 사용하지 않았다.

15. 신규 validated trajectory189개. 모든 추가 열은 당시 TRUE RMP dual에서 acceptance threshold를 통과했다.

16. 최종 retained1,433개; column 삭제/aging 없음. 재개 전 완료 RMP receipt7개, pricing24개, 신규 열93개와 pool prefix를 그대로 보존했다.

17. Columns/min PR147 **8.037371776 → 6.823627849**. 새 값의 분모는 build/audit/복원/checkpoint를 포함한 두 실행 segment의1661.872577초이며 수동 대기 간격은 제외한다. 전체 처리율은 낮아졌고 causal speedup은 주장하지 않는다.

18. Discovery median **71.574003150 → 64.306165050초**. Recovery 완료 RMP overhead는 round ledger와 cumulative wall에 별도 보존했다.

19. RMP native wall median **39.319015700 → 25.782715000초**. RMP 호출14개 중13개 OPTIMAL, 기존60초 TIME_LIMIT1개는 point/dual/certificate에서 제외했다. 재개 시 cold RMP 시간 배정은 preopt source commit에서300초로 고정했으며 첫 미완료 call 완료 시도만 한 번 수행했다.

20. 성공한 RMP upper trajectory: [0.5812261378620154, 0.5808561899852973, 0.5801980004787914, 0.5795862345547056, 0.5792398647891758, 0.5790886323783825, 0.5787304263463295, 0.5784007608260263, 0.5780852225505801, 0.577833741238716, 0.5775681034304079, 0.5772697011557064, 0.5769475518070709]. 동일 pool의 미완료 호출은 새 authoritative value로 사용하지 않았다.

21. Threshold distance: D_U **0.007514527387265 → 0.003235941332320**, D_L **0.005000037941130**. 전체 trajectory는 DW_ACCELERATED_CG_THRESHOLD_DISTANCE.csv에 보존했다.

22. Final Certification 네 문제 모두 OPTIMAL. 동일 true dual SHA `83962f3186e5283a7ff0c084ebb1bdaf7c10544db3224c8bc4de1d807e2c4681`, full original domain, cap120초, smoothing/quota shortcuts 없음.

23. 새 pricing corrected LB **0.5453106052406163**. Mixed-sense/global residual/downward numerical safety를 원본 theorem으로 적용했고 유리수 독립 검산 PASS.

24. Aggregated certified LB=max(arc floor, old valid corr, new corr)=**0.5687115725336208**. Pricing incumbent를 LB로 사용하지 않았다.

25. Smallest audited RMP upper **0.5769475518070709**.

26. 최종 certified D-W interval **[0.5687115725336208, 0.5769475518070709]**.

27. Materiality **INCONCLUSIVE**. L<T<U이므로 material/nonmaterial 어느 쪽도 증명하지 못했다.

28. Exact CG convergence **false**. Threshold 판정과 분리했고 네 OPTIMAL pricing optimum가 모두 음수다.

29. Remaining exact negative RC: [('MESS01', -0.007884880567136631), ('MESS02', -0.007916347402650662), ('MESS03', -0.00794350315966094), ('MESS04', -0.007892175436999044)]. Root LP printed bound 약−0.0096에서 terminal BestBd 약−0.0079로 proof gap을 닫았다. 최종 summed raw proof gap≈1.735e−18; safe-room4e−8은 numerical safety에 의한 진단값이며 LB 개선에 사용하지 않았다.

30. 다음 단일 blocker: **TRUE_NEGATIVE_RC_DOMINANT / full-domain root CG 수렴**. 다음 승인된 작업에서 remaining true-negative trajectory를 소진하는 Discovery를 계속한다. Pricing formulation strengthening이나 추가1800초 run은 이번 작업에서 구현/실행하지 않았다.

31. Branch-and-Price **NOT_RUN**.

32. 외부 B0 lane을 변경하지 않았고 다른 Lane의 process kill/terminate **0**.

33. B1/B2/B3 production calls **0/0/0**. May production / Actual / fresh AC 새 호출 없음.

34. Pre-CG190 PASS; post-heavy semantic/integration/relevant D-W192 PASS; full pytest **1,870 PASS**(1 historical NumPy warning). 검증 중 실제 concurrent heavy native solve0. Compile/static, git diff --check, source SHA, cumulative budget/receipt continuity, independent certificates 모두PASS.

35. Experiment payload remote SHA `82480648b1a86030f361a11aab70e71da53f0ec5` 일치 및 clean 확인. 최종 metadata push 후 HEAD/remote/PR head 일치와 clean을 별도 receipt `C:/Users/Public/CodexDWRootTests/PR149_FINAL_REMOTE_RECEIPT.json`에 기록한다. Force push/history rewrite/merge 없음.

PR147의 Arc-LP certificate, D-W dominance authority와 material threshold를 scientific base로 유지하고 PR144의 runtime acceleration 기능만 통합했다.

Discovery early termination은 same-iteration true RMP dual에서 검증된 distinct true-negative trajectory 4개를 확보한 경우에만 사용했으며 INTERRUPTED status를 pricing certificate로 사용하지 않았다.

Scientific lower-bound, materiality 및 CG convergence 판정은 true unstabilized RMP dual과 valid global pricing BestBd만 사용했다.

Persistent RMP는 full-scale paired canary에서 정확성과 성능 gate를 모두 통과한 경우에만 선택했으며 warm basis는 사용하지 않았다.

Branch-and-Price는 실행하지 않았고 B1/B2/B3 production도 실행하지 않았다.
