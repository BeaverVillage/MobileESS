from common import *
hist=read(ROOT/'GIT_DEEP_SEARCH_RECEIPT.json');replay=read(ROOT/'TRANSFORM_REPLAY_RECEIPT.json');src=read(ROOT/'PUBLIC_SOURCE_RECEIPTS.json');local=read(ROOT/'LOCAL_SEARCH_RECEIPT.json')
assert replay['TIMESTAMP_TRANSFORM_REPLAY_IDENTICAL'] and replay['MAPPING_REPLAY_IDENTICAL']
pipeline=read(ROOT/'EMBEDDING_PIPELINE_REPRODUCIBILITY.json')
hf=next(x for x in src['official_metadata_queries'] if 'huggingface' in x['url'])
pipeline['current_public_model_metadata']=hf.get('data');pipeline['current_head_proves_historical_resolved_revision']=False
write('EMBEDDING_PIPELINE_REPRODUCIBILITY.json',pipeline)
qdate=git('log','--all','--format=%H %cI %s','-S','2024-04-23','--','*.py','*.ipynb','*.md','*.json',cwd=RAD)
write('DATE_SIGNATURE_AUTHORITY_SEARCH.json',dict(signature='historic displayed end calendar date >= 2024-04-23',git_pickaxe_command='git log --all -S 2024-04-23 -- *.py *.ipynb *.md *.json',git_pickaxe_result=qdate,public_search='Exact RADDiT/date and encrypted_embeddings/April queries returned no relevant official export evidence',consumer_window='semantic_search.py uses 2024-08-01 to 2025-02-01; consumer iteration window is not the observed export cutoff',source_authority_found=False,membership_reconstructed=True))
write('DIAGNOSTIC_REPAIR_LOG.json',dict(issue='Initial calendar-date diagnostic used Timestamp.value (nanoseconds) against cached microseconds',repair='Explicit datetime64[us] conversion. Same predeclared observed date boundary; no threshold search.',independent_verification='verify.py compares datetime-valued original historic end_time directly against fixed-offset 2024-04-23 and checks exact member mask',prior_namespaces_modified=False))
level1=dict(status='NOT_APPROVED',provenance_grade='PARTIAL',criteria=dict(timestamp_transform_source_backed=False,deterministic_exact_diagnostic_replay=True,unique_raw_holdout_contradictions_zero=True,ambiguous_rows_explicit=True,no_fuzzy_matching=True,no_learned_time_offset=True,export_subset_provenance_sufficient_for_approval=False),raw_unique_candidates=1775514,ambiguous_rows=5458,unmatched_raw_embedding_keys=0,approved_mapping_rows=0,raw_membership_reconstructed_rows=1780972,raw_membership_date_signature='displayed end_time calendar date >= 2024-04-23',raw_membership_date_signature_exact=True,source_export_query_or_manifest_found=False,T0_consistent_unique=1775514,T1_consistent_unique=0,EMBEDDING_TO_RADDIT_MAPPING_PROVEN=False,TIMESTAMP_TRANSFORM_REPLAY_IDENTICAL=True,MAPPING_REPLAY_IDENTICAL=True,reason='Strong T0 metadata/DST and exact date-membership evidence do not establish the source operation or original export provenance. Level2 authorization remains closed.')
write('LEVEL1_MAPPING_AUDIT.json',level1)
flags=dict(STATUS='STOPPED_TIMESTAMP_EXPORT_AUTHORITY_UNRESOLVED',NEW_ML_FITS=0,V14R1_BASE_VERIFIED=True,HISTORIC_TIMESTAMP_AUTHORITY_RESOLVED=False,HISTORIC_STORED_ARROW_TIMEZONE_PROVEN=True,EMBEDDING_TIMESTAMP_AUTHORITY_RESOLVED=False,EMBEDDING_TIMESTAMP_TIMEZONE_METADATA_PRESENT=False,TIMESTAMP_TRANSFORMATION='UNRESOLVED',LEARNED_TIME_OFFSET_USED=False,ARBITRARY_OFFSET_SEARCH_USED=False,EMBEDDING_EXPORT_SCRIPT_FOUND=False,EMBEDDING_SUBSET_FILTER_AUTHORITY_FOUND=False,EMBEDDING_VECTOR_TRANSFORM_AUTHORITY_FOUND=False,EMBEDDING_TO_RADDIT_MAPPING_PROVEN=False,EMBEDDING_TO_RADDIT_MATCHED_ROWS=1775514,EMBEDDING_TO_RADDIT_AMBIGUOUS_ROWS=5458,EMBEDDING_TO_RADDIT_UNMATCHED_ROWS=0,EMBEDDING_MATCH_COUNT_SEMANTICS='T0 raw diagnostic candidates, not approved physical identity',APPROVED_LEVEL1_MAPPING_ROWS=0,EMBEDDING_PROVENANCE_GRADE='PARTIAL',RAW_SUBSET_MEMBERSHIP_RECONSTRUCTED=True,RAW_END_DATE_SIGNATURE_MEMBERSHIP_EXACT=True,EMBEDDING_ORDER_RELATION='UNPROVEN',LEVEL2_FINGERPRINT_RUN=False,RADDIT_TO_KESTREL_MAPPING_PROVEN=False,RADDIT_TO_KESTREL_UNIQUE_MATCHES=None,RADDIT_TO_KESTREL_AMBIGUOUS=None,NEGATIVE_CONTROLS_RUN=False,END_TO_END_CROSSWALK_PROVEN=False,V13_SEMANTIC_MAPPED_JOBS=None,V13_SEMANTIC_JOIN_RATE=None,GT4H_SEMANTIC_JOIN_RATE=None,GT12H_SEMANTIC_JOIN_RATE=None,GT24H_SEMANTIC_JOIN_RATE=None,AUTHORIZED_V13_MAPPING_ROWS=0,PUBLIC_LLM_PIPELINE_REPRODUCIBLE=False,DISTRIBUTED_VECTOR_TRANSFORM_REPRODUCIBLE=False,NEW_JOB_SEMANTIC_INPUT_AVAILABLE=False,NEW_JOB_EMBEDDING_PIPELINE_REPRODUCIBLE=False,NEXT_SEMANTIC_RUNTIME_ML_AUTHORIZED=False,RETROSPECTIVE_SEMANTIC_STUDY_POSSIBLE=False,RADDIT_PUBLIC_EMBEDDING_INPUT_OUTCOME_FREE=True,TIMESTAMP_TRANSFORM_REPLAY_IDENTICAL=True,MAPPING_REPLAY_IDENTICAL=True,APRIL_RUNTIME_EVALUATED=False,MAY_PAYLOAD_OPENED=False,V42_CHANGED=False,CC4_CHANGED=False,MESS_CHANGED=False,OPTIMIZER_CHANGED=False,OPENDSS_EXECUTED=False,EMBEDDING_VECTOR_PAYLOAD_DECODED=False,MODEL_DOWNLOADED=False,REEMBEDDING_ROWS=0,FUZZY_MATCHING_USED=False,STAGE_C_EXECUTED=False,PROVIDER_GENERATED=False,QUEUE_REPLAY_RUN=False)
write('FINAL_VERDICT.json',flags)
md('RADDIT_GIT_LINEAGE_SEARCH.md',f'''# Git lineage 조사

HEAD `ae1bf132addb41b469f3ef25a7626fe5ab06bc81`, reachable commits **{hist['commits']}**, 고유 source/document blobs **{hist['source_blobs']}**(.gitattributes 포함), main/pearc25/synthetic-trace-generator 3 branches, 태그 0개. `git fsck --unreachable --no-reflogs --connectivity-only`의 현재 local unreachable 객체는 **{len(hist['unreachable_objects'])}개**다. 원격에서 force-delete된 모든 과거 객체까지 존재하지 않는다는 뜻은 아니다.

| 명령·검색 | 파일/commit | 증거와 해석 | confidence / Q1–Q4 |
|---|---|---|---|
| log --all --oneline --decorate, --full-history --stat | 최초 0c71fa5 → ae1bf132 | 모든 reachable 이력과 commit messages를 기록 | 로컬 범위 높음, 생성 operation 미해소 |
| -S encrypted_embeddings, enc_embedding_int8 | semantic_search / validate_datasets notebook | 배포 파일을 읽는 consumer와 저장 dtype 출력 존재 | 소비/저장 상태 근거. Q2/Q3 미해소 |
| -S job_strings, historic_job_trace, 4096 | prep_for_embedding / embed_job_scripts | 4096행 순차 text batches → npy output | 공개 생성 경로 확인, 배포 export 미해소 |
| -S submit_time, FixedOffset | notebook source 및 stored outputs | FixedOffset(-360) historic와 naive embedding dtype가 함께 확인됨 | Q1 저장 representation 확인. 전환 operation 증명 아님 |
| -S tz_localize, tz_convert, timezone | 2026 tariff-aware code | 다른 데이터/파이프라인의 timezone 변환이다 | 이 2025 embedding export에 전용 불가 |
| -S to_parquet, 40000, targeted git grep | reachable source/notebook | 관련 chunk의 40,000행 크기는 출력에 존재하나 이를 생성하는 writer는 미확인 | Q2/Q3 미해소 |
| log --name-status --find-renames, git diff initial..HEAD | scripts/notebooks의 energy_aware_scheduling 이동 및 삭제된 quickstart output | rename/delete 전 source blob도 포함하여 검사 | 누락된 writer를 찾지 못함 |
| git show/cat-file notebook blobs | validate_datasets의 여러 버전 | {hist['notebook_cells_inspected']} cells와 {hist['stored_outputs_inspected']} output records 검사, 관련 evidence 28행 | source뿐 아니라 text/html/plain 출력 검사. 이미지 MIME {hist['image_output_mime_blocks_not_decoded']}개는 decode하지 않음 |
| LFS 역사 | historic 1개 + chunks 45개 | 46 paths, 46 distinct version records. 각 path는 공개 이력에서 한 LFS OID | 교체/과거 schema 변화의 근거 없음. 전역 부재 주장 아님 |
| -S 2024-04-23 | 모든 source/notebook/json 이력 | 관측된 end-date membership signature의 literal 검색은 빈 결과 | signature는 관측적이며 Q3 export authority 미해소 |

각 명령의 전체 output, blob OID·commit/path 참조는 GIT_DEEP_SEARCH_RECEIPT.json에 있다. NOTEBOOK_PROVENANCE_EVIDENCE.csv의 supports_*는 검색 lead이며 자동 승인 flag가 아니다. Raw Git 저장소에는 fetch/checkout/gc/쓰기 작업을 하지 않았다. 역사 LFS 대용량 download도 없다.''')
md('EMBEDDING_EXPORT_PIPELINE_FORENSIC.md','''# 배포 export 경로

확인한 경로는 historic → 8개 필드 문자열 → 4096행 batch JSON → Linq embedding → batch별 npy다. 배포 파일은 40,000행 단위 Parquet이며 마지막만 20,972행이다. 공개 npy output을 이어 붙여 metadata와 join하고 subset/filter·timezone 제거·vector transform을 적용한 뒤 chunk Parquet를 쓰는 operation은 조사한 source/history에 없다.

qint8 코드는 모델 weight quantization이다. 그것을 enc_embedding_int8 배포 열의 변환 코드라고 해석하지 않았다. embedding, concat, merge/join, dropna, script, runtime/power, encrypt/int8, write_parquet/to_parquet, 40000/4096, timezone 계열을 Git source와 notebook 저장 출력에서 확인했다. 서로 다른 tariff-aware code의 변환을 가져오지 않았다.

45개 footer 모두 timestamp[us], 물리 INT64, logical isAdjustedToUTC=false이며 timezone metadata가 없다. created_by는 parquet-cpp-arrow 16.1.0이다. 이 값은 writer engine 식별에 도움이 되지만 export script·모델 라이브러리 버전을 증명하지 않는다. Historic의 -06:00 metadata와 notebook FixedOffset(-360)은 저장된 표현의 근거다. 어떤 함수가 언제 제거했는지는 미해결이다.

새 진단: T0 EKEY2는 1,775,514개의 충돌 없는 유일 raw 후보를 유지한다. T1 EKEY0는 embedding 11행과 키가 겹치지만 유일 8쌍 모두 holdout 충돌, EKEY1의 유일 1쌍도 충돌, EKEY2는 0이다. DST 구간 20개 표본도 T0만 일치한다. 성능/일치율로 T0를 승인하지 않았다.

Historic 표시 종료일 >= 2024-04-23이라는 관측적 predicate가 1,780,972행의 raw metadata membership과 정확히 일치한다. 이는 단순 count equality를 넘어서는 결과이나 실제 source export query의 존재·동작·동기·timezone 처리까지 보증하지 않는다. 해당 날짜의 Git 및 targeted public follow-up에서도 source rule은 미확보다.

필요한 원본 자료: 사용한 historic revision과 source timezone 계약, 실제 .npy→encrypted Parquet export script/commit 또는 run manifest, 날짜/subset predicate와 row membership, model/tokenizer/library revisions, encrypted/int8 coordinate transform의 정의. 현재 provenance grade는 PARTIAL이며 source-backed timestamp 조건이 충족되지 않아 Level1을 승인하지 않는다.''')
md('SUBSET_FILTER_FORENSIC.md','''# 부분집합 재구성과 출처 근거

2,557,884 historic 행의 raw EKEY2 membership은 배포 1,780,972행과 집합 및 key multiplicity 수준에서 재구성된다. 유일 후보 1,775,514, ambiguous member 5,458, 비포함 776,912행을 분리했다.

**관측된 표시 종료일 >= 2024-04-23** predicate는 배포 raw membership과 행 단위로 정확히 같다. 관측 member end-time envelope(2024-04-23 00:01:25–2025-03-10 04:19:04)도 같다. 단지 행수만 맞춘 것이 아니다. cached membership mask 전체와 비교하며 검증 시 원본 historic의 timezone-aware end_time으로 별도 계산한다. 날짜 signature는 등록한 관측 envelope 진단에서 도출했으며 임의 threshold 조합 검색은 하지 않았다. 정확한 export 코드/manifest 또는 독립된 실행 기록은 여전히 없다. 따라서 RAW_SUBSET_MEMBERSHIP_RECONSTRUCTED=TRUE와 EMBEDDING_SUBSET_FILTER_AUTHORITY_FOUND=FALSE를 구분한다.

다른 단일 후보들은 membership을 재현하지 못했다. Submit envelope는 2,156,714행, start envelope는 1,799,429행을 남긴다. Script nonnull은 2,421,026행을 남기고 136,858행을 제외한다. raw member에도 script null 120,141행이 있어 missing-script 제거 규칙은 실제 membership 설명과 맞지 않는다. Runtime/power는 모든 historic 행에서 nonnull·positive이고 시각 순서도 유효하다. 이를 상위 원본 수집 이전에도 결측이 없었다는 증거로 확대하지 않는다.

전체 29개 조건 중 28개 수치 진단을 했고 2개의 종료일/envelope 표현이 exact membership을 재현했다. CPU/GPU restriction은 직접 flag가 없어 NOT_TESTABLE이다. 익명 partition token을 CPU/GPU 의미로 추정하지 않았다. 월·partition·QoS·job_type 빈도는 설명용 enrichment로 보존했다. Unique raw와 나머지를 비교했으며 V13 semantic-runtime bias 분석을 실행한 것은 아니다.

R2 calendar-date predicate의 초기 ns/us 단위 실수는 명시적 datetime64[us] 변환으로 수정하고 독립 datetime 비교로 검증했다. Threshold 자체를 바꾸지 않았으며 기존 V6–V14R1 파일은 수정하지 않았다. 원본 row-order를 사용해 중복을 해결하지 않는다.''')
answers=[
'naive embedding timestamp가 historic -06:00과 어떤 source operation으로 연결되는지 미입증이었다. 99.6935% raw 후보는 physical-instant authority가 아니었다.',
'허용된 T1 비교, DST 예시, notebook 저장 출력, reachable/unreachable Git·rename/delete·LFS 이력, local intermediates, 날짜 membership·결측 signature, 공식 public metadata와 V42 Arrival interface를 새로 조사했다.',
'저장 Arrow timezone은 고정 -06:00이다. Notebook output의 pytz.FixedOffset(-360)도 일치한다. America/Denver DST zone이나 upstream 수집 timezone으로 추정하지 않았다.',
'45개 모두 timestamp[us], Parquet 물리 INT64 및 isAdjustedToUTC=false다.',
'없다. EMBEDDING_TIMESTAMP_TIMEZONE_METADATA_PRESENT=FALSE. Writer footer는 parquet-cpp-arrow 16.1.0이지만 timezone 제거 구현을 설명하지 않는다.',
'T0의 EKEY0/1/2 모두 embedding 1,780,972행에 키가 있다. 유일 1:1은 각각 1,380,258 / 1,504,066 / 1,775,514행이며 유일 후보 holdout 충돌은 모두 0이다.',
'T1은 EKEY0: matched embedding 11행, 유일 8쌍 전부 충돌, ambiguous 3행. EKEY1: 1행·유일 1쌍·충돌 1. EKEY2: 0행. 따라서 충돌 없는 유일 후보는 모두 0이다.',
'실제 배포 변환으로 source-backed인 것은 아직 없다. T0는 강하게 지지되는 진단 가설이고 최종 TIMESTAMP_TRANSFORMATION=UNRESOLVED다.',
'등록한 DST 주변 20개 raw-candidate 표본 모두 표시 local wallclock에만 일치한다. 후보 없는 10개 날짜도 명시했다. 이는 T0 지지 증거지만 원래 stripping operation의 증거가 아니다.',
'NO. T0/T1 두 명시적으로 허용된 serialization 가설만 검사했다. arbitrary offset 또는 성능 기반 offset 탐색은 없다.',
'아니다. 공개 npy 생성 단계와 배포 chunk consumer 사이의 exporter는 찾지 못했다.',
'아니다. qint8는 공개 모델 weight quantization이며 배포 vector encryption/int8 변환과 구분했다.',
'아니다. 40,000행이라는 stored output/footer는 확인했지만 그 크기로 쓰는 생성 코드는 미확보다.',
'관측적 membership 규칙은 찾았다: historic 표시 종료일 >= 2024-04-23이면 정확히 1,780,972행이고 제외는 776,912행이다. 원본 export query가 이 predicate였다는 authority는 미입증이다.',
'행수뿐 아니라 전체 row membership이 일치한다. 그러나 실제 exporter/실행 manifest의 독립 근거가 없어 source-authority flag는 FALSE다.',
'Raw EKEY2 집합 및 group multiplicity 수준에서는 1,780,972행을 재구성할 수 있다. 중복 그룹 안에서 특정 vector row의 historic row를 유일하게 지정하는 것은 별개다.',
'아니다. 1,775,514개의 raw 유일 후보를 보존했으나 Level1 승인 행수는 0이다.',
'줄지 않았다. 2,514그룹, 5,458행이다. 그룹 크기 2/3/4/5/6/7에 해당하는 그룹 수는 2,167/287/42/14/3/1이다.',
'NO. 공유 필드를 모두 검사했으나 추가 non-vector field가 없고 start_time도 중복에서 같아 그대로 ambiguous로 남겼다.',
'최종 UNPROVEN. R1 raw unique 후보의 인접 역전 636,834, 전체 역전 쌍 66,906,351이다. raw reorder 증거를 승인 mapping 순서로 승격하지 않았다.',
'FALSE. source-backed timestamp와 충분한 original export provenance 조건이 충족되지 않았다.',
'PARTIAL. 단순 UNPROVEN으로 강한 metadata 증거를 지우지 않았고, source-backed transform이 없는 상태를 STRONGLY_SUPPORTED/PROVEN으로 올리지 않았다.',
'NO. 조건부 Level2 authorization이 닫혀 F0–F2를 실행하지 않았다.',
'NOT_RUN, null이다. 관측된 zero-match가 아니다.',
'NOT_RUN, null이다.',
'NOT_RUN, null이다.',
'Kestrel physical unique count는 미측정(null)이다. 승인된 end-to-end assignment는 없다.',
'T0 EKEY0–2 unique holdout 충돌은 0. T1 EKEY0는 8, EKEY1은 1, EKEY2는 비교쌍 0. Kestrel holdout은 NOT_RUN이다.',
'Negative controls는 NOT_RUN이다. T1 진단을 Kestrel NC1–3 실행으로 간주하지 않았다.',
'FALSE. Level1 미승인, Level2 미실행이다.',
'승인된 V13 연결은 0건이며 실제 가능한 개수/비율은 미측정(null)이다. 621,583개 GPU 작업에 새 physical join을 수행하지 않았다.',
'NOT_RUN, null이다. 이전 결과나 추정값을 새 support로 채우지 않았다.',
'NOT_RUN, null이다.',
'NOT_RUN, null이다.',
'NOT_RUN, null이다.',
'V13 end-to-end joined/unjoined bias는 미평가다. Historic raw subset의 missingness·월·범주 enrichment만 기술했으며 인과성을 주장하지 않는다.',
'공개 8-field render 함수의 직접 입력 범위에서는 TRUE다. runtime/end/power는 문자열에 없지만 상위 job_type 생성 시점과 비공개 export까지 attestation한 것은 아니다.',
'PARTIAL. Metadata·LFS payload identity·date membership·public text generation은 확보했고 원래 timezone strip/export/encryption operation은 미해결이다.',
'현재 SubmissionRuntimeRequest whitelist와 policy.Arrival에서 partition/qos 2개다. response_policy.ObservedJob도 정적으로 확인했다.',
'user, account, job_type, name, submit_line, script 6개다. workload_class가 job_type과 동일하다는 근거는 없다.',
'user/account/name/submit_line/script는 accepted submission 때 실제로 capture하도록 설계할 수 있다. job_type은 submit-only 분류 규칙의 별도 authority가 필요하다. 현재 구현이나 관측시점 인증이 있다는 주장은 아니다. 개인정보·sanitization 및 동일 표현 계약도 필요하다.',
'현재 공개 model HEAD 0c1a0b0589177079acc552433cad51d7c9132379(lastModified 2024-06-05)는 확인했다. RADDiT 생성 실행이 resolve한 model/tokenizer revision 및 transformers/quanto 버전은 고정된 기록이 없어 미입증이다.',
'FALSE. Weight qint8·last-token pooling·L2 normalization·2048 truncation은 공개 코드에서 확인하지만 배포 encrypted/int8 transform은 없다. Model download/re-embedding은 0이다.',
'유력한 raw 후보와 membership 복원은 가능하다. 승인된 historical crosswalk는 아직 FALSE이며 원본 timestamp/export authority가 필요하다.',
'현재 계약과 동일 배포 representation 기준 FALSE다. 6개 입력 누락과 불명확한 vector transform이 남아 있다.',
'FALSE. Level1/Level2·controls·temporal/tail support·bias·new-job input/representation 조건을 충족하지 못했다. Retrospective study 승인도 아직 없다.',
'예. NEW_ML_FITS=0. 학습·SVD·semantic kNN prediction·calibration·remaining/queue/provider/V42 등을 실행하지 않았다.',
'NO. April runtime 평가 없음. 2024년 과거 날짜 signature를 조사한 것을 2025년 holdout April 평가와 혼동하지 않는다.',
'NO. May runtime payload 미개봉. Footer·Git/source/notebook metadata 조사와 pre-April RADDiT projection만 사용했다.',
'사실: 저장 timezone 차이, T0/T1 diagnostic counts, exact 종료일 membership, 동일 replay, ambiguous 5,458행, 1-version LFS history, V42 6-field gap. 가설/미입증: 실제 stripping 함수, exporter가 사용한 cutoff/query, 원래 model/env/vector transform, Kestrel identity 및 semantic Runtime 성능. 의미 정보가 무용하다는 결론은 아니다.'
]
request=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig');section=request.split('32. FINAL REPORT QUESTIONS')[1].split('33. FINAL FLAGS')[0]
questions=re.findall(r'^\d+\. (.+)$',section,re.M)
assert len(questions)==len(answers)==50,(len(questions),len(answers))
md('FINAL_REVIEW_KO.md','# Runtime-vNext14R2 최종 검토\n\n**STOPPED_TIMESTAMP_EXPORT_AUTHORITY_UNRESOLVED. NEW_ML_FITS=0.**\n\n새 결과는 T1 EKEY2=0, T0 지지 DST 진단, notebook dtype 확인, 그리고 **표시 종료일 >= 2024-04-23의 exact raw subset membership**이다. 실제 export/stripping authority가 없어 Level1은 미승인이고 Level2는 미실행이다.\n\n'+'\n\n'.join(f'## {i}. {q}\n\n{a}' for i,(q,a) in enumerate(zip(questions,answers),1)))
md('README.md','''# Runtime-vNext14R2 timestamp/export authority

Base: V14R1 Draft PR #87, `604aaefd8c6a23a68a34544411125c934144cb2e`.

결과는 STOPPED_TIMESTAMP_EXPORT_AUTHORITY_UNRESOLVED, provenance PARTIAL, NEW_ML_FITS=0이다. T0 EKEY2의 유일 raw 후보 1,775,514행과 ambiguous 5,458행을 보존했다. 새 T1 EKEY2는 0행이며 약한 key에서의 유일 후보는 모두 holdout 충돌이었다.

새로 historic의 **표시 종료일 >= 2024-04-23**이 1,780,972 raw subset membership과 행 단위로 정확히 일치함을 확인했다. 실제 exporter의 predicate·timezone stripping 코드/manifest는 찾지 못해 승인 기준을 낮추지 않았다. 21개 commits, 43개 source/doc blobs, 59개 notebook outputs, local 616개 text files 및 공식 공개 metadata를 조사했다. 46개 LFS 경로는 각 1개 버전이고 unreachable 객체는 현재 local에서 0개였다.

읽기 순서: FINAL_REVIEW_KO.md(50문항), FINAL_VERDICT.json, LEVEL1_MAPPING_AUDIT.json, TIMESTAMP_TRANSFORMATION_TESTS.csv, SUBSET_FILTER_FORENSIC.md. 각 세부 CSV·JSON·source/local/delivery manifests를 함께 제공한다. Level2·negative controls·V13 support/bias는 gate 미통과로 NOT_RUN이다. 미측정 값을 0으로 만들지 않았고 성공 crosswalk 파일은 없다.

재현 코드는 PyArrow projected columns와 R1 hash-verified numeric caches를 재사용한다. `transforms.py --replay`는 fresh process에서 seed1402 chunk permutation 후 canonical sorting 및 diagnostic mapping을 검증한다. `date_signatures.py`는 등록된 관측 date-envelope 진단을 처리한다. V14R1 exact join helper는 pure function으로만 재사용하며 이전 namespace의 entry point를 실행하거나 파일을 쓰지 않는다.

큰 diagnostic ledgers/logs는 .local에 보존하고 hash만 Git에 넣는다. 벡터 decode·모델 다운로드·re-embedding·runtime training/inference·April/May evaluation·V42 실행/변경은 없다. 다음 자료는 원본 export script/commit 또는 실행 manifest, timestamp/source timezone 계약, exact subset/query와 row IDs, model/tokenizer/library revision 및 encrypted vector transform이다.''')
# CSV counts remain integers; missing observations remain empty.
for name,cols in [('SUBSET_FILTER_CANDIDATES.csv',['historic_kept','historic_removed']),('NOTEBOOK_PROVENANCE_EVIDENCE.csv',['cell_index','execution_count'])]:
    d=pd.read_csv(ROOT/name)
    for c in cols:d[c]=d[c].astype('Int64')
    d.to_csv(ROOT/name,index=False)
print('FINALIZED',len(questions),'questions; Level1 FALSE, Level2 NOT_RUN')
