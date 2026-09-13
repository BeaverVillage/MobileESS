# IEEE8500 topology-only deterministic selection — methodology v2

선정 전에 작성한 v2이다. 부모 workspace의 source/topology audit, v1 문서, FREEZE_MANIFEST.json과 638개 후보 pool은 변경하지 않는다. 사용자의 후속 지시에 따라 이 별도 디렉터리에서 12개 electrical host 선정만 수행한다.

## 입력과 불변 조건

허용 데이터는 부모 audit/의 candidate_pool_static_features.json, candidate_pair_metrics.npz, melbourne_12_anchors.json, melbourne_66_pair_geometry.json, primary_corridors.json, methodology_inputs.json, buses.json이며 원래 FREEZE_MANIFEST.json의 SHA256과 대조한다. 후보는 기존 순서의 638개 12.47-kV ABC primary bus만 사용한다. source/substation, regulator 양쪽 terminal, secondary, single/two-phase 제외 규칙과 기존 major-lateral/group ID는 그대로 유지한다. AIDC01–AIDC12는 서로 다른 12개 bus에 일대일 대응한다. source나 OpenDSS를 다시 읽거나 compile할 필요가 없다.

V41R4 및 May 결과를 읽지 않는다. 부하, AIDC power, voltage, line loading, sensitivity, loss, performance/objective, 운영 시계열은 선정 입력이 아니다. 고정 static access-anchor의 x_east_km/y_north_km만 Melbourne geometry로 사용한다. 원래 자료의 외부 경로는 접근하지 않는다.

## 정의와 hard criteria — v1 그대로

root=_hvmv_sub_lsb. Electrical distance는 원본 정적 line impedance 기반 tree 거리이며, regulator는 거리 0의 identity connector이다. Shared ratio는 C/(L_i+L_j−C), C는 공통 root-path impedance 합이다. root 상위 source 구간은 포함하지 않는다.

E_coord는 각각 중심화하고 RMS radius=1로 정규화한 Melbourne/IEEE8500 좌표 사이의 proper-rotation Procrustes RMS 오차이다. translation, uniform scale, rotation만 허용하고 reflection은 금지한다. E_pair는 각각 RMS로 정규화한 66 pair 거리 차이의 RMS이다. Retention은 site별 두 최근접 이웃 가운데 보존된 비율의 12-site 평균이다. 거리 동률은 AIDC ID 순으로 처리한다.

| Hard criterion | 변하지 않는 기준 |
|---|---:|
| distinct eligible bus / distinct coordinate | 정확히 12 |
| E_coord | ≤0.20 |
| E_pair | ≤0.20 |
| nearest-neighbor retention | ≥0.50 |
| 66 pair 각각 electrical tree distance | ≥0.9129072401559803 ohm |
| 66 pair 각각 geographic distance | ≥2221.532547954318 원본 좌표 단위 |

좌표 CRS/단위는 알 수 없으므로 geographic 값을 m/km로 바꾸지 않는다. 검증에서는 위 수치를 그대로 비교하며 hard threshold를 완화하는 tolerance는 두지 않는다.

## Electrical siting 우선순위

모든 hard criteria를 만족하는 mapping의 아래 tuple을 lexicographic하게 최소화한다. 앞선 목적을 개선하지 못하면 다음 목적을 평가한다. 각 연속 목적은 무차원 값에서 1e-9 단위로 반올림해 비교한다. 전역 lexicographic 최적값을 보장하는 절차는 아니다.

1. maximum pairwise shared-path ratio
2. mean pairwise shared-path ratio
3. negative minimum electrical distance / 전체 후보 maximum electrical distance
4. negative represented major-lateral count; negative represented group count; group occupancy count 제곱합 (기존 major 3개 + trunk/minor 1개)
5. negative minimum geographic distance / 전체 후보 geographic diameter
6. E_coord; E_pair; negative nearest-neighbor retention
7. AIDC01–AIDC12 순서의 lowercase bus ID tuple

v2에서 geographic dispersion의 우선 평가량은 minimum pair distance로 명확히 한다. convex hull area는 진단값으로 함께 저장하지만 점수에 추가하지 않는다. Mean electrical distance는 필수 보고 지표이며 핵심 우선순위에 새로운 목적을 끼워 넣지 않는다.

## 선정 전에 고정하는 결정적 절차

Python/NumPy/SciPy, single-thread 수치 라이브러리, seed=0 (실제로 난수 추출 없음), bus/site 사전순을 사용한다. 수행 시간에 따른 조기 종료나 사람이 고른 bus/seed는 사용하지 않는다.

1. Geometry multistart: Melbourne 중심/RMS 정규화 좌표를 0,5,…,355도 회전한다. IEEE 후보 pool RMS radius의 [0.30,0.40,0.50,0.60,0.70,0.80,0.90] 배 크기를 쓴다. translation center는 후보 bounding box 각 축의 [0.2,0.35,0.5,0.65,0.8] 위치의 Cartesian grid이다. 총 12,600개의 변환마다 12×638 squared-coordinate-cost Hungarian assignment를 구해 distinct bus mapping을 만든다.
2. 중복 mapping은 제거한다. Feasible mapping은 위 lexicographic tuple로, infeasible mapping은 (최대 정규화 hard violation, violation 합, E_coord+E_pair, bus tuple)로 정렬한다. 정규화 violation은 각 상한의 초과 비율 또는 각 하한의 부족 비율의 positive part이다.
3. Feasible geometric starts가 있으면 그 중 최대 32개, 그리고 별도로 infeasible starts 중 violation이 가장 작은 최대 64개를 사용한다. 시작점 수나 threshold를 결과에 따라 늘리거나 줄이지 않는다.
4. 각 start에서 최대 12 sweeps의 feasibility repair를 수행한다. AIDC01부터 AIDC12까지 해당 site를 pool의 모든 638개 bus로 교체한 mapping을 일괄 평가한다. 이미 사용 중인 다른 site의 bus는 제외한다. violation tuple이 가장 개선되는 교체만 채택한다. 매 sweep 끝에 66개 site-label swap도 평가한다. Feasible해지거나 전체 sweep에서 개선이 없으면 해당 repair를 끝낸다. 여기서는 infeasible 개선에만 violation score를 쓰고 성능 변수는 사용하지 않는다.
5. 모든 feasible repaired/geometric mapping을 모아 위 우선순위의 상위 최대 16개를 대상으로 deterministic feasible local improvement를 각각 최대 20 sweeps 수행한다. 각 sweep은 AIDC 순으로 638개 1-site 교체를 전부 검사하고, 모든 hard criteria를 만족하며 lexicographic tuple이 개선되는 최선의 교체를 채택한다. 이후 66개 label swap을 같은 기준으로 검사한다. 전체 sweep이 개선 없이 끝나면 해당 start를 종료한다. 상한에 도달하면 그대로 종료하고 이유를 로그에 남긴다.
6. 얻어진 feasible mapping 전체에서 최선 tuple을 최종 결과로 고른다. 독립 검증기가 tree path와 원본 좌표에서 모든 66 pair, geometry 및 자격 조건을 다시 계산해야 한다. selector cache의 점수만 복사해 승인하지 않는다.

Finite procedure가 hard-feasible mapping을 찾지 못하면 `DETERMINISTIC_PROCEDURE_NO_FEASIBLE_SELECTION_FOUND`로 보고한다. 이는 수학적 infeasibility 증명이 아니다. Hard criteria를 완화하거나 새 임의 host를 넣지 않는다.

## 승인과 산출물

절차/입력/code SHA256을 최초 실행 전에 PROCEDURE_FREEZE_MANIFEST.json에 기록한다. 결정적 절차를 완료하고 독립 검증에서 모든 hard criteria를 통과한 경우 상태는 **TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_SELECTION**이다. 전역 최적성, optimal AIDC siting, hosting capacity, 운영 성능 개선은 주장하지 않는다. 전역 optimality gap은 not certified로 명시한다.

Mapping에는 AIDC ID, bus ID, 원본 x/y, root로부터 corridor hop depth와 electrical distance, major-lateral/group ID를 저장한다. 66 pair ratio/distances, min/mean electrical distance, max/mean shared ratio, E_coord/E_pair/retention, site별 nearest neighbors, feeder topology plot, 재현 로그, 독립 검증 및 최종 SHA256 manifest를 함께 저장한다. AIDC load 추가 및 B0/B1/B2/B3 실행은 금지한다.
