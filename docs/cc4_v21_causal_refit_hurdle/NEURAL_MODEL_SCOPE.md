# Neural 비교 범위

`TFT`와 `DEEPAR` 표기는 PR63에서 사용한 compact 연구 구현을 뜻한다. 특정 외부 패키지의 전체 기본 모델이나 모든 가능한 TFT/DeepAR 설정을 대표하는 결과로 해석하지 않는다. 새 architecture·epoch search는 하지 않았다.

- `SmallTFT`: hidden size 16, 과거 336시간의 8개 입력과 미래 24시간의 71개 causal covariate에 대한 variable selection, LSTM encoder/decoder, 2-head causal attention 및 gated residual block을 사용한다. 직접 Q50/Q90을 출력하며 8 epoch, learning rate 0.001을 고정했다.
- `SmallDeepAR`: hidden size 16의 LSTM encoder/decoder와 발생확률·positive lognormal 분포를 사용한다. 학습의 teacher forcing과 구분하여 inference에서는 이전 sampled 값을 되먹임하고 실제 미래 target을 입력하지 않는다. 128개 sampled trajectory에서 Q50/Q90을 계산하며 18 epoch, learning rate 0.001을 고정했다.
- 두 모델은 3개 고정 seed를 사용한다. normalizer와 target scale은 매 refit의 mature training membership으로만 계산한다. Stage A에서 선택된 recency weight는 일별 loss에 적용한다.
- 보고된 neural 지표는 seed별 metric의 평균이고 CI는 같은 날의 seed 평균 loss를 사용한다. seed를 서로 다른 평가 날짜로 세지 않으며 별도 선택하지 않은 ensemble 예측의 성능으로 바꾸지 않는다.

구체적인 수식·sampling·정규화 및 학습 설정의 authority는 `neural.py`, `PROTOCOL.json`, fit receipt이다. 이 문서는 구현 범위를 설명하는 배포 문서이며 모델·예측·선택을 변경하지 않는다.
