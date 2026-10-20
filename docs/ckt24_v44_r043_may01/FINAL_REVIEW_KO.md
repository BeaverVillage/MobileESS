# Ckt24 r043 May01 사전 검증 결과

작성 UTC: 2026-10-20T06:00:48.841105+00:00. 요청한 B0/B1/B2/B3 및 8대 FULL/Compact/Actual/Fresh 최종 검증은 **미완료**다. 실행 전 Gate를 통과하지 못하여 A1/M1/A2/M2를 시작하지 않았다. 이 PR은 이식 완료나 확장성 성공 인증이 아닌 재현 가능한 사전 조사와 중단 근거다.

## 동결·격리

알고리즘 기준은 `affc7226a519adbe072d7debbc3ae25ea71c3487`이며 별도 Worktree `D:\ckt24_v44_r043_may01`와 Runtime `D:\ckt24_v44_r043_may01_runtime`를 사용했다. 기존 r044 이후 코드·운영 Worker·Monitor·원장·예약 작업을 수정하거나 중지하지 않았다. 소스의 기존 절대경로 기반 dispatcher를 호출하지 않았다. IEEE123 A1/UB/LB/Checkpoint를 Ckt24로 가져오지 않았다.

EPRI SVN r4176의 원본 파일 23개를 SHA-256으로 봉인했다. master는 스스로 전체 실행을 금지하는 복수 A-Diakoptics 예제를 포함하므로, 별도 adapter에서 계통 정의 prefix만 읽고 경로를 절대경로로 해석했다. 선로·변압기·부하·RegControl·정격은 변경하지 않았다. 원본 Ckt24에는 PV가 없고 RegControl은 1개다. IEEE123의 7개 RegControl이나 SVR12를 복사하지 않았다. SVR12 배치·연속접속·권선 검증은 수행되지 않았으므로 적용할 수 있다고 인증하지 않는다.

## 실제 측정

원본은 6,058 buses, 7,522 전기 노드, 5,222 선로, 843 변압기다. MV buses 1,349, LV buses 4,708. 원본 좌표가 있는 bus는 1,347개다. 좌표가 없는 LV bus의 XY를 생성하지 않았다. 도면은 원본 좌표를 가진 연결만 표시하며 전체 AC에는 모든 설비를 포함했다. 원본 buscoords의 GIS CRS·단위·지리적 의미는 다운로드 폴더에서 확인되지 않아 실제 GIS 위치 보존을 인증하지 않는다.

원본 8760시간 shape에 May01(연중 시간 2880–2903.75)을 대응시켰다. 이는 원본 shape를 2025년 실측 자료라고 주장하는 것이 아니다. 15분 시작 시각 96개에서 모든 bus/상 전압, 양단 선로/상 전류, 변압기 각 권선 kVA/전류 및 원본 제어 상태를 추출했다. `ORIGINAL_BASELINE_*`와 요청 이름을 따른 `B0_MV_LV_BOTTLENECKS.csv`는 **AIDC가 아직 포함되지 않은 원본 배경망 진단**으로, 공식 B0 결과가 아니다.

원본 제어를 동작시킨 순차 진단: 최대 부하율 0.665656215, 전압 0.967191460–1.050120817 pu, 최대 변압기 부하 1.806800501 pu. 변압기 초과 66/96슬롯, 전압 범위 초과 24/96슬롯이다. 원본 master처럼 controls off인 경우와 static인 경우를 모두 별도 비교했다.

낮의 지배 선로는 원본 `Other_Feeders`다. 이는 SubXfmr_LSB에서 `Feeders` 등가 부하로 이어지는 가지다. LV 선로나 이 가지를 목적함수에서 제외하거나 정격을 높이지 않았다. static 주간 최대 서비스 변압기는 `05410_g2100nj7400`이며 과부하를 숨기지 않았다.

배경부하 후보 1.0·0.75·0.5를 AC와 B3 실행 전에 등록했다. AIDC/GPU/Job/PCS/PV/정격은 스케일하지 않았다. 배경망 단독 검사에서 어느 후보도 전압·전류·변압기 조건을 동시에 통과하지 못했으므로 최종 시나리오를 선정하지 않았다. 이것을 모든 가능한 AIDC 배치의 불가능성 증명으로 해석하면 안 된다. 완전한 B0와 실제 Job/전력 모델 검증은 별도로 남아 있다.

## 교통·공간·제어 가능성

교통 서비스 24개(IDC12+STA12), 48개 교통 노드, 509개 Link 및 May01 Route Table 55,296개 경로를 확인했다. Route/Forecast는 r043 SHA와 일치하고, SUMO 원본 junction에서 XY를 직접 읽었다. 경로·ETA·에너지·connection-ready·서비스 ID를 재생성하지 않았다. `IDCnn → AIDCnn`은 원래 workload와의 명시적 별칭이며 순서를 바꾸지 않았다. 전력망–교통망은 합성적 거점 대응이며 동일 GIS 위치라는 주장이 아니다.

380개 원본 좌표 보유 MV 3상 bus에서 P ±30 kW / Q ±25 kvar의 독립 Fresh AC를 계산했다. 이는 가상 MV 주입 포트의 순간 응답이며 포트 설치·변압기·PCS 접속·SOC·경로·Job의 운전 가능성 인증이 아니다. 전체 최대 부하율과 Top20 각각의 부하율 변화, 전압 극값, 변압기 부하를 기록했다. 최상 delta rho는 -4.00736483e-05, 최악 delta rho는 4.00732361e-05다. Top20은 기본 혼잡 집합과 전체 max 변화를 함께 기록한다.

민감도 조사는 초기 진단에서 선택한 slot 67 (16:45)에 고정됐다. 최종 강화 수치 설정의 순차 진단 피크는 slot 69이며, 두 시점이 다르면 최종 피크의 감도를 조사했다고 해석할 수 없다. 각 Fresh 회로는 원본 tap 초기값부터 정착시킨 별도 snapshot이며 순차 운전의 tap 이력을 이식하지 않았다. 표의 Fresh 기준 rho 0.657374549와 순차 피크 rho 0.665656215도 다르다. 이는 미완료 사전 survey이며 완성된 AIDC B0나 동일 순차 제어 상태 주변의 민감도 인증이 아니다.

무교란 0 kW / 0 kvar 포트 추가에서도 최대 9.40789971e-07 pu의 차이가 관측됐다. 이는 엄밀한 오차 상한이 아닌 경험적 수치 바닥이다. 원본 `Other_Feeders`의 R1=1e-8, X1=1e-9 ohm은 수치 조건을 주의해야 하는 요소이며, 원인 확인을 위해 원본 임피던스를 변경하지 않았다. 작은 응답의 신호/무교란 비와 중앙 유한차분을 `FINITE_DIFFERENCE_QUALITY.csv`에 함께 기록했고, 약한 P 응답을 인증으로 승격하지 않았다.

공간 screening: `{'attempts': [{'scope': 'ALL24', 'status': 3, 'solutions': 0, 'wall': 9.963000059127808, 'source': 'OFFLINE_MAPPING_ONLY_NOT_A1_M1_A2_M2', 'spatial_metric': 'Original axes; no rotation/reflection/axis exchange', 'electrical_branch_dispersion_certified': False}, {'scope': 'AIDC12', 'status': 2, 'solutions': 2, 'wall': 0.8309998512268066, 'source': 'OFFLINE_MAPPING_ONLY_NOT_A1_M1_A2_M2', 'spatial_metric': 'Original axes; no rotation/reflection/axis exchange', 'electrical_branch_dispersion_certified': False, 'postcheck': 'DRAWING_ORDER_PASS_GEOGRAPHIC_AUTHORITY_AND_PHYSICAL_PCC_PENDING'}], 'rows': 12, 'relations': 132, 'inversions': 0, 'frozen': False, 'selection_limit': 'No port/transformer/interface engineering or branch-diversity certificate; no final deployment claim'}`. 모든 관계는 원본 X/Y축에서 검산하며 .01m Traffic 공차와 .01 원본 Ckt24 좌표 단위 공차를 먼저 고정했다. Mapping이 존재해도 물리적 PCC freeze가 아닌 **원본 도면 순서의 잠정 witness**다. branch 분산·실제 PCC 정격·포트 수가 인증되지 않아 최종 배치로 사용하지 않았다. 원본 정격을 만족하는 8대 초기 위치도 동결하지 않았다.

이번 offline 후보집합 380개와 3상 MV·서로 다른 bus·엄격한 원본 축 순서 조건에서 전체 24개 모델은 INFEASIBLE(status 3)로 종료했고, AIDC12 모델은 OPTIMAL(status 2) 잠정 witness를 찾았다. 이것은 모든 전압·상·설비 구성을 포괄하는 보편적 불가능성 증명이 아니다. AIDC12의 검산 132개 관계는 역전 0이지만 STA12는 미배치다. 따라서 전체 24개 관계 552개 PASS나 8개 STA 포트 AC 시험을 주장하지 않는다.

원본 Job descriptor와 12개 GPU 용량 및 전력 권한을 보존했다. descriptor의 Timeshift/Migration 권한은 실제 feasible schedule이 아니다. 실제 Job 변경→P/Q→Ckt24 AC witness가 없으므로 AIDC 및 Joint controllability는 false다. 가상 AIDC 부하 응답은 P 주입 부호를 반대로 해석할 수 있지만 실제 부하 감축 가능량으로 인증하지 않는다.

## 남은 필수 작업과 결과 해석

8대 Native0/FULL/Compact/Projection/독립 Replay, Ckt24 전기 계수와 실제 AIDC 기준 B0, 유효 PCC/포트 정격, branch 분산, 실제 Job 스케줄 기반 제어 가능성, 원본 Ckt24 설비 기반 TIME Actual adapter가 남아 있다. 차량 4 고정 위치는 `MESS8_HARDCODE_AUDIT.csv`에 기록했으며 수학적 동등성을 검증하지 않고 고쳤다고 주장하지 않았다. 따라서 기존 B0/B1/B2/B3 dispatcher에 이 실험을 연결하지 않았다.

`MAY01_B0_B3_FINAL_RESULTS.csv`의 네 행은 모두 NOT_RUN이며 UB/LB/Gap은 빈 값이다. TIME_LIMIT, FULL 가능해, Gap 인증, Actual/Fresh PASS를 생성하지 않았다. 개별 전기 민감도 합을 공동 효과로 보고하지 않았다. 최종 비교·계산시간·실제 AIDC 제어 heatmap은 측정이 없어 생성하지 않았다.

기존 r043 May01 최종 결과는 비교용으로만 별도 보존했다. 기존 B2/B3의 M_gap_certified=false도 유지했다. Ckt24 계통 규모와 차량 수가 함께 달라지므로 향후 성공해도 순수 계통 노드 수만의 scalability 실험이 아니다.

실행 명령과 파일 범위는 `README.md`, 각 Gate는 `PRE_SOLVER_GATES.json`, Raw 파일 경로·SHA는 `RAW_AC_RECEIPTS.json` 및 `SENSITIVITY_RAW_RECEIPT.json`에 있다. 원본 파일과 core source를 임의 수정하지 않고 모든 Gate를 다시 통과한 후에만 새 Ckt24 B1 A1부터 계산해야 한다.
