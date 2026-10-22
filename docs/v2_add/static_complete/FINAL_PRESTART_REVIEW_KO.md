# V2_add PR #236 — May01 원본 알고리즘 보존 및 정적 모델 검토

판정: **PRESTART_BLOCKED_WITH_EVIDENCE**. 공식 캠페인과 Native 최적화 호출은 모두 0회다.

원본 r043 `affc7226a519adbe072d7debbc3ae25ea71c3487`의 감사 대상 알고리즘 파일은 Git 정규화 Blob과 외부 SHA 핀 기준으로 변경이 없다. 일부 작업 파일의 CRLF 차이는 별도로 기록했다. 원본 K48/Beam/Direct Joint 코드는 보존했다.

이전 431,255행 지연 Master는 역사적 진단으로 보존했다. 새 공식 준비 경로는 해당 클래스를 가져오거나 호출하지 않는다. 원본 K48 Pricing은 계속 허용하며, 새 Grid CG·Lazy Callback·후보 후 행 추가·재최적화 루프는 사용하지 않는다.

| 모델 | Binary | Continuous | Rows | Nonzero |
|---|---:|---:|---:|---:|
| IEEE123 original FULL (user-provided reference) | 208312 | 108431 | 961472 | 8587630 |
| IEEE8500 DY original FULL (preserved prior reference) | 417296 | 3350097 | 20634824 | 302476152 |
| IEEE8500 Source-YY original FULL | 417296 | 3350097 | 20634824 | 302525444 |
| Historical delayed initial master (prohibited official path) | 417296 | 68609 | 431255 | 3071592 |
| Source-YY Static Complete M1 Native0 | 18680 | 1426579 | 1740213 | 51158488 |

정적 Native0 완성·전체 계수/RHS/Sense/Bound/Type/목적함수 Readback: **True**. 실제 Build/전체 Wall은 473.110713699949 / 558.8658952999394초, Peak RSS는 2.908703GiB다. 4GiB 및 시스템 여유 5GiB 보호를 적용했다. 부분 모델은 FULL로 승격하지 않는다.

완성 모델의 원본 Source-YY 대비 감소량: {'variables': 2322134, 'rows': 18894611, 'nonzeros': 251366956}. 단위는 변수/행/Nonzero다. IEEE123 대비 수치는 CSV에서 각 측정 범위를 구분한다.

정적 제거 분류: {'RETAIN': 1307684, 'EXACT_SUBSTITUTION': 2339646, 'SAFE_REMOVE': 7464472, 'EXACT_REDUNDANT': 9107430}. 안전 제약은 보수적 8포트 P300/Q250 외부 영역과 원본 성분의 반올림 오차 상계로 검증했다. 목적함수 면은 Ampacity 안전으로 제거하지 않고, 유지된 원본 면에서 함의되는 rho 하한으로 별도 증명했다. 미해결 행은 모두 남겼다.

독립 원본 FULL 동등성: **True**, 범위는 **고정 B0 AIDC의 M1**이다. 원본 전체 행, 생략 Bound, 복원식, 목적함수 및 LP 영역을 확인한다. STAY·다중 MOVE·P/Q·충방전·SOC 경계 유한 가능해는 정식화 전체 증명의 대체물이 아니다. A1/A2 가변 AIDC 및 M2의 A2 고정 영역은 이 증명의 범위 밖이다.

원본 node-flow Compact와 정적 Presolve를 재사용한 이동 블록은 Binary417,296→18,680이다. 변수489,321/행432,529/Nonzero2,974,415이며, Alias592개 및 삭제 행 근거1,167개를 원본 독립 유리수 검증기가 확인했다. 8대의 자유로운 STAY/MOVE·다중 이동·충방전·SOC·P/Q·PCS16 및24개 서비스 위치를 보존했다.

Source-YY 실제 OpenDSS 계수 재생성: **True**. Planning96, 독립 AIDC P/Q24축과 차량24개 위치 P/Q48축을 사용한다. 기존 DY 또는 IEEE123 계수는 재사용하지 않았다. 수학 Case SHA: `7af03a0cdc0f10720df1b4d7a0ec6e92f4fa2f3cd43c59f3a6c63919b1ba46bf`. 원본 입력 SHA를 명시적으로 묶은 Case는 `86c66af12f557def0b4000df18659e18b15860eeb232c3d4da09c71708077033`다. 원본 Source Wye/Wye IDC/480V와 기존 STA/750kVA, P5 및 SVR3를 동결했다. 유한 차분은 원본 알고리즘의 국소 선형화이며 전 제어 영역의 비선형 AC 인증을 뜻하지 않는다.

원본 평가 시점은 CommonClock의 실제 TIME 제어 처리 뒤 마지막 상태다. Source-YY B0 Planning96 전압 0.959196561398404~1.0405877827394807pu, Actual96/Fresh 전압 0.9515681447843148~1.040377077497905pu다. Prefix24의 최종 상태도 PASS다.

Actual96 전역/MV 최대 선로부하율은 75.71100804%, LV는 46.81064284%, MV–LV 차이는 28.90036520%p다. 기존 유한 P-only73.790115%, Q50 73.744164%는 Pilot이며 B2/B3 성과가 아니다.

Native TIME 전체 이벤트 안전은 FAIL로 보존한다. Prefix 저전압23초·과전압18초와 Planning 초기 과전압15초를 삭제하거나 초기 Tap/Queue/Delay를 바꾸지 않았다. 원본 소스는 제어 반복 중 모든 초의 전압을 최적화 안전 Gate로 검사하지 않으므로 이를 새로운 제약으로 추가하지 않았다. 원본 슬롯 최종 상태 판정과 추가 이벤트 진단을 분리했다.

원본 Stage 연결 상태:

- A1의 가변 Job/GPU/Rack/WAN/QoS/CC4와 Source-YY 전체 계통 FULL Native0·독립 수용 검증이 아직 연결되지 않았다.
- 전체96 원본 K48의 현재 Case 물리 메타데이터·배율 Helper View·Beam·Direct Joint 연결은 미인증이다. 단일 슬롯 Helper와8대 분할 검증은 범위가 더 좁다.
- A2의 실제 채택 M1 고정과 M2의 실제 A2 고정 입력·가변 영역 증명·Native0가 아직 연결되지 않았다.
- Actual B1/B3의 현재 AC·Controller, 전체 Migration·서비스·Carryout 독립 검증 및 실제 Checkpoint/Budget/Worker Handler 연결은 미인증이다.

원본 K48에 원시 IEEE8500 Helper를 직접 넣은 검사에서는 HELPER_PIVOT_AMBIGUOUS가 발생했다. 양의2진수 배율을 정확히 정규화한 Helper View는 실제 한 슬롯의 원본 exact_cut을 통과했다. 8대 분할도 차원 Guard만 바꾼 독립 계수 검증을 통과했다. 두 결과를 전체96 K48/Beam/Joint 통합 PASS로 승격하지 않는다.

원본 START_WINDOW 위반414개 캐시는 계속 거부한다. AIDC 전체 가변 Job 도메인, 실제 QoS/서비스/Carryout 및 Migration 검증을 고정 B0 또는 단일 Job 예제로 대체하지 않았다. GPU Scaling·경로 삭제·강제 STAY/MOVE·Budget/Gap 변경도 없다.

Checkpoint/Resume·실패 Stage 격리·중복 Worker 차단·입력 변조 거부 Fixture는 실제 과학 모델 인증과 분리한다. 기존 Native 원장과 Worker는 수정하지 않았다. 실제 최적화 전이므로 LB/UB/Gap 수치는 null이며, 이것 자체를 자동 실패 원인으로 삼지 않았다.

`SCIENTIFIC_SIMULATION_READY=False`, `FIELD_INSTALLATION_UNVERIFIED=True`. 현장 GIS/보호설비 인증 부재가 현재 시뮬레이션 차단 원인은 아니다. 물리 B0 후보는 원본 평가 계약에서 성립하지만, 전체 알고리즘 캠페인 Primary 인증은 남은 Gate 통과 전까지 보류한다.

준비 명령:

```powershell
& '..\V2_add_runtime\.venv\Scripts\python.exe' -X utf8 -m v2_add_preflight.static_execution proof
& '..\V2_add_runtime\.venv\Scripts\python.exe' -X utf8 -m v2_add_preflight.static_execution native0
& '..\V2_add_runtime\.venv\Scripts\python.exe' -X utf8 -m v2_add_preflight.static_verify
```

미실행 캠페인 명령 형식은 `python -m v2_add_preflight.static_execution campaign --approval <user-approval.json>`이다. 현재는 HOLD가 먼저 거부하며, 준비되지 않은 IEEE123 Worker로 우회하지 않는다. May02~07 신규 과학 실행은 하지 않았다.
