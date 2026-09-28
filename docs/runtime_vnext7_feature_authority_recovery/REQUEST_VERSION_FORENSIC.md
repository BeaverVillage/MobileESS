# Kestrel original-request forensic — Runtime-vNext7

최종 판정은 `NOT_FOUND_IN_SEARCHED_AUTHORITY`다. 공개 자료와 접근 가능한 로컬 자료에서 최초 제출값의 완전한 연결을 복구하지 못했다. 내부 로그가 존재하지 않는다거나 모든 현재 값이 변경됐다는 판정이 아니다. 신규 모델은 학습하지 않았다.

## 수집·출판 계보

`Slurm sacct → 주기적 수집 → NLR PostgreSQL load_slurm → set_job_calc / upd_calc_cols / upd_sharednodes → 내부 익명화·Parquet export → 공개 ZIP → hpc-oda descriptor/normalize → MobileESS`

NLR 데이터 카드는 수집 시각 형식, PostgreSQL 함수 이름, 제외된 JSONB·job_step, 7자리 해시를 설명하지만 내부 함수·내보내기 코드는 공개하지 않는다. 수집 명령의 `-D`, 수집 간격, UPSERT 키, 최초값 보존 여부, 유효시각, 재큐잉 시 덮어쓰기, 해시 알고리즘·salt·버전·null 처리의 증거가 없다. 공개 문서의 요청 필드 설명은 필드의 의미이며 원본 요청 버전의 증명이 아니다. [NLR 자료](https://data.nlr.gov/submissions/302)

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

정확한 downstream 경로는 `datasets/normalize.py::target_to_mapping_spec` → `ingest/jobs_parquet/apply.py::apply_mapping_spec`다. descriptor commit은 `218d75f56b783ebfd698100f9406cfb46fa04c01`; 최초 Kestrel descriptor 추가는 `0072ebe`다. 메모리는 `_memory_slurm_to_mb/_memory_slurm_column`: `n`을 처리하지만 `c`는 null로 떨어지는 제한이 있다. 이번 양수 GPU 621,583행의 메모리 문자열은 모두 `c/n` 범위 접미사가 없다. 숫자 MiB 변환은 할 수 있어도 per-node/per-CPU 의미를 복원했다고 보지 않는다. [실제 descriptor](https://github.com/NatLabRockies/hpc-oda-commons/blob/218d75f56b783ebfd698100f9406cfb46fa04c01/src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml)

`kernel/transformations.py::hash_identifier`는 선택적 salt와 SHA256 64자리 결과를 만드는 downstream 함수다. NLR의 기존 7자리 토큰 생성 구현으로 대체해서는 안 된다. `models/feature_policy.py`도 제출 시 관측 가능한 **개념**의 allowlist이며 Kestrel 행별 원본 버전 보증이 아니다. 후행 정규화는 사라진 이력을 복원하지 못한다.

## 필드별 변경 능력과 관측을 분리

기존 9개 중 8개는 Slurm 요청 변경 기능의 근거가 있다. 메모리도 과거 23.11.10.1 `scontrol/update_job.c`의 `MinMemoryNode/MinMemoryCPU` 경로로 확인했다. UserID 옵션·인증 주체를 작업 소유자 변경 증거로 오독하지 않았다. `submit_line`은 초기 job descriptor에 저장되는 개념이고, array index도 제출 시 선언되는 개념이다. 이 후보들을 “모두 mutable”이라고 제외하지 않았다. NLR capture/export 및 새 작업 토큰의 동일 표현 증거가 미완성이므로 D다. 과거 Kestrel의 실제 설치 버전·설정은 확보하지 못했으며 Slurm 23.11 또는 현재 26.05 문서를 그 버전으로 단정하지 않는다. [Slurm 변경 코드](https://github.com/SchedMD/slurm/blob/slurm-23-11-10-1/src/scontrol/update_job.c)

## 중복·배열·재큐잉

pre-April 원자료 **6,326,884행**을 중복 제거 전에 감사했다. `id` 중복 0, 숫자형 `job_id` 반복 4,104집단/310,128행이다. 3,830집단은 고유 배열 원소들이다. 나머지 274집단은 모두 고유한 array index 원소들에 **index 없는 범위 레코드 1개**가 더 있고 그 id는 집단 숫자 ID와 같다. 배열 부모/범위와 자식 구조에 부합하지만 정확한 NLR export 매핑을 못 찾았으므로 frozen 분류의 ambiguous 표기는 유지했다. 동일한 `(job_id,array_pos)`의 비결측 원소 중복도 0이다. [배열 ID의 지연 생성과 원소 업데이트](https://slurm.schedmd.com/job_array.html)

4집단에 여러 Submit 값, 127집단에 요청값 차이가 있다. 차이는 memory 97집단, GPU 단독19, partition 단독5, QoS 단독2, QoS+partition1, walltime1, GPU+QoS1, GPU+partition1이다. 이는 **서로 다른 배열 원소/범위 행 사이의 이질성**이며 동일 작업의 변경 이력으로 집계하지 않는다. 요청 차이에는 null/범위 행의 차이도 포함한다. 최초 관측시각이 유일한 행인 집단은 0이다. 유일한 최솟값이 있더라도 원본 이력이 완전하다는 증거가 추가로 필요하다.

4개 다중시각 집단은 55357(1,000행), 62827(100행), 3829214(600행), 4560799(155행)이다. 정확한 시각 배열은 `ARRAY_IDENTITY_SUPPLEMENT.json`과 전체 CSV에 보존했다. 마지막 두 집단의 2024년 5월/7월 기록은 pre-April-2025 범위다. 2025년 April/May 평가 데이터가 아니다.

원본을 복원했다고 증명한 건수는 0/6,326,884(0%), 중복 후보 기준도 0/310,128행이다. 논리적 작업 총수를 확정하지 못해 이 분모는 **행/고유 공개 id 기준의 입증률**이다. 전체 실제 수정률이나 원본 존재 확률 추정치가 아니다. REQUEUED/RESTART terminal 행은 확인되지 않았지만 완료된 작업이 과거 재큐잉되지 않았다는 증거가 되지 않는다.

공개 `id`의 숫자형 per-task 패턴과 공통 `job_id`는 데이터 카드의 JobID/JobIDRaw 단순 설명만으로 정확하게 매핑되지 않는다. 문서 오류 또는 DB 변환 가능성을 구분하지 못했다. 이 불확실성을 무시하고 숫자 ID로 deduplicate하지 않았다. 별도 폴더의 동일 ZIP도 SHA256이 같아 독립된 이전 snapshot이 아니다.

## submit_time과 추가 후보

문서상 `submit_time`은 sacct Submit이며 DB 삽입시각으로 설명되지 않는다. Slurm requeue 경로는 Submit를 갱신한다. UTC 변환은 시간대 표현만 바꾼다. 현재 행의 original/last-attempt 여부나 최초 시각을 증명할 코호트는 0건이다. `submit_hour`, `submit_day_of_week`, 공개 day/hour/minute도 엄격 피처에서 제외했다. [sacct duplicates·Submit 의미](https://slurm.schedmd.com/sacct.html), [requeue 구현](https://github.com/SchedMD/slurm/blob/slurm-23-11-10-1/src/slurmctld/job_mgr.c)

실제 원자료에는 `state/state_simple`, array metadata와 7종 해시가 존재한다. vNext6의 제한된 로드 projection에 없었던 열을 원자료에 없다고 해석하지 않도록 정정한다. 상태는 제출 피처로 승격하지 않는다. script/submitline/name/workdir/user/account 토큰 반복은 관측할 수 있지만 제출 시 생성·불변성·충돌/표현 일관성 증거가 필요하다. job_type/python/reframe은 생성 코드·시점이 불명확해 G다. workflow, executable, container digest, dependency 원본, 독립 project/category는 공개 열에서 찾지 못했다.

## 검색 범위와 한계

4개 루트(Codex native workspace, Mobile ESS 2, Mobile ESS, raw 데이터 센터)의 파일명·계보 검색, 로컬 저장소 이력, hpc-oda 315개 commit의 관련 함수 검색, NatLabRockies/NREL 공식 저장소 검색을 수행했다. 전체 내용 검색은 중복 파생 receipt가 많아 1,223개 경로 이후 중단했으며 **부분 검색**으로 기록했다. `SEARCH_AUTHORITY_RECEIPTS.json`, 경로 목록, `REPOSITORY_AUTHORITY_HISTORY.txt`가 범위를 기록한다. 실제 접근 못 한 내부 DB/외부 디스크까지 검색했다고 주장하지 않는다.

`period_selection/kestrel_raw_reproduction.py`는 공개 자료의 시간/ID 정렬과 필터링, `kestrel_adapter.py`는 처리된 시간으로 도착·큐 상태를 재구성한다. 원본 수집 이벤트 로그가 아니다. hpc-oda의 slurmctld adapter는 allocation/completion parser와 합성 unit fixture다. 공식 `hpc_tandem_predictions@77be4fd9` 검색 결과도 추적했다. `data_preprocessing.py`는 공개/가공 필드 변환, `system_state.py::create_job_event_timeline`은 제출/실행 시간으로 상태를 계산한다. NLR Kestrel `load_slurm`, immutable submit journal, 익명화 export 구현을 제공하지 않는다. 그 저장소의 모델·Parquet·노트북은 실행하지 않았다.

## 다음 단계에 필요한 최소 authority

원본 accepted submit 이벤트(작업/배열/attempt 키, original_submit_time, request values), 수정 이벤트의 effective timestamp와 이전/이후 값, requeue parent/attempt 연결, 수집 명령·보존 정책, `load_slurm` DDL/UPSERT 및 export 스냅샷 기준, 7자리 토큰의 일관된 생성/버전·null/충돌 처리 증거가 필요하다. 내부 코드를 공개할 수 없다면 해당 버전의 동작을 입증하는 비민감 명세·테스트·스냅샷 영수증도 검토할 수 있다. 특정 서명 방식만 필수인 것은 아니다. 증거를 새로 확보하면 **후속 provenance 계약 버전**을 먼저 작성하고 재학습 여부를 판단한다.
