# May01 전압 원인과 물리 후보 검토

기준 `759dd5f87edd7340c703507e42dc36ccd32afcdc`, 원본 `affc7226a519adbe072d7debbc3ae25ea71c3487`, 동일 V2_add/PR236이다. 원본 P5 Source1.04pu, Reg12 Vreg123.5V, CAPBank3 초기OFF 및 모든 선로·정격을 보존했다.

IDC08의 `full_mobile_idc08_lv.1`, Actual slot49/t44134s 무주입1.050523816pu는 480V Base 오류가 아니다. 원본 MV 상전압은 [1.045458734, 1.030324424, 1.045431200]pu이며, Delta/Wye의 LV A/B/C가 MV CA/AB/BC에 대응한다. 선간전압 전달 계산과 DSS의 차이는2.9743e-8pu, 동일 Tap/Cap 정적 재생의 전체 전압 오차는3.6326e-10pu다. 즉 현재 Delta/Wye 연구 설비에서 실제로 발생하는 전압 위반이다. 위상 순서 미정렬 비교 원문도 별도 보존했다.

원본 V44 IDC DSS 직접 readback은 Wye/Wye, 4.16/0.48kV, 750kVA, 권선%R=[0.8,0.2], XHL5.75%, 양 권선Rneut=-1, Tap1, 무부하/여자0이다. Rneut와 함께 실제 neutral node0 연결을 기록했으며 Rneut 숫자만으로 비접지라고 단정하지 않는다. 기존 Adapter는 Delta/grounded-Wye, 12.47/0.48kV, %R=[0.5,0.5], XHL5.662375826이다. DY와 Source-YY 각각24포트×13개 출력=312개씩, 총624개 양·음 P/Q·중간 출력 정적 점을 검사했다. 모두 포트 열 정격을 만족하지만 Source-YY도58개 점에서 국소 전압 위반이 있다. 순간 점을 일일 SOC 가능해로 취급하지 않았다. 최적화 전압 영역과 독립 Fresh가 계속 필요하다.

H0~H4의 위치는 기존 위반 경로의 가장 가까운 미사용3상MV선로를 기준으로 AC 이전에 동결했다. H1은 Bank3 재배치, H2/H3/H4는 기존3+1/2/3 Bank다. 결과는 `MAY01_SVR_HARDWARE_COMPARISON.csv`에 있다. Bank를 추가하면 IDC08 과전압은 줄어도 다른 경로의 지연 저전압이 생겼다. H4는 최대1.080995234pu로 과전압도 악화됐다. H4의 hyphen 버스는 기존 IEEE8500 식별자 whitelist만 확장하여 설치했으며 물리 파라미터는 바꾸지 않았다.

임피던스 맞춤 조정 대신 원본 V44의 Wye/Wye·R/X·Neutral을 그대로 쓰고 HV 정격전압만 실제12.47kV에 대응시킨 `H0_SOURCE_YY`도 별도 사전 등록했다. 이름판750kVA·기존 연구 포트600kVA·보수적인Normal/Emergency750kVA는 유지한다. 원본 Source의 기본Normal825/Emergency1125kVA와 이 보수적 신규 설비 한도는 구분했다. STA12와 C2 PCC, SVR3 위치는 그대로다. 이 후보의 B0 평가96은 0.951107894~1.049087870pu로 PASS지만 전체120은 FAIL이다. DY 계수를 YY에 재사용하지 않았다.

기존 초기 Tap은 모두1.0이고 최초 기존 Reg 동작은15초, 추가 SVR은30초다. 원본 냉시동의 저전압 `sx3312692a.1`은0.893556294pu, 23초 동안 존재하고 `190-8593.1` 초기 과전압은1.072061693pu로18초 지속한다. Planning 최초 `m1069533.3`은1.051828772pu다. H0_SOURCE_YY도 Prefix 저23초/고18초를 유지한다. Actual native0은2025-04-30 18:00 AEST, Planning native0은2025-05-01 00:00 AEST이며 IDC08 t44134는May01 06:15:34 AEST다. 절대 시각·MV/LV 분류·물리 상은 `MAY01_VOLTAGE_EVENT_CALENDAR_AND_PHASE.csv`에 추가했다. HVMV_Sub·750kVA 포트에는 자동 Tap 제어기가 없다. 원본12와 신규 SVR의 실제 TapNumber/Winding2·미래Queue·시간순서·포화·동작횟수는 CSV와 원시Trace에 기록했다.

초기 이전 AEMO/Weather만으로 Job-site 부하·Tap/Cap·내부 타이머·Queue를 동시에 확정할 수 없다는 이전 `integration/CAUSAL_PREFIX_INITIALIZATION_AUDIT.json`을 재사용한다. 이후 정착 Tap 복사, 반복 Prefix, Queue 삭제, Delay 생략, 위반시간 제외를 하지 않았다. Actual 전용 SVR로 Planning 문제가 해결됐다고 주장하지 않는다. 원본 상태·정책을 유지하는 범위에서 Prefix와 Planning의 물리적으로 정당한 해결책은 아직 확보하지 못했다.

각 baseline 위반의 Bus/Phase/Slot/시각/지속시간/Pending Queue/상류Tap 및 경로는 `MAY01_ALL_NODE_VOLTAGE_VIOLATIONS.csv.gz`, `MAY01_VIOLATION_UPSTREAM_PATHS.json.gz`에 있다. 무압축 원본은 Runtime으로 바이트 동일하게 옮겼고 위치 수정 증거가 원래 사전 봉인 SHA를 연결한다. 신규 구성·일정의 원시AC/Trace/Clock/상태·Fresh도 Runtime에 별도 보존했다.
