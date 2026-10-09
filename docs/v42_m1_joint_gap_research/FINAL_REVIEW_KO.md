# V42 M1 LB/UB 통합 연구 최종 검토

판정: **UB_IMPROVED_LB_UNCHANGED**. 신규 independently certified Global LB **0.5675886811427069**, independently validated integer Global UB **0.6063186498423855**, Certified Global Gap **약 6.3877251194%**다. 0.5% 목표는 False이며 `M1_ACCEPTED=false`, P2 certificate=null이다. 증거 무결성 PASS와 목표 달성을 구별한다.

| 비교 범위 | LB | UB | Gap |
|---|---:|---:|---:|
| 보존된 M188 native authority | 0.5687116104049206 | 0.6284141956452488 | 9.500515051068552% |
| 기존 native LB + 신규 strict RAW UB 비교 | 0.5687116104049206 | 0.6063186498423855 | 6.2025206461% |
| 이번 fresh exact certificate + strict RAW UB | 0.5675886811427069 | 0.6063186498423855 | 6.3877251194% |

두 번째 행의 native LB를 새 exact 인증으로 재분류하지 않았다. 과거 높은 hull exact claim은 전체 projection/계수 증명을 새로 재평가하지 않아 자동 채택하지 않았다. 정확한 분수와 outward Gap 상한은 `JOINT_LB_UB_GAP.json`에 있다.

## 동결과 실행 보존

작업공간은 `D:\MobileESS_v42`, 브랜치는 `v42`, 실행 시작 HEAD는 `3019dd59ee70241407dc6f9e70016de1e67d9385`다. 최종 commit HEAD는 clean commit 후 생성하는 루트 `V42_INTEGRATION_READY.json`에 기록한다. A186 `9a1b41260aff3bc70d2e36d7e1c293c03ea114de`, 완료 M188 `4b19e85089171729a3225529a40cb00bf31f43d5`, scientific PR162 C3A `1d922c91eb27056a5ccc79c92ef18146707099ab`를 고정했다.

May01 1,499-job, 4대/24지점/96슬롯/9,322 binary, 원본 `min rho_max` 문제만 연구했다. Scientific case SHA는 `cb3e1c040e2e52308995708b60e7451ca43d73a2dacfeb4a18c8e8e1cfb8293a`다. C3A 582,808행/306,040열과 원본 FULL 961,472행/316,743열의 입력·축·계수·RHS·objective·bounds·types를 보존했다. May12 1,782-job A1 P1-only 입력에 결과를 전용하지 않았다. `v42_unified`, `V42_CONFIG.json`, production evidence backend 및 A1 인증서는 변경하지 않았다. C: 원본은 SHA 검증 후 D: 복사본으로 사용했다.

등록 순서 Fixed Recourse→U1→U2→Multi-time R LP→R MILP→전체 C3A count leaf0→leaf1을 보존했다. 실행 중 solver/model/callback/파라미터를 변경하거나 중단·재시작하지 않았다. PR190 scalar solver를 병합하거나 반복하지 않았다. 전체 B1, A2/M2, Actual, Fresh AC는 실행하지 않았다.

## LB 증명 범위

R은 원본 grid 행 24개를 시간·장소별로 별도 유지하고 모든 96슬롯 route/SOC/mode/PCS 행을 보존하는 **row-deletion relaxation**이다. 독립 CSR·변수축 검사로 F⊆R을 증명했다. R 자체를 원본보다 강한 Cut으로 부르지 않는다. R MILP ObjBound와 제한 neighborhood bound는 fresh exact Global LB가 아니다.

Count cover는 네 차량의 IDC09, slots70/86의 원래 binary 8개 합을 사용한다. 저장 ROOT count는 1.2793879856147246이다. 합≤1 또는 합≥2의 두 영역은 모든 정수 배정을 포함한다. 개별 halfspace는 전체 F에 유효한 cut이 아니며, **두 leaf 모두의 exact LB 중 최소값**만 전역 bound다. 각 leaf는 전체 원본 C3A 행·변수·bounds를 유지한다. 원본 정수 witness20개 full replay PASS는 보조 검증이고, 유효성의 전역 근거는 완전한 integer count coverage 정리다.

원본 CSR에서 signed dual과 finite box를 재구성하여 `b*y + min_box((c-A^T*y)*x) + ObjCon`을 exact rational로 계산했다. Native objective/ObjBound/작성기 PASS는 증명이 아니다. equality multiplier repair로 raw exact LB 0.5671374761409242에서 0.5675886811427069로 증가한 +0.0004512050017826은 수치 인증 손실 감소이며 count 모델 강화가 아니다. 신규 LB와 동일 방식으로 fresh replay한 repaired parent 대비 Δ는 0.0이다. 기존 native LB보다 높은 exact bound 및 ΔLB≥0.001의 실질적 강화는 NOT_PROVEN이다. TIME_LIMIT로 목적값/dual이 없는 경우 실제 강화량도 NOT_PROVEN으로 표시했다.

원본 thermal6행과 transformer2행을 native binding 등식으로 정확히 소거했다. thermal은 `rho ≥ affine(Pch,Pdis,Q)`로 4대×24지점의 288 P/Q항을 유지하고, transformer는 P/Q 필요조건이다. 독립 재결합 checker가 coefficient/RHS를 exact 검증하고 RHS 변조를 거부했다. 이는 원래 행의 동등한 재표현이고 새로운 강화 inequality가 아니다. 증거는 `GRID_ROW_PQ_PROJECTION_PROOF.json`이다.

## UB와 정수 승인 provenance

기존 최선 .6284141956452488을 복원하고 모든 원본 행/정수/물리를 검사한 뒤에만 MIP start로 사용했다. 오래된 C3A warmstart .6694159238756877을 best UB와 혼동하지 않았다.

| 실험 | Native Runtime초 | 검증 후 UB | 원본 full replay |
|---|---:|---:|---|
| Fixed Recourse | 24.901 | 0.6284141956452488 | PASS, 유의미한 개선0 |
| U1 | 700.188 | 0.6111419081299193 | PASS |
| U2 | 980.121 | 0.6063186498423855 | 최종 RAW strict PASS |

U1은 baseline 대비 mode20/node28/route flow29개를 바꾸며 MESS01의 STA01→IDC01(79출발/81접속), IDC01→STA01(93/95) 이동을 추가했다. U2는 U1 대비 mode26/node70/route flow77개를 바꾸고 MESS02 IDC03 지원을 앞당겨 연장했으며, MESS04 IDC09 왕복을 없애 IDC01 지원을 연장했다. IDC01 동일 시간 지원 차량이 바뀐 슬롯은9개다. U1→U2 이동에너지−14.959365205kWh, 접속 불가−3슬롯이다. 초기0~65슬롯 mode 변경은0개다. P/Q·SOC는 함께 재최적화되었으며 개별 효과의 counterfactual 인과 분해는 NOT_PROVEN이다.

원래 capture pool의 scientific tolerance 검증은3/3 PASS이나, strict literal binary 검증은2/3 PASS다. U2 capture의 복원 `arc[MESS02,2297]`가 −4.9263490181890036e−15여서 strict gate는 거부했다. 원 pool/checkpoint/ledger는 보존했다. 같은 rho를 가진 실제 `U2_RAW_POINT.npz`의 원본9,322 C3A binary와208,312 FULL binary는 모두 literal0/1이다. 최종 승인 packet은 이 Native RAW 파일을 **bytes 그대로 복사**한 것이며 rounding/clipping/repair0이다. `UB_STRICT_ADMISSION_ADDENDUM.json`과 `FINAL_ADMISSION_VIEW.json`이 vector/file SHA를 연결한다.

독립 최종 checker는 동일 Native ledger/duals/row proof를 바이트 그대로 복사한 read-only replay view에서 이 strict RAW를 검증했다. evidence 경로만 바꾸었고 원래 결과를 덮어쓰거나 새 Native 예산을 생성하지 않았다. 전체 물리 replay, terminal SOC, 실제 단일 경로4대, 이동 중P/Q0, connection, 충방전 상호배타성, PCS16, 전압·선로·변압기 및 frozen AIDC PASS다.

## 비용과 테스트

Native 누적 3805.322초, Work 6847.338042, 호출 7회다. LB/UB 합산5,400초 한도 PASS; LB 2100.112/3,600, UB 1705.210/1,800이다. 실패 호출도 ledger에 포함하며 과거 ledger와 예산은 수정하지 않았다. Threads=1, M scientific Feasibility/Optimality/IntFeasTol=1e−8, Gap=.005를 유지했다. MemLimit/SoftMemLimit·RAM 자동중단은 없다.

Runner Wall 4095.465초, optimize API Wall 합 3805.374초다. Runner의 나머지 Wall 290.091초는 모델생성·replay·certificate·I/O 등을 포함한다. R enclosing cost는 Native API Wall을 포함했던 raw 측정을 보존하고 이를 뺀 exclusive view로 보고했다. 최종 independent certificate 재평가는 추가 Native0, Wall 225.840초다. 이 review까지 단계 Wall 4782.692초, 90분 실용성 PASS=True다. 구현 준비/별도 병렬 분석/Git delivery 비용은 solver Runtime과 구별한다.

CPU는 읽기 전용 process cumulative seconds와 sample-span delta, RSS는 snapshot/OS process peak로 기록한다. 관측 시작 이전 호출의 정확한 per-call CPU/RSS는 NOT_MEASURED이며 Work를 CPU로 바꾸지 않았다. 각 호출 종료 시 Gurobi MaxMemUsed attribute와 OS RSS를 구분한다. `RESOURCE_USAGE_AUDIT.json`을 참조한다.

최종 공통/연구 테스트 549 PASS/12 SKIP/0 FAIL, Native0이다. solve-dependent SKIP은 PASS로 세지 않았다. 최종 A1 May12 P1-only·C3A 동등성/원본물리 regression PASS(Wall 346.081초), 정수 witness20개 full replay PASS, source214개 선택 M blob 및 common physics 동일성 PASS다. 원래 integration receipts를 덮어쓰지 않았다.

## 요청한10개 질문

1. **ROOT가0.5687에 머문 이유:** 저장점에서 차량·위치·시간별 mode/route/PQ가 분산되고 서로 대체한다. PR188 saved child에서 다른 차량의 P/Q와10만개 이상 route 좌표 재배분을 확인했다. 이는 관측된 relaxation 진단이며 실제 정수 최적값과의 integrality gap 크기를 증명한 것은 아니다.
2. **신규 cover가 제거한 분수 운전:** IDC09 두 시간/4차량 count≈1.2794인 저장 ROOT 배정이 두 integer halfspace를 모두 위반한다. 모든 fractional 좌표를 제거해야 한다고 가정하지 않았다.
3. **모든 정수 운전에 유효한가:** 완전한 두 분기의 union이 모든 정수 count를 포괄한다. 개별 branch를 전체 F의 cut으로 사용하지 않았다. 원본 grid 투영은 등식 결합으로 exact 유효하다.
4. **인증 Global LB 실제 상승:** fresh exact parent 대비 0.0; 기존 native authority를 넘는 material 강화는 NOT_PROVEN. 인증 손실 repair와 구조적 강화는 분리했다.
5. **실제 UB 이동·충방전 변화:** U1의 MESS01 추가왕복, U2의 MESS02 IDC03 조기·장기지원/MESS04 IDC01 역할 교환과 joint P/Q/SOC 변화다. 위 수치와 `UB_MODE_ROUTE_ATTRIBUTION.json`에 기록했다.
6. **가장 좋은 정수 운전 물리 검증:** strict Native RAW 전체 원본 행렬·binary0/1·96슬롯 물리 PASS, repair0이다.
7. **최종 Gap:** fresh independently certified 약6.3877251194%; 보존 native LB와 새 UB 비교 약6.2025206461%다.
8. **0.5%/90분:** Gap 인증 False; runner 및 review까지90분 True. Git 비용은 별도 delivery 기록이다.
9. **결정적 병목:** 계산 가능한 전체-domain joint trajectory/grid bound를 얻지 못했다. 희소한 binary count 배정 제외가 목표rho 공간의 인증 상승으로 연결되었다는 증거가 없다. LP TIME_LIMIT와 수치 인증 손실은 각각 별도로 남겼다.
10. **다음 단일 개선:** 전체96슬롯 route/mode/SOC/PCS를 보존하는 trajectory pricing을 다중 선로·시간 P/Q dual vector와 결합한 희소 column-generation relaxation 파일럿이다. 제한 trajectory catalog의 bound를 전역화하지 말고 완전 pricing closure/정수영역 포함 증명을 먼저 갖추어야 한다.

## 추가6개 질문

1. **mode만으로 회피했는가:** 과거PR169 separator .2982020918→음수, 물리좌표/rho 동일이다. 그러나 strict 원본LP7행 잔차2.8056e−8>1e−8로 `NUMERICAL_FAIL_SEPARATOR_REMOVED_ONLY`; AUXILIARY_ESCAPE_FOUND=false다. 신규count는 route를 고정하면 node-link등식에 의해 mode-only 회피 불가능을 증명했다.
2. **다른 차량·시간 대체:** 저장 PR188 child5개에서 실제 다른 차량 P/Q/경로 재배분을 관측했다. 새 count leaf는 primal X가 없어 동일검사 NOT_RUN이며 Pi로 X를 추정하지 않았다.
3. **cut 후rho 인증 LB 증가:** 최종 exact 수치가 판정 기준이다. Δ≥.001 강화 NOT_PROVEN이며 특정 위반 제거를 LB 개선으로 보고하지 않았다.
4. **UB mode/route/SOC/PQ 기여:** 실제 joint 변화와 역할교환을 정량화했다. 초기mode변경0, 개별 counterfactual 기여는 NOT_PROVEN이다.
5. **물리 상호작용과 gap:** 차량간 공간·시간 대체와 전기간 충방전/SOC/이동 연결을 보존한 증명이 필요하다. 이러한 자유도가 진단에서 남았으나 그것이 실제 정수 최적값 차이를 설명한다는 전역 인과 증명은 NOT_PROVEN이다.
6. **다음 제거할 LP 자유도:** 다중 지점·시간의 P/Q 지원을 서로 다른 fractional trajectory로 재조합하는 자유도를 완전한 경로/SOC와 grid vector로 결합하는 것에 집중한다. 유효한 정수 운전의 볼록결합 자체를 삭제하는 방식은 금지한다.

추가 감사4개 및 모든 미실행 counterfactual은 수행 여부/검증 수준/추가Native0과 NOT_RUN/NOT_PROVEN을 구분했다. 최종 승인·handoff는 `M_RESEARCH_HANDOFF_KO.md`와 기존 통합 handoff 계약을 함께 따른다.
