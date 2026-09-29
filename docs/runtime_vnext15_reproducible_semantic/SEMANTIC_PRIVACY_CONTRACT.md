# Semantic 입력의 저장 경계

`SubmissionSemanticPayload`는 제출 경계에서만 다룬다. 기본 repr은 원문을 가리며, runtime request의 payload 필드도 repr에서 제외한다. Job name·명령·스크립트의 실제 원문을 logger, 결과 CSV, optimizer artifact 또는 manifest에 기록하지 않는다. 현재 연구 입력은 NLR이 공개한 익명화 토큰이며, 이 작업은 원래 값을 복원하지 않는다.

Canonicalization은 Unicode NFC와 바깥쪽 공백 정리만 수행한다. `field + identity_namespace + value`에 SHA256을 적용하여 namespace가 다른 동일 문자열을 분리한다. Recurrence map에는 이 pseudonym만 저장한다. SHA256은 역함수가 없는 digest이나 작은 후보 공간의 추측 공격을 막는 익명화 보장은 아니다. 민감한 실환경은 접근통제된 경계에서 영속적인 기관 토큰을 제공하고, 원문은 변환 직후 폐기해야 한다. 이 코드는 Python 메모리의 보안 삭제를 주장하지 않는다.

저장 허용 항목은 숫자 벡터, pseudonym 빈도, feature version, 모델/transformer digest, 공개된 익명화 source 토큰 및 수치 감사 결과다. 원문 전체가 포함된 dataclass 직렬화는 승인된 저장 API가 아니다. 과거 원본 Kestrel projection은 `.local`에만 저장한다.

Policy `Arrival`에는 `NumericSemanticFeatures`만 허용하고 raw payload는 거부한다. 제출 때 생성한 벡터를 RUNNING 기간에 보존하며 outcome으로 다시 계산하지 않는다. CC4는 `submit_time < issue_time`인 작업만 읽는다. D-1의 미제출 작업 payload는 사용할 수 없다.

Kestrel 익명 토큰을 실제 미래 사용자명으로 되돌리거나 그 비공개 hashing 함수를 재현하지 않는다. 기존 익명 namespace와 미래 실환경 namespace는 명시적으로 다르다. 동일 코드로 미래 입력을 변환할 수 있다는 사실은 새로운 namespace의 범주가 과거 TRAIN에서 알려졌다는 의미가 아니다. 알려진 범주 재사용에는 데이터 제공자가 보증하는 동일 identity namespace가 필요하며, 그 밖에는 unseen으로 처리한다.

`ENABLE_SUBMISSION_SEMANTICS=False`가 기본이다. 이 flag는 특징 생성만 제어한다. Runtime/CC4 모델의 선택·검증은 별도 조건이며, 실패한 모델이나 이전 미승인 baseline을 이 flag로 운영 승격할 수 없다.
