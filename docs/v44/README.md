# V44: V43 Planning + SVR12 Actual

2026-10-19 r043까지의 최신 결과와 실행 정책은 [r043 릴리스 기록](r043_release_20261019/README.md)에 정리했다. May01~07은 28/28건 Actual 실행 및 독립 Fresh 물리 검증 PASS다. May08~14는 B1/B3를 먼저 완료한 뒤 B0/B2를 날짜별 1-worker Planning→Actual/Fresh로 자동 이어서 실행한다. Planning Global Gap 인증은 Actual/Fresh PASS와 별도다. 이하 본문은 초기 준비 시점의 설계·검증 기록을 보존한다.

최종 Revision은 `V44_V43_PLANNING_SVR12_ACTUAL_V1`이다. 이전 SVR11 Planning Pilot 및 계수/Raw는 `svr11_revision01/`과 원래 Runtime 경로에 보존한다. 이전 준비 상태 문서는 `svr11_revision01/pre_final_architecture_snapshot/`에 보존했다. 최신 실행 여부와 상태는 `PREEXECUTION_CERTIFICATION.json` 및 `D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json`이 가리키는 캠페인 원장을 따른다.

Planning은 원본 IEEE123 / RegControl 7 / 추가 SVR 0 / Fixed ON Capacitor 4 모델이다. PR189 Fast A1, Seedless K16/K32/K48, Adaptive Beam 및 4-MESS Direct Compact Joint, 기존 FULL 제약/검증·Solver 정책을 유지한다. May01 동일 입력의 FULL은 961,472행·316,743열, C3A는 779,129행·306,040열이다. V43과 행렬 계수·목적함수·Bounds·변수 타입·행/열 Identity가 모두 정확히 일치했다. Native0 모델 생성 1회, Gurobi 최적화 0회다. 검증은 캠페인 밖에서 수행했다.

May01 B1 A1은 원본 Native/Windows/Source/정수 도메인·물리 계통이 같은 Golden003만 재사용한다. UB 0.6718471055537026, LB 0.6715871456570585, Gap 0.0386933%를 보존하며 재최적화하지 않는다. 다른 날짜의 A1/MESS 해를 복사하지 않는다. B3는 같은 날짜 B1 A1 → M1 → A2 → M2를 사용한다.

Actual/Fresh는 28 Case 모두 같은 IEEE123 + SVR12를 사용한다. 원래 7개 + 추가 36개 = RegControl 43개다. 성공한 `V43_FINAL_B2_SVR12_ACTUAL_AC_ONCE002`의 Scenario와 장비를 정확히 복제했고, 원래 SVR11의 BUS82 Line.l82 입력측 배치를 유지했다. 12번째 IDC01 뱅크는 Transformer.mess_idc01_tx Terminal1 입력측으로, 원래 149.1.2.3에서 svr_idc01_regulated를 거쳐 mess_idc01_pcc를 감지한다. 각 상 250kVA, 32 Tap steps / 0.9~1.1, VReg120·Band2V·Delay30s·TapDelay2s, MaxTapChange1 및 원래 PT/CT·임피던스·손실을 보존한다. 모든 12뱅크의 위치·정격·연결 및 Source SHA는 `v43_planning_svr12_actual_v1/FINAL_ARCHITECTURE.json`에 있다.

일별 D-1 18:00 독립 Source 초기 상태에서 24 Prefix + 96 평가 슬롯을 순차 계산한다. Planning Tap/Queue를 가져오지 않으며, 자정 초기화를 하지 않는다. Arm별 Actual Context, 후보별 Source/부하/Native TIME 상태 및 독립 Fresh Context를 구분한다. Tap은 최적화변수가 아니다. AIDC/MESS 명령은 동결하며 Actual P/Q 재최적화나 임의 Job 이동, 새 Time-shifting을 하지 않는다. Planning FULL 가능해와 Actual/Fresh 물리 안전 인증은 서로 다른 계통의 별도 결과다.

B0/B2는 기존 FCFS, B1/B3는 Known 연구용 허용창 완화와 Unknown R1-FLEX30-C1 / R1_ASSUMED를 유지한다. 기존 Signed Sensitivity 선택·수치 점수 코드는 그대로이며 원본 7-Reg 응답은 순위용 근사로만 명시한다. 이를 SVR12의 전압 인증으로 승격하지 않는다. 후보 실행의 최종 안전 판단은 실제 부하와 Tap/Queue를 계산한 새 SVR12 Current AC가 수행한다. 원래 7-Reg/SVR11 Current AC 인증이나 과거 Case의 affine/AC 보정 영수증은 재사용하지 않는다. Unknown QoS·권한·참여자 Hash와 GPU/Rack/확정예약/Overrun/WAN/Migration 제약, 0.95~1.05pu 및 모든 선로/변압기 정격은 그대로다.

기존 Reference C Raw를 독립 산술 검산했다. 96/96 수렴, 전압 0.9604433417~1.0459305301pu, 전압·전류·kVA 위반 0이다. 새 중복 AC96/Planning 재최적화는 실행하지 않았다. 새 Adapter는 짧은 Current/Fresh 동등성·43제어기 Inventory·자정 상태 연속성과 실제 B1 1제어시각 진입 검증으로 확인한다. 짧은 검증은 전체 B1 Actual96/Fresh96 및 Known Service Equivalence 인증이 아니다. 414 START, Unknown185 재현 또는 다른 27개 Case의 물리 PASS를 미리 주장하지 않는다.

May01~07 입력은 모두 MODEL_ASSUMED_VERIFIED다. May02~07 미지정 RUNNING 213 UID는 기존 issue-only 결정적 초기화로 복원했다. 실제 사이트 관측으로 승격하지 않는다. 일별 독립 MESS는 STA01/STA12/STA08/STA06, 차량별 760kWh, P300kW/PCS400kVA, SOC440~1080kWh 및 효율0.95라는 기존 연구 가정을 Planning/Actual에 동일 적용한다. 전일 최적해를 다음 날 초기 상태로 복사하지 않는다. Forecast causal availability는 NOT_CERTIFIED다.

사용자의 최신 직접 실행 지시와 스케줄러 재확인은 `v43_planning_svr12_actual_v1/EXECUTION_AUTHORIZATION.json`에 기록했다. B2 2-worker가 May01~07 날짜 큐를 먼저 처리하고, 큐가 종료되면 Main 1-worker가 날짜별 B0→B1→B3를 진행한다. 3개 Heavy Worker를 동시에 실행하지 않는다. Threads=1, M-stage마다 K48 별도300초 + Joint 별도900초 / 호출 cap140초, 기존10초 반환 여유, A1/A2 5400초·Gap≤0.5%다. 정상 timeout의 유효 FULL 해는 Gap 미인증으로 Actual에 인계하고, FULL 해가 없으면 해당 의존 단계만 차단한다.

Coordinator는 기존 공유 OS Lock 6개를 보유하며 Worker 슬롯·날짜/Arm Lock 및 PID 생성시각을 검증한다. 완료 Stage는 Source/Case/Hardware와 원장을 확인해 재사용한다. M Binary 복원은 FULL incumbent 재검산과 남은 Native 예산 재진입이며 Gurobi B&B 상태 복원이 아니다. Actual Tap/Queue를 정확히 복원하지 못하는 중단은 새 독립 Actual Attempt에서 처음부터 재생한다. Raw/원장/실패 Attempt를 덮어쓰거나 Native 예산을 초기화하지 않는다.

경량 회귀는 184 PASS / 0 FAIL이다. 날짜7개·Mock28개 체인, B3 A1 재사용과 A2/M2, Known/Unknown/FCFS 원래 메서드, 300/900 예산과 정상 timeout 인계, Binary/정적 역변환·원장, 실제 두 Mock 프로세스 OS Lock 동시성·중복 차단·종료 복구를 포함한다. XML 및 Native0/짧은 실제 AC 증거는 `v43_planning_svr12_actual_v1/`에 있다. 캠페인 안에 추가 검증 루프를 넣지 않았다.

기존 모니터 화면과 URL [http://127.0.0.1:8795/](http://127.0.0.1:8795/)을 부분 수정해 활성 Worker/PID/RAM/Stage, 별도 Native 예산·FULL/Gap, 날짜별 28 Case 상태를 표시한다. 새 서버/화면을 만들지 않는다.

실제 실행·Resume 명령은 Source SHA·7일 날짜·준비 인증 digest와 직접 사용자 승인이 결합된 Permit을 요구한다. 기본 CLI는 준비 전용이다. 캠페인 도중 Source/하드웨어를 수정하거나 미래 위반을 보고 SVR13을 소급 설치하지 않는다. 전체 28개 최적화·Actual/Fresh PASS는 실 결과가 있을 때만 인정한다. Draft PR233 유지, Main Merge 없음.

Current AC 후보별 전체 물리 Raw는 원래 경로에 보존하고, 감사 목록과 LRU 판정 캐시에 중복된 전체 Prefix 객체를 저장하지 않는다. 기존 V43의 감사 압축 방식을 사용해 Raw 참조·원래 판정·현재 요약·정확한 Source/부하 키를 유지한다. 메모리·JSON 직렬화 병목을 제거하는 저장 방식 수정이며 AC Solve/측정/정격 검사는 생략하지 않는다. 중단된 준비 검증 002의 부분 결과와 정산 기록도 별도 보존한다.

필수 준비 검증 최종 상태: **V44_PRESTART_READY**. Source SHA `f0c56b0ec67f58c213025c6528c5006b2ad20d8bcca2045cf92994835a673f72`, Actual Physics Source SHA `739598237b3b8b54e5fe9c7cb24f4b2b07c40ae40911d98614c70d2249e1bb01`. 이는 전체 28 Case PASS를 뜻하지 않는다. 상세 준비 보고는 `v43_planning_svr12_actual_v1/PRESTART_REPORT.json`을 따른다.

최신 사용자 지시: 활성 실행은 `V44_JOINT_CALL300_COMPLETED_K48_RESUME_V1` 운영 정책으로 Joint 호출 cap300초를 적용한다. K48 총300 / Joint 총900과 기존 사용량 차감을 유지하며, 완료 K48 지점에서 새 Attempt로 재개한다. 기존 과학적 Source와 기본140초 경로는 보존하고 별도 실행 정책 SHA로 구분한다. 상세 내용은 `v43_planning_svr12_actual_v1/cap300/README.md`를 따른다.

최신 사용자 정정: 완료 K48만 재사용하고 Joint는 새 독립900초를0초부터 시작한다. 이전 사용량은 차감하지 않는다. 활성 실행은 `v44.fresh900 --resume`이며, 이전 차감 정책 문서는 역사적 기록으로 보존한다. `v43_planning_svr12_actual_v1/fresh900/README.md`가 현재 정책이다.

최종 사용자 변경: 위 운영 기록을 대체하는 활성 정책은 `V44_SERIAL_ONE_WORKER_M_BARRIER_THREADS2_GAP3_V1`이다. 전체 Case Worker는 한 개이며, B2 May01~07을 순차 처리한 뒤 Main이 날짜별 B0→B1→B3를 처리한다. B2/B3 M1/M2의 Native Solver는 Threads=2 / Barrier, Joint Gap 3%이며 K48 300초·Joint 900초·호출 cap300초를 유지한다. May01 B2부터 `campaign002`에서 새 모델/K48/Joint 예산으로 실행하고, Golden003 재최적화와 기존 Raw 덮어쓰기는 없다. A 단계는 Threads=1·Gap0.5%, Actual은 기존 SVR12를 유지한다. 동일 코어·동일 추출 Root LP 비교에서는 Barrier91.807초, Dual212.925초로 둘 다 OPTIMAL이었다. 병렬 날짜 처리의 인과 효과를 측정한 실험은 아니다. 상세 근거·범위는 `v43_planning_svr12_actual_v1/serial_m2/README.md`를 따른다.

# Current execution policy: Q250 / M four threads

The latest user instruction selects `v44.q250_m4_v2`: B2 M1 and B3 M1/M2 use
per-vehicle reactive operating limits +/-250 kvar and four-thread Barrier,
with Joint inner gap 3%. A stages retain one thread. PCS400/P300, SOC, routes
and physical safety checks are preserved. This is an explicit new Q subdomain,
not an unchanged historical model. Fresh campaign004 starts at May01 B2 with
new M/K48/Joint clocks; one Worker processes B2 May01..07 then per-date
B0 -> B1 -> B3. Golden003 A1 remains reused. The older serial two-thread
policy is superseded. See [policy and evidence](v43_planning_svr12_actual_v1/q250_m4_v2/README.md).
