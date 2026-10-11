# V42 Exact C3A 현재 모델 통합·Global Gap 복구·Epoch15 전환 검토

작성 기준: 2026-10-11 20:01 KST. Exact C3A 통합·최소 검증·Epoch15 B2 재시작 및 기존 예약 전환을 완료했다. 정식 31일 캠페인은 진행 중이다. 과거 연구 성능, 단위 검사 결과, 현재 SVR11/LDC의 실측 결과를 구분한다.

최종 Scientific Source SHA: `7961f1b3a1837b017a5d8229cd1f9f7cdead95e614698da1ca8bd4be15491597`

최종 캠페인·Worker·예약 상태: Epoch15가 RUNNING이다. May01은 새 Native0 Worker에서 현재 행렬을 생성하며 May02는 RAM/Commit 신규 입장 대기다. B0 PASS31을 보존하고 B2/B1/B3 새 완료 결과는 0건이다. 기존 시간별 예약은 ACTIVE이며 기존 두 Windows 작업과 HTTP Monitor가 새 root/source를 가리킨다.

## 1. 현재 모델과 PR #162 선정 C3A의 차이

과거 PR #161 C2와 PR #162 C3A의 선정 상태는 `ULTRACOMPACT_EXACT_SELECTED`, 선정 방식은 C3A였다. [과거 선정 authority](../v42_m1_ultracompact_exact_20261006/ULTRACOMPACT_CURRENT_AUTHORITY_M1.json)와 [과거 검토](../v42_m1_ultracompact_exact_20261006/FINAL_REVIEW_KO.md)의 수치는 다음과 같다.

| 과거 동일 실험의 모델 | 행 | 열 | Binary | Nonzero |
|---|---:|---:|---:|---:|
| PR #161 기준 C2 | 654,348 | 306,040 | 9,322 | 5,584,200 |
| PR #162 선정 C3A | 582,808 | 306,040 | 9,322 | 5,351,612 |

과거 추가 삭제는 71,540행, 경계 강화는 48,551열이었다. 동일 과거 모델의 Full MILP Root LP는 212.29초에서 180.21초, Root Work는 452.05에서 359.99로 줄었다. 당시 Valid Gap 약 15.0436%는 3% 달성을 뜻하지 않는다. 이 수치를 현재 SVR11/LDC 모델의 성능으로 전용하지 않는다.

변경 전 현재 생성 경로는 원본 → Compact → Exact Static Presolve/C2까지 수행한 뒤 `C3A_policy='KEEP_ALL_REGENERATED_C2_ROWS'`를 기록했다. 이는 C2의 손실 없는 표현 및 기존 고정변수 제거를 보존하지만, PR #162의 추가 PCS/Q/종단행 삭제와 affine bound tightening을 실제 적용하지 않은 상태였다.

현재 모델에는 SVR11·LDC 및 원본 설비 전류 제약이 반영되어 있다. 따라서 과거의 삭제 인덱스·삭제량·행렬·해를 복사하지 않고 현재 생성 C2 행렬에서 같은 증명 기술을 다시 적용했다. 새 정책은 `SELECTED_EXACT_CURRENT_MATRIX_PROOFS`이다.

## 2. 실제 통합한 Exact Reduction 및 Bound Tightening

구현 경로는 원본 MILP → 기존 lossless Compact → Exact Static Presolve/C2 → 현재 행렬에서 증명한 Exact C3A이다. 새 column 축소·새 최적화 문제·새 알고리즘은 추가하지 않았다.

| 통합 기술 | 현재 행렬의 증명 및 적용 조건 |
|---|---|
| PCS 중복행 제거 | 현재 PCS16과 연결 P 제약 및 변수 경계의 exact rational 비음수 Farkas 조합을 재구성한다. 완전한 로컬 구조가 확인된 행만 삭제한다. |
| 연결 Q 행 제거 | 남은 현재 PCS facet의 exact 함의 조합이 연결 Qmax/Qmin의 원래 계수와 RHS를 증명할 때만 삭제한다. |
| 종단 위치 행 제거 | 실제 retained flow 등식의 합이 현재 종단 위치 행과 RHS에 정확히 일치하는 경우만 제거한다. |
| Affine bound tightening | 현재 4대 unit DAG의 경로 질량, PCS polygon 및 실제 injection/response 등식 정의로 support bound를 구한다. 끝점은 바깥 방향으로 반올림하며 독립 checker가 재검증한다. |
| Static Presolve·고정변수 제거 | 기존 C2의 검증된 치환·고정변수 제거를 유지한다. C3A의 retained column 축과 원본 lift 관계를 보존한다. |
| 독립 검증 | production 삭제 함수와 분리한 `current_verify.py`가 삭제행·경계·현재 CSR SHA 및 full LP/정수영역 보존을 확인한다. |

원본 목적함수 `minimize rho_max`, MESS 4대·96슬롯 이동경로, P/Q/SOC/PCS/이동에너지, AIDC 및 B3 단계별 고정 입력은 유지한다. 선로·변압기·SVR 정격과 전압 0.95~1.05 pu의 security row는 제거 대상에서 제외한다. SVR11·원본 RegControl7 탭은 백그라운드 자동제어이며 MILP 결정변수가 아니다.

현재 C3A 증명은 정수 가능영역뿐 아니라 full LP 가능영역의 보존까지 확인한다. 독립 검증이 실패한 행·경계는 Production에 채택하지 않는다.

B3의 stage batch에서 새 프로세스가 M1/M2 checkpoint를 다시 읽을 때도 selected C3A를 복원한다. 저장한 C3A CSR/data·행/열 축·삭제 인증·bound 증명·원본 FULL을 `CurrentC3A`로 재연결하고, C2는 원본 lift/transport에만 유지한다. 병합된 C3 transport를 검증하며 selected-state/source/proof SHA를 확인한다. 재시작에서 C2를 최종 C3A처럼 사용하는 경로를 수정했고, 기존 C2-only packet은 이전 복원 경로를 유지한다.

## 3. 변경 전후 현재 행·열·Binary·Nonzero 수

대표 B2 May01의 새 행렬을 생성하고 독립 증명한 실제 수치다. 과거 71,540행은 목표로 사용하지 않았다.

| 현재 SVR11/LDC 모델 | 행 | 열 | Binary | Nonzero |
|---|---:|---:|---:|---:|
| 변경 전 C2 | 1,056,220 | 353,601 | 9,326 | 12,612,466 |
| 선정 기술을 적용한 Exact C3A | 984,680 | 353,601 | 9,326 | 12,379,878 |

PCS16 53,652행, 연결 Qmax/Qmin 각각 8,942행, 종단 위치 4행을 제거했다. 총 71,540행(6.773%)·232,588 Nonzero(1.844%) 감소이며, 열·정수 축은 동일하다. 현재 변수 경계 강화는 **109,234개**로, SVR11/LDC의 추가 response 축 때문에 과거 48,551개와 다르다. injection P/Q 2,263/2,237개, transformer P/Q 14,590/14,688개, line P/Q/correction 각 25,152개다. 독립 exact fallback은 0개였으며 모든 삭제행·변경 bound의 full LP 함의를 검증했다.

C2 행렬 SHA는 `a92515e8cd0b0f28332983d68f016ef1f42d303a588ff5835d1f6e27bd8653c3`, C3A SHA는 `87262ab0f1aa9f311271c9bf387f83c39290a5a8b54d0915a565afc5b3cd9f3b`다. 원본 FULL matrix/domain SHA는 Epoch14와 bitwise 일치한다. 과거 행 인덱스 사용은 0이다.

## 4. 현재 Solver Gap과 독립 인증 Global Gap

모든 unrestricted Full MILP 호출은 `Solver_ObjVal`, `Solver_ObjBound`, `Solver_MIPGap`, 최초·최종 검증 UB, `solver_global_LB`, `solver_global_gap`, 독립 `certified_Global_LB`/`certified_gap`, Root LP·Node·Runtime을 기록한다. M 단계 결과 → Worker RESULT → 날짜 ledger → 보고서·Monitor로 같은 필드를 전달한다.

Solver MIPGap은 Solver incumbent를 사용한다. `solver_global_gap`은 독립 검증된 최종 UB와 exact equivalent 전체 C3A의 유효한 Solver ObjBound로 `(UB−LB)/abs(UB)`를 계산한다. 이는 원본 전체 가능영역에 대한 Solver 기반 평가이며 독립 rational 인증과 구분한다.

유효 Solver LB 승격은 unrestricted identity, 모든 원래 selected bounds/types/rows/objective 확인, neighborhood/Hamming 제한 없음, 원본 full LP·정수영역 동등성, 측정 가능한 Native Runtime을 모두 요구한다. U4 제한 모델의 BestBound는 승격하지 않는다. 수치 오류·미측정 Runtime·비정상 status·비유한 bound·검증 UB를 초과한 bound도 승격하지 않고 원시 진단만 남긴다.

기존 같은 case의 exact original-row dual이 있으면 독립 weak-duality·finite-box checker로 재검증한다. Gurobi MIP callback은 원본 행 Pi를 제공하지 않으므로 새 dual을 얻기 위해 별도 장시간 LP를 실행하지 않았다. 해당 독립 증거가 없으면 독립 인증 LB/Gap은 `null`이며, Full Solver Gap이 존재하면 별도로 표시한다.

M 목표는 3%이다. Full MILP는 `MIPGap=.03`, `MIPGapAbs=0`을 사용하고 유효 전체 Solver gap 목표 또는 Solver OPTIMAL에서 종료할 수 있다. 이것이 `global_gap_certified=true`라는 독립 인증 주장을 만들지는 않는다. A 단계 목표와 Native 예산은 변경하지 않았다.

개발용 대표 smoke의 실제 값: [실측 Native packet](CURRENT_RUNTIME_SMOKE.json)과 [독립 exact proof](CURRENT_EXACT_C3A_PROOF.json)를 확인했다.

| 대표 개발 검증 항목 | 실제 값 |
|---|---|
| Native Runtime / 요청 TimeLimit | 30.254999876초 / 30초 |
| Gurobi status | TIME_LIMIT (9), Native SolCount 2 |
| 최초·최종 검증 UB | 0.6760534504652341 / 0.6760534504652341 |
| Solver ObjVal | 0.6760534504652341 |
| Solver ObjBound / MIPGap | null / null; `NO_FINITE_SOLVER_BOUND` |
| 전체 Solver Global LB / Gap | null / null, 유효 bound 없음 |
| 독립 인증 Global LB / Gap | null / null, 독립 dual 증거 없음 |
| Root LP 시간 / 상태 | null / `NOT_REPORTED_OR_ROOT_INCOMPLETE` |
| B&B Node 수 | 0 |
| Full scope / 원본 FULL 가능해 / UB 비회귀 | PASS / PASS / PASS |
| 적용한 MIPGap / MIPGapAbs | 0.03 / 0 |

MIP Start가 실제 채택됐다. Presolve 29.95초 뒤 시간 제한에 도달했으며 native log에 Root relaxation 기록이 없다. 따라서 이 호출의 Gap은 0%나 100%가 아니라 미측정이다. 요청 TimeLimit 대비 0.255초 종료 비용도 실측 Native ledger에 포함됐으며 1,800초 누적 예산은 초과하지 않았다. 정식 May01은 아직 모델 생성 단계이므로 Solver Gap 및 Actual Fresh는 대기 상태다.

정식 Epoch15의 실시간 값은 별도 운영 snapshot에 기록한다. 개발 smoke의 해·Gap은 정식 캠페인 결과로 승격하지 않는다.

### 짧은 smoke에서 Root LP 미완료인 경우의 판정

30초 수준의 smoke는 모델 clone의 완전성, Native 입장/측정, MIP Start 및 검증 UB 보존을 확인하는 검사이다. Root 완료·월간 성능·3% 달성의 증거로 사용하지 않는다. Root가 중단되면 log의 실제 경과 초를 기록하되 `Root_LP_status=NATIVE_LOG_ROOT_INTERRUPTED`로 구분한다. native log에 시간이 없으면 `Root_LP_seconds=null`이며 0초나 완료로 표시하지 않는다.

Solver ObjBound가 유한하고 전체-domain admission을 통과하면 Root 미완료 중에도 Solver 기반 LB/Gap은 기록할 수 있다. 예를 들어 검증 UB>0에서 유효 LB=0이면 Gap은 100%이며, 계산 결과가 없는 상태와 구분된다. 독립 certificate가 없다면 독립 인증 Gap은 계속 미인증이다. Source SHA drift로 입장이 거절된 호출은 Native 0의 admission failure이며 실행 성공·Root 성능으로 집계하지 않는다.

## 5. Root LP 시간 및 최대 RAM

현재 측정 범위와 관측값: [실측 packet](CURRENT_RUNTIME_SMOKE.json)의 최종 재개 프로세스는 C3 proof 재생성·모델 clone·짧은 Native를 포함해 peak RSS 11,191,271,424 bytes (10.423 GiB), peak private commit 12,339,372,032 bytes (11.492 GiB)를 기록했다. Gurobi 내부 MaxMemUsed는 1.906106324 GB이며 전체 프로세스 RAM과 별도 계측이다. C3 준비 965.327초는 Native·Root LP 시간이 아니다. 전체 1,800초 solve의 최대 RAM 및 완료 Root 시간은 이번 작업에서 미측정이다. 신규 M reservation은 이 peak에 1GiB 이상의 여유를 더해 13GiB로 고정했다.

보존된 Epoch14 May01 Native log는 `Root relaxation: time limit, ... 1665.13 seconds`를 기록했다. Root relaxation이 시간 제한에 도달할 때까지 1,665.13초 경과했으며, 완료 Root 시간은 미측정이다. 이 날짜의 누적 Native는 1,800.329초, 최종 검증 UB는 0.6760534504652341이다. [원본 receipt](EPOCH14_RETAINED_BASELINE.json)의 `NATIVE_LOG_REPORTED`는 시간의 log 존재를 뜻하며 Root 완료를 인증하지 않는다. 결과와 log의 SHA를 보존하고 원본 파일을 수정하지 않았다. Full clone 시점까지 관측한 프로세스 peak는 RSS 6,588,575,744 bytes, private commit 10,347,618,304 bytes다. 이 값은 완료된 전체 solve의 최대 RAM을 측정한 값이 아니다. 새 source의 짧은 smoke 및 C3A proof 재생성 관측값과 측정 범위가 다르므로 RAM 감소율도 계산하지 않는다.

과거 212.29→180.21초 및 Work 452.05→359.99는 과거의 동등 C2/C3A 쌍에 한정한다. 현재는 별도의 반복 Full C2/C3A tournament를 수행하지 않으므로 현재 Root 개선율을 추정하지 않는다. 짧은 smoke에서 Root가 미완료하면 현재 완료 Root 시간 비교는 미측정으로 보고한다.

메모리는 모델 생성 전후 RSS/private/peak 및 Solver `MemUsed`/`MaxMemUsed`를 기록한다. 기존 `model.getA()[:rows] − case.A`의 대형 sparse difference 복제를 제거하고, 단일 임시 native CSR의 indptr/indices/data를 exact 비교한 뒤 해제한다. unrestricted lower/upper/types의 불필요한 numpy 복제도 제거했다. C3A는 retained-row CSR을 한 번 생성하며 추가 column 표현을 만들지 않는다.

## 6. 기존 U4 가능해 보존과 누적 Native 예산

Phase 1은 기존 U4 이웃 탐색으로 검증된 FULL 가능해를 확보·개선한다. Phase 2는 그 raw 검증 해를 MIP Start로 전달하고 모든 neighborhood 고정 및 Hamming 제한을 제거한 전체 Exact C3A를 사용한다.

M 단계는 초기화·U4·Full MILP를 합쳐 측정 Native 1,800초를 공유한다. 예를 들어 이미 100초를 사용했으면 Full MILP의 TimeLimit은 최대 남은 1,700초다. 새 phase 진입이 ledger를 초기화하지 않는다.

각 candidate는 raw 정수·원본 행렬·96슬롯 물리 replay를 통과해야 UB pool에 들어간다. 교체는 exact rational UB가 개선될 때만 수행한다. 무해·나쁜 해·수치 오류·메모리 오류에서 이전 검증 해와 checkpoint를 유지한다. 최종 원본 재검증과 최초 대비 UB 비회귀도 확인한다.

45개 Gap/UB/예산 검사에는 실제 작은 unrestricted Gurobi 문제, U4 bound 승격 공격, 수치·미측정 runtime rejection, 이전 UB 보존, 세 M 단계의 동일 정책, LogFile override·Root 중단 parser가 포함된다. 실제 작은 fixture는 UB 0.75→0.5, Solver ObjVal/ObjBound 0.5, Solver Gap 0을 기록했으며 독립 certified Gap으로 승격하지 않았다. 이 fixture 수치는 현재 전력망 성능이 아니다.

## 7. 수행한 최소 검증과 생략한 장시간 FULL 검증

확인된 Gap/공통 M suite는 [45개 검사](GAP_TESTS.xml), orchestration/source/batch/anytime/release 연계 suite는 [125개 검사](GAP_INTEGRATION_TESTS.xml) 모두 통과했다. [B3 저장·복원과 현재 C3A 검사 41개](B3_RESTORE_TESTS.xml)는 새 프로세스에서 선택 C3A 복원을 확인하고 행렬·bound·증명·축·Source SHA 변조를 거절했다. 이 복원 검사는 Native optimizer를 호출하지 않았다. [Gap admission 검증 receipt](GAP_VALIDATION.json)는 Source SHA, 독립/solver 구분 및 추가 LB optimizer 0회를 명시한다. C3A의 수학적·builder/source fixture suite 74개, 운영/release/batch suite 30개도 통과했다. suite의 검사 수는 중복될 수 있으며 고유 검사 수로 합산하지 않는다. 현재 대표 모델의 [독립 exact proof](CURRENT_EXACT_C3A_PROOF.json), [실측 smoke](CURRENT_RUNTIME_SMOKE.json), [원본·교차 연결 receipt](CURRENT_VALIDATION_ORIGINS.json)가 최소 릴리스 근거다.

최종 메모리 해제 변경은 affine 임시 배열을 삭제하는 한 문장뿐이다. 변경 전 AST와 이 한 문장을 제외한 변경 후 AST의 동등성을 확인했고, 같은 최종 Source SHA에서 [현재 C3A 경량 검사 10개](../v42_svr11_exact_c3a_integration_20261011/CURRENT_C3A_MEMORY_TESTS.xml)가 통과했다. 이 검사도 Native optimizer를 호출하지 않았다.

채택 해의 원본 정수/제약/물리 검증과 Planning→결정 동결→Actual→Fresh OpenDSS 96슬롯 직접 실행을 유지한다. Actual 재최적화·P/Q repair는 허용하지 않는다. TIME_LIMIT 또는 독립 Global Gap 미인증만으로 검증된 FULL 가능해의 정상 종료를 실패시키지 않는다.

이번 작업에서 다음은 수행하지 않았다.

- 과거 1,536 Assignment 전체 재검증.
- 전체 모델의 중복 전수 Forensic 감사.
- 31일 전체 모델의 반복 Full C2/C3A 비교 실행.
- 여러 Solver 설정의 장시간 tournament.
- DW·Column Generation·Benders 및 별도 장시간 LP/CG 연구.
- 유효성이 증명되고 SHA 동일성이 확인된 불변 원시 입력·Forecast 민감도의 반복 재검증.

장시간 전수 재실행 생략은 candidate 검증 생략을 뜻하지 않는다. 기존 검증기 및 Actual/Fresh를 통과하지 않은 해는 FULL 가능해로 승격하지 않는다.

## 8. 새 Source SHA·Epoch Root 및 보존/재사용

최종 Scientific Source SHA: `7961f1b3a1837b017a5d8229cd1f9f7cdead95e614698da1ca8bd4be15491597`

최종 Git commit·Source checkout·Epoch Root·Release receipt: manifest의 source_commit은 `e14bf3c6afb8cdcf85862c6900fde49deee3388e`이다. Source checkout은 `D:\v42_svr11_epoch15_20261011`, Epoch Root는 `D:\v42_svr11_may_20261011_15`다. `EXACT_C3A_SUCCESSOR_READY.json` PASS, 최소 source/proof/case/Native 교차 seal PASS, Forecast31 PASS, B0 qualified31 보존, B2/B1/B3 fresh zero-start가 확인됐다. [최소 검증 요약](MINIMAL_VALIDATION_SUMMARY.json)과 [운영 전환 snapshot](OPERATIONAL_HANDOFF.json)을 보존했다. 이후 문서 commit은 science SHA를 변경하지 않는다.

Scientific Source는 실행에 쓰이는 `v42_*` Python 파일의 SHA 집합으로 고정한다. 문서·보고서 갱신은 이 science snapshot과 구분하고 원본 execution SHA를 바꾸어 과거 증거를 재라벨하지 않는다. 현재 C3A 증명·Gap 검증·Native smoke는 최종 source에 바인딩한 release contract로 검증한다. 대표 FULL 최초 생성은 construction SHA `9d3141a694adb2c2634cafa83d249c7393c5301747e27bab1bd01c1e2768d6f3`이며 당시 Native0 기록을 보존했다. 최종 SHA에서는 저장된 새 C2/FULL의 exact state·수학 소스 일치를 확인한 뒤 C3 생산·독립 검증을 다시 실행했고, 모든 행렬/도메인/행 인증/경계 인증의 동일성을 확인했다. 최종 30초 Native는 최종 SHA에서 실제 실행했다. 이 개발 과정의 해/PASS는 정식 결과로 이식하지 않는다.

Epoch14의 새 날짜 배정은 중지했다. 마지막 May03 Worker는 FULL 가능해 및 Actual Fresh 96슬롯 PASS, 측정 Native 1,800.690초로 자연 종료했다. 정상 Worker 강제 종료는 0회다. 기존 결과·Native ledger·실패 증거와 SHA/runtime 요약은 보존한다.

[저장공간 검토](STORAGE_REVIEW.json)는 과거 대용량 행렬·원시 입력·민감도·물리 검증·실패 증거를 검토했다. 증거를 보존하면서 안전하게 삭제할 수 있다고 확인된 대용량 과거 파일은 없어 보존했고, 이번 작업의 삭제량은 0 bytes다. 같은 민감도 파일은 이미 NTFS hardlink로 공유 중이다. 새 Epoch도 검증한 불변 캐시를 hardlink로 재사용한다. 임시 fixture 6개(2,537 bytes) 삭제는 자동 승인 검토가 `blocked by policy` 사유로 거절했으므로 보존하고 커밋에서 제외했다.

새 Epoch의 B2 2025-05-01~31은 모든 날짜 Native0에서 신규 최적화한다. 이전 Epoch의 해/PASS는 재사용하지 않는다. 동일성이 검증된 원시 입력·Forecast 민감도는 재사용 가능하지만 현재 변경된 MILP rows/bounds는 새로 생성한다. 같은 설비·물리 정책의 기존 B0은 Source SHA와 동일성 확인 후 보존할 수 있다.

## 9. B2 May01/02 Worker 실제 실행 상태

실제 PID·request·단계·Native 사용량·입장 상태: 2026-10-11 20:01 KST의 실제 snapshot 기준이다. May01 request는 `dates/B2/2025-05-01/attempts/attempt_01/request.json`, Source SHA는 위 최종 SHA이며 `previous_attempts=[]`, Native 예산1,800초·Threads1·target_gap0.03·retry_starts_from_native_zero=true다.

| B2 날짜 | 실제 상태 | PID | Native | Actual Fresh |
|---|---|---:|---:|---|
| May01 | RUNNING, 현재 새 FULL/Compact/Static Presolve 모델 생성 | 105376 | 0초 | 대기 |
| May02 | NOT_EXECUTED, RAM/Commit 신규 입장 대기, attempt 없음 | 없음 | 0초 | 대기 |

실제 Worker create_time은 `1791716380.3288803`, cwd는 `D:\v42_svr11_epoch15_20261011`다. 날짜별 상세 phase는 [운영 snapshot](OPERATIONAL_HANDOFF.json)과 live Monitor에서 확인한다. 최초 Worker 시작은 월간 완료를 뜻하지 않는다.

| 정책·단계 | Worker 상한 |
|---|---:|
| B0 | 기존 완료 결과 유지 |
| B2 M | 2 |
| B1 A1 | 1 |
| B3 M1 | 2 |
| B3 A2 | 1 |
| B3 M2 | 2 |

B2 완료 후 B1→B3로 진행한다. B3는 M1 31일 → 전체 M1 Barrier → A2 31일 → 전체 A2 Barrier → M2 31일의 stage batch를 유지한다. 같은 Epoch의 B1 A1은 같은 날짜 B3 A1의 문제/입력/수학적 동등성이 검증된 경우에만 재사용한다.

메모리 부족 시 신규 Worker 입장만 대기하고 정상 Worker를 강제 종료하지 않는다. 따라서 상한이 2라고 해서 RAM admission 전에 May01/02가 둘 다 실행 중이라고 기록하지 않는다. 날짜 FAIL은 다음 날짜·다음 정책을 차단하지 않는다.

## 10. 1시간 예약·Windows Supervisor·Monitor 전환

기존 1시간 Codex 예약, Windows Supervisor 및 Monitor의 새 Epoch/Source/2-Worker 정책 전환 receipt와 실제 상태: [운영 전환 receipt](OPERATIONAL_HANDOFF.json)를 확인했다. 기존 heartbeat `v42-may-b2-b3-autonomous-recovery`는 같은 이름·같은 대상 chat·시간별 주기를 유지하고 ACTIVE로 갱신했다. 별도 과거 cron은 PAUSED를 유지했다. Windows `MobileESS_V42_May_B2_B3_Autonomous_Supervisor` 및 `..._Monitor`의 action/cwd를 Source15/Root15로 갱신했고 기존 logon·5분 주기·동시 실행 정책은 보존했다. Supervisor PID72476, HTTP Monitor PID122232가 새 root/최종 SHA에서 동작하며 HTTP8796은200이다. 이전 HTTP monitor만 교체했고 healthy worker 종료 및 Native ledger reset은0회다. [Live Monitor](http://127.0.0.1:8796)는 정식 캠페인 상태를 표시한다.

Monitor는 Solver ObjVal/ObjBound/MIPGap, 검증 UB 기준 전체 Solver Global Gap, 독립 인증 LB/Gap을 구분해 표시한다. 실행 중 Native 진단은 제한 U4인지 전체 모델인지와 provisional 상태를 명시하며 최종 admission 전 독립 인증으로 표시하지 않는다. Root가 중단됐거나 값이 아직 없는 경우는 각각 중단/미측정으로 남긴다.

최종 릴리스 판정은 새 Source seal·현재 exact C3A proof·원본 동등성·짧은 측정 Native smoke·검증 UB 비회귀·보존한 물리/Actual Fresh 및 운영 전환 receipt를 근거로 PASS다. 새 정식 B2 May01/02의 Actual Fresh 결과는 아직 없으며 정상 실행 흐름에서 검증한다. 현재 완료 Root 성능 및 3% 달성은 주장하지 않는다. 개발 smoke의 해·PASS는 정식 31일 캠페인 결과로 승격하지 않는다.
