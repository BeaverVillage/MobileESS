# Fold4 state forensic

CURRENT_STATE_TRACKS_FOLD4 = INCONCLUSIVE

직전24h 제출 requested GPU 합=1757,
pending GPU=637, running GPU=588.
다음 VALID exact runtime Q50=673s,
Q90=59862s, >4h=22.7342%.

FOLD_WORKLOAD_PRESSURE.csv와 FOLD_COMPOSITION_SHIFT.csv에 14일 전/직전의
모든 압력·구성값을 기록했다. 다섯 시기만의 기술적 비교로 incoming wave의
지속적 예측력을 확정할 수 없다. 완료된 작업의 runtime만 비교하므로 관측
cutoff의 completion-selection도 남는다. 이 결과로 feature나 gate를 바꾸지
않으며, 시간적 예측력은 고정된 Stage B 모델과 group ablation으로 판단한다.
