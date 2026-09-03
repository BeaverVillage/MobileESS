# V35R3C 최종 검토

## GIT

1. parent HEAD: 27b427827bdf1c397b66391f012be41ef9b2ae87
2. branch: codex/v35r3c-raddit-hpcoda-authority-recovery
3. worktree: C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3c_raddit_hpcoda_authority_recovery
4. final HEAD: RECORDED_AFTER_COMMIT_IN_FINAL_RESPONSE
5. clean: EXPECTED_CLEAN_AFTER_COMMIT
6. production files changed: 0
7. vendor/data files changed: 0
8. push/merge: NO/NO

## RECOVERED AUTHORITY

9. five RADDiT hashes PASS/FAIL: PASS
10. RADDiT payload row counts: {"data/baseline_power_results.parquet": 1035281, "data/baseline_runtime_results.parquet": 1035281, "data/historic_job_trace.parquet": 2557884, "data/semantic_search_power_results.parquet": 1035365, "data/semantic_search_runtime_results.parquet": 1035365}
11. payload schemas: {"data/baseline_power_results.parquet": {"avg_power_per_node": "double", "predicted_power": "double"}, "data/baseline_runtime_results.parquet": {"predicted_runtime_hours": "double", "wallclock_used_sec": "double"}, "data/historic_job_trace.parquet": {"account": "string", "avg_power_per_node": "double", "conda_envs": "list<element: string>", "end_time": "timestamp[us, tz=-06:00]", "job_id": "int64", "job_type": "string", "memory_req_raw": "double", "modules": "list<element: string>", "name": "string", "nodes_req": "int64", "partition": "string", "processors_req": "int64", "qos": "string", "script": "string", "start_time": "timestamp[us, tz=-06:00]", "submit_line": "string", "submit_time": "timestamp[us, tz=-06:00]", "user": "string", "wallclock_req_sec": "double", "wallclock_used_sec": "double"}, "data/semantic_search_power_results.parquet": {"avg_power_per_node": "double", "predicted_power": "double"}, "data/semantic_search_runtime_results.parquet": {"predicted_runtime_hours": "double", "wallclock_used_sec": "double"}}
12. payload time ranges: {"data/baseline_power_results.parquet": {}, "data/baseline_runtime_results.parquet": {}, "data/historic_job_trace.parquet": {"end_time": {"max": "2025-03-10T10:19:04+00:00", "min": "2023-12-15T20:24:12+00:00"}, "start_time": {"max": "2025-03-10T09:45:50+00:00", "min": "2023-12-15T20:21:15+00:00"}, "submit_time": {"max": "2025-03-10T09:45:47+00:00", "min": "2023-11-07T22:32:42+00:00"}}, "data/semantic_search_power_results.parquet": {}, "data/semantic_search_runtime_results.parquet": {}}
13. hpc-oda HEAD: 218d75f56b783ebfd698100f9406cfb46fa04c01
14. Kestrel source SHA match: True

## IDENTITY

15. RADDiT/Kestrel exact ID overlap: 1172189
16. timestamp-consistent overlap: 0
17. Apr-01 R_tau overlap: 0
18. Apr-01 P_tau overlap: 0
19. 339 temporal-job overlap: 0

## RUNTIME

20. runtime authority R-level: R1_REQUESTED_WALLTIME_ONLY
21. public benchmark reproduction: NOT_REPRODUCED_MISSING_XGBOOST_DEPENDENCY
22. query adapter equivalence: RUNTIME_QUERY_ADAPTER_EQUIVALENCE_FAIL
23. Apr-01 prediction coverage: 0/339 point; 0/339 safe
24. point MAE / median AE / P95 AE: NOT_AVAILABLE
25. point underprediction rate: NOT_AVAILABLE
26. q90 positive residual: None
27. safe historical coverage: NOT_AVAILABLE
28. requested-walltime/point ratio: NOT_AVAILABLE
29. requested-walltime/safe ratio: NOT_AVAILABLE

## SATURATION

30. RW saturated slots: 96
31. RP saturated slots: NOT_RUN_RUNTIME_POINT_UNAVAILABLE
32. RS saturated slots: NOT_RUN_RUNTIME_SAFE_UNAVAILABLE
33. first RS capacity-release slot: None
34. W1 free GPU: 0.0
35. W3 free GPU: 0.0
36. W5 free GPU: 0.0
37. free GPU-hours: 0.0
38. requested-walltime artifact: UNRESOLVED_NO_R3Q_SAFE_RUNTIME

## POWER

39. power authority P-level: RADDIT_POWER_DOMAIN_MISMATCH_FOR_H100
40. RADDiT CPU/GPU domain: CPU-exclusive validation; GPU/H100 not identifiable
41. H100 coverage: 0/339
42. exclusive/shared applicability: No H100 applicability; PARTIAL/shared 0/336
43. attribution status: POWER_ATTRIBUTION_AMBIGUOUS
44. model quality: CPU aggregate evaluation only; no H100 model
45. same-GPU-count power spread: NOT_AVAILABLE
46. Apr-01 power coverage: 0/339

## GRID BINDING

47. production mapping authority: GRID_BINDING_INCOMPLETE
48. result-independence PASS/FAIL: FAIL_NO_JOB_TO_AIDC_MAPPING
49. Fresh eligibility: FRESH_NOT_RUN_GRID_BINDING_INCOMPLETE

## CANDIDATES

50. temporal jobs: 339
51. W5-overlap jobs: 202
52. raw same-tier pairs: 27537
53. resource-feasible: 24
54. service-safe: 24
55. power-heterogeneous: 0
56. power-reducing: 0
57. Planning-improving: 0
58. accepted reprioritizations: 0

## EFFECT

59. shifted GPU-hours: 0.0
60. W1 IT power change: 0.0
61. W3 IT power change: 0.0
62. W5 IT power change: 0.0
63. PCC change: UNAVAILABLE_GRID_BINDING_INCOMPLETE
64. Planning rho change: 0.0
65. critical exposure change: 0.0 H0 proxy; exact unavailable
66. rebound: 0.0
67. Fresh rho/direction if authorized: NOT_AUTHORIZED

## SERVICE / CAUSALITY

68. high/normal delay: 0
69. completed-job delta: 0.0
70. completed-GPU-hour delta: 0.0
71. terminal pending delta: 0.0
72. future-feature reads: {"Fresh_reads_during_selection": 0, "future_actual_end_feature_reads": 0, "future_actual_start_feature_reads": 0, "post_issue_job_identity_reads_KQ0": 0, "realized_runtime_feature_reads_for_query": 0}
73. unsupported deadline: NO
74. Fresh used in selection: NO

## TESTS

75. passed/failed: {"command": "python -m pytest tests/dayahead/test_v35r3a_kestrel_scheduler_temporal.py tests/dayahead/test_v35r3c_raddit_hpcoda_authority_recovery.py -k 'not test_exact_starting_lineage_and_branch and not test_changes_are_confined_to_prototype_namespaces' -q", "failed": 0, "output": ".............................................................            [100%]\n61 passed, 2 deselected in 2.52s", "passed": 61, "status": "PASS"}

## CONCLUSION

76. primary classification: V35R3C_RECOVERED_AUTHORITY_STILL_INSUFFICIENT
77. production integration recommendation: PRODUCTION_INTEGRATION_RECOMMENDED = NO

## Q1–Q14

Q1. 예. 5개 모두 지정 SHA-256·크기·PAR1 매직을 만족하는 실제 Parquet이다.

Q2. 아니오. 숫자 full-ID는 1,172,189건 우연히 겹치지만 제출시각 일치는 0건이고 RADDiT ID는 연속 행 인덱스다.

Q3. 아니오. source/config/data SHA는 맞지만 필수 xgboost>=2.0 실행환경이 없고 설치가 금지되어 pinned MoE와 동등성 시험이 막혔다.

Q4. point 0.0%, safe 0.0%다.

Q5. 판정 불가다. 권위 있는 safe runtime이 없어 RS를 실행하지 않았다.

Q6. UNRESOLVED다. RP가 아니라 유효 RS로만 확정할 수 있다.

Q7. CPU-exclusive 검증만 덮는다. recovered trace에는 GPU 요청/H100 식별 필드가 없다.

Q8. 아니오. 336개 PARTIAL/shared에 대한 incremental power 경계가 없고 합산은 이중계산 위험이 있다.

Q9. 아니오. canonical H100 최근 120일의 양의 raw-energy 행이 0이라 P2 전용-node cohort도 비었다.

Q10. 0개다. H0의 resource/service-safe pair는 24개지만 power-beneficial 권위 교집합은 0개다.

Q11. 아니오. H0는 변화가 없고 job-to-AIDC/PCC binding이 없어 power-aware Planning을 실행하지 않았다.

Q12. Fresh는 과학적으로 허가되지 않아 실행하지 않았다.

Q13. 아니오. V35R3 production 통합을 권고하지 않는다.

Q14. 정확한 blockers는 pinned xgboost 실행/adapter 동등성 부재, H100-valid power label·모델 부재, PARTIAL/shared attribution 모호성, exact job-to-AIDC/PCC binding 부재다.
