# 실행·감사 기록

PR63의 target, feature, split, raw population과 frozen evidence를 그대로 두고 새 디렉터리에서 실험했다. 최초 등록, 단계별 선택, 최종 freeze와 평가 완료 시각을 JSON에 남겼다. 평가 결과에 따른 모델·feature·hyperparameter·refit·calibration 변경은 허용하지 않았다.

## 평가 전 수정

원본 코드 bytes와 amendment JSON을 함께 보존했다. `OPERATIONAL_AMENDMENT.json`은 독립적인 cache 계산의 병렬 실행과 process lock을 기록한다. 같은 membership·seed로 학습하는 hurdle/burst의 동일 구성요소를 재사용할 때도 원본과 대상 파일 digest를 남긴다.

`TIMESTAMP_CORRECTION.json`은 NumPy 문자열을 pandas Timestamp에 전달할 때 생긴 자료형 오류를 수정한 기록이다. 이미 구동 중이던 process는 수정 전 모듈을 계속 사용했으므로 중단 후 새 process에서 다시 실행했다. 실패한 로그도 보존했으며 target·날짜·membership 또는 예측 규칙을 변경하지 않았다.

`CALIBRATION_SUPPORT_AMENDMENT.json`은 성능을 보기 전 maturity-only 감사에서 발견한 28일 residual 창의 CALIBRATION 지원 부족을 기록한다. 28일 창은 26일 중 17일만 필요한 support를 만족했다. 전체 CALIBRATION support를 충족하는 창만 선택할 수 있게 했고 세 창의 진단 결과를 모두 남겼다. 선택 모델을 evaluation에서 다시 고르지 않는다.

## 재현과 저장

동일한 당일 fit을 여러 번 생성하지 않도록 tag별 lock을 사용하고 neural training은 GPU 전역 lock으로 직렬 처리한다. full-day label maturity와 feature availability를 각 issue에 대해 검사한다. May에는 이미 성숙한 Mar–Apr 및 앞선 May history만 고정 규칙에 따라 반영한다.

학습 checkpoint는 로컬에 보존하고, Git에는 해시와 재현 코드, exact membership·receipt·예측을 담은 감사 bundle을 저장한다. `verify.py`는 전체 로컬 감사, `verify_delivery.py`는 배포된 파일과 bundle의 읽기 전용 감사다. package/plot 코드는 선택 이후의 배포 도구이며 예측·평가 대상을 변경하지 않는다.

실제 ingestion latency는 인증되지 않았고 exposed historical 평가다. optimizer, MESS, IEEE123/8500, Actual/OpenDSS를 실행하거나 수정하지 않았으며 production promotion과 integration을 하지 않았다.
