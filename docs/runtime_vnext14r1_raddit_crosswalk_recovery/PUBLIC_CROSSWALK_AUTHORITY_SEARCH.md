# 공개 crosswalk authority 검색

검색일: 2026-09-29. 아래는 특정 lineage를 찾기 위한 제한된 조사이며 인터넷 전체를 소진했다는 주장이 아니다. 원본 저장소는 읽기 전용으로 조회했다. 검색 결과의 무관한 동명 RADDiT 자료는 근거로 사용하지 않았다.

| 출처 | 버전·날짜 | 확인한 사실 / 찾지 못한 근거 | 강도·관련성 |
|---|---|---|---|
| [RADDiT source](https://github.com/NatLabRockies/raddit/tree/ae1bf132addb41b469f3ef25a7626fe5ab06bc81) | main ae1bf132, 2026-01-29 | 21 reachable commits, main/pearc25/synthetic-trace-generator, 태그 없음. 42개의 고유 source/document blob과 notebook code/markdown을 검사. export·subset·timestamp 제거 규칙은 발견하지 못함 | 직접 코드 근거. 미공개 이력의 부재까지 증명하지 않음 |
| [prep_for_embedding](https://github.com/NatLabRockies/raddit/blob/ae1bf132addb41b469f3ef25a7626fe5ab06bc81/energy_aware_scheduling/scripts/prep_for_embedding.py) | 동일 commit | historic에서 8개 요청/semantic 필드를 문자열화하고 4096행 순차 배치. 행 필터가 보이지 않음 | 공개 preparation 경로에 강한 근거. 실제 배포 export를 보증하지 않음 |
| [embed_job_scripts](https://github.com/NatLabRockies/raddit/blob/ae1bf132addb41b469f3ef25a7626fe5ab06bc81/energy_aware_scheduling/scripts/embed_job_scripts.py) | 동일 commit | Linq-Embed-Mistral, last-token pooling, L2 normalization, npy 저장. enc_embedding_int8 배포 변환 없음 | 공개 생성 경로에 강한 근거. 배포 벡터와 동일 좌표계인지 미입증 |
| [semantic_search](https://github.com/NatLabRockies/raddit/blob/ae1bf132addb41b469f3ef25a7626fe5ab06bc81/energy_aware_scheduling/scripts/semantic_search.py) | 동일 commit | 정렬된 chunk를 읽고 새 positional row_id 생성. naive timestamp를 epoch 숫자로 취급하지만 원본 export의 timezone 규칙을 설명하지 않음 | 소비 코드. 원본 Slurm ID/crosswalk authority 아님 |
| [GitHub issues API](https://api.github.com/repos/NatLabRockies/raddit/issues?state=all&per_page=100), [PR API](https://api.github.com/repos/NatLabRockies/raddit/pulls?state=all&per_page=100) | 조회일 현재 | state=all 양쪽 빈 배열. 공개 fork jdseng/main은 upstream보다 2 commits 뒤, ahead=0 | 검색된 공개 issue/PR/fork에 추가 export 근거 없음 |
| [삭제 이력](https://github.com/NatLabRockies/raddit/commit/5d5dd60), [LFS 도입 이력](https://github.com/NatLabRockies/raddit/commit/8a0284e) | 2025-04 | 삭제된 quickstart_output과 historical source를 reachable history에서 확인. embedding chunk가 historic 파일보다 먼저 commit됨. 이 순서는 데이터 생성 순서를 증명하지 않음 | Git/LFS는 배포 byte 식별 근거이지 source row identity나 filter 근거가 아님 |
| [NLR 연구 기록](https://research-hub.nlr.gov/en/publications/energy-aware-hpc-scheduling-with-llm-based-power-prediction/), [SC25 proceedings](https://sc25.supercomputing.org/proceedings/workshops/workshop_pages/ws_ss107.html) | 2025, DOI 10.1145/3731599.3767563 | enriched job scripts에 기반한 LLM power prediction 연구 확인. 조회한 abstract/metadata는 export manifest, row crosswalk, timezone 규칙을 제공하지 않음 | 공식 연구 기록. 논문의 모든 부록을 검사했다는 뜻은 아님. ACM full text 요청은 HTTP 403 |
| [NLR advanced computing report](https://docs.nrel.gov/docs/fy24osti/89025.pdf) | 2023 annual report | SWR-23-34는 eagle-jobs software record로 기재 | 소프트웨어 식별 근거. RADDiT 배포 crosswalk 증거 없음 |
| [eagle-jobs](https://github.com/NatLabRockies/eagle-jobs) | master, GitHub pushed_at 2024-03-09 | README가 연결한 선행 Eagle 연구. 공개 landing documentation에서 이번 Kestrel/RADDiT export authority를 찾지 못함 | 관련 저장소 탐색. 전체 이력을 소진했다는 주장 아님 |

검색어: historic_job_trace, original job id, slurm id, source row, row_id, crosswalk, embedding export, encrypted_embeddings, job_strings, subset, filter, sanitized, anonymized, mapping, manifest. NLR/NREL documentation·data catalog·software record·companion paper 관련 검색도 수행했다. 일부 검색은 무관한 결과만 반환했고, 새 authoritative crosswalk는 확보하지 못했다. 이는 전역 부재의 증명이 아니다.

재현 근거: GIT_HISTORY_SOURCE_AUDIT.json, GIT_PICKAXE_AND_LFS_AUDIT.json, PUBLIC_GITHUB_RECEIPTS.json, V14의 hash-bound LOCAL_AUTHORITY_SEARCH.json. Notebook 저장 output/이미지는 검색에 사용하지 않았다. 실제 source text는 .local/HISTORICAL_SOURCE_TEXT.json에 보존했다.
