# V33XR2 — E1 계획 전압 상한 1.0495 pu 개발 실험

주 분류: **V33XR2_E1_VMAX10495_FRESH_VOLTAGE_FAIL**

Stage-1과 E1 Stage-2의 계획 상한만 1.0495 pu로 낮췄다. Fresh 물리 상한은 1.05 pu로 유지했으며 Fresh는 후보 궤적 동결 후 검증에만 사용했다.

## B1

- Stage-1 feasible: True
- Stage-2 feasible: True
- DA authorized: 179.804069079776 node-h
- Executed: 127.858237841567 node-h
- Execution ratio: 71.109757691211%
- Original E1 gain retained: 99.999999271881%
- Fresh Vmax/Vmin: 1.050210480163 / 0.976945969506 pu
- Fresh voltage/current/transformer violations: 4 / 0 / 0
- Fresh rho B1/B0/delta: 0.614532316236 / 0.614982325862 / -0.000450009626
- Mass error: 8.527e-14 node-h
- Future Actual reads: 0

계획 Vmax는 Stage-1에서 1.048685119071 pu, Stage-2에서 1.048701524249 pu였다. 둘 다 1.0495 pu보다 낮아 새 상한은 후보를 구조적으로 바꾸는 활성 제약이 되지 못했다.

## 해석

단일 1.0495 pu tightening은 B1 fast gate를 통과하지 못했다. 다음 최소 조치는 Stage-1 전압 보정 recourse capability 구현이다.

이 결과는 Apr-04 단일 개발 screening이며 1.0495 pu를 최종 margin으로 확정하지 않는다.

타깃 pytest 결과는 23 passed, 0 failed이고 내부 실행 계약 점검은 18 passed, 0 failed다. 전체 역사 회귀는 실행하지 않았다.
