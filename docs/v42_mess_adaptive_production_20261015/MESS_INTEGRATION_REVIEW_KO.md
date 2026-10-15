# PR230 반복 MESS 및 공통 평가 통합 검토

PR219–221의 반복·피드백·후보 다양화와 PR222의 Global/Moving 별도 Incumbent, STAY 및 완전 이동 경로 고정, 공동 P/Q/SOC 재배분 점수를 현재 날짜·Stage의 Production M 경로에 연결했다. B2 M1과 B3 M1/M2가 같은 함수를 호출한다. 역사적 연구 모듈의 전역 Raw·과거 Pool 또는 EF 비교 실행을 가져오지 않는다.

각 반복은 현재 FULL 검증 점에서 Beam을 생성하고, 네 차량의 STAY·단일 MOVE·복수 MOVE를 유지한다(해당 물리 도메인에 합법 후보가 존재할 때). PR221의 12개 결정적 admission variant는 출발·연결 시간대, 목적지, 이동 횟수에 따른 다양성을 보존한다. PR222 JointDispatchScore는 최종 Pool의 각 경로에서 네 차량의 P/Q/SOC를 함께 다시 최적화하는 HiGHS 점수이며, 이것을 실행 가능 UB나 Global LB로 인증하지 않는다.

실제 최적화는 기존 Exact Direct A*T 원본 행 치환이다. 네 차량 One-hot 경로 선택과 원본 384 Charge Mode, Pch/Pdis/Q/SOC, 모든 전압·선로·변압기·이동에너지·종단 SOC 제약을 유지한다. 원본 행·계수·Bounds·RHS·Sense·목적함수와 Start의 정확한 역변환을 검증한다. 정적 Cache는 Source/Case/행렬/Domain/목적함수/경로 계약 SHA가 일치할 때만 재사용하고, 매 Pool의 동적 연결과 Start는 재검증한다. 경로 집합과 수학적 모델 SHA가 중복이면 Native에 진입하지 않는다.

Joint에서 관측한 현재 FULL 검증 P/Q/SOC 점과 병목 선로·상·시간대가 다음 Beam에 반영된다. Global/Moving 최선은 별도로 유지하며 더 나쁜 해는 덮어쓰지 않는다. 매 반복의 Raw와 원장을 별도 디렉터리에 보존한다. 한 번 개선하지 못했다는 이유로 탐색을 종료하지 않는다. 단일 Joint 상한 140초, 마지막 호출은 남은 Native에서 안전 반환 10초를 뺀 범위이며, Cold와 Joint는 같은 Stage 1,800초 원장에 기록한다. K48 300초는 별도 원장이다. Restricted ObjBound는 Global LB가 아니다.

B3 M1→M2는 M1 FULL 인증 Raw와 원본 변수 이름·경로를 SHA로 봉인한 후, 새 M2 원본 이름에 정확히 대응하고 Forward/Inverse가 동일한지 검사한다. M2 Original FULL 재검증을 통과한 점만 M2 UB로 등록한다. 거부된 점은 UB로 사용하지 않으며, 새 도메인에서 합법인 경로만 재배분 후보로 남긴다. 점이 없으면 기존 Cold Initializer를 사용한다. M1의 LB/UB/Gap은 이전하지 않는다.

B0–B3 공통 평가에서 Known/Unknown 관측 Job의 제출·시작·완료·Carry, 실제 Compute GPUh와 점유 GPUh, 대기·Reference 시작 편차, Source Deadline/시작 Window 위반을 동일하게 계산한다. E1 의도적 부담 예산과 Flexible 실행량은 B1/B3에만 적용한다. Source Deadline이 지난 미완료 Job도 별도 위반으로 기록한다. Changed_GPUh는 처리량으로 사용하지 않는다. Fresh AC는 기존 11 SVR/7 RegControl 정착 원본 경로를 유지한다.

새 M Source는 명시적 SHA 핀을 통해 이전 Source와 분리한다. 이전 11개 AIDC/물리 파일은 과거 정확한 바이트 핀을 유지한다. 과거 May01 PASS/LB/UB를 새 Source로 승격하지 않는다. Launch Gate는 새 Release/Git/Policy/Case/예산과 일치해야 한다.

월간 대형 Native0는 사용자 지시로 11일 완료 결과와 May08 부분 산출물을 보존하고 일시 중단했다. 나머지 날짜의 실제 A2 행렬은 현재 M1 부모가 있어야 검증할 수 있다. May02–31 Heavy는 승인되지 않았으며 실행하지 않는다. May01 네 Arm은 한 번의 명시적 새 승인 주기로 직렬 실행하며 실패 후 자동 예산 재발급을 하지 않는다. B1 실패는 B2를 차단하지 않는다.

이 문서의 구현·Native0 증거와 실제 Heavy 성능은 분리한다. 실제 호출 수·UB 변화·Warm 채택·Stage Native/Wall·Actual/Fresh 결과는 실행 원본과 최종 결과 보고서에서 확정한다.
