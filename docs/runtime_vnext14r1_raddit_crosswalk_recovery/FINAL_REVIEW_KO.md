# Runtime-vNext14R1 최종 검토

**STOPPED_LEVEL1_TIMESTAMP_AUTHORITY_UNRESOLVED. NEW_ML_FITS=0.**

V14의 ID-only 실패를 반복하지 않았다. 45개 embedding chunk의 공유 payload에서 유력한 exact 행 연결 증거를 확보했지만, 사전 등록한 timestamp source-authority gate를 통과하지 못했다. Kestrel physical fingerprint 검사는 0-match 실패가 아니라 미실행이다.

## 1. V14는 왜 중단됐는가?

식별자·source authority 실패로 중단됐다. Semantic challenger가 학습되어 실패한 결과가 아니다.

## 2. 이번 V14R1에서 무엇을 새로 조사했는가?

45개 chunk의 공유 metadata만 projection하여 EKEY0–2 exact collision·holdout·bitwise equality·재시작 replay·순서를 검사하고 Git 전체 reachable source 이력과 targeted public lineage를 조사했다.

## 3. RADDiT job_id는 원 Slurm ID인가?

아니다. 2,557,884행 모두 0-based historic 행번호와 같다. 연결 키에서 제외했다.

## 4. public prep_for_embedding은 어떤 순서로 row를 처리하는가?

historic를 읽은 순서로 4096행 연속 배치한다. 배포 chunk 순서가 같다는 증명은 아니다.

## 5. embedding 생성 문자열에는 어떤 정보가 들어가는가?

user, account, partition, job_type, name, qos, submit_line, script의 8개 필드다.

## 6. 실제 runtime/end/power가 embedding text에 들어가는가?

검사한 public render/generation 코드에는 들어가지 않는다. 검색 DB의 outcome metadata와 생성 문자열을 구분했다. 비공개 배포 export까지 attestation한 것은 아니다.

## 7. distributed embedding chunk 총 행수는?

45개 chunk, 1,780,972행이다. 첫 44개는 각각 40,000행, 마지막은 20,972행이다. 벡터를 decode하지 않았다.

## 8. historic trace와 왜 행수가 다른가?

Historic 2,557,884행 중 776,912행 차이가 있다. EKEY2 raw metadata 부분집합은 확인했으나 제외 이유는 미입증이다.

## 9. embedding→historic exact match는 몇 개인가?

RAW_REPRESENTATION 키 존재는 1,780,972행 전부다. EKEY2 유일 후보는 1,775,514행, ambiguous 5,458행, 키 unmatched 0행이다. UTC 의미가 미입증이므로 승인 crosswalk 행수는 0이다.

## 10. 어떤 exact key가 가장 강한가?

EKEY2(submit+end+runtime+power)가 가장 많은 collision을 구분했다. 이는 coverage로 key를 선택했다는 뜻이 아니다. source-authority가 닫혀 최종 승인 key는 NONE이며 EKEY0부터 작은 유일 key를 검토한다는 계약을 유지했다.

## 11. unique 1:1 비율은?

EKEY0 1,380,258, EKEY1 1,504,066, EKEY2 1,775,514 / 1,780,972 = 99.69353814%다. 모두 raw representation 진단이다.

## 12. ambiguous match는?

EKEY0 400,714행, EKEY1 276,906행, EKEY2 5,458행이다. EKEY2의 2,514개 many:many 그룹은 start_time까지 동일하다.

## 13. embedding row order 관계는 무엇인가?

최종 UNPROVEN. 유일 raw 후보에서 인접 역전 636,834건, 전체 역전 쌍 66,906,351개, source-index 중복 0건이다. 44개 chunk 경계 중 source index가 증가하는 경계는 30개다. direct prefix/ordered subset 가정은 관측과 맞지 않는다. 시간 authority가 없어 REORDERED_BUT_EXACT_MAPPING_PROVEN으로 승인하지 않았다.

## 14. 누락 776,912행의 filter를 찾았는가?

아니다. 해당 raw key 집합 밖의 행수만 확인했고 선택 이유는 모르므로 count-matching filter를 만들지 않았다.

## 15. filter authority는 code/document로 입증됐는가?

FALSE. 공개 prep와 배포 chunk 사이 export 단계가 보이지 않는다.

## 16. RADDiT historic→Kestrel field lineage는?

FIELD_LINEAGE_MAP.csv에 timestamp, duration/request, resources와 단위를 명시했다. stored offset 기반 F0–F2만 계획상 허용하고 memory scope 및 categorical-token mapping은 미입증이다.

## 17. job_id를 제외한 physical fingerprint match는 몇 개인가?

NOT_RUN_LEVEL1_AUTHORITY_FAILURE, 관측 개수 null. 새 physical fingerprint에서 0개가 나왔다고 주장하지 않는다. integer flag의 0은 승인 assignment 수다.

## 18. 가장 강한 exact fingerprint는 무엇인가?

Kestrel F0–F2는 사전 등록만 했고 미실행이다. 선택된 Kestrel key는 없다. F3/F4는 field authority도 없어 비활성이다.

## 19. Kestrel/RADDiT 양쪽에서 key collision은 얼마인가?

Kestrel 비교 collision은 미측정(null). Embedding-historic EKEY2의 중복-key 행은 historic 8,855, embedding 5,458이다. 서로 다른 비교를 혼동하지 않는다.

## 20. unused holdout field contradiction은 몇 개인가?

Embedding-historic 유일 raw 후보에서는 EKEY0–2 각각 0이다. EKEY2 start_time 1,775,514쌍 일치. Kestrel holdout은 NOT_RUN이다.

## 21. negative control에서는 match가 얼마나 남는가?

NC1 +1초, NC2 날짜 내 requested walltime permutation, NC3 runtime permutation(seed1401)은 사전 등록했지만 Level1 중단 후 실행하지 않았다. 수치는 null이다.

## 22. timezone 차이는 어떻게 처리했는가?

historic -06:00은 기록 그대로 UTC epoch도 보존했다. embedding naive는 timezone을 부여하지 않았다. 표시된 raw 시각 비교와 UTC 비교 미실행을 분리했다. 정밀도 손실·truncation 없음.

## 23. 임의 시간 offset fitting을 했는가?

NO. ±시간 탐색, DST 역추정, 성능 최대화 offset을 사용하지 않았다.

## 24. approximate/fuzzy matching을 했는가?

NO. exact numeric/bitwise 비교만 수행했고 positional ID나 nearest timestamp로 보완하지 않았다.

## 25. end-to-end embedding→Kestrel mapping은 입증됐는가?

FALSE. Level1 source-authority 미충족, Level2 미실행이다.

## 26. V13 GPU 621,583건 중 semantic mapping 가능한 수는?

현재 승인된 연결은 0건이다. 실제 연결 가능한 전체 수는 이번 결과로 결정할 수 없다.

## 27. 전체 join rate는?

승인 join rate 0 / 621,583 = 0%. 실제 physical correspondence 부재를 측정한 0%가 아니다.

## 28. fold별 join rate는?

5개 fold의 TRAIN/CAL/VALID 모두 NOT_RUN, null이다. 숫자를 채워 넣지 않았다.

## 29. >4h join rate는?

null, NOT_RUN_LEVEL1_AUTHORITY_FAILURE.

## 30. >12h join rate는?

null, NOT_RUN_LEVEL1_AUTHORITY_FAILURE.

## 31. >24h join rate는?

null, NOT_RUN_LEVEL1_AUTHORITY_FAILURE.

## 32. matched/unmatched population bias가 있는가?

V13 end-to-end population이 없어 미평가다. historic의 선택적 subset 관측만으로 GPU/장기 작업 bias나 인과성을 주장하지 않는다.

## 33. public embedding-generation provenance는 outcome-free인가?

TRUE, 공개 문자열 작성/embedding 코드의 직접 입력 범위에서만 그렇다. job_type의 상위 생성 시점까지 인증하지 않았으며 distributed export provenance와 분리한다.

## 34. distributed embedding export provenance는 완전히 입증됐는가?

PARTIAL. 공개 렌더링·LLM·chunk payload/LFS 식별은 확인했지만 subset, timezone stripping, encrypted/int8 변환이 미입증이다.

## 35. new future job에서 semantic input을 받을 수 있는가?

현재 V42 SubmissionRuntimeRequest를 정적으로 읽었다. 8개 중 partition/qos만 허용되어 있고 script/submit_line/name/account/user/job_type 6개가 없다. 현재 계약 기준 FALSE다.

## 36. same embedding pipeline을 재현할 수 있는가?

FALSE. 공개 Linq 모델 예제는 있으나 model/tokenizer revision이 고정되지 않았고 배포 encrypted coordinate transform이 없다. 임의로 새 embedding을 실행하지 않았다.

## 37. semantic Runtime ML을 다음 단계에서 실행할 scientific authority가 생겼는가?

FALSE. source-backed timestamp, end-to-end unique linkage, actual V13 temporal support, selection bias 조건이 충족되지 않았다.

## 38. authority가 생겼다면 broad/partial/sparse 중 무엇인가?

NO_SUPPORT: 승인된 end-to-end support가 없다는 뜻이다. raw 후보의 규모나 semantic utility를 부정하는 분류가 아니다.

## 39. authority가 실패했다면 정확한 blocker는 무엇인가?

직접 blocker는 naive embedding timestamp의 원래 timezone/export 의미를 source code/document로 입증하지 못한 것이다. 5,458 duplicate rows, subset/export 변환 미공개도 별도로 기록했다. subset 미포함 자체는 실패 조건이 아니다.

## 40. 다음에 필요한 외부/원본 자료는 무엇인가?

source row crosswalk와 원 Slurm composite identity, embedding subset query/version, timestamp 변환 계약, row-order manifest, 동일 encrypted vector transform, 새 제출 semantic input capture 계약이다. 이 자료가 도착하면 사전 등록된 F0–F2와 controls부터 재개할 수 있다.

## 41. V14/J2–J5 ML은 이번 task에서 실행했는가?

NO. NEW_ML_FITS=0. 모델 학습·SVD·kNN 예측·calibration·remaining/queue/provider를 모두 실행하지 않았다.

## 42. April을 평가했는가?

NO. 기존 pre-April projection과 RADDiT의 pre-April metadata만 사용했다. Kestrel ZIP의 April member를 새로 열지 않았다.

## 43. May를 열었는가?

NO. May runtime payload 미개봉. 원본 raw size/mtime 검사는 내용 decode가 아니다.

## 44. 기존 V6–V14 evidence가 보존됐는가?

예. 기존 tracked 1,373개, delivery manifest 9개와 raw size/mtime 23,601개를 전후 검증한다. 실제 재검증 결과는 VERIFICATION.json에 기록하고 기존 파일은 수정하지 않는다.

## 45. 무엇이 확인된 사실이고 무엇이 여전히 가설인가?

확인: raw shared metadata의 전체 키 존재, 1,775,514개 유일 후보, 0 holdout/bitwise 충돌, 5,458개 ambiguity, 배포 순서 재배열, public text input 8개, 새 제출 계약의 6개 누락. 가설: 동일 absolute-time/export lineage, 제외 filter 이유, Kestrel physical identity, V13 temporal/tail support와 semantic ML 이익. Runtime 또는 semantic 정보가 무용하다는 주장은 하지 않는다.
