# V35R3J Final Review

Scale-consistent expanded AIDC IT-load modulation contract.

## GIT

1. **parent_HEAD** — `"3b0ce2c3276e32a1174976a44356e6b137123939"`
2. **branch** — `"codex/v35r3j-aidc-it-scale-consistency-freeze"`
3. **worktree** — `"C:\\codex_mobileess_workspace\\MobileESS_v35r3j_aidc_scale_freeze"`
4. **source_commit_at_build** — `"b59992b990ac9d5a619e7ee2450fb90d95ef750e"`
5. **clean_at_start** — `true`
6. **production_files_changed** — `0`
7. **MESS_files_changed** — `0`
8. **public_source_files_changed** — `0`
9. **push_merge** — `"NO/NO"`

## FROZEN_REFERENCE

10. **AIDC_IT_reference_kW** — `406.77599381381907`
11. **GPU_capacity** — `624`
12. **coefficient_W_per_requested_GPU** — `651.8846054708639`
13. **reference_semantic** — `"C_TESTBED_EQUIVALENT_IT_ACTIVE_STATE_ANCHOR"`
14. **coefficient_semantic** — `"D_HOMOGENEOUS_RESOURCE_POWER_PROXY_DERIVED_FROM_TESTBED_ANCHOR"`

## INCONSISTENCY

15. **LOW_full_active_measured_GPU_kW** — `292.8145968036744`
16. **CENTER_full_active_measured_GPU_kW** — `387.01971922821775`
17. **HIGH_full_active_measured_GPU_kW** — `409.67403208546114`
18. **LOW_residual_kW** — `113.96139701014465`
19. **CENTER_residual_kW** — `19.756274585601318`
20. **HIGH_residual_kW** — `-2.898038271642065`
21. **direct_physical_comparison_valid** — `"NO"`

## METHODS

22. **M0** — `"REJECTED_AS_FINAL_SCALE_CLOSURE: Direct NVML component W cannot be added one-for-one to a different-boundary equivalent IT anchor; HIGH also exceeds the anchor under a false containment interpretation."`
23. **M1** — `"VALID: Measured active/idle ratio modulates the frozen equivalent active-state coefficient and preserves the full-active anchor."`
24. **M2** — `"VALID_SELECTED: Predeclared min(d_direct,d_anchor) retains the measured component swing as an upper bound and the anchor-consistent modulation bound."`
25. **M3** — `"VALID_BUT_DUPLICATE_NOT_MAINTAINED: The frozen strict-F0 coefficient is exactly c_ref, so M3 is mathematically equivalent to M1."`
26. **selected** — `"M2_CONSERVATIVE_DUAL_ANCHOR_MODULATION"`

## FINAL_SWING

27. **LOW_W_per_GPU** — `396.85416154435006`
28. **CENTER_W_per_GPU** — `547.7239090195797`
29. **HIGH_W_per_GPU** — `579.7981786096108`
30. **original_changed** — `"YES_HIGH_ONLY"`
31. **transformation** — `"d_final=min(d_direct,c_ref*(1-p_idle/p_active)); HIGH=579.7981786096108"`

## EXPANDED_COHORT

32. **temporal_jobs** — `339`
33. **partial_shared_jobs** — `336`
34. **temporal_GPU_hours** — `14832.0`
35. **partial_shared_GPU_hours** — `14256.0`
36. **job_count_coverage** — `1.0`
37. **GPU_hour_coverage** — `1.0`

## APR01_POWER

38. **RW_mean_kW** — `406.7759938138192`
39. **RSP_LOW_mean_kW** — `390.64139180853175`
40. **RSP_CENTER_mean_kW** — `384.5075936377419`
41. **RSP_HIGH_mean_kW** — `383.2035741147222`
42. **RW_daily_energy_kWh** — `9762.62385153166`
43. **RSP_LOW_daily_energy_kWh** — `9375.393403404762`
44. **RSP_CENTER_daily_energy_kWh** — `9228.182247305806`
45. **RSP_HIGH_daily_energy_kWh** — `9196.885778753332`
46. **LOW_daily_delta_kWh** — `-387.23044812689955`
47. **CENTER_daily_delta_kWh** — `-534.4416042258549`
48. **HIGH_daily_delta_kWh** — `-565.7380727783276`
49. **LOW_max_slot_reduction_kW** — `81.35510311659175`
50. **CENTER_max_slot_reduction_kW** — `112.28340134901384`
51. **HIGH_max_slot_reduction_kW** — `118.8586266149702`

## CRITICAL_WINDOWS

52. **W1_mean_delta_kW** — `{"CENTER": -59.70190608313419, "HIGH": -63.19800146844756, "LOW": -43.25710360833415}`
53. **W3_mean_delta_kW** — `{"CENTER": -59.33675681045446, "HIGH": -62.8114693493745, "LOW": -42.9925341673046}`
54. **W5_mean_delta_kW** — `{"CENTER": -56.63465219262453, "HIGH": -59.95113166823376, "LOW": -41.0347203036858}`
55. **W1_CENTER_reduction_percent** — `14.6768508936296`
56. **W3_CENTER_reduction_percent** — `14.587084221497307`
57. **W5_CENTER_reduction_percent** — `13.92281084771835`

## STRICT_F0

58. **jobs** — `3`
59. **GPU_hours** — `576.0`
60. **expanded_job_multiple** — `113.0`
61. **expanded_GPU_hour_multiple** — `25.75`
62. **strict_flexibility_energy_mass_kWh** — `{"CENTER": 315.4889715952779, "HIGH": 333.9637508791358, "LOW": 228.58799704954563}`
63. **expanded_flexibility_energy_mass_kWh** — `{"CENTER": 8123.841018578405, "HIGH": 8599.566585137747, "LOW": 5886.1409240258}`

## CONSISTENCY

64. **full_active_reference_preserved** — `"YES"`
65. **arbitrary_beta_introduced** — `"NO"`
66. **penetration_rescaling_introduced** — `"NO"`
67. **whole_node_absolute_power_reconstructed** — `"NO"`
68. **shared_per_job_power_used** — `"NO"`
69. **GPU_slot_conservation** — `"PASS"`
70. **non_GPU_primary_delta_kW** — `0.0`

## IDC

71. **location_audit_performed** — `"NO"`
72. **location_changed** — `"NO"`
73. **optimization_runs** — `0`

## AUTHORITY

74. **level** — `"AF2_EXPANDED_AIDC_IT_CONTRACT_FROZEN"`
75. **primary_classification** — `"V35R3J_AIDC_IT_SCALE_PASS_WITH_CONSERVATIVE_NORMALIZATION"`
76. **EXPANDED_AIDC_POWER_CONTRACT_READY** — `"YES"`
77. **AIDC_AGGREGATE_SCIENCE_FREEZE** — `"YES"`
78. **AIDC_NEXT** — `"DOWNSTREAM_GRID_CERTIFICATION_AFTER_MESS_FREEZE"`
79. **PRODUCTION_INTEGRATION_RECOMMENDED** — `"NO"`

## FIREWALL

80. **Planning_reads** — `0`
81. **Fresh_reads** — `0`
82. **MESS_reads** — `0`
83. **Apr02_plus_reads** — `0`
84. **May_reads** — `0`

## TESTS

85. **passed** — `33`
86. **failed** — `0`

## Q1–Q21

**Q1.** A Melbourne-informed IEEE123 testbed-equivalent AIDC IT active-state anchor, not direct Kestrel whole-IT or GPU-only measurement.

**Q2.** NO; they have different physical/semantic measurement boundaries.

**Q3.** The direct HIGH NVML component sum is 409.674032 kW, while the independent equivalent anchor is 406.775994 kW; treating unlike boundaries as containment created the apparent exceedance.

**Q4.** M2 conservative dual-anchor modulation.

**Q5.** The predeclared hierarchy selects M2 after M0 fails boundary consistency and M1/M2 pass anchor preservation; grid data are never read.

**Q6.** {"CENTER": 547.7239090195797, "HIGH": 579.7981786096108, "LOW": 396.85416154435006}

**Q7.** NO; active and idle measurements remain unchanged. Only the derived HIGH swing is deterministically bounded.

**Q8.** YES; all 339 jobs and 14,832 GPU-h remain represented with 100% coverage.

**Q9.** YES; all 336 are represented by conserved slots without per-job power.

**Q10.** 534.4416042258549 kWh reduction.

**Q11.** {"W1": 59.70190608313419, "W3": 59.33675681045446, "W5": 56.63465219262453}

**Q12.** {"W1": 14.6768508936296, "W3": 14.587084221497307, "W5": 13.92281084771835}

**Q13.** YES by the common cohort energy-mass definition: expanded remains 25.75 times strict F0.

**Q14.** NO.

**Q15.** NO.

**Q16.** NO.

**Q17.** NO.

**Q18.** YES; AF2 aggregate AIDC power science is frozen as a candidate contract.

**Q19.** Wait for MESS freeze, then run downstream certification using existing location/facility/grid semantics without changing this contract.

**Q20.** NO; the required public H100 authority is already frozen.

**Q21.** NO.
