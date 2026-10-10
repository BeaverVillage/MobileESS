# 동결 계획 AC-only 재생 범위와 재현

이번 평가의 최상위 지시는 SVR4와 SVR7을 같은 날짜별 동결 AIDC/MESS 계획 및 Actual 입력에 적용하는 비교다. 새 Gurobi 최적화, 계획 변경, Actual P/Q 보정, Tap 결정변수 추가를 수행하지 않는다. 새 31일 MILP 캠페인은 보류한다.

실행 Source SHA는 `ce30af2a74d9d2b6a2f2a33fee7a690927752f940f94bd466218075ba34cbf04`이며 전체 1,225개 실행 Python 파일의 공통 Source Map을 사용한다. 시험 코드와 외부 실행 도구는 별도의 SHA/길이 영수증으로 보존한다. Source Map에는 Git commit 번호나 이 문서가 포함되지 않는다. 물리 재생 동안 실행 Source와 시험 코드를 수정하지 않았다.

SVR4는 STA01/STA06/STA08/BUS83의 기존 네 장치를 그대로 유지한다. SVR7은 BUS79/BUS108/BUS50 세 장치를 추가한다. `Line.l79`, `Line.l105`, `Line.l49`의 실제 하류 terminal 2에 직렬 설치하며 기존 선로 임피던스·길이·정격을 그대로 둔다. 총 7개 위치는 21개 단상 변압기 및 21개 추가 RegControl로 구현된다. 원본 IEEE123 RegControl 7개는 별도로 원본 AUTO 설정을 유지한다. 원본 커패시터 네 개는 Fixed-ON이고, 평가 시나리오의 D-STATCOM 및 CapControl 개수는 모두 0이다.

동결 계약은 `D:/v42_voltage_control_development_20261011/FROZEN_SVR4_INFRASTRUCTURE_06/HARDWARE_FREEZE_RECEIPT.json`과 `FROZEN_SVR7_INFRASTRUCTURE_02/HARDWARE_FREEZE_RECEIPT.json`이다. 각각의 SHA는 `61119445304423816bc67caf6745735e4850567798838b45f5b136543f12590a`, `490020ddf9c25f32a2bd6d6f13c5c05402aa5de0004f591047407bd96ccefffe`이다. 동일 Source에서 별도 DAYAHEAD/ACTUAL 인스턴스를 컴파일해 동일 원본 초기 상태와 서로 독립된 탭·큐 상태를 검증했다. 컴파일 초기상태 시험은 새로운 Planning 실행 또는 최적화된 E2E 검증을 뜻하지 않는다.

REF 비교는 두 단계로 구분한다. STATIC REF는 과거 저장 Actual 배열을 B1/B2 13개, B0 15개 전체에 대해 bit-exact로 재현하는 승인 게이트다. 주 비교 대상 REF_TIME은 SVR4/SVR7과 같은 native TIME 자동제어로 원본 계통을 96슬롯 재생한 결과다. STATIC REF와 REF_TIME을 섞어 전압 개선을 계산하지 않는다.

매 날짜는 독립 Fresh OpenDSS 프로세스에서 원본 초기 탭 1.0, 원본 커패시터 ON 및 빈 제어 큐로 시작한다. 96개 15분 슬롯을 순서대로 수행하며 슬롯 안의 원본 Delay/TapDelay 및 SVR 지연을 native DSS 시간과 제어 큐로 처리한다. 슬롯 경계에 남은 이벤트는 다음 슬롯의 현재 Actual 입력에서 처리한다. 수동 탭 설정이나 Planning 탭 복사가 없다. 측정 범위는 96개 슬롯 종료 상태이며 연속시간 과도현상 인증은 아니다.

열적 평가는 기존 native NormalAmps와 winding kVA를 보존하고 선로·변압기의 모든 실제 terminal 및 상을 검사한다. 변압기는 추가로 원본 winding 명판 전류 `kVA/(sqrt(3)*kV_LL)` 또는 단상 `kVA/kV_LN`를 독립 검사한다. kilo 단위가 상쇄되어 결과는 A다. 명판 전류와 native NormalAmps의 분모가 다른 경우 각각을 별도 보고한다. 과거 B0 `current_pu`는 원본 명판 전류 기준을 그대로 재현한다. 전압·A·kVA 배열을 바꾸거나 열적 한계를 완화하지 않는다.

손실 에너지는 슬롯 종료 손실 W를 0.25시간으로 합산한 추정치다. 슬롯 내 탭 이벤트 사이 손실을 연속 적분한 값으로 해석하지 않는다. Tap 동작은 슬롯 끝 변화, native 이벤트 및 슬롯 내 방향 반복을 구분한다. 기존과 추가 제어기의 서로 반대 방향 동작을 관측했다는 사실만으로 제어 발산 또는 무간섭을 주장하지 않는다.

유효한 동결 계획은 B0 31일, B1 31일, B2 3일이다. B2 나머지 28일과 유효한 A1→M1→A2→M2 결과가 없는 B3 31일은 NOT_TESTED이며 수치가 비어 있다. 승인 게이트로 실행하지 못한 유효 계획 날짜는 NOT_TESTED_CANARY_GATE로 별도 표시한다. 개발 및 비교에 사용한 날짜는 독립 Holdout이라고 주장하지 않는다.

현재 환경의 실행 도구는 Python 3.11과 `D:/v42_voltage_control_development_20261011/run_ac_only_svr_comparison.py`, `run_frozen_ac_day.py`다. 동결 큐는 `FROZEN_AC_MONTHLY_PRIORITY_03/FROZEN_AC_MAY31_PRIORITY_QUEUE.json`이며 SHA는 `301dafbb620152a2058e4700ef5b62b25d9e675358040544b12d12502b368c86`이다. 결과 루트는 `AC_ONLY_SVR4_SVR7_CANARY_03`이다. 각 날짜 폴더의 `DRIVER_USED.py`, `JOB_SOURCE_PROVENANCE.json`, 실행 Source 아카이브 및 입력·Actual 배열·슬롯 감사 영수증이 정확한 재현 근거다. 외부 원본 경로는 이 연구 환경에 종속되므로 다른 환경에서 복사본을 만들 경우 경로와 SHA를 다시 승인해야 한다.

새 SVR 계통에서 Planning 계통 모델 및 민감도를 재생성하고 D-1 Forecast만 사용하는 E2E 게이트를 통과하기 전에는 전체 MILP 캠페인을 허용하지 않는다. AC-only PASS는 기존 동결 계획의 물리 재생 PASS다. 새 계통에서 재최적화한 계획의 PASS, 모든 124개 정책·날짜 검증, 실제 제조사 설비 인증을 뜻하지 않는다. SVR 손실·임피던스·정격은 명시적인 유한 연구 설비 가정이며 투자비·설치비·경제성은 연구 범위 밖이다.
