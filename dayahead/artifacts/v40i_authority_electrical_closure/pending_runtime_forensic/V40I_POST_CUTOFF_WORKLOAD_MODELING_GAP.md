# Post-cutoff workload modeling gap

Planning은 D-1 18:00 AEST에 알려진 RUNNING 254와 PENDING 1,395 UID만 포함한다. 이후 도착은 예측·대체 workload로 추가되지 않는다. Actual도 같은 frozen UID universe의 service를 비교하므로 future arrivals는 현재 역전의 직접 원인이 아니다.

POST_CUTOFF_ARRIVAL_CAUSE_OF_CURRENT_REVERSAL = NO.

이는 실제 다음 날 모든 도착 workload를 포괄하는 운영 예측 검증이 아니다. 새 도착·GPU 규모·runtime·위치의 공동 불확실성은 현 실험에서 평가하지 않는다. 이번 작업에서 future-arrival predictor를 만들거나 이 May 결과를 이용해 보정하지 않았다.
