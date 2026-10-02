# V42 M1 exact compact monolithic 최종 검토

## 1. M1은 MILP인가?

예. 기존과 compact 모두 같은 물리 MILP이며 sparse 선형식과 정수성만 재표현했다.

## 2. Benders를 사용했는가?

이번 실험의 master/recourse/Farkas/Phase-I 실행은 모두 0이다. 상속된 toy 회귀 테스트는 별개다.

## 3. 기존 binary는 몇 개인가?

208312

## 4. route binary는 몇 개인가?

207928

## 5. compact binary는 몇 개인가?

9422 = node 9038 + selector 0 + charge mode 384

## 6. binary reduction은?

95.476976842%

## 7. total variable은 어떻게 변했는가?

316743 → 316839; 0.030308% 증가. integer dimension 감소를 compact라고 부른다.

## 8. row는?

954560 → 972540; 원 행을 모두 보존하고 expression bounds/terminal 정의 추가.

## 9. nnz는?

8282350 → 12678118; 53.073922% 증가.

## 10. 왜 route f를 continuous로 둘 수 있는가?

DAG 단위 흐름에서 binary node의 최초 도착 지점이 1의 흐름 전부를 받아야 한다. 평행 edge에는 binary flow selector를 유지한다.

## 11. path-integrality proof는?

COMPACT_PATH_INTEGRALITY_PROOF.md의 최초 positive head-time 귀납 증명과 unit time-cut lemma. 모든 head에서 z=0/1이 핵심이다.

## 12. parallel route 문제는?

Full graph의 평행 movement group 0, full selector 0. 동일효과/상이효과 fixture에서는 ID 경로를 보존하는 보수적 binary flow selectors를 검증했다. canonical dedup은 하지 않았다.

## 13. route를 삭제했는가?

새 삭제/필터는 없다. 원 native accepted 51,322 movement record, 198,986 unit-reachable movement 모두 보존. 원 unreachable symbolic-zero는 동일하다.

## 14. Top-K가 있는가?

없다.

## 15. movement count 제한이 있는가?

새 제한은 없다. P2의 count는 원 목적 tuple에만 남아 있다.

## 16. stay arc는 어떻게 사라졌는가?

8,942개의 reachable stay binary를 connected=z−sum outgoing f로 정확히 치환했다.

## 17. connected 의미는?

해당 site/time에서 PCS 연결을 유지하는 원 stay flow이다. 0≤connected≤1 및 departure≤z를 강제한다.

## 18. P/Q authority 동일?

Pch/Pdis/Q의 원 열/범위, 연결 gating, mode coupling, PCS16 행을 모두 유지했다.

## 19. SOC 동일?

원 sparse SOC 변수와 recurrence 전체를 그대로 보존했다.

## 20. travel energy timing 동일?

원 departure slot t의 SOC[t+1] recurrence에서 동일 energy_kwh*f를 debit한다.

## 21. connect와 arrive를 구분했는가?

흐름 endpoint는 connect. arrive는 원 authority 속성이며 endpoint에 쓰지 않았다.

## 22. terminal SOC 동일?

원 terminal equality를 그대로 보존한다. Terminal node t=96 정의도 추가했다.

## 23. PCS16 동일?

16면의 모든 coefficient/scale/RHS를 그대로 치환했다. 원 모델을 relax하거나 circle로 대체하지 않았다.

## 24. voltage band 동일?

M1 Planning 0.955–1.045 p.u. 유지.

## 25. all96 grid 동일?

원 954,560 행 전체 보존. line, voltage, transformer current/kVA 포함.

## 26. original→compact mapping?

Move x→f, 비terminal outgoing flow→z, terminal incoming flow→z, 나머지 물리 변수 identity.

## 27. compact→original mapping?

Move x=f, stay x=z−sum outgoing f, 물리/charge-mode/SOC identity.

## 28. fixtures exact?

12개 exhaustive fixture PASS. 31개 original route-ID path 물리 feasibility/objective 비교. objective 최대 오차 0.0. 추가 2개 물리 feasible sequence fixture는 FEASIBLE_SEQUENCE_FIXTURES.json에 기록했다.

## 29. path census 동일?

Original과 compact의 모든 물리 feasible 경로 및 최적 경로 집합 동일. 19회 fractional movement 강제 probe 모두 infeasible.

## 30. root LP objective 동일?

Gate=True; Original=0.5718494620559795, Compact=0.5718494622717606, difference=2.1578105968700356e-10.

## 31. root relaxation이 강해졌는가?

동일 F3의 linear projection이므로 이 재표현 자체는 root feasible set을 강화하지 않는다.

## 32. root relaxation을 약화했는가?

증명상 아니다. 양방향 LP mapping과 fresh full root objective tolerance gate를 별도로 기록했다.

## 33. original root seconds?

56.675548900006106

## 34. compact root seconds?

74.84949670001515

## 35. original canary UB?

NOT_RUN/NA

## 36. compact canary UB?

NOT_RUN/NA

## 37. original canary LB?

0.5722125039436496

## 38. compact canary LB?

0.5722125039436496

## 39. original gap?

0.03224989640084286

## 40. compact gap?

0.03224989640084286

## 41. processed nodes?

Original=1.0, Compact=1.0. Open nodes 및 iterations은 각 artifact에 기록.

## 42. branch structure?

Original은 reachable arc+mode, compact는 node+필요 selector+mode로 분기한다. 실제 선택된 branch variable family는 표준 callback에서 미수집/NA이며 추정하지 않았다.

## 43. 600s improvement?

relative gap reduction=0.0, valid LB delta=0.0. 기준은 실행 전 20% 또는 0.001로 고정.

## 44. production promising?

False

## 45. heuristic 사용했는가?

과학적 route/trajectory/시간/SOC/grid restriction 또는 approximate acceptance 없음.

## 46. solver heuristics는?

두 canary 모두 Heuristics=0. 동일 global cuts/branch-and-bound 정책.

## 47. validated MIP start는?

원 UB 0.5912812634331275의 모든 물리 column과 경로를 mapping. Independent validator PASS. 실제 start accepted: C0=False, C1=False.

## 48. incumbent fixing인가?

아니다. Full M1에서는 Start만 전달했다. Fixture의 개별 경로 고정은 exhaustive verification용이다.

## 49. scientific globality 유지?

모든 원 feasible 정수 경로를 보존하는 양방향 mapping이다. Root/node에서 전역 solver bound를 사용한다.

## 50. global gap 계산 가능?

Retained original-M1 UB=0.5912812634331275, LB=0.5722125039436496, gap=0.03224989640084286. Historical stronger S2 LB를 낮추지 않았다.

## 51. 0.5% 도달?

False

## 52. P1 accepted?

False. 독립 물리 검증과 전역 gap≤0.005의 canary 증거를 의미하며 M1 production acceptance와 분리한다.

## 53. P2 실행?

NOT_RUN. 원 energy→count contract만 보존.

## 54. M1 accepted?

false 유지.

## 55. A2 실행?

NOT_RUN.

## 56. M2 실행?

NOT_RUN.

## 57. Actual 실행?

NOT_RUN, P/Q repair OFF.

## 58. Fresh AC 실행?

NOT_RUN.

## 59. Benders cut 수?

0.

## 60. Farkas 사용?

이번 실험 0.

## 61. full route authority 유지?

봉인된 원 route gzip SHA/native authority를 사용했다. 새 scientific route selector/filter 없음.

## 62. current best UB?

0.5912812634331275

## 63. current valid LB?

0.5722125039436496

## 64. inherited gap?

0.03224989640084286

## 65. 새 LB?

C0 BestBd=0.28222432055490354; C1 BestBd=0.28222432055490354. 같은 물리 전역 LB이며 inherited S2와 max하여 보고.

## 66. production 1800s 실행?

아니오. 1800초 한도는 fresh LP 테스트용이며 production MILP는 실행하지 않았다.

## 67. production authorization?

False; actual 1800초 production은 별도 사용자 승인 필요.

## 68. next step?

Promising이면 별도 승인 후 compact production. 미달이면 결과 기반 domain pruning 없이 sparse 표현의 fill-in과 presolve/branch 성능을 검토. Root gate 미통과 시 수치 또는 mapping 원인부터 해결.

## 69. Problem13 final?

false.

## 70. final verdict?

STOP_CANARY_START_NOT_ACCEPTED

## 71. 계수 치환을 어떻게 검증했는가?

187786개의 changed-row를 IEEE coefficient의 exact Fraction 합으로 전수 검증; API matrix transport도 bit-for-bit 비교.

## 72. 다른 작업 병렬 실행을 숨겼는가?

각 실행 RESOURCE receipt에 CPU/cores/RAM/pagefile/process command lines 기록. 다른 Python 존재는 STOP 조건이 아니다. 자체 full solve는 순차 실행.

## 73. S2보다 낮은 F3 root를 어떻게 해석했는가?

양 arm 모두 같은 unstrengthened F3. S2는 별도 globally valid strengthening의 원 M1 LB이며 그대로 보존. 비교 대상 strengthening을 혼동하지 않는다.

## 74. 부모 branch와 evidence는 보존했는가?

PR120 exact head에서 sibling. inherited 2365개 tracked 파일의 physical SHA 보존. 중단한 acceleration branch와 runner를 재개/혼합하지 않았다.

## 75. 재현 시 어떤 파일이 필요한가?

PR120 sealed F3 MPS와 readonly physical input caches, compact sparse snapshot 및 Start/mapping maps가 local cache에 있다. MODEL_FREEZE와 EXECUTION_FREEZE로 SHA를 검증한다. optimizer source/policy는 code commit과 연결된다.

## 76. Root에서 모든 binary를 relax했는가?

예. Original arc/mode, compact z/selector/mode 모두 [0,1] continuous. Primary dual simplex는 양쪽 TIME_LIMIT. Barrier+crossover pilot은 실제 numerical failure 후 중단했고 compact는 미실행. 자동 dual presolve no-crossover pair 및 PreDual=0 primal-presolve pair는 별도 사전등록했다. 어느 pair라도 양쪽 OPTIMAL인데 objective/mapping이 불일치하면 hard STOP한다. 선택 pair: Method=2, Crossover=0, PreDual=0. MILP canary는 최초 Method=1 정책을 유지한다. 모든 raw evidence와 등록을 보존한다.

## 77. 숫자를 기대값으로 강제했는가?

아니다. Actual reachable node 9,038개와 mode384개로 9,422개의 binary를 집계했다. 9,696 가정은 쓰지 않았다.

## 78. 수치 warning과 시간 측정은?

원 scientific matrix의 작은 coefficients를 바꾸지 않는다. Solver warning/Kappa/KappaExact, optimize wall/runtime, construct/build, presolve/root 및 peak memory를 별도로 기록했다.

## 79. Incumbent 없는 canary의 후처리는?

두 raw 600초 결과는 저장됐으나 frozen worker의 비교 단계에서 valid_global_gap 누락 KeyError가 발생했다. CANARY_WORKER_COMPLETION_RECEIPT와 console에 exit=1/traceback을 보존한다. 읽기 전용 certificates.canaries로 기존 valid UB/LB를 유지하고 안전하게 비교를 완성했다. Solver UB는 null이며 새로운 incumbent를 만들지 않았다. Missing-incumbent 회귀 테스트를 추가했다. Frozen optimizer source는 바꾸거나 재실행하지 않았다.

## 80. Start 잔차의 독립 감사 결과는?

Original/compact 모두 동일한 native equality 2개가 FeasibilityTol=1e-8을 넘었고 최대 위반은 3.0752360699604075e-8이었다. Integer fractionality와 bound 위반은 0이다. MIP_START_TOLERANCE_AUDIT.json에 행 번호/이름/RHS/잔차를 기록했다. Start/과학적 point/tolerance를 수정하지 않았으며 solver 거부의 확정 인과로 단정하지 않는다.

