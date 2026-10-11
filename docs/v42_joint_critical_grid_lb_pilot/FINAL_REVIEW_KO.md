# 90초 Joint16 파일럿 독립 최종 검토

`verify.py --mode final`은 Gurobi를 import하거나 추가 optimize하지 않고 `INDEPENDENT_CERTIFICATE.json`을 생성했다. 결과는 **PASS / JOINT_LB_VALID_MATERIAL**이다. 이 검토와 아래 수치는 최초 90초 실행에만 해당한다.

원본 Source18r FULL 가능해를 Compact 물리 좌표로 옮긴 점은 보존된 143,260개 물리 행과 기존 Bounds·정수 타입을 만족한다. PR209의 16개 exact thermal 식은 원본 injection/response equality와 상수를 소거한 항등식이며, 각각 같은 rho에 적용되었다. 계수의 binary64 변환 오차를 유한 변수 Bounds로 감싸고 RHS를 외향 보정했으므로 모든 원본 가능해는 실제 Native Joint 영역에도 포함된다. 따라서 `min(native Joint16) <= min(FULL)`이다. 실제 Gurobi CSR·RHS·sense·Bounds·타입·목적함수와 ObjCon 0, rho [0,1]의 readback도 PASS다.

수치 하한은 `ObjVal` 대신 Gurobi 최소화 B&B의 **ObjBound = 0.42547778318693985**에서 가져왔다. 이를 원본의 Global LB로 해석하는 마지막 단계는 Gurobi의 수치적 global-bound 계약을 전제로 한다. 유리수 항등식·포함관계·반올림의 독립 exact 인증과 B&B 숫자의 exact 최적성 인증은 구분해야 한다. 이번 실행에 전체 exact B&B trace 인증은 없으며, MILP의 최적해도 확정하지 않았다.

검증 UB 0.6760534504652341 대비 Gap은 **37.064475760882175%**다. PR209 하한보다 0.30881312624910284, Source18r Full Solver ObjBound보다 0.1360772921014508 높아 사전 material 기준을 통과했다. 3% 목표 하한에는 도달하지 않았다. 축소 모델 incumbent는 원본 FULL 가능해로 인증하거나 새 UB로 승격하지 않았다.

Native는 Threads=1, TimeLimit=90, MIPGap=.03, MIPFocus=3, FeasibilityTol/IntFeasTol/OptimalityTol=1e-8로 한 번 실행했다. TIME_LIMIT(Status 9), Runtime 90.03500008583069초, 1 node이며 root relaxation은 완료되었다. 90초 이후 시간 한계 감지에 따른 약 0.035초 초과를 그대로 기록한다. 추가 LP, Full MILP 또는 캠페인 호출은 0회다.

Peak process RSS는 816,332,800 bytes, Windows OS peak private commit은 1,099,677,696 bytes, Gurobi MaxMemUsed는 0.858131338 GB다. 모니터 샘플의 최소 Available RAM 16,035,225,600 bytes와 Commit available 27,620,085,760 bytes는 각각 4GiB·6GiB 안전선을 유지했다. 모델 생성 후 별도 성장 reserve와 fresh 동시 Worker 검사도 통과했다. 메모리 중단, callback 오류 및 optimize 예외는 없었다.

로그에는 `Matrix range [2e-12, 4e+02]`에 대한 `large matrix coefficient range` 경고가 있다. 이를 수치 오류로 기록하지는 않지만 민감도 근거로 보존한다. `Numerical trouble`, `Numeric error`, `Out of memory`는 관찰되지 않았으며, 작은 계수 삭제 없이 Native 행 readback이 일치했다. 이 경고는 전체 exact 수치 최적성 인증을 주장할 근거가 아니다.

실행 전 고정된 수학 증거는 원본 물리 134,514행, node link 8,746행, 네 차량의 384개 에너지 보존식, C3A 삭제 물리행 71,540개 및 C2 SOC endpoint 정의 8개를 검사했다. 삭제 C2 node link 292개에 대한 추가 독립 정적 검사는 Native가 시작된 뒤 완료되어 별도 `PHYSICAL_RELATION_AUDIT_EXTENSION.json`과 `INDEPENDENT_NATIVE0_EXTENSION.json`으로 보존했다. 추가 검사는 288개 exact tautology와 4개 retained-flow implication을 확인했다. 모델 행렬·Bounds·타입·계수·파라미터는 변경되지 않았다. 최초 gate 파일·검토 코드·문서는 preregistered commit `5afca1c6`의 bytes로 복원했으며, 최종 인증은 그 고정 증거의 SHA와 실제 실행 기록을 검사했다. 추가 증거를 실행 전 검사라고 소급해서 표시하지 않는다.

이번 90초 실행은 K16을 동시에 적용하는 Compact 물리 모델이 큰 Full MILP 없이 실용적 메모리 안에서 유의미한 하한을 줄 수 있음을 보인다. 원본 전체 최적성 Gap은 여전히 크므로 결과를 계획 가능해나 Actual PASS로 사용하지 않는다. 후속 실행이나 확대 결과는 별도 실행 기록과 인증으로 판단해야 한다.
