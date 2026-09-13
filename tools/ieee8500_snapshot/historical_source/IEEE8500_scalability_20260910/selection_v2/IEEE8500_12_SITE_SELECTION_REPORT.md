# IEEE8500 topology-only 12-site deterministic selection

**TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_SELECTION** — 모든 기존 hard criteria를 독립 검증에서 통과했다. AIDC 수는 정확히 12개다. 전역 최적성이나 optimal AIDC siting을 주장하지 않는다. Source/topology 감사와 기존 후보 pool은 수정하지 않았다. V41R4/May 결과를 읽지 않았으며 OpenDSS compile, AIDC load 추가, B0–B3 실행은 모두 0회다.

## 최종 mapping

좌표는 원본 Buscoords의 값이다. 알려진 CRS/거리 단위가 없으므로 m/km로 해석하지 않는다. Feeder depth는 root `_hvmv_sub_lsb`에서의 상별 bank 집계 corridor hop 수이며, electrical root distance는 frozen static impedance metric의 합이다.

| AIDC | IEEE8500 bus | X | Y | Depth (hops) | Root distance (ohm) | Group |
|---|---|---:|---:|---:|---:|---|
| AIDC01 | `l3234149` | 1691184.306657 | 12273169.707430 | 34 | 1.853953615 | TRUNK_OR_MINOR_LATERAL |
| AIDC02 | `e182733` | 1662211.058118 | 12281038.938541 | 232 | 13.353642251 | MAJOR:m1047526 |
| AIDC03 | `m1027055` | 1664887.749064 | 12293210.239417 | 243 | 14.196739013 | MAJOR:m1047526 |
| AIDC04 | `l2935549` | 1673877.428688 | 12276709.061033 | 219 | 11.026257245 | MAJOR:l2820531 |
| AIDC05 | `l2804249` | 1679930.255830 | 12270197.584291 | 86 | 4.603917727 | MAJOR:l3081380 |
| AIDC06 | `m1142814` | 1685271.460315 | 12273423.839654 | 65 | 3.393852487 | MAJOR:l3081380 |
| AIDC07 | `m1026701` | 1665004.390856 | 12278164.435371 | 223 | 12.025036604 | TRUNK_OR_MINOR_LATERAL |
| AIDC08 | `m3037449` | 1681586.420184 | 12278554.788267 | 82 | 3.555870942 | TRUNK_OR_MINOR_LATERAL |
| AIDC09 | `l2990826` | 1678542.047701 | 12279603.163564 | 101 | 5.558983841 | TRUNK_OR_MINOR_LATERAL |
| AIDC10 | `m1166375` | 1688163.469790 | 12275377.308072 | 33 | 1.643648212 | TRUNK_OR_MINOR_LATERAL |
| AIDC11 | `m1047763` | 1670298.081741 | 12288479.510964 | 219 | 11.449474834 | MAJOR:m1047526 |
| AIDC12 | `d5710794-3_int` | 1693954.030051 | 12277578.757098 | 2 | 0.013105271 | TRUNK_OR_MINOR_LATERAL |

D5710794-3_INT를 포함한 모든 host는 기존 638개 pool에 있던 bus이다. Pool의 source/substation/regulator 제외 판정을 변경하거나 후보를 추가하지 않았다. 명칭의 `_INT`만으로 기존 자격 판정을 새로 변경하지 않았다.

## 검증 결과

| 지표 | 값 |
|---|---:|
| E_coord | 0.19973435477794546 |
| E_pair | 0.13024839036775257 |
| nearest_neighbor_retention | 0.9166666666666666 |
| nearest_neighbor_preserved_directed_relations | 22 |
| nearest_neighbor_total_directed_relations | 24 |
| min_electrical_tree_distance_ohm | 1.5046954171051596 |
| mean_electrical_tree_distance_ohm | 8.498402998427293 |
| max_shared_path_ratio | 0.5979814526345228 |
| mean_shared_path_ratio | 0.22856555877311102 |
| min_geographic_distance_original_units | 3219.8283459468025 |
| geographic_convex_hull_area_original_units_squared | 370239176.65636426 |
| represented_major_laterals | 3 |
| represented_groups | 4 |
| proper_rotation_determinant | 1.000000000000001 |
| E_coord_margin_to_limit | 0.0002656452220545502 |
| E_pair_margin_to_limit | 0.06975160963224744 |

E_coord는 0.20 제한에 가깝지만 hard threshold를 완화하지 않고 통과했다. E_coord 여유는 0.000265645이다. Retention은 24개의 directed two-neighbor 관계 중 22개 보존이며 완전 일치라는 뜻은 아니다. 3개 major lateral 및 trunk/minor의 4개 그룹이 모두 대표된다. Group occupancy: `{"MAJOR:l2820531": 1, "MAJOR:l3081380": 2, "MAJOR:m1047526": 3, "TRUNK_OR_MINOR_LATERAL": 6}`.

66쌍 모두 electrical distance ≥0.9129072401559803 ohm 및 geographic distance ≥2221.532547954318 original units를 만족한다. 전체 ratio, 공통 경로 impedance, LCA와 거리 값은 `ALL_66_PAIR_METRICS.csv`에 저장했다. Site별 이웃 집합은 `NEAREST_NEIGHBOR_RETENTION.csv`에 있다. Mapping의 root 경로는 `SELECTED_ROOT_PATHS.json`에 있다.

독립 검증기는 frozen primary corridors에서 root 경로를 재구축하여 교집합/대칭차집합을 합산했다. Geometry는 selector의 닫힌 형태 공식을 사용하지 않고 proper-rotation SVD와 직접 좌표 residual로 다시 계산했다. Selector와 독립 검증 지표의 최대 절대 차이는 4.55e-13이다.

## 결정적 절차와 한계

선정 전 v2 문서와 selector code를 `PROCEDURE_FREEZE_MANIFEST.json`으로 고정했다. 12,600개 geometric transforms에서 12,366개 distinct mappings를 만들었다. 초기 geometric feasible mapping은 0개였다. 정해진 64개 repair start에서 36개 feasible mapping을 얻고, 우선순위 상위 16개를 finite local improvement 절차로 평가했다.

핵심 우선순위는 maximum shared ratio → mean shared ratio → minimum electrical distance → major-lateral/group diversity → geographic dispersion → Melbourne relative-shape error였다. Hard criteria는 v1과 동일하다. 모든 설정은 `12_SITE_CANDIDATE_SELECTION_METHODOLOGY_V2.md`, 실행 로그는 `selection_run.log`, 개별 repair/descent 이력은 JSON에 있다.

동일한 frozen procedure를 2회 실행해 wall time을 제외한 search summary와 최종 mapping이 동일함을 확인했다. Repair 및 local improvement 결정 로그도 SHA256이 일치했다. 증거는 `DETERMINISM_VERIFICATION.json`과 첫 실행 기록에 있다.

이 결과는 동결 절차에서 얻은 feasible selection이다. 모든 12-bus 조합에 대한 탐색이나 전역 최적성 증명은 수행하지 않았다. Operational hosting capacity, AIDC 부하 수용 가능성, voltage/thermal 성능 및 B0–B3 개선 여부는 평가하지 않았다.

## 그림과 동결

![Selected sites on canonical feeder](FEEDER_TOPOLOGY_12_SITES.png)

그림은 원본 ABC primary topology의 646 corridors를 회색으로 표시하고 root→host 경로와 AIDC01–AIDC12를 강조한다. SVG도 함께 저장했다. 별도 `MELBOURNE_RELATIVE_GEOMETRY.png`는 proper rotation 후의 상대 구조 비교다.

원본 동결 manifest SHA256: `06df7aab97f246776ae96631b009b7409d343755b85a5ad64648d622250ba452`

사전 procedure freeze SHA256: `3e8b792170b88778902745bbddd0a5610900f2dc568ac10e4d6f74eb9a8ba6d1`

최종 산출물과 code/input hash는 `SELECTION_FREEZE_MANIFEST.json`에 기록한다. 모든 새 파일은 selection_v2 아래에만 썼다.
