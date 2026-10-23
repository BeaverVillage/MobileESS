May01 Source-YY IEEE8500에 **최적화 전에 완성되는 정적 M1 모델**을 추가합니다. 기존 431,255행 지연 Master는 역사적 진단으로 보존하며, 새 실행 준비 경로에서는 사용하지 않습니다. 원본 r043 K48/Adaptive Beam/Direct Joint 알고리즘과 Budget/Gap은 변경하지 않았습니다.

현재 판정은 **PRESTART_BLOCKED_WITH_EVIDENCE**입니다. 아래 수학·Native0 결과는 **고정 B0 AIDC M1** 범위이며, 전체 캠페인 통합 PASS가 아닙니다.

| 실측 지표 | Source-YY 원본 FULL | Static Complete M1 Native0 |
|---|---:|---:|
| Binary | 417,296 | 18,680 |
| Continuous | 3,350,097 | 1,426,579 |
| Rows | 20,634,824 | 1,740,213 |
| Nonzero | 302,525,444 | 51,158,488 |

- Native0 생성 473.11초, 저장 포함 558.87초, Peak RSS 2.909GiB. 전체 실제 Native 계수/RHS/Sense/Bound/Type/목적함수 Readback 및 독립 원본 좌표 합성 PASS.
- 원본 node-flow Compact·정적 Presolve와 보수적 전 영역 안전 상계, 별도 목적함수 지배 증명을 적용했습니다. 제거 근거를 증명하지 못한 행은 유지합니다. 모든 원본 선로·Triplex·양단 정격·16-face와 8대 STAY/MOVE 자유를 보존합니다.
- Source-YY 실제 OpenDSS Planning96 계수를 72축(AIDC P/Q24 + MESS P/Q48)으로 새로 생성했습니다. DY/IEEE123 계수를 재사용하지 않았습니다.
- 원본 전체 행의 독립 검증, 정확한 복원식/Bound/LP 영역 검증과 STAY·다중 MOVE·충방전·양/음 Q·SOC 경계 유한 사례 검증을 분리했습니다. 세 사례를 전체 동등성의 근거로 대체하지 않습니다.
- 원본 슬롯 최종 상태 계약을 감사했습니다. B0 Planning96/Actual96/Fresh 및 Prefix24 최종 상태는 PASS입니다. Actual 전역/MV 75.711008%, LV 46.810643%; 전압 0.951568~1.040377pu입니다. Prefix 저전압23초/과전압18초 및 Planning 초기 과전압15초는 추가 TIME 진단 FAIL로 그대로 보존합니다.

아직 전체 A1/A2 가변 Job·QoS·Carryout 모델, M2의 실제 A2 고정 영역, 96슬롯 동일 Case의 원본 K48/Beam/Joint 및 실제 Stage/Current-AC/Worker 연결이 인증되지 않았습니다. 원본 K48의 한 슬롯 Helper View와 8대 분할 검증 PASS는 이 전체 통합 인증의 대체물이 아닙니다. START_WINDOW 위반414개 캐시는 계속 거부합니다.

공식 캠페인·A1/M1/A2/M2/K48/Joint 장시간 최적화·Native presolve는 실행하지 않았습니다. 기존 V44/V1_add Source/Worker/원장과 이전 증거를 보존했습니다. May02~07 신규 과학 실행도 없습니다. 현장 GIS/보호설비 미인증은 별도 `FIELD_INSTALLATION_UNVERIFIED`로 관리하며 현재 시뮬레이션 차단 사유로 사용하지 않습니다.

필수14개 산출물과 한국어 상세 보고서는 `docs/v2_add/static_complete/`에 있습니다.
