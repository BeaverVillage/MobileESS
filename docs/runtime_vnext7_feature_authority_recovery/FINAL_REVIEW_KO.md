# Runtime-vNext7 최종 검토

**최초 제출 피처 권위를 복구하지 못했다. 엄격 피처0개인 계약을 동결하고 재학습 승인을 FALSE로 유지한다.** 문서·코드 의미를 더 복구했지만 원본값 증거와 혼동하지 않았다.

## 1. 왜 Runtime-vNext6에서 9개 피처를 제외했는가?

제출 당시 입력이라는 의미만 있고, 현재 공개 accounting 행이 최초 요청값인지 증명할 버전·수집·출판 연결이 없었기 때문이다. 이번 감사에서도 기존 9개는 D다.

## 2. 그 판단이 너무 보수적이었는가, 실제 provenance 문제인가?

운영 후보의 원본 제출 피처라는 기준에는 실제 증거 공백이 있다. 다만 모든 필드가 똑같이 mutable이라는 설명은 부정확하다. 메모리 변경 능력은 새로 확인했고 user·submitline·script·array는 불변 가능 개념과 NLR 매핑 증거를 분리했다. downstream allowlist는 행별 authority가 아니다.

## 3. requested walltime의 최초 제출값을 복원할 수 있는가?

입증하지 못했다. Timelimit 의미와 duration 변환은 확인했지만, 최초/유효/변경값을 가를 revision 또는 immutable snapshot이 없다.

## 4. requested GPU의 최초 제출값을 복원할 수 있는가?

입증하지 못했다. ReqTRES→gpus_requested의 내부 파서·갱신 경로와 최초 요청 버전이 공개되어 있지 않다.

## 5. QoS/partition/account의 최초 제출값을 복원할 수 있는가?

입증하지 못했다. 기본·명시·변경값 및 account 익명화 버전까지 연결할 자료가 없다. 수정 가능하다는 사실만으로 실제 전 행이 수정됐다고 말하지 않는다.

## 6. submit_time은 최초 제출시각인가, requeue 후 시각일 수 있는가?

문서상 sacct Submit이며 requeue 후 갱신된 시각일 수 있다. 삽입시각이라고 볼 근거는 없다. 최초 시각이 증명되는 별도 cohort도 0건이다. UTC 변환이나 최솟값 선택으로 해결되지 않는다.

## 7. duplicate/requeue로 original request를 복원할 수 있는 비율은?

입증한 비율은 공개 id/행 기준0/6,326,884=0%, 중복 후보 행 기준0/310,128이다. 숫자 ID 반복4,104집단은 배열 원소3,830집단 및 배열 범위+원소 형태274집단이다. 여러 submit 값4집단·요청 차이127집단을 같은 작업의 version 이력으로 인정하지 않았다. 실제 수정률을0%라고 뜻하지 않는다.

## 8. 기존 9개 중 production feature로 되살릴 것은?

현재 증거로는 없다. 9개 모두 research descriptor로 보존하되 production은 REQUEST_VERSION_UNVERIFIED로 fail-closed다.

## 9. 새 immutable submission-time feature가 있는가?

새 후보는 확인했다. 원자료의 array metadata·name/submitline/script/workdir 해시가 후보지만 원본 수집·해시·export 연결까지 통과한 수는0이다. job_type/python/reframe은 생성시점 미상 G다. 실제 archive state가 존재한다는 schema 정정도 반영했다.

## 10. workflow/script/job-name identity를 안전하게 사용할 수 있는가?

이미 공개된 익명 토큰의 반복·support 분석에 한해 PARTIAL이다. 역식별·원문 복원은 하지 않았다. strict 온라인 identity는 미지원이다. script의 DEV/CAL 미관측률77.49%/96.82%도 높다. workflow runtime CV는 권위 게이트로 보류했다.

## 11. long과 short를 구분하는 가장 강한 submission-time 정보는?

현재 판정할 수 없다. TRAIN의 기록 walltime 중앙값이6h/36h로 다르지만 검증된 최초 제출 피처가 아니다. 권위를 얻지 못한 피처를 상관·MI·classifier로 순위화하지 않았다.

## 12. >4h support는 충분한가?

전체 기술 분석에는 TRAIN47,229·DEV2,643·CAL1,594건이 있다. 세부 stratum 인증에는 일반화할 수 없다. CAL_VALID는464건, 장기 비율2.49%이며 종료시각 cutoff에 따른 선택효과도 있다.

## 13. ≥16 GPU validation support는 충분한가?

아니다. 이번 넓은 pre-April archive GPU cohort에서 DEV93건(장기14), CAL27건(장기6)이다. 기존 vNext6 필터와 동일한 코호트 수치가 아니며, 세부 그룹별 보장 성능을 인증하기에 부족하다.

## 14. STRICT_CAUSAL_SET에 몇 개 남는가?

작업별0개, 새 immutable0개다. 58개 후보 분류는 D24/E9/F14/G11이며 A/B/복원 가능한 C는 없다. 계약·분류의 SHA256을 기술 통계 전에 동결했다.

## 15. 다음 Runtime ML 재학습 근거가 생겼는가?

아니다. NEXT_RUNTIME_ML_RETRAIN_AUTHORIZED=FALSE. 새 모델·quantile 변경·survival 학습·April/May 평가를 수행하지 않았다. 이전 full-feature 연구 모델은 변경 없이 보존한다.

## 16. 아직 막는 provenance blocker는?

원본 accepted submit event와 attempt/array 식별, revision effective time, requeue 연결, 실제 sacct 수집 flags·보존 정책, load_slurm UPSERT/DDL와 export 기준, 익명 토큰의 안정적인 submit-time 생성·온라인 대응 증거다. NOT_FOUND_IN_SEARCHED_AUTHORITY이지 DOES_NOT_EXIST가 아니다.

## 범위·검증

|구간|mature GPU 행|>4h|장기 비율|≥16 GPU|≥16 GPU 중 >4h|
|---|---:|---:|---:|---:|---:|
|TRAIN|222,182|47,229|21.26%|3,607|442|
|DEV|12,002|2,643|22.02%|93|14|
|CAL_FIT|5,622|1,130|20.10%|10|2|
|CAL_VALID|18,640|464|2.49%|17|4|
|CAL|24,262|1,594|6.57%|27|6|
|ALL_MATURE|621,004|61,415|9.89%|30,437|677|

모델 학습0, 선택0. April/May 2025 payload 미개봉. 원자료6,326,884행 중복 제거 전 감사, 모든 실제 physical field의 분류 coverage 확인. 기존 vNext6 namespace와 base tracked 파일 보존은 VERIFICATION.json에 기록한다. 새로운 코드는 docs/runtime_vnext7_feature_authority_recovery에만 있다. 전수 내용 검색을 완료했다고 주장하지 않는다.

§9의 유효 제출 피처 전제 때문에 correlation/MI/variance/양방향 walltime 비율, 그리고 workflow runtime CV는 값 대신 SKIPPED_AUTHORITY_GATE를 보고했다. §10의 소급적 장단기 분포·요청 조합 분산은 별도 기술 통계다. 이것으로 유효 피처 또는 강한 분리력을 인정하지 않았다. 엄격한 기준 아래 과학적으로 계산 권한이 없는 항목을 임의 가정으로 채우지 않았다.

## 최종 flags

```json
{
  "REQUEST_VERSION_AUTHORITY_FOUND": false,
  "ORIGINAL_SUBMIT_TIME_RECOVERABLE": false,
  "REQUESTED_WALLTIME_INITIAL_VALUE_RECOVERABLE": false,
  "REQUESTED_GPU_INITIAL_VALUE_RECOVERABLE": false,
  "QOS_INITIAL_VALUE_RECOVERABLE": false,
  "PARTITION_INITIAL_VALUE_RECOVERABLE": false,
  "DUPLICATE_HISTORY_AVAILABLE": false,
  "REQUEUE_HISTORY_AVAILABLE": false,
  "HIGH_GPU_SUPPORT_SUFFICIENT": false,
  "RUNTIME_FEATURE_AUTHORITY_RECOVERED": false,
  "NEXT_RUNTIME_ML_RETRAIN_AUTHORIZED": false,
  "SUBMISSION_TIME_FEATURES_STRICTLY_VERIFIED": false,
  "STRICT_CAUSAL_RUNTIME_PROVIDER_READY": false,
  "IMMUTABLE_FEATURE_ONLY_MODEL_TRAINABLE": false,
  "STRICT_CAUSAL_JOB_FEATURE_COUNT": 0,
  "NEW_IMMUTABLE_FEATURE_COUNT": 0,
  "WORKFLOW_IDENTITY_SUPPORTED": "PARTIAL",
  "LONG_JOB_FEATURE_SEPARABILITY": "INCONCLUSIVE",
  "MUTABLE_REQUEST_FEATURE_COUNT": 8,
  "UNVERIFIED_REQUEST_FEATURE_COUNT": 9,
  "verdict": "FEATURE_AUTHORITY_NOT_RECOVERED; REQUEST_VERSION_UNVERIFIED; frozen strict set empty",
  "models_trained": 0,
  "model_selected": false,
  "April_payload_opened": false,
  "May_payload_opened": false,
  "authority_categories": {
    "D": 24,
    "F": 14,
    "G": 11,
    "E": 9
  },
  "search_negative_scope": "NOT_FOUND_IN_SEARCHED_AUTHORITY",
  "workflow_scope": "Existing anonymized token recurrence only; no strict new-job workflow identity.",
  "recoverability_false_meaning": "Not proven in searched authority, not proof of universal nonexistence.",
  "mutability_count_scope": "8 of prior9 request features; user excluded from mutable count; not empirical change count.",
  "submission_prediction_diagnostics": "SKIPPED_NO_VALID_FEATURES",
  "diagnostic_scope": "Section10 mature pre-April archive descriptors and label-free identity support",
  "feature_contract_frozen": true,
  "created_at": "2026-09-28T11:46:03.517065+00:00"
}
```

## V42가 새 제출 시 합법적으로 알 수 있는 정보

실제 accepted submit 이벤트를 받는다면 그때의 요청 walltime·자원·QoS·partition·account/owner·배열 선언 등은 관측할 수 있다. 이는 **미래 live capture 설계의 가능성**이다. 현재 공개 Kestrel archive의 동일 열이 그 시점의 값이라는 증거는 아니다. 이번 학습자료와 온라인 입력을 연결해 인증한 집합은 비어 있다. 다음 작업은 버전 증거 수집·검증이며 재학습이 아니다.

상세 근거: [계보/재큐잉 감사](REQUEST_VERSION_FORENSIC.md), [장기 작업 진단](LONG_JOB_ROOT_CAUSE_AUDIT.md), [공식 출처](EXTERNAL_AUTHORITY_SOURCES.md), [frozen strict 계약](STRICT_CAUSAL_FEATURE_CONTRACT.json), [최종 flags](FINAL_VERDICT.json).
