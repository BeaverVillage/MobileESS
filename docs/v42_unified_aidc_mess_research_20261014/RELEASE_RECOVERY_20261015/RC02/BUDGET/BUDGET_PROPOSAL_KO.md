# 후속 P1-only Native 예산 제안 — 미승인

기존 318.681초와 별도 A1 P1 50.622초 원장은 읽기 전용이다. A1의 180초 중 잔여분은 다른 단계의 승인 예산이 아니다. A1 성공 해를 그대로 재사용한다.

| 단계 | 제안 상한(초) | 포함 범위 |
|---|---:|---|
| M1 | 180 | 원본 Beam–Joint UB 및 해당 단계 보수적 HiGHS 비용 |
| A2 | 120 | 원본 P1 한 목적함수 |
| M2 | 180 | 원본 Beam–Joint UB 및 해당 단계 보수적 HiGHS 비용 |
| K48 M2 | 180 | 현재 최종 M2 Case의 포함성 증명 후 Global LB |
| Solver 합계 | 660 | P2 0회 |
| Return reserve / overshoot buffer | 30 / 60 | 새 예산에 분리 |
| 제안 총 상한 | **750** | 아직 승인되지 않음 |

M1 자체의 Global LB도 별도로 요구하면 K48 M1 180초를 추가하여 총 930초를 제안한다. M1 Original FULL 해를 A2에 전달하는 것과 최종 M2 Case의 Global LB 인증은 구분한다.

Planning만 먼저 승인하는 최소 단위는 M1→A2→M2 480초 + Reserve/Buffer 90초 = **570초**다. K48 M2까지 포함하는 제안은 750초, K48 M1도 포함하면 930초다. 세 가지 모두 미승인이며, Planning-only 경로에서는 K48 LB를 null로 남긴다.

현재 D0 M1 원본 Case 조립·엄밀 변환 검증은 약 1,481초의 Native0 Wall이 들었다. 그 결과를 동일 Source/Case에서 캐시로 보존하므로 중복 조립은 피한다. M2와 다른 날짜는 입력이 달라 이 시간을 그대로 재사용하거나 성공 시간을 보장하지 않는다. Native 상한과 모델 조립·Actual·Fresh 전체 Wall은 별도다.

위 상한은 제한된 첫 실행을 위한 제안이며 현재 Case가 상한 안에 실행 가능해/최적성 목표를 달성한다고 보장하지 않는다. Solver 오류·중단·시간초과도 원장에 청구하며, 해가 없거나 FULL 검증에 실패하면 후속 단계를 실행하지 않는다. 현재 K48 포함성 packet은 아직 미인증이므로 예산 승인이 곧 K48 실행 허가는 아니다.

May01 후속 Planning은 별도 승인 후 먼저 수행할 수 있다. 그 결과로 현재 D0 Case의 16슬롯 Canary, Actual96와 공식 `settle_slot → measure_full_network` Fresh96을 새로 검증한다. ASOF Substep 진단 FAIL만으로 공식 평가를 차단하지 않는다.

31일 총액은 May01 결과와 전체 Wall 계측 후 확정해야 한다. 동일 상한을 단순 확장한 참고치는 Solver 24,060초 + Return 30초 + Overshoot 1,860초 = 25,950초다. 이것은 승인이나 실행 계획 확정이 아니다. 자동 캠페인은 모든 필수 Gate와 별도 캠페인 예산 승인 전 HOLD다.
