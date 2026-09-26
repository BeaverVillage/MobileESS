# CC4-v2.4 최종 검토 — Request-state Burst Forecast

DEV/CAL에서 선택을 **C0**로 freeze한 뒤 evaluation했다. May는 exposed historical diagnostic이며 untouched confirmation이 아니다.

## 인과 경계와 고정 범위

사용자의 명시적 지시에 따라 V40S4 D1_SCHEDULER_REQUEST_STATE_PROXY_V1를 계승했다. Archive의 요청 GPU/walltime/partition/QoS는 assumption-based scheduler-visible proxy다. Historical issue-time 값과 정확히 같았음, request immutability, 변경 빈도 0을 주장하지 않는다. Version provenance는 UNVERIFIED, 변경 이력은 UNOBSERVED다. 코드/모델 authority를 historical scheduler snapshot 증거로 사용하지 않았다. 이 한계는 offline 실험 중단 사유로 쓰지 않았으며 production readiness는 fail-closed다.

Base raw LightGBM과 expanding/30-day/daily temporal policy, TRAIN burst threshold를 고정했다. 새 요청 feature는 실제 runtime 완료를 기다리지 않으며 submit<issue proxy 범위에서 계산한다. 기존 71 feature를 그대로 두고 request-state feature를 추가했다. No future runtime/end label enters request feature generation.

Detector gate는 두 후보 모두 **0.01 고정**이다. 이전 C2와 같고 이전 C1 0.0025보다 높다. Gate/threshold 탐색이나 전체 scaling은 없다. C1은 gated causal residual, C2는 새 request-feature burst-only conditional magnitude quantile이다. Gate 밖 Q50/Q90 및 전체 Q50은 C0와 정확히 같다. C2는 operational Q90 후보이며 unconditional calibration 보장은 아니다.

DEV/CAL 각각 AP·precision의 matched-gate PR69 detector 대비 +0.01 절대 개선, recall/burst≥60%, positive≥85%, ratio<2, pinball≤1.02×C0를 요구했다. 기준·feature·model 설정과 2% 의미 있는 pinball 악화 경계는 개발 결과를 보기 전에 등록했다. AP는 noninterpolated average precision이다.

## 모델과 detector 결과

| role | model | coverage | positive | burst | ratio | pinball | recall | precision | FPR | AP | high-risk fraction |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DEVELOPMENT | C0 | 81.39% | 72.48% | 0.00% | 1.099 | 161.104 | 34.94% | 11.74% | 16.65% | 0.1486 | 17.74% |
| DEVELOPMENT | C1 | 81.47% | 72.58% | 0.00% | 1.135 | 161.174 | 9.64% | 10.96% | 4.97% | 0.0876 | 5.24% |
| DEVELOPMENT | C2 | 81.97% | 73.33% | 4.82% | 1.631 | 162.787 | 9.64% | 10.96% | 4.97% | 0.0876 | 5.24% |
| CALIBRATION | C0 | 85.10% | 81.44% | 2.63% | 0.995 | 280.790 | 60.53% | 8.78% | 40.78% | 0.0962 | 41.99% |
| CALIBRATION | C1 | 86.38% | 83.03% | 10.53% | 1.207 | 278.390 | 26.32% | 14.29% | 10.24% | 0.1163 | 11.22% |
| CALIBRATION | C2 | 87.18% | 84.03% | 23.68% | 1.749 | 295.280 | 26.32% | 14.29% | 10.24% | 0.1163 | 11.22% |
| EXPOSED_EVALUATION | C0 | 86.03% | 81.96% | 0.76% | 1.209 | 203.045 | 46.21% | 7.64% | 37.22% | 0.0826 | 37.78% |
| EXPOSED_EVALUATION | C1 | 86.88% | 83.06% | 5.30% | 1.344 | 203.628 | 11.36% | 8.15% | 8.54% | 0.0918 | 8.71% |
| EXPOSED_EVALUATION | C2 | 87.17% | 83.43% | 9.09% | 1.827 | 214.251 | 11.36% | 8.15% | 8.54% | 0.0918 | 8.71% |
| MAY_HISTORICAL | C0 | 87.63% | 85.60% | 7.25% | 1.408 | 307.779 | 94.20% | 11.25% | 76.00% | 0.1449 | 77.69% |
| MAY_HISTORICAL | C1 | 90.05% | 88.42% | 27.54% | 2.151 | 311.587 | 65.22% | 11.63% | 50.67% | 0.1380 | 52.02% |
| MAY_HISTORICAL | C2 | 91.26% | 89.83% | 40.58% | 2.989 | 334.670 | 65.22% | 11.63% | 50.67% | 0.1380 | 52.02% |

C0 행의 detector 수치는 이전 PR69 balanced detector를 동일 gate0.01에서 평가한 reference다. C0 forecast에는 이 gate로 보정을 적용하지 않는다. 이전 C1 gate0.0025 수치는 DETECTOR_METRICS.csv에 별도로 보존한다.

## Paired uncertainty

동일 target-day를 paired로 묶어 1일/7개 관측일 circular block bootstrap을 각2,000회 시행했다. Forecast는 C0, detector는 matched-gate PR69와 비교한다. 매 draw에서 ratio/precision/FPR/AP를 다시 계산한다. CI는 frozen forecast 조건부이며 model selection/refit uncertainty와 multiple-comparison correction을 포함하지 않는다.

| role | model | metric | delta | 7-day 95% CI |
|---|---|---|---:|---|
| EXPOSED_EVALUATION | C1 | Q90_pinball | 0.5831 | [-1.2411, 2.5483] |
| EXPOSED_EVALUATION | C1 | burst_coverage | 0.0455 | [0.0165, 0.0769] |
| EXPOSED_EVALUATION | C1 | detector_recall | -0.3485 | [-0.4745, -0.2315] |
| EXPOSED_EVALUATION | C1 | precision | 0.0051 | [-0.0346, 0.0461] |
| EXPOSED_EVALUATION | C1 | pinball_minus_2pct_margin | -3.4778 | [-5.7148, -1.0625] |
| EXPOSED_EVALUATION | C1 | PR_AUC | 0.0091 | [-0.0087, 0.0263] |
| EXPOSED_EVALUATION | C2 | Q90_pinball | 11.2063 | [4.9984, 17.8222] |
| EXPOSED_EVALUATION | C2 | burst_coverage | 0.0833 | [0.0400, 0.1338] |
| EXPOSED_EVALUATION | C2 | detector_recall | -0.3485 | [-0.4745, -0.2315] |
| EXPOSED_EVALUATION | C2 | precision | 0.0051 | [-0.0346, 0.0461] |
| EXPOSED_EVALUATION | C2 | pinball_minus_2pct_margin | 7.1454 | [1.0692, 13.9561] |
| EXPOSED_EVALUATION | C2 | PR_AUC | 0.0091 | [-0.0087, 0.0263] |
| MAY_HISTORICAL | C1 | Q90_pinball | 3.8087 | [-5.6910, 13.1223] |
| MAY_HISTORICAL | C1 | burst_coverage | 0.2029 | [0.1111, 0.2923] |
| MAY_HISTORICAL | C1 | detector_recall | -0.2899 | [-0.4445, -0.1316] |
| MAY_HISTORICAL | C1 | precision | 0.0038 | [-0.0062, 0.0181] |
| MAY_HISTORICAL | C1 | pinball_minus_2pct_margin | -2.3469 | [-11.3397, 6.5804] |
| MAY_HISTORICAL | C1 | PR_AUC | -0.0069 | [-0.0517, 0.0356] |
| MAY_HISTORICAL | C2 | Q90_pinball | 26.8912 | [14.2153, 39.9747] |
| MAY_HISTORICAL | C2 | burst_coverage | 0.3333 | [0.2542, 0.4186] |
| MAY_HISTORICAL | C2 | detector_recall | -0.2899 | [-0.4445, -0.1316] |
| MAY_HISTORICAL | C2 | precision | 0.0038 | [-0.0062, 0.0181] |
| MAY_HISTORICAL | C2 | pinball_minus_2pct_margin | 20.7356 | [8.5384, 32.8516] |
| MAY_HISTORICAL | C2 | PR_AUC | -0.0069 | [-0.0517, 0.0356] |

## Stop rule과 판정

HOURLY_BURST_DEVELOPMENT_STOPPED = TRUE. 이 판단은 사전 지정한 의미 있는 ranking/precision 개선과 최종 forecast gate 및 조건부 CI를 함께 적용했다.

Hourly burst 추가 모델 개발은 중단한다. 후속 연구 후보로 cumulative next-day GPU-work, 3시간 GPU-work, 6시간 GPU-work target을 제안만 한다. 더 긴 집계가 timing noise와 burst 희소성에 주는 영향을 별도 사전등록으로 평가할 수 있다. 이번 task에서는 label 재집계, target 변경이나 optimizer 연동을 구현하지 않았다.

- NEW_MODEL_SUPERIOR = **FALSE**
- PRODUCTION_REPLACEMENT_SUPPORTED = **FALSE**
- OPTIMIZER_INTEGRATION_READY = **FALSE**
- PRODUCTION_PROMOTED = **FALSE**

과거 evaluation label은 해당 issue 이전 strict maturity를 만족하면 고정 prequential refit/residual 규칙에만 들어가며 tuning에는 사용하지 않는다. 기존 PR69 evidence는 보존했다. Optimizer/MESS/IEEE123/8500/Actual/OpenDSS/production은 수정·실행하지 않았다.
