# Runtime-vNext14R2 timestamp/export authority

Base: V14R1 Draft PR #87, `604aaefd8c6a23a68a34544411125c934144cb2e`.

결과는 STOPPED_TIMESTAMP_EXPORT_AUTHORITY_UNRESOLVED, provenance PARTIAL, NEW_ML_FITS=0이다. T0 EKEY2의 유일 raw 후보 1,775,514행과 ambiguous 5,458행을 보존했다. 새 T1 EKEY2는 0행이며 약한 key에서의 유일 후보는 모두 holdout 충돌이었다.

새로 historic의 **표시 종료일 >= 2024-04-23**이 1,780,972 raw subset membership과 행 단위로 정확히 일치함을 확인했다. 실제 exporter의 predicate·timezone stripping 코드/manifest는 찾지 못해 승인 기준을 낮추지 않았다. 21개 commits, 43개 source/doc blobs, 59개 notebook outputs, local 616개 text files 및 공식 공개 metadata를 조사했다. 46개 LFS 경로는 각 1개 버전이고 unreachable 객체는 현재 local에서 0개였다.

읽기 순서: FINAL_REVIEW_KO.md(50문항), FINAL_VERDICT.json, LEVEL1_MAPPING_AUDIT.json, TIMESTAMP_TRANSFORMATION_TESTS.csv, SUBSET_FILTER_FORENSIC.md. 각 세부 CSV·JSON·source/local/delivery manifests를 함께 제공한다. Level2·negative controls·V13 support/bias는 gate 미통과로 NOT_RUN이다. 미측정 값을 0으로 만들지 않았고 성공 crosswalk 파일은 없다.

재현 코드는 PyArrow projected columns와 R1 hash-verified numeric caches를 재사용한다. `transforms.py --replay`는 fresh process에서 seed1402 chunk permutation 후 canonical sorting 및 diagnostic mapping을 검증한다. `date_signatures.py`는 등록된 관측 date-envelope 진단을 처리한다. V14R1 exact join helper는 pure function으로만 재사용하며 이전 namespace의 entry point를 실행하거나 파일을 쓰지 않는다.

큰 diagnostic ledgers/logs는 .local에 보존하고 hash만 Git에 넣는다. 벡터 decode·모델 다운로드·re-embedding·runtime training/inference·April/May evaluation·V42 실행/변경은 없다. 다음 자료는 원본 export script/commit 또는 실행 manifest, timestamp/source timezone 계약, exact subset/query와 row IDs, model/tokenizer/library revision 및 encrypted vector transform이다.
