# Runtime-vNext14R2 최종 검토

**STOPPED_TIMESTAMP_EXPORT_AUTHORITY_UNRESOLVED. NEW_ML_FITS=0.**

새 결과는 T1 EKEY2=0, T0 지지 DST 진단, notebook dtype 확인, 그리고 **표시 종료일 >= 2024-04-23의 exact raw subset membership**이다. 실제 export/stripping authority가 없어 Level1은 미승인이고 Level2는 미실행이다.

## 1. V14R1의 정확한 blocker는 무엇이었는가?

naive embedding timestamp가 historic -06:00과 어떤 source operation으로 연결되는지 미입증이었다. 99.6935% raw 후보는 physical-instant authority가 아니었다.

## 2. V14R2에서 새로 조사한 범위는 무엇인가?

허용된 T1 비교, DST 예시, notebook 저장 출력, reachable/unreachable Git·rename/delete·LFS 이력, local intermediates, 날짜 membership·결측 signature, 공식 public metadata와 V42 Arrival interface를 새로 조사했다.

## 3. Historic timestamp의 저장 timezone은 무엇인가?

저장 Arrow timezone은 고정 -06:00이다. Notebook output의 pytz.FixedOffset(-360)도 일치한다. America/Denver DST zone이나 upstream 수집 timezone으로 추정하지 않았다.

## 4. Embedding timestamp Arrow type은 무엇인가?

45개 모두 timestamp[us], Parquet 물리 INT64 및 isAdjustedToUTC=false다.

## 5. Embedding timestamp에 timezone metadata가 있는가?

없다. EMBEDDING_TIMESTAMP_TIMEZONE_METADATA_PRESENT=FALSE. Writer footer는 parquet-cpp-arrow 16.1.0이지만 timezone 제거 구현을 설명하지 않는다.

## 6. T0(local wall-clock strip)은 몇 행을 exact match시키는가?

T0의 EKEY0/1/2 모두 embedding 1,780,972행에 키가 있다. 유일 1:1은 각각 1,380,258 / 1,504,066 / 1,775,514행이며 유일 후보 holdout 충돌은 모두 0이다.

## 7. T1(UTC strip)은 몇 행을 exact match시키는가?

T1은 EKEY0: matched embedding 11행, 유일 8쌍 전부 충돌, ambiguous 3행. EKEY1: 1행·유일 1쌍·충돌 1. EKEY2: 0행. 따라서 충돌 없는 유일 후보는 모두 0이다.

## 8. 어느 transformation이 source-backed인가?

실제 배포 변환으로 source-backed인 것은 아직 없다. T0는 강하게 지지되는 진단 가설이고 최종 TIMESTAMP_TRANSFORMATION=UNRESOLVED다.

## 9. DST 구간은 어떤 표현을 지지하는가?

등록한 DST 주변 20개 raw-candidate 표본 모두 표시 local wallclock에만 일치한다. 후보 없는 10개 날짜도 명시했다. 이는 T0 지지 증거지만 원래 stripping operation의 증거가 아니다.

## 10. 임의 offset fitting을 했는가? 반드시 NO.

NO. T0/T1 두 명시적으로 허용된 serialization 가설만 검사했다. arbitrary offset 또는 성능 기반 offset 탐색은 없다.

## 11. embedding export script를 찾았는가?

아니다. 공개 npy 생성 단계와 배포 chunk consumer 사이의 exporter는 찾지 못했다.

## 12. int8/encrypted transform code를 찾았는가?

아니다. qint8는 공개 모델 weight quantization이며 배포 vector encryption/int8 변환과 구분했다.

## 13. 40,000-row chunking code를 찾았는가?

아니다. 40,000행이라는 stored output/footer는 확인했지만 그 크기로 쓰는 생성 코드는 미확보다.

## 14. 누락 776,912행의 exact subset rule을 찾았는가?

관측적 membership 규칙은 찾았다: historic 표시 종료일 >= 2024-04-23이면 정확히 1,780,972행이고 제외는 776,912행이다. 원본 export query가 이 predicate였다는 authority는 미입증이다.

## 15. 단순 count matching이 아니라 source authority가 있는가?

행수뿐 아니라 전체 row membership이 일치한다. 그러나 실제 exporter/실행 manifest의 독립 근거가 없어 source-authority flag는 FALSE다.

## 16. embedding 1,780,972행의 historic membership을 재구성할 수 있는가?

Raw EKEY2 집합 및 group multiplicity 수준에서는 1,780,972행을 재구성할 수 있다. 중복 그룹 안에서 특정 vector row의 historic row를 유일하게 지정하는 것은 별개다.

## 17. 1,775,514 unique candidate는 승인 mapping으로 승격됐는가?

아니다. 1,775,514개의 raw 유일 후보를 보존했으나 Level1 승인 행수는 0이다.

## 18. 5,458 ambiguous rows는 줄었는가?

줄지 않았다. 2,514그룹, 5,458행이다. 그룹 크기 2/3/4/5/6/7에 해당하는 그룹 수는 2,167/287/42/14/3/1이다.

## 19. ambiguous rows를 row order로 해결했는가? 반드시 NO.

NO. 공유 필드를 모두 검사했으나 추가 non-vector field가 없고 start_time도 중복에서 같아 그대로 ambiguous로 남겼다.

## 20. embedding order relation은?

최종 UNPROVEN. R1 raw unique 후보의 인접 역전 636,834, 전체 역전 쌍 66,906,351이다. raw reorder 증거를 승인 mapping 순서로 승격하지 않았다.

## 21. Level1 mapping은 승인됐는가?

FALSE. source-backed timestamp와 충분한 original export provenance 조건이 충족되지 않았다.

## 22. Level1 provenance grade는 PROVEN/STRONGLY_SUPPORTED/PARTIAL/UNPROVEN 중 무엇인가?

PARTIAL. 단순 UNPROVEN으로 강한 metadata 증거를 지우지 않았고, source-backed transform이 없는 상태를 STRONGLY_SUPPORTED/PROVEN으로 올리지 않았다.

## 23. Kestrel F0–F2를 실행했는가?

NO. 조건부 Level2 authorization이 닫혀 F0–F2를 실행하지 않았다.

## 24. 실행했다면 F0 match는?

NOT_RUN, null이다. 관측된 zero-match가 아니다.

## 25. F1 match는?

NOT_RUN, null이다.

## 26. F2 match는?

NOT_RUN, null이다.

## 27. unique 1:1 physical matches는?

Kestrel physical unique count는 미측정(null)이다. 승인된 end-to-end assignment는 없다.

## 28. holdout contradictions는?

T0 EKEY0–2 unique holdout 충돌은 0. T1 EKEY0는 8, EKEY1은 1, EKEY2는 비교쌍 0. Kestrel holdout은 NOT_RUN이다.

## 29. negative controls는 얼마나 collapse했는가?

Negative controls는 NOT_RUN이다. T1 진단을 Kestrel NC1–3 실행으로 간주하지 않았다.

## 30. end-to-end Kestrel mapping은 증명됐는가?

FALSE. Level1 미승인, Level2 미실행이다.

## 31. V13 621,583 GPU jobs 중 몇 개가 semantic-linked인가?

승인된 V13 연결은 0건이며 실제 가능한 개수/비율은 미측정(null)이다. 621,583개 GPU 작업에 새 physical join을 수행하지 않았다.

## 32. fold별 support는?

NOT_RUN, null이다. 이전 결과나 추정값을 새 support로 채우지 않았다.

## 33. >4h support는?

NOT_RUN, null이다.

## 34. >12h support는?

NOT_RUN, null이다.

## 35. >24h support는?

NOT_RUN, null이다.

## 36. joined/unjoined selection bias는?

V13 end-to-end joined/unjoined bias는 미평가다. Historic raw subset의 missingness·월·범주 enrichment만 기술했으며 인과성을 주장하지 않는다.

## 37. RADDiT semantic text input은 outcome-free인가?

공개 8-field render 함수의 직접 입력 범위에서는 TRUE다. runtime/end/power는 문자열에 없지만 상위 job_type 생성 시점과 비공개 export까지 attestation한 것은 아니다.

## 38. distributed export provenance는 어느 수준인가?

PARTIAL. Metadata·LFS payload identity·date membership·public text generation은 확보했고 원래 timezone strip/export/encryption operation은 미해결이다.

## 39. V42는 8개 semantic 입력 중 몇 개를 현재 제공하는가?

현재 SubmissionRuntimeRequest whitelist와 policy.Arrival에서 partition/qos 2개다. response_policy.ObservedJob도 정적으로 확인했다.

## 40. 빠진 semantic submit-time field는 무엇인가?

user, account, job_type, name, submit_line, script 6개다. workload_class가 job_type과 동일하다는 근거는 없다.

## 41. 그 필드들을 미래정보 없이 추가할 수 있는가?

user/account/name/submit_line/script는 accepted submission 때 실제로 capture하도록 설계할 수 있다. job_type은 submit-only 분류 규칙의 별도 authority가 필요하다. 현재 구현이나 관측시점 인증이 있다는 주장은 아니다. 개인정보·sanitization 및 동일 표현 계약도 필요하다.

## 42. 정확한 Linq embedding revision을 확인했는가?

현재 공개 model HEAD 0c1a0b0589177079acc552433cad51d7c9132379(lastModified 2024-06-05)는 확인했다. RADDiT 생성 실행이 resolve한 model/tokenizer revision 및 transformers/quanto 버전은 고정된 기록이 없어 미입증이다.

## 43. distributed encrypted/int8 transform을 재현할 수 있는가?

FALSE. Weight qint8·last-token pooling·L2 normalization·2048 truncation은 공개 코드에서 확인하지만 배포 encrypted/int8 transform은 없다. Model download/re-embedding은 0이다.

## 44. historical semantic crosswalk은 가능한가?

유력한 raw 후보와 membership 복원은 가능하다. 승인된 historical crosswalk는 아직 FALSE이며 원본 timestamp/export authority가 필요하다.

## 45. new-job semantic generation도 가능한가?

현재 계약과 동일 배포 representation 기준 FALSE다. 6개 입력 누락과 불명확한 vector transform이 남아 있다.

## 46. 다음 semantic Runtime ML을 시작할 authority가 생겼는가?

FALSE. Level1/Level2·controls·temporal/tail support·bias·new-job input/representation 조건을 충족하지 못했다. Retrospective study 승인도 아직 없다.

## 47. NEW_ML_FITS가 0인가?

예. NEW_ML_FITS=0. 학습·SVD·semantic kNN prediction·calibration·remaining/queue/provider/V42 등을 실행하지 않았다.

## 48. April 평가를 했는가? 반드시 NO.

NO. April runtime 평가 없음. 2024년 과거 날짜 signature를 조사한 것을 2025년 holdout April 평가와 혼동하지 않는다.

## 49. May payload를 열었는가? 반드시 NO.

NO. May runtime payload 미개봉. Footer·Git/source/notebook metadata 조사와 pre-April RADDiT projection만 사용했다.

## 50. 최종적으로 무엇이 확인된 사실이고 무엇이 여전히 가설인가?

사실: 저장 timezone 차이, T0/T1 diagnostic counts, exact 종료일 membership, 동일 replay, ambiguous 5,458행, 1-version LFS history, V42 6-field gap. 가설/미입증: 실제 stripping 함수, exporter가 사용한 cutoff/query, 원래 model/env/vector transform, Kestrel identity 및 semantic Runtime 성능. 의미 정보가 무용하다는 결론은 아니다.
