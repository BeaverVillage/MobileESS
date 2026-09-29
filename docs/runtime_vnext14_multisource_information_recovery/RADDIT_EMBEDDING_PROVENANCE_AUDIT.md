# RADDiT embedding provenance

공개 prep_for_embedding.py와 quickstart_embedding.py의 입력은 user/account/partition/job_type/name/qos/submit_line/script입니다. 이 함수들에는 actual runtime, START/END, final state, power/energy 결과가 없습니다. RADDIT_EMBEDDING_OUTCOME_INPUT_FOUND=FALSE는 이 공개 입력 구성 코드의 검사 범위입니다. semantic_search.py가 runtime/power/END를 검색 DB의 별도 필드로 넣는 것은 현재 작업 embedding 입력에 넣는 것과 다릅니다.

공개 생성 코드는 4096차원 last-token pooling과 L2 정규화를 사용합니다. 배포 파일은 enc_embedding_int8이며 40000행 단위 45개 chunk입니다. 공개 전처리는 4096행 단위 원본 순서를 사용하지만, 배포 chunk의 필터·암호화·재정렬 과정과 historic job ID crosswalk는 확인하지 못했습니다. semantic_search.py의 row_id는 chunk를 합칠 때 새로 부여한 번호입니다. 원본 job identity 증명이 아닙니다.

역사적 ingestion 시점은 입증되지 않아 submission-time semantic proxy 후보로만 설명합니다. 실제 물리 작업 대응이 실패하여 SEM_SVD32와 k=10 semantic neighbor를 실행하지 않았습니다. 기존 연구의 outcome-free 코드가 배포 암호화 벡터의 완전한 생성 이력을 증명하지는 않습니다.

새 작업이 동일 입력/동일 암호화 좌표를 생성하는 V42 연결 경로는 확인되지 않았습니다. RADDIT_NEW_JOB_SEMANTIC_CALLABLE=FALSE, STRICT_CAUSAL_RUNTIME_PROVIDER_READY=FALSE입니다. 원본 식별자 재식별이나 근사 시간 연결은 시도하지 않았습니다. 상세 코드 hash와 45개 LFS OID 일치는 JSON audit에 보존합니다.
