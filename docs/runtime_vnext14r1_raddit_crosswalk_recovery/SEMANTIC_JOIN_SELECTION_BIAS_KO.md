# Selection bias 평가 상태

NOT_RUN_LEVEL1_AUTHORITY_FAILURE. V13 GPU 621,583건에 승인된 end-to-end 연결이 없어 matched/unmatched 비교 모집단을 만들지 않았다. 전체 0%는 승인된 연결 비율이며 물리적으로 대응 가능한 행이 0개라는 관측값이 아니다. Fold 및 tail join rate는 null이다. S0/S4 기존 예측을 다시 실행하거나 새 모델을 학습하지 않았다.

Embedding raw metadata의 historic 부분집합은 1,780,972행이고 나머지 776,912행이 제외되어 있다는 집합 수준의 증거는 확보했다. 이 선택이 V13 GPU 또는 장기 작업에 편향되는지는 아직 모른다. CPU-exclusive 결과라는 README 설명을 실제 export filter로 대입하지 않았다. 현재 결과로 selection bias의 부재·크기·인과관계를 주장할 수 없다.
