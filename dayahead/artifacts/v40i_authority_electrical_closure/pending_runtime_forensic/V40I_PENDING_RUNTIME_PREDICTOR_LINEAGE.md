# PENDING runtime predictor lineage

max(0,(end_time-start_time).total_seconds())

Target은 total elapsed execution runtime이다. Queueing delay는 제외되지만 raw internal pause를 빼는 label code는 없다. 합성 counterfactual migration pause는 원본 label에 없고 replay에서 별도 처리한다.

학습 cutoff: 2025-03-31T08:00:00Z; 학습 범위: [2024-12-01T08:00Z,2025-03-31T08:00Z) by completed end_time for final issue model. May label 사용 NO.

모델: Requested-walltime-bin MoE XGBoost, pooled users, global fallback. 목적: reg:absoluteerror; time decay exp(-0.05 * days_old); no GPU-weighted loss.

Features: num_cores_req, num_gpus_req, num_nodes_req, requested_memory_mib, requested_seconds, account, partition, qos, user

전처리는 제출 시점 allowlist, numeric와 categorical one-hot/SVD다. Target encoding은 꺼져 있다. 요청 walltime은 feature/routing/cap이고 GPU 수는 feature이며 label은 GPU-hour가 아니다.

Empirical 0.90 quantile of positive held-window residual max(actual-point,0), numpy linear; pooled across 87,824 jobs

min(requested_seconds,max(point+5576.44921875,900))

ceil(safe_seconds/900), minimum one slot; 15 minutes, NOT 5 minutes

q90은 조건부 coverage나 distribution-free conformal 보장이 아니다. 기존 pooled calibration coverage는 88.3790%다. Requested-walltime cap 및 GPU/standby·long-job 분포 차이를 별도로 기록한다.

Existing rolling-window predictions precede final issue fit; metrics describe the frozen recipe/calibration evidence, not an independent holdout of the final April-01 fitted state. That state was discarded by original code; no refit performed.

각 단계의 정확한 source/code/artifact 경로와 SHA-256, 날짜, feature, label, 보정·반올림 규칙은 JSON chain에 있다. 원본 소스·모델·q는 수정하지 않았다.
