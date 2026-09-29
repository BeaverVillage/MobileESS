# Embedding 부분집합 forensic

Historic 2,557,884행, embedding 1,780,972행, 차이 776,912행. EKEY2의 RAW_REPRESENTATION 키 집합은 historic의 정확히 1,780,972행과 대응한다. 키가 있는 모든 그룹의 양쪽 multiplicity도 일치한다. 이것은 어떤 metadata 부분집합이 배포됐는지에 대한 강한 진단 증거이며, 왜 그 행들을 골랐는지에 대한 근거는 아니다.

고유 후보는 1,775,514행(99.693538%); 나머지 5,458행은 2,514개 many:many 그룹이다. 공유 5개 필드를 모두 비교해도 이 그룹 수는 2,514개라서 start_time으로 개별 중복 행을 해소할 수 없다. 유일 후보의 float64 runtime/power bitwise 충돌은 0이고, start_time 충돌도 0이다.

고유 후보 source index 범위와 순서는 EMBEDDING_ORDER_AUDIT.json에 기록했다. 인접 역전 636,834건, 직접 prefix 아님, 연속 suffix 아님. 집합의 최소 historic index는 401,170, 최대는 2,557,883다. source index gap 합은 유일 후보 사이의 양의 차이를 합한 통계이므로 빠진 historic 행 776,912개와 혼동하지 않는다. 순서를 이용해 중복을 임의 배정하지 않았다.

조사 범위는 모든 로컬 reachable 21 commits, 3 remote branches, 태그 0개, 42 unique source/doc blobs, 삭제 이력, notebook code/markdown, LFS 포인터 이력이다. public prep는 전체 historic를 4096행 배치로 순차 처리한다. 소비 코드는 40,000행 chunk에 새 row_id를 매긴다. 두 단계 사이의 subset/export/encryption 구현은 찾지 못했다. 배포 payload SHA256과 Git LFS OID가 맞는다는 V14 증거는 파일의 동일성만 보증한다.

null/missing script, power availability, completion/runtime validity, date, CPU-exclusive, usable text, embedding failure, token length를 source code/document에서 조사했다. 공개 token max_length=2048는 truncation이고 특정 historic subset 제외 규칙의 증거가 아니다. README의 CPU-exclusive power 성과 역시 이 776,912행의 filter authority가 아니다. 누락 행수와 우연히 맞는 조건을 탐색해 규칙으로 채택하지 않았다.

EMBEDDING_SUBSET_FILTER_AUTHORITY_FOUND=FALSE. 필요한 자료는 chunk-global-row→original historic-row manifest, source export query와 filter/version, timestamp timezone 제거 계약, 동일 encrypted vector transform의 버전·설정이다. 부분집합이 존재한다는 결과와 배포 생성 경로의 완전한 입증은 별개다.
