# V42 CapControl·SVR 개발 기록

상태: 구현·진단 진행 중. 31일 캠페인 배포 보류.

최상위 변경 지시(2026-10-11)에 따라 D-STATCOM 개발 및 사용을 종료했다. 새 과학적 코드 루트는 `D:/v42voltage`이며, D-STATCOM 실행 패키지가 없다. 과거 921건, STA08 단일 장치 40건, Tap-aware 단일슬롯 진단과 코드는 별도의 역사적 증거로 보존한다. 단일슬롯 성공은 96슬롯 또는 캠페인 검증을 의미하지 않는다.

원본 7개 RegControl의 VReg/Band/R/X/PT/CT, 탭 범위, Delay=15초, TapDelay=2초와 자동 운전을 유지한다. 기존 커패시터는 C83 600kvar 1단계 및 C88a/C90b/C92c 각 50kvar이며 원본은 Fixed-ON이었다. CapControl은 이번 Source Epoch에서 추가하는 설비다.

REF(원본 Fixed-ON, 추가SVR 없음), CASE A(CapControl만), CASE B(Fixed-ON 및 SVR만), CASE C(CapControl 및 SVR)의 독립 비교를 수행한다. C83 단독 → 4개 커패시터, SVR 1개 → 필요한 2/4개 순서로 실제 동일 계획·입력 96슬롯을 진단한다. 새 제어는 기존 MILP 결정변수나 목적함수에 추가하지 않는다. 전압 한계는 Planning/Actual 모두 0.95–1.05pu다. 물리 정격, Actual MESS P/Q 및 SOC·경로는 완화·수정하지 않는다.

Snapshot/STATIC 반복은 실제 초가 아니다. 시간 기반 제어를 도입한다면 해당 global control mode 변경을 새 계약과 별도 REF 진단에 명시하고, 실제 DSS 시계와 queued action 기록으로 15분 슬롯 내 상태 계승 및 지연을 검증한다. 원본 RegControl element 설정은 변경하지 않는다.

개발에는 2025년 4월과 이미 알려진 B2 May01/B1 May28 사례를 사용한다. 해당 사례는 독립 Holdout이라고 부르지 않는다. 설치 위치·정격·임계값·밴드·지연을 평가 전에 동결한다. Planning은 D-1 Forecast, Actual은 동결된 정책과 해당 시점 Actual을 쓰며, 서로 독립된 Fresh 초기 탭·커패시터 상태에서 시작한다.

새 직렬 SVR이 추가되면 Planning의 계통 토폴로지, 민감도 및 물리 Source Authority를 재생성해야 한다. 이 Gate가 완료되지 않으면 새로운 Native 최적화나 전체 캠페인을 실행하지 않는다. 최종 공통 설비와 실제 E2E Canary가 검증된 뒤 B0 31일(1worker) → B2 31일(3worker) → B1 31일(1worker) → B3 31일(1worker) 순서를 적용한다.

투자비·설치비·경제성은 연구 범위 밖이며 분석하지 않는다. 논문은 CapControl/SVR을 공통 배전계통 전압제어 인프라로 가정하고 AIDC–MESS 공동최적화 및 최대선로부하율 개선을 핵심 평가로 유지한다. 미실행·미검증 결과를 0건 또는 PASS로 표시하지 않는다.
