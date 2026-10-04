1. Draft PR/branch/final SHA/clean tree는 PR_PUBLICATION.json 및 최종 응답에서 확인. Branch=codex/v42-may-b0-production-31d.

2. Base PR146 exact SHA=0760b8f56398344e55d938b175d88761d19ff657. 입력/모델/checker authority gate PASS.

3. B0 production run ID=B0_202505_20261004T203131_71a9bf18; local full artifacts=C:\v42_b0_runs\71a9bf18.

4. 날짜: frozen May authority의 2025-05-01~2025-05-31, 정확히 31 unique·sorted.

5. B0: AIDC workload/data centers PRESENT, grid flexibility OFF, MESS OFF, ML OFF 아님.

6. Configured/selected workers=4/3; peak={'B0': 4}.

7. Gurobi Threads=1 guard, global solver slots=4, measured peak=4. 기존 fixed B0 optimizer 호출=0.

8. 첫 4-worker wave PASS=True; peak RSS=0.945419 GiB, available RAM min=15.375240 GiB, commit max=67.119909%. 후반 실제 hard guard downgrade=[{'from_workers': 4, 'measured': {'B0_tree_RSS_GiB': 0, 'CPU_percent': 14.2, 'available_GiB': 1.7412109375, 'catastrophic_sustained_paging': False, 'commit_percent': 95.08044393176834, 'elapsed_s': 286.63999999995576, 'foreign_heavy': [{'PID': 107632, 'RSS_GiB': 16.190448760986328, 'classification': 'active unrelated full-scale native run'}], 'pagefile_change_GiB': 1.1516952514648438, 'pagefile_used_GiB': 1.7037239074707031, 'pages_input_per_sec': 448.7552687880606, 'timestamp_UTC': '2026-10-04T11:36:23.307084+00:00', 'total_physical_GiB': 31.71080780029297, 'worker_trees': {}}, 'reason': 'COMMIT_GUARD', 'to_workers': 3}].

9. Peak B0 tree RSS=0.945419 GiB; single-worker peak=0.281338 GiB.

10. Minimum available RAM=1.741211 GiB; floor=1 GiB.

11. Maximum system commit=95.080444%.

12. Pagefile change=1.140388 GiB; max Pages Input/sec=180074.9272765848; sustained catastrophic paging=False.

13. Campaign wall=332.953000 seconds.

14. 31-day terminal completeness=True; unfinished day count=0.

15. PASS/FAIL/INTERRUPTED/BLOCKED=31/0/0/0.

16. Fresh OpenDSS convergence=31/31 days, 2976/2976 slots.

17. Voltage min/max=0.9709522494379543/1.0499500187568245 pu.

18. Line max loading=0.9121109345027072 pu.

19. Transformer phase-current max loading=0.957529931063456 pu, source NormalAmps.

20. Transformer kVA max loading=0.8832415129718197 pu, separate winding kVA.

21. Violation counts={'voltage_violations': 0, 'line_current_violations': 0, 'transformer_current_violations': 0, 'transformer_kVA_violations': 0}; Planning voltage cells=0.

22. 기존 B0 metric={"authority": ["v42_capacity/planning.py", "v42_capacity/replay.py"], "runtime_shortfall_GPUh": 103074.47260195577, "CC4_shortfall_GPUh": 63442.0458551875, "Planning_IT_kWh": 108082.10321473914, "Planning_PCC_kWh": 152563.98761600722, "Actual_GPUh": 482537.99749999994, "Actual_IT_kWh": 324744.13360578945, "Actual_PCC_kWh": 369226.0344353302, "rho": null, "rho_reason": "Existing fixed B0 capacity/reference producer does not publish an optimized rho; no new objective invented", "comparisons_to_other_arms": false}. 다른 arm 비교·새 rho 발명 없음.

23. Retry=0, interruption transitions=0; restart receipt 참조.

24. Idempotency: terminal receipt 155개 hash/bytes 재검증, 재계산 0. 과거 B0 output 대체 0.

25. B1/B2/B3 production calls=0/0/0.

26. M1/B&P calls=0/0; Branch-and-Price 실행 없음.

27. B0 validation/regression/static/artifact 테스트와 정확한 deferred command는 VALIDATION_TESTS.json에 기록.

28. Git base SHA + executed code/input SHA manifest + frozen config/date/checker/OpenDSS/run ID. SHA256_MANIFEST.json으로 artifact bytes 검증.

29. Unresolved scientific issue=None; B0_SCIENTIFIC_PASS=True.

30. B0 종료 후 명시적 STOP. B1 READY/release/실행 없음.

자원 측정 간격 요건을 충족하지 못한 앞선 실행은 진단 이력으로 보존했다. 최종 authority는 새 run ID로 생성한 두 번째 31일 실행이며 앞선 output을 재사용하지 않았다. SUPERSEDED_RUN_RECEIPT.json과 NONAUTHORITATIVE_OBSERVER_INTERVAL_RUN을 참조.

“이번 실행은 2025년 5월 B0 31일 production campaign만 수행했으며, B1/B2/B3는 실행하지 않았다.”

“B0는 AIDC workload/data centers가 존재하지만 AIDC grid flexibility는 OFF이고 MESS는 OFF인 비교군 정의를 유지했다.”

“31개 날짜는 최대 4 day-workers, Gurobi Threads=1 정책으로 실행했으며, 자원 부족이 실제 hard guard로 관측된 경우에만 worker 수를 낮췄다.”

“Planning Freeze 이후 Actual에서 full reoptimization이나 local/global P/Q repair를 수행하지 않았으며 Fresh OpenDSS로 독립 검증했다.”

“B0 campaign 완료 후 자동으로 B1으로 진입하지 않고 중단했다.”
