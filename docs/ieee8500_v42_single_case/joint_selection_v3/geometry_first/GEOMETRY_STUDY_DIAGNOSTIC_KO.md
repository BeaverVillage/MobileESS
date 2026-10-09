# 현재 V3: LV 포트 재설계 연구의 공동 기하 witness

**12개 STA를 모두 원본 고객측 LV bus에 두고 12개 AIDC MV host를 공동 재선정한 기하 witness를 얻었다.** 원래24 service 및 교통 ID,6 MESS unit을 유지했다. 추가 CT·STA·차량을 만들지 않았다. 이 파일은 공통 기하 조건의 첫 feasible witness이며, 아직 AC controllability 점수로 고른 최종 연구 시나리오가 아니다.

전체24 지점에 회전 **-168.244235052°**, 양의 공통 배율 **0.001164294829**, 하나의 평행이동을 적용했다. determinant=1.35558244885e-06>0이다. Reflection,개별 지점 회전·좌표 이동, 공차 변경을 사용하지 않았다. 사전 동결한1m 공차에서66 AIDC–AIDC,144 AIDC–STA,66 STA–STA 쌍의552개 strict 축 관계가 모두 PASS이며,24 PCC bus가 서로 다르다.

LV 후보의 좌표는 **상위 primary bus의 원본 좌표를 사용한 proxy**이다. Source의 X/SX 오프셋은 고객측 위치의 survey가 아니다. 원본DSS CRS·좌표 단위·true east/north도 인증되지 않았다. 따라서 판정은 `ASSUMED_PROXY_DIRECTION_PASS`이며, 실측 지리 방향을 보장하지 않는다. 중복 primary 좌표는 동일 좌표로 처리했고 strict pair 순서를 인위적으로 벌리지 않았다.

위치 residual은 평균 **4.423467**, RMS **5.001561**, 최대 **9.543431** layout-equivalent km이다. 실제 도로 거리·지리 오차나 거리 최적성을 뜻하지 않는다.

후보는606개 독립 source audit MV host와1177개 원본 customer-side LV bus 전체이다. AIDC에는 원본 host 제외·12.47kV·연속ABC·q05 root guard를 유지했다. Split-phase LV STA에는 원본 서비스 transformer와triplex 경로 및 customer-side terminal을 확인한다. LV를3상 ABC terminal로 잘못 취급하지 않는다.

현재 사용자는 현장 실측 근거가 없는 조건에서 **시뮬레이션 기반 재설계 포트 연구를 허용했다**. 따라서 field qualification의 부재를 연구 중단 gate로 다시 적용하지 않는다. 연구용 PCS/보호/절연/DC–DC/BMS·정격·derating·접근/접속 시간의 가정을 별도로 공개하고, 원본 CT·triplex·전압·전류·reverse power와 실제 선택 포트의 P/Q AC 제약을 검사해야 한다. 차량450kW/600kVA를 각 LV 포트의 허용 정격으로 옮기지 않는다. 연구 승인과 Production/현장 인증은 다르다.

탐색 전에 `GEOMETRY_PREREGISTRATION.json`으로 단계·전체 domain·각도·분기·12초/20000 node 한도를 동결했다.135°를 먼저 시도한 이유는 이전의 기하 witness이며 AC 성능이 아니다.135°의 all-LV STA 시도는 시간 한도로UNKNOWN이고, 다음 원래v3 fit 각도에서22 search node로 all-LV witness를 얻었다. 한도 결과를 전체 transform family infeasible로 바꾸지 않는다. 점수 입력을 읽지 않았고 B0/B1/B2/B3/AC sensitivity로 이 witness를 선택하지 않았다.

다음 단계는 별도 사전 동결한 ex-ante controllability 점수·위치별 실제 모델 P/Q 상한으로 공동 재선정하고, 최종 선택 포트에서 실제 AC를 검사하는 것이다. 현재 geometry_first witness의 score-selection 및 연구 case freeze 상태는 PENDING이다. Native/full model은 실행하지 않았다.

재현: `.runtime/Scripts/python.exe -m ieee8500_v42.joint_geometry_v3 --verify --root .`. 이 명령은 solver를 호출하지 않고 원본 coordinate/proxy/traffic에서552축을 직접 재검산하며 `DIRECT_552_AXIS_VERIFICATION.csv`와 `GEOMETRY_VERIFICATION.json`을 출력한다.

Witness SHA256: `25b18a0f309a7ea257cc700e7ef869f5698fb69edc52fea5af8df228edc5681b`.

| 서비스 | 교통 ID | 후보 bus | 모델 |
|---|---|---|---|
| AIDC01 | TN_01 | m1125934 | MV_MODELED_PORT |
| AIDC02 | TN_02 | m1009805 | MV_MODELED_PORT |
| AIDC03 | TN_03 | m1027002 | MV_MODELED_PORT |
| AIDC04 | TN_04 | m1047480 | MV_MODELED_PORT |
| AIDC05 | TN_05 | l3011298 | MV_MODELED_PORT |
| AIDC06 | TN_06 | l3123452 | MV_MODELED_PORT |
| AIDC07 | TN_07 | l3048221 | MV_MODELED_PORT |
| AIDC08 | TN_08 | l2952003 | MV_MODELED_PORT |
| AIDC09 | TN_09 | l2766749 | MV_MODELED_PORT |
| AIDC10 | TN_10 | m1125962 | MV_MODELED_PORT |
| AIDC11 | TN_11 | m1026872 | MV_MODELED_PORT |
| AIDC12 | TN_12 | m1149235 | MV_MODELED_PORT |
| STA01 | TN_43 | sx2955055b | LV_MODELED_PORT_PRIMARY_PROXY |
| STA02 | TN_14 | sx2767409b | LV_MODELED_PORT_PRIMARY_PROXY |
| STA03 | TN_35 | sx2936211c | LV_MODELED_PORT_PRIMARY_PROXY |
| STA04 | TN_28 | sx2692664c | LV_MODELED_PORT_PRIMARY_PROXY |
| STA05 | TN_37 | sx2897766c | LV_MODELED_PORT_PRIMARY_PROXY |
| STA06 | TN_41 | sx2973156b | LV_MODELED_PORT_PRIMARY_PROXY |
| STA07 | TN_32 | sx3047058a | LV_MODELED_PORT_PRIMARY_PROXY |
| STA08 | TN_47 | sx3122821b | LV_MODELED_PORT_PRIMARY_PROXY |
| STA09 | TN_42 | sx3103822c | LV_MODELED_PORT_PRIMARY_PROXY |
| STA10 | TN_24 | sx2745806c | LV_MODELED_PORT_PRIMARY_PROXY |
| STA11 | TN_44 | sx3141401a | LV_MODELED_PORT_PRIMARY_PROXY |
| STA12 | TN_17 | sx2729434b | LV_MODELED_PORT_PRIMARY_PROXY |
