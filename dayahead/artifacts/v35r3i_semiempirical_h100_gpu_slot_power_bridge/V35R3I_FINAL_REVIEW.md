# V35R3I Final Review

Measurement-calibrated semi-empirical H100 GPU-slot component-delta candidate.

## GIT

1. **parent_HEAD** — `"549ce2aea231187a1df5f21b40fe49c5eb8c97a1"`
2. **branch** — `"codex/v35r3i-semiempirical-h100-gpu-slot-power-bridge"`
3. **worktree** — `"C:\\codex_mobileess_workspace\\MobileESS_v35r3i_h100_power_bridge"`
4. **source_commit_at_build** — `"a34f6fb6a5b1d87dc3f35eb5728963b5dc7beb6d"`
5. **clean_at_start** — `true`
6. **production_files_changed** — `0`
7. **MESS_files_changed** — `0`
8. **public_source_files_changed** — `0`
9. **push_merge** — `"NO/NO"`

## HARDWARE

10. **frozen_GPU_capacity** — `624`
11. **H100_GPUs_per_node** — `4`
12. **equivalent_node_count** — `156`
13. **pool_scale_relationship** — `"SAME_FROZEN_TESTBED_EQUIVALENT_SCALE; physical delta scale=1"`

## EXPANDED_FLEXIBILITY

14. **temporal_controlled_jobs** — `339`
15. **partial_shared_jobs** — `336`
16. **job_count_coverage** — `1.0`
17. **temporal_GPU_hours** — `14832.0`
18. **partial_shared_GPU_hours** — `14256.0`
19. **GPU_hour_power_coverage** — `1.0`

## RW_RSP_OCCUPANCY

20. **RW_saturated_slots** — `96`
21. **RSP_saturated_slots** — `59`
22. **RW_mean_active_GPUs** — `624.0`
23. **RSP_mean_active_GPUs** — `583.34375`
24. **max_RW_minus_RSP** — `205.0`
25. **W1_RSP_minus_RW** — `{"apr01_slots": [74], "maximum": -109.0, "mean": -109.0, "minimum": -109.0, "slot_values": [-109.0]}`
26. **W3_RSP_minus_RW** — `{"apr01_slots": [73, 74, 75], "maximum": -105.0, "mean": -108.33333333333333, "minimum": -111.0, "slot_values": [-105.0, -109.0, -111.0]}`
27. **W5_RSP_minus_RW** — `{"apr01_slots": [72, 73, 74, 75, 76], "maximum": -81.0, "mean": -103.4, "minimum": -111.0, "slot_values": [-81.0, -105.0, -109.0, -111.0, -111.0]}`

## ACTIVE_POWER_W_per_GPU

28. **source** — `"Dataset312 Kestrel H100 NVML run-level class-stratified"`
29. **LOW** — `469.25416154435004`
30. **CENTER** — `620.2239090195797`
31. **HIGH** — `656.5288975728544`

## IDLE_POWER_W_per_GPU

32. **classification** — `"IDLE_AUTHORITY_DIRECT"`
33. **source** — `"Dataset312 paper Appendix A.4 Kestrel no-task idle"`
34. **LOW** — `72.4`
35. **CENTER** — `72.5`
36. **HIGH** — `72.6`

## INCREMENTAL_GPU_POWER_W_per_GPU

37. **LOW** — `396.85416154435006`
38. **CENTER** — `547.7239090195797`
39. **HIGH** — `583.9288975728543`

## GPU_COMPONENT_TRAJECTORY

40. **RW_daily_energy_kWh** — `{"CENTER": 9288.473261477224, "HIGH": 9832.176770051068, "LOW": 7027.550323288185}`
41. **RSP_daily_energy_kWh** — `{"CENTER": 8754.031657251371, "HIGH": 9262.408148244354, "LOW": 6640.319875161287}`
42. **daily_energy_delta_kWh** — `{"CENTER": -534.4416042258551, "HIGH": -569.7686218067129, "LOW": -387.2304481268996}`
43. **peak_slot_power_delta_kW** — `{"CENTER": -112.28340134901384, "HIGH": -119.70542400243517, "LOW": -81.35510311659175}`
44. **W1_mean_power_delta_kW** — `{"CENTER": -59.70190608313425, "HIGH": -63.648249835441106, "LOW": -43.25710360833415}`
45. **W3_mean_power_delta_kW** — `{"CENTER": -59.33675681045454, "HIGH": -63.258963903725906, "LOW": -42.992534167304576}`
46. **W5_mean_power_delta_kW** — `{"CENTER": -56.634652192624614, "HIGH": -60.378248009033165, "LOW": -41.03472030368579}`

## PARTIAL_SHARED

47. **INCLUDED** — `"YES"`
48. **SHARED_JOB_POWER_ATTRIBUTION_USED** — `"NO"`
49. **node_packing_required** — `"NO"`
50. **double_count_conservation** — `"PASS"`

## STRICT_F0

51. **job_count** — `3`
52. **GPU_hours** — `576.0`
53. **expanded_job_multiple** — `113.0`
54. **expanded_GPU_hour_multiple** — `25.75`
55. **strict_power_flex_energy_mass_kWh** — `{"CENTER": 315.4889715952779, "HIGH": 336.3430450019641, "LOW": 228.58799704954563}`
56. **expanded_power_flex_energy_mass_kWh** — `{"CENTER": 8123.841018578405, "HIGH": 8660.833408800576, "LOW": 5886.1409240258}`

## AIDC_BASELINE

57. **authority** — `"V22SR1 final IEEE123 AIDC scale + V35R3A H0"`
58. **scale_binding** — `"PASS"`
59. **scale_factor** — `1.0`
60. **absolute_whole_node_reconstructed** — `"NO"`
61. **non_GPU_primary_delta** — `"ZERO"`
62. **candidate_IT_peak_RW_kW** — `406.77599381381907`
63. **candidate_IT_peak_RSP_kW** — `{"CENTER": 406.77599381381907, "HIGH": 406.77599381381907, "LOW": 406.77599381381907}`

## FACILITY

64. **C1_reused** — `"NO"`
65. **PCC_candidate_generated** — `"NO"`
66. **PCC_peak_RW** — `"NOT_GENERATED"`
67. **PCC_peak_RSP** — `"NOT_GENERATED"`

## SITE_BINDING

68. **existing_binding_available** — `"NO"`
69. **status** — `"MISSING_FOR_GRID_INTEGRATION"`

## AUTHORITY

70. **level** — `"SE3_FROZEN_AIDC_IT_DELTA_CANDIDATE"`
71. **primary_classification** — `"V35R3I_EXPANDED_H100_POWER_BRIDGE_PASS"`
72. **EXPANDED_FLEX_POWER_READY** — `"YES"`
73. **AIDC_GRID_INTEGRATION_NEXT** — `"YES_AFTER_SITE_BINDING"`
74. **PRODUCTION_INTEGRATION_RECOMMENDED** — `"NO"`

## FIREWALL

75. **Apr01_realized_runtime_reads** — `0`
76. **Apr01_future_end_reads** — `0`
77. **Apr01_consumed_energy_reads** — `0`
78. **future_node_assignment_reads** — `0`
79. **Planning_reads** — `0`
80. **Fresh_reads** — `0`
81. **MESS_reads** — `0`
82. **May_reads** — `0`

## TESTS

83. **passed** — `35`
84. **failed** — `0`

## Q1–Q23

**Q1.** YES; 336 PARTIAL/shared jobs are represented by conserved occupied GPU slots, without independent per-job power.

**Q2.** 100% (14,832/14,832 requested GPU-h); PARTIAL/shared is 14,256 GPU-h (96.116505%).

**Q3.** Every simultaneous requested GPU occupies one slot exactly once, class components sum to total occupancy, and occupancy never exceeds 624.

**Q4.** Dataset312 Kestrel four-H100 NVML GPU-only experiment-run means, summarized by class-stratified P05/P50/P95 rules.

**Q5.** Direct Level-A Kestrel idle evidence: 72.5 +/- 0.1 W/GPU in a powered no-task node (Dataset312 paper Appendix A.4).

**Q6.** {"LOW": 396.85416154435006, "CENTER": 547.7239090195797, "HIGH": 583.9288975728543}

**Q7.** RSP-minus-RW is zero in 59 equal-occupancy slots and robustly negative in 37 slots; daily energy deltas are reported by scenario.

**Q8.** W1/W3/W5 slotwise and mean RSP-minus-RW kW deltas are reported in the energy and robustness artifacts.

**Q9.** YES; all three scenarios are negative in every unequal-occupancy slot and zero otherwise.

**Q10.** Expanded cohort is 113x jobs and 25.75x requested GPU-h; energy-mass comparisons use the same scenario increments.

**Q11.** NO.

**Q12.** The 406.77599381381907-kW frozen RW IT baseline is copied unchanged for all 96 slots.

**Q13.** YES; only scale-1 scheduler-induced GPU-component delta is added.

**Q14.** NO.

**Q15.** NO.

**Q16.** NO.

**Q17.** NO for aggregate GPU-component delta; unresolved for whole-node/site attribution.

**Q18.** Not yet: aggregate IT is ready, but C1/PCC conversion is gated by the missing frozen site/rack/PCC binding.

**Q19.** Freeze an exogenous site/rack/PCC binding, run C1 and downstream Apr-01 grid certification with all three scenarios, then approve production semantics.

**Q20.** YES, as a measurement-calibrated semi-empirical GPU-component delta estimate, not measured per-job or whole-node power.

**Q21.** Carry LOW/CENTER/HIGH workload-power spread and the zero-primary-non-GPU/component-boundary limitation.

**Q22.** NO.

**Q23.** NO.
