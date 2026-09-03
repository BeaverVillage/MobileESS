# V35R3H Scientific Data 2026 H100 Resource-State Authority Audit

## GIT

1. parent HEAD: 0d27a63d858e2506622f4bcec65e90921a850c8b
2. branch: codex/v35r3h-scientificdata2026-h100-resource-state-audit
3. worktree: C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3h_scientificdata2026_h100_resource_state_audit
4. final HEAD: REPORTED_AT_HANDOFF_AFTER_ARTIFACT_COMMIT
5. clean: CLEAN_AFTER_FINAL_COMMIT
6. production files changed: 0
7. MESS files changed: 0
8. source files changed: 0
9. push/merge: NO_PUSH_NO_MERGE

## SOURCE

10. paper DOI: 10.1038/s41597-026-07496-6
11. Figshare returned DOI: 10.6084/m9.figshare.31654879.v1
12. Figshare version: 1
13. downloaded file count: 1
14. total source bytes: 209685111
15. code repository HEAD: f7f8d62e806ce2b64e93c58fce2bb18604f067ad

## DATA

16. total measurement sessions: 72
17. H100 sessions: 16
18. B200 sessions: 16
19. H100 raw samples: 720000
20. B200 raw samples: 720000

## HARDWARE

21. H100 model: NVIDIA H100 SXM 80GB
22. H100 GPUs/node: 8
23. B200 GPUs/node: 8
24. H100 node count configurations: [1]
25. H100 total-GPU configurations: [8]

## SENSORS

26. H100 per-GPU power directly measured: YES
27. CPU power directly measured: NO
28. whole-node power directly measured: NO
29. facility power directly measured: NO
30. native sampling frequency/interval: 50 Hz nominal / 20 ms; actual H100 medians 20 ms

## STATE SUPPORT

31. H100 active-GPU states directly observed: ["8_of_8_active"]
32. partial-GPU state directly measured: NO
33. idle GPU state directly measured: NO
34. all-GPU-idle state directly measured: NO
35. whole-node idle/base power directly measured: NO
36. shared multi-job state directly measured: NO

## SEMANTICS

37. multi-GPU experiments represent: one distributed training workload using all 8 GPUs in one node
38. multi-node experiments represent: none; no multi-node measurement sessions
39. shared/co-resident independent jobs present: NO

## POWER

40. H100 per-GPU mean range: {"max": 562.7488455333333, "min": 168.67906522222222}
41. H100 per-GPU P05/P50/P95 range: {"P05": {"max": 143.628, "min": 115.1}, "P50": {"max": 618.525, "min": 117.117}, "P95": {"max": 696.93, "min": 274.88804999999996}}
42. H100 node GPU-sum mean range: {"max": 4421.852076022222, "min": 1396.0015556222222}
43. H100 node GPU-sum P05/P50/P95 range: {"P05": {"max": 1048.3374000000001, "min": 975.0870000000001}, "P50": {"max": 4915.299, "min": 989.7495000000001}, "P95": {"max": 5543.39905, "min": 2247.39405}}
44. directly supported k states: [8]
45. resource-state curve identification: P_GPU_NODE_K_PARTIAL_SUPPORT: k=8 only; curve not identified
46. workload dependence summary: MATERIAL: image-generation and LLM session-node means differ substantially; class-specific variation retained

## ENVELOPE

47. class-agnostic state envelope available: YES_COMPONENT_ONLY_K8
48. supported k values: [8]
49. P_LOW definition: MIN_ACROSS_CLASSES_OF_WITHIN_CLASS_SESSION_NODE_MEAN_P05
50. P_CENTER definition: MEDIAN_ACROSS_CLASSES_OF_WITHIN_CLASS_SESSION_NODE_MEAN_P50
51. P_HIGH definition: MAX_ACROSS_CLASSES_OF_WITHIN_CLASS_SESSION_NODE_MEAN_P95

## WHOLE NODE

52. whole-node authority: W0_NO_WHOLE_NODE_POWER
53. active whole-node usable: NO
54. idle whole-node usable: NO

## H100 RESOURCE AUTHORITY

55. highest H100 authority: S2_H100_MULTI_GPU_NODE_COMPONENT_AUTHORITY
56. PARTIAL_GPU_PUBLIC_AUTHORITY: NO
57. SHARED_MULTI_JOB_PUBLIC_AUTHORITY: NO
58. IDLE_GPU_PUBLIC_AUTHORITY: NO

## DATASET312

59. component cross-check status: PASS_COMPATIBLE_NVML_GPU_COMPONENT_BOUNDARY_DIAGNOSTIC_ONLY
60. Dataset312 authority changed: NO

## B200

61. B200_USED_FOR_H100_MAGNITUDE: NO

## KESTREL BRIDGE

62. per-GPU component bridge: DIRECTLY_SUPPORTED
63. node GPU-sum bridge: SUPPORTED_COMPONENT_ONLY
64. partial-GPU bridge: UNSUPPORTED
65. shared bridge: UNSUPPORTED
66. idle-node bridge: UNSUPPORTED
67. per-job bridge: UNSUPPORTED
68. class-agnostic component envelope bridge: SUPPORTED_COMPONENT_ONLY_K8

## NEXT STEP

69. KESTREL_NODE_PACKING_NEXT: DEFER
70. PUBLIC_H100_EXACT_PARTIAL_SHARED_POWER_BLOCKER_REMAINS: YES
71. PRODUCTION_INTEGRATION_RECOMMENDED: NO

## FIREWALL

72. Kestrel Apr01 schedule reads: 0
73. RW/RSP reads: 0
74. Planning reads: 0
75. Fresh reads: 0
76. MESS reads: 0
77. May reads: 0

## TESTS

78. passed: 54
79. failed: 0

## CONCLUSION

80. primary classification: V35R3H_H100_MULTI_GPU_COMPONENT_ONLY

## 질문 답변

Q1. H100/B200 노드에서는 pynvml로 각 GPU의 전력·사용률·메모리·온도를 직접 측정했다. 노드 전력 입력은 측정하지 않았고 'node power'는 GPU 8개 전력의 합이다.

Q2. 예. 경로·파일명·GPU 메모리 용량으로 H100과 B200이 명확히 분리되며 B200 수치는 H100 통계에 포함되지 않았다.

Q3. H100 물리 노드당 8개다.

Q4. 동일한 단일 물리 노드의 GPU 8개가 하나의 분산 학습 작업에 함께 참여한 실험이다.

Q5. 동일 노드에서 직접 확인된 자원 상태는 8-of-8 하나뿐이다. 1/2/4 GPU 부분 점유 실험은 없다.

Q6. 직접 측정된 k는 8뿐이다.

Q7. 아니다. 작업에 의도적으로 할당되지 않은 GPU를 둔 부분 점유 실험은 없다. 순간 0% 사용률은 분산 작업 내부의 일시 정지일 뿐이다.

Q8. 아니다. 제어된 별도 all-GPU-idle 세션은 없다.

Q9. 아니다. 전체 노드 idle/base 입력 전력 센서가 없다.

Q10. 아니다. GPU NVML 합만 있으며 전체 노드 활성 입력 전력은 측정하지 않았다.

Q11. 아니다. 같은 노드에 공존하는 독립 작업 둘 이상의 실험은 없다.

Q12. 아니다. k=8 점 하나의 GPU-component 값만 직접 구성할 수 있어 P_node(k) 곡선은 식별되지 않는다.

Q13. 아니다. 비-GPU 노드 구성요소와 입력 센서가 없어 whole-node 곡선은 구성할 수 없다.

Q14. 아니다. Kestrel PARTIAL 상태에 필요한 k=1/2/3 등의 직접 측정이 없다.

Q15. 아니다. 공유 독립 작업과 GPU 소유권 자료가 없어 귀속을 만들 수 없다.

Q16. k=8 NVML GPU-component 노드 합에 한해 P_LOW=1474.606845 W, P_CENTER=2922.146633 W, P_HIGH=4345.175809 W의 클래스 층화 세션-평균 envelope가 가능하다.

Q17. 호환되는 H100 NVML GPU-component 경계에서 범위가 부분 중첩한다. 플랫폼·모델·GPU 수가 달라 진단적 일치만 인정하며 보정이나 스케일링은 하지 않았다.

Q18. 아니다. KESTREL_NODE_PACKING_NEXT=DEFER이다.

Q19. 재개하지 않는다. 향후 직접 상태가 확보되더라도 계산 가능한 것은 GPU-component 노드 합뿐이며 whole-node 또는 작업별 전력이 아니다.

Q20. Kestrel PARTIAL/SHARED에 필요한 동일 노드의 다중 k 직접 측정, 공유 작업별 GPU 소유권·보존 귀속, 전체 노드 활성/idle 입력 전력이 남은 차단 요인이다.

Q21. 아니다. B200_USED_FOR_H100_MAGNITUDE=NO이다.

Q22. 아니다. Kestrel schedule, grid/RW/RSP, Fresh, MESS, Apr02+, May 결과 읽기는 모두 0이다.

Q23. 아니다. PRODUCTION_INTEGRATION_RECOMMENDED=NO이다.
