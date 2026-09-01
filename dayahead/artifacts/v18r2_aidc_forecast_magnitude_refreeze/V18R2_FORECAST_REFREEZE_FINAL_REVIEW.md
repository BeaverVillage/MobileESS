# V18R2 AIDC Day-Ahead Flexible-Workload Magnitude Re-freeze

RESULT CLASSIFICATION: `B. V18R2_PASS_WITH_CAPACITY_TIMELINE_PARTIAL`

## READY

- `FORECAST_REFREEZE_READY = true`
- `FACILITY_COMPOSITION_READY = true`
- `NEW_LOCKED_SCIENCE_RUN_READY = false`

## 1. 기존 1,244 GPU-h 계보

기존 7일 `1,244.068855 GPU-h`는 frozen RC-MQT의 slotwise Q50 합 `4976.275421 GPU-h`에 `beta_AIDC=0.25`를 다시 적용해 만들어졌다. factor-4와 slot-hour 이중 적용은 없었고, 75% mechanical beta contraction과 slotwise-Q50/statistical underforecast, modelable filtering이 주요 원인이다.

## 2. Training 분포와 Q50 감사

- submitted flexible service target: `614322.972500 GPU-h`
- mean/day: `2730.324322`
- median/day: `891.285833`
- zero-arrival slot fraction: `0.892037`
- marginal slot median 합 / daily median: `0.00028049`
- H6: `CONTRIBUTOR`

## 3. Training-only model selection

Training-only 3-fold blocked CV에서 `CANDIDATE_B`을 선택했다. selected daily WAPE는 `0.914408`, old lineage-equivalent WAPE는 `0.999981`, Q50 aggregate mass ratio는 `0.264995`다. Heavy-tail 때문에 calibration 한계가 남으며 April을 이용한 재보정은 하지 않았다.

## 4. April observed diagnostic

| Day | Old GPU-h | New Q50 GPU-h | New/Old | Training percentile |
|---|---:|---:|---:|---:|
| 2025-04-02 | 179.947 | 2259.396 | 12.556 | 0.707 |
| 2025-04-03 | 183.769 | 1554.572 | 8.459 | 0.627 |
| 2025-04-12 | 166.751 | 1113.415 | 6.677 | 0.538 |
| 2025-04-13 | 155.315 | 349.946 | 2.253 | 0.387 |
| 2025-04-15 | 177.378 | 612.036 | 3.450 | 0.436 |
| 2025-04-22 | 183.058 | 612.036 | 3.343 | 0.436 |
| 2025-04-23 | 197.851 | 2259.396 | 11.420 | 0.707 |

새 April diagnostic Q50 합은 `8760.796667 GPU-h`이며, April target은 모델 동결 뒤 진단용으로만 읽었다.

## 5. Power tier

| Tier | GPU-h | IT energy kWh |
|---|---:|---:|
| FULL_1 | 1819.058 | 1041.170 |
| FULL_2 | 309.684 | 172.031 |
| FULL_4 | 322.481 | 168.807 |
| FULL_8 | 287.741 | 145.774 |
| FULL_16 | 177.001 | 86.972 |
| PARTIAL | 5844.833 | 2838.462 |

Tier mass identity 오차는 `3.638e-12 GPU-h`, partial CPU attribution은 `null`이다.

## 6. Scheduler와 시설 분해

새 flexible IT energy는 `4453.216570 kWh`, whole-facility share는 `3.374056%`다. 문헌 20~25%는 `LITERATURE_CONTEXT_ONLY`, `CALIBRATION=NO`다.

Reference scheduler는 shedding 없이 `8760.796667 GPU-h`를 보존했고 terminal backlog는 `0.000e+00 GPU-h`다. 시설 최소 locked residual은 `9.234237 kW`, 최대 보존오차는 `2.842e-14 kW`다.

## 7. 방화벽

B0-B3, OpenDSS, grid science run은 실행하지 않았다. untouched locked test가 없으므로 새 science run은 승인되지 않는다.
