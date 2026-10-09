# 과거 MV STA 불가능성 증명의 적용 범위

기존 저압 STA 12곳의 Primary Proxy는 모두 단상이다. 같은 버스에 `.1.2.3`를 붙여 중압 출력이나 3상 결선을 추가하는 것은 실제 존재하는 접속 모델이 아니다. 기존 L0는 5 kW/3 kvar/6 kVA/27 A 연구 포트 목적에 따라 선정한 것으로, 이번 고출력 요구 때문에 그 과거 선정 자체가 잘못됐다고 판단하지 않는다.

과거 전 각도 불가능성 증명은 **기존 AIDC 12개 물리 버스 고정 + 원본 source guard를 통과한 MV606 후보 + 공통 proper rotation + 276쌍 방향**의 동시 조건에 한정한다. 132개 AIDC–AIDC 축 조건에서 공통 회전이 191.319215°–191.823332° 열린 구간으로 제한되며 이 전체 구간에서 STA01·STA02·STA05·STA06·STA07·STA10의 적격 MV 후보는 0이다. 원본 십진 좌표를 유리수로 처리한 후보 구간 전수 감사와 그 증명 SHA는 high_impact_scenario의 MV_RELOCATION_ORIENTATION_RESULT.json 및 관련 CSV에 그대로 보존됐다.

그 증명은 Job/QoS·변압기·PCS·보호 정격 문제의 불가능성도, AIDC까지 공동 재선정한 문제의 불가능성도 아니다. 후보가 모두 소진되는 조건은 고정 AIDC가 정하는 좁은 상대 형상 영역이다. 606개 중압 적격 버스가 존재하며 그 개수 자체가 12개보다 적어서 생긴 문제가 아니다.

이후 별도 AIDC+STA 공동 형상 진단에서는 AIDC 고정을 해제하고 606개 MV 후보 전체를 사용했다. 공통 135° proper similarity에서 24개 서로 다른 원본 MV 버스와 276쌍/552축 PASS witness를 확보했다. 따라서 새 공동 후보 공간에 과거 불가능성을 확대할 수 없다. 이 과거135° witness는 진단 자료이며 이번 최종 배치로 자동 채택하지 않는다.

이번 재선정은 MV606 및 원본 고객 LV1177 후보, 기존 traffic24 IDs와 MESS6대를 보존한다. 원본 ABC 연결 트리를 기반으로 AC 점수를 읽기 전에 8개 연결 권역을 분할했다. 원본 간선을 자르며 eligible606MV+1177LV 수의 균형을 기준으로 가장 큰 권역부터 반복 분할한다. LV 고객은 가장 가까운 상위 ABC 조상으로 권역을 분류하고 그 단상 Primary 경로·기존 서비스 변압기·Triplex는 보존한다.

새 C1/C2에는 권역별 AIDC≤4, STA≤4, 합계≤6 및 AIDC/STA 각각≥4권역, 합계≥6권역을 실제 공동 CSP 제약으로 적용한다. C1의 MV6/LV6 서비스 배정은 AC 점수 전에 짝수 STA=MV·홀수 STA=LV로 사전등록했고 C2는 MV12를 검토한다. 탐색 시간 또는 노드 예산 소진은 UNKNOWN이며 정격·방향 또는 분산 제약을 조용히 완화하지 않는다.

8개 권역은 투명한 topology 기반 연구 분할이다. 이것을 8개의 독립 feeder lateral 또는 8개 별도 지리 지역으로 인증하지 않는다. 원본 lateral 그룹, Primary proxy 전기적 거리, 공통 상류 경로 비율과 실제 AC 기여의 중복은 별도 감사한다. 계통 좌표의 GIS/CRS·현장 접근성·재배치 후 실제 도로 ETA는 여전히 UNVERIFIED다. 중압 ABC 호스트 적격성이 IEEE1547·보호·변압기·PCS 설치 적격성을 자동 인증하지 않는다.

## 새 공동 문제의 선정 시점 감사

기존 AIDC 고정이 해제된 새 문제에서 C1과 C2의 공동 배치 witness를 확보했다. 이는 과거 고정 AIDC 조건의 불가능성 증명이 새 전체 공동 문제에는 적용되지 않음을 직접 보여준다. 후보가 많다는 추측이나 최적화 실패 여부가 아니라, 원본 버스 24곳의 실제 좌표·상 연결·552개 축 결과가 저장된 구성적 증거다.

최종 점수는 사전등록한 Planning B0·BG0.85·GPU780에서 606개 MV 및 1,177개 LV 후보의 대칭 ±1 kW/±1 kvar AC 교란으로 계산했다. 원래 6개 시간대(0,9,48,68,72,75)에 기준 B0의 전역 피크 74를 투명하게 추가한 별도 사전등록을 적용했으며, 원래 여섯 시간 결과도 보존했다. 이는 Actual 또는 B1/B2/B3 결과를 사용한 재선정이 아니다. FINAL_CANDIDATE_SCORE_FREEZE.json의 점수와 두 원본 민감도 archive SHA를 확인한 뒤 탐색했다.

AIDC와 STA 24개가 동시에 들어가는 bitset CSP에 모든 방향 조건, 버스 고유성, MV/LV 역할, 권역별 cardinality와 coverage를 넣었다. C1은 점수 전에 짝수 STA=MV·홀수 STA=LV를 결정한 6/6 구성이고 C2는 STA12 모두 MV이다. 권역별 AIDC≤4·STA≤4·합계≤6, AIDC와 STA 각각 최소4권역·합계 최소6권역 제약은 실제 탐색과 독립 감사에 적용했다. 권역은 원본 ABC 트리647개 버스를 원본 간선으로 나누어 eligible-host 수가 균형을 이루도록 만든 8개 연결 영역이며, AC 효과 점수 전에 동결했다.

| 구분 | AIDC MV | STA MV/LV | 권역 전체/AIDC/STA | 원본 ABC 조상 lateral 그룹 | 방향/분산 |
|---|---:|---:|---|---:|---|
| C1 | 12 | 6/6 | 7/7/6 | 4 | 276쌍·552축 및 사전 제약 PASS |
| C2 | 12 | 12/0 | 7/7/7 | 4 | 276쌍·552축 및 사전 제약 PASS |

7개 연결 권역을 7개의 독립 feeder lateral로 해석하지 않는다. 두 배치가 차지하는 원본 static638 features의 ABC 조상 lateral 분류 라벨은 각각4개이며 ORIGINAL_PRIMARY_LATERAL_DISTRIBUTION.csv에 그 원본 그룹별 설치 수를 기록했다. 정확히는 MAJOR:l2820531·MAJOR:l3081380·MAJOR:m1047526의 세 named major 그룹과 TRUNK_OR_MINOR_LATERAL 집계 bucket이므로 이것을 물리적으로 독립된 lateral4개로 인증하지 않는다. C1의 이 네 라벨 설치 수는 각각3·5·6·10개, C2는2·9·5·8개다. LV의 그룹은 가장 가까운 상위 ABC 조상의 원본 분류이므로 개별 단상 서비스가 독립 feeder라는 뜻도 아니다. 전기적 거리와 공통 상류 경로 비율은 ELECTRICAL_PAIR_DISTANCE_SHARED_PATH.csv, 모든 요구 상의 원본 경로는 ORIGINAL_PRIMARY_CONNECTION_PATH_AUDIT.csv에서 확인한다.

공통 변환은 양의 uniform scale 0.0011642948290067979와 하나의 proper rotation135°·공통 centroid translation이다. 모든 24개 위치에 동일한 변환을 적용했고 반사·개별 회전·임의 좌표·방향 뒤집기는 없다. 교통 축 차이가 ±0.001 km 범위이면 기존 동결 공차에 따른 무방향 조건이며 그 밖에는 부호를 엄격하게 보존한다. 원본 IEEE8500 도식 좌표의 CRS·방향·거리 단위는 실제 GIS로 인증되지 않았다. 특히 LV 고객 좌표는 원본 서비스 Primary의 위치 proxy이며 surveyed 고객 좌표가 아니다. 방향 PASS는 이 공통 도식 frame의 결과로서 물리적 지리·접근성을 인증하지 않는다.

원래 공통 각도 −168.244235°의 45초 탐색은 두 경우 모두 UNKNOWN_BOUNDED_SEARCH였고 다음 사전등록 각도135°에서 feasible witness를 얻었다. 시간 제한으로 종료된 각도를 수학적 불가능으로 판정하지 않는다. 점수 우선순위·원래 위치 거리·bus lexical tie-break를 사용한 첫 complete witness이며 전역 최적·최대효과·local optimum을 주장하지 않는다. 제어 효과의 중복과 상호보완성은 JOINT_CONTROL_OVERLAP_AUDIT.csv로 감사했으나 별도 overlap 목적함수나 교환 최적화로 개선한 배치가 아니다.

AIDC 점수에는 원본 Job mask의 알려진 감축 가능량 relaxation과 PF0.95 결합 Q만 반영했다. 실제 QoS를 만족하는 비영 96슬롯 감축 dispatch가 인증된 것은 아니므로 certified AIDC flexible P=0이다. MESS의 450 kW/300 kvar MV 및 5 kW/3 kvar LV 민감도 벡터는 정격·원본 ETA로 제한한 screening 응답이며 여섯 차량의 동시 feasible schedule이나 nonlinear 전압·상전류 PASS를 뜻하지 않는다. 따라서 실제 AIDC–MESS 공동 보완성은 UNPROVEN이다. AIDC 전체 부하 영향과 유연 Job 효과, MESS 응답은 구분했다.

권역 분산만으로 전기적 효과의 독립성을 입증할 수 없다. 동결 critical-corridor·7시간 screening 응답에서 C2의 STA–STA66쌍 모두 P-response cosine≥0.95이고 중앙값0.998440·positive-support Jaccard1.0이다. C1은66쌍 중19쌍이0.95 이상이고 중앙값0.508915다. AIDC–AIDC는 두 배치 모두66쌍 중45쌍이0.95 이상이다. 이는 여러 PCC가 같은 주요 선로 집합에 유사하게 작용하는 제한을 보여준다. 동결 후 이 결과를 근거로 입지를 다시 선택하지 않았고, JOINT_CONTROL_OVERLAP_SUMMARY.csv에 중복을 그대로 남겼다. 이 수치는 정책 개선율·독립 제어 자원 개수·실제 공동 추가 이득을 뜻하지 않는다.

MV의 원본 ABC 호스트 적격성과 새로운 750 kVA·12.47/0.480 kV 전용 변압기·PCS·보호 인터페이스의 engineering 설계 적격성은 서로 다른 gate다. 기존 Triplex·서비스 변압기·원본 선로 정격을 바꾸지 않았고 새 Primary 도체를 추가하지 않았다. LV 포트는 5 kW/3 kvar/6 kVA/27 A를 유지한다. MV 차량은 P450 kW·S600 kVA·E1800 kWh와 실제 상전류 제한721.687836 A를 함께 적용해야 하며 nonlinear AC에서 허용 출력이 줄 수 있다. 양방향 보호·접지·short-circuit·GIS·현장 도로 접근·재배치 PCC 실제 ETA는 ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED/UNVERIFIED다.

P0_PCC_MAPPING_COMPARISON.csv는 C0 PR197 원본 매핑 대비 C1/C2 48개 행을 기록한다. 기존 24개 traffic ID, 원본 ETA, Job/Rack/GPU 권위와 MESS6대는 보존하고 PCC만 변경했다. 양 배치의 SHA는 B0 전체 AC 또는 B1/B2/B3 결과를 확인하기 전에 기록했으며 이후 제어 효과로 bus를 바꾸지 않는다. 현재 문서의 방향·상 경로·분산 PASS는 최종 96슬롯 전압·선로·변압기·탭·커패시터 적격성이나 field 설치 PASS를 대신하지 않는다. 단일 연구 시나리오 결정·최종 Production 승격은 별도 원본 제약 검사와 공정한 사전 결정 규칙에 달려 있다. 기존 캠페인과 원본 DSS·과거 불가능성 증명·geometry-only seed는 보존하고 B1/B2/B3 Solver를 호출하지 않았다.

선정 파일:

- C1_SCORED/JOINT_LOCATION_SELECTION.csv — SHA `4688dc77d7252348792464e7264f6ca6a45184fd5a312a633c2a7d913703629e`
- C2_SCORED/JOINT_LOCATION_SELECTION.csv — SHA `900dec7fd8f16da4356bb109f2b629fa781c34de3ec94932d00264622fa5dd5a`
