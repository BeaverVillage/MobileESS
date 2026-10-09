# 원 IEEE8500 traffic ID와 현재 V42 이동 입력 독립 감사

원 IEEE8500에 사용한 **24개 traffic service/TN ID가 현재 May01 V42 경로표에서 그대로 보존됨을 확인했다.** 55,296개 경로 row를 읽기 전용으로 전수 검사했으며, forecast ETA·원 물리 거리·원 traction energy를 독립 재계산한 최대 차이는 각각 0.0초, 0.0 km, 0.0 kWh이다. 다만 현재 Native 입력은 4대/IEEE123이고, **새 6대 IEEE8500 시나리오의 Actual 이동 검증은 연결되지 않았다.** 이 감사 PASS를 6대 생산 실행 승인으로 사용하지 않는다.

감사기 `ieee8500_v42/traffic_mobility_audit.py`와 `TRAFFIC_MOBILITY_AUDIT.json`은 입력·원 소스 경로 및 SHA를 기록한다. 최초 원본 감사는 경로표를 제자리에서 읽었다. 이후 재현을 위해 승인된 5.8 MB gzip 경로표 등 계획 입력의 고정 사본을 새 namespace에 저장했다. 과거 launcher/Native/OpenDSS를 import하거나 실행하지 않았다. 모델 build, Native solve, AC solve, 경로 생성, forecast 생성, Actual replay는 모두 0회이다.

## 1. 비교한 입력과 ID 대응

현재 입력은 `D:\MobileESS_V42\runtime\v42_may_campaign\candidate_20261009_implementation01\inputs\B1\2025-05-01`의 `NATIVE_INPUT.json`, `OPERATIONS.json`, `WINDOWS.json`, `ROUTE_TABLE.json.gz`, `TRAFFIC_FORECAST.npz`이다. 원 route/forecast는 `C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\cache\v37_may_locked_final\traffic\shared\traffic\2025-05-01`과 바이트 SHA가 같다.

원 IEEE8500 `static_reference/final_service_nodes_24.csv`는 현재 road graph가 읽는 원 WSL service CSV와 SHA가 같다. 원 24곳 전기 registry의 `traffic_anchor`도 같다. Route service명 `IDC01–12`와 전기 location명 `AIDC01–12`는 단순 표기 차이가 있으므로 명시적인 일대일 alias가 필요하다.

| Route service | 전기 location | 보존된 traffic node |
|---|---|---|
| IDC01–IDC12 | AIDC01–AIDC12 | TN_01–TN_12, 같은 번호 |
| STA01 | STA01 | TN_43 |
| STA02 | STA02 | TN_14 |
| STA03 | STA03 | TN_35 |
| STA04 | STA04 | TN_28 |
| STA05 | STA05 | TN_37 |
| STA06 | STA06 | TN_41 |
| STA07 | STA07 | TN_32 |
| STA08 | STA08 | TN_47 |
| STA09 | STA09 | TN_42 |
| STA10 | STA10 | TN_24 |
| STA11 | STA11 | TN_44 |
| STA12 | STA12 | TN_17 |

각 row의 `road_origin_node`·`road_destination_node`를 이 대응표와 대조했다. 96 departure slots × 24 origins × 24 destinations의 모든 key가 있고 중복·누락은 없다. 2,304개는 같은 지점 stay row, 52,992개는 이동 row이다. 원 Native 시간 계약을 적용하면 51,322개 이동 arc를 유지하고 1,670개는 일과 종료의 connect bound 밖이라 제외한다. 이 감사는 제외를 완화하거나 새 경로를 만들지 않았다.

새 공동 AIDC/STA 재선정에서 전기 host가 바뀌더라도 원 traffic service/TN ID를 유지할 수 있다. 그러나 새 전기 host·traffic anchor·route alias를 하나의 최종 scenario SHA에 묶는 매핑과 새 위치에 대한 접근/연결 가정은 별도로 필요하다. 원 traffic ID 보존을 실제 새 부지의 도로 접근·지리적 일치 증거로 해석하지 않는다.

## 2. ETA, 거리, source graph, 에너지 단위

Forecast는 `[288,509]` float32 Q10/Q50/Q90 세 배열이고 단위는 초이다. 원 issue는 `2025-04-30T18:00:00+10:00`, 최대 input timestamp는 `17:55:00+10:00`이며 원 forecast causality flag는 PASS, 미래 Actual 사용 수는 0이다. target은 2025-05-01의 5분 288개이다.

15분 departure `t`는 원 forecast step `3t`를 사용한다. 모든 row의 경로 link별 해당 departure snapshot 값 합을 ETA와 대조하여 정확히 같음을 확인했다. 이동 중 매 link 진입시각으로 forecast를 보간하는 새로운 방법을 도입하지 않았다. 파일 NPZ SHA와 `metadata.bundle_sha`는 다른 정의이다. 전자는 container 바이트, 후자는 원 canonical metadata와 little-endian float32 세 배열의 logical SHA이며 각 정의로 따로 검증했다.

원 graph의 link-order CSV, service CSV, 물리 edge catalog gzip, elevated network XML의 바이트 수와 SHA로 graph manifest를 재구성하여 forecast `graph_sha`와 같은 값을 얻었다. 509 link tensor 축을 확인하고 모든 경로가 원 origin에서 destination까지 연속된 방향성 link 경로임을 검사했다. 물리 catalog의 ordered `length_m`를 km로 환산해 모든 route 거리를 다시 계산했으며 최대 차이는 0.0 km이다. IEEE8500의 단위 미인증 도식 XY 거리로 road distance를 대신하지 않았다. 원 elevated network hash를 확인했으나 이 감사에서 elevation profile 생성 알고리즘을 재실행하지 않았다.

원 `MESS_MOBILITY_PHYSICS_V1.json`은 28,000 kg, rolling·aerodynamic·grade·auxiliary의 결정론적 물리식이며 traffic ML은 ETA에만 사용한다. 저장된 각 row의 거리·상승/하강고도·Q10/Q50/Q90 ETA에서 식을 독립 계산했다. Nominal은 Q50 물리 에너지, safe energy는 세 ETA의 물리 에너지 최대값이며 모든 이동 row가 정확히 같다. 단위는 kWh이고 Native SOC에서 출발 시 공제한다. 이 일치가 새 1,800 kWh 차량의 질량·장비 적용성을 입증하지는 않는다. 그 차량 조건이 원 28,000 kg 계약을 그대로 사용하는지 별도 scenario에서 명시해야 한다.

## 3. Safe ETA와 연결시간

원 Safe ETA는 별도 blocked-OOF calibration의 `Q50 + departure lead-band margin`이다. 52,992개 이동 row 전부에서 route Q90와 다르므로 Safe ETA를 Q90 또는 그 최대값으로 바꾸면 원 알고리즘을 변경한다. 4개 band의 저장된 margin 범위는 receipt에 보존했다. 원 calibration Python source는 읽고 SHA를 기록했으나 legacy code 폴더에 calibration 결과 JSON은 없어 fit artifact·학습을 다시 인증하지 않았다. 동결된 route 표를 현재 권한으로 유지했다.

원 식은 `travel=ceil(SafeETA/900)`, `connection_ready=ceil((SafeETA+600)/900)`이다. 600초를 ceil 전에 더하며, 정수 travel slot에 무조건 1을 더하는 방식이 아니다. 원 Native arc는 `origin@depart → destination@connect`, arrival은 `depart+travel`, 전력 미가용 구간은 출발부터 connection ready 전까지이다. `RouteArc`는 `depart<arrive≤connect<96`을 요구한다.

600초는 원 공통 연결 가정이다. 새 MV/LV 지점의 실제 연결 작업시간·차량 접근·운영 가능 시점을 확인한 source는 이 입력에서 제공되지 않았다. `WINDOWS.json`의 1,605개 row는 AIDC job start windows이며 service access/vehicle connection windows가 아니다. `OPERATIONS.json`도 current day folder와 workload/AEMO forecast를 제공하므로 이를 port 연결시각 근거로 사용하지 않는다.

## 4. 현재 4대 입력과 6대 호환성

`NATIVE_INPUT.json`의 network는 IEEE123, schema는 `V42_MAY01_IEEE123_NATIVE_INPUT_BUNDLE`이다. 초기 위치는 MESS01=STA01, MESS02=STA12, MESS03=STA08, MESS04=STA06이다. Battery 필드는 minimum=440, maximum=1080, initial=terminal=760 kWh, p_limit=300 kW, pcs_kva=400 kVA, charge/discharge efficiency=0.95, dt=0.25 h이다. 이 bundle에는 nominal capacity kWh 필드가 없다. maximum SOC 값을 nominal capacity로 바꾸어 해석하지 않는다.

원 `v42_native.mess`의 unit flow/PQ/SOC 수식은 initial-site map을 순회하므로 6대 adapter의 기반이 될 수 있다. 하지만 현재 `v42_bootstrap.m1.native_inputs():40`은 차량 4대·site 24개를 강제하며 Actual/Fresh DTO와 원 `_actual_mess` batch에도 4대 축이 남아 있다. 따라서 초기 위치 두 개만 추가하거나 이름을 변경하는 것으로 연결 인증이 완료되지 않는다. 6대 조건, 450 kW/600 kVA/1,800 kWh 및 해당 초기·종단 SOC·route/port 조건을 하나의 동결 시나리오로 받아 원 제약·검증기를 같은 6대 축에 연결해야 한다.

## 5. Actual 이동 gate의 존재와 현재 미연결

원 외부 `dayahead/v33m3/actual_replay.py::replay_committed_move`는 동결된 committed link 경로를 유지하고, link 진입시각의 실제 5분 SUMO TT를 순차 합산한다. 실제 ETA로 같은 물리 energy를 계산하고 600초 연결시간을 더한다. 재최적화·reroute를 허용하는 기능이 아니다. 원 `dayahead/v35/execution.py::_actual_mess`는 이를 호출하여 계획·실제 에너지 차이와 실제 connection availability를 만들지만 `[96,4]`와 4대 초기/용량 축을 사용한다.

해당 May01 Actual parquet는 원 WSL 경로에 존재한다. 파일은 10,751,770 bytes이고 SHA는 receipt에 기록했다. **Actual 숫자 값은 로드하지 않았고 실제 route replay는 실행하지 않았다.** 파일 존재와 API 존재는 6대 Actual 검증 PASS가 아니다.

현재 `v42_may_campaign_native90/operations.py::actual():178–203`은 Planning MESS 배열을 `ACTUAL_MESS_TRAJECTORY.npz`에 복사하고 비트 단위 불변을 요구한다. 이 경로에는 원 SUMO committed-route replay, 실제 late connection availability 또는 실제 traction energy gate가 없다. 현재 B1은 MESS off의 AIDC 전용 arm이므로 이 동작으로 움직이는 6대 MESS의 Actual 실행성을 인증할 수 없다. 같은 adapter의 B2 적용 역시 해당 gate가 연결됐다는 증거가 아니다.

필수 미완료 항목은 MESS05/06 초기 위치와 6대 DTO 축, 명시적 1,800 kWh 및 6대 SOC/450 kW/600 kVA 조건, 원 차량 물리식 적용성, 새 host와 원 route ID/TN의 scenario-bound bijection, 위치별 접근/연결 가정, 동결된 6대 실제 단일 경로 plan, 계획 freeze 이후 같은 graph·route·physics에 연결된 SUMO replay, `[96,6]` 실제 availability와 `[97,6]` SOC 검증 및 지연에 따른 미접속 P/Q 충돌 gate이다. 실제 지연을 경로 변경이나 PQ repair로 숨기면 원 고정 결정 조건을 바꾸므로 해당 검증은 독립적으로 fail할 수 있어야 한다.

장비·PCC 실재 증거는 별도 equipment 감사의 범위이며 여기서 반복 판정하지 않았다. 이 문서의 결론은 **원 traffic/계획 route 입력은 일관되고, 새 6대 Actual 이동 gate는 아직 미연결**이라는 것이다.

## 6. 외부 경로 없이 재현하는 고정 사본

새 `data/traffic_audit/`는 현재 계획 route/forecast/operations, 원 24 service CSV·509 link order·physical edge catalog, 원 mobility physics contract 및 lossless gzip elevated XML을 보관한다. 원 XML은 134,326,711 bytes이고 gzip 보관본은 19,478,304 bytes이다. 원 XML을 Git에 직접 추가하지 않았다. 새 입력 보관량은 28,952,234 bytes이며, 단일 파일은 모두 50 MiB 미만이다. 원 파일 사본은 byte SHA를 검증하고 XML은 압축 container SHA와 **압축을 푼 원 bytes/SHA**를 함께 검증한다. Graph logical manifest는 원 XML의 decoded bytes/SHA를 사용하여 원 graph SHA를 그대로 유지한다.

NATIVE_INPUT/WINDOWS는 `data/workload_flexibility/`의 검증된 기존 사본을 재사용해 중복하지 않는다. `SOURCE_MANIFEST.json`은 모든 사본과 원 path/SHA, 공유 사본을 기록하고 `ORIGINAL_SOURCE_SHA_PROOF.json`은 최초 원본 감사의 source identity metadata를 보존한다. Actual May01 parquet·Actual 숫자 값·운영 outcome을 복사하지 않았다. Actual 파일 존재/SHA는 이 archived metadata에만 남으며 offline 재생에서 Actual 경로를 열지 않는다.

감사기는 고정 사본을 우선 사용하고 매번 manifest와 압축 복원 SHA를 검증한다. 원 Native bundle의 외부 route path 문자열을 바꾸지 않고 route SHA에 대응하는 고정 사본을 읽는다. 따라서 경로 위치를 바꾸어 원 권한 hash나 알고리즘을 바꾸지 않는다. 외부 원 경로를 사용할 때의 fallback도 유지한다. Offline 재현에서는 원 외부 Python source의 코드 SHA를 archived provenance로 표시하며 그 코드를 재실행하지 않는다.

검증 3개는 외부 파일을 여는 호출을 차단한 상태에서 전체 55,296개 route 재생 PASS, 사본 hash 변조 시 숫자 재생 전 중단, gzip의 원 decoded bytes/SHA 일치를 확인한다. 압축 확인용 작은 fixture를 실제 이동·물리 자격 증거로 사용하지 않는다.

재현 명령: `python -B -m ieee8500_v42.traffic_mobility_audit`. 출력은 `TRAFFIC_MOBILITY_AUDIT.json`이다. 검증은 `python -B -m unittest discover -s tests -p test_ieee8500_v42_traffic_mobility_audit.py -v`이다.
