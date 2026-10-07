# V42 A-stage 도메인 권한 V2 최종 검토

이 문서는 추가 실행 승인 전의 V2 도메인 정적 검토 단계 기록입니다. 추가 승인에 따른 네 날짜 stress 실행과 최종 판단은 ../v42_a_stage_v2_stress4_20261007/FINAL_REVIEW_KO.md에서 별도로 기록합니다.

1. 기존 prescreen은 물리적으로 가능한 시작을 R0 이후로 제한하여 과학적 feasible set과 계산용 활성 후보를 혼동했습니다.
2. reference-start 하한, known-window/reference-lower 필터 및 119 슬롯 복원 상한은 독립적 물리 release가 아닌 후보 제한이었습니다.
3. 인과 release, 기존 completion, GPU/rack/site, 보호·high·urgent, 체크포인트/WAN/restart, RUNNING 이력, terminal 불가능성과 완전 계수 일치 중복만 영구 컷이 가능합니다.
4. R0 거리, 작은 grid 이익, 낮은 선택확률, 모델 크기와 휴리스틱 dominance는 영구 컷이 불가능합니다.
5. R0는 P2 시작 이동 크기와 공통 no-action 시작/site 참조로 유지합니다.
6. R0는 독립적 hard rule이 없는 유연 PENDING 시작 도메인의 벽이 아닙니다.
7. 기존 과학적 class aggregation과 정확한 멤버를 유지했습니다.
8. class_exact_cardinality를 유지했고 활성화·복원 시 원래 class 수를 변경하지 않습니다.
9. 물리적으로 유효한 A_NOFLEX anchor는 heuristic에 의해 제거되지 않습니다.
10. 같은 jobs/service/Runtime/CC4/GPU/rack/grid 계수에서 no-flex feasible set은 flex set에 포함됩니다. no-flex 자체의 전역 feasibility를 주장하지 않습니다.
11. 모든 물리적 STAY 시작/site는 scientific universe에 있습니다. 활성 MILP는 증명된 histogram 범위는 전체, singleton mixed-flow는 S0+anchor와 지연 STAY를 사용합니다.
12. 기존 histogram의 정수·LP 투영은 정확히 증명했습니다. 모든 클래스의 일괄 compact 대체는 singleton mixed-flow LP 반례 때문에 채택하지 않았습니다.
13. 이미 압축된 histogram의 표현 변경 delta는 0입니다. 지원 확대의 변수 증가량과 전체 행/nnz 예측은 아래 표에 구분했습니다.
14. 전체 migration 경로 Option/native 열을 물질화하지 않았습니다.
15. 모든 원래 체크포인트·전송 시각을 lossless lazy block에 보존하며 원래 payload/path/restart/remaining/Runtime/grid를 재구성합니다.
16. 낮은 grid 이익 후보도 삭제하지 않습니다.
17. 저장된 signed 민감도, displacement, canonical 순서로 HIGH/MEDIUM/LOW_PRIORITY를 부여합니다.
18. 완전한 exact row/objective 계수 동일성만 중복을 제거합니다. 이번 과학 후보 제거는 0이며 안전한 일반 dominance 증명은 채택하지 않았습니다.
19. May10 복원 STAY 후보는 class support 기준 825,961개입니다.
20. May12 복원 STAY 후보는 class support 기준 188,520개입니다.
21. May17 복원 STAY 후보는 class support 기준 113,760개입니다.
22. May17 기존 35 rescue Option 전부 full attribute 정적 membership PASS입니다.
23. May19 복원 STAY 후보는 class support 기준 163,111개입니다.
24. PR165 38개 및 PR166 S_A/S_B/S_C/S_D의 모든 시험 Option을 원래 과학 속성까지 포함하여 정적으로 확인했습니다.
25. 날짜별 전망은 아래 표와 MODEL_SIZE_FORECAST.csv에 있습니다. native model을 생성하지 않았고 rows/nnz는 추정입니다.
26. binary/integer/continuous 변화는 기존 F2-CRA 분기에서 구조적으로 계산했습니다. A2SC 후속 축약률은 가정하지 않습니다.
27. 초기 정적 검토 단계의 May10/12/17/19 native optimize 호출은 0회입니다. 추가 승인 이후에는 12개 PASS receipt와 실행 소스 SHA를 고정한 permit 안에서만 네 날짜 실행을 허용합니다.
28. 기존 27개 PASS 날짜는 재실행하지 않았습니다.
29. CC4/Runtime/service/GPU/rack/WAN/grid/전압/정격은 변경하지 않았습니다. shift는 원래 양수 영역의 계수와 동일하며 새 이른 시작에는 절댓값 이동 크기를 사용합니다.
30. Production-domain 최적성은 미인증이고 PRODUCTION_DOMAIN_ACCEPTED=false입니다. root LP 가격 검사만으로 MILP 완결성을 주장하지 않습니다.
31. 추가 지시에서 네 날짜 실행은 이미 승인됐습니다. 실행 전 정확성·정적·짧은 테스트 PASS를 요구하며 생산 최적성에는 전체 finite 활성화 또는 유효한 정수 closure 증명이 필요합니다. 다른 27개 날짜는 계속 실행 금지입니다.
32. 구현 source commit: 게시 직전 source commit을 PUBLICATION_RECEIPT.json에서 기록합니다.; Draft PR: 검증 완료 후 게시합니다.

| 날짜 | 과학 STAY 복원 | 활성 columns | binary | integer count | continuous | rows 추정 | nnz 추정 |
|---|---:|---:|---:|---:|---:|---:|---:|
| May10 | 825,961 | 1,902,189 | 246,703 | 646,428 | 1,009,058 | 1,770,608 | 96,672,670 |
| May12 | 188,520 | 3,965,805 | 1,390,554 | 177,384 | 2,397,867 | 4,331,379 | 48,863,609 |
| May17 | 113,760 | 253,329 | 4,557 | 111,804 | 136,968 | 815,531 | 24,298,934 |
| May19 | 163,111 | 4,461,909 | 1,675,764 | 146,376 | 2,639,769 | 4,592,286 | 47,835,777 |

초기 정적 검토 단계에서는 production optimize를 실행하지 않았습니다. 후보 복원이 두 날짜의 계산 문제를 해결한다는 주장은 하지 않습니다. 추가 승인 후 결과는 stress4 보고서에서 확인합니다.

짧은 검증: 1523개 PASS. 초기 정적 검토 단계 Actual/Fresh/campaign/예약 실행은 0회입니다.
