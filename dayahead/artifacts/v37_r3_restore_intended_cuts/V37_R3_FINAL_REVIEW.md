# V37-R3R1 최종 준비 보고서

1. historical contract: `V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1`
2. omission cause: V34 통합 MESS 재작성 중 `restoration_cuts` 입력/삽입 경로 누락
3. cut input restored: YES
4. same-slot insertion: YES
5. P/Q-only recourse: YES
6. fixed discrete MESS decisions: YES
7. trust-region rho: 0.10
8. maximum rounds: 5
9. beam rerun after Fresh violation: NO
10. joint P-Q repair status: PASS
11. April-only evidence: YES
12. final authority SHA: `3ee89daad6d63cffb70c1a890f5141cf33bf4c951c9a9c364ae36692bcda6151`
13. cumulative fallback active: YES (K200→K400→K800→FULL)
14. persistent worker active: YES
15. duplicate restricted solves protected: YES
16. expected: 31
17. runnable: 31
18. parallel dates: 4
19. workers/date: 4
20. rolling pool ready: YES
21. PowerShell auto-launch ready: YES
22. refresh seconds: 10
23. x/14 major progress: YES
24. MESS candidate x/201: YES
25. K400 x/401: YES
26. K800 x/801: YES
27. FULL x/actual display (synthetic x/2160): YES
28. beam parent x/2: YES
29. seed x/2: YES
30. restoration round x/5: YES
31. Fresh x/96: YES (8-slot 간격 원자적 갱신, 마지막 96/96)
32. terminal row removal: YES
33. PASS/FAIL counters: YES
34. synthetic monitor test: PASS
35. duplicate-launch protection: PASS
36. atomic status: PASS
37. exact-match resume: PASS
38. interrupted candidate/round resume: PASS
39. branch: `codex/v37-may2025-locked-final`
40. final implementation commit(s): 최종 Git 기록 참조
41. clean/dirty: 범위 외 기존 변경은 보존
42. push: NO
43. merge: NO
44. MAY_STARTED: NO
45. MAY_CAMPAIGN_LAUNCH_READY: YES
46. exact one-command launcher: `powershell -ExecutionPolicy Bypass -File .\tools\v37\run_may_locked_final.ps1`
