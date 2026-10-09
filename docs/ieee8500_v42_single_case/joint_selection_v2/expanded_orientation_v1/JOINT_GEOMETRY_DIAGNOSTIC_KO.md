# IEEE8500 공동 AIDC–STA 방향 적격성 진단

**공동 전기적 위치를 재선정하면 276쌍의 방향 보존이 가능한 기하 witness를 얻는다.** AIDC 12곳과 STA 12곳의 서비스 ID 및 교통 ID는 유지했고, 전기적 후보 버스는 현재 사용자 지시에 따라 공동으로 변경했다. 과거 고정 v3 앵커의 불가능성 진단은 옛 fixed-anchor 계약에 대한 결과이며, 현재 공동 재선정 문제의 불가능성을 뜻하지 않는다.

하나의 공통 135° proper 회전과 양의 균일 배율 0.001164294829를 전체 24개에 적용했다. determinant=1.35558244885e-06>0이며, reflection 또는 개별 회전·이동을 사용하지 않았다. 사전 동결한 1 m 근접/축 공차를 바꾸지 않고 66 AIDC–AIDC, 144 AIDC–STA, 66 STA–STA 쌍, 총 552개 축 관계를 직접 검증했다. 모두 PASS이고 24개 전기적 버스는 서로 다르다.

이 결과는 **기하 조건의 첫 feasible witness**이다. 전체 제어 가능성 또는 최종 controllability 점수로 고른 운영 시나리오가 아니다. 후보들은 원본 v3 host 제외 규칙, 원본 q05 root-distance guard, 실제 12.47 kV·연속 ABC 경로를 만족하는 606개 원본 MV 호스트에서 선택했다. STA는 현재 witness에서 모두 MV fallback 후보이며 LV 포트를 승인하거나 활성화하지 않았다.

공통 frame과 교통 anchor의 위치 오차는 평균 **9.410440**, RMS **9.914074**, 최대 **14.020840** km 상당값이다. 방향을 정확히 보존하는 것과 거리·형상이 작게 왜곡되는 것은 별도 조건이다. 이 witness는 방향 적격성을 증명하지만 거리 최적성이나 높은 형상 품질을 주장하지 않는다. 숫자는 원본 layout를 공통 배율로 옮긴 equivalent km이며, 원본 DSS의 CRS·단위·true east/north가 인증되지 않았으므로 실제 지리 거리나 SCATS 주행 거리로 해석하지 않는다.

원래 v3의 0.912907 Ω / 2221.533 unknown-unit pair spacing은 통계적 분산 설계 기준이므로 새 계약에서는 별도 audit/tie-break 지표로 보존한다. 이 첫 witness의 분기는 거리·버스 사전순만 사용했으며, 기존 spacing 지표로 고르지 않았다. 원본 정적 전기 tree에서 276쌍의 전기 거리·공유 경로·원본 좌표 거리와 옛 threshold PASS/FAIL을 `OLD_PAIR_DISPERSION_AUDIT.csv`에 재계산했다. 원본 접속 정격 또는 물리적 안전 이격으로 잘못 취급하지 않는다. 전압·선로·변압기·GPU/랙·Workload/QoS·MESS SOC 및 위치별 P/Q·접속 장치/보호/접근 제약은 이 기하 탐색으로 통과한 것이 아니다.

**최종 Production freeze는 수행하지 않았다.** 원본 MV bus의 전기적 host eligibility와 실제 포트 승인·설비·보호·접근·시간 근거는 다르다. 현재 모든 후보의 물리적 포트 정격은 미입증이며, 이를 vehicle 450 kW / 600 kVA 정격으로 대체하지 않는다. 최신 사용자는 모든 적격성을 만족한 단일 시나리오의 동결을 이미 허용했으므로 별도의 이전 승인 조건을 현재 gate로 추가하지 않았다. 현재 동결을 막는 원인은 아직 해결되지 않은 물리적 적격성이다.

탐색은 Native/Gurobi/전력망 최적화가 아닌 정적 bitset CSP였다. 606개 전체를 포함하고 모든 pair의 부호를 공통 frame의 strict rank 순서로 검사했다. 각도 순서·정적 분기 기준·5초/5000 node 한도를 시행 전에 기록했다. 시간 한도에 도달한 앞선 각도들은 UNKNOWN이며 전체 변환군의 infeasible로 바꾸지 않았다. B0/B3·민감도/성능을 이용해 각도나 버스를 고르지 않았다. 큐 중복 제거는 동일 제약의 계산 개선이며 변경 전 search 결과도 별도 파일로 보존했다.

`verify_witness(Path(root))`는 solver를 호출하지 않고 원본 DSS 좌표와 원본 교통 anchor에서 24개 identity, source guard, 한 공통 변환 및 276쌍 방향을 재검산한다. 재현 명령은 `.runtime/Scripts/python.exe -m ieee8500_v42.joint_geometry --verify --root .`이다. 그 결과와 RMS/최대 오차, 입력·witness SHA는 `WITNESS_VERIFICATION.json`에 있다. 부모의 독립 source audit는 별도 구현으로 다시 검사한다.

현재 witness SHA256: `3c0b9cca836267690dd622321e190278169a924c60e0784431d17370093fd4e1`.

옛 분산 기준의 실패 수는 AIDC–AIDC / AIDC–STA / STA–STA 각각 다음과 같다: AIDC-AIDC: 전기 2/66, 좌표 3/66; AIDC-STA: 전기 12/144, 좌표 13/144; STA-STA: 전기 6/66, 좌표 8/66. 이는 현재 하드 방향 조건의 실패나 미입증 실제 포트의 허용을 뜻하지 않는다.

| 서비스 | 교통 ID | 전기적 후보 bus | 모드 |
|---|---|---|---|
| AIDC01 | TN_01 | l3160865 | MV_3PH_AIDC |
| AIDC02 | TN_02 | l2729414 | MV_3PH_AIDC |
| AIDC03 | TN_03 | m1009805 | MV_3PH_AIDC |
| AIDC04 | TN_04 | m1047486 | MV_3PH_AIDC |
| AIDC05 | TN_05 | m1142810 | MV_3PH_AIDC |
| AIDC06 | TN_06 | m1108380 | MV_3PH_AIDC |
| AIDC07 | TN_07 | m1108295 | MV_3PH_AIDC |
| AIDC08 | TN_08 | m1047534 | MV_3PH_AIDC |
| AIDC09 | TN_09 | 226-23751 | MV_3PH_AIDC |
| AIDC10 | TN_10 | l3160098 | MV_3PH_AIDC |
| AIDC11 | TN_11 | l3197646 | MV_3PH_AIDC |
| AIDC12 | TN_12 | l2973791 | MV_3PH_AIDC |
| STA01 | TN_43 | l3081380 | MV_FALLBACK_STA |
| STA02 | TN_14 | q1301 | MV_FALLBACK_STA |
| STA03 | TN_35 | m1089207 | MV_FALLBACK_STA |
| STA04 | TN_28 | m1142819 | MV_FALLBACK_STA |
| STA05 | TN_37 | m1125902 | MV_FALLBACK_STA |
| STA06 | TN_41 | m1108298 | MV_FALLBACK_STA |
| STA07 | TN_32 | l2804249 | MV_FALLBACK_STA |
| STA08 | TN_47 | m1069438 | MV_FALLBACK_STA |
| STA09 | TN_42 | m1047513 | MV_FALLBACK_STA |
| STA10 | TN_24 | m3763619 | MV_FALLBACK_STA |
| STA11 | TN_44 | l2879070 | MV_FALLBACK_STA |
| STA12 | TN_17 | e182733 | MV_FALLBACK_STA |
