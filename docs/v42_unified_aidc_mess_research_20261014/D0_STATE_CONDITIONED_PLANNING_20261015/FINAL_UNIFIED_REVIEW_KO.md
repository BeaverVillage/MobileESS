# D0 통합 최종 검토

새 D0 공개상태 Case와 원본 A1 모델을 구성했고 SourceRev1에서25초Pilot을실행했다. 초기324/472/1300은 보존했으나 현재D0 정수FULL 계획은확보하지못했다. 원본MESS 공식UB/LB는그대로유지했다.

Pilot 후입력검증과M1/A2/M2 인터페이스를보강한최종Source는Native0 재생성에서Matrix/domain/objective의동일SHA를확인했다. Rev1 Source/Case와Native결과는별도snapshot으로보존했다. 현재Source는Native NOT_RUN이며 Rev1 Bound/Primal인증을이전하지않는다. 아래Pilot측정치는Executed Rev1에만속한다.

누적Native는292.4430000782013→318.68099999427795초, 남음41.319000005722046초다. 신규1호출의25초cap대비1.23799991607666초초과를실측그대로기록했다. Worker1/Threads1이며 원장초기화·별도예산재사용·추가자동Heavy는없다.

회귀는 기존555개ID를보존하여 총624PASS, fail0/skip0/blocked solver0다. Native0 guard는optimize/presolve/computeIIS를차단했다. Fixture는실제May01성능인증이아니다.

## 1. 6시간 Prefix 없이 초기 상태 사용

PASS. 승인 원본의 Byte/semantic을 독립 확인하고 새 D0 Issue로 사용했다. 내부24오프셋은 좌표 변환이며 평가에6시간을 추가하지 않는다.

## 2. 324 Running /472GPU/1300Pending 불변

PASS. 사이트/Gang/Elapsed/Episode 및 완료44 제외를 보존했다. 상세 classification1624행과 initial authority를 확인한다.

## 3. 미복원 Prefix Gate 제외

PASS. 새 manifest에서 historical_prefix_gate_excluded=true. 이전 Prefix 인증은 NOT_CERTIFIED로 보존하며 새 Gate에 적용하지 않는다.

## 4. Runtime·QoS/Deadline 보존

PASS 입력 보존. 실제 기다림, 원본 Q50/Elapsed/Hard metadata를 유지했다. Source protected/batch와 요청 proxy의 미확인성은 그대로이며 연구85500초 창은 실제 SLA가 아니다. 만료 Hard를 자동 연장하지 않는다.

## 5. 공개 정보 Known 분류·스케줄링

분류PASS:1624Known, 기존Unknown78 재분류. 합법 D0 Scheduling 도메인을 생성했으나 실행 가능한 최적 Known 계획은 NOT_CERTIFIED. 미래UID/완료 Planning 사용0.

## 6. Known+CC4 A1 생성

Native0 모델PASS:844129행36931변수10920902NNZ. Known/UnknownQ50/Target/achieved reserve/shortfall/CDF/carry를 구별했다. Native Pilot은 실행했으나 계획 incumbent을 확보하지 못했다.

## 7. A1/A2 FULL 및 최적성

Executed Rev1 A1 NOT_CERTIFIED:status9/Solution0. Executed Rev1 고정-MESS A행렬의 진단 ObjBound0.08280107490283846만 기록하며 현재Case Bound 또는 Joint Global LB로 쓰지 않는다. P2 호출0/NOT_RUN. 최종Source Native 및A2 NOT_RUN. Native FULL-feasible 또는 Global Optimality 인증을 주장하지 않는다.

## 8. 현재GPU·전체Signed Sensitivity Unknown

원본 CurrentEvent 알고리즘과 회귀PASS. 현재GPU/Rack/원본C1 P/Q/전체선로상 Signed minimax로 선택하며 미래Known 잠재예약을 사전veto로 쓰지 않는다. 실제D0배치는 NOT_RUN.

## 9. 실제Pending Known Pre-placement

Native0 원본 교정 회귀PASS. 실제Start+Pending+현재GPU충돌만 trigger, Source/데이터/WAN/준비/권한 재검증 후 atomic allocation한다. 실제D0교정은 NOT_RUN; 확인되지 않은 권한은 부여하지 않는다.

## 10. Unknown Site Change UID/GPUh

실제D0 NOT_RUN. UID수와GPUh는 null이며0으로 보고하지 않는다. AIDC_ACTUAL_ALLOCATION_RESULTS.csv는 실제 이벤트가 없어 헤더만 포함한다.

## 11. C0/C1/C2 실제 최대부하

세 군 모두D0 NOT_RUN/부하null. 같은 초기 상태/Planning/CC4/외생조건 계약을 공유하고 실제Known교정 결과는 정책별로 달라질 수 있다. 기존 named fixture를 실제 May01 성능으로 이전하지 않는다.

## 12. Short/Overrun·Queue/Carry

원본회귀PASS:실제완료 전 Running보호/완료GPU해제/안전Backfill/Queue와서비스carry. Planning/Online allocator에 미래완료를 노출하지 않는다. Private simulator는기존Truth bank를보유한다. 새로운D0 측정은 NOT_RUN.

## 13. 11-SVR Fresh AC

새D0 NOT_RUN. 역사 V5 Original Full96/Fresh receipt는 초기화/현재D0 계획과 별개로 보존:활성2320/완료1690/Carry630, GPU위반0/Drop0, 설치11SVR/기존7RegControl. 과거Prefix 불일치 인증은 이전하지 않는다.

## 14. 공식MESS UB 유지

PASS. Adaptive Beam→4대Joint MILP→Original FULL→Incumbent Registry를 유지. Direct Compact 기본, experimental compression/cache 기본비활성 유지.

## 15. K48 공식Global LB

PASS 방법유지. 신규D0 K48 Native와Global LB/gap은NOT_RUN/null. DW/S1/restricted Joint를 공식 방법으로 대체하지 않았다.

## 16. S1 Route와Mode 원인 분리

저장Root의Arc4307/Mode192 분수, 다중위치187/동시충방전192를 원래CSR·P/Q·SOC·Grid row로 연결했다. B/C/D의검증STAY arc4525/mode192/둘4717 고정LP를준비했다. 세LP는NOT_RUN이므로5.02% gap의 지배원인 및 가족별인과분해는NOT_CERTIFIED.

## 17. Root LP 시간 병목

역사S1 Root처리에집중:presolve6.96 및second4.76, barrier완료누적23.49, crossover6.52/rootrelax17.69, 최종Native40.174/Node1. 중첩값은 합하지 않는다. 계수1e-13~400은범위이며 조건수는미측정. 이번D0 A1은presolve12.97, barrier누적26.22에서time limit/정수해0.

## 18. 새Cut/분해 인증LB개선

없음. 같은Mode384/SOC384를 반복하지 않았고 새LB값은null. Hull/DW/full-domain pricing의선택은B/C/D인과결과와계산비용 확인 후다. 완전pricing+dualcertificate 없는restricted master는Global LB가 아니다.

## 19. Beam 점수 예측력

실제PR221 후보384(고유284)와12pool을분석했다. 반복100은보호STAY/selected55와탐색중복45로 구분했다. 늦은연결/여러Critical slot 및critical switch를기록했지만12 FULL UB가모두동일하여예측력향상은NOT_CERTIFIED. 기존SignedP/Q/SOC/Rebound를새기능으로중복하지 않았다.

## 20. 4대24노드 UB/LB개선

신규개선 없음/NOT_RUN. 역사UB0.5398310226338695/K48LB0.46498486997548166/gap13.864737209%를그Case에서만보존한다. S1 UB0.6412659669740282/bound0.609063011458436/gap5.021778%는별개다.

## 21. D0 A1→M1→A2→M2 완료

완료하지 못했다. A1 model/onePilot까지만실행했고 현재D0 FULL primal없어M1/A2/M2 Native0/Native/Actual handoff를진행하지않았다. 옛Prefix를이유로막은것이아니다.

## 22. PASS/FAIL/NOT_RUN/NOT_CERTIFIED

PASS:승인초기/Source·time·forecast literal/native model/공식MESS유지/회귀624개(기존555+신규69). FAIL로 판명된D0 모델은없다. Time limit는INFEASIBLE증명이아니다. NOT_CERTIFIED:A1 FULL/P1/P2전체closure/실제성능/새LB·Beam예측력. NOT_RUN:P2/M1/A2/M2/S1B-C-D/새K48/Actual/Fresh.

## 23. 추가Native 예산

현재남음41.319000초,30초반환여유를유지하면11.319초뿐이다. 다음권고는D0 A1 P1 cap120초+반환30초(현재잔여포함총150초,추가최소108.681초→110초증액제안)이다. Presolve/Root완료와FULL incumbent검증을먼저하고인증된P1후P2각30초×3=90초별도배분한다. S1 B/C/D는각15초×3+반환30초=75초,현재상태단독진행시추가최소33.681초→35초다. 초기A1 성공후에만M1 UB120/K48 120, A2 P1 120/P2 90, M2 UB120/K48 120의단계별상한을검토한다. 모두탐색상한이며완료·최적성을보장하지않는다. 승인한360초를넘는실험을자동실행하지않았다.

## 검토 위치

`D0_CASE_MANIFEST.json`, `D0_MAY01_SCIENCE_CASE_KO.md`, `D0_KNOWN_BACKLOG_CLASSIFICATION.csv`, `D0_KNOWN_CC4_PLANNING_AUDIT.json`, `A1_PILOT01/SOLVE/A_RESULT.json`, `A1_PILOT01/SOLVE/NATIVE_SOLVER.log`, `D0_STAGE_EXECUTION_STATUS.csv`가新D0결과권위다. `REGRESSION01/REGRESSION_RESULTS.json`은Native0회귀다. MESS의기존source분석은S1/Beam별원본identity와scope를유지한다.

실제D0 성능/최적화통합완료는미확립이다. May31/IEEE8500/자동Scheduler는HOLD이며 새branch/worktree/PR를만들지않는다.

예산 외의 Source 제한도 남아 있다. 초기1624의 보호/batch 정보 및 요청버전 proxy는 미확인이고,55 Pending의Pre-placement 권한 False와데이터/WAN준비를확인 없이True로바꾸지않았다. D0 Actual provider/typed projection은준비된Native0코드범위다. 완성된A2/M2 Source/Matrix/FULL 및실제데이터권한 handoff가없어Actual factory는NOT_CERTIFIED로닫힌다. 예산증액만으로고객SLA나실행권한을인증하지않는다.
