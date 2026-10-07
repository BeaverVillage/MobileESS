# Hamming48 / 300초 최종 검토

HAMMING48_PRIMAL_IMPROVEMENT_CONFIRMED. 유효 UB 0.6339776033797229 → 0.6324498168172089, 추가 감소 0.0015277865625139553. 고정 global LB에 대한 새 gap 10.077987972%.

| 탐색 | Center UB | 반경 | Native Runtime(s) | Best valid UB | 개선 |
|---|---:|---:|---:|---:|---:|
| Hamming24 | 0.6694159238756877 | 24 | 112.52999997138977 | 0.6339776033797229 | 0.03543832049596485 |
| Hamming48 | 0.6339776033797229 | 48 | 300.1989998817444 | 0.6324498168172089 | 0.0015277865625139553 |

1. **Exact base HEAD?** 599d9ea67f6c348bfed9d1a594dc0d1eb3fd2768

2. **정확한 center incumbent?** PR169 `docs/v42_m1_gap_rootcause_20261007/UB_LOCAL_NEIGHBORHOOD_POINT.npz`의 x. rho=0.6339776033797229; SHA256=36389f34e16eaeb03b57b5b034a21cecb6aa5b6781a27899c79737412962b4cd

3. **Center replay PASS?** 예. 원래 C3A rows/bounds/B integrality 및 saved inverse·route·movement·SOC·P/Q·PCS·673920 grid rows·A1 frozen interface PASS. start 수리 0.

4. **Hamming24 정확한 정의?** 실제 PR169 solve_neighborhood.py의 원래 B 마지막 시간 인덱스64..84 선택을 복구했다. 저장된 2100 free_names와 순서까지 일치. 모든 MESS01..04의 node_activity 및 charge_mode만 포함. 나머지 B는 center로 고정, 원래 continuous bounds 유지. center=0이면 x, center=1이면 1−x를 합산.

5. **Hamming48은 반경만 달랐나?** 실험 설계의 변경은 반경24→48이다. 사용자 지시대로 center/start/outside 고정값은 새 PR169 incumbent로 갱신했다. 따라서 수치적으로 고정값과 local row 기준도 새 center를 따른다. 같은 옛 center 실험이라고 주장하지 않는다.

6. **Neighborhood B 수?** 2100 = node_activity2016 + charge_mode84.

7. **Outside fixed B 수?** 7222. 원래 B9322, C296718, 총306040 columns. 원래582808 rows에 Hamming row 한 개만 추가.

8. **Hamming48 start feasible?** 예. 독립 제한-model replay PASS, H=0, native Start 배열 bit-identical. native 수락=True.

9. **Solver 설정?** {'Threads': 1, 'TimeLimit': 300, 'Method': 2, 'NodeMethod': 1, 'Crossover': 2, 'MIPFocus': 3, 'MIPGap': 0.005, 'FeasibilityTol': 1e-08, 'OptimalityTol': 1e-08, 'IntFeasTol': 1e-08, 'Seed': 20260929, 'DegenMoves': 0}; solver 13.0.2. 모든 effective/default/nondefault parameters 별도 기록. LogFile 경로만 새 namespace. 별도 presolve call 없음.

10. **Optimize call 수?** 1회. exclusive OPTIMIZE_ONCE.json 및 single-call guard. 다음 실험 호출 0.

11. **Native status?** 9 (TIME_LIMIT). 전역 정수 최적성 증명 없음.

12. **Runtime?** 300.1989998817444 native seconds. TimeLimit300이며 실제 runtime을 그대로 보고했다.

13. **Work?** 708.4184145615152

14. **Nodes?** 85.0

15. **발견 incumbent 수?** MIPSOL 8 events(시작점과 종료시 중복 포함), new incumbent events 7(최초 center 포함), 엄격한 추가 개선 event 6; native SolCount=6. SolCount는 pool 수여서 callback event 수와 정의가 다를 수 있다. 모든 event point 저장.

16. **최선 solver objective?** 0.6324498168172089

17. **Best candidate original full replay?** True. 원래 C3A 및 frozen full physical/grid validator로 independently PASS 여부를 결정. 제한 neighborhood bound는 이 검증에 사용하지 않았다.

18. **Old valid UB?** 0.6339776033797229

19. **New valid UB?** 0.6324498168172089

20. **Absolute UB improvement?** 0.0015277865625139553

21. **Relative UB improvement?** 0.0024098431149134503 (0.240984311%)

22. **고정 valid LB로 새 global gap?** LB=0.5687116003498334; (UB−LB)/UB=0.10077987971936943, 10.077987972%. 남은 차이=0.06373821646737554이며 증명된 integrality gap이라고 부르지 않는다.

23. **Original separation 누적 제거 비율?** 0.3670756702813092 (36.707567028%); originalUB=0.6694159238756877, 누적 감소=0.0369661070584788.

24. **Hamming48 단독 current remaining separation 제거 비율?** 0.023408612318641355 (2.340861232%).

25. **H_best?** 33

26. **Radius48 boundary active?** False. 제한시간 결과이며 neighborhood 정수 optimum도 별도로 증명하지 않았다.

27. **PR169 대비 node_activity changed bits?** 32

28. **Charge_mode changed bits?** 1

29. **Changed MESS units?** 이진변수 변경: MESS01, MESS04; Pch/Pdis/Q/SOC 연속 궤적 변경: MESS01, MESS02, MESS03, MESS04

30. **Changed slots?** 이진변수 변경: [67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84]; 연속 물리 궤적 변경: [0, 1, 2, 3, 4, 5, 11, 14, 16, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 45, 53, 62, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 93, 94, 95]. MESS04 이동은 depart66/connect69 및 depart82/connect85이다. 이는 원래 route auxiliary가 도출한 결정이며, outside64..84의 원래 B는 모두 고정되어 있다.

31. **Movement 변화?** MOVE 선택 수 2→4; movement kWh 13.870119982561928→69.03977797111658. MOVE 결정 변경 2, STAY 결정 변경 32. 전체 arc 변경 목록과 depart/connect/energy 저장.

32. **Charge/discharge 변화?** 충전 활성 event 14→15, 방전 27→26; 활성여부 변경 충전1/방전25개(1e−8 kW 진단 기준). 충전 energy 442.0626395625037→435.62034393417355 kWh, 방전 385.78491822178216→327.5595713281295 kWh. 모든 unit·96 slot Pch/Pdis/Q/SOC 및 초기/말기 SOC를 저장했다.

33. **개선 critical grid rows?** line.sw2::A / slot31 / C3A row277902: 요구 rho 0.633977603380 → 0.588657544673 (감소 0.045320058707); line.sw2::A / slot28 / C3A row264242: 요구 rho 0.633977603380 → 0.616153838971 (감소 0.017823764409); line.sw2::A / slot40 / C3A row318967: 요구 rho 0.633977603380 → 0.621385946996 (감소 0.012591656383); line.sw2::A / slot72 / C3A row465542: 요구 rho 0.633977603380 → 0.630261330953 (감소 0.003716272426); line.sw2::A / slot81 / C3A row506393: 요구 rho 0.633977603380 → 0.631099625262 (감소 0.002877978117); 슬롯64..84 내 critical 예: line.sw2::A slot72 row465542: 감소 0.003716272426; line.sw2::A slot81 row506393: 감소 0.002877978117; line.sw2::A slot80 row501848: 감소 0.002549926387; line.sw2::A slot74 row474623: 감소 0.002309812408; line.sw2::A slot73 row470083: 감소 0.002277588435. 슬롯 바깥 개선도 원래 continuous 변수를 자유롭게 유지한 재최적화의 관찰이다.

34. **Global valid LB 변경?** NO. 0.5687116003498334로 유지.

35. **Neighborhood ObjBound를 global LB로 사용?** NO. native restricted ObjBound=0.6257749719677234는 해당 고정/반경 제한에서만 유효.

36. **Physics 변경?** NO. 4 MESS, time-DAG, travel energy/time, SOC dynamics/capacity/efficiency, PCS16, P/Q, grid/rating/transformer, A1 interface, P1/P2 정의 모두 유지. P2 solve 0.

37. **Tolerance 변경?** NO. native FeasibilityTol/OptimalityTol/IntFeasTol=1e−8, C3 replay=1e−8. 기존 frozen original inverse validator의 affine postsolve=1e−6, bound/route/grid=1e−8, 기존 physical subvalidator tolerance=1e−5도 그대로 유지했다. 이는 새 완화가 아니다. 후보 raw C3 vector는 변경하지 않았고 frozen route auxiliary inverse mapping만 기존 방식으로 적용했다.

38. **Solver sweep?** NO. 한 설정·한 optimize call.

39. **Primal search 전망?** 진단: diminishing. H24 gain=0.03543832049596485, H48 추가 gain=0.0015277865625139553, 비율=0.04311114469118014. 최선 점은 현재 center에서 H=33, 옛 H24 center에서 H=57이므로 어느 center의 radius24 제한에서도 제외된다. 두 center와 실제 runtime이 다르고 resource overlap도 통제하지 않아 반경만의 인과 효과로 해석하지 않는다. 전역 포화 증명 없음.

40. **단 하나의 다음 실험?** 이번 새 검증 incumbent rho=0.6324498168172089를 중심/start로 사용하고 슬롯64..84·Hamming48·동일 params·1 thread에서 TimeLimit=600초인 단일 primal 실험. center/outside 고정값을 새 incumbent로 갱신하고 시간 budget만 늘린다. 이 작업에서는 실행하지 않는다.

41. **Final classification?** HAMMING48_PRIMAL_IMPROVEMENT_CONFIRMED

42. **Final commit SHA?** 최종 40자리 HEAD는 이 Draft PR 본문의 `Final HEAD`와 사용자 최종 응답에 기록한다. 저장된 작업에서 `git rev-parse HEAD`로 동일 SHA를 확인한다. 사전등록 및 실행 source commit은 OPTIMIZE_ONCE.json에 별도로 기록한다. 자체 commit SHA를 같은 commit의 파일 내용에 넣는 순환을 만들지 않는다.

43. **Draft PR URL?** 생성 후 이 문서와 PR 본문에 기록

Grid 효과는 원래 C3A 행과 저장된 native row axes로 실제 branch/time을 복구하여 계산했다. Pch/Pdis/Q affine 기여 변화와 rho 감소의 동반 관찰은 인과 분해가 아니다. 모든 retained thermal rows를 평가하고 critical/top improvement rows를 CSV에 기록했으며, 원래 grid 전체는 별도 frozen replay로 확인했다.
