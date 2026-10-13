# B2 정차해 고착 진단 및 수정 — 캠페인 HOLD

May01은 PR220과 **같은 수치 최적화 문제**다. 기존 Raw의 현재 Original FULL Replay가 `0.5398310226338695`로 PASS했다. 운영 어댑터가 같은 Case의 검증된 이동 incumbent를 계승하지 않고 `RAW_REL`을 신규 정차 초기점으로 바꾸어, 우선 포함해야 할 MESS03의 완전한 3회 이동경로가 빠졌다. 경로 평가에도 별도 편향이 재현됐다. 이 두 인과관계를 수정했으며, 캠페인을 재개하지 않았다.

## 1. 실제 중단

Supervisor PID 32804, May01 Worker PID 15044, May02 Worker PID 16768은 종료됐다. PID·생성시각·명령줄을 확인한 소유 프로세스만 처리했다. 신규 Dispatch를 STOP/HOLD로 차단하고, 기존 Native cancel callback을 사용했다. Native 종료·원장 `inflight=null` 확인 후 Python orchestration을 종료했다. Windows 예약 Supervisor는 Disabled다. 모니터 PID 35740/기존 8793 포트는 유지했다.

May01 Native 최종 사용량 **1003.5010001659393초**, May02 **943.4019999504089초**다. May01 마지막 호출은 자연 종료됐고 May02 마지막 호출은 `RESOURCE_SOURCE_OR_USER_CANCEL`로 종료됐다. 두 날짜는 `DIAGNOSTIC_STOPPED`, 캠페인은 `HOLD_DIAGNOSTIC`이며 B2 완료 날짜는 0이다. FAIL/PASS를 새로 만들지 않았다. B0 31개 PASS와 독립 B1은 그대로 보존했다. B3 신규 M Dispatch도 HOLD다.

보존 루트는 `D:/v42_may_joint_repair_campaign_20261013`, 동결 운영 Source는 `D:/v42_may_joint_repair_source_20261013`이다. Native 원장·입력·Raw·로그·Reservoir·Pool은 그대로 두었다. 1,015개 증거 파일의 해시 인덱스는 별도 진단 루트에 있다. 기존 모니터의 상태 조회/운영 telemetry는 계속될 수 있으므로 모든 모니터 파일이 영구 불변이라고 주장하지 않는다.

## 2. Source/Case와 물리 문제 비교

기준 scientific source는 PR207 `497609b46faa14ea7e32a9483a333ab32fd264ef`, 연구 기준은 PR220 `b9684fa0999b88092d0cd38229f3453ef3f901b4` 및 PR221 `a874df15b9a306a7d769a60622b40fb76de3ffcc`다. 운영 전체 실행 SHA는 `e0e1f615d5773bbbe86720fff69811b40a9f65de82cde215106086c1f8ad2375`이며 연구 Git SHA와 같은 개념이 아니다. 운영 변경에는 날짜 연결·전처리 캐시·controller가 있다.

기존 Case SHA `34c0efff…`, 현재 `b6577cef…`와 bundle/anchor 메타데이터 SHA는 다르다. 하지만 FULL CSR, FULL named Domain, Dense CSR, Dense named Domain, 원본 Route Table은 각각 완전히 일치한다. FULL은 1,130,336행 × 344,967열, Dense는 715,596행 × 354,277열이다. Domain 해시는 모든 ndarray의 이름·형태·dtype·바이트를 포함하므로 Objective/RHS/Bounds/Types/행·열 좌표도 비교 범위에 포함된다.

이는 Grid/Voltage/Current/Security/PCC/Response의 계수와 RHS, FULL에 들어간 Forecast Load/PV/고정 AIDC, 초기/종단 SOC·충방전 효율·PCS16·Mode, SVR/Capacitor 고정조건의 **수학적 영향이 같음**을 보여준다. 원본 DAG/Arc/ETA/이동에너지는 같은 Route Table이고 현재 Raw의 독립 물리 Replay도 통과했다. 목적함수는 같은 `min rho_max`, 4 MESS, 24 sites, 96 slots다. 실제 수학적 물리 변경은 발견되지 않았다.

보조 확인으로 PR207 Git에 보존된 legacy final-integration input JSON도 읽었다. network/alpha_BG/capacities/racks/초기 위치/battery는 같다. Battery는 min440/max1080/initial760/terminal760kWh, P_limit300kW, PCS400kVA, 효율 각각0.95, dt0.25h다. issue_time은 같은 순간이고 Route Table 내용도 같다. 하지만 이 legacy bundle은 PR220 authority가 가리키는 exact Source18r bundle과 다르다. 실제 배열을 읽어 보니 첫 차이는 voltage_constant의 shape `[96,386]` 대 현재 `[96,838]`이며 branch 축도383 대416이다. 따라서 이 legacy 파일을 현재 문제의 비교 기준으로 채택하거나 단순 npz 포장 차이라고 설명하지 않았다. 대상 CASE 동일성 판정은 **PR220 Source18r의 FULL/Dense named CSR/domain** 및 현재 Original FULL Replay에 근거한다. 이 보조 비교의 적용 범위와 실제 차이는 `PHASE1_ACTUAL_GRID_ARRAY_COMPARISON.json`에 분리했다.

PR220 authority와 정확히 같은 해시의 과거 anchor JSON을 PR207 Git object에서 복원해 실제 leaf를 비교했다. **유일한 변경은 `/independent_AIDC_identity/source/path`이고, 고정 controls/control_names는 모두 같다.** 이전 FULL npz와 정확한 PR220 provenance bundle JSON은 이전 외부 실행 경로에 남아 있지 않아 모든 bundle leaf의 최초 차이를 복원했다고 주장하지 않는다. 보존된 PR220 authority의 전체 수치 해시와 현재 실제 배열 재계산, 현재 FULL Raw Replay로 **CASE_IDENTICAL_IN_NUMERIC_MODEL**을 판정했다. 달라진 실행/파일 위치 메타데이터를 물리 문제 변경의 근거로 사용하지 않았다. 상세 해시는 `PHASE1_HASH_SCREEN.json`, anchor 실제 비교는 `PHASE1_ANCHOR_ACTUAL_COMPARISON.json`, 실제 행 위반/물리 항목은 `PR220_CURRENT_MAY01_FULL_REPLAY.json`에 있다.

## 3–4. 완전한 이동경로와 탈락 위치

MESS03: STA08→IDC06 (Depart4/Arrive6/Connect7, arc4954), IDC06→IDC05 (64/66/66, arc37751), IDC05→IDC01 (77/79/79, arc44900). 이동에너지는 합계 **66.66442632042374kWh**다. MESS01/02/04는 각각 STA01/STA12/STA06 STAY다.

완전 경로 Signature는 `448e4e1d8cf4bc78739de40de6d659c389d2d28e84a6992d20ac2a966593a101`이다. 현재 DAG에서 유효하지만 운영 initial generated 13개 MESS03 후보, 최종 Reservoir 725개, 생성된 12개 Pool의 각 8개 후보 모두에 없었다. 즉 Reservoir/Ranking/Admission 이전에 authoritative route가 누락됐다. 개별 MOVE만 존재하는 것으로 판정하지 않았다.

해당 경로를 진단용으로 삽입하여 초기 STAY context에서 평가하면 기존 Lookahead score는 **0.6810899843834426**으로 STAY **0.6760534504652362**보다 나쁘다. Reservoir에 삽입했을 때 순위는 726개 중 **90위**다. 이 점수는 미변경 차량의 측정 P/Q를 고정하고, 변경 차량의 greedy 시간 순서 운전만 근사한다. 따라서 실제 4대 공동 redispatch 후 FULL UB 0.539831 대비 **0.1412589617495731** 과대 예측이 재현됐다. 충전 Rebound는 기존 V3에서 signed service에 이미 포함되어 extra를 다시 더하지 않으므로 이 반례를 단순한 Rebound 중복 합산으로 설명하지 않았다.

Beam width12/16, label expansion의 depth4 및 feedback expansion의 depth3+depth4 reservoir는 heuristic 제외다. 현재 연구 알고리즘에는 전역 완전 탐색 보장이 없다. width/time limit 증가 또는 MOVE 보너스로 문제를 가리지 않았다.

## 5. lambda/Start/Native 입력

중단 전 May01·May02 각각 11개 Native Joint 호출의 모든 저장 capture는 네 차량 모두 ordinal0 STAY one-hot였다. May01 5개/May02 5개 호출은 Status2 restricted OPTIMAL, 나머지는 Status11 INTERRUPTED였다. Status11에는 140초 wall/interruption 및 user cancel이 포함되며 전부 정식 Status9 TIME_LIMIT로 재표기하지 않았다. 실제 ObjBound와 Gap을 각각 보존했다. 현재 모델에 winner가 없으므로 제한 Pool의 OPTIMAL 0.676053은 원본 전역 최적성과 무관하다.

수정 검증 Pool에는 원본 winner를 완전하게 포함했다. 4 one-hot lambda, 원본 Route/Node/Flow/Arc/Alias, 384 modes와 Pch/Pdis/Q/SOC가 복원됐다. Native CSR/RHS/Sense/Bounds/Types/Objective/Start Readback 모두 PASS. Binary416, 열137,635, 행715,600, NNZ7,008,230이며 Start 최대 행 잔차는 `9.947604224258756e-11`이다. `T@Start`는 원본 Raw와 배열 단위로 동일하다.

Gurobi Optimize/Presolve는 호출하지 않았다. 따라서 **Native Start 속성 반영과 수학적 유효성**은 확인했지만, Solver의 Optimize 중 MIP Start 처리 메시지/탐색 채택을 새로 확인했다고 주장하지 않는다.

## 6–7. 직접 원인과 최초 코드

운영 `v42_may_final/pr221.py::_optimize_case/configure`는 same-case historical incumbent registry 없이 `_initialize`를 호출하고, 모든 research module의 `RAW_REL`을 `INITIAL_POINT.npz`로 바꿨다. `_initialize` 자체는 유효한 `case.point`를 재사용하지만, 운영 이전 계약에서 PR220 winner가 여기에 제공되지 않았다. 명시 `initial_point` 인자도 adapter에서 반영하지 않았다. 이어 archived legacy pool을 제거하여 same-case winner를 보존할 다른 경로도 없어졌다.

`tools/adaptive_compact_joint/beam.py::generate` 및 `resume_feedback.py::generate`가 이 정차 Raw를 `PR220_AUTHORITY`로 읽어 우선 포함했다. 그래서 실제 historical winner는 생성/Pool에 들어갈 의무를 잃었다. heuristic redispatch 편향은 후보 순위의 별도 문제다. 정상 Joint solver를 네 차량 이동 불필요의 증거로 해석할 수 없었다.

## 8. 수정 및 수학적 차이

`incumbent.py`는 날짜/Arm, FULL·selected CSR/domain 및 Route/Battery 계약을 묶은 명시 registry를 사용한다. Raw bytes 확인→owned output에 그대로 복사→현재 FULL Replay 후에만 승인한다. 다른 날짜/입력 및 변경 Raw는 읽기/검증 단계에서 거부한다. 현재 stage point와 승인된 incumbent를 모두 비교하고 최선을 초기점으로 전달한다. `VERIFIED_CASE_AUTHORITY`에 현재 최선을 저장해 pool 우선 포함을 유지한다. BEST_GLOBAL_UB와 BEST_MOVING_FEASIBLE_UB를 각각 보존하고, 각 Pool ObjVal/FULL UB와 분리한다. 더 나쁜 capture가 다음 feedback center를 덮어쓰지 않는다.

`dispatch_score.py`는 기존 Beam labels를 유지하면서 최종 admission shortlist만 작은 joint redispatch LP로 재평가한다. 네 차량의96-slot Pch/Pdis/Q/SOC, 96슬롯을 덮는 original critical rows, PCS envelope, 이동 접속 차단/에너지/효율/종단 SOC와 충전 Rebound를 동시에 고려한다. 원본 mode disjunction을 연속 완화한 heuristic이고 전체 Grid를 검증하지 않으므로 FULL UB/Global LB로 사용하지 않는다. 차량별 원래8 후보+추가4 finalists 및 보존 witness만 평가하고 LP당2초/Threads1을 사용한다. LP 실패는 원본 경로 불가능 판정이 아니다.

원본 Exact C3A+Dense Joint MILP의 모든 물리 행·RHS·Bounds·Types·Objective와 384 binary modes는 그대로다. 바뀐 부분은 후보집합/Start/최종 heuristic ranking이다. STAY·단일/복수 MOVE, 서로 다른 목적지·출발·접속시각, 네 차량 동시 이동 선택권을 유지한다. 특정 차량/이동 횟수 강제는 없다. Restricted feasible 영역의 원본 FULL 포함 증명도 그대로 통과했다.

## 9. 회귀 결과

현재 Original FULL old Raw PASS; repaired production Beam body에서 완전한 winner 생성·Pool 유지 PASS; 각 차량8개 후보의 STAY/단일/복수 MOVE PASS; Native0 exact links/Start/CSR PASS; 실제 Raw의 최종 Bank 계승 PASS; 날짜·물리 drift/Raw 오염/foreign cert/나쁜 Pool 보존 및 SOC/rebound/time coverage 테스트를 포함해 **17 tests PASS**.

같은 initial context의 redispatch LP score는 STAY **0.47589068413920194**, 기존 moving **0.46309732724272656**으로 편향 반례에서 moving을 더 좋게 평가했다. 이는 heuristic 품질 진단이며 새 가능해/인증 bound가 아니다. 확인된 FULL UB는 기존 **0.5398310226338695**이며 새 개선해는 없다. 기존 K48 LB **0.4649848699754817**은 연구 인증 기록 그대로 유지하며 기존 Gap은 **13.864737209%**다. 새 restricted bound/score로 이를 대체하지 않았다.

## 10. 일반화와 남은 불확실성

날짜별 수치 계약 및 FULL Replay로 May02에 May01 Raw를 주입하지 않는다. 구체적으로 May02 이동의 필요성/최선값과 cold-start에서 새로운 최선 경로를 발견할 확률, end-to-end 성능 개선은 아직 실험하지 않았다. May01 witness inclusion 및 Native0가 성공했다고 31일 캠페인 성능을 보장하지 않는다. 원본 PR221 research files는 수정하지 않았다.

## 11. 새 Runtime/메모리

진단 중 새 Gurobi Native Optimize Runtime **0초**, Optimize/Presolve 호출 **0회**다. Native0 모델 구성/검증 wall은 43.270초, 실제 repaired Beam+shortlist 회귀 wall은 50.559초다. 해당 Native0 RSS는 약2.04GB, 사용 가능 RAM은 약16.84GB였다. 진단 후 snapshot RAM available19.20GB, Commit available45.85GB. LP score 단일 예시는 약0.07초; 전체 캠페인 iteration 속도 향상으로 환산하지 않는다. Source·ledger·1800초 예산을 초기화하지 않았다.

## 12. 재개 상태

**B2 및 B3 M HOLD 유지.** 이 Draft는 수정 검토/Native0 결과이며 production rollout이 아니다. 신규 source/policy·registry·hardware/scientific release receipt를 일관되게 동결하는 연결 작업과 사용자 재개 지시 없이 campaign을 켜지 않는다. 잔여 Native 예산을 새1800초로 바꾸지 않으며 새로운31일 run은 시작하지 않았다.

별도 증거 루트: `D:/v42_b2_stationary_diagnosis_20261013`. 보고서와 핵심 JSON/회귀 스크립트를 이 Draft에 함께 저장한다. 대형 current matrices와 모든 stopped campaign 파일은 원래 보호 경로를 유지한다.
