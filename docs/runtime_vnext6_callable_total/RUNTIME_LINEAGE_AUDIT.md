# Runtime-vNext6 계보 감사

기준은 PR #72의 f084c4c82cc3873dbe32f350f4da87ececdf88ce다. 이전 결과를 수정하지 않고 디렉터리별 바이트 해시를 보존했다. 연구 모델, 직렬화 모델, 임의 새 작업 호출 가능성, optimizer 권한은 서로 다른 조건이다.

| 계보 | 파일 존재 | 직렬화 모델 수 | 타깃·제한 |
| --- | --- | --- | --- |
| V35R3D | True | 0 | Historical point+empirical safe margin; not a Q90 bundle |
| V40I | True | 0 | Forensic evidence; no new promoted estimator |
| V40J | True | 0 | Runtime redesign research; preserve rejection gates |
| V40K | True | 0 | Central runtime research; preserve conditional/tail limits |
| V40S3 | True | 0 | Body/tail research; request-version provenance unresolved |
| V40S4 | True | 0 | Explicit scheduler-request proxy, not immutable original requests |
| V40S5 | True | 0 | Direct runtime uncertainty research |
| V40S5R1 | True | 795 | Rolling-origin total/remaining research; optimizer_use_allowed false |
| runtime-vNext | True | 696 | Pending total and independent Running remaining; mixed pre/April/May issue family |
| runtime-vNext2 | True | 0 | Q95 diagnostic; not Q90 promotion |
| runtime-vNext3 | True | 0 | Adaptive Running bounds; total authority unchanged |
| runtime-vNext4 | True | 295 | GPU-weighted remaining quantiles and AFT; excluded from total package |
| runtime-vNext5 | True | 0 | Remaining residual calibration; Pending R0 unchanged |

기존 vNext 분할의 CALIBRATION은 2025-04-02~04-07이므로 이번 pre-April 선택에 재사용하지 않는다. vNext4/5의 R2 등은 Running remaining 모델이며 이번 총 실행시간 후보가 아니다. 역사적 운영 recipe나 저장 booster가 있다는 이유만으로 새로운 제출 작업에 대한 승인된 provider라고 주장하지 않는다.

비교 B0 후보는 실제 저장된 vNext의 2025-03-14T08:00Z PENDING Q50/Q90 총 실행시간 booster다. 180일 end-window/14일 반감기 recipe와 같은 시각 전처리 artifact를 검증해 재현한다. 사용자·계정 등은 기존 피처로만 처리하며 identity lookup은 예측에 사용하지 않는다. 이는 과거 생산계 전체의 재승인이 아니라 재현 가능한 pre-April 연구 기준이다.

V35R3D의 point+5576.44921875초 empirical margin은 Q90이라는 이름으로 바꾸지 않는다. 원 legacy 보정의 earliest availability가 4월인 부분도 pre-April bundle에 가져오지 않는다. May-only 생산 snapshot은 목록·해시 수준으로만 보존하고 이번 학습·선택·평가 입력으로 쓰지 않는다.

요청값은 final accounting archive에 있으나 원본 제출 버전·수집 시각·수정 이력은 미확인이다. 기존 연구의 proxy 권한과 정확한 역사적 원본성은 구분한다. 새 작업의 feature receipt는 실제 관측 시각과 source hash를 요구해야 하며, 과거 학습의 provenance 한계를 성공 플래그로 덮지 않는다.

April/May는 새 실험의 모델·피처·보정·백엔드 선택에 사용하지 않는다. April은 모델/번들 동결 후 별도 잠금 평가를 수행하고, May 결과는 본 작업에서 열지 않는다.
