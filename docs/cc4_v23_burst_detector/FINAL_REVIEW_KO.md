# CC4-v2.3 최종 검토

**C0 유지. 높은 detector recall은 달성했지만 낮은 precision, 부족한 final burst coverage와 높은 reserve 때문에 challenger 채택은 지지되지 않는다.** C0 유지 자체도 기존 C0가 모든 operational gate를 통과한다는 뜻은 아니다.

May에서 C1 recall은 100%지만 744시간 중 715시간(96.10%)을 gate 안으로 분류하고 FPR은 95.70%, precision은 9.65%다. C1 final burst coverage는 17.39%, requirement ratio는 2.174다. C2는 recall 94.20%, final burst coverage 46.38%, ratio 3.164이며 pinball이 C0보다 6.72% 악화된다. 두 후보 모두 final burst 60%와 ratio <2를 만족하지 못한다. Gate 밖 예측의 동일성은 지켰지만 C1의 May gate가 사실상 대부분의 시간을 포함하므로 효율적인 burst 선별을 달성했다고 주장하지 않는다.

선택된 balanced detector의 May PR-AUC는 0.1449로 기존 detector의 0.1569보다 점추정이 낮다. 여기서 PR-AUC는 trapezoid 면적이 아니라 **noninterpolated average precision(AP)**다. Recall 상승을 detector의 전반적인 ranking 성능 향상으로 해석할 수 없다. 낮은 threshold로 넓어진 gate와 함께 봐야 한다.

## 선택과 feature ablation

등록 2026-09-26 15:58:15 UTC → DEV/CAL 선택 freeze 16:00:24 UTC → evaluation 완료 16:04:16 UTC 순서를 기록했다. C1은 D1_BASE71_BALANCED/gate 0.0025, C2는 같은 detector/gate 0.01/conditional-tail Q50로 연구 candidate만 고정했다. DEV/CAL 모든 hard gate를 충족한 challenger는 없었다. 신규 163-feature D2도 같은 classifier 설정으로 학습·평가했고 선택되지 않았다.

동일 gate 0.0025에서 D2의 DEV/CAL recall은 39.76%/52.63%로 D1의 60.24%/89.47%보다 낮았다. May D2는 recall 94.20%, precision 10.48%, FPR 82.22%, AP 0.1534지만 이를 보고 후보를 재선택하지 않았다. Feature 추가의 이점은 본 프로토콜에서 입증되지 않았다.

최근 workload의 관측 support도 제한된다. May 31개 issue 중 28개는 직전 6시간에 완전히 mature한 workload hour가 하나도 없었고, 6/12/24시간 평균 mature fraction은 각각 1.61%/1.61%/13.31%였다. [FEATURE_SUPPORT.csv](FEATURE_SUPPORT.csv)에 구간별 support를 저장했다. Missing은 zero workload와 구분했다. 이 사실만으로 성능 저하의 원인이 확정된다고 주장하지 않는다.

선택은 evaluation 전에 **C0**로 고정했다. May는 이미 노출된 historical diagnostic이며 untouched confirmation이 아니다.

Base raw LightGBM과 temporal policy, conditional-tail magnitude model을 고정했다. 기존71 feature와 burst 확장 feature의 balanced LightGBM detector를 비교하고 DEV/CAL에서 gate와 correction을 선택했다. gate 밖 Q50/Q90은 C0와 같고 전체 Q90 scaling/capping은 없다.

C1은 예측 risk로 조건화한 과거 causal residual 보정이다. C2는 고정 expert의 conditional burst-tail quantile로 만든 operational Q90 후보이며 unconditional quantile의 수학적 보장을 주장하지 않는다. 2%를 의미 있는 pinball 악화 경계로 사전 지정했다.

| 구간 | 모델 | coverage | positive | detector recall | precision | FPR | PR-AUC | burst coverage | ratio | pinball |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DEVELOPMENT | C0 | 81.39% | 72.48% | 8.43% | 14.29% | 3.21% | 0.1245 | 0.00% | 1.099 | 161.104 |
| DEVELOPMENT | C1 | 83.41% | 75.45% | 60.24% | 8.26% | 42.40% | 0.1486 | 0.00% | 1.598 | 157.128 |
| DEVELOPMENT | C2 | 83.76% | 75.98% | 34.94% | 11.74% | 16.65% | 0.1486 | 19.28% | 2.069 | 158.362 |
| CALIBRATION | C0 | 85.10% | 81.44% | 13.16% | 8.47% | 9.22% | 0.0943 | 2.63% | 0.995 | 280.790 |
| CALIBRATION | C1 | 90.71% | 88.42% | 89.47% | 7.91% | 67.58% | 0.0962 | 2.63% | 1.541 | 275.844 |
| CALIBRATION | C2 | 91.19% | 89.02% | 60.53% | 8.78% | 40.78% | 0.0962 | 42.11% | 2.513 | 297.138 |
| EXPOSED_EVALUATION | C0 | 86.03% | 81.96% | 15.91% | 12.43% | 7.47% | 0.0937 | 0.76% | 1.209 | 203.045 |
| EXPOSED_EVALUATION | C1 | 90.01% | 87.09% | 87.12% | 8.00% | 66.82% | 0.0826 | 7.58% | 1.766 | 201.546 |
| EXPOSED_EVALUATION | C2 | 89.77% | 86.79% | 46.21% | 7.64% | 37.22% | 0.0826 | 25.76% | 2.867 | 229.137 |
| MAY_HISTORICAL | C0 | 87.63% | 85.60% | 36.23% | 14.12% | 22.52% | 0.1569 | 7.25% | 1.408 | 307.779 |
| MAY_HISTORICAL | C1 | 91.80% | 90.45% | 100.00% | 9.65% | 95.70% | 0.1449 | 17.39% | 2.174 | 307.623 |
| MAY_HISTORICAL | C2 | 93.15% | 92.02% | 94.20% | 11.25% | 76.00% | 0.1449 | 46.38% | 3.164 | 328.461 |

## 고정 candidate

```json
{
  "C1": {
    "config": {
      "family": "C1",
      "detector": "D1_BASE71_BALANCED",
      "threshold": 0.0025,
      "tail_quantile": null
    },
    "hard_feasible": false,
    "rank": [
      true,
      2.0684739134201697,
      true,
      true,
      1.5694777776732007,
      -0.080857197770517,
      0.5498778475088453,
      -0.12241339586491089,
      216.48608805715133
    ]
  },
  "C2": {
    "config": {
      "family": "C2",
      "detector": "D1_BASE71_BALANCED",
      "threshold": 0.01,
      "tail_quantile": 0.5
    },
    "hard_feasible": false,
    "rank": [
      true,
      1.8291694304336361,
      true,
      true,
      2.2909827331264276,
      -0.1025975832122879,
      0.28719458618073357,
      -0.12241339586491089,
      227.75028279682138
    ]
  }
}
```

## Paired 95% CI

1일과 7개 관측 target-day circular block을 2,000회 resampling했다. 아래는 7일 결과다. 예측 loss는 C0 대비, detector metric은 PR67 old detector/gate0.10 대비이며 selection uncertainty는 포함하지 않는다.

| 구간 | 모델 | 지표 | delta | 95% CI |
|---|---|---|---:|---|
| EXPOSED_EVALUATION | C1 | Q90_pinball | -1.4986 | [-4.6103, 1.7854] |
| EXPOSED_EVALUATION | C1 | burst_coverage | 0.0682 | [0.0224, 0.1242] |
| EXPOSED_EVALUATION | C1 | detector_recall | 0.7121 | [0.6583, 0.7658] |
| EXPOSED_EVALUATION | C1 | pinball_minus_2pct_margin | -5.5595 | [-9.5086, -1.5160] |
| EXPOSED_EVALUATION | C2 | Q90_pinball | 26.0921 | [16.3908, 35.9518] |
| EXPOSED_EVALUATION | C2 | burst_coverage | 0.2500 | [0.1802, 0.3305] |
| EXPOSED_EVALUATION | C2 | detector_recall | 0.3030 | [0.2273, 0.3910] |
| EXPOSED_EVALUATION | C2 | pinball_minus_2pct_margin | 22.0312 | [11.9565, 32.3644] |
| MAY_HISTORICAL | C1 | Q90_pinball | -0.1553 | [-13.4478, 12.3070] |
| MAY_HISTORICAL | C1 | burst_coverage | 0.1014 | [0.0319, 0.1837] |
| MAY_HISTORICAL | C1 | detector_recall | 0.6377 | [0.5614, 0.7222] |
| MAY_HISTORICAL | C1 | pinball_minus_2pct_margin | -6.3109 | [-19.2869, 5.9456] |
| MAY_HISTORICAL | C2 | Q90_pinball | 20.6825 | [-0.4995, 39.9667] |
| MAY_HISTORICAL | C2 | burst_coverage | 0.3913 | [0.2933, 0.4783] |
| MAY_HISTORICAL | C2 | detector_recall | 0.5797 | [0.4875, 0.6731] |
| MAY_HISTORICAL | C2 | pinball_minus_2pct_margin | 14.5269 | [-6.9961, 33.5080] |

## 판정

May 7일 block CI에서 C1의 burst coverage 개선은 +10.14pp [3.19, 18.37], C2는 +39.13pp [29.33, 47.83]이다. 개선 방향의 근거는 있지만 두 후보의 최종 burst coverage는 목표에 못 미친다. C1 pinball 차이는 −0.155 [−13.448, 12.307]이고 2% noninferiority margin에 대한 차이의 CI 상한도 +5.946이므로 통계적으로 robust한 pinball 개선이나 2% noninferiority를 입증하지 못한다. AP 차이의 CI도 0을 포함한다. 개별 CI는 다중비교 보정을 하지 않았으며 selection uncertainty, 장기 종속성, post-exposure bias를 제거하지 않는다.

- Target/interface: 기존 hourly future-work target과 Q50/Q90 배열 형식, base prediction 및 gate 밖 동일성은 감사 통과. 실제 ingestion/request-version authority는 미인증이므로 production interface readiness로 확대 해석하지 않는다.
- TEMPORAL_POLICY_CHANGED = **FALSE**. Temporal 효과를 새로 검색하지 않았다.
- BASE_MODEL_CHANGED = **FALSE**. Base architecture 및 conditional-tail magnitude는 그대로다. 요청된 detector feature/class-balance/gate와 conditional-tail quantile만 DEV/CAL에서 비교했다.
- New detector/model superior: **전체 gate를 만족하는 우월성 미지지**. Burst coverage의 일부 개선과 전반적인 실용적 우월성을 구분한다.
- PRODUCTION_REPLACEMENT_SUPPORTED = **FALSE**
- OPTIMIZER_INTEGRATION_READY = **FALSE**
- PRODUCTION_PROMOTED = **FALSE**

모든 후보의 DEV/CAL 결과는 SELECTION_METRICS.csv, feature ablation과 threshold별 detector 결과는 DETECTOR_METRICS.csv, risk/burst strata와 gate 결과는 별도 CSV에 있다. 연구 candidate는 hard gate 실패 시에도 보고하지만 adoption으로 해석하지 않는다.

## 검증 결과

14개 focused test를 통과했다. 443개 issue의 미래/미성숙 workload와 label 변경에 대한 feature invariance를 포함한다. 독립 감사는 273개 exact training membership·numeric weight vector, 546개 classifier checkpoint, 1,365개 frozen tail checkpoint와 14,616개 최종 예측 행을 별도로 재현했고 차이는 0이었다. Parent/source digest 709개도 일치했다. 독립 bootstrap 구현은 80개 CI 행·16,000개 paired resample을 재계산했으며 최대 수치 차이는 2.558e−13이었다.

Frozen verifier는 C1의 issue Timestamp 객체 273개를 JSON 문자열과 직접 비교해 실패했다. 다른 membership 값은 모두 동일했다. 원본 코드는 바꾸지 않고 delivery-only adapter가 기존 JSON writer와 같은 `str()` 표현으로만 정규화한 뒤 원래 모든 검사를 통과했다. 원래 오류, 표현 차이 수, source 보존을 `VERIFIER_SERIALIZATION_AUDIT.json`에 기록했다. 모델·예측·선택을 수정한 amendment가 아니다.

과거 mature evaluation labels는 고정 prequential feature/refit/residual 규칙에만 들어간다. 실제 ingestion latency와 request-version provenance는 미인증이다. finite-rank residual은 시계열 의존성에 대한 distribution-free coverage 보장을 주지 않는다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS 및 production을 수정·실행하지 않았다.
