# May01 대비 May02 B3 지연 원인과 r028 보정

2026-10-18 실제 저장 결과를 비교했다. 비교 대상은 May01 B3 attempt002 A2와 May02 B3 attempt012 A2다.

| 측정 항목 | May01 | May02 |
|---|---:|---:|
| A2 총 Native 시간 | 950.909초, PASS | 5,400.089초, 한도 종료 |
| 주 P1 LP | 2회 / 24.539초 | 19회 / 4,102.466초 |
| 전체 Local Pricing | 259회 / 16.477초 | 2,957회 / 938.258초 |
| 첫 P1에서 찾은 개선 블록 | 18개 | 123개 |
| 첫 activation에 실제 추가 | 18개 | 64개 |
| 마지막 완료 Pricing의 개선 블록 | 0개, closure | 103개, 미완료 |
| P1 solver | 원본 Barrier, Method=2 | 강제 Dual Simplex, Method=1 |
| NumericFocus / Presolve / Aggregate | 0 / auto / 기본값 | 3 / 1 / 0 |
| job 수 / class 수 | 1,499 / 117 | 1,386 / 138 |

May02는 job이 더 많은 날이 아니다. P1에서 추가해야 할 개선 방향이 훨씬 많이 남았고 모델이 반복 확장됐다. 동시에 수치 안정화 어댑터가 Phase I의 robust simplex 설정을 주 P1과 모든 Pricing에도 적용했다. May01과 같은 원본 Barrier를 쓰지 않았다. 이것이 앞선 r027의 시작점·basis·64개 제한 보정만으로 충분하지 않았던 추가 구현상 원인이다. 두 날짜의 입력과 활성 모델이 다르므로 위 시간 차이 전부를 solver 변경 하나의 효과로 단정하지 않는다.

r028은 다음을 분리한다.

- Phase I: 기존 수치 안정화와 Native1500초 제한 유지.
- 정상 P1 및 첫 Local Pricing: 원본 solver 정책 유지. Method=2, NumericFocus=0, 자동 Presolve를 Phase I 값으로 덮어쓰지 않음.
- 같은 행렬·bounds·senses·RHS·types의 Local Pricing에 유효 basis가 있으면 그 경우에만 Dual Simplex로 재최적화.
- 원본 행·dual·이전 가능해 dominance 검산이 실패한 경우에만 한 번의 robust repair. 모든 Native는 원래 A5400 원장에 합산.
- r027의 검산한 가능해 전달, 검증된 개선 블록 전체 activation, 원본 Full Pricing 및 독립 LB/Gap/물리 검산 유지.

다른 오류 수정도 승계했다. May03~05 B1의 이전 keyword-only 기본값 유실은 올바른 `m1=None` 호출로 복구하며 완료 Planning이 없어 A1부터 실행한다. May06은 기존 P1 closure와 정수 결정, Native12.264초를 보존하고 정확한 고정정수/연속해 복원 뒤 전체 검산을 수행한다. 단순 클리핑과 허용오차 확대는 하지 않는다.

사용자가 확정한 A2 선택 행의 완화 폭은 ±0.005 pu, 즉 0.945~1.055 pu다. 발동 조건은 유지하며 M2와 Actual/Fresh는 0.95~1.05 pu다.

검증은 회귀 **298개 PASS**, 실제 May06 693,549행·22,616열의 Native0 입력·행렬·typed fingerprint·P1 인증·기존 Native 승계 검산이다. r028 Source SHA는 `2f703e81672b020022d2d8126ba42f52d6c0040bdf58b3f85199251d2eac7292`다.

현재 실행 중인 May07 B1 Actual/Fresh를 보존하고, r028 작업이 자연 종료 경계에서 인계하도록 구성했다. r027은 실행 전 대기 상태에서 대체됐으며 기존 원본을 보존했다. **수정 코드와 검증은 완료됐지만, r028의 실제 속도 개선·May02 최종 PASS·May06 실제 연속 복원 및 Actual/Fresh PASS는 아직 측정 전이다.** 결과를 확인하기 전 성공으로 보고하지 않는다.
