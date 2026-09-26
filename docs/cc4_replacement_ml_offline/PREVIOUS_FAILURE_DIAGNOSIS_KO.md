# 이전 신경망 실패 진단

과거 판정은 수정하지 않았다. R6는 `V40R6_MULTI_HORIZON_GPUWORK_SAFETY_FAIL`, R6R1은 `V40R6R1_JOINT_GPUWORK_RESERVE_FAIL`, 선택 NONE 및 NO_MODEL_PROMOTED를 그대로 보존한다. 원본 보고서는 history/B, history/C, history/D에 고정 commit별로 저장했다.

| model | lr | selected_epoch | epochs_run | first_train_loss | last_train_loss | first_development_primary | last_development_primary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TFT | 0.0003 | 1 | 9 | 0.15612 | 0.10378 | 0.65365 | 0.7248 |
| DEEPAR | 0.0003 | 1 | 9 | 1.2825 | 1.2073 | 0.64315 | 0.64588 |
| NHITS | 0.0003 | 22 | 30 | 0.14486 | 0.090928 | 0.77577 | 0.72831 |
| CMABF | 0.0003 | 1 | 9 | 0.91797 | 0.78289 | 0.67408 | 0.70921 |

근거: R3 `train.py:fit_neural_once`, `neural.py:neural_loss`, `library_batch`, 각 fits/*/result.json의 전체 history. 두 learning-rate trial의 곡선은 PREVIOUS_TRAINING_CURVES.csv에 저장했다.

TFT/DeepAR/CMABF의 epoch 1 선택은 실제 기록이다. 학습 손실 하락과 development 양수-target Q90 점수 악화가 함께 나타난다. 이는 일반화 악화와 일치하지만, 이것만으로 실제 과적합과 시간적 분포변화를 분리할 수는 없다. 과거에는 TRAIN 양수 Q95로 선형 스케일링했다. TFT/NHiTS는 전체 표본의 Q50/Q90 pinball 평균을 학습하면서 양수 표본의 Q90 점수만으로 조기종료했다. DeepAR는 Gaussian NLL, CMABF는 발생 BCE·분위수·양수분위수·burst 혼합 손실을 사용했다. 따라서 학습 목적과 조기종료 목적이 다르며, zero-heavy 자료에서 epoch 1의 높은 예측이 양수 지표에 유리할 가능성이 있다. 이는 코드와 곡선에 근거한 원인 후보이며 단일 원인 확정은 아니다.

과거 maturity mask는 history_values에서 관측 END/구간 종료 경계를 적용하고, library_batch에서 미성숙 GPUh를 다시 0 placeholder로 가렸다. 이 0은 mask와 함께 전달되며 GPU 결측값 대체가 아니다. DeepAR 학습의 teacher forcing은 생성 likelihood 계산용 shifted target이며, 추론에서는 y 없이 autoregressive 경로를 생성한다. 코드 검토에서 미래 target을 추론 입력으로 넣는 경로는 발견하지 못했다. 6시간 lead는 미래 calendar/lead covariate로 표시되지만 별도 bridge decoder를 학습하지 않은 구조적 한계는 있다.

과거 학습은 비유한 loss를 검사하고 gradient norm 1로 clip했다. gradient의 전후 norm 및 비유한 gradient 통계는 기록되어 있지 않으므로 비정상 gradient가 없었다고 소급 확정할 수 없다. best epoch 1만으로 epoch 수를 늘릴 근거도 없다.

이번 TFT는 16 hidden의 소형 TFT 기반 구현(변수선택, gated residual, LSTM, causal attention)이며 원본 라이브러리 TFT의 재현이라고 부르지 않는다. 전체 window 원단위 pinball(0.2 Q50 + 0.8 Q90), log1p 출력, TRAIN 분위수 초기화를 사용한다. 이번 DeepAR 기반 구현은 전체 H4 합계 target을 직접 autoregressive 예측하고, 0 질량을 분리한 hurdle lognormal likelihood를 사용한다. 양수 log-target 정규화는 TRAIN으로만 추정한다. DeepAR의 NLL와 Q90 조기종료 목적 차이는 여전히 남아 있고 명시한다. 두 모델 모두 raw 336×8 과거 sequence와 동일 71개 window 특징을 사용하므로 LightGBM의 요약 특징보다 표현 형태가 풍부하다. 정보원과 성숙 경계는 같지만 순수 파라미터화만 바꾼 ablation은 아니다.

이번의 실제 gradient norm, 학습/검증 곡선, checkpoint SHA, seed, 시간, GPU peak는 fits/*/receipt.json에 저장했다. 과거 30분 target 실험과 이번 H4 직접 합계 예측 실험의 수치를 동일 표본의 개선율로 비교하지 않는다.
