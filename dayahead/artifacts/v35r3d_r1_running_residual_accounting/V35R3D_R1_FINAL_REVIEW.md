# V35R3D-R1 Final Review

## 1–86 결과

1. 98fb2923b24e145346d2f4bc3bb9be6aab395bba
2. codex/v35r3d-r1-running-residual-accounting-correction
3. C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3d_r1_running_residual_accounting
4. PENDING_THIS_COMMIT (authoritative value reported after commit)
5. YES after commit
6. 0
7. 0
8. NO/NO
9. 243
10. 498.0
11. 170 / 272.0 GPU
12. 0 / 0.0 GPU
13. 73 / 226.0 GPU
14. 0 / 0.0 GPU
15. 45.381526104%
16. 73 jobs / 226.0 GPU / 56.5 GPU-h at OLD_RS slot 1 (70.625000% of OLD_RS PRE-DAY running release GPUs)
17. 87824
18. 5576.449219 s
19. 5576.449219 s
20. 90.001594097%
21. 88.379030789%
22. 90.001594097%
23. 88.379030789%
24. 5.282155220%
25. 24.095919111%
26. Q_CONF90_FINITE_SAMPLE_SPLIT_CONFORMAL
27. 5576.449219 s
28. 88.379030789%
29. 91
30. 161
31. 252
32. 86
33. 338
34. 0
35. 338
36. 0
37. 163
38. 175
39. 338
40. 0
41. 96
42. 0
43. 59
44. 17
45. 34
46. 32
47. 40.25
48. 109.5
49. 96.5
50. 226
51. 428
52. 465
53. 65
54. 428
55. 290
56. 3408.0
57. 0.0
58. 0.0
59. RW 0 / RSP 1
60. RW 0 / RSP 3
61. RW 0 / RSP 4
62. RW 0.0 / RSP 4.0
63. RW 0.0 / RSP 30.0
64. RW 0.0 / RSP 39.0
65. RW 0 / RSP 0
66. RW 202 / RSP 151
67. 56.25
68. 239
69. 86
70. 0
71. -51
72. YES
73. R2_DIAGNOSTIC_CAUSAL_RUNTIME
74. PASS
75. CONDITIONAL_SAFE_COVERAGE_LIMITED_BY_REQUESTED_WALLTIME_CAP
76. REQUESTED_WALLTIME_CONSERVATIVE
77. V35R3D_R1_RSP_TEMPORAL_OPPORTUNITY_CONFIRMED
78. YES
79. NO
80. 0
81. 0
82. 0
83. 0
84. NO
85. 31
86. 0

## Q1–Q17

Q1. 73개이다.
Q2. 226.0/498 GPU, 즉 45.381526%이다.
Q3. OLD_RS가 첫 15분 뒤 해제한 226.0 GPU, 즉 56.5 GPU-h(73개 작업)가 이 조건에서 왔다. 이는 OLD_RS PRE-DAY running release GPU의 70.625000%이다.
Q4. Empirical q는 uncapped 90.001594%로 정상이다. requested-walltime cap이 coverage를 88.379031%로 낮췄다.
Q5. YES. conformal uncapped coverage는 90.001594%이다. 다만 residual tie 때문에 q는 empirical 값과 같다.
Q6. 1.622563%p를 잃는다.
Q7. ACCOUNTING_LABEL_AMBIGUITY_CORRECTED
Q8. RSP standby는 PRE-DAY 163개, APR-01 175개, 총 338개가 시작한다.
Q9. RW 96개, RSP 59개이다.
Q10. RW 40.25 GPU-h, RSP 96.5 GPU-h이다.
Q11. RW 226, RSP 465이다.
Q12. YES
Q13. W1/W3/W5 RSP release events는 1/3/4이다.
Q14. YES. RSP에서 W5에 남는 pre-W5 admission 결정은 151개이며 RW와의 W5-active 작업 집합 대칭차는 325개이다.
Q15. YES
Q16. NO. 미래 Apr-01 end/runtime은 사용하지 않았다.
Q17. NO.

전력·계통 효과는 평가하지 않았다.
