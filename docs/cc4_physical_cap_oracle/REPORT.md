# CC4 physical-cap oracle coverage audit

감사일: 2026-09-23. 동결 V41R4 May evaluation의 동일 모집단에서 **physical-cap oracle coverage는 85.9418558343%**, 따라서 **PHYSICAL_85PCT_ATTAINABLE = TRUE**이다. 이는 cap만을 기준으로 한 평가 coverage의 달성 가능성이다. 특정 학습법으로 85%가 확보되거나 모든 운영 제약하에서 실행 가능함을 뜻하지 않는다.

```ini
N = 2511
count(Y_k <= C_phys_k) = 2158
count(Y_k > C_phys_k) = 353
physical_cap_oracle_coverage = 0.8594185583432895
TARGET_COVERAGE = 0.85
PHYSICAL_85PCT_ATTAINABLE = TRUE
```

| 지표 | Covered / N | Coverage 또는 gap |
| --- | ---: | ---: |
| Current uncapped coverage | 2084 / 2511 | 82.9948227798% |
| Current actionable coverage | 2045 / 2511 | 81.4416567105% |
| Physical-cap oracle coverage | 2158 / 2511 | 85.9418558343% |
| Gap: physical oracle − uncapped | 74 / 2511 | +2.9470330546 percentage points |
| Gap: physical oracle − actionable | 113 / 2511 | +4.5001991239 percentage points |

85% 이상에는 `ceil(2511 × 0.85) = 2135`개 covered window가 필요하다. 현재 actionable 대비 **최소 90개 순증**이 필요하다. Cap 이하이지만 현재 actionable miss인 window는 113개이며, 85% 목표는 이 중 90개를 회복하고 기존 covered window를 유지하면 충족한다. Oracle은 목표보다 0.9418558343 percentage points 높고, 필요한 정수 covered count보다 23개 많다.

## 동일 May population과 target

- 최종 authority: `CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/FINAL_RESULT_INDEX.json`의 2025-05-01–2025-05-31, B0/B1/B2/B3 총 124 policy-day.
- Fixed UTC+10 modeled day마다 k=0..80, 15분 stride, 4시간 `[start, end)` window 81개. 일별 첫 start는 00:00, 마지막 start는 20:00. 자정을 넘는 window를 추가하지 않았다.
- 네 정책의 Y, raw prediction, actionable prediction, physical cap, historical cap 및 window 축이 전부 정확히 동일함을 확인한 뒤 day-window를 한 번씩만 계산했다. 31 × 81 = 2511이며 policy를 네 번 합산하지 않았다.
- Y는 해당 window에 **원래 submit time이 들어가는 Job들의 전체 lifetime GPU service**, 즉 `sum(gpus_requested × (observed end − observed start)/3600)`이다. 기존 CC4 target을 그대로 유지했다. 이 값은 window 내 실제 GPU 점유 적분이나 실제 queue delay가 아니다.
- Coverage는 저장값 그대로 `Y <= bound`로 계산했다. Equality는 covered이고 반올림·epsilon을 적용하지 않았다.

## Authority 복원과 cap 검증

Y는 FINAL_RESULT_INDEX가 가리키는 최종 Actual 경로의 대응 `common_inputs/{day}/{policy}/H4_SCORE.json.realized_H4_GPUh`에서 직접 읽었다. 기존 요약 CSV를 입력으로 사용하지 않았다.

각 policy-day의 `dayahead/ml/ML_SNAPSHOT.json.future_service_capacity_gpu` 96 × eligible sites 행렬을 읽어 다음 식으로 매 window의 cap을 새로 복원했다.

```text
C_phys[k] = 0.25 × sum(capacity_gpu[t,s], t=k..k+15, s in future_service_eligible_sites)
```

이는 검증된 source `dayahead/v41/reserve.py`의 `windows`, `cap_reserve`, `validate_snapshot`, `add_constraints`가 사용하는 정의다. 선택된 `PLANNING_RESULT.json.ML_snapshot_SHA`와 snapshot SHA가 일치하고, `H4_window_persistence`에 기록된 optimizer table의 SHA도 일치한다. 복원 cap을 snapshot `H4_CAP_PHYS`, prediction table `PHYS_CAP_GPUh`, 실제 optimization의 `H4_OPTIMIZER_WINDOWS.parquet.PHYS_CAP_GPUh`와 전부 정확히 대조했다.

**3120 GPU·h를 상수로 입력하지 않았다.** 결과적으로 이 May authority에서는 모든 eligible site의 slot별 capacity 합이 780 GPU이고 모든 window의 복원값이 3120 GPU·h로 같았다. 이 값은 알려진 Job 부하를 차감한 available headroom과는 구별된다.

Raw/actionable 역시 snapshot과 prediction/optimizer table을 대조했다. 모든 window에서 다음 식이 정확히 성립한다.

```text
actionable[k] = min(raw[k], historical_cap[k], physical_cap[k])
```

## Prediction clipping과 realized 초과의 구분

| | Y > physical cap | Y <= physical cap | 합계 |
| --- | ---: | ---: | ---: |
| Physical prediction cap binds | 131 | 386 | 517 |
| Physical prediction cap does not bind | 222 | 1772 | 1994 |
| 합계 | **353** | **2158** | **2511** |

`physical cap binds`는 `physical == actionable AND actionable < raw`이다. 따라서 기존 **517/2511**은 prediction clipping 수이며, **realized Y > C_phys는 353/2511**이다. Prediction이 physical cap에 잘리지 않은 222개 window에서도 realized target은 physical cap을 초과했다.

## Historical-cap oracle — 별도 계산

각 window에 대응하는 snapshot `H4_CAP_HIST` 및 prediction/optimizer `HIST_CAP_GPUh`를 사용했다. Historical cap은 일별 authority 값이며 May 범위는 11022.20444444445–12054.431111111111 GPU·h, 고유값은 19개다. Historical pool을 재학습하거나 cap quantile을 다시 조정하지 않았다.

```ini
N = 2511
count(Y_k <= C_hist_k) = 2418
count(Y_k > C_hist_k) = 93
historical_cap_oracle_coverage = 0.9629629629629629
HISTORICAL_85PCT_ATTAINABLE = TRUE
```

Historical-only oracle ceiling은 **96.2962962963%**다. 현재 historical prediction cap binding은 0개지만, realized historical-cap 초과는 93개다. 이 historical ceiling을 physical ceiling과 합치지 않았다. 이번 authority에서는 모든 historical cap이 physical cap보다 높으므로 두 cap을 동시에 적용한 oracle은 physical oracle과 같다.

## 검증과 산출물

- 최종 accepted joint decision SHA, Actual READY의 decision SHA 연결, 선택된 plan의 ML snapshot SHA, optimizer persistence SHA를 확인했다.
- 124 policy-day 모두에서 slot capacity → physical cap 복원, snapshot/prediction/optimizer 값 및 policy 간 동일성을 확인했다.
- 소비한 모든 authority 파일은 기존 archive extraction manifest의 SHA와 일치했고, 계산 전후 SHA도 같았다. 자세한 목록은 `SOURCE_MANIFEST.json`에 있다.
- 저장된 contributor 개별 행이 있는 30일에서는 Y를 별도로 재계산했으며 최대 오차는 0이다. **2025-05-21은 contributor 표가 없어 최종 H4_SCORE의 81개 Y를 사용했다.** 네 정책 간 값 일치를 확인했고, 해당 날짜를 제외하거나 다른 값으로 채우지 않았다.
- 두 CSV를 다시 읽어 모든 값의 정확한 round-trip을 확인했다. 검증 결과는 `VALIDATION.json`이다.
- **Fitting, quantile level, calibration factor, feature, threshold 변경 없음.** 학습·추론·최적화·Actual replay 호출 없음. CC4-v2 개선안 결정 및 실행은 이번 audit에 포함하지 않았다.

산출물:

- `CC4_PHYSICAL_CAP_EXCEEDANCE_WINDOWS.csv`: 353행. 요청한 `date, window_start, Y_k_GPUh, C_phys_k_GPUh, exceedance_GPUh`. Window start는 fixed UTC+10 offset을 포함한다. Exceedance는 `Y_k − C_phys_k`이다.
- `CC4_ALL_MAY_WINDOWS.csv`: 2511개 전체 window의 Y, 두 cap, 기존 두 prediction, coverage 및 binding flag.
- `SUMMARY.json`: 정확한 숫자와 boolean 판정.
- `SOURCE_MANIFEST.json`, `VALIDATION.json`, `audit.py`: 출처·검증·재현 계산.
