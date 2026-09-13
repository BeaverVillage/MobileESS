# IEEE8500 source-proximity guard 재선정

**TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_SELECTION**. 원래 638개 candidate의 root electrical-distance q05=1.3819547376654384 ohm 미만 32개를 hard-exclude하여 606개 pool에서 동일한 v2 결정적 절차를 재실행했다. 나머지 hard criteria, Melbourne geometry 및 lexicographic ordering은 그대로 유지했다. 모든 조건을 독립 검증에서 통과했고 동일 절차 2회 실행의 mapping/decision log가 일치했다. 전역 최적성은 주장하지 않는다.

## 12-site mapping

Root는 _hvmv_sub_lsb이다. Depth는 집계 corridor hop 수, electrical root distance는 frozen impedance tree metric이다.

| AIDC | Guarded IEEE8500 host | Depth | Root distance (ohm) | v2 대비 |
|---|---|---:|---:|---|
| AIDC01 | `l3234149` | 34 | 1.853953615 | 유지 |
| AIDC02 | `e182733` | 232 | 13.353642251 | 유지 |
| AIDC03 | `m1027055` | 243 | 14.196739013 | 유지 |
| AIDC04 | `m1069411` | 226 | 11.629006421 | 변경 |
| AIDC05 | `l2688693` | 88 | 4.903899887 | 변경 |
| AIDC06 | `m1142814` | 65 | 3.393852487 | 유지 |
| AIDC07 | `m1026690` | 225 | 12.201711927 | 변경 |
| AIDC08 | `l3123452` | 71 | 3.103538467 | 변경 |
| AIDC09 | `l2728247` | 96 | 5.428287813 | 변경 |
| AIDC10 | `l2973833` | 29 | 1.529107248 | 변경 |
| AIDC11 | `m1047763` | 219 | 11.449474834 | 유지 |
| AIDC12 | `e192258` | 34 | 1.634678318 | 변경 |

## v2 대비 변경 site만

| AIDC | 기존 v2 | Guarded selection |
|---|---|---|
| AIDC04 | `l2935549` | `m1069411` |
| AIDC05 | `l2804249` | `l2688693` |
| AIDC07 | `m1026701` | `m1026690` |
| AIDC08 | `m3037449` | `l3123452` |
| AIDC09 | `l2990826` | `l2728247` |
| AIDC10 | `m1166375` | `l2973833` |
| AIDC12 | `d5710794-3_int` | `e192258` |

총 7개 site의 bus가 변경되었고 5개는 유지되었다. 기존 12개 host 중 새로운 guard로 직접 제외되는 host는 d5710794-3_int이다. 나머지 변경은 수정된 candidate pool에서 전체 12-site deterministic procedure를 다시 수행한 결과이다. 운영 성능이 개선되었다는 판단은 하지 않는다.

638개 root-distance 분포 및 percentile 통계는 ROOT_DISTANCE_GUARD_AUDIT.json과 CANDIDATE_ROOT_DISTANCE_DISTRIBUTION.csv, 제외 32개는 ROOT_DISTANCE_EXCLUDED_CANDIDATES.csv, 수정 pool은 GUARDED_CANDIDATE_POOL.csv에 있다. 전체 좌표/depth/root distance/group은 AIDC01_AIDC12_IEEE8500_MAPPING.csv에 저장했다. 66 pair 및 geometry 검증은 ALL_66_PAIR_METRICS.csv와 SELECTION_VALIDATION.json에 있다.

selection_v2 및 모든 기존 evidence는 변경하지 않았다. V41R4 또는 May/B0-B3/voltage/loading/sensitivity/performance 결과를 읽지 않았다. AIDC load/PCC 추가, OpenDSS compile 및 B0-B3 실행은 하지 않았다. Source-proximity guard는 topology-only 제한이며 operational benefit에 대한 증거가 아니다.

실행 전 동결은 PROCEDURE_FREEZE_MANIFEST.json, 최종 hash 동결은 GUARDED_SELECTION_FREEZE_MANIFEST.json, v2 전체 파일의 사전/사후 무결성은 V2_IMMUTABILITY_BEFORE.json 및 V2_IMMUTABILITY_VERIFICATION.json에 기록한다.
