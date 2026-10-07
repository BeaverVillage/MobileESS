# M1 C3A root gap 진단 최종 검토

최종 분류: **ROOT_GAP_NOT_EXPLAINED_BY_TESTED_LOCAL_HULLS**. 알려진 정수 incumbent와의 약 15.04% 차이는 진짜 정수 최적 gap의 증명이 아니다. 시험한 한 슬롯 hull에서 material한 검증 하한 상승은 얻지 못했다.

순수 LP와 일부 강화 barrier 점의 RAW numerical FAIL을 유지하고 PASS 회차도 구분한다. 워크플로·해시·정수 유효성 검증과 엄격 수치 feasibility 검증을 분리해 `VERIFICATION.json`에 기록한다.

## 1. 기존 1시간 solve 중단

예. 사용자 지시에 따라 정확한 대상 프로세스만 종료했고 재시작하지 않았다.

## 2. 정확한 종료 프로세스

PID 72696, Python311/python.exe, `run_one.py --run`, cwd `C:/v42_m1_c3_native_1h_20261007`. 프로세스 생성 UTC 06:56:49.758725, solver 시작 06:56:57.606972, 종료 07:37:07.492493(16:37:07 KST). Graceful IPC가 없어 identity 확인 뒤 해당 PID만 terminate했다.

## 3. 종료 Runtime/Work

종료 시점의 native Runtime/Work는 얻지 못했다. 마지막 callback의 Runtime 346.781000137 s, Work 573.650794736는 종료보다 2,062.960724 s 오래된 관측이다. Wall 경과 2,409.744539 s를 native Runtime으로 바꾸어 쓰지 않았다.

## 4. 종료 UB/LB/gap

마지막 실제 callback UB=0.6694159238756877, LB=0.5687116103498335, native gap=15.0436089%, NodeCount=0, SolCount=1이다. 종료 시점의 bound/vector는 알 수 없다. 보존한 마지막 accepted incumbent은 원래 검증 start와 같은 SHA다.

## 5. 중단 실험의 benchmark 제외

예. 완료 1시간 benchmark, TIME_LIMIT 결과, solver failure로 분류하지 않았다. `USER_AUTHORIZED_ABORT_FOR_ROOT_GAP_DIAGNOSIS` provenance로 분리했다. Post-root의 세부 작업 종류도 로그 없이 추정하지 않았다.

## 6. 순수 LP objective

보존된 pure LP ObjVal=0.568711942993466, native OPTIMAL(2), Runtime 251.318 s, Work 481.274780, barrier 112회다. 첫 solve는 점 저장 전에 검증 assert로 capture를 잃었고, 사용자가 허용한 동일 설정 1회 추가 solve로 모든 X/Pi/RC/Slack을 저장했다. 총 순수 LP optimize는 2회다. RAW 행 위반 2.80560037424e-08>1e-8이므로 엄격 feasible point 인증은 FAIL이다.

## 7. 원래 discrete 개수

9,322개. node_activity 8,938개, charge_mode 384개. Route flow는 continuous이며 단일 DAG path/node integrality로 연결된다. 별도 route/transit/connection/PCS binary는 없다. Terminal t=96의 node도 포함했다.

## 8. 분수 개수와 비율

7,454개, 79.9613817%. node 7,070개(79.1004699%), mode 384개(100%). 판정은 1e-8<x<1−1e-8이며 전체 Σmin(x,1−x)=472.381350188이다.

## 9. 가장 분수인 계열

Fractional 비율 및 평균 min(x,1−x)는 charge_mode가 가장 크다(100%, 0.482885820). 총 분수량은 node_activity가 더 크다(286.953195285 대 185.428154903). 최대 개별 변수는 charge_mode[MESS04,69]=0.499905056385다.

## 10. 가장 분수인 MESS

MESS02의 총 분수량 118.435848441이 가장 크다. 다른 유닛도 약 117.93~118.02로 비슷하므로 특정 한 유닛에 집중된 현상은 아니다.

## 11. 가장 분수인 시간 window

최대 한 슬롯 block은 MESS04/69, 최대 4슬롯 window는 MESS02/73~76(분수량 5.996711602). 분수량의 80%에 3,504개, 90%에 5,271개 변수가 필요하다.

## 12. Location split

예. 384개 유닛/슬롯 중 377개에서 둘 이상의 connected stay site에 질량이 있었다. t72 MESS02는 약 1의 stay 질량을 여덟 사이트에 분산했다.

## 13. Route split

예. 복수 출발 MOVE route는 292개 슬롯, 같은 source/time의 arc 분기는 316개였다. 서로 다른 site stay만 있는 경우를 MOVE route split로 세지 않았다.

## 14. Move/stay 혼합

예. 출발 MOVE/STAY 혼합 316개, 진행 중 transit을 포함한 connection/transit 혼합 352개다. node_activity를 transit 중 모든 시점의 실제 location binary로 해석하지 않았다.

## 15. PCS/mode 혼합

예. mode는 384개 모두 분수이고 C,D>1e-8도 384개에 있다. 최대 min(C,D)=78.960959357 kW. 그러나 peak의 일부 충전은 약 1e-7 kW이고, mode≈0.5 자체만으로 gap 기여를 증명하지 않는다. PCS-mode local hull 위반은 별도 검증했다.

## 16. rho 임계 line/time

저장된 점의 active thermal face는 95개, 슬롯 66~95다. line.sw1::A(48), line.l3::A(1), line.l10::A(23), line.sw2::A(9), line.l116::A(12), line.l58::A(2). 대표 t72 line.sw1::A/C3 row 465244 및 t79 line.l10::A/row 497237를 원래 FULL row 축으로 복원했다.

## 17. rho 이점의 경로

t72 대표 행에서 baseline required rho 0.667834891220에 LP Pdis −0.100563786618, Q +0.001440838255, Pch 약 1.3e−10이 더해져 rho≈0.568711942988이다. Reference는 Pdis=0, Q +0.001581032656으로 rho≈0.669415923876이다. 분산 P/Q가 두 점 사이 차이를 만든다는 affine 증거는 있다. 모든 분수 배치가 정수 hull 밖이거나 이 차이 전체가 진짜 integrality gap이라는 증명은 없다.

## 18. 계열별 gap 기여

두 제한 시험에서 지배적인 gap 기여 계열을 확정할 만큼의 전역 하한 상승을 얻지 못했다. TimeLimit 결과는 해당 계열의 무관함을 증명하지 않는다. 아래 표의 LB는 diagnostic partial-MILP bound이며 해당 시험의 incumbent를 원래 all-integer 생산 UB로 쓰지 않았다.

## 19. 시험한 유효 부등식

Aggregate charge-mode/discharge-mode caps, aggregate/local connected C+D perspective, 정확한 stored PCS16 charge/discharge half-polygons union에서 나온 네 folded PCS connected facets를 검토했다. 실제 cut 선택은 위반 크기, nnz, 고정 ID 순의 작은 32개 batch였다.

## 20. 독립 유효성 증명

후보 46,136개 모두 독립 검증 PASS다. 기본 10,368개는 원래 DAG/물리 제약을 별도로 재구성하고, 4개 block의 정수 상태 13,964개·연속 꼭짓점 30,616개를 rational 계산했다. Folded 35,768개는 각 site의 원래 PCS vertices 및 보수적인 coefficient rounding을 검증했다. 변조 14건은 모두 거부됐다. 저장된 점의 최대 aggregate/local/folded 위반 19.1820303704/6.9897626252/16.7177797095도 dyadic 유리수로 정확히 재현했다(LOCAL_HULL_SEPARATION_WITNESS.json). 따라서 그 투영 좌표는 해당 유효 facet 밖이다. 원래 raw C3A feasible point 인증이나 모든 LP optimum의 위반 증명, 전역 96슬롯 hull의 완성 증명은 아니다.

## 21. Baseline 위반

Baseline 큰/작은 signed violation 판정 1e−8 기준: aggregate connected 250개, local connected 5871개, folded 2323개. Aggregate mode 두 계열은 0개다. Basic connected 위반은 모두 t66 이전이고 folded는 critical t66~95에 29개가 있다. RAW 점 인증 실패를 숨기지 않았으며 큰 구조적 위반과 작은 수치 위반을 구분했다.

## 22. Baseline LB

기존 PR162 유효 conservative global LB=0.568711600349833. Pure LP primal proxy=0.568711942993466; 실제 native LP ObjBound=-97.992210364300; 독립 exact bounded-Lagrangian LB=0.567137476140924. 세 값을 섞지 않았다.

## 23. 최고 strengthened LB

추가 제약이 정수 집합을 보존하므로 이전 global LB를 운반하고 새 exact dual certificate와 max를 취했다. 최고 유효 strengthened global LB=0.568711600349833. 마지막 approximate ObjVal=0.568711662530299는 하한 증명으로 사용하지 않았다. R1은 dual 저장이 없어 새 certificate를 만들지 않았다.

## 24. 절대 LB 변화

유효 global ΔLB=0.000000000000000. 마지막 primal proxy 변화=-2.80463166691e-07이며 이를 certified bound 상승으로 부르지 않는다.

## 25. 0.5% 목표 회수율

0.5% 기준에 필요한 LB=0.666068844256309, 기존 LB부터 필요한 상승=0.097357243906476. 검증된 상승으로 회수한 비율은 0.000000%다.

## 26. 추가 행

320행(AGGREGATE_CONNECTED_POWER 252개, FOLDED_PCS_CONNECTED_POWER 38개, LOCAL_CONNECTED_POWER 30개), 원래 행 삭제 0. Baseline 582,808행 → 실험 LP 583,128행; 열은 306,040개 그대로다. Production C3S로 채택하지 않았다.

## 27. 추가 nnz

추가 nnz 17,837, 최종 5,369,449. ΔLB/1,000행 및 ΔLB/100,000nnz는 모두 0 기준으로 계산했고 trace에 기록했다.

## 28. LP/root 비용

마지막 LP Runtime 245.878 s, Work 463.617170; recovery baseline 대비 Runtime 증분 -5.440 s. 전체 10 cut LP Runtime 합 3749.957 s. Baseline presolved 407,255/299,112/4,429,517(rows/cols/nnz)이며 각 회차 presolved 증분도 trace에 있다. Root-only는 수행하지 않았다.

## 29. 기존 start feasibility

예. 원래 start SHA be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5를 유지했다. 원래 C3A row 최대 위반 1.382773e−9, bound/integrality 위반 0 및 물리 replay PASS를 보존했다. 모든 후보 추가 행에 대한 최대 signed residual=0≤1e−8이다. Start를 수정하거나 feasibility 기준을 완화하지 않았다.

## 30. 정수 집합 보존

예. 증명된 후보와 선택 제약은 모든 원래 integer-feasible 점에 유효하므로 원래 정수 feasible set과 각 점의 P1/P2 값을 보존한다. N4/H96, 원래 route·SOC·효율·이동 에너지·P/Q·PCS16·grid·A1 authority를 바꾸지 않았다. 이 증명과 수치 LP point의 RAW FAIL은 별개다.

## 31. Material 강화 여부

아니오. 사전 material 기준 global ΔLB≥0.001을 만족하지 못했다. 10회/320 cut까지의 제한 결과이며, 남은 후보나 전역 다기간 hull의 효과가 없다는 증명은 아니다. 마지막 저장 cut LP 점의 원래 discrete 중 7,454개가 여전히 분수다. 시험 후보 중 241개는 아직 미선택 위반으로 남았다. 이 값은 남은 후보의 효과나 gap 원인 증명이 아닌 point census다.

## 32. 최종 root-only bound

해당 없음. 독립 검증된 material LB gain이 없어 조건부 C3S native root-only solve를 실행하지 않았다. 결과를 만들어 쓰지 않았고 full B&B도 재개하지 않았다.

## 33. 문제 분류와 미해결 결합

검증된 한 슬롯 PCS/connection 누락은 존재하지만 그것을 제한된 batch로 강화해도 목표 gap을 설명하는 하한 상승은 입증하지 못했다. 이전 native root는 완료됐으므로 root 미완료가 이번 문제는 아니다. 모델 크기의 영향 및 post-root 작업 종류는 이 실험으로 확정하지 않았다. 시간 간 SOC/mobility와 여러 critical grid rows의 공동 결합이 남고, barrier 수치 인증 한계도 별도로 남는다.

## 34. 다음 과학 실험 하나

다음 실험은 정확히 하나만 권고한다: MESS04의 0-based 69~72 네 슬롯에서 원래 route/stay/transit·mode·P/Q·SOC transition을 공동으로 갖는 작은 exact hull을 만들고, 고정 line.sw1::A/line.l10::A 임계 행에 연결한 유효 cut의 위반과 LP bound 효과를 검사한다. 69 출발→71 연결의 분수 이동 세 개와 이동 에너지, 71의 C/D 혼합, 72의 최대 critical-face 차이를 한 창에 포함한다. 경계 SOC를 관측 LP 값으로 고정하지 않는다. 전역 96슬롯 schedule 열거, 물리 변경, full B&B 없이 별도 요청 후 진행한다. 이번에는 실행하지 않았다.

## 35. 최종 commit / Draft PR

Base Draft PR #162 exact head `1d922c91eb27056a5ccc79c92ef18146707099ab`. Branch `codex/v42-m1-root-gap-attribution-20261007`. Draft PR: [Draft PR #167](https://github.com/BeaverVillage/MobileESS/pull/167)

최종 commit은 이 검토 문서를 포함한 Draft PR의 최종 HEAD로 식별한다. 파일에 자기 자신의 commit SHA를 넣을 수 없으므로 실제 SHA는 PR body와 최종 응답에 기록하고 Git HEAD와 대조한다.

## 선택적 정수화 실제 결과

| 계열 | native Status | Runtime(s) | native LB | 기존 LB와 max한 global LB |
|---|---:|---:|---:|---:|
| node_activity | 9 | 300.128 | 0.568711610350 | 0.568711600350 |
| charge_mode | 9 | 300.208 | 0.568711610515 | 0.568711600515 |

Status 9는 TIME_LIMIT 진단이다. 각 TimeLimit=300, Threads=1이며 다른 원래 discrete 계열은 continuous다. `native LB` 열은 실제 partial-MILP ObjBound이다. 마지막 global LB 열에만 `max(기존 LB, nextafter(native LB−1e−8, −∞))` convention을 적용했고, exact rational dual certificate로 부르지 않는다. TimeLimit 설정 300초와 실제 Runtime을 분리했다. Gurobi는 종료에 필요한 속성 계산으로 Runtime이 설정 시간을 넘을 수 있다고 명시한다 ([공식 TimeLimit 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#timelimit)). 세부 row/bound 및 복원한 integrality 오차는 개별 RESULT JSON에 남겼다.
