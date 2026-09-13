# FINAL AIDC authority + topology-only STA service registry

**TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_STA_SELECTION**. AIDC 12개를 v3 그대로 FINAL authority로 동결하고 STA 12개를 추가 선정했다. 모든 24개 host는 서로 다른 guard 통과 12.47-kV ABC primary bus이며 모두 MESS service location이다. AIDC host 변경=0, PCC 생성=0, background scaling=0, B0–B3 실행=0. 운영 성능 결과를 읽거나 선정에 사용하지 않았다.

| Location | IEEE8500 electrical bus | Depth (corridors) | Root distance (ohm) |
|---|---|---:|---:|
| AIDC01 | `l3234149` | 34 | 1.853954 |
| AIDC02 | `e182733` | 232 | 13.353642 |
| AIDC03 | `m1027055` | 243 | 14.196739 |
| AIDC04 | `m1069411` | 226 | 11.629006 |
| AIDC05 | `l2688693` | 88 | 4.903900 |
| AIDC06 | `m1142814` | 65 | 3.393852 |
| AIDC07 | `m1026690` | 225 | 12.201712 |
| AIDC08 | `l3123452` | 71 | 3.103538 |
| AIDC09 | `l2728247` | 96 | 5.428288 |
| AIDC10 | `l2973833` | 29 | 1.529107 |
| AIDC11 | `m1047763` | 219 | 11.449475 |
| AIDC12 | `e192258` | 34 | 1.634678 |
| STA01 | `m1142810` | 66 | 3.971984 |
| STA02 | `m1166366` | 27 | 1.419586 |
| STA03 | `l3030197` | 58 | 2.358314 |
| STA04 | `m1089115` | 106 | 7.138513 |
| STA05 | `l2990826` | 101 | 5.558984 |
| STA06 | `m1069310` | 244 | 12.393388 |
| STA07 | `m1009763` | 231 | 13.194784 |
| STA08 | `e182732` | 206 | 10.166233 |
| STA09 | `m1026855` | 196 | 8.753275 |
| STA10 | `e182746` | 159 | 6.737183 |
| STA11 | `r18241` | 218 | 11.316724 |
| STA12 | `m1027043` | 242 | 14.125251 |

좌표/traffic anchor/group을 포함한 전체 mapping은 FINAL_24_LOCATION_ELECTRICAL_MAPPING.csv에 있다. FINAL_AIDC_HOST_AUTHORITY.json은 원래 v3 mapping의 bytes hash와 최종 불변 authority를 기록한다.

STA geometry: E_coord=0.199932686, E_pair=0.123767137, 2-neighbor retention=70.83% (17/24). STA electrical distance min/mean=0.938727/8.448961 ohm; shared-path ratio max/mean=0.665054/0.318583. 사전 정의한 모든 hard criteria를 독립 검증에서 통과했다. 동일 절차 2회 실행의 최종 mapping과 결정 로그가 일치했다. 전역 최적성이나 optimal siting은 주장하지 않는다.

**Cross-pair 진단의 한계:** AIDC–STA 144 pairs의 최소 electrical distance는 0.071487710 ohm, 최대 shared ratio는 0.994964498이다. STA–STA electrical spacing 기준보다 가까운 cross pairs는 9개다. 이는 cross pair에 부과한 hard criterion이 아니므로 통과/실패 판정에 사용하지 않았다. Melbourne 최근접 AIDC의 geographic identity는 6/12 STA에서 보존된다. 따라서 24개 전체 상대 geometry나 AIDC–STA 간 전기적 독립성이 보장된다는 해석은 하지 않는다. Cross metrics는 operational benefit을 뜻하지 않는다.

66 STA pairs와 144 cross pairs, nearest-AIDC/alignment diagnostics를 CSV/JSON으로 저장했다. 그림은 원본 ABC primary topology에 fixed AIDC와 selected STA를 표시하며 SVG/PNG로 저장한다. 절차와 입력/code는 선정 전에 PROCEDURE_FREEZE_MANIFEST.json으로 동결했고 최종 산출물은 SERVICE_REGISTRY_FREEZE_MANIFEST.json으로 고정한다.
