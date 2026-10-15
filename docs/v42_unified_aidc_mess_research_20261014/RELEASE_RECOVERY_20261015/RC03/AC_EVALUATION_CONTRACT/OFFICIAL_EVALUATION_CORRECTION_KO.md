# V42 공식 AC 평가 기준 정정

사용자의 최신 명시적 정정에 따라 공식 연구 평가 계약은 `SLOTTED_SETTLED_ORIGINAL_PR223_V1`이다.

- 공식 전체 평가: **15분 × 96슬롯**.
- 각 슬롯은 원본 `CommonClock.settle_slot` 이후 `measure_full_network`로 측정한다.
- 전체 버스·상 전압, 전체 선로·상 전류, 원본 및 추가 변압기의 전류·kVA를 원본 한계로 검증한다.
- 원본 11 SVR, 7 RegControl, AUTO, LDC, Tap 범위, Delay/TapDelay, 제어 이력은 바꾸지 않는다.
- 현재 D0 Case의 실제 AIDC C1 P/Q·최종 MESS 운전·Actual Trace SHA로 Fresh96을 새로 검증한다. PR223 또는 고정 PR223 M2 진단의 PASS를 현재 Case로 이전하지 않는다.

RC01/RC02의 ASOF Substep 진단은 당시 평가 입력에서 발생한 슬롯 내부 물리 시간 위반의 근거로 그대로 보존한다. 0.9203485~1.0836574 pu, E0~E3, E2/E3의 각 100개 위반 셀과 제어 이력을 지우거나 재분류하지 않는다. 다만 **이 진단의 FAIL을 공식 Canary/캠페인의 추가 필수 Gate로 사용하지 않는다.** 따라서 RC01/RC02의 ‘ASOF 위반 때문에 공식 Gate FAIL’이라는 운영 해석은 이 문서로 대체한다. 원본 Raw와 당시 보고서는 변경하지 않는다.

슬롯 정착 AC PASS는 슬롯 내부 모든 순간의 전압 안전을 보장하지 않는다. 연속 시간 안전성은 인증하지 않았으며, Substep 진단에서 관측된 한계를 별도로 보고한다. 이것은 원본 전압 한계의 완화가 아니라 승인된 측정 시점과 평가 범위의 복귀다.

16슬롯은 제한된 Canary이다. 16슬롯 PASS를 96슬롯 PASS로 표시하지 않는다. RC01의 고정 PR223 M2 진단 Case에서 기존 Fresh16 결과는 0.9683101~1.0436863 pu, 최대 선로·상 부하율 0.615970으로 PASS지만, 새 D0 A1→M1→A2→M2 또는 Full96 인증이 아니다.

기존 A1 P1 해, P1-only/P2 0회, Unknown 기본 배치, 연구용 PENDING Pre-site, 원본 MESS Beam–Joint MILP와 K48은 이 평가 기준 정정으로 변경하지 않는다. 후속 Native 예산·현재 Case FULL·Production 연결·Actual96/Fresh96·K48 포함성 등 별도 필수 조건은 유지한다.
