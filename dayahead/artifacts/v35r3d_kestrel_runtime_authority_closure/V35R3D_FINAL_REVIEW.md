# V35R3D Final Review

## 1–87 결과

1. 11553d456beb5a821408065aeea3bbda107961e9
2. codex/v35r3d-kestrel-runtime-authority-closure
3. C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3d_kestrel_runtime_authority_closure
4. PENDING_THIS_COMMIT (authoritative value reported after commit)
5. YES after commit
6. 0
7. 0
8. NO/NO
9. 3.11.7
10. 3.2.0
11. 218d75f56b783ebfd698100f9406cfb46fa04c01
12. 3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f
13. recipe.job_runtime.kestrel_moe_best_rolling
14. PASS
15. PASS; 245 rows; MAE 23883.486 s
16. PASS; 4 fixed windows; 5987 rows
17. FIXED_32_WINDOW_SUBSET_PASS_FULL_120_NOT_RUN_PROHIBITIVE
18. 5778.795127 s
19. 428.809326 s
20. 21483.769898 s
21. PASS
22. True
23. True
24. True
25. True
26. True
27. 0.0
28. 243/243 (100.000000%)
29. 100.000000%
30. 339/339 (100.000000%)
31. 100.000000%
32. 582/582
33. 0
34. 2025-03-24T00:00:00+10:00 to 2025-03-31T00:00:00+10:00 (exclusive)
35. 87824
36. 5576.449219
37. 4866.277249
38. 347.013947
39. 18782.792285
40. 0.507902168
41. 0.883790308
42. 0.240959191
43. 96
44. 0
45. 0
46. 17
47. 30
48. 34
49. 40.25
50. 111.0
51. 109.5
52. 226
53. 429
54. 428
55. 161
56. 0
57. 0
58. 65
59. 429
60. 428
61. 3408.0
62. 0.0
63. 0.0
64. RW 0 / RS 0
65. RW 0 / RS 0
66. RW 0 / RS 0
67. RW 0.0 / RS 0.0
68. RW 0.0 / RS 0.0
69. RW 0.0 / RS 0.0
70. RW 0 / RS 0
71. 69.25
72. 202
73. -161
74. 0
75. YES
76. 0
77. 0
78. 0
79. 0/0
80. NO
81. R2_DIAGNOSTIC_CAUSAL_RUNTIME
82. V35R3D_RUNTIME_PARTIAL_COVERAGE_ONLY
83. CONDITIONAL
84. YES
85. NO
86. 45
87. 0

## Q1–Q15

Q1. YES. 격리 환경에서 xgboost 3.2.0과 로컬 고정 hpc-oda를 실행해 이전 환경 차단을 제거했다.
Q2. 고정 레시피로 32개 고정 창을 재현했다. 전체 120창은 추정 17.02시간으로 실행하지 않아 권위는 R2로 제한한다.
Q3. YES. 245행이 일치했고 최대 절대차는 0.0이다.
Q4. 243/243 (100.000000%)
Q5. 339/339 (100.000000%)
Q6. q90_plus=5576.449219초, 경험적 안전 포괄률=88.379031%.
Q7. RW 96개, RS 0개.
Q8. RW 40.25 GPU-h, RS 109.5 GPU-h.
Q9. YES.
Q10. 0개.
Q11. YES
Q12. NO. 미래 실제 종료시각이나 Apr-01 실현 런타임을 사용하지 않았다.
Q13. CONDITIONAL. 고정 32창 진단은 통과했지만 전체 공개 120창 미실행으로 R2 한계를 유지한다.
Q14. YES
Q15. NO.

전력·계통 효과는 이 런타임 전용 과업에서 평가하지 않았다.
