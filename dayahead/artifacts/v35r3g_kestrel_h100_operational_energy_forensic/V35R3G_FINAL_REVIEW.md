# V35R3G Kestrel Dataset 302 Operational Energy Forensic

## GIT

1. parent HEAD: 8b3808a92930709a4df01365653b96b7bdb3a0df
2. branch: codex/v35r3g-kestrel-h100-operational-energy-forensic
3. worktree: C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3g_kestrel_h100_operational_energy_forensic
4. final HEAD: REPORTED_AT_HANDOFF_AFTER_ARTIFACT_COMMIT
5. clean: CLEAN_AFTER_FINAL_COMMIT
6. production files changed: 0
7. MESS files changed: 0
8. vendor/source files changed: 0
9. push/merge: NO_PUSH_NO_MERGE

## SOURCE

10. Dataset302 SHA: 3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f
11. normalized source rows: 10559977
12. row granularity: ONE_PARENT_JOB_ROW_PER_ID_ARRAY_ELEMENTS_SEPARATE_NO_STEPS
13. duplicate logical allocation count: 0
14. source time span: 2023-08-10T04:13:58+00:00 to 2026-01-01T06:48:47+00:00

## ENERGY FIELDS

15. canonical energy field(s): ["consumed_energy_raw_joules", "consumed_energy_raw_watt_hours (derived)"]
16. units: ["J", "Wh"]
17. Joule/Wh consistency: PASS; Wh is ConsumedEnergyRaw/3600, not an independent sensor
18. positive-energy all-source rows: 7064950
19. zero/missing-energy rows: 3495027
20. invalid-energy rows: 0

## PHYSICAL BOUNDARY

21. ConsumedEnergyRaw physical boundary: SLURM_NODE_LEVEL_MONITORING_SENSOR_BOUNDARY_EXACT_PLUGIN_AND_COMPONENTS_UNKNOWN
22. includes GPU energy: UNKNOWN
23. includes CPU energy: UNKNOWN
24. whole-node input: UNKNOWN
25. idle/base included: UNKNOWN
26. physical-boundary authority source: Dataset302 datacard + Slurm sacct/slurm.conf; Kestrel plugin/sensor configuration absent

## ATTRIBUTION

27. exclusive job attribution authorized: NO
28. partial-exclusive attribution authorized: NO
29. shared-job attribution authorized: NO
30. shared double-count risk: SHARED_ENERGY_DOUBLE_COUNT_RISK

## H100

31. confirmed H100 jobs: 1332564
32. H100 positive-energy jobs: 0
33. full-node exclusive H100 positive-energy jobs: 0
34. partial-exclusive H100 positive-energy jobs: 0
35. shared H100 positive-energy jobs: 0

## GLOBAL

36. global full-node-exclusive usable jobs: 0
37. global full-node-exclusive GPU-h: 0.0
38. global full-node-exclusive node-h: 0.0
39. first/last usable label date: NONE

## PREISSUE

40. exact issue timestamp: 2025-03-31T18:00:00+10:00 = 2025-03-31T08:00:00+00:00
41. causal preissue full-node-exclusive usable jobs: 0
42. causal preissue GPU-h: 0.0
43. causal preissue node-h: 0.0
44. causal preissue distinct days: 0

## RECENCY

45. 365d usable jobs: 0
46. 180d usable jobs: 0
47. 120d usable jobs: 0
48. 60d usable jobs: 0
49. 30d usable jobs: 0
50. last usable preissue label date: NONE
51. gap to issue: NOT_APPLICABLE_NO_USABLE_LABEL

## DERIVED POWER

52. average-power quantity authorized: NO
53. physical name of quantity: NOT_AUTHORIZED
54. P05/P50/P95: NOT_AUTHORIZED
55. full-node scaling: NOT_AUTHORIZED
56. Dataset312 diagnostic comparison performed: NO

## PARTIAL / SHARED

57. PARTIAL direct operational label authority: NO
58. SHARED direct operational label authority: NO
59. shared conservation classification: SHARED_ENERGY_DOUBLE_COUNT_RISK

## MODELABILITY

60. modelability classification: NOT_MODELABLE_NO_POSITIVE_ENERGY
61. chronological train/validation possible: NO
62. causal query-feature authority: PASS_FIREWALL; FAIL_TARGET_AVAILABILITY
63. Apr01 running feature-domain coverage: {"coverage_fraction": 0.0, "covered_rows": 0, "rows": 243, "status": "NOT_COVERED_EMPTY_AUTHORIZED_TRAINING_DOMAIN"}
64. Apr01 temporal-pending feature-domain coverage: {"coverage_fraction": 0.0, "covered_rows": 0, "rows": 339, "status": "NOT_COVERED_EMPTY_AUTHORIZED_TRAINING_DOMAIN"}
65. strict-F0 feature-domain coverage: {"coverage_fraction": 0.0, "covered_rows": 0, "rows": 3, "status": "NOT_COVERED_EMPTY_AUTHORIZED_TRAINING_DOMAIN"}
66. PARTIAL/shared feature-domain coverage: {"coverage_fraction": 0.0, "covered_rows": 0, "rows": 336, "status": "NOT_COVERED_EMPTY_AUTHORIZED_TRAINING_DOMAIN"}

## AUTHORITY

67. highest energy authority: E0_ENERGY_FIELD_PRESENT_ONLY
68. primary classification: V35R3G_PREISSUE_H100_POSITIVE_ENERGY_EMPTY

## NEXT STEP

69. CAUSAL_H100_POWER_MODEL_NEXT: NO
70. SHARED_H100_POWER_NEXT: DEFER
71. DATASET312_AUTHORITY_CHANGED: NO
72. PRODUCTION_INTEGRATION_RECOMMENDED: NO

## CAUSALITY

73. Apr01 consumed-energy reads: 0
74. Apr01 realized-runtime reads: 0
75. Apr01 future-end reads: 0
76. grid reads: 0
77. Fresh reads: 0
78. MESS reads: 0

## TESTS

79. passed: 34
80. failed: 0

## 질문 답변

Q1. Slurm이 보고한 노드 수준 모니터링 센서의 누적 에너지(J)이나, Kestrel의 실제 플러그인과 센서 구성은 공개 자료에 없다.

Q2. 아니다. H100 GPU 에너지 포함 여부는 UNKNOWN이다.

Q3. 아니다. 전체 노드 AC/DC 입력 에너지라는 권위는 없다.

Q4. 아니다. 데이터셋에 Slurm Exclusive 필드가 없고 물리 센서 경계도 미해결이다.

Q5. 전체 공개 추적에서 양의 에너지를 가진 H100 작업은 0개다.

Q6. 엄격한 full-node exclusive H100 양의 에너지 작업은 0개다.

Q7. Apr-01 발행 시각 이전의 인과적으로 사용 가능한 full-node exclusive H100 라벨은 0개다.

Q8. 365/180/120/60/30일 창 모두 0개다.

Q9. 확인되었다. 최근뿐 아니라 전체 공개 추적에서 H100 양의 에너지 권위가 비어 있다.

Q10. 허가된 평균 전력량은 없다. E/runtime 계산을 수행하지 않았다.

Q11. 사용 가능한 라벨이 없으므로 최근성 날짜와 issue 간격은 정의되지 않는다.

Q12. 아니다. 시간/자원 다양성을 평가할 양의 타깃 자체가 없다.

Q13. 아니다. 부분 독점 H100의 양의 에너지가 없고 센서 경계도 미해결이다.

Q14. 아니다. 공유 작업 에너지를 작업별로 나누면 보존과 이중계수 문제가 생긴다.

Q15. 아니다. Dataset302는 공유 H100 귀속 차단 요인을 해결하지 못한다.

Q16. E0_ENERGY_FIELD_PRESENT_ONLY

Q17. 아니다. CAUSAL_H100_POWER_MODEL_NEXT=NO이다.

Q18. 해당 없음. 허가된 학습 타깃 코호트가 없다.

Q19. 양의 H100 에너지 부재가 즉시 차단 요인이며, 물리 경계와 독점 귀속도 미해결이다.

Q20. 아니다. Apr-01 실현 에너지/런타임/종료 시각 읽기는 모두 0이다.

Q21. 아니다. Dataset312로 Dataset302 라벨을 제조하거나 스케일링하지 않았다.

Q22. 아니다. 생산 통합 권고는 NO이다.
