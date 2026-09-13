# IEEE8500 12-site candidate-selection methodology — topology-only freeze v1

이 문서는 선정 방법을 동결한다. AIDC 수는 **12개**이며, IEEE8500 host bus는 **아직 선정하지 않았다**. 최적화와 B0/B1/B2/B3 실행 횟수는 0이다. 아래 수치와 우선순위는 May 성능 결과를 사용하지 않은 사전 설계값이며, 선정 결과를 보고 조정하지 않는다.

## 허용 입력과 동결 경계

- `audit/source_manifest.json`으로 고정한 원본 IEEE8500 회로, 전압 등급, phase 연결, line impedance, bus 좌표만 사용한다. 회로의 부하량은 compile에 원본 그대로 존재하지만 선정 점수에는 사용하지 않는다.
- Melbourne 구조는 기존 모델의 **고정 IDC access anchor**를 사용한다. WSL `04_frozen_topology/v01_reduced48_final_v2_package/v01_reduced48_nodes_v2.csv`와 V41R4 코드의 `SERVICE_NODES`가 가리키는 `final_service_nodes_24.csv`를 traffic_node로 연결하였다. IDC01–IDC12 ↔ TN_01–TN_12 ↔ IDC_01–IDC_12를 모두 검증했다. 출력 식별자는 AIDC01–AIDC12이다.
- 정확한 외부 원본 경로와 SHA256은 `audit/melbourne_static_sources.json`, 12개 anchor는 `audit/melbourne_12_anchors.csv`, 66개 상대 거리쌍은 `audit/melbourne_66_pair_geometry.csv`에 고정했다. 원본 파일은 읽기만 하고 사본은 이 workspace에 보관했다.
- 앞서 존재하던 representative-real-facility mapping의 위경도는 모델의 access anchor와 다르므로 선정 입력으로 사용하지 않는다. 기존 IEEE123 host bus 번호도 전이하지 않는다.
- May 결과, B0–B3 목적값, 운영 부하/traffic/workload 시계열, congestion·voltage violation·loss·sensitivity·ESS benefit는 입력 금지다. April 성능을 이용한 선정 튜닝도 하지 않는다.

## 후보 자격 — 638개 전기적 후보, 12개 host 미선정

모든 조건을 동시에 만족해야 한다.

1. `sqrt(3) × OpenDSS Bus.kVBase = 12.47 kV` (수치 판정 허용오차 ±0.1%). 실제 운전 전압 magnitude가 아닌 nominal base이다.
2. bus nodes 집합이 정확히 `{1,2,3}`이고, feeder head에서 해당 bus까지 A/B/C 모두 연결된 primary 경로가 존재한다. 단상 세 개로 나뉘어 모델링된 series link와 regulator bank는 실제 phase 연결을 모아 판단한다.
3. source/substation 및 regulator 단자 제외. 보수적으로 regulator의 **양쪽 단자 모두** 제외하고, `regxfmr_*`, substation transformer 단자, `hvmv_sub` 관련 bus와 `sourcebus`도 제외한다. 이 조건으로 총 11 buses를 제외하며 이 중 9개가 12.47-kV ABC bus이다.
4. secondary, single-phase 및 two-phase primary bus 제외. 특히 secondary `.1.2`는 ABC가 아니다.
5. canonical root와 연결되고, 원본 Buscoords에서 유한한 좌표가 정의되어야 한다. 638개 후보 모두 좌표가 있으며 서로 다른 좌표이다.

`audit/buses.csv`는 전체 bus별 제외 사유, `audit/candidate_pool_static_features.csv`는 무순위 자격 pool이다. 파일의 bus 정렬은 식별자 사전순이며 추천 순위가 아니다. 모든 `selected` 값은 false이다. 후보 목록은 수용 용량이나 AIDC 접속 가능성을 보증하지 않는다.

## 전기적 tree와 major lateral 정의

ABC primary graph는 647 vertices / 646 corridors의 tree이다. root는 기존 substation 저압측 feeder regulator 출력 `_hvmv_sub_lsb`이며, root 자체는 host 후보가 아니다. 같은 bus pair를 잇는 ABC 단상 regulator/link는 하나의 corridor로 집계한다. 실제 회로 요소는 수정하지 않는다.

각 line corridor의 가중치 w는 `length × mean(|Zaa|, |Zbb|, |Zcc|)` [ohm]이다. 여기서 `Zpp = Rpp + jXpp`는 원본 line series impedance matrix의 대각 성분이다. ABC가 세 단상 line으로 표현되면 세 상의 실제 series impedance를 평균한다. 각 line의 길이와 impedance는 OpenDSS의 동일 단위쌍을 사용하므로 units=none인 가상 link도 임의 km 환산 없이 처리한다. Regulator bank는 이 선정용 metric에서 가중치 0의 identity connector로 취급한다. 이것은 정적 impedance 기반 거리이며 전압 민감도나 정확한 Thevenin impedance가 아니다.

주간선은 root부터 시작하여 매 분기에서 **하위 적격 bus 수가 가장 큰 child**를 따라가는 경로로 정의한다. 동률은 bus ID 사전순으로 푼다. 이 주간선에서 갈라지는 side subtree 중 적격 bus가 `ceil(0.05 × 638) = 32`개 이상인 것을 major primary lateral로 고정한다. major subtree끼리는 겹치지 않는다. 나머지는 trunk/minor 그룹이다. 이 사전 정의로 얻은 major lateral은 **3개**이며, 12개로 만들기 위해 threshold를 낮추지 않는다.

| Major lateral root | Junction | 하위 후보 수 |
|---|---|---:|
| l3081380 | m1142843 | 134 |
| m1047526 | m1047521 | 122 |
| l2820531 | m1047507 | 61 |

Trunk/minor 그룹 후보는 321개다. 위 root 이름은 분류 경계이며 AIDC host 선정이 아니다. topology 자체에는 전력망이 하나이므로 서로 다른 lateral도 공통 feeder trunk를 공유한다.

## 평가량의 정확한 정의

각 후보 b의 root 경로를 P(b), 그 가중치 합을 L(b)라고 한다. 두 후보 u,v의 공통 upstream 길이는 C(u,v) = Σ[w(e), e ∈ P(u) ∩ P(v)]이다.

- **Shared upstream-path ratio**: `R(u,v) = C(u,v) / [L(u)+L(v)−C(u,v)]`. 가중 Jaccard 비율이며, root보다 상위 source/substation 구간은 포함하지 않는다. worst pair와 66쌍 평균을 모두 평가한다.
- **Electrical tree distance**: `D(u,v) = L(u)+L(v)−2C(u,v)`. 66쌍의 최소값과 평균값을 평가한다.
- **Geographic distance**: 원본 Buscoords의 Euclidean 거리. 좌표 CRS/단위가 원본에서 검증되지 않았으므로 미터나 km로 해석하지 않는다. 후보 pool의 최대 pair distance로 정규화한다.
- **Melbourne 상대 구조**: 12개 고정 model anchor 위경도를 평균 위도 기준 local east/north 평면으로 변환한다 (`R=6371.0088 km`). 12-site mapping π에서 Melbourne과 선택된 IEEE8500 좌표 각각을 중심화하고 RMS radius로 정규화한다. translation·uniform scale·rotation은 허용하지만 reflection은 허용하지 않는다. 최적 proper rotation의 Procrustes RMS residual을 E_coord로 정의한다.
- **Pair shape error**: 66개 Melbourne 거리와 66개 IEEE8500 거리를 각각 RMS pair distance로 나눈 후 차이의 RMS를 E_pair로 정의한다. 가까운/먼 site 구조를 직접 비교한다.
- **Local-neighborhood retention**: 각 site의 두 최근접 이웃 집합에 대하여 보존된 이웃 수를 2로 나누고 12 sites 평균을 취한다. 거리 동률은 site ID 사전순이다.

## 고정 feasibility 조건과 최적화 우선순위

후속 선정 실행은 서로 다른 12개 bus와 AIDC01–AIDC12의 일대일 mapping을 함께 구한다. 후보 pool 전체의 203,203개 pair에서 계산한 5th percentile을 거리 하한으로 사용한다. quantile은 linear interpolation이다. 임계값은 성능 데이터 없이 현재 pool에서 동결했다.

| Hard condition | 고정값 |
|---|---:|
| E_coord | ≤ 0.20 |
| E_pair | ≤ 0.20 |
| Local-neighborhood retention | ≥ 0.50 |
| 모든 site pair의 electrical distance | ≥ 0.9129072401559803 ohm |
| 모든 site pair의 geographic distance | ≥ 2221.532547954318 original-coordinate units |
| 서로 다른 적격 bus / distinct coordinate | 정확히 12개 |

이 조건들은 상대 구조 보존과 최소 dispersion을 확보하기 위한 사전 기준이다. **아직 joint feasibility를 검증하거나 12개를 고르지 않았다.** 조건을 만족하는 12-site set이 없으면 `TOPOLOGY_ONLY_12_SITE_SELECTION_INFEASIBLE`로 중단하며, 123-bus 변형·임의 bus·threshold 완화·May 결과 기반 재튜닝을 하지 않는다.

Feasible mapping 사이에서는 다음 목적을 **lexicographic**하게 순서대로 최적화한다. 앞선 최적값을 고정한 뒤 다음 목적을 계산하며 임의 가중합을 쓰지 않는다.

1. 대표되는 major lateral 개수 최대화. 구조상 상한은 3이다.
2. 세 major lateral과 trunk/minor의 네 그룹에 대한 site 개수 제곱합 최소화. 이는 동일 그룹 집중을 줄이는 diversity 동률 처리이다.
3. 66쌍 중 maximum R 최소화, 이어서 mean R 최소화.
4. minimum D 최대화, 이어서 mean D 최대화.
5. minimum normalized geographic distance 최대화, 이어서 선택된 12점의 convex-hull area / 전체 후보 convex-hull area 최대화.
6. E_coord, E_pair 순으로 최소화하고 local-neighborhood retention 최대화.
7. 최종 동률은 `(bus(AIDC01), …, bus(AIDC12))`의 lowercase bus ID 사전순이다.

Objective 비교는 각 값을 무차원화한 뒤 1e-9 tolerance로 고정한다. D는 전체 후보 pair의 maximum D로 나눈다. 목적 1–2는 정수 exact 비교이다. 해법 구현은 seed=0, single-thread, 고정 bus/site 순서를 사용하고 solver/version/optimality gap/각 단계 최적값을 기록해야 한다. 전역 최적성이 확인되지 않은 경우에는 `PROVISIONAL_NOT_GLOBALLY_CERTIFIED`로 표시하며 최적 후보라는 표현과 후속 simulation 승인에 사용하지 않는다. 시간 제한을 이유로 임의의 12개를 확정하지 않는다.

## 동결과 후속 산출물

이 문서, 원본 source manifest, Melbourne anchor/66-pair 자료, 638개 후보 pool, corridor와 pair metric을 `FREEZE_MANIFEST.json`의 SHA256으로 고정한다. 허용 입력 밖의 파일을 selector가 읽으면 실패 처리한다. 후속 selection 출력은 12개 bus와 AIDC mapping, 전 후보 제외 사유, major lateral 점유, 66개 pair metric, shape residual, threshold 통과표, 단계별 최적화 증거 및 입력 hash를 포함해야 한다.

이번 단계는 **source audit + methodology freeze**에서 끝난다. AIDC load 추가, load scaling, PCC 생성, B0/B1/B2/B3 실행은 포함하지 않는다.
