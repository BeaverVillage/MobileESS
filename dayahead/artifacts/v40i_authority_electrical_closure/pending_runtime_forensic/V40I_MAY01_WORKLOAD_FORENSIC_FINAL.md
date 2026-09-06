# V40I May-01 workload forensic 최종

주원인은 PENDING runtime 과소예측과 frozen spatial placement의 결합이다. +29 GPU는 29개 1-GPU job으로 정확히 재현됐다.

29개 모두 raw prediction 16,436.296875초 → q90 5,576.44921875초 추가 → safe 22,012.74609375초 → ceil 25×900=22,500초다. Actual은 28,577–43,227초로, 올림 이후에도 6,077–20,727초 부족했다. Raw prediction과 안전 여유 부족은 같은 29 GPU를 설명하므로 두 원인을 중복 합산하지 않는다. ROUNDING_INDUCED_UNDER와 AUTHORITY_MISMATCH는 0이다.
29개는 관측된 9개 predictor input feature가 모두 동일하다(1 GPU, 1 node, 1 core, 85G memory, 43,200초 요청, gpu-h100-stdby/standby 및 같은 hashed user/account). 그러므로 동일 point prediction을 받은 것은 feature/모델 규칙과 일치한다. 이 cohort에서는 requested-walltime cap도 작동하지 않아 margin 부족을 cap 때문으로 설명하지 않는다.

위치 이동 교차 집계: [{"group": "downstream->downstream", "job_count": 15, "GPU_count": 15, "slot73_contribution": 15}, {"group": "upstream->downstream", "job_count": 14, "GPU_count": 14, "slot73_contribution": 14}, {"group": "downstream->upstream", "job_count": 0, "GPU_count": 0, "slot73_contribution": 0}, {"group": "upstream->upstream", "job_count": 0, "GPU_count": 0, "slot73_contribution": 0}]

PENDING overprediction은 3 UID/−3 GPU, admission delay는 별도 3 UID/−3 GPU다. 해당 UID와 raw/safe/effective 오차, 시작·완료, 위치·권위는 각각 CSV에 있다.

| 효과 | sw2 하류 GPU |
|---|---:|
| Temporal | −2 |
| Spatial PENDING | +9 |
| Interaction | −4 |
| Migration | −1 |
| 합계 | +2 |

각 항은 1,649 UID의 factorial ledger로 재현했다. 10개 계획 migration 중 5개는 실행되고 5개는 checkpoint 이전 완료했다. Migration은 primary cause가 아니다. RUNNING 잔여시간 realization은 B0 −41, B1 −32 GPU로 절대 부하를 감소시켰고 비교 차이 +9는 그대로 보존했다.
Interaction −4는 −1인 7 UID와 +1인 3 UID의 합이다. 예를 들어 UID 8665994는 site만 AIDC02→AIDC10으로 바꾸면 slot 73의 하류에 1 GPU가 남지만 start까지 B1 값으로 바꾸면 이미 종료되어 0이 된다. UID 8666154–8666156은 AIDC12 admission 상호작용으로 각각 +1이다. 모든 시나리오의 start/finish와 active 상태를 CSV로 보존했다.

PENDING predictor는 walltime-bin MoE XGBoost이며 label은 max(0,end−start) execution elapsed seconds다. Queue delay는 포함되지 않는다. Raw 내부 pause는 제거하는 코드가 없으므로 순수 compute-time 측정이라고 주장하지 않는다. 요청 walltime과 GPU는 feature이며, 요청 walltime은 routing과 cap에도 쓰인다. GPU 조건부 uncertainty/safety margin 또는 GPU-weighted loss는 없다.

최종 model 학습은 2025-03-31 08:00 UTC 이전 120일의 완료 1,288,805행이다. May 학습·calibration은 NO. q는 3월 24–30일 AEST의 기존 28 rolling window, 87,824행 positive residual에서 계산한 pooled empirical 90% 분위수다. 보정 sample 자체의 coverage가 88.379%이며 독립 final-state holdout이 아니다.

Pre-May GPU-positive 표본 21,762개: raw underprediction 39.026744%, effective(ceil 포함) underprediction 6.254021%. GPU-weighted raw underprediction 39.722934%.
더 직접적인 H100-standby pre-May subgroup은 3,717개이며 raw underprediction 51.546946%, 보정·올림 후 28.167877%, GPU-weighted 보정·올림 후 31.194220%다. 따라서 pooled calibration이 해당 subgroup의 조건부 tail coverage를 보장했다고 해석할 수 없다.
전체·GPU·H100·H100-standby의 MAE/medianAE/RMSE/bias/P90/P95/long-job/가중 지표 및 시간·GPU bucket은 validation JSON에 있다. Feeder critical-slot의 preMay 검증 자료는 없어 service-axis miss-rate proxy로 명시했다.

B1 critical slot: feeder gross 2693.449615 kW, AIDC 334.562009 kW, B1-controllable incremental PCC 24.099852 kW. AIDC/feeder 12.4213%, flexible/AIDC 7.2034%, controllable/feeder 0.8948%.
전체 day 비율은 96-slot 에너지 적분의 비율로 계산했다. Frozen domain은 temporal 616, spatial 679(그중 RUNNING migration 가능 63) UID다. Idle/host/cooling 전체를 flexible job에 임의 배분하지 않았다. 제어 가능한 부하 규모는 효과의 크기를 제한하는 요인이지만 sign 역전을 단독 설명하지 않는다.

기존 sw2 phase-A sensitivity × Actual PCC 변화는 ΔI≈0.148915853403 A, 기존 AC 관측은 +0.146241726480 A다. 차이 -0.002674126923 A는 선형화 잔차로 보존한다. 하류 AIDC05/09/10/11/12는 약 0.138 A/kW, 상류는 약 0.00004–0.00063 A/kW다. 따라서 total GPU 감소보다 위치가 중요하며 모든 AIDC가 weak sensitivity라는 가설은 기각한다.

Claim boundary: Planning 개선과 이 May-01 폐쇄 cohort의 workload/placement realization 차이는 주장할 수 있다. 새로운 predictor/robust scheduling 우월성, full-May 통계 유의성, 미래 도착 예측 효과는 주장하지 않는다.

실행: optimization NO; predictor retraining NO; Actual-informed retuning NO; 31일 electrical regeneration NO; B2/B3 NO; full May NO. 재생성은 별도 승인 전 HOLD다. 원인 분석 결과로 frozen 정책·모델·q·계수·도메인을 수정하지 않았다.
