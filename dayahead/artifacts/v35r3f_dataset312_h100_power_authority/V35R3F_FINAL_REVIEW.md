# V35R3F Dataset 312 H100 Power Authority Final Review

Primary classification: **V35R3F_DATASET312_COMPONENT_ONLY**

Dataset 312 provides valid high-resolution H100 NVML and AMD RAPL component measurements for full-node-exclusive GenAI benchmarks. It does not directly measure whole-node input, facility input, partial-GPU occupancy, shared multi-job occupancy, or a frozen-archive idle trace. The fail-closed authority is therefore H1 component-level only.

## Numbered report

1. parent HEAD: 9034dd40f89a2d226a9bbbd47548224998ee3564
2. branch: codex/v35r3f-dataset312-h100-power-authority
3. worktree: C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3f_dataset312_h100_power_authority
4. final HEAD: FINAL_COMMIT_REPORTED_BY_GIT_AFTER_ARTIFACT_COMMIT
5. clean: CLEAN_AFTER_FINAL_COMMIT
6. production files changed: 0
7. vendor files changed: 0
8. MESS files changed: 0
9. push/merge: NO_PUSH_NO_MERGE
10. Dataset ID: NLR Data Catalog Dataset 312
11. dataset version: 2
12. archive SHA-256: dcad6de800fb565d850b163902e2eddae48aabd1ed1c7336f9a1cdaf3012f137
13. archive integrity: PASS
14. extracted file count: 3149
15. raw bytes processed: 1657703929
16. authoritative GPU channels: gpu-0..3[mW] per node via NVML
17. authoritative CPU channels: cpu-0/1 package and core RAPL energy/power channels
18. whole-node directly measured: NO
19. facility directly measured: NO (DIPLOEE profiles are synthetic)
20. native intervals: [0.100089, 0.100091, 0.100092, 0.100095, 0.200233, 0.200234, 0.200235, 0.200236, 0.200237, 0.200238, 0.200239, 0.20024, 0.200241, 0.200242, 0.200243, 0.200244, 0.200245, 0.200246, 0.200247, 0.200248, 0.200249, 0.20025, 0.200251, 0.200252, 0.200253, 0.200254, 0.200255, 0.200256, 0.200257, 0.200258, 0.200259, 0.20026, 0.200262, 0.200263, 0.200265, 0.200266, 0.200267, 0.20027, 0.200274, 0.200275, 0.200278]
21. timebase anomalies: {"duplicates": 0, "gaps": 271, "max_gap_s": 0.829718, "non_monotonic": 0}
22. workload classes: ["FINE_TUNING_LORA", "INFERENCE_OFFLINE", "INFERENCE_ONLINE_FINITE", "INFERENCE_ONLINE_RATE", "TRAINING_STABLE_DIFFUSION"]
23. model families: ["LLAMA2_70B", "LLAMA3_70B", "STABLE_DIFFUSION_V2"]
24. node counts: [1, 2, 4, 8, 16]
25. GPUs per node: 4
26. partial GPU measured: NO
27. shared jobs measured: NO
28. idle measured: NO
29. valid runs: 2472
30. structural-invalid runs: 0
31. sensor-invalid runs: 533
32. valid-extreme field records: 1154
33. raw/aggregate reconciliation: RAW_AGGREGATED_RECONCILIATION_PARTIAL
34. primary boundary: GPU_PLUS_RAPL_PACKAGE_COMPONENT_SUM (component-level only)
35. overall mean range W: 738.87 to 38775.76
36. overall P05/P50/P95 ranges: {"P05_range_W": "733.35 to 11664.22", "P50_range_W": "736.28 to 39249.49", "P95_range_W": "742.05 to 48105.34"}
37. max workload spread W: 5349.257156272979
38. node scaling per-node means W: {"LLAMA2_70B:16": 2401.467, "LLAMA2_70B:2": 2630.546, "LLAMA2_70B:4": 2575.689, "LLAMA2_70B:8": 2469.069, "STABLE_DIFFUSION_V2:1": 2705.939, "STABLE_DIFFUSION_V2:16": 2067.139, "STABLE_DIFFUSION_V2:2": 2656.493, "STABLE_DIFFUSION_V2:4": 2396.466, "STABLE_DIFFUSION_V2:8": 2235.033}
39. maximum scale: 16 nodes / 64 GPUs
40. energy reconciliation: PARTIAL
41. resource-state support: STATE_SUPPORT_FULL_NODE_EXCLUSIVE_ONLY
42. authority level: H1_COMPONENT_LEVEL_H100_POWER_AUTHORITY
43. partial GPU identified: NO
44. shared power identified: NO
45. robust envelope: YES_COMPONENT_BOUNDARY_ONLY; NO_WHOLE_NODE_ENVELOPE
46. envelope dimensions: ["full-node exclusive", "node_count", "power_boundary", "normalization"]
47. P_LOW: minimum across classes of within-class run-mean P05
48. P_CENTER: median across classes of within-class run-mean P50
49. P_HIGH: maximum across classes of within-class run-mean P95
50. unknown class: Use class-stratified envelope only for supported full-node-exclusive component boundary
51. full-node bridge: DIAGNOSTIC_ONLY
52. partial bridge: UNSUPPORTED
53. shared bridge: UNSUPPORTED
54. idle bridge: UNSUPPORTED
55. per-job bridge: UNSUPPORTED
56. Dataset312 job join: FORBIDDEN
57. RADDiT H100 magnitude: NO
58. partial/shared answer: NO_DEFENSIBLE_PUBLIC_BRIDGE
59. KESTREL_NODE_PACKING_NEXT: DEFER
60. PRODUCTION_INTEGRATION_RECOMMENDED: NO
61. tests passed: 28
62. tests failed: 0
63. primary classification: V35R3F_DATASET312_COMPONENT_ONLY

## Required questions

Q1. Per-device NVML H100 power/temperature and per-socket RAPL package/core energy-derived power, recorded by WattAMeter.
Q2. GPU and CPU component power only. Whole-node input power is not measured; the supplied power[W] is a component sum and also adds nested RAPL package/core channels.
Q3. Raw inference is approximately 0.1 s; raw training approximately 0.2 s. Supplied outputs are 0.1 s, 0.2 s, and 0.001 s interpolation for online-rate inference.
Q4. Llama-2 70B LoRA fine-tuning, Stable Diffusion v2 training, and Llama-3 70B offline/online inference.
Q5. Node counts.
Q6. 1/2/4/8/16 nodes and, at four GPUs per node, 4/8/16/32/64 GPUs.
Q7. NO.
Q8. NO.
Q9. No P_node(k,c). Supported is a full-node-exclusive measured-component function by experiment node count and represented benchmark class.
Q10. Use GPU+RAPL-package component sum only as a component-level diagnostic; no measured quantity is authorized as whole-node IT power.
Q11. Reported numerically in NODE_SCALING and WORKLOAD_POWER_VARIABILITY; per-node power changes with both class and weak-scaling configuration.
Q12. [{"P_CENTER": 2723.2467725492343, "P_HIGH": 2854.901953571029, "P_LOW": 2106.251719845168, "node_count": 1, "unit": "W_per_node"}, {"P_CENTER": 2645.9762912563483, "P_HIGH": 2670.1390783627394, "P_LOW": 2615.6521142485976, "node_count": 2, "unit": "W_per_node"}, {"P_CENTER": 2519.4316388945035, "P_HIGH": 2611.2802386479034, "P_LOW": 2166.4226845384683, "node_count": 4, "unit": "W_per_node"}, {"P_CENTER": 2413.419134963119, "P_HIGH": 2485.041312108554, "P_LOW": 2012.8594989341368, "node_count": 8, "unit": "W_per_node"}, {"P_CENTER": 2236.2161306754842, "P_HIGH": 2420.7328663809417, "P_LOW": 1908.0537139916075, "node_count": 16, "unit": "W_per_node"}]
Q13. YES only for the supported full-node-exclusive component-level envelope; NO for whole-node IT or partial/shared states.
Q14. NO.
Q15. NO defensible whole-node bound from frozen Dataset 312 alone; missing idle/base and non-GPU/CPU-package components prevent a closed physical bound.
Q16. Shared jobs consume one physical node boundary; summing independent job coefficients would count the same GPU/CPU/base hardware more than once.
Q17. DEFER. The deterministic packing design is sound, but physical whole-node, idle, partial/shared power authority is still missing.
Q18. Whole-node input/base power, partial/shared occupancy behavior or independent bounds, idle power, and a deterministic resource-to-node occupancy mapping.
Q19. NO.
Q20. NO.

## Source boundary warning

The robust envelope is an empirical envelope for measured GPU plus CPU-package components under full-node-exclusive workloads. It is not a whole-node IT input-power envelope and cannot be used to assign power to individual Kestrel jobs.
