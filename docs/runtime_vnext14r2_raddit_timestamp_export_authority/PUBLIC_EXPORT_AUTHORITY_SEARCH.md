# 공식 export authority 검색

조회일 2026-09-29. R1의 hash-bound 공개 조사도 재사용했다. 이번 추가 검색은 timestamp/export/subset에 한정하며 인터넷 또는 저자 비공개 저장소의 전역 부재를 주장하지 않는다. 제3자 요약은 authority로 사용하지 않았다.

| URL | 발표·revision 날짜 | 정확히 뒷받침하는 내용 | 공식/primary 여부 | blocker 해소 여부 |
|---|---|---|---|---|
| [RADDiT](https://github.com/NatLabRockies/raddit/tree/ae1bf132addb41b469f3ef25a7626fe5ab06bc81) | main 2026-01-29, 최초 source 2025-04-25 | 공개 preparation/embedding/consumer 코드와 sanitized artifact 배포. 실제 export script는 조사한 이력에서 미발견 | Primary | Q2/Q3 미해소 |
| [공식 API](https://api.github.com/repos/NatLabRockies/raddit/issues?state=all&per_page=100), [PR API](https://api.github.com/repos/NatLabRockies/raddit/pulls?state=all&per_page=100) | 조회일 현재 | all-state issue/PR 빈 배열. 3개 branch, 태그 없음. fork 목록에 jdseng/raddit 하나 | Primary | 추가 export 기록 미확보. R1 fork 비교는 ahead=0, behind=2 |
| [NLR Data Catalog](https://data.nlr.gov/search?search=RADDiT) | 웹 revision 미표시, 조회일 현재 | HTTP 200 search landing 확인. 응답에서 실제 row crosswalk/export 규칙을 확보하지 못함 | 공식 | 미해소. 동적 검색 전체가 검증됐다는 주장이 아님 |
| [NLR 연구 기록](https://research-hub.nlr.gov/en/publications/energy-aware-hpc-scheduling-with-llm-based-power-prediction/) | 2025, NLR/CP-2C00-95075 | RADDiT 관련 논문 식별, enriched job scripts에 기반한 embedding을 사용하는 연구임을 확인 | 공식 primary 연구 metadata | abstract는 timestamp/export manifest를 제공하지 않음 |
| [SC25 proceedings](https://sc25.supercomputing.org/proceedings/workshops/workshop_pages/ws_ss107.html) | SC25, 2025-11-16–21 | 관련 논문 저자·연구 개요 확인 | 공식 학회 | 세부 필터·시간 변환 미해소 |
| [ACM DOI](https://dl.acm.org/doi/10.1145/3731599.3767563), [PDF](https://dl.acm.org/doi/pdf/10.1145/3731599.3767563) | 2025-11-16 print, 2025-11-07 DOI 생성 | Crossref publisher-deposited metadata와 full-text URL 확인. 웹 도구로 full text/PDF를 회수하지 못함 | Primary publisher / 등록 metadata | full methods·supplement를 검사했다고 주장하지 않음 |
| [Crossref API](https://api.crossref.org/works/10.1145/3731599.3767563) | indexed 2026-08-21 | HTTP 200, 논문 식별·공식 PDF 경로. 관계 metadata는 비어 있음 | Publisher-deposited metadata | 독립 export manifest 없음 |
| [OSTI DOI API](https://www.osti.gov/api/v1/records?doi=10.1145%2F3731599.3767563) | 조회일 | bounded HTTP 요청 timeout. 검색엔진의 title+OSTI 조회에서도 새로운 공식 export authority 미확보 | 공식 endpoint, 조회 실패 | 미해소, record 부재로 해석하지 않음 |
| [NLR PDF 경로 조회](https://docs.nlr.gov/docs/fy26osti/95075.pdf) | publication number 기반 후보 URL | 회수 실패. 이 URL의 존재를 확인한 것은 아님 | 공식 domain의 후보 경로 | 미해소 |
| [SWR-23-34 관련 보고서](https://docs.nrel.gov/docs/fy24osti/89025.pdf), [eagle-jobs](https://github.com/NatLabRockies/eagle-jobs) | 2023 annual report / R1 확인 master pushed 2024-03-09 | 선행 Eagle 연구 software record와 관련 저장소. R1 검색 결과를 hash-bound 재사용 | 공식/primary | Kestrel embedding export authority 아님 |
| [Linq model card](https://huggingface.co/Linq-AI-Research/Linq-Embed-Mistral), [model API](https://huggingface.co/api/models/Linq-AI-Research/Linq-Embed-Mistral) | API lastModified 2024-06-05 | 현재 공개 sha `0c1a0b0589177079acc552433cad51d7c9132379`, pooling/normalization 예제 확인 | 모델 제작자 primary | RADDiT 실행 당시 resolve된 revision·환경·encrypted transform은 입증하지 못함 |

검색어는 RADDiT, historic_job_trace, encrypted_embeddings, timezone, America/Denver, embedding export, Kestrel embedding, job scripts, semantic search, int8, Linq-Embed-Mistral, row mapping 및 논문 정확한 제목/DOI였다. 무관한 동명 검색 결과와 제3자 성능 요약은 제외했다. 성능 수치로 어떤 변환·필터도 선택하지 않았다.

기계 판독 receipt는 PUBLIC_SOURCE_RECEIPTS.json에 있다. 현재 model HEAD를 과거 생성 revision으로 대입하지 않았다. 외부 메일·이슈·PR 댓글 등 저자 연락은 하지 않았다.
