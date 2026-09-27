# 실행 및 감사 범위

Scientific code/protocol은 모델 학습 전에 `CODE_FREEZE.json`으로, sigma는 DEV 전에 `DISTRIBUTION_PARAMETERS.json`으로, gate/ensemble/eligibility는 evaluation 전에 `FINAL_SELECTION_FREEZE.json`으로 동결했다. 이후 core code와 설정을 변경하지 않았다. Report/plot/delivery helper는 이미 동결된 결과를 표시·검증할 뿐 selection에 관여하지 않는다.

사전 reuse 감사의 첫 실행은 원 PR64 weight 필드가 numeric array일 것으로 검사하여 중단됐다. 실제 원 receipt는 pandas Index의 축약 문자열이었다. `reuse_preflight_weight_representation.log`를 보존했다. Freeze 전에 auditor를 수정하여 원 문자열을 정확히 비교하고 frozen weighting formula로 전체 numeric 배열을 재구성했다. 실제 학습/예측/분포/selection은 이 사전 점검 이후 시작했다. Source evidence를 수정하거나 숫자를 추정해 원 receipt에 채우지 않았다.

`tests.log`의 invalid-value warning은 zero-denominator synthetic case에서 의도적으로 만드는 nonfinite bootstrap 결과다. Test는 이런 draw를 버리지 않고 CI unavailable로 처리하는지 확인하며 PASS다. 실제 평가의 invalid CI rows는0이다.

모델 비교의 prior cached evidence는 이미 exposed다. New freeze는 이번 실행의 evaluation scoring보다 앞서지만 기존 결과를 untouched로 되돌리지 않는다. Primary와 eligibility는 DEV/CAL로만 결정했고 이번 Dec–Feb/May 평가 후 바꾸지 않았다.

새 분포 모델379개 daily fit은 각 occurrence/location2개 checkpoint로 구성된다. 이 중106일은 TRAIN OOS sigma 추정,273일은 기존 OOS issue calendar다. 기존 모델 재학습은0회다. 새 checkpoint는 local 보존, Git에는 recipe·membership·prediction/parameter·digest를 보존한다.
