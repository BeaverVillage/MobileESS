# AIDC Class 집계 원인과 Production 복구

기존 `a_engine.authorized_data`는 Job의 UID/QoS Receipt를 제외하더라도 Boundary 전체를 Class Key에 넣었다. Boundary의 UID별 `window_authority_sha256` 때문에 수학적으로 같은 Job도 분리됐다. May01에서는 1,555개 양의 잔여 서비스 Job이 1,555개 Class가 됐다. 잔여 서비스 0인 RUNNING 69개와 그 GPU 187은 별도의 원본 고정 부하로 유지한다.

공통 `table_v_dw.prepare_current_dw`는 Full Flex인 경우 검증된 LP 집계 경로를 사용한다. B1 A1, B3 A1/A2 모두 이 경로를 사용하며 날짜나 Class 수 조건은 없다. B0/B2 Reference 경로에는 DW 호출을 추가하지 않는다. B3 A1 재사용은 기존 Case/Source/행렬/Domain/목적함수/원본 FULL 재검증을 그대로 통과해야 한다.

제외하는 Key 필드는 Job의 `uid`, `qos_receipt_sha`, Boundary의 `window_authority_sha256`뿐이다. UID 원장에는 원본 Receipt 전체, 개별 Authority SHA, Boundary와 Domain SHA를 보존한다. `duration_authority_sha256` 및 나머지 수학적 속성은 제외하지 않는다. Window 수치, Runtime, CC4 Kernel/Gamma, GPU, Site/Start, WAN/Migration, Deadline, Hard Contract, 원본 Graph, 목적함수 속성을 유지한다.

Semantic Key는 후보군일 뿐이다. 실제 원본 FULL에서 추출한 모든 UID의 Local A, Global Coupling B, RHS, Bounds, Types, Objective를 독립 검사한다. May01 기존 Source의 229개 후보군은 모두 이 검사를 통과했다. 새 Source로 재발행한 입력에서도 229개 후보군의 UID 구성과 Semantic Identity가 기존 것과 정확히 같다. Source/Case 및 원본 FULL의 열 순서/SHA는 별도이며 이전 LB/UB/Gap은 이전하지 않는다.

FULL 정수 MILP는 축소하지 않았다. 기존 STAY/개별 Migration Lane 및 원본 F2-CRA 정수 모델이 UB와 Original FULL 검증의 권위다. 새로운 축약은 기존 동일 연속 Lane Sum 논리를 완전한 Local LP 블록에 적용한다. 기존 SINGLE의 분수 혼합 Flow를 다른 STAY 완화로 바꾸지 않는다.

기존 Geometry Cache도 공통 빌더에 연결했다. 검증된 Window 수치를 Key에 유지하고 각 UID Domain SHA를 원본 공식으로 다시 봉인한다. May01 재구성에서는 동일 Geometry 재사용 1,328회, 실제 생성 227회였으며, 별도 Runtime/계약 속성을 포함한 수학적 Class는 229개다. 원본 `a_engine` 함수의 코드나 전역변수를 수정하지 않는다.

31일 감사는 날짜마다 D0/Forecast/Runtime/CC4/물리 입력을 독립 컴파일한다. Class, UID, Pricing 결과, LB를 다른 날짜로 복사하지 않는다. A2는 실제 현재 M1의 Fixed-MESS가 필요하다. 해당 부모가 없는 Native0 감사에서는 이를 정확히 표시하며, A1의 Grid/인증을 A2 인증으로 대체하지 않는다. Production A2는 현재 원본 행렬의 동치성 검사를 통과하기 전에는 Native 실행에 진입하지 않는다.

이전 B1 EXECUTION05는 사용자 요청으로 협조 종료됐다. 확정 Native는 1,736.792000055313초다. 원본 Raw/원장/Source를 보존하고 `SUPERSEDED_BY_VERIFIED_CLASS_AGGREGATION`으로 구분했다. 이 표시는 이전 결과가 과학적으로 무효였다는 의미가 아니다. B0 기존 성공 결과도 그대로 보존했다.
