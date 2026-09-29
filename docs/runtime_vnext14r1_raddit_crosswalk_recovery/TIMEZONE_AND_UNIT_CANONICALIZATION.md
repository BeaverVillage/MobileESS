# 시간·단위 비교 계약

사전 규칙은 PREREGISTRATION.json에 match rate 계산 전에 고정했다.

* RADDiT historic: `timestamp[us, tz=-06:00]`. 기록된 고정 offset을 보존하고 UTC epoch microseconds도 별도 projection에 저장했다. 이 고정 offset을 임의로 America/Denver의 계절별 offset으로 재해석하지 않았다.
* Embedding: `timestamp[us]`, timezone 없음. UTC라고 가정하거나 historic의 -06:00을 옮겨 붙이지 않았다. source-backed UTC comparison은 **NOT_RUN_NAIVE_EMBEDDING_TIMEZONE_UNPROVEN**이다. 실패 match count 0으로 표시하지 않는다.
* RAW_REPRESENTATION: historic의 표시된 연월일·시분초·microsecond와 embedding의 저장된 naive 구성요소를 그대로 비교한다. historic의 `tz_localize(None)`은 이 진단에만 사용했다. 동일한 절대 시각의 입증이나 embedding UTC 변환을 의미하지 않는다. -06:00, UTC, DST 중 어느 의미인지 matching 성능으로 선택하지 않았다.
* Kestrel datacard: Slurm `%Y-%m-%dT%H:%M:%S%z`와 PostgreSQL timestamptz. 실제 저장 offset을 UTC로 정규화하는 F0–F2 비교를 사전 등록했지만 Level1 authority 중단으로 실행하지 않았다.
* 모든 timestamp precision은 microsecond 그대로이며 floor/truncation은 하지 않았다. subsecond/null 계수는 EMBEDDING_SCHEMA_AUDIT.json 및 EXACT_SHARED_FIELD_SUPPLEMENT.json에 있다.
* runtime/power는 float64 숫자 및 bitwise equality로 검사했다. EKEY2의 유일 raw 후보 1,775,514쌍에서 두 float의 numeric/binary 불일치가 모두 0이었다. tolerance를 도입하지 않았다.
* Kestrel duration의 seconds 변환은 단위 변환으로만 허용한다. `memory_req`는 Slurm의 per-node/per-CPU 접미사를 포함할 수 있어 `memory_req_raw`와 동일하다는 근거가 없고 F3는 비활성이다. 범주 anonymization 대응표가 없어 F4도 비활성이다.

미해결 naive timestamp 의미는 사전 등록한 source-authorized timestamp 조건을 충족하지 못한다. 유일 raw 후보는 유력한 행 연결 증거지만 이번의 verified physical crosswalk로 승격하지 않는다. 남은 5,458개의 duplicate rows는 다른 matched subset의 논리적 불가능성을 뜻하지 않으며, 순서만으로 해소할 수도 없다.
