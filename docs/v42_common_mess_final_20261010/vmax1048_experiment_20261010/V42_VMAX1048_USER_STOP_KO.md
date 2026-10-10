# V42 1.048 pu 진단 — 사용자 지시로 중지

2026-10-10 사용자가 연구 방향을 D-STATCOM 설비 도입으로 변경하고 1.048 실험 중지를 명시했습니다. 소유 PID·생성 시각·명령·작업 디렉터리를 검증한 뒤 해당 worker만 종료했습니다. 기존 원본 Canary, Source Epoch 및 완료 Native ledger는 보존했습니다.

| 항목 | 보존 상태 |
|---|---|
| Attempt | B2_MAY01_VMAX1048_CANARY |
| 실행 Source commit | 16db6465231699aa9f4a9551cdafc59347d45dce |
| 실행 Source SHA | f792f2d327445ebe29cb1f95de30e40f096cfce853071f15637578bd1ec6db4d |
| 정책 | V42_PLANNING_VMAX_1048_DIAGNOSTIC_V1 |
| 종료 상태 | STOPPED_BY_USER |
| 실제 완료 Native 호출 | 3회 |
| 완료 호출의 측정 Native Runtime | 213.47500038146973초 |
| 중단 호출의 최종 Native Runtime | UNKNOWN |
| 전체 최종 Native Runtime | UNKNOWN |
| 마지막 progress의 FULL verified UB | 0.5464151451386842 |
| 최종 계획 동결·Actual/Fresh | NOT_RUN |
| Full AC Physical PASS | FALSE — 미검증 |

마지막 progress의 UB는 최종 채택·Actual 검증 결과가 아닙니다. callback에서 관찰한 진행 중 시간은 중단 호출의 최종 측정값으로 바꾸지 않았습니다. 완료 213.475초를 실험 전체 시간이라고 보고하지 않습니다. 기존 NATIVE_RUNTIME_LEDGER.json은 수정하지 않았고, USER_STOP_RECEIPT.json과 종료 직전 사본을 별도로 저장했습니다. 이 Attempt를 다시 실행하거나 Native 시간을 초기화하지 않습니다.

실제 저장 모델의 독립 감사에서 FULL 계수·목적함수·변수 영역·상한 이외 RHS는 원본과 일치했고, 전압 상한 RHS 37,056개만 변경됐습니다. 기존 최종점은 새 상한을 474개 셀에서 위반해 새 초기해로 승인하지 않았습니다. 이 모델 감사와 실제 세 번의 완료 최적화 호출은 보존된 진단 증거이며, Actual 전압 개선을 입증하지 않습니다.

새 D-STATCOM 시나리오는 별도 branch/source epoch에서 원래 Planning 0.950~1.050 pu를 사용합니다. 이 중지된 강화 상한 정책은 새 시나리오에 적용하지 않습니다. 기존 May01 1.050 pu 결과와 19개 위반·제어·P/Q 원인 감사는 원본 증거로 유지합니다.

기설 전압제어 인프라를 가정하는 새 연구에서는 설비 투자비·설치비 및 별도 경제성 분석을 범위에서 제외한다는 후속 사용자 지시를 적용합니다.
