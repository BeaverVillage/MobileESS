from common import *
import csv
def md(name,text):(ROOT/name).write_text(text.rstrip()+'\n',encoding='utf-8')
def table(name,rows):pd.DataFrame(rows).to_csv(ROOT/name,index=False)
a=read(ROOT/'EMBEDDING_EXACT_AUDIT_DETAIL.json');s=a['stats'][-1];order=read(ROOT/'EMBEDDING_ORDER_AUDIT.json')
assert read(ROOT/'EMBEDDING_FRESH_PROCESS_REPLAY.json')['pass_replay']
status='STOPPED_LEVEL1_TIMESTAMP_AUTHORITY_UNRESOLVED'
nr='NOT_RUN_LEVEL1_AUTHORITY_FAILURE'
flags=dict(STATUS=status,NEW_ML_FITS=0,V14_BASE_VERIFIED=True,EMBEDDING_TOTAL_ROWS=1780972,RADDIT_HISTORIC_TOTAL_ROWS=2557884,
 EMBEDDING_TO_RADDIT_MAPPING_PROVEN=False,EMBEDDING_TO_RADDIT_MATCHED_ROWS=s['unique_1to1'],EMBEDDING_TO_RADDIT_AMBIGUOUS_ROWS=s['ambiguous_embedding_rows'],EMBEDDING_TO_RADDIT_UNMATCHED_ROWS=0,
 EMBEDDING_MATCH_COUNT_SEMANTICS='MATCHED_ROWS counts unique RAW_REPRESENTATION diagnostic candidates, not authorized UTC physical links; ambiguous rows excluded. All three counts partition embedding population.',EMBEDDING_AUTHORIZED_MAPPING_ROWS=0,
 EMBEDDING_ORDER_RELATION='UNPROVEN',EMBEDDING_SUBSET_FILTER_AUTHORITY_FOUND=False,RADDIT_TO_KESTREL_MAPPING_PROVEN=False,RADDIT_TO_KESTREL_MATCHED_ROWS=0,RADDIT_TO_KESTREL_AMBIGUOUS_ROWS=0,
 RADDIT_KESTREL_STATUS=nr,RADDIT_KESTREL_OBSERVED_PHYSICAL_MATCHES=None,RADDIT_KESTREL_OBSERVED_AMBIGUOUS_ROWS=None,RADDIT_KESTREL_COUNT_SEMANTICS='Integer flags count authorized assignments only. The physical test was NOT_RUN, not an observed zero-match failure.',
 END_TO_END_CROSSWALK_PROVEN=False,V13_SEMANTIC_MAPPED_JOBS=0,V13_SEMANTIC_JOIN_RATE=0.0,V13_GT4H_SEMANTIC_JOIN_RATE=None,V13_GT12H_SEMANTIC_JOIN_RATE=None,V13_GT24H_SEMANTIC_JOIN_RATE=None,
 SEMANTIC_SUPPORT_CLASS='NO_SUPPORT',SEMANTIC_SUPPORT_MEANING='No authorized end-to-end support in this run, not evidence that semantic information is useless.',RADDIT_PUBLIC_EMBEDDING_INPUT_OUTCOME_FREE=True,DISTRIBUTED_EMBEDDING_EXPORT_PROVENANCE='PARTIAL',HISTORICAL_EMBEDDING_CROSSWALK_PROVEN=False,
 NEW_JOB_SEMANTIC_INPUT_AVAILABLE=False,NEW_JOB_EMBEDDING_PIPELINE_REPRODUCIBLE=False,NEXT_SEMANTIC_RUNTIME_ML_AUTHORIZED=False,APPROXIMATE_MATCHING_USED=False,LEARNED_TIME_OFFSET_USED=False,FUZZY_MATCHING_USED=False,APRIL_RUNTIME_EVALUATED=False,MAY_PAYLOAD_OPENED=False,V42_CHANGED=False,CC4_CHANGED=False,MESS_CHANGED=False,OPTIMIZER_CHANGED=False,OPENDSS_EXECUTED=False,
 EMBEDDING_VECTOR_PAYLOAD_DECODED=False,STAGE_C_EXECUTED=False,PROVIDER_EXECUTED=False,QUEUE_REPLAY_EXECUTED=False,NEW_MODEL_INFERENCE_RUN=False)
write('FINAL_VERDICT.json',flags)
write('CROSSWALK_RECOVERY_SUMMARY.json',dict(status=status,base=BASE,level1=dict(raw_metadata_matches=1780972,unique_raw_candidates=1775514,ambiguous_raw_rows=5458,no_raw_key_match=0,unique_ratio=1775514/1780972,holdout_conflicts=0,float_binary_conflicts=0,fresh_process_replay=True,authorized=False,blocker='Naive embedding timezone/export semantics unresolved under preregistered source-authority rule'),level2=dict(status=nr,observed_matches=None,authorized_matches=0),order=order,missing_filter_authority=False,stop_authority='USER_REQUEST.txt sections 8,16,25A; PREREGISTRATION timestamp and Level1 proof contract',success_crosswalk_files_created=False,next_ml_authorized=False))
lineage=[]
def lin(c,k,r,uk,ur,tm,av,eq,reason):lineage.append(dict(canonical_concept=c,kestrel_field=k,raddit_field=r,unit_kestrel=uk,unit_raddit=ur,time_semantics=tm,availability_semantics=av,exactly_comparable=eq,reason=reason))
for c in ['submit_time','start_time','end_time']:lin(c,c,c,'timestamp us with stored offset','timestamp us fixed -06:00','UTC from stored offset only','archived event record; end is outcome',True,'F0 planned, not run. Embedding is naive and separately unresolved.')
for c,k,r,uk,ur in [('actual_runtime','wallclock_used','wallclock_used_sec','duration ns','seconds float64'),('requested_walltime','wallclock_req','wallclock_req_sec','duration ns','seconds float64'),('requested_nodes','nodes_req','nodes_req','count','count'),('requested_processors','processors_req','processors_req','count','count')]:lin(c,k,r,uk,ur,'No time shift','archive value; submission-time version not certified',True,'F1/F2 planned unit conversion; equality/lineage not yet measured')
lin('requested_memory','memory_req','memory_req_raw','Slurm string with scope suffix','undocumented numeric','NA','archive request',False,'No proven unit and per-node/per-CPU scope mapping. F3 disabled.')
for k,r in [('qos','qos'),('partition','partition'),('account_hash','account'),('user_hash','user'),('name_hash','name'),('submit_script_hash','script'),('submit_line_hash','submit_line'),('job_type_hash','job_type')]:lin(r,k,r,'anonymized token/hash','sanitized categorical token/text','NA','public prep inputs; job_type derivation timing not certified',False,'No shared anonymization/token crosswalk authority; never force equality. F4 disabled.')
lin('identity','id / job_id','job_id','source composite identity / Slurm integer','0-based historic row position','NA','identity only',False,'All 2557884 historic job_id values equal row position; excluded from linkage keys.')
lin('average_power','consumed_energy_*','avg_power_per_node','energy units, multiple measurement definitions','power per node','post-completion','outcome field',False,'No direct equally-defined power field established; not a Kestrel key.')
table('FIELD_LINEAGE_MAP.csv',lineage)
table('RADDIT_KESTREL_FINGERPRINT_AUDIT.csv',[dict(key=f'F{i}',status=nr if i<3 else 'NOT_ELIGIBLE_FIELD_AUTHORITY_UNPROVEN',matched_rows=None,unique_1to1=None,ambiguous_rows=None,kestrel_duplicate_key_rate=None,raddit_duplicate_key_rate=None,unused_field_contradictions=None,reason='Level1 gate closed' if i<3 else 'Memory scope or categorical-token authority absent') for i in range(5)])
table('RADDIT_KESTREL_MATCH_CONSISTENCY.csv',[dict(field=c,status=nr,compared_pairs=None,contradictions=None) for c in ['runtime_arithmetic','request_shape','memory','qos','partition','account','semantic_tokens']])
table('NEGATIVE_CONTROL_MATCH_AUDIT.csv',[dict(control=n,definition=d,seed=1401,fingerprint='F2',status=nr,TRUE_EXACT_MATCHES=None,NEGATIVE_CONTROL_MATCHES=None) for n,d in [('NC1','submit timestamp +1 second'),('NC2','requested walltime permuted within UTC submit date'),('NC3','runtime permuted within UTC submit date')]])
coverage=[dict(scope='V13_ALL',stratum='ALL',denominator=621583,authorized_mapped_jobs=0,authorized_join_rate=0.0,physical_coverage_measured=False,status='NO_AUTHORIZED_CROSSWALK')]
for fold in range(1,6):
    for role in ['TRAIN','CAL','VALID']:coverage.append(dict(scope=f'fold{fold}',stratum=role,denominator=None,authorized_mapped_jobs=None,authorized_join_rate=None,physical_coverage_measured=False,status=nr))
for st in ['<=4h','>4h','>12h','>24h','GPU_BUCKET','REQUESTED_WALLTIME_BUCKET','QOS','PARTITION','S0_ERROR_STRATA']:coverage.append(dict(scope='V13_STRATA',stratum=st,denominator=None,authorized_mapped_jobs=None,authorized_join_rate=None,physical_coverage_measured=False,status=nr))
table('SEMANTIC_SUPPORT_COVERAGE.csv',coverage)
table('SEMANTIC_JOIN_SELECTION_BIAS.csv',[dict(metric=c,status=nr,matched_value=None,unmatched_value=None,reason='No authorized end-to-end population; no new model prediction') for c in ['runtime_distribution','requested_walltime','gpu','qos','partition','gt4h_fraction','gt12h_fraction','gt24h_fraction','temporal_fold_distribution','S0_prediction_error','S4_prediction_error']])
md('SEMANTIC_JOIN_SELECTION_BIAS_KO.md','''# Selection bias 평가 상태

NOT_RUN_LEVEL1_AUTHORITY_FAILURE. V13 GPU 621,583건에 승인된 end-to-end 연결이 없어 matched/unmatched 비교 모집단을 만들지 않았다. 전체 0%는 승인된 연결 비율이며 물리적으로 대응 가능한 행이 0개라는 관측값이 아니다. Fold 및 tail join rate는 null이다. S0/S4 기존 예측을 다시 실행하거나 새 모델을 학습하지 않았다.

Embedding raw metadata의 historic 부분집합은 1,780,972행이고 나머지 776,912행이 제외되어 있다는 집합 수준의 증거는 확보했다. 이 선택이 V13 GPU 또는 장기 작업에 편향되는지는 아직 모른다. CPU-exclusive 결과라는 README 설명을 실제 export filter로 대입하지 않았다. 현재 결과로 selection bias의 부재·크기·인과관계를 주장할 수 없다.''')
md('EMBEDDING_SUBSET_FILTER_FORENSIC.md',f'''# Embedding 부분집합 forensic

Historic 2,557,884행, embedding 1,780,972행, 차이 776,912행. EKEY2의 RAW_REPRESENTATION 키 집합은 historic의 정확히 1,780,972행과 대응한다. 키가 있는 모든 그룹의 양쪽 multiplicity도 일치한다. 이것은 어떤 metadata 부분집합이 배포됐는지에 대한 강한 진단 증거이며, 왜 그 행들을 골랐는지에 대한 근거는 아니다.

고유 후보는 1,775,514행(99.693538%); 나머지 5,458행은 2,514개 many:many 그룹이다. 공유 5개 필드를 모두 비교해도 이 그룹 수는 2,514개라서 start_time으로 개별 중복 행을 해소할 수 없다. 유일 후보의 float64 runtime/power bitwise 충돌은 0이고, start_time 충돌도 0이다.

고유 후보 source index 범위와 순서는 EMBEDDING_ORDER_AUDIT.json에 기록했다. 인접 역전 {order['adjacent_inversions']:,}건, 직접 prefix 아님, 연속 suffix 아님. 집합의 최소 historic index는 {order['set_member_min']:,}, 최대는 {order['set_member_max']:,}다. source index gap 합은 유일 후보 사이의 양의 차이를 합한 통계이므로 빠진 historic 행 776,912개와 혼동하지 않는다. 순서를 이용해 중복을 임의 배정하지 않았다.

조사 범위는 모든 로컬 reachable 21 commits, 3 remote branches, 태그 0개, 42 unique source/doc blobs, 삭제 이력, notebook code/markdown, LFS 포인터 이력이다. public prep는 전체 historic를 4096행 배치로 순차 처리한다. 소비 코드는 40,000행 chunk에 새 row_id를 매긴다. 두 단계 사이의 subset/export/encryption 구현은 찾지 못했다. 배포 payload SHA256과 Git LFS OID가 맞는다는 V14 증거는 파일의 동일성만 보증한다.

null/missing script, power availability, completion/runtime validity, date, CPU-exclusive, usable text, embedding failure, token length를 source code/document에서 조사했다. 공개 token max_length=2048는 truncation이고 특정 historic subset 제외 규칙의 증거가 아니다. README의 CPU-exclusive power 성과 역시 이 776,912행의 filter authority가 아니다. 누락 행수와 우연히 맞는 조건을 탐색해 규칙으로 채택하지 않았다.

EMBEDDING_SUBSET_FILTER_AUTHORITY_FOUND=FALSE. 필요한 자료는 chunk-global-row→original historic-row manifest, source export query와 filter/version, timestamp timezone 제거 계약, 동일 encrypted vector transform의 버전·설정이다. 부분집합이 존재한다는 결과와 배포 생성 경로의 완전한 입증은 별개다.''')
answers=[
('V14는 왜 중단됐는가?','식별자·source authority 실패로 중단됐다. Semantic challenger가 학습되어 실패한 결과가 아니다.'),
('이번 V14R1에서 무엇을 새로 조사했는가?','45개 chunk의 공유 metadata만 projection하여 EKEY0–2 exact collision·holdout·bitwise equality·재시작 replay·순서를 검사하고 Git 전체 reachable source 이력과 targeted public lineage를 조사했다.'),
('RADDiT job_id는 원 Slurm ID인가?','아니다. 2,557,884행 모두 0-based historic 행번호와 같다. 연결 키에서 제외했다.'),
('public prep_for_embedding은 어떤 순서로 row를 처리하는가?','historic를 읽은 순서로 4096행 연속 배치한다. 배포 chunk 순서가 같다는 증명은 아니다.'),
('embedding 생성 문자열에는 어떤 정보가 들어가는가?','user, account, partition, job_type, name, qos, submit_line, script의 8개 필드다.'),
('실제 runtime/end/power가 embedding text에 들어가는가?','검사한 public render/generation 코드에는 들어가지 않는다. 검색 DB의 outcome metadata와 생성 문자열을 구분했다. 비공개 배포 export까지 attestation한 것은 아니다.'),
('distributed embedding chunk 총 행수는?','45개 chunk, 1,780,972행이다. 첫 44개는 각각 40,000행, 마지막은 20,972행이다. 벡터를 decode하지 않았다.'),
('historic trace와 왜 행수가 다른가?','Historic 2,557,884행 중 776,912행 차이가 있다. EKEY2 raw metadata 부분집합은 확인했으나 제외 이유는 미입증이다.'),
('embedding→historic exact match는 몇 개인가?','RAW_REPRESENTATION 키 존재는 1,780,972행 전부다. EKEY2 유일 후보는 1,775,514행, ambiguous 5,458행, 키 unmatched 0행이다. UTC 의미가 미입증이므로 승인 crosswalk 행수는 0이다.'),
('어떤 exact key가 가장 강한가?','EKEY2(submit+end+runtime+power)가 가장 많은 collision을 구분했다. 이는 coverage로 key를 선택했다는 뜻이 아니다. source-authority가 닫혀 최종 승인 key는 NONE이며 EKEY0부터 작은 유일 key를 검토한다는 계약을 유지했다.'),
('unique 1:1 비율은?',f"EKEY0 {a['stats'][0]['unique_1to1']:,}, EKEY1 {a['stats'][1]['unique_1to1']:,}, EKEY2 1,775,514 / 1,780,972 = {1775514/1780972:.8%}다. 모두 raw representation 진단이다."),
('ambiguous match는?','EKEY0 400,714행, EKEY1 276,906행, EKEY2 5,458행이다. EKEY2의 2,514개 many:many 그룹은 start_time까지 동일하다.'),
('embedding row order 관계는 무엇인가?',f"최종 UNPROVEN. 유일 raw 후보에서 인접 역전 {order['adjacent_inversions']:,}건, 전체 역전 쌍 {order['total_pair_inversions_unique_raw_candidates']:,}개, source-index 중복 0건이다. 44개 chunk 경계 중 source index가 증가하는 경계는 {order['monotonic_chunk_boundary_transitions']}개다. direct prefix/ordered subset 가정은 관측과 맞지 않는다. 시간 authority가 없어 REORDERED_BUT_EXACT_MAPPING_PROVEN으로 승인하지 않았다."),
('누락 776,912행의 filter를 찾았는가?','아니다. 해당 raw key 집합 밖의 행수만 확인했고 선택 이유는 모르므로 count-matching filter를 만들지 않았다.'),
('filter authority는 code/document로 입증됐는가?','FALSE. 공개 prep와 배포 chunk 사이 export 단계가 보이지 않는다.'),
('RADDiT historic→Kestrel field lineage는?','FIELD_LINEAGE_MAP.csv에 timestamp, duration/request, resources와 단위를 명시했다. stored offset 기반 F0–F2만 계획상 허용하고 memory scope 및 categorical-token mapping은 미입증이다.'),
('job_id를 제외한 physical fingerprint match는 몇 개인가?','NOT_RUN_LEVEL1_AUTHORITY_FAILURE, 관측 개수 null. 새 physical fingerprint에서 0개가 나왔다고 주장하지 않는다. integer flag의 0은 승인 assignment 수다.'),
('가장 강한 exact fingerprint는 무엇인가?','Kestrel F0–F2는 사전 등록만 했고 미실행이다. 선택된 Kestrel key는 없다. F3/F4는 field authority도 없어 비활성이다.'),
('Kestrel/RADDiT 양쪽에서 key collision은 얼마인가?','Kestrel 비교 collision은 미측정(null). Embedding-historic EKEY2의 중복-key 행은 historic 8,855, embedding 5,458이다. 서로 다른 비교를 혼동하지 않는다.'),
('unused holdout field contradiction은 몇 개인가?','Embedding-historic 유일 raw 후보에서는 EKEY0–2 각각 0이다. EKEY2 start_time 1,775,514쌍 일치. Kestrel holdout은 NOT_RUN이다.'),
('negative control에서는 match가 얼마나 남는가?','NC1 +1초, NC2 날짜 내 requested walltime permutation, NC3 runtime permutation(seed1401)은 사전 등록했지만 Level1 중단 후 실행하지 않았다. 수치는 null이다.'),
('timezone 차이는 어떻게 처리했는가?','historic -06:00은 기록 그대로 UTC epoch도 보존했다. embedding naive는 timezone을 부여하지 않았다. 표시된 raw 시각 비교와 UTC 비교 미실행을 분리했다. 정밀도 손실·truncation 없음.'),
('임의 시간 offset fitting을 했는가?','NO. ±시간 탐색, DST 역추정, 성능 최대화 offset을 사용하지 않았다.'),
('approximate/fuzzy matching을 했는가?','NO. exact numeric/bitwise 비교만 수행했고 positional ID나 nearest timestamp로 보완하지 않았다.'),
('end-to-end embedding→Kestrel mapping은 입증됐는가?','FALSE. Level1 source-authority 미충족, Level2 미실행이다.'),
('V13 GPU 621,583건 중 semantic mapping 가능한 수는?','현재 승인된 연결은 0건이다. 실제 연결 가능한 전체 수는 이번 결과로 결정할 수 없다.'),
('전체 join rate는?','승인 join rate 0 / 621,583 = 0%. 실제 physical correspondence 부재를 측정한 0%가 아니다.'),
('fold별 join rate는?','5개 fold의 TRAIN/CAL/VALID 모두 NOT_RUN, null이다. 숫자를 채워 넣지 않았다.'),
('>4h join rate는?','null, NOT_RUN_LEVEL1_AUTHORITY_FAILURE.'),
('>12h join rate는?','null, NOT_RUN_LEVEL1_AUTHORITY_FAILURE.'),
('>24h join rate는?','null, NOT_RUN_LEVEL1_AUTHORITY_FAILURE.'),
('matched/unmatched population bias가 있는가?','V13 end-to-end population이 없어 미평가다. historic의 선택적 subset 관측만으로 GPU/장기 작업 bias나 인과성을 주장하지 않는다.'),
('public embedding-generation provenance는 outcome-free인가?','TRUE, 공개 문자열 작성/embedding 코드의 직접 입력 범위에서만 그렇다. job_type의 상위 생성 시점까지 인증하지 않았으며 distributed export provenance와 분리한다.'),
('distributed embedding export provenance는 완전히 입증됐는가?','PARTIAL. 공개 렌더링·LLM·chunk payload/LFS 식별은 확인했지만 subset, timezone stripping, encrypted/int8 변환이 미입증이다.'),
('new future job에서 semantic input을 받을 수 있는가?','현재 V42 SubmissionRuntimeRequest를 정적으로 읽었다. 8개 중 partition/qos만 허용되어 있고 script/submit_line/name/account/user/job_type 6개가 없다. 현재 계약 기준 FALSE다.'),
('same embedding pipeline을 재현할 수 있는가?','FALSE. 공개 Linq 모델 예제는 있으나 model/tokenizer revision이 고정되지 않았고 배포 encrypted coordinate transform이 없다. 임의로 새 embedding을 실행하지 않았다.'),
('semantic Runtime ML을 다음 단계에서 실행할 scientific authority가 생겼는가?','FALSE. source-backed timestamp, end-to-end unique linkage, actual V13 temporal support, selection bias 조건이 충족되지 않았다.'),
('authority가 생겼다면 broad/partial/sparse 중 무엇인가?','NO_SUPPORT: 승인된 end-to-end support가 없다는 뜻이다. raw 후보의 규모나 semantic utility를 부정하는 분류가 아니다.'),
('authority가 실패했다면 정확한 blocker는 무엇인가?','직접 blocker는 naive embedding timestamp의 원래 timezone/export 의미를 source code/document로 입증하지 못한 것이다. 5,458 duplicate rows, subset/export 변환 미공개도 별도로 기록했다. subset 미포함 자체는 실패 조건이 아니다.'),
('다음에 필요한 외부/원본 자료는 무엇인가?','source row crosswalk와 원 Slurm composite identity, embedding subset query/version, timestamp 변환 계약, row-order manifest, 동일 encrypted vector transform, 새 제출 semantic input capture 계약이다. 이 자료가 도착하면 사전 등록된 F0–F2와 controls부터 재개할 수 있다.'),
('V14/J2–J5 ML은 이번 task에서 실행했는가?','NO. NEW_ML_FITS=0. 모델 학습·SVD·kNN 예측·calibration·remaining/queue/provider를 모두 실행하지 않았다.'),
('April을 평가했는가?','NO. 기존 pre-April projection과 RADDiT의 pre-April metadata만 사용했다. Kestrel ZIP의 April member를 새로 열지 않았다.'),
('May를 열었는가?','NO. May runtime payload 미개봉. 원본 raw size/mtime 검사는 내용 decode가 아니다.'),
('기존 V6–V14 evidence가 보존됐는가?','예. 기존 tracked 1,373개, delivery manifest 9개와 raw size/mtime 23,601개를 전후 검증한다. 실제 재검증 결과는 VERIFICATION.json에 기록하고 기존 파일은 수정하지 않는다.'),
('무엇이 확인된 사실이고 무엇이 여전히 가설인가?','확인: raw shared metadata의 전체 키 존재, 1,775,514개 유일 후보, 0 holdout/bitwise 충돌, 5,458개 ambiguity, 배포 순서 재배열, public text input 8개, 새 제출 계약의 6개 누락. 가설: 동일 absolute-time/export lineage, 제외 filter 이유, Kestrel physical identity, V13 temporal/tail support와 semantic ML 이익. Runtime 또는 semantic 정보가 무용하다는 주장은 하지 않는다.')]
md('FINAL_REVIEW_KO.md','# Runtime-vNext14R1 최종 검토\n\n**STOPPED_LEVEL1_TIMESTAMP_AUTHORITY_UNRESOLVED. NEW_ML_FITS=0.**\n\nV14의 ID-only 실패를 반복하지 않았다. 45개 embedding chunk의 공유 payload에서 유력한 exact 행 연결 증거를 확보했지만, 사전 등록한 timestamp source-authority gate를 통과하지 못했다. Kestrel physical fingerprint 검사는 0-match 실패가 아니라 미실행이다.\n\n'+ '\n\n'.join(f'## {i}. {q}\n\n{ans}' for i,(q,ans) in enumerate(answers,1)))
md('README.md','''# Runtime-vNext14R1 RADDiT crosswalk forensic

Base: V14 Draft PR #86, dbe906d6b211fcbb71d8b4c1c17a33ce492452ea.

결론: STOPPED_LEVEL1_TIMESTAMP_AUTHORITY_UNRESOLVED. NEW_ML_FITS=0.

공유 metadata exact audit에서 1,780,972 embedding 행 모두 historic key가 존재한다. EKEY2의 유일 raw 후보 1,775,514행, 중복 모호 행 5,458개, 유일 후보 holdout/float bitwise 충돌 0개다. 하지만 naive timestamp/export authority가 없어 승인 crosswalk를 생성하지 않았다. Kestrel F0–F2·negative controls·V13 coverage/bias는 NOT_RUN이며 observed count/rate는 null이다. 승인된 V13 연결은 0 / 621,583이다.

읽기 순서: FINAL_REVIEW_KO.md, FINAL_VERDICT.json, EMBEDDING_HISTORIC_KEY_AUDIT.csv, TIMEZONE_AND_UNIT_CANONICALIZATION.md, PUBLIC_CROSSWALK_AUTHORITY_SEARCH.md. 45개 최종 질문과 모든 요청 flag를 포함한다.

계산은 사용자 요청에 맞춰 PyArrow projected metadata와 numeric pandas joins로 수행했다. CSV는 연구 pipeline용 flat typed table이며 workbook/시각화는 만들지 않았다. 미실행 값을 0으로 대체하지 않는다. 원본 벡터는 읽지 않는다. .local의 projection과 negative forensic ledgers는 LOCAL_EVIDENCE_MANIFEST.json에 hash-bound되며 Git에 올리지 않는다. 성공을 가장하는 빈 crosswalk 파일은 없다.

재현: Python 3.11.7, pandas 2.2.3, numpy 2.4.6 및 PyArrow. `embedding_audit.py --replay`는 보존한 shared-metadata projection에서 세 diagnostic ledger의 content SHA256을 새 프로세스로 검증한다. `test_forensic.py`는 작은 합성자료의 collisions, missing/contradicting fields, float exactness를 검증한다. 이전 namespace의 스크립트나 모델은 실행하지 않았다. `prepare.py`는 원래 base HEAD에서만 실행하도록 고정했다. 이미 동결한 결과를 덮어쓰지 말고 재연구는 별도 namespace에서 수행해야 한다.

다음 연구에는 source export와 timestamp/crosswalk 계약이 필요하다. Semantic 정보가 무용하다는 결론은 없다. 모델 학습·April·May·V42/CC4/MESS/optimizer/OpenDSS 실행은 없었다.''')
# Keep missing CSV count cells blank, and measured counts integral.
df=pd.read_csv(ROOT/'EMBEDDING_HISTORIC_KEY_AUDIT.csv')
for c in df:
    if pd.api.types.is_numeric_dtype(df[c]):df[c]=df[c].astype('Int64')
df.to_csv(ROOT/'EMBEDDING_HISTORIC_KEY_AUDIT.csv',index=False)
print('FINAL REPORTS WRITTEN',len(answers))
