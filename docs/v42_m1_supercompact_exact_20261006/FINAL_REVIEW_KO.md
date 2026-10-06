# 현재 4-MESS M1 exact supercompact 검토

최종 상태: **SUPER_COMPACT_EXACT_SELECTED**. 선택: **True**.

기준: PR160 `8513a281615d9e0fd0af2b7cb3d36b6f8a1fb962`. PR124 `c7d808a315e04aefc1bcfc537b84cc38d895a9ab`는 설계/증명 참고에만 사용했다. scientific authority, 4 MESS, 96 slot, objective P1, PCS16, SOC 양 끝점, 모든 route/travel/grid 한계와 MIPGap .005를 보존했다.

| 모델 | rows | cols | binary | continuous | nnz |
|---|---:|---:|---:|---:|---:|
| F0 | 886,017 | 316,743 | 208,312 | 108,431 | 8,447,855 |
| C0 | 895,055 | 325,781 | 9,422 | 316,359 | 8,664,917 |
| C1 | 704,775 | 325,781 | 9,422 | 316,359 | 5,804,032 |
| C2 | 654,348 | 306,040 | 9,322 | 296,718 | 5,584,200 |

F1 원본 arc reference: rows 695,737, cols 316,743, B 208,312, nnz 5,586,970. F0/F1은 동일 authority·start·설정의 PR160 영수증을 사용했고 새 heavy solve를 재실행하지 않았다.

| 질문 | 답변 |
|---|---|
| 1. 현재 원본 규모 | rows 886,017, cols 316,743, B 208,312, C 108,431, nnz 8,447,855 |
| 2. C0 규모 | rows 895,055, cols 325,781, B 9,422, C 316,359, nnz 8,664,917 |
| 3. C1 규모 | rows 704,775, cols 325,781, B 9,422, C 316,359, nnz 5,804,032 |
| 4. C2 규모 | rows 654,348, cols 306,040, B 9,322, C 296,718, nnz 5,584,200 |
| 5. 최종 binary | 9,322; 원본 대비 95.524982% 감소 |
| 6. 최종 continuous | 296,718; C0 대비 6.208453% 감소 |
| 7. compact-specific 제거 행 | 50,427; C1→C2 순차 압축 |
| 8. 제거·고정 변수 | 제거 19,741, continuous 고정값 증명 15,642, source activity binary 추가 고정 4개. 제거·고정 집계는 중첩되며 합산하지 않는다. |
| 9. 결정적 flow contraction | 192개 flow를 동일 activity 변수로 단위 치환. 중간 scientific event를 제거하는 다단계 route chain contraction은 0개. |
| 10. bound 변경 | 24,620건; 독립 검증 24,620건. 동일 변수의 순차 tightening은 각각 기록. |
| 11. compact LP에서 PR160 삭제 유지 | 190,280개 전부. 정확한 행/대표/PCS/연결/분수 convex-hull 상계를 독립 재검증. |
| 12. LP strengthening으로 PR160 행 유지 | 0개. 이번 인증 집합에는 integer-only 삭제 증명이 없었고 UNKNOWN/정수 전용 증명으로 삭제한 행도 0개. |
| 13. grid auxiliary 제거 | 19,441개. 상수·완전히 같은 정의·희소 단위 alias만 채택. |
| 14. nnz 증가로 grid auxiliary 유지 | 42,955개에서 보수적 nnz union 비용 증가. 그 외 KEEP_FIXED/정확한 계수 표현 불가/필수 변수도 별도 기록. |
| 15. C0 대비 행 감소 | 26.892984% |
| 16. C0 대비 열 감소 | 6.059592% |
| 17. C0 대비 nnz 감소 | 35.553912% |
| 18. 계수 범위 | C0 [1.0006451962467139e-13, 400.0] → C2 [1.0006451962467139e-13, 400.0]; 모든 채택 계수/RHS는 저장 binary rational과 정확히 일치. |
| 19. 1,536 할당 동등성 | PASS; F0/F1/C0/C1/C2의 feasibility, objective, 정수 경로와 모든 원본 P/Q/SOC/grid 행을 비교. |
| 20. 경로 전수·양방향 증명 | PASS; 작은 4종 그래프 11개 원본 경로와 compact 상태를 전수 비교. 평행 arc 에너지 fixture에는 binary selector 2개를 유지. 실제 현재 그래프 평행 arc 0개. |
| 21. fractional 삭제 증명 | PASS; C0 LP의 원본 arc LP 투영이 동일함을 증명하고 PR160 및 C2 삭제마다 분수점에 유효한 증명만 적용. |
| 22. adversarial 검사 | PASS; 14개. 분기/역방향/단말/이동 SOC/PCS 사분면/grid/비결정적 chain/fill/정수 전용 중복 반례 포함. |
| 23. 현재 검증 start | PASS; COMPACT_START_VALID=true, P/Q/SOC/모드/경로 물리값 변경 0. |
| 24. 최대 start residual | 1.3827730072080158e-09; FeasibilityTol=1e-8 유지. |
| 25. C0 root 완료 | False |
| 26. C1 root 완료 | False |
| 27. C2 root 완료 | True |
| 28. root Work/time | 아래 arm 표. C2 root LP Work는 로그의 반올림 값 452.05, root LP 시간 207.78초. C0/C1 root 미완료이며 미완료 Work를 matched progress 개선으로 해석하지 않는다. 첫 optimal-root callback은 전달되지 않아 null로 보존. |
| 29. node 수 | C0: 1.0 (root 이후 0.0) / C1: 1.0 (root 이후 0.0) / C2: 1.0 (root 이후 0.0) |
| 30. 유효 UB/LB/gap | 아래 표. native BestBd와 inherited full-domain LB는 별도 열로 표시. |
| 31. 메모리 | 아래 peak RSS/process commit 표. 메모리만으로 선택하지 않는다. |
| 32. SUPER_COMPACT_EXACT_SELECTED | True |
| 33. 정확한 commit / Draft PR | 실행 source 4c491cbb4427776d0ac095ef563c3908422522f8; evidence receipt 4c491cbb4427776d0ac095ef563c3908422522f8; Draft PR 작성 예정; 게시 후 최종 head는 PUBLICATION.json/최종 응답에 별도 기록. |
| 34. 선택 시 다음 lane | Lane A native C2가 우선. Lane B/C는 callback/원본 행 preimage 증명 후, Lane D는 original-arc F1, Lane E는 recourse 10배 개선 예측 이후. 이번 작업에서는 tournament 미실행. |

| arm | root 완료 | root LP s | root LP Work (로그) | native Runtime s | 전체 Work | nodes | raw BestBd | safe native LB | inherited LB | valid LB | valid UB | valid gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | False | None | None | 271.3949999809265 | 622.2463904292557 | 1.0 | 0.25295395759592587 | 0.2529539475959258 | 0.5687115725336208 | 0.5687115725336208 | 0.6694159238756877 | 0.15043614552672033 |
| C1 | False | None | None | 271.05400013923645 | 475.00657846686187 | 1.0 | 0.25295395759592587 | 0.2529539475959258 | 0.5687115725336208 | 0.5687115725336208 | 0.6694159238756877 | 0.15043614552672033 |
| C2 | True | 207.78 | 452.05 | 271.05800008773804 | 571.2450218620137 | 1.0 | 0.5687116104028936 | 0.5687116004028935 | 0.5687115725336208 | 0.5687116004028935 | 0.6694159238756877 | 0.15043610389449788 |

| arm | peak RSS GiB | process commit GiB | min free RAM GiB | 전체 arm s | 최초 native / independently valid incumbent s |
|---|---:|---:|---:|---:|---|
| C0 | 3.880928 | 4.648560 | 14.200691 | 277.014679 | 3.731010499992408 / 4.7517804999952205 |
| C1 | 3.422756 | 4.213959 | 12.564678 | 275.839105 | 2.9733830000041053 / 3.844725600007223 |
| C2 | 3.379848 | 4.217869 | 14.913757 | 275.654277 | 2.8214614000171423 / 3.6759528999973554 |

RSS/commit은 0.5초 간격의 동일 worker 순차 실행에서 관측한 최대치다. 모든 arm은 build 포함 300초 hard wall과 native TimeLimit=270초의 동일 설정으로 실행했다. 원본 검증 seed는 arm 시작 시점부터 유효한 incumbent로 별도 보유했으며 native 해가 검증 실패하면 유효 UB를 갱신하지 않았다. native 흐름의 정수 경로 복원은 유일하게 함의되는 algebraic flow 값만 허용했고 P/Q/SOC는 보정하지 않았다.

정적 고정점은 3라운드. 제거 행 증명: {'ELIMINATED_DEFINITION': 19737, 'CONSTANT_SAFE': 1, 'FIXED_BOUND_EQUALITY': 13224, 'SINGLETON_BOUND_IMPLIED': 1, 'EXACT_PROPORTIONAL_IMPLICATION': 17464}. 변수 제거: {'FIXED_CONSTANT': 12, 'FIXED_ZERO': 2410, 'DETERMINISTIC_FLOW': 192, 'DUPLICATE_AUXILIARY': 17127}. 독립 검증은 production deletion 함수를 호출하지 않고 C1 전체 행의 C2 preimage를 재구성했다.

Continuous 증가의 주원인은 원래 binary였던 207,928개 경로 arc를 continuous로 옮긴 것이다. 연결과 이동 에너지·비음수 flow bounds 때문에 비결정적 이동 flow는 유지했다. 192개 결정적 stay flow는 activity에 정확히 치환했으며 P/Q 연결 시간은 그대로다. 비단위 또는 dense 치환에서 계수 표현·bound 운반·nnz union/fill 비용이 안전하다고 증명되지 않으면 KEEP했다. 보수적 비용 proxy는 실제 성능 개선 증거와 구별한다.

채택한 크기 gate: binary 95.524982% 감소, C0 대비 행 26.892984%, nnz 35.553912%. 선택 판정 근거는 SUPERCOMPACT_SELECTION.json의 matched root/valid gap/node gates다. LP microcheck 및 tournament solve 호출은 0회.

이번 작업은 현재 4-MESS V42 M1의 scientific problem을 변경하지 않고, 이동경로의 integer 표현을 exact node-activity/flow formulation으로 재구성하고, 수학적으로 중복·고정·결정적임이 증명된 행과 변수만 제거한 exact reformulation이다.

PR160의 삭제 증명은 compact continuous relaxation에서도 다시 검증했으며, integer feasible set에서만 중복이지만 compact LP relaxation을 강화하는 행은 성능을 위해 유지했다.

Compact-specific continuous flow와 linking structure도 fixed-point exact presolve로 감사했으며, 증명되지 않은 행·변수·경로는 제거하지 않았다.

Binary 감소, row 감소, memory 감소만으로 성공을 선언하지 않았으며, root completion, valid global bound, node progress 및 valid MIP-gap의 실제 개선을 최종 선택 기준으로 사용했다.
