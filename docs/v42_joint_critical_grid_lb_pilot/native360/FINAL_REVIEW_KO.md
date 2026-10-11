# 사용자 승인 360초 설정 실행 독립 최종 검토

사용자의 명시적 후속 요청 `90초 짧아 360초 돌려`에 따라, 최초 90초 결과를 보존하고 같은 고정 Joint16 모델을 추가로 한 번 실행한 기록을 검사했다. 사전 `PRE_NATIVE_MODEL_REUSE_REVIEW.json`은 모델·K16·U4 start·Native0·물리 증거 8개 파일의 원본/복사 SHA 동일성과 모델 재생성 0회를 확인했다. FULL/C3A 행렬을 적재하거나 Native0를 재생성하지 않았다. Worker=1, Threads=1, TimeLimit=360이며 나머지 수학 영역과 파라미터는 최초 실행과 같다.

`verify.py --mode final --time-limit 360` 결과는 **PASS / JOINT_LB_VALID_MATERIAL**이다. Global LB로 사용하는 `ObjBound`는 **0.42547778318693985**로 최초 90초 하한과 동일하다. 검증 원본 UB 0.6760534504652341 대비 Gap은 **37.064475760882175%**다. PR209 대비 +0.30881312624910284, Source18r Full Solver Bound 대비 +0.1360772921014508을 유지하며 3% 목표는 미달이다.

이번 실행은 360초 한계에 도달하지 않았다. Status=2, Native Runtime **116.45700001716614초**, 1 node에서 설정 MIPGap=.03의 종료 기준을 만족했다. 실제 축소 문제 MIPGap은 **0.09809284281922011%**다. 이 종료 상태는 설정 허용 Gap 안의 종료이며 exact 최적성 인증을 의미하지 않는다. 두 실행을 합친 실제 Native Runtime은 **206.49200010299683초**, Optimize 호출은 총 **2회**다. Full MILP·별도 LP·캠페인 호출은 모두 0회다.

축소 모델의 새 incumbent `ObjVal=0.4258955562455018`은 독립 Joint replay를 통과했다. 행 최대 오차는 5.684341886080802e-14이며 Bounds와 Binary 최대 오차는 0이다. 별도 원시 벡터 진단에서 207,736개 continuous route_flow가 전부 정확히 0/1이고 9,322개 Binary도 정확히 0/1임을 확인했다. 점을 반올림하거나 clip하지 않았다. 그 진단은 축소 incumbent의 정수 경로를 확인하는 수치 점 검토이며 원본 FULL·Actual 가능성 인증은 아니다. 새 원본 UB로 사용하지 않는다.

같은 수치적 solver 계약 아래에서 고정 Native Joint16의 최적값은 하한 0.42547778318693985와 축소 incumbent 0.4258955562455018 사이에 있다. 남은 간격은 약 **0.0004177730585619**로, 3% 원본 Gap 목표 하한 0.6557718469512771과의 차이에 비해 매우 작다. 이번 결과는 **같은 K16 모델의 시간만 더 늘려 목표에 도달할 근거가 없다는 판단**을 지지한다. 이를 exact rational incumbent 상한이나 원본 FULL 최적값의 상한으로 확대 해석하지 않는다. 다른 제약 선택·K16 확대·가중치 반복의 실제 성능은 이번 실행으로 검증하지 않았다.

정확한 인증의 범위는 원본 FULL→Compact→Joint 포함관계, 원본 helper 소거 항등식, 실제 보존 물리 영역, 유한 Bounds를 이용한 외향 RHS 보정이다. 마지막 숫자 하한의 유효성은 실제 Native readback 및 Gurobi 최소화 B&B의 수치적 global-bound 계약을 전제로 한다. exact B&B trace 인증은 없다. 최초 Native0의 고정 증거와 사후 보강 정적 감사는 별도로 보존되었으며, 이번 추가 실행에서 행렬·계수·Bounds·타입·목적함수와 가중치를 변경하지 않았다.

Peak process RSS는 **909,983,744 bytes**, Windows OS peak private commit은 **1,123,233,792 bytes**, Gurobi MaxMemUsed는 **0.879543621 GB**다. 모니터 최소 Available RAM **16,190,054,400 bytes**, Commit available **28,987,068,416 bytes**로 안전선을 유지했다. 메모리 중단·callback 오류·optimize 예외는 없었다. 첫 실행과 같은 coefficient-range 경고를 보존했으며 numerical trouble/error 또는 메모리 부족은 관찰하지 않았다.

K16 Joint Compact 방법은 실제 정수 다기간 물리 영역을 유지하면서 작은 메모리로 유의미한 Global LB를 제공했다. 이번 추가 실행은 하한을 높이지 않았고, 고정 K16의 수치적 최적값을 좁은 범위로 제한했다. **동일 모델의 추가 시간 연장은 채택 근거가 없다.** 다른 축소 계통 설계의 검토는 이 결과와 구분해야 하며 이번 인증에는 추가 Solver 실행이 포함되지 않는다.
