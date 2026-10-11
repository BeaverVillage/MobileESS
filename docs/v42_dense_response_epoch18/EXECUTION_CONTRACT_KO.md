# Source18 검증 및 단일 Root 실행 계약

Source17 `6e34a48035f5dc9ef1f1df95768c67c143cfc4c3`는 보존한다. 이 successor의 원본 입력은 보류 중인 B2 May01 입력과 실제 SVR11/LDC Forecast이며, 과거 최적화 점·UB·LB·MIP Start는 읽지 않는다.

처리는 원본 입력 → 공유 Route/SOC Physical Prescreen → 원본 행렬 생성 및 물리·계통 외접 영역 증명 → 기존 Node-Activity Compact → Source17 Security Reduction → Static Presolve → Exact C3A → Dense Response → Gurobi 순서다. 정수 경로에 대한 SOC 진단은 fractional LP zero 증명 없이 제거에 사용하지 않는다. 추가 Backward/SOC 제거 0개는 정상 완료 결과다. 기존 Forward의 구조적 0만 원본 변수 생성 전에 제외한다.

Dense 단계는 현재 저장 계수와 RHS를 사용해 동일한 전압 선형식을 공유한다. 원본 변수·경계·정수형·목적함수는 유지하며, 새 연속 Y의 등식과 저장된 유한 경계가 원래 전압 부등식과 양방향으로 동등하다. 독립 검증기가 삭제 행, 새 등식, 경계, 원본 정수·LP 사영을 재구성한다. 행 제곱 구조 지표는 실제 Presolve 또는 시간 개선 증거로 사용하지 않는다.

사용자의 최신 지시로 추가 Prescreen 제거가 0개여도 전체 독립 증명과 실제 Dense 압축이 PASS하면 Root 실험을 승인한다. Native 0에서 생성한 **동일한 live case**를 전달한다. 전체 원본 모델을 중복 생성하지 않는다. 새 초기 가능해 및 U4 결과를 원본 FULL에서 검증한 뒤 Full Native 최대 600초를 정확히 한 번 호출한다. M Native 누적 예산은 1,800초다. 실제 파라미터는 모든 override 뒤 Native 진입 전에 Readback·검증한다.

유한 목적값이 있는 실제 `Root relaxation: objective` 로그만 완료로 인정한다. 완료 시간 ≤180초면 `ROOT180_PASS`, 초과 완료면 `ROOT180_UNMET`, 미완료면 `ROOT_INCOMPLETE`다. 수치 실패·시간 제한 중단을 PASS로 바꾸지 않는다. Presolve·Barrier·Crossover의 로그 시간은 의미와 중첩을 구분하고, 실제 ObjBound/Gap/메모리와 함께 기록한다.

공식 5월 캠페인은 HOLD다. 이 개발 runner에는 캠페인 release 동작이 없다. Supervisor·예약 작업·자동 재시작을 활성화하지 않는다. 이후 Multi-Time Tightening은 이 작업·측정·Source/행렬 동결이 완료된 뒤 별도 개발 브랜치에서만 시작한다.
