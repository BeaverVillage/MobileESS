# 독립 검토 후 부가 검증

선택과 evaluation이 끝난 뒤 독립 에이전트가 read-only 검토했다. 평가 membership, 고정 Q90/Q95 값, R0 원본 일치, total/remaining target, requested reference, paired CI는 통과했다. 다음 두 사항을 발견하여 부모와 등록 source·frozen 결과를 보존한 상태로 보완했다.

1. `study.choose()`의 mandatory coverage/overreserve는 missing이면 탈락하지만, preference인 GPU coverage/long-under가 missing이면 preferred status만 잃는다. 등록 문구 “Missing metrics fail closed”의 넓은 의미에 비해 구현이 충분히 엄격하지 않다. **실제 DEV/CAL의 모든 해당 지표는 finite**이고 양 상태의 선택은 R0여서 관측 선택에 영향이 없다. `review_addendum.py`가 모든 선택 지표의 finite 여부를 강제 검증하고 합성 NaN 입력 거부를 검증한다. 이 guard를 통과하지 못하면 이 evidence를 유효하다고 해석하거나 publish할 수 없다. 등록 source를 평가 후 다시 쓰거나 정책을 재선택하지 않았다. 변경된 데이터에 대한 prospective 사용은 이 고정 연구의 범위 밖이다.
2. 최초 paired CI는 missed GPU-slots의 **절대 차이**에 대한 CI이며 감소율 자체의 CI는 아니었다. `MISSED_SLOT_REDUCTION_UNCERTAINTY.csv`에 감소율 `1 − candidate/reference`를 매 paired day/block resample에서 새로 계산한 CI를 추가했다. 관측 denominator로 absolute CI를 나누지 않았다. 모든 2,000회 draw의 denominator가 양수임을 검증했다.

`REVIEW_ADDENDUM_VALIDATION.json`은 이 부가 검증의 실제 작성 시각과 source hash를 기록한다. 선택, quantile 수준, threshold, model, feature, prediction, split 또는 exclusion을 변경하지 않았다. May는 여전히 exposed historical diagnostic이며 production promotion은 없다.
