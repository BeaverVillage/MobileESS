# Runtime-vNext14 최종 검토

**판정: STOPPED_SOURCE_AUTHORITY_FAILURE. 신규 ML fit 0회.**
이 결과는 semantic 정보의 예측 효용 실패가 아니라, 원 물리 작업과의 연결을 입증하지 못해 §39에서 중단한 negative forensic result입니다.

## 완료 범위

- 두 중첩 raw root의23,601개 파일을 한 번씩 inventory하고27개 초기 family군으로 정리했습니다. 후보 Parquet schema2,588개, ZIP 내부 목록17개를 검사했습니다.
- V13 S0/S4의 전체 VALID 예측을 정확히 재현했습니다. V6–V13 원 파일 hash를 유지했습니다.
- 원본 Kestrel pre-April identity6,326,884행을 복구하고 기존 V13 GPU621,583행의 identity를 모두 원본 archive에 대조했습니다.
- RADDiT2,557,884행의 ID는 연속 row position입니다. 원본 ID+submit exact match0이며, V13 GPU의 JKEY0–3도모두0입니다.
- 배포 embedding45개 chunk/1,780,972행의 schema·offset을 기록하고 LFS OID 일치를 검증했습니다. Raw vector와 payload shared-field alignment는 중단 뒤 실행하지 않았습니다.

## 미실행 범위

J2–J5, SVD32, semantic kNN, facility join, grouped ablation, C1, remaining/provider, April 평가, May 열람은 미실행입니다. 미측정 성능·ambiguity·missing count를0/PASS로 채우지 않았습니다. Embedding audit의 null count는 중단 때문에 미측정이라는 뜻입니다.
Unused-field cardinality와 실제 facility sampling/latency 분석도 미실행이며, metadata에서 확인한 사실만 별도로 기록했습니다. 요청된 source-gap 표는 로컬 근거 정리이고, 모든 challenger 성능 실패 후 수행하는 Stage G나 외부 신규 탐색이 아닙니다.

## 해석 한계

ID 단독 숫자 일치와 같은 과거 작업임을 증명하는 exact identity를 구분합니다. 임의 시간 offset, nearest timestamp, row number 대입으로 join rate를 높이지 않았습니다. S0/S4 수치는 baseline 재현이며 V14 semantic arm의 결과가 아닙니다. Raw source는 수정하지 않았고 V42/CC4/MESS/kernel/optimizer/OpenDSS를 수정·실행하지 않았습니다.

## 1. V13은 정확히 왜 실패했는가?

V13 6개 후보의 all-gate 통과는0개였습니다. S4 pooled 91.84%는 단독 범위 내지만 min-fold70.70%, >4h69.72%, >12h64.25%, >24h46.88%로 temporal/long-runtime 기준에 미달했습니다. V13 결과를 재해석하거나 변경하지 않았습니다.

## 2. V14에서 새롭게 검사한 raw-data root는 무엇인가?

ROOT_A=C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터; ROOT_B=C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터. ROOT_B는 ROOT_A 안에 있으므로 물리 경로는 한 번만 집계하고 root membership 두 개를 표시했습니다.

## 3. 전체 raw source는 몇 개의 dataset family로 분류됐는가?

23,601개 파일을 27개 초기 family군으로 분류했습니다. 여기에는 코드·문서·비런타임 자료가 포함됩니다. 독립된 유효 데이터셋 27개라는 뜻이 아닙니다. 파일별 A–H 분류와 복사본 grouping을 별도로 제공했습니다.

## 4. Kestrel과 직접 job-level join 가능한 source는 무엇인가?

원래 Kestrel archive는 기존 V13 작업 identity를 모두 재확인하는 데 사용했습니다. 새 semantic source의 physical-job join은 입증되지 않았습니다. 시설 time-level 후보와 다른 HPC 자료를 직접 job feature로 연결하지 않았습니다.

## 5. RADDiT historic trace와 Kestrel join rate는?

원본 pre-April archive 6,326,884행과 RADDiT 2,557,884행의 ID+submit exact match는0개입니다. V13 GPU 621,583행의 authorized join rate도0%입니다. RADDiT ID는0~2,557,883의 row position입니다. 원본 전체에서 ID 단독 우연 일치1,159,305 keys가 있어도 submit을 추가하면0개이며 이를 실제 연결로 인정하지 않았습니다.

## 6. Fold별 RADDiT join rate는?

5개 fold의 TRAIN/CAL/VALID 모두 authorized join rate0%입니다. 분모와 >4h/>12h/>24h 및 GPU strata는 SEMANTIC_SUPPORT_METRICS.csv에 있습니다.

## 7. Long-job에서 join bias가 있는가?

Joined population 자체가0이므로 matched/unmatched runtime 차이나 semantic bias 효과를 추정할 수 없습니다. Long-job별 matched0 및 원래 unmatched 모집단 통계만 보고했습니다.

## 8. RADDiT embedding row mapping은 증명됐는가?

FALSE. 45개 chunk의 footer 총행수는1,780,972, historic trace는2,557,884입니다. 동일 순서를 가정하지 않았습니다. Source stop 이후 payload shared-field alignment는 미실행이며 ambiguous/missing count는 null로 남겼습니다. 45개 실제 파일의 SHA256은 별도 사본의 LFS OID와 일치합니다.

## 9. Embedding 생성에 actual runtime/end/power가 들어갔는가?

공개 job-string 생성 함수에는 actual runtime/START/END/power가 없었습니다. 이 범위에서 OUTCOME_INPUT_FOUND=FALSE입니다. 검색 DB의 별도 outcome column은 vector 생성 입력과 다릅니다. 비공개 배포 chunk 변환 이력까지 입증한 것은 아닙니다.

## 10. Embedding은 submission-time semantic proxy로 방어 가능한가?

공개 생성법은 submission semantic proxy 후보로 방어할 수 있습니다. 그러나 current trace의 물리 작업 대응·배포 vector provenance가 확정되지 않아 V14 입력으로 승인하지 않았습니다. Strict causal authority가 아닙니다.

## 11. New future job에서 embedding을 만들 수 있는가?

FALSE. 공개 LLM 생성 예시는 있지만 V42가 원 script/metadata와 동일 encrypted coordinate transform을 제공받는 경로는 입증되지 않았습니다. 역사적 lookup은 새 작업 provider가 아닙니다.

## 12. SVD32는 TRAIN only로 fit됐는가?

NOT_RUN_SOURCE_AUTHORITY_FAILURE. 원 Slurm↔RADDiT physical-job mapping이 입증되지 않아 §39에 따라 실행하지 않았습니다. SEM_SVD32 차원은32로 사전 고정했지만 reducer fit은0회입니다.

## 13. Semantic kNN은 end<t만 사용했는가?

NOT_RUN_SOURCE_AUTHORITY_FAILURE. 원 Slurm↔RADDiT physical-job mapping이 입증되지 않아 §39에 따라 실행하지 않았습니다. k=10과 END<t 조건은 계약에만 동결했으며 neighbor search를 실행하지 않았습니다.

## 14. Kestrel unused raw field 중 새로 usable한 것이 있었는가?

name/submit-line/script/workdir/job-type hash와 array 관련 column은 schema에 존재합니다. §39 stop으로 TRAIN cardinality/VALID unseen 통계를 새로 계산하지 않았고 새로운 static family를 승인하지 않았습니다. 미실행 값을0으로 채우지 않았습니다.

## 15. requeue/attempt authority를 찾았는가?

일반 Slurm 문서/예시는 있으나 검색한 로컬 권위에서 해당 V13 episode의 역사적 requeue/attempt ledger를 찾지 못했습니다. NOT_FOUND_IN_SEARCHED_LOCAL_AUTHORITY입니다.

## 16. job-step authority를 찾았는가?

job-step을 설명하는 sacct 문서는 있지만 해당 기간의 원 작업과 연결할 historical job-step record authority를 찾지 못했습니다.

## 17. PUE/IT-power는 같은 facility인가?

로컬 README는 ESIF 시설 PUE/IT-power임을 명시합니다. 같은 시설의 후보이나 facility-wide power를 Kestrel 전용 node telemetry로 간주하지 않았습니다.

## 18. PUE/IT-power 시간 범위가 folds와 겹치는가?

Footer ts 범위2015-11-10~2025-08-29는 달력상5개 fold와 겹칩니다. ts는 timezone-naive이며 UTC/ingestion timing이 확정되지 않아 정확한 시간 join 승인을 내리지 않았습니다. Power 값과 post-April runtime outcome은 읽지 않았습니다.

## 19. Facility feature는 backward-asof만 사용했는가?

NOT_RUN_SOURCE_AUTHORITY_FAILURE. 원 Slurm↔RADDiT physical-job mapping이 입증되지 않아 §39에 따라 실행하지 않았습니다. backward-asof만 허용한다는 규칙은 유지했고 실제 facility join은0회입니다.

## 20. GenAI dataset은 direct join 가능한가?

승인하지 않았습니다. 검사된 aggregated schema는 power[W], timestep[s]이며 공인 Slurm ID/절대 시각 연결이 없습니다. Catalog version2026-04-10은 수집 기간이2026-only라는 증거가 아니므로 그 주장은 하지 않았습니다.

## 21. Eagle을 Kestrel feature로 쓰지 않은 이유는?

Eagle은 별도 HPC system입니다. node telemetry가 존재해도 Kestrel 작업의 결측 feature를 채우는 데 사용하지 않았습니다.

## 22. J0 S0 reproduction은 정확한가?

TRUE. S0의5개 fold 전체 VALID Q50/Q90가 저장값과 bit-identical하고 V9 full VALID hazard parameters도 동일합니다. 새 fit은 없습니다.

## 23. J1 S4 reproduction은 정확한가?

TRUE. S4의5개 fold 전체 VALID Q50/Q90가 저장값과 bit-identical합니다. 두 baseline 각각234,036 VALID행을 확인했고 pooled exact-completed 평가는230,237행입니다.

## 24. J2 semantic-only incremental result는?

NOT_RUN_SOURCE_AUTHORITY_FAILURE. 원 Slurm↔RADDiT physical-job mapping이 입증되지 않아 §39에 따라 실행하지 않았습니다.

## 25. J3 semantic+state result는?

NOT_RUN_SOURCE_AUTHORITY_FAILURE. 원 Slurm↔RADDiT physical-job mapping이 입증되지 않아 §39에 따라 실행하지 않았습니다.

## 26. J4 semantic-neighbor result는?

NOT_RUN_SOURCE_AUTHORITY_FAILURE. 원 Slurm↔RADDiT physical-job mapping이 입증되지 않아 §39에 따라 실행하지 않았습니다.

## 27. J5 all-authorized result는?

NOT_RUN_SOURCE_AUTHORITY_FAILURE. 원 Slurm↔RADDiT physical-job mapping이 입증되지 않아 §39에 따라 실행하지 않았습니다.

## 28. 어느 정보 family가 min-fold를 가장 개선했는가?

평가 불가. 새 information family가 실행되지 않아 predictive contribution을 비교할 수 없습니다.

## 29. 어느 정보 family가 >4h를 가장 개선했는가?

평가 불가. J2-J0/J3-J1/J4-J3/J5-J4의 paired delta는 null이며 유효 paired jobs는0입니다.

## 30. pooled Q90는?

V14 selected model은 없습니다. 재현한 V13 S0/S4 pooled는91.74%/91.84%입니다. 미실행 challenger coverage를 생성하지 않았습니다.

## 31. min-fold는?

V13 S0/S4 재현 min-fold는66.47%/70.70%입니다. V14 신규 모델의 min-fold는 미측정입니다.

## 32. >4h/>12h/>24h는?

V13 S4 재현 >4h69.72%, >12h64.25%, >24h46.88%입니다. 이는 새 semantic 모델 성능이 아닙니다.

## 33. pinball은?

V13 S0/S4 재현 Q90 pinball은4923.74s/4752.76s입니다. J2–J5 값은 없습니다.

## 34. reservation ratio는?

V13 S4 재현 reservation/actual=3.392101, W0-relative=0.659856입니다. 새 semantic arm ratio는 미실행입니다.

## 35. short-job overreservation은?

V13 S4 재현 short-job GPUh 예약/실제=70.584847입니다. 새 arm 비교는 없습니다.

## 36. semantic improvement가 joined-subset bias 때문은 아닌가?

Semantic improvement를 주장하지 않았습니다. COMMON_JOINED_POPULATION은0행이고 FULL_V13_POPULATION baseline과 결측 범위만 유지했습니다.

## 37. C1을 실행했는가?

아니요. 신규 challenger가 미실행이며 기존 S0/S4도 C1 min-fold≥80% AND >4h≥80% 조건을 만족하지 못합니다.

## 38. TOTAL all-gate pass 후보가 있는가?

없습니다. Baseline은 기존 gate 실패를 재현했고 J2–J5는 성능 실패가 아니라 source-authority 미충족으로 미실행입니다.

## 39. Stage C가 실행됐는가?

V14의 Stage C unused-field 정밀 분석은 source stop 후 미실행입니다. 최종 flag의 legacy STAGE_C_AUTHORIZED(remaining/provider 단계)도FALSE입니다. 혼동하지 않도록 두 범위를 구분합니다.

## 40. Remaining model은 통과했는가?

NOT_RUN_SOURCE_AUTHORITY_FAILURE. 원 Slurm↔RADDiT physical-job mapping이 입증되지 않아 §39에 따라 실행하지 않았습니다. REMAINING_MODEL_RUN=FALSE, validation도FALSE입니다.

## 41. Provider는 new job에 callable한가?

새 provider를 만들지 않았고 new-job semantic callability를 입증하지 못했습니다.

## 42. April을 평가했는가?

아니요. April의 자료 지위는 EXPOSED_REGRESSION_ONLY이고 이번 평가는 미실행입니다.

## 43. April로 tuning했는가? 반드시 NO.

NO. April selection/tuning은 수행하지 않았습니다.

## 44. May를 열었는가? 반드시 NO.

NO. May의 runtime payload/labels/outcomes를 decode·요약·평가하지 않았습니다. 원 archive의 May member는 열지 않았고 path/schema inventory 및 전체 파일 hash는 record decoding과 구분했습니다.

## 45. V42 research provider로 승격 가능한가?

아니요. V42_RESEARCH_RUNTIME_PROVIDER_READY=FALSE입니다.

## 46. strict causal provider인가?

아니요. STRICT_CAUSAL_RUNTIME_PROVIDER_READY=FALSE, REQUEST_VERSION_AUTHORITY_FOUND=FALSE입니다.

## 47. V14도 실패했다면 다음으로 빠진 정보는 무엇인가?

V14는 semantic 성능검증에 실패한 것이 아니라 physical-job identity 연결을 확보하지 못한 forensic stop입니다. 우선 필요한 정보는 공인 Slurm↔RADDiT↔embedding crosswalk와 chunk export/timezone/ingestion 계약입니다.

## 48. 그 정보가 local raw에 있는가?

자료·source code·generic Slurm docs는 있으나 필요한 historical crosswalk/export receipt는 검색 범위에서 찾지 못했습니다. 관련24개 정보축의 로컬 근거와 미확인을 gap CSV/문서에 구분했습니다.

## 49. public source에서 추가로 찾은 후보는 무엇인가?

이번 mandatory stop에서 외부 신규 source 탐색은 실행하지 않았습니다. 모델 실패 이후 Stage G는 발동되지 않았습니다. 로컬에 저장된 공개 source 주소를 새 발견이나 검증으로 계산하지 않았습니다.

## 50. 최종적으로 무엇이 "알려진 한계"이고 무엇이 "미검증 가설"인가?

알려진 한계: positional ID, ID+submit exact join0, 미입증된 embedding row/export mapping, 미확인 new-job callability입니다. 미검증 가설: semantic/telemetry가 runtime robustness를 개선할 수 있는지입니다. 이번에 시험하지 않은 정보를 무용하다고 보거나 runtime randomness/예측 불가능/hidden-variable causality를 주장하지 않습니다.

검증 결과는 VERIFICATION.json, 입력/로컬 ledger/전달 파일 hash는 각 manifest에 있습니다. 초기 archive concat의 mixed timezone dtype 오류와 UTC 정규화 후 성공 로그를 모두 보존했습니다. Timestamp를 fitting하거나 근사 매칭하지 않았습니다.
