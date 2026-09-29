# 배포 export 경로

확인한 경로는 historic → 8개 필드 문자열 → 4096행 batch JSON → Linq embedding → batch별 npy다. 배포 파일은 40,000행 단위 Parquet이며 마지막만 20,972행이다. 공개 npy output을 이어 붙여 metadata와 join하고 subset/filter·timezone 제거·vector transform을 적용한 뒤 chunk Parquet를 쓰는 operation은 조사한 source/history에 없다.

qint8 코드는 모델 weight quantization이다. 그것을 enc_embedding_int8 배포 열의 변환 코드라고 해석하지 않았다. embedding, concat, merge/join, dropna, script, runtime/power, encrypt/int8, write_parquet/to_parquet, 40000/4096, timezone 계열을 Git source와 notebook 저장 출력에서 확인했다. 서로 다른 tariff-aware code의 변환을 가져오지 않았다.

45개 footer 모두 timestamp[us], 물리 INT64, logical isAdjustedToUTC=false이며 timezone metadata가 없다. created_by는 parquet-cpp-arrow 16.1.0이다. 이 값은 writer engine 식별에 도움이 되지만 export script·모델 라이브러리 버전을 증명하지 않는다. Historic의 -06:00 metadata와 notebook FixedOffset(-360)은 저장된 표현의 근거다. 어떤 함수가 언제 제거했는지는 미해결이다.

새 진단: T0 EKEY2는 1,775,514개의 충돌 없는 유일 raw 후보를 유지한다. T1 EKEY0는 embedding 11행과 키가 겹치지만 유일 8쌍 모두 holdout 충돌, EKEY1의 유일 1쌍도 충돌, EKEY2는 0이다. DST 구간 20개 표본도 T0만 일치한다. 성능/일치율로 T0를 승인하지 않았다.

Historic 표시 종료일 >= 2024-04-23이라는 관측적 predicate가 1,780,972행의 raw metadata membership과 정확히 일치한다. 이는 단순 count equality를 넘어서는 결과이나 실제 source export query의 존재·동작·동기·timezone 처리까지 보증하지 않는다. 해당 날짜의 Git 및 targeted public follow-up에서도 source rule은 미확보다.

필요한 원본 자료: 사용한 historic revision과 source timezone 계약, 실제 .npy→encrypted Parquet export script/commit 또는 run manifest, 날짜/subset predicate와 row membership, model/tokenizer/library revisions, encrypted/int8 coordinate transform의 정의. 현재 provenance grade는 PARTIAL이며 source-backed timestamp 조건이 충족되지 않아 Level1을 승인하지 않는다.
