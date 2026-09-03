# V35R3A Kestrel scheduler-level temporal prototype

## 68-item report

1. **source baseline HEAD** — `"1b6916f2829106db9ad5a3589e0cdfa0508c4d5b"`

2. **branch** — `"codex/v35r3a-kestrel-scheduler-temporal"`

3. **worktree path** — `"C:\\Users\\kjw39\\OneDrive\\문서\\ChatGPT\\Mobile ESS 2\\MobileESS_v35r3a_kestrel_scheduler_temporal"`

4. **final HEAD** — `"RECORDED_IN_FINAL_RESPONSE_AFTER_COMMIT"`

5. **clean status** — `"EXPECTED_AFTER_COMMIT"`

6. **active V35R3 files changed** — `0`

7. **push/merge** — `"NO/NO"`

8. **RADDiT HEAD** — `"ae1bf132addb41b469f3ef25a7626fe5ab06bc81"`

9. **FastSim HEAD** — `"68c8ba7ede664e7678a84a924eaedaa58503defb"`

10. **NLR HPC docs HEAD** — `"914f6da551424f6227e9bd65e0745b6686a6cbd8"`

11. **Kestrel archive integrity** — `"PASS"`

12. **runnable vendor components** — `"RADDiT/FastSim source inspectable; direct FastSim run unavailable"`

13. **redacted/LFS/missing components** — `["sacctmgr association dump", "sacctmgr QoS dump", "node topology/state dump", "reservation history", "Kestrel slurm.conf priority weights", "RADDiT frozen runtime result is a Git-LFS pointer"]`

14. **authority level** — `"PUBLIC_POLICY_RELATIVE_SCHEDULER_TWIN"`

15. **priority components** — `["QoS precedence: high before normal; standby only when otherwise idle", "eligible age represented by submission-order FIFO", "partition semantics preserved; *-stdby remains protected", "stable job-ID tie breaking", "SiteFactor reserved for eligible normal-QoS order changes"]`

16. **backfill implementation** — `{"duration": "submission-side requested walltime", "hole_use": "later jobs may use an earlier compatible hole without moving an existing reservation", "main_loop": "priority-order reservation", "preemption": false, "type": "CONSERVATIVE_REQUESTED_WALLTIME_FIRST_FIT"}`

17. **resource model** — `"156 shareable H100 nodes / 624 GPU aggregate feasibility; exact node packing unavailable"`

18. **baseline fidelity metrics** — `{"actual_wait_P50_hours": 0.0008333333333333334, "actual_wait_P95_hours": 31.15416666666667, "actual_wait_max_hours": 93.16583333333334, "actual_wait_mean_hours": 4.3586474581921495, "compared_start_count": 22331, "qos": "ALL", "replay_wait_P50_hours": 20.20138888888889, "replay_wait_P95_hours": 372.0336111111111, "replay_wait_max_hours": 442.6822222222222, "replay_wait_mean_hours": 79.39226772448863, "start_MAE_hours": 75.35254259151453, "start_P95_AE_hours": 355.445, "start_median_AE_hours": 20.19, "start_order_spearman": 0.45960769738330454}`

19. **known limitations** — `["Kestrel priority weights and flags", "fair-share usage tree/history", "association priorities", "reservation/dependency/hold/requeue history", "complete node-state/topology history"]`

20. **running jobs/resources** — `{"job_count": 243, "policy": "FIXED_NON_PREEMPTIVE", "requested_GPU_hours": 25571.133333333335, "requested_GPUs_sum": 498.0, "requested_nodes_sum": 267.0}`

21. **pending jobs/resources** — `{"job_count": 421, "known_requested_GPU_hours": 14832.0, "known_requested_GPUs_sum": 384.0, "partial_request_count": 336, "partial_temporal_queue_controlled_count": 0, "partition_counts": {"gpu-h100-stdby": 421}, "qos_counts": {"normal": 1, "standby": 420}, "requested_node_hours": 16608.0, "requested_nodes_sum": 421.0, "schedulable_request_job_count": 339, "temporal_queue_controlled_count": 0, "unknown_GPU_request_count": 82, "wallclock_hours": {"max": 48.0, "min": 36.0, "p50": 36.0, "p95": 48.0}}`

22. **protected high-QoS jobs** — `0`

23. **temporal queue-controlled candidates** — `{"authority_note": "Normal QoS, complete submission request, non-standby partition.", "job_count": 0, "known_requested_GPU_hours": 0.0, "known_requested_GPUs": 0.0, "subset_of_temporal": true, "workload_class": "TEMPORAL_QUEUE_CONTROLLED"}`

24. **PARTIAL/shared temporal candidates** — `0`

25. **spatio-temporal candidates** — `{"authority_note": "None: submission-time exclusivity and exact AIDC binding are absent.", "job_count": 0, "known_requested_GPU_hours": 0.0, "known_requested_GPUs": 0.0, "subset_of_temporal": true, "workload_class": "SPATIO_TEMPORAL_CANDIDATE"}`

26. **unknown/excluded jobs** — `82`

27. **completed jobs** — `75`

28. **completed GPU-hours** — `2786.75`

29. **mean/P95/max wait** — `[40.0375, 40.0375, 40.0375]`

30. **terminal pending GPU-hours** — `3456.0`

31. **critical W1/W3/W5 power** — `{"W1_energy_kWh": 101.69399845345477, "W1_mean_kW": 406.77599381381907, "W1_peak_kW": 406.77599381381907, "W3_energy_kWh": 305.0819953603643, "W3_mean_kW": 406.77599381381907, "W3_peak_kW": 406.77599381381907, "W5_energy_kWh": 508.4699922672738, "W5_mean_kW": 406.77599381381907, "W5_peak_kW": 406.77599381381907}`

32. **Planning rho/critical exposure** — `[0.5670071217020519, null]`

33. **reprioritized jobs** — `0`

34. **advanced jobs** — `0`

35. **delayed jobs** — `0`

36. **shifted GPU-hours** — `0.0`

37. **W1 power reduction** — `0.0`

38. **W3 power reduction** — `0.0`

39. **W5 power reduction** — `0.0`

40. **maximum rebound** — `0.0`

41. **Planning rho improvement** — `0.0`

42. **critical-exposure improvement** — `0.0`

43. **number of modified priority pairs** — `0`

44. **total SiteFactor perturbation** — `0`

45. **high-QoS delay count** — `0.0`

46. **completed-job delta** — `0.0`

47. **completed-GPU-hour delta** — `0.0`

48. **mean-wait delta** — `0.0`

49. **P95-wait delta** — `0.0`

50. **max-wait delta** — `0.0`

51. **terminal-pending-GPU-hour delta** — `0.0`

52. **service non-inferiority PASS/FAIL** — `"PASS"`

53. **future job identity reads in KQ0** — `0`

54. **future start/end numeric reads** — `0`

55. **realized-runtime reads before freeze** — `0`

56. **Fresh reads during policy construction** — `0`

57. **post-issue grid-feedback calls** — `0`

58. **Fresh run available YES/NO** — `"NO"`

59. **Planning/Fresh effect direction** — `"Planning no-change; Fresh not run"`

60. **voltage/current/transformer violations** — `"NOT_EVALUATED_GRID_BINDING_AUTHORITY_INCOMPLETE"`

61. **current W^F modified?** — `"NO"`

62. **proposed W^T meaning** — `"scheduler-controlled temporal pending-queue workload"`

63. **proposed W^ST meaning** — `"W^T subset with independent spatial exclusivity/resource/binding authority"`

64. **W retraining required?** — `"YES_FOR_FUTURE_WT; NOT_PERFORMED"`

65. **production-change recommendation** — `"NO"`

66. **estimated invalidation scope** — `"future W target/schema, queue state, scheduler adapter, power/grid binding; current production preserved"`

67. **passed/failed** — `{"artifact_id": "V35R3A_TEST_REPORT_V1", "status": "PASS", "passed": 46, "failed": 0, "command": "python -m pytest tests/dayahead/test_v35r2_aidc_mess_forensic.py tests/dayahead/test_v35r3a_kestrel_scheduler_temporal.py -q", "output": "46 passed in 3.68s", "tested_at": "2026-09-03T05:41:38.409030+00:00"}`

68. **primary classification** — `"V35R3A_KNOWN_QUEUE_TEMPORAL_MASS_INSUFFICIENT"`

## Q1–Q12

### Q1

부분적으로 가능. submit/start/end 이벤트 비교로 R_tau/P_tau는 복구했지만 hold/dependency/requeue 이력이 없어 exact snapshot은 아니다.

### Q10

개념적 분리는 타당하지만 현재 Apr-01 KQ0 증거는 생산 분리를 정당화하기에 부족하다.

### Q11

현재는 권고하지 않는다(NO).

### Q12

활성 V35R3 종료 후 read-only squeue/scontrol snapshot과 slurm.conf/sprio/association/reservation 덤프를 1회 확보하는 것이 최소 다음 단계다.

### Q2

정확한 Kestrel 재현이 아니라 PUBLIC_POLICY_RELATIVE_SCHEDULER_TWIN이다.

### Q3

엄격한 제출측·QoS·파티션 조건에서 0건, 0.0 GPU-h였다.

### Q4

아니오. KQ0에 안전한 교환쌍이 없어 이동량은 0이었다.

### Q5

W1/W3/W5 모두 0 kW 감소였다.

### Q6

아니오. 동일 스케줄이므로 rho와 임계 노출 개선은 0이다.

### Q7

아니오. high/urgent 지연은 0건이다.

### Q8

NO. 지원되지 않은 개별 작업 지연 마감은 만들지 않았다.

### Q9

NO. 미래 actual start/end/runtime은 정책 결정에 쓰지 않았다.
