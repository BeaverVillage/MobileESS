# 부분집합 재구성과 출처 근거

2,557,884 historic 행의 raw EKEY2 membership은 배포 1,780,972행과 집합 및 key multiplicity 수준에서 재구성된다. 유일 후보 1,775,514, ambiguous member 5,458, 비포함 776,912행을 분리했다.

**관측된 표시 종료일 >= 2024-04-23** predicate는 배포 raw membership과 행 단위로 정확히 같다. 관측 member end-time envelope(2024-04-23 00:01:25–2025-03-10 04:19:04)도 같다. 단지 행수만 맞춘 것이 아니다. cached membership mask 전체와 비교하며 검증 시 원본 historic의 timezone-aware end_time으로 별도 계산한다. 날짜 signature는 등록한 관측 envelope 진단에서 도출했으며 임의 threshold 조합 검색은 하지 않았다. 정확한 export 코드/manifest 또는 독립된 실행 기록은 여전히 없다. 따라서 RAW_SUBSET_MEMBERSHIP_RECONSTRUCTED=TRUE와 EMBEDDING_SUBSET_FILTER_AUTHORITY_FOUND=FALSE를 구분한다.

다른 단일 후보들은 membership을 재현하지 못했다. Submit envelope는 2,156,714행, start envelope는 1,799,429행을 남긴다. Script nonnull은 2,421,026행을 남기고 136,858행을 제외한다. raw member에도 script null 120,141행이 있어 missing-script 제거 규칙은 실제 membership 설명과 맞지 않는다. Runtime/power는 모든 historic 행에서 nonnull·positive이고 시각 순서도 유효하다. 이를 상위 원본 수집 이전에도 결측이 없었다는 증거로 확대하지 않는다.

전체 29개 조건 중 28개 수치 진단을 했고 2개의 종료일/envelope 표현이 exact membership을 재현했다. CPU/GPU restriction은 직접 flag가 없어 NOT_TESTABLE이다. 익명 partition token을 CPU/GPU 의미로 추정하지 않았다. 월·partition·QoS·job_type 빈도는 설명용 enrichment로 보존했다. Unique raw와 나머지를 비교했으며 V13 semantic-runtime bias 분석을 실행한 것은 아니다.

R2 calendar-date predicate의 초기 ns/us 단위 실수는 명시적 datetime64[us] 변환으로 수정하고 독립 datetime 비교로 검증했다. Threshold 자체를 바꾸지 않았으며 기존 V6–V14R1 파일은 수정하지 않았다. 원본 row-order를 사용해 중복을 해결하지 않는다.
