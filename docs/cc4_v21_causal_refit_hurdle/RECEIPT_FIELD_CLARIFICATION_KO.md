# Prediction receipt 필드의 정확한 의미

이 문서는 배포 봉인 이후 추가한 설명이다. 기존 코드·freeze·prediction·membership·metric·보고서·DELIVERY_MANIFEST를 변경하지 않는다.

`fits/*/*/PREDICTION_*.json`의 `evaluation_labels_in_fit`이라는 필드명은 실제 계산식보다 넓은 의미로 읽힐 수 있다. 이 값은 `int((label_available_time[training_rows] >= fit_cutoff).sum())`, 즉 **그 fit cutoff에 아직 성숙하지 않은 training label의 수**다. 모든 receipt에서 0이다. “평가 기간에 속하는 label이 단 한 개도 training에 들어가지 않는다”는 뜻은 아니다.

이번 실험은 처음부터 prequential refit/calibration을 등록했다. 미래 issue에서는 **이미 성숙한** 이전 May/평가일 label이 고정된 refit 및 residual 규칙에 들어갈 수 있다. 이러한 label로 모델 family, feature, hyperparameter, cadence, calibration 창을 다시 선택하거나 평가 결과에 맞춰 scale/cap을 조정하지 않는다. 정확한 포함 날짜는 각 fit의 `MEMBERSHIP.json` 및 `mature_May_days`에서 확인할 수 있다.

이 필드의 정확한 해석명은 `immature_training_labels_at_fit_cutoff`이다. 원래 bytes와 digest를 보존하기 위해 기존 필드명을 사후 변경하지 않고 의미를 명시한다. `verify.py`는 별도로 모든 학습 날짜가 strict maturity cutoff를 통과했는지 검사하므로 검증 결론에는 영향이 없다.
