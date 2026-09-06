# H100-standby runtime forensic

Visible subgroup point misfit under changing multimodal outcome mix, combined with pooled q that does not provide H100-standby conditional tail coverage.

검증 N=3,717; point MAE=13900.357s, RMSE=25543.440s, mean(actual−point)=4854.318s, median=86.336s. 과소예측 51.5469%. 평균과 중앙값은 양수지만 일별 bias 부호는 다르다.

| 지표 | Pooled | H100-standby |
|---|---:|---:|
| Point underprediction | 0.507902 | 0.515469 |
| q-only underprediction | 0.099984 | 0.283831 |
| q-only coverage | 0.900016 | 0.716169 |
| capped-safe coverage | 0.883790 | 0.716169 |
| ceil coverage | 0.902874 | 0.718321 |
| q-only mean positive residual, sec | 2672.305931 | 7530.758915 |
| q-only P90 positive residual, sec | 0.000000 | 23641.513135 |
| q-only P95 positive residual, sec | 8074.743976 | 39455.439355 |

Frozen pooled q=5576.44921875s. H100 diagnostic q90=29217.962354s, q95=45031.888574s. 적용·변경하지 않았다. 기존 28.17%는 ceil 후이며 q만 적용하면 28.3831%다.

학습 subgroup 87,319건 중 FAILED 54,057건(runtime 중앙값 23s), COMPLETED 28,394건(48,917s)이다. 검증에는 FAILED 675/3,717, COMPLETED 2,562/3,717이 포함된다. 절대오차 목적은 평균·상단 분위수가 아닌 조건부 중앙값 중심이며 서로 다른 종료 regime과 tail을 한 point로 나타낸다. 이 mix 변화는 관측 근거이지만 개별 tree/leaf의 원인 기여율을 증명하지 않는다. 종료 상태는 미래 정보이므로 새 feature로 넣지 않았다.

학습에는 >12h 18,103건, May cohort와 같은 43,200s 요청 635건, 동일 9-feature vector 0건이 있다. broad training support는 YES이나 final expert/leaf support는 미보존이다. 7-day calibration에는 같은 43,200s H100 요청이 0건이고 목·금 표본은 각각 1건이다. 단순히 7일이 짧아서 실패했다고 결론내리지 않는다.

H100/standby는 partition/QoS로 모델에 보인다. Feature omission은 기각한다. 실제 runtime은 짧은 mass와 15.5–16h mass가 분리되는 mixture-like이고 긴 우측 tail이 있다. 이는 경험적 분포 진단이며 asymptotic heavy-tail 법칙이나 fitted mixture 모델 주장이 아니다.

May +29의 historical rank: runtime [0.6642453591606134, 0.6954533225719667], point residual [0.7742803336023675, 0.8872746838848534]; {'EXPECTED_HISTORICAL_TAIL': 29}. Broad preMay tail 범위 안에 있지만 matched walltime validation은 없어 같은 family coverage를 주장하지 않는다.

정확한 최종 tree 오차 원인은 INSUFFICIENT_EVIDENCE. 현재 근거는 subgroup point misfit + pooled conditional coverage mismatch이며, 별도 pre-May 연구에서 point redesign/conditional upper bound/robust reserve 조합을 비교할 이유가 된다. 현재 model/q/Planning/May 결과는 변경하지 않았다.
