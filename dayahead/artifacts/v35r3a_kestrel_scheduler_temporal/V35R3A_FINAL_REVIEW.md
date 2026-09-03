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

15. **priority components** — `["hard service tiers: high > normal > standby, using the raw QoS field", "standby consumes only residual capacity after high/normal reservations", "eligible age represented by submission-order FIFO", "partition names containing stdby are audited but do not define QoS", "stable job-ID tie breaking", "SiteFactor may reorder only within normal or standby tier"]`

16. **backfill implementation** — `{"duration": "submission-side requested walltime", "hole_use": "later jobs may use an earlier compatible hole without moving an existing reservation", "main_loop": "priority-order reservation", "preemption": false, "type": "CONSERVATIVE_REQUESTED_WALLTIME_FIRST_FIT"}`

17. **resource model** — `"156 shareable H100 nodes / 624 GPU aggregate feasibility; exact node packing unavailable"`

18. **baseline fidelity metrics** — `{"actual_wait_P50_hours": 0.0008333333, "actual_wait_P95_hours": 31.1541666667, "actual_wait_max_hours": 93.1658333333, "actual_wait_mean_hours": 4.3586474582, "compared_start_count": 22331, "qos": "ALL", "replay_wait_P50_hours": 28.7730555556, "replay_wait_P95_hours": 373.9413888889, "replay_wait_max_hours": 440.4386111111, "replay_wait_mean_hours": 87.0504223078, "start_MAE_hours": 82.9520765727, "start_P95_AE_hours": 364.2075, "start_median_AE_hours": 28.7613888889, "start_order_spearman": 0.4622885733}`

19. **known limitations** — `["Kestrel priority weights and flags", "fair-share usage tree/history", "association priorities", "reservation/dependency/hold/requeue history", "complete node-state/topology history"]`

20. **running jobs/resources** — `{"job_count": 243, "policy": "FIXED_NON_PREEMPTIVE", "requested_GPU_hours": 25571.133333333335, "requested_GPUs_sum": 498.0, "requested_nodes_sum": 267.0}`

21. **pending jobs/resources** — `{"full_node_request_count": 3, "job_count": 421, "known_requested_GPU_hours": 14832.0, "known_requested_GPUs_sum": 384.0, "partial_request_count": 336, "partial_temporal_queue_controlled_count": 336, "partition_counts": {"gpu-h100-stdby": 421}, "partition_only_stdby_without_standby_qos_count": 1, "partition_stdby_name_count": 421, "qos_counts": {"normal": 1, "standby": 420}, "qos_partition_semantics_ambiguous_count": 1, "qos_resource_summary": {"high": {"full_node_request_count": 0, "job_count": 0, "known_requested_GPU_hours": 0.0, "partial_shared_request_count": 0, "schedulable_job_count": 0}, "normal": {"full_node_request_count": 1, "job_count": 1, "known_requested_GPU_hours": 192.0, "partial_shared_request_count": 0, "schedulable_job_count": 1}, "standby": {"full_node_request_count": 2, "job_count": 420, "known_requested_GPU_hours": 14640.0, "partial_shared_request_count": 336, "schedulable_job_count": 338}}, "requested_node_hours": 16608.0, "requested_nodes_sum": 421.0, "schedulable_request_job_count": 339, "temporal_controllable_mass_after_standby_correction": {"job_count": 339, "known_requested_GPU_hours": 14832.0}, "temporal_controllable_mass_before_standby_correction": {"job_count": 0, "known_requested_GPU_hours": 0.0}, "temporal_queue_controlled_count": 339, "unknown_GPU_request_count": 82, "wallclock_hours": {"max": 48.0, "min": 36.0, "p50": 36.0, "p95": 48.0}}`

22. **protected high-QoS jobs** — `0`

23. **temporal queue-controlled candidates** — `{"authority_note": "Union of normal and standby queue-controlled classes.", "job_count": 339, "known_requested_GPU_hours": 14832.0, "known_requested_GPUs": 384.0, "subset_of_temporal": true, "workload_class": "TEMPORAL_QUEUE_CONTROLLED"}`

24. **PARTIAL/shared temporal candidates** — `336`

25. **spatio-temporal candidates** — `{"authority_note": "None: submission-time exclusivity and exact AIDC binding are absent.", "job_count": 0, "known_requested_GPU_hours": 0.0, "known_requested_GPUs": 0.0, "subset_of_temporal": true, "workload_class": "SPATIO_TEMPORAL_CANDIDATE"}`

26. **unknown/excluded jobs** — `82`

27. **completed jobs** — `75`

28. **completed GPU-hours** — `2786.75`

29. **mean/P95/max wait** — `[4.7875, 4.7875, 4.7875]`

30. **terminal pending GPU-hours** — `3408.0`

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

67. **passed/failed** — `{"artifact_id": "V35R3A_TEST_REPORT_V1", "status": "PASS", "passed": 52, "failed": 0, "command": "python -m pytest tests/dayahead/test_v35r2_aidc_mess_forensic.py tests/dayahead/test_v35r3a_kestrel_scheduler_temporal.py -q", "output": "52 passed in 2.02s", "tested_at": "2026-09-03T06:02:12.647119+00:00"}`

68. **primary classification** — `"V35R3A_STANDBY_TEMPORAL_MASS_PRESENT_NO_GRID_BENEFIT"`

## Q1–Q12

### Q1

부분적으로 가능. submit/start/end 이벤트 비교로 R_tau/P_tau는 복구했지만 hold/dependency/requeue 이력이 없어 exact snapshot은 아니다.

### Q10

개념적 분리는 타당하고 standby temporal mass가 확인됐지만, 현재 relative twin과 불완전한 grid binding만으로 생산 분리를 승인하기에는 부족하다.

### Q11

현재는 권고하지 않는다(NO).

### Q12

활성 V35R3 종료 후 read-only squeue/scontrol snapshot과 slurm.conf/sprio/association/reservation 덤프를 1회 확보하는 것이 최소 다음 단계다.

### Q2

정확한 Kestrel 재현이 아니라 PUBLIC_POLICY_RELATIVE_SCHEDULER_TWIN이다.

### Q3

엄격한 제출측·QoS·파티션 조건에서 339건, 14832.0 GPU-h였다.

### Q4

tier-aware 서비스 게이트 하에서 이동 GPU-h는 0.0였다.

### Q5

W1/W3/W5 IT 감소는 각각 0.0/0.0/0.0 kW였다.

### Q6

Planning rho 개선은 0.0, critical-exposure proxy 개선은 0.0 kW-slot이었다.

### Q7

아니오. high/urgent 지연은 0건이다.

### Q8

NO. 지원되지 않은 개별 작업 지연 마감은 만들지 않았다.

### Q9

NO. 미래 actual start/end/runtime은 정책 결정에 쓰지 않았다.

## Standby semantics correction addendum

### A1

420건은 raw QoS 필드가 실제 standby였다. partition 이름만으로 추론하지 않았다. 별도의 1건은 raw QoS=normal, partition=gpu-h100-stdby로 감사됐다.

### A2

C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR_scheduler_authority\06_official_web_docs\NLR_Slurm_Batch_Jobs.html (SHA-256 5c181dd2b7a558ec36e4a5c6debb00248dd1c745317392bcdb95d458f9b1a219, saved HTML lines 7140-7151)가 high precedence와 standby idle-only/AU-free 의미를 정의한다.

### A3

standby 338건, 14640.0 GPU-h가 STANDBY_QUEUE_CONTROLLED가 됐다.

### A4

standby PARTIAL/shared 요청은 336건이다.

### A5

NO. high/normal 지연은 0건이다.

### A6

실제로 재정렬된 standby 작업은 0건이다.

### A7

W1/W3/W5에서 빠진 standby 실행 GPU-h는 각각 0.0/0.0/0.0이다.

### A8

AIDC PCC W1/W3/W5 감소는 각각 0.0/0.0/0.0 kW다.

### A9

Planning rho_max 변화는 0.0다.

### A10

정확한 critical exposure 변화는 0.0; aggregate proxy 개선은 0.0 kW-slot이다.

### A11

NO. 개별 작업 지연 deadline을 만들지 않았다.

### A12

NO. Fresh 결과는 정책 선택에 사용하지 않았다.

### A13

후보 질량은 교정 전 0건에서 교정 후 339건으로 크게 늘었지만, 실제 grid-beneficial 이동은 0.0 GPU-h였다.

### A14

FIXED/TEMPORAL_QUEUE_CONTROLLED/SPATIO_TEMPORAL의 개념적 분리는 지지하지만, exact scheduler와 job-grid binding 전에는 생산 반영을 정당화하지 않는다.
