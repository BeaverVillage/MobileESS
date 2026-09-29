# Git lineage 조사

HEAD `ae1bf132addb41b469f3ef25a7626fe5ab06bc81`, reachable commits **21**, 고유 source/document blobs **43**(.gitattributes 포함), main/pearc25/synthetic-trace-generator 3 branches, 태그 0개. `git fsck --unreachable --no-reflogs --connectivity-only`의 현재 local unreachable 객체는 **0개**다. 원격에서 force-delete된 모든 과거 객체까지 존재하지 않는다는 뜻은 아니다.

| 명령·검색 | 파일/commit | 증거와 해석 | confidence / Q1–Q4 |
|---|---|---|---|
| log --all --oneline --decorate, --full-history --stat | 최초 0c71fa5 → ae1bf132 | 모든 reachable 이력과 commit messages를 기록 | 로컬 범위 높음, 생성 operation 미해소 |
| -S encrypted_embeddings, enc_embedding_int8 | semantic_search / validate_datasets notebook | 배포 파일을 읽는 consumer와 저장 dtype 출력 존재 | 소비/저장 상태 근거. Q2/Q3 미해소 |
| -S job_strings, historic_job_trace, 4096 | prep_for_embedding / embed_job_scripts | 4096행 순차 text batches → npy output | 공개 생성 경로 확인, 배포 export 미해소 |
| -S submit_time, FixedOffset | notebook source 및 stored outputs | FixedOffset(-360) historic와 naive embedding dtype가 함께 확인됨 | Q1 저장 representation 확인. 전환 operation 증명 아님 |
| -S tz_localize, tz_convert, timezone | 2026 tariff-aware code | 다른 데이터/파이프라인의 timezone 변환이다 | 이 2025 embedding export에 전용 불가 |
| -S to_parquet, 40000, targeted git grep | reachable source/notebook | 관련 chunk의 40,000행 크기는 출력에 존재하나 이를 생성하는 writer는 미확인 | Q2/Q3 미해소 |
| log --name-status --find-renames, git diff initial..HEAD | scripts/notebooks의 energy_aware_scheduling 이동 및 삭제된 quickstart output | rename/delete 전 source blob도 포함하여 검사 | 누락된 writer를 찾지 못함 |
| git show/cat-file notebook blobs | validate_datasets의 여러 버전 | 104 cells와 59 output records 검사, 관련 evidence 28행 | source뿐 아니라 text/html/plain 출력 검사. 이미지 MIME 9개는 decode하지 않음 |
| LFS 역사 | historic 1개 + chunks 45개 | 46 paths, 46 distinct version records. 각 path는 공개 이력에서 한 LFS OID | 교체/과거 schema 변화의 근거 없음. 전역 부재 주장 아님 |
| -S 2024-04-23 | 모든 source/notebook/json 이력 | 관측된 end-date membership signature의 literal 검색은 빈 결과 | signature는 관측적이며 Q3 export authority 미해소 |

각 명령의 전체 output, blob OID·commit/path 참조는 GIT_DEEP_SEARCH_RECEIPT.json에 있다. NOTEBOOK_PROVENANCE_EVIDENCE.csv의 supports_*는 검색 lead이며 자동 승인 flag가 아니다. Raw Git 저장소에는 fetch/checkout/gc/쓰기 작업을 하지 않았다. 역사 LFS 대용량 download도 없다.
