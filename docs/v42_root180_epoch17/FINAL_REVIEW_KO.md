# Epoch17 Exact Reduction / Root180 최종 보고

판정: **`EXACT_REDUCTION_VALID_ROOT180_UNMET`**.

## 1. Epoch16 중단·종료 증거

신규 배정을 먼저 HOLD로 전환하고 두 Windows 예약을 Disabled, 시간별 heartbeat를 PAUSED로 유지했다. Supervisor 97960(생성시간 1791719054.0489655)을 신원 확인 후 정지했다. STOP 요청은 기록했으나 기존 Worker가 동적 STOP을 소비하지 않아 기존 누적 예산에 따른 정상 종료를 기다렸다. May01 PID112344(1791719054.888811), May02 PID118816(1791719054.9230924)의 소멸과 잔존 최적화 프로세스 0을 확인한 뒤 Supervisor만 종료했다. 최종 Native는 1800.561999797821/1800.5910000801086초이다. 누적 Native 예산 종료의 소폭 초과도 실제값으로 보존했다. Worker 원시 terminal 표시는 PASS였지만 공식 승격 없이 USER_CANCELLED_DISCARDED로 폐기했다. Epoch15의 종료시점이 확정되지 않은 IN_FLIGHT 최종 Runtime은 null이며 완료된 일부 Runtime을 전체로 대체하지 않았다. 증거: `stop_delete/MINIMAL_STOP_RUNTIME_RECEIPT_FINAL_16_development.json`, `stop_delete/HELD_CONTROLLER_TERMINATION_16_development.json`.

## 2. 기존 B2 삭제 범위

공식 Epoch14/15/16 실행 산출물 583개·1,742,385,404 bytes, 관련 C3A/Full 개발 산출물 97개·295,397,355 bytes, 합계 **680개·2,037,782,759 bytes**를 사전 allowlist·PID/생성시간·reparse/path guard로 삭제했다. 현재 PR의 순수 성능 복사본 6개·48,533 bytes를 삭제하고 혼합 문서 9개의 B2 결과를 정리했다. 이전 Source14/15/16 worktree에 남았던 순수 B2 성능 사본 16개·137,195 bytes도 삭제하고 혼합 문서 20개의 B2 결과만 정리했다. 별도 문서 합계는 22개·185,728 bytes 삭제, 29개 혼합 문서 정리이며 위 runtime-tree 680개와 중복 합산하지 않는다. 별도 임시 감사 복사본 3개·2,110 bytes도 삭제했다. B0·다른 정책·raw·Forecast·원본 계수 캐시는 보존했다. 세 범주의 실제 파일 삭제 합계는 705개·2,037,970,597 bytes이다. Git의 이전 커밋과 PR160–162의 역사 기록은 재작성하지 않았다. 정확한 대상·파일 수·용량·부재 검사는 `stop_delete/FINAL_OLD_B2_STOP_DELETE_SUMMARY.json` 및 각 inventory/receipt에 있다.

## 3. PR160–162에서 누락됐던 개선

Epoch16은 Compact→Static Presolve→지역 C3A 순서였다. PR160의 현재 sensitivity/route/PCS affine support 보안 제거와 PR161의 Q/SOC endpoint envelope 및 source node 고정이 빠져 있었다. Static Presolve의 상수·중복·비례 행 제거가 일반 보안 support 검사를 대신하지 못했다. 기존 C3A의 PCS53,652·연결Q17,884·terminal4 제거는 실제 적용되고 있었다. 이전 Source의 190,280개 행 번호를 가져오지 않고 현재 입력으로 증명을 새로 생성했다. 109,234개 기존 auxiliary 후보 감사에서 일반 치환의 NNZ/정확한 binary64 이득을 증명하지 못한 후보는 유지했다. 새롭게 소비자가 사라진 연속·무한 bounds·목적함수0 auxiliary만 정의 등식과 함께 안전하게 제거했다.

## 4. 모든 Family 비교와 증가 원인

`FINAL_ALL_FAMILY_COMPARISON.md/.json`에 모든 Original/C2/C3A Row·Column family, 개수·NNZ·추가 삭제량·증명/보존 근거를 기록했다. 과거 Original 열은 75,455행이 이미 줄어든 saved F0이며 raw original과 구분했다. PR162 대비 Epoch16 증가는 401,872행·47,561열·4 Binary·7,028,266 NNZ이다. 선로263개는 동일하지만 변압기 phase120→153, 물리 전압 node386→419이다. LDC419→838 endpoint 중복은 기존 static 단계에서 대부분 제거된다. 주요 density 증가는 lossless sparse flow와 현재 AUTO/TIME 독립 prefix 중앙차분 response의 차이로, line binding은 평균 약4.8→49 stored entries이다. AIDC 고정 입력 1152개 중1050개가 다르며 최대차54.772397564kW는 RHS/여유와 입력에 따른 response를 바꾼다. route·SOC·PCS·mode·energy·injection의 원본 block은 bitwise 동일하다. 상세: `audit/MODEL_GROWTH_CAUSES.md`. Original/최종 C3A 열 NNZ는 새 matrix에서 직접 셌다. 새 C2 열 NNZ도 삭제된 71,540행만 288개 관련 alias를 통해 정확히 투영하여 232,588 NNZ를 복원했다. C2−C3A 총차와 family별 합계가 모두 일치하며 Original/C2/C3A의 모든 행·열 family 개수와 NNZ가 숫자로 완성됐다. 추가 Native 호출이나 전체 C2 모델 재생성은 없었다.

## 5. 새로운 제거와 Exact 증명

현재 pre-C2 보안 증명은 287,097행이다: voltage_lower 46,380, voltage_upper 43,036, NormalAmps 14,686, transformer_kVA 114,252, line_thermal_face 68,743. 이 수는 static 중복과 겹칠 수 있으므로 최종 순감소와 구분한다. 사전 bound 강화는 {'SOC': 40, 'Q': 8942, 'node_activity': 4}, C3A 지역 제거는 71,540행이다. 원본 homogeneous PCS의 정확한 binary rational vertices, 비음수 unit DAG fractional flow, connected mass≤1, 현재 원본 binding을 사용했다. Producer의 outward sparse enclosure와 독립 elementary interval 재생·필요시 exact rational fallback을 모두 통과했다. SOC 합계 상계를 site perspective 삭제에 분배하지 않았고, 작은 sensitivity를 0 처리하지 않았다. 새 대표 실행은 daily skip을 꺼 full independent pre-C2/C3A proof를 기록했다. 최종 해는 원본 FULL literal integer/96-slot physical replay를 통과했다. `EXACT_SECURITY_REDUCTION_PROOF.md`, 새 `ORIGINAL_DOMAIN_EQUIVALENCE.json`, `CURRENT_EXACT_C3A_PROOF.json`이 근거다.

## 6. 전체 모델 크기

| 단계 | Rows | Columns | Binary | NNZ |
|---|---:|---:|---:|---:|
| PR162 C3A | 582,808 | 306,040 | 9,322 | 5,351,612 |
| Epoch16 C3A | 984,680 | 353,601 | 9,326 | 12,379,878 |
| 새 original | 1,130,336 | 344,967 | 208,312 | 16,432,980 |
| 새 compact | 1,139,374 | 354,005 | 9,422 | 16,650,042 |
| 새 C2 | 802,026 | 339,387 | 9,322 | 8,842,298 |
| 새 C3A | 730,486 | 339,387 | 9,322 | 8,609,710 |

Epoch16 최종 대비 순감소: 254,194행, 14,214열, 3,770,168NNZ (30.45%).

## 7. 실제 Native presolved 모델

| 실제 Full 로그 단계 | Rows | Columns | NNZ |
|---|---:|---:|---:|
| Main presolved | 624,655 | 339,287 | 8,719,504 |
| Root relaxation presolved | 555,509 | 396,854 | 7,936,819 |

실제 Full solve 로그의 두 단계를 구분했으며 별도 read-only presolve 결과로 대체하지 않았다. Main presolved NNZ는 선택 C3A보다 +109,794개이며, Root relaxation Columns는 Main presolved보다 +57,567개이다. Native 내부 변환 결과를 Production exact proof 행렬의 크기와 혼동하지 않는다. 역사적 실제 Main은 407,856/287,699/4,511,774, Root relaxation은 371,383/306,776/4,067,204이다.

## 8. 실제 Root 시간과 목표 판정

모델 생성 Wall 986.5070632999996초; Gurobi clone build 2.8481900000479072초; Presolve 66.0초; Barrier 로그 시간 558.02초; Crossover 완료 시간 미확인/null초; **완료 Root LP 미확인/null초, ROOT_INCOMPLETE**. 중단된 Root relaxation의 로그 경과시간은 532.16초이며 완료시간으로 사용하지 않는다. 완료 message의 Native elapsed 미확인/null초; 완료 이후 Native 미확인/null초. 원시 로그는 `time limit, 79764 iterations, 532.16 seconds (831.30 work units)`이며 Crossover는 시간 제한으로 종료됐다. 원시 telemetry의 Root_LP_status=NATIVE_LOG_REPORTED, callback root_completed=True는 시간 제한 message를 완료로 잘못 분류했다(불일치=True). 보고서는 원시 로그의 불완료 판정을 우선한다. Barrier는 로그에 출력된 raw timer이며 다른 phase와 기계적으로 더하지 않는다. Crossover는 Root relaxation에 포함된다. 역사 기준180.21초, 사전 공개한 약180초 허용 상한200초, 실제 달성=False. 불완료/중단 root를 달성으로 표시하지 않았다. 동일 fresh U4 point를 Full MIP Start로 전달했으며 Full Native 호출은1회, 실제 요청 cap은 600.0초, Native status는 9이다. Full 전체 Native는 API 600.2009999752045초, 원시 로그 600.19초로 서로 다른 출력 정밀도를 보존한다. 완료 Root message 뒤 다음 허용 callback에서 종료하는 runner이며, 완료 message가 없으면 cap에서 종료한다. 이 cap은 전체 월간 M 예산 1800초와 구분한다.

### 실측 성능 한계

현재 Main Presolve는 66.0초, 역사 PR162는13.06초였다. 새 선택 C3A NNZ는 8,609,710개(역사5,351,612개), Native Main presolved NNZ는 8,719,504개(역사4,511,774개)이다. 실제 로그 계수 범위는 Matrix [1e-13, 4e+02], RHS [2e-25, 2e+03]이다. FeasibilityTol/OptimalityTol1e-9는 유지했다. LDC sensitivity 두 endpoint half의 bitwise 중복과 AUTO/TIME control-prefix 중앙차분 response의 증가한 density는 직접 입력·행렬 감사로 확인했다. LDC 중복은 기존 static 단계가 대부분 흡수했고, 고정 AIDC 상수 및 time-prefix가 다른 response에는 같은 방향만으로 alias를 주장하지 않는다. 이들은 관측된 모델 차이이며, 각 차이의 Root 지연 기여시간을 별도로 계측하거나 인과 비율로 산정하지 않았다.

## 9. Solver 설정 비교

| 설정 | PR162 | 새 Full |
|---|---:|---:|
| Method/Threads/Crossover/NodeMethod | 2/1/2/1 | 2/1/2/1 |
| MIPFocus/DegenMoves/PreCrush | 3/0/1 | 3/0/1 |
| FeasibilityTol/OptimalityTol/IntFeasTol | 1e-8/1e-8/1e-8 | 1e-9/1e-9/1e-8 |
| NumericFocus/ScaleFlag | 선정 source·Native 로그 미지정(기본값) | 3/2 |
| Seed | 20260929 | 새 Full identity·Native 로그 미지정(기본값) |
| MIPGap | .005 benchmark | .03 공식 M 목표 |
| Native 한도 | 285초 benchmark | 누적1800초, 대표 Full만600초 |
| NodefileStart/Dir | 선정 source·Native 로그 미지정(기본값) | .5 / D드라이브 |

U4·A단계 알고리즘/예산·전압0.95~1.05·정격·PCS/SOC·실제 route·목적함수는 유지했다. 추가 DW/CG/Benders, parameter tournament, 전체 assignment 반복 검증은 수행하지 않았다.

## 10. Solver UB/LB/Gap

검증 UB=0.6760534504652342; Solver ObjVal=0.6760534504652342; ObjBound=0.2898247524586287; admitted Global LB=0.2898247524586287; 검증 UB 기준 Global Gap=57.129905592644725%; API MIPGap=57.129905592644725%; nodes=1.0. 전체 새 대표 누적 Native=631.3369998931885초, Full Native=600.2009999752045초. U4 BestBound는 diagnostic이며 Global LB로 사용하지 않았다. Solver bound와 독립 exact dual certificate를 구분했다. Full native error=None; LB 거절 이유=None.

## 11. 메모리

대표 프로세스 peak RSS 10,190,266,368 bytes, peak private commit 11,359,748,096 bytes; Gurobi MaxMemUsed 4.664949765 GB. 종료 관측 RAM_available 14,603,030,528 bytes, Commit_available 26,162,995,200 bytes. Windows의 system Commit_peak는 이전 실행도 포함하는 전역 고수위이며 이번 프로세스 peak로 해석하지 않았다. 프로세스 peak는 모델 생성·증명·U4·Full·최종 검증까지 이 대표 프로세스의 고수위이다. 후속 Root 검증 및 release 계약을 통과하는 경우의 Worker admission 정책은 RAM/Commit과 측정 peak+여유를 사용한다. UNMET 상태에서는 이 정책으로 새 Worker를 시작하지 않는다.

## 12. 새 Epoch SHA·May01/02 상태

Source17 `D:\v42_svr11_epoch17_20261011`, 측정 commit `5ddd2c8ebf882277c556c97c03c63373dd9b90b5`, 실행 Source SHA `d38bdce9f15feaf642934f4139e786eb1707652539e1e865ef2bf2bc0c09bc7b`. 최종 matrix SHA `d67a073fc06a7537fd585de8ff786a01a854df5ee4f52be17f39fa66da6292a9`, domain SHA `821842e0ef3a83df4bb9a6466a1f7a5e952710dd2f695801b1de168becd4d6e5`, Bound SHA `35001e4fee1aa806bda82fb3d08e7ff887a35b9b6b1cbe2856447d7299dc8736`. Full 시작 point SHA `1a1212368b833a14c225bd1ceff22ba8334fdef4e4a12c6b9a08b2a578166072`. 후속 문서 정리·Root 완료 판정 wrapper·B0 release 도구 변경은 측정한 1,258개 실행 Python SHA를 바꾸지 않는다. 수학/행렬/Bounds/수치 파라미터는 유지했고, 원시 telemetry는 보존한 채 `representative/ROOT180_COMPLETION_AUDIT.json`으로 잘못된 완료 표시를 분리했다. 현재 실제 운영 상태는 `representative/FINAL_OPERATIONAL_HOLD_RECEIPT.json`에 있다. B0 31일은 삭제 이후에도 원본 result bytes·execution SHA·보존된 물리/raw 증거를 통해 별도 재검증했다. 공식 Source17 B0/다른 정책 manifest 공개는 하지 않았다. 이전 B2 해·UB/LB/Gap을 읽거나 승격한 수는0이다.

- B2 2025-05-01: `HOLD_NOT_RELEASED`, attempts=0, attempt_paths=[], PID=None, Native=0.
- B2 2025-05-02: `HOLD_NOT_RELEASED`, attempts=0, attempt_paths=[], PID=None, Native=0.

공식 Root17 디렉터리 존재=True, 공식 manifest 존재=False, ledger 존재=False. Root180 gate가 통과하지 않아 새 공식31일 캠페인을 시작하지 않았다. Source17은 후보이며 공식 배정은 HOLD, 두 예약 Disabled·heartbeat PAUSED를 유지한다. 실제 측정값을 보존하며 재측정/확대 탐색을 자동 실행하지 않는다.

## 검증 자료

최종 통합 targeted 테스트96 passed/1 skipped(25.93초, `FINAL_TARGETED_TESTS.xml`); 시간 제한 로그·원시 로그 byte drift·timer drift를 차단하는 새 완료 판정 검사도 포함한다. 보안·C3A 독립 reviewer28 passed, 추가 domain 변조6개 거절 및 subnormal3개 통과; 구성/복원/생략모드 관련 targeted58 passed. `audit/SOURCE17_INDEPENDENT_SECURITY_REVIEW.json`은 실제 검토 source SHA에 결합되어 있다. 대표 원본 모델을 다시 생성하고 독립 증명을 수행했으며 기존 생성 matrix/가능해를 재사용하지 않았다. Root 측정과 native raw log, final replay 및 Source17 seal은 `representative/`의 receipt로 추적한다.
