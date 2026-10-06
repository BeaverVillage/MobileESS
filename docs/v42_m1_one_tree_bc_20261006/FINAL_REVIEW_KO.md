# M1 one-tree exact grid branch-and-cut 최종 검토

최종 상태: **ONE_TREE_EXACT_BC_REJECTED**. ONE_TREE_BC_SELECTED=false.
고정 source commit: `69ae9406e5fa3c5569cc08d8d723ad0cbbcea445`; parent PR158 `a6045405b254703285a9d8469105746e3fc1b904`.
합산 연속 wall: 560.890초 (상한600초), sequential, native optimize 각1회.

| 항목 | A original monolithic | B one-tree |
|---|---|---|
| 1. Exactness | 12개 / 1,536 정수 조합: 49 feasible·1,487 infeasible 일치; fractional-node·sense·재거부 PASS | 회귀63개 PASS |
| 2. 원래 모델 | 886,017 rows / 316,743 cols / 208,312 binary / 8,447,855 nnz | 동일 변수·objective·domain |
| 3. 초기 모델 | 전체 모델 | 287,552 rows / 316,743 cols / 208,312 binary / 2,784,047 nnz |
| 4. Deferred rows | 0 | 598,465; auxiliary81,216 유지 |
| 5. Callback 횟수 | 20447 | 3235 |
| 6. MIPNODE 고유 추가 행 | 0 | 0 |
| 7. MIPSOL 고유 추가 행 | 0 | 212512 |
| 8. Family 추가 행 | — | {"voltage_upper": 23, "line_thermal_face": 212249, "voltage_lower": 216, "transformer_kVA": 24} |
| 9. 최종 고유 원래 행 | 886017 | 500064 |
| 10. 거부된 invalid integer 후보 | 0 | 1 |
| 11. 첫 native / 검증 완료 incumbent 초 | 2.822518300 / 3.305569000 | 3.588924400 / 4.612589500 |
| 12–13. Valid UB 시작 → 종료 | 0.669415924 → 0.669415924 | 0.669415924 → 0.669415924 |
| 14–15. Valid global LB 시작 → 종료 | 0.568711573 → 0.568711573 | 0.568711573 → 0.568711573 |
| 16–17. Valid gap 시작 → 종료 | 15.043615% → 15.043615% | 15.043615% → 15.043615% |
| 18. Gap 감소 / wall초 | 0.000000000 | 0.000000000 |
| 19. Node / LP iter / work | 1.0 / 170295.0 / 523.1789555187033 | 1.0 / 236461.0 / 468.0294115083269 |
| 20. Build / native / wall초 | 1.634 / 273.569 / 278.132 | 1.289 / 271.840 / 276.499 |
| 21. RSS / process commit / min RAM | 3.035 GiB / 4.172 GiB / 15.857 GiB | 8.126 GiB / 11.303 GiB / 10.599 GiB |
| 22. Selected | — | False |
| 23. Benchmark source commit | 69ae9406e5fa3c5569cc08d8d723ad0cbbcea445 | Draft PR는 별도 PR_RECEIPT.json 및 최종 응답에 기록 |

실제 MIPNODE separation=0,
MIPSOL exhaustive separation=2.
고유 registry 중복 없음; 중복 등록 회피=0,
사용자 허용 lazy 재거부 cbLazy 재제출=0,
usercut→lazy 승격=0.
각 MIPSOL의 모든598,465행 검사와 모든 위반 행 제출을 ledger로 독립 감사했다.
최종 독립 point 감사는 중복 제거 전의 전체 grid673,920행까지 추가로 검사했다.
Full-scale에서는 optimal fractional MIPNODE separation이 관측되지 않아
그 가속 정책의 실제 성능은 측정되지 않았다. MIPNODE fixture는 별도로 PASS했다.
`final_active_original_rows`는 초기 행과 고유 제출 행 합계이며,
Gurobi 내부 cut-pool 잔존 행 수를 주장하지 않는다. 애플리케이션 cut deletion은 없다.
원래 full-grid/비-grid/정수 route/SOC/PCS/mode/objective 최종 검증 PASS.

Valid UB는 검증 통과 native point 또는 동일하게 검증된 기존 원래 시작점만 사용했다.
LB는 기존 원래 full-domain certificate floor와 본 원래 변수-domain native tree LB의
최댓값이며 RMP/restricted-column LB는 읽거나 사용하지 않았다. 작은1e-8 하향 조정은
기존 native numerical authority이며 새로운 exact-rational native bound 증명이라고
주장하지 않는다. 시작 incumbent는 비교 시작 시점0초에 이미 유효하므로,
표의 first native valid 시간은 실제 native callback 후보의 감사 완료 시각이다.
RSS/commit/RAM은1초 관찰치의 극값이며 연속 native 메모리 최대치라고 주장하지 않는다.
Native status A=11, B=11; gap<=.005 수렴을 달성했다고
주장하지 않는다. Errors A=[], B=[].
Arm JSON의 `raw_native_bound` 필드는 실제로1e-8 하향 safety bound이다.
원시 native bound는 보존된 로그에서 A≈0.2529539575959, B=0으로 확인된다.
필드 의미 교정은 M1_ONE_TREE_BC_FIELD_SCOPE.json에 기록했으며 raw 결과는 보존했다.

선정은 사전 등록된 valid-gap-progress 기준만 사용했다. 양쪽 감소가0이면 false이고,
메모리·행 개수·cut 개수·invalid objective만으로 성공을 판단하지 않았다.
추가 policy 비교, production3600초 canary, P2/M2/B2/B3는 실행하지 않고 STOP했다.
PR157/PR158 기존 evidence와 scientific source를 변경하지 않았다.

본 방법은 원래 V42 M1 grid constraints 자체를 callback에서 동적으로 추가하는 exact branch-and-cut이며, heuristic feasible-set restriction이 아니다.

모든 integer incumbent는 598,465개 deferred grid-security rows에 대한 exhaustive separation을 통과한 경우에만 valid UB로 인정했다.

MIPNODE critical/multi-row selection은 계산 가속에만 사용하며, MIPSOL exhaustive separation과 최종 scientific feasibility를 대체하지 않았다.

PR158의 outer-loop row generation과 달리 한 번의 native B&B tree를 유지하며 grid rows를 추가하는 구조를 시험했다.
