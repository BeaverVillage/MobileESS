"""Assemble the forensic report from fixed evidence; never trains or selects a model."""
from common7 import *
import datetime,pandas as pd,subprocess

def md(name,text):
    with (ROOT/name).open('x',encoding='utf-8',newline='\n') as f:f.write(text.strip()+'\n')

def main():
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    a=read(ROOT/'AUTHORITY_SOURCE_RECEIPTS.json');sup=read(ROOT/'SUPPLEMENTAL_AUTHORITY_SOURCES.json');dup=read(ROOT/'REQUEUE_DUPLICATE_SUMMARY.json')
    role=pd.read_csv(ROOT/'COHORT_ROLE_SUMMARY.csv').set_index('role');wf=pd.read_csv(ROOT/'WORKFLOW_IDENTITY_AUDIT.csv');counts=pd.read_csv(ROOT/'FEATURE_AUTHORITY_DECISION.csv').authority_category.value_counts().to_dict()
    links={'nlr':'https://data.nlr.gov/submissions/302','sacct':'https://slurm.schedmd.com/sacct.html','array':'https://slurm.schedmd.com/job_array.html','scontrol':'https://slurm.schedmd.com/scontrol.html',
      'descriptor':'https://github.com/NatLabRockies/hpc-oda-commons/blob/218d75f56b783ebfd698100f9406cfb46fa04c01/src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml',
      'jobmgr':'https://github.com/SchedMD/slurm/blob/slurm-23-11-10-1/src/slurmctld/job_mgr.c','update':'https://github.com/SchedMD/slurm/blob/slurm-23-11-10-1/src/scontrol/update_job.c'}
    md('REQUEST_VERSION_FORENSIC.md',f'''
# Kestrel original-request forensic — Runtime-vNext7

최종 판정은 `NOT_FOUND_IN_SEARCHED_AUTHORITY`다. 공개 자료와 접근 가능한 로컬 자료에서 최초 제출값의 완전한 연결을 복구하지 못했다. 내부 로그가 존재하지 않는다거나 모든 현재 값이 변경됐다는 판정이 아니다. 신규 모델은 학습하지 않았다.

## 수집·출판 계보

`Slurm sacct → 주기적 수집 → NLR PostgreSQL load_slurm → set_job_calc / upd_calc_cols / upd_sharednodes → 내부 익명화·Parquet export → 공개 ZIP → hpc-oda descriptor/normalize → MobileESS`

NLR 데이터 카드는 수집 시각 형식, PostgreSQL 함수 이름, 제외된 JSONB·job_step, 7자리 해시를 설명하지만 내부 함수·내보내기 코드는 공개하지 않는다. 수집 명령의 `-D`, 수집 간격, UPSERT 키, 최초값 보존 여부, 유효시각, 재큐잉 시 덮어쓰기, 해시 알고리즘·salt·버전·null 처리의 증거가 없다. 공개 문서의 요청 필드 설명은 필드의 의미이며 원본 요청 버전의 증명이 아니다. [NLR 자료]({links['nlr']})

`REQUEST_FIELD_LINEAGE.csv`의 `database_column`은 공개 스키마에 대응하는 문서상 이름이다. 실제 DB DDL을 복구했다는 뜻이 아니다. `normalization_code`의 공통 경로는 정규화 프레임워크 설명이며 58개 모든 후보가 현 descriptor에 구현됐다는 뜻이 아니다. 실제 구현된 열은 아래 표와 descriptor로 한정한다. 분류표의 `source_backed=False`는 **최초 제출값부터 공개·온라인 표현까지 완전한 연결**이 없다는 뜻이다. 의미 문서가 전혀 없다는 뜻이 아니다.

|피처|sacct/공개 열|downstream 변환|최초값 판정|
|---|---|---|---|
|requested_seconds|Timelimit → wallclock_req|duration seconds|D: TimeLimit 변경 가능, 최초 버전 미확인|
|num_gpus_req|ReqTRES → gpus_requested|integer|D: NLR GPU 파싱·갱신 구현 미확인|
|num_nodes_req|ReqNodes → nodes_req|integer|D: NumNodes 변경 가능|
|num_cores_req|ReqCPUS → processors_req|integer|D: NumCPUs 변경 가능|
|requested_memory_mib|ReqMem → memory_req|memory_slurm|D: MinMemoryNode/MinMemoryCPU 변경 가능, 요청 단위 범위 미확인|
|qos|QOS → qos|pass-through|D: 최초 명시값·기본값·변경값 분리 불가|
|partition|Partition → partition|pass-through|D: 최초 목록·유효 partition 버전 분리 불가|
|account|Account → account_hash|공개 해시 pass-through|D: Account 변경 및 해시 일관성 증거 미완성|
|user|User → user_hash|공개 해시 pass-through|D: 일반 소유자 변경 경로는 확인 안 됨. 제출 시 소유자 개념과 공개 토큰의 일관된 원본 대응을 별도 구분|

정확한 downstream 경로는 `datasets/normalize.py::target_to_mapping_spec` → `ingest/jobs_parquet/apply.py::apply_mapping_spec`다. descriptor commit은 `218d75f56b783ebfd698100f9406cfb46fa04c01`; 최초 Kestrel descriptor 추가는 `0072ebe`다. 메모리는 `_memory_slurm_to_mb/_memory_slurm_column`: `n`을 처리하지만 `c`는 null로 떨어지는 제한이 있다. 이번 양수 GPU 621,583행의 메모리 문자열은 모두 `c/n` 범위 접미사가 없다. 숫자 MiB 변환은 할 수 있어도 per-node/per-CPU 의미를 복원했다고 보지 않는다. [실제 descriptor]({links['descriptor']})

`kernel/transformations.py::hash_identifier`는 선택적 salt와 SHA256 64자리 결과를 만드는 downstream 함수다. NLR의 기존 7자리 토큰 생성 구현으로 대체해서는 안 된다. `models/feature_policy.py`도 제출 시 관측 가능한 **개념**의 allowlist이며 Kestrel 행별 원본 버전 보증이 아니다. 후행 정규화는 사라진 이력을 복원하지 못한다.

## 필드별 변경 능력과 관측을 분리

기존 9개 중 8개는 Slurm 요청 변경 기능의 근거가 있다. 메모리도 과거 23.11.10.1 `scontrol/update_job.c`의 `MinMemoryNode/MinMemoryCPU` 경로로 확인했다. UserID 옵션·인증 주체를 작업 소유자 변경 증거로 오독하지 않았다. `submit_line`은 초기 job descriptor에 저장되는 개념이고, array index도 제출 시 선언되는 개념이다. 이 후보들을 “모두 mutable”이라고 제외하지 않았다. NLR capture/export 및 새 작업 토큰의 동일 표현 증거가 미완성이므로 D다. 과거 Kestrel의 실제 설치 버전·설정은 확보하지 못했으며 Slurm 23.11 또는 현재 26.05 문서를 그 버전으로 단정하지 않는다. [Slurm 변경 코드]({links['update']})

## 중복·배열·재큐잉

pre-April 원자료 **6,326,884행**을 중복 제거 전에 감사했다. `id` 중복 0, 숫자형 `job_id` 반복 4,104집단/310,128행이다. 3,830집단은 고유 배열 원소들이다. 나머지 274집단은 모두 고유한 array index 원소들에 **index 없는 범위 레코드 1개**가 더 있고 그 id는 집단 숫자 ID와 같다. 배열 부모/범위와 자식 구조에 부합하지만 정확한 NLR export 매핑을 못 찾았으므로 frozen 분류의 ambiguous 표기는 유지했다. 동일한 `(job_id,array_pos)`의 비결측 원소 중복도 0이다. [배열 ID의 지연 생성과 원소 업데이트]({links['array']})

4집단에 여러 Submit 값, 127집단에 요청값 차이가 있다. 차이는 memory 97집단, GPU 단독19, partition 단독5, QoS 단독2, QoS+partition1, walltime1, GPU+QoS1, GPU+partition1이다. 이는 **서로 다른 배열 원소/범위 행 사이의 이질성**이며 동일 작업의 변경 이력으로 집계하지 않는다. 요청 차이에는 null/범위 행의 차이도 포함한다. 최초 관측시각이 유일한 행인 집단은 0이다. 유일한 최솟값이 있더라도 원본 이력이 완전하다는 증거가 추가로 필요하다.

4개 다중시각 집단은 55357(1,000행), 62827(100행), 3829214(600행), 4560799(155행)이다. 정확한 시각 배열은 `ARRAY_IDENTITY_SUPPLEMENT.json`과 전체 CSV에 보존했다. 마지막 두 집단의 2024년 5월/7월 기록은 pre-April-2025 범위다. 2025년 April/May 평가 데이터가 아니다.

원본을 복원했다고 증명한 건수는 0/6,326,884(0%), 중복 후보 기준도 0/310,128행이다. 논리적 작업 총수를 확정하지 못해 이 분모는 **행/고유 공개 id 기준의 입증률**이다. 전체 실제 수정률이나 원본 존재 확률 추정치가 아니다. REQUEUED/RESTART terminal 행은 확인되지 않았지만 완료된 작업이 과거 재큐잉되지 않았다는 증거가 되지 않는다.

공개 `id`의 숫자형 per-task 패턴과 공통 `job_id`는 데이터 카드의 JobID/JobIDRaw 단순 설명만으로 정확하게 매핑되지 않는다. 문서 오류 또는 DB 변환 가능성을 구분하지 못했다. 이 불확실성을 무시하고 숫자 ID로 deduplicate하지 않았다. 별도 폴더의 동일 ZIP도 SHA256이 같아 독립된 이전 snapshot이 아니다.

## submit_time과 추가 후보

문서상 `submit_time`은 sacct Submit이며 DB 삽입시각으로 설명되지 않는다. Slurm requeue 경로는 Submit를 갱신한다. UTC 변환은 시간대 표현만 바꾼다. 현재 행의 original/last-attempt 여부나 최초 시각을 증명할 코호트는 0건이다. `submit_hour`, `submit_day_of_week`, 공개 day/hour/minute도 엄격 피처에서 제외했다. [sacct duplicates·Submit 의미]({links['sacct']}), [requeue 구현]({links['jobmgr']})

실제 원자료에는 `state/state_simple`, array metadata와 7종 해시가 존재한다. vNext6의 제한된 로드 projection에 없었던 열을 원자료에 없다고 해석하지 않도록 정정한다. 상태는 제출 피처로 승격하지 않는다. script/submitline/name/workdir/user/account 토큰 반복은 관측할 수 있지만 제출 시 생성·불변성·충돌/표현 일관성 증거가 필요하다. job_type/python/reframe은 생성 코드·시점이 불명확해 G다. workflow, executable, container digest, dependency 원본, 독립 project/category는 공개 열에서 찾지 못했다.

## 검색 범위와 한계

4개 루트(Codex native workspace, Mobile ESS 2, Mobile ESS, raw 데이터 센터)의 파일명·계보 검색, 로컬 저장소 이력, hpc-oda 315개 commit의 관련 함수 검색, NatLabRockies/NREL 공식 저장소 검색을 수행했다. 전체 내용 검색은 중복 파생 receipt가 많아 1,223개 경로 이후 중단했으며 **부분 검색**으로 기록했다. `SEARCH_AUTHORITY_RECEIPTS.json`, 경로 목록, `REPOSITORY_AUTHORITY_HISTORY.txt`가 범위를 기록한다. 실제 접근 못 한 내부 DB/외부 디스크까지 검색했다고 주장하지 않는다.

`period_selection/kestrel_raw_reproduction.py`는 공개 자료의 시간/ID 정렬과 필터링, `kestrel_adapter.py`는 처리된 시간으로 도착·큐 상태를 재구성한다. 원본 수집 이벤트 로그가 아니다. hpc-oda의 slurmctld adapter는 allocation/completion parser와 합성 unit fixture다. 공식 `hpc_tandem_predictions@77be4fd9` 검색 결과도 추적했다. `data_preprocessing.py`는 공개/가공 필드 변환, `system_state.py::create_job_event_timeline`은 제출/실행 시간으로 상태를 계산한다. NLR Kestrel `load_slurm`, immutable submit journal, 익명화 export 구현을 제공하지 않는다. 그 저장소의 모델·Parquet·노트북은 실행하지 않았다.

## 다음 단계에 필요한 최소 authority

원본 accepted submit 이벤트(작업/배열/attempt 키, original_submit_time, request values), 수정 이벤트의 effective timestamp와 이전/이후 값, requeue parent/attempt 연결, 수집 명령·보존 정책, `load_slurm` DDL/UPSERT 및 export 스냅샷 기준, 7자리 토큰의 일관된 생성/버전·null/충돌 처리 증거가 필요하다. 내부 코드를 공개할 수 없다면 해당 버전의 동작을 입증하는 비민감 명세·테스트·스냅샷 영수증도 검토할 수 있다. 특정 서명 방식만 필수인 것은 아니다. 증거를 새로 확보하면 **후속 provenance 계약 버전**을 먼저 작성하고 재학습 여부를 판단한다.
''')
    table='|구간|mature GPU 행|>4h|장기 비율|≥16 GPU|≥16 GPU 중 >4h|\n|---|---:|---:|---:|---:|---:|\n'
    for name,r in role.iterrows():table+=f'|{name}|{int(r.n):,}|{int(r.long_n):,}|{r.long_fraction:.2%}|{int(r.high_gpu_n):,}|{int(r.high_gpu_long_n):,}|\n'
    md('LONG_JOB_ROOT_CAUSE_AUDIT.md',f'''
# pre-April 장기 작업 기술 감사

피처 권위 분류·계약 해시를 먼저 동결했다. 본 문서는 사용자 §10의 **라벨이 성숙한 아카이브 기술 통계**이며 인과적 피처 유용성·모델 선택 결과가 아니다. strict feature가 0개이므로 §9의 Spearman/MI, 범주별 예측 분산, walltime/runtime 양방향 비율은 수행하지 않았다. workflow runtime CV도 같은 권위 게이트로 보류하고 CSV에 결측 사유를 썼다. 그 대신 라벨과 무관한 토큰 반복·미관측률을 모두 보고한다.

{table}

모집단은 아카이브에서 요청 GPU>0으로 기록된 모든 행이다. 기존 vNext6 학습용 필터나 April 평가 코호트와 동일하지 않다. 실제 실행 시간을 0초 이상으로 허용하고 terminal state로 성공 작업만 선별하지 않았다. 요청 GPU와 Submit 자체가 버전 미확정이므로 이 집단 역시 **소급적 descriptor 코호트**다. 전체 GPU 621,583행 중 621,004행이 label_valid다. end/start의 2025-04-01 이후 시각은 라벨 산술 전에 제거했다. April/May 2025 파티션 payload는 열지 않았다.

TRAIN은 end∈[2024-09-15 08:00Z,2025-03-14 08:00Z). DEV는 submit∈[03-15,03-23), end<03-23. CAL_FIT은 submit∈[03-23,03-27),end<03-27. CAL_VALID는 submit∈[03-27,03-31),end<03-31 08:00Z. CAL은 마지막 두 구간 합집합이다. ALL_MATURE는 전체 pre-April 성숙 라벨이며 TRAIN과 겹친다. cutoff 직전 제출 후 아직 끝나지 않은 장기 작업은 빠지므로 구간별 장기 비율의 차이는 workload shift와 maturity-selection을 구분할 수 없다.

TRAIN에서 단기/장기 작업의 기록 walltime 중앙값은 **6시간/36시간**, cores는 **4/8**, GPU는 **1/1**, nodes는 **1/1**이다. 범위 접미사가 없는 메모리 수치 중앙값은 **81,920/10,240 MiB**이며 범위를 확정하지 못해 total 또는 per-node로 해석하지 않는다. 개별 QoS/partition/account/user 빈도와 모든 수치 분위수는 `LONG_JOB_FEATURE_DIAGNOSTIC.csv`에 보존했다. 이 차이는 기록된 요청값의 연관성이다. 가장 강한 **제출 당시** 정보가 무엇인지는 확인할 수 없다.

TRAIN의 동일한 아카이브 요청 9개 값 조합은 3,372종이다. 단기와 장기가 함께 있는 조합은 551종, 해당 행은 150,595(67.78%)이고 장기 작업의 98.40%가 이 혼합 조합에 속한다. 표본 10개 이상 조합의 runtime CV 중앙값은 0.959, 양수 최소값 기준 max/min 중앙값은 약329다. ALL_MATURE에서도 장기 작업의 98.41%가 혼합 조합에 속한다. 넓은 내부 분산은 관측되지만 **분포의 통계적 heavy-tail 형태를 검정한 것은 아니며**, 원본 요청 동일성이나 불충분한 피처의 인과적 기여를 증명하지 않는다. script/업무 종류가 섞였을 수 있다.

장기 작업은 TRAIN47,229·DEV2,643·CAL1,594건으로 전체 수가 극소수인 문제는 아니다. 그러나 CAL_VALID 장기 비율은2.49%이고 TRAIN21.26%와 다르다. DEV/CAL의 ≥16 GPU 표본은93/27건, 그중 장기는14/6건뿐이다. 이 작은 수로 GPU·workflow별 보장 성능을 인증할 수 없다. `HIGH_GPU_SUPPORT_SUFFICIENT=FALSE`는 수치에 기반한 보수적 기술 판단이며 조정된 성능 임계값이 아니다.

TRAIN의 name/submitline/script/workdir 토큰별 중앙 표본은 모두1이다. script token의 DEV 미관측률은77.49%, CAL96.82%; name은57.22%/89.64%; workdir은88.59%/93.14%다. 단순 문자열 반복은 안정적 workflow identity나 온라인 재현성을 증명하지 않는다. `COHORT_CATEGORY_SUPPORT.csv.gz`는 모든 관측 category×role별 n/long_n/high_gpu_n/seen_in_train을 저장한다. 누락·미존재 범주는 별도 G 및 미지원 판정이며 의미를 생성하지 않았다.

원인 후보 A–F 판정:

- A: 아카이브에 정보가 전혀 없다는 결론은 부당하다. **검증된 작업별 피처가 0개**라는 제약은 확실하다.
- B: 원본 request/version 연결이 미확정이라는 provenance 문제가 있다. 실제 모든 값이 변경되거나 원본이 소실됐다는 비율은 추정 불가다.
- C: 전체 장기 표본은 많지만 highGPU 및 세부 category의 장기 validation은 희소하다.
- D: 동일 아카이브 요청 조합 안의 폭넓은 runtime 분산을 관측했다. 원본 클래스의 heavy-tail 인과 진단은 미확정이다.
- E: 구간별 분포·토큰 support가 다르다. 실제 workload 변화와 종료 cutoff에 따른 선택효과를 분리하지 못한다.
- F: provenance 제한, 내부 이질성, 희소 검증 표본, 분포 차이의 복합 위험이다. 이번 관측만으로 vNext6 실패의 기여율이나 주된 인과 원인을 추정하지 않는다.

`LONG_JOB_FEATURE_SEPARABILITY=INCONCLUSIVE`. 이번에는 예측기·분류기를 학습하지 않았으며 April 성능으로 후보를 고르지 않았다.
''')
    sources=a['remote']+sup['sources']+[read(ROOT/'ARRAY_AUTHORITY_SOURCE.json')]
    source_text='# External authority sources\n\n수집일·바이트 해시는 아래와 SOURCE_MANIFEST.json에 기록했다. 현재 Slurm 문서는 2026년 문서이며 Kestrel의 2023–2025 설치 버전을 증명하지 않는다. 과거 Slurm source tag도 의미를 교차검증하는 근거다. hpc-oda는 공개 ZIP 이후의 정규화 코드다.\n\n'
    for r in sources:
        source_text+=f"- [{r.get('key',Path(r['path']).name)}]({r['url']}) — retrieved {r['downloaded_at']}; SHA256 `{r['sha256']}`; bytes {r['bytes']}; HTTP Last-Modified {r.get('http_last_modified','not supplied')}.\n"
    source_text+='\n고정 Slurm tag `slurm-23-11-10-1`의 tag object SHA는 `dcc87b59a2cd6ea4b4902e8fb5be464d2aafbfd2`; hpc-oda는 `218d75f56b783ebfd698100f9406cfb46fa04c01`; tandem source는 `77be4fd9f38627cf97fec3cc8794d02e040ea1de`다. 공식 저장소의 모델 코드는 읽기 전용 출처 조사이며 실행하지 않았다. 공개 Kestrel data card 원본은 로컬 파일의 hash로 별도 고정한다. 다른 저장소의 알고리즘을 NLR 비공개 함수라고 가정하지 않았다.\n'
    md('EXTERNAL_AUTHORITY_SOURCES.md',source_text)
    verdict={k:False for k in ['REQUEST_VERSION_AUTHORITY_FOUND','ORIGINAL_SUBMIT_TIME_RECOVERABLE','REQUESTED_WALLTIME_INITIAL_VALUE_RECOVERABLE','REQUESTED_GPU_INITIAL_VALUE_RECOVERABLE','QOS_INITIAL_VALUE_RECOVERABLE','PARTITION_INITIAL_VALUE_RECOVERABLE','DUPLICATE_HISTORY_AVAILABLE','REQUEUE_HISTORY_AVAILABLE','HIGH_GPU_SUPPORT_SUFFICIENT','RUNTIME_FEATURE_AUTHORITY_RECOVERED','NEXT_RUNTIME_ML_RETRAIN_AUTHORIZED','SUBMISSION_TIME_FEATURES_STRICTLY_VERIFIED','STRICT_CAUSAL_RUNTIME_PROVIDER_READY','IMMUTABLE_FEATURE_ONLY_MODEL_TRAINABLE']}
    verdict.update(STRICT_CAUSAL_JOB_FEATURE_COUNT=0,NEW_IMMUTABLE_FEATURE_COUNT=0,WORKFLOW_IDENTITY_SUPPORTED='PARTIAL',LONG_JOB_FEATURE_SEPARABILITY='INCONCLUSIVE',MUTABLE_REQUEST_FEATURE_COUNT=8,UNVERIFIED_REQUEST_FEATURE_COUNT=9,
      verdict='FEATURE_AUTHORITY_NOT_RECOVERED; REQUEST_VERSION_UNVERIFIED; frozen strict set empty',models_trained=0,model_selected=False,April_payload_opened=False,May_payload_opened=False,
      authority_categories=counts,search_negative_scope='NOT_FOUND_IN_SEARCHED_AUTHORITY',workflow_scope='Existing anonymized token recurrence only; no strict new-job workflow identity.',
      recoverability_false_meaning='Not proven in searched authority, not proof of universal nonexistence.',mutability_count_scope='8 of prior9 request features; user excluded from mutable count; not empirical change count.',
      submission_prediction_diagnostics='SKIPPED_NO_VALID_FEATURES',diagnostic_scope='Section10 mature pre-April archive descriptors and label-free identity support',feature_contract_frozen=True,created_at=now)
    write('FINAL_VERDICT.json',verdict)
    answers=[
      ('왜 Runtime-vNext6에서 9개 피처를 제외했는가?','제출 당시 입력이라는 의미만 있고, 현재 공개 accounting 행이 최초 요청값인지 증명할 버전·수집·출판 연결이 없었기 때문이다. 이번 감사에서도 기존 9개는 D다.'),
      ('그 판단이 너무 보수적이었는가, 실제 provenance 문제인가?','운영 후보의 원본 제출 피처라는 기준에는 실제 증거 공백이 있다. 다만 모든 필드가 똑같이 mutable이라는 설명은 부정확하다. 메모리 변경 능력은 새로 확인했고 user·submitline·script·array는 불변 가능 개념과 NLR 매핑 증거를 분리했다. downstream allowlist는 행별 authority가 아니다.'),
      ('requested walltime의 최초 제출값을 복원할 수 있는가?','입증하지 못했다. Timelimit 의미와 duration 변환은 확인했지만, 최초/유효/변경값을 가를 revision 또는 immutable snapshot이 없다.'),
      ('requested GPU의 최초 제출값을 복원할 수 있는가?','입증하지 못했다. ReqTRES→gpus_requested의 내부 파서·갱신 경로와 최초 요청 버전이 공개되어 있지 않다.'),
      ('QoS/partition/account의 최초 제출값을 복원할 수 있는가?','입증하지 못했다. 기본·명시·변경값 및 account 익명화 버전까지 연결할 자료가 없다. 수정 가능하다는 사실만으로 실제 전 행이 수정됐다고 말하지 않는다.'),
      ('submit_time은 최초 제출시각인가, requeue 후 시각일 수 있는가?','문서상 sacct Submit이며 requeue 후 갱신된 시각일 수 있다. 삽입시각이라고 볼 근거는 없다. 최초 시각이 증명되는 별도 cohort도 0건이다. UTC 변환이나 최솟값 선택으로 해결되지 않는다.'),
      ('duplicate/requeue로 original request를 복원할 수 있는 비율은?','입증한 비율은 공개 id/행 기준0/6,326,884=0%, 중복 후보 행 기준0/310,128이다. 숫자 ID 반복4,104집단은 배열 원소3,830집단 및 배열 범위+원소 형태274집단이다. 여러 submit 값4집단·요청 차이127집단을 같은 작업의 version 이력으로 인정하지 않았다. 실제 수정률을0%라고 뜻하지 않는다.'),
      ('기존 9개 중 production feature로 되살릴 것은?','현재 증거로는 없다. 9개 모두 research descriptor로 보존하되 production은 REQUEST_VERSION_UNVERIFIED로 fail-closed다.'),
      ('새 immutable submission-time feature가 있는가?','새 후보는 확인했다. 원자료의 array metadata·name/submitline/script/workdir 해시가 후보지만 원본 수집·해시·export 연결까지 통과한 수는0이다. job_type/python/reframe은 생성시점 미상 G다. 실제 archive state가 존재한다는 schema 정정도 반영했다.'),
      ('workflow/script/job-name identity를 안전하게 사용할 수 있는가?','이미 공개된 익명 토큰의 반복·support 분석에 한해 PARTIAL이다. 역식별·원문 복원은 하지 않았다. strict 온라인 identity는 미지원이다. script의 DEV/CAL 미관측률77.49%/96.82%도 높다. workflow runtime CV는 권위 게이트로 보류했다.'),
      ('long과 short를 구분하는 가장 강한 submission-time 정보는?','현재 판정할 수 없다. TRAIN의 기록 walltime 중앙값이6h/36h로 다르지만 검증된 최초 제출 피처가 아니다. 권위를 얻지 못한 피처를 상관·MI·classifier로 순위화하지 않았다.'),
      ('>4h support는 충분한가?','전체 기술 분석에는 TRAIN47,229·DEV2,643·CAL1,594건이 있다. 세부 stratum 인증에는 일반화할 수 없다. CAL_VALID는464건, 장기 비율2.49%이며 종료시각 cutoff에 따른 선택효과도 있다.'),
      ('≥16 GPU validation support는 충분한가?','아니다. 이번 넓은 pre-April archive GPU cohort에서 DEV93건(장기14), CAL27건(장기6)이다. 기존 vNext6 필터와 동일한 코호트 수치가 아니며, 세부 그룹별 보장 성능을 인증하기에 부족하다.'),
      ('STRICT_CAUSAL_SET에 몇 개 남는가?','작업별0개, 새 immutable0개다. 58개 후보 분류는 D24/E9/F14/G11이며 A/B/복원 가능한 C는 없다. 계약·분류의 SHA256을 기술 통계 전에 동결했다.'),
      ('다음 Runtime ML 재학습 근거가 생겼는가?','아니다. NEXT_RUNTIME_ML_RETRAIN_AUTHORIZED=FALSE. 새 모델·quantile 변경·survival 학습·April/May 평가를 수행하지 않았다. 이전 full-feature 연구 모델은 변경 없이 보존한다.'),
      ('아직 막는 provenance blocker는?','원본 accepted submit event와 attempt/array 식별, revision effective time, requeue 연결, 실제 sacct 수집 flags·보존 정책, load_slurm UPSERT/DDL와 export 기준, 익명 토큰의 안정적인 submit-time 생성·온라인 대응 증거다. NOT_FOUND_IN_SEARCHED_AUTHORITY이지 DOES_NOT_EXIST가 아니다.')]
    report='# Runtime-vNext7 최종 검토\n\n**최초 제출 피처 권위를 복구하지 못했다. 엄격 피처0개인 계약을 동결하고 재학습 승인을 FALSE로 유지한다.** 문서·코드 의미를 더 복구했지만 원본값 증거와 혼동하지 않았다.\n\n'
    for i,(q,ans) in enumerate(answers,1):report+=f'## {i}. {q}\n\n{ans}\n\n'
    report+='## 범위·검증\n\n'+table+'\n'
    report+='모델 학습0, 선택0. April/May 2025 payload 미개봉. 원자료6,326,884행 중복 제거 전 감사, 모든 실제 physical field의 분류 coverage 확인. 기존 vNext6 namespace와 base tracked 파일 보존은 VERIFICATION.json에 기록한다. 새로운 코드는 docs/runtime_vnext7_feature_authority_recovery에만 있다. 전수 내용 검색을 완료했다고 주장하지 않는다.\n\n'
    report+='§9의 유효 제출 피처 전제 때문에 correlation/MI/variance/양방향 walltime 비율, 그리고 workflow runtime CV는 값 대신 SKIPPED_AUTHORITY_GATE를 보고했다. §10의 소급적 장단기 분포·요청 조합 분산은 별도 기술 통계다. 이것으로 유효 피처 또는 강한 분리력을 인정하지 않았다. 엄격한 기준 아래 과학적으로 계산 권한이 없는 항목을 임의 가정으로 채우지 않았다.\n\n'
    report+='## 최종 flags\n\n```json\n'+json.dumps(verdict,ensure_ascii=False,indent=2)+'\n```\n\n'
    report+='## V42가 새 제출 시 합법적으로 알 수 있는 정보\n\n실제 accepted submit 이벤트를 받는다면 그때의 요청 walltime·자원·QoS·partition·account/owner·배열 선언 등은 관측할 수 있다. 이는 **미래 live capture 설계의 가능성**이다. 현재 공개 Kestrel archive의 동일 열이 그 시점의 값이라는 증거는 아니다. 이번 학습자료와 온라인 입력을 연결해 인증한 집합은 비어 있다. 다음 작업은 버전 증거 수집·검증이며 재학습이 아니다.\n\n'
    report+='상세 근거: [계보/재큐잉 감사](REQUEST_VERSION_FORENSIC.md), [장기 작업 진단](LONG_JOB_ROOT_CAUSE_AUDIT.md), [공식 출처](EXTERNAL_AUTHORITY_SOURCES.md), [frozen strict 계약](STRICT_CAUSAL_FEATURE_CONTRACT.json), [최종 flags](FINAL_VERDICT.json).\n'
    md('FINAL_REVIEW_KO.md',report)
    local=a['local']+[record(WORK.parent/'Mobile ESS/github_MobileESS/period_selection'/n) for n in ['kestrel_raw_reproduction.py','kestrel_adapter.py']]
    write('SOURCE_MANIFEST.json',dict(created_at=now,base_commit=BASE,raw_archives=read(ROOT/'ARCHIVE_COPY_AUDIT.json'),remote=sources,local=local,
      payload_reads='Only ZIP partitions <=2025/03, then submit<2025-04-01. Later member metadata only. 2024 April/May are historical pre-April2025, not locked evaluation.',
      caches=[read(ROOT/'PREPARATION_RECEIPT.json')['gpu_local_data']],search_receipts=[record(ROOT/p) for p in ['SEARCH_AUTHORITY_RECEIPTS.json','SEARCH_JOB_SOURCE_PATHS.txt','REPOSITORY_AUTHORITY_HISTORY.txt']],
      source_code_execution='Local audit scripts only. Inspected external ML-related source is never executed.',
      reproducibility='Large input ZIP, .local caches and downloaded official source bytes remain local; manifest records hash and URLs. Delivered audit records/CSVs and source scripts reproduce from exact ZIP.'))
    md('README.md','''
# Runtime-vNext7 forensic delivery

먼저 `FINAL_REVIEW_KO.md`와 `FINAL_VERDICT.json`을 읽는다. 연구를 재현할 때 학습 명령은 없다.

Python 3.11+, pandas/numpy/pyarrow 사용. `common7.py`의 로컬 source 경로를 환경에 맞춰 설정하고 **빈 새 output 디렉터리**에서 순서대로 `prepare_forensic.py`, `authority_sources.py`, `duplicate_forensic.py`, `classify_authority.py`, `supplemental_forensic.py`, `descriptive_audit.py`, `build_reports.py`를 실행한다. 기존 frozen 산출물을 덮어쓰지 않는다. 검색 receipt/경로 목록은 원래 환경의 수동 검색 증거이며 출처를 보존한 채 복사하거나 새 검색으로 다시 기록해야 한다. 분류 스크립트는 결과 성능을 입력으로 읽지 않는다.

`verify_delivery.py`는 모델을 학습하지 않고 계보, cutoff, frozen hashes, 분류 completeness와 보존 범위를 검증한다. `.local`은 입력 cache로 Git에 넣지 않는다. `COHORT_CATEGORY_SUPPORT.csv.gz`는 완전한 범주별 지원도 CSV다. 역할 이름 TRAIN/DEV/CAL은 기술 통계 기간의 이름이며 이번에 fit/calibration을 실행했다는 의미가 아니다.

데이터 전체·비공개 요청 로그를 저장소에 새로 올리지 않았다. 기존 공개 익명값을 포함한 필요한 중복 감사 추출·집계만 새 namespace에 저장했다. 후보별 runtime CV/상관·MI/비율이 비어 있는 이유는 strict authority gate이며 누락을 0으로 대체하지 않는다.
''')
    print('REPORTS_COMPLETE',verdict['verdict'],flush=True)

if __name__=='__main__':main()
