# Planning 1.048 pu 진단 실험

`V42_PLANNING_VMAX_1048_DIAGNOSTIC_V1`은 기존 과학적 모델과 다른 강화된 Planning feasible set이다. B2 M과 B3 M1/M2는 같은 `v42_common_mess.planning_policy.build_case` 인터페이스를 사용한다. 정상 실행의 기본 정책, B3 A1/A2, Actual/Fresh의 0.950–1.050 pu 기준은 유지한다. 새 정책은 명시적인 Context와 진단 Source Manifest로만 활성화된다.

모델은 제곱전압을 사용한다. 정확한 십진수 제곱을 IEEE double로 변환해 Planning 하한 0.902500, 상한 1.098304를 적용한다. FULL 생성 시 원래 Stage 전압 Authority를 M단계에만 강화하고, 그 FULL에서 기존 Compact/Presolve/C3A를 다시 생성한다. 원본 수치 도메인·목적함수·이동·PCS·SOC·전류·변압기·제어 설정을 유지한다. Stage Case/Model/Domain SHA는 새 모델에서 다시 계산한다.

실제 May01 Builder는 기존 FULL 배열과 독립 비교한다. 37,056개 전압 상한 행의 RHS만 변경돼야 하며 전체 CSR 계수, 나머지 RHS, 변수·행 Metadata·Bounds·Types·목적함수는 바이트가 같아야 한다. Native Gurobi의 계수/RHS Readback과 원본 FULL/Compact/C3A Transport를 검증한다. 기존 May01 strict 점은 강화된 FULL에서 독립 재검증하며 신규 MIP Start로 전달하지 않는다. 이전 Native0 저장 FULL 감사에서 이 점은 강화된 상한 474개를 위반했다. 이 감사는 실제 재최적화를 대체하지 않는다.

새 Attempt는 `B2_MAY01_VMAX1048_CANARY`이며 공통 U4 엔진과 1,800초 누적 실측 Native 상한을 사용한다. L1–L4/DW/CG 추가 LB Solver는 실행하지 않는다. 전역 Gap은 독립 인증이 없으면 UNKNOWN이다. 모델 생성과 Actual/Fresh Wall Time은 Native 최적화 예산과 별도로 보존한다. NO_VALID_FEASIBLE/TIME_LIMIT를 유효한 원본 FULL 불가능성 증명 없이 INFEASIBLE이라고 부르지 않는다.

기존 May03 Canary는 종료하지 않는다. 별도 진단 Permit은 보존된 Epoch 2 May03 Canary의 Source/Manifest·날짜·Arm·PID 생성 시각·명령 및 자체 Slot 3 Lease를 확인한다. 모든 실제 Native 진입에서 원본 Scope·DateBudget·Threads=1과 새 Source/정책 Admission을 검증한다. 진단은 공식 31일 완료 집계에 포함하지 않으며 Production 전환을 승인하지 않는다.

Actual은 원본 Fixed Replay/Fresh Body를 사용하며 재최적화·P/Q Repair를 하지 않는다. 관찰 전용 Hook이 96슬롯의 7개 RegControl 설정 SHA·활성·탭·완료·반복 횟수와 4개 ON capacitor를 별도 파일에 기록한다. 원래 Source·전압/전류/탭 배열은 수정하지 않는다. 위반 한 건 이상이면 엄격한 Actual AC 검증 FAIL이다.

기존 May01 결과는 Source `1e691988`에서 생성했고 신규 진단은 route_witness 결함 수정 후 Source `982c108e`의 후손이다. 같은 최종 알고리즘 버전과 과학적 자원을 사용하며 모델 조건은 상한만 바뀌지만, 탐색 경로와 실측 Runtime도 기록한다. 기존/신규 결과표를 상한 변경의 순수 인과 추정이라고 주장하지 않는다. 관측 후 선택한 May01 진단이므로 독립 Holdout 성능도 아니다.

1.048에서 위반이 남으면 그대로 FAIL과 Trade-off를 보고하며 더 낮은 상한을 자동 선택하지 않는다. May01 실제 AC 성공 후 B3 M1/M2의 실제 Canary와 추가 날짜·비교 정책을 검증해야 31일 전환을 고려할 수 있다. 현재 진단 Manifest는 전체 전환을 명시적으로 금지한다.
