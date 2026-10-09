# 고정 AIDC 방향 충돌의 원인 진단

**판정: 최종 시나리오 및 STA 재선정 HOLD. AIDC 12개 버스는 변경하지 않았다.** 스케일·부하율·B3 성능을 고려하기 전에 고정 앵커의 방향 계약을 독립적으로 검사했다. `FINAL_STA_MAPPING.csv`는 12개 기존 STA 정체성과 교통 ID를 보존하며 최종 LV 선택 칸은 비어 있다. 이 진단으로 최종 구성을 동결하거나 승인하지 않는다.

현재 v3 전력망 앵커와 교통 앵커는 사전 규정한 **공통 proper similarity(양의 균일 배율, 한 번의 회전·이동, 반사 없음)** 에서 66개 AIDC 쌍의 모든 좌우·상하 부호를 동시에 보존할 수 없다. 공통 최소제곱 fit은 방향 계약을 만족한 승인 변환이 아니라 시각적 진단이다. 이 fit에서 17/66 쌍, 17/132 축 관계가 충돌한다. 원본 DSS 축을 그대로 비교한 충돌은 115/132이다. 임의의 비선형 좌표 워프 또는 실제 지리 위치 자체의 불가능성까지 증명한 것은 아니다.

## 원본 좌표는 무엇을 보증하는가

[원본 IEEE8500 Buscoords](<C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/IEEE8500_scalability_20260910/source/Buscoords.dss:1>) 헤더는 Busname, x, y만 제공한다. 확인한 원본 파일에는 CRS, EPSG, 좌표 단위 및 X/Y가 실제 동/북이라는 근거가 없다. 따라서 원본 좌표는 **원본 전기계통 배치/layout의 권위**이며 실제 지리 좌표 권위라고 주장하지 않는다. 선로 길이의 km/ft 단위를 Buscoords 단위로 가져오지 않았다. source X/Y 방향도 임의로 반사하거나 각각 뒤집지 않았다.

[X/SX 좌표 생성 주석](<C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/IEEE8500_scalability_20260910/source/Buscoords.dss:2483>)는 저압 secondary/load 좌표를 스크립트로 추가했다고 명시한다. 1,171개 고객 좌표는 상위 primary에서 (+45,+40) 이동했고, 별도의 6개 수동 schematic 행은 (+0,+9) 이동했다. 이는 고객 위치 측량 자료가 아니다. LV 후보는 실제 transformer–triplex 연결관계를 따라 1,177개 고객 측 단말을 열거했고, 탐색 좌표는 상위 서비스 변압기 primary 좌표를 proxy로 사용했다.

## 교통 좌표의 동·북 방향 검증

[원본 교통 CSV 조인과 좌표 투영](<C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/IEEE8500_scalability_20260910/station_selection_v1/prepare_sta.py:7>)는 `final_service_nodes_24.csv`의 traffic_node를 `v01_reduced48_nodes_v2.csv`에 조인한다. 모든 서비스의 원본 longitude/latitude와 고정 앵커 값은 정확히 일치했다. 24개 전체의 평균 위도·경도를 기준으로 다음 식을 독립 재계산했다.

`x_east_km = 6371.0088 × cos(mean_lat) × (lon − mean_lon)`

`y_north_km = 6371.0088 × (lat − mean_lat)`

각도는 radian이다. 평균 위도는 -37.816359524116°, 평균 경도는 144.974520689175°이다. 평균 위도의 cos는 양수여서 x는 경도 증가 방향, y는 위도 증가 방향이다. 고정 투영과 재계산의 최대 절대오차는 2.24e-12 km이다. `TRAFFIC_PROJECTION_SOURCE_AUDIT.csv`에 원본 lat/lon, 교통 ID, 투영과 오차를 남겼다. 입력 CSV 자체의 별도 EPSG 인증까지 추가로 주장하지 않는다.

## 왜 과거 v3가 통과했는데 현재 방향 요구와 충돌하는가

[과거 v3 metrics 코드](<C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/IEEE8500_scalability_20260910/selection_v3_source_proximity/select_sites.py:44>)의 hard gate는 각 pair의 x/y 부호가 아니다. 전체 12개 점의 중심/RMS 정규화 후 proper Procrustes 회전으로 계산한 평균 형상 오차 `E_coord ≤ 0.20`, 66쌍 정규화 거리 RMS 오차 `E_pair ≤ 0.20`, 최근접 2개 이웃 보존율 `≥ 0.50`, 모든 pair의 최소 전기적·좌표 거리 및 host 중복 배제였다. 결과는 E_coord=0.1996973436, E_pair=0.1293899223, 이웃 보존 22/24로 해당 기준을 통과했다. 형상과 거리의 평균 오차가 허용되므로 개별 좌우·상하 관계가 뒤집히는 것은 이 옛 gate에 의해 배제되지 않는다.

[v3 root-distance guard](<C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/IEEE8500_scalability_20260910/selection_v3_source_proximity/select_sites.py:34>)는 원래 638개 pool의 root electrical distance q05=1.3819547377 ohm 미만 32개를 제외하는 정적 topology 제한을 추가했다. 이는 방향 부호의 별도 제약을 추가하지 않았고, AC·전압·부하율 결과로 선택한 것도 아니다. 따라서 과거 결과의 `hard_criteria_all_pass`는 옛 topology/shape 기준의 통과이며 새 all-pair 방향 계약의 통과가 아니다.

STA도 독립 형상 fit으로 선택했다. [과거 STA 교차쌍 진단의 명시적 한계](<C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/IEEE8500_scalability_20260910/station_selection_v1/STA_SELECTION_PROCEDURE.md:23>)는 AIDC–STA 144개 교차쌍을 진단 전용이라고 했고, 독립 STA fit이 모든 교차 상대방향을 보장하지 않는다고 명시했다. 이에 따라 과거 자료가 24개 전체의 정확한 방향 보존을 입증한다고 확대 해석하지 않았다. 이번 진단은 고정 AIDC 앵커만으로도 충돌을 발견하므로 STA 후보를 바꾸거나 LV로 이동시키는 것으로 원인을 해결할 수 없다.

## 평균 fit의 실패보다 강한 증거

`DIRECTION_ROOT_CAUSE_AUDIT.json`의 affine certificate는 허용 변환이 아니라 **외부 완화(outer relaxation)** 이다. 직교성·동일 배율·양의 determinant 조건을 제거하여 x축/y축 projection row를 각각 자유롭게 허용해도 부호 제약이 불가능함을 검사한다. `v = sign(traffic_delta) × (DSS_b − DSS_a)`에 대해 preserving row r는 모든 `r·v > 0`을 만족해야 한다. 양의 가중치들의 합을 1로 정규화했을 때 세 witness 벡터의 가중합이 0이므로 이를 모두 엄격 양수로 만드는 row는 없다. x와 y 모두 이 certificate를 얻었다. 따라서 훨씬 좁은 공통 proper similarity도 불가능하다. 전체 각도 경계 구간 검사도 같은 결과를 준다.

- x witness: AIDC02–AIDC03, AIDC07–AIDC11, AIDC11–AIDC12.
- y witness: AIDC09–AIDC12, AIDC10–AIDC12, AIDC11–AIDC12.

근접 처리 공차는 후보 평가 전에 1 m pair 거리 및 1 m 축 차이로 동결했고 완화하지 않았다. 이 witness들은 해당 공차로 제외되지 않으며 66개 고정 AIDC 쌍 중 거리 근접으로 면제되는 쌍은 없다. AIDC 버스, 원본 좌표 및 서비스 정체성을 재배치하거나 성능에 맞춰 튜닝하지 않았다.

`AIDC_66_DIRECTION_AUDIT.csv`는 모든 66쌍의 이름, 교통 ID, DSS bus, 원본 traffic/DSS 좌표, 공통 fit 좌표와 각 축 delta/expected/raw/fit 부호를 제공한다. `AIDC_DIRECTION_CONFLICTS.csv`는 raw 축 또는 진단 fit에 충돌이 있는 축별 행을 모두 제공하고 두 충돌 여부를 구분한다. 기존 276쌍 audit도 원본 축 부호와 진단 fit 부호를 기록한다.

최종 진행에는 이 고정 AIDC/좌표/정확 방향 계약의 충돌에 대한 명시적 결정과 검증 가능한 저압 포트·보호·접근 자료가 필요하다. 이 파일은 어떤 계약도 변경하지 않고 승인 여부를 대신 결정하지 않는다. 출처 파일 경로와 SHA256은 `DIRECTION_ROOT_CAUSE_AUDIT.json`에 고정했다.
