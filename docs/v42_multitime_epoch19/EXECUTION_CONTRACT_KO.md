# Source19 Multi-Time 정적 검증 계약

Dense·Physical·Exact 증명·Source/행렬 동결 및 승인된 단일 Root 측정이 끝난 뒤 시작한다. 선행 결과는 Draft PR207의 동결 head `497609b46faa14ea7e32a9483a333ab32fd264ef`다. 선행 실행 Source SHA는 `146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8`, case SHA는 `34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292`다. 모든 모델/입력/Proof authority는 이 Source18r의 실제 저장 구조에 묶는다.

현재 Root는 TimeLimit600에 미완료됐고 의미 있는 완료 LP 기준점이 없다. 따라서 이번 연구의 Full-size MILP/LP Native 호출은 0회로 고정한다. Root600 반복, Parameter sweep, 31일 캠페인, Cut generation 반복은 금지한다. 작은 Fixture도 Exact Rational 산술/경로 열거로 확인해 Native0을 유지한다. Solver 호출을 만들거나 예약하지 않는다.

PR109~111/137/167/169/182/185~187의 1차 소스 실패·비물질 결과를 먼저 감사한다. 651개 기존 제약 또는 거대 EF를 복제하지 않는다. 현재 계통 계수/물리 상계로 1개 실제 선로와 1개 구간만 선택한다. 과거 다른 Source의 LP 점·LB·슬롯은 현재 위반/성능 증거로 사용하지 않는다.

후보는 원본 정수 가능해 보존을 96슬롯 일반 수학 증명과 독립 검증으로 확인한다. 분수점이 정수 Convex Hull에 속하면 배제할 수 없다. 단순 SOC 등식 합산, DAG 경로 분해로 이미 암시되는 행, 기존 Mode만 바꿔 고칠 수 있는 위반은 효과를 주장하지 않는다. 충전 후 복귀, 이동 후 Q 공급/흡수, 다슬롯 종단SOC 복구 및 Rebound는 모두 허용한다.

후보는 최대1종이며 Full-size 추가 제약·행·열·NNZ·Binary는 모두0이다. 정적 조사 wall 목표는30분 이하이고 Full 모델 재생성·NativeOptimize·LP·MILP·파라미터 탐색은0이다. 실제 Current LP 위반 또는 완료된 비교 LB 개선이 없으면 채택하지 않고 `LB_IMPROVEMENT_UNPROVEN`/`MULTITIME_TIGHTENING_LB_UNPROVEN`으로 판정한다. B2/B3 생성기·Source17·Source18·원본 입력·과학 증거는 변경하지 않는다. 5월 캠페인 HOLD, Windows 예약 Disabled, heartbeat PAUSED를 유지한다. 결과는 별도 Draft PR로 기록한다.

## 최종 사용자 정정 적용

후보1종, Fullsize제약삽입0, 모든Native/LP/FullMILP/Fullmodel재생성0. Static판정 MULTITIME_LB_UNPROVEN으로 종료했다. Root진단은 기존로그/저장행렬 Native0만 수행한다. Threads1/Worker수 유지, Threads2/4 및 자동증가 금지, 페이징/가상메모리 증설 금지. WholeprocessPeakRSS/PrivateCommit/AvailableRAM/Commit여유를 사용한다. 공용 예산·중단정책은 수정하지 않는다.
